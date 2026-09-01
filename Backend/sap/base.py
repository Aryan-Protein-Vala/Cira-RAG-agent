"""Backend interface shared by the HANA, Service Layer and simulator drivers."""

from __future__ import annotations

from typing import Any

from .types_ import ColumnInfo, TableInfo


class DataBackend:
    name: str = "base"
    dialect: str = "hana"
    simulated: bool = False
    schema: str = ""

    # ── lifecycle ────────────────────────────────────────────────────────────
    def ping(self) -> dict:
        """Return {'ok': bool, 'detail': str, 'latency_ms': int, ...}."""
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
