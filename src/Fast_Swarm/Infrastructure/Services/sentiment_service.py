"""Sentiment data service for market sentiment indicators."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.sentiment_models import BtcDominance, FearGreedIndex, FundingRate


class SentimentService:
    """Service for retrieving market sentiment data."""

    async def get_fear_greed_latest(self, session: AsyncSession, limit: int = 30) -> list[FearGreedIndex]:
        """Get most recent Fear & Greed Index readings."""
        statement = select(FearGreedIndex).order_by(desc(FearGreedIndex.timestamp)).limit(limit)
        result = await session.exec(statement)
        return result.all()

    async def get_fear_greed_current(self, session: AsyncSession) -> FearGreedIndex | None:
        """Get the current Fear & Greed value."""
        statement = select(FearGreedIndex).order_by(desc(FearGreedIndex.timestamp)).limit(1)
        result = await session.exec(statement)
        return result.first()

    async def get_btc_dominance_latest(self, session: AsyncSession, limit: int = 30) -> list[BtcDominance]:
        """Get most recent BTC dominance readings."""
        statement = select(BtcDominance).order_by(desc(BtcDominance.timestamp)).limit(limit)
        result = await session.exec(statement)
        return result.all()

    async def get_btc_dominance_current(self, session: AsyncSession) -> BtcDominance | None:
        """Get the current BTC dominance percentage."""
        statement = select(BtcDominance).order_by(desc(BtcDominance.timestamp)).limit(1)
        result = await session.exec(statement)
        return result.first()

    async def get_funding_rates(
        self, session: AsyncSession, symbol: str | None = None, limit: int = 100
    ) -> list[FundingRate]:
        """Get recent funding rates, optionally filtered by symbol."""
        statement = select(FundingRate)
        if symbol:
            statement = statement.where(FundingRate.symbol == symbol)
        statement = statement.order_by(desc(FundingRate.time)).limit(limit)
        result = await session.exec(statement)
        return result.all()

    async def get_sentiment_summary(self, session: AsyncSession) -> dict[str, Any]:
        """Get a summary of current market sentiment."""
        fear_greed = await self.get_fear_greed_current(session)
        btc_dom = await self.get_btc_dominance_current(session)
        return {
            "fear_greed": {"value": fear_greed.value, "classification": fear_greed.classification}
            if fear_greed
            else None,
            "btc_dominance": {"dominance": btc_dom.dominance, "total_market_cap": btc_dom.total_market_cap}
            if btc_dom
            else None,
        }
