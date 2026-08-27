"""CIRA backend API.

FastAPI + SSE streaming chat over SAP Business One (HANA first, Service Layer
and SQL Server as configured fallbacks).

Request-shape notes worth knowing before editing:
* every endpoint except /health and /auth/login requires a signed bearer token;
* SSE generators own short-lived DB sessions (a request-scoped one would hold a
  SQLite write lock for the 10-30 s lifetime of a stream);
* the full result set never passes through the LLM — it is streamed to the
  browser from the agent's ResultBus and persisted alongside the message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import audit
import config
import docs_store
from agent import generate_title as agent_generate_title
from agent import stream_chat_query
from auth import (
    authenticate,
    bearer_scheme,
    create_token,
    require_roles,
    validate_and_extract,
)
from database import (
    ChatMessage,
    ChatSession,
    create_short_lived_session,
    get_db,
    init_db,
)
from sap import router as sap
from sap.router import BackendUnavailable
from sap.types_ import SapDataError, SapUnavailableError

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("cira")


@asynccontextmanager
async def lifespan(app: FastAPI):
    fatal, warnings = config.validate()
    for message in warnings:
        log.warning("CONFIG: %s", message)
    if fatal:
        for message in fatal:
            log.error("CONFIG: %s", message)
        raise RuntimeError(
            "Refusing to start with an unsafe or impossible configuration "
            f"({len(fatal)} problem(s)). Fix the CONFIG errors above."
        )

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
            if info.get("simulated"):
                attempts = "; ".join(
                    f"{a.get('candidate')}={'ok' if a.get('ok') else a.get('error')}"
                    for a in info.get("attempts", [])
                ) or "nothing enabled"
                log.warning("Serving SANDBOX data — this is NOT your ERP. Attempts: %s", attempts)
        except Exception as exc:
            log.error("SAP warm-up failed: %s", exc)

    async def sweep_uploads():
        while True:
            try:
                _sweep_expired_uploads()
            except Exception as exc:  # pragma: no cover
                log.debug("upload sweep failed: %s", exc)
            await asyncio.sleep(3600)

    tasks = [asyncio.create_task(warm_up()), asyncio.create_task(sweep_uploads())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()


app = FastAPI(title="CIRA Chat Backend", version="2.1.0", lifespan=lifespan)

# CORS: a wildcard origin combined with allow_credentials is the classic
# "any website may read your ERP responses" mistake. config.STRICT (default true)
# makes that combination a startup error instead of a deployment footnote, and
# credentials are off unless the operator explicitly allowlists origins.
if config.ALLOWED_ORIGINS:
    cors_kwargs = {
        "allow_origins": config.ALLOWED_ORIGINS,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "expose_headers": ["Content-Type"],
        "allow_credentials": False,
    }
elif config.ALLOW_ORIGIN_REGEX:
    cors_kwargs = {
        "allow_origin_regex": config.ALLOW_ORIGIN_REGEX,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "expose_headers": ["Content-Type"],
        "allow_credentials": False,
    }
else:  # pragma: no cover - blocked by config.validate(STRICT)
    cors_kwargs = {
        "allow_origins": [],
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": [],
        "allow_credentials": False,
    }
app.add_middleware(CORSMiddleware, **cors_kwargs)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    company_db: str = Field(default="", max_length=128)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=1, max_length=128)


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class CompanyConnectionCreate(BaseModel):
    company_db: str
    hana_address: str
    hana_port: int
    hana_user: str
    hana_password: str
    service_layer_port: int = 50000


class TitleRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = authenticate(request.employee_id, request.password, request.company_db)
    if not user:
        audit.event("login_failed", employee_id=request.employee_id,
                    company_db=request.company_db or config.DEFAULT_COMPANY_DB)
        # One generic message: do not tell the caller whether the id exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID or password.",
        )
    
    # Check multi-tenant connection
    from database import CompanyConnection
    result = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == user["company_db"]))
    conn = result.scalars().first()
    if not conn:
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
            "company_db": user["company_db"],
        },
    }


@app.get("/auth/me")
async def me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    ctx = validate_and_extract(credentials)
    return {
        "employee_id": ctx["employee_id"],
        "name": ctx.get("name"),
        "roles": ctx.get("roles", []),
        "company_db": ctx.get("company_db"),
        "expires_at": ctx.get("exp"),
        "company_db": ctx.get("company_db", ""),
    }


async def set_tenant_context(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    ctx = validate_and_extract(credentials)
    company_db = ctx.get("company_db")
    if company_db:
        from database import CompanyConnection
        result = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == company_db))
        conn = result.scalars().first()
        if conn:
            import config
            tenant_config = {
                "HANA_SCHEMA": conn.company_db,
                "SAP_B1_COMPANY_DB": conn.company_db,
                "HANA_HOST": conn.hana_address,
                "HANA_PORT": conn.hana_port,
                "HANA_USER": conn.hana_user,
                "HANA_PASSWORD": conn.hana_password,
                "SAP_B1_HOST": conn.hana_address,
                "SAP_B1_PORT": conn.service_layer_port,
                "SAP_B1_USER": conn.hana_user,
                "SAP_B1_PASSWORD": conn.hana_password,
            }
            config.CURRENT_TENANT.set(tenant_config)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/admin/login")
async def admin_login(request: AdminLoginRequest):
    if request.username == "admin" and request.password == "asdfghjkl;":
        minted = create_token("admin", "Administrator", ["admin"], company_db="")
        return {"token": minted["token"]}
    raise HTTPException(status_code=401, detail="Invalid admin credentials")


@app.get("/admin/connections")
async def get_connections(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    ctx = validate_and_extract(credentials)
    if "admin" not in ctx.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin only")
    
    from database import CompanyConnection
    result = await db.execute(select(CompanyConnection))
    connections = result.scalars().all()
    return [{"id": c.id, "company_db": c.company_db, "hana_address": c.hana_address, "hana_port": c.hana_port, "hana_user": c.hana_user, "service_layer_port": c.service_layer_port} for c in connections]


@app.post("/admin/connections")
async def create_connection(data: CompanyConnectionCreate, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    ctx = validate_and_extract(credentials)
    if "admin" not in ctx.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin only")
    
    from database import CompanyConnection
    # Check if exists
    result = await db.execute(select(CompanyConnection).where(CompanyConnection.company_db == data.company_db))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Company DB already exists")
        
    conn = CompanyConnection(**data.dict())
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return {"id": conn.id, "company_db": conn.company_db}


@app.delete("/admin/connections/{id}")
async def delete_connection(id: int, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    ctx = validate_and_extract(credentials)
    if "admin" not in ctx.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin only")
    
    from database import CompanyConnection
    await db.execute(delete(CompanyConnection).where(CompanyConnection.id == id))
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Health & diagnostics
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Liveness only, and deliberately silent about topology.

    The old build exposed host, port, schema, ERP username and the Service Layer
    URL here (unauthenticated) and a test asserted otherwise — that test was
    failing on main.
    """
    return {
        "status": "ok",
        "version": app.version,
        "llm": "configured" if config.USE_LLM else "deterministic-planner",
        "knowledge_documents": docs_store.document_count(),
    }


