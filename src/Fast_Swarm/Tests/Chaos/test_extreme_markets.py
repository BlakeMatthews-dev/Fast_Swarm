"""
Extreme Market Conditions Tests - CHAOS ENGINEER

MASTER TEST ADMIN DECREE: Test the system under market stress.
These tests simulate extreme but realistic market conditions.

"The market can remain irrational longer than you can remain solvent."
"""

import math
from dataclasses import dataclass

import pytest

from Agents.Services.fitness_service import TradeData, calculate_fitness
from Tests.Fixtures.factories import TradeFactory

# =============================================================================
# EXTREME MARKET SCENARIOS
# =============================================================================


@dataclass
class MarketScenario:
    """Definition of an extreme market condition."""

    name: str
    description: str
    trades: list[TradeData]


def create_flash_crash_trades(count: int = 20) -> list[TradeData]:
    """
    Simulate a 50% flash crash scenario.

    Rapid losses followed by partial recovery.
    """
    trades = []

    # Initial winning trades (before crash)
    for _ in range(5):
        trades.append(TradeFactory.create(pnl_pct=2.0))

    # Flash crash - rapid consecutive losses
    for i in range(10):
        # Losses get progressively worse
        loss_pct = -5.0 - (i * 2)  # -5% to -23%
        trades.append(TradeFactory.create(pnl_pct=loss_pct))

    # Partial recovery
    for _ in range(5):
        trades.append(TradeFactory.create(pnl_pct=3.0))

    return trades


def create_liquidity_crisis_trades(count: int = 15) -> list[TradeData]:
    """
    Simulate a liquidity crisis with massive slippage.

    Entry prices are good but exits are terrible due to slippage.
    """
    trades = []

    for i in range(count):
        # Even "winning" trades have massive slippage eating profits
        expected_pnl = 3.0 if i % 3 != 0 else -2.0
        slippage_impact = -5.0  # 5% slippage on every trade
        actual_pnl = expected_pnl + slippage_impact

        trades.append(TradeFactory.create(pnl_pct=actual_pnl))

    return trades


def create_whipsaw_trades(count: int = 20) -> list[TradeData]:
    """
    Simulate whipsaw market - constant stop-outs.

    Pattern: small loss, small loss, small loss...
    """
    trades = []

    for _ in range(count):
        # Constant small losses from stop-outs
        loss = -1.5  # Stop loss hit
        trades.append(TradeFactory.create(pnl_pct=loss))

    return trades


def create_gap_event_trades(count: int = 10) -> list[TradeData]:
    """
    Simulate gap events where price jumps overnight.

    Stops are jumped, losses exceed expected max.
    """
    trades = []

    for i in range(count):
        if i % 3 == 0:
            # Gap against position - stop jumped
            loss = -15.0  # Way past stop loss
            trades.append(TradeFactory.create(pnl_pct=loss))
        elif i % 3 == 1:
            # Gap in favor - unexpected win
            win = 10.0
            trades.append(TradeFactory.create(pnl_pct=win))
        else:
            # Normal trade
            trades.append(TradeFactory.create(pnl_pct=1.5))

    return trades


def create_trending_market_trades(count: int = 30) -> list[TradeData]:
    """
    Simulate a strong trending market.

    High win rate, compounding gains.
    """
    trades = []

    for i in range(count):
        if i % 5 == 0:
            # Occasional pullback loss
            trades.append(TradeFactory.create(pnl_pct=-2.0))
        else:
            # Trend-following wins
            win = 3.0 + (i * 0.1)  # Compounding
            trades.append(TradeFactory.create(pnl_pct=win))

    return trades


def create_ranging_market_trades(count: int = 30) -> list[TradeData]:
    """
    Simulate a ranging/choppy market.

    50/50 win rate, small moves.
    """
    trades = []

    for i in range(count):
        if i % 2 == 0:
            trades.append(TradeFactory.create(pnl_pct=1.5))
        else:
            trades.append(TradeFactory.create(pnl_pct=-1.5))

    return trades


