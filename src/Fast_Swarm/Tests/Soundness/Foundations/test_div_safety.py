"""
EDD Soundness Test: Division Safety - IMPLEMENTED

MASTER TEST ADMIN - Evidence-Driven Development Suite
Source of truth: Master_plan.md (Safety Invariants)

CRITICAL: All division operations must survive zero denominators.
These tests MUST NOT be removed or weakened. They prevent production crashes.

Division Hotspots Tested:
1. Sortino ratio: downside_dev == 0 (all winners)
2. Sharpe ratio: std_dev == 0 (identical returns)
3. Profit factor: gross_loss == 0 (all winners)
4. Win rate: total_trades == 0 (empty list)
5. Max drawdown: peak == 0 (starting from zero)
6. Average PnL: total_trades == 0 (empty list)
"""

import math
import os

# Import factories for edge case generation
import sys

import pytest

from Agents.Services.fitness_service import (
    TradeData,
    calculate_ev,
    calculate_ev_multiplier,
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
    get_tier,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from Fixtures.factories import TradeFactory

# =============================================================================
# CONSTANTS - NO MAGIC NUMBERS
# =============================================================================

# Sortino cap when no downside deviation (from fitness_service.py:360)
SORTINO_CAP_NO_LOSSES = 4.0

# Expected fitness for failed EV gate
FITNESS_EV_GATE_FAILED = 0.0

# Expected tier for zero fitness
TIER_DIES = "DIES"


# =============================================================================
# TEST: Division Safety
# =============================================================================


class TestDivisionSafety:
    """CONTRACT: All division operations must be safe."""

    def test_sharpe_with_zero_volatility(self):
        """
        CONTRACT: Sharpe returns finite value when std_return = 0.

        Scenario: All trades have identical PnL (zero variance).
        Risk: Division by std_dev in Sharpe calculation.
        Expected: Finite result, no crash.
        """
        trades = TradeFactory.identical_pnl(count=10, pnl_pct=2.0)
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score), f"Fitness must be finite, got {result.fitness_score}"
        assert 0.0 <= result.fitness_score <= 100.0, f"Fitness must be in [0, 100], got {result.fitness_score}"

    def test_sortino_with_zero_downside(self):
        """
        CONTRACT: Sortino returns capped value when downside_std = 0.

        Scenario: All trades are winners (no negative returns).
        Risk: Division by downside_dev in Sortino calculation.
        Expected: Returns SORTINO_CAP_NO_LOSSES (4.0), not Inf.
        """
        trades = TradeFactory.all_winners(count=10, pnl_pct=5.0)
        sortino = calculate_sortino(trades)

        assert sortino == SORTINO_CAP_NO_LOSSES, (
            f"Sortino with no losses should be capped at {SORTINO_CAP_NO_LOSSES}, got {sortino}"
        )
        assert math.isfinite(sortino), f"Sortino must be finite, got {sortino}"

    def test_win_rate_with_zero_trades(self):
        """
        CONTRACT: Win rate returns 0 when total_trades = 0.

        Scenario: Empty trade list.
        Risk: Division by len(trades) in win rate calculation.
        Expected: Returns 0.0, no crash.
        """
        trades = TradeFactory.empty_list()
        win_rate = calculate_win_rate(trades)

        assert win_rate == 0.0, f"Win rate with no trades should be 0.0, got {win_rate}"

    def test_avg_pnl_with_zero_trades(self):
        """
        CONTRACT: Average PnL returns 0 when total_trades = 0.

        Scenario: Empty trade list.
        Risk: Division by len(trades) in EV calculation.
        Expected: Returns 0.0, no crash.
        """
        trades = TradeFactory.empty_list()
        ev = calculate_ev(trades)

        assert ev == 0.0, f"EV with no trades should be 0.0, got {ev}"

    def test_roi_with_zero_entry_price(self):
        """
        CONTRACT: ROI calculation handles zero entry price.

        Scenario: Trade with entry_price = 0.
        Risk: Division by entry_price in ROI calculation.
        Expected: No crash, valid result or filtered out.
        """
        # Create trade with zero entry price
        trade = TradeData(
            pnl=100.0,
            pnl_pct=5.0,  # Pre-calculated PnL %
            is_win=True,
            entry_price=0.0,  # Zero entry price
            exit_price=100.0,
            size=1.0,
        )
        trades = [trade]

        # Should not crash
        result = calculate_fitness(trades)
        assert math.isfinite(result.fitness_score), "Fitness must be finite even with zero entry price"

    def test_profit_factor_with_zero_losses(self):
        """
        CONTRACT: Profit factor with zero losses is bounded.

        Scenario: All trades are winners (gross_loss = 0).
        Risk: Division by gross_loss in profit factor.
        Expected: Returns bounded value, not Inf.
        """
        trades = TradeFactory.all_winners(count=10, pnl_pct=5.0)
        result = calculate_fitness(trades)

        # Profit factor is embedded in fitness calculation
        # The key is that fitness is finite and bounded
        assert math.isfinite(result.fitness_score), "Fitness must be finite with all winners"
        assert result.fitness_score > 0, "All winners should have positive fitness"

    def test_max_drawdown_with_zero_peak(self):
        """
        CONTRACT: Max drawdown handles zero or constant equity.

        Scenario: All trades have zero PnL (equity never changes).
        Risk: Division by peak in drawdown calculation.
        Expected: Returns 0.0 drawdown, no crash.
        """
        trades = TradeFactory.zero_pnl(count=10)
        max_dd = calculate_max_drawdown(trades)

        assert max_dd == 0.0, f"Drawdown with zero PnL trades should be 0.0, got {max_dd}"

    def test_fitness_with_empty_trades(self):
        """
        CONTRACT: Fitness with empty trades returns zero, no crash.

        Scenario: Empty trade list.
        Risk: Multiple division operations.
        Expected: Returns 0.0 fitness, DIES tier.
        """
        trades = TradeFactory.empty_list()
        result = calculate_fitness(trades)

        assert result.fitness_score == FITNESS_EV_GATE_FAILED, (
            f"Empty trades should have 0.0 fitness, got {result.fitness_score}"
        )
        assert result.tier == TIER_DIES, f"Empty trades should be DIES tier, got {result.tier}"
        assert math.isfinite(result.fitness_score), "Fitness must be finite"

    def test_fitness_with_single_trade(self):
        """
        CONTRACT: Single trade produces valid fitness.

        Scenario: Only one trade in list.
        Risk: Sortino requires 2+ trades, variance calculations.
        Expected: Valid finite result.
        """
        trades = TradeFactory.single_trade(pnl_pct=5.0)
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score), "Single trade should produce finite fitness"
        # Single winning trade passes EV gate
        assert result.fitness_score >= 0, "Single winning trade should have non-negative fitness"


