"""Create a demo partner + tenant.

Every credential comes from the environment - this file used to hard-code
"SandboxPassword123!" for both the HANA user and the Service Layer user, point
the tenant at 10.0.0.1, and create it with write_enabled=1. A tenant that can
write to an ERP must never be created by a script that needs no arguments.

Usage:
    CIRA_DEMO_PARTNER_EMAIL=... CIRA_DEMO_PARTNER_PASSWORD=... \
    CIRA_DEMO_SAP_HOST=... CIRA_DEMO_SAP_DB_USER=... CIRA_DEMO_SAP_DB_PASSWORD=... \
    CIRA_DEMO_SAP_SL_USER=... CIRA_DEMO_SAP_SL_PASSWORD=... CIRA_DEMO_COMPANY_DB=... \
    python seed_tenant.py
"""

import asyncio
import os
import sys
import uuid

from database import AsyncSessionLocal, Partner, Tenant
from passwords import hash_password


def _required(name: str, hint: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set. {hint}")
    return value


async def seed():
    partner_email = _required("CIRA_DEMO_PARTNER_EMAIL", "Partner admin login e-mail.")
    partner_password = _required("CIRA_DEMO_PARTNER_PASSWORD", "Partner admin password.")
    sap_host = _required("CIRA_DEMO_SAP_HOST", "SAP B1 server hostname or IP.")
    sap_db_user = _required("CIRA_DEMO_SAP_DB_USER", "SAP HANA database user.")
    sap_db_password = _required("CIRA_DEMO_SAP_DB_PASSWORD", "SAP HANA database password.")
    sap_sl_user = _required("CIRA_DEMO_SAP_SL_USER", "Service Layer user.")
    sap_sl_password = _required("CIRA_DEMO_SAP_SL_PASSWORD", "Service Layer password.")
    company_db = _required("CIRA_DEMO_COMPANY_DB", "SAP B1 company database name.")

    # Writes stay OFF unless explicitly requested. Everything the agent can do
    # read-only works; drafts and document creation need a deliberate opt-in.
    write_enabled = 1 if os.getenv("CIRA_DEMO_WRITE_ENABLED", "").lower() in ("1", "true", "yes") else 0

    async with AsyncSessionLocal() as db:
        partner = Partner(
            id=str(uuid.uuid4()),
            name=os.getenv("CIRA_DEMO_PARTNER_NAME", "Demo Partner"),
            slug=os.getenv("CIRA_DEMO_PARTNER_SLUG", f"demo-partner-{uuid.uuid4().hex[:6]}"),
            email=partner_email,
            password_hash=hash_password(partner_password),
            is_active=1,
        )
        db.add(partner)
        await db.commit()
        await db.refresh(partner)
        
        # Create a tenant
        t_id = str(uuid.uuid4())
        tenant = Tenant(
            id=t_id,
            partner_id=partner.id,
            company_name=os.getenv("CIRA_DEMO_COMPANY_NAME", "Demo Tenant"),
            sap_host=sap_host,
            sap_hana_port=int(os.getenv("CIRA_DEMO_SAP_HANA_PORT", "30013")),
            sap_sl_port=int(os.getenv("CIRA_DEMO_SAP_SL_PORT", "50000")),
            sap_db_user=sap_db_user,
            sap_db_password=sap_db_password,
            sap_sl_user=sap_sl_user,
            sap_sl_password=sap_sl_password,
            company_db=company_db,
            is_active=1,
            write_enabled=write_enabled,
        )
        db.add(tenant)
        await db.commit()
        print(f"Tenant created (write_enabled={write_enabled}).")

if __name__ == "__main__":
    asyncio.run(seed())
