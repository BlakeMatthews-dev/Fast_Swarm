"""
Motion Derivative Service.

Computes velocity, acceleration, and jerk z-scores for Bear Protection.
Designed to be called at candle finalization time, NOT as a separate batch process.

The defensive_trigger boolean is computed inline and included in the candle
before it's inserted into the database.

Usage:
    # When a 1h or 4h candle closes:
    motion_data = await compute_motion_derivatives_for_candle(
        session=session,
        symbol="BTC",
        timeframe="1h",
        new_candle={"time": ..., "close": ..., "adx_14": ...}
    )

    # Merge into candle before insert
    candle.update(motion_data)
    # candle now has: close_acceleration_zscore, adx_14_jerk_zscore, defensive_trigger
"""

import logging
from datetime import datetime
from typing import Optional
import statistics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# AJ config thresholds (validated: +994% ROI on crypto, +4.2% on stocks)
ACC_THRESHOLD = -1.5
ADX_JERK_THRESHOLD = -0.5

# Window size for z-score computation
ZSCORE_WINDOW = 21


def compute_zscore(values: list[float], current_value: float) -> Optional[float]:
    """
    Compute z-score of current value against recent window.

    Args:
        values: List of recent values (should have at least ZSCORE_WINDOW items)
        current_value: The current value to z-score

    Returns:
        Z-score or None if insufficient data
    """
    if len(values) < ZSCORE_WINDOW or current_value is None:
        return None

    # Use the most recent ZSCORE_WINDOW values
    window = values[-ZSCORE_WINDOW:]

    try:
        mean = statistics.mean(window)
        std = statistics.stdev(window)

        if std == 0:
            return 0.0

        return (current_value - mean) / std
    except (statistics.StatisticsError, ZeroDivisionError):
        return None


def compute_derivatives(closes: list[float], adx_values: list[float]) -> dict:
    """
    Compute motion derivatives from price and ADX series.

    Args:
        closes: List of close prices (newest last)
        adx_values: List of ADX_14 values (newest last)

    Returns:
        Dict with derivative z-scores and defensive_trigger
    """
    result = {
        "close_velocity_zscore": None,
        "close_acceleration_zscore": None,
        "close_jerk_zscore": None,
        "adx_14_velocity_zscore": None,
        "adx_14_acceleration_zscore": None,
        "adx_14_jerk_zscore": None,
        "defensive_trigger": None,
    }

    n = len(closes)
    if n < ZSCORE_WINDOW + 3:  # Need enough data for 3rd derivative + z-score window
        return result

    # Compute price derivatives
    velocities = []
    for i in range(1, n):
        velocities.append(closes[i] - closes[i-1])

    accelerations = []
    for i in range(1, len(velocities)):
        accelerations.append(velocities[i] - velocities[i-1])

    jerks = []
    for i in range(1, len(accelerations)):
        jerks.append(accelerations[i] - accelerations[i-1])

    # Z-score the current values
    if len(accelerations) >= ZSCORE_WINDOW:
        result["close_velocity_zscore"] = compute_zscore(velocities[:-1], velocities[-1])
        result["close_acceleration_zscore"] = compute_zscore(accelerations[:-1], accelerations[-1])

    if len(jerks) >= ZSCORE_WINDOW:
        result["close_jerk_zscore"] = compute_zscore(jerks[:-1], jerks[-1])

    # Compute ADX derivatives (if available)
    valid_adx = [a for a in adx_values if a is not None]
    if len(valid_adx) >= ZSCORE_WINDOW + 3:
        adx_vels = []
        for i in range(1, len(valid_adx)):
            adx_vels.append(valid_adx[i] - valid_adx[i-1])

        adx_accs = []
        for i in range(1, len(adx_vels)):
            adx_accs.append(adx_vels[i] - adx_vels[i-1])

        adx_jerks = []
        for i in range(1, len(adx_accs)):
            adx_jerks.append(adx_accs[i] - adx_accs[i-1])

        if len(adx_jerks) >= ZSCORE_WINDOW:
            result["adx_14_jerk_zscore"] = compute_zscore(adx_jerks[:-1], adx_jerks[-1])

    # Compute defensive_trigger (CTC signal)
    acc_z = result["close_acceleration_zscore"]
    adx_jerk_z = result["adx_14_jerk_zscore"]

    if acc_z is not None and adx_jerk_z is not None:
        result["defensive_trigger"] = 1 if (acc_z < ACC_THRESHOLD and adx_jerk_z < ADX_JERK_THRESHOLD) else 0

    return result


