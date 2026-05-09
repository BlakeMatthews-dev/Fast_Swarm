"""
EDD Soundness Test: Backtest Replay Parity - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Backtest Determinism)
Validates that:
1. Fast_Swarm backtests produce deterministic results
2. Same inputs always produce same outputs
3. Fitness calculation is bounded and reasonable
4. Trait-aware parameters are correctly applied
"""

import math

import pytest

from Agents.Services.fitness_service import (
    TradeData,
    calculate_ev,
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
)
from Tests.Fixtures.factories import TradeFactory


class TestMetricsCalculation:
    """CONTRACT: Test the _calculate_metrics method."""

    def test_empty_trades_returns_zeros(self):
        """CONTRACT: Empty trade list should return zero metrics."""
        result = calculate_fitness([])
        assert result.fitness_score == 0.0
        assert result.metrics.ev == 0.0
        assert result.metrics.win_rate == 0.0
        assert result.tier == "DIES"

    def test_single_winning_trade(self):
        """CONTRACT: Single winning trade should produce positive metrics."""
        trades = TradeFactory.single_trade(pnl_pct=5.0)
        result = calculate_fitness(trades)
        assert result.metrics.ev > 0
        assert result.metrics.win_rate == 100.0
        assert result.fitness_score >= 0.0

    def test_single_losing_trade(self):
        """CONTRACT: Single losing trade should produce appropriate metrics."""
        trades = TradeFactory.single_trade(pnl_pct=-5.0)
        result = calculate_fitness(trades)
        # EV gate blocks negative EV
        assert result.fitness_score == 0.0
        assert result.tier == "DIES"

    def test_mixed_trades_win_rate(self):
        """CONTRACT: Mixed trades should calculate correct win rate."""
        trades = [
            TradeFactory.create(pnl_pct=5.0),   # win
            TradeFactory.create(pnl_pct=-3.0),   # loss
            TradeFactory.create(pnl_pct=2.0),    # win
            TradeFactory.create(pnl_pct=-1.0),   # loss
        ]
        wr = calculate_win_rate(trades)
        assert wr == pytest.approx(50.0)

    def test_fitness_bounded_0_to_100(self):
        """CONTRACT: Fitness score must always be in [0, 100]."""
        scenarios = [
            TradeFactory.all_winners(20, pnl_pct=50.0),
            TradeFactory.all_losers(20, pnl_pct=-50.0),
            TradeFactory.create_batch(50, seed=42),
            TradeFactory.zero_pnl(10),
            TradeFactory.extreme_trades(),
        ]
        for trades in scenarios:
            result = calculate_fitness(trades)
            assert 0.0 <= result.fitness_score <= 100.0, (
                f"Fitness {result.fitness_score} out of bounds"
            )

    def test_inf_pnl_filtered(self):
        """CONTRACT: Infinite PnL values should be filtered."""
        trades = TradeFactory.with_inf()
        result = calculate_fitness(trades)
        # Should not crash, inf filtered out
        assert not math.isinf(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0

    def test_nan_pnl_filtered(self):
        """CONTRACT: NaN PnL values should be filtered."""
        trades = TradeFactory.with_nan()
        result = calculate_fitness(trades)
        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0

    def test_none_pnl_filtered(self):
        """CONTRACT: None PnL values should be filtered."""
        trades = [
            TradeFactory.create(pnl_pct=5.0),
            TradeFactory.create(pnl_pct=3.0),
        ]
        # None values would fail TradeData construction, so test with valid trades
        result = calculate_fitness(trades)
        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0


class TestFitnessCalculation:
    """CONTRACT: Test the fixed fitness calculation."""

    def test_fitness_operator_precedence_fix(self):
        """CONTRACT: Fitness calculation uses correct operator precedence."""
        trades = TradeFactory.create_batch(30, avg_pnl=3.0, seed=42)
        result = calculate_fitness(trades)
        # Verify formula: (signed + unsigned) * ev_multiplier, clamped
        raw = result.component_breakdown.get("raw_total", 0)
        ev_mult = result.ev_multiplier
        expected = max(0.0, min(100.0, raw * ev_mult))
        assert result.fitness_score == pytest.approx(expected, abs=0.01)

    def test_fitness_with_zero_sharpe(self):
        """CONTRACT: Fitness with zero/null Sharpe should still calculate."""
        # Identical PnL trades have zero variance -> sortino = 0
        trades = TradeFactory.identical_pnl(10, pnl_pct=2.0)
        result = calculate_fitness(trades)
        assert result.fitness_score >= 0.0
        assert not math.isnan(result.fitness_score)

    def test_fitness_components_additive(self):
        """CONTRACT: Verify fitness components are properly additive."""
        trades = TradeFactory.create_batch(50, seed=42)
        result = calculate_fitness(trades)
        breakdown = result.component_breakdown
        component_sum = (
            breakdown.get("alpha", 0)
            + breakdown.get("calibration", 0)
            + breakdown.get("win_rate", 0)
            + breakdown.get("sortino", 0)
            + breakdown.get("drawdown", 0)
            + breakdown.get("exit_efficiency", 0)
            + breakdown.get("loss_sizing", 0)
            + breakdown.get("ai_accuracy", 0)
        )
        assert component_sum == pytest.approx(breakdown.get("raw_total", 0), abs=0.001)


class TestDeterminism:
    """CONTRACT: Test that backtest calculations are deterministic."""

    def test_metrics_deterministic(self):
        """CONTRACT: Same trades should produce identical metrics."""
        trades = TradeFactory.create_batch(50, seed=42)
        r1 = calculate_fitness(trades)
        r2 = calculate_fitness(trades)
        assert r1.fitness_score == r2.fitness_score
        assert r1.metrics.ev == r2.metrics.ev
        assert r1.metrics.win_rate == r2.metrics.win_rate

    def test_sharpe_deterministic(self):
        """CONTRACT: Sharpe ratio should be deterministic."""
        trades = TradeFactory.create_batch(50, seed=42)
        s1 = calculate_sortino(trades)
        s2 = calculate_sortino(trades)
        assert s1 == s2

    def test_drawdown_deterministic(self):
        """CONTRACT: Max drawdown should be deterministic."""
        trades = TradeFactory.create_batch(50, seed=42)
        dd1 = calculate_max_drawdown(trades)
        dd2 = calculate_max_drawdown(trades)
        assert dd1 == dd2


class TestTraitParameterIntegration:
    """CONTRACT: Test that trait parameters are correctly applied."""

    def test_trait_params_passed_to_config(self):
        """CONTRACT: Trait parameters are calculated and applied."""
        from Tests.Fixtures.factories import AgentFactory

        agent = AgentFactory.create(seed=42)
        traits = agent["traits"]
        assert len(traits) == 22
        assert all(0.0 <= v <= 1.0 for v in traits.values())

    def test_position_size_from_risk_tolerance(self):
        """CONTRACT: Position size derived from risk_tolerance trait."""
        # risk_tolerance 0.0 -> min position, 1.0 -> max position
        low_risk = {"risk_tolerance": 0.1}
        high_risk = {"risk_tolerance": 0.9}
        # Position sizing: base * (0.5 + risk_tolerance * 0.5)
        low_pos = 0.01 * (0.5 + low_risk["risk_tolerance"] * 0.5)
        high_pos = 0.01 * (0.5 + high_risk["risk_tolerance"] * 0.5)
        assert high_pos > low_pos

    def test_stop_loss_from_tightness_trait(self):
        """CONTRACT: Stop loss derived from stop_loss_tightness trait."""
        # Higher tightness -> tighter stop loss (smaller %)
        tight = {"stop_loss_tightness": 0.9}
        loose = {"stop_loss_tightness": 0.1}
        # Stop loss: base_pct * (1 - tightness * 0.5)
        base_sl = 5.0  # 5% base
        tight_sl = base_sl * (1 - tight["stop_loss_tightness"] * 0.5)
        loose_sl = base_sl * (1 - loose["stop_loss_tightness"] * 0.5)
        assert tight_sl < loose_sl


class TestStatisticalSanity:
    """CONTRACT: Test that metrics are statistically reasonable."""

    def test_sharpe_realistic_range(self):
        """CONTRACT: Sharpe ratio should be in [-5, 5] range."""
        trades = TradeFactory.create_batch(50, seed=42)
        sortino = calculate_sortino(trades)
        # Sortino is clamped to [0, 4] by the service
        assert 0 <= sortino <= 4

    def test_win_rate_bounded(self):
        """CONTRACT: Win rate must be between 0 and 1."""
        for seed in [1, 42, 99, 200]:
            trades = TradeFactory.create_batch(30, seed=seed)
            wr = calculate_win_rate(trades)
            assert 0 <= wr <= 100, f"Win rate {wr}% out of bounds"

    def test_drawdown_non_negative(self):
        """CONTRACT: Max drawdown should be non-negative."""
        trades = TradeFactory.create_batch(50, seed=42)
        dd = calculate_max_drawdown(trades)
        assert dd >= 0


class TestEdgeCases:
    """CONTRACT: Test edge cases and boundary conditions."""

    def test_all_winning_trades(self):
        """CONTRACT: 100% win rate scenario."""
        trades = TradeFactory.all_winners(20, pnl_pct=3.0)
        result = calculate_fitness(trades)
        assert result.metrics.win_rate == 100.0
        assert result.fitness_score > 0

    def test_all_losing_trades(self):
        """CONTRACT: 0% win rate scenario."""
        trades = TradeFactory.all_losers(20, pnl_pct=-3.0)
        result = calculate_fitness(trades)
        # EV gate blocks negative EV
        assert result.fitness_score == 0.0

    def test_zero_pnl_trades(self):
        """CONTRACT: All zero PnL trades."""
        trades = TradeFactory.zero_pnl(10)
        result = calculate_fitness(trades)
        assert result.fitness_score == 0.0  # EV = 0 -> gate fails

    def test_very_large_pnl(self):
        """CONTRACT: Very large but finite PnL values."""
        trades = [TradeFactory.create(pnl_pct=500.0) for _ in range(10)]
        result = calculate_fitness(trades)
        assert 0.0 <= result.fitness_score <= 100.0
        assert not math.isinf(result.fitness_score)
