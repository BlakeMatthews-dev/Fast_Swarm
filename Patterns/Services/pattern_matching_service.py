"""
Pattern Matching Service for Fast_Swarm.

Provides indicator condition matching, confidence scoring, and pattern evaluation.
Evolution discovers optimal boundaries - we just match against them.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

# =============================================================================
# Constants - Supported Indicators
# =============================================================================

INDICATORS = [
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_width",
    "atr",
    "adx",
    "obv",
    "volume_ratio",
    "ema_9",
    "ema_21",
    "ema_50",
    "sma_200",
    "stoch_k",
    "stoch_d",
    "williams_r",
    "cci",
    "roc",
    "momentum",
    "mfi",
    "vwap",
]

# Indicator bounds for validation
INDICATOR_BOUNDS = {
    "rsi": (0, 100),
    "stoch_k": (0, 100),
    "stoch_d": (0, 100),
    "adx": (0, 100),
    "mfi": (0, 100),
    "williams_r": (-100, 0),
    "atr": (0, float("inf")),
    "volume_ratio": (0, float("inf")),
    "bb_width": (0, float("inf")),
    # MACD, CCI, ROC, momentum are unbounded
}

# Default lookback periods
INDICATOR_LOOKBACK = {
    "rsi": 15,  # 14 + 1
    "macd": 35,  # 26 + 9
    "macd_signal": 35,
    "macd_histogram": 35,
    "bb_upper": 21,  # 20 + 1
    "bb_middle": 21,
    "bb_lower": 21,
    "bb_width": 21,
    "atr": 15,  # 14 + 1
    "adx": 15,
    "ema_9": 10,
    "ema_21": 22,
    "ema_50": 51,
    "sma_200": 200,
    "stoch_k": 15,
    "stoch_d": 15,
    "williams_r": 15,
    "cci": 21,
    "roc": 13,
    "momentum": 11,
    "mfi": 15,
    "vwap": 1,
    "obv": 1,
    "volume_ratio": 2,
}


class Signal(Enum):
    """Trading signal types."""

    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class LogicOperator(Enum):
    """Condition combination operators."""

    AND = "AND"
    OR = "OR"


@dataclass
class MatchResult:
    """Result of pattern matching."""

    matched: bool
    confidence: float
    signal: Signal
    matched_conditions: int
    total_conditions: int
    details: dict[str, Any]


@dataclass
class Condition:
    """A single indicator condition."""

    indicator: str
    min_value: float
    max_value: float
    weight: float = 1.0


# =============================================================================
# Indicator Condition Matching
# =============================================================================


def match_condition(
    value: float | None,
    min_value: float,
    max_value: float,
    tolerance: float = 1e-9,
) -> bool:
    """
    Check if value falls within [min_value, max_value] (inclusive).

    Args:
        value: The indicator value to check
        min_value: Minimum bound (inclusive)
        max_value: Maximum bound (inclusive)
        tolerance: Float comparison tolerance

    Returns:
        True if value is within bounds, False otherwise
    """
    if value is None:
        return False

    if not isinstance(value, (int, float)):
        return False

    if math.isnan(value) or math.isinf(value):
        return False

    # Inclusive bounds with tolerance
    return (value >= min_value - tolerance) and (value <= max_value + tolerance)


def match_indicator_condition(
    indicator_name: str,
    indicator_value: float | None,
    condition: dict[str, Any],
) -> bool:
    """
    Match a single indicator against a condition.

    Args:
        indicator_name: Name of the indicator
        indicator_value: Current value of the indicator
        condition: Dict with 'min' and 'max' keys

    Returns:
        True if indicator matches condition
    """
    if indicator_value is None:
        return False

    min_val = condition.get("min", float("-inf"))
    max_val = condition.get("max", float("inf"))

    return match_condition(indicator_value, min_val, max_val)


def calculate_condition_confidence(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    """
    Calculate confidence score for how well a value matches a range.

    Values at center of range = 1.0, at edges = lower confidence.

    Args:
        value: The indicator value
        min_value: Minimum bound
        max_value: Maximum bound

    Returns:
        Confidence score in [0, 1]
    """
    if not match_condition(value, min_value, max_value):
        return 0.0

    range_size = max_value - min_value
    if range_size <= 0:
        return 1.0 if value == min_value else 0.0

    center = (min_value + max_value) / 2
    distance_from_center = abs(value - center)
    max_distance = range_size / 2

    # Linear confidence: 1.0 at center, decreasing to edges
    # Minimum confidence at edges is 0.5 (not 0)
    confidence = 1.0 - (distance_from_center / max_distance) * 0.5

    return max(0.0, min(1.0, confidence))


# =============================================================================
# Multi-Condition Logic
# =============================================================================


def match_conditions_and(
    indicators: dict[str, float],
    conditions: list[dict[str, Any]],
) -> tuple[bool, int, int]:
    """
    Match multiple conditions with AND logic (all must match).

    Args:
        indicators: Dict of indicator name -> value
        conditions: List of condition dicts

    Returns:
        Tuple of (all_matched, matched_count, total_count)
    """
    if not conditions:
        return True, 0, 0

    matched_count = 0
    for cond in conditions:
        indicator_name = cond.get("indicator")
        indicator_value = indicators.get(indicator_name)

        if match_indicator_condition(indicator_name, indicator_value, cond):
            matched_count += 1

    all_matched = matched_count == len(conditions)
    return all_matched, matched_count, len(conditions)


def match_conditions_or(
    indicators: dict[str, float],
    conditions: list[dict[str, Any]],
) -> tuple[bool, int, int]:
    """
    Match multiple conditions with OR logic (any must match).

    Args:
        indicators: Dict of indicator name -> value
        conditions: List of condition dicts

    Returns:
        Tuple of (any_matched, matched_count, total_count)
    """
    if not conditions:
        return False, 0, 0

    matched_count = 0
    for cond in conditions:
        indicator_name = cond.get("indicator")
        indicator_value = indicators.get(indicator_name)

        if match_indicator_condition(indicator_name, indicator_value, cond):
            matched_count += 1

    any_matched = matched_count > 0
    return any_matched, matched_count, len(conditions)


def match_conditions(
    indicators: dict[str, float],
    conditions: list[dict[str, Any]],
    logic: LogicOperator = LogicOperator.AND,
) -> tuple[bool, int, int]:
    """
    Match conditions with specified logic operator.

    Args:
        indicators: Dict of indicator name -> value
        conditions: List of condition dicts
        logic: AND or OR operator (default AND)

    Returns:
        Tuple of (matched, matched_count, total_count)
    """
    if logic == LogicOperator.OR:
        return match_conditions_or(indicators, conditions)
    return match_conditions_and(indicators, conditions)


# =============================================================================
# Confidence Scoring
# =============================================================================


def calculate_match_confidence(
    indicators: dict[str, float],
    conditions: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> float:
    """
    Calculate overall confidence score for a pattern match.

    Args:
        indicators: Dict of indicator name -> value
        conditions: List of condition dicts
        weights: Optional indicator weight overrides

    Returns:
        Confidence score in [0, 1]
    """
    if not conditions:
        return 0.0

    weights = weights or {}
    total_weight = 0.0
    weighted_confidence = 0.0

    for cond in conditions:
        indicator_name = cond.get("indicator")
        indicator_value = indicators.get(indicator_name)

        if indicator_value is None:
            continue

        if math.isnan(indicator_value) or math.isinf(indicator_value):
            continue

        min_val = cond.get("min", float("-inf"))
        max_val = cond.get("max", float("inf"))
        weight = weights.get(indicator_name, cond.get("weight", 1.0))

        confidence = calculate_condition_confidence(indicator_value, min_val, max_val)
        weighted_confidence += confidence * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return max(0.0, min(1.0, weighted_confidence / total_weight))


# =============================================================================
# Pattern Matching
# =============================================================================


def match_pattern(
    pattern: dict[str, Any],
    indicators: dict[str, float],
    check_entry: bool = True,
    check_exit: bool = False,
) -> MatchResult:
    """
    Match a pattern against indicator values.

    Args:
        pattern: Pattern dict with entry_conditions and exit_conditions
        indicators: Dict of indicator name -> value
        check_entry: Whether to check entry conditions
        check_exit: Whether to check exit conditions

    Returns:
        MatchResult with match status and confidence
    """
    entry_conditions = pattern.get("entry_conditions", [])
    exit_conditions = pattern.get("exit_conditions", [])
    logic_str = pattern.get("logic", "AND").upper()
    logic = LogicOperator.OR if logic_str == "OR" else LogicOperator.AND

    # Check entry conditions
    entry_matched = False
    entry_count = 0
    entry_total = 0

    if check_entry and entry_conditions:
        entry_matched, entry_count, entry_total = match_conditions(indicators, entry_conditions, logic)

    # Check exit conditions
    exit_matched = False
    exit_count = 0
    exit_total = 0

    if check_exit and exit_conditions:
        exit_matched, exit_count, exit_total = match_conditions(indicators, exit_conditions, logic)

    # Determine signal
    signal = Signal.NONE
    if check_entry and entry_matched:
        # Pattern direction (default LONG)
        direction = pattern.get("direction", "LONG").upper()
        signal = Signal.LONG if direction == "LONG" else Signal.SHORT
    elif check_exit and exit_matched:
        signal = Signal.NONE  # Exit signal

    # Calculate confidence
    all_conditions = []
    if check_entry:
        all_conditions.extend(entry_conditions)
    if check_exit:
        all_conditions.extend(exit_conditions)

    confidence = calculate_match_confidence(indicators, all_conditions)

    # Overall match status
    matched = entry_matched if check_entry else exit_matched
    matched_count = entry_count + exit_count
    total_count = entry_total + exit_total

    return MatchResult(
        matched=matched,
        confidence=confidence if matched else 0.0,
        signal=signal,
        matched_conditions=matched_count,
        total_conditions=total_count,
        details={
            "entry_matched": entry_matched,
            "exit_matched": exit_matched,
            "entry_conditions_matched": entry_count,
            "exit_conditions_matched": exit_count,
        },
    )


def match_pattern_against_candle(
    pattern: dict[str, Any],
    candle: dict[str, float],
    indicators: dict[str, float],
) -> MatchResult:
    """
    Match a pattern against a single candle with its indicators.

    Args:
        pattern: Pattern dict
        candle: OHLCV candle dict
        indicators: Pre-computed indicator values

    Returns:
        MatchResult
    """
    # Combine candle data with indicators
    combined = {**indicators}
    combined["open"] = candle.get("open", 0)
    combined["high"] = candle.get("high", 0)
    combined["low"] = candle.get("low", 0)
    combined["close"] = candle.get("close", 0)
    combined["volume"] = candle.get("volume", 0)

    return match_pattern(pattern, combined, check_entry=True, check_exit=False)


def match_pattern_against_series(
    pattern: dict[str, Any],
    candles: list[dict[str, float]],
    indicator_series: list[dict[str, float]],
) -> list[MatchResult]:
    """
    Match a pattern against a series of candles.

    Args:
        pattern: Pattern dict
        candles: List of OHLCV candles
        indicator_series: List of indicator dicts (one per candle)

    Returns:
        List of MatchResults (one per candle)
    """
    results = []
    for i, candle in enumerate(candles):
        indicators = indicator_series[i] if i < len(indicator_series) else {}
        result = match_pattern_against_candle(pattern, candle, indicators)
        results.append(result)
    return results


# =============================================================================
# Indicator Calculations
# =============================================================================


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    """
    Calculate RSI (Relative Strength Index).

    Args:
        closes: List of closing prices
        period: RSI period (default 14)

    Returns:
        RSI value in [0, 100] or None if insufficient data
    """
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return None

    # Use recent 'period' values
    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return max(0.0, min(100.0, rsi))


def calculate_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float] | None:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        closes: List of closing prices
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line period (default 9)

    Returns:
        Dict with 'macd', 'signal', 'histogram' or None
    """
    if len(closes) < slow + signal:
        return None

    def ema(data: list[float], period: int) -> list[float]:
        if len(data) < period:
            return []
        multiplier = 2 / (period + 1)
        ema_values = [sum(data[:period]) / period]
        for price in data[period:]:
            ema_values.append((price * multiplier) + (ema_values[-1] * (1 - multiplier)))
        return ema_values

    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)

    if not fast_ema or not slow_ema:
        return None

    # Align EMAs
    offset = slow - fast
    if offset > len(fast_ema):
        return None

    macd_line = []
    for i in range(len(slow_ema)):
        fast_idx = i + offset
        if fast_idx < len(fast_ema):
            macd_line.append(fast_ema[fast_idx] - slow_ema[i])

    if len(macd_line) < signal:
        return None

    signal_line = ema(macd_line, signal)
    if not signal_line:
        return None

    macd_value = macd_line[-1]
    signal_value = signal_line[-1]
    histogram = macd_value - signal_value

    return {
        "macd": macd_value,
        "macd_signal": signal_value,
        "macd_histogram": histogram,
    }


