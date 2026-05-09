"""
Normalization Functions.

Three curve types for converting raw metrics to scores:
1. Sigmoid: smooth S-curve for bounded values (win rate, calibration)
2. Logarithmic penalty: penalizes bad values heavily (drawdown)
3. Diminishing returns: rewards improvement less at high end (Sortino)
"""

import math


def sigmoid_normalize(value: float, center: float = 0.5, steepness: float = 10.0) -> float:
    """
    Sigmoid normalization: smooth S-curve mapping to [0, 1].

    Args:
        value: Input value.
        center: Value that maps to 0.5.
        steepness: Controls transition sharpness. Higher = sharper.

    Returns:
        Normalized value in [0, 1].
    """
    x = steepness * (value - center)

    # Prevent overflow
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0

    return 1.0 / (1.0 + math.exp(-x))


def logarithmic_penalty(value: float, max_val: float = 50.0) -> float:
    """
    Logarithmic penalty: penalizes bad values heavily.

    Used for drawdown-like metrics where the first few percent
    matter much more than later ones.

    score = 1 - log(1 + value) / log(1 + max_val)

    Args:
        value: Input value (0 to max_val). Higher = worse.
        max_val: Maximum expected value.

    Returns:
        Score in [0, 1]. 0 at max_val, 1 at 0.
    """
    if value <= 0:
        return 1.0
    if value >= max_val:
        return 0.0

    # log(1 + x) / log(1 + max) gives [0, 1] for [0, max]
    # Invert so lower drawdown = higher score
    log_ratio = math.log1p(value) / math.log1p(max_val)
    return max(0.0, min(1.0, 1.0 - log_ratio))


def diminishing_returns(value: float, saturation: float = 4.0) -> float:
    """
    Diminishing returns: rewards improvement less at high end.

    Uses 1 - exp(-value/saturation) curve.
    At saturation value, score is ~0.63 (1 - 1/e).

    Args:
        value: Input value (>= 0). Higher = better.
        saturation: Value at which ~63% of maximum score is reached.

    Returns:
        Score in [0, 1). Asymptotically approaches 1.
    """
    if value <= 0:
        return 0.0
    if saturation <= 0:
        return 0.0

    return 1.0 - math.exp(-value / saturation)
