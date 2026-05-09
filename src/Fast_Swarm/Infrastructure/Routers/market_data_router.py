from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ...Database import get_session
from ..Models.market_data_models import ExchangeTick, OrderBookSnapshot
from ..Services.market_data_service import MarketDataService

router = APIRouter(prefix="/market_data", tags=["Market Data"])
market_service = MarketDataService()


@router.get("/candles", response_model=list[dict])
async def get_candles(
    symbol: str = Query(..., description="e.g. BTC, ETH, SOL"),
    timeframe: str = Query("1h", description="e.g. 1m, 5m, 15m, 1h, 1d"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """
    Get latest candles with pre-computed indicators for a symbol.

    Returns newest first. Includes 200+ technical indicators like RSI, MACD,
    Bollinger Bands, ATR, ADX, Stochastic, and more.
    """
    candles = await market_service.get_recent_candles(session, symbol, timeframe, limit)
    return [
        {
            "time": c.time.isoformat() if c.time else None,
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "rsi_14": c.rsi_14,
            "macd_line": c.macd_line,
            "macd_signal": c.macd_signal,
            "bb_upper": c.bb_upper,
            "bb_lower": c.bb_lower,
            "atr_14": c.atr_14,
            "adx_14": c.adx_14,
            "stoch_k": c.stoch_k,
            "stoch_d": c.stoch_d,
            "fear_greed_value": c.fear_greed_value,
            "regime": c.regime,
        }
        for c in candles
    ]


@router.get("/range")
async def get_candle_range(
    symbol: str,
    timeframe: str,
    start: datetime = Query(..., description="ISO format start time"),
    end: datetime = Query(..., description="ISO format end time"),
    session: AsyncSession = Depends(get_session),
):
    """Get candles within a specific time range."""
    candles = await market_service.get_candle_range(session, symbol, timeframe, start, end)
    return [
        {
            "time": c.time.isoformat() if c.time else None,
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "rsi_14": c.rsi_14,
            "macd_line": c.macd_line,
            "atr_14": c.atr_14,
            "regime": c.regime,
        }
        for c in candles
    ]


@router.get("/price/{symbol}")
async def get_latest_price(symbol: str, session: AsyncSession = Depends(get_session)):
    """Get the latest close price for a symbol."""
    price = await market_service.get_latest_price(session, symbol)
    return {"symbol": symbol, "price": price}


@router.get("/symbols")
async def get_available_symbols(session: AsyncSession = Depends(get_session)):
    """Get list of all available symbols in the database."""
    symbols = await market_service.get_available_symbols(session)
    return {"symbols": symbols, "count": len(symbols)}


@router.get("/timeframes/{symbol}")
async def get_available_timeframes(symbol: str, session: AsyncSession = Depends(get_session)):
    """Get available timeframes for a specific symbol."""
    timeframes = await market_service.get_available_timeframes(session, symbol)
    return {"symbol": symbol, "timeframes": timeframes}


@router.get("/ticks")
async def get_ticks(
    symbol: str = Query(..., description="Symbol (e.g., BTC, ETH)"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Get raw tick data (12.5M+ rows)."""
    stmt = select(ExchangeTick).where(ExchangeTick.symbol == symbol).order_by(desc(ExchangeTick.time)).limit(limit)
    result = await session.exec(stmt)
    return [
        {
            "time": t.time.isoformat(),
            "exchange": t.exchange,
            "symbol": t.symbol,
            "price": t.price,
            "size": t.size,
            "side": t.side,
        }
        for t in result.all()
    ]


@router.get("/orderbook")
async def get_orderbook_snapshots(
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Get order book snapshots (781K+ rows)."""
    stmt = select(OrderBookSnapshot).order_by(desc(OrderBookSnapshot.timestamp))
    if symbol:
        stmt = stmt.where(OrderBookSnapshot.symbol == symbol)
    stmt = stmt.limit(limit)
    result = await session.exec(stmt)
    return [
        {
            "timestamp": s.timestamp,
            "exchange": s.exchange,
            "symbol": s.symbol,
            "mid_price": s.mid_price,
            "spread_bps": s.spread_bps,
            "imbalance": s.imbalance,
            "bid_vol_10": s.bid_vol_10,
            "ask_vol_10": s.ask_vol_10,
        }
        for s in result.all()
    ]
