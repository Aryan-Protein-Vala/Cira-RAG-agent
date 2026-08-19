"""Backend selection + the single data API the rest of CIRA talks to.

Selection order for CIRA_DATA_SOURCE=auto:
    1. SAP HANA (direct SQL — full depth: every table, view, join, aggregate)
    2. SAP B1 Service Layer (OData — entity level only)
    3. Offline simulator (clearly flagged as simulated)

A failed primary is retried every CIRA_BACKEND_RETRY_S seconds, so the moment
the RDP/VPN route to HANA comes up the app switches back to live data without
a restart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

import config
from . import entities
from .base import DataBackend
from .hana_backend import HanaBackend
from .query_spec import Aggregate, ColumnResolver, QuerySpec, build_select, spec_from_payload
from .serialize import rows_to_jsonable
from .service_layer import ServiceLayerBackend
from .sim_backend import SimulatorBackend
from .sql_guard import apply_row_limit, ensure_read_only
from .types_ import QueryResult, SapDataError, SapUnavailableError

log = logging.getLogger("cira.sap")

RETRY_SECONDS = int(os.getenv("CIRA_BACKEND_RETRY_S", "120"))


class _Selector:
    def __init__(self) -> None:
        self._active_by_tenant: dict[str, DataBackend] = {}
        self._active_at_by_tenant: dict[str, float] = {}
        self._last_error: str = ""
        self._probe_log: list[dict] = []
        self._refreshing = False
        self._lock = threading.Lock()

    def _get_tenant_id(self) -> str:
        tenant = config.CURRENT_TENANT.get() or {}
        return tenant.get("HANA_SCHEMA", "default")

    # ── construction helpers ────────────────────────────────────────────────
    @staticmethod
    def _make(kind: str) -> DataBackend:
        if kind == "hana":
            return HanaBackend()
        if kind in ("service", "service_layer", "odata"):
            return ServiceLayerBackend()
        return SimulatorBackend()

    def _candidates(self) -> list[str]:
        mode = (config.DATA_SOURCE or "auto").lower()
        if mode in ("hana", "service", "service_layer", "odata", "simulator", "sim", "mock"):
            return [{"sim": "simulator", "mock": "simulator"}.get(mode, mode)]
        order = []
        tenant = config.CURRENT_TENANT.get() or {}
        if tenant.get("HANA_PASSWORD", config.HANA_PASSWORD):
            order.append("hana")
        if tenant.get("SAP_B1_PASSWORD", config.SAP_B1_PASSWORD):
            order.append("service")
        order.append("simulator")
        return order

    # ── selection ────────────────────────────────────────────────────────────
    def get(self, force: bool = False) -> DataBackend:
        now = time.time()
        tenant_id = self._get_tenant_id()
        active = self._active_by_tenant.get(tenant_id)
        active_at = self._active_at_by_tenant.get(tenant_id, 0.0)

        if active is not None and not force:
            if active.simulated and now - active_at >= RETRY_SECONDS:
                self._schedule_refresh(tenant_id)
            return active
        return self._select(tenant_id, force)

    def _schedule_refresh(self, tenant_id: str) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
            self._active_at_by_tenant[tenant_id] = time.time()

        # Save the current context so the background thread connects to the right DB
        current_ctx = config.CURRENT_TENANT.get()
        
        def worker():
            try:
                # Restore context in thread
                config.CURRENT_TENANT.set(current_ctx)
                self._select(tenant_id, force=True)
            except Exception as exc:  # pragma: no cover
                log.debug("background backend refresh failed: %s", exc)
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=worker, name=f"cira-sap-refresh-{tenant_id}", daemon=True).start()

    def _select(self, tenant_id: str, force: bool = False) -> DataBackend:
        now = time.time()
        probes: list[dict] = []
        chosen: DataBackend | None = None
        for kind in self._candidates():
            try:
                backend = self._make(kind)
            except Exception as exc:  # pragma: no cover
                probes.append({"backend": kind, "ok": False, "error": str(exc)})
                continue
            probe = backend.ping()
            probe["candidate"] = kind
            probes.append(probe)
            if probe.get("ok"):
                chosen = backend
                break
            self._last_error = probe.get("error", "")
            log.warning("SAP backend %s unavailable for %s: %s", kind, tenant_id, probe.get("error"))

        if chosen is None:
            chosen = SimulatorBackend()
            chosen.ping()

        existing = self._active_by_tenant.get(tenant_id)
        if existing is not None and existing is not chosen:
            try:
                existing.close()
            except Exception:
                pass

        self._active_by_tenant[tenant_id] = chosen
        self._active_at_by_tenant[tenant_id] = now
        self._probe_log = probes
        log.info("Active SAP backend for %s: %s (schema=%s)", tenant_id, chosen.name, chosen.schema)
        return chosen

    @property
    def probes(self) -> list[dict]:
        return self._probe_log

    @property
    def last_error(self) -> str:
        return self._last_error


_selector = _Selector()


def get_active_backend(force: bool = False) -> DataBackend:
    return _selector.get(force=force)


# ─────────────────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────────────────
def _list_tables_sync(pattern: str = "", limit: int = 300) -> dict:
    backend = get_active_backend()
    tables = backend.list_tables(pattern=pattern, limit=limit)
    return {
        "backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "count": len(tables),
        "tables": [t.as_dict() for t in tables],
    }


def _search_schema_sync(keyword: str, limit: int = 40) -> dict:
    backend = get_active_backend()
    keyword = (keyword or "").strip()
    result: dict[str, Any] = {
        "backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "keyword": keyword,
        "tables": [],
        "columns": [],
        "suggested_entities": [],
    }
    if not keyword:
        result["tables"] = [t.as_dict() for t in backend.list_tables(limit=limit)]
        return result

    # 1. tables whose name/description matches
    tables = backend.list_tables(pattern=keyword, limit=limit)
    result["tables"] = [t.as_dict() for t in tables]

    # 2. friendly alias hits (e.g. "customer" -> OCRD)
    alias_hits: list[dict] = []
    needle = keyword.lower()
    for alias, table in entities.TABLE_ALIASES.items():
        if needle in alias:
            alias_hits.append({"alias": alias, "table": table,
                               "description": entities.describe_table_name(table)})
    seen = set()
    deduped = []
    for hit in alias_hits:
        if hit["table"] in seen:
            continue
        seen.add(hit["table"])
        deduped.append(hit)
    result["suggested_entities"] = deduped[:12]

    # 3. columns anywhere in the schema
    result["columns"] = _search_columns(backend, keyword, limit)
    return result


def _search_columns(backend: DataBackend, keyword: str, limit: int) -> list[dict]:
    like = f"%{keyword.upper()}%"
    if isinstance(backend, HanaBackend):
        try:
            rows = backend._fetch_dicts(  # noqa: SLF001 - internal helper by design
                'SELECT TOP ' + str(int(limit)) + ' TABLE_NAME AS "table", '
                'COLUMN_NAME AS "column", DATA_TYPE_NAME AS "type", COMMENTS AS "description" '
                "FROM SYS.TABLE_COLUMNS "
                "WHERE SCHEMA_NAME = ? AND (UPPER(COLUMN_NAME) LIKE ? OR UPPER(COMMENTS) LIKE ?) "
                "ORDER BY TABLE_NAME, POSITION",
                [backend.schema, like, like],
            )
            return rows
        except Exception as exc:
            log.debug("column search failed: %s", exc)
            return []

    out: list[dict] = []
    for table in backend.list_tables(limit=500):
        for col in backend.get_columns(table.name):
            if keyword.lower() in col.name.lower() or keyword.lower() in (col.description or "").lower():
                out.append({
                    "table": table.name,
                    "column": col.name,
                    "type": col.data_type,
                    "description": col.description,
                })
                if len(out) >= limit:
                    return out
    return out


def _resolve_table(backend: DataBackend, name: str) -> str:
    """Map a friendly entity name to a real table that exists on the backend."""
    physical = entities.normalise_table_name(name)
    tables = {t.name.upper(): t.name for t in backend.list_tables(limit=100000)}
    if not tables:  # catalog unavailable — trust the caller
        return physical
    if physical.upper() in tables:
        return tables[physical.upper()]
    raw = (name or "").strip().upper()
    if raw in tables:
        return tables[raw]
    # last resort: fuzzy match on name/description
    candidates = [t for t in tables.values() if raw and raw in t.upper()]
    if len(candidates) == 1:
        return candidates[0]
    hints = ", ".join(sorted(candidates)[:8]) or ", ".join(sorted(tables)[:8])
    raise SapDataError(
        f"Table or entity '{name}' does not exist in schema {backend.schema}. "
        f"Use the schema search tool to find the right name. Close matches: {hints}"
    )


def _describe_table_sync(table: str, sample_rows: int = 3) -> dict:
    backend = get_active_backend()
    physical = _resolve_table(backend, table)
    cols = backend.get_columns(physical)
    info = {
        "backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "table": physical,
        "description": entities.describe_table_name(physical),
        "row_count": backend.row_count(physical),
        "column_count": len(cols),
        "columns": [c.as_dict() for c in cols],
        "semantics": entities.semantics_for(physical),
    }
    if sample_rows > 0 and cols:
        try:
            result = _run_query_sync({"table": physical, "limit": sample_rows})
            info["sample"] = result.rows
        except Exception as exc:
            info["sample_error"] = str(exc)
    return info


# ─────────────────────────────────────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────────────────────────────────────
def _finalise(rows: list[dict], decode: bool = True) -> list[dict]:
    return entities.decode_rows(rows) if decode else rows


def _run_query_sync(payload: dict) -> QueryResult:
    started = time.time()
    backend = get_active_backend()
    spec: QuerySpec = spec_from_payload(payload)
    spec.limit = max(1, min(int(spec.limit or config.DEFAULT_ROW_LIMIT), config.MAX_ROW_LIMIT))
    spec.table = _resolve_table(backend, spec.table)

    columns = backend.get_columns(spec.table)
    if not columns:
        raise SapDataError(
            f"Could not read the column list for {spec.table} from {backend.name}."
        )
    resolver = ColumnResolver(columns)

    if isinstance(backend, ServiceLayerBackend):
        return _run_query_service_layer(backend, spec, resolver, started)

    sql, params = build_select(
        spec, resolver, backend.dialect, schema=backend.schema if backend.dialect == "hana" else ""
    )
    col_names, raw_rows = backend.execute(sql, params)
    rows = _finalise(rows_to_jsonable(col_names, raw_rows))

    total = None
    if len(rows) >= spec.limit:
        total = _count_matching(backend, spec, resolver)

    return QueryResult(
        ok=True,
        source=f"{backend.name} · {backend.schema}",
        backend=backend.name,
        entity=payload.get("entity") or spec.table,
        table=spec.table,
        columns=col_names,
        rows=rows,
        row_count=len(rows),
        total_available=total,
        truncated=bool(total and total > len(rows)),
        sql=sql,
        simulated=backend.simulated,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def _count_matching(backend: DataBackend, spec: QuerySpec, resolver: ColumnResolver) -> int | None:
    """How many rows would the same filter return without the row cap?"""
    try:
        count_spec = QuerySpec(
            table=spec.table,
            filters=spec.filters,
            search_text=spec.search_text,
            search_columns=spec.search_columns,
            date_column=spec.date_column,
            date_from=spec.date_from,
            date_to=spec.date_to,
            year=spec.year,
            aggregates=[Aggregate("count", "*", "Count")],
            limit=1,
        )
        sql, params = build_select(
            count_spec, resolver, backend.dialect,
            schema=backend.schema if backend.dialect == "hana" else "",
        )
        cols, rows = backend.execute(sql, params)
        if rows:
            value = rows[0][0]
            return int(value) if value is not None else None
    except Exception as exc:
        log.debug("count query failed: %s", exc)
    return None


def _run_query_service_layer(
    backend: ServiceLayerBackend, spec: QuerySpec, resolver: ColumnResolver, started: float
) -> QueryResult:
    filters = []
    for f in spec.filters:
        value = entities.encode_value(f.column, f.value if f.value is not None else f.values)
        filters.append((f.column, f.op, value))
    if spec.year:
        filters.append(("DocDate", "gte", f"{spec.year}-01-01"))
        filters.append(("DocDate", "lte", f"{spec.year}-12-31"))
    if spec.date_from:
        filters.append((spec.date_column or "DocDate", "gte", spec.date_from))
    if spec.date_to:
        filters.append((spec.date_column or "DocDate", "lte", spec.date_to))

    select = spec.columns or None
    order = [(o.column, o.direction) for o in spec.order_by if o.column]
    columns, rows = backend.fetch_entity(
        spec.table, select=select, filters=filters, order_by=order, limit=spec.limit
    )
    rows = _finalise([{k: v for k, v in row.items()} for row in rows])

    warnings = []
    if spec.group_by or spec.aggregates:
        rows, columns = _aggregate_in_python(rows, spec)
        warnings.append(
            "Aggregated in the application because the Service Layer cannot GROUP BY; "
            "results cover the first "
            f"{spec.limit} rows only. Enable HANA SQL access for exact totals."
        )

    return QueryResult(
        ok=True,
        source=f"{backend.name} · {backend.company}",
        backend=backend.name,
        entity=spec.table,
        table=spec.table,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        sql="",
        simulated=False,
        elapsed_ms=int((time.time() - started) * 1000),
        warnings=warnings,
    )


def _aggregate_in_python(rows: list[dict], spec: QuerySpec) -> tuple[list[dict], list[str]]:
    from collections import defaultdict

    keys = spec.group_by or []
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[tuple(row.get(k) for k in keys)].append(row)

    out = []
    for key, group in buckets.items():
        rec = {k: v for k, v in zip(keys, key)}
        if not spec.aggregates:
            rec["Count"] = len(group)
        for agg in spec.aggregates:
            values = [r.get(agg.column) for r in group]
            numeric = [v for v in values if isinstance(v, (int, float))]
            alias = agg.alias or f"{agg.func.title()}_{agg.column}"
            if agg.func == "count":
                rec[alias] = len(group)
            elif agg.func == "sum":
                rec[alias] = round(sum(numeric), 2)
            elif agg.func == "avg":
                rec[alias] = round(sum(numeric) / len(numeric), 2) if numeric else None
            elif agg.func == "min":
                rec[alias] = min(numeric) if numeric else None
            elif agg.func == "max":
                rec[alias] = max(numeric) if numeric else None
            elif agg.func == "count_distinct":
                rec[alias] = len({str(v) for v in values})
        out.append(rec)

    measure = None
    if out:
        measure = next((k for k in out[0] if k not in keys), None)
    if measure:
        out.sort(key=lambda r: (r.get(measure) is None, r.get(measure)), reverse=True)
    out = out[: spec.limit]
    return out, (list(out[0].keys()) if out else keys)


def _run_sql_sync(sql: str, limit: int | None = None) -> QueryResult:
    started = time.time()
    backend = get_active_backend()
    statement = ensure_read_only(sql)
    row_cap = max(1, min(int(limit or config.DEFAULT_ROW_LIMIT), config.MAX_ROW_LIMIT))
    if backend.dialect == "odata":
        raise SapDataError(
            "Raw SQL needs the HANA connection; only entity queries are available "
            "through the Service Layer right now."
        )
    guarded = apply_row_limit(statement, row_cap, backend.dialect)
    if backend.dialect == "hana" and backend.schema:
        guarded = _qualify_bare_tables(guarded, backend)
    col_names, raw_rows = backend.execute(guarded, [])
    rows = _finalise(rows_to_jsonable(col_names, raw_rows))
    return QueryResult(
        ok=True,
        source=f"{backend.name} · {backend.schema} (SQL)",
        backend=backend.name,
        entity="SQL",
        table="",
        columns=col_names,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= row_cap,
        sql=guarded,
        simulated=backend.simulated,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def _qualify_bare_tables(sql: str, backend: DataBackend) -> str:
    """Prefix unqualified SAP B1 table names with the company schema."""
    import re

    known = {t.name.upper() for t in backend.list_tables(limit=100000)}
    if not known:
        return sql

    def repl(match: re.Match) -> str:
        keyword, spacing, name = match.group(1), match.group(2), match.group(3)
        bare = name.strip('"').upper()
        if bare in known and "." not in name:
            return f'{keyword}{spacing}"{backend.schema}"."{bare}"'
        return match.group(0)

    return re.sub(
        r'\b(FROM|JOIN)(\s+)("?[A-Za-z_@][\w@$#]*"?)',
        repl,
        sql,
        flags=re.IGNORECASE,
    )


def _health_sync() -> dict:
    backend = get_active_backend()
    probe = backend.ping()
    tables = []
    try:
        tables = backend.list_tables(limit=100000)
    except Exception as exc:
        probe.setdefault("warnings", []).append(f"catalog unavailable: {exc}")
    return {
        "active_backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "tables_visible": len(tables),
        "probe": probe,
        "attempts": _selector.probes,
        "config": config.summary(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Async facade (all DB work runs in a worker thread so the event loop is free)
# ─────────────────────────────────────────────────────────────────────────────
async def list_tables(pattern: str = "", limit: int = 300) -> dict:
    return await asyncio.to_thread(_list_tables_sync, pattern, limit)


async def search_schema(keyword: str, limit: int = 40) -> dict:
    return await asyncio.to_thread(_search_schema_sync, keyword, limit)


async def describe_table(table: str, sample_rows: int = 3) -> dict:
    return await asyncio.to_thread(_describe_table_sync, table, sample_rows)


async def run_query(payload: dict) -> QueryResult:
    return await asyncio.to_thread(_run_query_sync, payload)


async def run_sql(sql: str, limit: int | None = None) -> QueryResult:
    return await asyncio.to_thread(_run_sql_sync, sql, limit)


async def health() -> dict:
    return await asyncio.to_thread(_health_sync)


__all__ = [
    "SapDataError",
    "SapUnavailableError",
    "describe_table",
    "get_active_backend",
    "health",
    "list_tables",
    "run_query",
    "run_sql",
    "search_schema",
]
