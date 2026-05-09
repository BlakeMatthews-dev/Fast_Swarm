"""
Seeded Random Number Generator - V3 Parity.

Uses Linear Congruential Generator (LCG) with glibc parameters:
- Multiplier: 1103515245
- Increment: 12345
- Modulus: 0x7FFFFFFF (2^31 - 1)

This ensures exact reproducibility across Python and TypeScript implementations.
"""

from collections.abc import Callable

# LCG Parameters (glibc compatible, V3 parity)
LCG_MULTIPLIER = 1103515245
LCG_INCREMENT = 12345
LCG_MODULUS = 0x7FFFFFFF  # 2^31 - 1


def seeded_random(seed: int) -> Callable[[], float]:
    """
    Create a seeded random number generator.

    Returns a function that produces deterministic pseudo-random
    floats in the range [0, 1).

    V3 Parity: Uses same LCG as TypeScript implementation.

    Args:
        seed: Integer seed for the generator.

    Returns:
        A callable that returns the next random float.

    Example:
        >>> rng = seeded_random(42)
        >>> rng()  # First random value
        0.xxx...
        >>> rng()  # Second random value
        0.yyy...
    """
    # Handle edge cases
    if seed < 0:
        seed = -seed  # Convert negative to positive

    # Initialize state with masked seed
    state = [seed & LCG_MODULUS]

    def next_random() -> float:
        """Generate next random float in [0, 1)."""
        # LCG formula: state = (state * a + c) mod m
        state[0] = (state[0] * LCG_MULTIPLIER + LCG_INCREMENT) & LCG_MODULUS
        # Return normalized float in [0, 1)
        return state[0] / LCG_MODULUS

    return next_random


def seeded_noise(seed: int, amplitude: float = 0.05) -> float:
    """
    Generate a single noise value in [-amplitude, +amplitude].

    Used for adding ±5% noise to derived traits.

    Args:
        seed: Integer seed for reproducibility.
        amplitude: Maximum deviation (default 0.05 = ±5%).

    Returns:
        Float in range [-amplitude, +amplitude].
    """
    rng = seeded_random(seed)
    # Generate value in [0, 1) and map to [-amplitude, +amplitude]
    raw = rng()
    return (raw * 2 - 1) * amplitude


def seeded_choice(items: list, seed: int):
    """
    Choose a random item from a list deterministically.

    Args:
        items: List of items to choose from.
        seed: Integer seed for reproducibility.

    Returns:
        One item from the list.

    Raises:
        ValueError: If items is empty.
    """
    if not items:
        raise ValueError("Cannot choose from empty list")

    rng = seeded_random(seed)
    index = int(rng() * len(items))
    # Ensure index is within bounds (rng() could theoretically be very close to 1)
    index = min(index, len(items) - 1)
    return items[index]


def seeded_shuffle(items: list, seed: int) -> list:
    """
    Shuffle a list deterministically (Fisher-Yates).

    Args:
        items: List to shuffle.
        seed: Integer seed for reproducibility.

    Returns:
        New shuffled list (does not modify original).
    """
    result = items.copy()
    rng = seeded_random(seed)

    # Fisher-Yates shuffle
    for i in range(len(result) - 1, 0, -1):
        j = int(rng() * (i + 1))
        result[i], result[j] = result[j], result[i]

    return result


def seeded_range(seed: int, min_val: float, max_val: float) -> float:
    """
    Generate a random float in [min_val, max_val).

    Args:
        seed: Integer seed for reproducibility.
        min_val: Minimum value (inclusive).
        max_val: Maximum value (exclusive).

    Returns:
        Float in range [min_val, max_val).
    """
    rng = seeded_random(seed)
    return min_val + rng() * (max_val - min_val)
