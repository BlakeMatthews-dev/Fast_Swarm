"""
TDD: Specialist Fitness Model V4 Tests.

Defines the API contract for src/Fast_Swarm/Metrics/fitness_model.py.
The V4 model scores agents on:
- Specialist depth (40 pts): how good in best regime
- Risk discipline (35 pts): how safe outside best regime
- Signal quality (20 pts): is the edge real?
- Uniqueness (5 pts): tiebreaker for diversity
"""

from dataclasses import dataclass

import pytest

from Fast_Swarm.Metrics.fitness_model import (
    apply_interaction_penalties,
    calculate_risk_discipline,
    calculate_specialist_depth,
    calculate_specialist_fitness,
    calculate_uniqueness,
    ev_multiplier,
)
from Fast_Swarm.Metrics.signal_quality import calculate_signal_quality


# =============================================================================
# Mock Data
# =============================================================================


@dataclass
class MockRegimeMetrics:
    """Metrics for trades in a single regime."""
    sortino: float = 2.0
    alpha_pct: float = 10.0
    expectancy_pct: float = 2.0
    exit_efficiency: float = 0.65
    payoff_ratio: float = 1.5
    max_drawdown_pct: float = 12.0
    exposure: float = 0.3
    risk_of_ruin: float = 0.05
    max_consecutive_losses: int = 3
    n_trades: int = 50
    returns: list = None

    def __post_init__(self):
        if self.returns is None:
            self.returns = [0.01] * 35 + [-0.005] * 15


@dataclass
class MockPopulationReturns:
    """Average returns of the population for uniqueness calc."""
    returns: list = None

    def __post_init__(self):
        if self.returns is None:
            self.returns = [0.005] * 50


# =============================================================================
# EV Gate (Hard Gate Fix)
# =============================================================================


class TestEVMultiplier:
    """EV gate: hard zero for non-positive EV."""

    def test_zero_ev_returns_zero(self):
        """FIXED BUG: EV=0 -> 0.0, not 0.35."""
        assert ev_multiplier(0.0) == 0.0

    def test_negative_ev_returns_zero(self):
        """Negative EV -> 0.0."""
        assert ev_multiplier(-5.0) == 0.0

    def test_tiny_positive_ev(self):
        """Just above zero: small positive multiplier."""
        result = ev_multiplier(0.001)
        assert 0.0 < result < 0.5

    def test_one_percent_ev(self):
        """1% EV -> ~0.8."""
        result = ev_multiplier(1.0)
        assert abs(result - 0.8) < 0.05

    def test_three_percent_ev(self):
        """3% EV -> ~1.2."""
        result = ev_multiplier(3.0)
        assert abs(result - 1.2) < 0.05

    def test_nine_percent_ev_cap(self):
        """9%+ EV -> 1.5 cap."""
        assert ev_multiplier(9.0) == 1.5
        assert ev_multiplier(20.0) == 1.5

    def test_monotonically_increasing(self):
        """Higher EV -> higher multiplier."""
        values = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 9.0]
        prev = 0.0
        for v in values:
            curr = ev_multiplier(v)
            assert curr >= prev
            prev = curr


# =============================================================================
# Specialist Depth (40 pts)
# =============================================================================


class TestSpecialistDepth:
    """Score agent's performance in their best regime."""

    def test_returns_bounded_0_40(self):
        """Output must be in [0, 40]."""
        metrics = MockRegimeMetrics()
        result = calculate_specialist_depth(metrics)
        assert 0.0 <= result <= 40.0

    def test_good_specialist_high_score(self):
        """Strong specialist: high Sortino + alpha + expectancy."""
        metrics = MockRegimeMetrics(
            sortino=3.5,
            alpha_pct=50.0,
            expectancy_pct=5.0,
            exit_efficiency=0.75,
            payoff_ratio=2.5,
        )
        result = calculate_specialist_depth(metrics)
        assert result > 25.0  # Should score well

    def test_weak_specialist_low_score(self):
        """Weak specialist: poor metrics."""
        metrics = MockRegimeMetrics(
            sortino=0.3,
            alpha_pct=-5.0,
            expectancy_pct=0.2,
            exit_efficiency=0.35,
            payoff_ratio=0.7,
        )
        result = calculate_specialist_depth(metrics)
        assert result < 15.0

    def test_sortino_diminishing_returns(self):
        """Sortino 4.0 vs 3.0: diminishing marginal value."""
        m1 = MockRegimeMetrics(sortino=3.0)
        m2 = MockRegimeMetrics(sortino=4.0)
        s1 = calculate_specialist_depth(m1)
        s2 = calculate_specialist_depth(m2)
        # Gap between 3->4 should be smaller than 1->2
        m3 = MockRegimeMetrics(sortino=1.0)
        m4 = MockRegimeMetrics(sortino=2.0)
        s3 = calculate_specialist_depth(m3)
        s4 = calculate_specialist_depth(m4)
        assert (s2 - s1) < (s4 - s3)


