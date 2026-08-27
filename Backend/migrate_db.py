"""Idempotent schema migration + connectivity check for CIRA.

    python migrate_db.py                 # migrate cira.db
    python migrate_db.py --check         # also validate config + probe every SAP source
    python migrate_db.py --require-live  # ...and exit 1 unless a real ERP answered

Only ever ADDs columns and indexes; nothing is dropped or rewritten.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

DB_PATH = Path(config.DATABASE_PATH)

EXPECTED = {
    "company_connections": {
        "id": "INTEGER", "company_db": "VARCHAR", "display_name": "VARCHAR",
        "enabled": "INTEGER", "source_priority": "VARCHAR", "hana_host": "VARCHAR",
        "hana_port": "INTEGER", "hana_user": "VARCHAR", "hana_secret": "VARCHAR",
        "hana_encrypt": "INTEGER", "hana_extra_schemas": "VARCHAR",
        "service_layer_port": "INTEGER", "sl_user": "VARCHAR", "sl_secret": "VARCHAR",
        "sl_use_tls": "INTEGER", "notes": "VARCHAR",
        "created_at": "DATETIME", "updated_at": "DATETIME",
    },
    "chat_sessions": {
        "id": "INTEGER",
        "session_id": "VARCHAR",
        "title": "VARCHAR",
        "employee_id": "VARCHAR",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "chat_messages": {
        "id": "INTEGER",
        "session_id": "VARCHAR",
        "employee_id": "VARCHAR",
        "role": "VARCHAR",
        "content": "TEXT",
        "msg_type": "VARCHAR",
        "data_payload": "TEXT",
        "entity": "TEXT",
        "chart_payload": "TEXT",
        "meta_payload": "TEXT",
        "created_at": "DATETIME",
    },
}

CREATE = {
    # Tenant registry maintained by the admin panel (/admin/connections).
    # `hana_secret` / `sl_secret` hold `env:VAR_NAME` or `enc:<token>` — never a raw
    # password (see credential_store.py), so this table is safe to back up.
    "company_connections": """
        CREATE TABLE IF NOT EXISTS company_connections (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            company_db         VARCHAR NOT NULL UNIQUE,
            display_name       VARCHAR,
            enabled            INTEGER NOT NULL DEFAULT 1,
            source_priority    VARCHAR,
            hana_host          VARCHAR NOT NULL,
            hana_port          INTEGER NOT NULL DEFAULT 30013,
            hana_user          VARCHAR NOT NULL,
            hana_secret        VARCHAR NOT NULL,
            hana_encrypt       INTEGER NOT NULL DEFAULT 1,
            hana_extra_schemas VARCHAR,
            service_layer_port INTEGER DEFAULT 50000,
            sl_user            VARCHAR,
            sl_secret          VARCHAR,
            sl_use_tls         INTEGER NOT NULL DEFAULT 1,
            notes              VARCHAR,
            created_at         DATETIME,
            updated_at         DATETIME
        )
    """,
    "chat_sessions": """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  VARCHAR NOT NULL UNIQUE,
            title       VARCHAR,
            employee_id VARCHAR NOT NULL,
            created_at  DATETIME,
            updated_at  DATETIME
        )
    """,
    "chat_messages": """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    VARCHAR NOT NULL,
            employee_id   VARCHAR NOT NULL,
            role          VARCHAR,
            content       TEXT,
            msg_type      VARCHAR,
            data_payload  TEXT,
            entity        TEXT,
            chart_payload TEXT,
            meta_payload  TEXT,
            created_at    DATETIME
        )
    """,
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_chat_sessions_session_id  ON chat_sessions(session_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_sessions_employee_id ON chat_sessions(employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id  ON chat_messages(session_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_employee_id ON chat_messages(employee_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_emp ON chat_messages(session_id, employee_id)",
]


def migrate() -> None:
    print(f"Database: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")

    for ddl in CREATE.values():
        cur.execute(ddl)
    for ddl in INDEXES:
        cur.execute(ddl)
    conn.commit()

    added = []
    for table, columns in EXPECTED.items():
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if cur.fetchone() is None:
            # Never ALTER a table that does not exist: the first cut of the admin
            # panel added company_connections to EXPECTED but not to CREATE, so
            # `python migrate_db.py` crashed for anyone following the README.
            raise SystemExit(
                f"[MIGRATE] table '{table}' is missing but no CREATE for it exists in "
                "migrate_db.py — add it to CREATE (keep it in sync with database.py)."
            )
        cur.execute(f"PRAGMA table_info({table})")
        existing = {r[1] for r in cur.fetchall()}
        for name, sql_type in columns.items():
            if name not in existing:
                print(f"  [MIGRATE] ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                added.append(f"{table}.{name}")
    conn.commit()

    missing = []
    for table in EXPECTED:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if cur.fetchone() is None:
            missing.append(table)
    if missing:
        raise SystemExit(f"[MIGRATE] still missing tables after migration: {', '.join(missing)}")

    print("\nMigration complete.")
    print(f"  Columns added: {', '.join(added)}" if added else "  Schema already up to date.")
    for table in EXPECTED:
        cur.execute(f"PRAGMA table_info({table})")
        print(f"  {table}: {[r[1] for r in cur.fetchall()]}")
    conn.close()


def check_sap() -> int:
    """Print the effective configuration and which source would answer.

    Returns a process exit code: 1 when the configuration is impossible/unsafe,
    2 when --require-live was asked for and no live ERP answered. The previous
    version always exited 0, so "simulated" looked like success in a deploy script.
    """
    import asyncio

    print("\nConfiguration check")
    fatal, warnings = config.validate()
    for problem in fatal:
        print(f"  [ERROR] {problem}")
    for note in warnings:
        print(f"  [warn ] {note}")
    print(f"  sources enabled : {config.enabled_sources() or 'NONE'}")
    print(f"  company DBs     : {', '.join(sorted(config.TENANTS))}")
    if fatal:
        print("\n  Fix the [ERROR] lines before querying anything.")
        return 1

    from sap import router as sap

    print("\nProbing SAP connectivity ...")
    try:
        info = asyncio.run(sap.health(force=True))
    except Exception as exc:
        print(f"  [ERROR] no backend answered: {exc}")
        return 1
    print(f"  Active backend : {info['active_backend']}")
    print(f"  Schema         : {info['schema']}")
    print(f"  Simulated      : {info['simulated']}")
    print(f"  Tables visible : {info['tables_visible']}")
    for attempt in info.get("attempts", []):
        state = "OK " if attempt.get("ok") else "FAIL"
        print(f"   - [{state}] {attempt.get('candidate', attempt.get('backend'))}: "
              f"{attempt.get('error', 'ok')}")
    if info["simulated"]:
        print("\n  ⚠ SANDBOX DATA — every answer will be labelled SIMULATED.")
        print("    This is not your ERP. Check HANA_* / SAP_B1_* in Backend/.env,")
        print("    then re-run: python ../scripts/diagnose.py --require-live")
        if "--require-live" in sys.argv:
            return 2
    return 0


if __name__ == "__main__":
    migrate()
    code = 0
    if "--check" in sys.argv or "--require-live" in sys.argv:
        code = check_sap()
    raise SystemExit(code)
