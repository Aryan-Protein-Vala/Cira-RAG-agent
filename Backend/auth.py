"""Session authentication and per-request tenant binding.

The project notes claimed "HMAC-SHA256 JWT-style session tokens", but the code
used to accept *any* base64 blob the browser produced: anyone could mint a
token for any employee id (including ADMIN-001) with two lines of JavaScript.
This module implements what was advertised:

  * tokens are minted server-side by POST /auth/login
  * payload.signature, HMAC-SHA256 over the payload with a server secret
  * constant-time verification, issued-at + expiry enforcement
  * the company DB is fixed at sign-in and validated against the tenant
    registry, so a token can never be used to reach an unregistered schema
  * unsigned/tampered/expired tokens are rejected with 401

Nothing here is a user *directory*: `authenticate()` accepts the bootstrap
admin only, and only when CIRA_ADMIN_ID/CIRA_ADMIN_PASSWORD are configured.
There is deliberately no permissive default (the previous build shipped
a working demo pair in git *and* "any employee id + any password" = true).
Wire this to your IdP or an SAP `OUSR` lookup for real deployments; the rest of
the app only depends on `validate_and_extract()`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

log = logging.getLogger("cira.auth")

bearer_scheme = HTTPBearer(auto_error=True)


def _load_secret() -> bytes:
    if config.SECRET_KEY:
        return config.SECRET_KEY.encode("utf-8")
    key_file = Path(config.DATA_DIR) / ".session_secret"
    if key_file.exists():
        return key_file.read_text().strip().encode("utf-8")
    generated = secrets.token_urlsafe(48)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(generated)
    try:
        key_file.chmod(0o600)
    except Exception:  # pragma: no cover - windows
        pass
    log.warning(
        "CIRA_SECRET_KEY not set — generated one at %s. Set it explicitly in "
        "production so tokens survive redeploys across multiple hosts.",
        key_file,
    )
    return generated.encode("utf-8")


_SECRET = _load_secret()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    return _b64e(hmac.new(_SECRET, payload_b64.encode("ascii"), hashlib.sha256).digest())


def create_token(employee_id: str, name: str = "", roles: list[str] | None = None,
                 ttl: int | None = None, company_db: str | None = None) -> dict:
    now = int(time.time())
    exp = now + int(ttl or config.TOKEN_TTL_SECONDS)
    payload = {
        "sub": employee_id,
        "employee_id": employee_id,
        "name": name or employee_id,
        "roles": roles or ["employee"],
        "company_db": company_db or config.DEFAULT_COMPANY_DB,
        "iat": now,
        "exp": exp,
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    token = f"{payload_b64}.{_sign(payload_b64)}"
    return {"token": token, "expires_at": exp, "user": payload}


def verify_token(token: str) -> dict:
    if not token or "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token — please sign in again.",
        )
    payload_b64, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token signature is invalid — please sign in again.",
        )
    try:
        payload = json.loads(_b64d(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed session token.",
        ) from exc

    now = time.time()
    if float(payload.get("exp", 0)) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please sign in again.",
        )
    if float(payload.get("iat", now)) > now + 300:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not yet valid.")
    if not payload.get("employee_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no subject.")
    return payload


def bind_tenant(company_db: str, *, required: bool = True) -> dict | None:
    """Resolve + activate the tenant for the current context.

    Unknown company DBs are refused (when `required`) rather than silently
    running on whichever global config happens to be set — that was how a token
    could ask for "CLIENT_B_PROD" and actually receive the default schema's
    data while the UI printed the other name.
    """
    tenant = config.tenant_for(company_db)
    if tenant is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Company DB {company_db!r} is not configured for this deployment. "
                    "Ask an administrator to register it (CIRA_TENANTS)."
                ),
            )
        return None
    config.CURRENT_TENANT.set(tenant)
    return tenant


def validate_and_extract(credentials: HTTPAuthorizationCredentials) -> dict:
    """FastAPI dependency helper — verifies the token and binds its tenant."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    payload = verify_token(credentials.credentials)
    bind_tenant(payload.get("company_db") or config.DEFAULT_COMPANY_DB)
    return payload


def require_roles(*roles: str):
    """Dependency factory for endpoints that must not be open to every session."""

    allowed = {r.strip().lower() for r in roles if r and r.strip()}

    def dependency(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
        payload = validate_and_extract(credentials)
        user_roles = {str(r).lower() for r in (payload.get("roles") or [])}
        if allowed and not (user_roles & allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the roles: {', '.join(sorted(allowed))}.",
            )
        return payload

    return dependency


def authenticate(employee_id: str, password: str, company_db: str = "") -> dict | None:
    """Validate sign-in credentials.

    Two identities exist today: the bootstrap admin (only when explicitly
    configured) and, if the operator opted in, "any employee id" demo mode.
    A real deployment replaces this with an IdP or an `OUSR` check.
    """
    employee_id = (employee_id or "").strip()
    if not employee_id or not password:
        return None

    if config.ADMIN_ID and employee_id.lower() == config.ADMIN_ID.lower():
        if config.ADMIN_PASSWORD and hmac.compare_digest(password, config.ADMIN_PASSWORD):
            return {
                "employee_id": "ADMIN-001",
                "name": "System Admin",
                "roles": ["admin", "employee"],
                "company_db": company_db or config.DEFAULT_COMPANY_DB,
            }
        return None

    if config.ALLOW_ANY_EMPLOYEE:
        return {
            "employee_id": employee_id,
            "name": employee_id,
            "roles": ["employee"],
            "company_db": company_db or config.DEFAULT_COMPANY_DB,
        }
    return None


def exchange_for_sap_token(user_token: str, employee_id: str) -> str:
    """OAuth2 on-behalf-of exchange — placeholder, documented honestly.

    CIRA reaches SAP with one read-only technical user (Backend/.env), so every
    session shares the same ERP identity and SAP-side row-level authorisation is
    *not* per employee. Until an IdP is wired up, do not claim otherwise.
    """
    return f"cira-service-account:{employee_id}"
