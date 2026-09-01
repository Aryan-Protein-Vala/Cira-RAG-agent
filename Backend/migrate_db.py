"""Idempotent schema migration + connectivity check for CIRA.

    python migrate_db.py            # migrate cira.db
    python migrate_db.py --check    # also probe SAP HANA / Service Layer

Only ever ADDs columns and indexes; nothing is dropped or rewritten.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

DB_PATH = Path(config.DATABASE_PATH)

EXPECTED = {
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
        cur.execute(f"PRAGMA table_info({table})")
        existing = {r[1] for r in cur.fetchall()}
        for name, sql_type in columns.items():
            if name not in existing:
                print(f"  [MIGRATE] ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                added.append(f"{table}.{name}")
    conn.commit()

    print("\nMigration complete.")
    print(f"  Columns added: {', '.join(added)}" if added else "  Schema already up to date.")
    for table in EXPECTED:
        cur.execute(f"PRAGMA table_info({table})")
        print(f"  {table}: {[r[1] for r in cur.fetchall()]}")
    conn.close()


def check_sap() -> None:
    import asyncio

    from sap import router as sap

    print("\nProbing SAP connectivity ...")
    info = asyncio.run(sap.health())
    print(f"  Active backend : {info['active_backend']}")
    print(f"  Schema         : {info['schema']}")
    print(f"  Simulated      : {info['simulated']}")
    print(f"  Tables visible : {info['tables_visible']}")
    for attempt in info.get("attempts", []):
        state = "OK " if attempt.get("ok") else "FAIL"
        print(f"   - [{state}] {attempt.get('candidate', attempt.get('backend'))}: "
              f"{attempt.get('error', attempt.get('host', ''))}")
    if info["simulated"]:
        print("\n  ⚠ Running on the offline sandbox. Check HANA_* / SAP_B1_* in Backend/.env,")
        print("    and confirm the HANA SQL port is reachable from this host:")
        print(f"      python -c \"import socket;print(socket.create_connection(('{config.HANA_HOST}',{config.HANA_PORT}),5))\"")


if __name__ == "__main__":
    migrate()
    if "--check" in sys.argv:
        check_sap()
