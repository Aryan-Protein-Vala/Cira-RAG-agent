"""Session authentication.

The project notes claimed "HMAC-SHA256 JWT-style session tokens", but the code
actually accepted *any* base64 blob the browser produced: anyone could mint a
token for any employee id (including ADMIN-001) with two lines of JavaScript,
and every /history, /sessions and /chat call trusted it.

This module implements what was advertised:
  * tokens are minted server-side by POST /auth/login
  * payload.signature, HMAC-SHA256 over the payload with a server secret
  * constant-time verification, issued-at + expiry enforcement
  * unsigned/legacy tokens are rejected with 401 so the UI can re-authenticate

Swap `authenticate()` for your IdP / SAP OUSR lookup when SSO is wired up; the
rest of the app only depends on `validate_and_extract()`.
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

from fastapi import HTTPException, status
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
                 ttl: int | None = None) -> dict:
    now = int(time.time())
    exp = now + int(ttl or config.TOKEN_TTL_SECONDS)
    payload = {
        "sub": employee_id,
        "employee_id": employee_id,
        "name": name or employee_id,
        "roles": roles or ["employee"],
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


def validate_and_extract(credentials: HTTPAuthorizationCredentials) -> dict:
    """FastAPI dependency helper — returns the verified user context."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    return verify_token(credentials.credentials)


def authenticate(employee_id: str, password: str) -> dict | None:
    """Validate sign-in credentials.

    Replace this body with an LDAP/Azure AD/SAP OUSR check for production; the
    demo rules below are configurable through the environment.
    """
    employee_id = (employee_id or "").strip()
    if not employee_id or not password:
        return None

    if employee_id.lower() == config.ADMIN_ID.lower():
        if hmac.compare_digest(password, config.ADMIN_PASSWORD):
            return {"employee_id": "ADMIN-001", "name": "System Admin",
                    "roles": ["admin", "employee"]}
        return None

    if config.ALLOW_ANY_EMPLOYEE:
        return {"employee_id": employee_id, "name": employee_id, "roles": ["employee"]}
    return None


async def exchange_for_sap_token(user_token: str, employee_id: str) -> str:
    """OAuth2 on-behalf-of exchange placeholder.

    CIRA currently reaches SAP with a read-only technical user (see
    Backend/.env.example). When your IdP is configured, exchange the user's
    token here for a user-scoped SAP token and pass it down to the SAP client
    so row-level authorisations apply per employee.
    """
    return f"cira-service-account:{employee_id}"
