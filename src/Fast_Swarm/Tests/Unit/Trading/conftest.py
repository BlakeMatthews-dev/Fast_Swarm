"""
Shared fixtures for Trading unit tests.

Provides mock-based fixtures that do NOT require a real database connection.
DB-dependent tests should use the root conftest's db_session fixture and be
marked with @pytest.mark.requires_db.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)


# ============================================================================
# SERVICE FIXTURE
# ============================================================================


@pytest.fixture
def paper_trading_service() -> AgentPaperTradingService:
    """Fresh AgentPaperTradingService instance (no shared state)."""
    return AgentPaperTradingService()


# ============================================================================
# MOCK SESSION
# ============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """
    Mock AsyncSession that stubs out exec/commit/refresh/add.

    Tests that need to control query results should configure
    ``mock_session.exec.return_value.first.return_value`` before calling
    the service method.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    # Default: exec returns a result proxy whose .first() returns None
    result_proxy = MagicMock()
    result_proxy.first.return_value = None
    session.exec = AsyncMock(return_value=result_proxy)

    return session


# ============================================================================
# AGENT RECORD
# ============================================================================


def _make_agent(
    agent_id: str | None = None,
    name: str = "TestAgent",
    status: str = "active",
    assigned_patterns: dict | None = None,
    pattern_weights: dict | None = None,
    traits: dict | None = None,
) -> SimpleNamespace:
    """
    Build a lightweight agent-like object that quacks like Agent.

    Uses SimpleNamespace so we don't need actual SQLModel imports or a DB.
    """
    return SimpleNamespace(
        agent_id=agent_id or f"agent-{uuid.uuid4().hex[:8]}",
        name=name,
        status=status,
        assigned_patterns=assigned_patterns or {},
        pattern_weights=pattern_weights or {},
        traits=traits or {"kelly_fraction": 0.1},
    )


@pytest.fixture
def sample_agent_record() -> SimpleNamespace:
    """
    A sample agent record with one long pattern and one short pattern.

    Patterns have entry/exit conditions that can be evaluated by the
    mocked pattern_matcher.
    """
    return _make_agent(
        agent_id="agent-test-0001",
        name="PaperTrader",
        assigned_patterns={
            "pat-long-001": {
                "entry_conditions": {"indicator": "rsi_14", "operator": "<", "value": 30},
                "exit_conditions": {"indicator": "rsi_14", "operator": ">", "value": 70},
                "direction": "long",
            },
            "pat-short-001": {
                "entry_conditions": {"indicator": "rsi_14", "operator": ">", "value": 80},
                "exit_conditions": {"indicator": "rsi_14", "operator": "<", "value": 40},
                "direction": "short",
            },
        },
        pattern_weights={"pat-long-001": 1.0, "pat-short-001": 1.0},
        traits={"kelly_fraction": 0.1},
    )


@pytest.fixture
def make_agent():
    """Factory fixture — call ``make_agent(...)`` to build agents inline."""
    return _make_agent


# ============================================================================
# CANDLE DATA
# ============================================================================


@pytest.fixture
def sample_candle_data() -> dict:
    """Minimal candle data dict used by evaluate_and_trade."""
    return {
        "open": 50000.0,
        "high": 50500.0,
        "low": 49500.0,
        "close": 50100.0,
        "volume": 1234.5,
        "rsi_14": 45.0,
    }


# ============================================================================
# EVALUATE_CONDITIONS MOCK RESULT
# ============================================================================


def make_eval_result(matched: bool = False, confidence: float = 1.0):
    """Build a SimpleNamespace that mimics evaluate_conditions return value."""
    return SimpleNamespace(matched=matched, confidence=confidence)
