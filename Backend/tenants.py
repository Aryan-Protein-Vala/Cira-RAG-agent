"""Company-DB (tenant) registry: environment config + admin-panel rows.

Both the SQL guard and the SAP drivers take their connection parameters from a
tenant dict. Tenants can come from:

  * `CIRA_TENANTS` / `CIRA_TENANT_<NAME>_<SETTING>` / `CIRA_TENANTS_JSON` (config.py)
  * the `company_connections` table, maintained by the admin panel (`/admin/*`)

DB rows are validated here (schema identifier, host, port, target reachability)
and merged into `config.TENANTS`, so `config.tenant_for()` is the single lookup
for the whole app — no second, weaker path for "dynamic" tenants.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
from typing import Any

import config
import credential_store as cira_secrets

log = logging.getLogger("cira.tenants")

# SAP HANA schema/company names: identifier-shaped, may contain $ and #, max 127.
SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#@]{0,126}$")
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9_]([A-Za-z0-9_.-]*[A-Za-z0-9_])?$"
)
INSTANCE_RE = re.compile(r"^[A-Za-z0-9_\\]{1,64}$")  # SQL Server named instances

CACHE_TTL_S = config.TENANT_CACHE_TTL_S

_lock = threading.RLock()
_loaded_at: float = 0.0
_rows: dict[str, dict] = {}
_source_ids: dict[str, int] = {}


# ── validation ───────────────────────────────────────────────────────────────
def valid_schema(name: str) -> str:
    clean = (name or "").strip()
    if not SCHEMA_RE.match(clean):
        raise ValueError(
            "Company DB / schema must be identifier-shaped (letters, digits, _, $, #; "
            f"max 127 chars). Got {clean!r}."
        )
    return clean.upper()


def valid_host(host: str) -> str:
    clean = (host or "").strip()
    if len(clean) > 253:
        raise ValueError("Host is too long.")
    if not (HOSTNAME_RE.match(clean) or _is_ip(clean) or INSTANCE_RE.match(clean)):
        raise ValueError(f"Host {clean!r} is not a valid hostname, IP or named instance.")
    return clean


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def valid_port(port: Any, name: str = "port") -> int:
    try:
        number = int(port)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer.") from None
    if not 1 <= number <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535.")
    return number


def assert_safe_target(host: str, port: int) -> None:
    """Refuse targets that turn CIRA into an internal port scanner.

    The app connects wherever an admin tells it to; without this a stolen admin
    session is a free SSRF against the cloud metadata service and the loopback
    range. Set CIRA_ALLOW_LOOPBACK_TARGETS=true when CIRA legitimately runs on
    the database host (that is a documented deployment in the README).
    """
    blocked = {
        "localhost", "metadata.google.internal", "metadata",
        "instance", "169.254.169.254",
    }
    lowered = host.strip().lower().rstrip(".")
    if lowered in blocked and not config.ALLOW_LOOPBACK_TARGETS:
        raise ValueError(f"Target {host!r} is refused (cloud metadata / loopback alias).")
    addresses = [lowered]
    if not _is_ip(lowered):
        try:
            infos = socket.getaddrinfo(lowered, port, proto=socket.IPPROTO_TCP)
            addresses = [info[4][0] for info in infos] or [lowered]
        except socket.gaierror:
            return  # unresolvable now is fine: DNS may come up later; connect() will fail clearly
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if config.ALLOW_LOOPBACK_TARGETS:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError(
                f"Target {host!r} resolves to {address}, which CIRA refuses to connect to "
                "(loopback/link-local/metadata). Set CIRA_ALLOW_LOOPBACK_TARGETS=true only "
                "when the database really is on this host."
            )
        if ip.version == 6 and ip.is_loopback:
            raise ValueError(f"Target {host!r} resolves to an IPv6 loopback address.")


# ── row -> tenant override dict ──────────────────────────────────────────────
def build_settings(row) -> dict[str, Any]:
    """Translate a CompanyConnection ORM row into a config tenant override."""
    company_db = valid_schema(row.company_db)
    host = valid_host(row.hana_host)
    port = valid_port(row.hana_port, "hana_port")
    password = cira_secrets.resolve(row.hana_secret)
    tenant: dict[str, Any] = {
        "COMPANY_DB": company_db,
        "HANA_SCHEMA": company_db,
        "HANA_HOST": host,
        "HANA_PORT": port,
        "HANA_USER": (row.hana_user or "").strip(),
        "HANA_PASSWORD": password,
        # Enabled on the presence of the *reference*: an unset env var must fail
        # with "env var X is not set", not silently fall back to the sandbox.
        "HANA_ENABLED": bool((row.hana_user or "").strip() and (row.hana_secret or "").strip()),
        "HANA_SECRET_RESOLVED": bool(password),
        "HANA_ENCRYPT": bool(row.hana_encrypt),
        "SAP_B1_HOST": host,
        "SAP_B1_PORT": valid_port(row.service_layer_port or 50000, "service_layer_port"),
        "SAP_B1_COMPANY_DB": company_db,
        "MSSQL_DATABASE": company_db,
    }
    if (row.hana_extra_schemas or "").strip():
        tenant["HANA_EXTRA_SCHEMAS"] = [
            part.strip().upper() for part in row.hana_extra_schemas.split(",") if part.strip()
        ]
    # Service Layer credentials are B1 users (e.g. 'manager'), NOT the HANA schema
    # user — the first cut of the admin panel reused them and posted the HANA
    # password to the Service Layer, which is both wrong and a needless spread.
    if (row.sl_user or "").strip():
        sl_password = cira_secrets.resolve(row.sl_secret)
        scheme = "https" if row.sl_use_tls else "http"
        tenant["SERVICE_LAYER_BASE"] = (
            f"{scheme}://{host}:{tenant['SAP_B1_PORT']}/b1s/v1"
        )
        tenant["SAP_B1_USER"] = row.sl_user.strip()
        tenant["SAP_B1_PASSWORD"] = sl_password
        tenant["SERVICE_LAYER_ENABLED"] = True
    else:
        tenant["SERVICE_LAYER_ENABLED"] = False
    return tenant


# ── registry sync (SQLite -> config.TENANTS) ─────────────────────────────────
def _row_to_tenant(row) -> tuple[str, dict]:
    settings = build_settings(row)
    return str(row.company_db).strip().upper(), settings


def sync(rows: list) -> int:
    """Replace the DB-backed part of the registry. Returns the number registered."""
    global _loaded_at, _rows, _source_ids
    with _lock:
        previous = set(_source_ids)
        fresh: dict[str, dict] = {}
        ids: dict[str, int] = {}
        for row in rows:
            try:
                name, settings = _row_to_tenant(row)
            except ValueError as exc:
                log.warning("Ignoring tenant %r: %s", getattr(row, "company_db", "?"), exc)
                continue
            fresh[name] = settings
            ids[name] = int(row.id)
        for stale in previous - set(fresh):
            config.forget_tenant(stale)
        for name, settings in fresh.items():
            config.register_tenant(name, settings)
        _rows, _source_ids, _loaded_at = fresh, ids, time.time()
        return len(fresh)


def invalidate() -> None:
    with _lock:
        global _loaded_at
        _loaded_at = 0.0


def is_fresh() -> bool:
    with _lock:
        return bool(_loaded_at) and (time.time() - _loaded_at) < CACHE_TTL_S


def registered_names() -> list[str]:
    with _lock:
        return sorted(_rows)


def secret_source(row) -> dict:
    """What the admin UI may know about a stored secret — never the value."""
    return {
        "hana_secret_source": cira_secrets.describe(getattr(row, "hana_secret", "")),
        "sl_secret_source": cira_secrets.describe(getattr(row, "sl_secret", "")),
    }


async def refresh(force: bool = False) -> int:
    """Reload the registry from the DB (called at startup, after CRUD, on demand)."""
    if not force and is_fresh():
        return len(_rows)
    from sqlalchemy import select

    from database import CompanyConnection, create_short_lived_session

    async with create_short_lived_session() as db:
        result = await db.execute(
            select(CompanyConnection).where(CompanyConnection.enabled.is_(True))
        )
        rows = list(result.scalars().all())
    count = sync(rows)
    log.info("Tenant registry loaded: %d company DB(s) from the admin panel", count)
    return count


def known(company_db: str) -> bool:
    """Is this company DB sign-in-able? env registry + admin panel + default."""
    name = config.normalise_tenant_key(company_db or "")
    if not name:
        return True  # '' means "use the deployment default"
    return config.tenant_for(company_db) is not None


# ── connectivity test (admin panel "Test") ──────────────────────────────────
def test_tenant(settings: dict, timeout_s: float = 8.0) -> dict:
    """Ping HANA (and the Service Layer if configured) for one tenant dict."""
    import asyncio

    async def _run() -> dict:
        from sap.hana_backend import HanaBackend

        results: dict[str, Any] = {"company_db": settings.get("HANA_SCHEMA"), "checks": []}
        host, port = settings.get("HANA_HOST"), settings.get("HANA_PORT")
        if host:
            reachable = await asyncio.to_thread(_tcp, str(host), int(port or 30013), timeout_s)
            results["checks"].append({"target": "hana tcp", "ok": reachable["ok"],
                                      "detail": reachable["detail"]})
            if reachable["ok"]:
                try:
                    backend = HanaBackend(
                        host=str(host), port=int(port or 30013),
                        user=str(settings.get("HANA_USER") or ""),
                        password=str(settings.get("HANA_PASSWORD") or ""),
                        schema=str(settings.get("HANA_SCHEMA") or ""),
                    )
                    probe = backend.ping(force=True)
                    results["checks"].append({
                        "target": "hana login",
                        "ok": bool(probe.get("ok")),
                        "detail": probe.get("error") or f"schema={probe.get('schema')}",
                    })
                    if probe.get("ok"):
                        tables = backend.list_tables(limit=100000)
                        results["tables_visible"] = len(tables)
                        try:
                            backend.close()
                        except Exception:
                            pass
                except Exception as exc:
                    results["checks"].append({"target": "hana login", "ok": False,
                                              "detail": str(exc)[:200]})
        if settings.get("SERVICE_LAYER_ENABLED"):
            from sap.service_layer import ServiceLayerBackend

            try:
                sl = ServiceLayerBackend()
                probe = sl.ping(force=True)
                results["checks"].append({"target": "service layer", "ok": bool(probe.get("ok")),
                                          "detail": probe.get("error") or "login ok"})
            except Exception as exc:
                results["checks"].append({"target": "service layer", "ok": False,
                                          "detail": str(exc)[:200]})
        results["ok"] = any(c["ok"] for c in results["checks"]) if results["checks"] else False
        return results

    return asyncio.run(_run())


def _tcp(host: str, port: int, timeout_s: float) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"ok": True, "detail": f"{host}:{port} reachable"}
    except Exception as exc:
        return {"ok": False, "detail": f"{host}:{port} — {exc.__class__.__name__}"}
