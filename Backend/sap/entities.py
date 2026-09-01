"""SAP Business One semantic layer.

Maps the words humans use ("open invoices", "vendors", "stock") onto the real
B1 table names, knows which columns matter on each table, and translates the
one-letter status codes B1 stores into words a human (and an LLM) understands.

Nothing here restricts what can be queried -- the agent can always address any
table in the company schema by its real name.  This map only makes the common
90% fast and accurate.
"""

from __future__ import annotations

import re

# ── Friendly name -> physical table ──────────────────────────────────────────
TABLE_ALIASES: dict[str, str] = {}


def _alias(table: str, *names: str) -> None:
    for n in names:
        TABLE_ALIASES[n.lower()] = table


# Sales
_alias("OQUT", "salesquotations", "quotations", "quotes", "sales quotes")
_alias("ORDR", "orders", "salesorders", "sales orders", "sales order", "so", "salesorderset")
_alias("RDR1", "salesorderlines", "order lines", "orderlines", "sales order lines")
_alias("ODLN", "deliveries", "deliverynotes", "delivery notes", "shipments", "goods issue notes")
_alias("DLN1", "deliverylines", "delivery lines")
_alias("ORDN", "returns", "salesreturns", "sales returns")
_alias("OINV", "invoices", "arinvoices", "ar invoices", "sales invoices", "customer invoices", "billing")
_alias("INV1", "invoicelines", "invoice lines", "ar invoice lines")
_alias("ORIN", "creditmemos", "arcreditmemos", "credit notes", "sales credit memos")
_alias("ODPI", "ardownpayments", "customer down payments")

# Purchasing
_alias("OPRQ", "purchaserequests", "purchase requests", "requisitions")
_alias("OPQT", "purchasequotations", "purchase quotations", "rfq")
_alias("OPOR", "purchaseorders", "purchase orders", "po", "pos", "procurement", "procurementset")
_alias("POR1", "purchaseorderlines", "po lines", "purchase order lines")
_alias("OPDN", "goodsreceiptpo", "goods receipt po", "grpo", "purchase deliveries")
_alias("ORPD", "goodsreturns", "purchase returns")
_alias("OPCH", "apinvoices", "ap invoices", "purchaseinvoices", "vendor invoices", "supplier invoices")
_alias("PCH1", "apinvoicelines", "ap invoice lines")
_alias("ORPC", "apcreditmemos", "purchase credit memos")

# Business partners
_alias("OCRD", "businesspartners", "business partners", "customers", "vendors", "suppliers", "bp", "accounts", "clients")
_alias("CRD1", "bpaddresses", "addresses", "business partner addresses")
_alias("OCPR", "contacts", "contactpersons", "contact persons")
_alias("OCRG", "customergroups", "bp groups", "customer groups")

# Inventory
_alias("OITM", "items", "products", "inventory", "stock", "materials", "articles", "itemmaster", "item master")
_alias("ITM1", "itemprices", "price list entries", "item prices")
_alias("OITW", "itemwarehouse", "stock by warehouse", "warehouse stock", "item warehouse")
_alias("OWHS", "warehouses", "locations", "stores")
_alias("OITB", "itemgroups", "item groups", "product groups", "categories")
_alias("OINM", "inventorytransactions", "stock movements", "inventory movements", "inventory journal")
_alias("OWTR", "stocktransfers", "inventory transfers", "transfers")
_alias("OIGN", "goodsreceipts", "goods receipt")
_alias("OIGE", "goodsissues", "goods issue")
_alias("OBTN", "batches", "batch numbers")
_alias("OSRN", "serialnumbers", "serials")

# Finance
_alias("OJDT", "journalentries", "journal entries", "je", "gl postings", "general ledger")
_alias("JDT1", "journallines", "journal entry lines", "gl lines")
_alias("OACT", "chartofaccounts", "chart of accounts", "glaccounts", "gl accounts", "accounts ledger")
_alias("ORCT", "incomingpayments", "incoming payments", "customer payments", "receipts")
_alias("OVPM", "outgoingpayments", "outgoing payments", "vendor payments", "supplier payments")
_alias("OCRN", "currencies")
_alias("ORTT", "exchangerates", "exchange rates")
_alias("OFPR", "postingperiods", "posting periods", "fiscal periods")
_alias("OVTG", "taxcodes", "tax groups", "vat codes")
_alias("OBGT", "budgets", "budget")

# People
_alias("OHEM", "employees", "employeesinfo", "staff", "headcount", "employeeset", "payroll")
_alias("OUDP", "departments")
_alias("OHPS", "positions", "job positions")
_alias("OUBR", "branches")
_alias("OSLP", "salesemployees", "sales employees", "sales reps", "salespersons")
_alias("OUSR", "users", "systemusers", "b1 users")