@app.get("/sap/health")
async def sap_health(
    force: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Backend diagnostics — authenticated, since it names schemas and failures.


class WriteRequest(BaseModel):
    entity: str = Field(..., description="SAP B1 Service Layer entity (e.g. 'BusinessPartners')")
    table: str = Field("", description="Underlying SAP table name (e.g. 'OCRD')")
    data: dict = Field(..., description="Field values to write")


@app.post("/sap/write")
async def sap_write(
    body: WriteRequest,
    user_context: dict = Depends(set_tenant_context),
):
    """Create a new entity record in SAP Business One via the Service Layer."""
    try:
        return await sap.health(force=bool(force))
    except BackendUnavailable as exc:
        return {
            "active_backend": None,
            "schema": None,
            "simulated": None,
            "tables_visible": 0,
            "attempts": sap.probe_log(),
            "error": str(exc),
            "config": config.summary(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SAP metadata
# ─────────────────────────────────────────────────────────────────────────────
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
    except SapDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=_client_error(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Writes
# ─────────────────────────────────────────────────────────────────────────────
class WriteRequest(BaseModel):
    entity: str = Field(..., max_length=128, description="SAP B1 Service Layer entity (e.g. 'BusinessPartners')")
    table: str = Field(default="", max_length=128, description="Underlying SAP table name (e.g. 'OCRD')")
    data: dict = Field(default_factory=dict)


_SAFE_ENTITY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,62}$")
WRITE_ROLES = tuple(sorted(config.SAP_WRITE_ROLES) or ["admin"])


@app.post("/sap/write")
async def sap_write(
    body: WriteRequest,
    user: dict = Depends(require_roles(*WRITE_ROLES)),
):
    """Create one record in SAP Business One through the Service Layer.

    Guarded four ways, because this is the only way CIRA can change a
    production ERP: the path must be enabled, the caller must hold a write
    role, the entity must be on the allowlist, and every attempt is audited.
    """
    if not config.SAP_WRITE_ENABLED:
        audit.event("sap_write_refused", employee_id=user["employee_id"],
                    entity=body.entity, reason="path_disabled")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "SAP write operations are disabled for this deployment. An "
                "administrator must set CIRA_SAP_WRITE_ENABLED=true (and the "
                "Service Layer credentials) to create records."
            ),
        )
    entity = (body.entity or "").strip()
    if not _SAFE_ENTITY.match(entity):
        raise HTTPException(status_code=422, detail="Unsupported entity name.")
    if entity not in config.SAP_WRITE_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"'{entity}' is not on the writable-entity allowlist "
                f"({', '.join(sorted(config.SAP_WRITE_ENTITIES))})."
            ),
        )
    if len(body.data) > config.SAP_WRITE_MAX_FIELDS:
        raise HTTPException(status_code=422, detail="Too many fields in one write.")

    audit.set_context(employee_id=user["employee_id"])
    audit.event("sap_write_attempt", employee_id=user["employee_id"], entity=entity,
                fields=sorted(body.data)[:60])
    try:
        result = await sap.create_entity(entity, body.data)
    except (SapDataError, SapUnavailableError, BackendUnavailable) as exc:
        audit.event("sap_write_failed", employee_id=user["employee_id"], entity=entity,
                    error=str(exc)[:400])
        raise HTTPException(status_code=422, detail=str(exc)[:400]) from exc
    except Exception as exc:
        audit.event("sap_write_failed", employee_id=user["employee_id"], entity=entity,
                    error=str(exc)[:400])
        raise HTTPException(status_code=502, detail=_client_error(exc)) from exc
    audit.event("sap_write_ok", employee_id=user["employee_id"], entity=entity,
                 response=_response_id(result))
    return {"ok": True, "result": result}


