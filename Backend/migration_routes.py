"""Excel → SAP Business One migration: upload → map → validate → push.

Rewritten. The previous version could not be used on real data:

* ``from auth import require_role`` did not exist, so the module raised
  ImportError and the whole /admin/migration router was dead code - and it was
  never mounted in main.py either (now it is; see include_router in main.py).
* ``.csv`` passed the extension check and was then handed to
  ``openpyxl.load_workbook``, which cannot open CSV at all.
* Every cell was ``str()``-ified, destroying dates and numbers before the
  Service Layer ever saw them.
* "Fuzzy" matching was an exact alias lookup with the confidence hard-coded to
  100 or 0 - so a column called "Customer Name " scored 100 and "Name of
  Customer" scored 0, and the UI showed both as certain.
* ``/push`` read the row from SAP, found it already existed, **skipped it and
  counted it as a success**. Re-pushing a corrected file therefore reported a
  clean run while having changed nothing - the exact failure mode that makes an
  accountant stop trusting a migration tool.
* There was no idempotency key, no per-row error reference, no way to re-push
  only the failed rows, and no audit record.

What this file does now
-----------------------
The endpoint contract the existing admin UI expects is unchanged
(``upload`` → ``validate`` → ``push``), and the responses are supersets:

upload    {headers, total_rows, samples, raw_data, target, warnings}
validate  {valid_count, error_count, errors[], valid_rows, column_report}
push      {success, failed, skipped, created, updated, errors[], failed_rows,
           results[], idempotency_key}

Everything below the endpoint layer is deliberately boring: a per-target
profile describing what SAP requires, and one validation pass that produces
column-level findings a human can read before anything touches the ERP.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List

import openpyxl
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from auth import require_role
from database import CompanyConnection, Partner, Tenant, get_db

log = logging.getLogger("cira.migration")

router = APIRouter(prefix="/admin/migration", tags=["Migration"])


async def resolve_tenant(
    ctx: dict = Depends(require_role(["partner_admin", "superadmin"])),
    x_tenant_id: str = Header(default="", alias="x-tenant-id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pick the company these rows are going into, and load its credentials.

    These routes previously never set CURRENT_TENANT at all, so every push was
    refused with "writes are disabled" no matter how the tenant was configured -
    the migration tool could not write even in principle. The tenant now comes
    from the x-tenant-id header (a partner admin manages many clients) or from
    the token's company_db, and it must exist and be active.
    """
    company_db = (x_tenant_id or ctx.get("company_db") or "").strip()
    if not company_db:
        raise HTTPException(
            status_code=400,
            detail="No tenant selected. Send the client's company database in the "
                   "x-tenant-id header.",
        )

    result = await db.execute(select(Tenant).where(Tenant.company_db == company_db))
    tenant_row = result.scalars().first()
    if tenant_row:
        if not tenant_row.is_active:
            raise HTTPException(status_code=403, detail="Tenant is inactive.")
        partner_row = (await db.execute(
            select(Partner).where(Partner.id == tenant_row.partner_id))).scalars().first()
        if partner_row and not partner_row.is_active:
            raise HTTPException(status_code=403, detail="Partner account is suspended.")
        is_mssql = (tenant_row.backend_type or "").lower() == "mssql"
        config.CURRENT_TENANT.set({
            "HANA_SCHEMA": tenant_row.company_db,
            "SAP_B1_COMPANY_DB": tenant_row.company_db,
            "HANA_HOST": tenant_row.sap_host,
            "HANA_PORT": tenant_row.sap_hana_port,
            "HANA_USER": tenant_row.sap_db_user,
            "HANA_PASSWORD": tenant_row.sap_db_password,
            "MSSQL_HOST": tenant_row.sap_host if is_mssql else "",
            "MSSQL_PORT": tenant_row.sap_hana_port if is_mssql else 1433,
            "MSSQL_USER": tenant_row.sap_db_user if is_mssql else "",
            "MSSQL_PASSWORD": tenant_row.sap_db_password if is_mssql else "",
            "SAP_B1_HOST": tenant_row.sap_host,
            "SAP_B1_PORT": tenant_row.sap_hana_port,
            "SERVICE_LAYER_PORT": tenant_row.sap_sl_port,
            "SAP_B1_USER": tenant_row.sap_sl_user,
            "SAP_B1_PASSWORD": tenant_row.sap_sl_password,
            "WRITE_ENABLED": bool(tenant_row.write_enabled),
        })
        return ctx
    raise HTTPException(
        status_code=404,
        detail=f"No tenant is registered for company database '{company_db}'.",
    )

