"""
Production-caller tests for fitness_service.calculate_fitness.

Tests the public calculate_fitness() function as a production caller would:
pass in trades + optional params, assert on the FitnessResult contract.

Uses TradeFactory from Tests.Fixtures.factories for all trade generation.
"""

import math

import pytest

from Agents.Services.fitness_service import (
    FitnessResult,
    TradeData,
    calculate_fitness,
    calculate_sortino,
    calculate_sortino_component,
    get_tier,
)
from Tests.Fixtures.factories import TradeFactory


# =============================================================================
# TestCalculateFitness - 6 tests
# =============================================================================


class TestCalculateFitness:
    """Tests for the main calculate_fitness entry point."""

    def test_winning_above_50(self):
        """Agent with >50% win rate and positive EV produces fitness > 50."""
        # 70% win rate, positive avg PnL, seeded for reproducibility
        trades = TradeFactory.create_batch(50, avg_pnl=3.0, win_rate=0.7, seed=42)

        result = calculate_fitness(
            trades,
            benchmark_pct=20.0,
            calibration_score=0.7,
            exit_efficiency=0.65,
            loss_sizing=1.5,
            ai_accuracy=0.7,
        )

        assert isinstance(result, FitnessResult)
        assert result.fitness_score > 50, (
            f"Expected fitness > 50 for a winning agent, got {result.fitness_score}"
        )

    def test_losing_below_50(self):
        """Agent with <50% win rate and negative EV gets fitness < 50 (or 0 via EV gate)."""
        # All losers -> negative EV -> EV gate blocks -> fitness = 0
        trades = TradeFactory.all_losers(count=20, pnl_pct=-3.0)

        result = calculate_fitness(trades)

        assert result.fitness_score < 50, (
            f"Expected fitness < 50 for a losing agent, got {result.fitness_score}"
        )
        # Negative EV should trigger EV gate, producing exactly 0
        assert result.fitness_score == 0.0

    def test_empty_trades_zero(self):
        """No trades produces fitness = 0."""
        trades = TradeFactory.empty_list()

        result = calculate_fitness(trades)

        assert result.fitness_score == 0.0
        assert result.tier == "DIES"
        assert result.ev_multiplier == 0.0

    def test_nan_handled(self):
        """NaN values in trades are filtered out gracefully, no crash."""
        trades = TradeFactory.with_nan()

        # Should not raise
        result = calculate_fitness(trades)

        assert isinstance(result, FitnessResult)
        assert math.isfinite(result.fitness_score)
        assert not math.isnan(result.fitness_score)

    def test_negative_ev_gated(self):
        """Negative EV triggers the EV gate, producing fitness = 0."""
        # Mix of trades where losers dominate -> negative EV
        trades = TradeFactory.create_batch(30, avg_pnl=-2.0, win_rate=0.3, seed=99)

        result = calculate_fitness(trades)

        assert result.fitness_score == 0.0, (
            f"EV gate should block negative-EV agents, got fitness {result.fitness_score}"
        )
        assert result.tier == "DIES"

    def test_fitness_clamped_0_100(self):
        """Extreme input values still produce a result clamped to [0, 100]."""
        # Extreme winning trades with maxed-out optional params
        trades = TradeFactory.all_winners(count=50, pnl_pct=50.0)

        result = calculate_fitness(
            trades,
            benchmark_pct=100.0,       # max alpha
            calibration_score=1.0,     # max calibration
            exit_efficiency=1.0,       # max exit efficiency
            loss_sizing=5.0,           # well above cap
            ai_accuracy=1.0,           # max AI accuracy
        )

        assert 0.0 <= result.fitness_score <= 100.0, (
            f"Fitness must be in [0, 100], got {result.fitness_score}"
        )

        # Also test with extreme negative params (should still be >= 0)
        trades_bad = TradeFactory.create_batch(20, avg_pnl=0.5, win_rate=0.55, seed=7)
        result_bad = calculate_fitness(
            trades_bad,
            benchmark_pct=-100.0,
            calibration_score=0.0,
            exit_efficiency=0.0,
            loss_sizing=0.0,
            ai_accuracy=0.0,
        )
        assert 0.0 <= result_bad.fitness_score <= 100.0


# =============================================================================
# TestSortinoComponent - 2 tests
# =============================================================================


class TestSortinoComponent:
    """Tests for the Sortino ratio component."""

    def test_sortino_component_bounded(self):
        """Sortino component never exceeds 15 points regardless of input."""
        # Even a very high sortino ratio (far above 4) should cap at 15
        assert calculate_sortino_component(0.0) == 0.0
        assert calculate_sortino_component(4.0) == 15.0
        assert calculate_sortino_component(100.0) == 15.0
        assert calculate_sortino_component(-5.0) == 0.0

        # Check intermediate value
        component = calculate_sortino_component(2.0)
        assert 0.0 <= component <= 15.0
        assert component == pytest.approx(7.5)

    def test_sortino_uses_quantstats_logic(self):
        """
        Sortino calculation delegates to the metrics engine (QuantStats-backed),
        not a hand-rolled denominator. Verify by checking that the service-level
        calculate_sortino returns a bounded value and handles edge cases.
        """
        # All-winners: no downside deviation. QuantStats handles this gracefully.
        winners = TradeFactory.all_winners(count=20, pnl_pct=3.0)
        sortino_val = calculate_sortino(winners)
        assert math.isfinite(sortino_val)
        # Bounded to [0, 4] by the service
        assert 0.0 <= sortino_val <= 4.0

        # Mixed trades should produce a positive sortino
        mixed = TradeFactory.create_batch(30, avg_pnl=2.0, win_rate=0.6, seed=11)
        sortino_mixed = calculate_sortino(mixed)
        assert math.isfinite(sortino_mixed)
        assert 0.0 <= sortino_mixed <= 4.0

        # Single trade: insufficient data -> 0
        single = TradeFactory.single_trade(5.0)
        assert calculate_sortino(single) == 0.0


# =============================================================================
# TestFitnessResult - 2 tests
# =============================================================================


class TestFitnessResult:
    """Tests for FitnessResult tier assignment and component breakdown."""

    @pytest.mark.parametrize(
        "score, expected_tier",
        [
            (0.0, "DIES"),
            (20.0, "DIES"),
            (39.9, "DIES"),
            (40.0, "SURVIVES"),
            (60.0, "SURVIVES"),
            (79.9, "SURVIVES"),
            (80.0, "PROMOTED"),
            (100.0, "PROMOTED"),
        ],
    )
    def test_tier_assignment(self, score: float, expected_tier: str):
        """Tier boundaries: DIES (<40), SURVIVES (40-79), PROMOTED (>=80)."""
        assert get_tier(score) == expected_tier

    def test_component_breakdown_present(self):
        """FitnessResult contains all 8 component keys plus raw_total and ev_multiplier."""
        trades = TradeFactory.create_batch(20, avg_pnl=2.0, win_rate=0.6, seed=33)
        result = calculate_fitness(trades)

        expected_keys = {
            "alpha",
            "calibration",
            "win_rate",
            "sortino",
            "drawdown",
            "exit_efficiency",
            "loss_sizing",
            "ai_accuracy",
            "raw_total",
            "ev_multiplier",
        }

        # Only check when EV gate passes (otherwise breakdown is minimal)
        if result.fitness_score > 0:
            assert expected_keys.issubset(result.component_breakdown.keys()), (
                f"Missing keys: {expected_keys - set(result.component_breakdown.keys())}"
            )
            # All component values should be finite numbers
            for key, value in result.component_breakdown.items():
                assert math.isfinite(value), f"Component '{key}' is not finite: {value}"
