"""
Fitness Property Tests - MASTER TEST ADMIN

INVARIANTS THAT MUST HOLD FOR ALL POSSIBLE INPUTS.
These are mathematical truths, not implementation details.

Using Hypothesis to bombard the code with chaos.
Target: 100,000+ examples per invariant.

JUST KEEP TESTING, JUST KEEP TESTING!
"""

import math
import os

# Import custom strategies
import sys
from datetime import timedelta

from hypothesis import Phase, assume, given, settings
from hypothesis import strategies as st

from Agents.Services.fitness_service import (
    calculate_ev,
    calculate_ev_multiplier,
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
    get_tier,
)

sys.path.insert(0, os.path.dirname(__file__))
from strategies import (
    ev_value,
    fitness_score,
    losing_trade_list,
    mixed_edge_case_trades,
    trade_list,
    trade_list_with_edge_cases,
    valid_traits,
    winning_trade_list,
)

# =============================================================================
# HYPOTHESIS PROFILES - Configure based on context
# =============================================================================

# War mode: Maximum examples, no deadline
settings.register_profile(
    "war",
    max_examples=100000,
    deadline=None,
    suppress_health_check=[],
    phases=[Phase.generate, Phase.shrink],
)

# CI mode: Reasonable examples, with deadline
settings.register_profile(
    "ci",
    max_examples=10000,
    deadline=timedelta(seconds=30),
)

# Dev mode: Fast iteration
settings.register_profile(
    "dev",
    max_examples=100,
    deadline=timedelta(seconds=5),
)

# Default to dev for normal test runs (use --hypothesis-profile=war for full)
settings.load_profile("dev")


# =============================================================================
# INVARIANT CONSTANTS
# =============================================================================

FITNESS_MIN = 0.0
FITNESS_MAX = 100.0

EV_MULTIPLIER_MIN = 0.35
EV_MULTIPLIER_MAX = 1.5

TRAIT_MIN = 0.0
TRAIT_MAX = 1.0

WIN_RATE_MIN = 0.0
WIN_RATE_MAX = 100.0

SORTINO_MAX = 4.0  # Capped value in fitness_service

TIER_VALUES = {"DIES", "SURVIVES", "PROMOTED"}


# =============================================================================
# TEST: Fitness Invariants
# =============================================================================


class TestFitnessInvariants:
    """CONTRACT: Fitness calculation invariants must hold for ALL inputs."""

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=1000)
    def test_fitness_always_bounded_0_100(self, trades):
        """
        INVARIANT: For any trade list, 0 <= fitness <= 100.

        This is a fundamental bound that must NEVER be violated.
        """
        result = calculate_fitness(trades)

        assert FITNESS_MIN <= result.fitness_score <= FITNESS_MAX, (
            f"Fitness {result.fitness_score} violates bounds [{FITNESS_MIN}, {FITNESS_MAX}]"
        )

    @given(trades=trade_list(min_size=1, max_size=50))
    @settings(max_examples=500)
    def test_fitness_deterministic(self, trades):
        """
        INVARIANT: Same trades always produce same fitness.

        Determinism is critical for reproducibility.
        """
        result1 = calculate_fitness(trades)
        result2 = calculate_fitness(trades)

        assert result1.fitness_score == result2.fitness_score, (
            f"Non-deterministic: {result1.fitness_score} != {result2.fitness_score}"
        )

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=1000)
    def test_fitness_never_nan(self, trades):
        """
        INVARIANT: Fitness is never NaN.

        NaN is a silent killer - it propagates and corrupts.
        """
        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score), "Fitness must never be NaN"

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=1000)
    def test_fitness_always_finite(self, trades):
        """
        INVARIANT: Fitness is always finite.

        Inf breaks comparisons and rankings.
        """
        result = calculate_fitness(trades)

        assert math.isfinite(result.fitness_score), f"Fitness must be finite, got {result.fitness_score}"

    @given(trades=trade_list_with_edge_cases(min_size=0, max_size=50))
    @settings(max_examples=500)
    def test_fitness_resilient_to_edge_cases(self, trades):
        """
        INVARIANT: Fitness handles edge cases gracefully.

        Even with NaN/Inf inputs, output must be valid.
        """
        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score), "Fitness must not be NaN"
        assert math.isfinite(result.fitness_score) or result.fitness_score == 0.0, (
            f"Fitness must be finite, got {result.fitness_score}"
        )
        assert FITNESS_MIN <= result.fitness_score <= FITNESS_MAX, f"Fitness {result.fitness_score} out of bounds"


# =============================================================================
# TEST: EV Multiplier Invariants
# =============================================================================


