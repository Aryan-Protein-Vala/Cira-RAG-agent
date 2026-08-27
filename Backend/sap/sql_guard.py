"""Read-only *and* scoped SQL guard + a small dialect bridge.

The agent is allowed to write raw SQL (that is what makes "ask anything about
any table" possible), so every statement is validated here before it reaches a
database connection:

* exactly one statement
* it must be a SELECT (or a WITH ... SELECT)
* no DML/DDL/DCL/procedure calls, even in a sub-query
* every qualified table reference must live in an allowed schema — this is the
  part that was missing: the guard used to accept `SELECT * FROM "SYS"."USERS"`,
  which on a SYSTEM connection hands out password hashes
* a row limit is always injected when the author forgot one, in the syntax the
  *target* dialect understands (LIMIT is not valid T-SQL)

The SQL is also re-bound to the driver's paramstyle here instead of with a
blind `sql.replace("?", "%s")` at execute time, which used to corrupt literal
question marks inside string literals.
"""

from __future__ import annotations

import re

from .types_ import SapDataError

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")

FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "DROP", "CREATE", "ALTER", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "CALL", "EXEC", "EXECUTE", "PROCEDURE", "FUNCTION", "TRIGGER",
    "IMPORT", "EXPORT", "LOAD", "UNLOAD", "BACKUP", "RESTORE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "SET", "ALTERSYSTEM",
    "CONNECT", "DISCONNECT", "SHUTDOWN", "KILL",
}

# Locking / row-targeting clauses that a read-only statement has no business
# containing.  Matched as phrases so the *words* stay usable in identifiers
# (e.g. a T-SQL `FOR JSON` clause or a column called "SETTINGS_FOR").
FORBIDDEN_PHRASES = {
    re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE),
    re.compile(r"\bFOR\s+SHARE\b", re.IGNORECASE),
    re.compile(r"\bWITH\s+(?:UPDLOCK|READPAST|XLOCK|NOLOCK\s*,)\b", re.IGNORECASE),
    re.compile(r"\bINTO\s+@", re.IGNORECASE),
}

# HANA catalog views that are safe to read (metadata only). Anything else under
# SYS is denied: SYS.USERS / SYS.DB_USERS hold password hashes, SYS.CONFIGURATION
# and SYS.SYSTEM_PARAMETERS expose server settings, SYS.LICENSE the install.
CATALOG_ALLOWLIST = {
    "SYS.TABLES", "SYS.VIEWS", "SYS.TABLE_COLUMNS", "SYS.VIEW_COLUMNS",
    "SYS.COLUMNS", "SYS.SCHEMAS", "SYS.COMMENTS", "SYS.INDEXES",
    "SYS.CONSTRAINTS", "SYS.KEY_COLUMN_USAGE", "SYS.REFERENTIAL_CONSTRAINTS",
    "SYS.SEQUENCES", "SYS.SYNONYMS", "SYS.FUNCTIONS", "SYS.PROCEDURES",
    "SYS.TRIGGERS", "SYS.UDFS", "SYS.UDTS", "SYS.DEPENDENCIES",
    "SYS.OBJECTS", "SYS.OBJECT_INFO", "SYS.M_DATABASE", "SYS.M_TABLES",
    "SYS.M_TABLE_COLUMNS", "SYS.M_SERVICES", "SYS.M_SYSTEM_OVERVIEW",
    "SYS.TABLE_STATISTICS", "SYS.JDBC_DRIVER",
}

# Qualified reference after FROM/JOIN: "S"."T", [S].[T], S.T, with up to 3 parts.
_IDENT = r'(?:\[[^\]]+\]|"[^"]+"|`[^`]+`|[A-Za-z_@#][\w@$#]*)'
_QUALIFIED = re.compile(
    rf"(?P<full>{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}})",
)
_AFTER_FROM = re.compile(rf"\b(?:FROM|JOIN|INTO|UPDATE)\b\s*(?P<ref>{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}})?", re.IGNORECASE)


