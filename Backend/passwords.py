"""One place where passwords are hashed and checked.

Why this module exists
----------------------
The codebase previously used ``passlib.context.CryptContext(schemes=["bcrypt"])``
in four separate files (``admin_routes.py``, ``seed_admins.py``,
``seed_tenant.py``, ``create_mock_users.py``, ``create_superadmin.py``).

passlib 1.7.4 is its last release (2020). It detects the bcrypt version by
reading ``bcrypt.__about__.__version__``, which bcrypt removed in 4.1, and its
"wrap bug" self-test feeds an over-long password to ``bcrypt.hashpw()``, which
bcrypt >= 4.1 rejects with ``ValueError: password cannot be longer than 72
bytes``. The net effect on a clean install was that **no password could be
hashed or verified at all** - every partner admin, superadmin and seeded
account was unusable - while the test suite stayed green because it never
exercised the hashing path.

Calling bcrypt directly removes the dead dependency and the version sniffing.
bcrypt is a hard dependency; there is no fallback to plaintext, ever.
"""

from __future__ import annotations

import logging

import bcrypt

log = logging.getLogger("cira.passwords")

# Cost factor. 12 is ~250 ms on commodity hardware and is the current sane
# default for a login endpoint; raise it per deployment if you like latency.
BCRYPT_ROUNDS = 12

# bcrypt truncates input at 72 bytes and (>= 4.1) raises on anything longer.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Return a bcrypt hash. Raises ValueError on an empty password."""
    if not password:
        raise ValueError("Refusing to hash an empty password.")
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        log.warning(
            "Password longer than %d bytes was truncated before hashing "
            "(bcrypt's documented limit).", BCRYPT_MAX_BYTES,
        )
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check. A malformed stored hash returns False, never raises."""
    if not password or not password_hash:
        return False
    try:
        raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        log.warning("Password verification failed against a malformed hash: %s", exc)
        return False


__all__ = ["BCRYPT_ROUNDS", "hash_password", "verify_password"]
