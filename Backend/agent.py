"""CIRA agent: natural language -> SAP Business One data -> table + chart + summary.

Design notes
------------
* Tools return a *compact* summary to the LLM (row count, columns, aggregates,
  a few sample rows).  The full result set never enters the prompt — it is put
  on a per-request ResultBus and streamed straight to the browser.  The old
  code pushed 500 raw rows through the model, which was slow, expensive and
  frequently blew the context window.
* Datasets are emitted from the bus, not by re-parsing ToolMessage strings.
* Four SAP tools give genuinely deep access: schema search, table description,
  structured query (filters/group by/aggregates) and guarded read-only SQL for
  anything that needs joins or window functions.
* When no LLM key is configured the deterministic planner answers instead, so
  the product still works end to end (and CI can test it).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

import config
import docs_store
from sap import router as sap
from sap.charts import build_chart, detect_chart_type
from sap.entities import known_entities, normalise_table_name
from sap.types_ import QueryResult, SapDataError, SapUnavailableError

log = logging.getLogger("cira.agent")


# ─────────────────────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────────────────────
def build_llm(model: str | None = None):
    """Create the chat model, or None when no API key is configured."""
    if not config.OPENROUTER_API_KEY:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        model=model or config.MODEL_NAME,
        temperature=config.LLM_TEMPERATURE,
        timeout=config.LLM_TIMEOUT_S,
        max_retries=config.LLM_MAX_RETRIES,
        streaming=True,
        default_headers={
            "HTTP-Referer": "https://cira.local",
            "X-Title": "CIRA - Corporate Intelligence and Reporting Assistant",
        },
    )


llm = build_llm() if config.USE_LLM else None


# ─────────────────────────────────────────────────────────────────────────────
# Result bus
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Dataset:
    entity: str
    table: str
    rows: list[dict]
    columns: list[str]
    source: str
    simulated: bool
    sql: str = ""
    total_available: int | None = None
    truncated: bool = False
    elapsed_ms: int = 0
    warnings: list[str] = field(default_factory=list)


class ResultBus:
    """Collects datasets produced by tool calls during a single question."""

    def __init__(self) -> None:
        self._pending: list[Dataset] = []
        self.all: list[Dataset] = []
        self.sources: list[str] = []

    def push(self, dataset: Dataset) -> None:
        self._pending.append(dataset)
        self.all.append(dataset)

    def drain(self) -> list[Dataset]:
        out, self._pending = self._pending, []
        return out

    def note_source(self, name: str) -> None:
        if name not in self.sources:
            self.sources.append(name)


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────────────
def _summarise_numeric(rows: list[dict], columns: list[str]) -> dict:
    """Give the LLM totals so it can write an accurate one-line summary."""
    totals: dict[str, Any] = {}
    for col in columns:
        values = [r.get(col) for r in rows]
        numeric = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(numeric) >= max(2, len(rows) * 0.6) and not re.search(
            r"(num|entry|id|code|line|year|qty_no)$", col.lower()
        ):
            totals[col] = {
                "sum": round(sum(numeric), 2),
                "avg": round(sum(numeric) / len(numeric), 2),
                "min": min(numeric),
                "max": max(numeric),
            }
    return totals


def _result_to_tool_payload(result: QueryResult, note: str = "") -> dict:
    preview = result.rows[: config.LLM_PREVIEW_ROWS]
    payload = {
        "ok": True,
        "table": result.table or result.entity,
        "source": result.source,
        "simulated": result.simulated,
        "rows_returned": result.row_count,
        "total_matching_rows": result.total_available,
        "truncated": result.truncated,
        "columns": result.columns,
        "totals": _summarise_numeric(result.rows, result.columns),
        "sample_rows": preview,
        "rendered_in_ui": True,
        "note": note or (
            "The full result set is already rendered for the user as an interactive "
            "table and chart. Do not repeat the rows in your answer."
        ),
    }
    if result.warnings:
        payload["warnings"] = result.warnings
    if result.sql:
        payload["sql"] = result.sql
    return payload


def make_tools(bus: ResultBus, user_query: str, employee_id: str) -> list[StructuredTool]:
    async def sap_search_schema(keyword: str) -> dict:
        """Find SAP Business One tables and columns anywhere in the company database.

        Use this FIRST whenever you are unsure which table or field holds the data
        (for example "serial", "discount", "batch", "landed cost", "UDF").
        Searches table names, table descriptions, column names and column comments
        across the entire schema, including user-defined tables and fields.
        """
        bus.note_source("SAP schema catalog")
        try:
            return await sap.search_schema(keyword, limit=40)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def sap_describe_table(table: str) -> dict:
        """List every column (name, type, description) of one SAP B1 table or entity.

        Accepts either a physical table name (OINV, ORDR, OITM, JDT1, "@MY_UDT")
        or a friendly name (invoices, sales orders, items, journal lines).
        Also returns the row count and a few sample rows.
        """
        bus.note_source("SAP schema catalog")
        try:
            return await sap.describe_table(table, sample_rows=3)
        except SapDataError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"Could not describe {table}: {exc}"}

    async def sap_query(
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        search: str | None = None,
        year: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        group_by: list[str] | None = None,
        aggregates: list[dict] | None = None,
        order_by: list[dict] | None = None,
        limit: int = 500,
    ) -> dict:
        """Query live SAP Business One data. This is the main tool — prefer it.

        table:      physical table (ORDR, OINV, OPOR, OITM, OCRD, OHEM, JDT1, OITW ...)
                    or a friendly name (orders, invoices, purchase orders, items,
                    business partners, employees, journal lines, stock by warehouse).
        columns:    optional list of columns; omit for a sensible default set.
        filters:    list of {"column": "...", "op": "...", "value": ...} where op is one of
                    eq, ne, gt, gte, lt, lte, contains, startswith, in, between, isnull, notnull.
                    Words are translated to SAP codes automatically
                    (DocStatus "Open" -> 'O', CardType "vendor" -> 'S').
        search:     free-text match across the table's text columns.
        year/date_from/date_to: date window on the table's main date column
                    (dates as 'YYYY-MM-DD').
        group_by + aggregates: for "total/average/how many ... by ..." questions, e.g.
                    group_by=["CardName"], aggregates=[{"func":"sum","column":"DocTotal","alias":"Total"}].
                    Functions: sum, count, avg, min, max, count_distinct.
        order_by:   list of {"column": "Total", "direction": "desc"}.
        limit:      max rows (default 500, hard cap from config).

        The rows are rendered for the user automatically as an interactive table and
        chart — never paste them into your reply.
        """
        payload = {
            "table": table,
            "columns": columns or [],
            "filters": filters or [],
            "search": search or "",
            "year": year,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "group_by": group_by or [],
            "aggregates": aggregates or [],
            "order_by": order_by or [],
            "limit": limit or config.DEFAULT_ROW_LIMIT,
        }
        try:
            result = await sap.run_query(payload)
        except SapDataError as exc:
            return {"ok": False, "error": str(exc),
                    "hint": "Use sap_search_schema or sap_describe_table to find the right names."}
        except SapUnavailableError as exc:
            return {"ok": False, "error": f"SAP is unreachable: {exc}"}
        except Exception as exc:
            log.exception("sap_query failed")
            return {"ok": False, "error": str(exc)}

        bus.note_source(result.source)
        bus.push(
            Dataset(
                entity=normalise_table_name(table) or result.table,
                table=result.table,
                rows=result.rows,
                columns=result.columns,
                source=result.source,
                simulated=result.simulated,
                sql=result.sql,
                total_available=result.total_available,
                truncated=result.truncated,
                elapsed_ms=result.elapsed_ms,
                warnings=result.warnings,
            )
        )
        return _result_to_tool_payload(result)

    async def sap_sql(sql: str) -> dict:
        """Run a read-only SQL SELECT against SAP HANA for anything the structured
        tool cannot express: joins across tables, sub-queries, window functions,
        UNION, HAVING, date arithmetic.

        Rules: a single SELECT (or WITH ... SELECT) statement, no writes of any kind,
        SAP B1 table names as-is (ORDR, RDR1, OINV, INV1, OCRD, OITM ...), the
        company schema is added automatically. Always alias aggregates and keep the
        result under a few thousand rows.
        Example: SELECT T1."CardName", SUM(T0."LineTotal") AS "Revenue" FROM RDR1 T0
                 JOIN ORDR T1 ON T0."DocEntry" = T1."DocEntry" GROUP BY T1."CardName"
                 ORDER BY "Revenue" DESC
        """
        try:
            result = await sap.run_sql(sql, limit=config.DEFAULT_ROW_LIMIT)
        except SapDataError as exc:
            return {"ok": False, "error": str(exc)}
        except SapUnavailableError as exc:
            return {"ok": False, "error": f"SAP is unreachable: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"SQL failed: {exc}"}

        bus.note_source(result.source)
        bus.push(
            Dataset(
                entity="SQL result",
                table=_guess_table_from_sql(sql),
                rows=result.rows,
                columns=result.columns,
                source=result.source,
                simulated=result.simulated,
                sql=result.sql,
                truncated=result.truncated,
                elapsed_ms=result.elapsed_ms,
            )
        )
        return _result_to_tool_payload(result)

    async def query_company_docs(query: str) -> dict:
        """Search internal company policy documents (travel, expenses, procurement,
        credit & collections, data security). Use for "what is our policy on ..."
        questions — not for ERP figures.
        """
        bus.note_source("Company Knowledge Base")
        hits = await asyncio.to_thread(docs_store.search, query, 3)
        if not hits:
            return {"ok": True, "matches": [], "note": "No policy document matched that question."}
        return {"ok": True, "matches": hits}

    return [
        StructuredTool.from_function(coroutine=sap_query, name="sap_query",
                                     description=sap_query.__doc__),
        StructuredTool.from_function(coroutine=sap_search_schema, name="sap_search_schema",
                                     description=sap_search_schema.__doc__),
        StructuredTool.from_function(coroutine=sap_describe_table, name="sap_describe_table",
                                     description=sap_describe_table.__doc__),
        StructuredTool.from_function(coroutine=sap_sql, name="sap_sql",
                                     description=sap_sql.__doc__),
        StructuredTool.from_function(coroutine=query_company_docs, name="query_company_docs",
                                     description=query_company_docs.__doc__),
    ]


def _guess_table_from_sql(sql: str) -> str:
    m = re.search(r'\bFROM\s+"?([A-Za-z_@][\w@$#]*)"?', sql, re.IGNORECASE)
    return (m.group(1).upper() if m else "SQL")


# ─────────────────────────────────────────────────────────────────────────────
# SSE helpers
# ─────────────────────────────────────────────────────────────────────────────
def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_DIVIDER = re.compile(r"^\s*[-=]{3,}\s*$")
_ROW_DUMP = re.compile(r"^\s*\d+[.)]\s+.*\|")


class TextFilter:
    """Streams the model's prose but suppresses raw data dumps line by line."""

    def __init__(self) -> None:
        self.buffer = ""
        self.suppress = False

    def feed(self, text: str) -> str:
        self.buffer += text
        out = []
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if self._keep(line):
                out.append(line + "\n")
        return "".join(out)

    def flush(self) -> str:
        line, self.buffer = self.buffer, ""
        return line if self._keep(line) else ""

    def _keep(self, line: str) -> bool:
        if not self.suppress:
            return True
        stripped = line.strip()
        if not stripped:
            return True
        if _TABLE_LINE.match(line) or _DIVIDER.match(stripped) or _ROW_DUMP.match(line):
            return False
        return True