def strip_noise(sql: str) -> str:
    """Remove comments and string literals so keyword scanning is reliable."""
    cleaned = _BLOCK_COMMENT.sub(" ", sql)
    cleaned = _LINE_COMMENT.sub(" ", cleaned)
    cleaned = _STRING_LITERAL.sub("''", cleaned)
    return cleaned


def _unquote(part: str) -> str:
    part = (part or "").strip()
    if len(part) >= 2 and part[0] == '"' and part[-1] == '"':
        return part[1:-1].replace('""', '"').strip()
    if part.startswith("[") and part.endswith("]"):
        return part[1:-1].strip()
    if len(part) >= 2 and part[0] == "`" and part[-1] == "`":
        return part[1:-1].strip()
    return part


def table_references(sql: str) -> list[tuple[str | None, str]]:
    """(schema_or_database, table) for every FROM/JOIN target in the statement.

    Only *qualified* references are reported; an unqualified `FROM "OINV"` is the
    caller's own schema and gets normalised by the router.
    """
    scan = strip_noise(sql)
    out: list[tuple[str | None, str]] = []
    for match in _AFTER_FROM.finditer(scan):
        ref = (match.group("ref") or "").strip()
        if not ref:
            continue  # FROM (subquery) / FROM dual-style — nothing to scope-check
        parts = [p.strip() for p in re.split(r"\s*\.\s*", ref) if p.strip()]
        parts = [_unquote(p) for p in parts]
        if len(parts) == 1:
            out.append((None, parts[0].upper()))
        elif len(parts) >= 2:
            # 2 parts -> schema.table ; 3 parts -> database.schema.table
            out.append((parts[-2].upper(), parts[-1].upper()))
    return out


def enforce_scope(sql: str, allowed_schemas: list[str], *, allow_unqualified: bool = True) -> str:
    """Reject any FROM/JOIN that reaches outside the caller's company schema.

    `allowed_schemas` is compared case-insensitively.  Catalog views under SYS are
    allowed only when listed in CATALOG_ALLOWLIST.
    """
    allowed = {(s or "").strip().upper() for s in allowed_schemas if (s or "").strip()}
    refs = table_references(sql)
    if not refs:
        return sql
    for schema, table in refs:
        if schema is None:
            if not allow_unqualified:
                raise SapDataError(
                    f"Table '{table}' must be qualified with the company schema."
                )
            continue
        if schema in allowed:
            continue
        if f"{schema}.{table}" in CATALOG_ALLOWLIST:
            continue
        raise SapDataError(
            f"Access to \"{schema}\".\"{table}\" is not allowed: only the company "
            f"schema ({', '.join(sorted(allowed))}) and the read-only catalog views "
            "may be queried. Drop the schema prefix to query the company database."
        )
    return sql


def ensure_read_only(sql: str) -> str:
    """Validate and normalise a statement. Returns the cleaned statement."""
    if not sql or not sql.strip():
        raise SapDataError("Empty SQL statement.")

    statement = sql.strip()
    scan = strip_noise(statement)

    # Reject statement stacking ("SELECT 1; DROP TABLE X")
    if len([part for part in scan.split(";") if part.strip()]) > 1:
        raise SapDataError("Only a single SELECT statement is allowed.")

    statement = statement.rstrip().rstrip(";").rstrip()
    scan = strip_noise(statement)

    first = scan.lstrip().split(None, 1)
    head = (first[0] if first else "").upper()
    if head not in {"SELECT", "WITH"}:
        raise SapDataError("Only read-only SELECT/WITH statements are allowed.")

    words = {w.upper() for w in re.findall(r"[A-Za-z_]+", scan)}
    hit = words & FORBIDDEN
    # "SET" is legal inside "OFFSET"/"RESULTSET" tokens; identifiers keep their
    # underscores (so "U_SET_FLAG" is one token) — a bare hit is a genuine risk.
    if hit:
        raise SapDataError(
            "Statement rejected: read-only access only "
            f"(disallowed keyword: {', '.join(sorted(hit))})."
        )
    for phrase in FORBIDDEN_PHRASES:
        found = phrase.search(scan)
        if found:
            raise SapDataError(
                "Statement rejected: locking/hint clauses are not allowed "
                f"({found.group(0).strip()!r})."
            )
    if not re.search(r"\bFROM\b", scan, re.IGNORECASE):
        raise SapDataError(
            "Statement rejected: every query must read FROM a table in the company "
            "schema (SELECT of literals/system functions is not available)."
        )
    return statement


