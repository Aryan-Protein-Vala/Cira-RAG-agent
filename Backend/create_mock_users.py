import asyncio
import uuid
from passlib.context import CryptContext
from database import AsyncSessionLocal, SuperAdmin, Partner, init_db
from sqlalchemy import select

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Create SuperAdmin
        admin_email = "aryansharma24112003@gmail.com"
        result = await session.execute(select(SuperAdmin).where(SuperAdmin.email == admin_email))
        if not result.scalars().first():
            admin = SuperAdmin(
                id=str(uuid.uuid4()),
                email=admin_email,
                password_hash=pwd_context.hash("aryan")
            )
            session.add(admin)
            print(f"Created SuperAdmin: {admin_email}")

        # Create Partner Admin
        partner_email = "partner@cira.app"
        result = await session.execute(select(Partner).where(Partner.email == partner_email))
        if not result.scalars().first():
            partner = Partner(
                id=str(uuid.uuid4()),
                name="Mock Partner",
                email=partner_email,
                password_hash=pwd_context.hash("partner123"),
                slug="mockpartner"
            )
            session.add(partner)
            print(f"Created Partner: {partner_email} (password: partner123)")
            
        await session.commit()

if __name__ == "__main__":
    asyncio.run(main())
