"""Backend interface shared by the HANA, Service Layer, SQL Server and simulator drivers.

Contract, in words, because the previous build checked capabilities with
`hasattr(backend, "create_entity")` (a typo there silently became "not
supported"):

* `dialect`      — "hana" | "mssql" | "sqlite" | "odata"; decides SQL rendering
* `sql_schema`   — schema qualifier to emit in FROM ("" for sqlite / OData)
* `capabilities` — explicit set of what this backend may do ("write", ...)
* `execute()`    — MUST only ever be handed a statement that passed sql_guard
"""

from __future__ import annotations

from typing import Any

from .types_ import ColumnInfo, TableInfo


class DataBackend:
    name: str = "base"
    dialect: str = "hana"
    simulated: bool = False
    schema: str = ""
    capabilities: frozenset[str] = frozenset()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def ping(self, force: bool = False) -> dict:
        """Return {'ok': bool, 'detail': str, 'latency_ms': int, ...}.

        `force=True` re-authenticates; health checks use the cached result so a
        public diagnostics endpoint cannot be turned into an ERP login storm.
        """
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - optional
        return None

    # ── catalog ──────────────────────────────────────────────────────────────
    def list_tables(self, pattern: str = "", include_views: bool = True,
                    limit: int = 1000) -> list[TableInfo]:
        raise NotImplementedError

    def get_columns(self, table: str) -> list[ColumnInfo]:
        raise NotImplementedError

    def table_exists(self, table: str) -> bool:
        return any(t.name.upper() == table.upper() for t in self.list_tables(limit=100000))

    def row_count(self, table: str) -> int | None:
        return None

    # ── data ─────────────────────────────────────────────────────────────────
    def execute(self, sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
        """Run a validated read-only statement. Returns (columns, rows)."""
        raise NotImplementedError

    # ── capability helpers ───────────────────────────────────────────────────
    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def sql_schema(self) -> str:
        """Schema qualifier to emit in FROM clauses (empty = connection default)."""
        return self.schema if self.dialect != "sqlite" else ""

    @property
    def allowed_schemas(self) -> list[str]:
        """Schemas raw SQL may name explicitly; enforced by sql_guard.enforce_scope."""
        return [s for s in (self.schema,) if s]
