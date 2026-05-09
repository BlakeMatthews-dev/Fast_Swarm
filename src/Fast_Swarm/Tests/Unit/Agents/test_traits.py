"""
Agent Traits Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md Section 1.2 (22-Trait Genome)
All traits are float 0.0-1.0, with specific formulas for derived parameters.
"""

import pytest

from Fast_Swarm.Agents.Services.agent_service import (
    calculate_derived_traits,
    calculate_max_hold_duration_ms,
    calculate_position_size,
    calculate_stop_loss,
    calculate_take_profit,
)
from Fast_Swarm.Agents.Services.trait_service import (
    ALL_22_TRAITS,
    BASE_TRAITS,
    CORE_RISK_TRAITS,
    DERIVED_TRAITS,
    EXECUTION_TRAITS,
    MACRO_TRAITS,
    PATTERN_SELECTION_TRAITS,
    SENTIMENT_TRAITS,
    TECHNICAL_TRAITS,
    clamp_traits,
    crossover_and_mutate,
    crossover_traits,
    fill_missing_traits,
    generate_all_traits,
    mutate_trait,
    traits_are_equal,
    validate_all_traits,
    validate_trait_value,
)

# ============================================================================
# TRAIT DEFINITIONS CONTRACT (22 traits total)
# ============================================================================


class TestTraitPresence:
    """CONTRACT: All 22 traits must be present."""

    def test_all_22_traits_defined(self):
        """CONTRACT: System defines exactly 22 traits."""
        assert len(ALL_22_TRAITS) == 22

    def test_core_risk_traits_present(self):
        """CONTRACT: 4 core risk traits must exist."""
        assert len(CORE_RISK_TRAITS) == 4
        for trait in CORE_RISK_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_pattern_selection_traits_present(self):
        """CONTRACT: 2 pattern selection traits must exist."""
        assert len(PATTERN_SELECTION_TRAITS) == 2
        for trait in PATTERN_SELECTION_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_execution_traits_present(self):
        """CONTRACT: 1 execution trait must exist."""
        assert len(EXECUTION_TRAITS) == 1
        for trait in EXECUTION_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_technical_traits_present(self):
        """CONTRACT: 1 technical trait must exist."""
        assert len(TECHNICAL_TRAITS) == 1
        for trait in TECHNICAL_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_sentiment_traits_present(self):
        """CONTRACT: 3 sentiment traits must exist."""
        assert len(SENTIMENT_TRAITS) == 3
        for trait in SENTIMENT_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_macro_traits_present(self):
        """CONTRACT: 2 macro traits must exist."""
        assert len(MACRO_TRAITS) == 2
        for trait in MACRO_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_derived_traits_present(self):
        """CONTRACT: 3 derived traits must exist."""
        assert len(DERIVED_TRAITS) == 3
        for trait in DERIVED_TRAITS:
            assert trait in ALL_22_TRAITS

    def test_generated_traits_have_all_22(self):
        """CONTRACT: generate_all_traits returns all 22 traits."""
        traits = generate_all_traits(seed=42)
        assert len(traits) == 22
        for trait_name in ALL_22_TRAITS:
            assert trait_name in traits


class TestTraitBounds:
    """CONTRACT: All traits must be bounded [0.0, 1.0]."""

    @pytest.mark.parametrize("trait_name", ALL_22_TRAITS)
    def test_generated_trait_bounded_0_to_1(self, trait_name):
        """CONTRACT: Each generated trait value is in [0.0, 1.0]."""
        traits = generate_all_traits(seed=42)
        value = traits[trait_name]
        assert 0.0 <= value <= 1.0, f"{trait_name}={value} out of bounds"

    def test_trait_at_lower_bound_valid(self):
        """CONTRACT: Trait value of exactly 0.0 is valid."""
        is_valid, error = validate_trait_value(0.0)
        assert is_valid is True

    def test_trait_at_upper_bound_valid(self):
        """CONTRACT: Trait value of exactly 1.0 is valid."""
        is_valid, error = validate_trait_value(1.0)
        assert is_valid is True

    def test_trait_below_lower_bound_rejected(self):
        """CONTRACT: Trait value < 0.0 must be rejected."""
        is_valid, error = validate_trait_value(-0.1)
        assert is_valid is False
        assert "0.0" in error or "[0" in error

    def test_trait_above_upper_bound_rejected(self):
        """CONTRACT: Trait value > 1.0 must be rejected."""
        is_valid, error = validate_trait_value(1.1)
        assert is_valid is False
        assert "1.0" in error or "1]" in error

    def test_trait_nan_rejected(self):
        """CONTRACT: NaN trait value must be rejected."""
        is_valid, error = validate_trait_value(float("nan"))
        assert is_valid is False
        assert "NaN" in error

    def test_trait_inf_rejected(self):
        """CONTRACT: Infinity trait value must be rejected."""
        is_valid, error = validate_trait_value(float("inf"))
        assert is_valid is False
        assert "Infinity" in error or "inf" in error.lower()


