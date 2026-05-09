"""
Trait Service for Fast_Swarm.

Provides trait generation, mutation, crossover, and validation.
All traits are float values in [0.0, 1.0].
"""

import math
import random
from typing import Any

from .agent_service import calculate_derived_traits

# =============================================================================
# Constants - 22 Trait Definitions
# =============================================================================

CORE_RISK_TRAITS = [
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
]

PATTERN_SELECTION_TRAITS = [
    "win_rate_preference",
    "momentum_vs_reversion",
]

EXECUTION_TRAITS = [
    "entry_aggression",
]

TECHNICAL_TRAITS = [
    "lookback_preference",
]

SENTIMENT_TRAITS = [
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
]

MACRO_TRAITS = [
    "funding_rate_sensitivity",
    "correlation_awareness",
]

DERIVED_TRAITS = [
    "drawdown_sensitivity",
    "stop_loss_tightness",
    "exit_aggression",
]

# Additional traits to reach 22
ADDITIONAL_TRAITS = [
    "patience",
    "adaptability",
    "trend_following",
    "mean_reversion",
    "breakout_preference",
    "volume_sensitivity",
]

# All 22 traits
ALL_22_TRAITS = (
    CORE_RISK_TRAITS
    + PATTERN_SELECTION_TRAITS
    + EXECUTION_TRAITS
    + TECHNICAL_TRAITS
    + SENTIMENT_TRAITS
    + MACRO_TRAITS
    + DERIVED_TRAITS
    + ADDITIONAL_TRAITS
)

# Base traits (not derived)
BASE_TRAITS = [t for t in ALL_22_TRAITS if t not in DERIVED_TRAITS]


# =============================================================================
# Trait Validation
# =============================================================================