class TestEVMultiplierInvariants:
    """CONTRACT: EV multiplier invariants."""

    @given(ev=st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=1000)
    def test_ev_multiplier_always_bounded(self, ev):
        """
        INVARIANT: EV multiplier is always in [0.35, 1.5].

        This bound is critical for fitness scaling.
        """
        mult = calculate_ev_multiplier(ev)

        assert EV_MULTIPLIER_MIN <= mult <= EV_MULTIPLIER_MAX, (
            f"EV={ev}: Multiplier {mult} violates bounds [{EV_MULTIPLIER_MIN}, {EV_MULTIPLIER_MAX}]"
        )

    @given(ev=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_ev_multiplier_monotonic_positive(self, ev):
        """
        INVARIANT: Higher positive EV produces higher multiplier (within bounds).

        The multiplier should reward positive expectancy.
        """
        mult = calculate_ev_multiplier(ev)

        # At extreme positive EV, should be at max
        if ev >= 9:
            assert mult == EV_MULTIPLIER_MAX, f"EV={ev} should give max multiplier"

        # At zero or negative EV, should be at min
        if ev <= 0:
            assert mult == EV_MULTIPLIER_MIN, f"EV={ev} should give min multiplier"

    @given(ev1=ev_value(), ev2=ev_value())
    @settings(max_examples=500)
    def test_ev_multiplier_ordering(self, ev1, ev2):
        """
        INVARIANT: If ev1 < ev2, then multiplier(ev1) <= multiplier(ev2).

        Monotonicity ensures consistent incentives.
        """
        assume(ev1 < ev2)  # Only test when ev1 < ev2

        mult1 = calculate_ev_multiplier(ev1)
        mult2 = calculate_ev_multiplier(ev2)

        assert mult1 <= mult2, f"Monotonicity violated: mult({ev1})={mult1} > mult({ev2})={mult2}"


# =============================================================================
# TEST: Tier Invariants
# =============================================================================


class TestTierInvariants:
    """CONTRACT: Tier mapping invariants."""

    @given(score=fitness_score())
    @settings(max_examples=1000)
    def test_tier_always_valid(self, score):
        """
        INVARIANT: get_tier returns a valid tier string.
        """
        tier = get_tier(score)

        assert tier in TIER_VALUES, f"Invalid tier '{tier}' for score {score}"

    @given(score=st.floats(min_value=0, max_value=39.999, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_tier_dies_range(self, score):
        """
        INVARIANT: Score < 40 maps to DIES.
        """
        tier = get_tier(score)
        assert tier == "DIES", f"Score {score} should be DIES, got {tier}"

    @given(score=st.floats(min_value=40, max_value=79.999, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_tier_survives_range(self, score):
        """
        INVARIANT: Score 40-79 maps to SURVIVES.
        """
        tier = get_tier(score)
        assert tier == "SURVIVES", f"Score {score} should be SURVIVES, got {tier}"

    @given(score=st.floats(min_value=80, max_value=100, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_tier_promoted_range(self, score):
        """
        INVARIANT: Score 80+ maps to PROMOTED.
        """
        tier = get_tier(score)
        assert tier == "PROMOTED", f"Score {score} should be PROMOTED, got {tier}"


# =============================================================================
# TEST: Win Rate Invariants
# =============================================================================


class TestWinRateInvariants:
    """CONTRACT: Win rate calculation invariants."""

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_win_rate_bounded(self, trades):
        """
        INVARIANT: Win rate is always in [0, 100].
        """
        win_rate = calculate_win_rate(trades)

        assert WIN_RATE_MIN <= win_rate <= WIN_RATE_MAX, (
            f"Win rate {win_rate} violates bounds [{WIN_RATE_MIN}, {WIN_RATE_MAX}]"
        )

    @given(trades=winning_trade_list(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_all_winners_100_percent(self, trades):
        """
        INVARIANT: All winning trades = 100% win rate.
        """
        win_rate = calculate_win_rate(trades)
        assert win_rate == 100.0, f"All winners should be 100%, got {win_rate}"

    @given(trades=losing_trade_list(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_all_losers_0_percent(self, trades):
        """
        INVARIANT: All losing trades = 0% win rate.
        """
        win_rate = calculate_win_rate(trades)
        assert win_rate == 0.0, f"All losers should be 0%, got {win_rate}"


# =============================================================================
# TEST: Sortino Invariants
# =============================================================================


class TestSortinoInvariants:
    """CONTRACT: Sortino ratio calculation invariants."""

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_sortino_bounded(self, trades):
        """
        INVARIANT: Sortino is bounded [0, 4].
        """
        sortino = calculate_sortino(trades)

        assert 0.0 <= sortino <= SORTINO_MAX, f"Sortino {sortino} violates bounds [0, {SORTINO_MAX}]"

    @given(trades=winning_trade_list(min_size=2, max_size=50))
    @settings(max_examples=200)
    def test_sortino_all_winners_capped(self, trades):
        """
        INVARIANT: All winners = capped Sortino (no downside deviation).
        """
        sortino = calculate_sortino(trades)
        assert sortino == SORTINO_MAX, f"All winners should cap Sortino at {SORTINO_MAX}, got {sortino}"

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_sortino_never_nan(self, trades):
        """
        INVARIANT: Sortino is never NaN.
        """
        sortino = calculate_sortino(trades)
        assert not math.isnan(sortino), "Sortino must never be NaN"

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_sortino_always_finite(self, trades):
        """
        INVARIANT: Sortino is always finite.
        """
        sortino = calculate_sortino(trades)
        assert math.isfinite(sortino), f"Sortino must be finite, got {sortino}"


# =============================================================================
# TEST: Max Drawdown Invariants
# =============================================================================


class TestMaxDrawdownInvariants:
    """CONTRACT: Max drawdown calculation invariants."""

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_drawdown_bounded(self, trades):
        """
        INVARIANT: Max drawdown is in [0, 100].
        """
        max_dd = calculate_max_drawdown(trades)

        assert 0.0 <= max_dd <= 100.0, f"Drawdown {max_dd} violates bounds [0, 100]"

    @given(trades=winning_trade_list(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_all_winners_zero_drawdown(self, trades):
        """
        INVARIANT: All winning trades = 0% max drawdown.

        Equity curve only goes up, never draws down.
        """
        max_dd = calculate_max_drawdown(trades)
        assert max_dd == 0.0, f"All winners should have 0% drawdown, got {max_dd}"

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_drawdown_never_nan(self, trades):
        """
        INVARIANT: Drawdown is never NaN.
        """
        max_dd = calculate_max_drawdown(trades)
        assert not math.isnan(max_dd), "Drawdown must never be NaN"


# =============================================================================
# TEST: EV Invariants
# =============================================================================


class TestEVInvariants:
    """CONTRACT: Expected Value calculation invariants."""

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_ev_never_nan(self, trades):
        """
        INVARIANT: EV is never NaN.
        """
        ev = calculate_ev(trades)
        assert not math.isnan(ev), "EV must never be NaN"

    @given(trades=trade_list(min_size=0, max_size=100))
    @settings(max_examples=500)
    def test_ev_always_finite(self, trades):
        """
        INVARIANT: EV is always finite.
        """
        ev = calculate_ev(trades)
        assert math.isfinite(ev), f"EV must be finite, got {ev}"

    @given(trades=winning_trade_list(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_ev_positive_for_all_winners(self, trades):
        """
        INVARIANT: All winning trades = positive EV.
        """
        ev = calculate_ev(trades)
        assert ev > 0, f"All winners should have positive EV, got {ev}"

    @given(trades=losing_trade_list(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_ev_negative_for_all_losers(self, trades):
        """
        INVARIANT: All losing trades = negative EV.
        """
        ev = calculate_ev(trades)
        assert ev < 0, f"All losers should have negative EV, got {ev}"


# =============================================================================
# TEST: Trait Invariants
# =============================================================================


class TestTraitInvariants:
    """CONTRACT: Trait value invariants."""

    @given(traits=valid_traits())
    @settings(max_examples=500)
    def test_traits_bounded(self, traits):
        """
        INVARIANT: All traits are in [0, 1].
        """
        for name, value in traits.items():
            assert TRAIT_MIN <= value <= TRAIT_MAX, (
                f"Trait '{name}' = {value} violates bounds [{TRAIT_MIN}, {TRAIT_MAX}]"
            )

    @given(traits=valid_traits())
    @settings(max_examples=500)
    def test_traits_never_nan(self, traits):
        """
        INVARIANT: No trait is NaN.
        """
        for name, value in traits.items():
            assert not math.isnan(value), f"Trait '{name}' must not be NaN"


# =============================================================================
# TEST: Stress Tests
# =============================================================================


class TestStressInvariants:
    """Stress tests with larger inputs."""

    @given(trades=mixed_edge_case_trades(size=100))
    @settings(max_examples=100, deadline=timedelta(seconds=10))
    def test_fitness_survives_chaos(self, trades):
        """
        STRESS: Fitness survives mixed edge case bombardment.
        """
        result = calculate_fitness(trades)

        # Must not crash and must produce valid output
        assert not math.isnan(result.fitness_score)
        assert FITNESS_MIN <= result.fitness_score <= FITNESS_MAX

    @given(trades=trade_list(min_size=100, max_size=200))
    @settings(max_examples=20, deadline=timedelta(seconds=30))
    def test_fitness_scales_with_trade_count(self, trades):
        """
        PROPERTY: Fitness handles moderately large trade lists.

        Note: True stress testing (1000+ trades) is in Tests/Performance/
        where we use direct generation, not Hypothesis.
        """
        result = calculate_fitness(trades)

        assert not math.isnan(result.fitness_score)
        assert FITNESS_MIN <= result.fitness_score <= FITNESS_MAX
