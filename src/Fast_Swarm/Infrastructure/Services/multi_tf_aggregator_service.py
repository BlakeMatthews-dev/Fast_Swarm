"""
Multi-Timeframe Aggregator Service.

Aggregates indicators from multiple timeframes into a single dict with
TF-prefixed keys for Bear Protection evaluation.

The BearProtectionService expects indicators like:
- tf_1h_close_acceleration_zscore
- tf_4h_adx_14_jerk_zscore
- tf_1d_close_velocity_zscore

This service fetches the latest data from each timeframe and combines them.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import polars as pl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Timeframes to aggregate for Bear Protection
BEAR_PROTECTION_TIMEFRAMES = ["1h", "4h", "1d"]

# Indicator columns to aggregate (motion derivatives for Bear Protection)
MOTION_DERIVATIVE_COLUMNS = [
    "close_velocity_zscore",
    "close_acceleration_zscore",
    "adx_14_jerk_zscore",
    "close_jerk_zscore",  # Include price jerk for completeness
]


async def get_multi_tf_indicators(
    session: AsyncSession,
    symbol: str,
    exchange: str,
    as_of_time: Optional[datetime] = None,
    timeframes: list[str] = None,
) -> dict[str, float]:
    """
    Fetch and aggregate indicators from multiple timeframes.

    Args:
        session: Database session
        symbol: Symbol to fetch (e.g., 'BTC')
        exchange: Exchange (e.g., 'binance')
        as_of_time: Time to fetch indicators for (default: now)
        timeframes: Timeframes to aggregate (default: 1h, 4h, 1d)

    Returns:
        Dict with tf-prefixed indicator keys:
        {
            'tf_1h_close_acceleration_zscore': -1.8,
            'tf_1h_adx_14_jerk_zscore': -0.7,
            'tf_4h_close_acceleration_zscore': -2.1,
            ...
        }
    """
    timeframes = timeframes or BEAR_PROTECTION_TIMEFRAMES
    as_of_time = as_of_time or datetime.now(timezone.utc)

    aggregated = {}

    for tf in timeframes:
        # Fetch most recent candle before as_of_time
        query = text("""
            SELECT
                close_velocity_zscore,
                close_acceleration_zscore,
                close_jerk_zscore,
                adx_14_jerk_zscore,
                time
            FROM enhanced_candles
            WHERE symbol = :symbol
              AND exchange = :exchange
              AND timeframe = :timeframe
              AND time <= :as_of_time
            ORDER BY time DESC
            LIMIT 1
        """)

        result = await session.execute(query, {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": tf,
            "as_of_time": as_of_time,
        })
        row = result.fetchone()

        if row:
            # Add with tf prefix
            prefix = f"tf_{tf}_"
            if row.close_velocity_zscore is not None:
                aggregated[f"{prefix}close_velocity_zscore"] = float(row.close_velocity_zscore)
            if row.close_acceleration_zscore is not None:
                aggregated[f"{prefix}close_acceleration_zscore"] = float(row.close_acceleration_zscore)
            if row.close_jerk_zscore is not None:
                aggregated[f"{prefix}close_jerk_zscore"] = float(row.close_jerk_zscore)
            if row.adx_14_jerk_zscore is not None:
                aggregated[f"{prefix}adx_14_jerk_zscore"] = float(row.adx_14_jerk_zscore)

    return aggregated


def aggregate_from_parquet(
    data_dir,
    symbol: str,
    timeframes: list[str] = None,
    as_of_time: Optional[datetime] = None,
) -> dict[str, float]:
    """
    Aggregate indicators from parquet files (for backtesting).

    Args:
        data_dir: Path to derivatives data directory
        symbol: Symbol to fetch (e.g., 'BTC', 'AAPL')
        timeframes: Timeframes to aggregate
        as_of_time: Time to get indicators for

    Returns:
        Dict with tf-prefixed indicator keys
    """
    from pathlib import Path

    timeframes = timeframes or BEAR_PROTECTION_TIMEFRAMES
    data_dir = Path(data_dir)
    aggregated = {}

    for tf in timeframes:
        path = data_dir / f"symbol={symbol}" / f"timeframe={tf}" / "data.parquet"
        if not path.exists():
            continue

        df = pl.read_parquet(path).sort("time")

        if as_of_time:
            # Filter to candles before as_of_time
            df = df.filter(pl.col("time") <= as_of_time)

        if df.is_empty():
            continue

        # Get the latest row
        row = df.tail(1).to_dicts()[0]

        # Add with tf prefix
        prefix = f"tf_{tf}_"
        for col in MOTION_DERIVATIVE_COLUMNS:
            if col in row and row[col] is not None:
                aggregated[f"{prefix}{col}"] = float(row[col])

    return aggregated


def merge_indicators_with_tf_prefix(
    base_indicators: dict,
    tf_name: str,
    tf_indicators: dict,
) -> dict:
    """
    Merge timeframe-specific indicators into base dict with prefix.

    Args:
        base_indicators: Base indicator dict to merge into
        tf_name: Timeframe name (e.g., '1h', '4h')
        tf_indicators: Indicators from that timeframe

    Returns:
        Updated base_indicators dict
    """
    prefix = f"tf_{tf_name}_"

    for col in MOTION_DERIVATIVE_COLUMNS:
        if col in tf_indicators and tf_indicators[col] is not None:
            base_indicators[f"{prefix}{col}"] = float(tf_indicators[col])

    return base_indicators


class MultiTFAggregator:
    """
    Stateful multi-TF indicator aggregator.

    Maintains the latest indicators from each timeframe and provides
    a combined view for Bear Protection evaluation.

    Usage:
        aggregator = MultiTFAggregator()

        # Update when new candles arrive
        aggregator.update_timeframe('1h', candle_indicators)
        aggregator.update_timeframe('4h', candle_indicators)

        # Get combined indicators for Bear Protection
        multi_tf_indicators = aggregator.get_combined()
    """

    def __init__(self, timeframes: list[str] = None):
        self.timeframes = timeframes or BEAR_PROTECTION_TIMEFRAMES
        self._latest_indicators: dict[str, dict] = {tf: {} for tf in self.timeframes}
        self._last_update: dict[str, datetime] = {}

    def update_timeframe(self, tf: str, indicators: dict, timestamp: datetime = None):
        """Update indicators for a specific timeframe."""
        if tf not in self.timeframes:
            return

        # Store the motion derivative indicators
        self._latest_indicators[tf] = {
            col: indicators.get(col) for col in MOTION_DERIVATIVE_COLUMNS
            if col in indicators
        }
        self._last_update[tf] = timestamp or datetime.now(timezone.utc)

    def get_combined(self) -> dict[str, float]:
        """
        Get combined indicators with tf_ prefixes.

        Returns dict ready for BearProtectionService.MarketState:
        {
            'tf_1h_close_acceleration_zscore': -1.8,
            'tf_1h_adx_14_jerk_zscore': -0.7,
            ...
        }
        """
        combined = {}

        for tf in self.timeframes:
            prefix = f"tf_{tf}_"
            for col, value in self._latest_indicators[tf].items():
                if value is not None:
                    combined[f"{prefix}{col}"] = float(value)

        return combined

    def get_staleness(self) -> dict[str, float]:
        """Get staleness of each timeframe's data in seconds."""
        now = datetime.now(timezone.utc)
        staleness = {}

        for tf in self.timeframes:
            last = self._last_update.get(tf)
            if last:
                staleness[tf] = (now - last).total_seconds()
            else:
                staleness[tf] = float('inf')

        return staleness

    def is_fresh(self, max_staleness_seconds: dict[str, float] = None) -> bool:
        """
        Check if all timeframes have fresh data.

        Args:
            max_staleness_seconds: Max allowed staleness per TF
                Default: 1h=3700, 4h=14500, 1d=90000
        """
        if max_staleness_seconds is None:
            max_staleness_seconds = {
                "1h": 3700,    # 1h + 100s buffer
                "4h": 14500,   # 4h + 100s buffer
                "1d": 90000,   # 1d + 3600s buffer
            }

        staleness = self.get_staleness()
        for tf in self.timeframes:
            max_stale = max_staleness_seconds.get(tf, 3700)
            if staleness.get(tf, float('inf')) > max_stale:
                return False

        return True


# =============================================================================
# Convenience Functions for Bear Protection
# =============================================================================


def build_market_state_indicators(
    symbol: str,
    tf_1h_row: dict = None,
    tf_4h_row: dict = None,
    tf_1d_row: dict = None,
) -> dict[str, float]:
    """
    Build indicator dict for BearProtectionService from separate TF candle rows.

    This is a simple utility when you have individual candle rows from each TF.

    Args:
        symbol: Symbol name
        tf_1h_row: 1h candle dict with indicator columns
        tf_4h_row: 4h candle dict
        tf_1d_row: 1d candle dict

    Returns:
        Dict ready for executor._build_market_state()
    """
    indicators = {}

    for tf_name, row in [("1h", tf_1h_row), ("4h", tf_4h_row), ("1d", tf_1d_row)]:
        if row is None:
            continue

        prefix = f"tf_{tf_name}_"
        for col in MOTION_DERIVATIVE_COLUMNS:
            if col in row and row[col] is not None:
                indicators[f"{prefix}{col}"] = float(row[col])

    return indicators
