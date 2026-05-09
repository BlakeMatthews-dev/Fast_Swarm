"""
OHLCV Data Loader for Local Backtesting.

Loads candle data from PostgreSQL enhanced_candles table (5.2M+ rows).
All indicators are pre-computed in the database.

Uses SYNC database connection to avoid async/event loop conflicts.
"""

import math
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import create_engine, func, select, text

# Try to import async database components (may not be available in all contexts)
try:
    from Fast_Swarm.Database import async_session_maker
    from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle
except ImportError:
    # Fallback: these will be None if imports fail
    async_session_maker = None  # type: ignore[assignment]
    EnhancedCandle = None  # type: ignore[assignment,misc]


# Build sync database URL
def _get_sync_db_url():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "coinswarm")
    password = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
    database = os.getenv("POSTGRES_DB", "coinswarm")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


# Singleton sync engine with connection pooling
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            _get_sync_db_url(),
            pool_size=10,  # Concurrent connections
            max_overflow=20,  # Extra connections under load
            pool_recycle=3600,  # Recycle connections after 1 hour
            pool_pre_ping=True,  # Verify connections are alive
        )
    return _sync_engine


def preload_candles_for_windows(
    windows: list,
    loader: "OHLCVLoader" = None,
) -> dict:
    """
    Preload candle data for a list of windows.

    Loads each unique (symbol, timeframe) pair once with the full date range
    needed to cover all windows. Returns dict for use with engine.preloaded_candles.

    Args:
        windows: List of Window objects (from backtest.windows module)
        loader: Optional OHLCVLoader instance (creates one if not provided)

    Returns:
        Dict of "{symbol}_{timeframe}" -> DataFrame

    Example:
        from Fast_Swarm.local_agents.backtest.windows import get_windows
        from Fast_Swarm.local_agents.backtest.data import preload_candles_for_windows
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine

        windows = get_windows(count=100)
        preloaded = preload_candles_for_windows(windows)
        engine = LocalBacktestEngine(preloaded_candles=preloaded)

        # Now backtests won't hit DB - data is already loaded
        for agent in agents:
            trades = engine.run(agent, window.to_dataset())
    """
    if loader is None:
        loader = OHLCVLoader()

    # Group windows by (symbol, timeframe) and find min/max timestamps
    ranges = {}
    for w in windows:
        key = (w.symbol, w.timeframe)
        if key not in ranges:
            ranges[key] = {"min_ts": w.start_ts, "max_ts": w.end_ts}
        else:
            ranges[key]["min_ts"] = min(ranges[key]["min_ts"], w.start_ts)
            ranges[key]["max_ts"] = max(ranges[key]["max_ts"], w.end_ts)

    # Load each unique pair once
    preloaded = {}
    for (symbol, timeframe), ts_range in ranges.items():
        cache_key = f"{symbol}_{timeframe}"
        df = loader.load_candles(
            asset=symbol,
            timeframe=timeframe,
            start_ts=ts_range["min_ts"],
            end_ts=ts_range["max_ts"],
            with_indicators=True,
        )
        preloaded[cache_key] = df
        print(f"  Preloaded {cache_key}: {len(df)} candles")

    return preloaded


