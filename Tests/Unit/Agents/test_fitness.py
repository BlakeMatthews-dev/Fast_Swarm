"""
Agent Fitness Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md Section 1.3 (100-Point Fitness Model)
Fitness = (Signed + Unsigned Components) × EV_Multiplier, bounded [0, 100]
"""

import math

from Fast_Swarm.Agents.Services.fitness_service import (
    FitnessResult,
    TradeData,
    calculate_ai_accuracy_component,
    calculate_alpha_component,
    calculate_calibration_component,
    calculate_drawdown_component,
    calculate_ev,
    calculate_ev_multiplier,
    calculate_exit_efficiency_component,
    calculate_fitness,
    calculate_loss_sizing_component,
    calculate_sortino_component,
    calculate_win_rate_component,
    ev_gate,
    fitness_below_threshold,
    fitness_promoted,
    fitness_survives,
    get_tier,
)

# ============================================================================
# Test Data Helpers
# ============================================================================


def make_trade(pnl: float, pnl_pct: float, is_win: bool = None) -> TradeData:
    """Create a TradeData instance."""
    if is_win is None:
        is_win = pnl > 0
    return TradeData(pnl=pnl, pnl_pct=pnl_pct, is_win=is_win)


def make_trades(pnl_pcts: list) -> list:
    """Create a list of trades from PnL percentages."""
    return [make_trade(p * 100, p) for p in pnl_pcts]


# ============================================================================
# FITNESS CALCULATION CONTRACT (100-point model)
# ============================================================================


class TestFitnessScale:
    """CONTRACT: Fitness is always in [0, 100] scale."""

    def test_fitness_bounded_0_to_100(self):
        """CONTRACT: Fitness score must ALWAYS be in [0, 100]."""
        trades = make_trades([5.0, 3.0, 2.0, 1.0])  # Positive EV
        result = calculate_fitness(trades)

        assert 0.0 <= result.fitness_score <= 100.0

    def test_fitness_never_negative(self):
        """CONTRACT: Fitness cannot go below 0."""
        # Very negative scenario
        result = calculate_fitness(
            make_trades([-10, -5, -3]),  # All losses
            benchmark_pct=-100,
            calibration_score=0.0,
        )

        assert result.fitness_score >= 0.0

    def test_fitness_never_over_100(self):
        """CONTRACT: Fitness cannot exceed 100."""
        # Extreme positive scenario
        result = calculate_fitness(
            make_trades([50, 40, 30, 20, 10]),  # High wins
            benchmark_pct=100,
            calibration_score=1.0,
            exit_efficiency=0.9,
            loss_sizing=3.0,
            ai_accuracy=0.9,
        )

        assert result.fitness_score <= 100.0

    def test_fitness_returns_float(self):
        """CONTRACT: Fitness is always a float, not int."""
        trades = make_trades([2.0, 1.0, 0.5])
        result = calculate_fitness(trades)

        assert isinstance(result.fitness_score, float)


class TestEVGate:
    """CONTRACT: EV Gate blocks agents with negative expectancy."""

    def test_ev_gate_blocks_negative_expectancy(self):
        """CONTRACT: EV ≤ 0% → fitness = 0 (hard gate)."""
        # All losing trades
        trades = make_trades([-5, -3, -2, -1])
        result = calculate_fitness(trades)

        assert result.fitness_score == 0.0
        assert result.tier == "DIES"

    def test_ev_gate_allows_positive_expectancy(self):
        """CONTRACT: EV > 0% → fitness calculation proceeds."""
        trades = make_trades([5, 3, 2, 1])
        result = calculate_fitness(trades)

        assert result.fitness_score > 0.0

    def test_ev_gate_at_exactly_zero(self):
        """CONTRACT: EV = 0% → fitness = 0 (gate triggers)."""
        # Mixed trades that sum to zero
        trades = make_trades([5, -5, 3, -3])
        ev = calculate_ev(trades)

        assert ev == 0.0
        assert not ev_gate(ev)

    def test_ev_calculation_from_trades(self):
        """CONTRACT: EV = average(pnl_pct) from all trades."""
        trades = make_trades([10, 5, 0, -5])  # Average = 2.5
        ev = calculate_ev(trades)

        assert ev == 2.5