# All extreme scenarios
EXTREME_SCENARIOS = {
    "flash_crash": MarketScenario(
        name="Flash Crash",
        description="50% crash in 48 hours",
        trades=create_flash_crash_trades(),
    ),
    "liquidity_crisis": MarketScenario(
        name="Liquidity Crisis",
        description="Massive slippage on all trades",
        trades=create_liquidity_crisis_trades(),
    ),
    "whipsaw": MarketScenario(
        name="Whipsaw Market",
        description="Constant stop-outs",
        trades=create_whipsaw_trades(),
    ),
    "gap_event": MarketScenario(
        name="Gap Events",
        description="Overnight price gaps",
        trades=create_gap_event_trades(),
    ),
    "trending": MarketScenario(
        name="Trending Market",
        description="Strong trend with pullbacks",
        trades=create_trending_market_trades(),
    ),
    "ranging": MarketScenario(
        name="Ranging Market",
        description="Choppy, directionless market",
        trades=create_ranging_market_trades(),
    ),
}


# =============================================================================
# TEST: Fitness Survives Extreme Markets
# =============================================================================


class TestExtremeMarketConditions:
    """CONTRACT: Fitness calculation survives all extreme market conditions."""

    @pytest.mark.chaos
    @pytest.mark.parametrize("scenario_name", list(EXTREME_SCENARIOS.keys()))
    def test_fitness_survives_scenario(self, scenario_name):
        """
        CHAOS: Fitness must not crash or produce invalid output in extreme scenarios.
        """
        scenario = EXTREME_SCENARIOS[scenario_name]
        result = calculate_fitness(scenario.trades)

        # Must not crash
        assert result is not None, f"Fitness returned None for {scenario_name}"

        # Must produce valid fitness
        assert not math.isnan(result.fitness_score), f"Fitness is NaN for {scenario_name}"
        assert math.isfinite(result.fitness_score), f"Fitness is infinite for {scenario_name}"
        assert 0.0 <= result.fitness_score <= 100.0, f"Fitness {result.fitness_score} out of bounds for {scenario_name}"

    @pytest.mark.chaos
    @pytest.mark.parametrize("scenario_name", list(EXTREME_SCENARIOS.keys()))
    def test_metrics_valid_in_scenario(self, scenario_name):
        """
        CHAOS: All metrics must be valid (not NaN/Inf) in extreme scenarios.
        """
        scenario = EXTREME_SCENARIOS[scenario_name]
        result = calculate_fitness(scenario.trades)

        # Check all key metrics (ev, win_rate, etc. are inside result.metrics)
        metrics_to_check = [
            ("fitness_score", result.fitness_score),
            ("ev", result.metrics.ev),
            ("win_rate", result.metrics.win_rate),
            ("sortino", result.metrics.sortino),
            ("max_drawdown", result.metrics.max_drawdown),
        ]

        for metric_name, value in metrics_to_check:
            assert not math.isnan(value), f"{metric_name} is NaN in {scenario_name}"
            assert math.isfinite(value), f"{metric_name} is infinite in {scenario_name}"

    @pytest.mark.chaos
    def test_flash_crash_low_fitness(self):
        """
        CHAOS: Flash crash should produce low/zero fitness due to negative EV.

        Note: When EV gate triggers (negative EV), metrics are zeroed.
        We test the FITNESS outcome, not raw metrics.
        """
        scenario = EXTREME_SCENARIOS["flash_crash"]
        result = calculate_fitness(scenario.trades)

        # Flash crash with heavy losses should have low fitness
        assert result.fitness_score < 50.0, f"Flash crash fitness {result.fitness_score} should be low"
        assert result.tier in ("DIES", "SURVIVES"), "Flash crash should not produce PROMOTED tier"

    @pytest.mark.chaos
    def test_whipsaw_zero_fitness(self):
        """
        CHAOS: Whipsaw market (all losses) triggers EV gate = zero fitness.

        The EV gate zeros everything when EV <= 0, so we verify the OUTCOME.
        """
        scenario = EXTREME_SCENARIOS["whipsaw"]
        result = calculate_fitness(scenario.trades)

        # Whipsaw (constant losses) triggers EV gate
        assert result.fitness_score == 0.0, f"Whipsaw (all losses) should have zero fitness, got {result.fitness_score}"
        assert result.tier == "DIES", f"Whipsaw should be DIES tier, got {result.tier}"

    @pytest.mark.chaos
    def test_trending_market_positive_ev(self):
        """
        CHAOS: Trending market (mostly wins) should have positive EV.
        """
        scenario = EXTREME_SCENARIOS["trending"]
        result = calculate_fitness(scenario.trades)

        assert result.metrics.ev > 0, f"Trending EV {result.metrics.ev} should be positive"
        assert result.metrics.win_rate > 70.0, f"Trending win rate {result.metrics.win_rate}% should be high"


