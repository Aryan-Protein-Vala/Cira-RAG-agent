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
        # Default to Sales
        entity = "SalesOrderSet"

    if entity not in CATALOG:
        return entity, [], []

    schema = CATALOG[entity]
    columns = list(schema["columns"].keys())
    data = schema["mock_data"]
    return entity, columns, data


def _build_odata_query(entity: str, columns: list, query_lower: str) -> str:
    """
    Constructs a strict OData query string using ONLY catalog-defined fields.
    """
    base_url = "[SAP_ODATA_BASE_URL]"
    select = ",".join(columns)
    
    # Build $filter based on keywords
    filters = []
    if "delivered" in query_lower or "status" in query_lower:
        filters.append("Status eq 'Delivered'")
    if "germany" in query_lower or "de-1000" in query_lower:
        filters.append("Plant eq 'DE-1000'")
    if "2024" in query_lower:
        filters.append("year(OrderDate) eq 2024")

    filter_str = ""
    if filters:
        filter_str = f"&$filter={' and '.join(filters)}"

    return f"GET {base_url}/{entity}?$select={select}{filter_str}&$top=50"


async def stream_chat_query(query: str, history: list) -> AsyncGenerator[str, None]:
    """
    Agentic router with two tools:
      1. query_sap_odata  — grounded against sap_schema_catalog.json
      2. query_company_docs — Vector DB (mock ChromaDB similarity search)
    Streams SSE chunks: {type: 'chunk', text} and {type: 'tabular', data}
    """
    query_lower = query.lower()

    # ── Tool 1: query_company_docs (Vector RAG) ──────────────────────────────
    if "policy" in query_lower or "travel" in query_lower or "document" in query_lower or "procedure" in query_lower:
        thinking = "Invoking tool: query_company_docs → Searching ChromaDB vector store... "
        for word in thinking.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.04)

        result = (
            "\n\nAccording to the company policy documents (similarity score: 0.94):\n\n"
            "**Travel Policy (v2.3)**\n"
            "- All flights must be booked **14 days in advance**.\n"
            "- Business Class requires manager approval above $3,000 net fare.\n"
            "- Hotel stays are capped at **$250/night** in Tier 1 cities.\n"
            "- Expense reports must be submitted within **5 business days** of return."
        )
        for word in result.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.04)

    # ── Tool 2: query_sap_odata (Schema-Grounded SAP Tool) ──────────────────
    elif any(kw in query_lower for kw in ["data", "sales", "order", "employee", "procurement", "purchase", "vendor", "sap", "table", "show"]):
        entity, columns, mock_data = _resolve_entity_and_columns(query_lower)
        odata_query = _build_odata_query(entity, columns, query_lower)

        # Simulate grounding + OData construction
        step1 = f"Invoking tool: query_sap_odata → Entity resolved: {entity} "
        for word in step1.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.04)

        step2 = f"\nConstructing OData query (grounded against sap_schema_catalog.json):\n`{odata_query}`\n"
        for word in step2.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.03)

        # Simulate 400 self-correction if "bad request" in query
        if "bad" in query_lower or "error" in query_lower or "hallucinate" in query_lower:
            error_msg = "\n⚠ SAP returned 400 Bad Request (invented column: `OrderTotal`). Retrying with catalog-only fields... ✓ Retry successful.\n"
            for word in error_msg.split(" "):
                yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
                await asyncio.sleep(0.04)

        step3 = f"\nSAP returned {len(mock_data)} records. Rendering structured data:\n"
        for word in step3.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.03)

        # Emit the tabular payload — frontend DataCard renders this instantly
        yield f"data: {json.dumps({'type': 'tabular', 'data': mock_data, 'entity': entity})}\n\n"

    # ── Fallback: general conversational response ────────────────────────────
    else:
        history_note = f"(Session has {len(history)} prior messages.) " if history else ""
        tools_list = ", ".join(CATALOG.keys()) if CATALOG else "SalesOrderSet, EmployeeSet, ProcurementSet"
        msg = (
            f"{history_note}Hello! I am CIRA, your SAP Intelligence Agent.\n\n"
            f"I have two tools available:\n"
            f"- **query_sap_odata** — grounded against: {tools_list}\n"
            f"- **query_company_docs** — ChromaDB vector search for policies & SOPs\n\n"
            f"Try: *'Show me sales orders'*, *'Employee data'*, *'Travel policy'*, or *'Trigger bad request'*."
        )
        for word in msg.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.04)