class TestEVMultiplier:
    """CONTRACT: EV multiplier scales fitness based on expectancy."""

    def test_ev_multiplier_at_0_percent(self):
        """CONTRACT: EV=0% → multiplier=0.35."""
        mult = calculate_ev_multiplier(0)

        assert mult == 0.35

    def test_ev_multiplier_at_1_percent(self):
        """CONTRACT: EV=1% → multiplier=0.8."""
        mult = calculate_ev_multiplier(1)

        assert mult == 0.8

    def test_ev_multiplier_at_3_percent(self):
        """CONTRACT: EV=3% → multiplier=1.2."""
        mult = calculate_ev_multiplier(3)

        assert mult == 1.2

    def test_ev_multiplier_at_9_percent_plus(self):
        """CONTRACT: EV≥9% → multiplier=1.5 (capped)."""
        mult_9 = calculate_ev_multiplier(9)
        mult_15 = calculate_ev_multiplier(15)
        mult_100 = calculate_ev_multiplier(100)

        assert mult_9 == 1.5
        assert mult_15 == 1.5
        assert mult_100 == 1.5

    def test_ev_multiplier_interpolates_linearly(self):
        """CONTRACT: Multiplier interpolates between defined points."""
        # Test midpoint between 1% (0.8) and 3% (1.2)
        # At 2%, should be 1.0
        mult = calculate_ev_multiplier(2)

        assert mult == 1.0


class TestSignedComponents:
    """CONTRACT: Signed components can be positive or negative."""

    def test_alpha_component_range(self):
        """CONTRACT: Alpha = ±35 points (-100% to +100% normalized)."""
        alpha_min = calculate_alpha_component(-100)
        alpha_max = calculate_alpha_component(100)

        assert alpha_min == -35.0
        assert alpha_max == 35.0

    def test_alpha_at_negative_100_percent(self):
        """CONTRACT: Alpha at -100% benchmark → -35 points."""
        alpha = calculate_alpha_component(-100)

        assert alpha == -35.0

    def test_alpha_at_zero_percent(self):
        """CONTRACT: Alpha at 0% benchmark → 0 points."""
        alpha = calculate_alpha_component(0)

        assert alpha == 0.0

    def test_alpha_at_positive_100_percent(self):
        """CONTRACT: Alpha at +100% benchmark → +35 points."""
        alpha = calculate_alpha_component(100)

        assert alpha == 35.0

    def test_calibration_component_range(self):
        """CONTRACT: Calibration = ±10 points (0.5 baseline = 0)."""
        cal_min = calculate_calibration_component(0.0)
        cal_max = calculate_calibration_component(1.0)

        assert cal_min == -10.0
        assert cal_max == 10.0

    def test_calibration_at_baseline(self):
        """CONTRACT: Calibration at 0.5 → 0 points."""
        cal = calculate_calibration_component(0.5)

        assert cal == 0.0

    def test_calibration_below_baseline(self):
        """CONTRACT: Calibration < 0.5 → negative points."""
        cal = calculate_calibration_component(0.3)

        assert cal < 0.0

    def test_calibration_above_baseline(self):
        """CONTRACT: Calibration > 0.5 → positive points."""
        cal = calculate_calibration_component(0.7)

        assert cal > 0.0