def dataset_events(dataset: Dataset, user_query: str) -> list[dict]:
    """Build the tabular + chart SSE payloads for one dataset."""
    events: list[dict] = []
    rows = dataset.rows[: config.MAX_STREAMED_ROWS]
    events.append(
        {
            "type": "tabular",
            "entity": dataset.entity or dataset.table or "SAP Data",
            "data": rows,
            "meta": {
                "source": dataset.source,
                "simulated": dataset.simulated,
                "table": dataset.table,
                "columns": dataset.columns,
                "rowCount": len(dataset.rows),
                "totalAvailable": dataset.total_available,
                "truncated": dataset.truncated or len(dataset.rows) > len(rows),
                "elapsedMs": dataset.elapsed_ms,
                "sql": dataset.sql,
                "warnings": dataset.warnings,
            },
        }
    )
    chart = build_chart(
        rows,
        dataset.table or dataset.entity,
        user_query=user_query,
        entity_label=dataset.entity or dataset.table,
        simulated=dataset.simulated,
    )
    if chart:
        events.append(chart)
    return events


SYSTEM_PROMPT = """You are CIRA (Corporate Intelligence & Reporting Assistant), the executive \
analytics agent for the SAP Business One company database '{schema}' on SAP HANA. \
You are talking to employee '{employee}'.

DATA ACCESS
- `sap_query` — structured query over any SAP B1 table: filters, free-text search, date \
windows, GROUP BY and aggregates. Use it for almost everything.
- `sap_sql` — read-only SELECT for joins, sub-queries and window functions \
(e.g. revenue per item = RDR1/INV1 joined to their header).
- `sap_search_schema` / `sap_describe_table` — use these when you are not certain which \
table or column holds a field. Never guess a column name twice: look it up.
- `query_company_docs` — internal policies (travel, expenses, procurement, credit, security).

SAP B1 FACTS YOU MUST USE
- Header/line pairs: ORDR/RDR1 (sales orders), OINV/INV1 (A/R invoices), OPOR/POR1 \
(purchase orders), OPCH/PCH1 (A/P invoices), ODLN/DLN1 (deliveries), OQUT/QUT1 (quotations).
- Masters: OCRD (business partners; CardType C=customer, S=vendor, L=lead), OITM (items), \
OITW (stock per warehouse), OWHS (warehouses), OHEM (employees), OACT (G/L accounts), \
OJDT/JDT1 (journal entries), OINM (stock movements), OOPR (opportunities).
- Document status lives in DocStatus: 'O' = open, 'C' = closed; CANCELED = 'Y'/'N'. \
Amounts are DocTotal (header) and LineTotal (line). Dates: DocDate, DocDueDate.
- The tools translate the words "open", "closed", "customer", "vendor" into these codes \
for you — just pass them as filter values.

HOW TO ANSWER (STRICT RAG & GROUNDEDNESS RULES)
1. You are STRICTLY a Retrieval-Augmented Generation (RAG) assistant for SAP Business One.
2. NEVER use pre-trained world knowledge, general knowledge, or hypothetical guesses to answer questions about company business, financials, invoices, inventory, sales, or partners.
3. You MUST call a tool (`sap_query`, `sap_sql`, `sap_describe_table`, `sap_search_schema`, or `query_company_docs`) to retrieve the exact records before answering.
4. If a tool returns no data, empty records, or an error, state clearly: "No records found in the SAP database for this query." Do NOT synthesize, estimate, or make up sample data.
5. If a tool returns an error, read it: it usually names the correct table or column. Fix the call and retry (at most twice) before explaining the problem.
6. The UI automatically renders the returned rows as an interactive, sortable, exportable table plus a chart. NEVER write markdown tables, bullet dumps of rows, or long lists.
7. Reply with 1–3 short sentences of executive insight based ONLY on the retrieved data. Use the `totals` the tool gives you.
8. If the data is flagged `simulated: true`, state clearly that this is local sandbox data because the live HANA connection is unavailable.
9. Be completely honest about data limits: if something is not in the ERP records retrieved, state that clearly.

Available entity shortcuts: {entities}
"""


