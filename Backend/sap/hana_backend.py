"""SAP HANA driver — the deep path.

Highlights vs. the previous implementation:

* a real connection pool (the old code opened a fresh TCP+TLS session for every
  single question, which on a remote Azure HANA costs 1-3 seconds each time)
* full catalog introspection over SYS.TABLES / SYS.VIEWS / SYS.TABLE_COLUMNS,
  including the SAP B1 column COMMENTS, so the agent can find *any* table or
  field in the company database (including user tables "@..." and UDFs "U_...")
* automatic company-schema detection: if the configured schema does not exist,
  we look for schemas that contain the SAP B1 marker table OADM
* every result value is coerced into a JSON-safe type
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

log = logging.getLogger("cira.hana")


class HanaBackend(DataBackend):
    name = "SAP HANA"
    dialect = "hana"
    simulated = False

    def __init__(
        self,
        host: str = config.HANA_HOST,
        port: int = config.HANA_PORT,
        user: str = config.HANA_USER,
        password: str = config.HANA_PASSWORD,
        schema: str = config.HANA_SCHEMA,
        pool_size: int = config.HANA_POOL_SIZE,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.schema = (schema or "").strip()
        self.pool_size = max(1, pool_size)
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._created = 0
        self._lock = threading.Lock()
        self._catalog_lock = threading.Lock()
        self._tables_cache: tuple[float, list[TableInfo]] | None = None
        self._columns_cache: dict[str, tuple[float, list[ColumnInfo]]] = {}
        self._schema_verified = False

    # ── connections ──────────────────────────────────────────────────────────
    def _connect(self):
        try:
            from hdbcli import dbapi
        except ImportError as exc:  # pragma: no cover
            raise SapUnavailableError(
                "hdbcli is not installed — run `pip install hdbcli`."
            ) from exc

        kwargs: dict[str, Any] = {
            "address": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "autocommit": True,
            "connectTimeout": config.HANA_CONNECT_TIMEOUT_MS,
            "communicationTimeout": config.HANA_QUERY_TIMEOUT_S * 1000,
        }
        if config.HANA_ENCRYPT:
            kwargs["encrypt"] = True
            kwargs["sslValidateCertificate"] = config.HANA_VALIDATE_CERT
        if self.schema:
            kwargs["currentSchema"] = self.schema
        try:
            return dbapi.connect(**kwargs)
        except Exception as exc:
            # Some HANA revisions reject currentSchema for restricted users
            if self.schema and "schema" in str(exc).lower():
                kwargs.pop("currentSchema", None)
                return dbapi.connect(**kwargs)
            raise

    def _acquire(self):
        try:
            conn = self._pool.get_nowait()
            try:
                if conn.isconnected():
                    return conn
            except Exception:
                pass
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
            raise SapUnavailableError(f"HANA connection failed: {exc}") from exc

    def _release(self, conn) -> None:
        if conn is None:
            return
        try:
            if self._pool.qsize() < self.pool_size and conn.isconnected():
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
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params or ()))
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
            info = self._fetch_dicts(
                "SELECT CURRENT_USER AS \"user\", CURRENT_SCHEMA AS \"schema\", "
                "VERSION AS \"version\" FROM SYS.M_DATABASE"
            )
            detail = info[0] if info else {}
            self._verify_schema()
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

    def list_schemas(self) -> list[str]:
        try:
            rows = self._fetch_dicts(
                'SELECT SCHEMA_NAME AS "s" FROM SYS.SCHEMAS ORDER BY SCHEMA_NAME'
            )
            return [r["s"] for r in rows]
        except Exception as exc:
            log.warning("Could not list schemas: %s", exc)
            return []

    def find_company_schemas(self) -> list[str]:
        """Schemas that contain the SAP B1 marker table OADM."""
        try:
            rows = self._fetch_dicts(
                'SELECT SCHEMA_NAME AS "s" FROM SYS.TABLES WHERE TABLE_NAME = \'OADM\' '
                "ORDER BY SCHEMA_NAME"
            )
            return [r["s"] for r in rows]
        except Exception:
            return []

    def _verify_schema(self) -> None:
        """Make sure self.schema actually exists; auto-correct when possible."""
        if self._schema_verified:
            return
        schemas = self.list_schemas()
        if not schemas:
            self._schema_verified = True
            return
        upper = {s.upper(): s for s in schemas}
        if self.schema and self.schema.upper() in upper:
            self.schema = upper[self.schema.upper()]
            self._schema_verified = True
            return
        candidates = self.find_company_schemas()
        if candidates:
            chosen = candidates[0]
            log.warning(
                "Configured schema %r not found — using SAP B1 company schema %r",
                self.schema, chosen,
            )
            self.schema = chosen
        self._schema_verified = True

    # ── catalog ──────────────────────────────────────────────────────────────
    def list_tables(self, pattern: str = "", include_views: bool = True,
                    limit: int = 1000) -> list[TableInfo]:
        self._verify_schema()
        now = time.time()
        with self._catalog_lock:
            cached = self._tables_cache
        if cached and now - cached[0] < config.SCHEMA_CACHE_TTL_S:
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
            'SELECT TABLE_NAME AS "name", \'TABLE\' AS "kind", COMMENTS AS "comments" '
            "FROM SYS.TABLES WHERE SCHEMA_NAME = ? "
            "UNION ALL "
            'SELECT VIEW_NAME AS "name", \'VIEW\' AS "kind", COMMENTS AS "comments" '
            "FROM SYS.VIEWS WHERE SCHEMA_NAME = ? "
            "ORDER BY 1"
        )
        rows = self._fetch_dicts(sql, [self.schema, self.schema])
        counts = self._record_counts()
        tables = []
        for r in rows:
            name = r["name"]
            tables.append(
                TableInfo(
                    name=name,
                    schema=self.schema,
                    description=r.get("comments") or "",
                    kind=r.get("kind") or "TABLE",
                    row_count=counts.get(name),
                )
            )
        return tables

    def _record_counts(self) -> dict[str, int]:
        try:
            rows = self._fetch_dicts(
                'SELECT TABLE_NAME AS "t", RECORD_COUNT AS "c" '
                "FROM SYS.M_TABLES WHERE SCHEMA_NAME = ?",
                [self.schema],
            )
            return {r["t"]: int(r["c"] or 0) for r in rows}
        except Exception as exc:  # monitoring views need extra privileges
            log.debug("record counts unavailable: %s", exc)
            return {}

    def get_columns(self, table: str) -> list[ColumnInfo]:
        self._verify_schema()
        key = table.upper()
        now = time.time()
        cached = self._columns_cache.get(key)
        if cached and now - cached[0] < config.SCHEMA_CACHE_TTL_S:
            return cached[1]

        sql = (
            'SELECT COLUMN_NAME AS "name", DATA_TYPE_NAME AS "type", LENGTH AS "len", '
            'SCALE AS "scale", IS_NULLABLE AS "nullable", COMMENTS AS "comments", '
            'POSITION AS "pos" '
            "FROM SYS.TABLE_COLUMNS WHERE SCHEMA_NAME = ? AND TABLE_NAME = ? "
            "UNION ALL "
            'SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH, SCALE, IS_NULLABLE, COMMENTS, POSITION '
            "FROM SYS.VIEW_COLUMNS WHERE SCHEMA_NAME = ? AND VIEW_NAME = ? "
            "ORDER BY 7"
        )
        rows = self._fetch_dicts(sql, [self.schema, key, self.schema, key])
        cols = [
            ColumnInfo(
                name=r["name"],
                data_type=r.get("type") or "",
                length=int(r["len"]) if r.get("len") not in (None, "") else None,
                scale=int(r["scale"]) if r.get("scale") not in (None, "") else None,
                nullable=str(r.get("nullable", "TRUE")).upper() in ("TRUE", "Y", "1"),
                description=r.get("comments") or "",
                position=int(r.get("pos") or 0),
            )
            for r in rows
        ]
        self._columns_cache[key] = (now, cols)
        return cols

    def row_count(self, table: str) -> int | None:
        try:
            rows = self._fetch_dicts(
                f'SELECT COUNT(*) AS "c" FROM "{self.schema}"."{table.upper()}"'
            )
            return int(rows[0]["c"]) if rows else None
        except Exception:
            return None