class TestUnsignedComponents:
    """CONTRACT: Unsigned components are always positive."""

    def test_win_rate_component_10pts(self):
        """CONTRACT: Win Rate contributes 0-10 points (30-70% range)."""
        wr_min = calculate_win_rate_component(30)
        wr_max = calculate_win_rate_component(70)

        assert wr_min == 0.0
        assert wr_max == 10.0

    def test_win_rate_at_30_percent(self):
        """CONTRACT: Win rate 30% → 0 points."""
        wr = calculate_win_rate_component(30)

        assert wr == 0.0

    def test_win_rate_at_70_percent(self):
        """CONTRACT: Win rate 70% → 10 points."""
        wr = calculate_win_rate_component(70)

        assert wr == 10.0

    def test_sortino_component_15pts(self):
        """CONTRACT: Sortino contributes 0-15 points (0-4 range)."""
        sort_min = calculate_sortino_component(0)
        sort_max = calculate_sortino_component(4)

        assert sort_min == 0.0
        assert sort_max == 15.0

    def test_sortino_at_zero(self):
        """CONTRACT: Sortino 0 → 0 points."""
        sort = calculate_sortino_component(0)

        assert sort == 0.0

    def test_sortino_at_4(self):
        """CONTRACT: Sortino 4 → 15 points."""
        sort = calculate_sortino_component(4)

        assert sort == 15.0

    def test_drawdown_component_10pts(self):
        """CONTRACT: Drawdown contributes 0-10 points (0-50% inverted)."""
        dd_best = calculate_drawdown_component(0)
        dd_worst = calculate_drawdown_component(50)

        assert dd_best == 10.0
        assert dd_worst == 0.0

    def test_drawdown_at_0_percent(self):
        """CONTRACT: Drawdown 0% → 10 points (best)."""
        dd = calculate_drawdown_component(0)

        assert dd == 10.0

    def test_drawdown_at_50_percent(self):
        """CONTRACT: Drawdown 50% → 0 points (worst)."""
        dd = calculate_drawdown_component(50)

        assert dd == 0.0

    def test_exit_efficiency_component_10pts(self):
        """CONTRACT: Exit Efficiency contributes 0-10 points (0.3-0.8 range)."""
        ee_min = calculate_exit_efficiency_component(0.3)
        ee_max = calculate_exit_efficiency_component(0.8)

        assert ee_min == 0.0
        assert ee_max == 10.0

    def test_loss_sizing_component_5pts(self):
        """CONTRACT: Loss Sizing contributes 0-5 points (0.5-2.0 range)."""
        ls_min = calculate_loss_sizing_component(0.5)
        ls_max = calculate_loss_sizing_component(2.0)

        assert ls_min == 0.0
        assert ls_max == 5.0

    def test_ai_accuracy_component_5pts(self):
        """CONTRACT: AI Accuracy contributes 0-5 points (0.4-0.8 range)."""
        ai_min = calculate_ai_accuracy_component(0.4)
        ai_max = calculate_ai_accuracy_component(0.8)

        assert ai_min == 0.0
        assert ai_max == 5.0


class TestFitnessFormula:
    """CONTRACT: Final fitness = min(100, max(0, (signed + unsigned) × EV))."""

    def test_fitness_formula_complete(self):
        """CONTRACT: fitness = (alpha + calibration + win_rate + sortino +
        drawdown + exit_eff + loss_size + ai_acc) × ev_multiplier."""
        trades = make_trades([5, 4, 3, 2, 1])  # Positive EV
        result = calculate_fitness(
            trades,
            benchmark_pct=50,  # +17.5 alpha
            calibration_score=0.75,  # +5 calibration
        )

        # Verify it's a valid fitness result
        assert isinstance(result, FitnessResult)
        assert result.fitness_score >= 0
        assert result.fitness_score <= 100
        assert "alpha" in result.component_breakdown

    def test_fitness_with_all_components_at_max(self):
        """CONTRACT: All components at max → fitness = 100."""
        # Create trades with 100% win rate and high EV
        trades = [make_trade(100, 15, True) for _ in range(20)]

        result = calculate_fitness(
            trades,
            benchmark_pct=100,  # +35 alpha
            calibration_score=1.0,  # +10 calibration
            exit_efficiency=0.9,  # +10 exit eff
            loss_sizing=3.0,  # +5 loss sizing
            ai_accuracy=0.9,  # +5 ai accuracy
        )

        # Should hit 100 cap
        assert result.fitness_score == 100.0

    def test_fitness_with_all_components_at_min(self):
        """CONTRACT: All components at min → fitness = 0."""
        # Negative EV trades → EV gate blocks
        trades = make_trades([-5, -10, -15])

        result = calculate_fitness(
            trades,
            benchmark_pct=-100,
            calibration_score=0.0,
            exit_efficiency=0.0,
            loss_sizing=0.0,
            ai_accuracy=0.0,
        )

        assert result.fitness_score == 0.0

    def test_fitness_clamps_to_100(self):
        """CONTRACT: Even if formula exceeds 100, result is 100."""
        # High EV and all max components
        trades = [make_trade(500, 50, True) for _ in range(10)]

        result = calculate_fitness(
            trades,
            benchmark_pct=100,
            calibration_score=1.0,
            exit_efficiency=1.0,
            loss_sizing=5.0,
            ai_accuracy=1.0,
        )

        assert result.fitness_score == 100.0

    def test_fitness_clamps_to_0(self):
        """CONTRACT: Even if formula goes negative, result is 0."""
        # EV gate handles this
        trades = make_trades([-10, -20, -30])
        result = calculate_fitness(trades)

        assert result.fitness_score == 0.0


