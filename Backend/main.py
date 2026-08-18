import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import init_db, get_db, ChatSession, ChatMessage
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
    db: AsyncSession,
    sap_token: str,
    employee_id: str
):
    # 1. Fetch history for this session
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    result = await db.execute(stmt)
    history = result.scalars().all()

    # 2. Persist user message
    user_msg = ChatMessage(session_id=session_id, role='user', content=query, msg_type='text')
    db.add(user_msg)
    await db.commit()

    # 3. Stream agent output (tool is instantiated with the per-user SAP token)
    full_text = ""
    tabular_data = None

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

    # 4. Persist assistant response
    assistant_msg = ChatMessage(
        session_id=session_id,
        role='assistant',
        content=full_text.strip(),
        msg_type='tabular' if tabular_data else 'text',
        data_payload=json.dumps(tabular_data) if tabular_data else None
    )
    db.add(assistant_msg)
    await db.commit()


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    # 1. Validate incoming session token — strip any master credentials from agent
    user_context = validate_and_extract(credentials)
    employee_id = user_context.get("employee_id", "UNKNOWN")

    # 2. OAuth2 SAML Bearer exchange — mint a short-lived, user-scoped SAP token
    sap_token = await exchange_for_sap_token(credentials.credentials, employee_id)

    # 3. Ensure session exists in DB
    stmt = select(ChatSession).where(ChatSession.session_id == request.session_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        db.add(ChatSession(session_id=request.session_id, title=request.session_id))
        await db.commit()

    # 4. Stream with per-user SAP token injected into tool context
    return StreamingResponse(
        generate_chat_response(request.query, request.session_id, db, sap_token, employee_id),
        media_type="text/event-stream"
    )


@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    # Validate token before returning any history
    validate_and_extract(credentials)

    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
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