# =============================================================================
# Risk Discipline (35 pts)
# =============================================================================


class TestRiskDiscipline:
    """Score agent's safety outside their specialist regime."""

    def test_returns_bounded_0_35(self):
        """Output in [0, 35]."""
        metrics = MockRegimeMetrics()
        result = calculate_risk_discipline(metrics)
        assert 0.0 <= result <= 35.0

    def test_sitting_out_full_score(self):
        """Low exposure + low drawdown + low ruin = full score."""
        metrics = MockRegimeMetrics(
            exposure=0.05,
            max_drawdown_pct=2.0,
            risk_of_ruin=0.01,
            max_consecutive_losses=2,
        )
        result = calculate_risk_discipline(metrics)
        assert result > 30.0

    def test_high_exposure_penalized(self):
        """Trading >30% out of regime -> penalty."""
        metrics = MockRegimeMetrics(exposure=0.6)
        result = calculate_risk_discipline(metrics)
        assert result < 30.0

    def test_high_drawdown_penalized(self):
        """Big drawdown outside specialty -> penalty."""
        metrics = MockRegimeMetrics(max_drawdown_pct=25.0)
        result = calculate_risk_discipline(metrics)
        assert result < 30.0

    def test_high_ruin_penalized(self):
        """High ruin probability -> severe penalty."""
        metrics = MockRegimeMetrics(risk_of_ruin=0.4, max_drawdown_pct=5.0)
        result = calculate_risk_discipline(metrics)
        assert result < 26.0

    def test_consecutive_losses_penalized(self):
        """Long losing streaks -> penalty."""
        metrics = MockRegimeMetrics(max_consecutive_losses=8)
        result = calculate_risk_discipline(metrics)
        assert result < 33.0


# =============================================================================
# Signal Quality (20 pts)
# =============================================================================


class TestSignalQuality:
    """Is the agent's edge real or noise?"""

    def test_returns_bounded_0_20(self):
        """Output in [0, 20]."""
        trades = [{"entry_confidence": 0.7, "outcome": 0.02}] * 50
        result = calculate_signal_quality(trades, n_trades=50, specialist_type="bull")
        assert 0.0 <= result <= 20.0

    def test_more_trades_higher_confidence(self):
        """100 trades scores higher than 10 trades (confidence weighting)."""
        trades_10 = [{"entry_confidence": 0.7, "outcome": 0.02}] * 10
        trades_100 = [{"entry_confidence": 0.7, "outcome": 0.02}] * 100

        s10 = calculate_signal_quality(trades_10, n_trades=10, specialist_type="bull")
        s100 = calculate_signal_quality(trades_100, n_trades=100, specialist_type="bull")
        assert s100 > s10

    def test_empty_trades_low(self):
        """No trades -> low signal quality."""
        result = calculate_signal_quality([], n_trades=0, specialist_type="bull")
        assert result < 5.0


# =============================================================================
# Uniqueness (5 pts - Tiebreaker)
# =============================================================================


