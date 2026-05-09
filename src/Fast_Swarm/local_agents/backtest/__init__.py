"""
Local Backtest Package for Agent Evolution.

Provides the backtest engine that connects agents to real OHLCV data.
"""

from Fast_Swarm.local_agents.backtest.data import Candle, OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import (
    ASSET_TIERS,
    TRADING_COSTS,
    BacktestConfig,
    LocalBacktestEngine,
    calculate_mfe_mae,
    get_asset_tier,
    get_trading_costs_pct,
)
from Fast_Swarm.local_agents.backtest.pattern_matcher import (
    INDICATOR_ALIASES,
    INDICATOR_BOUNDS,
    PatternMatcher,
    evaluate_conditions,
)

__all__ = [
    "ASSET_TIERS",
    "INDICATOR_ALIASES",
    "INDICATOR_BOUNDS",
    "TRADING_COSTS",
    "BacktestConfig",
    "Candle",
    "LocalBacktestEngine",
    "OHLCVLoader",
    "PatternMatcher",
    "calculate_mfe_mae",
    "evaluate_conditions",
    "get_asset_tier",
    "get_trading_costs_pct",
]
