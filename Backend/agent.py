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

from sap_b1_client import execute_b1_query, SAP_B1_COMPANY_DB

# OpenRouter Settings for testing
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-dummy")
MODEL_NAME = "openrouter/free"

llm = ChatOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    model=MODEL_NAME,
    temperature=0.1
)


def _generate_chart_payload(entity: str, data: list, user_query: str) -> dict | None:
    if not data or not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        return None
    
    q_lower = user_query.lower()
    chart_type = 'bar'
    if 'pie' in q_lower or 'distribution' in q_lower or 'share' in q_lower:
        chart_type = 'pie'
    elif 'line' in q_lower or 'trend' in q_lower or 'growth' in q_lower or 'over time' in q_lower:
        chart_type = 'line'
    elif 'area' in q_lower:
        chart_type = 'area'

    first = data[0]
    keys = list(first.keys())
    if not keys:
        return None

    # Smart mapping for SAP Business One entities
    if entity in ("Orders", "SalesOrderSet", "Invoices"):
        x_key = "CardName" if "CardName" in first else ("DocNum" if "DocNum" in first else keys[0])
        y_key = "DocTotal" if "DocTotal" in first else ("NetAmount" if "NetAmount" in first else (keys[1] if len(keys) > 1 else keys[0]))
        title = f"{entity} Value by {x_key}"
    elif entity in ("Items",):
        x_key = "ItemName" if "ItemName" in first else "ItemCode"
        y_key = "QuantityOnStock" if "QuantityOnStock" in first else ("AvgPrice" if "AvgPrice" in first else (keys[1] if len(keys) > 1 else keys[0]))
        title = f"Inventory Stock: {y_key} by {x_key}"
    elif entity in ("PurchaseOrders", "ProcurementSet"):
        x_key = "CardName" if "CardName" in first else ("VendorName" if "VendorName" in first else keys[0])
        y_key = "DocTotal" if "DocTotal" in first else ("NetAmount" if "NetAmount" in first else (keys[1] if len(keys) > 1 else keys[0]))
        title = f"Procurement Value by {x_key}"
    elif entity in ("BusinessPartners",):
        x_key = "CardName" if "CardName" in first else ("City" if "City" in first else keys[0])
        y_key = "CurrentAccountBalance" if "CurrentAccountBalance" in first else (keys[1] if len(keys) > 1 else keys[0])
        title = f"Account Balance by {x_key}"
    elif entity in ("EmployeesInfo", "EmployeeSet"):
        x_key = "Department" if "Department" in first else "JobTitle"
        y_key = "Salary" if "Salary" in first else (keys[1] if len(keys) > 1 else keys[0])
        title = f"Compensation Breakdown by {x_key}"
    else:
        x_key = next((k for k in keys if isinstance(first[k], str)), keys[0])
        y_key = next((k for k in keys if isinstance(first[k], (int, float))), (keys[1] if len(keys) > 1 else keys[0]))
        title = f"{entity} Metrics"

    return {
        "type": "chart",
        "chartType": chart_type,
        "title": title,
        "data": data,
        "xKey": x_key,
        "yKey": y_key,
        "category": f"SAP B1 ({entity})"
    }


