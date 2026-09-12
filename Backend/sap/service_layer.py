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
    "bost_Open": "bost_Open", "bost_Close": "bost_Close",
}
YESNO_ENUMS = {"Y": "tYES", "N": "tNO", "true": "tYES", "false": "tNO", "tYES": "tYES", "tNO": "tNO"}
CARD_TYPE_ENUMS = {
    "C": "cCustomer",
    "Customer": "cCustomer",
    "customer": "cCustomer",
    "cCustomer": "cCustomer",
    "S": "cSupplier",
    "Vendor": "cSupplier",
    "vendor": "cSupplier",
    "Supplier": "cSupplier",
    "supplier": "cSupplier",
    "cSupplier": "cSupplier",
    "L": "cLid",
    "Lead": "cLid",
    "lead": "cLid",
    "cLid": "cLid",
}


def map_field(table: str, column: str) -> str:
    return FIELD_MAP.get(table.upper(), {}).get(column) or FIELD_MAP["*"].get(column) or column


def normalize_write_payload(table_or_entity: str, data: dict) -> dict:
    """Prepare and sanitize incoming form data for SAP B1 Service Layer POST requests."""
    import re
    table = ENTITY_TO_TABLE.get(table_or_entity, table_or_entity).upper()
    entity = TABLE_TO_ENTITY.get(table, table_or_entity)

    DOCUMENT_ENTITIES = {
        "Orders", "Invoices", "PurchaseOrders", "Quotations", "CreditNotes",
        "PurchaseQuotations", "PurchaseInvoices", "DeliveryNotes", "Returns",
        "PurchaseDeliveryNotes", "PurchaseCreditNotes", "Drafts"
    }
    DOCUMENT_ONLY_FIELDS = {"DocDate", "DocDueDate", "DocTotal", "DocStatus",
                            "DocumentStatus", "DocCurrency", "DocCur", "TaxDate",
                            "ShipDate", "Confirmed", "PickStatus"}
    MASTER_DATA_ENTITIES = {"BusinessPartners", "Items", "ItemGroups",
                            "BusinessPartnerGroups", "Warehouses", "Departments",
                            "SalesPersons", "EmployeesInfo", "Users", "Currencies",
                            "ChartOfAccounts", "ContactEmployees"}

    out = {}
    for k, v in data.items():
        if v is None or v == "":
            continue

        # Drop document-only fields when writing to master-data entities
        if entity in MASTER_DATA_ENTITIES and k in DOCUMENT_ONLY_FIELDS:
            log.debug("normalize_write_payload: dropping document-only field %r for entity %s", k, entity)
            continue

        # Drop master-data-only fields when writing to transactional documents/drafts
        if entity in DOCUMENT_ENTITIES and k in ("CardType", "DocTotal", "DocStatus", "DocumentStatus"):
            continue

        field = map_field(table, k)

        # 1. Date normalization: convert ISO or formatted dates to ISO YYYY-MM-DD
        is_date_field = any(d in k.lower() for d in ("date", "time"))
        if isinstance(v, str) and (is_date_field or re.match(r"^\d{4}-\d{2}-\d{2}", v.strip())):
            v_clean = v.strip()
            if "T" in v_clean and re.match(r"^\d{4}-\d{2}-\d{2}T", v_clean):
                v = v_clean.split("T")[0]
            elif not re.match(r"^\d{4}-\d{2}-\d{2}$", v_clean):
                d_match = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", v_clean)
                if d_match:
                    p1, p2, year = d_match.groups()
                    tenant = config.CURRENT_TENANT.get() or {}
                    loc = str(tenant.get("locale", "en-IN")).lower()
                    # Indian / UK / European formats use DD/MM/YYYY
                    if "in" in loc or "gb" in loc or "eu" in loc or int(p1) > 12:
                        day, month = p1, p2
                    else:
                        month, day = p1, p2
                    v = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # 2. CardType enum normalization for BusinessPartners
        if field == "CardType" and isinstance(v, str) and entity not in DOCUMENT_ENTITIES:
            v = CARD_TYPE_ENUMS.get(v, CARD_TYPE_ENUMS.get(v.strip(), v))

        # 3. DocumentStatus enum normalization
        if field in ("DocumentStatus", "DocStatus") and isinstance(v, str):
            v = STATUS_ENUMS.get(v, STATUS_ENUMS.get(v.title(), v))

        # 4. Boolean / YesNo flags
        if field in ("Cancelled", "Valid", "Active", "Frozen", "validFor", "Confirmed", "DeferredTax", "PartialDelivery"):
            if isinstance(v, bool):
                v = "tYES" if v else "tNO"
            elif isinstance(v, str) and v in YESNO_ENUMS:
                v = YESNO_ENUMS[v]

        out[field] = v
    return out