def _response_id(result) -> str:
    if isinstance(result, dict):
        for key in ("DocEntry", "CardCode", "ItemCode", "object_key"):
            if key in result:
                return f"{key}={result[key]}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Speech to text
# ─────────────────────────────────────────────────────────────────────────────
AUDIO_TYPES = {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg",
               "audio/x-m4a", "audio/aac", "audio/flac", "video/webm"}


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Proxy a recording to Groq Whisper. Disabled unless GROQ_API_KEY is set."""
    user = validate_and_extract(credentials)
    if not config.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text is not configured on this deployment.",
        )
    if (file.content_type or "").split(";")[0] not in AUDIO_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported audio content type.")

    raw = await file.read(config.MAX_AUDIO_BYTES + 1)
    if len(raw) > config.MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio larger than {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )
    audit.event("transcribe", employee_id=user["employee_id"], bytes=len(raw))

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                files={"file": (Path(file.filename or "audio.webm").name, raw,
                                 file.content_type or "audio/webm")},
                data={"model": "whisper-large-v3", "language": "en"},
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            )
    except httpx.HTTPError as exc:
        log.warning("transcribe upstream error: %s", exc)
        raise HTTPException(status_code=502, detail="Speech-to-text provider unreachable.") from exc

    if response.status_code != 200:
        log.warning("transcribe rejected by provider: HTTP %s", response.status_code)
        # The upstream body can contain account/provider detail; keep it in logs.
        raise HTTPException(
            status_code=502,
            detail="Speech-to-text provider rejected the audio.",
        )
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Unexpected provider response.") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────
def _client_error(exc: Exception) -> str:
    """Never forward driver/provider internals to the browser."""
    text = str(exc) or exc.__class__.__name__
    for token in (config.HANA_HOST, config.HANA_USER, config.HANA_PASSWORD,
                  config.MSSQL_HOST, config.MSSQL_USER, config.MSSQL_PASSWORD,
                  config.SAP_B1_PASSWORD, config.SERVICE_LAYER_BASE):
        if token:
            text = text.replace(str(token), "[redacted]")
    return text[:400]


async def generate_chat_response(query: str, session_id: str, employee_id: str):
    """SSE generator. Owns its DB sessions; collects every table for persistence."""
    full_text: list[str] = []
    tables: list[dict] = []
    chart_payload: dict | None = None
    form_payload: dict | None = None
    error_text: str | None = None

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
                yield _sse({"type": "error", "text": "You do not have access to this conversation."})
                yield _sse({"type": "done"})
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
        history = list(history_result.scalars().all())

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
        async for chunk in stream_chat_query(query, history, employee_id=employee_id):
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
                # A single answer can contain several tables (e.g. a join
                # follow-up). Only the last one used to survive into history,
                # so a reloaded conversation silently lost data.
                if len(tables) < config.MAX_RESULT_TABLES:
                    tables.append(
                        {
                            "entity": data.get("entity"),
                            "data": data.get("data"),
                            "meta": data.get("meta"),
                            "chart": None,
                        }
                    )
            elif kind == "chart":
                if tables and tables[-1]["chart"] is None:
                    tables[-1]["chart"] = data
                chart_payload = chart_payload or data
            elif kind == "form":
                form_payload = data
            elif kind == "error":
                error_text = str(data.get("text", ""))
                full_text.append(error_text)
    finally:
        text = "".join(full_text).strip()
        try:
            async with create_short_lived_session() as db:
                db.add(
                    ChatMessage(
                        session_id=session_id,
                        employee_id=employee_id,
                        role="assistant",
                        content=text,
                        msg_type=(
                            "form" if form_payload
                            else "chart" if chart_payload
                            else "tabular" if tables
                            else "text"
                        ),
                        data_payload=_dump(tables or None),
                        entity=tables[0]["entity"] if tables else None,
                        chart_payload=_dump(chart_payload),
                        form_payload=_dump(form_payload),
                        meta_payload=_dump(_meta_payload(tables, error_text)),
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

                    obj.updated_at = _dt.datetime.now(_dt.UTC)
                await db.commit()
        except Exception as exc:  # never break the stream because of persistence
            log.warning("Could not persist assistant message: %s", exc)


def _meta_payload(tables: list[dict], error_text: str | None) -> dict | None:
    """Primary table's metadata (source, sql, simulated…) + the error, if any."""
    meta = dict(tables[0].get("meta") or {}) if tables else {}
    if error_text:
        meta["error"] = error_text[:500]
    if len(tables) > 1:
        meta["tableCount"] = len(tables)
    return meta or None


