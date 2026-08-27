"""Secret-at-rest policy for the tenant registry.

Import it as `credential_store` — the module is deliberately NOT called `secrets`,
because shadowing the stdlib module breaks starlette (`from secrets import token_hex`)
for anything installed in the same environment.


The admin panel lets an operator save SAP credentials in SQLite. Storing those
as plaintext next to the chat history is how you end up with a second credential
leak (the first one was a default value in config.py, found in review). So a
stored secret must be one of:

  env:VAR_NAME      — nothing on disk; resolved from the process environment.
                      RECOMMENDED for production.
  enc:<token>       — Fernet (AES-128-CBC + HMAC-SHA256) keyed by CIRA_SECRET_KEY
                      (HKDF-expanded). Requires the `cryptography` package.
  <raw password>    — encrypted at rest with the same key (this is what the admin
                      panel does, so operators never have to pre-encrypt anything).
                      Stored raw only when CIRA_ALLOW_PLAINTEXT_SECRETS=true, which
                      surfaces as `secret_source=plaintext` in the admin API so it
                      cannot be forgotten.

Nothing here is ever returned by an API response — only `secret_source`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

import config

log = logging.getLogger("cira.secrets")

ENV_PREFIX = "env:"
ENC_PREFIX = "enc:"


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    digest = hashlib.sha256(b"cira-tenant-secret/v1|" + _key_material()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _key_material() -> bytes:
    if config.SECRET_KEY:
        return config.SECRET_KEY.encode("utf-8")
    # Same fallback file auth.py uses, so the key survives redeploys locally.
    from pathlib import Path

    path = Path(config.DATA_DIR) / ".session_secret"
    return path.read_bytes() if path.exists() else b"cira-insecure-fallback-key"


def available() -> bool:
    return _fernet() is not None


def describe(value: str | None) -> str:
    """How a stored secret is protected — safe to expose to the admin UI."""
    raw = (value or "").strip()
    if not raw:
        return "none"
    if raw.startswith(ENV_PREFIX):
        return "env"
    if raw.startswith(ENC_PREFIX):
        return "encrypted"
    return "plaintext"


def validate_for_storage(value: str | None) -> str:
    """Normalise a secret submitted by the admin panel into what gets stored.

    Accepted inputs and what happens to each:

      env:VAR_NAME   stored as a reference only — nothing secret on disk
      enc:<token>    stored as given, after verifying it decrypts with this key
      <raw password>  encrypted at rest with Fernet (preferred), or stored raw
                      only when CIRA_ALLOW_PLAINTEXT_SECRETS=true, or rejected
                      outright if `cryptography` is missing and plaintext is off
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError(
            "A secret is required: type the password (it will be encrypted at rest), "
            "or use `env:VAR_NAME` to keep nothing on disk."
        )
    if raw.startswith(ENV_PREFIX):
        name = raw[len(ENV_PREFIX):].strip()
        if not name.replace("_", "").isalnum() or name[:1].isdigit():
            raise ValueError(f"`env:{name}` is not a valid environment variable name.")
        return f"{ENV_PREFIX}{name}"
    if raw.startswith(ENC_PREFIX):
        token = raw[len(ENC_PREFIX):]
        fernet = _fernet()
        if fernet is None:
            raise ValueError(
                "Verifying an `enc:` value needs the `cryptography` package "
                "(pip install cryptography). Use `env:VAR_NAME` instead."
            )
        try:  # reject anything we cannot read back later
            fernet.decrypt(token.encode("ascii"))
        except Exception as exc:
            raise ValueError(
                "`enc:` value does not decrypt with this CIRA_SECRET_KEY. Re-encrypt it, "
                "or paste the raw password and let CIRA encrypt it for you."
            ) from exc
        return raw
    if raw.startswith("plain:"):
        raw = raw[len("plain:"):]
    if config.ALLOW_PLAINTEXT_SECRETS:
        log.warning(
            "Storing a tenant secret in PLAINTEXT in %s because CIRA_ALLOW_PLAINTEXT_SECRETS=true. "
            "Do not ship this to production.",
            config.DATABASE_PATH,
        )
        return raw
    if not available():
        raise ValueError(
            "Cannot encrypt a secret at rest because the `cryptography` package is missing. "
            "Install it (pip install cryptography) or store the password as `env:VAR_NAME`."
        )
    return encrypt(raw)


def encrypt(plain: str) -> str:
    """Produce an `enc:` value (helper for ops scripts and tests)."""
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("cryptography is not installed; use env:VAR_NAME instead.")
    return ENC_PREFIX + fernet.encrypt(plain.encode("utf-8")).decode("ascii")


def resolve(value: str | None) -> str:
    """Turn a stored secret into the live password string ('' when unset)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith(ENV_PREFIX):
        return os.getenv(raw[len(ENV_PREFIX):], "").strip()
    if raw.startswith(ENC_PREFIX):
        fernet = _fernet()
        if fernet is None:
            log.error("Tenant secret is `enc:` but cryptography is missing — treating as unset.")
            return ""
        try:
            return fernet.decrypt(raw[len(ENC_PREFIX):].encode("ascii")).decode("utf-8")
        except Exception as exc:
            # A rotated CIRA_SECRET_KEY makes stored values unreadable.
            log.error("Could not decrypt a stored tenant secret (%s). Re-save it.", exc.__class__.__name__)
            return ""
    return raw