class ServiceLayerBackend(DataBackend):
    name = "SAP B1 Service Layer"
    dialect = "odata"
    simulated = False

    def __init__(self):
        tenant = config.CURRENT_TENANT.get() or {}

        # Host: prefer tenant SAP_B1_HOST, fall back to config
        sl_host = tenant.get("SAP_B1_HOST") or config.SAP_B1_HOST

        # Port: The Service Layer always runs on 50000 (or explicit SERVICE_LAYER_PORT).
        # SAP_B1_PORT in the tenant context / .env may be the HANA port (30013) — we
        # must NOT use that for the Service Layer URL.  Only override if the tenant
        # explicitly set SERVICE_LAYER_PORT.
        sl_port = tenant.get("SERVICE_LAYER_PORT") or config.SERVICE_LAYER_PORT

        # If the tenant set an explicit full URL, honour it.
        if tenant.get("SERVICE_LAYER_BASE"):
            self.base = tenant["SERVICE_LAYER_BASE"].rstrip("/")
        else:
            self.base = f"https://{sl_host}:{sl_port}/b1s/v1"

        self.company = tenant.get("SAP_B1_COMPANY_DB") or config.SAP_B1_COMPANY_DB
        self.user = tenant.get("SAP_B1_USER") or config.SAP_B1_USER
        self.password = tenant.get("SAP_B1_PASSWORD") or config.SAP_B1_PASSWORD
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
            urls_to_try = [self.base]
            if "/b1s/v1" in self.base:
                urls_to_try.append(self.base.replace("/b1s/v1", "/b1s/v2"))
            elif "/b1s/v2" in self.base:
                urls_to_try.append(self.base.replace("/b1s/v2", "/b1s/v1"))

            last_exc = None
            for base_url in urls_to_try:
                try:
                    with self._client() as client:
                        resp = client.post(f"{base_url}/Login", json=payload)
                        if resp.status_code == 200:
                            self.base = base_url
                            data = resp.json()
                            timeout_min = int(data.get("SessionTimeout") or 30)
                            self._cookies = {k: v for k, v in resp.cookies.items()}
                            self._expires_at = time.time() + max(60, (timeout_min - 1) * 60)
                            return self._cookies
                        if resp.status_code != 404:
                            raise SapUnavailableError(
                                f"Service Layer login failed (HTTP {resp.status_code}): {resp.text[:200]}"
                            )
                except Exception as exc:
                    last_exc = exc
                    if isinstance(exc, SapUnavailableError) and "login failed" in str(exc):
                        raise
            raise SapUnavailableError(f"Service Layer unreachable: {last_exc}") from last_exc

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

    def _post(self, path: str, data: dict) -> dict:
        cookies = self._login()
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        for attempt in range(2):
            with self._client(cookies) as client:
                resp = client.post(url, json=data)
            if resp.status_code == 401 and attempt == 0:
                cookies = self._login(force=True)
                continue
            if resp.status_code >= 400:
                raise SapDataError(
                    f"Service Layer write error {resp.status_code}: {resp.text[:300]}"
                )
            # Service layer usually returns 201 Created with the entity
            return resp.json() if resp.text else {}
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

    # SAP document type codes for SeriesService — maps Service Layer entity → NNM1.ObjectCode
    # https://help.sap.com/docs/SAP_BUSINESS_ONE_SERVICE_LAYER
    ENTITY_SERIES_DOC_TYPE: dict[str, str] = {
        "BusinessPartners": "2",
        "Items": "4",
        "Orders": "17",
        "Quotations": "23",
        "Invoices": "13",
        "CreditNotes": "14",
        "DeliveryNotes": "15",
        "Returns": "16",
        "PurchaseOrders": "22",
        "PurchaseInvoices": "18",
        "PurchaseDeliveryNotes": "20",
        "PurchaseCreditNotes": "19",
        "IncomingPayments": "24",
        "VendorPayments": "46",
        "JournalEntries": "30",
        "SalesOpportunities": "97",
        "PurchaseQuotations": "540660006",
    }

    def _get_primary_series(self, entity: str) -> int | None:
        """Fetch the primary (default) numbering series for an entity from SAP."""
        doc_type = self.ENTITY_SERIES_DOC_TYPE.get(entity)
        if not doc_type:
            return None
        try:
            resp = self._post(
                "SeriesService_GetDocumentSeries",
                {"DocumentTypeParams": {"Document": doc_type}},
            )
            series_list = resp.get("value") or []
            # Prefer the series marked as default, else take the first one
            for s in series_list:
                if s.get("IsDefault") == "tYES" or s.get("IsDefault") is True:
                    return int(s["Series"])
            if series_list:
                return int(series_list[0]["Series"])
        except Exception as exc:
            log.warning("Could not fetch series for entity %s: %s", entity, exc)
        return None

    def create_entity(self, table_or_entity: str, data: dict) -> dict:
        """Create a new entity in the SAP Service Layer."""
        entity = TABLE_TO_ENTITY.get(table_or_entity.upper(), table_or_entity)
        payload = normalize_write_payload(table_or_entity, data)

        # ── Line Items Transformation for Documents ──
        # If the flat form passed ItemCode/Quantity/UnitPrice/TaxCode, move them into DocumentLines
        # Must execute before entity name is updated to "Drafts"
        DOCUMENT_ENTITIES = {
            "Orders", "Invoices", "PurchaseOrders", "Quotations", "CreditNotes",
            "PurchaseQuotations", "PurchaseInvoices", "DeliveryNotes", "Returns",
            "PurchaseDeliveryNotes", "PurchaseCreditNotes"
        }
        DRAFTABLE = set(DOCUMENT_ENTITIES)
        is_draft = entity in DRAFTABLE or entity == "Drafts"

        if entity in DOCUMENT_ENTITIES or is_draft:
            item_code = payload.pop("ItemCode", None)
            quantity = payload.pop("Quantity", None)
            unit_price = payload.pop("UnitPrice", None)
            tax_code = payload.pop("TaxCode", None)
            
            # Remove read-only document fields if present
            for ro_field in ("DocTotal", "DocStatus", "DocumentStatus", "DocEntry", "DocNum", "CardType"):
                payload.pop(ro_field, None)

            # Use existing DocumentLines if provided, else create it
            if "DocumentLines" not in payload:
                payload["DocumentLines"] = []
                
            if item_code:
                line = {
                    "ItemCode": item_code,
                    "Quantity": float(quantity) if quantity else 1.0
                }
                if unit_price is not None:
                    line["UnitPrice"] = float(unit_price)
                if tax_code is not None:
                    line["TaxCode"] = tax_code
                payload["DocumentLines"].append(line)

        # ── Numbering Series Injection ──
        if is_draft:
            # For Drafts, omit Series so SAP B1 automatically applies the default Draft Series (ObjectCode 112)
            # Injecting the target document's series into /b1s/v1/Drafts causes SAP error -5002
            payload.pop("Series", None)
        elif "Series" not in payload:
            series = self._get_primary_series(entity)
            if series is not None:
                payload["Series"] = series
                log.debug("Auto-injected Series=%s for entity %s", series, entity)
            else:
                MASTER_DATA = {"BusinessPartners", "Items", "ItemGroups", "Warehouses"}
                if entity in MASTER_DATA:
                    payload["Series"] = -1
                    log.debug("Auto-injected Series=-1 (Manual) for Master Data %s", entity)

        # ── Draft-First Writes ──
        if is_draft and entity != "Drafts":
            payload["DocObjectCode"] = f"o{entity}"
            log.info("Routing write for %s to Drafts (DocObjectCode: %s)", entity, payload["DocObjectCode"])
            entity = "Drafts"

        log.info("Posting to Service Layer: %s  payload=%s", entity, payload)
        return self._post(entity, payload)


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
