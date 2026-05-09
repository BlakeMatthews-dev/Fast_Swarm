"""
PostgreSQL OHLCV Loader - Uses EnhancedCandle table (5.2M+ rows).

This module provides a data loader interface compatible with the backtest system
but fetches data from PostgreSQL's enhanced_candles table instead of SQLite.
"""

import asyncio
from datetime import UTC, datetime

import pandas as pd
from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle
from sqlmodel import select


class PostgresOHLCVLoader:
    """
    Async OHLCV loader that fetches from PostgreSQL enhanced_candles table.

    The enhanced_candles table contains 5.2M+ rows with 60+ pre-computed indicators
    covering 2017-2025 across multiple timeframes (1m, 5m, 15m, 1h, 6h, 1d).

    Indicators include: RSI, MACD, Bollinger Bands, ATR, ADX, Stochastic,
    volume indicators (OBV, CMF, MFI), sentiment data, and cross-asset metrics.
    """

    # Standard OHLCV columns
    OHLCV_COLUMNS = ["time", "open", "high", "low", "close", "volume"]

    # Indicator columns available in EnhancedCandle
    INDICATOR_COLUMNS = [
        # Moving Averages
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_9",
        "ema_12",
        "ema_21",
        "ema_26",
        # RSI
        "rsi_7",
        "rsi_14",
        "rsi_21",
        # MACD
        "macd_line",
        "macd_signal",
        "macd_histogram",
        # Bollinger Bands
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "bb_width",
        "bb_pct",
        # ATR/Volatility
        "atr_7",
        "atr_14",
        "natr_14",
        "true_range",
        # Stochastic
        "stoch_k",
        "stoch_d",
        "stochrsi_k",
        "stochrsi_d",
        # ADX/Trend
        "adx_14",
        "plus_di",
        "minus_di",
        # Volume indicators
        "obv",
        "volume_sma_20",
        "cmf_20",
        "mfi_14",
        # Sentiment/Regime
        "fear_greed_value",
        "fear_greed_class",
        "regime",
        "regime_encoded",
        # Tick aggregates
        "tick_cvd_ratio",
        "tick_trade_imbalance",
        "tick_buy_volume_pct",
        "tick_volatility",
        "tick_momentum",
        # Order book aggregates
        "book_avg_spread_bps",
        "book_avg_imbalance",
        "book_depth_ratio",
        # Cross-asset metrics
        "btc_eth_correlation_14d",
        "eth_btc_ratio",
        "alt_dominance_pct",
    ]

    async def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get distinct symbols available for a timeframe."""
        async with async_session_maker() as session:
            statement = select(EnhancedCandle.symbol).where(EnhancedCandle.timeframe == timeframe).distinct()
            result = await session.exec(statement)
            return list(result.all())

    async def load_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """
        Load candles from PostgreSQL enhanced_candles table.

        Args:
            asset: Trading pair symbol (e.g., 'BTC', 'ETH', 'SOL')
            timeframe: Candle interval (e.g., '1h', '15m', '1d')
            start_ts: Start timestamp in milliseconds (inclusive)
            end_ts: End timestamp in milliseconds (inclusive)
            limit: Maximum number of candles to return
            with_indicators: Include pre-computed indicators (default True)

        Returns:
            DataFrame with OHLCV data and optionally indicators
        """
        async with async_session_maker() as session:
            statement = (
                select(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )

            if start_ts is not None:
                start_dt = datetime.fromtimestamp(start_ts / 1000, tz=UTC)
                statement = statement.where(EnhancedCandle.time >= start_dt)

            if end_ts is not None:
                end_dt = datetime.fromtimestamp(end_ts / 1000, tz=UTC)
                statement = statement.where(EnhancedCandle.time <= end_dt)

            statement = statement.order_by(EnhancedCandle.time.asc())

            if limit is not None:
                statement = statement.limit(limit)

            result = await session.exec(statement)
            candles = result.all()

            if not candles:
                return pd.DataFrame()

            # Convert to DataFrame
            data = [candle.model_dump() for candle in candles]
            df = pd.DataFrame(data)

            # Convert timestamp to milliseconds for compatibility
            df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)

            # Ensure numeric types
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            if not with_indicators:
                # Return only OHLCV columns
                cols = ["timestamp", "open", "high", "low", "close", "volume"]
                return df[[c for c in cols if c in df.columns]]

            return df

    async def get_latest_candle(self, asset: str, timeframe: str = "1h") -> dict | None:
        """Get the most recent candle for a symbol."""
        async with async_session_maker() as session:
            statement = (
                select(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
                .order_by(EnhancedCandle.time.desc())
                .limit(1)
            )
            result = await session.exec(statement)
            candle = result.first()
            return candle.model_dump() if candle else None

    async def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get total candle count for an asset/timeframe."""
        from sqlalchemy import func

        async with async_session_maker() as session:
            statement = (
                select(func.count())
                .select_from(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )
            result = await session.exec(statement)
            return result.one() or 0


class SyncPostgresOHLCVLoader:
    """
    Synchronous wrapper for PostgresOHLCVLoader.

    Use this in contexts where async is not available (e.g., some backtest engines).
    Creates its own event loop if needed.
    """

    def __init__(self):
        self._async_loader = PostgresOHLCVLoader()

    def _run_async(self, coro):
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, use nest_asyncio or raise
            raise RuntimeError(
                "SyncPostgresOHLCVLoader cannot be used inside async context. Use PostgresOHLCVLoader directly instead."
            )
        except RuntimeError:
            # No running loop, create one
            return asyncio.run(coro)

    def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get distinct symbols available for a timeframe."""
        return self._run_async(self._async_loader.get_available_assets(timeframe))

    def load_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """Load candles synchronously."""
        return self._run_async(
            self._async_loader.load_candles(asset, timeframe, start_ts, end_ts, limit, with_indicators)
        )

    def get_latest_candle(self, asset: str, timeframe: str = "1h") -> dict | None:
        """Get the most recent candle for a symbol."""
        return self._run_async(self._async_loader.get_latest_candle(asset, timeframe))

    def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get total candle count for an asset/timeframe."""
        return self._run_async(self._async_loader.get_candle_count(asset, timeframe))
