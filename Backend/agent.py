import json
import asyncio
from typing import AsyncGenerator

try:
    with open("sap_schema_catalog.json", "r") as f:
        CATALOG: dict = json.load(f)
except FileNotFoundError:
    CATALOG = {}


def _resolve_entity_and_columns(query_lower: str) -> tuple[str, list, list]:
    """
    Grounding step: Match user query keywords to a catalog entity set.
    Returns (entity_set_name, selected_columns, mock_data).
    """
    if "employee" in query_lower or "hr" in query_lower or "staff" in query_lower or "salary" in query_lower:
        entity = "EmployeeSet"
    elif "procurement" in query_lower or "purchase" in query_lower or "vendor" in query_lower or "po" in query_lower:
        entity = "ProcurementSet"
    else:
        entity = "SalesOrderSet"

    if entity not in CATALOG:
        return entity, [], []

    schema = CATALOG[entity]
    columns = list(schema["columns"].keys())
    data = schema["mock_data"]
    return entity, columns, data


def _build_odata_query(entity: str, columns: list, query_lower: str, sap_token: str) -> str:
    """
    Constructs a strict OData query using ONLY catalog-defined fields.
    Injects the per-user SAP token into the Authorization header representation.
    In production: this token is passed as Authorization: Bearer <sap_token>
    in the actual httpx call to the SAP OData endpoint.
    """
    base_url = "[SAP_ODATA_BASE_URL]"
    select = ",".join(columns)

    filters = []
    if "delivered" in query_lower or "status" in query_lower:
        filters.append("Status eq 'Delivered'")
    if "germany" in query_lower or "de-1000" in query_lower:
        filters.append("Plant eq 'DE-1000'")
    if "2024" in query_lower:
        filters.append("year(OrderDate) eq 2024")

    filter_str = f"&$filter={' and '.join(filters)}" if filters else ""
    auth_note = f"[Auth: Bearer {sap_token[:30]}...]" if len(sap_token) > 30 else f"[Auth: Bearer {sap_token}]"
    return f"GET {base_url}/{entity}?$select={select}{filter_str}&$top=50  {auth_note}"


async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str,           # Per-request SAP access token (from OAuth2 SAML exchange)
    employee_id: str = "UNKNOWN"
) -> AsyncGenerator[str, None]:
    """
    Agentic router with two dynamically-instantiated tools:
      1. query_sap_odata  — grounded against sap_schema_catalog.json,
                            authorized with the per-user SAP token.
      2. query_company_docs — Vector DB similarity search (mock ChromaDB).

    The agent NEVER holds a master SAP credential. Every OData call is made
    with a short-lived, user-scoped SAP access token obtained via OAuth2SAMLBearer.
    SAP enforces its own row-level security via the named user mapping (SU01).
    """
    query_lower = query.lower()

    # ── Tool 1: query_company_docs (Vector RAG) ──────────────────────────────
    if "policy" in query_lower or "travel" in query_lower or "document" in query_lower or "procedure" in query_lower:
        thinking = f"[Agent: query_company_docs] Searching ChromaDB vector store as user {employee_id}... "
        for word in thinking.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.04)

        result = (
            "\n\n**Company Policy (ChromaDB similarity score: 0.94)**\n\n"
            "**Travel Policy (v2.3)**\n"
            "- All flights must be booked **14 days in advance**.\n"
            "- Business Class requires manager approval above $3,000 net fare.\n"
            "- Hotel stays are capped at **$250/night** in Tier 1 cities.\n"
            "- Expense reports must be submitted within **5 business days** of return."
        )
        for word in result.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.04)

    # ── Tool 2: query_sap_odata (Schema-Grounded, Per-User Token) ────────────
    elif any(kw in query_lower for kw in ["data", "sales", "order", "employee", "procurement", "purchase", "vendor", "sap", "table", "show"]):
        entity, columns, mock_data = _resolve_entity_and_columns(query_lower)
        odata_query = _build_odata_query(entity, columns, query_lower, sap_token)

        # Step 1: Report entity resolution and token context
        step1 = (
            f"[Agent: query_sap_odata] Tool instantiated for user **{employee_id}**. "
            f"Entity resolved: **{entity}**. "
            f"SAP token scope: user-delegated (OAuth2 SAML Bearer). "
        )
        for word in step1.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.04)

        # Step 2: Show the grounded OData query being constructed
        step2 = f"\n\nConstructing OData query (catalog-grounded, strictly no hallucinated columns):\n```\n{odata_query}\n```\n"
        for word in step2.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.03)

        # Step 3: Simulate 400 self-correction
        if "bad" in query_lower or "error" in query_lower or "hallucinate" in query_lower:
            error_msg = (
                "\n\n⚠ **SAP returned HTTP 400 Bad Request** — invented column `OrderTotal` not in catalog. "
                "Re-grounding against `sap_schema_catalog.json`... Retry with `NetAmount`... ✓ **Success.**\n"
            )
            for word in error_msg.split(" "):
                yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
                await asyncio.sleep(0.04)

        # Step 4: SAP enforces row-level security — only return records the user can see
        step3 = (
            f"\n\nSAP authorization check passed (SU01 named-user mapping active). "
            f"Returning {len(mock_data)} records visible to **{employee_id}**:\n"
        )
        for word in step3.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.03)

        # Emit structured tabular payload — frontend DataCard renders this instantly
        yield f"data: {json.dumps({'type': 'tabular', 'data': mock_data, 'entity': entity})}\n\n"

    # ── Fallback: conversational ──────────────────────────────────────────────
    else:
        history_note = f"(Session has {len(history)} prior messages.) " if history else ""
        tools_list = ", ".join(CATALOG.keys()) if CATALOG else "SalesOrderSet, EmployeeSet, ProcurementSet"
        msg = (
            f"Hello **{employee_id}**! {history_note}I am CIRA, your SAP Intelligence Agent.\n\n"
            f"Your session is authenticated with a user-delegated SAP token. "
            f"SAP enforces your authorization profile (SU01 roles) on every query.\n\n"
            f"**Available tools:**\n"
            f"- `query_sap_odata` — grounded against: {tools_list}\n"
            f"- `query_company_docs` — ChromaDB vector search for policies & SOPs\n\n"
            f"Try: *'Show me sales orders'*, *'Employee data'*, *'Travel policy'*, or *'Trigger bad request'*."
        )
        for word in msg.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.04)
