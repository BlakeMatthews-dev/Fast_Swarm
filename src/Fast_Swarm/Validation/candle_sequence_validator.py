"""
Candle Sequence Validator.

Detects gaps in historical candle data that could corrupt backtest results.
"""

from datetime import timedelta
from typing import Any

# Expected intervals for each timeframe
EXPECTED_GAPS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def detect_gaps(
    candles: list[dict[str, Any]], timeframe: str = "1m"
) -> list[dict[str, Any]]:
    """
    Detect gaps in candle sequence.

    Args:
        candles: List of candle dicts with "timestamp" key (as datetime or unix).
        timeframe: Timeframe string (1m, 5m, 15m, 1h, 4h, 1d).

    Returns:
        List of gap dicts with start, end, and missing_candles count.
    """
    if len(candles) < 2:
        return []

    expected_interval = EXPECTED_GAPS.get(timeframe, timedelta(minutes=1))
    # Allow up to 3x expected interval before flagging as gap
    max_gap = expected_interval * 3

    gaps = []
    for i in range(1, len(candles)):
        prev_time = candles[i - 1].get("timestamp")
        curr_time = candles[i].get("timestamp")

        if prev_time is None or curr_time is None:
            continue

        # Handle both datetime objects and unix timestamps
        if isinstance(prev_time, (int, float)):
            from datetime import datetime, timezone

            prev_time = datetime.fromtimestamp(prev_time, tz=timezone.utc)
        if isinstance(curr_time, (int, float)):
            from datetime import datetime, timezone

            curr_time = datetime.fromtimestamp(curr_time, tz=timezone.utc)

        actual_gap = curr_time - prev_time

        if actual_gap > max_gap:
            missing_count = int(actual_gap / expected_interval) - 1
            gaps.append(
                {
                    "start": prev_time,
                    "end": curr_time,
                    "missing_candles": missing_count,
                    "gap_duration": actual_gap,
                }
            )

    return gaps


def validate_candle_sequence(
    candles: list[dict[str, Any]], timeframe: str = "1m"
) -> tuple[bool, str]:
    """
    Validate candles have no significant gaps.

    Args:
        candles: List of candle dicts.
        timeframe: Timeframe string.

    Returns:
        Tuple of (is_valid, message).
    """
    if not candles:
        return True, "empty sequence"

    gaps = detect_gaps(candles, timeframe)

    if gaps:
        total_missing = sum(g["missing_candles"] for g in gaps)
        return False, f"{len(gaps)} gaps detected, ~{total_missing} missing candles"

    return True, "ok"
