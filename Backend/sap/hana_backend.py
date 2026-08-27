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
import re
import threading
import time
from typing import Any

import config

from .base import DataBackend
from .serialize import to_jsonable
from .types_ import ColumnInfo, SapUnavailableError, TableInfo

log = logging.getLogger("cira.hana")


def _safe_error(exc: Exception) -> str:
    """Strip host/port/user detail from driver exceptions before they travel."""
    text = str(exc) or exc.__class__.__name__
    for token in (str(config.HANA_HOST), str(config.HANA_USER), str(config.HANA_PASSWORD)):
        if token:
            text = text.replace(token, "[redacted]")
    text = re.sub(r"(\d{1,3}\.){3}\d{1,3}:?\d*", "[host redacted]", text)
    return text[:300]


class HanaBackend(DataBackend):
    name = "SAP HANA"
    dialect = "hana"
    simulated = False
    capabilities = frozenset({"sql", "catalog", "write-via-service-layer"})

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        schema: str | None = None,
        pool_size: int | None = None,
    ):
        tenant = config.CURRENT_TENANT.get() or None

        self.host = host or str(config.resolve(tenant, "HANA_HOST", config.HANA_HOST))
        self.port = port or int(config.resolve(tenant, "HANA_PORT", config.HANA_PORT))
        self.user = user or str(config.resolve(tenant, "HANA_USER", config.HANA_USER))
        self.password = password or str(config.resolve(tenant, "HANA_PASSWORD", config.HANA_PASSWORD))
        self.schema = (
            schema or str(config.resolve(tenant, "HANA_SCHEMA", config.HANA_SCHEMA)) or ""
        ).strip()
        self.pool_size = max(
            1, pool_size or int(config.resolve(tenant, "HANA_POOL_SIZE", config.HANA_POOL_SIZE))
        )
        if not self.host or not self.user or not self.password:
            raise config.ConfigError(
                "SAP HANA is not fully configured (HANA_HOST / HANA_USER / "
                "HANA_PASSWORD / HANA_SCHEMA are required in Backend/.env)."
            )
        # The pool only bounds *idle* connections; the semaphore bounds the total
        # ever opened, so a burst of concurrent questions cannot exhaust HANA
        # (each overflow connection used to be created unconditionally).
        self._max_total = self.pool_size * 4
        self._slots = threading.BoundedSemaphore(self._max_total)
        self._acquire_wait_s = max(1.0, config.HANA_CONNECT_TIMEOUT_MS / 1000 * 2)
        self._pool: queue.LifoQueue = queue.LifoQueue(maxsize=self.pool_size)
        self._created = 0
        self._lock = threading.Lock()
        self._ping_cache: tuple[float, dict] | None = None
        self._catalog_lock = threading.Lock()
        self._tables_cache: tuple[float, list[TableInfo]] | None = None
        self._columns_cache: dict[str, tuple[float, list[ColumnInfo]]] = {}
        self._schema_verified = False

    @property
    def allowed_schemas(self) -> list[str]:
        """Company schema + whatever the operator explicitly opted in to."""
        extra = [s.strip().upper() for s in (config.HANA_EXTRA_SCHEMAS or []) if s.strip()]
        return [s for s in [self.schema, *extra] if s]

    # ── connections ──────────────────────────────────────────────────────────
    def _connect(self):
        try:
            from hdbcli import dbapi
        except ImportError as exc:  # pragma: no cover
            raise SapUnavailableError(
                "the SAP HANA driver (hdbcli) is not installed in this venv. It is not "
                "on PyPI: install the SAP HANA Client "
                "(https://help.sap.com/viewer/p/SAP_HANA_CLIENT) or "
                "`pip install <hdbcli-*.whl>` from it. On SQL Server B1, use "
                "CIRA_DATA_SOURCE=mssql instead of HANA."
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
        database_name = getattr(config, "HANA_DATABASE_NAME", "")
        if database_name:
            kwargs["databaseName"] = database_name
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
            while True:
                conn = self._pool.get_nowait()
                try:
                    if conn.isconnected():
                        return conn
                except Exception:
                    pass
                try:
                    conn.close()
                finally:
                    self._slots.release()
        except queue.Empty:
            pass

        if not self._slots.acquire(timeout=self._acquire_wait_s):
            raise SapUnavailableError(
                f"HANA connection pool is saturated ({self._max_total} connections in use); "
                "raise HANA_POOL_SIZE or retry shortly."
            )
        with self._lock:
            self._created += 1
        try:
            return self._connect()
        except Exception as exc:
            with self._lock:
                self._created -= 1
            self._slots.release()
            raise SapUnavailableError(f"HANA connection failed: {exc}") from exc

    def _release(self, conn) -> None:
        if conn is None:
            return
        healthy = False
        try:
            healthy = bool(conn.isconnected())
        except Exception:
            healthy = False
        if healthy:
            try:
                self._pool.put_nowait(conn)
                return
            except queue.Full:
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

    def create_entity(self, table_or_entity: str, data: dict) -> dict:
        """Create a new entity in SAP by delegating to the OData Service Layer.

        Writes must go through the Service Layer so B1 business logic (numbering
        ranges, defaults, field validation, activation) runs; even when the read
        path is direct HANA SQL we never INSERT from here.  The backend is the
        shared per-tenant instance (a fresh one per write used to leak a Service
        Layer session each time).
        """
        from .service_layer import get_service_layer

        return get_service_layer().create_entity(table_or_entity, data)

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
    def ping(self, force: bool = False) -> dict:
        now = time.time()
        if not force and self._ping_cache and now - self._ping_cache[0] < config.HEALTH_CACHE_TTL_S:
            return dict(self._ping_cache[1], cached=True)
        started = now
        try:
            info = self._fetch_dicts(
                "SELECT CURRENT_USER AS \"user\", CURRENT_SCHEMA AS \"schema\", "
                "VERSION AS \"version\" FROM SYS.M_DATABASE"
            )
            detail = info[0] if info else {}
            self._verify_schema()
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
                # Never echo driver errors verbatim to the caller: they contain
                # host, port and sometimes the username.
                "error": _safe_error(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }
        self._ping_cache = (time.time(), result)
        return dict(result)

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

    def search_columns(self, keyword: str, limit: int = 40) -> list[dict]:
        """Column-name/comment search across the whole company schema.

        Lives here (rather than reaching into backend._fetch_dicts from the
        router) so the statement, its TOP clause and its bind parameters stay
        next to the catalog they describe.
        """
        self._verify_schema()
        cap = max(1, min(int(limit or 40), 500))
        needle = f"%{(keyword or '').upper()}%"
        return self._fetch_dicts(
            f"SELECT TOP {cap} TABLE_NAME AS \"table\", "
            'COLUMN_NAME AS "column", DATA_TYPE_NAME AS "type", COMMENTS AS "description" '
            "FROM SYS.TABLE_COLUMNS "
            "WHERE SCHEMA_NAME = ? AND (UPPER(COLUMN_NAME) LIKE ? OR UPPER(COMMENTS) LIKE ?) "
            "ORDER BY TABLE_NAME, POSITION",
            [self.schema, needle, needle],
        )

    def row_count(self, table: str) -> int | None:
        try:
            rows = self._fetch_dicts(
                f'SELECT COUNT(*) AS "c" FROM "{self.schema}"."{table.upper()}"'
            )
            return int(rows[0]["c"]) if rows else None
        except Exception:
            return None