def _build_messages(query: str, history: list, employee_id: str, schema: str) -> list:
    entity_hint = ", ".join(
        f"{e['table']} ({e['aliases'][0]})" for e in known_entities()[:40]
    )
    messages = [
        SystemMessage(
            content=SYSTEM_PROMPT.format(
                schema=schema, employee=employee_id, entities=entity_hint
            )
        )
    ]
    for msg in history[-12:]:
        role = getattr(msg, "role", None)
        content = (getattr(msg, "content", "") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content[:4000]))
        elif role == "assistant":
            messages.append(AIMessage(content=content[:4000]))
    messages.append(HumanMessage(content=query))
    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str = "",
    employee_id: str = "UNKNOWN",
) -> AsyncGenerator[str, None]:
    bus = ResultBus()
    backend = None
    try:
        backend = await asyncio.to_thread(sap.get_active_backend)
    except Exception as exc:  # pragma: no cover
        log.warning("backend probe failed: %s", exc)

    schema = getattr(backend, "schema", config.HANA_SCHEMA)
    if backend is not None:
        yield sse(
            {
                "type": "backend",
                "name": backend.name,
                "schema": schema,
                "simulated": backend.simulated,
            }
        )

    if llm is None:
        async for chunk in _deterministic_stream(query, bus, employee_id):
            yield chunk
        yield sse({"type": "done"})
        return

    tools = make_tools(bus, query, employee_id)
    from langgraph.prebuilt import create_react_agent

    agent = create_react_agent(llm, tools)
    messages = _build_messages(query, history, employee_id, schema)
    text_filter = TextFilter()
    emitted_any_text = False

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": config.AGENT_RECURSION_LIMIT},
        ):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                content = getattr(chunk, "content", "") if chunk is not None else ""
                if isinstance(content, list):  # some providers stream content blocks
                    content = "".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                if content:
                    visible = text_filter.feed(content)
                    if visible:
                        emitted_any_text = True
                        yield sse({"type": "chunk", "text": visible})

            elif kind == "on_tool_start":
                name = event.get("name", "")
                label = {
                    "sap_query": "Querying SAP Business One…",
                    "sap_sql": "Running SQL on SAP HANA…",
                    "sap_search_schema": "Searching the SAP schema…",
                    "sap_describe_table": "Reading table definition…",
                    "query_company_docs": "Searching company policies…",
                }.get(name, f"Running {name}…")
                yield sse({"type": "status", "text": label, "tool": name})

            elif kind == "on_tool_end":
                for dataset in bus.drain():
                    text_filter.suppress = True
                    for payload in dataset_events(dataset, query):
                        yield sse(payload)
                for source in bus.sources:
                    yield sse({"type": "source", "name": source})

        tail = text_filter.flush()
        if tail.strip():
            emitted_any_text = True
            yield sse({"type": "chunk", "text": tail})

        if not emitted_any_text:
            summary = _fallback_summary(bus)
            if summary:
                yield sse({"type": "chunk", "text": summary})

    except asyncio.CancelledError:  # client disconnected
        raise
    except Exception as exc:
        log.exception("agent stream failed")
        message = str(exc)
        friendly = _friendly_error(message)
        yield sse({"type": "error", "text": friendly, "detail": message[:500]})
        yield sse({"type": "chunk", "text": friendly})

    yield sse({"type": "done"})


