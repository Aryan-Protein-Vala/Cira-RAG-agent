"""Microsoft SQL Server driver.

This is the equivalent of `hana_backend.py` but for SAP Business One running on Microsoft SQL Server.
It uses `pymssql` to connect and queries `sys.tables`, `sys.views`, and `sys.columns` for schema discovery.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

import config

from .base import DataBackend
from .serialize import to_jsonable
from .sql_guard import rebind_param_markers
from .types_ import ColumnInfo, SapUnavailableError, TableInfo

log = logging.getLogger("cira.mssql")

_ALLOWED_EXTRA_SCHEMAS = "MSSQL_EXTRA_SCHEMAS"


def _safe_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for token in (str(config.MSSQL_HOST), str(config.MSSQL_USER), str(config.MSSQL_PASSWORD)):
        if token:
            text = text.replace(token, "[redacted]")
    return text[:300]


class MssqlBackend(DataBackend):
    name = "Microsoft SQL Server"
    dialect = "mssql"
    simulated = False
    # Read-only by design: no `write` capability, so /sap/write never lands here.
    capabilities = frozenset({"sql", "catalog"})

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        pool_size: int | None = None,
    ):
        tenant = config.CURRENT_TENANT.get() or None
        self.host = host or str(config.resolve(tenant, "MSSQL_HOST", config.MSSQL_HOST))
        self.port = port or int(config.resolve(tenant, "MSSQL_PORT", config.MSSQL_PORT))
        self.user = user or str(config.resolve(tenant, "MSSQL_USER", config.MSSQL_USER))
        self.password = password or str(config.resolve(tenant, "MSSQL_PASSWORD", config.MSSQL_PASSWORD))
        # `schema` is the *database* name here (the field the rest of CIRA shows
        # as "schema"); MSSQL_SCHEMA is the inside-database schema, usually dbo.
        self.database = (
            database or str(config.resolve(tenant, "MSSQL_DATABASE", config.MSSQL_DATABASE)) or ""
        ).strip()
        self.schema = self.database
        self._sql_schema = (
            str(config.resolve(tenant, "MSSQL_SCHEMA", config.MSSQL_SCHEMA)) or "dbo"
        ).strip()
        self.pool_size = max(
            1, pool_size or int(config.resolve(tenant, "MSSQL_POOL_SIZE", config.MSSQL_POOL_SIZE))
        )
        if not self.host or not self.user or not self.password or not self.database:
            raise config.ConfigError(
                "SQL Server is not fully configured (MSSQL_HOST / MSSQL_USER / "
                "MSSQL_PASSWORD / MSSQL_DATABASE are required in Backend/.env)."
            )
        self._max_total = self.pool_size * 4
        self._slots = threading.BoundedSemaphore(self._max_total)
        self._pool: queue.LifoQueue = queue.LifoQueue(maxsize=self.pool_size)
        self._ping_cache: tuple[float, dict] | None = None
        self._created = 0
        self._lock = threading.Lock()
        self._catalog_lock = threading.Lock()
        self._tables_cache: tuple[float, list[TableInfo]] | None = None
        self._columns_cache: dict[str, tuple[float, list[ColumnInfo]]] = {}

    # NOTE: `sql_schema` is a property on DataBackend, so it must be overridden
    # as a property here too (assigning self.sql_schema in __init__ would raise
    # AttributeError: can't set attribute).
    @property
    def sql_schema(self) -> str:  # type: ignore[override]
        return self._sql_schema

    @property
    def allowed_schemas(self) -> list[str]:  # type: ignore[override]
        """dbo (or the configured schema) plus any explicit MSSQL extras."""
        extra = [x.strip().upper() for x in (config.HANA_EXTRA_SCHEMAS or []) if x.strip()]
        return [s for s in [self._sql_schema.upper(), *extra] if s]

    # ── connections ──────────────────────────────────────────────────────────
    def _connect(self):
        try:
            import pymssql
        except ImportError as exc:  # pragma: no cover
            raise SapUnavailableError(
                "pymssql is not installed in this venv — `pip install pymssql`, or "
                "use the official MS Driver for Python (ODBC) if the company standard "
                "requires signing/certificates."
            ) from exc

        try:
            # pymssql connects to server:port or server if port is default
            # pymssql takes host:port, or host\instance for named instances.
            server = f"{self.host}:{self.port}" if self.port and self.port != 1433 else self.host
            return pymssql.connect(
                server=server,
                user=self.user,
                password=self.password,
                database=self.database,
                login_timeout=max(1, config.MSSQL_CONNECT_TIMEOUT // 1000),
                # Per-query timeout: without it a runaway SELECT holds a pooled
                # connection (and locks nothing, but starves the pool) forever.
                timeout=config.MSSQL_QUERY_TIMEOUT,
                autocommit=True,
            )
        except Exception as exc:
            raise SapUnavailableError(f"MSSQL connection failed: {exc}") from exc

    def _acquire(self):
        try:
            while True:
                conn = self._pool.get_nowait()
                try:
                    # pymssql has no isconnected(); a 1-row round trip is the check.
                    cur = conn.cursor()
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    cur.close()
                    return conn
                except Exception:
                    try:
                        conn.close()
                    finally:
                        self._slots.release()
        except queue.Empty:
            pass

        if not self._slots.acquire(timeout=max(1.0, config.MSSQL_CONNECT_TIMEOUT / 1000 * 2)):
            raise SapUnavailableError(
                f"SQL Server pool is saturated ({self._max_total} connections in use)."
            )
        with self._lock:
            self._created += 1
        try:
            return self._connect()
        except Exception:
            with self._lock:
                self._created -= 1
            self._slots.release()
            raise

    def _release(self, conn) -> None:
        if conn is None:
            return
        try:
            self._pool.put_nowait(conn)
            return
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        self._slots.release()

    def close(self) -> None:
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                return
            try:
                conn.close()
            except Exception:
                pass
            finally:
                self._slots.release()

    # ── raw execution ────────────────────────────────────────────────────────
    def execute(self, sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
        conn = self._acquire()
        cursor = None
        try:
            # Bind at the *marker* level: a blind sql.replace("?", "%s") used to
            # corrupt literal question marks inside string literals and left
            # unescaped % (LIKE patterns) to break pymssql's % interpolation.
            sql_mssql = rebind_param_markers(sql, "format")
            cursor = conn.cursor()
            cursor.execute(sql_mssql, tuple(params or ()))
            columns = [d[0] for d in (cursor.description or [])]
            rows = cursor.fetchall() if cursor.description else []
            return columns, rows
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            self._release(conn)

    def _fetch_dicts(self, sql: str, params: list[Any] | None = None) -> list[dict]:
        columns, rows = self.execute(sql, params)
        out = []
        for row in rows:
            rec = {}
            for i, c in enumerate(columns):
                val = to_jsonable(row[i] if i < len(row) else None)
                rec[c] = val.strip() if isinstance(val, str) else val
            out.append(rec)
        return out

    # ── health / schema discovery ────────────────────────────────────────────
    def ping(self, force: bool = False) -> dict:
        now = time.time()
        if not force and self._ping_cache and now - self._ping_cache[0] < config.HEALTH_CACHE_TTL_S:
            return dict(self._ping_cache[1], cached=True)
        started = now
        try:
            info = self._fetch_dicts(
                "SELECT DB_NAME() AS [database], @@VERSION AS [version], "
                "DATABASEPROPERTYEX(DB_NAME(), 'Updateability') AS [readwrite]"
            )
            detail = info[0] if info else {}
            result = {
                "ok": True,
                "backend": self.name,
                "schema": self.schema,
                "server_version": detail.get("version"),
                "latency_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            result = {
                "ok": False,
                "backend": self.name,
                "schema": self.schema,
                "error": _safe_error(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }
        self._ping_cache = (time.time(), result)
        return dict(result)

    # ── catalog ──────────────────────────────────────────────────────────────
    def list_tables(self, pattern: str = "", include_views: bool = True,
                    limit: int = 1000) -> list[TableInfo]:
        now = time.time()
        with self._catalog_lock:
            cached = self._tables_cache
        # Reusing the HANA cache TTL setting
        if cached and now - cached[0] < getattr(config, "SCHEMA_CACHE_TTL_S", 3600):
            tables = cached[1]
        else:
            tables = self._load_tables()
            with self._catalog_lock:
                self._tables_cache = (now, tables)

        result = tables
        if pattern:
            needle = pattern.strip().lower()
            result = [
                t for t in tables
                if needle in t.name.lower() or needle in (t.description or "").lower()
            ]
        if not include_views:
            result = [t for t in result if t.kind == "TABLE"]
        return result[:limit]

    def _load_tables(self) -> list[TableInfo]:
        # Restrict the catalog to the configured schema so a second database on
        # the same server cannot leak its table list into the agent's choices.
        sql = (
            "SELECT t.name, 'TABLE' AS kind FROM sys.tables t "
            "JOIN sys.schemas sc ON sc.schema_id = t.schema_id "
            "WHERE sc.name = %s "
            "UNION ALL "
            "SELECT v.name, 'VIEW' AS kind FROM sys.views v "
            "JOIN sys.schemas sc2 ON sc2.schema_id = v.schema_id "
            "WHERE sc2.name = %s "
            "ORDER BY 1"
        )
        try:
            rows = self._fetch_dicts(sql, [self._sql_schema, self._sql_schema])
            counts = self._record_counts()

            # Attempt to fetch extended properties (comments)
            comments = {}
            try:
                c_rows = self._fetch_dicts(
                    "SELECT obj.name as name, ep.value as comments "
                    "FROM sys.extended_properties ep "
                    "JOIN sys.objects obj ON ep.major_id = obj.object_id "
                    "WHERE ep.minor_id = 0 AND ep.name = 'MS_Description'"
                )
                for r in c_rows:
                    comments[r["name"]] = str(r["comments"])
            except Exception:
                pass

            tables = []
            for r in rows:
                name = r["name"]
                tables.append(
                    TableInfo(
                        name=name,
                        schema=self.schema,
                        description=comments.get(name, ""),
                        kind=r.get("kind") or "TABLE",
                        row_count=counts.get(name),
                    )
                )
            return tables
        except Exception as exc:
            log.warning("Could not list MSSQL tables: %s", exc)
            return []

    def _record_counts(self) -> dict[str, int]:
        try:
            rows = self._fetch_dicts(
                "SELECT t.name AS t, p.rows AS c "
                "FROM sys.tables t "
                "INNER JOIN sys.partitions p ON t.object_id = p.object_id "
                "WHERE p.index_id IN (0,1)"
            )
            # Group by table because a table can have multiple partitions
            counts = {}
            for r in rows:
                counts[r["t"]] = counts.get(r["t"], 0) + int(r["c"])
            return counts
        except Exception as exc:
            log.debug("MSSQL record counts unavailable: %s", exc)
            return {}

    def get_columns(self, table: str) -> list[ColumnInfo]:
        key = table.upper()
        now = time.time()
        cached = self._columns_cache.get(key)
        if cached and now - cached[0] < getattr(config, "SCHEMA_CACHE_TTL_S", 3600):
            return cached[1]

        sql = (
            "SELECT c.name, t.name as type, c.max_length as len, "
            "c.scale, c.is_nullable as nullable, ep.value as comments, c.column_id as pos "
            "FROM sys.columns c "
            "JOIN sys.types t ON c.user_type_id = t.user_type_id "
            "JOIN sys.objects o ON c.object_id = o.object_id "
            "LEFT JOIN sys.extended_properties ep ON ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description' "
            "WHERE UPPER(o.name) = %s AND SCHEMA_NAME(o.schema_id) = %s "
            "ORDER BY c.column_id"
        )
        try:
            rows = self._fetch_dicts(sql, [key, self._sql_schema])
            cols = [
                ColumnInfo(
                    name=r["name"],
                    data_type=r.get("type") or "",
                    length=int(r["len"]) if r.get("len") not in (None, "") else None,
                    scale=int(r["scale"]) if r.get("scale") not in (None, "") else None,
                    nullable=str(r.get("nullable", "1")).upper() in ("TRUE", "Y", "1"),
                    description=str(r.get("comments") or ""),
                    position=int(r.get("pos") or 0),
                )
                for r in rows
            ]
            self._columns_cache[key] = (now, cols)
            return cols
        except Exception as exc:
            log.warning("Could not get MSSQL columns for %s: %s", key, exc)
            return []

    def row_count(self, table: str) -> int | None:
        try:
            rows = self._fetch_dicts(
                f"SELECT COUNT(*) AS c FROM [{self._sql_schema}].[{table.replace(']', ']]')}]"
            )
            return int(rows[0]["c"]) if rows else None
        except Exception:
            return None