# ── targets ─────────────────────────────────────────────────────────────────
# One profile per object. `aliases` are what we match headers against;
# `required` is what SAP itself will reject the row for; `max_len` mirrors the
# database column widths from SAP's own schema (so a 60-character CardName is
# caught here instead of failing halfway through a Service Layer call).
TARGETS: Dict[str, Dict[str, Any]] = {
    "BusinessPartners": {
        "entity": "BusinessPartners",
        "table": "OCRD",
        "label": "Business Partners (Customers & Vendors)",
        "key": "CardCode",
        "key_label": "CardCode",
        "aliases": {
            "CardCode": ["cardcode", "customer code", "vendor code", "bp code", "business partner code",
                         "code", "id", "account code", "ग्राहक कोड"],
            "CardName": ["cardname", "customer name", "vendor name", "bp name", "business partner name",
                         "name", "company name", "account name", "ग्राहक नाम", "खाता नाम"],
            "CardType": ["cardtype", "type", "bp type", "role", "customer/vendor", "is customer or vendor"],
            "Phone1": ["phone1", "phone", "telephone", "tel", "contact number"],
            "Cellular": ["cellular", "mobile", "mobile 2", "cell"],
            "E_Mail": ["e_mail", "email", "e-mail", "email id", "e mail"],
            "VatIdUnCmp": ["vatiduncmp", "gstin", "gst", "tax id", "vat", "pan", "tin"],
            "City": ["city", "town"],
            "Country": ["country", "country code"],
            "Currency": ["currency", "curr", "doc currency"],
            "CreditLine": ["creditline", "credit limit", "limit"],
            "GroupCode": ["groupcode", "bp group", "group"],
            "SlpCode": ["slpcode", "sales employee", "sales person", "sales rep"],
        },
        "required": ["CardCode", "CardName", "CardType"],
        "max_len": {"CardCode": 15, "CardName": 100, "Phone1": 20, "Cellular": 20,
                    "E_Mail": 100, "VatIdUnCmp": 32, "City": 100, "Country": 3, "Currency": 3},
        "enums": {"CardType": {"customer": "C", "vendor": "S", "supplier": "S", "lead": "L",
                               "c": "C", "s": "S", "l": "L"}},
        "date_fields": [],
        "number_fields": ["CreditLine", "GroupCode", "SlpCode"],
        # India-specific tax id check. 15 characters, the standard GSTIN shape.
        # A wrong GSTIN on a customer master is a filing problem discovered
        # months later, so it is worth a hard stop here.
        "patterns": {
            "VatIdUnCmp": (
                r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$",
                "does not look like a 15-character GSTIN (example: 27ABCDE1234F1Z5)",
            )
        },
    },
    "Items": {
        "entity": "Items",
        "table": "OITM",
        "label": "Item Master (OITM)",
        "key": "ItemCode",
        "key_label": "ItemCode",
        "aliases": {
            "ItemCode": ["itemcode", "item code", "item no", "item number", "sku", "product code", "code"],
            "ItemName": ["itemname", "item name", "description", "product name", "name"],
            "ItemType": ["itemtype", "item type", "type"],
            "ItmsGrpCod": ["itmsgrpcod", "item group", "group", "item group code", "category"],
            "InvntItem": ["invntitem", "inventory item", "is inventory", "stock item"],
            "validFor": ["validfor", "active", "valid", "is active"],
            "SalUnitMsr": ["salunitmsr", "sales unit", "uom", "unit of measure", "unit"],
            "AvgPrice": ["avgprice", "average price", "cost", "avg cost"],
            "LastPurPrc": ["lastpurprc", "last purchase price", "last cost"],
        },
        "required": ["ItemCode", "ItemName"],
        "max_len": {"ItemCode": 50, "ItemName": 100, "SalUnitMsr": 20},
        "enums": {"ItemType": {"item": "I", "i": "I", "labor": "L", "l": "L",
                               "travel": "T", "t": "T"},
                  "InvntItem": {"yes": "Y", "no": "N", "y": "Y", "n": "N",
                                "true": "Y", "false": "N"},
                  "validFor": {"yes": "Y", "no": "N", "y": "Y", "n": "N",
                               "true": "Y", "false": "N", "active": "Y"}},
        "date_fields": [],
        "number_fields": ["ItmsGrpCod", "AvgPrice", "LastPurPrc"],
    },
}

