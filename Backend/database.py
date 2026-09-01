"""SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, event, func, select
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
    return dt.datetime.now(dt.timezone.utc)


class CompanyConnection(Base):
    __tablename__ = "company_connections"

    id = Column(Integer, primary_key=True, index=True)
    company_db = Column(String, unique=True, index=True, nullable=False)
    hana_address = Column(String, nullable=False)
    hana_port = Column(Integer, nullable=False)
    hana_user = Column(String, nullable=False)
    hana_password = Column(String, nullable=False)
    service_layer_port = Column(Integer, default=50000)
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
    await _seed_default_connection()


async def _seed_default_connection() -> None:
    """Seed the default tenant from .env if table is empty or missing it."""
    try:
        if not config.SAP_B1_COMPANY_DB:
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CompanyConnection).where(
                    CompanyConnection.company_db == config.SAP_B1_COMPANY_DB
                )
            )
            if not result.scalars().first():
                conn = CompanyConnection(
                    company_db=config.SAP_B1_COMPANY_DB,
                    hana_address=config.HANA_HOST or "127.0.0.1",
                    hana_port=config.HANA_PORT or 30013,
                    hana_user=config.HANA_USER or "SYSTEM",
                    hana_password=config.HANA_PASSWORD or "",
                    service_layer_port=config.SAP_B1_PORT or 50000,
                )
                session.add(conn)
                await session.commit()
    except Exception as exc:
        pass


async def _add_missing_columns() -> None:
    """Tiny in-process migration so older cira.db files keep working."""
    expected = {
        "company_connections": {
            "company_db": "VARCHAR",
            "hana_address": "VARCHAR",
            "hana_port": "INTEGER",
            "hana_user": "VARCHAR",
            "hana_password": "VARCHAR",
            "service_layer_port": "INTEGER",
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
    "create_short_lived_session",
    "engine",
    "func",
    "get_db",
    "init_db",
]
