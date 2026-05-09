"""
Candle Gap Detection.

Detects missing candles in a time series based on expected intervals.
Non-blocking: logs warnings but does not halt backtests.
"""

import logging

logger = logging.getLogger(__name__)

EXPECTED_INTERVALS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def detect_gaps(
    candles: list[dict],
    timeframe: str,
    max_gap_factor: int = 3,
) -> list[dict]:
    """
    Detect missing candles in a time series.

    Args:
        candles: List of candle dicts with 'timestamp' or 'time' key.
        timeframe: Expected timeframe string (e.g. '1m', '5m', '1h').
        max_gap_factor: How many intervals constitute a gap (default 3).

    Returns:
        List of gap dicts: {start, end, missing} where missing is the
        estimated number of missing candles.
    """
    if len(candles) < 2:
        return []

    expected = EXPECTED_INTERVALS.get(timeframe, 60)
    max_gap = expected * max_gap_factor
    gaps = []

    for i in range(1, len(candles)):
        prev_ts = candles[i - 1].get("timestamp", candles[i - 1].get("time", 0))
        curr_ts = candles[i].get("timestamp", candles[i].get("time", 0))

        if prev_ts == 0 or curr_ts == 0:
            continue

        actual_gap = curr_ts - prev_ts
        if actual_gap > max_gap:
            missing_count = int(actual_gap / expected) - 1
            gaps.append({
                "start": prev_ts,
                "end": curr_ts,
                "missing": missing_count,
            })

    return gaps


def warn_if_gaps(candles: list[dict], timeframe: str) -> int:
    """
    Log a warning if data has gaps. Returns total missing candle count.

    Args:
        candles: List of candle dicts.
        timeframe: Expected timeframe string.

    Returns:
        Total number of estimated missing candles (0 if no gaps).
    """
    gaps = detect_gaps(candles, timeframe)
    if not gaps:
        return 0

    total_missing = sum(g["missing"] for g in gaps)
    logger.warning(
        f"Data has {len(gaps)} gap(s) ({total_missing} missing candles) "
        f"for timeframe={timeframe}"
    )
    return total_missing
