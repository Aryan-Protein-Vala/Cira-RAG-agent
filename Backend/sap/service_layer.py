"""SAP Business One Service Layer (OData v4) client.

Used when the HANA SQL port (30013/3xx15) is blocked but the Service Layer
(50000) is reachable, e.g. from a DMZ host.  It is deliberately a *secondary*
path: OData cannot join or aggregate across the whole company database the way
raw SQL can, so grouping is finished in Python.

Fixes vs. the previous version:
* session cookies now expire (B1 sessions die after ~30 min) and are re-minted
* 401 actually triggers a retry instead of silently returning nothing
* server-side paging is followed (@odata.nextLink) so >20 rows are returned
* DocStatus 'Open' is translated to the real enum `bost_Open`
* field names are mapped (OnHand -> QuantityOnStock, ...)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

import config
from .base import DataBackend
from .types_ import ColumnInfo, SapDataError, SapUnavailableError, TableInfo

log = logging.getLogger("cira.servicelayer")

# SAP B1 table -> Service Layer entity set
TABLE_TO_ENTITY = {
    "ORDR": "Orders",
    "OQUT": "Quotations",
    "OINV": "Invoices",
    "ORIN": "CreditNotes",
    "ODLN": "DeliveryNotes",
    "ORDN": "Returns",
    "OPOR": "PurchaseOrders",
    "OPCH": "PurchaseInvoices",
    "OPDN": "PurchaseDeliveryNotes",
    "ORPC": "PurchaseCreditNotes",
    "OCRD": "BusinessPartners",
    "OCPR": "ContactEmployees",
    "OCRG": "BusinessPartnerGroups",
    "OITM": "Items",
    "OITB": "ItemGroups",
    "OWHS": "Warehouses",
    "OHEM": "EmployeesInfo",
    "OUDP": "Departments",
    "OSLP": "SalesPersons",
    "OJDT": "JournalEntries",
    "OACT": "ChartOfAccounts",
    "ORCT": "IncomingPayments",
    "OVPM": "VendorPayments",
    "OOPR": "SalesOpportunities",
    "OSCL": "ServiceCalls",
    "OWOR": "ProductionOrders",
    "OUSR": "Users",
    "OCRN": "Currencies",
}
ENTITY_TO_TABLE = {v: k for k, v in TABLE_TO_ENTITY.items()}

# Column name differences between the HANA tables and the OData projection
FIELD_MAP = {
    "OITM": {
        "OnHand": "QuantityOnStock",
        "IsCommited": "QuantityOrderedByCustomers",
        "OnOrder": "QuantityOrderedFromVendors",
        "ItemName": "ItemName",
        "validFor": "Valid",
        "ItmsGrpCod": "ItemsGroupCode",
        "AvgPrice": "AvgStdPrice",
    },
    "OCRD": {
        "Balance": "CurrentAccountBalance",
        "validFor": "Valid",
        "GroupCode": "GroupCode",
        "E_Mail": "EmailAddress",
        "Phone1": "Phone1",
    },
    "OHEM": {
        "empID": "EmployeeID",
        "firstName": "FirstName",
        "lastName": "LastName",
        "jobTitle": "JobTitle",
        "dept": "Department",
        "salary": "Salary",
        "startDate": "StartDate",
        "Active": "Active",
    },
    "*": {
        "DocStatus": "DocumentStatus",
        "CANCELED": "Cancelled",
        "DocCur": "DocCurrency",
        "DocDate": "DocDate",
        "DocTotal": "DocTotal",
        "CardName": "CardName",
        "CardCode": "CardCode",
    },
}

STATUS_ENUMS = {
    "O": "bost_Open", "C": "bost_Close", "Open": "bost_Open", "Closed": "bost_Close",
}
YESNO_ENUMS = {"Y": "tYES", "N": "tNO"}


def map_field(table: str, column: str) -> str:
    return FIELD_MAP.get(table.upper(), {}).get(column) or FIELD_MAP["*"].get(column) or column


class ServiceLayerBackend(DataBackend):
    name = "SAP B1 Service Layer"
    dialect = "odata"
    simulated = False

    def __init__(self):
        self.base = config.SERVICE_LAYER_BASE
        self.company = config.SAP_B1_COMPANY_DB
        self.user = config.SAP_B1_USER
        self.password = config.SAP_B1_PASSWORD
        self.schema = self.company
        self._cookies: dict[str, str] | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        self._entity_sets: list[str] | None = None

    # ── session ──────────────────────────────────────────────────────────────
    def _client(self, cookies: dict | None = None) -> httpx.Client:
        return httpx.Client(
            verify=config.SAP_B1_VERIFY_SSL,
            timeout=config.SAP_B1_TIMEOUT_S,
            cookies=cookies or {},
            headers={"Accept": "application/json"},
        )

    def _login(self, force: bool = False) -> dict[str, str]:
        with self._lock:
            if not force and self._cookies and time.time() < self._expires_at:
                return self._cookies
            payload = {
                "CompanyDB": self.company,
                "UserName": self.user,
                "Password": self.password,
            }
            try:
                with self._client() as client:
                    resp = client.post(f"{self.base}/Login", json=payload)
            except Exception as exc:
                raise SapUnavailableError(f"Service Layer unreachable: {exc}") from exc
            if resp.status_code != 200:
                raise SapUnavailableError(
                    f"Service Layer login failed (HTTP {resp.status_code}): {resp.text[:200]}"
                )
            data = resp.json()
            timeout_min = int(data.get("SessionTimeout") or 30)
            self._cookies = {k: v for k, v in resp.cookies.items()}
            # renew a minute before B1 kills the session
            self._expires_at = time.time() + max(60, (timeout_min - 1) * 60)
            return self._cookies

    def _get(self, path: str, params: dict | None = None) -> dict:
        cookies = self._login()
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        for attempt in range(2):
            with self._client(cookies) as client:
                resp = client.get(url, params=params if attempt == 0 else None)
            if resp.status_code == 401 and attempt == 0:
                cookies = self._login(force=True)
                continue
            if resp.status_code >= 400:
                raise SapDataError(
                    f"Service Layer error {resp.status_code}: {resp.text[:300]}"
                )
            return resp.json()
        raise SapUnavailableError("Service Layer authentication kept failing.")

    # ── interface ────────────────────────────────────────────────────────────
    def ping(self) -> dict:
        started = time.time()
        try:
            self._login(force=True)
            return {
                "ok": True,
                "backend": self.name,
                "base_url": self.base,
                "company_db": self.company,
                "latency_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "backend": self.name,
                "base_url": self.base,
                "error": str(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }

    def entity_sets(self) -> list[str]:
        if self._entity_sets is None:
            try:
                doc = self._get("")
                self._entity_sets = sorted(
                    str(e.get("name")) for e in doc.get("value", []) if e.get("name")
                )
            except Exception as exc:
                log.warning("Could not read Service Layer service document: %s", exc)
                self._entity_sets = sorted(TABLE_TO_ENTITY.values())
        return self._entity_sets

    def list_tables(self, pattern: str = "", include_views: bool = True,
                    limit: int = 1000) -> list[TableInfo]:
        from . import entities

        out = []
        for entity in self.entity_sets():
            table = ENTITY_TO_TABLE.get(entity, entity)
            out.append(
                TableInfo(
                    name=table,
                    schema=self.company,
                    description=entities.describe_table_name(table) or f"OData entity set {entity}",
                    kind="ENTITY",
                )
            )
        if pattern:
            needle = pattern.lower()
            out = [t for t in out if needle in t.name.lower() or needle in t.description.lower()]
        return out[:limit]

    def get_columns(self, table: str) -> list[ColumnInfo]:
        entity = TABLE_TO_ENTITY.get(table.upper(), table)
        try:
            data = self._get(entity, {"$top": 1})
        except Exception:
            return []
        rows = data.get("value") or []
        if not rows:
            return []
        cols = []
        for i, (key, value) in enumerate(rows[0].items()):
            if key.startswith("@") or isinstance(value, (list, dict)):
                continue
            dtype = (
                "INTEGER" if isinstance(value, int) and not isinstance(value, bool)
                else "DECIMAL" if isinstance(value, float)
                else "NVARCHAR(254)"
            )
            cols.append(ColumnInfo(name=key, data_type=dtype, position=i + 1))
        return cols

    def execute(self, sql: str, params: list[Any] | None = None):
        raise SapDataError(
            "Raw SQL is not available over the Service Layer. "
            "Use the structured query tool, or open HANA port "
            f"{config.HANA_PORT} to enable full SQL access."
        )

    # ── data ─────────────────────────────────────────────────────────────────
    def fetch_entity(
        self,
        table: str,
        select: list[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
        order_by: list[tuple[str, str]] | None = None,
        limit: int = 500,
    ) -> tuple[list[str], list[dict]]:
        entity = TABLE_TO_ENTITY.get(table.upper(), table)
        params: dict[str, Any] = {}
        if select:
            params["$select"] = ",".join(map_field(table, c) for c in select)
        clauses = []
        for column, op, value in filters or []:
            field = map_field(table, column)
            clauses.append(_odata_clause(field, op, value))
        if clauses:
            params["$filter"] = " and ".join(c for c in clauses if c)
        if order_by:
            params["$orderby"] = ",".join(
                f"{map_field(table, c)} {'desc' if d.lower().startswith('d') else 'asc'}"
                for c, d in order_by
            )

        rows: list[dict] = []
        page_params = dict(params)
        page_params["$top"] = min(limit, 100)
        url = entity
        while len(rows) < limit:
            data = self._get(url, page_params)
            batch = data.get("value") or []
            rows.extend(
                {k: v for k, v in row.items() if not k.startswith("@") and not isinstance(v, (list, dict))}
                for row in batch
            )
            next_link = data.get("@odata.nextLink") or data.get("odata.nextLink")
            if not next_link or not batch:
                break
            url = next_link if next_link.startswith("http") else f"{self.base}/{next_link}"
            page_params = None  # nextLink already carries the query
        rows = rows[:limit]
        columns = list(rows[0].keys()) if rows else (select or [])
        return columns, rows


def _odata_clause(field: str, op: str, value: Any) -> str:
    op = (op or "eq").lower()
    if field.lower() in ("documentstatus", "docstatus") and isinstance(value, str):
        value = STATUS_ENUMS.get(value, STATUS_ENUMS.get(value.title(), value))
        return f"{field} eq '{value}'"
    if isinstance(value, str) and value in YESNO_ENUMS and field.lower() in ("cancelled", "valid", "active", "frozen"):
        return f"{field} eq '{YESNO_ENUMS[value]}'"

    def literal(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    if op in ("contains", "like"):
        return f"contains({field},{literal(str(value).strip('%'))})"
    if op == "startswith":
        return f"startswith({field},{literal(value)})"
    if op == "endswith":
        return f"endswith({field},{literal(value)})"
    if op in ("in", "notin"):
        values = value if isinstance(value, (list, tuple)) else [value]
        joined = " or ".join(f"{field} eq {literal(v)}" for v in values)
        return f"({joined})" if op == "in" else f"not ({joined})"
    mapping = {"eq": "eq", "ne": "ne", "gt": "gt", "gte": "ge", "ge": "ge",
               "lt": "lt", "lte": "le", "le": "le"}
    return f"{field} {mapping.get(op, 'eq')} {literal(value)}"
