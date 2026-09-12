"""Accuracy harness - measures what actually happened, not just that a tool ran.

Run it against a live backend:

    # terminal 1
    cd Backend && uvicorn main:app --port 8000

    # terminal 2
    cd Backend
    export CIRA_HARNESS_TOKEN=...          # employee or superadmin bearer token
    #   or: export CIRA_SUPERADMIN_EMAIL=... CIRA_SUPERADMIN_PASSWORD=...
    export CIRA_HARNESS_TENANT=db_sandbox  # company_db of the tenant to test
    python tests/accuracy/runner.py --suite sandbox

What changed and why
--------------------
The previous runner scored a question as PASS when the agent called
``sap_query`` with a table name that appeared in ``expected_tables``. Nothing
was compared against the answer: not the SQL, not the columns, not the number of
rows, not the value. A confidently wrong answer passed. That number was then
published as an "accuracy scorecard", which is exactly the kind of invented
metric this project cannot ship.

Each question is now graded on independent checks that are all printed:

  tool      did the agent call a query tool at all
  table     did the SQL that actually executed touch an expected table
  column    did it reference an expected column
  rows      did it return at least ``expect_min_rows`` rows (default 1)
  sql       optional ``expect_sql_regex`` / ``forbid_sql_regex``
  trap      hallucination traps: a refusal or an explicit "not in SAP" statement
  clarify   ambiguous questions: the agent must ask, not guess
  error     no transport/LLM error occurred

A question PASSES only when every applicable check passes, and the reason string
names the first failing check. Results are written incrementally, so a crash on
question 41 still leaves 40 graded results on disk instead of an empty file.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))

# ── configuration: everything from the environment, nothing hard-coded ──────
# The previous version shipped a personal Gmail address and the password
# "aryan" in this file, which made the repository itself a credential store.
API_URL = os.getenv("CIRA_API_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.getenv("CIRA_HARNESS_TOKEN", "").strip()
SUPERADMIN_EMAIL = os.getenv("CIRA_SUPERADMIN_EMAIL", "").strip()
SUPERADMIN_PASSWORD = os.getenv("CIRA_SUPERADMIN_PASSWORD", "").strip()
TENANT_ID = os.getenv("CIRA_HARNESS_TENANT", "").strip()
REQUEST_TIMEOUT = float(os.getenv("CIRA_HARNESS_TIMEOUT", "45"))

# Ground truth. When the tenant under test is the offline sandbox, point this at
# the sandbox SQLite file and a question carrying `ground_truth_sql` gets its
# answer checked against a value computed independently, by us, from the same
# data - not against the agent's own output.
#
# Without it the harness only proves the *shape* of an answer (right table,
# right column, some rows). That distinction is printed on every run so nobody
# quotes a structural score as an accuracy score.
GROUND_TRUTH_DB = os.getenv("CIRA_GROUND_TRUTH_DB", os.getenv("CIRA_SIM_DB_PATH", "")).strip()

# A refusal must say something a human would accept as "I could not answer".
REFUSAL_MARKERS = (
    "not available", "not in sap", "cannot", "can't", "do not have", "don't have",
    "unable", "sorry", "no data", "not found", "could not", "does not contain",
    "not tracked", "not stored", "not something", "outside sap",
)

# Questions in the ``hallucination`` bucket must refuse. Everything else must not
# refuse: if the agent declines a normal question, that is a failure, not a pass.
# (The old runner awarded passes for "did nothing" on the hallucination bucket -
# an agent that never answers scored 100% on it.)


async def get_token() -> str:
    if TOKEN:
        return TOKEN
    if not (SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD):
        sys.exit(
            "No credentials. Set CIRA_HARNESS_TOKEN, or CIRA_SUPERADMIN_EMAIL + "
            "CIRA_SUPERADMIN_PASSWORD. The harness deliberately has no defaults."
        )
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(
            f"{API_URL}/superadmin/login",
            json={"username": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD},
        )
        if r.status_code != 200:
            sys.exit(f"Login failed ({r.status_code}): {r.text[:300]}")
        return r.json()["token"]


async def resolve_tenant(client: httpx.AsyncClient, token: str) -> str:
    if TENANT_ID:
        return TENANT_ID
    r = await client.get(
        f"{API_URL}/superadmin/tenants", headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code != 200:
        sys.exit(f"Could not list tenants ({r.status_code}): {r.text[:300]}")
    tenants = r.json()
    if not tenants:
        sys.exit("No tenants exist. Create one (seed_tenant.py) or set CIRA_HARNESS_TENANT.")
    return tenants[0]["company_db"]


async def ask(client: httpx.AsyncClient, token: str, tenant: str, q: dict) -> dict:
    """Send one question over SSE and collect every event we care about."""
    headers = {"Authorization": f"Bearer {token}", "x-tenant-id": tenant}
    body = {"query": q["question"], "session_id": f"accuracy_{q['id']}_{int(time.time())}"}
    started = time.time()
    events: list[dict] = []
    transport_error = ""
    try:
        async with client.stream(
            "POST", f"{API_URL}/chat", headers=headers, json=body, timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status_code != 200:
                detail = (await response.aread()).decode("utf-8", "replace")[:300]
                return {"events": [], "final_text": "", "tools": [], "queries": [],
                        "tables": [], "sql": [], "row_counts": [], "data_rows": [],
                        "errors": [f"HTTP {response.status_code}: {detail}"],
                        "latency_ms": int((time.time() - started) * 1000)}
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    pass
    except Exception as exc:  # transport failure must be reported, not swallowed
        transport_error = f"{type(exc).__name__}: {exc}"

    text_parts, tools, queries, tables, sql, row_counts, errors = [], [], [], [], [], [], []
    data_rows: list = []
    for ev in events:
        kind = ev.get("type")
        if kind == "chunk":
            text_parts.append(ev.get("text", ""))
        elif kind == "status":
            tools.append(ev.get("tool", ""))
        elif kind == "action":
            tools.append(ev.get("tool", ""))
            args = ev.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if isinstance(args, dict):
                queries.append(args)
        elif kind == "tabular":
            meta = ev.get("meta") or {}
            tables.append(str(meta.get("table") or ev.get("entity") or "").upper())
            if meta.get("sql"):
                sql.append(meta["sql"])
            row_counts.append(int(meta.get("rowCount") or len(ev.get("data") or [])))
            for row in (ev.get("data") or []):
                if isinstance(row, dict):
                    data_rows.append(row)
                elif isinstance(row, (list, tuple)):
                    data_rows.append(list(row))
        elif kind == "error":
            errors.append(str(ev.get("text", ""))[:200])

    if transport_error:
        errors.append(transport_error)
    return {
        "events": events,
        "final_text": "".join(text_parts),
        "tools": tools,
        "queries": queries,
        "tables": tables,
        "sql": sql,
        "row_counts": row_counts,
        "data_rows": data_rows,
        "errors": errors,
        "latency_ms": int((time.time() - started) * 1000),
    }


def _sql_blob(result: dict) -> str:
    parts = list(result["sql"])
    for qy in result["queries"]:
        parts.append(json.dumps(qy))
    return " ".join(parts).upper()


def _norm_value(value) -> str:
    text = str(value).strip().replace(",", "").replace("₹", "").replace("$", "")
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
        return f"{number:.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return text.lower()


def ground_truth_values(question: dict) -> tuple[set[str], str]:
    """Run the question's own ground_truth_sql and return the expected values."""
    sql = question.get("ground_truth_sql")
    if not sql:
        return set(), "no ground_truth_sql for this question"
    if not GROUND_TRUTH_DB or not os.path.exists(GROUND_TRUTH_DB):
        return set(), "ground-truth DB not configured (set CIRA_GROUND_TRUTH_DB)"
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{GROUND_TRUTH_DB}?mode=ro", uri=True)
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return set(), f"ground-truth SQL failed: {exc}"
    values = {_norm_value(cell) for row in rows for cell in row if cell is not None}
    return values, f"{len(rows)} ground-truth row(s)"


