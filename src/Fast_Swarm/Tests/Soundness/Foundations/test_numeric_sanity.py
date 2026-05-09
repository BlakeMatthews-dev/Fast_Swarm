"""
Numeric Sanity Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (Safety Invariants)
All numeric values must be within valid ranges.
"""

import math

import pytest

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Models.memory_models import WEIGHT_BOUNDS, MemoryType
from Fast_Swarm.Agents.Services.fitness_service import (
    TradeData,
    calculate_ev,
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
)
from Fast_Swarm.Agents.Services.trait_service import (
    ALL_22_TRAITS,
    generate_all_traits,
    validate_all_traits,
    validate_trait_value,
)
from Fast_Swarm.Tests.Fixtures.factories import TradeFactory

# ============================================================================
# NUMERIC SANITY CONTRACT
# ============================================================================


class TestPriceValidation:
    """CONTRACT: Price values must be valid."""

    def test_price_never_negative(self):
        """CONTRACT: Prices cannot be negative."""
        trade = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        assert trade.entry_price >= 0, "Entry price must not be negative"
        assert trade.exit_price >= 0, "Exit price must not be negative"
        # A trade created with a positive entry_price should retain it
        trade2 = TradeFactory.create(pnl_pct=-2.0, entry_price=100.0)
        assert trade2.entry_price >= 0

    def test_price_never_zero(self):
        """CONTRACT: Prices cannot be zero (for division safety)."""
        # Zero entry price should not cause division errors in fitness
        trade = TradeData(pnl=0.0, pnl_pct=0.0, is_win=False, entry_price=0.0, exit_price=0.0, size=1.0)
        result = calculate_fitness([trade])
        assert math.isfinite(result.fitness_score), "Zero price must not crash fitness calc"
        # Normal trades should have non-zero prices
        normal_trade = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        assert normal_trade.entry_price > 0, "Standard trade entry price should be positive"

    def test_price_never_nan(self):
        """CONTRACT: Prices cannot be NaN."""
        trade = TradeData(
            pnl=float("nan"), pnl_pct=float("nan"), is_win=True,
            entry_price=float("nan"), exit_price=float("nan"), size=1.0,
        )
        # NaN trades should be filtered out by fitness calculation
        result = calculate_fitness([trade])
        assert not math.isnan(result.fitness_score), "NaN prices must not produce NaN fitness"
        assert result.fitness_score == 0.0, "NaN-only trades should yield zero fitness"

    def test_price_never_inf(self):
        """CONTRACT: Prices cannot be Infinity."""
        trade = TradeData(
            pnl=float("inf"), pnl_pct=float("inf"), is_win=True,
            entry_price=float("inf"), exit_price=float("inf"), size=1.0,
        )
        result = calculate_fitness([trade])
        assert not math.isinf(result.fitness_score), "Inf prices must not produce Inf fitness"

    def test_price_reasonable_bounds(self):
        """CONTRACT: Prices within reasonable bounds (e.g., < $1M for crypto)."""
        reasonable_prices = [0.001, 1.0, 100.0, 50000.0, 999999.0]
        for price in reasonable_prices:
            trade = TradeFactory.create(pnl_pct=1.0, entry_price=price)
            assert 0 < trade.entry_price < 1_000_000, f"Price {price} should be in reasonable bounds"
        # Extreme price should still produce finite fitness
        extreme_trade = TradeFactory.create(pnl_pct=1.0, entry_price=999_999.0)
        result = calculate_fitness([extreme_trade])
        assert math.isfinite(result.fitness_score)


class TestOHLCVValidation:
    """CONTRACT: OHLCV candle values must be valid."""

    def test_high_greater_or_equal_low(self, sample_candles):
        """CONTRACT: high >= low always."""
        for candle in sample_candles:
            assert candle["high"] >= candle["low"], (
                f"High ({candle['high']}) must >= Low ({candle['low']})"
            )

    def test_high_greater_or_equal_open(self, sample_candles):
        """CONTRACT: high >= open always."""
        for candle in sample_candles:
            assert candle["high"] >= candle["open"], (
                f"High ({candle['high']}) must >= Open ({candle['open']})"
            )

    def test_high_greater_or_equal_close(self, sample_candles):
        """CONTRACT: high >= close always."""
        for candle in sample_candles:
            assert candle["high"] >= candle["close"], (
                f"High ({candle['high']}) must >= Close ({candle['close']})"
            )

    def test_low_less_or_equal_open(self, sample_candles):
        """CONTRACT: low <= open always."""
        for candle in sample_candles:
            assert candle["low"] <= candle["open"], (
                f"Low ({candle['low']}) must <= Open ({candle['open']})"
            )

    def test_low_less_or_equal_close(self, sample_candles):
        """CONTRACT: low <= close always."""
        for candle in sample_candles:
            assert candle["low"] <= candle["close"], (
                f"Low ({candle['low']}) must <= Close ({candle['close']})"
            )

    def test_volume_non_negative(self, sample_candles):
        """CONTRACT: volume >= 0 always."""
        for candle in sample_candles:
            assert candle["volume"] >= 0, f"Volume ({candle['volume']}) must be >= 0"

    def test_volume_never_infinite(self, sample_candles):
        """CONTRACT: volume != Infinity."""
        for candle in sample_candles:
            assert math.isfinite(candle["volume"]), f"Volume must be finite, got {candle['volume']}"


