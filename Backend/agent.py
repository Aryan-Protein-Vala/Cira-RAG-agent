import json
import asyncio
import re
import httpx
from typing import AsyncGenerator

try:
    with open("sap_schema_catalog.json", "r") as f:
        CATALOG: dict = json.load(f)
except FileNotFoundError:
    CATALOG = {}

# Flip to False and set real endpoint when SAP is connected
MOCK_SAP = True
SAP_ODATA_BASE_URL = "[SAP_ODATA_BASE_URL]"  # e.g. https://host/sap/opu/odata/sap/


# ── Fix 4.1: Word-boundary keyword matching (no more substring false positives) ──

def _resolve_entity(query_lower: str) -> str:
    """
    Fix 4.1: Uses word-boundary regex instead of raw substring 'in' checks.
    Prevents 'report' → ProcurementSet, 'through' → EmployeeSet etc.
    """
    # HR / Employee — whole words only
    if re.search(r'\b(employee|employees|hr|staff|salary|salaries|headcount|payroll)\b', query_lower):
        return "EmployeeSet"
    # Procurement / Purchase Orders — whole words only
    if re.search(r'\b(procurement|purchase|purchases|vendor|vendors|purchase order|po number)\b', query_lower):
        return "ProcurementSet"
    # Default: Sales
    return "SalesOrderSet"


def _build_odata_query(entity: str, query_lower: str) -> str:
    """
    Fix 4.2: Only applies filters whose fields actually exist in the target entity schema.
    Prevents EmployeeSet from receiving Status/Plant/OrderDate filters it doesn't have.
    """
    if entity not in CATALOG:
        return f"{SAP_ODATA_BASE_URL}/{entity}?$top=50"

    schema_cols = CATALOG[entity]["columns"]
    all_cols = list(schema_cols.keys())
    select = ",".join(all_cols)

    filters = []
    # Only add Status filter if entity has a Status column
    if "Status" in schema_cols and ("delivered" in query_lower or "status" in query_lower):
        filters.append("Status eq 'Delivered'")
    # Only add Plant filter if entity has a Plant column
    if "Plant" in schema_cols and re.search(r'\b(germany|de.?1000)\b', query_lower):
        filters.append("Plant eq 'DE-1000'")
    # Only add OrderDate filter if entity has an OrderDate column
    if "OrderDate" in schema_cols and "2024" in query_lower:
        filters.append("year(OrderDate) eq 2024")

    filter_str = f"&$filter={' and '.join(filters)}" if filters else ""
    return f"{SAP_ODATA_BASE_URL}/{entity}?$select={select}{filter_str}&$top=50&$format=json"


# ── SAP OData Tool ─────────────────────────────────────────────────────────────

async def query_sap_odata(query: str, sap_token: str, employee_id: str) -> dict:
    """
    Executes the SAP OData GET request using the per-user SAP token.

    Fix 3: httpx.AsyncClient is kept alive across the retry block using a
    single `async with` that wraps BOTH the initial request and the retry,
    so the client is never closed before the retry is attempted.

    Fix 3.4: Self-correction retry does NOT strip security filters — it only
    retries by dropping keyword-derived $filter hints (like 'Delivered'),
    not access-control filters. This prevents global data exposure.
    """
    entity = _resolve_entity(query.lower())
    url = _build_odata_query(entity, query.lower())

    if MOCK_SAP:
        schema = CATALOG.get(entity, {})
        return {"ok": True, "entity": entity, "url": url, "data": schema.get("mock_data", [])}

    headers = {
        "Authorization": f"Bearer {sap_token}",
        "Accept": "application/json",
        "sap-client": "100",
    }

    # Fix 3: Single AsyncClient context wraps both request AND retry
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)

        if resp.status_code == 403:
            return {"ok": False, "error": "User is unauthorized to access this data.", "entity": entity, "status": 403}

        if resp.status_code == 400:
            # Self-correction: drop only the keyword-derived $filter, keep $select intact.
            # Never strip access-control filters (Fix 3.4).
            all_cols = list(CATALOG.get(entity, {}).get("columns", {}).keys())
            retry_url = f"{SAP_ODATA_BASE_URL}/{entity}?$select={','.join(all_cols)}&$top=50&$format=json"
            resp2 = await client.get(retry_url, headers=headers)  # ← Fix 3: client still open here
            if resp2.status_code == 200:
                payload = resp2.json()
                return {"ok": True, "entity": entity, "url": retry_url,
                        "data": payload.get("d", {}).get("results", []), "self_corrected": True}
            return {"ok": False, "error": f"SAP returned {resp2.status_code} after self-correction retry.", "entity": entity}

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "error": f"SAP returned HTTP {exc.response.status_code}.", "entity": entity}

        payload = resp.json()
        return {"ok": True, "entity": entity, "url": url, "data": payload.get("d", {}).get("results", [])}


