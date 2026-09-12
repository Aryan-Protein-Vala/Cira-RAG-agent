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

# Explicit, test-only credentials. These used to live as defaults inside
# config.py (a real admin password) and inside test_api.py (the same string
# hard-coded) - so the "test" password was also the production default and it
# shipped in the repository. Tests now opt into demo mode deliberately and
# production has no default at all (see config.ADMIN_PASSWORD /
# config.ALLOW_ANY_EMPLOYEE).
os.environ.setdefault("CIRA_ALLOW_ANY_EMPLOYEE", "1")
os.environ.setdefault("CIRA_ADMIN_PASSWORD", "test-only-admin-password")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session", autouse=True)
def _seeded_tenant():
    """One write-enabled sandbox tenant, created directly in the test database.

    The migration endpoints resolve the tenant from the database (as they must in
    production), so the tests need a real row rather than a monkeypatched dict.
    """
    import asyncio

    import config as cfg
    import database as db_mod

    async def _create():
        await db_mod.init_db()
        async with db_mod.AsyncSessionLocal() as session:
            from sqlalchemy import select
            existing = (await session.execute(
                select(db_mod.Tenant).where(db_mod.Tenant.company_db == "CIRA_TEST")
            )).scalars().first()
            if existing:
                return
            partner = db_mod.Partner(
                id="test-partner", name="Test Partner", slug="test-partner",
                email="partner@example.test", password_hash="x-not-used", is_active=1,
            )
            session.add(partner)
            session.add(db_mod.Tenant(
                id="test-tenant", partner_id="test-partner", company_name="Test Co",
                sap_host="127.0.0.1", sap_hana_port=30013, sap_sl_port=50000,
                sap_db_user="TEST", sap_db_password="TEST", sap_sl_user="TEST",
                sap_sl_password="TEST", company_db="CIRA_TEST",
                is_active=1, write_enabled=1,
            ))
            await session.commit()

    asyncio.run(_create())
    yield
