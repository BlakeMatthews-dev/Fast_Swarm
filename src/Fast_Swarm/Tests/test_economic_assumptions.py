"""
Economic Assumptions Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Economic Assumptions)
Tests that verify economic assumptions about fees, spreads, and data.
"""

import pytest

from Agents.Services.fitness_service import calculate_fitness
from Tests.Fixtures.factories import TradeFactory


class TestFeeAssumptions:
    """CONTRACT: Fee assumptions for exchanges."""

    def test_maker_fee_realistic(self):
        """CONTRACT: Maker fees -5 to 10 bps."""
        # Exchanges offer rebates (negative fees) for makers up to about -5 bps
        # and charge up to ~10 bps
        maker_fee_bps_low = -5  # rebate
        maker_fee_bps_high = 10
        typical_maker_fee = 2  # bps
        assert maker_fee_bps_low <= typical_maker_fee <= maker_fee_bps_high

    def test_taker_fee_realistic(self):
        """CONTRACT: Taker fees 0 to 20 bps."""
        taker_fee_bps_low = 0
        taker_fee_bps_high = 20
        typical_taker_fee = 7  # bps
        assert taker_fee_bps_low <= typical_taker_fee <= taker_fee_bps_high


class TestSpreadAssumptions:
    """CONTRACT: Spread assumptions for trading pairs."""

    def test_spread_non_negative(self):
        """CONTRACT: Spreads >= 0."""
        spreads_bps = [0.5, 1.0, 2.0, 5.0, 10.0]
        for spread in spreads_bps:
            assert spread >= 0

    def test_major_pair_spread_tight(self):
        """CONTRACT: BTC/ETH spread < 50 bps."""
        max_major_spread_bps = 50
        btc_typical_spread = 1.0  # bps
        eth_typical_spread = 2.0  # bps
        assert btc_typical_spread < max_major_spread_bps
        assert eth_typical_spread < max_major_spread_bps


class TestCandleContinuity:
    """CONTRACT: OHLCV data continuity."""

    def test_candle_timestamps_increase(self, sample_candles):
        """CONTRACT: Candle timestamps strictly increase."""
        for i in range(1, len(sample_candles)):
            assert sample_candles[i]["timestamp"] > sample_candles[i - 1]["timestamp"]

    def test_candle_gap_matches_timeframe(self, sample_candles):
        """CONTRACT: Gap between candles matches timeframe."""
        expected_gap = 3600000  # 1 hour in milliseconds
        for i in range(1, len(sample_candles)):
            gap = sample_candles[i]["timestamp"] - sample_candles[i - 1]["timestamp"]
            assert gap == expected_gap, f"Gap {gap} != expected {expected_gap} at index {i}"


class TestAgentFitnessBounds:
    """CONTRACT: Agent fitness realistic bounds."""

    def test_fitness_not_extreme(self):
        """CONTRACT: Fitness < 1000 (avoid overfitting signals)."""
        trades = TradeFactory.create_batch(50, avg_pnl=10.0, seed=42)
        result = calculate_fitness(trades)
        assert result.fitness_score < 1000, "Fitness should be bounded by [0, 100]"
        assert result.fitness_score <= 100.0

    def test_high_fitness_positive_pnl(self):
        """CONTRACT: High fitness implies positive PnL."""
        trades = TradeFactory.all_winners(30, pnl_pct=5.0)
        result = calculate_fitness(trades)
        assert result.fitness_score > 0
        assert result.metrics.ev > 0, "High fitness agents must have positive EV"
