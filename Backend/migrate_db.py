"""
Safe idempotent migration for cira.db.
Run this whenever the SQLAlchemy models in database.py change.
It only ADDs missing columns — it never drops or modifies existing ones.
"""
import sqlite3

DB_PATH = "cira.db"

EXPECTED = {
    "chat_sessions": {
        "id":          "INTEGER",
        "session_id":  "VARCHAR",
        "title":       "VARCHAR",
        "employee_id": "VARCHAR",
    },
    "chat_messages": {
        "id":            "INTEGER",
        "session_id":    "VARCHAR",
        "employee_id":   "VARCHAR",
        "role":          "VARCHAR",
        "content":       "TEXT",
        "msg_type":      "VARCHAR",
        "data_payload":  "TEXT",
        "entity":        "TEXT",
        "chart_payload": "TEXT",
    },
}

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Create tables if fresh install
cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  VARCHAR NOT NULL UNIQUE,
        title       VARCHAR,
        employee_id VARCHAR NOT NULL
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_sessions_session_id   ON chat_sessions(session_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_sessions_employee_id  ON chat_sessions(employee_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id    VARCHAR NOT NULL,
        employee_id   VARCHAR NOT NULL,
        role          VARCHAR,
        content       TEXT,
        msg_type      VARCHAR,
        data_payload  TEXT,
        entity        TEXT,
        chart_payload TEXT
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id   ON chat_messages(session_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_employee_id  ON chat_messages(employee_id)")
conn.commit()

# Add any missing columns to existing tables
added = []
for table, columns in EXPECTED.items():
    cur.execute(f"PRAGMA table_info({table})")
    existing = {r[1] for r in cur.fetchall()}
    for col_name, col_type in columns.items():
        if col_name not in existing:
            print(f"  [MIGRATE] ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            added.append(f"{table}.{col_name}")

conn.commit()

print("\n Migration complete.")
if added:
    print(f"   Columns added: {', '.join(added)}")
else:
    print("   No changes needed - schema is already up to date.")

print("\nFinal schema:")
for table in EXPECTED:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"  {table}: {cols}")

conn.close()
