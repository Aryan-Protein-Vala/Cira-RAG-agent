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
from .types_ import ColumnInfo, TableInfo

log = logging.getLogger("cira.sim")

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
for _t in ("RDR1", "INV1", "POR1", "PCH1", "DLN1", "QUT1"):
    SCHEMA[_t] = list(_DOC_LINE)

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

    # Helpful indexes
    for table, column in [("ORDR", "CardCode"), ("OINV", "CardCode"), ("OINV", "DocDate"),
                          ("ORDR", "DocDate"), ("RDR1", "DocEntry"), ("INV1", "DocEntry"),
                          ("OPOR", "CardCode"), ("OITW", "ItemCode"), ("JDT1", "TransId"),
                          ("OINM", "ItemCode")]:
        cur.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" ON "{table}" ("{column}")')

    conn.commit()
    _ = orders, purchase_orders  # keep references for readability