# =============================================================================
# TEST: Inf and NaN Resilience
# =============================================================================


class TestInfNaNResilience:
    """CONTRACT: Inf and NaN values are handled gracefully."""

    def test_inf_pnl_does_not_crash(self):
        """
        CONTRACT: Infinite PnL does not crash service.

        Scenario: Trade list contains Inf PnL.
        Risk: Math operations on Inf.
        Expected: No exception raised.
        """
        trades = TradeFactory.with_inf()

        # Should not raise any exception
        try:
            result = calculate_fitness(trades)
            assert True  # No crash
        except Exception as e:
            pytest.fail(f"Inf PnL should not crash: {e}")

    def test_nan_pnl_does_not_crash(self):
        """
        CONTRACT: NaN PnL does not crash service.

        Scenario: Trade list contains NaN PnL.
        Risk: Math operations on NaN propagate.
        Expected: No exception raised.
        """
        trades = TradeFactory.with_nan()

        try:
            result = calculate_fitness(trades)
            assert True  # No crash
        except Exception as e:
            pytest.fail(f"NaN PnL should not crash: {e}")

    def test_inf_pnl_filtered_from_metrics(self):
        """
        CONTRACT: Infinite PnL filtered from metric calculations.

        Scenario: Mix of valid trades and Inf PnL trade.
        Risk: Inf pollutes averages and sums.
        Expected: Finite result based on valid trades only.
        """
        trades = TradeFactory.with_inf()
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score), (
            f"Fitness must be finite when Inf is filtered, got {result.fitness_score}"
        )
        # With 2 valid winning trades at 5.0 and 3.0 PnL, should pass EV gate
        assert result.fitness_score > 0, "Valid trades should produce positive fitness"

    def test_nan_pnl_filtered_from_metrics(self):
        """
        CONTRACT: NaN PnL filtered from metric calculations.

        Scenario: Mix of valid trades and NaN PnL trade.
        Risk: NaN propagates through calculations.
        Expected: Finite result based on valid trades only.
        """
        trades = TradeFactory.with_nan()
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score), (
            f"Fitness must be finite when NaN is filtered, got {result.fitness_score}"
        )
        assert not math.isnan(result.fitness_score), "Fitness must not be NaN"

    def test_fitness_never_returns_inf(self):
        """
        CONTRACT: Fitness score is always finite.

        Scenario: Various extreme inputs.
        Risk: Calculations produce Inf.
        Expected: Result is always finite.
        """
        extreme_scenarios = [
            TradeFactory.all_winners(100, pnl_pct=100.0),  # Extreme gains
            TradeFactory.all_losers(100, pnl_pct=-50.0),  # Extreme losses
            TradeFactory.extreme_trades(),  # Mixed extreme
        ]

        for i, trades in enumerate(extreme_scenarios):
            result = calculate_fitness(trades)
            assert math.isfinite(result.fitness_score), (
                f"Scenario {i}: Fitness must be finite, got {result.fitness_score}"
            )

    def test_fitness_never_returns_nan(self):
        """
        CONTRACT: Fitness score is never NaN.

        Scenario: Various edge cases including NaN inputs.
        Risk: NaN propagates through calculations.
        Expected: Result is never NaN.
        """
        edge_cases = TradeFactory.edge_cases()

        for name, trades in edge_cases.items():
            result = calculate_fitness(trades)
            assert not math.isnan(result.fitness_score), f"Edge case '{name}': Fitness must not be NaN"