# CRM / service / production
_alias("OOPR", "opportunities", "pipeline", "sales opportunities", "leads")
_alias("OCLG", "activities", "calendar", "tasks", "meetings")
_alias("OSCL", "servicecalls", "service calls", "tickets", "support calls")
_alias("OCTR", "servicecontracts", "contracts", "service contracts")
_alias("OWOR", "productionorders", "production orders", "work orders", "manufacturing orders")
_alias("OITT", "billofmaterials", "bom", "bill of materials", "recipes")

# System / metadata
_alias("OADM", "companydetails", "company", "company details")
_alias("CUFD", "userfields", "user defined fields", "udf", "custom fields")
_alias("OUTB", "usertables", "user defined tables", "udt")
_alias("OUQR", "userqueries", "saved queries", "user queries")

TABLE_DESCRIPTIONS: dict[str, str] = {
    "OQUT": "Sales quotations (header)",
    "ORDR": "Sales orders (header)",
    "RDR1": "Sales order line items",
    "ODLN": "Deliveries / shipments (header)",
    "DLN1": "Delivery line items",
    "ORDN": "Sales returns (header)",
    "OINV": "A/R invoices — customer billing (header)",
    "INV1": "A/R invoice line items",
    "ORIN": "A/R credit memos (header)",
    "OPRQ": "Purchase requests",
    "OPQT": "Purchase quotations",
    "OPOR": "Purchase orders (header)",
    "POR1": "Purchase order line items",
    "OPDN": "Goods receipt PO (header)",
    "OPCH": "A/P invoices — vendor bills (header)",
    "PCH1": "A/P invoice line items",
    "ORPC": "A/P credit memos",
    "OCRD": "Business partner master — customers, vendors and leads",
    "CRD1": "Business partner addresses",
    "OCPR": "Business partner contact persons",
    "OCRG": "Customer groups",
    "OITM": "Item master — products, services and materials",
    "ITM1": "Item price list entries",
    "OITW": "Item stock per warehouse",
    "OWHS": "Warehouse master",
    "OITB": "Item groups / product categories",
    "OINM": "Inventory transaction journal (every stock movement)",
    "OWTR": "Inventory transfers",
    "OJDT": "Journal entries (header)",
    "JDT1": "Journal entry lines — the general ledger",
    "OACT": "Chart of accounts",
    "ORCT": "Incoming payments",
    "OVPM": "Outgoing payments",
    "OCRN": "Currencies",
    "OFPR": "Posting periods",
    "OHEM": "Employee master data",
    "OUDP": "Departments",
    "OSLP": "Sales employees / buyers",
    "OUSR": "SAP B1 users",
    "OOPR": "Sales opportunities (pipeline)",
    "OCLG": "Activities / calendar entries",
    "OSCL": "Service calls",
    "OWOR": "Production orders",
    "OITT": "Bill of materials",
    "OADM": "Company configuration",
    "CUFD": "User-defined field definitions",
    "OUTB": "User-defined tables",
    "OUQR": "Saved user queries",
}