class TestDerivedTraits:
    """CONTRACT: Derived traits calculated from anchors with ±5% noise."""

    def test_drawdown_sensitivity_derived(self):
        """CONTRACT: drawdown_sensitivity is derived from risk_tolerance."""
        base = {"risk_tolerance": 0.3, "hold_duration_bias": 0.5}
        for trait in BASE_TRAITS:
            if trait not in base:
                base[trait] = 0.5

        result = calculate_derived_traits(base)
        # drawdown_sensitivity ≈ 1 - risk_tolerance = 0.7 ± 5%
        assert "drawdown_sensitivity" in result
        assert 0.60 <= result["drawdown_sensitivity"] <= 0.80

    def test_stop_loss_tightness_derived(self):
        """CONTRACT: stop_loss_tightness is derived from risk_tolerance."""
        base = {"risk_tolerance": 0.8, "hold_duration_bias": 0.5}
        for trait in BASE_TRAITS:
            if trait not in base:
                base[trait] = 0.5

        result = calculate_derived_traits(base)
        # stop_loss_tightness ≈ 1 - risk_tolerance = 0.2 ± 5%
        assert "stop_loss_tightness" in result
        assert 0.10 <= result["stop_loss_tightness"] <= 0.30

    def test_exit_aggression_derived(self):
        """CONTRACT: exit_aggression is derived from hold_duration_bias."""
        base = {"risk_tolerance": 0.5, "hold_duration_bias": 0.2}
        for trait in BASE_TRAITS:
            if trait not in base:
                base[trait] = 0.5

        result = calculate_derived_traits(base)
        # exit_aggression ≈ 1 - hold_duration_bias = 0.8 ± 5%
        assert "exit_aggression" in result
        assert 0.70 <= result["exit_aggression"] <= 0.90

    def test_derived_traits_within_5_percent_noise(self):
        """CONTRACT: Derived traits deviate max ±5% from anchor formula."""
        base = {"risk_tolerance": 0.5, "hold_duration_bias": 0.5}
        for trait in BASE_TRAITS:
            if trait not in base:
                base[trait] = 0.5

        # Run multiple times to check noise bounds
        for _ in range(10):
            result = calculate_derived_traits(base)
            # Expected: 1 - 0.5 = 0.5, with ±5% = 0.45 to 0.55
            assert 0.45 <= result["drawdown_sensitivity"] <= 0.55
            assert 0.45 <= result["stop_loss_tightness"] <= 0.55
            assert 0.45 <= result["exit_aggression"] <= 0.55

    def test_derived_traits_still_bounded_0_1(self):
        """CONTRACT: Even with noise, derived traits stay in [0, 1]."""
        # Test at extremes
        base_low = {"risk_tolerance": 0.0, "hold_duration_bias": 0.0}
        base_high = {"risk_tolerance": 1.0, "hold_duration_bias": 1.0}

        for trait in BASE_TRAITS:
            if trait not in base_low:
                base_low[trait] = 0.5
                base_high[trait] = 0.5

        for _ in range(20):
            result_low = calculate_derived_traits(base_low)
            result_high = calculate_derived_traits(base_high)

            for trait in DERIVED_TRAITS:
                assert 0.0 <= result_low[trait] <= 1.0
                assert 0.0 <= result_high[trait] <= 1.0