# ── Vector RAG Tool (ChromaDB mock) ───────────────────────────────────────────

async def query_company_docs(query: str) -> str:
    """Mock ChromaDB similarity search over unstructured policy documents."""
    await asyncio.sleep(0.05)
    return (
        "**Travel Policy (v2.3)** [similarity: 0.94]\n"
        "- All flights must be booked **14 days in advance**.\n"
        "- Business Class requires manager approval above $3,000 net fare.\n"
        "- Hotel stays are capped at **$250/night** in Tier 1 cities.\n"
        "- Expense reports must be submitted within **5 business days** of return."
    )


# ── Agentic Router — mimics LangChain astream_events (v2) ────────────────────

async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str,
    employee_id: str = "UNKNOWN"
) -> AsyncGenerator[str, None]:
    """
    Routes queries to the correct tool and streams SSE chunks.
    Fix 3.3: Token is NEVER streamed into SSE output. 
    Fix 4.1: Uses word-boundary entity resolution.
    Fix 4.2: Filters are schema-validated before being added to OData queries.
    """
    query_lower = query.lower()

    async def emit(text: str, delay: float = 0.04):
        for word in text.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(delay)

    # ── Tool: query_company_docs ───────────────────────────────────────────────
    if re.search(r'\b(policy|policies|travel|document|procedure|sop|guideline)\b', query_lower):
        async for chunk in emit(f"[on_tool_start] Invoking **query_company_docs** for `{employee_id}`..."):
            yield chunk

        doc_result = await query_company_docs(query)

        async for chunk in emit(f"\n\n[on_tool_end] ChromaDB returned 1 match.\n\n{doc_result}"):
            yield chunk

    # ── Tool: query_sap_odata ──────────────────────────────────────────────────
    elif any(re.search(rf'\b{kw}\b', query_lower) for kw in
             ["data", "sales", "order", "orders", "employee", "employees",
              "procurement", "purchase", "vendor", "sap", "table", "show",
              "hr", "staff", "salary"]):

        entity = _resolve_entity(query_lower)
        url = _build_odata_query(entity, query_lower)

        # Fix 3.3: NEVER include token in streamed output
        async for chunk in emit(
            f"[on_tool_start] Invoking **query_sap_odata** · Entity: **{entity}** · User: **{employee_id}**\n\n"
            f"OData query (catalog-grounded):\n```\nGET {url}\nAuthorization: Bearer [REDACTED]\n```\n"
        ):
            yield chunk

        result = await query_sap_odata(query, sap_token, employee_id)

        if not result["ok"]:
            status = result.get("status", 500)
            error_msg = result.get("error", "Unknown SAP error.")
            async for chunk in emit(f"\n\n[on_tool_end] ⚠ SAP returned HTTP **{status}**: {error_msg}"):
                yield chunk
            return

        if result.get("self_corrected"):
            async for chunk in emit("\n\n[on_tool_end] ⚠ Self-corrected after 400 Bad Request (dropped hint filters, kept $select). ✓"):
                yield chunk

        async for chunk in emit(
            f"\n\n[on_tool_end] SAP returned **{len(result['data'])}** records visible to **{employee_id}** (SU01 auth enforced):"
        ):
            yield chunk

        yield f"data: {json.dumps({'type': 'tabular', 'data': result['data'], 'entity': result['entity']})}\n\n"

    # ── Fallback: conversational ───────────────────────────────────────────────
    else:
        history_note = f"(Session context: {len(history)} messages.) " if history else ""
        tools_list = ", ".join(CATALOG.keys()) if CATALOG else "SalesOrderSet, EmployeeSet, ProcurementSet"
        msg = (
            f"Hello **{employee_id}**! {history_note}I am **CIRA**, your SAP Intelligence Agent.\n\n"
            f"Your session is authenticated with a user-delegated SAP token. "
            f"SAP enforces your authorization profile on every query.\n\n"
            f"**Available tools:**\n"
            f"- `query_sap_odata` — {tools_list}\n"
            f"- `query_company_docs` — ChromaDB vector search (policies & SOPs)\n\n"
            f"Try: *'Show me sales orders'*, *'Employee data'*, *'Travel policy'*, or *'Trigger bad request'*."
        )
        async for chunk in emit(msg):
            yield chunk
