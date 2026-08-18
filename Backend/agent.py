from typing import Dict, Any
import json

# Set up simple mock schema
MOCK_SAP_DATA = [
    {"id": "1001", "product": "Premium Widget", "quantity": 50, "status": "Shipped", "date": "2026-08-15"},
    {"id": "1002", "product": "Standard Widget", "quantity": 120, "status": "Processing", "date": "2026-08-17"},
    {"id": "1003", "product": "Super Widget", "quantity": 10, "status": "Pending", "date": "2026-08-18"}
]

def query_sap_data(query: str) -> str:
    """Mock Tool: Converts natural language request to SAP OData query and returns JSON."""
    return json.dumps(MOCK_SAP_DATA)

def process_chat_query(query: str, session_id: str) -> Dict[str, Any]:
    """
    Agentic Router Mock.
    If the user asks for tabular data, route to `query_sap_data`.
    Otherwise, return a standard text response.
    """
    query_lower = query.lower()
    
    if "data" in query_lower or "sales" in query_lower or "table" in query_lower or "sap" in query_lower:
        sap_json = query_sap_data(query)
        return {
            "type": "tabular",
            "text": "Here is the tabular data you requested from SAP.",
            "data": json.loads(sap_json)
        }
    else:
        return {
            "type": "text",
            "text": f"I received your query: '{query}'. How else can I help you today? (Ask for 'data' to see the SAP OData tool in action!)"
        }
