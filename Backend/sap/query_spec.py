"""Structured, injection-safe SELECT builder.

The agent describes *what* it wants (table, filters, grouping, sorting) and
this module renders dialect-correct SQL:

* identifiers are validated against the live catalog and quoted, so a
  hallucinated / hostile column name can never reach the database
* every value is bound as a parameter (never string-interpolated)
* a row limit is always present
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import entities
from .types_ import ColumnInfo, SapDataError

OPERATORS = {
    "eq": "=", "=": "=", "==": "=",
    "ne": "<>", "!=": "<>", "<>": "<>",
    "gt": ">", ">": ">",
    "gte": ">=", ">=": ">=",
    "lt": "<", "<": "<",
    "lte": "<=", "<=": "<=",
    "like": "LIKE",
    "contains": "LIKE",
    "startswith": "LIKE",
    "endswith": "LIKE",
    "in": "IN",
    "notin": "NOT IN",
    "between": "BETWEEN",
    "isnull": "IS NULL",
    "notnull": "IS NOT NULL",
}

AGG_FUNCS = {"sum", "count", "avg", "min", "max", "count_distinct"}

_IDENT_RE = re.compile(r"^[A-Za-z_@#][A-Za-z0-9_@#$.]*$")


@dataclass
class Filter:
    column: str
    op: str = "eq"
    value: Any = None
    values: list[Any] | None = None


@dataclass
class Aggregate:
    func: str
    column: str = "*"
    alias: str = ""


@dataclass
class Order:
    column: str
    direction: str = "desc"


@dataclass
class QuerySpec:
    table: str
    columns: list[str] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    search_text: str = ""
    search_columns: list[str] = field(default_factory=list)
    date_column: str = ""
    date_from: str = ""
    date_to: str = ""
    year: int | None = None
    group_by: list[str] = field(default_factory=list)
    aggregates: list[Aggregate] = field(default_factory=list)
    order_by: list[Order] = field(default_factory=list)
    limit: int = 500
    distinct: bool = False


class ColumnResolver:
    """Case-insensitive lookup of real column names for one table."""

    def __init__(self, columns: Iterable[ColumnInfo]):
        self.columns: list[ColumnInfo] = list(columns)
        self._by_lower = {c.name.lower(): c for c in self.columns}

    def exists(self, name: str) -> bool:
        return name.lower() in self._by_lower

    def resolve(self, name: str) -> ColumnInfo:
        col = self._by_lower.get((name or "").strip().lower())
        if col is None:
            close = self.suggest(name)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            raise SapDataError(f"Unknown column '{name}'.{hint}")
        return col

    def suggest(self, name: str, limit: int = 6) -> list[str]:
        needle = (name or "").lower()
        if not needle:
            return []
        scored = []
        for col in self.columns:
            low = col.name.lower()
            if needle in low or low in needle:
                scored.append((0, col.name))
            elif needle[:3] and low.startswith(needle[:3]):
                scored.append((1, col.name))
            elif needle in (col.description or "").lower():
                scored.append((2, col.name))
        scored.sort()
        return [n for _, n in scored[:limit]]

    def numeric(self) -> list[ColumnInfo]:
        return [c for c in self.columns if c.is_numeric]

    def textual(self) -> list[ColumnInfo]:
        return [c for c in self.columns if not c.is_numeric and not c.is_date]

    def dates(self) -> list[ColumnInfo]:
        return [c for c in self.columns if c.is_date]


def _q(identifier: str) -> str:
    if not _IDENT_RE.match(identifier or ""):
        raise SapDataError(f"Illegal identifier: {identifier!r}")
    return '"' + identifier.replace('"', "") + '"'


def _alias_for(agg: Aggregate) -> str:
    if agg.alias:
        return re.sub(r"[^A-Za-z0-9_ ]", "", agg.alias)[:40] or "value"
    if agg.func == "count" and agg.column in ("*", ""):
        return "Count"
    return f"{agg.func.replace('_', ' ').title().replace(' ', '')}_{agg.column}"[:40]


def _agg_sql(agg: Aggregate, resolver: ColumnResolver) -> str:
    func = agg.func.lower().strip()
    if func not in AGG_FUNCS:
        raise SapDataError(f"Unsupported aggregate '{agg.func}'. Use one of {sorted(AGG_FUNCS)}.")
    if func == "count" and agg.column in ("*", "", None):
        return "COUNT(*)"
    col = resolver.resolve(agg.column)
    if func == "count_distinct":
        return f"COUNT(DISTINCT {_q(col.name)})"
    return f"{func.upper()}({_q(col.name)})"


def choose_default_columns(table: str, resolver: ColumnResolver, max_cols: int = 14) -> list[str]:
    """Pick a sensible, human-facing column set instead of SELECT *."""
    preferred = [c for c in entities.preferred_columns(table) if resolver.exists(c)]
    if preferred:
        return [resolver.resolve(c).name for c in preferred][:max_cols]

    picked: list[str] = []
    # keys first, then names/descriptions, then dates, then amounts
    def _add(cols: list[ColumnInfo]):
        for c in cols:
            if len(picked) >= max_cols:
                return
            if c.name in picked or entities.is_noisy(c.name):
                continue
            picked.append(c.name)

    lower = {c.name.lower(): c for c in resolver.columns}
    key_like = [c for n, c in lower.items() if n.endswith("code") or n.endswith("num")
                or n in {"docentry", "transid", "abvalue", "empid", "linenum"}]
    name_like = [c for n, c in lower.items() if "name" in n or "dscription" in n
                 or "description" in n or n in {"memo", "subject", "comments"}]
    _add(key_like)
    _add(name_like)
    _add(resolver.dates())
    _add(resolver.numeric())
    _add(resolver.columns)
    return picked[:max_cols]


def build_select(
    spec: QuerySpec,
    resolver: ColumnResolver,
    dialect: str,
    schema: str = "",
) -> tuple[str, list[Any]]:
    """Render the SQL string + bound parameters for a spec."""
    table = spec.table.upper()
    params: list[Any] = []

    grouped = bool(spec.group_by or spec.aggregates)

    select_parts: list[str] = []
    if grouped:
        for gcol in spec.group_by:
            col = resolver.resolve(gcol)
            select_parts.append(_q(col.name))
        for agg in spec.aggregates:
            select_parts.append(f"{_agg_sql(agg, resolver)} AS {_q(_alias_for(agg))}")
        if not spec.aggregates:
            select_parts.append("COUNT(*) AS \"Count\"")
    else:
        cols = spec.columns or choose_default_columns(table, resolver)
        for c in cols:
            col = resolver.resolve(c)
            select_parts.append(_q(col.name))
        if not select_parts:
            select_parts.append("*")

    where: list[str] = []

    for f in spec.filters:
        col = resolver.resolve(f.column)
        op_key = (f.op or "eq").lower().strip()
        if op_key not in OPERATORS:
            raise SapDataError(f"Unsupported operator '{f.op}'.")
        sql_op = OPERATORS[op_key]
        name = _q(col.name)

        if op_key == "isnull":
            where.append(f"{name} IS NULL")
            continue
        if op_key == "notnull":
            where.append(f"{name} IS NOT NULL")
            continue

        if op_key in ("in", "notin"):
            raw_values = f.values if f.values is not None else f.value
            if not isinstance(raw_values, (list, tuple)):
                raw_values = [raw_values]
            vals = [entities.encode_value(col.name, v) for v in raw_values if v is not None]
            if not vals:
                continue
            placeholders = ", ".join("?" for _ in vals)
            where.append(f"{name} {sql_op} ({placeholders})")
            params.extend(vals)
            continue

        if op_key == "between":
            raw_values = f.values if f.values is not None else f.value
            if not isinstance(raw_values, (list, tuple)) or len(raw_values) != 2:
                raise SapDataError("'between' needs exactly two values.")
            where.append(f"{name} BETWEEN ? AND ?")
            params.extend(list(raw_values))
            continue

        value = f.value if f.value is not None else (f.values[0] if f.values else None)
        if value is None:
            continue

        if op_key in ("contains", "like", "startswith", "endswith"):
            text = str(value)
            if op_key == "contains":
                pattern = f"%{text}%"
            elif op_key == "startswith":
                pattern = f"{text}%"
            elif op_key == "endswith":
                pattern = f"%{text}"
            else:
                pattern = text if "%" in text else f"%{text}%"
            where.append(f"UPPER({name}) LIKE UPPER(?)")
            params.append(pattern)
            continue

        encoded = entities.encode_value(col.name, value)
        if isinstance(encoded, str) and not col.is_numeric and not col.is_date and op_key == "eq":
            # B1 stores padded/cased codes inconsistently — compare case-insensitively
            where.append(f"UPPER(TRIM({name})) = UPPER(?)")
            params.append(str(encoded).strip())
        else:
            where.append(f"{name} {sql_op} ?")
            params.append(encoded)

    # Free-text search across text columns
    if spec.search_text:
        targets = spec.search_columns or [
            c.name for c in resolver.textual()
            if not entities.is_noisy(c.name)
            and (c.length or 0) >= 3
        ][:8]
        ors = []
        for cname in targets:
            if not resolver.exists(cname):
                continue
            ors.append(f"UPPER({_q(resolver.resolve(cname).name)}) LIKE UPPER(?)")
            params.append(f"%{spec.search_text}%")
        if ors:
            where.append("(" + " OR ".join(ors) + ")")

    # Date window
    date_col = spec.date_column
    if not date_col:
        sem = entities.semantics_for(table)
        cand = sem.get("date", "")
        if cand and resolver.exists(cand):
            date_col = cand
        elif resolver.dates():
            date_col = resolver.dates()[0].name
    if date_col and resolver.exists(date_col):
        dq = _q(resolver.resolve(date_col).name)
        if spec.year:
            year_fn = f"YEAR({dq})" if dialect != "sqlite" else f"CAST(strftime('%Y', {dq}) AS INTEGER)"
            where.append(f"{year_fn} = ?")
            params.append(int(spec.year))
        if spec.date_from:
            where.append(f"{dq} >= ?")
            params.append(spec.date_from)
        if spec.date_to:
            where.append(f"{dq} <= ?")
            params.append(spec.date_to)
    elif spec.year or spec.date_from or spec.date_to:
        raise SapDataError(
            f"Table {table} has no date column to filter on; drop the date/year filter."
        )

    # ORDER BY (aliases from aggregates are allowed)
    alias_names = {_alias_for(a).lower(): _alias_for(a) for a in spec.aggregates}
    order_parts: list[str] = []
    for o in spec.order_by:
        direction = "DESC" if str(o.direction).lower().startswith("d") else "ASC"
        key = (o.column or "").lower()
        if key in alias_names:
            order_parts.append(f"{_q(alias_names[key])} {direction}")
        elif key in {"count", "value"} and grouped and not spec.aggregates:
            order_parts.append(f'"Count" {direction}')
        else:
            col = resolver.resolve(o.column)
            if grouped and col.name not in spec.group_by:
                # ordering by a non-grouped column is invalid — aggregate it
                order_parts.append(f"SUM({_q(col.name)}) {direction}")
            else:
                order_parts.append(f"{_q(col.name)} {direction}")

    if not order_parts:
        if grouped and (spec.aggregates or True):
            first_measure = (
                _q(_alias_for(spec.aggregates[0])) if spec.aggregates else '"Count"'
            )
            order_parts.append(f"{first_measure} DESC")
        else:
            sem = entities.semantics_for(table)
            for cand in (sem.get("date"), sem.get("key")):
                if cand and resolver.exists(cand):
                    order_parts.append(f"{_q(resolver.resolve(cand).name)} DESC")
                    break

    limit = max(1, int(spec.limit or 500))

    distinct = "DISTINCT " if spec.distinct and not grouped else ""
    cols_sql = ", ".join(select_parts)
    qualified = f"{_q(schema)}.{_q(table)}" if schema and dialect != "sqlite" else _q(table)

    if dialect == "sqlite":
        sql = f"SELECT {distinct}{cols_sql}\nFROM {qualified}"
    else:
        sql = f"SELECT TOP {limit} {distinct}{cols_sql}\nFROM {qualified}"

    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    if spec.group_by:
        sql += "\nGROUP BY " + ", ".join(_q(resolver.resolve(g).name) for g in spec.group_by)
    if order_parts:
        sql += "\nORDER BY " + ", ".join(order_parts)
    if dialect == "sqlite":
        sql += f"\nLIMIT {limit}"

    return sql, params


def spec_from_payload(payload: dict) -> QuerySpec:
    """Build a QuerySpec from the loose JSON an LLM produces."""
    table = entities.normalise_table_name(str(payload.get("table") or payload.get("entity") or ""))
    if not table:
        raise SapDataError("A table or entity name is required.")

    filters: list[Filter] = []
    raw_filters = payload.get("filters") or []
    if isinstance(raw_filters, dict):
        raw_filters = [{"column": k, "op": "eq", "value": v} for k, v in raw_filters.items()]
    for f in raw_filters:
        if not isinstance(f, dict):
            continue
        column = f.get("column") or f.get("field") or f.get("name")
        if not column:
            continue
        filters.append(
            Filter(
                column=str(column),
                op=str(f.get("op") or f.get("operator") or "eq"),
                value=f.get("value"),
                values=f.get("values"),
            )
        )

    aggregates: list[Aggregate] = []
    for a in payload.get("aggregates") or []:
        if isinstance(a, str):
            # "sum(DocTotal)" shorthand
            m = re.match(r"\s*(\w+)\s*\(\s*([\w@#*]+)\s*\)\s*", a)
            if m:
                aggregates.append(Aggregate(func=m.group(1).lower(), column=m.group(2)))
            continue
        if isinstance(a, dict):
            aggregates.append(
                Aggregate(
                    func=str(a.get("func") or a.get("function") or "sum").lower(),
                    column=str(a.get("column") or a.get("field") or "*"),
                    alias=str(a.get("alias") or ""),
                )
            )

    orders: list[Order] = []
    raw_order = payload.get("order_by") or payload.get("sort") or []
    if isinstance(raw_order, str):
        raw_order = [raw_order]
    for o in raw_order:
        if isinstance(o, str):
            parts = o.split()
            orders.append(Order(column=parts[0], direction=parts[1] if len(parts) > 1 else "desc"))
        elif isinstance(o, dict):
            orders.append(
                Order(
                    column=str(o.get("column") or o.get("field") or ""),
                    direction=str(o.get("direction") or o.get("dir") or "desc"),
                )
            )

    group_by = payload.get("group_by") or []
    if isinstance(group_by, str):
        group_by = [group_by]

    columns = payload.get("columns") or []
    if isinstance(columns, str):
        columns = [c.strip() for c in columns.split(",") if c.strip()]

    return QuerySpec(
        table=table,
        columns=[str(c) for c in columns],
        filters=filters,
        search_text=str(payload.get("search") or payload.get("search_text") or ""),
        search_columns=list(payload.get("search_columns") or []),
        date_column=str(payload.get("date_column") or ""),
        date_from=str(payload.get("date_from") or ""),
        date_to=str(payload.get("date_to") or ""),
        year=int(payload["year"]) if str(payload.get("year") or "").isdigit() else None,
        group_by=[str(g) for g in group_by],
        aggregates=aggregates,
        order_by=orders,
        limit=int(payload.get("limit") or payload.get("top") or 500),
        distinct=bool(payload.get("distinct")),
    )
