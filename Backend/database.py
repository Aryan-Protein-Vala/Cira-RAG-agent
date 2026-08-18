from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, event
from sqlalchemy.future import select

DATABASE_URL = "sqlite+aiosqlite:///./cira.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "timeout": 30,               # Fix 5: 30s busy timeout prevents "database is locked" under concurrency
        "check_same_thread": False,
    }
)

# Fix 5: Enable WAL journal mode on every new connection — allows concurrent reads during writes
@event.listens_for(engine.sync_engine, "connect")
def set_wal_mode(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.close()

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    title = Column(String)
    employee_id = Column(String, index=True)  # Fix 2: IDOR — sessions are now owned by an employee


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    employee_id = Column(String, index=True)  # Fix 2: IDOR — messages are now owned by an employee
    role = Column(String)           # 'user' or 'assistant'
    content = Column(Text)
    msg_type = Column(String, nullable=True)    # 'text' or 'tabular'
    data_payload = Column(Text, nullable=True)  # json dump of data if tabular


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Fix 4: get_db is intentionally NOT used inside StreamingResponse generators.
# Instead, use create_short_lived_session() for isolated DB access within SSE streams.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def create_short_lived_session() -> AsyncSession:
    """Creates a standalone async session for use inside SSE generator functions."""
    return AsyncSessionLocal()