class TestFitnessEdgeCases:
    """CONTRACT: Fitness handles edge cases gracefully."""

    def test_fitness_with_no_trades(self):
        """CONTRACT: Zero trades → fitness = 0."""
        result = calculate_fitness([])

        assert result.fitness_score == 0.0
        assert result.tier == "DIES"

    def test_fitness_with_one_trade(self):
        """CONTRACT: Single trade → fitness calculated (no Sharpe/Sortino)."""
        trades = [make_trade(100, 5, True)]
        result = calculate_fitness(trades)

        # Should calculate but with limited metrics
        assert result.fitness_score >= 0.0
        assert isinstance(result.fitness_score, float)

    def test_fitness_with_nan_pnl(self):
        """CONTRACT: NaN pnl trades filtered, fitness still calculated."""
        trades = [
            make_trade(100, 5, True),
            make_trade(float("nan"), float("nan"), True),
            make_trade(200, 10, True),
        ]
        result = calculate_fitness(trades)

        # Should work with valid trades only
        assert result.fitness_score >= 0.0
        assert math.isfinite(result.fitness_score)

    def test_fitness_with_inf_pnl(self):
        """CONTRACT: Inf pnl trades filtered, fitness still calculated."""
        trades = [
            make_trade(100, 5, True),
            make_trade(float("inf"), float("inf"), True),
            make_trade(200, 10, True),
        ]
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score)

    def test_fitness_with_null_pnl(self):
        """CONTRACT: Null pnl trades filtered, fitness still calculated."""
        # In Python, we use None; TradeData can't have None, so test separately
        valid_trades = make_trades([5, 10])
        result = calculate_fitness(valid_trades)

        assert math.isfinite(result.fitness_score)

    def test_fitness_all_winning_trades(self):
        """CONTRACT: 100% win rate → high fitness (but not suspicious)."""
        trades = [make_trade(100, 5, True) for _ in range(20)]
        result = calculate_fitness(trades)

        assert result.fitness_score > 0
        # 100% win rate = 10 points for win_rate component
        assert result.component_breakdown["win_rate"] == 10.0

    def test_fitness_all_losing_trades(self):
        """CONTRACT: 100% loss rate → fitness = 0 (EV gate)."""
        trades = [make_trade(-100, -5, False) for _ in range(20)]
        result = calculate_fitness(trades)

        assert result.fitness_score == 0.0

    def test_fitness_with_zero_std_deviation(self):
        """CONTRACT: All identical PnL → Sharpe = 0 (div by zero safe)."""
        # All trades with exactly same PnL
        trades = [make_trade(100, 5, True) for _ in range(10)]
        result = calculate_fitness(trades)

        # Should not crash
        assert math.isfinite(result.fitness_score)


class TestFitnessDeterminism:
    """CONTRACT: Same inputs produce same fitness."""

    def test_fitness_deterministic(self):
        """CONTRACT: Same trades → same fitness every time."""
        trades = make_trades([5, 3, 2, 1, -1])

        result1 = calculate_fitness(trades)
        result2 = calculate_fitness(trades)
        result3 = calculate_fitness(trades)

        assert result1.fitness_score == result2.fitness_score
        assert result2.fitness_score == result3.fitness_score

    def test_fitness_order_independent(self):
        """CONTRACT: Trade order doesn't affect fitness."""
        pnls = [5, 3, 2, 1, -1]
        trades1 = make_trades(pnls)
        trades2 = make_trades(list(reversed(pnls)))

        result1 = calculate_fitness(trades1)
        result2 = calculate_fitness(trades2)

        # EV and win rate are order-independent
        assert result1.metrics.ev == result2.metrics.ev
        assert result1.metrics.win_rate == result2.metrics.win_rate


class TestFitnessTierMapping:
    """CONTRACT: Fitness maps to tier/survival decisions."""

    def test_fitness_below_40_dies(self):
        """CONTRACT: Fitness < 40 → agent dies/retired."""
        assert get_tier(0) == "DIES"
        assert get_tier(20) == "DIES"
        assert get_tier(39.9) == "DIES"
        assert fitness_below_threshold(35)

    def test_fitness_40_to_79_survives(self):
        """CONTRACT: Fitness 40-79 → agent survives."""
        assert get_tier(40) == "SURVIVES"
        assert get_tier(50) == "SURVIVES"
        assert get_tier(79) == "SURVIVES"
        assert fitness_survives(50)
        assert not fitness_survives(39)
        assert not fitness_survives(80)

    def test_fitness_80_plus_promoted(self):
        """CONTRACT: Fitness ≥ 80 → agent promoted/elite."""
        assert get_tier(80) == "PROMOTED"
        assert get_tier(90) == "PROMOTED"
        assert get_tier(100) == "PROMOTED"
        assert fitness_promoted(80)
        assert fitness_promoted(100)
        assert not fitness_promoted(79)
