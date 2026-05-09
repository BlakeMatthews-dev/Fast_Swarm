# Tests/Fixtures - Test data factories and fixtures
#
# Usage:
#   from Tests.Fixtures import TradeFactory, AgentFactory, PatternFactory
#   from Tests.Fixtures import CANONICAL_AGENTS, CANONICAL_PATTERNS, CANONICAL_WINDOWS

from Tests.Fixtures.canonical_agents import CANONICAL_AGENTS, get_agent
from Tests.Fixtures.canonical_patterns import CANONICAL_PATTERNS, get_pattern
from Tests.Fixtures.canonical_windows import CANONICAL_WINDOWS, get_window
from Tests.Fixtures.factories import AgentFactory, PatternFactory, TradeFactory

__all__ = [
    # Factories
    "TradeFactory",
    "AgentFactory",
    "PatternFactory",
    # Canonical data
    "CANONICAL_AGENTS",
    "CANONICAL_PATTERNS",
    "CANONICAL_WINDOWS",
    # Helpers
    "get_agent",
    "get_pattern",
    "get_window",
]