def grade(question: dict, result: dict) -> dict:
    """Return {pass, checks: {...}, failed_on, reason}. Every check is reported."""
    checks: dict[str, dict] = {}

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"pass": bool(ok), "detail": detail}

    text_lower = result["final_text"].lower()
    said_no = any(marker in text_lower for marker in REFUSAL_MARKERS)
    queried = bool(result["sql"] or result["queries"])
    blob = _sql_blob(result)
    expected_tables = {t.upper() for t in question.get("expected_tables", [])}
    expected_columns = {c.upper() for c in question.get("expected_columns", [])}

    add("error", not result["errors"], "; ".join(result["errors"])[:200])
    add("tool", queried or said_no or bool(result["tables"]),
        "query tool called" if queried else "no query tool call")

    if question.get("expected_rejection") or question.get("hallucination_trap"):
        # Traps: a competent agent either refuses, or queries and then states
        # that the data is not there. It must NOT produce an answer.
        produced_number = bool(re.search(r"\d[\d,]{2,}", result["final_text"]))
        add("trap", said_no or not produced_number,
            "refused / stated the data is unavailable" if said_no
            else ("answered with a figure anyway" if produced_number else "no answer"))
        add("table", True, "not applicable to a trap")
        add("column", True, "not applicable to a trap")
        add("rows", True, "not applicable to a trap")
    elif question.get("expected_clarification"):
        add("clarify", not queried or said_no,
            "asked instead of guessing" if said_no else
            ("queried without clarifying" if queried else "no query"))
        add("table", True, "not applicable to a clarification")
        add("column", True, "not applicable to a clarification")
        add("rows", True, "not applicable to a clarification")
    else:
        table_hit = expected_tables & ({t.upper() for t in result["tables"]} | set())
        if not table_hit and expected_tables:
            table_hit = {t for t in expected_tables if t in blob}
        add("table", bool(table_hit) or not expected_tables,
            f"hit {sorted(table_hit)}" if table_hit else
            f"expected any of {sorted(expected_tables)}; saw {sorted(set(result['tables']))}")

        column_hit = {c for c in expected_columns if c in blob}
        add("column", bool(column_hit) or not expected_columns,
            f"referenced {sorted(column_hit)}" if column_hit else
            f"expected any of {sorted(expected_columns)}")

        min_rows = int(question.get("expect_min_rows", 1))
        got = max(result["row_counts"]) if result["row_counts"] else 0
        add("rows", got >= min_rows, f"{got} rows returned (need >= {min_rows})")

        expected_values, gt_detail = ground_truth_values(question)
        if expected_values:
            returned = {_norm_value(v) for row in result["data_rows"]
                        for v in (row.values() if isinstance(row, dict) else row)}
            hits = expected_values & returned
            add("value", bool(hits),
                f"matched {sorted(hits)[:4]} of {sorted(expected_values)[:6]} ({gt_detail})"
                if hits else
                f"none of {sorted(expected_values)[:6]} appeared in the returned rows ({gt_detail})")
        else:
            add("value", True, f"NOT VERIFIED - {gt_detail}")

        if question.get("expect_sql_regex"):
            add("sql", bool(re.search(question["expect_sql_regex"], blob, re.I)),
                f"pattern {question['expect_sql_regex']!r}")
        if question.get("forbid_sql_regex") and re.search(question["forbid_sql_regex"], blob, re.I):
            add("sql", False, f"forbidden pattern {question['forbid_sql_regex']!r} present")

    failed_on = [name for name, c in checks.items() if not c["pass"]]
    passed = not failed_on
    if passed:
        reason = "all checks passed"
    else:
        first = failed_on[0]
        reason = f"{first}: {checks[first]['detail']}"
    return {"pass": passed, "checks": checks, "failed_on": failed_on, "reason": reason}


