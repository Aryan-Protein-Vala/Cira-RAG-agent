"""SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, event, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

import config

DATABASE_URL = f"sqlite+aiosqlite:///{config.DATABASE_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "timeout": 30,           # busy timeout: prevents "database is locked"
        "check_same_thread": False,
    },
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class CompanyConnection(Base):
    """A company DB (tenant) an employee may sign in to, entered in the admin panel.

    Hardened versus the first cut of that feature:
    * the SAP password is never stored raw — `hana_secret` holds `env:VAR_NAME` or
      `enc:<fernet>` (see Backend/secrets.py), and no API response includes it;
    * Service Layer credentials are separate fields (they are B1 users, not the
      HANA schema user — reusing the HANA password for both leaked it to a second
      endpoint and never worked anyway);
    * `enabled` lets an operator park a company DB without deleting it;
    * `source_priority` pins the backend order per tenant.
    """

    __tablename__ = "company_connections"

    id = Column(Integer, primary_key=True, index=True)
    company_db = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String)
    enabled = Column(Integer, default=1, nullable=False)     # 0/1 (SQLite has no bool)
    source_priority = Column(String, default="")               # "" -> global CIRA_DATA_SOURCE_ORDER
    # SAP HANA
    hana_host = Column(String, nullable=False)
    hana_port = Column(Integer, nullable=False, default=30013)
    hana_user = Column(String, nullable=False)
    hana_secret = Column(String, nullable=False)              # env:VAR or enc:<token>
    hana_encrypt = Column(Integer, default=1, nullable=False)
    hana_extra_schemas = Column(String, default="")
    # SAP B1 Service Layer (optional; required for writes)
    service_layer_port = Column(Integer, default=50000)
    sl_user = Column(String, default="")
    sl_secret = Column(String, default="")
    sl_use_tls = Column(Integer, default=1, nullable=False)
    notes = Column(String, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String)
    employee_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    employee_id = Column(String, index=True, nullable=False)
    role = Column(String)                        # 'user' | 'assistant'
    content = Column(Text)
    msg_type = Column(String, nullable=True)     # 'text' | 'tabular' | 'chart' | 'form'
    data_payload = Column(Text, nullable=True)   # JSON: table rows
    entity = Column(String, nullable=True)       # e.g. OINV
    chart_payload = Column(Text, nullable=True)  # JSON: chart config
    form_payload = Column(Text, nullable=True)   # JSON: form schema
    meta_payload = Column(Text, nullable=True)   # JSON: source/backend/sql/etc.
    created_at = Column(DateTime, default=_utcnow)


Index("ix_chat_messages_session_employee", ChatMessage.session_id, ChatMessage.employee_id)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _add_missing_columns()


async def _add_missing_columns() -> None:
    """Tiny in-process migration so older cira.db files keep working."""
    expected = {
        "company_connections": {
            "display_name": "VARCHAR",
            "enabled": "INTEGER DEFAULT 1",
            "source_priority": "VARCHAR",
            "hana_extra_schemas": "VARCHAR",
            "sl_user": "VARCHAR",
            "sl_secret": "VARCHAR",
            "sl_use_tls": "INTEGER DEFAULT 1",
            "notes": "VARCHAR",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "chat_sessions": {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
            "employee_id": "VARCHAR",
        },
        "chat_messages": {
            "entity": "VARCHAR",
            "chart_payload": "TEXT",
            "form_payload": "TEXT",
            "meta_payload": "TEXT",
            "created_at": "DATETIME",
            "employee_id": "VARCHAR",
        },
    }
    async with engine.begin() as conn:
        for table, columns in expected.items():
            rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            existing = {r[1] for r in rows.fetchall()}
            for name, sql_type in columns.items():
                if name not in existing:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                    )


async def get_db():
    """FastAPI dependency. Not used inside SSE generators (see below)."""
    async with AsyncSessionLocal() as session:
        yield session


def create_short_lived_session() -> AsyncSession:
    """Standalone session for use inside streaming generators.

    A Depends(get_db) session held open for the 10-30s lifetime of an SSE
    response keeps a SQLite write lock and blocks every other request.
    """
    return AsyncSessionLocal()


__all__ = [
    "AsyncSessionLocal",
    "Base",
    "ChatMessage",
    "ChatSession",
    "CompanyConnection",
    "create_short_lived_session",
    "engine",
    "func",
    "get_db",
    "init_db",
]