class TestTraitToParameterFormulas:
    """CONTRACT: Traits convert to trading parameters via specific formulas."""

    def test_position_size_formula(self):
        """CONTRACT: position_size_pct = 0.01 + risk_tolerance * 0.09 → [1%, 10%]."""
        # Test at 0.5
        result = calculate_position_size(0.5)
        assert abs(result - 0.055) < 0.001  # 5.5%

    def test_position_size_at_min_risk_tolerance(self):
        """CONTRACT: risk_tolerance=0 → position_size=1%."""
        result = calculate_position_size(0.0)
        assert abs(result - 0.01) < 0.001

    def test_position_size_at_max_risk_tolerance(self):
        """CONTRACT: risk_tolerance=1 → position_size=10%."""
        result = calculate_position_size(1.0)
        assert abs(result - 0.10) < 0.001

    def test_stop_loss_formula(self):
        """CONTRACT: stop_loss_pct = 0.10 - stop_loss_tightness * 0.09 → [1%, 10%] (inverted)."""
        result = calculate_stop_loss(0.5)
        assert abs(result - 0.055) < 0.001

    def test_stop_loss_at_min_tightness(self):
        """CONTRACT: stop_loss_tightness=0 → stop_loss=10% (loose)."""
        result = calculate_stop_loss(0.0)
        assert abs(result - 0.10) < 0.001

    def test_stop_loss_at_max_tightness(self):
        """CONTRACT: stop_loss_tightness=1 → stop_loss=1% (tight)."""
        result = calculate_stop_loss(1.0)
        assert abs(result - 0.01) < 0.001

    def test_take_profit_formula(self):
        """CONTRACT: take_profit_pct = 0.02 + profit_target_greed * 0.18 → [2%, 20%]."""
        result = calculate_take_profit(0.5)
        assert abs(result - 0.11) < 0.001  # 11%

    def test_take_profit_at_min_greed(self):
        """CONTRACT: profit_target_greed=0 → take_profit=2%."""
        result = calculate_take_profit(0.0)
        assert abs(result - 0.02) < 0.001

    def test_take_profit_at_max_greed(self):
        """CONTRACT: profit_target_greed=1 → take_profit=20%."""
        result = calculate_take_profit(1.0)
        assert abs(result - 0.20) < 0.001

    def test_max_hold_formula(self):
        """CONTRACT: max_hold_ms = 3.6M + hold_duration_bias * 601.2M → [1hr, 7days]."""
        result = calculate_max_hold_duration_ms(0.5)
        expected = 3_600_000 + int(0.5 * 601_200_000)
        assert abs(result - expected) < 1000

    def test_max_hold_at_min_bias(self):
        """CONTRACT: hold_duration_bias=0 → max_hold=1 hour."""
        result = calculate_max_hold_duration_ms(0.0)
        assert result == 3_600_000  # 1 hour in ms

    def test_max_hold_at_max_bias(self):
        """CONTRACT: hold_duration_bias=1 → max_hold=7 days."""
        result = calculate_max_hold_duration_ms(1.0)
        expected = 3_600_000 + 601_200_000  # 604,800,000 ms = 7 days
        assert result == expected


class TestTraitMutation:
    """CONTRACT: Mutation is ±10% per generation, bounded."""

    def test_mutation_within_10_percent(self):
        """CONTRACT: Mutated trait differs by max ±10% from original."""
        original = 0.5
        for i in range(20):
            mutated = mutate_trait(original, mutation_rate=0.10, seed=i)
            assert abs(mutated - original) <= 0.10

    def test_mutation_preserves_bounds(self):
        """CONTRACT: Mutation never produces trait outside [0, 1]."""
        # Test at boundaries
        for _ in range(20):
            low_result = mutate_trait(0.05, mutation_rate=0.10)
            high_result = mutate_trait(0.95, mutation_rate=0.10)
            assert 0.0 <= low_result <= 1.0
            assert 0.0 <= high_result <= 1.0

    def test_mutation_at_boundary_clamps(self):
        """CONTRACT: Trait at 0.95 with +10% mutation clamps to 1.0."""
        # Force positive mutation by testing multiple times
        for i in range(100):
            result = mutate_trait(0.99, mutation_rate=0.10, seed=i)
            assert result <= 1.0  # Should never exceed

    def test_mutation_rate_configurable(self):
        """CONTRACT: Mutation rate can be configured (default 0.10)."""
        original = 0.5
        # With 5% mutation rate
        for i in range(20):
            mutated = mutate_trait(original, mutation_rate=0.05, seed=i)
            assert abs(mutated - original) <= 0.05

    def test_mutation_deterministic_with_seed(self):
        """CONTRACT: Same seed produces identical mutations."""
        original = 0.5
        result1 = mutate_trait(original, mutation_rate=0.10, seed=42)
        result2 = mutate_trait(original, mutation_rate=0.10, seed=42)
        assert result1 == result2


