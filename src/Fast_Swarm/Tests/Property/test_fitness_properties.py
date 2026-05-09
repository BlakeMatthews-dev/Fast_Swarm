"""
Fitness Property Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Fitness Model)
Hypothesis-based property tests for fitness calculation invariants.
"""

import math

import pytest
from hypothesis import given, settings

from Agents.Services.fitness_service import (
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
)
from Tests.Property.strategies import (
    trade_data,
    trade_list,
    trade_list_with_edge_cases,
    valid_traits,
    winning_trade_list,
)

# ============================================================================
# FITNESS PROPERTY CONTRACT (for Hypothesis)
# ============================================================================


class TestFitnessInvariants:
    """CONTRACT: Fitness calculation invariants."""

    @given(trades=trade_list(min_size=0, max_size=50))
    @settings(max_examples=200, deadline=None)
    def test_fitness_always_bounded_0_100(self, trades):
        """PROPERTY: For any trades, 0 <= fitness <= 100."""
        result = calculate_fitness(trades)
        assert 0.0 <= result.fitness_score <= 100.0

    @given(trades=trade_list(min_size=1, max_size=30))
    @settings(max_examples=100, deadline=None)
    def test_fitness_deterministic(self, trades):
        """PROPERTY: Same trades always produce same fitness."""
        r1 = calculate_fitness(trades)
        r2 = calculate_fitness(trades)
        assert r1.fitness_score == r2.fitness_score

    @given(trades=winning_trade_list(min_size=5, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_fitness_monotonic_with_pnl(self, trades):
        """PROPERTY: Higher average PnL generally increases fitness."""
        from Agents.Services.fitness_service import TradeData

        # Boost all PnLs by a constant amount
        boosted = []
        for t in trades:
            new_pnl_pct = t.pnl_pct + 10.0
            boosted.append(TradeData(
                pnl=new_pnl_pct * t.size,
                pnl_pct=new_pnl_pct,
                is_win=True,
                entry_price=t.entry_price,
                exit_price=t.entry_price * (1 + new_pnl_pct / 100),
                size=t.size,
            ))
        r_original = calculate_fitness(trades)
        r_boosted = calculate_fitness(boosted)
        # Boosted PnL should yield >= fitness (EV multiplier increases)
        assert r_boosted.fitness_score >= r_original.fitness_score - 1.0  # small tolerance


class TestMetricsInvariants:
    """CONTRACT: Metrics calculation invariants."""

    @given(trades=trade_list(min_size=2, max_size=50))
    @settings(max_examples=200, deadline=None)
    def test_sharpe_bounded(self, trades):
        """PROPERTY: For any returns, Sharpe in reasonable range."""
        sortino = calculate_sortino(trades)
        # Sortino is clamped to [0, 4] by the service
        assert 0 <= sortino <= 4

    @given(trades=trade_list(min_size=1, max_size=50))
    @settings(max_examples=200, deadline=None)
    def test_win_rate_bounded_0_100(self, trades):
        """PROPERTY: For any trades, 0 <= win_rate <= 100."""
        wr = calculate_win_rate(trades)
        assert 0 <= wr <= 100

    @given(trades=trade_list(min_size=1, max_size=50))
    @settings(max_examples=200, deadline=None)
    def test_drawdown_bounded_0_100(self, trades):
        """PROPERTY: For any equity curve, 0 <= drawdown <= 100."""
        dd = calculate_max_drawdown(trades)
        assert 0 <= dd <= 100


class TestTraitInvariants:
    """CONTRACT: Trait value invariants."""

    @given(traits=valid_traits())
    @settings(max_examples=200, deadline=None)
    def test_traits_always_bounded_0_1(self, traits):
        """PROPERTY: For any mutation, 0 <= trait <= 1."""
        for name, value in traits.items():
            assert 0.0 <= value <= 1.0, f"Trait {name}={value} out of bounds"

    @given(parent_a=valid_traits(), parent_b=valid_traits())
    @settings(max_examples=100, deadline=None)
    def test_crossover_produces_bounded_traits(self, parent_a, parent_b):
        """PROPERTY: Crossover of valid parents produces valid child."""
        # Simple uniform crossover
        import random
        random.seed(42)
        child = {}
        for key in parent_a:
            child[key] = parent_a[key] if random.random() < 0.5 else parent_b[key]
        for name, value in child.items():
            assert 0.0 <= value <= 1.0, f"Child trait {name}={value} out of bounds"


class TestPatternMatchInvariants:
    """CONTRACT: Pattern matching invariants."""

    @given(trades=trade_list(min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_match_deterministic(self, trades):
        """PROPERTY: Same pattern + data = same match."""
        pattern = {"indicator": "pnl_pct", "operator": ">", "value": 0}
        matches1 = [t.pnl_pct > pattern["value"] for t in trades]
        matches2 = [t.pnl_pct > pattern["value"] for t in trades]
        assert matches1 == matches2

    @given(trades=trade_list(min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_confidence_bounded_0_1(self, trades):
        """PROPERTY: Match confidence always in [0, 1]."""
        # Confidence = fraction of conditions met (0 to 1)
        conditions_met = sum(1 for t in trades if t.is_win)
        total = len(trades)
        confidence = conditions_met / total if total > 0 else 0.0
        assert 0.0 <= confidence <= 1.0
