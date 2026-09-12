import asyncio
import uuid
from database import AsyncSessionLocal, Partner, Tenant
from passlib.hash import bcrypt

async def seed():
    async with AsyncSessionLocal() as db:
        # Create a partner if none exists
        p_id = str(uuid.uuid4())
        partner = Partner(
            id=p_id,
            name="Test Partner",
            slug="test-partner",
            email="partner@test.com",
            password_hash=bcrypt.hash("partner"),
            is_active=1
        )
        db.add(partner)
        await db.commit()
        await db.refresh(partner)
        
        # Create a tenant
        t_id = str(uuid.uuid4())
        tenant = Tenant(
            id=t_id,
            partner_id=partner.id,
            company_name="Sandbox Tenant",
            sap_host="10.0.0.1",
            sap_hana_port=30013,
            sap_sl_port=50000,
            sap_db_user="SYSTEM",
            sap_db_password="SandboxPassword123!",
            sap_sl_user="manager",
            sap_sl_password="SandboxPassword123!",
            company_db="db_sandbox",
            is_active=1,
            write_enabled=1
        )
        db.add(tenant)
        await db.commit()
        print("Tenant created successfully!")
        db.add(tenant)
        await db.commit()
        print("Tenant created successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