def _dump(value) -> str | None:
    """Serialise for storage, capping rows per table so the DB cannot explode."""
    if value is None:
        return None
    if isinstance(value, list):
        for table in value:
            if not isinstance(table, dict):
                continue
            rows = table.get("data")
            if isinstance(rows, list) and len(rows) > config.MAX_PERSISTED_ROWS:
                table["data"] = rows[: config.MAX_PERSISTED_ROWS]
                meta = table.get("meta")
                if not isinstance(meta, dict):
                    meta = {}
                    table["meta"] = meta
                meta["persistedTruncated"] = True
    return json.dumps(value, default=str)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user_context: dict = Depends(set_tenant_context),
):
    employee_id = user_context["employee_id"]
    audit.set_context(employee_id=employee_id, session_id=request.session_id,
                      company_db=user_context.get("company_db"))

    return StreamingResponse(
        generate_chat_response(request.query, request.session_id, employee_id),
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
    limit: int = 200,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    ctx = validate_and_extract(credentials)
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.employee_id == ctx["employee_id"])
        .order_by(ChatSession.updated_at.desc().nullslast(), ChatSession.id.desc())
        .limit(min(max(limit, 1), 500))
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


def _loads(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _normalise_tables(payload) -> tuple[list | None, list]:
    """History rows hold either a bare row list (legacy) or [{data, meta, chart}]."""
    if not isinstance(payload, list) or not payload:
        return None, []
    if isinstance(payload[0], dict) and "data" in payload[0]:
        return payload[0].get("data"), payload
    return payload, [{"data": payload, "meta": None, "chart": None, "entity": None}]


@app.get("/history/{session_id}")
async def get_history(
    session_id: str,
    limit: int = 400,
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
        .limit(min(max(limit, 1), 1000))
    )
    messages = result.scalars().all()

    out = []
    for m in messages:
        primary_rows, tables = _normalise_tables(_loads(m.data_payload))
        meta = _loads(m.meta_payload)
        out.append(
            {
                "role": m.role,
                "content": m.content,
                "type": m.msg_type,
                "data": primary_rows,
                "tables": tables,
                "entity": m.entity,
                "chart": _loads(m.chart_payload),
                "form": _loads(m.form_payload),
                "meta": meta,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {"messages": out}


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


def _sweep_expired_uploads() -> int:
    """Delete uploads older than CIRA_UPLOAD_TTL_HOURS.

    Attachments are folded into the question text at send time, so keeping the
    bytes forever only grows the disk (the old build never deleted anything).
    """
    directory = Path(config.UPLOAD_DIR)
    if not directory.exists():
        return 0
    cutoff = time.time() - config.UPLOAD_TTL_HOURS * 3600
    removed = 0
    for path in directory.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    ctx = validate_and_extract(credentials)
    import uuid

    # Read with a cap *before* deciding: the old code buffered the whole body
    # (unbounded) and only then compared len(raw), so one large POST was enough
    # to exhaust the process's memory.
    raw = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    safe_name = Path(file.filename or "upload.bin").name
    file_id = uuid.uuid4().hex
    target = Path(config.UPLOAD_DIR) / f"{ctx['employee_id']}_{file_id}_{safe_name}"

    preview = ""
    suffix = Path(safe_name).suffix.lower()
    if suffix in TEXTUAL_SUFFIXES:
        preview = raw.decode("utf-8", errors="replace")[:6000]
        # Persist only what the model can actually use; skip binaries entirely.
        target.write_bytes(raw[:6000])
    else:
        raise HTTPException(
            status_code=415,
            detail=(
                "Only plain-text attachments (.txt/.md/.csv/.json/...) can be read into "
                "a question; other file types are not stored."
            ),
        )

    audit.event("upload", employee_id=ctx["employee_id"], name=safe_name, bytes=len(raw))
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
