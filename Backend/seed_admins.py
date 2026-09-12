"""Create the first superadmin and a partner admin.

Both accounts are read from the environment. There are deliberately NO
defaults: this file used to contain a personal Gmail address and the password
"aryan" in plain text, which meant the repository itself was the credential.

Usage:
    CIRA_SUPERADMIN_EMAIL=you@example.com \
    CIRA_SUPERADMIN_PASSWORD='...' \
    CIRA_PARTNER_EMAIL=partner@example.com \
    CIRA_PARTNER_PASSWORD='...' \
    python seed_admins.py
"""

import asyncio
import os
import sys
import uuid

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import engine, SuperAdmin, Partner
from passwords import hash_password


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(
            f"{name} is not set. Refusing to create an account with a guessed "
            f"or hard-coded credential. See the docstring in seed_admins.py."
        )
    return value


async def seed() -> None:
    superadmin_email = _required("CIRA_SUPERADMIN_EMAIL")
    superadmin_password = _required("CIRA_SUPERADMIN_PASSWORD")
    partner_email = os.getenv("CIRA_PARTNER_EMAIL", "").strip()
    partner_password = os.getenv("CIRA_PARTNER_PASSWORD", "").strip()

    async with AsyncSession(engine) as db:
        result = await db.execute(select(SuperAdmin).where(SuperAdmin.email == superadmin_email))
        if not result.scalars().first():
            db.add(SuperAdmin(
                id=str(uuid.uuid4()),
                email=superadmin_email,
                password_hash=hash_password(superadmin_password),
            ))
            print(f"Created SuperAdmin {superadmin_email}")

        if partner_email and partner_password:
            result = await db.execute(select(Partner).where(Partner.email == partner_email))
            if not result.scalars().first():
                db.add(Partner(
                    id=str(uuid.uuid4()),
                    name=os.getenv("CIRA_PARTNER_NAME", "Partner"),
                    slug=os.getenv("CIRA_PARTNER_SLUG", "partner"),
                    email=partner_email,
                    password_hash=hash_password(partner_password),
                    brand_name=os.getenv("CIRA_PARTNER_BRAND", "Partner"),
                    plan=os.getenv("CIRA_PARTNER_PLAN", "standard"),
                ))
                print(f"Created Partner {partner_email}")
        elif partner_email or partner_password:
            print("Both CIRA_PARTNER_EMAIL and CIRA_PARTNER_PASSWORD are required; skipping partner.")

        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