# =============================================================================
# TEST: Stress Combinations
# =============================================================================


class TestStressCombinations:
    """Test combinations of stress scenarios."""

    @pytest.mark.chaos
    def test_mixed_extreme_scenarios(self):
        """
        CHAOS: Mixed trades from multiple extreme scenarios.
        """
        mixed_trades = []
        for scenario in EXTREME_SCENARIOS.values():
            mixed_trades.extend(scenario.trades[:5])  # First 5 from each

        result = calculate_fitness(mixed_trades)

        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0

    @pytest.mark.chaos
    def test_repeated_flash_crashes(self):
        """
        CHAOS: Multiple flash crashes in sequence (worst case).

        EV gate will zero everything, so we test the fitness outcome.
        """
        trades = []
        for _ in range(3):  # 3 flash crashes
            trades.extend(create_flash_crash_trades())

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        # Multiple crashes = net negative = EV gate = low/zero fitness
        assert result.fitness_score < 30.0, f"Multiple crashes should have low fitness, got {result.fitness_score}"

    @pytest.mark.chaos
    def test_alternating_trending_whipsaw(self):
        """
        CHAOS: Alternating between trending and whipsaw (regime changes).
        """
        trades = []
        for i in range(5):
            if i % 2 == 0:
                trades.extend(create_trending_market_trades(10))
            else:
                trades.extend(create_whipsaw_trades(10))

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0


# =============================================================================
# TEST: Edge Value Combinations
# =============================================================================


class TestEdgeValueCombinations:
    """Test trades with edge case PnL values."""

    @pytest.mark.chaos
    def test_tiny_pnl_values(self):
        """
        CHAOS: Very small PnL values (near-zero).
        """
        trades = [
            TradeFactory.create(pnl_pct=0.001),
            TradeFactory.create(pnl_pct=-0.001),
            TradeFactory.create(pnl_pct=0.0001),
            TradeFactory.create(pnl_pct=-0.0001),
        ] * 10

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        assert math.isfinite(result.fitness_score)

    @pytest.mark.chaos
    def test_large_pnl_swings(self):
        """
        CHAOS: Large PnL swings (high volatility).
        """
        trades = []
        for i in range(20):
            if i % 2 == 0:
                trades.append(TradeFactory.create(pnl_pct=50.0))  # 50% win
            else:
                trades.append(TradeFactory.create(pnl_pct=-30.0))  # 30% loss

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0

    @pytest.mark.chaos
    def test_single_massive_winner(self):
        """
        CHAOS: Many small losses, one massive winner.
        """
        trades = [TradeFactory.create(pnl_pct=-2.0) for _ in range(19)]
        trades.append(TradeFactory.create(pnl_pct=100.0))  # 100% win

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        # Should still have positive EV due to massive winner

    @pytest.mark.chaos
    def test_single_massive_loser(self):
        """
        CHAOS: Many small winners, one massive loser.

        The massive loser may or may not trigger EV gate depending on
        whether net EV is still positive. Test that we get valid output.
        """
        trades = [TradeFactory.create(pnl_pct=2.0) for _ in range(19)]
        trades.append(TradeFactory.create(pnl_pct=-50.0))  # 50% loss

        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        assert 0.0 <= result.fitness_score <= 100.0
        # If net EV is negative, fitness will be 0; otherwise it will be reduced
        # The key is that it doesn't crash and produces valid output