async def compute_motion_derivatives_for_candle(
    session: AsyncSession,
    symbol: str,
    exchange: str,
    timeframe: str,
    new_candle: dict,
) -> dict:
    """
    Compute motion derivatives for a new candle at finalization time.

    Fetches the previous candles from the database, computes derivatives,
    and returns the derivative values to be merged into the candle before insert.

    Args:
        session: Database session
        symbol: Symbol (e.g., 'BTC')
        exchange: Exchange (e.g., 'binance')
        timeframe: Timeframe (e.g., '1h', '4h')
        new_candle: Dict with at least 'close' and optionally 'adx_14'

    Returns:
        Dict with motion derivative fields ready to merge into candle
    """
    # Only compute for Bear Protection timeframes
    if timeframe not in ("1h", "4h", "1d"):
        return {}

    # Fetch recent candles (need ZSCORE_WINDOW + 3 for derivatives)
    window_size = ZSCORE_WINDOW + 5  # Extra buffer

    query = text("""
        SELECT close, adx_14
        FROM enhanced_candles
        WHERE symbol = :symbol
          AND exchange = :exchange
          AND timeframe = :timeframe
        ORDER BY time DESC
        LIMIT :limit
    """)

    result = await session.execute(query, {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "limit": window_size,
    })
    rows = result.fetchall()

    if len(rows) < ZSCORE_WINDOW:
        logger.debug(f"Insufficient history for {symbol}/{timeframe}: {len(rows)} rows")
        return {}

    # Reverse to chronological order (oldest first) and extract values
    rows = rows[::-1]
    closes = [float(r[0]) for r in rows]
    adx_values = [float(r[1]) if r[1] is not None else None for r in rows]

    # Add the new candle's values
    closes.append(float(new_candle["close"]))
    adx_values.append(float(new_candle.get("adx_14")) if new_candle.get("adx_14") else None)

    # Compute derivatives
    motion_data = compute_derivatives(closes, adx_values)

    if motion_data.get("defensive_trigger") == 1:
        logger.warning(f"DEFENSIVE TRIGGER: {symbol}/{timeframe} - acc={motion_data['close_acceleration_zscore']:.2f}, jerk={motion_data['adx_14_jerk_zscore']:.2f}")

    return motion_data


def compute_motion_derivatives_from_history(
    candle_history: list[dict],
    current_candle: dict,
) -> dict:
    """
    Compute motion derivatives from in-memory candle history.

    Use this when you have candles already loaded in memory (e.g., from parquet
    or cached in HivemindDataFeedService).

    Args:
        candle_history: List of previous candle dicts (oldest first)
        current_candle: The new candle being finalized

    Returns:
        Dict with motion derivative fields
    """
    if len(candle_history) < ZSCORE_WINDOW:
        return {}

    # Extract values
    closes = [float(c.get("close", 0)) for c in candle_history]
    adx_values = [c.get("adx_14") for c in candle_history]

    # Add current candle
    closes.append(float(current_candle.get("close", 0)))
    adx_values.append(current_candle.get("adx_14"))

    # Clean adx values
    adx_values = [float(a) if a is not None else None for a in adx_values]

    return compute_derivatives(closes, adx_values)


# =============================================================================
# Integration helpers
# =============================================================================


def enrich_candle_with_motion(candle: dict, history: list[dict]) -> dict:
    """
    Convenience function to enrich a candle dict with motion derivatives.

    This modifies the candle in-place and returns it.

    Args:
        candle: Candle dict to enrich
        history: Previous candles for derivative computation

    Returns:
        The same candle dict, now with motion derivative fields
    """
    motion_data = compute_motion_derivatives_from_history(history, candle)
    candle.update(motion_data)
    return candle


def check_defensive_trigger(candle: dict) -> bool:
    """
    Check if a candle's defensive_trigger is active.

    Args:
        candle: Candle dict with defensive_trigger field

    Returns:
        True if defensive signal is firing
    """
    return candle.get("defensive_trigger") == 1


def check_multi_tf_defensive(tf_1h_candle: dict, tf_4h_candle: dict) -> bool:
    """
    Check if BOTH 1h and 4h timeframes show defensive trigger.

    This is the full Bear Protection signal - requires 2 TF confirmation.

    Args:
        tf_1h_candle: Latest 1h candle with defensive_trigger
        tf_4h_candle: Latest 4h candle with defensive_trigger

    Returns:
        True if BOTH timeframes show danger (CTC signal fires)
    """
    return (
        tf_1h_candle.get("defensive_trigger") == 1
        and tf_4h_candle.get("defensive_trigger") == 1
    )
