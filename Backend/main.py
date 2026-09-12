"""CIRA backend API.

FastAPI + SSE streaming chat over SAP Business One / HANA.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import httpx
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
from admin_routes import router as admin_router

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
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = authenticate(request.employee_id, request.password, request.company_db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID, password, or company DB.",
        )
    
    # Check multi-tenant connection
    from database import Tenant, CompanyConnection, Partner
    t_res = await db.execute(select(Tenant).where(Tenant.company_db == user["company_db"]))
    tenant_row = t_res.scalars().first()
    
    brand_name = "CIRA"
    logo_url = ""
    
    if tenant_row:
        if not tenant_row.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant account is inactive or suspended.",
            )
        # Fetch partner branding
        p_res = await db.execute(select(Partner).where(Partner.id == tenant_row.partner_id))
        partner = p_res.scalars().first()
        if partner:
            brand_name = partner.brand_name or "CIRA"
            logo_url = partner.logo_url or ""
    else:
        result = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == user["company_db"]))
        conn = result.scalars().first()
        if not conn:
            # If it's the default company configured in .env, auto-register it
            if user["company_db"] == config.SAP_B1_COMPANY_DB or not config.SAP_B1_COMPANY_DB:
                conn = CompanyConnection(
                    company_db=user["company_db"],
                    hana_address=config.HANA_HOST or "127.0.0.1",
                    hana_port=config.HANA_PORT or 30013,
                    hana_user=config.HANA_USER or "SYSTEM",
                    hana_password=config.HANA_PASSWORD or "",
                    # Service Layer port is ALWAYS 50000, never the HANA port (30013)
                    service_layer_port=config.SERVICE_LAYER_PORT,
                )
                db.add(conn)
                await db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Company database is not configured on this server.",
                )
        
    minted = create_token(user["employee_id"], user["name"], user["roles"], company_db=user["company_db"])
    return {
        "token": minted["token"],
        "expires_at": minted["expires_at"],
        "user": {
            "employee_id": user["employee_id"],
            "name": user["name"],
            "roles": user["roles"],
            "brand_name": brand_name,
            "logo_url": logo_url
        },
    }


@app.get("/auth/me")
async def me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    ctx = validate_and_extract(credentials)
    # The frontend usually hits /auth/me to restore session, so it's good to include it here but
    # for simplicity, we rely on the login data stored in local storage for branding, or we can just 
    # fetch the branding dynamically if needed. We'll just return what's in the token.
    return {
        "employee_id": ctx["employee_id"],
        "name": ctx.get("name"),
        "roles": ctx.get("roles", []),
        "expires_at": ctx.get("exp"),
        "company_db": ctx.get("company_db", ""),
    }


async def set_tenant_context(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    ctx = validate_and_extract(credentials)
    company_db = ctx.get("company_db")
    if company_db:
        from database import Tenant, CompanyConnection, Partner
        result = await db.execute(select(Tenant).where(Tenant.company_db == company_db))
        tenant_row = result.scalars().first()
        
        if tenant_row:
            if not tenant_row.is_active:
                raise HTTPException(status_code=403, detail="Tenant is inactive.")
            p_res = await db.execute(select(Partner).where(Partner.id == tenant_row.partner_id))
            partner_row = p_res.scalars().first()
            if partner_row and not partner_row.is_active:
                raise HTTPException(status_code=403, detail="Partner account is suspended.")

            is_mssql = (tenant_row.backend_type or "").lower() == "mssql"
            tenant_config = {
                "HANA_SCHEMA": tenant_row.company_db,
                "SAP_B1_COMPANY_DB": tenant_row.company_db,
                "HANA_HOST": tenant_row.sap_host,
                "HANA_PORT": tenant_row.sap_hana_port,
                "HANA_USER": tenant_row.sap_db_user,
                "HANA_PASSWORD": tenant_row.sap_db_password,
                "MSSQL_HOST": tenant_row.sap_host if is_mssql else "",
                "MSSQL_PORT": tenant_row.sap_hana_port if is_mssql else 1433,
                "MSSQL_USER": tenant_row.sap_db_user if is_mssql else "",
                "MSSQL_PASSWORD": tenant_row.sap_db_password if is_mssql else "",
                "SAP_B1_HOST": tenant_row.sap_host,
                "SAP_B1_PORT": tenant_row.sap_hana_port,
                "SERVICE_LAYER_PORT": tenant_row.sap_sl_port,
                "SAP_B1_USER": tenant_row.sap_sl_user,
                "SAP_B1_PASSWORD": tenant_row.sap_sl_password,
                "WRITE_ENABLED": bool(tenant_row.write_enabled),
            }
            config.CURRENT_TENANT.set(tenant_config)
        else:
            c_res = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == company_db))
            conn = c_res.scalars().first()
            if conn:
                tenant_config = {
                    "HANA_SCHEMA": conn.company_db,
                    "SAP_B1_COMPANY_DB": conn.company_db,
                    "HANA_HOST": conn.hana_address,
                    "HANA_PORT": conn.hana_port,
                    "HANA_USER": conn.hana_user,
                    "HANA_PASSWORD": conn.hana_password,
                    "SAP_B1_HOST": conn.hana_address,
                    "SAP_B1_PORT": conn.hana_port,
                    "SERVICE_LAYER_PORT": conn.service_layer_port,
                    "SAP_B1_USER": config.SAP_B1_USER,
                    "SAP_B1_PASSWORD": config.SAP_B1_PASSWORD,
                    "WRITE_ENABLED": False,
                }
                config.CURRENT_TENANT.set(tenant_config)
    return ctx

app.include_router(admin_router)

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


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    validate_and_extract(credentials)
    if not config.GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
        
    audio_content = await file.read()
    
    files = {
        "file": (file.filename, audio_content, file.content_type)
    }
    data = {
        "model": "whisper-large-v3",
        "language": "en"
    }
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            files=files,
            data=data,
            headers=headers,
            timeout=30.0
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


class WriteRequest(BaseModel):
    entity: str = Field(..., description="SAP B1 Service Layer entity (e.g. 'BusinessPartners')")
    table: str = Field("", description="Underlying SAP table name (e.g. 'OCRD')")
    data: dict = Field(..., description="Field values to write")


@app.post("/sap/write")
async def sap_write(
    body: WriteRequest,
    user_context: dict = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a new entity record in SAP Business One via the Service Layer."""
    # Ensure stored service_layer_port is correct (fix legacy rows that stored 30013)
    company_db = user_context.get("company_db", "")
    if company_db:
        from database import CompanyConnection
        result = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == company_db))
        conn_row = result.scalars().first()
        if conn_row and conn_row.service_layer_port == config.HANA_PORT:
            log.warning(
                "Fixing stored service_layer_port %s → 50000 for %s",
                conn_row.service_layer_port, company_db
            )
            conn_row.service_layer_port = config.SERVICE_LAYER_PORT
            await db.commit()
            curr = dict(config.CURRENT_TENANT.get() or {})
            curr["SERVICE_LAYER_PORT"] = config.SERVICE_LAYER_PORT
            config.CURRENT_TENANT.set(curr)

    current_cfg = config.CURRENT_TENANT.get({})
    if not current_cfg.get("WRITE_ENABLED", False):
        raise HTTPException(status_code=403, detail="SAP writes are disabled for this tenant.")

    try:
        target = body.table if body.table else body.entity
        result = await sap.create_entity(target, body.data)
        return {"ok": True, "result": result}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("SAP write failed for entity=%s data=%s: %s", body.entity, body.data, exc, exc_info=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/sap/health")
async def sap_health(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    validate_and_extract(credentials)
    return await sap.health()


@app.get("/sap/tables")
async def sap_tables(
    pattern: str = "",
    limit: int = 300,
    user_context: dict = Depends(set_tenant_context),
):
    return await sap.list_tables(pattern=pattern, limit=min(limit, 2000))


@app.get("/sap/table/{table_name}")
async def sap_table(
    table_name: str,
    user_context: dict = Depends(set_tenant_context),
):
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
    form_payload = None

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
            elif kind == "form":
                form_payload = data
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
                        msg_type="form" if form_payload else ("chart" if chart_payload else ("tabular" if rows else "text")),
                        data_payload=json.dumps(rows, default=str) if rows is not None else None,
                        entity=entity_name,
                        chart_payload=json.dumps(chart_payload, default=str) if chart_payload else None,
                        form_payload=json.dumps(form_payload, default=str) if form_payload else None,
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
    user_context: dict = Depends(set_tenant_context),
):
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
                "form": _loads(m.form_payload),
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
    try:
        validate_and_extract(credentials)
        title = await agent_generate_title(request.prompt)
        return {"title": title}
    except Exception as exc:
        log.warning("generate_title fallback: %s", exc)
        words = (request.prompt or "").strip().split()
        return {"title": " ".join(words[:5])[:40] or "New conversation"}


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