# Columns worth showing first for the heavy tables (B1 headers have 150+ cols).
PREFERRED_COLUMNS: dict[str, list[str]] = {
    "ORDR": ["DocNum", "DocDate", "DocDueDate", "CardCode", "CardName", "DocTotal",
             "DocCur", "DocStatus", "CANCELED", "SlpCode", "Comments"],
    "OQUT": ["DocNum", "DocDate", "DocDueDate", "CardCode", "CardName", "DocTotal",
             "DocCur", "DocStatus", "CANCELED"],
    "OINV": ["DocNum", "DocDate", "DocDueDate", "CardCode", "CardName", "DocTotal",
             "PaidToDate", "DocStatus", "CANCELED", "DocCur", "VatSum"],
    "ORIN": ["DocNum", "DocDate", "CardCode", "CardName", "DocTotal", "DocStatus", "CANCELED"],
    "ODLN": ["DocNum", "DocDate", "CardCode", "CardName", "DocTotal", "DocStatus", "CANCELED"],
    "OPOR": ["DocNum", "DocDate", "DocDueDate", "CardCode", "CardName", "DocTotal",
             "DocCur", "DocStatus", "CANCELED"],
    "OPCH": ["DocNum", "DocDate", "DocDueDate", "CardCode", "CardName", "DocTotal",
             "PaidToDate", "DocStatus", "CANCELED"],
    "OPDN": ["DocNum", "DocDate", "CardCode", "CardName", "DocTotal", "DocStatus"],
    "RDR1": ["DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "Price",
             "LineTotal", "WhsCode", "ShipDate"],
    "INV1": ["DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "Price",
             "LineTotal", "WhsCode"],
    "POR1": ["DocEntry", "LineNum", "ItemCode", "Dscription", "Quantity", "Price",
             "LineTotal", "WhsCode"],
    "OCRD": ["CardCode", "CardName", "CardType", "GroupCode", "Balance", "Phone1",
             "E_Mail", "City", "Country", "Currency", "validFor", "CreateDate"],
    "OITM": ["ItemCode", "ItemName", "ItemType", "ItmsGrpCod", "OnHand", "IsCommited",
             "OnOrder", "AvgPrice", "LastPurPrc", "InvntItem", "validFor"],
    "OITW": ["ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder", "AvgPrice"],
    "OWHS": ["WhsCode", "WhsName", "City", "Country", "Inactive"],
    "OHEM": ["empID", "firstName", "lastName", "jobTitle", "dept", "branch", "salary",
             "startDate", "Active", "email"],
    "OJDT": ["TransId", "RefDate", "Memo", "TransType", "DebPayAcct", "BaseRef"],
    "JDT1": ["TransId", "Line_ID", "Account", "AcctName", "Debit", "Credit", "RefDate", "LineMemo"],
    "OACT": ["AcctCode", "AcctName", "CurrTotal", "ActType", "Levels", "Postable"],
    "ORCT": ["DocNum", "DocDate", "CardCode", "CardName", "DocTotal", "DocCurr", "Canceled"],
    "OVPM": ["DocNum", "DocDate", "CardCode", "CardName", "DocTotal", "DocCurr", "Canceled"],
    "OOPR": ["OpprId", "CardCode", "CardName", "OpenDate", "CloseDate", "MaxSumLoc",
             "PredDate", "Status"],
    "OSCL": ["callID", "customer", "subject", "createDate", "status", "priority"],
    "OWOR": ["DocNum", "ItemCode", "PlannedQty", "CmpltQty", "Status", "PostDate", "DueDate"],
}

# What a table "means" — used for automatic charts, date filters and sorting.
SEMANTICS: dict[str, dict[str, str]] = {
    "ORDR": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "OQUT": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "OINV": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "ORIN": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "ODLN": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "OPOR": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "OPCH": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "OPDN": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "status": "DocStatus", "key": "DocNum"},
    "ORCT": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "key": "DocNum"},
    "OVPM": {"date": "DocDate", "amount": "DocTotal", "party": "CardName", "key": "DocNum"},
    "OCRD": {"date": "CreateDate", "amount": "Balance", "party": "CardName", "key": "CardCode"},
    "OITM": {"date": "CreateDate", "amount": "OnHand", "party": "ItemName", "key": "ItemCode"},
    "OITW": {"amount": "OnHand", "party": "WhsCode", "key": "ItemCode"},
    "OHEM": {"date": "startDate", "amount": "salary", "party": "lastName", "key": "empID"},
    "JDT1": {"date": "RefDate", "amount": "Debit", "party": "AcctName", "key": "TransId"},
    "OJDT": {"date": "RefDate", "party": "Memo", "key": "TransId"},
    "OWOR": {"date": "PostDate", "amount": "PlannedQty", "party": "ItemCode", "key": "DocNum"},
    "OOPR": {"date": "OpenDate", "amount": "MaxSumLoc", "party": "CardName", "key": "OpprId"},
    "RDR1": {"date": "ShipDate", "amount": "LineTotal", "party": "Dscription", "key": "ItemCode"},
    "INV1": {"amount": "LineTotal", "party": "Dscription", "key": "ItemCode"},
    "POR1": {"amount": "LineTotal", "party": "Dscription", "key": "ItemCode"},
}

# One-letter codes SAP B1 stores -> words.  (column name is matched case-insensitively)
CODE_MAPS: dict[str, dict[str, str]] = {
    "docstatus": {"O": "Open", "C": "Closed", "L": "Closed", "D": "Draft", "P": "Paid"},
    "canceled": {"Y": "Cancelled", "N": "Active", "C": "Cancellation"},
    "cardtype": {"C": "Customer", "S": "Vendor", "L": "Lead"},
    "itemtype": {"I": "Item", "L": "Labor", "T": "Travel", "F": "Fixed Asset"},
    "validfor": {"Y": "Active", "N": "Inactive"},
    "frozenfor": {"Y": "Frozen", "N": "Not frozen"},
    "invntitem": {"Y": "Inventory item", "N": "Non-inventory"},
    "inactive": {"Y": "Inactive", "N": "Active"},
    "active": {"Y": "Active", "N": "Inactive"},
    "postable": {"Y": "Postable", "N": "Title account"},
    "objtype": {},
    "doctype": {"I": "Items", "S": "Service"},
    "printed": {"Y": "Printed", "N": "Not printed"},
    "status": {"O": "Open", "C": "Closed", "-3": "Open", "-2": "Lost", "-1": "Won"},
}

