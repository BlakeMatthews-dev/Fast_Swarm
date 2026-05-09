import asyncio
import os
import sys

sys.path.append(os.getcwd())
from sqlalchemy import text


async def count_trades():
    print("Initializing DB...")
    # Direct connection test to avoid potential Database.py overhead issues for this check
    from Fast_Swarm.Database import DATABASE_URL

    # Create a new engine just for this script if needed, or re-use imports
    # DATABASE_URL should be correct now
    print(f"Connecting to: {DATABASE_URL}")

    # We need async engine for async session, or sync engine for sync session.
    # Database.py uses async engine.
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.connect() as conn:
        print("Connected! Running query...")
        # Use backtest_trades_unified (canonical table, not legacy agent_trades)
        result = await conn.execute(text("SELECT COUNT(*) FROM backtest_trades_unified"))
        count = result.scalar()
        print(f"Total Backtest Trades in DB: {count}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(count_trades())
