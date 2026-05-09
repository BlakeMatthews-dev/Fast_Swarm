"""
Confidence Calculator Math.
Exact parity with `v3/cloudflare-agents/spawning/confidence-calculator.ts`.

Implements:
1. Steep Logarithmic Scaling for INSIDE threshold (0.1 -> 1.0)
2. Exponential Decay for OUTSIDE threshold (0.1 -> 0.0)

Operators:
- < / <= : Less than (value must be below threshold)
- > / >= : Greater than (value must be above threshold)
- == : Equals (value must be close to threshold)
- between : Range (value must be between two bounds)
- in : Discrete (value must be in a list)
"""

import math


def calculate_log_scaled_confidence(linear_position: float) -> float:
    """
    V3 Parity: Math.log1p(linearPosition * 999) / Math.log(1000)

    Maps a linear 0.0-1.0 compliance score to a steep log curve.
    - 0.0 (At threshold edge) -> 0.0 (will be shifted to 0.1 base)
    - 0.5 (Halfway) -> 0.9 (Very high confidence quickly)
    - 1.0 (Optimal/Center) -> 1.0
    """
    # Handle NaN and special values
    if not math.isfinite(linear_position):
        if math.isnan(linear_position):
            return 0.0
        if linear_position == float("inf"):
            return 1.0
        return 0.0  # -inf

    if linear_position <= 0:
        return 0.0
    if linear_position >= 1:
        return 1.0

    return math.log1p(linear_position * 999) / math.log(1000)


def evaluate_condition_confidence(
    operator: str, value: float, threshold: float, indicator_min: float, indicator_max: float
) -> float:
    """
    Evaluates a single condition and returns 0.0-1.0 confidence.

    Parity with V3 `evaluateConditionConfidence`.
    """
    if not math.isfinite(value):
        return 0.0

    # === LESS THAN (< or <=) ===
    if operator in ["<", "<="]:
        inclusive = operator == "<="

        # INSIDE (Success)
        if value <= threshold if inclusive else value < threshold:
            # If deeply inside (near min), confidence is high.
            # If near threshold, confidence is low (0.1).

            range_span = threshold - indicator_min
            if range_span <= 0:
                return 1.0  # Edge case

            distance_from_min = value - indicator_min
            # Linear position: 1.0 at min (best), 0.0 at threshold (worst)
            linear_position = 1.0 - max(0.0, min(1.0, distance_from_min / range_span))

            # Apply steep log scaling + Base 0.1
            log_scaled = calculate_log_scaled_confidence(linear_position)
            return 0.1 + (log_scaled * 0.9)

        # OUTSIDE (Fail) - Decay
        else:
            distance_outside = value - threshold
            max_distance = indicator_max - threshold
            if max_distance <= 0:
                return 0.0

            decay_ratio = min(1.0, distance_outside / max_distance)
            # V3: 0.1 * (0.001 ^ decay_ratio)
            return 0.1 * pow(0.001, decay_ratio)

    # === GREATER THAN (> or >=) ===
    elif operator in [">", ">="]:
        inclusive = operator == ">="

        # INSIDE (Success)
        if value >= threshold if inclusive else value > threshold:
            range_span = indicator_max - threshold
            if range_span <= 0:
                return 1.0

            distance_from_threshold = value - threshold
            # Linear position: 0.0 at threshold (worst), 1.0 at max (best)
            linear_position = max(0.0, min(1.0, distance_from_threshold / range_span))

            log_scaled = calculate_log_scaled_confidence(linear_position)
            return 0.1 + (log_scaled * 0.9)

        # OUTSIDE (Fail)
        else:
            distance_outside = threshold - value
            max_distance = threshold - indicator_min
            if max_distance <= 0:
                return 0.0

            decay_ratio = min(1.0, distance_outside / max_distance)
            return 0.1 * pow(0.001, decay_ratio)

    # === EQUALS (==) ===
    elif operator == "==":
        if abs(value - threshold) < 0.00001:
            return 1.0

        # V3 Logic: 5% of range is "Close Enough" (0.5 - 1.0)
        total_range = indicator_max - indicator_min
        close_enough = total_range * 0.05

        distance = abs(value - threshold)

        if distance <= close_enough:
            linear_pos = 1.0 - (distance / close_enough)
            return 0.5 + (linear_pos * 0.5)
        else:
            # Decay quickly
            decay_ratio = min(1.0, distance / (total_range * 0.1))
            return 0.5 * pow(0.01, decay_ratio)

    # === BETWEEN (range) ===
    elif operator == "between":
        # threshold is a tuple (low, high)
        if not isinstance(threshold, (tuple, list)) or len(threshold) != 2:
            return None

        low, high = threshold
        # Normalize if inverted
        if low > high:
            low, high = high, low

        # Zero-width range (exact match)
        if low == high:
            if abs(value - low) < 0.00001:
                return 1.0
            else:
                # Decay based on distance
                distance = abs(value - low)
                max_distance = max(high - indicator_min, indicator_max - low)
                if max_distance <= 0:
                    return None
                decay_ratio = min(1.0, distance / max_distance)
                return 0.1 * pow(0.001, decay_ratio)

        # INSIDE (Success) - center-based confidence
        if low <= value <= high:
            center = (low + high) / 2
            half_range = (high - low) / 2
            distance_from_center = abs(value - center)
            # Linear position: 1.0 at center, 0.0 at edge
            linear_position = 1.0 - (distance_from_center / half_range)
            linear_position = max(0.0, min(1.0, linear_position))

            log_scaled = calculate_log_scaled_confidence(linear_position)
            return 0.1 + (log_scaled * 0.9)

        # OUTSIDE (Fail) - Decay
        else:
            if value < low:
                distance_outside = low - value
                max_distance = low - indicator_min
            else:
                distance_outside = value - high
                max_distance = indicator_max - high

            if max_distance <= 0:
                return None

            decay_ratio = min(1.0, distance_outside / max_distance)
            result = 0.1 * pow(0.001, decay_ratio)
            return result if result >= 0.01 else None

    # === IN (discrete values) ===
    elif operator == "in":
        # threshold is a list of valid values
        if not isinstance(threshold, (list, tuple)):
            return None
        if len(threshold) == 0:
            return None

        if value in threshold:
            return 1.0
        else:
            return None

    return None


