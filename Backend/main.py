import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import init_db, get_db, ChatSession, ChatMessage
from agent import stream_chat_query

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

async def generate_chat_response(query: str, session_id: str, db: AsyncSession):
    # 1. Fetch History
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    result = await db.execute(stmt)
    history = result.scalars().all()
    
    # 2. Save user message
    user_msg = ChatMessage(session_id=session_id, role='user', content=query, msg_type='text')
    db.add(user_msg)
    await db.commit()
    
    # 3. Stream agent output
    full_text = ""
    tabular_data = None
    
    async for chunk in stream_chat_query(query, history):
        yield chunk
        
        # Parse chunk to accumulate response for DB saving
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:])
                if data["type"] == "chunk":
                    full_text += data["text"]
                elif data["type"] == "tabular":
                    tabular_data = data["data"]
            except json.JSONDecodeError:
                pass
                
    # 4. Save assistant message
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
async def chat_endpoint(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    # Check if session exists
    stmt = select(ChatSession).where(ChatSession.session_id == request.session_id)
    result = await db.execute(stmt)
    session = result.scalars().first()
    if not session:
        new_session = ChatSession(session_id=request.session_id, title=f"Session {request.session_id}")
        db.add(new_session)
        await db.commit()

    return StreamingResponse(
        generate_chat_response(request.query, request.session_id, db), 
        media_type="text/event-stream"
    )

@app.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    result = await db.execute(stmt)
    history = result.scalars().all()
    
    formatted = []
    for msg in history:
        formatted.append({
            "role": msg.role,
            "content": msg.content,
            "type": msg.msg_type,
            "data": json.loads(msg.data_payload) if msg.data_payload else None
        })
    return {"messages": formatted}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
