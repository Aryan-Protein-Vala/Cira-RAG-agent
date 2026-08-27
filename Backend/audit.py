"""Append-only audit trail for everything CIRA does to the ERP.

A system that can run raw SQL against a production company database *and* create
records in it has to be able to answer "who saw what, and who wrote what" the
next morning. This is a JSONL file under Backend/data/ (rotate or ship it with
your log collector); writes are best-effort and must never break a request.

Events recorded:
  login / login_failed      who signed in (and from which company DB)
  sap_sql                   the exact statement sent to HANA/MSSQL + row count
  sap_query                 the structured query intent (table + filter summary)
  sap_write                 the entity, payload keys and SAP's response id
  upload / transcribe       attachment metadata (never the content)
  config_error              refused actions (closed write path, foreign tenant…)
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
from pathlib import Path

import config

log = logging.getLogger("cira.audit")

# Set per request so tool code deep in the call stack can attribute its queries.
# None (not {}) — a mutable default would be shared by every request.
REQUEST_CONTEXT: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "CIRA_AUDIT_CONTEXT", default=None
)

_lock = threading.Lock()


def set_context(**fields) -> None:
    merged = dict(REQUEST_CONTEXT.get() or {})
    merged.update({k: v for k, v in fields.items() if v is not None})
    REQUEST_CONTEXT.set(merged)


def event(action: str, **fields) -> None:
    """Record one audit line. Never raises."""
    if not config.AUDIT_ENABLED:
        return
    try:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "action": action}
        record.update(REQUEST_CONTEXT.get() or {})
        for key, value in fields.items():
            record[key] = _trim(value)
        path = Path(config.AUDIT_LOG_PATH)
        line = json.dumps(record, default=str, ensure_ascii=False)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if path.exists() and path.stat().st_size > config.AUDIT_MAX_BYTES:
                    path.replace(path.with_suffix(f".{int(time.time())}.jsonl"))
            except OSError:
                pass
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception as exc:  # pragma: no cover - auditing must not break requests
        log.debug("audit write failed: %s", exc)


def _trim(value):
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "…[truncated]"
    if isinstance(value, (list, tuple, set)):
        return [_trim(v) for v in list(value)[:100]]
    if isinstance(value, dict):
        return {str(k): _trim(v) for k, v in list(value.items())[:100]}
    return value
