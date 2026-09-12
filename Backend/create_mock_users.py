import asyncio
import uuid
from sqlalchemy import select
from database import AsyncSessionLocal, SuperAdmin, Partner
from admin_routes import get_password_hash

async def create_users():
    async with AsyncSessionLocal() as session:
        # Create SuperAdmin
        sa_email = "aryansharma24112003@gmail.com"
        result = await session.execute(select(SuperAdmin).where(SuperAdmin.email == sa_email))
        if not result.scalars().first():
            sa = SuperAdmin(
                id=str(uuid.uuid4()),
                email=sa_email,
                password_hash=get_password_hash("aryan")
            )
            session.add(sa)
            print(f"SuperAdmin {sa_email} created.")

        # Create Partner Admin
        pa_email = "admin@partner.com"
        result = await session.execute(select(Partner).where(Partner.email == pa_email))
        if not result.scalars().first():
            pa = Partner(
                id=str(uuid.uuid4()),
                name="Test Partner",
                slug="test-partner",
                email=pa_email,
                password_hash=get_password_hash("aryan"),
                brand_name="B1 Copilot Partner",
                is_active=1
            )
            session.add(pa)
            print(f"Partner Admin {pa_email} created.")

        await session.commit()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(create_users())
