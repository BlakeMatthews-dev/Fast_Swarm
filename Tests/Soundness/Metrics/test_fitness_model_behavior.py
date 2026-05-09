"""
EDD: Fitness Model Behavior Tests.

Tests the current V3 agent fitness model for edge cases,
bounds, and expected economic behavior.

This validates CURRENT behavior before we replace with V4.
"""

import math
from dataclasses import dataclass

import pytest

from Fast_Swarm.local_agents.shared.fitness import (
    AGENT_FITNESS_BOUNDS,
    AGENT_FITNESS_WEIGHTS,
    FitnessBreakdown,
    calculate_agent_fitness,
    calculate_alpha_contribution,
    calculate_calibration_contribution,
    calculate_drawdown_score,
    calculate_exit_efficiency_score,
    calculate_loss_sizing_score,
    calculate_sortino_score,
    calculate_win_rate_score,
    expectancy_multiplier,
)


# =============================================================================
# Mock Metrics
# =============================================================================


@dataclass
class MockMetrics:
    """Configurable metrics for testing."""

    alpha_pct: float = 0.0
    expectancy_pct: float = 1.0  # Just passes EV gate
    win_rate_pct: float = 50.0
    sortino_ratio: float = 1.0
    max_drawdown_pct: float = 10.0
    calibration_score: float = 0.5
    exit_efficiency: float = 0.5
    loss_sizing_ratio: float = 1.0
    ai_decisions: int = 100
    ai_correct: int = 60


# =============================================================================
# Economic Validity
# =============================================================================


class TestFitnessEconomicValidity:
    """The fitness model should reward economically sound behavior."""

    def test_positive_ev_required(self):
        """Zero or negative EV -> zero fitness."""
        metrics = MockMetrics(expectancy_pct=0.0)
        result = calculate_agent_fitness(metrics)
        assert result.final_fitness == 0.0

        metrics.expectancy_pct = -5.0
        result = calculate_agent_fitness(metrics)
        assert result.final_fitness == 0.0

    def test_high_alpha_high_fitness(self):
        """High alpha contributes significantly to fitness."""
        low_alpha = MockMetrics(alpha_pct=0.0, expectancy_pct=3.0)
        high_alpha = MockMetrics(alpha_pct=80.0, expectancy_pct=3.0)

        low_result = calculate_agent_fitness(low_alpha)
        high_result = calculate_agent_fitness(high_alpha)

        assert high_result.final_fitness > low_result.final_fitness
        # Alpha is 35 pts out of 100 - should be significant
        assert high_result.final_fitness - low_result.final_fitness > 10

    def test_low_drawdown_rewarded(self):
        """Lower drawdown -> higher fitness."""
        low_dd = MockMetrics(max_drawdown_pct=5.0, expectancy_pct=3.0)
        high_dd = MockMetrics(max_drawdown_pct=45.0, expectancy_pct=3.0)

        low_result = calculate_agent_fitness(low_dd)
        high_result = calculate_agent_fitness(high_dd)

        assert low_result.final_fitness > high_result.final_fitness

    def test_high_sortino_rewarded(self):
        """Higher Sortino -> higher fitness."""
        low_s = MockMetrics(sortino_ratio=0.5, expectancy_pct=3.0)
        high_s = MockMetrics(sortino_ratio=3.5, expectancy_pct=3.0)

        low_result = calculate_agent_fitness(low_s)
        high_result = calculate_agent_fitness(high_s)

        assert high_result.final_fitness > low_result.final_fitness

    def test_ev_multiplier_amplifies_good_agents(self):
        """Higher EV = higher multiplier = higher fitness."""
        low_ev = MockMetrics(expectancy_pct=0.5, alpha_pct=50.0)
        high_ev = MockMetrics(expectancy_pct=8.0, alpha_pct=50.0)

        low_result = calculate_agent_fitness(low_ev)
        high_result = calculate_agent_fitness(high_ev)

        assert high_result.final_fitness > low_result.final_fitness
        # Multiplier effect should be substantial (0.7x vs 1.5x)
        assert high_result.final_fitness > low_result.final_fitness * 1.5


# =============================================================================
# Bounds and Capping
# =============================================================================


class TestFitnessBounds:
    """Output should always be in [0, 100]."""

    def test_maximum_possible_fitness(self):
        """Best possible metrics -> capped at 100."""
        metrics = MockMetrics(
            alpha_pct=100.0,
            expectancy_pct=9.0,  # 1.5x multiplier
            win_rate_pct=70.0,
            sortino_ratio=4.0,
            max_drawdown_pct=0.0,
            calibration_score=1.0,
            exit_efficiency=0.8,
            loss_sizing_ratio=2.0,
            ai_decisions=100,
            ai_correct=80,
        )
        result = calculate_agent_fitness(metrics)
        assert result.final_fitness <= 100.0

    def test_minimum_possible_fitness(self):
        """Worst metrics (but positive EV) -> capped at 0."""
        metrics = MockMetrics(
            alpha_pct=-100.0,
            expectancy_pct=0.01,  # Barely passes gate
            win_rate_pct=30.0,
            sortino_ratio=0.0,
            max_drawdown_pct=50.0,
            calibration_score=0.0,
            exit_efficiency=0.3,
            loss_sizing_ratio=0.5,
            ai_decisions=100,
            ai_correct=40,
        )
        result = calculate_agent_fitness(metrics)
        assert result.final_fitness >= 0.0

    def test_negative_alpha_can_push_below_zero(self):
        """Negative alpha makes raw fitness negative, then clamp to 0."""
        metrics = MockMetrics(
            alpha_pct=-100.0,  # -35 pts
            expectancy_pct=0.1,  # Low multiplier
            calibration_score=0.0,  # -10 pts
        )
        result = calculate_agent_fitness(metrics)
        # Signed can go to -45, but final is clamped to 0
        assert result.final_fitness >= 0.0


