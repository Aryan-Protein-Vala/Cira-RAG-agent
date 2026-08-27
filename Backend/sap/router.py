"""Backend selection + the single data API the rest of CIRA talks to.

Selection is explicit, never inferred from "did a password happen to be set":

* `CIRA_DATA_SOURCE=hana`     -> HANA only, fail loudly if it is unreachable
* `CIRA_DATA_SOURCE=auto`     -> enabled sources in CIRA_DATA_SOURCE_ORDER
                                 (default: hana, service, mssql, simulator)
* each candidate must be fully configured (config.enabled_sources)

A dead backend is *retired*, not closed under the feet of the threads using it,
and a query that fails with a connectivity error fails over to the next enabled
source instead of erroring until the process restarts.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import config

from . import entities
from .base import DataBackend
from .query_spec import (
    Aggregate,
    ColumnResolver,
    QuerySpec,
    build_select,
    spec_from_payload,
)
from .serialize import rows_to_jsonable
from .sql_guard import apply_row_limit, enforce_scope, ensure_read_only
from .types_ import QueryResult, SapDataError, SapUnavailableError

log = logging.getLogger("cira.sap")

T = TypeVar("T")

_KNOWN_KINDS = {"hana", "service", "service_layer", "odata", "mssql", "simulator", "sim", "mock"}
_CANONICAL = {
    "service_layer": "service",
    "odata": "service",
    "sim": "simulator",
    "mock": "simulator",
}


class BackendUnavailable(RuntimeError):
    """No configured backend could answer the query."""


def _make(kind: str) -> DataBackend:
    """Instantiate a backend. Raises ConfigError when it is not configured."""
    if kind == "hana":
        from .hana_backend import HanaBackend

        return HanaBackend()
    if kind == "mssql":
        from .mssql_backend import MssqlBackend

        return MssqlBackend()
    if kind == "service":
        from .service_layer import ServiceLayerBackend

        return ServiceLayerBackend()
    from .sim_backend import SimulatorBackend

    return SimulatorBackend()


def candidate_kinds(tenant: dict | None = None) -> list[str]:
    """Backend kinds to try, honouring CIRA_DATA_SOURCE (explicit mode = exactly one)."""
    mode = (config.DATA_SOURCE or "auto").lower()
    if mode not in {"auto", ""}:
        kind = _CANONICAL.get(mode, mode)
        if kind not in _KNOWN_KINDS:
            raise config.ConfigError(f"CIRA_DATA_SOURCE={mode!r} is not a known source")
        return [kind]
    return config.enabled_sources(tenant)


class _Selector:
    """Per-tenant backend selection with a lock, a health cache and failover."""

    def __init__(self) -> None:
        # One reentrant lock guards every mutation of the maps below. The previous
        # implementation locked only its refresh flag while _select() swapped and
        # *closed* backends, so concurrent requests could run queries on a pool
        # that another thread had just closed.
        self._lock = threading.RLock()
        self._active: dict[str, DataBackend] = {}
        self._active_at: dict[str, float] = {}
        self._unhealthy_until: dict[str, float] = {}
        self._refreshing: set[str] = set()
        self._probe_log: list[dict] = []
        self._last_error = ""
        self._retiring: set[int] = set()

    # ── tenant keying ────────────────────────────────────────────────────────
    @staticmethod
    def _tenant() -> dict | None:
        return config.CURRENT_TENANT.get()

    @classmethod
    def _tenant_id(cls) -> str:
        return config.tenant_id_of(cls._tenant())

    # ── selection ─────────────────────────────────────────────────────────────
    def get(self, force: bool = False) -> DataBackend:
        tenant_id = self._tenant_id()
        now = time.time()
        with self._lock:
            active = self._active.get(tenant_id)
            stale_live = (
                active is not None
                and not active.simulated
                and now >= self._unhealthy_until.get(tenant_id, 0.0)
                and self._needs_reprobe(tenant_id, now)
            )
            if active is not None and not force and not stale_live:
                return active
            if active is not None and not force:
                # Background refresh: simulated or unhealthy backends are retried,
                # but the caller keeps working on what we have.
                self._schedule_refresh(tenant_id)
                return active
        return self._select(tenant_id)

    def _needs_reprobe(self, tenant_id: str, now: float) -> bool:
        return now - self._active_at.get(tenant_id, 0.0) >= config.HEALTH_CACHE_TTL_S

    def _schedule_refresh(self, tenant_id: str) -> None:
        with self._lock:
            if tenant_id in self._refreshing:
                return
            self._refreshing.add(tenant_id)
            self._active_at[tenant_id] = time.time()

        # contextvars are *not* inherited by bare threads: copy the tenant into it
        # explicitly so the background probe connects to the right company DB.
        tenant = self._tenant()

        def worker() -> None:
            token = config.CURRENT_TENANT.set(tenant)
            try:
                self._select(tenant_id, probe=True)
            except Exception as exc:  # pragma: no cover
                log.debug("background backend refresh failed: %s", exc)
            finally:
                config.CURRENT_TENANT.reset(token)
                with self._lock:
                    self._refreshing.discard(tenant_id)

        threading.Thread(target=worker, name=f"cira-sap-refresh-{tenant_id}", daemon=True).start()

    def _select(self, tenant_id: str, probe: bool = False) -> DataBackend:
        tenant = config.CURRENT_TENANT.get()
        probes: list[dict] = []
        chosen: DataBackend | None = None
        for kind in candidate_kinds(tenant):
            try:
                backend = _make(kind)
            except (config.ConfigError, ImportError, SapUnavailableError) as exc:
                probes.append({"backend": kind, "ok": False, "error": str(exc)[:300]})
                continue
            except Exception as exc:  # pragma: no cover - defensive
                probes.append({"backend": kind, "ok": False, "error": str(exc)[:300]})
                continue
            try:
                probe_result = backend.ping()
            except Exception as exc:  # pragma: no cover - defensive
                probe_result = {"ok": False, "error": str(exc)[:300]}
            probe_result["candidate"] = kind
            probes.append(probe_result)
            if probe_result.get("ok"):
                chosen = backend
                break
            self._last_error = str(probe_result.get("error", ""))[:300]
            log.warning("SAP backend %s unavailable for %s: %s", kind, tenant_id, self._last_error)
            try:
                backend.close()
            except Exception:
                pass

        if chosen is None:
            if config.SIMULATOR_ALLOWED and "simulator" not in [p.get("candidate") for p in probes]:
                try:
                    chosen = _make("simulator")
                    chosen.ping()
                except Exception as exc:  # pragma: no cover
                    log.error("Sandbox backend failed to start: %s", exc)
            if chosen is None:
                raise BackendUnavailable(
                    "No SAP backend is reachable. "
                    + (f"Last error: {self._last_error}" if self._last_error else "")
                )

        with self._lock:
            previous = self._active.get(tenant_id)
            self._active[tenant_id] = chosen
            self._active_at[tenant_id] = time.time()
            self._unhealthy_until.pop(tenant_id, None)
            self._probe_log = probes
            if previous is not None and previous is not chosen:
                self._retire_locked(previous)
        if not chosen.simulated:
            log.info(
                "Active SAP backend for %s: %s (schema=%s%s)",
                tenant_id, chosen.name, chosen.schema, ", reprobe" if probe else "",
            )
        return chosen

    def _retire_locked(self, backend: DataBackend) -> None:
        """Stop advertising a backend; close it only once no query holds it."""
        self._retiring.add(id(backend))
        threading.Thread(
            target=self._close_when_idle, args=(backend,),
            name="cira-sap-retire", daemon=True,
        ).start()

    def _close_when_idle(self, backend: DataBackend) -> None:
        # `execute()` increments a per-backend in-flight counter; give in-flight
        # queries a grace period instead of yanking the connection mid-cursor.
        for _ in range(60):
            if getattr(backend, "_inflight", None) is None or backend._inflight <= 0:
                break
            time.sleep(0.5)
        else:
            log.warning("Retiring %s while still busy; leaving it to GC", backend.name)
            with self._lock:
                self._retiring.discard(id(backend))
            return
        try:
            backend.close()
        except Exception:
            pass
        with self._lock:
            self._retiring.discard(id(backend))

    # ── failover ──────────────────────────────────────────────────────────────
    def mark_unhealthy(self, tenant_id: str, reason: str) -> None:
        with self._lock:
            self._unhealthy_until[tenant_id] = time.time() + config.BACKEND_RETRY_S
            self._last_error = reason[:300]
            current = self._active.get(tenant_id)
            if current is not None:
                self._retire_locked(current)
                self._active.pop(tenant_id, None)

    def run(self, work: Callable[[DataBackend], T], *, allow_failover: bool = True) -> T:
        """Run `work(backend)` while tracking that it is in flight.

        The counter is what makes retirement safe: `_close_when_idle` will not
        yank a connection pool out from under a running query, and `run()` is the
        single place that knows a query is live (every entry point goes through it).
        """
        tenant_id = self._tenant_id()
        backend = self.get()
        _bump(backend, 1)
        try:
            try:
                return work(backend)
            except (SapUnavailableError, BackendUnavailable) as exc:
                if backend.simulated or not allow_failover:
                    raise
                log.warning(
                    "%s failed (%s); failing over for tenant %s", backend.name, exc, tenant_id
                )
                self.mark_unhealthy(tenant_id, str(exc))
                try:
                    fallback = self.get(force=True)
                except Exception as inner:
                    raise BackendUnavailable(
                        f"{backend.name} is unreachable ({exc}) and no other configured "
                        "source answered."
                    ) from inner
                if fallback is backend:
                    raise
                _bump(fallback, 1)
                try:
                    return work(fallback)
                finally:
                    _bump(fallback, -1)
        finally:
            _bump(backend, -1)

    @property
    def probes(self) -> list[dict]:
        with self._lock:
            return list(self._probe_log)

    @property
    def last_error(self) -> str:
        return self._last_error


_selector = _Selector()


def get_active_backend(force: bool = False) -> DataBackend:
    return _selector.get(force=force)


def probe_log() -> list[dict]:
    """Why each candidate was accepted/rejected (for /sap/health and migrate --check)."""
    return _selector.probes


def _bump(backend: DataBackend, delta: int) -> None:
    """In-flight query counter for safe backend retirement."""
    try:
        backend._inflight = max(0, int(getattr(backend, "_inflight", 0)) + delta)
    except Exception:  # pragma: no cover - never break a query over bookkeeping
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────────────────
def _list_tables_sync(pattern: str = "", limit: int = 300) -> dict:
    backend = _selector.get()
    tables = backend.list_tables(pattern=pattern, limit=limit)  # catalog reads are cheap + cached
    return {
        "backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "count": len(tables),
        "tables": [t.as_dict() for t in tables],
    }


def _search_schema_sync(keyword: str, limit: int = 40) -> dict:
    backend = _selector.get()
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
            alias_hits.append(
                {
                    "alias": alias,
                    "table": table,
                    "description": entities.describe_table_name(table),
                }
            )
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
    search = getattr(backend, "search_columns", None)
    if callable(search):
        try:
            return search(keyword, limit)
        except Exception as exc:
            log.debug("native column search failed: %s", exc)
            return []

    out: list[dict] = []
    for table in backend.list_tables(limit=500):
        for col in backend.get_columns(table.name):
            if (
                keyword.lower() in col.name.lower()
                or keyword.lower() in (col.description or "").lower()
            ):
                out.append(
                    {
                        "table": table.name,
                        "column": col.name,
                        "type": col.data_type,
                        "description": col.description,
                    }
                )
                if len(out) >= limit:
                    return out
    return out


def _resolve_table(backend: DataBackend, name: str) -> str:
    """Map a friendly entity name to a real table that exists on the backend."""
    physical = entities.normalise_table_name(name)
    try:
        tables = {t.name.upper(): t.name for t in backend.list_tables(limit=100000)}
    except Exception as exc:  # pragma: no cover - catalog unreadable
        log.debug("catalog unavailable (%s); trusting table name %r", exc, physical)
        tables = {}
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
    return _selector.run(lambda backend: _describe_on(backend, table, sample_rows))


def _describe_on(backend: DataBackend, table: str, sample_rows: int) -> dict:
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
            info["sample_error"] = str(exc)[:200]
    return info


# ─────────────────────────────────────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────────────────────────────────────
def _finalise(rows: list[dict], decode: bool = True) -> list[dict]:
    return entities.decode_rows(rows) if decode else rows


def _run_query_sync(payload: dict) -> QueryResult:
    return _selector.run(lambda backend: _query_on(backend, payload))


def _query_on(backend: DataBackend, payload: dict) -> QueryResult:
    started = time.time()
    spec: QuerySpec = spec_from_payload(payload)
    spec.limit = max(1, min(int(spec.limit or config.DEFAULT_ROW_LIMIT), config.MAX_ROW_LIMIT))
    spec.table = _resolve_table(backend, spec.table)

    columns = backend.get_columns(spec.table)
    if not columns:
        raise SapDataError(
            f"Could not read the column list for {spec.table} from {backend.name}. "
            "The table may be empty or the user may lack SELECT rights on it."
        )
    resolver = ColumnResolver(columns)

    if backend.dialect == "odata":
        return _run_query_service_layer(backend, spec, resolver, started)

    sql, params = build_select(
        spec, resolver, backend.dialect, schema=backend.sql_schema
    )
    col_names, raw_rows = backend.execute(sql, params)
    rows = _finalise(rows_to_jsonable(col_names, raw_rows))
    _audit_query(backend, spec, params, len(rows))

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
            count_spec, resolver, backend.dialect, schema=backend.sql_schema
        )
        _, rows = backend.execute(sql, params)
        if rows:
            value = rows[0][0]
            return int(value) if value is not None else None
    except Exception as exc:
        log.debug("count query failed: %s", exc)
    return None


def _run_query_service_layer(
    backend: DataBackend, spec: QuerySpec, resolver: ColumnResolver, started: float
) -> QueryResult:
    """OData path. Every identifier goes through the catalog resolver first.

    This used to pass `resolver` in and never use it, so column names reached the
    $filter/$select string unvalidated — OData injection on a hallucinated name.
    """
    filters = []
    for f in spec.filters:
        column = resolver.resolve(f.column).name
        value = entities.encode_value(column, f.value if f.value is not None else f.values)
        filters.append((column, f.op, value))
    if spec.year:
        date_col = resolver.resolve(spec.date_column).name if spec.date_column and resolver.exists(spec.date_column) else "DocDate"
        filters.append((date_col, "gte", f"{spec.year}-01-01"))
        filters.append((date_col, "lte", f"{spec.year}-12-31"))
    if spec.date_from or spec.date_to:
        date_col = resolver.resolve(spec.date_column).name if spec.date_column and resolver.exists(spec.date_column) else "DocDate"
        if spec.date_from:
            filters.append((date_col, "gte", spec.date_from))
        if spec.date_to:
            filters.append((date_col, "lte", spec.date_to))

    select = [resolver.resolve(c).name for c in spec.columns if resolver.exists(c)] or None
    order = [
        (resolver.resolve(o.column).name, o.direction)
        for o in spec.order_by
        if o.column and resolver.exists(o.column)
    ]
    columns, rows = backend.fetch_entity(  # type: ignore[attr-defined]
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
        source=f"{backend.name} · {getattr(backend, 'company', backend.schema)}",
        backend=backend.name,
        entity=spec.table,
        table=spec.table,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        sql="",
        simulated=backend.simulated,
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
        rec = dict(zip(keys, key, strict=False))
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
    return _selector.run(lambda backend: _sql_on(backend, sql, limit))


def _sql_on(backend: DataBackend, sql: str, limit: int | None) -> QueryResult:
    started = time.time()
    if backend.dialect == "odata":
        raise SapDataError(
            "Raw SQL needs the HANA connection; only entity queries are available "
            "through the Service Layer right now."
        )
    statement = ensure_read_only(sql)
    # Read-only is not the same as scoped: without this, `FROM "SYS"."USERS"`
    # sailed through and returned password hashes from a SYSTEM connection.
    enforce_scope(statement, backend.allowed_schemas)
    row_cap = max(1, min(int(limit or config.DEFAULT_ROW_LIMIT), config.MAX_ROW_LIMIT))
    guarded = apply_row_limit(statement, row_cap, backend.dialect)
    if backend.sql_schema:
        guarded = _qualify_bare_tables(guarded, backend)
    col_names, raw_rows = backend.execute(guarded, [])
    rows = _finalise(rows_to_jsonable(col_names, raw_rows))
    _audit_sql(backend, guarded, len(rows))
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


def _audit_query(backend: DataBackend, spec: QuerySpec, params: list, row_count: int) -> None:
    """Record the *intent* (table, filters, groups) — never the bound values, which
    may contain names/amounts that have no business in a log file."""
    try:
        import audit

        audit.event(
            "sap_query",
            backend=backend.name,
            schema=backend.schema,
            table=spec.table,
            filters=[{"column": f.column, "op": f.op} for f in spec.filters][:20],
            group_by=list(spec.group_by)[:10],
            aggregates=[f"{a.func}({a.column})" for a in spec.aggregates][:10],
            year=spec.year,
            date_from=spec.date_from,
            date_to=spec.date_to,
            limit=spec.limit,
            rows=row_count,
        )
    except Exception:  # pragma: no cover
        pass


def _audit_sql(backend: DataBackend, sql: str, row_count: int) -> None:
    try:
        import audit

        audit.event(
            "sap_sql",
            backend=backend.name,
            schema=backend.schema,
            rows=row_count,
            sql=sql,
        )
    except Exception:  # pragma: no cover - auditing must never break a query
        pass


def _qualify_bare_tables(sql: str, backend: DataBackend) -> str:
    """Prefix unqualified SAP B1 table names with the company schema."""
    import re

    known = {t.name.upper() for t in backend.list_tables(limit=100000)}
    if not known:
        return sql
    from .hana_backend import sql_ident

    def quote(ident: str) -> str:
        return f"[{ident.replace(']', ']]')}]" if backend.dialect == "mssql" else sql_ident(ident)

    def repl(match: re.Match) -> str:
        keyword, spacing, name = match.group(1), match.group(2), match.group(3)
        bare = name.strip('"[]').upper()
        if bare in known and "." not in name:
            return f"{keyword}{spacing}{quote(backend.sql_schema)}.{quote(bare)}"
        return match.group(0)

    return re.sub(
        r'\b(FROM|JOIN)(\s+)("?\[?[A-Za-z_@][\w@$#\]]*"?)',
        repl,
        sql,
        flags=re.IGNORECASE,
    )


def _health_sync(force: bool = False) -> dict:
    backend = _selector.get(force=force)
    probe = backend.ping(force=force)
    tables = []
    try:
        tables = backend.list_tables(limit=100000)
    except Exception as exc:
        probe.setdefault("warnings", []).append(f"catalog unavailable: {str(exc)[:200]}")
    fatal, warnings = config.validate()
    return {
        "active_backend": backend.name,
        "schema": backend.schema,
        "simulated": backend.simulated,
        "tables_visible": len(tables),
        "last_error": _selector.last_error,
        "probe": probe,
        "attempts": _selector.probes,
        "config": config.summary(),
        "config_errors": fatal,
        "config_warnings": warnings,
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


async def health(force: bool = False) -> dict:
    return await asyncio.to_thread(_health_sync, force)


def health_sync(force: bool = False) -> dict:
    return _health_sync(force)


# ─────────────────────────────────────────────────────────────────────────────
# Writes (Service Layer only, capability-checked)
# ─────────────────────────────────────────────────────────────────────────────
def _create_entity_sync(table_or_entity: str, data: dict) -> dict:
    backend = _selector.get()
    if not backend.can("write") and not backend.can("write-via-service-layer"):
        raise SapDataError(
            f"The active backend '{backend.name}' cannot write to SAP. Records can "
            "only be created when the SAP B1 Service Layer is reachable "
            "(SAP_B1_* in Backend/.env)."
        )
    if backend.simulated:
        raise SapDataError(
            "Refusing to write while on the offline sandbox: nothing real would "
            "change. Connect the Service Layer to enable data entry."
        )
    create = getattr(backend, "create_entity", None)
    if not callable(create):
        raise SapDataError(f"{backend.name} does not implement create_entity.")
    return create(table_or_entity, data)


async def create_entity(table_or_entity: str, data: dict) -> dict:
    return await asyncio.to_thread(_create_entity_sync, table_or_entity, data)


__all__ = [
    "BackendUnavailable",
    "SapDataError",
    "SapUnavailableError",
    "candidate_kinds",
    "create_entity",
    "describe_table",
    "get_active_backend",
    "health",
    "health_sync",
    "list_tables",
    "probe_log",
    "run_query",
    "run_sql",
    "search_schema",
]
