"""Create or rotate one superadmin account.

There is no default e-mail and no default password. The previous version
shipped `SUPERADMIN_EMAIL=aryan@cira.app` and
`SUPERADMIN_PASSWORD=cira_admin_2026` as fallbacks, i.e. the repository
contained working production credentials.

Usage:
    CIRA_SUPERADMIN_EMAIL=you@example.com CIRA_SUPERADMIN_PASSWORD='...' \
    python create_superadmin.py
"""

import asyncio
import os
import sys
import uuid

from sqlalchemy import select

from database import AsyncSessionLocal, SuperAdmin, init_db
from passwords import hash_password


async def main() -> None:
    email = os.getenv("CIRA_SUPERADMIN_EMAIL", "").strip().lower()
    password = os.getenv("CIRA_SUPERADMIN_PASSWORD", "")
    if not email or not password:
        sys.exit(
            "Set CIRA_SUPERADMIN_EMAIL and CIRA_SUPERADMIN_PASSWORD. "
            "There are no default credentials."
        )
    if len(password) < 12:
        sys.exit("Choose a superadmin password of at least 12 characters.")

    await init_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SuperAdmin).where(SuperAdmin.email == email))
        existing = result.scalars().first()
        if existing:
            existing.password_hash = hash_password(password)
            print(f"SuperAdmin '{email}' password rotated.")
        else:
            session.add(SuperAdmin(id=str(uuid.uuid4()), email=email,
                                   password_hash=hash_password(password)))
            print(f"SuperAdmin '{email}' provisioned.")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