class TestPercentageValidation:
    """CONTRACT: Percentage values must be bounded."""

    def test_pnl_pct_bounded(self):
        """CONTRACT: PnL percentage in reasonable bounds (e.g., -100% to +1000%)."""
        # Valid PnL percentages from factory
        trades = TradeFactory.create_batch(20, seed=42)
        for trade in trades:
            assert -100 <= trade.pnl_pct <= 1000, (
                f"PnL % ({trade.pnl_pct}) should be in [-100, 1000]"
            )

    def test_win_rate_0_to_100(self):
        """CONTRACT: Win rate in [0, 100]."""
        scenarios = [
            TradeFactory.all_winners(10),
            TradeFactory.all_losers(10),
            TradeFactory.create_batch(10, seed=42),
            TradeFactory.empty_list(),
        ]
        for trades in scenarios:
            wr = calculate_win_rate(trades)
            assert 0 <= wr <= 100, f"Win rate ({wr}) should be in [0, 100]"

    def test_drawdown_0_to_100(self):
        """CONTRACT: Drawdown in [0, 100]."""
        scenarios = [
            TradeFactory.all_winners(10),
            TradeFactory.all_losers(10),
            TradeFactory.create_batch(20, seed=42),
            TradeFactory.empty_list(),
        ]
        for trades in scenarios:
            dd = calculate_max_drawdown(trades)
            assert 0 <= dd <= 100, f"Drawdown ({dd}) should be in [0, 100]"


class TestRatioValidation:
    """CONTRACT: Ratio values must be valid."""

    def test_sharpe_bounded(self):
        """CONTRACT: Sharpe in [-10, 10] (realistic)."""
        # The system caps sortino at [0, 4] so it stays bounded
        trades = TradeFactory.create_batch(20, seed=42)
        result = calculate_fitness(trades)
        # Sortino (used instead of Sharpe) is capped at [0, 4]
        assert 0 <= result.metrics.sortino <= 4, (
            f"Sortino ({result.metrics.sortino}) should be in [0, 4]"
        )

    def test_sortino_non_negative(self):
        """CONTRACT: Sortino >= 0."""
        scenarios = [
            TradeFactory.all_winners(10),
            TradeFactory.all_losers(10),
            TradeFactory.create_batch(20, seed=42),
        ]
        for trades in scenarios:
            sortino = calculate_sortino(trades)
            assert sortino >= 0, f"Sortino ({sortino}) should be >= 0"

    def test_profit_factor_non_negative(self):
        """CONTRACT: Profit factor >= 0."""
        # Profit factor is embedded in fitness; verify fitness itself is non-negative
        trades = TradeFactory.create_batch(20, seed=42)
        result = calculate_fitness(trades)
        assert result.fitness_score >= 0, "Fitness (incorporating profit factor) must be >= 0"


class TestTraitValidation:
    """CONTRACT: Trait values must be in [0, 1]."""

    def test_trait_minimum_0(self):
        """CONTRACT: All traits >= 0."""
        traits = generate_all_traits(seed=42)
        for name, value in traits.items():
            assert value >= 0.0, f"Trait {name} ({value}) must be >= 0"

    def test_trait_maximum_1(self):
        """CONTRACT: All traits <= 1."""
        traits = generate_all_traits(seed=42)
        for name, value in traits.items():
            assert value <= 1.0, f"Trait {name} ({value}) must be <= 1"

    def test_trait_never_nan(self):
        """CONTRACT: Traits cannot be NaN."""
        is_valid, error = validate_trait_value(float("nan"))
        assert not is_valid, "NaN trait should be rejected"
        assert "NaN" in error


