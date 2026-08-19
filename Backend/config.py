"""
Central configuration for the CIRA backend.

Every tunable lives here and is driven by environment variables (loaded from
Backend/.env when present).  Nothing else in the codebase should call
os.getenv() directly -- that was one of the reasons the old code drifted
(different defaults for the same setting in agent.py and sap_b1_client.py).
"""

from __future__ import annotations

import os
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


# ─────────────────────────────────────────────────────────────────────────────
# Data source selection
#   auto      -> HANA, then Service Layer, then simulator (default)
#   hana      -> HANA only (fail loudly if unreachable)
#   service   -> SAP B1 Service Layer (OData) only
#   simulator -> local SQLite SAP-B1-shaped sandbox (offline development)
# ─────────────────────────────────────────────────────────────────────────────
DATA_SOURCE = _str("CIRA_DATA_SOURCE", "auto").lower()

# ── SAP HANA (direct SQL — this is the "deep" path) ──────────────────────────
HANA_HOST = _str("HANA_HOST", _str("SAP_B1_HOST", "20.204.5.237"))
HANA_PORT = _int("HANA_PORT", 30013)
HANA_USER = _str("HANA_USER", "SYSTEM")
HANA_PASSWORD = _str("HANA_PASSWORD", "")
HANA_SCHEMA = _str("HANA_SCHEMA", _str("SAP_B1_COMPANY_DB", "CIRA_DEMO_NEW"))
HANA_ENCRYPT = _bool("HANA_ENCRYPT", True)
HANA_VALIDATE_CERT = _bool("HANA_SSL_VALIDATE_CERT", False)
HANA_CONNECT_TIMEOUT_MS = _int("HANA_CONNECT_TIMEOUT_MS", 8000)
HANA_QUERY_TIMEOUT_S = _int("HANA_QUERY_TIMEOUT_S", 120)
HANA_POOL_SIZE = _int("HANA_POOL_SIZE", 4)
# Extra schemas the agent is allowed to read (comma separated). The company
# schema is always allowed; SYS is used read-only for catalog introspection.
HANA_EXTRA_SCHEMAS = [
    s.strip().upper() for s in _str("HANA_EXTRA_SCHEMAS", "").split(",") if s.strip()
]

# ── SAP Business One Service Layer (OData) ───────────────────────────────────
SAP_B1_HOST = _str("SAP_B1_HOST", HANA_HOST)
SAP_B1_PORT = _int("SAP_B1_PORT", 50000)
SAP_B1_COMPANY_DB = _str("SAP_B1_COMPANY_DB", HANA_SCHEMA)
SAP_B1_USER = _str("SAP_B1_USER", "manager")
SAP_B1_PASSWORD = _str("SAP_B1_PASSWORD", "")
SAP_B1_VERIFY_SSL = _bool("SAP_B1_VERIFY_SSL", False)
SAP_B1_TIMEOUT_S = _float("SAP_B1_TIMEOUT_S", 20.0)
SERVICE_LAYER_BASE = _str(
    "SAP_B1_SERVICE_LAYER_URL", f"https://{SAP_B1_HOST}:{SAP_B1_PORT}/b1s/v1"
).rstrip("/")

# ── Row limits ───────────────────────────────────────────────────────────────
DEFAULT_ROW_LIMIT = _int("CIRA_DEFAULT_ROW_LIMIT", 500)
MAX_ROW_LIMIT = _int("CIRA_MAX_ROW_LIMIT", 10000)
# Rows persisted with a chat message (keeps cira.db from exploding)
MAX_PERSISTED_ROWS = _int("CIRA_MAX_PERSISTED_ROWS", 2000)
# Rows sent to the browser in a single SSE payload
MAX_STREAMED_ROWS = _int("CIRA_MAX_STREAMED_ROWS", 5000)
# How many rows the LLM itself gets to see (it only needs a preview)
LLM_PREVIEW_ROWS = _int("CIRA_LLM_PREVIEW_ROWS", 8)

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

# ── Auth ─────────────────────────────────────────────────────────────────────
SECRET_KEY = _str("CIRA_SECRET_KEY", "")
TOKEN_TTL_SECONDS = _int("CIRA_TOKEN_TTL_SECONDS", 12 * 3600)
# Demo/bootstrap credentials.  In production point CIRA_USERS at a JSON map or
# wire validate_credentials() to your IdP / SAP OUSR table.
ADMIN_ID = _str("CIRA_ADMIN_ID", "admin")
ADMIN_PASSWORD = _str("CIRA_ADMIN_PASSWORD", "asdfghjkl;")
# When true any non-empty employee id + password is accepted (demo mode).
ALLOW_ANY_EMPLOYEE = _bool("CIRA_ALLOW_ANY_EMPLOYEE", True)

# ── HTTP / CORS ──────────────────────────────────────────────────────────────
_origins = _str("CIRA_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]
ALLOW_ORIGIN_REGEX = _str("CIRA_ALLOWED_ORIGIN_REGEX", "" if ALLOWED_ORIGINS else ".*")

# ── Storage ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(_str("CIRA_DATA_DIR", str(BASE_DIR / "data")))
DATABASE_PATH = Path(_str("CIRA_DB_PATH", str(BASE_DIR / "cira.db")))
SIMULATOR_DB_PATH = Path(_str("CIRA_SIM_DB_PATH", str(DATA_DIR / "sap_b1_sim.db")))
KNOWLEDGE_DIR = Path(_str("CIRA_KNOWLEDGE_DIR", str(BASE_DIR / "knowledge")))
UPLOAD_DIR = Path(_str("CIRA_UPLOAD_DIR", str(DATA_DIR / "uploads")))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Misc ─────────────────────────────────────────────────────────────────────
LOG_LEVEL = _str("CIRA_LOG_LEVEL", "INFO").upper()
SCHEMA_CACHE_TTL_S = _int("CIRA_SCHEMA_CACHE_TTL_S", 900)


def summary() -> dict:
    """Non-secret snapshot of the effective configuration (used by /health)."""
    return {
        "data_source": DATA_SOURCE,
        "hana": {
            "host": HANA_HOST,
            "port": HANA_PORT,
            "schema": HANA_SCHEMA,
            "user": HANA_USER,
            "encrypt": HANA_ENCRYPT,
            "credentials_configured": bool(HANA_PASSWORD),
        },
        "service_layer": {
            "base_url": SERVICE_LAYER_BASE,
            "company_db": SAP_B1_COMPANY_DB,
            "user": SAP_B1_USER,
            "credentials_configured": bool(SAP_B1_PASSWORD),
        },
        "llm": {
            "enabled": USE_LLM,
            "model": MODEL_NAME if USE_LLM else "deterministic-planner",
            "base_url": OPENROUTER_BASE_URL,
        },
        "limits": {
            "default_rows": DEFAULT_ROW_LIMIT,
            "max_rows": MAX_ROW_LIMIT,
        },
    }
