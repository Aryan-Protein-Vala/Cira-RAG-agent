"""Shared pytest fixtures.

The whole suite runs against the offline SAP B1 sandbox so it needs no ERP,
no network and no API keys.
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
os.environ.setdefault("CIRA_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("CIRA_HANA_SCHEMA", "CIRA_TEST")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