# ── paramstyle rebinding ────────────────────────────────────────────────────
def rebind_param_markers(sql: str, style: str) -> str:
    """Rewrite the canonical `?` markers to `style` ('qmark'|'format') safely.

    String literals and quoted identifiers are skipped, and for 'format' any
    stray `%` outside a marker is doubled — pymssql/pyodbc build the final query
    with `%`, so an unescaped `%` inside a LIKE pattern raises or corrupts data.
    """
    if style not in {"qmark", "format"}:
        raise ValueError(f"unsupported paramstyle {style!r}")
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":  # string literal ('' escapes)
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            literal = sql[i:j]
            # A `?` inside a literal is data, never a marker; but a literal `%`
            # still has to be doubled because pymssql builds the final statement
            # with `%`-interpolation even for literals in the text.
            if style == "format":
                literal = literal.replace("%", "%%")
            out.append(literal)
            i = j
            continue
        if ch in '"[':
            close = '"' if ch == '"' else "]"
            j = sql.find(close, i + 1)
            j = n if j == -1 else j + 1
            out.append(sql[i:j])
            i = j
            continue
        if ch == "?":
            out.append("%s" if style == "format" else "?")
        elif ch == "%":
            # Already a marker? keep it; otherwise escape for %-interpolating drivers.
            if style == "format" and i + 1 < n and sql[i + 1] == "s":
                out.append("%s")
                i += 2
                continue
            out.append("%%" if style == "format" else "%")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# ── row limits per dialect ──────────────────────────────────────────────────
def has_row_limit(sql: str) -> bool:
    scan = strip_noise(sql).upper()
    return bool(
        re.search(r"\bSELECT\s+(?:DISTINCT\s+)?TOP\s+\d+", scan)
        or re.search(r"\bLIMIT\s+\d+", scan)
        or re.search(r"\bFETCH\s+(?:FIRST|NEXT)\b", scan)
        or re.search(r"\bOFFSET\s+\d+\s+ROWS\b", scan)
    )


_ORDER_BY_TAIL = re.compile(
    r"\bORDER\s+BY\b(?![\s\S]*\b(GROUP\s+BY|HAVING|WINDOW|UNION)\b)[\s\S]*$",
    re.IGNORECASE,
)


def apply_row_limit(sql: str, limit: int, dialect: str) -> str:
    """Force a row cap onto a statement that does not already have one."""
    limit = int(limit)
    if limit <= 0 or has_row_limit(sql):
        return sql
    if dialect == "sqlite":
        return f"{sql}\nLIMIT {limit}"
    if dialect == "mssql":
        # T-SQL has no LIMIT. OFFSET/FETCH is the only form that survives an
        # existing ORDER BY, and it *requires* one.
        if _ORDER_BY_TAIL.search(sql):
            return f"{sql}\nOFFSET 0 ROWS\nFETCH NEXT {limit} ROWS ONLY"
        return (
            f"{sql}\nORDER BY (SELECT NULL)\n"
            f"OFFSET 0 ROWS\nFETCH NEXT {limit} ROWS ONLY"
        )
    if dialect == "odbc":
        return f"{sql}\nOFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
    # HANA accepts both LIMIT and TOP; wrapping keeps ORDER BY / UNION intact.
    return f"SELECT * FROM (\n{sql}\n) LIMIT {limit}"


