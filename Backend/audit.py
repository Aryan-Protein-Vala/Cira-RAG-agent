import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any
import config

log = logging.getLogger("cira.audit")

AUDIT_DIR = config.DATA_DIR / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
_file_lock = threading.Lock()

SENSITIVE_KEYS = {"password", "secret", "token", "sap_db_password", "sap_sl_password", "api_key", "llm_api_key"}

def _redact(obj: Any) -> Any:
    """Recursively redacts sensitive keys from audit logs."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = _redact(v)
        return cleaned
    elif isinstance(obj, list):
        return [_redact(item) for item in obj]
    return obj


def audit_log(action: str, payload: dict = None, status: str = "success", error: str = None):
    """
    Thread-safe, append-only JSONL audit log per tenant.
    Redacts secrets and protects against directory traversal.
    """
    try:
        tenant_config = config.CURRENT_TENANT.get() or {}
        raw_tenant_id = (
            tenant_config.get("SAP_B1_COMPANY_DB")
            or tenant_config.get("HANA_SCHEMA")
            or config.SAP_B1_COMPANY_DB
            or "default_tenant"
        )
        
        # Sanitize against path traversal attacks and constrain length
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(raw_tenant_id).strip())
        tenant_id = sanitized[:64] if sanitized else "unknown_tenant"
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "action": action,
            "status": status,
            "payload": _redact(payload) if payload else None,
            "error": str(error) if error else None,
        }
        
        line = json.dumps(entry, default=str) + "\n"
        log_file = AUDIT_DIR / f"{tenant_id}.jsonl"

        with _file_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
                
    except Exception as e:
        log.error("Failed to write audit log: %s", e)
