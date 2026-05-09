"""
Fast_Swarm Utilities Package

Ported and improved from Coinswarm-1/local-utilities with:
- Async-first design using existing Database sessions
- No SQLite - PostgreSQL only
- Integrated with Fast_Swarm patterns and models
- Cleaner error handling and logging
"""

from .pattern_backtest import (
    backtest_pattern_on_windows,
    calculate_metrics_for_trades,
    generate_random_windows,
)
from .pattern_discovery import (
    DiscoveryCycleResult,
    PatternDiscoveryScheduler,
)
from .pattern_priority import (
    Priority,
    get_prioritized_patterns,
    recalculate_all_priorities,
    update_priority_after_backtest,
)

__all__ = [
    # Priority
    "Priority",
    "get_prioritized_patterns",
    "update_priority_after_backtest",
    "recalculate_all_priorities",
    # Backtest
    "backtest_pattern_on_windows",
    "generate_random_windows",
    "calculate_metrics_for_trades",
    # Discovery
    "PatternDiscoveryScheduler",
    "DiscoveryCycleResult",
]
