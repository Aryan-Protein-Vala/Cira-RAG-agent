import json
import asyncio
from typing import AsyncGenerator

MOCK_SAP_DATA = [
    {"id": "1001", "product": "Premium Widget", "quantity": 50, "status": "Shipped", "date": "2026-08-15"},
    {"id": "1002", "product": "Standard Widget", "quantity": 120, "status": "Processing", "date": "2026-08-17"},
    {"id": "1003", "product": "Super Widget", "quantity": 10, "status": "Pending", "date": "2026-08-18"}
]

try:
    with open("sap_schema_catalog.json", "r") as f:
        SCHEMA = json.load(f)
except FileNotFoundError:
    SCHEMA = {}

async def stream_chat_query(query: str, history: list) -> AsyncGenerator[str, None]:
    """
    Mock Agent running astream_events logic with custom tools (SAP + Vector DB).
    Yields SSE chunks.
    """
    query_lower = query.lower()
    
    # 1. Simulating Langchain grounding and Vector DB searching
    if "policy" in query_lower or "travel" in query_lower or "document" in query_lower:
        msg = "I am searching the Vector Database (query_company_docs) for company policies... "
        for word in msg.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.05)
            
        res = "\nAccording to the unstructured documents in ChromaDB, the travel policy dictates that all flights must be booked 14 days in advance and require manager approval for Business Class."
        for word in res.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.05)
            
    elif "data" in query_lower or "sales" in query_lower or "table" in query_lower or "sap" in query_lower:
        if "bad" in query_lower or "error" in query_lower:
            msg = "Constructing OData query... Oh wait, I hallucinated a column and received 400 Bad Request! Retrying using strictly fields from sap_schema_catalog.json... Success!\n\n"
            for word in msg.split():
                yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
                await asyncio.sleep(0.05)
        else:
            msg = "Querying SAP OData securely using grounded schema...\n"
            for word in msg.split():
                yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
                await asyncio.sleep(0.05)
        
        yield f"data: {json.dumps({'type': 'tabular', 'data': MOCK_SAP_DATA})}\n\n"
        
        followup = "\nHere is the tabular data you requested."
        for word in followup.split(" "):
            yield f"data: {json.dumps({'type': 'chunk', 'text': ' ' + word})}\n\n"
            await asyncio.sleep(0.05)
            
    else:
        history_context = ""
        if len(history) > 0:
            history_context = f"(I remember {len(history)} previous messages in this session!) "
            
        msg = f"I received your query: '{query}'. {history_context}I can query SAP data or search unstructured company policies. Try asking about 'sales data', 'travel policy', or 'trigger bad request'."
        for word in msg.split():
            yield f"data: {json.dumps({'type': 'chunk', 'text': word + ' '})}\n\n"
            await asyncio.sleep(0.05)
