"""CIRA backend API.

FastAPI + SSE streaming chat over SAP Business One / HANA.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
import docs_store
from agent import generate_title as agent_generate_title
from agent import stream_chat_query
from auth import authenticate, bearer_scheme, create_token, exchange_for_sap_token, validate_and_extract
from database import (
    ChatMessage,
    ChatSession,
    create_short_lived_session,
    get_db,
    init_db,
)
from sap import router as sap

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("cira")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("CIRA backend starting — data source mode: %s", config.DATA_SOURCE)
    if not config.OPENROUTER_API_KEY:
        log.warning(
            "No OPENROUTER_API_KEY configured — running the deterministic planner. "
            "Set it in Backend/.env for full natural-language reasoning."
        )

    async def warm_up():
        try:
            info = await sap.health()
            log.info(
                "SAP backend: %s (schema=%s, simulated=%s, tables=%s)",
                info.get("active_backend"), info.get("schema"),
                info.get("simulated"), info.get("tables_visible"),
            )
        except Exception as exc:
            log.warning("SAP warm-up failed: %s", exc)

    task = asyncio.create_task(warm_up())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="CIRA Chat Backend", version="2.0.0", lifespan=lifespan)

cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["*"],
}
if config.ALLOWED_ORIGINS:
    cors_kwargs["allow_origins"] = config.ALLOWED_ORIGINS
else:
    cors_kwargs["allow_origins"] = []
    cors_kwargs["allow_origin_regex"] = config.ALLOW_ORIGIN_REGEX
app.add_middleware(CORSMiddleware, **cors_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    company_db: str = Field(default="")


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=1, max_length=128)


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class TitleRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def login(request: LoginRequest):
    user = authenticate(request.employee_id, request.password, request.company_db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID, password, or company DB.",
        )
    minted = create_token(user["employee_id"], user["name"], user["roles"], company_db=user["company_db"])
    return {
        "token": minted["token"],
        "expires_at": minted["expires_at"],
        "user": {
            "employee_id": user["employee_id"],
            "name": user["name"],
            "roles": user["roles"],
        },
    }


@app.get("/auth/me")
async def me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    ctx = validate_and_extract(credentials)
    return {
        "employee_id": ctx["employee_id"],
        "name": ctx.get("name"),
        "roles": ctx.get("roles", []),
        "expires_at": ctx.get("exp"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Health & diagnostics
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "llm": config.MODEL_NAME if config.USE_LLM else "deterministic-planner",
        "knowledge_documents": docs_store.document_count(),
    }


@app.get("/sap/health")
async def sap_health():
    return await sap.health()


@app.get("/sap/tables")
async def sap_tables(
    pattern: str = "",
    limit: int = 300,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    validate_and_extract(credentials)
    return await sap.list_tables(pattern=pattern, limit=min(limit, 2000))


@app.get("/sap/table/{table_name}")
async def sap_table(
    table_name: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    validate_and_extract(credentials)
    try:
        return await sap.describe_table(table_name, sample_rows=3)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────
async def generate_chat_response(query: str, session_id: str, sap_token: str, employee_id: str):
    """SSE generator. Owns its own short-lived DB sessions (never a request-scoped one)."""
    full_text: list[str] = []
    tabular_data = None
    tabular_meta = None
    entity_name = None
    chart_payload = None

    async with create_short_lived_session() as db:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.session_id == session_id,
                ChatSession.employee_id == employee_id,
            )
        )
        session_obj = result.scalars().first()
        if session_obj is None:
            # Refuse to hijack a session id that belongs to somebody else
            existing = await db.execute(
                select(ChatSession).where(ChatSession.session_id == session_id)
            )
            if existing.scalars().first() is not None:
                yield f"data: {json.dumps({'type': 'error', 'text': 'You do not have access to this conversation.'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            db.add(
                ChatSession(
                    session_id=session_id,
                    title=query[:40] or "New conversation",
                    employee_id=employee_id,
                )
            )
            await db.commit()

        history_result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.employee_id == employee_id,
            )
            .order_by(ChatMessage.id)
        )
        history = history_result.scalars().all()

        db.add(
            ChatMessage(
                session_id=session_id,
                employee_id=employee_id,
                role="user",
                content=query,
                msg_type="text",
            )
        )
        await db.commit()

    try:
        async for chunk in stream_chat_query(
            query, history, sap_token=sap_token, employee_id=employee_id
        ):
            yield chunk
            if not chunk.startswith("data: "):
                continue
            try:
                data = json.loads(chunk[6:])
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            if kind == "chunk":
                full_text.append(str(data.get("text", "")))
            elif kind == "tabular":
                tabular_data = data.get("data")
                tabular_meta = data.get("meta")
                entity_name = data.get("entity")
            elif kind == "chart":
                chart_payload = data
            elif kind == "error":
                full_text.append(str(data.get("text", "")))
    finally:
        text = "".join(full_text).strip()
        rows = tabular_data
        if isinstance(rows, list) and len(rows) > config.MAX_PERSISTED_ROWS:
            rows = rows[: config.MAX_PERSISTED_ROWS]
        try:
            async with create_short_lived_session() as db:
                db.add(
                    ChatMessage(
                        session_id=session_id,
                        employee_id=employee_id,
                        role="assistant",
                        content=text,
                        msg_type="chart" if chart_payload else ("tabular" if rows else "text"),
                        data_payload=json.dumps(rows, default=str) if rows is not None else None,
                        entity=entity_name,
                        chart_payload=json.dumps(chart_payload, default=str) if chart_payload else None,
                        meta_payload=json.dumps(tabular_meta, default=str) if tabular_meta else None,
                    )
                )
                session_row = await db.execute(
                    select(ChatSession).where(
                        ChatSession.session_id == session_id,
                        ChatSession.employee_id == employee_id,
                    )
                )
                obj = session_row.scalars().first()
                if obj is not None:
                    import datetime as _dt

                    obj.updated_at = _dt.datetime.now(_dt.timezone.utc)
                await db.commit()
        except Exception as exc:  # never break the stream because of persistence
            log.warning("Could not persist assistant message: %s", exc)


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    user_context = validate_and_extract(credentials)
    employee_id = user_context["employee_id"]
    sap_token = await exchange_for_sap_token(credentials.credentials, employee_id)

    return StreamingResponse(
        generate_chat_response(request.query, request.session_id, sap_token, employee_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx: do not buffer SSE
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sessions & history
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/sessions")
async def get_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    ctx = validate_and_extract(credentials)
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.employee_id == ctx["employee_id"])
        .order_by(ChatSession.updated_at.desc().nullslast(), ChatSession.id.desc())
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.session_id),
                "title": s.title or "Untitled",
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    ctx = validate_and_extract(credentials)
    employee_id = ctx["employee_id"]

    owned = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.employee_id == employee_id,
        )
    )
    if owned.scalars().first() is None:
        raise HTTPException(status_code=403, detail="You do not have access to this session.")

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.employee_id == employee_id,
        )
        .order_by(ChatMessage.id)
    )
    messages = result.scalars().all()

    def _loads(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    return {
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "type": m.msg_type,
                "data": _loads(m.data_payload),
                "entity": m.entity,
                "chart": _loads(m.chart_payload),
                "meta": _loads(m.meta_payload),
                "timestamp": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    }


@app.put("/session/{session_id}")
async def rename_session(
    session_id: str,
    request: RenameRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    ctx = validate_and_extract(credentials)
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.employee_id == ctx["employee_id"],
        )
    )
    session_obj = result.scalars().first()
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session_obj.title = request.title.strip()[:200]
    await db.commit()
    return {"ok": True, "title": session_obj.title}


@app.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    ctx = validate_and_extract(credentials)
    employee_id = ctx["employee_id"]
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.employee_id == employee_id,
        )
    )
    session_obj = result.scalars().first()
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.employee_id == employee_id,
        )
    )
    await db.delete(session_obj)
    await db.commit()
    return {"ok": True}


@app.post("/generate_title")
async def generate_title_endpoint(
    request: TitleRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    validate_and_extract(credentials)
    return {"title": await agent_generate_title(request.prompt)}


# ─────────────────────────────────────────────────────────────────────────────
# Attachments
# ─────────────────────────────────────────────────────────────────────────────
TEXTUAL_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".tsv", ".xml", ".yaml", ".yml"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    ctx = validate_and_extract(credentials)
    import uuid
    from pathlib import Path

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File larger than 8 MB.")

    safe_name = Path(file.filename or "upload.bin").name
    file_id = uuid.uuid4().hex
    target = config.UPLOAD_DIR / f"{ctx['employee_id']}_{file_id}_{safe_name}"
    target.write_bytes(raw)

    preview = ""
    suffix = Path(safe_name).suffix.lower()
    if suffix in TEXTUAL_SUFFIXES:
        try:
            preview = raw.decode("utf-8", errors="replace")[:6000]
        except Exception:
            preview = ""

    return {
        "ok": True,
        "file_id": file_id,
        "name": safe_name,
        "size": len(raw),
        "content_type": file.content_type,
        "text_preview": preview,
        "usable_as_context": bool(preview),
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # pragma: no cover
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
