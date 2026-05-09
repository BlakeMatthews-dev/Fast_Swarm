"""
Sentiment Data Collector — fetches Fear & Greed Index and funding rates.

Runs on startup (backfill) and every 4 hours (refresh).
Fear & Greed API: https://api.alternative.me/fng/ (free, no auth)
"""

import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..Models.sentiment_models import FearGreedIndex

logger = logging.getLogger(__name__)

FEAR_GREED_API = "https://api.alternative.me/fng/"


async def fetch_fear_greed(session: AsyncSession, days: int = 30) -> int:
    """
    Fetch Fear & Greed Index from alternative.me API.

    Args:
        session: Database session
        days: Number of days to fetch (max ~2000)

    Returns:
        Number of new records inserted
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{FEAR_GREED_API}?limit={days}&format=json")
            response.raise_for_status()
            data = response.json()

        records = data.get("data", [])
        if not records:
            logger.warning("[Sentiment] No Fear & Greed data returned")
            return 0

        inserted = 0
        for record in records:
            ts = int(record.get("timestamp", 0))
            value = int(record.get("value", 50))
            classification = record.get("value_classification", "Neutral")

            # Check if already exists
            from sqlmodel import select

            existing = await session.execute(
                select(FearGreedIndex).where(FearGreedIndex.timestamp == ts)
            )
            if existing.scalar_one_or_none():
                continue

            entry = FearGreedIndex(
                timestamp=ts,
                value=value,
                classification=classification,
            )
            session.add(entry)
            inserted += 1

        if inserted > 0:
            await session.commit()
            logger.info("[Sentiment] Inserted %d Fear & Greed records", inserted)

        return inserted

    except Exception as e:
        logger.error("[Sentiment] Failed to fetch Fear & Greed: %s", e)
        await session.rollback()
        return 0


async def sentiment_collector_loop():
    """Background loop: fetch sentiment data every 4 hours."""
    import asyncio

    from Fast_Swarm.Database import async_session_maker

    # Initial backfill on startup
    await asyncio.sleep(30)  # Wait for DB
    try:
        async with async_session_maker() as session:
            count = await fetch_fear_greed(session, days=365)
            print(f"[Sentiment] Initial backfill: {count} Fear & Greed records")
    except Exception as e:
        print(f"[Sentiment] Initial backfill failed: {e}")

    # Refresh every 4 hours
    while True:
        await asyncio.sleep(4 * 3600)
        try:
            async with async_session_maker() as session:
                count = await fetch_fear_greed(session, days=7)
                if count > 0:
                    print(f"[Sentiment] Refreshed: {count} new Fear & Greed records")
        except Exception as e:
            print(f"[Sentiment] Refresh failed: {e}")
