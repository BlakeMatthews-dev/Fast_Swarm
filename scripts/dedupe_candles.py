"""
One-time script to remove duplicate rows from enhanced_candles table.
Run this once, then the unique index can be created.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from Fast_Swarm.Database import async_session_maker
from sqlalchemy import text


async def dedupe_enhanced_candles():
    print("=" * 60)
    print("DEDUPLICATING enhanced_candles table")
    print("=" * 60)

    async with async_session_maker() as session:
        # Disable TimescaleDB decompression limit for this session
        await session.execute(text("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0"))

        # Count total rows
        result = await session.execute(text("SELECT COUNT(*) FROM enhanced_candles"))
        total = result.scalar()
        print(f"Total rows before: {total:,}")

        # Count duplicates
        result = await session.execute(
            text("""
            SELECT COUNT(*) FROM (
                SELECT symbol, timeframe, time, COUNT(*) as cnt
                FROM enhanced_candles
                GROUP BY symbol, timeframe, time
                HAVING COUNT(*) > 1
            ) dupes
        """)
        )
        dupe_groups = result.scalar()
        print(f"Duplicate groups found: {dupe_groups:,}")

        if dupe_groups == 0:
            print("No duplicates found!")
            return

        print("\nRemoving duplicates (keeping first occurrence)...")
        print("This may take several minutes on 5M+ row table...")

        # Delete duplicates - keep the row with the smallest ctid
        result = await session.execute(
            text("""
            DELETE FROM enhanced_candles a
            USING enhanced_candles b
            WHERE a.ctid > b.ctid
              AND a.symbol = b.symbol
              AND a.timeframe = b.timeframe
              AND a.time = b.time
        """)
        )
        await session.commit()

        deleted = result.rowcount
        print(f"Deleted {deleted:,} duplicate rows")

        # Count after
        result = await session.execute(text("SELECT COUNT(*) FROM enhanced_candles"))
        after = result.scalar()
        print(f"Total rows after: {after:,}")

        # Now create the unique index
        print("\nCreating unique index...")
        await session.execute(
            text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_enhanced_candles_unique
            ON enhanced_candles(symbol, timeframe, time)
        """)
        )
        await session.commit()
        print("Unique index created successfully!")

    print("=" * 60)
    print("DONE - Backfill ON CONFLICT should now work")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(dedupe_enhanced_candles())