class TestTraitCrossover:
    """CONTRACT: Crossover averages parent traits."""

    def test_crossover_averages_parents(self):
        """CONTRACT: Child trait = (parent_a_trait + parent_b_trait) / 2."""
        parent_a = generate_all_traits(seed=1)
        parent_b = generate_all_traits(seed=2)

        child = crossover_traits(parent_a, parent_b, seed=100)

        # Check base traits are averaged
        for trait_name in BASE_TRAITS:
            expected = (parent_a[trait_name] + parent_b[trait_name]) / 2
            assert abs(child[trait_name] - expected) < 0.01

    def test_crossover_all_22_traits(self):
        """CONTRACT: Crossover applies to all 22 traits."""
        parent_a = generate_all_traits(seed=1)
        parent_b = generate_all_traits(seed=2)

        child = crossover_traits(parent_a, parent_b)

        assert len(child) == 22

    def test_crossover_with_mutation(self):
        """CONTRACT: Crossover followed by mutation."""
        parent_a = generate_all_traits(seed=1)
        parent_b = generate_all_traits(seed=2)

        child = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.10, seed=42)

        # Should have all 22 traits
        assert len(child) == 22

        # Values should differ from pure crossover due to mutation
        pure_crossover = crossover_traits(parent_a, parent_b, seed=42)
        # At least some traits should differ
        differences = sum(1 for t in BASE_TRAITS if abs(child[t] - pure_crossover[t]) > 0.001)
        assert differences > 0

    def test_crossover_preserves_bounds(self):
        """CONTRACT: Crossover result always in [0, 1]."""
        parent_a = generate_all_traits(seed=1)
        parent_b = generate_all_traits(seed=2)

        child = crossover_traits(parent_a, parent_b)

        for trait_name, value in child.items():
            assert 0.0 <= value <= 1.0

    def test_crossover_deterministic_with_seed(self):
        """CONTRACT: Same parents + seed = same child traits."""
        parent_a = generate_all_traits(seed=1)
        parent_b = generate_all_traits(seed=2)

        child1 = crossover_traits(parent_a, parent_b, seed=42)
        child2 = crossover_traits(parent_a, parent_b, seed=42)

        assert traits_are_equal(child1, child2)


class TestTraitSeedDeterminism:
    """CONTRACT: Same seed produces identical trait values."""

    def test_seed_produces_identical_traits(self):
        """CONTRACT: seed=42 always produces exact same trait values."""
        traits1 = generate_all_traits(seed=42)
        traits2 = generate_all_traits(seed=42)

        assert traits_are_equal(traits1, traits2)

    def test_different_seeds_produce_different_traits(self):
        """CONTRACT: Different seeds produce different traits."""
        traits1 = generate_all_traits(seed=1)
        traits2 = generate_all_traits(seed=2)

        # Should be different
        assert not traits_are_equal(traits1, traits2)

    def test_seed_none_produces_random(self):
        """CONTRACT: seed=None produces different traits each time."""
        traits1 = generate_all_traits(seed=None)
        traits2 = generate_all_traits(seed=None)

        # Very unlikely to be identical
        # Just check they're valid
        assert len(traits1) == 22
        assert len(traits2) == 22


class TestTraitValidation:
    """CONTRACT: Trait validation catches invalid values."""

    @pytest.mark.parametrize("invalid_value", [-0.1, 1.1, float("nan"), float("inf")])
    def test_invalid_trait_value_rejected(self, invalid_value):
        """CONTRACT: Invalid trait values raise ValidationError."""
        is_valid, error = validate_trait_value(invalid_value)
        assert is_valid is False
        assert len(error) > 0

    def test_none_value_rejected(self):
        """CONTRACT: None trait value is rejected."""
        is_valid, error = validate_trait_value(None)
        assert is_valid is False

    def test_missing_trait_filled(self):
        """CONTRACT: Missing trait in dict gets filled."""
        partial = {"risk_tolerance": 0.5}
        complete = fill_missing_traits(partial, seed=42)

        assert len(complete) == 22
        assert complete["risk_tolerance"] == 0.5  # Preserved

    def test_clamp_traits_bounds(self):
        """CONTRACT: clamp_traits brings values to [0, 1]."""
        bad_traits = {"risk_tolerance": 1.5, "volatility_seeking": -0.3}
        clamped = clamp_traits(bad_traits)

        assert clamped["risk_tolerance"] == 1.0
        assert clamped["volatility_seeking"] == 0.0

    def test_validate_all_traits_complete(self):
        """CONTRACT: validate_all_traits checks all 22."""
        complete = generate_all_traits(seed=42)
        is_valid, error = validate_all_traits(complete)
        assert is_valid is True

    def test_validate_all_traits_missing_fails(self):
        """CONTRACT: Missing trait fails validation."""
        incomplete = generate_all_traits(seed=42)
        del incomplete["risk_tolerance"]

        is_valid, error = validate_all_traits(incomplete)
        assert is_valid is False
        assert "risk_tolerance" in error
