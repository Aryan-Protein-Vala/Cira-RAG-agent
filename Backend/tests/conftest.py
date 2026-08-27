"""Shared pytest fixtures.

The whole suite runs against the offline SAP B1 sandbox so it needs no ERP,
no network and no API keys.

Note these are *test* settings that deliberately turn demo mode on;
`tests/test_config_policy.py` asserts the shipped defaults are the safe ones.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_TMP = tempfile.mkdtemp(prefix="cira-tests-")
os.environ.setdefault("CIRA_DATA_SOURCE", "simulator")
os.environ.setdefault("CIRA_DATA_DIR", _TMP)
os.environ.setdefault("CIRA_DB_PATH", str(Path(_TMP) / "cira_test.db"))
os.environ.setdefault("CIRA_SIM_DB_PATH", str(Path(_TMP) / "sap_sim.db"))
os.environ.setdefault("CIRA_AUDIT_LOG", str(Path(_TMP) / "audit.jsonl"))
os.environ.setdefault("CIRA_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENROUTER_API_KEY", "")
# HANA_SCHEMA (not CIRA_HANA_SCHEMA — that variable has never existed) so the
# sandbox is labelled with a test schema instead of the developer's real one.
os.environ.setdefault("HANA_SCHEMA", "CIRA_TEST")
# TestClient does not exercise CORS pre-flight; relax the strict-origin guard.
os.environ.setdefault("CIRA_STRICT", "false")
# Two identities the API tests need: the bootstrap admin and "some employee".
os.environ.setdefault("CIRA_ADMIN_ID", "admin")
os.environ.setdefault("CIRA_ADMIN_PASSWORD", "test-admin-password-123")
os.environ.setdefault("CIRA_ALLOW_ANY_EMPLOYEE", "true")
os.environ.setdefault("CIRA_ALLOW_SIMULATOR", "true")

import pytest  # noqa: E402 -- env must be set before config imports


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def audit_lines():
    """Read whatever the audit trail recorded during a test."""
    import config

    def _read():
        import json

        path = Path(config.AUDIT_LOG_PATH)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    return _read
