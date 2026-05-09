"""
Shared test fixtures for Local Agents test suite.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

# =============================================================================
# Type Stubs (will be replaced with real imports once implemented)
# =============================================================================


@dataclass
class AgentTraits:
    """Agent personality traits (22 total)."""

    # Core Risk (4)
    risk_tolerance: float = 0.5
    hold_duration_bias: float = 0.5
    volatility_seeking: float = 0.5
    profit_target_greed: float = 0.5

    # Pattern Selection (2)
    win_rate_preference: float = 0.5
    momentum_vs_reversion: float = 0.5

    # Execution (1)
    entry_aggression: float = 0.5

    # Technical (1)
    lookback_preference: float = 0.5

    # Sentiment (3)
    sentiment_weight: float = 0.5
    news_reactivity: float = 0.5
    sentiment_contrarian: float = 0.5

    # Macro (2)
    funding_rate_sensitivity: float = 0.5
    correlation_awareness: float = 0.5

    # Decision Anchor (1) - Independent
    uncertainty_anchor: float = 0.5

    # Derived (3) - From anchors with ±5% noise
    drawdown_sensitivity: float = 0.5
    stop_loss_tightness: float = 0.5
    exit_aggression: float = 0.5

    # Threshold (3) - From uncertainty_anchor
    ai_assist_range: float = 0.2
    min_threshold: float = 0.3
    ai_threshold: float = 0.7

    # Memory (2)
    memory_condensation: float = 0.5
    inheritance_decay: float = 0.3


@dataclass
class AgentMetrics:
    """Aggregated metrics for fitness calculation."""

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Core metrics
    alpha_pct: float = 0.0
    expectancy_pct: float = 0.0
    win_rate_pct: float = 50.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0

    # Judgment metrics
    calibration_score: float = 0.5
    exit_efficiency: float = 0.5
    loss_sizing_ratio: float = 1.0

    # AI metrics
    ai_decisions: int = 0
    ai_correct: int = 0
    ai_usage_rate: float = 0.0


@dataclass
class Memory:
    """Agent memory entry."""

    memory_id: str = ""
    agent_id: str = ""
    memory_type: str = "observation"  # observation, opinion, lesson, counterfactual, regret, affirmation
    content: str = ""
    weight: float = 0.5
    confidence: float = 0.5
    linked_trade_ids: list = field(default_factory=list)
    linked_memory_ids: list = field(default_factory=list)
    spawned_from: str | None = None
    context_snapshot: dict = field(default_factory=dict)
    created_at: int = 0
    last_accessed_at: int = 0
    reinforcement_count: int = 0
    contradiction_count: int = 0


@dataclass
class FitnessBreakdown:
    """Detailed fitness calculation result."""

    # EV Gate
    expectancy_pct: float = 0.0
    ev_multiplier: float = 0.0
    ev_gate_passed: bool = False

    # Signed components
    alpha_contribution: float = 0.0
    calibration_contribution: float = 0.0
    signed_total: float = 0.0

    # Unsigned components
    win_rate_score: float = 0.0
    sortino_score: float = 0.0
    drawdown_score: float = 0.0
    exit_efficiency_score: float = 0.0
    loss_sizing_score: float = 0.0
    ai_accuracy_score: float = 0.0
    unsigned_total: float = 0.0

    # Final scores
    raw_fitness: float = 0.0
    scaled_fitness: float = 0.0
    final_fitness: float = 0.0


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_traits() -> AgentTraits:
    """Standard trait set for tests (seed=42 equivalent)."""
    return AgentTraits(
        risk_tolerance=0.65,
        hold_duration_bias=0.45,
        volatility_seeking=0.55,
        profit_target_greed=0.60,
        win_rate_preference=0.50,
        momentum_vs_reversion=0.70,
        entry_aggression=0.55,
        lookback_preference=0.40,
        sentiment_weight=0.35,
        news_reactivity=0.45,
        sentiment_contrarian=0.30,
        funding_rate_sensitivity=0.25,
        correlation_awareness=0.40,
        uncertainty_anchor=0.50,
        # Derived
        drawdown_sensitivity=0.38,  # ~1 - 0.65 + noise
        stop_loss_tightness=0.33,  # ~1 - 0.65 + noise
        exit_aggression=0.58,  # ~1 - 0.45 + noise
        # Threshold
        ai_assist_range=0.20,
        min_threshold=0.30,
        ai_threshold=0.70,
        # Memory
        memory_condensation=0.50,
        inheritance_decay=0.30,
    )


@pytest.fixture
def sample_metrics() -> AgentMetrics:
    """Good metrics for fitness tests."""
    return AgentMetrics(
        total_trades=100,
        winning_trades=55,
        losing_trades=45,
        alpha_pct=25.0,
        expectancy_pct=2.0,
        win_rate_pct=55.0,
        sortino_ratio=1.5,
        max_drawdown_pct=15.0,
        calibration_score=0.7,
        exit_efficiency=0.5,
        loss_sizing_ratio=1.2,
        ai_decisions=5,
        ai_correct=4,
        ai_usage_rate=0.05,
    )


@pytest.fixture
def poor_metrics() -> AgentMetrics:
    """Poor metrics for fitness tests."""
    return AgentMetrics(
        total_trades=50,
        winning_trades=15,
        losing_trades=35,
        alpha_pct=-30.0,
        expectancy_pct=-1.5,
        win_rate_pct=30.0,
        sortino_ratio=0.3,
        max_drawdown_pct=45.0,
        calibration_score=0.3,
        exit_efficiency=0.25,
        loss_sizing_ratio=0.6,
        ai_decisions=10,
        ai_correct=3,
        ai_usage_rate=0.20,
    )


@pytest.fixture
def sample_memory() -> Memory:
    """Standard memory for tests."""
    return Memory(
        memory_id="mem-001",
        agent_id="agent-001",
        memory_type="lesson",
        content="RSI below 30 often signals a buying opportunity",
        weight=0.7,
        confidence=0.8,
    )


@pytest.fixture
def mock_ollama(mocker: Any):
    """Mock Ollama LLM calls."""
    return mocker.patch("local_agents.shared.llm_client.call_ollama")