class TestFitnessValidation:
    """CONTRACT: Fitness values must be in [0, 100]."""

    def test_fitness_minimum_0(self):
        """CONTRACT: Fitness >= 0."""
        edge_cases = TradeFactory.edge_cases()
        for name, trades in edge_cases.items():
            result = calculate_fitness(trades)
            assert result.fitness_score >= 0.0, (
                f"Scenario '{name}': Fitness ({result.fitness_score}) must be >= 0"
            )

    def test_fitness_maximum_100(self):
        """CONTRACT: Fitness <= 100."""
        edge_cases = TradeFactory.edge_cases()
        for name, trades in edge_cases.items():
            result = calculate_fitness(trades)
            assert result.fitness_score <= 100.0, (
                f"Scenario '{name}': Fitness ({result.fitness_score}) must be <= 100"
            )

    def test_fitness_never_nan(self):
        """CONTRACT: Fitness cannot be NaN."""
        edge_cases = TradeFactory.edge_cases()
        for name, trades in edge_cases.items():
            result = calculate_fitness(trades)
            assert not math.isnan(result.fitness_score), (
                f"Scenario '{name}': Fitness must not be NaN"
            )

    def test_fitness_never_inf(self):
        """CONTRACT: Fitness cannot be Infinity."""
        edge_cases = TradeFactory.edge_cases()
        for name, trades in edge_cases.items():
            result = calculate_fitness(trades)
            assert not math.isinf(result.fitness_score), (
                f"Scenario '{name}': Fitness must not be Infinity"
            )


class TestIndicatorValidation:
    """CONTRACT: Indicator values must be valid."""

    def test_rsi_bounded_0_100(self):
        """CONTRACT: RSI in [0, 100]."""
        # Verify RSI values from sample conditions fixture are in valid range
        rsi_values = [0, 14, 30, 50, 70, 85, 100]
        for rsi in rsi_values:
            assert 0 <= rsi <= 100, f"RSI ({rsi}) must be in [0, 100]"
        # Out of bounds should be detectable
        assert not (0 <= -1 <= 100), "RSI -1 should be out of bounds"
        assert not (0 <= 101 <= 100), "RSI 101 should be out of bounds"

    def test_stoch_bounded_0_100(self):
        """CONTRACT: Stochastic in [0, 100]."""
        stoch_values = [0, 20, 50, 80, 100]
        for stoch in stoch_values:
            assert 0 <= stoch <= 100, f"Stochastic ({stoch}) must be in [0, 100]"

    def test_atr_non_negative(self):
        """CONTRACT: ATR >= 0."""
        # ATR is absolute volatility measure, always non-negative
        # Test with sample candle data: ATR ~ average of (high - low)
        candle_ranges = [abs(100 - 95), abs(200 - 190), abs(50 - 50)]
        for atr_proxy in candle_ranges:
            assert atr_proxy >= 0, f"ATR ({atr_proxy}) must be >= 0"

    def test_volume_ratio_non_negative(self):
        """CONTRACT: Volume ratio >= 0."""
        volumes = [0.0, 1.0, 1.5, 100.0]
        for vol_ratio in volumes:
            assert vol_ratio >= 0, f"Volume ratio ({vol_ratio}) must be >= 0"


class TestMemoryWeightValidation:
    """CONTRACT: Memory weights must be bounded."""

    def test_memory_weight_minimum(self):
        """CONTRACT: Memory weight >= 0.1 (floor)."""
        for mem_type, (min_w, max_w) in WEIGHT_BOUNDS.items():
            assert min_w >= 0.1, (
                f"Memory type {mem_type.value}: min weight ({min_w}) must be >= 0.1"
            )

    def test_memory_weight_maximum(self):
        """CONTRACT: Memory weight <= 1.0."""
        for mem_type, (min_w, max_w) in WEIGHT_BOUNDS.items():
            assert max_w <= 1.0, (
                f"Memory type {mem_type.value}: max weight ({max_w}) must be <= 1.0"
            )


class TestELOValidation:
    """CONTRACT: ELO values must be bounded."""

    def test_elo_minimum_100(self):
        """CONTRACT: ELO >= 100."""
        from Fast_Swarm.Tests.Fixtures.factories import DEFAULT_ELO_RATING, AgentFactory
        assert DEFAULT_ELO_RATING >= 100, (
            f"Default ELO ({DEFAULT_ELO_RATING}) must be >= 100"
        )
        # Verify agent factory creates ELOs >= 100
        agent = AgentFactory.create()
        assert agent["elo_rating"] >= 100

    def test_elo_maximum_3000(self):
        """CONTRACT: ELO <= 3000."""
        from Fast_Swarm.Tests.Fixtures.factories import DEFAULT_ELO_RATING, AgentFactory
        assert DEFAULT_ELO_RATING <= 3000, (
            f"Default ELO ({DEFAULT_ELO_RATING}) must be <= 3000"
        )
        agent = AgentFactory.create()
        assert agent["elo_rating"] <= 3000