def validate_trait_value(value: Any) -> tuple[bool, str]:
    """
    Validate a single trait value.

    Args:
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        return False, "Trait value cannot be None"

    if not isinstance(value, (int, float)):
        return False, f"Trait value must be numeric, got {type(value).__name__}"

    if math.isnan(value):
        return False, "Trait value cannot be NaN"

    if math.isinf(value):
        return False, "Trait value cannot be Infinity"

    if value < 0.0 or value > 1.0:
        return False, f"Trait value must be in [0.0, 1.0], got {value}"

    return True, ""


def validate_all_traits(traits: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate all 22 traits are present and valid.

    Args:
        traits: Dictionary of trait values

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(traits, dict):
        return False, "Traits must be a dictionary"

    for trait_name in ALL_22_TRAITS:
        if trait_name not in traits:
            return False, f"Missing required trait: {trait_name}"

        value = traits[trait_name]
        is_valid, error = validate_trait_value(value)
        if not is_valid:
            return False, f"Trait {trait_name}: {error}"

    return True, ""


# =============================================================================
# Trait Generation
# =============================================================================


def generate_base_traits(seed: int | None = None) -> dict[str, float]:
    """
    Generate random values for base traits (non-derived).

    Args:
        seed: Optional random seed for determinism

    Returns:
        Dictionary of base trait values
    """
    if seed is not None:
        random.seed(seed)

    traits = {}
    for trait_name in BASE_TRAITS:
        traits[trait_name] = random.random()

    return traits


def generate_all_traits(seed: int | None = None) -> dict[str, float]:
    """
    Generate all 22 traits with proper derivation.

    Args:
        seed: Optional random seed for determinism

    Returns:
        Dictionary with all 22 traits
    """
    base_traits = generate_base_traits(seed)

    # Use calculate_derived_traits to add derived traits
    # Need to temporarily set seed for the noise in derived traits
    if seed is not None:
        random.seed(seed + 1000)  # Different seed for derived noise

    all_traits = calculate_derived_traits(base_traits)

    # Ensure all 22 traits are present
    for trait_name in ALL_22_TRAITS:
        if trait_name not in all_traits:
            all_traits[trait_name] = 0.5  # Default

    return all_traits


# =============================================================================
# Trait Mutation
# =============================================================================


def mutate_trait(
    value: float,
    mutation_rate: float = 0.10,
    seed: int | None = None,
) -> float:
    """
    Mutate a single trait value by ±mutation_rate.

    Args:
        value: Current trait value
        mutation_rate: Maximum mutation (default 0.10 = ±10%)
        seed: Optional random seed

    Returns:
        Mutated value, clamped to [0.0, 1.0]
    """
    if seed is not None:
        random.seed(seed)

    mutation = random.uniform(-mutation_rate, mutation_rate)
    new_value = value + mutation

    # Clamp to bounds
    return max(0.0, min(1.0, new_value))


def mutate_traits(
    traits: dict[str, float],
    mutation_rate: float = 0.10,
    seed: int | None = None,
) -> dict[str, float]:
    """
    Mutate all traits by ±mutation_rate.

    Args:
        traits: Dictionary of trait values
        mutation_rate: Maximum mutation (default 0.10 = ±10%)
        seed: Optional random seed

    Returns:
        Dictionary of mutated traits
    """
    if seed is not None:
        random.seed(seed)

    mutated = {}
    for trait_name, value in traits.items():
        if trait_name in DERIVED_TRAITS:
            # Skip derived traits, recalculate after
            continue

        mutation = random.uniform(-mutation_rate, mutation_rate)
        mutated[trait_name] = max(0.0, min(1.0, value + mutation))

    # Recalculate derived traits from mutated base traits
    return calculate_derived_traits(mutated)


# =============================================================================
# Trait Crossover
# =============================================================================


def crossover_traits(
    parent_a: dict[str, float],
    parent_b: dict[str, float],
    seed: int | None = None,
) -> dict[str, float]:
    """
    Create child traits by averaging parent traits.

    Args:
        parent_a: First parent's traits
        parent_b: Second parent's traits
        seed: Optional random seed (not used in basic averaging)

    Returns:
        Child traits (average of parents)
    """
    child = {}

    for trait_name in BASE_TRAITS:
        val_a = parent_a.get(trait_name, 0.5)
        val_b = parent_b.get(trait_name, 0.5)
        child[trait_name] = (val_a + val_b) / 2.0

    # Recalculate derived traits
    if seed is not None:
        random.seed(seed)

    return calculate_derived_traits(child)


def crossover_and_mutate(
    parent_a: dict[str, float],
    parent_b: dict[str, float],
    mutation_rate: float = 0.10,
    seed: int | None = None,
) -> dict[str, float]:
    """
    Create child by crossover then mutation.

    Args:
        parent_a: First parent's traits
        parent_b: Second parent's traits
        mutation_rate: Mutation rate after crossover
        seed: Optional random seed

    Returns:
        Child traits (crossed over and mutated)
    """
    child = crossover_traits(parent_a, parent_b, seed)
    return mutate_traits(child, mutation_rate, seed)


# =============================================================================
# Trait Utilities
# =============================================================================


def fill_missing_traits(
    partial_traits: dict[str, float],
    seed: int | None = None,
) -> dict[str, float]:
    """
    Fill in missing traits with random values.

    Args:
        partial_traits: Dictionary with some traits
        seed: Optional random seed for filling

    Returns:
        Complete dictionary with all 22 traits
    """
    if seed is not None:
        random.seed(seed)

    complete = partial_traits.copy()

    for trait_name in BASE_TRAITS:
        if trait_name not in complete:
            complete[trait_name] = random.random()

    # Add derived traits
    return calculate_derived_traits(complete)


def clamp_traits(traits: dict[str, float]) -> dict[str, float]:
    """
    Clamp all trait values to [0.0, 1.0].

    Args:
        traits: Dictionary of trait values

    Returns:
        Dictionary with clamped values
    """
    return {name: max(0.0, min(1.0, float(value))) for name, value in traits.items()}


def traits_are_equal(
    traits_a: dict[str, float],
    traits_b: dict[str, float],
    tolerance: float = 1e-9,
) -> bool:
    """
    Check if two trait dictionaries are equal within tolerance.

    Args:
        traits_a: First traits dict
        traits_b: Second traits dict
        tolerance: Numeric tolerance for comparison

    Returns:
        True if all traits match within tolerance
    """
    for trait_name in ALL_22_TRAITS:
        val_a = traits_a.get(trait_name, 0.0)
        val_b = traits_b.get(trait_name, 0.0)
        if abs(val_a - val_b) > tolerance:
            return False
    return True
