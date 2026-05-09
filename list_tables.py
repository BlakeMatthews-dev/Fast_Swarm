import asyncio
import os
import sys

sys.path.append(os.getcwd())
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from Fast_Swarm.Database import DATABASE_URL


async def list_tables():
    print("Connecting to DB to list tables...")
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
            )
        )
        rows = result.fetchall()
        print(f"Found {len(rows)} tables:")
        for row in rows:
            print(f"  - {row[0]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(list_tables())
