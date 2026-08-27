"""Admin API — the multi-tenant company-DB registry.

This replaces the first cut of the feature, which had four show-stoppers:

1. `POST /admin/login` compared the password against a literal in source
   (`admin` / the README demo password), ignoring every config knob — a
   permanent backdoor that minted the `admin` role anyone who read the repo
   could use. Admins now sign in through /auth/login and these routes require
   the `admin` role from a real token.
2. `POST /auth/login` refused *every* sign-in until a `company_connections`
   row existed, so a fresh deployment was locked out of itself (9 tests failed).
   The check is now "is this company DB known" = env registry + admin rows + the
   deployment default, and `CIRA_REQUIRE_REGISTERED_COMPANY_DB=true` tightens it.
3. SAP passwords were stored (and would have been echoed by future listings) in
   plaintext, and the HANA user/password was reused for the Service Layer login
   — wrong principal and a needless second destination for the secret.
   Secrets are now `env:VAR` / `enc:<fernet>` and never returned.
4. Any admin could point the server at any host:port (SSRF to the cloud metadata
   IP) with no validation and no trace in the log. Targets are validated and
   every write is audited.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import audit
import config
import credential_store as cira_secrets
import tenants
from auth import require_roles
from database import CompanyConnection, get_db

log = logging.getLogger("cira.admin")

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("admin"))],
)


class ConnectionCreate(BaseModel):
    company_db: str = Field(..., min_length=2, max_length=127)
    display_name: str = Field(default="", max_length=120)
    hana_address: str = Field(..., min_length=1, max_length=253)
    hana_port: int = Field(default=30013, ge=1, le=65535)
    hana_user: str = Field(..., min_length=1, max_length=64)
    # 'env:VAR_NAME' (nothing stored) or 'enc:<token>' — see Backend/credential_store.py
    hana_password: str = Field(..., min_length=1, max_length=4096)
    hana_encrypt: bool = True
    hana_extra_schemas: str = Field(default="", max_length=512)
    service_layer_port: int = Field(default=50000, ge=1, le=65535)
    sl_user: str = Field(default="", max_length=64)
    sl_password: str = Field(default="", max_length=4096)
    sl_use_tls: bool = True
    source_priority: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=500)
    test_first: bool = False


class ConnectionUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    hana_address: str | None = Field(default=None, min_length=1, max_length=253)
    hana_port: int | None = Field(default=None, ge=1, le=65535)
    hana_user: str | None = Field(default=None, min_length=1, max_length=64)
    hana_password: str | None = Field(default=None, min_length=1, max_length=4096)
    hana_encrypt: bool | None = None
    hana_extra_schemas: str | None = Field(default=None, max_length=512)
    service_layer_port: int | None = Field(default=None, ge=1, le=65535)
    sl_user: str | None = Field(default=None, max_length=64)
    sl_password: str | None = Field(default=None, max_length=4096)
    sl_use_tls: bool | None = None
    source_priority: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class TargetCheck(BaseModel):
    company_db: str = Field(..., min_length=2, max_length=127)
    hana_address: str = Field(..., min_length=1, max_length=253)
    hana_port: int = Field(default=30013, ge=1, le=65535)
    hana_user: str = Field(default="", max_length=64)
    hana_password: str = Field(default="", max_length=4096)
    service_layer_port: int = Field(default=50000, ge=1, le=65535)
    sl_user: str = Field(default="", max_length=64)
    sl_password: str = Field(default="", max_length=4096)


def _bad(message: str) -> None:
    # 422 as an int: the HTTP_422_* constant was renamed across starlette versions
    raise HTTPException(status_code=422, detail=message)


def _checked(fn):
    """Run a validator, turning a ValueError into a 422 instead of a 500."""
    try:
        return fn()
    except ValueError as exc:
        _bad(str(exc))
        raise AssertionError("unreachable") from exc


def _serialise(row: CompanyConnection) -> dict:
    """Safe projection: identity + topology, never secret material."""
    return {
        "id": row.id,
        "company_db": row.company_db,
        "display_name": row.display_name or row.company_db,
        "enabled": bool(row.enabled),
        "source_priority": row.source_priority or "",
        "hana_address": row.hana_host,
        "hana_port": row.hana_port,
        "hana_user": row.hana_user,
        "hana_encrypt": bool(row.hana_encrypt),
        "hana_extra_schemas": row.hana_extra_schemas or "",
        "service_layer_port": row.service_layer_port,
        "sl_user": row.sl_user or "",
        "sl_use_tls": bool(row.sl_use_tls),
        "notes": row.notes or "",
        "hana_secret_source": cira_secrets.describe(row.hana_secret),
        "sl_secret_source": cira_secrets.describe(row.sl_secret),
        # an `env:` reference that is not set on this host would otherwise fail at
        # query time with a confusing driver error — say so in the panel instead
        "hana_secret_resolved": bool(cira_secrets.resolve(row.hana_secret)),
        "sl_secret_resolved": bool(cira_secrets.resolve(row.sl_secret)) if row.sl_user else True,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validated_fields(payload) -> dict:
    """Schema/host/port/target checks shared by create and test."""
    company_db = tenants.valid_schema(payload.company_db)
    host = tenants.valid_host(payload.hana_address)
    port = tenants.valid_port(payload.hana_port, "hana_port")
    return {"company_db": company_db, "host": host, "port": port}


@router.get("/connections")
async def list_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CompanyConnection).order_by(CompanyConnection.company_db))
    rows = result.scalars().all()
    return {
        "connections": [_serialise(row) for row in rows],
        "count": len(rows),
        # env-registered company DBs are valid sign-ins too, and invisible here
        "from_environment": sorted(
            name for name in config.TENANTS if name not in tenants.registered_names()
        ),
        "secret_storage": {
            "encrypted_available": cira_secrets.available(),
            "plaintext_allowed": config.ALLOW_PLAINTEXT_SECRETS,
        },
    }


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    checked = _checked(lambda: _validated_fields(payload))
    secret = _checked(lambda: cira_secrets.validate_for_storage(payload.hana_password))
    sl_secret = (
        _checked(lambda: cira_secrets.validate_for_storage(payload.sl_password))
        if payload.sl_user.strip()
        else ""
    )
    if payload.sl_user.strip() and not sl_secret:
        _bad("A Service Layer user was given without a secret.")
    _checked(lambda: tenants.assert_safe_target(checked["host"], checked["port"]))
    _checked(lambda: tenants.valid_port(payload.service_layer_port, "service_layer_port"))

    row = CompanyConnection(
        company_db=checked["company_db"],
        display_name=payload.display_name.strip() or checked["company_db"],
        enabled=1,
        source_priority=payload.source_priority.strip(),
        hana_host=checked["host"],
        hana_port=checked["port"],
        hana_user=payload.hana_user.strip(),
        hana_secret=secret,
        hana_encrypt=1 if payload.hana_encrypt else 0,
        hana_extra_schemas=payload.hana_extra_schemas.strip(),
        service_layer_port=payload.service_layer_port,
        sl_user=payload.sl_user.strip(),
        sl_secret=sl_secret,
        sl_use_tls=1 if payload.sl_use_tls else 0,
        notes=payload.notes.strip(),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{checked['company_db']} is already registered.",
        ) from None
    await db.refresh(row)

    await tenants.refresh(force=True)   # make it immediately sign-in-able
    audit.event("tenant_created", employee_id=user["employee_id"],
                company_db=row.company_db, host=row.hana_host, port=row.hana_port,
                secret_source=cira_secrets.describe(row.hana_secret))
    response = _serialise(row)
    if payload.test_first:
        response["test"] = await _test_row(row)
    return response


@router.post("/connections/test")
async def test_target(payload: TargetCheck, user: dict = Depends(require_roles("admin"))):
    """Try a connection *before* saving it — nothing is written by this call."""
    checked = _checked(lambda: _validated_fields(payload))
    _checked(lambda: tenants.assert_safe_target(checked["host"], checked["port"]))
    try:
        password = (
            cira_secrets.resolve(cira_secrets.validate_for_storage(payload.hana_password))
            if payload.hana_password else ""
        )
    except ValueError as exc:  # a reachability test without a secret is still useful
        log.debug("test_target secret: %s", exc)
        password = ""
    settings = {
        "COMPANY_DB": checked["company_db"],
        "HANA_SCHEMA": checked["company_db"],
        "HANA_HOST": checked["host"],
        "HANA_PORT": checked["port"],
        "HANA_USER": payload.hana_user.strip(),
        "HANA_PASSWORD": password,
        "HANA_ENABLED": bool(payload.hana_user.strip() and password),
    }
    import asyncio

    return await asyncio.to_thread(tenants.test_tenant, settings)


async def _get_row(db: AsyncSession, connection_id: int) -> CompanyConnection:
    result = await db.execute(
        select(CompanyConnection).where(CompanyConnection.id == connection_id)
    )
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return row


async def _test_row(row: CompanyConnection) -> dict:
    import asyncio

    try:
        settings = tenants.build_settings(row)
    except ValueError as exc:
        return {"ok": False, "checks": [{"target": "config", "ok": False, "detail": str(exc)}]}
    return await asyncio.to_thread(tenants.test_tenant, settings)


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: int, db: AsyncSession = Depends(get_db)):
    row = await _get_row(db, connection_id)
    return await _test_row(row)


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, connection_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _serialise(row)

    if "hana_address" in changes or "hana_port" in changes:
        host = tenants.valid_host(changes.get("hana_address", row.hana_host))
        port = tenants.valid_port(changes.get("hana_port", row.hana_port), "hana_port")
        _checked(lambda: tenants.assert_safe_target(host, port))
        row.hana_host, row.hana_port = host, port
    if changes.get("hana_password"):
        row.hana_secret = _checked(
            lambda: cira_secrets.validate_for_storage(changes.pop("hana_password"))
        )
    changes.pop("hana_password", None)
    if changes.get("sl_password"):
        row.sl_secret = _checked(
            lambda: cira_secrets.validate_for_storage(changes.pop("sl_password"))
        )
    changes.pop("sl_password", None)

    for field, value in changes.items():
        if field == "enabled":
            row.enabled = 1 if value else 0
        elif field == "hana_encrypt":
            row.hana_encrypt = 1 if value else 0
        elif field == "sl_use_tls":
            row.sl_use_tls = 1 if value else 0
        elif field == "service_layer_port":
            row.service_layer_port = _checked(
                lambda current=value: tenants.valid_port(current, "service_layer_port")
            )
        else:
            setattr(row, field, value)

    await db.commit()
    await db.refresh(row)
    await tenants.refresh(force=True)
    audit.event("tenant_updated", employee_id=user["employee_id"], company_db=row.company_db,
                fields=sorted(changes))
    return _serialise(row)


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, connection_id)
    company_db = row.company_db
    await db.execute(delete(CompanyConnection).where(CompanyConnection.id == connection_id))
    await db.commit()
    await tenants.refresh(force=True)
    audit.event("tenant_deleted", employee_id=user["employee_id"], company_db=company_db)
    return {"ok": True, "removed": company_db}


@router.get("/overview")
async def overview(user: dict = Depends(require_roles("admin"))):
    """What an operator checks after editing tenants: who is live, and why not."""
    await tenants.refresh()
    sources = config.enabled_sources()
    return {
        "global_sources_enabled": sources,
        "data_source": config.DATA_SOURCE,
        "company_dbs": sorted(config.TENANTS),
        "from_admin_panel": tenants.registered_names(),
        "per_tenant": {
            name: {
                "sources": config.enabled_sources(config.TENANTS.get(name)),
                "hana_host_set": bool((config.TENANTS.get(name) or {}).get("HANA_HOST")),
                "schema": (config.TENANTS.get(name) or {}).get("HANA_SCHEMA"),
            }
            for name in sorted(config.TENANTS)
        },
        "policies": {
            "writes_enabled": config.SAP_WRITE_ENABLED,
            "allow_any_employee": config.ALLOW_ANY_EMPLOYEE,
            "plaintext_secrets": config.ALLOW_PLAINTEXT_SECRETS,
            "loopback_targets": config.ALLOW_LOOPBACK_TARGETS,
            "require_registered_company_db": config.REQUIRE_REGISTERED_COMPANY_DB,
        },
    }
