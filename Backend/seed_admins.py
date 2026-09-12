import asyncio
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, SuperAdmin, Partner
from passlib.context import CryptContext
import uuid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def seed():
    async with AsyncSession(engine) as db:
        # Seed SuperAdmin
        email = "aryansharma24112003@gmail.com"
        result = await db.execute(select(SuperAdmin).where(SuperAdmin.email == email))
        if not result.scalars().first():
            superadmin = SuperAdmin(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=pwd_context.hash("aryan")
            )
            db.add(superadmin)
            print(f"Created SuperAdmin {email}")

        # Seed Partner Admin
        partner_email = "admin@partner.com"
        result = await db.execute(select(Partner).where(Partner.email == partner_email))
        if not result.scalars().first():
            partner = Partner(
                id=str(uuid.uuid4()),
                name="Mock Partner",
                slug="mock-partner",
                email=partner_email,
                password_hash=pwd_context.hash("aryan"),
                brand_name="Mock Partner Brand",
                plan="enterprise"
            )
            db.add(partner)
            print(f"Created Partner {partner_email}")
        
        await db.commit()

asyncio.run(seed())