def _friendly_error(message: str) -> str:
    low = message.lower()
    if "api key" in low or "401" in low or "unauthor" in low:
        return ("⚠ The AI model rejected the request — check OPENROUTER_API_KEY in "
                "Backend/.env.")
    if "rate limit" in low or "429" in low:
        return "⚠ The AI provider is rate limiting us. Please retry in a few seconds."
    if "recursion" in low:
        return ("⚠ I needed too many steps for that question. Try narrowing it "
                "(one entity, one period).")
    if "timeout" in low or "timed out" in low:
        return "⚠ The request timed out. Try a smaller period or fewer rows."
    return f"⚠ Something went wrong while answering: {message[:300]}"


def _fallback_summary(bus: ResultBus) -> str:
    if not bus.all:
        return ""
    parts = []
    for ds in bus.all[:2]:
        total = ds.total_available or len(ds.rows)
        label = ds.entity or ds.table
        parts.append(f"Returned {len(ds.rows):,} {label} record(s)"
                     + (f" out of {total:,} matching" if total > len(ds.rows) else "")
                     + ".")
    if bus.all[0].simulated:
        parts.append("Note: this is sandbox data — the live HANA connection is unavailable.")
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic planner (no LLM key configured)
# ─────────────────────────────────────────────────────────────────────────────
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def plan_query(query: str) -> dict:
    """Heuristically turn a question into a sap_query payload."""
    import datetime as dt

    q = query.lower()
    table = None
    for phrase, candidate in [
        ("purchase order", "OPOR"), ("po ", "OPOR"), ("procurement", "OPOR"),
        ("supplier invoice", "OPCH"), ("vendor invoice", "OPCH"), ("ap invoice", "OPCH"),
        ("invoice", "OINV"), ("billing", "OINV"),
        ("sales order", "ORDR"), ("order", "ORDR"),
        ("quotation", "OQUT"), ("quote", "OQUT"),
        ("delivery", "ODLN"), ("shipment", "ODLN"),
        ("credit memo", "ORIN"),
        ("customer", "OCRD"), ("vendor", "OCRD"), ("supplier", "OCRD"),
        ("business partner", "OCRD"), ("client", "OCRD"),
        ("inventory", "OITM"), ("stock", "OITM"), ("item", "OITM"), ("product", "OITM"),
        ("warehouse", "OITW"),
        ("employee", "OHEM"), ("staff", "OHEM"), ("headcount", "OHEM"), ("payroll", "OHEM"),
        ("journal", "JDT1"), ("ledger", "JDT1"), ("gl ", "JDT1"),
        ("account", "OACT"),
        ("payment", "ORCT"), ("receipt", "ORCT"),
        ("opportunit", "OOPR"), ("pipeline", "OOPR"),
        ("service call", "OSCL"), ("production", "OWOR"),
    ]:
        if phrase in q:
            table = candidate
            break
    table = table or "ORDR"

    payload: dict[str, Any] = {"table": table, "limit": config.DEFAULT_ROW_LIMIT}
    filters: list[dict] = []

    if "open" in q or "outstanding" in q or "pending" in q or "unpaid" in q:
        filters.append({"column": "DocStatus", "op": "eq", "value": "Open"})
    elif "closed" in q or "completed" in q:
        filters.append({"column": "DocStatus", "op": "eq", "value": "Closed"})

    if table == "OCRD":
        if "vendor" in q or "supplier" in q:
            filters = [{"column": "CardType", "op": "eq", "value": "vendor"}]
        elif "customer" in q or "client" in q:
            filters = [{"column": "CardType", "op": "eq", "value": "customer"}]

    year_match = re.search(r"\b(20\d{2})\b", q)
    today = dt.date.today()
    if year_match:
        payload["year"] = int(year_match.group(1))
    elif "last quarter" in q:
        quarter = (today.month - 1) // 3
        start_year = today.year if quarter else today.year - 1
        start_month = (quarter - 1) * 3 + 1 if quarter else 10
        start = dt.date(start_year, start_month, 1)
        end_month = start_month + 2
        end = dt.date(start_year, end_month, 28) + dt.timedelta(days=4)
        end = end - dt.timedelta(days=end.day)
        payload["date_from"], payload["date_to"] = start.isoformat(), end.isoformat()
    elif "this year" in q or "ytd" in q:
        payload["year"] = today.year
    elif "last year" in q:
        payload["year"] = today.year - 1
    elif "last month" in q:
        first = today.replace(day=1)
        end = first - dt.timedelta(days=1)
        payload["date_from"], payload["date_to"] = end.replace(day=1).isoformat(), end.isoformat()
    elif "last 30 days" in q or "past month" in q:
        payload["date_from"] = (today - dt.timedelta(days=30)).isoformat()

    if filters:
        payload["filters"] = filters

    group_hint = re.search(r"\bby (the )?([a-z ]{3,20})", q)
    wants_group = any(w in q for w in ("top ", "highest", "largest", "most", "total by",
                                       "per ", "breakdown", "group", "which vendor",
                                       "which customer", "ranking", "by month", "trend"))
    if wants_group or group_hint:
        target = (group_hint.group(2).strip() if group_hint else "")
        dimension = None
        if "month" in target or "month" in q or "trend" in q:
            dimension = {"OINV": "DocDate", "ORDR": "DocDate", "OPOR": "DocDate"}.get(table)
        if dimension is None:
            if table in ("ORDR", "OINV", "OPOR", "OPCH", "ODLN", "OQUT", "ORCT", "OOPR"):
                dimension = "CardName"
            elif table == "OITM":
                dimension = "ItemName"
            elif table == "OCRD":
                dimension = "City" if "city" in target or "region" in target else "CardName"
            elif table == "OHEM":
                dimension = "jobTitle" if "title" in target else "branch"
            elif table == "OITW":
                dimension = "WhsCode"
            elif table == "JDT1":
                dimension = "AcctName"
        measure = {
            "ORDR": "DocTotal", "OINV": "DocTotal", "OPOR": "DocTotal", "OPCH": "DocTotal",
            "ODLN": "DocTotal", "OQUT": "DocTotal", "ORCT": "DocTotal", "OOPR": "MaxSumLoc",
            "OCRD": "Balance", "OITM": "OnHand", "OITW": "OnHand", "OHEM": "salary",
            "JDT1": "Debit",
        }.get(table)
        if dimension and measure and "count" not in q and "how many" not in q:
            payload["group_by"] = [dimension]
            payload["aggregates"] = [
                {"func": "sum", "column": measure, "alias": f"Total_{measure}"},
                {"func": "count", "column": "*", "alias": "Documents"},
            ]
            payload["order_by"] = [{"column": f"Total_{measure}", "direction": "desc"}]
        elif dimension:
            payload["group_by"] = [dimension]
            payload["aggregates"] = [{"func": "count", "column": "*", "alias": "Records"}]
            payload["order_by"] = [{"column": "Records", "direction": "desc"}]

    top_match = re.search(r"\btop\s+(\d{1,4})\b", q)
    if top_match:
        payload["limit"] = int(top_match.group(1))

    name_match = re.search(r"(?:for|from|of)\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,2})", query)
    if name_match and table in ("ORDR", "OINV", "OPOR", "OPCH", "ODLN", "OQUT"):
        candidate = name_match.group(1).strip()
        if candidate.lower() not in ("last", "the", "this", "sap", "hana", "open", "closed"):
            payload.setdefault("filters", []).append(
                {"column": "CardName", "op": "contains", "value": candidate}
            )
    return payload


