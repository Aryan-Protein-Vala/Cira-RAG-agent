import json
import asyncio
import re
import httpx
from typing import AsyncGenerator
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import os
from dotenv import load_dotenv

load_dotenv()

try:
    with open("sap_schema_catalog.json", "r") as f:
        CATALOG: dict = json.load(f)
except FileNotFoundError:
    CATALOG = {}

# Mock settings
MOCK_SAP = True
SAP_ODATA_BASE_URL = "[SAP_ODATA_BASE_URL]"

# OpenRouter Settings for testing
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-dummy")
MODEL_NAME = "meta-llama/llama-3-8b-instruct:free"

llm = ChatOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    model=MODEL_NAME,
    temperature=0.1
)

def _build_odata_query(entity: str, filters_dict: dict = None) -> str:
    if entity not in CATALOG:
        return f"{SAP_ODATA_BASE_URL}/{entity}?$top=50"

    schema_cols = CATALOG[entity]["columns"]
    all_cols = list(schema_cols.keys())
    select = ",".join(all_cols)

    filters = []
    if filters_dict:
        # Construct basic filters using schema validation
        if "Status" in schema_cols and filters_dict.get("status"):
            filters.append(f"Status eq '{filters_dict['status']}'")
        if "Plant" in schema_cols and filters_dict.get("plant"):
            filters.append(f"Plant eq '{filters_dict['plant']}'")
        if "OrderDate" in schema_cols and filters_dict.get("year"):
            filters.append(f"year(OrderDate) eq {filters_dict['year']}")

    filter_str = f"&$filter={' and '.join(filters)}" if filters else ""
    return f"{SAP_ODATA_BASE_URL}/{entity}?$select={select}{filter_str}&$top=50&$format=json"


async def _execute_sap_odata(entity: str, filters_dict: dict, sap_token: str, employee_id: str) -> dict:
    url = _build_odata_query(entity, filters_dict)

    if MOCK_SAP:
        schema = CATALOG.get(entity, {})
        return {"ok": True, "entity": entity, "url": url, "data": schema.get("mock_data", [])}

    headers = {
        "Authorization": f"Bearer {sap_token}",
        "Accept": "application/json",
        "sap-client": "100",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)

        if resp.status_code == 403:
            return {"ok": False, "error": "User is unauthorized to access this data.", "entity": entity, "status": 403}

        if resp.status_code == 400:
            # Self-correction: drop hint filters
            all_cols = list(CATALOG.get(entity, {}).get("columns", {}).keys())
            retry_url = f"{SAP_ODATA_BASE_URL}/{entity}?$select={','.join(all_cols)}&$top=50&$format=json"
            resp2 = await client.get(retry_url, headers=headers)
            if resp2.status_code == 200:
                payload = resp2.json()
                return {"ok": True, "entity": entity, "url": retry_url, "data": payload.get("d", {}).get("results", []), "self_corrected": True}
            return {"ok": False, "error": f"SAP returned {resp2.status_code} after self-correction retry.", "entity": entity}

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "error": f"SAP returned HTTP {exc.response.status_code}.", "entity": entity}

        payload = resp.json()
        return {"ok": True, "entity": entity, "url": url, "data": payload.get("d", {}).get("results", [])}


async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str,
    employee_id: str = "UNKNOWN"
) -> AsyncGenerator[str, None]:
    """
    Real LangGraph ReAct Agent powered by OpenRouter.
    Dynamic tools capture the per-request SAP token and stream SSE chunks.
    """

    # 1. Define tools dynamically to capture context (sap_token, employee_id)
    @tool
    async def query_sap_odata(entity: str, status: str = None, plant: str = None, year: int = None) -> dict:
        """
        Query SAP OData grounded catalog. 
        Valid entities: SalesOrderSet, EmployeeSet, ProcurementSet.
        Optional filters: status ('Delivered'), plant ('DE-1000'), year (2024).
        """
        filters_dict = {"status": status, "plant": plant, "year": year}
        return await _execute_sap_odata(entity, filters_dict, sap_token, employee_id)

    @tool
    async def query_company_docs(query: str) -> str:
        """Search ChromaDB vector store for company policies, travel documents, or SOPs."""
        await asyncio.sleep(0.05)
        return (
            "**Travel Policy (v2.3)** [similarity: 0.94]\n"
            "- All flights must be booked 14 days in advance.\n"
            "- Business Class requires manager approval above $3,000 net fare.\n"
            "- Hotel stays are capped at $250/night in Tier 1 cities.\n"
            "- Expense reports must be submitted within 5 business days of return."
        )

    tools = [query_sap_odata, query_company_docs]
    agent = create_react_agent(llm, tools)

    # 2. Build Message History
    system_prompt = (
        f"You are CIRA, an enterprise SAP Intelligence Agent for user {employee_id}. "
        "Use your tools to answer data queries. "
        "IMPORTANT: Only use entity names exactly as defined in your tool schema."
    )
    messages = [SystemMessage(content=system_prompt)]
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            # For simplicity, passing basic assistant text history
            messages.append(AIMessage(content=msg.content))
    messages.append(HumanMessage(content=query))

    # 3. Stream Events (v2) from LangGraph
    try:
        async for event in agent.astream_events({"messages": messages}, version="v2"):
            kind = event["event"]

            # Stream LLM tokens
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                if content and isinstance(content, str):
                    # Replace newlines so they don't break SSE framing (if streaming raw tokens)
                    # For safety, yield word by word or token by token
                    yield f"data: {json.dumps({'type': 'chunk', 'text': content})}\n\n"

            # Announce tool starts
            elif kind == "on_tool_start":
                tool_name = event["name"]
                if tool_name in ["query_sap_odata", "query_company_docs"]:
                    msg = f"\n\n*[Agent: invoking {tool_name}...]*\n\n"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"

            # Handle tool ends (trigger DataCard if SAP)
            elif kind == "on_tool_end":
                tool_name = event["name"]
                output = event["data"].get("output", "")
                
                if tool_name == "query_sap_odata" and isinstance(output, dict) and output.get("ok"):
                    # Yield tabular data directly so UI can render DataCard
                    yield f"data: {json.dumps({'type': 'tabular', 'data': output['data'], 'entity': output['entity']})}\n\n"
                    msg = f"\n\n*[Agent: SAP returned {len(output['data'])} records]*\n\n"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"
                
                elif tool_name == "query_company_docs":
                    msg = f"\n\n*[Agent: Retrieved document context]*\n\n"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'chunk', 'text': f' An error occurred during reasoning: {str(e)}'})}\n\n"