# =============================================================================
# Component Independence
# =============================================================================


class TestFitnessComponents:
    """Individual components should be independent and bounded."""

    def test_alpha_contribution_range(self):
        """Alpha: [-35, +35]."""
        assert calculate_alpha_contribution(-100.0) == -35.0
        assert calculate_alpha_contribution(0.0) == 0.0
        assert calculate_alpha_contribution(100.0) == 35.0

    def test_calibration_contribution_range(self):
        """Calibration: [-10, +10]."""
        assert calculate_calibration_contribution(0.0) == -10.0
        assert calculate_calibration_contribution(0.5) == 0.0
        assert calculate_calibration_contribution(1.0) == 10.0

    def test_win_rate_score_range(self):
        """Win rate: [0, 10]."""
        assert calculate_win_rate_score(30.0) == 0.0
        assert calculate_win_rate_score(70.0) == 10.0
        assert 0.0 <= calculate_win_rate_score(50.0) <= 10.0

    def test_sortino_score_range(self):
        """Sortino: [0, 15]."""
        assert calculate_sortino_score(0.0) == 0.0
        assert calculate_sortino_score(4.0) == 15.0
        assert 0.0 <= calculate_sortino_score(2.0) <= 15.0

    def test_drawdown_score_inverted(self):
        """Drawdown: [0, 10], lower DD = higher score."""
        # 0% drawdown -> full 10 pts
        assert calculate_drawdown_score(0.0) == 10.0
        # 50% drawdown -> 0 pts
        assert calculate_drawdown_score(50.0) == 0.0
        # 25% drawdown -> 5 pts
        assert abs(calculate_drawdown_score(25.0) - 5.0) < 0.01

    def test_exit_efficiency_range(self):
        """Exit efficiency: [0, 10]."""
        assert calculate_exit_efficiency_score(0.3) == 0.0
        assert calculate_exit_efficiency_score(0.8) == 10.0

    def test_loss_sizing_range(self):
        """Loss sizing: [0, 5]."""
        assert calculate_loss_sizing_score(0.5) == 0.0
        assert calculate_loss_sizing_score(2.0) == 5.0


# =============================================================================
# Weight Sum Verification
# =============================================================================


class TestFitnessWeightSum:
    """Weights should add up correctly."""

    def test_total_weight_is_100(self):
        """All component weights sum to 100."""
        total = sum(AGENT_FITNESS_WEIGHTS.values())
        # Signed: alpha(35) + calibration(10) = 45
        # Unsigned: win_rate(10) + sortino(15) + drawdown(10) + exit(10) + loss(5) + ai(5) = 55
        assert total == 100, f"Weights sum to {total}, expected 100"

    def test_max_raw_fitness_with_ev_1_5(self):
        """Max raw * 1.5 multiplier can exceed 100 (clamp needed)."""
        # Max signed: 35 + 10 = 45
        # Max unsigned: 10 + 15 + 10 + 10 + 5 + 5 = 55
        # Max raw: 100
        # Max scaled: 100 * 1.5 = 150 (needs clamping to 100)
        metrics = MockMetrics(
            alpha_pct=100.0,
            expectancy_pct=9.0,
            win_rate_pct=70.0,
            sortino_ratio=4.0,
            max_drawdown_pct=0.0,
            calibration_score=1.0,
            exit_efficiency=0.8,
            loss_sizing_ratio=2.0,
            ai_decisions=100,
            ai_correct=80,
        )
        result = calculate_agent_fitness(metrics)
        assert result.scaled_fitness >= 100  # Before clamp
        assert result.final_fitness == 100  # After clamp


# =============================================================================
# NaN/Inf Safety
# =============================================================================


class TestFitnessNaNSafety:
    """NaN and Inf inputs should not crash."""

    def test_nan_alpha(self):
        """NaN alpha -> 0 contribution."""
        assert calculate_alpha_contribution(float('nan')) == 0.0

    def test_nan_calibration(self):
        """NaN calibration -> 0 contribution."""
        assert calculate_calibration_contribution(float('nan')) == 0.0

    def test_inf_sortino(self):
        """Inf Sortino -> capped at bounds."""
        result = calculate_sortino_score(float('inf'))
        assert result == 0.0  # isfinite check returns 0.0

    def test_negative_inf_drawdown(self):
        """Negative Inf drawdown -> 0 score."""
        result = calculate_drawdown_score(float('-inf'))
        assert result == 0.0