async def _deterministic_stream(query: str, bus: ResultBus, employee_id: str):
    """No-LLM mode: still fetches real data and writes a factual summary."""
    q = query.lower()

    policy_hit = any(w in q for w in ("policy", "policies", "sop", "guideline", "allowed",
                                      "reimburse", "per diem", "approval limit"))
    if policy_hit:
        yield sse({"type": "status", "text": "Searching company policies…"})
        hits = await asyncio.to_thread(docs_store.search, query, 2)
        if hits:
            yield sse({"type": "source", "name": "Company Knowledge Base"})
            text = "\n\n".join(f"**{h['title']} — {h['section']}**\n{h['content'][:700]}" for h in hits)
            yield sse({"type": "chunk", "text": text})
            return

    yield sse({"type": "status", "text": "Querying SAP Business One…"})

    # "inventory by category" needs the item-group name, which lives in OITB
    if ("item" in q or "inventory" in q or "stock" in q or "product" in q) and (
        "categor" in q or "group" in q
    ):
        try:
            joined = await sap.run_sql(
                'SELECT T1."ItmsGrpNam" AS "Category", '
                'SUM(T0."OnHand") AS "QuantityOnStock", '
                'SUM(T0."OnHand" * T0."AvgPrice") AS "StockValue", '
                'COUNT(*) AS "Items" '
                'FROM OITM T0 JOIN OITB T1 ON T0."ItmsGrpCod" = T1."ItmsGrpCod" '
                'GROUP BY T1."ItmsGrpNam" ORDER BY "StockValue" DESC',
                limit=100,
            )
            if joined.ok and joined.rows:
                dataset = Dataset(
                    entity="Inventory by category",
                    table="OITM",
                    rows=joined.rows,
                    columns=joined.columns,
                    source=joined.source,
                    simulated=joined.simulated,
                    sql=joined.sql,
                    elapsed_ms=joined.elapsed_ms,
                )
                bus.push(dataset)
                yield sse({"type": "source", "name": joined.source})
                for event in dataset_events(dataset, query):
                    yield sse(event)
                total_value = sum(
                    r.get("StockValue") or 0 for r in joined.rows if isinstance(r.get("StockValue"), (int, float))
                )
                text = (f"Stock is spread across {len(joined.rows)} item groups with a total "
                        f"valuation of {total_value:,.0f}.")
                if joined.simulated:
                    text += " ⚠ Sandbox data — the live SAP HANA server is not reachable."
                yield sse({"type": "chunk", "text": text})
                return
        except Exception:
            pass

    payload = plan_query(query)
    try:
        result = await sap.run_query(payload)
    except Exception as exc:
        yield sse({"type": "error", "text": f"⚠ SAP query failed: {exc}"})
        yield sse({"type": "chunk", "text": f"⚠ I could not fetch that data: {exc}"})
        return

    dataset = Dataset(
        entity=result.table,
        table=result.table,
        rows=result.rows,
        columns=result.columns,
        source=result.source,
        simulated=result.simulated,
        sql=result.sql,
        total_available=result.total_available,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )
    bus.push(dataset)
    yield sse({"type": "source", "name": result.source})
    for event in dataset_events(dataset, query):
        yield sse(event)

    totals = _summarise_numeric(result.rows, result.columns)
    bits = [f"Found {result.row_count:,} {result.table} record(s)"]
    if result.total_available and result.total_available > result.row_count:
        bits.append(f"out of {result.total_available:,} matching the filter")
    sentence = " ".join(bits) + "."
    money = next((c for c in ("Total_DocTotal", "DocTotal", "Total", "Balance", "LineTotal",
                              "salary", "OnHand") if c in totals), None)
    if money:
        sentence += (f" {money} totals {totals[money]['sum']:,.2f} "
                     f"(avg {totals[money]['avg']:,.2f}, max {totals[money]['max']:,.2f}).")
    if result.simulated:
        sentence += (" ⚠ This is sandbox data — the live SAP HANA server is not reachable "
                     "from this machine.")
    sentence += "\n\n_(Deterministic mode: no OPENROUTER_API_KEY configured, so this summary "
    sentence += "is generated without the LLM.)_"
    yield sse({"type": "chunk", "text": sentence})


async def generate_title(prompt: str) -> str:
    """Short chat title. Uses the LLM when available, else a clean truncation."""
    text = (prompt or "").strip()
    if llm is not None:
        try:
            title_llm = build_llm(config.TITLE_MODEL_NAME)
            response = await title_llm.ainvoke(
                [
                    SystemMessage(content=(
                        "Generate a 2-4 word title for this user message. "
                        "No quotes, no punctuation, no explanation.")),
                    HumanMessage(content=text[:500]),
                ]
            )
            title = (response.content or "").strip().strip('"\'')
            title = re.sub(r"\s+", " ", title)
            if title:
                return title[:40]
        except Exception as exc:
            log.warning("title generation failed: %s", exc)
    words = re.sub(r"\s+", " ", text).split(" ")
    return " ".join(words[:6])[:40] or "New conversation"