def evaluate_pattern_confidence(
    conditions: dict[str, dict], indicators: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> dict | None:
    """
    Evaluate a multi-condition pattern against current indicators.

    Args:
        conditions: Dict of indicator -> {operator, value} conditions
        indicators: Current indicator values
        bounds: Indicator bounds as {indicator: (min, max)}

    Returns:
        Dict with 'overall_confidence' and per-condition breakdown,
        or None if pattern fails (missing indicator or any condition returns None).

    Example:
        >>> conditions = {'rsi14': {'operator': '<', 'value': 30}}
        >>> indicators = {'rsi14': 25}
        >>> bounds = {'rsi14': (0, 100)}
        >>> result = evaluate_pattern_confidence(conditions, indicators, bounds)
        >>> result['overall_confidence']
        0.85
    """
    if not conditions:
        return None

    confidences = {}
    for indicator, condition in conditions.items():
        # Check if indicator exists
        if indicator not in indicators:
            return None

        value = indicators[indicator]
        operator = condition.get("operator", "<")
        threshold = condition.get("value")

        # Get bounds for this indicator
        indicator_bounds = bounds.get(indicator, (0, 100))
        indicator_min, indicator_max = indicator_bounds

        # Evaluate condition
        conf = evaluate_condition_confidence(operator, value, threshold, indicator_min, indicator_max)

        # If any condition returns None (far outside), pattern fails
        if conf is None:
            return None

        confidences[indicator] = conf

    # Calculate average confidence
    if len(confidences) == 0:
        return None

    overall = sum(confidences.values()) / len(confidences)

    return {"overall_confidence": overall, "per_condition": confidences}


def truncate_confidence(confidence: float) -> float | None:
    """
    Truncate confidence to 2 decimal places.
    Returns None if below threshold (0.01).
    """
    if confidence is None:
        return None
    if confidence < 0.01:
        return None
    # Truncate (floor) to 2 decimals
    return math.floor(confidence * 100) / 100
