import asyncio
import os
import sys

sys.path.append(os.getcwd())
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Use the DATABASE_URL from Database.py
from Fast_Swarm.Database import DATABASE_URL


async def check_schema():
    print("Connecting to DB to check 'patterns' table schema...")
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.connect() as conn:
        print("Connected.")
        # Query information_schema
        result = await conn.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'patterns';")
        )
        rows = result.fetchall()
        print(f"Found {len(rows)} columns:")
        for row in rows:
            print(f"  - {row[0]} ({row[1]})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_schema())