class TestUniqueness:
    """Diversity bonus: low correlation with population."""

    def test_returns_bounded_0_5(self):
        """Output in [0, 5]."""
        agent_returns = [0.02, -0.01, 0.03, -0.02, 0.01]
        pop_returns = [0.01, 0.005, 0.008, 0.003, 0.006]
        result = calculate_uniqueness(agent_returns, pop_returns)
        assert 0.0 <= result <= 5.0

    def test_identical_returns_zero(self):
        """Same as population -> 0 uniqueness."""
        returns = [0.01, -0.01, 0.02, -0.02, 0.015]
        result = calculate_uniqueness(returns, returns)
        assert result < 1.0

    def test_uncorrelated_high(self):
        """Uncorrelated with population -> high score."""
        agent = [0.05, -0.03, 0.01, -0.04, 0.02]
        pop = [0.01, 0.01, 0.01, 0.01, 0.01]  # Constant
        result = calculate_uniqueness(agent, pop)
        assert result > 3.0


# =============================================================================
# Interaction Penalties (Multiplicative)
# =============================================================================


class TestInteractionPenalties:
    """Dangerous combinations get penalized."""

    def test_no_penalty_normal_agent(self):
        """Normal metrics -> penalty factor = 1.0."""
        factor = apply_interaction_penalties(
            specialist_sortino=1.5,
            specialist_max_dd=15.0,
            risk_of_ruin=0.05,
            specialist_trades=50,
        )
        assert factor == 1.0

    def test_fragile_penalty(self):
        """High Sortino + high drawdown = fragile."""
        factor = apply_interaction_penalties(
            specialist_sortino=3.0,
            specialist_max_dd=35.0,
            risk_of_ruin=0.05,
            specialist_trades=50,
        )
        assert factor < 1.0

    def test_high_ruin_penalty(self):
        """High ruin probability -> severe penalty."""
        factor = apply_interaction_penalties(
            specialist_sortino=1.5,
            specialist_max_dd=15.0,
            risk_of_ruin=0.35,
            specialist_trades=50,
        )
        assert factor < 0.8

    def test_low_trades_penalty(self):
        """Too few trades -> unreliable metrics penalty."""
        factor = apply_interaction_penalties(
            specialist_sortino=1.5,
            specialist_max_dd=15.0,
            risk_of_ruin=0.05,
            specialist_trades=10,
        )
        assert factor < 0.7

    def test_multiple_penalties_stack(self):
        """Multiple problems -> penalties multiply."""
        factor = apply_interaction_penalties(
            specialist_sortino=3.0,
            specialist_max_dd=35.0,
            risk_of_ruin=0.35,
            specialist_trades=10,
        )
        # 0.75 * 0.70 * 0.60 = 0.315
        assert factor < 0.4


# =============================================================================
# Full Pipeline
# =============================================================================


class TestSpecialistFitnessFull:
    """End-to-end specialist fitness calculation."""

    def test_output_bounded_0_100(self):
        """Final fitness in [0, 100]."""
        result = calculate_specialist_fitness(
            specialist_metrics=MockRegimeMetrics(),
            out_of_regime_metrics=MockRegimeMetrics(exposure=0.1, max_drawdown_pct=5.0),
            trades=[{"entry_confidence": 0.6, "outcome": 0.01}] * 50,
            agent_returns=[0.01] * 50,
            population_returns=[0.005] * 50,
            specialist_type="bull",
        )
        assert 0.0 <= result <= 100.0

    def test_zero_ev_returns_zero(self):
        """EV gate: zero expectancy -> zero fitness."""
        result = calculate_specialist_fitness(
            specialist_metrics=MockRegimeMetrics(expectancy_pct=0.0),
            out_of_regime_metrics=MockRegimeMetrics(),
            trades=[],
            agent_returns=[0.0] * 50,
            population_returns=[0.005] * 50,
            specialist_type="bull",
        )
        assert result == 0.0

    def test_good_specialist_scores_high(self):
        """Strong specialist in bull regime."""
        result = calculate_specialist_fitness(
            specialist_metrics=MockRegimeMetrics(
                sortino=3.0, alpha_pct=40.0, expectancy_pct=4.0,
                exit_efficiency=0.7, payoff_ratio=2.0,
            ),
            out_of_regime_metrics=MockRegimeMetrics(
                exposure=0.05, max_drawdown_pct=3.0, risk_of_ruin=0.01,
            ),
            trades=[{"entry_confidence": 0.8, "outcome": 0.03}] * 80,
            agent_returns=[0.02, -0.005] * 40,
            population_returns=[0.005] * 80,
            specialist_type="bull",
        )
        assert result > 50.0
