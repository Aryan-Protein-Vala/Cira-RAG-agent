"""Shared dataclasses for the SAP data layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnInfo:
    name: str
    data_type: str = ""
    length: int | None = None
    scale: int | None = None
    nullable: bool = True
    description: str = ""
    position: int = 0

    def as_dict(self) -> dict:
        d = {
            "column": self.name,
            "type": self.data_type,
            "nullable": self.nullable,
        }
        if self.length:
            d["length"] = self.length
        if self.description:
            d["description"] = self.description
        return d

    @property
    def is_numeric(self) -> bool:
        t = (self.data_type or "").upper()
        return any(
            k in t
            for k in (
                "INT",
                "DECIMAL",
                "DOUBLE",
                "REAL",
                "FLOAT",
                "NUMERIC",
                "SMALLDECIMAL",
                "BIGINT",
            )
        )

    @property
    def is_date(self) -> bool:
        t = (self.data_type or "").upper()
        return any(k in t for k in ("DATE", "TIME", "SECONDDATE"))


@dataclass
class TableInfo:
    name: str
    schema: str = ""
    description: str = ""
    kind: str = "TABLE"  # TABLE | VIEW
    row_count: int | None = None
    columns: list[ColumnInfo] = field(default_factory=list)

    def as_dict(self, with_columns: bool = False) -> dict:
        d: dict[str, Any] = {
            "table": self.name,
            "kind": self.kind,
        }
        if self.schema:
            d["schema"] = self.schema
        if self.description:
            d["description"] = self.description
        if self.row_count is not None:
            d["rows"] = self.row_count
        if with_columns:
            d["columns"] = [c.as_dict() for c in self.columns]
        return d


@dataclass
class QueryResult:
    """Outcome of a data query, independent of which backend produced it."""

    ok: bool
    source: str = ""
    backend: str = ""
    entity: str = ""
    table: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    total_available: int | None = None
    truncated: bool = False
    sql: str = ""
    simulated: bool = False
    elapsed_ms: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "source": self.source,
            "backend": self.backend,
            "entity": self.entity,
            "table": self.table,
            "columns": self.columns,
            "data": self.rows,
            "count": self.row_count,
            "total_available": self.total_available,
            "truncated": self.truncated,
            "sql": self.sql,
            "simulated": self.simulated,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "warnings": self.warnings,
        }


class SapDataError(RuntimeError):
    """Raised for user-correctable problems (unknown table/column, bad SQL...)."""


class SapUnavailableError(RuntimeError):
    """Raised when a backend cannot be reached at all."""