# =============================================================================
# TEST: Zero PnL Edge Cases
# =============================================================================


class TestZeroPnlEdgeCases:
    """CONTRACT: Zero PnL edge cases handled correctly."""

    def test_max_drawdown_with_zero_pnl(self):
        """
        CONTRACT: Max drawdown is 0 with zero PnL trades.

        Scenario: All trades have exactly 0% PnL.
        Risk: Equity curve is flat, peak calculation edge case.
        Expected: 0% drawdown.
        """
        trades = TradeFactory.zero_pnl(count=10)
        max_dd = calculate_max_drawdown(trades)

        assert max_dd == 0.0, f"Zero PnL trades should have 0% drawdown, got {max_dd}"

    def test_all_zero_pnl_metrics(self):
        """
        CONTRACT: All-zero PnL produces valid metrics.

        Scenario: All trades have exactly 0% PnL.
        Risk: EV = 0, fails gate.
        Expected: Zero fitness (EV gate fails), but no crash.
        """
        trades = TradeFactory.zero_pnl(count=10)
        result = calculate_fitness(trades)

        # EV = 0, so EV gate should fail
        assert result.fitness_score == 0.0, (
            f"Zero PnL trades should have 0 fitness (EV gate), got {result.fitness_score}"
        )
        assert result.tier == TIER_DIES, "Zero PnL trades should be DIES tier"
        assert math.isfinite(result.fitness_score), "Fitness must be finite"

    def test_identical_pnl_sharpe(self):
        """
        CONTRACT: Identical PnL values (zero variance) handled.

        Scenario: All trades have exactly the same PnL.
        Risk: std_dev = 0 in Sharpe calculation.
        Expected: Finite Sharpe ratio or capped value.
        """
        trades = TradeFactory.identical_pnl(count=10, pnl_pct=2.0)
        result = calculate_fitness(trades)

        # Should not crash, should produce valid fitness
        assert math.isfinite(result.fitness_score), "Identical PnL trades should produce finite fitness"
        assert result.fitness_score > 0, "Positive identical PnL trades should have positive fitness"


# =============================================================================
# TEST: EV Multiplier Edge Cases
# =============================================================================


