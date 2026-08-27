"""
Central configuration for the CIRA backend.

Every tunable lives here and is driven by environment variables (loaded from
Backend/.env when present).  Nothing else in the codebase should call
os.getenv() directly -- that was one of the reasons the old code drifted
(different defaults for the same setting in agent.py and sap_b1_client.py).

Two rules this module exists to enforce:

1. NO credentials are ever defaulted in source.  A password that has a
   non-empty default is indistinguishable from "the operator configured this
   backend", which is how the previous build silently preferred a hard-coded
   MSSQL `sa` account over the intended HANA connection.
2. Backend selection is driven by explicit enablement (host present /
   *_ENABLED flag), never by "did a password happen to be set".
"""

from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load Backend/.env first (explicit), then any .env found from the CWD.
load_dotenv(BASE_DIR / ".env")
load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _list(name: str, default: str = "") -> list[str]:
    raw = _str(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Data source selection
#   auto      -> every enabled source, in DATA_SOURCE_ORDER (HANA first)
#   hana      -> SAP HANA only            (the production path: full SQL depth)
#   service   -> SAP B1 Service Layer only (OData, no joins/aggregates)
#   mssql     -> SQL Server only          (B1 on MS SQL)
#   simulator -> offline SQLite sandbox   (dev/CI only; always flagged simulated)
# ─────────────────────────────────────────────────────────────────────────────
DATA_SOURCE = _str("CIRA_DATA_SOURCE", "auto").lower()

# Preference order for `auto`. HANA is the primary: it is the only backend that
# can reach every table/view/UDF in the company schema with real SQL.
DATA_SOURCE_ORDER = _list("CIRA_DATA_SOURCE_ORDER", "hana,service,mssql,simulator")

# ── SAP HANA (direct SQL — this is the "deep" path) ──────────────────────────
# Host/user/schema have no defaults on purpose: an unconfigured HANA source must
# fail *loudly at startup*, not quietly fall back to sandbox data.
HANA_HOST = _str("HANA_HOST")
HANA_PORT = _int("HANA_PORT", 30013)
HANA_USER = _str("HANA_USER")
HANA_PASSWORD = _str("HANA_PASSWORD")
HANA_SCHEMA = _str("HANA_SCHEMA")
HANA_DATABASE_NAME = _str("HANA_DATABASE_NAME")
# A backend is a candidate iff it is explicitly enabled OR its host is set.
HANA_ENABLED = _bool("HANA_ENABLED", bool(HANA_HOST))
HANA_ENCRYPT = _bool("HANA_ENCRYPT", True)
HANA_VALIDATE_CERT = _bool("HANA_SSL_VALIDATE_CERT", False)
HANA_CONNECT_TIMEOUT_MS = _int("HANA_CONNECT_TIMEOUT_MS", 8000)
HANA_QUERY_TIMEOUT_S = _int("HANA_QUERY_TIMEOUT_S", 120)
HANA_POOL_SIZE = _int("HANA_POOL_SIZE", 4)
# Extra schemas the raw-SQL tool may read. The company schema is always allowed
# and the SYS allowlist in sql_guard.py is what makes "read-only" also mean
# "scoped": without it `SELECT * FROM "SYS"."USERS"` was accepted (SYSTEM user!).
HANA_EXTRA_SCHEMAS = [s.strip().upper() for s in _str("HANA_EXTRA_SCHEMAS", "").split(",") if s.strip()]

# ── Microsoft SQL Server (alternative to HANA, B1 on MS SQL) ────────────────
MSSQL_HOST = _str("MSSQL_HOST")
MSSQL_PORT = _int("MSSQL_PORT", 1433)
MSSQL_USER = _str("MSSQL_USER")
MSSQL_PASSWORD = _str("MSSQL_PASSWORD")
MSSQL_DATABASE = _str("MSSQL_DATABASE")
MSSQL_SCHEMA = _str("MSSQL_SCHEMA", "dbo")
MSSQL_CONNECT_TIMEOUT = _int("MSSQL_CONNECT_TIMEOUT", 8000)
MSSQL_QUERY_TIMEOUT = _int("MSSQL_QUERY_TIMEOUT", 120)
MSSQL_POOL_SIZE = _int("MSSQL_POOL_SIZE", 4)
MSSQL_ENABLED = _bool("MSSQL_ENABLED", bool(MSSQL_HOST))

# ── SAP Business One Service Layer (OData) ──────────────────────────────────
SAP_B1_HOST = _str("SAP_B1_HOST")
SAP_B1_PORT = _int("SAP_B1_PORT", 50000)
SAP_B1_COMPANY_DB = _str("SAP_B1_COMPANY_DB", HANA_SCHEMA)
SAP_B1_USER = _str("SAP_B1_USER")
SAP_B1_PASSWORD = _str("SAP_B1_PASSWORD")
SAP_B1_VERIFY_SSL = _bool("SAP_B1_VERIFY_SSL", False)
SAP_B1_TIMEOUT_S = _float("SAP_B1_TIMEOUT_S", 20.0)
SERVICE_LAYER_BASE = _str("SAP_B1_SERVICE_LAYER_URL").rstrip("/") or (
    f"https://{SAP_B1_HOST}:{SAP_B1_PORT}/b1s/v1" if SAP_B1_HOST else ""
)
SERVICE_LAYER_ENABLED = _bool(
    "SAP_B1_ENABLED", bool(SAP_B1_HOST and SAP_B1_USER and SAP_B1_PASSWORD)
)

# ── Multi-tenancy (company DB per request) ──────────────────────────────────
# The active company DB for the current request/asyncio task.  A tenant may
# override any setting above with CIRA_TENANT_<TENANT>_<SETTING>; that is what
# makes per-company isolation real instead of "same SYSTEM user, other schema".
TENANT_ENV_PREFIX = "CIRA_TENANT_"
DEFAULT_TENANT_NAME_RAW = "DEFAULT"
CURRENT_TENANT: ContextVar[dict | None] = ContextVar("CURRENT_TENANT", default=None)


def _normalise_tenant_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", (name or "").strip().upper())


def build_tenants() -> dict[str, dict]:
    """Tenant registry: company DB name -> config overrides for that tenant.

    `CIRA_TENANTS=a,b,c` registers tenants that otherwise inherit the global
    settings.  Per-tenant overrides use `CIRA_TENANT_<NAME>_<SETTING>`, e.g.

        CIRA_TENANTS=ACME_PROD,ACME_TEST
        CIRA_TENANT_ACME_TEST_MSSQL_HOST=10.0.0.7
        CIRA_TENANT_ACME_TEST_MSSQL_USER=cira_ro

    Every tenant starts with no credentials of its own; nothing is shared
    implicitly beyond what is configured globally.
    """
    # Key = normalised lookup name, value carries the *original* COMPANY_DB so a
    # Service Layer login / HANA schema always gets the exact SAP name.
    def _register(name: str, overrides: dict | None = None) -> None:
        key = _normalise_tenant_key(name)
        entry = dict(tenants.get(key, {}))
        entry.setdefault("COMPANY_DB", (name or "").strip() or DEFAULT_TENANT_NAME_RAW)
        entry.update(overrides or {})
        tenants[key] = entry

    default_raw = (HANA_SCHEMA or SAP_B1_COMPANY_DB or "DEFAULT").strip()
    tenants: dict[str, dict] = {}
    _register(default_raw)
    for name in _list("CIRA_TENANTS"):
        _register(name)

    # Explicit JSON blob (used by tests / k8s ConfigMaps): CIRA_TENANTS_JSON
    raw_json = _str("CIRA_TENANTS_JSON")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                for name, overrides in parsed.items():
                    if not isinstance(overrides, dict):
                        continue
                    _register(name, overrides)
        except json.JSONDecodeError as exc:  # pragma: no cover - misconfig
            raise ValueError(f"CIRA_TENANTS_JSON is not valid JSON: {exc}") from exc

    # Env overrides: CIRA_TENANT_<NAME>_<SETTING>
    known = {
        "HANA_HOST", "HANA_PORT", "HANA_USER", "HANA_PASSWORD", "HANA_SCHEMA",
        "HANA_DATABASE_NAME", "HANA_POOL_SIZE",
        "MSSQL_HOST", "MSSQL_PORT", "MSSQL_USER", "MSSQL_PASSWORD",
        "MSSQL_DATABASE", "MSSQL_SCHEMA", "MSSQL_POOL_SIZE",
        "SAP_B1_HOST", "SAP_B1_PORT", "SAP_B1_COMPANY_DB", "SAP_B1_USER",
        "SAP_B1_PASSWORD", "SERVICE_LAYER_BASE",
    }
    # CIRA_TENANT_<NAME>_<SETTING>: match the longest tenant name first so
    # "ACME" must not swallow "ACME_LIVE_MSSQL_HOST".
    by_key = sorted(
        ((_normalise_tenant_key(name), name) for name in tenants),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for env_name, value in os.environ.items():
        if not env_name.startswith(TENANT_ENV_PREFIX) or not value.strip():
            continue
        remainder = env_name[len(TENANT_ENV_PREFIX):]
        for tenant_key, tenant_name in by_key:
            if not remainder.startswith(tenant_key + "_"):
                continue
            setting = remainder[len(tenant_key) + 1:]
            if setting in known:
                tenants[tenant_name][setting] = value.strip()
            break
    return tenants


TENANTS = build_tenants()

# Backwards-compatible name kept so older references keep resolving.
MOCK_TENANTS = TENANTS


def tenant_for(company_db: str) -> dict | None:
    """Look up a tenant; unknown company DBs resolve to *nothing* (never a
    silent fall-through to whichever global config happens to be set)."""
    name = _normalise_tenant_key(company_db or "")
    if not name or name == "_":
        return TENANTS.get(DEFAULT_TENANT_NAME)
    return TENANTS.get(name)


def tenant_id_of(tenant: dict | None) -> str:
    """Stable key for backend pooling: one pooled connection set per company DB."""
    if not tenant:
        return DEFAULT_TENANT_NAME
    return _normalise_tenant_key(tenant.get("COMPANY_DB") or tenant.get("HANA_SCHEMA") or DEFAULT_TENANT_NAME)


def resolve(tenant: dict | None, setting: str, fallback: object) -> object:
    """Tenant override -> global config -> explicit fallback (single lookup path)."""
    if tenant:
        value = tenant.get(setting)
        if value not in (None, ""):
            return value
    global_value = globals().get(setting, None)
    if global_value in (None, ""):
        return fallback
    return global_value


# Which *_ENABLED flags were set *explicitly* by the operator.  An unset flag
# must never veto a source whose host is configured for a specific tenant —
# that (boolean defaults masquerading as intent) is what made MSSQL win before.
_EXPLICIT_ENABLE_FLAGS = {
    name for name in ("HANA_ENABLED", "MSSQL_ENABLED", "SAP_B1_ENABLED", "SERVICE_LAYER_ENABLED")
    if os.getenv(name) not in (None, "")
}

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _source_enabled(tenant: dict | None, *flag_names: str, requires: list[tuple[str, object]]) -> bool:
    """Explicit `*_ENABLED` flag (tenant then global) wins; otherwise the source
    is enabled iff every setting in `requires` resolves to a value."""
    for flag in flag_names:
        for scope in (tenant or {}, globals()):
            value = scope.get(flag)
            explicit = flag in _EXPLICIT_ENABLE_FLAGS or scope is not globals()
            if value not in (None, "") and explicit:
                return value is True or (
                    isinstance(value, str) and value.strip().lower() in _TRUTHY
                )
    return all(resolve(tenant, setting, global_value) for setting, global_value in requires)


_CANDON_ORDER = ("hana", "service", "mssql", "simulator")


def enabled_sources(tenant: dict | None = None) -> list[str]:
    """Which backend kinds are usable for this tenant, in preference order."""
    usable: dict[str, bool] = {
        "hana": _source_enabled(
            tenant, "HANA_ENABLED",
            requires=[("HANA_HOST", HANA_HOST), ("HANA_USER", HANA_USER),
                      ("HANA_PASSWORD", HANA_PASSWORD), ("HANA_SCHEMA", HANA_SCHEMA)],
        ),
        "service": _source_enabled(
            tenant, "SERVICE_LAYER_ENABLED", "SAP_B1_ENABLED",
            requires=[("SAP_B1_HOST", SAP_B1_HOST), ("SAP_B1_USER", SAP_B1_USER),
                      ("SAP_B1_PASSWORD", SAP_B1_PASSWORD)],
        ),
        "mssql": _source_enabled(
            tenant, "MSSQL_ENABLED",
            requires=[("MSSQL_HOST", MSSQL_HOST), ("MSSQL_USER", MSSQL_USER),
                      ("MSSQL_PASSWORD", MSSQL_PASSWORD), ("MSSQL_DATABASE", MSSQL_DATABASE)],
        ),
        "simulator": SIMULATOR_ALLOWED,
    }
    order = [kind.strip().lower() for kind in DATA_SOURCE_ORDER if kind.strip()]
    # Unknown kinds in the order list are ignored; anything enabled but not listed
    # is appended after the explicit order (simulator stays where it is).
    ordered = [kind for kind in order if usable.get(kind, False)]
    ordered += [kind for kind in _CANDON_ORDER if kind not in ordered and usable.get(kind, False)]
    return ordered


DEFAULT_TENANT_NAME = _normalise_tenant_key(HANA_SCHEMA or SAP_B1_COMPANY_DB or "DEFAULT")
DEFAULT_COMPANY_DB = (HANA_SCHEMA or SAP_B1_COMPANY_DB or "DEFAULT").strip()

# ── Row limits ───────────────────────────────────────────────────────────────
DEFAULT_ROW_LIMIT = _int("CIRA_DEFAULT_ROW_LIMIT", 500)
MAX_ROW_LIMIT = _int("CIRA_MAX_ROW_LIMIT", 10000)
# Rows persisted with a chat message (keeps cira.db from exploding)
MAX_PERSISTED_ROWS = _int("CIRA_MAX_PERSISTED_ROWS", 2000)
# Rows sent to the browser in a single SSE payload
MAX_STREAMED_ROWS = _int("CIRA_MAX_STREAMED_ROWS", 2000)
# How many rows the LLM itself gets to see (it only needs a preview)
LLM_PREVIEW_ROWS = _int("CIRA_LLM_PREVIEW_ROWS", 8)
# How many tables from one answer are streamed/persisted
MAX_RESULT_TABLES = _int("CIRA_MAX_RESULT_TABLES", 4)

# ── LLM (OpenRouter by default, any OpenAI-compatible endpoint works) ────────
OPENROUTER_API_KEY = _str("OPENROUTER_API_KEY") or _str("OPENAI_API_KEY")
OPENROUTER_BASE_URL = _str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = _str("CIRA_MODEL", "openrouter/free")
TITLE_MODEL_NAME = _str("CIRA_TITLE_MODEL", MODEL_NAME)
LLM_TEMPERATURE = _float("CIRA_LLM_TEMPERATURE", 0.1)
LLM_TIMEOUT_S = _float("CIRA_LLM_TIMEOUT_S", 90.0)
LLM_MAX_RETRIES = _int("CIRA_LLM_MAX_RETRIES", 2)
AGENT_RECURSION_LIMIT = _int("CIRA_AGENT_RECURSION_LIMIT", 24)
# Set to false to force the deterministic (no-LLM) planner even when a key exists
USE_LLM = _bool("CIRA_USE_LLM", True) and bool(OPENROUTER_API_KEY)
# Speech-to-text provider key (POST /transcribe). No default, no key -> endpoint disabled.
GROQ_API_KEY = _str("GROQ_API_KEY")

# ── Auth ────────────────────────────────────────────────────────────────────
SECRET_KEY = _str("CIRA_SECRET_KEY", "")
TOKEN_TTL_SECONDS = _int("CIRA_TOKEN_TTL_SECONDS", 12 * 3600)
# Bootstrap credentials. Deliberately empty: with no CIRA_ADMIN_PASSWORD there is
# no admin account at all (see auth.authenticate). The previous build shipped a
# working `admin`/<demo password> pair in git, in the README, *and* defaulted
# "any employee id + any password" to True — i.e. auth was decoration.
ADMIN_ID = _str("CIRA_ADMIN_ID")
ADMIN_PASSWORD = _str("CIRA_ADMIN_PASSWORD")
# Demo mode: any non-empty employee id + any password is accepted.
ALLOW_ANY_EMPLOYEE = _bool("CIRA_ALLOW_ANY_EMPLOYEE", False)
# HMAC key material for /sap/write request signing (see main.py); demo mode off.
WEBHOOK_SECRET = _str("CIRA_WEBHOOK_SECRET")

# ── SAP writes (data-entry forms) ────────────────────────────────────────────
# Writes are the highest-risk thing CIRA can do to a production ERP, so they are
# opt-in, admin-only, and limited to an explicit entity allowlist.
SAP_WRITE_ENABLED = _bool("CIRA_SAP_WRITE_ENABLED", False)
SAP_WRITE_ROLES = {r.strip().lower() for r in _list("CIRA_SAP_WRITE_ROLES", "admin") if r.strip()}
SAP_WRITE_ENTITIES = {
    e.strip() for e in _list(
        "CIRA_SAP_WRITE_ENTITIES",
        "BusinessPartners,Items,Orders,Invoices,Quotations,PurchaseOrders,JournalEntries",
    ) if e.strip()
}
SAP_WRITE_MAX_FIELDS = _int("CIRA_SAP_WRITE_MAX_FIELDS", 120)

# ── HTTP / CORS ──────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = _list("CIRA_ALLOWED_ORIGINS")
ALLOW_ORIGIN_REGEX = _str("CIRA_ALLOWED_ORIGIN_REGEX", "")
# Refuse to serve the app with a wildcard-CORS + credentials combination.
STRICT = _bool("CIRA_STRICT", True)
MAX_UPLOAD_BYTES = _int("CIRA_MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
MAX_AUDIO_BYTES = _int("CIRA_MAX_AUDIO_BYTES", 25 * 1024 * 1024)

# ── Storage ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(_str("CIRA_DATA_DIR", str(BASE_DIR / "data")))
DATABASE_PATH = Path(_str("CIRA_DB_PATH", str(DATA_DIR / "cira.db")))
SIMULATOR_DB_PATH = Path(_str("CIRA_SIM_DB_PATH", str(DATA_DIR / "sap_b1_sim.db")))
KNOWLEDGE_DIR = Path(_str("CIRA_KNOWLEDGE_DIR", str(BASE_DIR / "knowledge")))
UPLOAD_DIR = Path(_str("CIRA_UPLOAD_DIR", str(DATA_DIR / "uploads")))
UPLOAD_TTL_HOURS = _int("CIRA_UPLOAD_TTL_HOURS", 24)
# Audit trail: who asked what of the ERP, and what was written. JSONL, rotated.
AUDIT_LOG_PATH = Path(_str("CIRA_AUDIT_LOG", str(DATA_DIR / "audit.jsonl")))
AUDIT_MAX_BYTES = _int("CIRA_AUDIT_MAX_BYTES", 50 * 1024 * 1024)
AUDIT_ENABLED = _bool("CIRA_AUDIT_ENABLED", True)
# The offline sandbox is a development affordance; disable it in production so a
# dead HANA connection can never be mistaken for a working one.
SIMULATOR_ALLOWED = _bool("CIRA_ALLOW_SIMULATOR", True)

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Misc ────────────────────────────────────────────────────────────────────
LOG_LEVEL = _str("CIRA_LOG_LEVEL", "INFO").upper()
SCHEMA_CACHE_TTL_S = _int("CIRA_SCHEMA_CACHE_TTL_S", 900)
HEALTH_CACHE_TTL_S = _int("CIRA_HEALTH_CACHE_TTL_S", 10)
BACKEND_RETRY_S = _int("CIRA_BACKEND_RETRY_S", 60)


class ConfigError(RuntimeError):
    """Raised for a configuration that cannot be honoured (fail at startup)."""


def validate() -> tuple[list[str], list[str]]:
    """Return (fatal_problems, warnings) for the effective configuration.

    Called by main.py at startup and by `migrate_db.py --check`, so an operator
    learns *before* the first user question whether CIRA is on live data.
    """
    fatal: list[str] = []
    warn: list[str] = []

    mode = DATA_SOURCE
    if mode not in {"auto", "hana", "service", "mssql", "simulator", "sim", "mock"}:
        fatal.append(f"CIRA_DATA_SOURCE={mode!r} is not a known source")

    if mode in {"hana", "service", "mssql"}:
        kind = {"sim": "simulator", "mock": "simulator"}.get(mode, mode)
        if kind not in enabled_sources():
            fatal.append(
                f"CIRA_DATA_SOURCE={mode} but that source is not enabled — set its "
                f"host/credentials in Backend/.env (see .env.example)"
            )
    elif mode == "auto":
        if not enabled_sources():
            if SIMULATOR_ALLOWED:
                warn.append(
                    "No SAP source is configured — CIRA will serve SANDBOX data and "
                    "label it SIMULATED. Set HANA_HOST/HANA_USER/HANA_PASSWORD for live data."
                )
            else:
                fatal.append(
                    "No SAP source is configured and the simulator is disabled "
                    "(CIRA_ALLOW_SIMULATOR=false). Set HANA_* in Backend/.env."
                )

    if not ADMIN_ID or not ADMIN_PASSWORD:
        warn.append(
            "No CIRA_ADMIN_ID/CIRA_ADMIN_PASSWORD configured — the admin sign-in is "
            "disabled. Until a real IdP or an OUSR lookup is wired up, an admin cannot "
            "sign in (and SAP writes stay unavailable)."
        )
    if ALLOW_ANY_EMPLOYEE:
        warn.append(
            "CIRA_ALLOW_ANY_EMPLOYEE=true — ANY employee ID with ANY password can sign in. "
            "Never leave this on for a deployment that can reach production data."
        )
    if not ALLOWED_ORIGINS and not ALLOW_ORIGIN_REGEX:
        if STRICT:
            fatal.append(
                "No allowed origins configured. Set CIRA_ALLOWED_ORIGINS (comma separated) "
                "or CIRA_ALLOWED_ORIGIN_REGEX; a wildcard origin with credentials is not "
                "allowed. Set CIRA_STRICT=false only for local development."
            )
        else:
            warn.append("CIRA_ALLOWED_ORIGINS is empty with CIRA_STRICT=false — any origin may call the API.")
    if not SECRET_KEY:
        warn.append(
            "CIRA_SECRET_KEY not set — an HMAC key was generated into Backend/data/. "
            "Set it explicitly so sessions survive redeploys / multiple hosts."
        )
    if SAP_WRITE_ENABLED:
        if not SAP_WRITE_ROLES:
            fatal.append("CIRA_SAP_WRITE_ENABLED=true but CIRA_SAP_WRITE_ROLES is empty — refusing to expose unauthenticated writes.")
        warn.append(
            f"SAP write path ENABLED (roles={sorted(SAP_WRITE_ROLES)}, "
            f"entities={len(SAP_WRITE_ENTITIES)}). Every write is audited to {AUDIT_LOG_PATH}."
        )
    return fatal, warn


def summary() -> dict:
    """Non-secret snapshot of the effective configuration.

    Safe for an authenticated diagnostics endpoint: hosts, ports, usernames and
    schema names are *not* included (the previous build leaked all of them on an
    unauthenticated /sap/health).
    """
    return {
        "data_source": DATA_SOURCE,
        "sources_enabled": enabled_sources(),
        "hana": {
            "configured": bool(HANA_HOST and HANA_USER and HANA_PASSWORD),
            "schema_configured": bool(HANA_SCHEMA),
            "encrypt": HANA_ENCRYPT,
        },
        "service_layer": {
            "configured": bool(SAP_B1_HOST and SAP_B1_USER and SAP_B1_PASSWORD),
        },
        "mssql": {"configured": bool(MSSQL_HOST and MSSQL_USER and MSSQL_PASSWORD)},
        "llm": {
            "enabled": USE_LLM,
            "model": MODEL_NAME if USE_LLM else "deterministic-planner",
        },
        "limits": {
            "default_rows": DEFAULT_ROW_LIMIT,
            "max_rows": MAX_ROW_LIMIT,
        },
        "policies": {
            "sap_write_enabled": SAP_WRITE_ENABLED,
            "allow_any_employee": ALLOW_ANY_EMPLOYEE,
            "simulator_allowed": SIMULATOR_ALLOWED,
            "audit_enabled": AUDIT_ENABLED,
        },
        "tenants": sorted(TENANTS),
    }
