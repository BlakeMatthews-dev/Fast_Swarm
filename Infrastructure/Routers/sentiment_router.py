"""Sentiment data router for market sentiment indicators."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Services.sentiment_service import SentimentService

router = APIRouter(prefix="/sentiment", tags=["Sentiment"])
sentiment_service = SentimentService()


@router.get("/summary")
async def get_sentiment_summary(session: AsyncSession = Depends(get_session)):
    """
    Get current market sentiment summary.

    Returns Fear & Greed Index and BTC dominance in a single call.
    """
    return await sentiment_service.get_sentiment_summary(session)


@router.get("/fear-greed")
async def get_fear_greed(limit: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_session)):
    """
    Get Fear & Greed Index history.

    Values: 0 = Extreme Fear, 100 = Extreme Greed
    Classifications: Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    """
    readings = await sentiment_service.get_fear_greed_latest(session, limit)
    return [
        {
            "timestamp": r.timestamp,
            "value": r.value,
            "classification": r.classification,
        }
        for r in readings
    ]


@router.get("/fear-greed/current")
async def get_fear_greed_current(session: AsyncSession = Depends(get_session)):
    """Get the current Fear & Greed Index value."""
    reading = await sentiment_service.get_fear_greed_current(session)
    if not reading:
        return {"error": "No data available"}
    return {
        "timestamp": reading.timestamp,
        "value": reading.value,
        "classification": reading.classification,
    }


@router.get("/btc-dominance")
async def get_btc_dominance(limit: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_session)):
    """
    Get BTC dominance history.

    Shows Bitcoin's percentage share of total crypto market cap.
    """
    readings = await sentiment_service.get_btc_dominance_latest(session, limit)
    return [
        {
            "timestamp": r.timestamp,
            "dominance": r.dominance,
            "total_market_cap": r.total_market_cap,
        }
        for r in readings
    ]


@router.get("/funding-rates")
async def get_funding_rates(
    symbol: str | None = Query(None, description="Filter by symbol (e.g., BTC, ETH)"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """
    Get perpetual futures funding rates.

    Positive = longs pay shorts (bullish market bias)
    Negative = shorts pay longs (bearish market bias)
    """
    rates = await sentiment_service.get_funding_rates(session, symbol, limit)
    return [
        {
            "time": r.time.isoformat() if r.time else None,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "funding_rate": r.funding_rate,
        }
        for r in rates
    ]
