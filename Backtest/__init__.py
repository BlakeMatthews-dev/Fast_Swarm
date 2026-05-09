"""
Fast_Swarm Backtest Module.

Provides backtesting capabilities for pattern and agent evaluation.
"""

from .Models.backtest_models import (
    BacktestConfig,
    BacktestResult,
    ExitStrategy,
    TradeRecord,
)
from .Services.backtest_service import (
    calculate_backtest_metrics,
    calculate_mfe_mae,
    run_backtest,
)

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "ExitStrategy",
    "TradeRecord",
    "calculate_backtest_metrics",
    "calculate_mfe_mae",
    "run_backtest",
]
