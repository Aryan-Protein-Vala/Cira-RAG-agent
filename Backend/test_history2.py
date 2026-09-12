import asyncio
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, ChatSession
import json

async def main():
    async with AsyncSession(engine) as db:
        owned = await db.execute(
            select(ChatSession).where(
                ChatSession.session_id == 's1',
                ChatSession.employee_id == 'EMP-20481',
            )
        )
        print("Owned result:", owned.scalars().first())

asyncio.run(main())
