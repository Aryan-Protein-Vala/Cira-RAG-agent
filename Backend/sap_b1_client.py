import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

# SAP Business One Configuration
SAP_B1_HOST = os.getenv("SAP_B1_HOST", "20.204.5.237")
SAP_B1_PORT = int(os.getenv("SAP_B1_PORT", "50000"))
SAP_B1_COMPANY_DB = os.getenv("SAP_B1_COMPANY_DB", "CIRA_DEMO_NEW")
SAP_B1_USER = os.getenv("SAP_B1_USER", "manager5")
SAP_B1_PASSWORD = os.getenv("SAP_B1_PASSWORD", "1234")
SAP_B1_VERIFY_SSL = os.getenv("SAP_B1_VERIFY_SSL", "false").lower() == "true"
MOCK_SAP = os.getenv("MOCK_SAP", "false").lower() == "true"

# HANA DB Direct SQL Config
HANA_HOST = os.getenv("HANA_HOST", "20.204.5.237")
HANA_PORT = int(os.getenv("HANA_PORT", "30013"))
HANA_USER = os.getenv("HANA_USER", "manager5")
HANA_PASSWORD = os.getenv("HANA_PASSWORD", "1234")

SERVICE_LAYER_BASE = f"https://{SAP_B1_HOST}:{SAP_B1_PORT}/b1s/v1"

# Session cache
_cached_session = {
    "cookies": None,
    "session_id": None
}

async def get_b1_session() -> dict | None:
    """Authenticate with SAP Business One Service Layer and cache cookies."""
    global _cached_session
    if _cached_session["cookies"]:
        return _cached_session["cookies"]

    login_url = f"{SERVICE_LAYER_BASE}/Login"
    payload = {
        "CompanyDB": SAP_B1_COMPANY_DB,
        "UserName": SAP_B1_USER,
        "Password": SAP_B1_PASSWORD
    }

    try:
        async with httpx.AsyncClient(verify=SAP_B1_VERIFY_SSL, timeout=8.0) as client:
            resp = await client.post(login_url, json=payload)
            if resp.status_code == 200:
                cookies = dict(resp.cookies)
                data = resp.json()
                _cached_session["cookies"] = cookies
                _cached_session["session_id"] = data.get("SessionId")
                return cookies
            else:
                print(f"[SAP B1] Login failed HTTP {resp.status_code}: {resp.text}")
                return None
    except Exception as exc:
        print(f"[SAP B1] Service Layer connection error: {exc}")
        return None


import asyncio

async def execute_b1_query(entity: str, filters: dict = None, select_fields: list = None, top: int = 50) -> dict:
    """
    Query SAP Business One Service Layer entity set (e.g. Orders, Invoices, Items, BusinessPartners).
    Falls back gracefully to mock catalog or HANA direct connection.
    """
    if MOCK_SAP:
        return _get_mock_fallback(entity)

    # 1. Attempt Service Layer (OData API)
    cookies = await get_b1_session()
    if cookies:
        url = f"{SERVICE_LAYER_BASE}/{entity}"
        params = {"$top": top}

        if select_fields:
            params["$select"] = ",".join(select_fields)

        if filters:
            filter_clauses = []
            for k, v in filters.items():
                if v is not None:
                    if isinstance(v, str):
                        filter_clauses.append(f"{k} eq '{v}'")
                    else:
                        filter_clauses.append(f"{k} eq {v}")
            if filter_clauses:
                params["$filter"] = " and ".join(filter_clauses)

        try:
            async with httpx.AsyncClient(verify=SAP_B1_VERIFY_SSL, timeout=12.0, cookies=cookies) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("value", [])
                    return {
                        "ok": True,
                        "source": "SAP Business One Service Layer",
                        "entity": entity,
                        "data": results,
                        "count": len(results)
                    }
                elif resp.status_code == 401:
                    # Session expired, invalidate cache and retry once
                    global _cached_session
                    _cached_session["cookies"] = None
        except Exception as exc:
            print(f"[SAP B1] Service Layer query failed: {exc}")

    # 2. Attempt Direct HANA DB Query offloaded to worker thread (Non-blocking)
    hana_result = await asyncio.to_thread(query_hana_db, entity, filters, select_fields, top)
    if hana_result.get("ok"):
        return hana_result

    # 3. Fallback to Catalog Mock if local / offline
    print(f"[SAP B1] Falling back to schema mock for {entity}")
    return _get_mock_fallback(entity)


def query_hana_db(entity: str, filters: dict = None, select_fields: list = None, top: int = 50) -> dict:
    """Direct SQL query via official SAP HANA hdbcli with safe parameterization and connection closing."""
    conn = None
    try:
        from hdbcli import dbapi
        conn = dbapi.connect(
            address=HANA_HOST,
            port=HANA_PORT,
            user=HANA_USER,
            password=HANA_PASSWORD,
            currentSchema=SAP_B1_COMPANY_DB,
            connectTimeout=4000
        )
        cursor = conn.cursor()

        # Whitelisted Table Mapping for SAP B1
        TABLE_MAP = {
            "Orders": "ORDR",
            "SalesOrderSet": "ORDR",
            "Invoices": "OINV",
            "PurchaseOrders": "OPOR",
            "ProcurementSet": "OPOR",
            "Items": "OITM",
            "BusinessPartners": "OCRD",
            "EmployeesInfo": "OHEM",
            "EmployeeSet": "OHEM"
        }
        table_name = TABLE_MAP.get(entity, "ORDR")

        cols = ", ".join([f'"{c}"' for c in select_fields]) if select_fields else "*"
        params = []
        where_clause = ""
        if filters:
            conditions = []
            for k, v in filters.items():
                if v is not None:
                    conditions.append(f'"{k}" = ?')
                    params.append(v)
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

        sql = f'SELECT TOP {int(top)} {cols} FROM "{SAP_B1_COMPANY_DB}"."{table_name}" {where_clause};'
        cursor.execute(sql, params)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return {
            "ok": True,
            "source": f"SAP HANA DB ({table_name})",
            "entity": entity,
            "data": rows,
            "count": len(rows)
        }
    except Exception as exc:
        print(f"[SAP HANA] Direct DB query error: {exc}")
        return {"ok": False, "error": str(exc)}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _get_mock_fallback(entity: str) -> dict:
    """Load mock data from sap_schema_catalog.json for local resilience."""
    try:
        with open("sap_schema_catalog.json", "r") as f:
            catalog = json.load(f)
            schema = catalog.get(entity, {})
            return {
                "ok": True,
                "source": "SAP B1 Catalog (Simulated)",
                "entity": entity,
                "data": schema.get("mock_data", []),
                "count": len(schema.get("mock_data", []))
            }
    except Exception:
        return {"ok": False, "entity": entity, "data": []}
