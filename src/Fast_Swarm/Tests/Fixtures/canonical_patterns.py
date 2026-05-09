"""
Canonical Patterns - FROZEN TEST PATTERNS

MASTER TEST ADMIN DECREE: These patterns are IMMUTABLE.
They define the exact trading patterns used for regression/snapshot testing.
Changing these invalidates all golden files.

Usage:
    from Tests.Fixtures.canonical_patterns import CANONICAL_PATTERNS
    pattern = CANONICAL_PATTERNS["rsi_oversold"]
"""

from typing import Any

# =============================================================================
# CANONICAL PATTERNS - DO NOT MODIFY WITHOUT UPDATING GOLDEN FILES
# =============================================================================

CANONICAL_PATTERNS: dict[str, dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # RSI Patterns
    # -------------------------------------------------------------------------
    "rsi_oversold": {
        "pattern_id": "canonical-rsi-oversold",
        "name": "RSI Oversold",
        "entry_conditions": {
            "indicator": "rsi_14",
            "operator": "<",
            "value": 30,
        },
        "exit_conditions": {
            "indicator": "rsi_14",
            "operator": ">",
            "value": 70,
        },
        "direction": "long",
        "description": "Buy when RSI < 30, sell when RSI > 70",
        "timeframes": ["1h", "4h", "1d"],
    },
    "rsi_overbought": {
        "pattern_id": "canonical-rsi-overbought",
        "name": "RSI Overbought",
        "entry_conditions": {
            "indicator": "rsi_14",
            "operator": ">",
            "value": 70,
        },
        "exit_conditions": {
            "indicator": "rsi_14",
            "operator": "<",
            "value": 30,
        },
        "direction": "short",
        "description": "Short when RSI > 70, cover when RSI < 30",
        "timeframes": ["1h", "4h", "1d"],
    },
    # -------------------------------------------------------------------------
    # MACD Patterns
    # -------------------------------------------------------------------------
    "macd_bullish_cross": {
        "pattern_id": "canonical-macd-bullish-cross",
        "name": "MACD Bullish Cross",
        "entry_conditions": {
            "indicator": "macd_histogram",
            "operator": ">",
            "value": 0,
            "crossover": True,
        },
        "exit_conditions": {
            "indicator": "macd_histogram",
            "operator": "<",
            "value": 0,
        },
        "direction": "long",
        "description": "Buy on MACD bullish cross, exit on bearish cross",
        "timeframes": ["1h", "4h"],
    },
    "macd_bearish_cross": {
        "pattern_id": "canonical-macd-bearish-cross",
        "name": "MACD Bearish Cross",
        "entry_conditions": {
            "indicator": "macd_histogram",
            "operator": "<",
            "value": 0,
            "crossover": True,
        },
        "exit_conditions": {
            "indicator": "macd_histogram",
            "operator": ">",
            "value": 0,
        },
        "direction": "short",
        "description": "Short on MACD bearish cross, cover on bullish cross",
        "timeframes": ["1h", "4h"],
    },
    # -------------------------------------------------------------------------
    # Bollinger Band Patterns
    # -------------------------------------------------------------------------
    "bb_squeeze": {
        "pattern_id": "canonical-bb-squeeze",
        "name": "Bollinger Band Squeeze",
        "entry_conditions": {
            "indicator": "bb_width",
            "operator": "<",
            "value": 0.05,
        },
        "exit_conditions": {
            "indicator": "bb_width",
            "operator": ">",
            "value": 0.15,
        },
        "direction": "long",
        "description": "Enter on low volatility squeeze, exit on expansion",
        "timeframes": ["1h", "4h"],
    },
    "bb_lower_touch": {
        "pattern_id": "canonical-bb-lower-touch",
        "name": "BB Lower Band Touch",
        "entry_conditions": {
            "indicator": "price_vs_bb_lower",
            "operator": "<=",
            "value": 1.0,  # Price at or below lower band
        },
        "exit_conditions": {
            "indicator": "price_vs_bb_middle",
            "operator": ">=",
            "value": 1.0,  # Price at or above middle band
        },
        "direction": "long",
        "description": "Buy at lower band, sell at middle band",
        "timeframes": ["1h", "4h"],
    },
    # -------------------------------------------------------------------------
    # Moving Average Patterns
    # -------------------------------------------------------------------------
    "golden_cross": {
        "pattern_id": "canonical-golden-cross",
        "name": "Golden Cross",
        "entry_conditions": {
            "indicator": "sma_50_vs_200",
            "operator": ">",
            "value": 1.0,
            "crossover": True,
        },
        "exit_conditions": {
            "indicator": "sma_50_vs_200",
            "operator": "<",
            "value": 1.0,
        },
        "direction": "long",
        "description": "Buy when 50 SMA crosses above 200 SMA",
        "timeframes": ["1d"],
    },
    "death_cross": {
        "pattern_id": "canonical-death-cross",
        "name": "Death Cross",
        "entry_conditions": {
            "indicator": "sma_50_vs_200",
            "operator": "<",
            "value": 1.0,
            "crossover": True,
        },
        "exit_conditions": {
            "indicator": "sma_50_vs_200",
            "operator": ">",
            "value": 1.0,
        },
        "direction": "short",
        "description": "Short when 50 SMA crosses below 200 SMA",
        "timeframes": ["1d"],
    },
    # -------------------------------------------------------------------------
    # Volume Patterns
    # -------------------------------------------------------------------------
    "volume_breakout": {
        "pattern_id": "canonical-volume-breakout",
        "name": "Volume Breakout",
        "entry_conditions": {
            "indicator": "volume_vs_avg",
            "operator": ">",
            "value": 2.0,  # 2x average volume
            "price_condition": {
                "indicator": "price_vs_high_20",
                "operator": ">",
                "value": 1.0,
            },
        },
        "exit_conditions": {
            "indicator": "trailing_stop",
            "value": 0.05,  # 5% trailing stop
        },
        "direction": "long",
        "description": "Buy on high volume breakout above 20-day high",
        "timeframes": ["1h", "4h"],
    },
    # -------------------------------------------------------------------------
    # Momentum Patterns
    # -------------------------------------------------------------------------
    "momentum_surge": {
        "pattern_id": "canonical-momentum-surge",
        "name": "Momentum Surge",
        "entry_conditions": {
            "indicator": "roc_10",  # 10-period rate of change
            "operator": ">",
            "value": 5.0,  # 5% momentum
        },
        "exit_conditions": {
            "indicator": "roc_10",
            "operator": "<",
            "value": 0,
        },
        "direction": "long",
        "description": "Buy on strong momentum, exit on momentum loss",
        "timeframes": ["1h", "4h"],
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_pattern(name: str) -> dict[str, Any]:
    """Get a canonical pattern by name."""
    if name not in CANONICAL_PATTERNS:
        available = ", ".join(CANONICAL_PATTERNS.keys())
        raise ValueError(f"Unknown pattern '{name}'. Available: {available}")
    # Return a copy to prevent modification
    return dict(CANONICAL_PATTERNS[name])


def get_long_patterns() -> dict[str, dict[str, Any]]:
    """Get all long-only patterns."""
    return {k: dict(v) for k, v in CANONICAL_PATTERNS.items() if v["direction"] == "long"}


def get_short_patterns() -> dict[str, dict[str, Any]]:
    """Get all short-only patterns."""
    return {k: dict(v) for k, v in CANONICAL_PATTERNS.items() if v["direction"] == "short"}


def get_patterns_for_timeframe(timeframe: str) -> dict[str, dict[str, Any]]:
    """Get patterns suitable for a specific timeframe."""
    return {k: dict(v) for k, v in CANONICAL_PATTERNS.items() if timeframe in v.get("timeframes", [])}


def get_all_pattern_names() -> list:
    """Get list of all canonical pattern names."""
    return list(CANONICAL_PATTERNS.keys())


# =============================================================================
# PATTERN COMBINATIONS FOR TESTING
# =============================================================================

PATTERN_COMBINATIONS = {
    "rsi_macd_combo": ["rsi_oversold", "macd_bullish_cross"],
    "mean_reversion_suite": ["rsi_oversold", "bb_lower_touch"],
    "trend_following_suite": ["golden_cross", "momentum_surge", "volume_breakout"],
    "full_arsenal": list(CANONICAL_PATTERNS.keys()),
}


def get_pattern_combination(name: str) -> list:
    """Get a predefined pattern combination."""
    if name not in PATTERN_COMBINATIONS:
        available = ", ".join(PATTERN_COMBINATIONS.keys())
        raise ValueError(f"Unknown combination '{name}'. Available: {available}")
    return [get_pattern(p) for p in PATTERN_COMBINATIONS[name]]
