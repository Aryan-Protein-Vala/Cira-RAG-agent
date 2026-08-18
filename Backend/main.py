import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import init_db, get_db, create_short_lived_session, ChatSession, ChatMessage
from agent import stream_chat_query
from auth import bearer_scheme, validate_and_extract, exchange_for_sap_token

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="CIRA Chat Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    session_id: str


async def generate_chat_response(
    query: str,
    session_id: str,
    sap_token: str,
    employee_id: str
):
    """
    Fix 4: This generator creates its OWN short-lived DB sessions instead of
    holding a Depends(get_db) session open for the lifetime of a 10-15s SSE stream.
    Two sessions: one for pre-stream setup, one for post-stream persistence.
    """
    full_text = ""
    tabular_data = None

    # ── Pre-stream: fetch history + save user message ─────────────────────────
    async with create_short_lived_session() as db:
        # Ensure session exists and belongs to this employee
        stmt = select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.employee_id == employee_id
        )
        result = await db.execute(stmt)
        if not result.scalars().first():
            db.add(ChatSession(session_id=session_id, title=session_id, employee_id=employee_id))
            await db.commit()

        # Fetch past messages (scoped to this employee's session — IDOR fix)
        stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.employee_id == employee_id
        ).order_by(ChatMessage.id)
        result = await db.execute(stmt)
        history = result.scalars().all()

        # Save user message
        db.add(ChatMessage(
            session_id=session_id,
            employee_id=employee_id,
            role='user',
            content=query,
            msg_type='text'
        ))
        await db.commit()

    # ── Mid-stream: yield SSE chunks from agent ───────────────────────────────
    async for chunk in stream_chat_query(query, history, sap_token=sap_token, employee_id=employee_id):
        yield chunk
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:])
                if data["type"] == "chunk":
                    full_text += data["text"]
                elif data["type"] == "tabular":
                    tabular_data = data["data"]
            except json.JSONDecodeError:
                pass

    # ── Post-stream: persist assistant response ───────────────────────────────
    async with create_short_lived_session() as db:
        db.add(ChatMessage(
            session_id=session_id,
            employee_id=employee_id,
            role='assistant',
            content=full_text.strip(),
            msg_type='tabular' if tabular_data else 'text',
            data_payload=json.dumps(tabular_data) if tabular_data else None
        ))
        await db.commit()


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    # 1. Validate incoming session token
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    # 2. OAuth2 SAML Bearer exchange — mint short-lived, user-scoped SAP token
    sap_token = await exchange_for_sap_token(credentials.credentials, employee_id)

    # Fix 4: Do NOT inject db session here — generator manages its own sessions
    return StreamingResponse(
        generate_chat_response(request.query, request.session_id, sap_token, employee_id),
        media_type="text/event-stream"
    )


@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    # Validate token
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    # Fix 2: IDOR — verify session ownership before returning any history
    stmt = select(ChatSession).where(
        ChatSession.session_id == session_id,
        ChatSession.employee_id == employee_id   # ← ownership check
    )
    result = await db.execute(stmt)
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this session."
        )

    # Return only messages owned by this employee
    stmt = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.employee_id == employee_id   # ← ownership check
    ).order_by(ChatMessage.id)
    result = await db.execute(stmt)
    history = result.scalars().all()

    return {"messages": [
        {
            "role": m.role,
            "content": m.content,
            "type": m.msg_type,
            "data": json.loads(m.data_payload) if m.data_payload else None
        } for m in history
    ]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