@dataclass
class Candle:
    """Single OHLCV candle with optional indicators."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    asset: str = ""
    timeframe: str = "1h"
    indicators: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "asset": self.asset,
            "timeframe": self.timeframe,
            **self.indicators,
        }


class OHLCVLoader:
    """
    Load OHLCV data from PostgreSQL enhanced_candles table.

    The enhanced_candles table contains 5.2M+ rows with 60+ pre-computed indicators
    covering 2017-2025 across multiple timeframes (1m, 5m, 15m, 1h, 6h, 1d).

    All data comes from PostgreSQL - no SQLite fallback.
    """

    # Indicator columns available in EnhancedCandle (60+ columns)
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

    def __init__(
        self,
        db_path: str | None = None,
        enhanced_db_path: str | None = None,
        use_enhanced: bool = True,
        ohlcv_db: str | None = None,
    ):
        """
        Initialize the loader.

        Note: db_path, enhanced_db_path, ohlcv_db parameters are ignored.
        All data comes from PostgreSQL enhanced_candles table.
        These parameters exist only for backward compatibility.
        """
        # Parameters kept for backward compatibility but ignored
        # All data comes from PostgreSQL
        self._assets_cache: list[str] | None = None

    def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get list of available assets in the database."""
        if self._assets_cache is not None:
            return self._assets_cache

        engine = _get_sync_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT DISTINCT symbol FROM enhanced_candles
                WHERE timeframe = :timeframe
            """),
                {"timeframe": timeframe},
            )
            assets = [row[0] for row in result.fetchall()]

        self._assets_cache = assets
        return assets

    def load_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """
        Load OHLCV candles as a DataFrame from PostgreSQL (SYNC).

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH").
            timeframe: Candle timeframe ("1h", "6h", "1d", "15m", etc.).
            start_ts: Start timestamp (ms).
            end_ts: End timestamp (ms).
            limit: Maximum number of candles.
            with_indicators: Whether to include indicators (always available from DB).

        Returns:
            DataFrame with OHLCV + indicators.
        """
        engine = _get_sync_engine()

        # Build query with parameters
        params = {"symbol": asset, "timeframe": timeframe}
        where_clauses = ["symbol = :symbol", "timeframe = :timeframe"]

        if start_ts is not None:
            start_dt = datetime.fromtimestamp(start_ts / 1000, tz=UTC)
            where_clauses.append("time >= :start_dt")
            params["start_dt"] = start_dt

        if end_ts is not None:
            end_dt = datetime.fromtimestamp(end_ts / 1000, tz=UTC)
            where_clauses.append("time <= :end_dt")
            params["end_dt"] = end_dt

        where_sql = " AND ".join(where_clauses)
        limit_sql = f"LIMIT {limit}" if limit else ""

        query = text(f"""
            SELECT * FROM enhanced_candles
            WHERE {where_sql}
            ORDER BY time ASC
            {limit_sql}
        """)

        with engine.connect() as conn:
            result = conn.execute(query, params)
            rows = result.fetchall()
            columns = result.keys()

        if not rows:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=columns)

        # Convert time to timestamp in milliseconds for compatibility
        df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)

        # Add asset column for compatibility
        df["asset"] = asset

        # Ensure numeric types for OHLCV
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if not with_indicators:
            # Return only OHLCV columns
            cols = ["timestamp", "asset", "timeframe", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]

        return df

    def iter_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> Iterator[Candle]:
        """
        Iterate over candles one at a time.

        Useful for streaming backtests.
        """
        df = self.load_candles(
            asset=asset,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            with_indicators=True,
        )

        if df.empty:
            return

        # Get indicator columns
        base_cols = {
            "timestamp",
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "asset",
            "symbol",
            "timeframe",
            "exchange",
            "enriched_at",
        }
        indicator_cols = [c for c in df.columns if c not in base_cols]

        for _, row in df.iterrows():
            indicators = {}
            for col in indicator_cols:
                val = row.get(col)
                if val is not None and not pd.isna(val):
                    if isinstance(val, (int, float)):
                        if not (math.isnan(val) or math.isinf(val)):
                            indicators[col] = float(val)
                    else:
                        indicators[col] = val  # Keep strings (like regime)

            yield Candle(
                timestamp=int(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                asset=asset,
                timeframe=timeframe,
                indicators=indicators,
            )

    def get_date_range(self, asset: str, timeframe: str = "1h") -> tuple[int, int]:
        """Get the date range available for an asset."""

        async def _get_range():
            async with async_session_maker() as session:
                statement = (
                    select(func.min(EnhancedCandle.time), func.max(EnhancedCandle.time))
                    .where(EnhancedCandle.symbol == asset)
                    .where(EnhancedCandle.timeframe == timeframe)
                )
                result = await session.exec(statement)
                row = result.one_or_none()
                return row

        row = self._run_async(_get_range())

        if row and row[0] and row[1]:
            min_ts = int(row[0].timestamp() * 1000)
            max_ts = int(row[1].timestamp() * 1000)
            return (min_ts, max_ts)
        return (0, 0)

    def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get the number of candles available for an asset."""

        async def _get_count():
            async with async_session_maker() as session:
                statement = (
                    select(func.count())
                    .select_from(EnhancedCandle)
                    .where(EnhancedCandle.symbol == asset)
                    .where(EnhancedCandle.timeframe == timeframe)
                )
                result = await session.exec(statement)
                return result.one() or 0

        return self._run_async(_get_count())


class AsyncOHLCVLoader:
    """
    Async version of OHLCVLoader for use in async contexts.

    Use this directly in async code to avoid sync wrapper overhead.
    """

    INDICATOR_COLUMNS = OHLCVLoader.INDICATOR_COLUMNS

    async def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get list of available assets in the database."""
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
        """Load OHLCV candles as a DataFrame from PostgreSQL."""
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

        # Convert time to timestamp in milliseconds
        df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)
        df["asset"] = asset

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if not with_indicators:
            cols = ["timestamp", "asset", "timeframe", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]

        return df

    async def get_date_range(self, asset: str, timeframe: str = "1h") -> tuple[int, int]:
        """Get the date range available for an asset."""
        async with async_session_maker() as session:
            statement = (
                select(func.min(EnhancedCandle.time), func.max(EnhancedCandle.time))
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )
            result = await session.exec(statement)
            row = result.one_or_none()

        if row and row[0] and row[1]:
            min_ts = int(row[0].timestamp() * 1000)
            max_ts = int(row[1].timestamp() * 1000)
            return (min_ts, max_ts)
        return (0, 0)

    async def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get the number of candles available for an asset."""
        async with async_session_maker() as session:
            statement = (
                select(func.count())
                .select_from(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )
            result = await session.exec(statement)
            return result.one() or 0
