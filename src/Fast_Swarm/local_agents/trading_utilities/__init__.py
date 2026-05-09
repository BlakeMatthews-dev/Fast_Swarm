"""
Trading utilities package - shared simulation and pattern matching.

This module provides the canonical implementation for trading simulations
that ALL callers should import from:
- Pattern backtests
- Agent backtests
- Live trading (future)

Single source of truth prevents divergence between implementations.
"""

from .pattern_matching import (
    # Trade dataclass
    Trade,
    calculate_condition_confidence,
    calculate_dynamic_trail_pct,
    calculate_entry_confidence,
    calculate_trailing_stop_price,
    # Exit logic
    check_ml_indicator_exits,
    classify_regime,
    # Helper functions
    extract_indicators,
    get_atr_multiplier_for_profit,
    parse_exit_conditions,
    # Core simulation
    run_simulation,
)

__all__ = [
    "Trade",
    "calculate_condition_confidence",
    "calculate_dynamic_trail_pct",
    "calculate_entry_confidence",
    "calculate_trailing_stop_price",
    "check_ml_indicator_exits",
    "classify_regime",
    "extract_indicators",
    "get_atr_multiplier_for_profit",
    "parse_exit_conditions",
    "run_simulation",
]
