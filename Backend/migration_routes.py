from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
import openpyxl
from io import BytesIO
import re
from typing import List, Dict, Any
from admin_routes import require_role

router = APIRouter(prefix="/admin/migration", tags=["Migration"])

import difflib

# Very simple fuzzy mapping alias dictionary
# Target field -> Common aliases
BP_ALIASES = {
    "CardCode": ["customer code", "vendor code", "bp code", "id", "cardcode", "code", "customer id", "vendor id"],
    "CardName": ["customer name", "vendor name", "bp name", "name", "cardname", "khata", "ग्राहक नाम", "company name"],
    "CardType": ["type", "bp type", "cardtype", "role", "customer/vendor", "category"],
    "Phone1": ["phone", "mobile", "contact number", "phone1", "tel", "telephone", "contact"],
    "E_Mail": ["email", "e-mail", "email id", "mail", "email address"],
    "Cellular": ["cellular", "mobile 2", "alt phone"],
    "VatIdUnCmp": ["gstin", "gst", "tax id", "pan", "vat", "tax number"]
}

def _fuzzy_match_header(header: str) -> str:
    h = header.lower().strip()
    
    # 1. Exact alias match
    for target, aliases in BP_ALIASES.items():
        if h in [a.lower() for a in aliases]:
            return target
            
    # 2. Fuzzy alias match using difflib
    all_aliases = []
    alias_to_target = {}
    for target, aliases in BP_ALIASES.items():
        for a in aliases:
            a_lower = a.lower()
            all_aliases.append(a_lower)
            alias_to_target[a_lower] = target
            
    matches = difflib.get_close_matches(h, all_aliases, n=1, cutoff=0.75)
    if matches:
        return alias_to_target[matches[0]]
        
    return header # No match

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    ctx: dict = Depends(require_role(["partner_admin", "superadmin"]))
):
    if not file.filename.endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .csv files are supported.")
        
    contents = await file.read()
    
    # Process Excel
    try:
        wb = openpyxl.load_workbook(filename=BytesIO(contents), data_only=True)
        sheet = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")
        
    # Extract rows (dropping fully empty rows)
    raw_rows = []
    for row in sheet.iter_rows(values_only=True):
        if any(cell is not None and str(cell).strip() != "" for cell in row):
            raw_rows.append([str(cell).strip() if cell is not None else "" for cell in row])
            
    if not raw_rows:
        raise HTTPException(status_code=400, detail="The file is empty or contains no data.")
        
    # Auto-locate header row (row with most text that matches our aliases)
    best_header_idx = 0
    best_match_count = -1
    
    for i, row in enumerate(raw_rows[:10]): # Search first 10 rows
        matches = sum(1 for cell in row if _fuzzy_match_header(cell) in BP_ALIASES)
        if matches > best_match_count:
            best_match_count = matches
            best_header_idx = i
            
    headers = raw_rows[best_header_idx]
    data_rows = raw_rows[best_header_idx+1:]
    
    # Perform mapping
    mapping = []
    for h in headers:
        mapped_to = _fuzzy_match_header(h) if h else ""
        confidence = 100 if mapped_to in BP_ALIASES else 0
        mapping.append({
            "source": h,
            "target": mapped_to if confidence > 0 else "",
            "confidence": confidence
        })
        
    # Return 3 samples
    samples = data_rows[:3] if len(data_rows) >= 3 else data_rows
    
    return {
        "headers": mapping,
        "total_rows": len(data_rows),
        "samples": samples,
        "raw_data": data_rows # Send all back to client for now
    }

@router.post("/validate")
async def validate_data(
    payload: dict,
    ctx: dict = Depends(require_role(["partner_admin", "superadmin"]))
):
    # Payload expects: {"mapping": [{"target": "CardCode", ...}], "rows": [["C001", "Acme", ...]]}
    mapping = payload.get("mapping", [])
    rows = payload.get("rows", [])
    
    target_idx_map = {m["target"]: i for i, m in enumerate(mapping) if m.get("target")}
    
    errors = []
    valid_rows = []
    
    seen_cardcodes = set()
    
    for r_idx, row in enumerate(rows):
        row_errors = []
        
        # Build the final object
        obj = {}
        for target, idx in target_idx_map.items():
            if idx < len(row):
                obj[target] = row[idx]
                
        # CardCode Validation
        card_code = obj.get("CardCode", "")
        if not card_code:
            row_errors.append("CardCode is required.")
        elif card_code in seen_cardcodes:
            row_errors.append(f"Duplicate CardCode '{card_code}' in file.")
        else:
            seen_cardcodes.add(card_code)
            
        # CardType Validation
        card_type = obj.get("CardType", "").upper()
        if card_type and card_type not in ["C", "S", "L", "CUSTOMER", "VENDOR", "LEAD"]:
            row_errors.append(f"Invalid CardType '{card_type}'. Must be C, S, or L.")
            
        # GSTIN Validation (basic 15 char check)
        gstin = obj.get("VatIdUnCmp", "")
        if gstin and len(gstin) != 15:
            row_errors.append(f"GSTIN '{gstin}' should be exactly 15 characters.")
            
        if row_errors:
            errors.append({"row": r_idx + 1, "errors": row_errors, "data": obj})
        else:
            # Clean up obj for push
            if card_type in ["CUSTOMER", "C"]: obj["CardType"] = "C"
            elif card_type in ["VENDOR", "S"]: obj["CardType"] = "S"
            elif card_type in ["LEAD", "L"]: obj["CardType"] = "L"
            elif not card_type: obj["CardType"] = "C" # Default
            
            valid_rows.append(obj)
            
    return {
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "errors": errors,
        "valid_rows": valid_rows
    }

@router.post("/push")
async def push_data(
    payload: dict,
    ctx: dict = Depends(require_role(["partner_admin", "superadmin"]))
):
    from sap.router import create_entity, run_query
    from config import CURRENT_TENANT
    
    valid_rows = payload.get("valid_rows", [])
    if not valid_rows:
        raise HTTPException(status_code=400, detail="No valid rows to push.")
        
    results = {"success": 0, "failed": 0, "errors": []}
    
    for obj in valid_rows:
        try:
            # 1. Check if it exists (idempotent GET)
            # In a real scenario, we use SAP endpoint /BusinessPartners('CardCode')
            # Here we mock by doing a query
            exists = await run_query({"table": "OCRD", "filters": [{"column": "CardCode", "op": "eq", "value": obj["CardCode"]}]})
            if exists.rows:
                # Exists. We would PATCH. For MVP, just skip or mock update.
                results["success"] += 1
                continue
                
            # 2. POST
            await create_entity("BusinessPartners", obj)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"cardcode": obj.get("CardCode", "Unknown"), "error": str(e)})
            
    return results
