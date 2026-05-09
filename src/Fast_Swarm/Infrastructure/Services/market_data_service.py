from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.market_data_models import EnhancedCandle


class MarketDataService:
    """
    Service for retrieving historical and recent OHLCV data from enhanced_candles.

    The enhanced_candles table contains 5.2M rows with 200+ pre-computed indicators
    covering 2017-2025 across multiple timeframes (1m, 5m, 15m, 1h, etc.)
    """

    async def get_recent_candles(
        self, session: AsyncSession, symbol: str, timeframe: str, limit: int = 100
    ) -> list[EnhancedCandle]:
        """
        Get the most recent candles for a symbol and timeframe.

        Args:
            symbol: Trading pair (e.g., 'BTC', 'ETH', 'SOL')
            timeframe: Candle interval (e.g., '1h', '15m', '1d')
            limit: Maximum number of candles to return

        Returns:
            List of candles, newest first
        """
        statement = (
            select(EnhancedCandle)
            .where(EnhancedCandle.symbol == symbol)
            .where(EnhancedCandle.timeframe == timeframe)
            .order_by(desc(EnhancedCandle.time))
            .limit(limit)
        )
        result = await session.exec(statement)
        return result.all()

    async def get_candle_range(
        self, session: AsyncSession, symbol: str, timeframe: str, start_time: datetime, end_time: datetime
    ) -> list[EnhancedCandle]:
        """
        Get candles within a specific time range.

        Args:
            symbol: Trading pair
            timeframe: Candle interval
            start_time: Range start (inclusive)
            end_time: Range end (inclusive)

        Returns:
            List of candles, oldest first (chronological order)
        """
        statement = (
            select(EnhancedCandle)
            .where(EnhancedCandle.symbol == symbol)
            .where(EnhancedCandle.timeframe == timeframe)
            .where(EnhancedCandle.time >= start_time)
            .where(EnhancedCandle.time <= end_time)
            .order_by(EnhancedCandle.time.asc())
        )
        result = await session.exec(statement)
        return result.all()

    async def get_latest_price(self, session: AsyncSession, symbol: str) -> float | None:
        """Get the latest close price for a symbol."""
        statement = (
            select(EnhancedCandle.close)
            .where(EnhancedCandle.symbol == symbol)
            .order_by(desc(EnhancedCandle.time))
            .limit(1)
        )
        result = await session.exec(statement)
        return result.first()

    async def get_available_symbols(self, session: AsyncSession) -> list[str]:
        """Get list of all available symbols in the database."""
        statement = select(EnhancedCandle.symbol).distinct()
        result = await session.exec(statement)
        return result.all()

    async def get_available_timeframes(self, session: AsyncSession, symbol: str) -> list[str]:
        """Get available timeframes for a specific symbol."""
        statement = select(EnhancedCandle.timeframe).where(EnhancedCandle.symbol == symbol).distinct()
        result = await session.exec(statement)
        return result.all()