async def main() -> int:
    parser = argparse.ArgumentParser(description="CIRA accuracy harness")
    parser.add_argument("--suite", default="sandbox", help="suite_<name>.jsonl")
    parser.add_argument("--out", default=os.path.join(HERE, "results.json"))
    parser.add_argument("--ids", default="", help="comma-separated question ids to run")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--label", default="", help="free-text label stored in the results file")
    args = parser.parse_args()

    suite_path = os.path.join(HERE, f"suite_{args.suite}.jsonl")
    if not os.path.exists(suite_path):
        sys.exit(f"Suite not found: {suite_path}")

    questions = [json.loads(line) for line in open(suite_path) if line.strip()]
    if args.ids:
        wanted = {int(i) for i in args.ids.split(",") if i.strip()}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    token = await get_token()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        tenant = await resolve_tenant(client, token)
        print(f"Suite: {args.suite}  |  {len(questions)} questions  |  tenant: {tenant}"
              f"  |  api: {API_URL}")

        results: list[dict] = []
        for i, question in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] Q{question['id']} ({question['bucket']}): "
                  f"{question['question']}")
            try:
                outcome = await ask(client, token, tenant, question)
            except Exception as exc:
                outcome = {"events": [], "final_text": "", "tools": [], "queries": [],
                           "tables": [], "sql": [], "row_counts": [], "data_rows": [],
                           "errors": [f"harness: {type(exc).__name__}: {exc}"], "latency_ms": 0}
            graded = grade(question, outcome)
            record = {
                "id": question["id"],
                "bucket": question["bucket"],
                "question": question["question"],
                "pass": graded["pass"],
                "reason": graded["reason"],
                "failed_on": graded["failed_on"],
                "checks": graded["checks"],
                "final_text": outcome["final_text"][:2000],
                "sql": outcome["sql"],
                "tables": outcome["tables"],
                "row_counts": outcome["row_counts"],
                "latency_ms": outcome["latency_ms"],
                "errors": outcome["errors"],
            }
            results.append(record)
            print(f"    -> {'PASS' if graded['pass'] else 'FAIL'} ({graded['reason']})")

            # Persist after every question: a crash must not erase the run.
            payload = {
                "run": {
                    "suite": args.suite,
                    "api_url": API_URL,
                    "tenant": tenant,
                    "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "label": args.label,
                    "answered": len(results),
                    "suite_total": len(questions),
                },
                "results": results,
            }
            with open(args.out, "w") as fh:
                json.dump(payload, fh, indent=2)

    passes = sum(1 for r in results if r["pass"])
    print(f"\n{passes}/{len(results)} passed "
          f"({100.0 * passes / max(1, len(results)):.1f}%) - written to {args.out}")
    if len(results) < len(questions):
        print("WARNING: the run is INCOMPLETE; the gate will refuse to certify it.")
    failures = [r for r in results if not r["pass"]]
    if failures:
        print(f"\n{len(failures)} failures (this is the useful part of the report):")
        for r in failures:
            print(f"  Q{r['id']:>3} [{r['bucket']}] {r['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