def calculate_bollinger_bands(
    closes: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, float] | None:
    """
    Calculate Bollinger Bands.

    Args:
        closes: List of closing prices
        period: SMA period (default 20)
        std_dev: Standard deviation multiplier (default 2)

    Returns:
        Dict with 'bb_upper', 'bb_middle', 'bb_lower', 'bb_width' or None
    """
    if len(closes) < period:
        return None

    recent = closes[-period:]
    middle = sum(recent) / period

    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)

    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    width = (upper - lower) / middle if middle != 0 else 0

    return {
        "bb_upper": upper,
        "bb_middle": middle,
        "bb_lower": lower,
        "bb_width": width,
    }


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """
    Calculate ATR (Average True Range).

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ATR period (default 14)

    Returns:
        ATR value or None
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[-period:]) / period
    return max(0.0, atr)


def calculate_stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_period: int = 14,
    d_period: int = 3,
) -> dict[str, float] | None:
    """
    Calculate Stochastic Oscillator.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        k_period: %K period (default 14)
        d_period: %D period (default 3)

    Returns:
        Dict with 'stoch_k', 'stoch_d' or None
    """
    if len(highs) < k_period or len(lows) < k_period or len(closes) < k_period:
        return None

    k_values = []
    for i in range(k_period - 1, len(closes)):
        window_highs = highs[i - k_period + 1 : i + 1]
        window_lows = lows[i - k_period + 1 : i + 1]

        highest = max(window_highs)
        lowest = min(window_lows)
        current_close = closes[i]

        if highest == lowest:
            k_values.append(50.0)
        else:
            k = ((current_close - lowest) / (highest - lowest)) * 100
            k_values.append(max(0.0, min(100.0, k)))

    if len(k_values) < d_period:
        return None

    stoch_k = k_values[-1]
    stoch_d = sum(k_values[-d_period:]) / d_period

    return {
        "stoch_k": max(0.0, min(100.0, stoch_k)),
        "stoch_d": max(0.0, min(100.0, stoch_d)),
    }


def calculate_williams_r(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """
    Calculate Williams %R.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: Period (default 14)

    Returns:
        Williams %R in [-100, 0] or None
    """
    if len(highs) < period or len(lows) < period or len(closes) < period:
        return None

    highest = max(highs[-period:])
    lowest = min(lows[-period:])
    current_close = closes[-1]

    if highest == lowest:
        return -50.0

    wr = ((highest - current_close) / (highest - lowest)) * -100
    return max(-100.0, min(0.0, wr))


def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """
    Calculate ADX (Average Directional Index).

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ADX period (default 14)

    Returns:
        ADX value in [0, 100] or None
    """
    if len(highs) < period * 2 or len(lows) < period * 2 or len(closes) < period * 2:
        return None

    # Simplified ADX calculation
    atr = calculate_atr(highs, lows, closes, period)
    if atr is None or atr == 0:
        return None

    # Calculate +DM and -DM
    plus_dm = []
    minus_dm = []

    for i in range(1, len(highs)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)

    if len(plus_dm) < period:
        return None

    # Smoothed averages
    avg_plus_dm = sum(plus_dm[-period:]) / period
    avg_minus_dm = sum(minus_dm[-period:]) / period

    # Directional indicators
    plus_di = (avg_plus_dm / atr) * 100 if atr > 0 else 0
    minus_di = (avg_minus_dm / atr) * 100 if atr > 0 else 0

    # ADX
    di_sum = plus_di + minus_di
    if di_sum == 0:
        return 0.0

    dx = abs(plus_di - minus_di) / di_sum * 100
    return max(0.0, min(100.0, dx))


def calculate_all_indicators(
    candles: list[dict[str, float]],
) -> dict[str, float | None]:
    """
    Calculate all indicators from OHLCV candles.

    Args:
        candles: List of OHLCV candle dicts

    Returns:
        Dict of indicator name -> value
    """
    if not candles:
        return {}

    opens = [c.get("open", 0) for c in candles]
    highs = [c.get("high", 0) for c in candles]
    lows = [c.get("low", 0) for c in candles]
    closes = [c.get("close", 0) for c in candles]
    volumes = [c.get("volume", 0) for c in candles]

    indicators = {}

    # RSI
    indicators["rsi"] = calculate_rsi(closes)

    # MACD
    macd_result = calculate_macd(closes)
    if macd_result:
        indicators.update(macd_result)

    # Bollinger Bands
    bb_result = calculate_bollinger_bands(closes)
    if bb_result:
        indicators.update(bb_result)

    # ATR
    indicators["atr"] = calculate_atr(highs, lows, closes)

    # Stochastic
    stoch_result = calculate_stochastic(highs, lows, closes)
    if stoch_result:
        indicators.update(stoch_result)

    # Williams %R
    indicators["williams_r"] = calculate_williams_r(highs, lows, closes)

    # ADX
    indicators["adx"] = calculate_adx(highs, lows, closes)

    # Volume ratio
    if len(volumes) >= 2 and volumes[-2] > 0:
        indicators["volume_ratio"] = volumes[-1] / volumes[-2]

    # EMAs
    def simple_ema(data: list[float], period: int) -> float | None:
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = (price * multiplier) + (ema_val * (1 - multiplier))
        return ema_val

    indicators["ema_9"] = simple_ema(closes, 9)
    indicators["ema_21"] = simple_ema(closes, 21)
    indicators["ema_50"] = simple_ema(closes, 50)

    # SMA 200
    if len(closes) >= 200:
        indicators["sma_200"] = sum(closes[-200:]) / 200

    return indicators


# =============================================================================
# Validation Functions
# =============================================================================


def validate_indicator(name: str) -> bool:
    """Check if indicator name is valid."""
    return name in INDICATORS


def validate_condition(condition: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate a condition dict.

    Args:
        condition: Condition dict with 'indicator', 'min', 'max'

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(condition, dict):
        return False, "Condition must be a dict"

    indicator = condition.get("indicator")
    if not indicator:
        return False, "Missing 'indicator' field"

    if not validate_indicator(indicator):
        return False, f"Unknown indicator: {indicator}"

    min_val = condition.get("min")
    max_val = condition.get("max")

    if min_val is not None and max_val is not None:
        if min_val > max_val:
            return False, f"min ({min_val}) > max ({max_val})"

    return True, ""


def get_indicator_lookback(indicator: str) -> int:
    """Get required lookback period for an indicator."""
    return INDICATOR_LOOKBACK.get(indicator, 1)


def get_indicator_bounds(indicator: str) -> tuple[float, float]:
    """Get valid bounds for an indicator."""
    return INDICATOR_BOUNDS.get(indicator, (float("-inf"), float("inf")))


def has_sufficient_data(
    candle_count: int,
    indicators_needed: list[str],
) -> bool:
    """
    Check if we have enough candles for required indicators.

    Args:
        candle_count: Number of available candles
        indicators_needed: List of indicator names

    Returns:
        True if sufficient data
    """
    for indicator in indicators_needed:
        required = get_indicator_lookback(indicator)
        if candle_count < required:
            return False
    return True


# =============================================================================
# Performance Helpers
# =============================================================================


class IndicatorCache:
    """Cache for computed indicators to avoid recalculation."""

    def __init__(self):
        self._cache: dict[str, dict[str, float]] = {}

    def get(self, key: str) -> dict[str, float] | None:
        """Get cached indicators for a candle key."""
        return self._cache.get(key)

    def set(self, key: str, indicators: dict[str, float]) -> None:
        """Cache indicators for a candle key."""
        self._cache[key] = indicators

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


def match_patterns_batch(
    patterns: list[dict[str, Any]],
    indicators: dict[str, float],
) -> list[MatchResult]:
    """
    Match multiple patterns against the same indicators.

    Args:
        patterns: List of pattern dicts
        indicators: Dict of indicator values

    Returns:
        List of MatchResults
    """
    results = []
    for pattern in patterns:
        result = match_pattern(pattern, indicators)
        results.append(result)
    return results
