import asyncio
import os
import uuid
from passlib.context import CryptContext
from sqlalchemy import select
from database import AsyncSessionLocal, SuperAdmin, init_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def main():
    await init_db()
    email = os.getenv("SUPERADMIN_EMAIL", "aryan@cira.app").strip().lower()
    password = os.getenv("SUPERADMIN_PASSWORD", "cira_admin_2026")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SuperAdmin).where(SuperAdmin.email == email))
        existing = result.scalars().first()
        if existing:
            existing.password_hash = pwd_context.hash(password)
            await session.commit()
            print(f"SuperAdmin account '{email}' updated successfully.")
        else:
            admin = SuperAdmin(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=pwd_context.hash(password)
            )
            session.add(admin)
            await session.commit()
            print(f"SuperAdmin account '{email}' provisioned successfully.")

if __name__ == "__main__":
    asyncio.run(main())