async def stream_chat_query(
    query: str,
    history: list,
    sap_token: str,
    employee_id: str = "UNKNOWN"
) -> AsyncGenerator[str, None]:
    """
    Real LangGraph ReAct Agent powered by OpenRouter and connected to SAP Business One on HANA.
    """

    # 1. Define tools dynamically to capture context
    @tool
    async def query_sap_b1(entity: str, status: str = None, card_name: str = None, year: int = None) -> dict:
        """
        Query SAP Business One on HANA live schema.
        Valid SAP B1 entities:
        - 'Orders' (Sales Orders / ORDR table)
        - 'Invoices' (A/R Invoices / OINV table)
        - 'Items' (Inventory stock & prices / OITM table)
        - 'PurchaseOrders' (Procurement & vendor orders / OPOR table)
        - 'BusinessPartners' (Customers & Vendors / OCRD table)
        - 'EmployeesInfo' (Staff & payroll / OHEM table)
        - Legacy aliases also supported: 'SalesOrderSet', 'EmployeeSet', 'ProcurementSet'
        Optional filters: status ('Open'/'Closed'), card_name ('Acme'), year (2024).
        """
        filters = {}
        if status:
            filters["DocStatus"] = status
        if card_name:
            filters["CardName"] = card_name
        return await execute_b1_query(entity=entity, filters=filters)

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

    tools = [query_sap_b1, query_company_docs]
    agent = create_react_agent(llm, tools)

    # 2. Build Message History with Proactive Tool Execution System Prompt
    system_prompt = (
        f"You are CIRA, the executive SAP Business One AI intelligence agent for company database '{SAP_B1_COMPANY_DB}' and user '{employee_id}'.\n"
        "CORE PROTOCOL:\n"
        "1. When the user asks for data, reports, tables, or charts (e.g. sales, orders, invoices, inventory items, vendors, employees), ALWAYS invoke the 'query_sap_b1' tool.\n"
        "2. Valid entities: Orders, Items, Invoices, PurchaseOrders, BusinessPartners, EmployeesInfo.\n"
        "3. CRITICAL: After calling the tool, the UI AUTOMATICALLY renders beautiful interactive tables and chart visualizations from the raw data — do NOT repeat the data in your text response.\n"
        "4. Your ONLY text output after fetching data must be a crisp 1-2 sentence executive summary (e.g. 'You have 2 invoices totaling $79,400 with $63,200 already collected.'). NO inline tables, NO lists of rows, NO markdown tables.\n"
        "5. Never refuse to fetch data — always call the tool immediately."
    )
    messages = [SystemMessage(content=system_prompt)]
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    messages.append(HumanMessage(content=query))

    # 3. Stream Events (v2) from LangGraph
    sap_data_emitted = False  # once we emit tabular/chart, suppress LLM inline data text

    try:
        async for event in agent.astream_events({"messages": messages}, version="v2"):
            kind = event["event"]

            # Stream LLM text tokens
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                if content and isinstance(content, str):
                    if sap_data_emitted:
                        # Suppress markdown table rows / enumerated data lists
                        lines = content.split("\n")
                        clean = "\n".join(
                            l for l in lines
                            if not (l.strip().startswith("|") or
                                    re.match(r"^\s*\d+[.)]\s+", l) or
                                    re.match(r"^-{3,}", l))
                        )
                        if clean.strip():
                            yield f"data: {json.dumps({'type': 'chunk', 'text': clean})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'chunk', 'text': content})}\n\n"

            # Announce tool starts
            elif kind == "on_tool_start":
                tool_name = event["name"]
                if tool_name in ("query_sap_b1", "query_sap_odata"):
                    yield f"data: {json.dumps({'type': 'source', 'name': 'SAP Business One (HANA)'})}\n\n"
                elif tool_name == "query_company_docs":
                    yield f"data: {json.dumps({'type': 'source', 'name': 'Company Knowledge Base'})}\n\n"

            # Handle tool ends — LangGraph wraps returns in a ToolMessage object
            elif kind == "on_tool_end":
                tool_name = event["name"]
                raw_output = event["data"].get("output")

                # Normalize output: ToolMessage → dict
                output = {}
                if isinstance(raw_output, dict):
                    output = raw_output
                elif raw_output is not None:
                    # ToolMessage: .content is a JSON string of the actual return value
                    content_str = getattr(raw_output, "content", None)
                    if content_str is None:
                        content_str = str(raw_output)
                    try:
                        output = json.loads(content_str)
                    except Exception:
                        # Last resort: try parsing the string representation
                        try:
                            import ast
                            output = ast.literal_eval(content_str)
                        except Exception:
                            output = {}

                if tool_name in ("query_sap_b1", "query_sap_odata") and output.get("ok"):
                    raw_data = output.get("data", [])
                    entity_name = output.get("entity", "SAP Data")

                    # Emit DataCard SSE event
                    yield f"data: {json.dumps({'type': 'tabular', 'data': raw_data, 'entity': entity_name})}\n\n"
                    sap_data_emitted = True

                    # Emit ChartCard SSE event when data is visualizable
                    chart_payload = _generate_chart_payload(entity_name, raw_data, query)
                    if chart_payload:
                        yield f"data: {json.dumps(chart_payload)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'chunk', 'text': f'⚠ An error occurred: {str(e)}'})}\n\n"