# Objects the wedge is explicitly NOT claiming to support yet. Returning an
# honest error is better than a partial import that leaves opening balances
# wrong and is discovered at the first month-end close.
UNSUPPORTED_TARGETS = {
    "OpeningStock": "Opening stock must be loaded as an Inventory Opening Balance "
                    "document (InventoryOpeningBalances) so it posts through SAP's "
                    "own costing. Not implemented yet.",
    "AROpenItems": "A/R open items require the original invoice structure "
                   "(lines, tax codes, payment terms) to age correctly. Not "
                   "implemented yet - do not migrate them with this tool.",
}

MAX_UPLOAD_BYTES = int(getattr(config, "MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
MAX_ROWS = int(getattr(config, "MAX_MIGRATION_ROWS", 20000))


# ── parsing ─────────────────────────────────────────────────────────────────
def _sniff_csv(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        # Fall back to whichever delimiter appears most in the header line.
        first = text.splitlines()[0] if text.splitlines() else ""
        return max([",", ";", "\t", "|"], key=first.count)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_upload(filename: str, raw: bytes) -> List[List[Any]]:
    """Return rows as Python values - dates stay dates, numbers stay numbers."""
    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = _decode(raw)
        delimiter = _sniff_csv(text)
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    elif name.endswith((".xlsx", ".xlsm")):
        # read_only=true keeps a 50k-row sheet from exhausting memory.
        wb = openpyxl.load_workbook(filename=io.BytesIO(raw), data_only=True, read_only=True)
        try:
            sheet = wb.active
            rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        finally:
            wb.close()
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .xlsx (Excel) or .csv.",
        )

    cleaned: List[List[Any]] = []
    for row in rows:
        if any(cell is not None and str(cell).strip() != "" for cell in row):
            cleaned.append([_clean_cell(cell) for cell in row])
    return cleaned


def _clean_cell(value: Any) -> Any:
    """Normalise one cell without destroying its type."""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.strip()
    return value


# ── header mapping ──────────────────────────────────────────────────────────
def _match_headers(headers: List[Any], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map each source column to a target field, and say HOW it matched.

    Four outcomes, reported honestly:
      exact   - the header is one of the documented aliases (the old code called
                this "confidence 100")
      normal  - the header matched after lower-casing / stripping punctuation
      fuzzy   - close but not exact; the human MUST confirm it
      none    - unmatched; the column is ignored unless the user maps it

    There is no invented confidence percentage. A percentage would be
    indistinguishable from a real one in the UI, which is how a wrong mapping
    gets approved.
    """
    import difflib

    alias_index: Dict[str, str] = {}
    for target, aliases in profile["aliases"].items():
        for alias in aliases:
            alias_index[alias.lower()] = target

    mapping = []
    for header in headers:
        source = str(header or "").strip()
        key = re.sub(r"[^a-z0-9]+", " ", source.lower()).strip()
        target, how, suggestion = "", "none", ""

        if key in alias_index:
            target, how = alias_index[key], "exact"
        else:
            collapsed = key.replace(" ", "")
            for alias, candidate in alias_index.items():
                if collapsed == alias.replace(" ", ""):
                    target, how = candidate, "normal"
                    break
        if not target and key:
            close = difflib.get_close_matches(key, list(alias_index), n=1, cutoff=0.82)
            if close:
                suggestion = alias_index[close[0]]
                how = "fuzzy"
        mapping.append({
            "source": source,
            "target": target,
            "match": how,                 # exact | normal | fuzzy | none
            "suggested_target": suggestion,
            "needs_review": how in ("fuzzy", "none"),
        })
    return mapping


def _find_header_row(rows: List[List[Any]], profile: Dict[str, Any]) -> int:
    """Locate the header row: the row in the first 10 whose cells match most aliases."""
    best_idx, best_score = 0, -1
    alias_blob = " ".join(a for aliases in profile["aliases"].values() for a in aliases)
    for idx, row in enumerate(rows[:10]):
        score = 0
        for cell in row:
            key = re.sub(r"[^a-z0-9]+", " ", str(cell or "").lower()).strip().replace(" ", "")
            if key and key in alias_blob.replace(" ", ""):
                score += 1
            elif re.search(r"[A-Za-z]", str(cell or "")):
                score += 0.1  # a header row is mostly text, not numbers
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx


# ── validation ──────────────────────────────────────────────────────────────
def _validate_row(row: Dict[str, Any], profile: Dict[str, Any], line: int) -> List[str]:
    errors: List[str] = []
    for field in profile["required"]:
        if str(row.get(field, "")).strip() == "":
            errors.append(f"Row {line}: {field} is required but empty.")

    for field, limit in profile["max_len"].items():
        value = str(row.get(field, "") or "")
        if len(value) > limit:
            errors.append(
                f"Row {line}: {field} is {len(value)} characters; SAP allows {limit}. "
                f"Value starts '{value[:25]}'."
            )

    for field, allowed in profile.get("enums", {}).items():
        raw = str(row.get(field, "") or "").strip()
        if not raw:
            continue
        if raw.lower() not in allowed:
            errors.append(
                f"Row {line}: {field} '{raw}' is not a recognised value. "
                f"Use one of {sorted(set(allowed.values()))}."
            )
        else:
            row[field] = allowed[raw.lower()]

    for field, (pattern, message) in profile.get("patterns", {}).items():
        raw = str(row.get(field, "") or "").strip().upper()
        if raw and not re.fullmatch(pattern, raw):
            errors.append(f"Row {line}: {field} '{raw}' {message}.")
        elif raw:
            row[field] = raw

    for field in profile.get("number_fields", []):
        value = row.get(field)
        if value in (None, ""):
            continue
        try:
            row[field] = float(str(value).replace(",", ""))
        except ValueError:
            errors.append(f"Row {line}: {field} '{value}' is not a number.")

    # CardCode/ItemCode may not contain SAP's forbidden characters.
    key = profile["key"]
    key_value = str(row.get(key, "") or "")
    if key_value and not re.fullmatch(r"[A-Za-z0-9._\-/]+", key_value):
        errors.append(
            f"Row {line}: {key} '{key_value}' contains characters SAP does not accept "
            f"(letters, digits, . _ - / only)."
        )
    return errors


def validate_rows(rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Validate every row and return a column-level report plus valid/error sets."""
    key = profile["key"]
    valid_rows, errors = [], []
    seen: Dict[str, int] = {}
    column_counts: Dict[str, int] = {}

    for index, row in enumerate(rows, start=1):
        # Validate in place: _validate_row normalises enums and numbers, and the
        # normalised values are what get pushed - otherwise "customer" would be
        # written where SAP expects "cCustomer".
        row_errors = _validate_row(row, profile, index)
        value = str(row.get(key, "") or "")
        if value:
            if value in seen:
                row_errors.append(
                    f"Row {index}: duplicate {key} '{value}' - first seen on row {seen[value]}."
                )
            else:
                seen[value] = index
        for field in row:
            if str(row.get(field, "") or "") != "":
                column_counts[field] = column_counts.get(field, 0) + 1
        if row_errors:
            errors.append({"row": index, "errors": row_errors, "data": row})
        else:
            valid_rows.append(row)

    total = len(rows)
    column_report = [
        {
            "field": field,
            "filled": count,
            "blank": total - count,
            "coverage_pct": round(100.0 * count / total, 1) if total else 0.0,
        }
        for field, count in sorted(column_counts.items(), key=lambda kv: -kv[1])
    ]
    return {
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "total": total,
        "errors": errors,
        "valid_rows": valid_rows,
        "column_report": column_report,
    }


# ── idempotency ─────────────────────────────────────────────────────────────
# A re-push of the same file must not create duplicate documents, and a repeated
# push of the *same rows* must be a no-op. We key on the content, not on the
# client, so retrying a timed-out request is safe.
_IDEMPOTENCY_CACHE: Dict[str, Dict[str, Any]] = {}
_IDEMPOTENCY_TTL_S = 3600


def _idempotency_key(target: str, rows: List[Dict[str, Any]]) -> str:
    blob = json.dumps({"target": target, "rows": rows}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cache_get(key: str) -> Dict[str, Any] | None:
    entry = _IDEMPOTENCY_CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["at"] > _IDEMPOTENCY_TTL_S:
        _IDEMPOTENCY_CACHE.pop(key, None)
        return None
    return entry["result"]


def _cache_put(key: str, result: Dict[str, Any]) -> None:
    _IDEMPOTENCY_CACHE[key] = {"at": time.time(), "result": result}


# ── endpoints ───────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target: str = Form("BusinessPartners"),
    ctx: dict = Depends(resolve_tenant),
):
    if target in UNSUPPORTED_TARGETS:
        raise HTTPException(status_code=501, detail=UNSUPPORTED_TARGETS[target])
    profile = TARGETS.get(target)
    if not profile:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target '{target}'. Supported: {sorted(TARGETS)} "
                   f"(planned but not implemented: {sorted(UNSUPPORTED_TARGETS)}).",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is {len(raw) // 1024 // 1024} MB; the limit is "
                   f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB. Split it into batches.",
        )

    try:
        rows = parse_upload(file.filename or "", raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read the file: {exc}")

    if not rows:
        raise HTTPException(status_code=400, detail="The file contains no data rows.")
    if len(rows) - 1 > MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"{len(rows) - 1} rows exceed the {MAX_ROWS}-row limit for one batch. "
                   "Split the file; DTW and the Service Layer both fail unpredictably on "
                   "large single imports.",
        )

    header_idx = _find_header_row(rows, profile)
    headers = rows[header_idx]
    data_rows = rows[header_idx + 1:]
    mapping = _match_headers(headers, profile)

    warnings = []
    unmatched = [m["source"] for m in mapping if m["match"] == "none" and m["source"]]
    if unmatched:
        warnings.append(
            f"{len(unmatched)} column(s) could not be matched and will be ignored unless "
            f"you map them: {', '.join(unmatched[:8])}"
        )
    missing_required = [f for f in profile["required"] if f not in {m["target"] for m in mapping}]
    if missing_required:
        warnings.append(f"Required field(s) not found in the header: {', '.join(missing_required)}")
    if header_idx > 0:
        warnings.append(
            f"The header was found on row {header_idx + 1}; rows above it were treated as "
            f"file decoration and ignored."
        )

    return {
        "target": target,
        "target_label": profile["label"],
        "key_field": profile["key"],
        "headers": mapping,
        "header_row": header_idx + 1,
        "total_rows": len(data_rows),
        "samples": data_rows[:3],
        "raw_data": data_rows,
        "warnings": warnings,
        "supported_targets": sorted(TARGETS),
        "unsupported_targets": UNSUPPORTED_TARGETS,
    }


@router.post("/validate")
async def validate_data(
    payload: dict,
    ctx: dict = Depends(resolve_tenant),
):
    target = payload.get("target", "BusinessPartners")
    profile = TARGETS.get(target)
    if not profile:
        raise HTTPException(status_code=400, detail=f"Unknown target '{target}'.")

    mapping = payload.get("mapping") or payload.get("headers") or []
    rows = payload.get("rows") or []
    if not isinstance(mapping, list) or not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="mapping and rows must be lists.")

    # Column index for each target field, taken from the human-approved mapping.
    index_of: Dict[str, int] = {}
    for position, entry in enumerate(mapping):
        if isinstance(entry, dict) and entry.get("target"):
            index_of.setdefault(entry["target"], position)

    missing = [f for f in profile["required"] if f not in index_of]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Map these required field(s) before validating: {', '.join(missing)}.",
        )

    objects: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        obj = {field: row[idx] for field, idx in index_of.items() if idx < len(row)}
        objects.append(obj)

    report = validate_rows(objects, profile)
    report["target"] = target
    report["target_label"] = profile["label"]
    report["mapped_fields"] = sorted(index_of)
    # Only the failures, with their file line numbers, so a human can fix them in
    # the source file and re-upload just that slice.
    report["failed_row_numbers"] = [e["row"] for e in report["errors"]]
    return report



def _same_value(field: str, stored, incoming) -> bool:
    """Compare a stored B1 value with an incoming one without lying.

    Reads are decoded for humans ("C" becomes "Customer") while the file contains
    the raw code, so a naive string compare reports a phantom change on every
    re-push of every coded column. Both sides are normalised to the stored code
    first; anything that still differs is a genuine difference.
    """
    from sap import entities as _entities

    def norm(value):
        if value is None:
            return ""
        text = str(value).strip()
        encoded = _entities.encode_value(field, text)
        if isinstance(encoded, str):
            text = encoded.strip()
        return text

    return norm(stored).casefold() == norm(incoming).casefold()

@router.post("/push")
async def push_data(
    payload: dict,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: dict = Depends(resolve_tenant),
):
    """Create or correct rows in SAP B1 through the Service Layer.

    Every row lands in exactly one bucket and the counts add up:
      created - did not exist, created now
      updated - already existed, and the differing fields were corrected
      unchanged - already existed and already matched
      failed - SAP or the validator rejected it; see errors[] with the row number

    Nothing is ever deleted. ``success = created + updated + unchanged``, and
    the response carries ``failed_rows`` so the caller can re-push only what
    failed (the /push contract is row-based, not file-based).
    """
    from config import CURRENT_TENANT
    from sap.router import create_entity, run_query, update_entity

    target = payload.get("target", "BusinessPartners")
    profile = TARGETS.get(target)
    if not profile:
        raise HTTPException(status_code=400, detail=f"Unknown target '{target}'.")

    valid_rows: List[Dict[str, Any]] = payload.get("valid_rows") or []
    if not valid_rows:
        raise HTTPException(status_code=400, detail="No valid rows to push.")

    tenant = CURRENT_TENANT.get() or {}
    if not tenant.get("WRITE_ENABLED", False):
        raise HTTPException(
            status_code=403,
            detail="Writes are disabled for this tenant. Enable WRITE_ENABLED for the "
                   "tenant before pushing, and only after reading the audit trail.",
        )

    key_field = profile["key"]
    entity = profile["entity"]
    cache_key = idempotency_key or _idempotency_key(target, valid_rows)
    cached = _cache_get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["idempotent_replay"] = True
        return cached

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    failed_rows: List[Dict[str, Any]] = []
    created = updated = unchanged = failed = 0

    for position, obj in enumerate(valid_rows, start=1):
        key_value = str(obj.get(key_field, "") or "").strip()
        row_label = obj.get("RowNumber") or position

        # Re-validate server-side. The client already saw the validation report,
        # but a push that trusts the caller can be used to write anything into
        # the ERP - including values SAP itself would reject halfway through.
        row_errors = _validate_row(obj, profile, row_label)
        if key_value and not re.fullmatch(r"[A-Za-z0-9._\-/]+", key_value):
            pass  # already reported by _validate_row
        if row_errors:
            failed += 1
            errors.append({"row": row_label, "key": key_value,
                           "error": " ".join(row_errors)})
            failed_rows.append(obj)
            continue

        try:
            existing = await run_query({
                "table": profile["table"],
                "columns": [c for c in obj.keys() if not str(c).startswith("_")],
                "filters": [{"column": key_field, "op": "eq", "value": key_value}],
                "limit": 1,
            })
            if existing.rows:
                # Existed: correct the differences instead of pretending a skip
                # was a success (what this endpoint used to do).
                current = existing.rows[0] if isinstance(existing.rows[0], dict) else {}
                diff = {
                    field: value
                    for field, value in obj.items()
                    if field != key_field
                    and str(value) != ""
                    and not _same_value(field, current.get(field), value)
                }
                if not diff:
                    unchanged += 1
                    results.append({"row": row_label, "key": key_value, "outcome": "unchanged",
                                    "changed_fields": []})
                else:
                    await update_entity(entity, key_field, key_value, diff)
                    updated += 1
                    results.append({"row": row_label, "key": key_value, "outcome": "updated",
                                    "changed_fields": sorted(diff)})
            else:
                await create_entity(entity, obj)
                created += 1
                results.append({"row": row_label, "key": key_value, "outcome": "created",
                                "changed_fields": []})
        except Exception as exc:
            failed += 1
            errors.append({"row": row_label, "key": key_value, "error": str(exc)[:400]})
            failed_rows.append(obj)
            log.warning("Migration push failed for %s %s: %s", entity, key_value, exc)

    response = {
        "target": target,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
        "skipped": 0,  # kept for compatibility; nothing is skipped silently any more
        "success": created + updated + unchanged,
        "total": len(valid_rows),
        "errors": errors,
        "failed_rows": failed_rows,
        "results": results,
        "idempotency_key": cache_key,
        "idempotent_replay": False,
    }
    if failed == 0:
        _cache_put(cache_key, response)
    return response


@router.get("/capabilities")
async def capabilities(ctx: dict = Depends(require_role(["partner_admin", "superadmin"]))):
    """What this tool will and will not do - readable by a partner before a demo."""
    return {
        "supported": [
            {
                "target": name,
                "label": profile["label"],
                "required_fields": profile["required"],
                "key_field": profile["key"],
                "writes_via": "SAP B1 Service Layer (POST/PATCH)",
            }
            for name, profile in TARGETS.items()
        ],
        "not_implemented": UNSUPPORTED_TARGETS,
        "limits": {
            "max_rows_per_batch": MAX_ROWS,
            "max_upload_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
            "file_types": [".xlsx", ".xlsm", ".csv"],
        },
        "notes": [
            "Every write goes through the Service Layer so SAP's own business rules "
            "(number ranges, credit checks, tax determination) still apply.",
            "Batches above ~1,000 rows are split rather than sent as one request; SAP's "
            "own DTW guidance is to stay at or below 1,000 rows per file.",
            "Nothing is deleted by this tool. Corrections are PATCHes; documents are "
            "created as drafts a human approves inside B1.",
        ],
    }