# Reverse direction: what the user says -> what B1 stores
VALUE_ENCODINGS: dict[str, dict[str, str]] = {
    "docstatus": {
        "open": "O", "o": "O", "pending": "O", "outstanding": "O", "unpaid": "O",
        "closed": "C", "c": "C", "complete": "C", "completed": "C", "delivered": "C",
        "draft": "D",
    },
    "canceled": {"cancelled": "Y", "canceled": "Y", "active": "N", "not cancelled": "N",
                 "yes": "Y", "no": "N", "y": "Y", "n": "N"},
    "cardtype": {"customer": "C", "customers": "C", "client": "C", "clients": "C",
                 "vendor": "S", "vendors": "S", "supplier": "S", "suppliers": "S",
                 "lead": "L", "leads": "L", "prospect": "L"},
    "itemtype": {"item": "I", "items": "I", "labor": "L", "labour": "L", "travel": "T",
                 "fixed asset": "F"},
    "validfor": {"active": "Y", "yes": "Y", "y": "Y", "inactive": "N", "no": "N", "n": "N"},
    "inactive": {"inactive": "Y", "yes": "Y", "y": "Y", "active": "N", "no": "N", "n": "N"},
    "active": {"active": "Y", "yes": "Y", "y": "Y", "inactive": "N", "no": "N", "n": "N"},
}

# Housekeeping columns that add noise to an executive table.
NOISY_COLUMNS = {
    "loginstanc", "usersign", "usersign2", "transfered", "createts", "updatets",
    "datasource", "userfld", "objtype", "logmsg", "printed", "attachment",
    "checksum", "instance", "srccurr", "srcrate", "extrdays", "reserve",
}


def normalise_table_name(name: str) -> str:
    """Resolve a friendly entity name to a physical SAP B1 table name.

    Returns the uppercase physical name; unknown names are returned uppercased
    unchanged so the caller can still validate them against the live catalog.
    """
    if not name:
        return ""
    raw = name.strip()
    key = re.sub(r"[^a-z0-9@ ]", "", raw.lower()).strip()
    if key in TABLE_ALIASES:
        return TABLE_ALIASES[key]
    compact = key.replace(" ", "")
    if compact in TABLE_ALIASES:
        return TABLE_ALIASES[compact]
    # singular/plural tolerance
    for candidate in (compact + "s", compact.rstrip("s")):
        if candidate in TABLE_ALIASES:
            return TABLE_ALIASES[candidate]
    return raw.upper()


def describe_table_name(table: str) -> str:
    return TABLE_DESCRIPTIONS.get(table.upper(), "")


def semantics_for(table: str) -> dict:
    return SEMANTICS.get(table.upper(), {})


def preferred_columns(table: str) -> list[str]:
    return PREFERRED_COLUMNS.get(table.upper(), [])


def encode_value(column: str, value):
    """Translate a human word into the code SAP B1 stores in that column."""
    if not isinstance(value, str):
        return value
    mapping = VALUE_ENCODINGS.get((column or "").lower())
    if not mapping:
        return value
    return mapping.get(value.strip().lower(), value)


def decode_rows(rows: list[dict]) -> list[dict]:
    """Replace B1 one-letter codes with readable words, in place-ish."""
    if not rows:
        return rows
    columns = list(rows[0].keys())
    decodable = {c: CODE_MAPS[c.lower()] for c in columns if CODE_MAPS.get(c.lower())}
    if not decodable:
        return rows
    for row in rows:
        for col, mapping in decodable.items():
            val = row.get(col)
            if isinstance(val, str) and val in mapping:
                row[col] = mapping[val]
            elif isinstance(val, int) and str(val) in mapping:
                row[col] = mapping[str(val)]
    return rows


def is_noisy(column: str) -> bool:
    return column.lower() in NOISY_COLUMNS


def known_entities() -> list[dict]:
    """Compact catalogue handed to the LLM in the system prompt."""
    seen: dict[str, list[str]] = {}
    for alias, table in TABLE_ALIASES.items():
        seen.setdefault(table, []).append(alias)
    out = []
    for table, aliases in sorted(seen.items()):
        out.append(
            {
                "table": table,
                "description": TABLE_DESCRIPTIONS.get(table, ""),
                "aliases": sorted(aliases, key=len)[:4],
            }
        )
    return out
