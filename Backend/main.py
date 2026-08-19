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
    entity_name = None
    chart_payload = None

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
                if isinstance(data, dict):
                    msg_type = data.get("type")
                    if msg_type == "chunk":
                        full_text += str(data.get("text", ""))
                    elif msg_type == "tabular":
                        tabular_data = data.get("data")
                        entity_name = data.get("entity")
                    elif msg_type == "chart":
                        chart_payload = data
            except Exception:
                pass

    # ── Post-stream: persist assistant response with entity & chart ───────────
    async with create_short_lived_session() as db:
        db.add(ChatMessage(
            session_id=session_id,
            employee_id=employee_id,
            role='assistant',
            content=full_text.strip(),
            msg_type='chart' if chart_payload else ('tabular' if tabular_data else 'text'),
            data_payload=json.dumps(tabular_data) if tabular_data else None,
            entity=entity_name,
            chart_payload=json.dumps(chart_payload) if chart_payload else None
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
            "data": json.loads(m.data_payload) if m.data_payload else None,
            "entity": getattr(m, "entity", None),
            "chart": json.loads(m.chart_payload) if getattr(m, "chart_payload", None) else None
        } for m in history
    ]}

@app.get("/sessions")
async def get_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    stmt = select(ChatSession).where(ChatSession.employee_id == employee_id).order_by(ChatSession.id.desc())
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return {"sessions": [
        {"id": str(s.session_id), "title": s.title}
        for s in sessions
    ]}

class RenameRequest(BaseModel):
    title: str

@app.put("/session/{session_id}")
async def rename_session(
    session_id: str,
    request: RenameRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    stmt = select(ChatSession).where(ChatSession.session_id == session_id, ChatSession.employee_id == employee_id)
    result = await db.execute(stmt)
    session_obj = result.scalars().first()
    
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session_obj.title = request.title
    await db.commit()
    return {"ok": True}

from sqlalchemy import delete

@app.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    stmt = select(ChatSession).where(ChatSession.session_id == session_id, ChatSession.employee_id == employee_id)
    result = await db.execute(stmt)
    session_obj = result.scalars().first()
    
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await db.delete(session_obj)
    
    # Also delete associated messages
    del_stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.employee_id == employee_id)
    await db.execute(del_stmt)
    
    await db.commit()
    return {"ok": True}

class TitleRequest(BaseModel):
    prompt: str

@app.post("/generate_title")
async def generate_title(
    request: TitleRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    from agent import llm
    from langchain_core.messages import SystemMessage, HumanMessage
    
    # Fix 2: Auth Hardening — prevent unauthenticated OpenRouter usage
    validate_and_extract(credentials)
    
    messages = [
        SystemMessage(content="You are a helpful assistant. Generate a short, 2-4 word summary title for the following user message. Do not use quotes or punctuation. Respond ONLY with the title."),
        HumanMessage(content=request.prompt)
    ]
    response = await llm.ainvoke(messages)
    title = response.content.strip().strip('"\'')
    if len(title) > 40:
        title = title[:40] + "..."
    return {"title": title}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