# ── HANA -> SQLite translation (offline simulator only) ──────────────────────
_TOP_RE = re.compile(r"\bSELECT\s+(DISTINCT\s+)?TOP\s+(\d+)\s+", re.IGNORECASE)
_FUNCS = [
    (re.compile(r"\bYEAR\s*\(", re.IGNORECASE), "__YEAR__("),
    (re.compile(r"\bMONTH\s*\(", re.IGNORECASE), "__MONTH__("),
    (re.compile(r"\bDAY\s*\(", re.IGNORECASE), "__DAY__("),
    (re.compile(r"\bIFNULL\s*\(", re.IGNORECASE), "IFNULL("),
    (re.compile(r"\bCOALESCE\s*\(", re.IGNORECASE), "COALESCE("),
    (re.compile(r"\bCURRENT_DATE\b", re.IGNORECASE), "date('now')"),
    (re.compile(r"\bCURRENT_TIMESTAMP\b", re.IGNORECASE), "datetime('now')"),
    (re.compile(r"\bNOW\s*\(\s*\)", re.IGNORECASE), "datetime('now')"),
    (re.compile(r"\bTO_DATE\s*\(", re.IGNORECASE), "date("),
    (re.compile(r"\bTO_VARCHAR\s*\(", re.IGNORECASE), "CAST_TEXT("),
    (re.compile(r"\bTO_DECIMAL\s*\(", re.IGNORECASE), "CAST_REAL("),
    (re.compile(r"\bDOUBLE\s*\(", re.IGNORECASE), "CAST_REAL("),
    (re.compile(r"\bNVL\s*\(", re.IGNORECASE), "IFNULL("),
]


def translate_for_sqlite(sql: str, schema: str) -> str:
    """Best-effort rewrite of HANA SQL so the offline sandbox understands it."""
    out = sql

    # "SCHEMA"."TABLE" / SCHEMA.TABLE  ->  "TABLE"
    out = re.sub(rf'"{re.escape(schema)}"\s*\.\s*', "", out, flags=re.IGNORECASE)
    out = re.sub(rf"\b{re.escape(schema)}\s*\.\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r'"SYSTEM"\s*\.\s*', "", out, flags=re.IGNORECASE)
    # The sandbox is one flat SQLite file: any other schema prefix is dropped.
    out = re.sub(r'"([A-Za-z_@][\w$#]*)"\s*\.\s*(?=")', "", out)

    # SELECT TOP n  ->  ... LIMIT n
    limit_value: int | None = None

    def _strip_top(match: re.Match) -> str:
        nonlocal limit_value
        limit_value = int(match.group(2))
        distinct = match.group(1) or ""
        return f"SELECT {distinct}"

    out = _TOP_RE.sub(_strip_top, out, count=1)

    for pattern, repl in _FUNCS:
        out = pattern.sub(repl, out)

    # SQLite has no YEAR()/MONTH()/DAY(): use strftime
    out = re.sub(r"__YEAR__\(([^()]*)\)", r"CAST(strftime('%Y', \1) AS INTEGER)", out)
    out = re.sub(r"__MONTH__\(([^()]*)\)", r"CAST(strftime('%m', \1) AS INTEGER)", out)
    out = re.sub(r"__DAY__\(([^()]*)\)", r"CAST(strftime('%d', \1) AS INTEGER)", out)
    out = re.sub(r"CAST_TEXT\(([^()]*)\)", r"CAST(\1 AS TEXT)", out)
    out = re.sub(r"CAST_REAL\(([^()]*)\)", r"CAST(\1 AS REAL)", out)

    if limit_value is not None and not re.search(r"\bLIMIT\s+\d+", out, re.IGNORECASE):
        out = f"{out}\nLIMIT {limit_value}"
    return out
