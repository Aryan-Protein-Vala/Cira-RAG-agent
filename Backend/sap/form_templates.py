"""Official SAP Business One Service Layer Form Templates.

Provides canonical, schema-verified form structures based on the SAP B1 Service Layer
reference documentation. Ensures reliable, consistent, and validated data entry.
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def _today_mmddyyyy() -> str:
    today = dt.date.today()
    return f"{today.month:02d}/{today.day:02d}/{today.year}"


def _due_date_mmddyyyy(days: int = 30) -> str:
    due = dt.date.today() + dt.timedelta(days=days)
    return f"{due.month:02d}/{due.day:02d}/{due.year}"


TEMPLATES: dict[str, dict[str, Any]] = {
    # ── Business Partners (Customer / Vendor / Lead) ─────────────────────────
    "BusinessPartners_Customer": {
        "entity": "BusinessPartners",
        "table": "OCRD",
        "title": "Create Customer",
        "fields": [
            {
                "name": "CardCode",
                "label": "Customer Code",
                "type": "text",
                "required": True,
                "hint": "Unique SAP ID (e.g. C00001)",
            },
            {
                "name": "CardName",
                "label": "Customer / Company Name",
                "type": "text",
                "required": True,
                "hint": "Full legal or trading name",
            },
            {
                "name": "CardType",
                "label": "Partner Type",
                "type": "select",
                "required": True,
                "default": "cCustomer",
                "options": [
                    {"value": "cCustomer", "label": "Customer"},
                    {"value": "cSupplier", "label": "Vendor / Supplier"},
                    {"value": "cLid", "label": "Lead"},
                ],
            },
            {
                "name": "Currency",
                "label": "Account Currency",
                "type": "select",
                "required": False,
                "default": "INR",
                "options": [
                    {"value": "INR", "label": "Indian Rupee (INR)"},
                    {"value": "USD", "label": "US Dollar (USD)"},
                    {"value": "EUR", "label": "Euro (EUR)"},
                    {"value": "AED", "label": "UAE Dirham (AED)"},
                    {"value": "GBP", "label": "British Pound (GBP)"},
                    {"value": "##", "label": "All Currencies (##)"},
                ],
            },
            {
                "name": "Phone1",
                "label": "Primary Phone",
                "type": "text",
                "required": False,
                "hint": "e.g. +91 98765 43210",
            },
            {
                "name": "EmailAddress",
                "label": "Email Address",
                "type": "text",
                "required": False,
                "hint": "e.g. finance@customer.com",
            },
            {
                "name": "FederalTaxID",
                "label": "GSTIN / Tax ID",
                "type": "text",
                "required": False,
                "hint": "e.g. 07AAAAA0000A1Z5",
            },
        ],
    },
    "BusinessPartners_Vendor": {
        "entity": "BusinessPartners",
        "table": "OCRD",
        "title": "Register Vendor",
        "fields": [
            {
                "name": "CardCode",
                "label": "Vendor Code",
                "type": "text",
                "required": True,
                "hint": "Unique SAP ID (e.g. V00001)",
            },
            {
                "name": "CardName",
                "label": "Vendor / Supplier Name",
                "type": "text",
                "required": True,
                "hint": "Full legal or vendor name",
            },
            {
                "name": "CardType",
                "label": "Partner Type",
                "type": "select",
                "required": True,
                "default": "cSupplier",
                "options": [
                    {"value": "cSupplier", "label": "Vendor / Supplier"},
                    {"value": "cCustomer", "label": "Customer"},
                    {"value": "cLid", "label": "Lead"},
                ],
            },
            {
                "name": "Currency",
                "label": "Account Currency",
                "type": "select",
                "required": False,
                "default": "INR",
                "options": [
                    {"value": "INR", "label": "Indian Rupee (INR)"},
                    {"value": "USD", "label": "US Dollar (USD)"},
                    {"value": "EUR", "label": "Euro (EUR)"},
                    {"value": "AED", "label": "UAE Dirham (AED)"},
                    {"value": "GBP", "label": "British Pound (GBP)"},
                ],
            },
            {
                "name": "Phone1",
                "label": "Primary Phone",
                "type": "text",
                "required": False,
            },
            {
                "name": "EmailAddress",
                "label": "Email Address",
                "type": "text",
                "required": False,
            },
            {
                "name": "FederalTaxID",
                "label": "GSTIN / Tax ID",
                "type": "text",
                "required": False,
            },
        ],
    },

    # ── Item Master Data ─────────────────────────────────────────────────────
    "Items": {
        "entity": "Items",
        "table": "OITM",
        "title": "Create Item Master",
        "fields": [
            {
                "name": "ItemCode",
                "label": "Item Code",
                "type": "text",
                "required": True,
                "hint": "Unique Item Code (e.g. A00001)",
            },
            {
                "name": "ItemName",
                "label": "Item Description",
                "type": "text",
                "required": True,
                "hint": "Detailed item / product name",
            },
            {
                "name": "ItemsGroupCode",
                "label": "Item Group Code",
                "type": "number",
                "required": True,
                "default": 100,
                "hint": "Item group category code (e.g. 100)",
            },
            {
                "name": "ItemType",
                "label": "Item Type",
                "type": "select",
                "required": True,
                "default": "itItems",
                "options": [
                    {"value": "itItems", "label": "Inventory / Goods (itItems)"},
                    {"value": "itLabor", "label": "Labor / Service (itLabor)"},
                    {"value": "itTravel", "label": "Travel (itTravel)"},
                ],
            },
            {
                "name": "AvgStdPrice",
                "label": "Standard Price (INR)",
                "type": "number",
                "required": False,
                "default": 0.0,
                "hint": "Base or valuation price",
            },
            {
                "name": "SalesUnit",
                "label": "Sales Unit of Measure",
                "type": "text",
                "required": False,
                "default": "Pcs",
                "hint": "e.g. Pcs, Box, Kg, Mtr",
            },
        ],
    },

    # ── Sales Orders ─────────────────────────────────────────────────────────
    "Orders": {
        "entity": "Orders",
        "table": "ORDR",
        "title": "Create Sales Order",
        "fields": [
            {
                "name": "CardCode",
                "label": "Customer Code",
                "type": "text",
                "required": True,
                "hint": "Customer ID in SAP (e.g. C00001)",
            },
            {
                "name": "Series",
                "label": "Numbering Series",
                "type": "number",
                "required": True,
                "hint": "SAP Numbering Series ID",
            },
            {
                "name": "BPL_IDAssignedToInvoice",
                "label": "Branch (BPL ID)",
                "type": "number",
                "required": True,
                "hint": "Business Place / Branch ID",
            },
            {
                "name": "DocDate",
                "label": "Posting Date",
                "type": "date",
                "required": True,
                "default": _today_mmddyyyy(),
                "hint": "Format: MM/DD/YYYY",
            },
            {
                "name": "DocDueDate",
                "label": "Delivery Date",
                "type": "date",
                "required": True,
                "default": _due_date_mmddyyyy(7),
                "hint": "Format: MM/DD/YYYY",
            },

            {
                "name": "Comments",
                "label": "Order Remarks",
                "type": "text",
                "required": False,
                "hint": "Additional notes / reference",
            },
            {
                "name": "ItemCode",
                "label": "Item Code",
                "type": "text",
                "required": True,
                "hint": "SAP Item Code to add to order",
            },
            {
                "name": "Quantity",
                "label": "Quantity",
                "type": "number",
                "required": True,
                "default": 1,
            },
            {
                "name": "UnitPrice",
                "label": "Unit Price",
                "type": "number",
                "required": False,
                "hint": "Leave blank to use default price list",
            },
        ],
    },

    # ── A/R Invoices ─────────────────────────────────────────────────────────
    "Invoices": {
        "entity": "Invoices",
        "table": "OINV",
        "title": "Create A/R Invoice",
        "fields": [
            {
                "name": "CardCode",
                "label": "Customer Code",
                "type": "text",
                "required": True,
                "hint": "Customer ID in SAP (e.g. C00001)",
            },
            {
                "name": "Series",
                "label": "Numbering Series",
                "type": "number",
                "required": True,
                "hint": "SAP Numbering Series ID",
            },
            {
                "name": "BPL_IDAssignedToInvoice",
                "label": "Branch (BPL ID)",
                "type": "number",
                "required": True,
                "hint": "Business Place / Branch ID",
            },
            {
                "name": "DocDate",
                "label": "Invoice Date",
                "type": "date",
                "required": True,
                "default": _today_mmddyyyy(),
                "hint": "Format: MM/DD/YYYY",
            },
            {
                "name": "DocDueDate",
                "label": "Due Date",
                "type": "date",
                "required": True,
                "default": _due_date_mmddyyyy(30),
                "hint": "Format: MM/DD/YYYY",
            },

            {
                "name": "Comments",
                "label": "Invoice Comments",
                "type": "text",
                "required": False,
            },
            {
                "name": "ItemCode",
                "label": "Item Code",
                "type": "text",
                "required": True,
                "hint": "SAP Item Code to invoice",
            },
            {
                "name": "Quantity",
                "label": "Quantity",
                "type": "number",
                "required": True,
                "default": 1,
            },
            {
                "name": "UnitPrice",
                "label": "Unit Price",
                "type": "number",
                "required": False,
                "hint": "Leave blank to use default price list",
            },
            {
                "name": "TaxCode",
                "label": "Tax Code",
                "type": "text",
                "required": False,
                "hint": "e.g. IGST18, EXEMPT",
            },
        ],
    },

    # ── Purchase Orders ──────────────────────────────────────────────────────
    "PurchaseOrders": {
        "entity": "PurchaseOrders",
        "table": "OPOR",
        "title": "Create Purchase Order",
        "fields": [
            {
                "name": "CardCode",
                "label": "Vendor Code",
                "type": "text",
                "required": True,
                "hint": "Vendor ID in SAP (e.g. V00001)",
            },
            {
                "name": "DocDate",
                "label": "Order Date",
                "type": "date",
                "required": True,
                "default": _today_mmddyyyy(),
                "hint": "Format: MM/DD/YYYY",
            },
            {
                "name": "DocDueDate",
                "label": "Expected Delivery Date",
                "type": "date",
                "required": True,
                "default": _due_date_mmddyyyy(14),
                "hint": "Format: MM/DD/YYYY",
            },

            {
                "name": "Comments",
                "label": "PO Remarks",
                "type": "text",
                "required": False,
            },
            {
                "name": "ItemCode",
                "label": "Item Code",
                "type": "text",
                "required": True,
            },
            {
                "name": "Quantity",
                "label": "Quantity",
                "type": "number",
                "required": True,
                "default": 1,
            },
        ],
    },
}


def get_template_for_intent(intent_or_entity: str) -> dict[str, Any] | None:
    """Find the best canonical template matching a user's intent or entity name."""
    needle = intent_or_entity.strip().lower()

    if any(w in needle for w in ("vendor", "supplier", "csupplier")):
        return TEMPLATES["BusinessPartners_Vendor"]
    if any(w in needle for w in ("customer", "client", "business partner", "ccustomer", "businesspartners", "ocrd")):
        return TEMPLATES["BusinessPartners_Customer"]
    if any(w in needle for w in ("item", "product", "material", "inventory item", "oitm", "items")):
        return TEMPLATES["Items"]
    if any(w in needle for w in ("sales order", "order", "ordr", "orders")):
        return TEMPLATES["Orders"]
    if any(w in needle for w in ("invoice", "ar invoice", "oinv", "invoices", "bill")):
        return TEMPLATES["Invoices"]
    if any(w in needle for w in ("purchase order", "po", "opor", "purchaseorders")):
        return TEMPLATES["PurchaseOrders"]

    # Direct entity key lookup
    for key, tpl in TEMPLATES.items():
        if key.lower() == needle or tpl["entity"].lower() == needle or tpl["table"].lower() == needle:
            return tpl

    return None
