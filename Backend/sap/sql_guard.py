"""Read-only SQL guard + small HANA -> SQLite dialect bridge.

The agent is allowed to write raw SQL (that is what makes "ask anything about
any table" possible), so every statement is validated here before it reaches a
database connection:

* exactly one statement
* it must be a SELECT (or a WITH ... SELECT)
* no DML/DDL/DCL/procedure calls, even in a sub-query
* a row limit is always injected when the author forgot one
"""

from __future__ import annotations

import re

from .types_ import SapDataError

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
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


def strip_noise(sql: str) -> str:
    """Remove comments and string literals so keyword scanning is reliable."""
    cleaned = _BLOCK_COMMENT.sub(" ", sql)
    cleaned = _LINE_COMMENT.sub(" ", cleaned)
    cleaned = _STRING_LITERAL.sub("''", cleaned)
    return cleaned


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
    # "SET" is legal inside "OFFSET"/"RESULTSET" tokens, the regex split above
    # already separates words so a bare SET is a genuine hit.
    if hit:
        raise SapDataError(
            "Statement rejected: read-only access only "
            f"(disallowed keyword: {', '.join(sorted(hit))})."
        )
    return statement


def has_row_limit(sql: str) -> bool:
    scan = strip_noise(sql).upper()
    return bool(
        re.search(r"\bSELECT\s+TOP\s+\d+", scan)
        or re.search(r"\bLIMIT\s+\d+", scan)
        or re.search(r"\bFETCH\s+FIRST\b", scan)
    )


def apply_row_limit(sql: str, limit: int, dialect: str) -> str:
    """Force a row cap onto a statement that does not already have one."""
    if limit <= 0 or has_row_limit(sql):
        return sql
    if dialect == "sqlite":
        return f"{sql}\nLIMIT {int(limit)}"
    # HANA: wrap so we never fight with the author's ORDER BY / UNION
    return f"SELECT * FROM (\n{sql}\n) LIMIT {int(limit)}"


# ── HANA -> SQLite translation (offline simulator only) ──────────────────────
_TOP_RE = re.compile(r"\bSELECT\s+(DISTINCT\s+)?TOP\s+(\d+)\s+", re.I)
_FUNCS = [
    (re.compile(r"\bYEAR\s*\(", re.I), "__YEAR__("),
    (re.compile(r"\bMONTH\s*\(", re.I), "__MONTH__("),
    (re.compile(r"\bDAY\s*\(", re.I), "__DAY__("),
    (re.compile(r"\bIFNULL\s*\(", re.I), "IFNULL("),
    (re.compile(r"\bCURRENT_DATE\b", re.I), "date('now')"),
    (re.compile(r"\bCURRENT_TIMESTAMP\b", re.I), "datetime('now')"),
    (re.compile(r"\bNOW\s*\(\s*\)", re.I), "datetime('now')"),
    (re.compile(r"\bTO_DATE\s*\(", re.I), "date("),
    (re.compile(r"\bTO_VARCHAR\s*\(", re.I), "CAST_TEXT("),
    (re.compile(r"\bTO_DECIMAL\s*\(", re.I), "CAST_REAL("),
    (re.compile(r"\bDOUBLE\s*\(", re.I), "CAST_REAL("),
]


def translate_for_sqlite(sql: str, schema: str) -> str:
    """Best-effort rewrite of HANA SQL so the offline sandbox understands it."""
    out = sql

    # "SCHEMA"."TABLE" / SCHEMA.TABLE  -> "TABLE"
    out = re.sub(rf'"{re.escape(schema)}"\s*\.\s*', "", out, flags=re.I)
    out = re.sub(rf"\b{re.escape(schema)}\s*\.\s*", "", out, flags=re.I)
    out = re.sub(r'"SYSTEM"\s*\.\s*', "", out, flags=re.I)

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

    if limit_value is not None and not re.search(r"\bLIMIT\s+\d+", out, re.I):
        out = f"{out}\nLIMIT {limit_value}"
    return out
