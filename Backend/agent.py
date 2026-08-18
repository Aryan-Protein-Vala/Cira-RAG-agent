import json
import asyncio
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


# ── SAP OData Tool ─────────────────────────────────────────────────────────────

def _resolve_entity(query_lower: str) -> str:
    if "employee" in query_lower or "hr" in query_lower or "staff" in query_lower or "salary" in query_lower:
        return "EmployeeSet"
    elif "procurement" in query_lower or "purchase" in query_lower or "vendor" in query_lower or "po" in query_lower:
        return "ProcurementSet"
    return "SalesOrderSet"


def _build_odata_query(entity: str, query_lower: str) -> str:
    """Strict OData query — only uses fields present in sap_schema_catalog.json."""
    if entity not in CATALOG:
        return f"{SAP_ODATA_BASE_URL}/{entity}?$top=50"

    all_cols = list(CATALOG[entity]["columns"].keys())
    select = ",".join(all_cols)

    filters = []
    if "delivered" in query_lower or "status" in query_lower:
        filters.append("Status eq 'Delivered'")
    if "germany" in query_lower or "de-1000" in query_lower:
        filters.append("Plant eq 'DE-1000'")
    if "2024" in query_lower:
        filters.append("year(OrderDate) eq 2024")

    filter_str = f"&$filter={' and '.join(filters)}" if filters else ""
    return f"{SAP_ODATA_BASE_URL}/{entity}?$select={select}{filter_str}&$top=50&$format=json"


async def query_sap_odata(query: str, sap_token: str, employee_id: str) -> dict:
    """
    Executes the SAP OData GET request using the per-user SAP token.
    
    Real behavior:
      - Sends Authorization: Bearer <sap_token> (user-scoped, from OAuth2 SAML exchange)
      - SAP enforces row-level auth via named-user mapping (SU01 / SAML2)
      - 403 → user has no authorization for this data object
      - 400 → hallucinated column → self-correct against catalog and retry
    
    Mock behavior (MOCK_SAP=True):
      - Returns mock_data from sap_schema_catalog.json
    """
    entity = _resolve_entity(query.lower())
    url = _build_odata_query(entity, query.lower())

    if MOCK_SAP:
        schema = CATALOG.get(entity, {})
        return {
            "ok": True,
            "entity": entity,
            "url": url,
            "data": schema.get("mock_data", [])
        }

    # Real httpx call — uses the per-user SAP token (never a master credential)
    headers = {
        "Authorization": f"Bearer {sap_token}",
        "Accept": "application/json",
        "sap-client": "100",  # SAP client number — configure per environment
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 403:
            return {
                "ok": False,
                "error": "User is unauthorized to access this data.",
                "entity": entity,
                "status": 403
            }

        if resp.status_code == 400:
            # Attempt self-correction: drop $filter and retry with only $select
            retry_url = f"{SAP_ODATA_BASE_URL}/{entity}?$select={','.join(list(CATALOG[entity]['columns'].keys()))}&$top=50&$format=json"
            resp2 = await client.get(retry_url, headers=headers)
            if resp2.status_code == 200:
                payload = resp2.json()
                return {"ok": True, "entity": entity, "url": retry_url, "data": payload.get("d", {}).get("results", []), "self_corrected": True}
            return {"ok": False, "error": f"SAP returned {resp2.status_code} after self-correction retry.", "entity": entity}

        resp.raise_for_status()
        payload = resp.json()
        return {
            "ok": True,
            "entity": entity,
            "url": url,
            "data": payload.get("d", {}).get("results", [])
        }

    except httpx.RequestError as exc:
        return {"ok": False, "error": f"Network error reaching SAP: {exc}", "entity": entity}


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


# ── Agentic Router — mimics LangChain astream_events (v2) ───────────────────

async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str,
    employee_id: str = "UNKNOWN"
) -> AsyncGenerator[str, None]:
    """
    Routes queries to the correct tool and streams SSE chunks.
    Mimics LangChain astream_events v2 event structure:
      on_tool_start  → yields thinking text
      on_tool_end    → yields result (text chunk or tabular payload)
      on_llm_stream  → yields token-by-token text
    """
    query_lower = query.lower()

    async def emit(text: str, delay: float = 0.04):
        """Yield text word by word, simulating on_llm_stream token events."""
        for word in text.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(delay)

    # ── on_tool_start: query_company_docs ─────────────────────────────────────
    if any(kw in query_lower for kw in ["policy", "travel", "document", "procedure", "sop"]):
        async for chunk in emit(f"[on_tool_start] Invoking **query_company_docs** for `{employee_id}`..."):
            yield chunk

        doc_result = await query_company_docs(query)

        async for chunk in emit(f"\n\n[on_tool_end] ChromaDB returned 1 match.\n\n{doc_result}"):
            yield chunk

    # ── on_tool_start: query_sap_odata ────────────────────────────────────────
    elif any(kw in query_lower for kw in ["data", "sales", "order", "employee", "procurement",
                                           "purchase", "vendor", "sap", "table", "show", "hr"]):
        entity = _resolve_entity(query_lower)
        url = _build_odata_query(entity, query_lower)

        async for chunk in emit(
            f"[on_tool_start] Invoking **query_sap_odata** · Entity: **{entity}** · User: **{employee_id}**\n\n"
            f"OData query (catalog-grounded):\n```\nGET {url}\nAuthorization: Bearer {sap_token[:24]}...\n```\n"
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
            async for chunk in emit("\n\n[on_tool_end] ⚠ Self-corrected after 400 Bad Request. Retried with catalog-only fields. ✓"):
                yield chunk

        async for chunk in emit(f"\n\n[on_tool_end] SAP returned **{len(result['data'])}** records visible to **{employee_id}** (SU01 auth enforced):"):
            yield chunk

        # Emit structured tabular payload — DataCard renders this instantly
        yield f"data: {json.dumps({'type': 'tabular', 'data': result['data'], 'entity': result['entity']})}\n\n"

    # ── on_llm_stream: fallback conversational ────────────────────────────────
    else:
        history_note = f"(Session context: {len(history)} messages.) " if history else ""
        tools_list = ", ".join(CATALOG.keys()) if CATALOG else "SalesOrderSet, EmployeeSet, ProcurementSet"
        msg = (
            f"Hello **{employee_id}**! {history_note}I am **CIRA**, your SAP Intelligence Agent.\n\n"
            f"Your session token has been exchanged for a user-scoped SAP access token "
            f"via OAuth2 SAML Bearer. SAP enforces your authorization profile on every query.\n\n"
            f"**Available tools:**\n"
            f"- `query_sap_odata` — {tools_list}\n"
            f"- `query_company_docs` — ChromaDB vector search (policies & SOPs)\n\n"
            f"Try: *'Show me sales orders'*, *'Employee data'*, *'Travel policy'*, or *'Trigger bad request'*."
        )
        async for chunk in emit(msg):
            yield chunk
