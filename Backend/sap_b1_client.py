"""Backwards-compatible shim for the pre-2.0 SAP client.

The real implementation now lives in the `sap` package:

    from sap import router as sap
    await sap.run_query({"table": "OINV", "filters": [...]})
    await sap.run_sql("SELECT ...")
    await sap.search_schema("warehouse")

This module keeps the two symbols the old code exported so any private script
that still imports them keeps working.
"""

from __future__ import annotations

import warnings

import config
from sap import router as _router
from sap.types_ import SapDataError

SAP_B1_COMPANY_DB = config.HANA_SCHEMA


async def execute_b1_query(entity: str, filters: dict | None = None,
                           select_fields: list | None = None, top: int = 500) -> dict:
    """Deprecated: use `sap.router.run_query` (structured spec) instead."""
    warnings.warn(
        "execute_b1_query() is deprecated; use sap.router.run_query()",
        DeprecationWarning,
        stacklevel=2,
    )
    payload = {
        "table": entity,
        "columns": select_fields or [],
        "filters": [{"column": k, "op": "eq", "value": v} for k, v in (filters or {}).items()],
        "limit": top,
    }
    try:
        result = await _router.run_query(payload)
        return result.as_dict()
    except SapDataError as exc:
        return {"ok": False, "entity": entity, "data": [], "error": str(exc)}


__all__ = ["SAP_B1_COMPANY_DB", "execute_b1_query"]