class TestEVMultiplierEdgeCases:
    """CONTRACT: EV multiplier is always bounded."""

    def test_ev_multiplier_negative_ev(self):
        """CONTRACT: Negative EV returns minimum multiplier."""
        mult = calculate_ev_multiplier(-10.0)
        assert mult == 0.35, f"Negative EV should return 0.35, got {mult}"

    def test_ev_multiplier_zero_ev(self):
        """CONTRACT: Zero EV returns minimum multiplier."""
        mult = calculate_ev_multiplier(0.0)
        assert mult == 0.35, f"Zero EV should return 0.35, got {mult}"

    def test_ev_multiplier_extreme_positive_ev(self):
        """CONTRACT: Extreme positive EV is capped at 1.5."""
        mult = calculate_ev_multiplier(1000.0)  # Unrealistic 1000% EV
        assert mult == 1.5, f"Extreme EV should be capped at 1.5, got {mult}"

    def test_ev_multiplier_always_bounded(self):
        """CONTRACT: EV multiplier is always in [0.35, 1.5]."""
        test_values = [-100, -10, -1, 0, 0.5, 1, 2, 3, 5, 9, 10, 100, 1000]

        for ev in test_values:
            mult = calculate_ev_multiplier(ev)
            assert 0.35 <= mult <= 1.5, f"EV={ev}: Multiplier {mult} out of bounds [0.35, 1.5]"


# =============================================================================
# TEST: Tier Mapping
# =============================================================================


class TestTierMapping:
    """CONTRACT: Tier mapping is consistent."""

    def test_tier_dies_below_40(self):
        """CONTRACT: Fitness < 40 maps to DIES."""
        for score in [0, 10, 20, 30, 39, 39.9]:
            tier = get_tier(score)
            assert tier == "DIES", f"Score {score} should be DIES, got {tier}"

    def test_tier_survives_40_to_79(self):
        """CONTRACT: Fitness 40-79 maps to SURVIVES."""
        for score in [40, 50, 60, 70, 79, 79.9]:
            tier = get_tier(score)
            assert tier == "SURVIVES", f"Score {score} should be SURVIVES, got {tier}"

    def test_tier_promoted_80_plus(self):
        """CONTRACT: Fitness 80+ maps to PROMOTED."""
        for score in [80, 85, 90, 95, 100]:
            tier = get_tier(score)
            assert tier == "PROMOTED", f"Score {score} should be PROMOTED, got {tier}"

    def test_tier_boundary_40(self):
        """CONTRACT: Exactly 40 is SURVIVES."""
        assert get_tier(40.0) == "SURVIVES"
        assert get_tier(39.999) == "DIES"

    def test_tier_boundary_80(self):
        """CONTRACT: Exactly 80 is PROMOTED."""
        assert get_tier(80.0) == "PROMOTED"
        assert get_tier(79.999) == "SURVIVES"


# =============================================================================
# TEST: Comprehensive Edge Case Matrix
# =============================================================================


class TestEdgeCaseMatrix:
    """Comprehensive edge case testing using factory scenarios."""

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "empty",
            "single_winner",
            "single_loser",
            "all_winners",
            "all_losers",
            "identical_pnl",
            "zero_pnl",
            "with_nan",
            "with_inf",
            "with_neg_inf",
            "extreme",
        ],
    )
    def test_all_edge_cases_no_crash(self, scenario_name):
        """
        CONTRACT: All edge case scenarios must not crash.

        Parametrized test covering all edge cases from TradeFactory.
        """
        edge_cases = TradeFactory.edge_cases()
        trades = edge_cases[scenario_name]

        try:
            result = calculate_fitness(trades)

            # Basic validity checks
            assert result is not None
            assert hasattr(result, "fitness_score")
            assert hasattr(result, "tier")
            assert math.isfinite(result.fitness_score) or result.fitness_score == 0.0
            assert not math.isnan(result.fitness_score)
            assert result.tier in ["DIES", "SURVIVES", "PROMOTED"]

        except Exception as e:
            pytest.fail(f"Edge case '{scenario_name}' crashed: {e}")

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "empty",
            "single_winner",
            "single_loser",
            "all_winners",
            "all_losers",
            "identical_pnl",
            "zero_pnl",
            "with_nan",
            "with_inf",
            "with_neg_inf",
            "extreme",
        ],
    )
    def test_all_edge_cases_fitness_bounded(self, scenario_name):
        """
        CONTRACT: All edge cases produce fitness in [0, 100].
        """
        edge_cases = TradeFactory.edge_cases()
        trades = edge_cases[scenario_name]

        result = calculate_fitness(trades)

        assert 0.0 <= result.fitness_score <= 100.0, (
            f"Edge case '{scenario_name}': Fitness {result.fitness_score} out of [0, 100]"
        )
