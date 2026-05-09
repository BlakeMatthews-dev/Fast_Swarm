"""
Pytest Configuration - Fast_Swarm Test Suite

Shared fixtures and configuration for all tests.
Uses PostgreSQL with transaction rollback for test isolation.

Note: Fast_Swarm is installed in editable mode (pip install -e .)
so imports like `from Fast_Swarm.Agents...` work automatically.
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Set test database URL - uses same PostgreSQL, different schema or rollback
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "coinswarm")
os.environ.setdefault("POSTGRES_PASSWORD", "coinswarm_dev_2024")
os.environ.setdefault("POSTGRES_DB", "coinswarm")


# ============================================================================
# DATABASE FIXTURES - PostgreSQL with Transaction Rollback
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a database session with transaction rollback.

    Each test runs in a transaction that gets rolled back,
    ensuring test isolation without polluting the database.
    """
    db_url = (
        f"postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}"
        f"/{os.environ['POSTGRES_DB']}"
    )
    engine = create_async_engine(db_url, echo=False, future=True)

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session, session.begin():
        yield session
            # Rollback happens automatically when context exits

    await engine.dispose()


# ============================================================================
# AGENT FIXTURES
# ============================================================================


def generate_test_agent_id() -> str:
    """Generate a unique test agent ID."""
    return f"test-agent-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_traits() -> dict[str, float]:
    """
    Complete 22-trait genome with valid values [0.0, 1.0].

    From Master_plan.md:
    - Core Risk (1-4): risk_tolerance, hold_duration_bias, volatility_seeking, profit_target_greed
    - Pattern Selection (5-7): win_rate_preference, drawdown_sensitivity, momentum_vs_reversion
    - Trade Execution (8-10): stop_loss_tightness, entry_aggression, exit_aggression
    - Technical (11): lookback_preference
    - Sentiment (12-14): sentiment_weight, news_reactivity, sentiment_contrarian
    - Macro (15-16): funding_rate_sensitivity, correlation_awareness
    - Additional (17-22): patience, adaptability, trend_following, mean_reversion, breakout_preference, volume_sensitivity
    """
    return {
        # Core Risk (1-4)
        "risk_tolerance": 0.5,
        "hold_duration_bias": 0.5,
        "volatility_seeking": 0.5,
        "profit_target_greed": 0.5,
        # Pattern Selection (5-7)
        "win_rate_preference": 0.5,
        "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5,
        # Trade Execution (8-10)
        "stop_loss_tightness": 0.5,
        "entry_aggression": 0.5,
        "exit_aggression": 0.5,
        # Technical (11)
        "lookback_preference": 0.5,
        # Sentiment (12-14)
        "sentiment_weight": 0.5,
        "news_reactivity": 0.5,
        "sentiment_contrarian": 0.5,
        # Macro (15-16)
        "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5,
        # Additional (17-22)
        "patience": 0.5,
        "adaptability": 0.5,
        "trend_following": 0.5,
        "mean_reversion": 0.5,
        "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


@pytest.fixture
def sample_agent_data(sample_traits: dict[str, float]) -> dict[str, Any]:
    """Sample agent data for creation tests."""
    return {
        "agent_id": generate_test_agent_id(),
        "name": "Test Agent",
        "generation": 1,
        "traits": sample_traits,
        "status": "active",
        "is_active": True,
        "fitness_score": 0.0,
        "elo_rating": 1500.0,
    }


@pytest_asyncio.fixture
async def sample_agent(db_session: AsyncSession, sample_agent_data: dict[str, Any]):
    """Create and return a sample agent in the database."""
    from Fast_Swarm.Agents.Models.agent_models import Agent

    agent = Agent(**sample_agent_data)
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def multiple_agents(db_session: AsyncSession, sample_traits: dict[str, float]) -> list:
    """Create multiple agents for list/filter tests."""
    from Fast_Swarm.Agents.Models.agent_models import Agent

    agents = []
    for i in range(5):
        agent = Agent(
            agent_id=generate_test_agent_id(),
            name=f"Test Agent {i}",
            generation=i % 3 + 1,
            traits=sample_traits,
            status="active" if i < 3 else "retired",
            is_active=i < 3,
            fitness_score=float(i * 20),
            elo_rating=1500.0 + i * 100,
        )
        db_session.add(agent)
        agents.append(agent)

    await db_session.flush()
    for agent in agents:
        await db_session.refresh(agent)

    return agents


# ============================================================================
# PATTERN FIXTURES
# ============================================================================


@pytest.fixture
def sample_conditions() -> list[dict[str, Any]]:
    """Sample pattern entry conditions."""
    return [
        {"indicator": "rsi", "operator": "<", "value": 30},
        {"indicator": "volume_ratio", "operator": ">", "value": 1.5},
    ]


@pytest.fixture
def sample_exit_conditions() -> list[dict[str, Any]]:
    """Sample pattern exit conditions."""
    return [
        {"indicator": "rsi", "operator": ">", "value": 70},
        {"indicator": "pnl_pct", "operator": ">", "value": 5.0},
    ]


@pytest.fixture
def sample_pattern_data(sample_conditions, sample_exit_conditions) -> dict[str, Any]:
    """Sample pattern data for creation tests."""
    return {
        "pattern_id": f"test-pattern-{uuid.uuid4().hex[:8]}",
        "name": "Test RSI Oversold",
        "entry_conditions": sample_conditions,
        "exit_conditions": sample_exit_conditions,
        "origin": "TECHNICAL",
        "tier": 3,
        "fitness_score": 0.0,
        "is_active": True,
    }


# ============================================================================
# TRADE FIXTURES
# ============================================================================


@pytest.fixture
def sample_trade_data() -> dict[str, Any]:
    """Sample trade data."""
    return {
        "trade_id": f"test-trade-{uuid.uuid4().hex[:8]}",
        "agent_id": None,  # Set by test
        "pattern_id": None,  # Set by test
        "asset": "BTC/USDT",
        "direction": "LONG",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "size": 0.1,
        "pnl": 100.0,
        "pnl_pct": 2.0,
        "entry_time": datetime.utcnow(),
        "exit_time": datetime.utcnow(),
    }


@pytest.fixture
def sample_trades_data() -> list[dict[str, Any]]:
    """Multiple sample trades for batch tests."""
    base_time = datetime.utcnow()
    trades = []
    for i in range(10):
        trades.append(
            {
                "trade_id": f"test-trade-{uuid.uuid4().hex[:8]}",
                "asset": "BTC/USDT" if i % 2 == 0 else "ETH/USDT",
                "direction": "LONG" if i % 3 != 0 else "SHORT",
                "entry_price": 50000.0 + i * 100,
                "exit_price": 50000.0 + i * 100 + (50 if i % 2 == 0 else -30),
                "size": 0.1,
                "pnl": 50.0 if i % 2 == 0 else -30.0,
                "pnl_pct": 1.0 if i % 2 == 0 else -0.6,
            }
        )
    return trades


# ============================================================================
# OHLCV FIXTURES
# ============================================================================


@pytest.fixture
def sample_candles() -> list[dict[str, Any]]:
    """Sample OHLCV candles for backtest tests."""
    base_time = 1704067200000  # 2024-01-01 00:00:00 UTC
    candles = []
    price = 42000.0

    for i in range(100):
        # Simulate price movement
        change = (i % 7 - 3) * 50  # -150 to +150
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + abs(change) * 0.2
        low_price = min(open_price, close_price) - abs(change) * 0.2

        candles.append(
            {
                "timestamp": base_time + i * 3600000,  # 1 hour intervals
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 1000.0 + i * 10,
            }
        )
        price = close_price

    return candles


# ============================================================================
# MEMORY FIXTURES
# ============================================================================


@pytest.fixture
def sample_episodic_memory() -> dict[str, Any]:
    """Sample episodic memory entry."""
    return {
        "memory_id": f"mem-{uuid.uuid4().hex[:8]}",
        "agent_id": None,  # Set by test
        "memory_type": "episodic",
        "content": {
            "trade_id": "trade-123",
            "outcome": "win",
            "lesson": "RSI oversold works in ranging markets",
        },
        "weight": 0.8,
        "created_at": datetime.utcnow(),
    }


@pytest.fixture
def sample_semantic_memory() -> dict[str, Any]:
    """Sample semantic memory entry."""
    return {
        "memory_id": f"mem-{uuid.uuid4().hex[:8]}",
        "agent_id": None,  # Set by test
        "memory_type": "semantic",
        "content": {
            "pattern": "rsi_oversold",
            "win_rate": 0.65,
            "avg_pnl": 2.3,
            "sample_size": 50,
        },
        "weight": 0.9,
        "created_at": datetime.utcnow(),
    }


# ============================================================================
# PYTEST MARKERS
# ============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "soundness: marks soundness/EDD tests")
    config.addinivalue_line("markers", "property: marks property-based tests")
    config.addinivalue_line("markers", "requires_db: marks tests requiring database")
    # MASTER TEST ADMIN markers
    config.addinivalue_line("markers", "critical: business-critical tests (run first)")
    config.addinivalue_line("markers", "division_safety: division by zero protection")
    config.addinivalue_line("markers", "edge_case: boundary condition tests")
    config.addinivalue_line("markers", "mutation: mutation testing targets")
    config.addinivalue_line("markers", "chaos: fault injection tests")
    config.addinivalue_line("markers", "concurrency: race condition tests")
    config.addinivalue_line("markers", "performance: load/stress tests")
    config.addinivalue_line("markers", "regression: golden file snapshot tests")


# ============================================================================
# HYPOTHESIS CONFIGURATION - MASTER TEST ADMIN WAR PROFILES
# ============================================================================

from datetime import timedelta

from hypothesis import Phase, Verbosity, settings

# War mode: Maximum examples, no deadline - for finding BLACK SWANS
settings.register_profile(
    "war",
    max_examples=100000,
    deadline=None,
    suppress_health_check=[],
    verbosity=Verbosity.verbose,
    phases=[Phase.generate, Phase.shrink],
)

# CI mode: Reasonable examples, with deadline - for continuous integration
settings.register_profile(
    "ci",
    max_examples=10000,
    deadline=timedelta(seconds=30),
)

# Dev mode: Fast iteration - for development workflow
settings.register_profile(
    "dev",
    max_examples=100,
    deadline=timedelta(seconds=5),
)

# Default to dev for normal test runs
# Use --hypothesis-profile=war for full assault
# Use --hypothesis-profile=ci for CI pipelines
settings.load_profile("dev")


# ============================================================================
# FACTORY FIXTURES - MASTER TEST ADMIN APPROVED
# ============================================================================

from Tests.Fixtures.factories import AgentFactory, PatternFactory, TradeFactory


@pytest.fixture
def trade_factory():
    """Provide TradeFactory for tests."""
    return TradeFactory


@pytest.fixture
def agent_factory():
    """Provide AgentFactory for tests."""
    return AgentFactory


@pytest.fixture
def pattern_factory():
    """Provide PatternFactory for tests."""
    return PatternFactory


@pytest.fixture
def edge_case_trades():
    """All edge case trade scenarios for exhaustive testing."""
    return TradeFactory.edge_cases()


# ============================================================================
# CANONICAL FIXTURES - FROZEN TEST DATA
# ============================================================================

from Tests.Fixtures.canonical_agents import CANONICAL_AGENTS
from Tests.Fixtures.canonical_patterns import CANONICAL_PATTERNS
from Tests.Fixtures.canonical_windows import CANONICAL_WINDOWS


@pytest.fixture
def canonical_agents():
    """All canonical agents for regression testing."""
    return CANONICAL_AGENTS


@pytest.fixture
def canonical_patterns():
    """All canonical patterns for regression testing."""
    return CANONICAL_PATTERNS


@pytest.fixture
def canonical_windows():
    """All canonical windows for regression testing."""
    return CANONICAL_WINDOWS


@pytest.fixture
def balanced_trader():
    """The balanced_trader canonical agent."""
    return dict(CANONICAL_AGENTS["balanced_trader"])


@pytest.fixture
def aggressive_momentum():
    """The aggressive_momentum canonical agent."""
    return dict(CANONICAL_AGENTS["aggressive_momentum"])


# ============================================================================
# FEATURE FLAG FIXTURES
# ============================================================================

from Config.feature_flags import FLAGS, ServiceVersion, reset_flags, with_version


@pytest.fixture
def feature_flags():
    """Provide feature flags for tests."""
    return FLAGS


@pytest.fixture
def green_mode():
    """Context manager to run service in green (experimental) mode."""

    def _green(service_name: str):
        return with_version(service_name, ServiceVersion.GREEN)

    return _green


@pytest.fixture(autouse=False)
def reset_feature_flags():
    """Reset feature flags after test (use when modifying flags)."""
    yield
    reset_flags()
