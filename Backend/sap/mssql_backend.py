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
from .types_ import ColumnInfo, SapUnavailableError, TableInfo

log = logging.getLogger("cira.mssql")


class MssqlBackend(DataBackend):
    name = "Microsoft SQL Server"
    dialect = "mssql"
    simulated = False

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        pool_size: int | None = None,
    ):
        tenant = config.CURRENT_TENANT.get() or {}
        self.host = host or tenant.get("MSSQL_HOST", config.MSSQL_HOST)
        self.port = port or tenant.get("MSSQL_PORT", config.MSSQL_PORT)
        self.user = user or tenant.get("MSSQL_USER", config.MSSQL_USER)
        self.password = password or tenant.get("MSSQL_PASSWORD", config.MSSQL_PASSWORD)
        self.schema = (database or tenant.get("MSSQL_DATABASE", config.MSSQL_DATABASE) or "").strip()
        self.pool_size = max(1, pool_size or tenant.get("MSSQL_POOL_SIZE", config.MSSQL_POOL_SIZE))
        
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._created = 0
        self._lock = threading.Lock()
        self._catalog_lock = threading.Lock()
        self._tables_cache: tuple[float, list[TableInfo]] | None = None
        self._columns_cache: dict[str, tuple[float, list[ColumnInfo]]] = {}

    # ── connections ──────────────────────────────────────────────────────────
    def _connect(self):
        try:
            import pymssql
        except ImportError as exc:  # pragma: no cover
            raise SapUnavailableError(
                "pymssql is not installed — run `pip install pymssql`."
            ) from exc

        try:
            # pymssql connects to server:port or server if port is default
            server = f"{self.host}:{self.port}" if self.port else self.host
            return pymssql.connect(
                server=server,
                user=self.user,
                password=self.password,
                database=self.schema,
                login_timeout=max(1, config.MSSQL_CONNECT_TIMEOUT // 1000),
                autocommit=True
            )
        except Exception as exc:
            raise SapUnavailableError(f"MSSQL connection failed: {exc}") from exc

    def _acquire(self):
        try:
            conn = self._pool.get_nowait()
            try:
                # Basic liveness check for pymssql (no built-in isconnected(), we assume it's alive or ping it)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        except queue.Empty:
            pass

        with self._lock:
            self._created += 1
        try:
            return self._connect()
        except Exception as exc:
            with self._lock:
                self._created -= 1
            raise

    def _release(self, conn) -> None:
        if conn is None:
            return
        try:
            if self._pool.qsize() < self.pool_size:
                self._pool.put_nowait(conn)
                return
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

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

    # ── raw execution ────────────────────────────────────────────────────────
    def execute(self, sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
        conn = self._acquire()
        cursor = None
        try:
            # Replace HANA ? parameter markers with %s for pymssql if any
            sql_mssql = sql.replace("?", "%s")
            
            # Remove HANA quotes in schema."TABLE" for MSSQL schema..[TABLE] or dbo.[TABLE]
            # Since B1 usually uses `dbo`, we'll just run queries directly if they have quotes
            # or try to let pymssql handle it.
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
    def ping(self) -> dict:
        started = time.time()
        try:
            info = self._fetch_dicts("SELECT SYSTEM_USER as [user], DB_NAME() as [schema], @@VERSION as [version]")
            detail = info[0] if info else {}
            return {
                "ok": True,
                "backend": self.name,
                "host": f"{self.host}:{self.port}",
                "schema": self.schema,
                "user": detail.get("user"),
                "version": detail.get("version"),
                "latency_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "backend": self.name,
                "host": f"{self.host}:{self.port}",
                "schema": self.schema,
                "error": str(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }

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
        sql = (
            "SELECT name, 'TABLE' AS kind "
            "FROM sys.tables "
            "UNION ALL "
            "SELECT name, 'VIEW' AS kind "
            "FROM sys.views "
            "ORDER BY 1"
        )
        try:
            rows = self._fetch_dicts(sql)
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
            "WHERE UPPER(o.name) = %s "
            "ORDER BY c.column_id"
        )
        try:
            rows = self._fetch_dicts(sql, [key])
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
            rows = self._fetch_dicts(f'SELECT COUNT(*) AS c FROM [{table}]')
            return int(rows[0]["c"]) if rows else None
        except Exception:
            return None
