"""Offline SAP Business One sandbox.

When the real HANA box is unreachable (local laptops, CI, the sandbox this was
developed in) CIRA must still be *honestly* usable: the old code silently
returned a 2-row hard-coded catalog and pretended it was live ERP data.

This module instead materialises a small but realistic SAP B1 company database
in SQLite -- the same table names, the same column names, the same one-letter
status codes, tens of thousands of rows -- so the *entire* query path
(catalog discovery, filters, GROUP BY, joins, raw SQL, charts) is exercised for
real.  Every response coming from here is flagged `simulated: true` and the UI
shows a "SIMULATED DATA" badge, so nobody mistakes it for production numbers.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import config
from .base import DataBackend
from .sql_guard import translate_for_sqlite
from .types_ import ColumnInfo, SapDataError, TableInfo

log = logging.getLogger("cira.sim")

# Bump this whenever SCHEMA, the anchors or the generator change. An existing
# sandbox file with an older marker is rebuilt automatically, instead of
# silently serving stale data that does not match the accuracy suite.
SANDBOX_SCHEMA_VERSION = 2

# name, sqlite type, HANA-ish type shown in the catalog, description
Col = tuple[str, str, str, str]

SCHEMA: dict[str, list[Col]] = {
    "OADM": [
        ("CompnyName", "TEXT", "NVARCHAR(100)", "Company name"),
        ("CompnyAddr", "TEXT", "NVARCHAR(200)", "Company address"),
        ("MainCurncy", "TEXT", "NVARCHAR(3)", "Local currency"),
        ("Version", "TEXT", "NVARCHAR(20)", "SAP B1 version"),
    ],
    "OCRG": [
        ("GroupCode", "INTEGER", "INTEGER", "Business partner group code"),
        ("GroupName", "TEXT", "NVARCHAR(50)", "Business partner group name"),
        ("GroupType", "TEXT", "NVARCHAR(1)", "C=Customer, S=Vendor"),
    ],
    "OCRD": [
        ("CardCode", "TEXT", "NVARCHAR(15)", "Business partner code"),
        ("CardName", "TEXT", "NVARCHAR(100)", "Business partner name"),
        ("CardType", "TEXT", "NVARCHAR(1)", "C=Customer, S=Vendor, L=Lead"),
        ("GroupCode", "INTEGER", "INTEGER", "Business partner group"),
        ("Balance", "REAL", "DECIMAL(19,6)", "Account balance"),
        ("Phone1", "TEXT", "NVARCHAR(20)", "Telephone 1"),
        ("E_Mail", "TEXT", "NVARCHAR(100)", "E-mail address"),
        ("City", "TEXT", "NVARCHAR(100)", "City"),
        ("Country", "TEXT", "NVARCHAR(3)", "Country code"),
        ("Currency", "TEXT", "NVARCHAR(3)", "Default currency"),
        ("CreditLine", "REAL", "DECIMAL(19,6)", "Credit limit"),
        ("validFor", "TEXT", "NVARCHAR(1)", "Y=Active, N=Inactive"),
        ("CreateDate", "TEXT", "DATE", "Creation date"),
        ("SlpCode", "INTEGER", "INTEGER", "Sales employee code"),
    ],
    "OCPR": [
        ("CntctCode", "INTEGER", "INTEGER", "Contact person internal code"),
        ("CardCode", "TEXT", "NVARCHAR(15)", "Business partner code"),
        ("Name", "TEXT", "NVARCHAR(90)", "Contact person name"),
        ("Position", "TEXT", "NVARCHAR(90)", "Job title"),
        ("Tel1", "TEXT", "NVARCHAR(20)", "Telephone"),
        ("E_MailL", "TEXT", "NVARCHAR(100)", "E-mail"),
    ],
    "OITB": [
        ("ItmsGrpCod", "INTEGER", "INTEGER", "Item group code"),
        ("ItmsGrpNam", "TEXT", "NVARCHAR(50)", "Item group name"),
    ],
    "OITM": [
        ("ItemCode", "TEXT", "NVARCHAR(50)", "Item number"),
        ("ItemName", "TEXT", "NVARCHAR(100)", "Item description"),
        ("ItemType", "TEXT", "NVARCHAR(1)", "I=Item, L=Labor, T=Travel"),
        ("ItmsGrpCod", "INTEGER", "INTEGER", "Item group"),
        ("OnHand", "REAL", "DECIMAL(19,6)", "Quantity in stock"),
        ("IsCommited", "REAL", "DECIMAL(19,6)", "Committed quantity"),
        ("OnOrder", "REAL", "DECIMAL(19,6)", "Ordered from vendors"),
        ("AvgPrice", "REAL", "DECIMAL(19,6)", "Average cost price"),
        ("LastPurPrc", "REAL", "DECIMAL(19,6)", "Last purchase price"),
        ("InvntItem", "TEXT", "NVARCHAR(1)", "Y=Inventory item"),
        ("validFor", "TEXT", "NVARCHAR(1)", "Y=Active"),
        ("SalUnitMsr", "TEXT", "NVARCHAR(20)", "Sales unit of measure"),
        ("CreateDate", "TEXT", "DATE", "Creation date"),
    ],
    "OWHS": [
        ("WhsCode", "TEXT", "NVARCHAR(8)", "Warehouse code"),
        ("WhsName", "TEXT", "NVARCHAR(100)", "Warehouse name"),
        ("City", "TEXT", "NVARCHAR(100)", "City"),
        ("Country", "TEXT", "NVARCHAR(3)", "Country"),
        ("Inactive", "TEXT", "NVARCHAR(1)", "Y=Inactive"),
    ],
    "OITW": [
        ("ItemCode", "TEXT", "NVARCHAR(50)", "Item number"),
        ("WhsCode", "TEXT", "NVARCHAR(8)", "Warehouse code"),
        ("OnHand", "REAL", "DECIMAL(19,6)", "In stock in this warehouse"),
        ("IsCommited", "REAL", "DECIMAL(19,6)", "Committed"),
        ("OnOrder", "REAL", "DECIMAL(19,6)", "On order"),
        ("AvgPrice", "REAL", "DECIMAL(19,6)", "Average price"),
        ("MinStock", "REAL", "DECIMAL(19,6)", "Minimum stock level"),
    ],
    "OSLP": [
        ("SlpCode", "INTEGER", "INTEGER", "Sales employee code"),
        ("SlpName", "TEXT", "NVARCHAR(50)", "Sales employee name"),
        ("Commission", "REAL", "DECIMAL(19,6)", "Commission %"),
    ],
    "OUDP": [
        ("Code", "INTEGER", "INTEGER", "Department code"),
        ("Name", "TEXT", "NVARCHAR(50)", "Department name"),
    ],
    "OHEM": [
        ("empID", "INTEGER", "INTEGER", "Employee number"),
        ("firstName", "TEXT", "NVARCHAR(50)", "First name"),
        ("lastName", "TEXT", "NVARCHAR(50)", "Last name"),
        ("jobTitle", "TEXT", "NVARCHAR(90)", "Job title"),
        ("dept", "INTEGER", "INTEGER", "Department code"),
        ("branch", "TEXT", "NVARCHAR(50)", "Branch"),
        ("salary", "REAL", "DECIMAL(19,6)", "Monthly salary"),
        ("startDate", "TEXT", "DATE", "Employment start date"),
        ("Active", "TEXT", "NVARCHAR(1)", "Y=Active"),
        ("email", "TEXT", "NVARCHAR(100)", "Work e-mail"),
        ("manager", "INTEGER", "INTEGER", "Manager employee number"),
    ],
    "OUSR": [
        ("USERID", "INTEGER", "INTEGER", "Internal user id"),
        ("USER_CODE", "TEXT", "NVARCHAR(25)", "User code"),
        ("U_NAME", "TEXT", "NVARCHAR(155)", "User name"),
        ("E_Mail", "TEXT", "NVARCHAR(100)", "E-mail"),
        ("Department", "INTEGER", "INTEGER", "Department"),
    ],
}

# Document headers share a shape in SAP B1 — build them programmatically.
_DOC_HEADER: list[Col] = [
    ("DocEntry", "INTEGER", "INTEGER", "Document internal key"),
    ("DocNum", "INTEGER", "INTEGER", "Document number"),
    ("DocType", "TEXT", "NVARCHAR(1)", "I=Items, S=Service"),
    ("DocDate", "TEXT", "DATE", "Posting date"),
    ("DocDueDate", "TEXT", "DATE", "Due date"),
    ("TaxDate", "TEXT", "DATE", "Document date"),
    ("CardCode", "TEXT", "NVARCHAR(15)", "Business partner code"),
    ("CardName", "TEXT", "NVARCHAR(100)", "Business partner name"),
    ("DocTotal", "REAL", "DECIMAL(19,6)", "Document total including tax"),
    ("VatSum", "REAL", "DECIMAL(19,6)", "Tax amount"),
    ("DocCur", "TEXT", "NVARCHAR(3)", "Document currency"),
    ("DocStatus", "TEXT", "NVARCHAR(1)", "O=Open, C=Closed"),
    ("CANCELED", "TEXT", "NVARCHAR(1)", "Y=Cancelled"),
    ("SlpCode", "INTEGER", "INTEGER", "Sales employee"),
    ("Comments", "TEXT", "NVARCHAR(254)", "Remarks"),
]
_DOC_LINE: list[Col] = [
    ("DocEntry", "INTEGER", "INTEGER", "Parent document key"),
    ("LineNum", "INTEGER", "INTEGER", "Row number"),
    ("ItemCode", "TEXT", "NVARCHAR(50)", "Item number"),
    ("Dscription", "TEXT", "NVARCHAR(100)", "Item/service description"),
    ("Quantity", "REAL", "DECIMAL(19,6)", "Quantity"),
    ("Price", "REAL", "DECIMAL(19,6)", "Unit price"),
    ("LineTotal", "REAL", "DECIMAL(19,6)", "Row total"),
    ("WhsCode", "TEXT", "NVARCHAR(8)", "Warehouse"),
    ("ShipDate", "TEXT", "DATE", "Delivery date"),
]

for _t in ("ORDR", "OINV", "OPOR", "OPCH", "ODLN", "OQUT", "ORIN"):
    SCHEMA[_t] = list(_DOC_HEADER)
SCHEMA["OINV"] = list(_DOC_HEADER) + [
    ("PaidToDate", "REAL", "DECIMAL(19,6)", "Amount already paid"),
]
SCHEMA["OPCH"] = list(_DOC_HEADER) + [
    ("PaidToDate", "REAL", "DECIMAL(19,6)", "Amount already paid"),
]
for _t in ("RDR1", "INV1", "POR1", "PCH1", "DLN1", "QUT1", "PDN1"):
    SCHEMA[_t] = list(_DOC_LINE)
# Goods Receipt PO (OPDN/PDN1) - same shape as the other documents.
SCHEMA["OPDN"] = list(_DOC_HEADER)

SCHEMA.update(
    {
        "ORCT": [
            ("DocEntry", "INTEGER", "INTEGER", "Internal key"),
            ("DocNum", "INTEGER", "INTEGER", "Payment number"),
            ("DocDate", "TEXT", "DATE", "Posting date"),
            ("CardCode", "TEXT", "NVARCHAR(15)", "Customer code"),
            ("CardName", "TEXT", "NVARCHAR(100)", "Customer name"),
            ("DocTotal", "REAL", "DECIMAL(19,6)", "Payment amount"),
            ("DocCurr", "TEXT", "NVARCHAR(3)", "Currency"),
            ("Canceled", "TEXT", "NVARCHAR(1)", "Y=Cancelled"),
            ("CashSum", "REAL", "DECIMAL(19,6)", "Cash amount"),
            ("TrsfrSum", "REAL", "DECIMAL(19,6)", "Bank transfer amount"),
        ],
        "OVPM": [
            ("DocEntry", "INTEGER", "INTEGER", "Internal key"),
            ("DocNum", "INTEGER", "INTEGER", "Payment number"),
            ("DocDate", "TEXT", "DATE", "Posting date"),
            ("CardCode", "TEXT", "NVARCHAR(15)", "Vendor code"),
            ("CardName", "TEXT", "NVARCHAR(100)", "Vendor name"),
            ("DocTotal", "REAL", "DECIMAL(19,6)", "Payment amount"),
            ("DocCurr", "TEXT", "NVARCHAR(3)", "Currency"),
            ("Canceled", "TEXT", "NVARCHAR(1)", "Y=Cancelled"),
        ],
        "OACT": [
            ("AcctCode", "TEXT", "NVARCHAR(15)", "G/L account code"),
            ("AcctName", "TEXT", "NVARCHAR(100)", "G/L account name"),
            ("CurrTotal", "REAL", "DECIMAL(19,6)", "Account balance"),
            ("ActType", "TEXT", "NVARCHAR(1)", "Account type"),
            ("Postable", "TEXT", "NVARCHAR(1)", "Y=Postable"),
            ("Levels", "INTEGER", "INTEGER", "Level in the chart of accounts"),
        ],
        "OJDT": [
            ("TransId", "INTEGER", "INTEGER", "Journal entry number"),
            ("RefDate", "TEXT", "DATE", "Posting date"),
            ("Memo", "TEXT", "NVARCHAR(254)", "Remarks"),
            ("TransType", "INTEGER", "INTEGER", "Origin object type"),
            ("BaseRef", "TEXT", "NVARCHAR(50)", "Origin document number"),
        ],
        "JDT1": [
            ("TransId", "INTEGER", "INTEGER", "Journal entry number"),
            ("Line_ID", "INTEGER", "INTEGER", "Row number"),
            ("Account", "TEXT", "NVARCHAR(15)", "G/L account"),
            ("AcctName", "TEXT", "NVARCHAR(100)", "G/L account name"),
            ("Debit", "REAL", "DECIMAL(19,6)", "Debit amount"),
            ("Credit", "REAL", "DECIMAL(19,6)", "Credit amount"),
            ("RefDate", "TEXT", "DATE", "Posting date"),
            ("LineMemo", "TEXT", "NVARCHAR(254)", "Row remarks"),
            ("ShortName", "TEXT", "NVARCHAR(15)", "Offsetting BP/account"),
        ],
        "OINM": [
            ("TransNum", "INTEGER", "INTEGER", "Transaction number"),
            ("ItemCode", "TEXT", "NVARCHAR(50)", "Item number"),
            ("WhsCode", "TEXT", "NVARCHAR(8)", "Warehouse"),
            ("DocDate", "TEXT", "DATE", "Posting date"),
            ("InQty", "REAL", "DECIMAL(19,6)", "Quantity in"),
            ("OutQty", "REAL", "DECIMAL(19,6)", "Quantity out"),
            ("TransType", "INTEGER", "INTEGER", "Document object type"),
            ("DocNum", "INTEGER", "INTEGER", "Document number"),
            ("CalcPrice", "REAL", "DECIMAL(19,6)", "Calculated cost"),
        ],
        "OOPR": [
            ("OpprId", "INTEGER", "INTEGER", "Opportunity number"),
            ("CardCode", "TEXT", "NVARCHAR(15)", "Business partner"),
            ("CardName", "TEXT", "NVARCHAR(100)", "Business partner name"),
            ("OpenDate", "TEXT", "DATE", "Start date"),
            ("CloseDate", "TEXT", "DATE", "Closing date"),
            ("PredDate", "TEXT", "DATE", "Predicted closing date"),
            ("MaxSumLoc", "REAL", "DECIMAL(19,6)", "Potential amount"),
            ("Status", "TEXT", "NVARCHAR(1)", "O=Open, C=Closed"),
            ("SlpCode", "INTEGER", "INTEGER", "Sales employee"),
        ],
        "OSCL": [
            ("callID", "INTEGER", "INTEGER", "Service call number"),
            ("customer", "TEXT", "NVARCHAR(15)", "Customer code"),
            ("subject", "TEXT", "NVARCHAR(100)", "Subject"),
            ("createDate", "TEXT", "DATE", "Creation date"),
            ("closeDate", "TEXT", "DATE", "Closing date"),
            ("status", "INTEGER", "INTEGER", "Status code"),
            ("priority", "TEXT", "NVARCHAR(1)", "L/M/H priority"),
            ("technician", "TEXT", "NVARCHAR(10)", "Assigned technician code"),
        ],
        # ── master data the accuracy suite asks for ─────────────────────────
        # These were referenced by suite_sandbox.jsonl but did not exist in the
        # sandbox, so those questions could not be measured at all.
        "OVTG": [
            ("Code", "TEXT", "NVARCHAR(8)", "Tax code"),
            ("Name", "TEXT", "NVARCHAR(50)", "Tax code description"),
            ("Rate", "REAL", "DECIMAL(19,6)", "Effective rate %"),
            ("ValidFor", "TEXT", "NVARCHAR(1)", "Y=Active"),
        ],
        "OCTG": [
            ("GroupNum", "INTEGER", "INTEGER", "Payment terms key"),
            ("PymntGroup", "TEXT", "NVARCHAR(50)", "Payment terms name"),
            ("ExtraDays", "INTEGER", "INTEGER", "Extra days"),
            ("ExtraMonth", "INTEGER", "INTEGER", "Extra months"),
        ],
        "OCRN": [
            ("CurrCode", "TEXT", "NVARCHAR(3)", "Currency code"),
            ("CurrName", "TEXT", "NVARCHAR(50)", "Currency name"),
            ("DocRate", "REAL", "DECIMAL(19,6)", "Exchange rate"),
            ("Locked", "TEXT", "NVARCHAR(1)", "Y=Locked"),
        ],
        "OINS": [
            ("insID", "INTEGER", "INTEGER", "Customer equipment card number"),
            ("itemCode", "TEXT", "NVARCHAR(50)", "Item code"),
            ("customer", "TEXT", "NVARCHAR(15)", "Customer code"),
            ("serialNum", "TEXT", "NVARCHAR(50)", "Serial number"),
            ("startDate", "TEXT", "DATE", "Warranty start"),
            ("endDate", "TEXT", "DATE", "Warranty end"),
        ],
        # CRD1 (BP addresses) was missing, so "business partners in <state>"
        # could never be answered from this sandbox.
        "CRD1": [
            ("CardCode", "TEXT", "NVARCHAR(15)", "Business partner code"),
            ("Address", "TEXT", "NVARCHAR(200)", "Street address"),
            ("City", "TEXT", "NVARCHAR(100)", "City"),
            ("State", "TEXT", "NVARCHAR(3)", "State / province code"),
            ("ZipCode", "TEXT", "NVARCHAR(20)", "Postcode"),
            ("Country", "TEXT", "NVARCHAR(3)", "Country code"),
            ("AdresType", "TEXT", "NVARCHAR(1)", "B=Billing, S=Shipping"),
        ],
        "OWOR": [
            ("DocEntry", "INTEGER", "INTEGER", "Internal key"),
            ("DocNum", "INTEGER", "INTEGER", "Production order number"),
            ("ItemCode", "TEXT", "NVARCHAR(50)", "Produced item"),
            ("PlannedQty", "REAL", "DECIMAL(19,6)", "Planned quantity"),
            ("CmpltQty", "REAL", "DECIMAL(19,6)", "Completed quantity"),
            ("Status", "TEXT", "NVARCHAR(1)", "P=Planned, R=Released, L=Closed"),
            ("PostDate", "TEXT", "DATE", "Order date"),
            ("DueDate", "TEXT", "DATE", "Due date"),
            ("Warehouse", "TEXT", "NVARCHAR(8)", "Warehouse"),
        ],
    }
)

CITIES = [
    ("Mumbai", "IN"), ("Pune", "IN"), ("Bengaluru", "IN"), ("Chennai", "IN"),
    ("Delhi", "IN"), ("Hyderabad", "IN"), ("Ahmedabad", "IN"), ("Kolkata", "IN"),
    ("Singapore", "SG"), ("Dubai", "AE"), ("Frankfurt", "DE"), ("Chicago", "US"),
]
FIRST = ["Aarav", "Vivaan", "Diya", "Ananya", "Rohan", "Kavya", "Ishaan", "Meera",
         "Arjun", "Sara", "Kabir", "Nisha", "Dev", "Priya", "Aditya", "Riya",
         "Marcus", "Elena", "Chen", "Yusuf", "Grace", "Tomas"]
LAST = ["Sharma", "Patel", "Iyer", "Nair", "Reddy", "Gupta", "Mehta", "Singh",
        "Bose", "Kulkarni", "Rao", "Desai", "Fernandes", "Khan", "Weber", "Lim"]
COMPANY_A = ["Acme", "Zenith", "Premier", "TechnoSoft", "Nordic", "BlueOcean", "Vertex",
             "Sunrise", "Ironclad", "Quantum", "Everest", "Kinetic", "Apex", "Lumen",
             "Falcon", "Sterling", "Orbit", "Cobalt", "Summit", "Delta", "Pioneer"]
COMPANY_B = ["Industries", "Manufacturing", "Electronics", "Logistics", "Traders",
             "Engineering", "Systems", "Global Corp", "Enterprises", "Solutions",
             "Fabricators", "Polymers", "Motors", "Chemicals", "Foods"]
ITEM_A = ["Industrial", "High Precision", "Hydraulic", "Stainless", "Copper", "Ceramic",
          "Pneumatic", "Digital", "Heavy Duty", "Compact", "Modular", "Thermal"]
ITEM_B = ["Steel Rod", "Servo Motor", "Pressure Valve", "Bearing Set", "Control Panel",
          "Gear Box", "Sensor Array", "Cable Harness", "Hydraulic Pump", "Filter Unit",
          "Drive Shaft", "Coupling", "Compressor", "Relay Module", "Actuator"]
GROUPS = ["Raw Materials", "Finished Goods", "Spare Parts", "Consumables", "Packaging",
          "Electronics", "Services"]
DEPARTMENTS = ["Finance", "Sales", "Procurement", "Operations", "IT", "Human Resources",
               "Quality", "Logistics"]
JOB_TITLES = ["Analyst", "Manager", "Senior Manager", "Executive", "Engineer",
              "Team Lead", "Director", "Coordinator"]
ACCOUNTS = [
    ("110000", "Cash on Hand", "A"), ("110100", "Bank Current Account", "A"),
    ("120000", "Trade Receivables", "A"), ("130000", "Inventory", "A"),
    ("210000", "Trade Payables", "L"), ("220000", "Tax Payable", "L"),
    ("300000", "Share Capital", "C"), ("400000", "Sales Revenue", "R"),
    ("410000", "Service Revenue", "R"), ("500000", "Cost of Goods Sold", "E"),
    ("510000", "Freight Expense", "E"), ("520000", "Salaries Expense", "E"),
    ("530000", "Travel Expense", "E"), ("540000", "Utilities Expense", "E"),
]


class SimulatorBackend(DataBackend):
    name = "SAP B1 Simulator (offline sandbox)"
    dialect = "sqlite"
    simulated = True

    def __init__(self, path: Path | None = None, schema: str = ""):
        self.path = Path(path or config.SIMULATOR_DB_PATH)
        self.schema = schema or config.HANA_SCHEMA or "CIRA_SANDBOX"
        self._local = threading.local()
        self._lock = threading.Lock()
        self._ready = False

    # ── connection ───────────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        self._ensure_seeded()
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _ensure_seeded(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=60)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ORDR'"
                )
                seeded = cur.fetchone() is not None
                if seeded:
                    cur.execute("SELECT COUNT(*) FROM ORDR")
                    seeded = (cur.fetchone() or [0])[0] > 0
                if seeded:
                    # A file built by an older version of this module is missing
                    # tables or anchors the current suite expects - rebuild it.
                    try:
                        cur.execute("SELECT version FROM _SANDBOX_META")
                        current = (cur.fetchone() or [0])[0]
                    except sqlite3.Error:
                        current = 0
                    if current != SANDBOX_SCHEMA_VERSION:
                        log.info(
                            "Sandbox at %s is schema v%s but v%s is required - rebuilding.",
                            self.path, current, SANDBOX_SCHEMA_VERSION,
                        )
                        seeded = False
                if not seeded:
                    log.info("Seeding offline SAP B1 sandbox at %s ...", self.path)
                    started = time.time()
                    _build_dataset(conn)
                    log.info("Sandbox ready in %.1fs", time.time() - started)
            finally:
                conn.close()
            self._ready = True

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── interface ────────────────────────────────────────────────────────────
    def ping(self) -> dict:
        started = time.time()
        try:
            self._conn().execute("SELECT 1").fetchone()
            return {
                "ok": True,
                "backend": self.name,
                "schema": self.schema,
                "simulated": True,
                "path": str(self.path),
                "latency_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {"ok": False, "backend": self.name, "error": str(exc)}

    def list_tables(self, pattern: str = "", include_views: bool = True,
                    limit: int = 1000) -> list[TableInfo]:
        conn = self._conn()
        out: list[TableInfo] = []
        for name in sorted(SCHEMA):
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except Exception:
                count = None
            from . import entities

            out.append(
                TableInfo(
                    name=name,
                    schema=self.schema,
                    description=entities.describe_table_name(name),
                    kind="TABLE",
                    row_count=count,
                )
            )
        if pattern:
            needle = pattern.lower()
            out = [t for t in out if needle in t.name.lower() or needle in t.description.lower()]
        return out[:limit]

    def get_columns(self, table: str) -> list[ColumnInfo]:
        cols = SCHEMA.get(table.upper())
        if not cols:
            return []
        return [
            ColumnInfo(
                name=name,
                data_type=hana_type,
                length=_length_of(hana_type),
                nullable=True,
                description=desc,
                position=i + 1,
            )
            for i, (name, _sqlite_type, hana_type, desc) in enumerate(cols)
        ]

    def row_count(self, table: str) -> int | None:
        try:
            return self._conn().execute(f'SELECT COUNT(*) FROM "{table.upper()}"').fetchone()[0]
        except Exception:
            return None

    def execute(self, sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
        translated = translate_for_sqlite(sql, self.schema)
        cur = self._conn().execute(translated, tuple(params or ()))
        columns = [d[0] for d in (cur.description or [])]
        rows = cur.fetchall()
        cur.close()
        return columns, rows

    def create_entity(self, table_or_entity: str, data: dict) -> dict:
        """Persist a write into the offline sandbox for real.

        This used to return a random DocEntry and write nothing, which meant the
        write path - and therefore the whole migration wedge - could not be
        exercised or regression-tested without a live B1 box. We now INSERT into
        the matching sandbox table (same names and columns as B1) so the
        draft/idempotency/re-diff flows are testable offline. Every response is
        still flagged simulated, and the table is the sandbox copy, never HANA.
        """
        from .service_layer import ENTITY_TO_TABLE, TABLE_TO_ENTITY

        raw = (table_or_entity or "").strip()
        table = ENTITY_TO_TABLE.get(raw, ENTITY_TO_TABLE.get(raw.upper(), raw)).upper()
        if table not in SCHEMA:
            table = TABLE_TO_ENTITY.get(raw.upper(), raw).upper()
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if cur.fetchone() is None:
            raise SapDataError(
                f"The offline sandbox has no table '{table}', so it cannot store this write. "
                f"Available: {', '.join(sorted(SCHEMA))}."
            )

        cur.execute(f'PRAGMA table_info("{table}")')
        known = {row[1] for row in cur.fetchall()}
        payload = {k: v for k, v in (data or {}).items()
                   if k in known and not str(k).startswith("_") and v not in ("", None)}
        if not payload:
            raise SapDataError(
                f"None of the supplied fields exist on sandbox table '{table}'."
            )

        import random
        next_entry = random.randint(300000, 999999)
        for key in ("DocEntry", "TransId", "AbsEntry", "LogInstanc"):
            if key in known and key not in payload:
                payload[key] = next_entry
        if "DocNum" in known and "DocNum" not in payload:
            payload["DocNum"] = next_entry

        cols = ", ".join(f'"{c}"' for c in payload)
        marks = ", ".join("?" for _ in payload)
        try:
            cur.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', list(payload.values()))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise SapDataError(f"The sandbox rejected the write to {table}: {exc}") from exc

        return {
            **payload,
            "_simulated": True,
            "_table": table,
            "_note": "Written to the OFFLINE SANDBOX, not to a live SAP Business One company.",
        }

    def update_entity(self, table_or_entity: str, key_field: str, key_value: str,
                      data: dict) -> dict:
        """Mirror of ServiceLayerBackend.update_entity for the offline sandbox."""
        from .service_layer import ENTITY_TO_TABLE

        raw = (table_or_entity or "").strip()
        table = ENTITY_TO_TABLE.get(raw, ENTITY_TO_TABLE.get(raw.upper(), raw)).upper()
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f'PRAGMA table_info("{table}")')
        known = {row[1] for row in cur.fetchall()}
        if not known or key_field not in known:
            raise SapDataError(f"Cannot update {table}: unknown table or key '{key_field}'.")

        payload = {k: v for k, v in (data or {}).items()
                   if k in known and not str(k).startswith("_") and v not in ("", None)}
        payload.pop(key_field, None)
        if not payload:
            return {"_noop": True, "_reason": "nothing to update", "_simulated": True}
        sets = ", ".join(f'"{c}" = ?' for c in payload)
        cur.execute(f'UPDATE "{table}" SET {sets} WHERE "{key_field}" = ?',
                    [*payload.values(), key_value])
        conn.commit()
        return {key_field: key_value, **payload, "_updated": cur.rowcount,
                "_simulated": True}

    # ── draft lifecycle (offline mirror of the Service Layer's Drafts entity) ──
    def get_draft(self, doc_entry: int) -> dict:
        cur = self._conn().cursor()
        cur.execute('SELECT DocEntry, DocNum, DocObjectCode, CardCode FROM "ODRF" WHERE DocEntry = ?',
                    (int(doc_entry),))
        row = cur.fetchone()
        if not row:
            raise SapDataError(f"No sandbox draft with DocEntry {doc_entry}.")
        return {"DocEntry": row[0], "DocNum": row[1], "DocObjectCode": row[2],
                "CardCode": row[3], "_simulated": True}

    def cancel_draft(self, doc_entry: int) -> dict:
        cur = self._conn().cursor()
        cur.execute('UPDATE "ODRF" SET "CANCELED" = ? WHERE "DocEntry" = ?', ("Y", int(doc_entry)))
        self._conn().commit()
        return {"DocEntry": int(doc_entry), "CANCELED": "Y", "_simulated": True,
                "_note": "Drafts are cancelled, never deleted."}

    def save_draft_to_document(self, doc_entry: int) -> dict:
        return {"DocEntry": int(doc_entry), "_simulated": True,
                "_note": "A real deployment would POST DraftsService_SaveDraftToDocument; "
                         "the sandbox does not post documents."}



def _length_of(hana_type: str) -> int | None:
    if "(" in hana_type:
        inner = hana_type.split("(", 1)[1].rstrip(")")
        head = inner.split(",")[0]
        if head.isdigit():
            return int(head)
    return None


# ── dataset generation ───────────────────────────────────────────────────────
def _build_dataset(conn: sqlite3.Connection) -> None:
    rnd = random.Random(20240719)
    cur = conn.cursor()

    for table, cols in SCHEMA.items():
        col_sql = ", ".join(f'"{c[0]}" {c[1]}' for c in cols)
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        cur.execute(f'CREATE TABLE "{table}" ({col_sql})')

    def insert(table: str, rows: list[dict]) -> None:
        if not rows:
            return
        cols = [c[0] for c in SCHEMA[table]]
        placeholders = ", ".join("?" for _ in cols)
        quoted = ", ".join(f'"{c}"' for c in cols)
        cur.executemany(
            f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
            [tuple(r.get(c) for c in cols) for r in rows],
        )

    today = dt.date.today()
    start = today - dt.timedelta(days=730)

    def rand_date(a: dt.date = start, b: dt.date = today) -> dt.date:
        return a + dt.timedelta(days=rnd.randint(0, (b - a).days))

    # Company
    insert("OADM", [{
        "CompnyName": "CIRA Demo Industries Pvt Ltd",
        "CompnyAddr": "Plot 42, MIDC Industrial Area, Pune 411018",
        "MainCurncy": "INR",
        "Version": "SAP Business One 10.0 (offline sandbox)",
    }])

    # BP groups
    bp_groups = [{"GroupCode": 100 + i, "GroupName": n, "GroupType": t}
                 for i, (n, t) in enumerate(
                     [("Key Accounts", "C"), ("Retail", "C"), ("Distributors", "C"),
                      ("Raw Material Vendors", "S"), ("Service Vendors", "S"),
                      ("Logistics Partners", "S")])]
    insert("OCRG", bp_groups)

    # Sales employees
    sales_emps = []
    for i in range(1, 13):
        sales_emps.append({
            "SlpCode": i,
            "SlpName": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
            "Commission": round(rnd.uniform(1.0, 5.0), 2),
        })
    insert("OSLP", sales_emps)
    slp_codes = [s["SlpCode"] for s in sales_emps]

    # Business partners
    customers, vendors = [], []
    used_names = set()
    for i in range(220):
        while True:
            name = f"{rnd.choice(COMPANY_A)} {rnd.choice(COMPANY_B)}"
            if name not in used_names:
                used_names.add(name)
                break
        is_customer = i < 150
        city, country = rnd.choice(CITIES)
        code = f"{'C' if is_customer else 'V'}{20000 + i}"
        row = {
            "CardCode": code,
            "CardName": name,
            "CardType": "C" if is_customer else "S",
            "GroupCode": rnd.choice([g["GroupCode"] for g in bp_groups
                                     if g["GroupType"] == ("C" if is_customer else "S")]),
            "Balance": round(rnd.uniform(-50000, 900000), 2) if is_customer else round(rnd.uniform(-200000, 300000), 2),
            "Phone1": f"+91-{rnd.randint(70,99)}{rnd.randint(10000000,99999999)}",
            "E_Mail": f"accounts@{name.split()[0].lower()}.example.com",
            "City": city,
            "Country": country,
            "Currency": "INR" if country == "IN" else rnd.choice(["USD", "EUR", "SGD"]),
            "CreditLine": round(rnd.choice([250000, 500000, 1000000, 2500000]), 2),
            "validFor": "Y" if rnd.random() > 0.08 else "N",
            "CreateDate": rand_date(today - dt.timedelta(days=1500), today).isoformat(),
            "SlpCode": rnd.choice(slp_codes),
        }
        (customers if is_customer else vendors).append(row)
    # Reserve the codes used by the named anchor records below. Without this the
    # random generator also produced a "C20000" with a different name, so
    # "customer C20000" had two answers.
    RESERVED_BP_CODES = {"C20000", "C20001"}
    customers = [c for c in customers if c["CardCode"] not in RESERVED_BP_CODES]
    vendors = [v for v in vendors if v["CardCode"] not in RESERVED_BP_CODES]
    insert("OCRD", customers + vendors)

    # Contacts
    contacts = []
    for i, bp in enumerate(customers + vendors):
        for _ in range(rnd.randint(0, 2)):
            contacts.append({
                "CntctCode": len(contacts) + 1,
                "CardCode": bp["CardCode"],
                "Name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
                "Position": rnd.choice(["Purchase Manager", "CFO", "Plant Head",
                                        "Accounts Payable", "Director"]),
                "Tel1": f"+91-{rnd.randint(70,99)}{rnd.randint(10000000,99999999)}",
                "E_MailL": f"contact{len(contacts)+1}@{bp['CardName'].split()[0].lower()}.example.com",
            })
    insert("OCPR", contacts)

    # Item groups + items
    item_groups = [{"ItmsGrpCod": 100 + i, "ItmsGrpNam": n} for i, n in enumerate(GROUPS)]
    insert("OITB", item_groups)

    items = []
    for i in range(320):
        name = f"{rnd.choice(ITEM_A)} {rnd.choice(ITEM_B)} {rnd.choice(['10mm','25mm','2.5in','XL','Mk II','Series 7'])}"
        avg = round(rnd.uniform(120, 45000), 2)
        items.append({
            "ItemCode": f"A{100001 + i}",
            "ItemName": name,
            "ItemType": "I" if i % 17 else "L",
            "ItmsGrpCod": rnd.choice([g["ItmsGrpCod"] for g in item_groups]),
            "OnHand": round(rnd.uniform(0, 4200), 2),
            "IsCommited": round(rnd.uniform(0, 400), 2),
            "OnOrder": round(rnd.uniform(0, 900), 2),
            "AvgPrice": avg,
            "LastPurPrc": round(avg * rnd.uniform(0.85, 1.15), 2),
            "InvntItem": "Y" if i % 17 else "N",
            "validFor": "Y" if rnd.random() > 0.05 else "N",
            "SalUnitMsr": rnd.choice(["Pcs", "Units", "Kg", "Box", "Set"]),
            "CreateDate": rand_date(today - dt.timedelta(days=1500), today).isoformat(),
        })
    # A00001..A00003 are the named anchors added below.
    items = [i for i in items if i["ItemCode"] not in {"A00001", "A00002", "A00003"}]
    insert("OITM", items)

    # Warehouses + per-warehouse stock
    warehouses = []
    for i, (city, country) in enumerate(CITIES[:6]):
        warehouses.append({
            "WhsCode": f"WH{i+1:02d}",
            "WhsName": f"{city} Warehouse",
            "City": city,
            "Country": country,
            "Inactive": "N",
        })
    insert("OWHS", warehouses)

    stock_rows = []
    for item in items:
        for wh in rnd.sample(warehouses, rnd.randint(1, 4)):
            stock_rows.append({
                "ItemCode": item["ItemCode"],
                "WhsCode": wh["WhsCode"],
                "OnHand": round(rnd.uniform(0, 1200), 2),
                "IsCommited": round(rnd.uniform(0, 120), 2),
                "OnOrder": round(rnd.uniform(0, 250), 2),
                "AvgPrice": item["AvgPrice"],
                "MinStock": round(rnd.uniform(0, 150), 2),
            })
    insert("OITW", stock_rows)

    # Departments & employees
    departments = [{"Code": 1 + i, "Name": n} for i, n in enumerate(DEPARTMENTS)]
    insert("OUDP", departments)

    employees = []
    for i in range(96):
        first, last = rnd.choice(FIRST), rnd.choice(LAST)
        employees.append({
            "empID": 1000 + i,
            "firstName": first,
            "lastName": last,
            "jobTitle": rnd.choice(JOB_TITLES),
            "dept": rnd.choice([d["Code"] for d in departments]),
            "branch": rnd.choice(["Pune HQ", "Mumbai", "Bengaluru", "Singapore"]),
            "salary": round(rnd.uniform(45000, 420000), 2),
            "startDate": rand_date(today - dt.timedelta(days=2500), today).isoformat(),
            "Active": "Y" if rnd.random() > 0.1 else "N",
            "email": f"{first.lower()}.{last.lower()}{i}@ciraindustries.example.com",
            "manager": 1000 + rnd.randint(0, 12),
        })
    insert("OHEM", employees)

    insert("OUSR", [{
        "USERID": i + 1,
        "USER_CODE": f"user{i+1:03d}",
        "U_NAME": f"{e['firstName']} {e['lastName']}",
        "E_Mail": e["email"],
        "Department": e["dept"],
    } for i, e in enumerate(employees[:30])])

    # Accounts
    insert("OACT", [{
        "AcctCode": code,
        "AcctName": name,
        "CurrTotal": round(rnd.uniform(-2_000_000, 9_000_000), 2),
        "ActType": typ,
        "Postable": "Y",
        "Levels": 3,
    } for code, name, typ in ACCOUNTS])

    # ── documents ────────────────────────────────────────────────────────────
    def make_docs(table: str, line_table: str | None, count: int, partners: list[dict],
                  start_num: int, paid: bool = False) -> list[dict]:
        headers, lines = [], []
        for n in range(count):
            bp = rnd.choice(partners)
            doc_date = rand_date()
            n_lines = rnd.randint(1, 5)
            total = 0.0
            doc_entry = start_num + n
            for line_no in range(n_lines):
                item = rnd.choice(items)
                qty = float(rnd.randint(1, 60))
                price = round(item["AvgPrice"] * rnd.uniform(1.05, 1.6), 2)
                line_total = round(qty * price, 2)
                total += line_total
                if line_table:
                    lines.append({
                        "DocEntry": doc_entry,
                        "LineNum": line_no,
                        "ItemCode": item["ItemCode"],
                        "Dscription": item["ItemName"],
                        "Quantity": qty,
                        "Price": price,
                        "LineTotal": line_total,
                        "WhsCode": rnd.choice(warehouses)["WhsCode"],
                        "ShipDate": (doc_date + dt.timedelta(days=rnd.randint(1, 30))).isoformat(),
                    })
            vat = round(total * 0.18, 2)
            grand = round(total + vat, 2)
            status = "C" if rnd.random() < 0.55 else "O"
            header = {
                "DocEntry": doc_entry,
                "DocNum": doc_entry,
                "DocType": "I",
                "DocDate": doc_date.isoformat(),
                "DocDueDate": (doc_date + dt.timedelta(days=rnd.choice([15, 30, 45, 60]))).isoformat(),
                "TaxDate": doc_date.isoformat(),
                "CardCode": bp["CardCode"],
                "CardName": bp["CardName"],
                "DocTotal": grand,
                "VatSum": vat,
                "DocCur": bp["Currency"],
                "DocStatus": status,
                "CANCELED": "Y" if rnd.random() < 0.03 else "N",
                "SlpCode": rnd.choice(slp_codes),
                "Comments": rnd.choice([
                    "", "", "Priority customer", "Partial shipment agreed",
                    "Payment terms revised", "Rush order", "Annual contract",
                ]),
            }
            if paid:
                header["PaidToDate"] = round(grand if status == "C" else grand * rnd.uniform(0, 0.8), 2)
            headers.append(header)
        insert(table, headers)
        if line_table:
            insert(line_table, lines)
        return headers

    orders = make_docs("ORDR", "RDR1", 1500, customers, 1)
    invoices = make_docs("OINV", "INV1", 1250, customers, 5001, paid=True)
    make_docs("ODLN", "DLN1", 900, customers, 9001)
    make_docs("OQUT", "QUT1", 700, customers, 12001)
    make_docs("ORIN", None, 120, customers, 15001)
    purchase_orders = make_docs("OPOR", "POR1", 850, vendors, 20001)
    ap_invoices = make_docs("OPCH", "PCH1", 640, vendors, 25001, paid=True)

    # Payments
    incoming = []
    for i, inv in enumerate(rnd.sample(invoices, 700)):
        d = dt.date.fromisoformat(inv["DocDate"]) + dt.timedelta(days=rnd.randint(1, 75))
        amount = round(inv["DocTotal"] * rnd.uniform(0.3, 1.0), 2)
        incoming.append({
            "DocEntry": 30001 + i, "DocNum": 30001 + i,
            "DocDate": min(d, today).isoformat(),
            "CardCode": inv["CardCode"], "CardName": inv["CardName"],
            "DocTotal": amount, "DocCurr": inv["DocCur"],
            "Canceled": "N",
            "CashSum": round(amount * rnd.choice([0, 0, 0.2]), 2),
            "TrsfrSum": amount,
        })
    insert("ORCT", incoming)

    outgoing = []
    for i, inv in enumerate(rnd.sample(ap_invoices, 400)):
        d = dt.date.fromisoformat(inv["DocDate"]) + dt.timedelta(days=rnd.randint(1, 60))
        outgoing.append({
            "DocEntry": 35001 + i, "DocNum": 35001 + i,
            "DocDate": min(d, today).isoformat(),
            "CardCode": inv["CardCode"], "CardName": inv["CardName"],
            "DocTotal": round(inv["DocTotal"] * rnd.uniform(0.4, 1.0), 2),
            "DocCurr": inv["DocCur"], "Canceled": "N",
        })
    insert("OVPM", outgoing)

    # Journal entries derived from invoices
    journals, journal_lines = [], []
    for i, inv in enumerate(rnd.sample(invoices, 900)):
        trans_id = 50001 + i
        journals.append({
            "TransId": trans_id,
            "RefDate": inv["DocDate"],
            "Memo": f"A/R Invoice {inv['DocNum']} - {inv['CardName']}",
            "TransType": 13,
            "BaseRef": str(inv["DocNum"]),
        })
        journal_lines.append({
            "TransId": trans_id, "Line_ID": 0, "Account": "120000",
            "AcctName": "Trade Receivables", "Debit": inv["DocTotal"], "Credit": 0.0,
            "RefDate": inv["DocDate"], "LineMemo": "Customer invoice",
            "ShortName": inv["CardCode"],
        })
        journal_lines.append({
            "TransId": trans_id, "Line_ID": 1, "Account": "400000",
            "AcctName": "Sales Revenue", "Debit": 0.0,
            "Credit": round(inv["DocTotal"] - inv["VatSum"], 2),
            "RefDate": inv["DocDate"], "LineMemo": "Revenue recognition",
            "ShortName": "400000",
        })
        journal_lines.append({
            "TransId": trans_id, "Line_ID": 2, "Account": "220000",
            "AcctName": "Tax Payable", "Debit": 0.0, "Credit": inv["VatSum"],
            "RefDate": inv["DocDate"], "LineMemo": "Output GST",
            "ShortName": "220000",
        })
    insert("OJDT", journals)
    insert("JDT1", journal_lines)

    # Inventory movements
    movements = []
    for i in range(4000):
        item = rnd.choice(items)
        inbound = rnd.random() < 0.5
        qty = float(rnd.randint(1, 90))
        movements.append({
            "TransNum": 60001 + i,
            "ItemCode": item["ItemCode"],
            "WhsCode": rnd.choice(warehouses)["WhsCode"],
            "DocDate": rand_date().isoformat(),
            "InQty": qty if inbound else 0.0,
            "OutQty": 0.0 if inbound else qty,
            "TransType": rnd.choice([13, 15, 17, 20, 21, 59, 60]),
            "DocNum": rnd.randint(1000, 40000),
            "CalcPrice": item["AvgPrice"],
        })
    insert("OINM", movements)

    # Opportunities / service calls / production
    opps = []
    for i in range(260):
        bp = rnd.choice(customers)
        opened = rand_date()
        opps.append({
            "OpprId": 1 + i,
            "CardCode": bp["CardCode"], "CardName": bp["CardName"],
            "OpenDate": opened.isoformat(),
            "CloseDate": (opened + dt.timedelta(days=rnd.randint(10, 200))).isoformat(),
            "PredDate": (opened + dt.timedelta(days=rnd.randint(20, 180))).isoformat(),
            "MaxSumLoc": round(rnd.uniform(50000, 8_000_000), 2),
            "Status": rnd.choice(["O", "O", "C"]),
            "SlpCode": rnd.choice(slp_codes),
        })
    insert("OOPR", opps)

    calls = []
    for i in range(180):
        bp = rnd.choice(customers)
        created = rand_date()
        calls.append({
            "callID": 1 + i,
            "customer": bp["CardCode"],
            "subject": rnd.choice([
                "Motor overheating", "Delayed shipment", "Installation support",
                "Warranty claim", "Calibration request", "Spare part enquiry",
            ]),
            "createDate": created.isoformat(),
            "closeDate": (created + dt.timedelta(days=rnd.randint(1, 40))).isoformat(),
            "status": rnd.choice([-3, -2, -1, 1]),
            "priority": rnd.choice(["L", "M", "H"]),
            "technician": f"T{rnd.randint(1, 5):02d}",
        })
    insert("OSCL", calls)

    prod = []
    for i in range(160):
        item = rnd.choice(items)
        posted = rand_date()
        planned = float(rnd.randint(10, 500))
        prod.append({
            "DocEntry": 1 + i, "DocNum": 70001 + i,
            "ItemCode": item["ItemCode"],
            "PlannedQty": planned,
            "CmpltQty": round(planned * rnd.uniform(0, 1), 2),
            "Status": rnd.choice(["P", "R", "R", "L"]),
            "PostDate": posted.isoformat(),
            "DueDate": (posted + dt.timedelta(days=rnd.randint(5, 60))).isoformat(),
            "Warehouse": rnd.choice(warehouses)["WhsCode"],
        })
    insert("OWOR", prod)

    # ── seed the tables added above ────────────────────────────────────────
    insert("OVTG", [
        {"Code": c, "Name": n, "Rate": r, "ValidFor": "Y"}
        for c, n, r in [
            ("GST5", "GST 5%", 5.0), ("GST12", "GST 12%", 12.0),
            ("GST18", "GST 18%", 18.0), ("GST28", "GST 28%", 28.0),
            ("VAT5", "VAT 5%", 5.0), ("EX0", "Exempt 0%", 0.0),
        ]
    ])
    insert("OCTG", [
        {"GroupNum": 1 + i, "PymntGroup": name, "ExtraDays": days, "ExtraMonth": months}
        for i, (name, days, months) in enumerate([
            ("Cash", 0, 0), ("Net 15", 15, 0), ("Net 30", 30, 0),
            ("Net 45", 45, 0), ("Net 60", 60, 0), ("Advance 50%", 0, 0),
            ("Net 30 EOM", 30, 1), ("Letter of Credit", 90, 0),
        ])
    ])
    insert("OCRN", [
        {"CurrCode": c, "CurrName": n, "DocRate": r, "Locked": "N"}
        for c, n, r in [
            ("INR", "Indian Rupee", 1.0), ("USD", "US Dollar", 83.2),
            ("EUR", "Euro", 90.1), ("AED", "UAE Dirham", 22.65),
            ("GBP", "Pound Sterling", 105.4), ("SGD", "Singapore Dollar", 61.8),
        ]
    ])
    insert("OINS", [
        {
            "insID": 1 + i,
            "itemCode": rnd.choice(items)["ItemCode"],
            "customer": rnd.choice(customers)["CardCode"],
            "serialNum": f"SN{100000 + i}",
            "startDate": (d := rand_date()).isoformat(),
            "endDate": (d + dt.timedelta(days=365)).isoformat(),
        }
        for i in range(140)
    ])
    addresses = []
    for i, c in enumerate(customers):
        addresses.append({
            "CardCode": c["CardCode"],
            "Address": f"{rnd.randint(1, 300)} {rnd.choice(['MG Road', 'Industrial Estate', 'Ring Road', 'Sector 5'])}",
            "City": c["City"],
            "State": rnd.choice(["CA", "NY", "TX", "MH", "KA", "DL"]),
            "ZipCode": f"{rnd.randint(100000, 999999)}",
            "Country": c["Country"],
            "AdresType": "B",
        })
    insert("CRD1", addresses)
    grpo = make_docs("OPDN", "PDN1", 420, vendors, 30001)
    _ = grpo

    # ── named anchor records ───────────────────────────────────────────────
    # The accuracy suite asks about specific, human-readable entities
    # ("Earthshaker Corporation", item "A00001", the "Printers" group). Without
    # these anchors those questions had no correct answer in the sandbox, so
    # they could only be graded structurally - which is not evidence of
    # accuracy. All values here are fixed, so expected results are stable.
    insert("OCRD", [
        {"CardCode": "C20000", "CardName": "Earthshaker Corporation", "CardType": "C",
         "GroupCode": bp_groups[0]["GroupCode"], "Balance": 412350.75,
         "Phone1": "+91-9820011223", "E_Mail": "ap@earthshaker.example.com",
         "City": "Mumbai", "Country": "IN", "Currency": "INR",
         "CreditLine": 2500000.0, "validFor": "Y", "CreateDate": (today - dt.timedelta(days=900)).isoformat(),
         "SlpCode": 1},
        {"CardCode": "C20001", "CardName": "Maxi-Teq", "CardType": "C",
         "GroupCode": bp_groups[0]["GroupCode"], "Balance": 158900.40,
         "Phone1": "+91-9820044556", "E_Mail": "purchase@maxi-teq.example.com",
         "City": "Pune", "Country": "IN", "Currency": "INR",
         "CreditLine": 1000000.0, "validFor": "Y", "CreateDate": (today - dt.timedelta(days=700)).isoformat(),
         "SlpCode": 2},
    ])
    insert("OCPR", [
        {"CntctCode": 9001, "CardCode": "C20001", "Name": "Rohit Deshmukh",
         "Position": "Purchase Manager", "Tel1": "+91-9820044557",
         "E_MailL": "rohit.deshmukh@maxi-teq.example.com"},
        {"CntctCode": 9002, "CardCode": "C20000", "Name": "Anita Rao",
         "Position": "Accounts Payable", "Tel1": "+91-9820011224",
         "E_MailL": "anita.rao@earthshaker.example.com"},
    ])
    insert("OITB", [
        {"ItmsGrpCod": 200, "ItmsGrpNam": "Printers"},
        {"ItmsGrpCod": 201, "ItmsGrpNam": "Servers"},
    ])
    insert("OITM", [
        {"ItemCode": "A00001", "ItemName": "LaserJet Printer XL", "ItemType": "I",
         "ItmsGrpCod": 200, "OnHand": 240.0, "IsCommited": 35.0, "OnOrder": 0.0,
         "AvgPrice": 18500.0, "LastPurPrc": 17800.0, "InvntItem": "Y", "validFor": "Y",
         "SalUnitMsr": "Pcs", "CreateDate": (today - dt.timedelta(days=800)).isoformat()},
        {"ItemCode": "A00002", "ItemName": "Rack Server 2U", "ItemType": "I",
         "ItmsGrpCod": 201, "OnHand": 62.0, "IsCommited": 10.0, "OnOrder": 25.0,
         "AvgPrice": 142000.0, "LastPurPrc": 139500.0, "InvntItem": "Y", "validFor": "Y",
         "SalUnitMsr": "Pcs", "CreateDate": (today - dt.timedelta(days=600)).isoformat()},
        {"ItemCode": "A00003", "ItemName": "Thermal Printer Compact", "ItemType": "I",
         "ItmsGrpCod": 200, "OnHand": 0.0, "IsCommited": 0.0, "OnOrder": 40.0,
         "AvgPrice": 7200.0, "LastPurPrc": 7100.0, "InvntItem": "Y", "validFor": "Y",
         "SalUnitMsr": "Pcs", "CreateDate": (today - dt.timedelta(days=400)).isoformat()},
    ])
    insert("OITW", [
        {"ItemCode": "A00001", "WhsCode": "WH01", "OnHand": 140.0, "IsCommited": 20.0,
         "OnOrder": 0.0, "AvgPrice": 18500.0, "MinStock": 50.0},
        {"ItemCode": "A00001", "WhsCode": "WH02", "OnHand": 100.0, "IsCommited": 15.0,
         "OnOrder": 0.0, "AvgPrice": 18500.0, "MinStock": 40.0},
        {"ItemCode": "A00002", "WhsCode": "WH01", "OnHand": 62.0, "IsCommited": 10.0,
         "OnOrder": 25.0, "AvgPrice": 142000.0, "MinStock": 20.0},
        {"ItemCode": "A00003", "WhsCode": "WH01", "OnHand": 0.0, "IsCommited": 0.0,
         "OnOrder": 40.0, "AvgPrice": 7200.0, "MinStock": 10.0},
    ])
    insert("OACT", [
        {"AcctCode": "111000", "AcctName": "Cash in Bank", "CurrTotal": 3271450.88,
         "ActType": "A", "Postable": "Y", "Levels": 3},
    ])
    insert("OINS", [
        {"insID": 9001 + i, "itemCode": "A00001", "customer": "C20000",
         "serialNum": f"LJXL-{1000 + i}", "startDate": (today - dt.timedelta(days=300)).isoformat(),
         "endDate": (today + dt.timedelta(days=65)).isoformat()}
        for i in range(2)
    ])
    insert("OSCL", [
        {"callID": 9001, "customer": "C20000", "subject": "Printer jams on duplex",
         "createDate": (today - dt.timedelta(days=6)).isoformat(),
         "closeDate": (today - dt.timedelta(days=3)).isoformat(),
         "status": -3, "priority": "H", "technician": "T01"},
        {"callID": 9002, "customer": "C20001", "subject": "Server fan noise",
         "createDate": (today - dt.timedelta(days=2)).isoformat(),
         "closeDate": (today - dt.timedelta(days=1)).isoformat(),
         "status": -2, "priority": "M", "technician": "T01"},
    ])
    insert("OINV", [
        {"DocEntry": 90001, "DocNum": 90001, "DocDate": (today - dt.timedelta(days=45)).isoformat(),
         "CardCode": "C20000", "CardName": "Earthshaker Corporation", "DocTotal": 486250.0,
         "DocCur": "INR", "DocStatus": "O", "CANCELED": "N", "SlpCode": 1,
         "Comments": "Q1 printer rollout", "PaidToDate": 0.0},
        {"DocEntry": 90002, "DocNum": 90002, "DocDate": (today - dt.timedelta(days=20)).isoformat(),
         "CardCode": "C20000", "CardName": "Earthshaker Corporation", "DocTotal": 132900.0,
         "DocCur": "INR", "DocStatus": "O", "CANCELED": "N", "SlpCode": 1,
         "Comments": "Consumables", "PaidToDate": 0.0},
        {"DocEntry": 90003, "DocNum": 90003, "DocDate": (today - dt.timedelta(days=10)).isoformat(),
         "CardCode": "C20001", "CardName": "Maxi-Teq", "DocTotal": 74500.0,
         "DocCur": "INR", "DocStatus": "O", "CANCELED": "N", "SlpCode": 2,
         "Comments": "Thermal printers", "PaidToDate": 0.0},
    ])
    insert("INV1", [
        {"DocEntry": 90001, "LineNum": 0, "ItemCode": "A00001", "Dscription": "LaserJet Printer XL",
         "Quantity": 24.0, "Price": 18500.0, "LineTotal": 444000.0, "WhsCode": "WH01",
         "ShipDate": (today - dt.timedelta(days=45)).isoformat()},
        {"DocEntry": 90001, "LineNum": 1, "ItemCode": "A00002", "Dscription": "Rack Server 2U",
         "Quantity": 0.2979, "Price": 142000.0, "LineTotal": 42300.0, "WhsCode": "WH01",
         "ShipDate": (today - dt.timedelta(days=45)).isoformat()},
        {"DocEntry": 90002, "LineNum": 0, "ItemCode": "A00001", "Dscription": "LaserJet Printer XL",
         "Quantity": 7.0, "Price": 18985.71, "LineTotal": 132900.0, "WhsCode": "WH02",
         "ShipDate": (today - dt.timedelta(days=20)).isoformat()},
        {"DocEntry": 90003, "LineNum": 0, "ItemCode": "A00003", "Dscription": "Thermal Printer Compact",
         "Quantity": 10.0, "Price": 7450.0, "LineTotal": 74500.0, "WhsCode": "WH01",
         "ShipDate": (today - dt.timedelta(days=10)).isoformat()},
    ])
    insert("ORDR", [
        {"DocEntry": 90011, "DocNum": 90011, "DocDate": (today - dt.timedelta(days=12)).isoformat(),
         "CardCode": "C20000", "CardName": "Earthshaker Corporation", "DocTotal": 3700000.0,
         "DocCur": "INR", "DocStatus": "O", "CANCELED": "N", "SlpCode": 1,
         "Comments": "Annual printer contract"},
        {"DocEntry": 90012, "DocNum": 90012, "DocDate": (today - dt.timedelta(days=4)).isoformat(),
         "CardCode": "C20001", "CardName": "Maxi-Teq", "DocTotal": 1420000.0,
         "DocCur": "INR", "DocStatus": "O", "CANCELED": "N", "SlpCode": 2,
         "Comments": "Server refresh"},
    ])
    insert("RDR1", [
        {"DocEntry": 90011, "LineNum": 0, "ItemCode": "A00001", "Dscription": "LaserJet Printer XL",
         "Quantity": 200.0, "Price": 18500.0, "LineTotal": 3700000.0, "WhsCode": "WH01",
         "ShipDate": (today + dt.timedelta(days=18)).isoformat()},
        {"DocEntry": 90012, "LineNum": 0, "ItemCode": "A00002", "Dscription": "Rack Server 2U",
         "Quantity": 10.0, "Price": 142000.0, "LineTotal": 1420000.0, "WhsCode": "WH01",
         "ShipDate": (today + dt.timedelta(days=25)).isoformat()},
    ])
    insert("OPDN", [
        {"DocEntry": 90021, "DocNum": 90021, "DocDate": (today - dt.timedelta(days=70)).isoformat(),
         "CardCode": vendors[0]["CardCode"], "CardName": vendors[0]["CardName"],
         "DocTotal": 2130000.0, "DocCur": "INR", "DocStatus": "C", "CANCELED": "N",
         "SlpCode": 1, "Comments": "Server hardware intake"},
    ])
    insert("PDN1", [
        {"DocEntry": 90021, "LineNum": 0, "ItemCode": "A00002", "Dscription": "Rack Server 2U",
         "Quantity": 15.0, "Price": 142000.0, "LineTotal": 2130000.0, "WhsCode": "WH01",
         "ShipDate": (today - dt.timedelta(days=70)).isoformat()},
    ])

    # Helpful indexes
    for table, column in [("ORDR", "CardCode"), ("OINV", "CardCode"), ("OINV", "DocDate"),
                          ("ORDR", "DocDate"), ("RDR1", "DocEntry"), ("INV1", "DocEntry"),
                          ("OPOR", "CardCode"), ("OITW", "ItemCode"), ("JDT1", "TransId"),
                          ("OINM", "ItemCode"), ("OVTG", "Code"), ("OCTG", "GroupNum"),
                          ("OCRN", "CurrCode"), ("OINS", "itemCode"), ("CRD1", "CardCode"),
                          ("OPDN", "DocEntry"), ("PDN1", "DocEntry")]:
        cur.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" ON "{table}" ("{column}")')

    cur.execute('DROP TABLE IF EXISTS "_SANDBOX_META"')
    cur.execute('CREATE TABLE "_SANDBOX_META" (version INTEGER)')
    cur.execute('INSERT INTO "_SANDBOX_META" (version) VALUES (?)', (SANDBOX_SCHEMA_VERSION,))
    conn.commit()
    _ = orders, purchase_orders  # keep references for readability
