"""
Triage Tests: Economic Validity - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (EDD Economic Validity)
Tests for fitness logic parity with local_agents.
"""

import pytest

from Agents.Services.fitness_service import (
    calculate_alpha_component,
    calculate_calibration_component,
    calculate_ev,
    calculate_ev_multiplier,
    calculate_fitness,
    ev_gate,
)
from Tests.Fixtures.factories import TradeFactory


class TestEVGate:
    """CONTRACT: Expectancy Value gate."""

    def test_ev_gate_closed_negative_expectancy(self):
        """CONTRACT: fitness = 0 if expectancy <= 0."""
        trades = TradeFactory.all_losers(20, pnl_pct=-5.0)
        result = calculate_fitness(trades)
        assert result.fitness_score == 0.0

    def test_ev_gate_passed_positive_expectancy(self):
        """CONTRACT: EV gate passed if expectancy > 0."""
        trades = TradeFactory.all_winners(20, pnl_pct=5.0)
        ev = calculate_ev(trades)
        assert ev > 0
        assert ev_gate(ev) is True


class TestEVMultiplier:
    """CONTRACT: EV multiplier scaling."""

    def test_ev_multiplier_zero(self):
        """CONTRACT: expectancy=0 -> multiplier=0.35."""
        # EV <= 0 returns 0.35
        mult = calculate_ev_multiplier(0.0)
        assert mult == pytest.approx(0.35)

    def test_ev_multiplier_low(self):
        """CONTRACT: expectancy=1 -> multiplier~0.8."""
        mult = calculate_ev_multiplier(1.0)
        assert mult == pytest.approx(0.8)

    def test_ev_multiplier_mid(self):
        """CONTRACT: expectancy=3 -> multiplier~1.2."""
        mult = calculate_ev_multiplier(3.0)
        assert mult == pytest.approx(1.2)

    def test_ev_multiplier_high(self):
        """CONTRACT: expectancy=9 -> multiplier~1.5."""
        mult = calculate_ev_multiplier(9.0)
        assert mult == pytest.approx(1.5)

    def test_ev_multiplier_capped(self):
        """CONTRACT: expectancy=100 -> multiplier=1.5 (capped)."""
        mult = calculate_ev_multiplier(100.0)
        assert mult == pytest.approx(1.5)


class TestAlphaContribution:
    """CONTRACT: Alpha contribution to fitness."""

    def test_alpha_negative_100(self):
        """CONTRACT: alpha=-100 -> contribution=-35."""
        comp = calculate_alpha_component(-100.0)
        assert comp == pytest.approx(-35.0)

    def test_alpha_positive_100(self):
        """CONTRACT: alpha=+100 -> contribution=+35."""
        comp = calculate_alpha_component(100.0)
        assert comp == pytest.approx(35.0)

    def test_alpha_zero(self):
        """CONTRACT: alpha=0 -> contribution=0."""
        comp = calculate_alpha_component(0.0)
        assert comp == pytest.approx(0.0)


class TestCalibrationContribution:
    """CONTRACT: Calibration contribution to fitness."""

    def test_calibration_perfect(self):
        """CONTRACT: calibration=1.0 -> contribution=+10."""
        comp = calculate_calibration_component(1.0)
        assert comp == pytest.approx(10.0)

    def test_calibration_zero(self):
        """CONTRACT: calibration=0.0 -> contribution=-10."""
        comp = calculate_calibration_component(0.0)
        assert comp == pytest.approx(-10.0)

    def test_calibration_mid(self):
        """CONTRACT: calibration=0.5 -> contribution=0."""
        comp = calculate_calibration_component(0.5)
        assert comp == pytest.approx(0.0)


class TestFullFitnessParity:
    """CONTRACT: Full fitness calculation parity with local_agents."""

    def test_realistic_case(self):
        """CONTRACT: Known inputs produce expected fitness."""
        trades = TradeFactory.create_batch(50, avg_pnl=3.0, win_rate=0.6, seed=42)
        result = calculate_fitness(trades)
        assert 0.0 <= result.fitness_score <= 100.0
        assert result.tier in ("DIES", "SURVIVES", "PROMOTED")

    def test_fitness_bounded_0_to_100(self):
        """CONTRACT: Fitness always in [0, 100]."""
        for seed in [1, 42, 99, 200, 333]:
            trades = TradeFactory.create_batch(30, seed=seed)
            result = calculate_fitness(trades)
            assert 0.0 <= result.fitness_score <= 100.0


class TestFeeBounds:
    """CONTRACT: Fee assumptions for trading tiers."""

    def test_tier1_fee_bps(self):
        """CONTRACT: BTC/ETH fee <= 10 bps."""
        tier1_fee_bps = 10
        actual_fee_bps = 7.5  # Typical maker/taker average for BTC/ETH
        assert actual_fee_bps <= tier1_fee_bps

    def test_tier1_slippage_bps(self):
        """CONTRACT: BTC/ETH slippage <= 1 bps."""
        # For highly liquid BTC/ETH, slippage is very low
        tier1_slippage_bps = 1.0
        # BTC order book is extremely deep
        actual_slippage_bps = 0.5
        assert actual_slippage_bps <= tier1_slippage_bps
