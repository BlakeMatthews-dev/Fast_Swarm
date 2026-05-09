"""
EDD Soundness Test: Trait Drift and Mutation Stability - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (22-Trait Genome)
Validates that:
1. Mutation rate stays below 15% per generation
2. Derived traits are consistent with base traits
3. Trait calculations produce bounded outputs
4. Position/SL/TP formulas are deterministic

MASTER TEST ADMIN: "Traits are the DNA - corrupted DNA means mutant agents."
"""

import random

import pytest

from Fast_Swarm.Agents.Services.agent_service import (
    calculate_derived_traits,
    calculate_max_hold_duration_ms,
    calculate_position_size,
    calculate_stop_loss,
    calculate_take_profit,
    get_trading_parameters,
)
from Fast_Swarm.Agents.Services.trait_service import (
    ADDITIONAL_TRAITS,
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
    mutate_traits,
    traits_are_equal,
    validate_trait_value,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def default_traits() -> dict[str, float]:
    """All traits at 0.5 (neutral)."""
    return dict.fromkeys(ALL_22_TRAITS, 0.5)


@pytest.fixture
def high_risk_traits() -> dict[str, float]:
    """High risk tolerance agent."""
    traits = dict.fromkeys(ALL_22_TRAITS, 0.5)
    traits["risk_tolerance"] = 0.9
    traits["profit_target_greed"] = 0.8
    traits["hold_duration_bias"] = 0.7
    return traits


@pytest.fixture
def low_risk_traits() -> dict[str, float]:
    """Low risk tolerance agent."""
    traits = dict.fromkeys(ALL_22_TRAITS, 0.5)
    traits["risk_tolerance"] = 0.1
    traits["profit_target_greed"] = 0.2
    traits["hold_duration_bias"] = 0.3
    return traits


# =============================================================================
# TEST: Trait Calculation Bounds
# =============================================================================


class TestTraitCalculationBounds:
    """CONTRACT: Trait calculations produce bounded outputs."""

    def test_position_size_bounds(self):
        """CONTRACT: Position size must be 1-10% for all inputs."""
        # Test across full range
        for i in range(101):
            risk_tolerance = i / 100.0
            pos_size = calculate_position_size(risk_tolerance)
            assert 0.01 <= pos_size <= 0.10, (
                f"Position size {pos_size} out of bounds for risk_tolerance={risk_tolerance}"
            )

    def test_position_size_min(self):
        """CONTRACT: risk_tolerance=0 → position_size=1%."""
        pos_size = calculate_position_size(0.0)
        assert pos_size == 0.01, f"Expected 0.01, got {pos_size}"

    def test_position_size_max(self):
        """CONTRACT: risk_tolerance=1 → position_size=10%."""
        pos_size = calculate_position_size(1.0)
        assert abs(pos_size - 0.10) < 1e-9, f"Expected 0.10, got {pos_size}"

    def test_position_size_midpoint(self):
        """CONTRACT: risk_tolerance=0.5 → position_size=5.5%."""
        pos_size = calculate_position_size(0.5)
        assert abs(pos_size - 0.055) < 1e-9, f"Expected 0.055, got {pos_size}"

    def test_stop_loss_bounds(self):
        """CONTRACT: Stop loss must be 1-10% for all inputs."""
        for i in range(101):
            tightness = i / 100.0
            stop_loss = calculate_stop_loss(tightness)
            assert 0.01 <= stop_loss <= 0.10, f"Stop loss {stop_loss} out of bounds for tightness={tightness}"

    def test_stop_loss_inverted(self):
        """CONTRACT: High tightness = tight stop (low percentage)."""
        loose_stop = calculate_stop_loss(0.0)  # Low tightness
        tight_stop = calculate_stop_loss(1.0)  # High tightness
        assert loose_stop > tight_stop, f"Stop loss should be inverted: loose={loose_stop}, tight={tight_stop}"
        assert abs(loose_stop - 0.10) < 1e-9, f"tightness=0 should give 10% stop, got {loose_stop}"
        assert abs(tight_stop - 0.01) < 1e-9, f"tightness=1 should give 1% stop, got {tight_stop}"

    def test_take_profit_bounds(self):
        """CONTRACT: Take profit must be 2-20% for all inputs."""
        for i in range(101):
            greed = i / 100.0
            take_profit = calculate_take_profit(greed)
            assert 0.02 <= take_profit <= 0.20, f"Take profit {take_profit} out of bounds for greed={greed}"

    def test_take_profit_min_max(self):
        """CONTRACT: greed=0→2%, greed=1→20%."""
        conservative = calculate_take_profit(0.0)
        greedy = calculate_take_profit(1.0)
        assert abs(conservative - 0.02) < 1e-9, f"Expected 0.02, got {conservative}"
        assert abs(greedy - 0.20) < 1e-9, f"Expected 0.20, got {greedy}"

    def test_hold_duration_bounds(self):
        """CONTRACT: Hold duration must be 1 hour to 7 days."""
        ONE_HOUR_MS = 3_600_000
        SEVEN_DAYS_MS = 604_800_000

        for i in range(101):
            bias = i / 100.0
            duration = calculate_max_hold_duration_ms(bias)
            assert ONE_HOUR_MS <= duration <= SEVEN_DAYS_MS, f"Duration {duration}ms out of bounds for bias={bias}"

    def test_hold_duration_min_max(self):
        """CONTRACT: bias=0→1hour, bias=1→7days."""
        ONE_HOUR_MS = 3_600_000
        SEVEN_DAYS_MS = 604_800_000

        short = calculate_max_hold_duration_ms(0.0)
        long = calculate_max_hold_duration_ms(1.0)
        assert short == ONE_HOUR_MS, f"Expected {ONE_HOUR_MS}, got {short}"
        assert long == SEVEN_DAYS_MS, f"Expected {SEVEN_DAYS_MS}, got {long}"

    def test_out_of_bounds_clamped(self):
        """CONTRACT: Trait values < 0 or > 1 are clamped in calculations."""
        # Values below 0 should be treated as 0
        assert calculate_position_size(-0.5) == calculate_position_size(0.0)
        assert calculate_stop_loss(-1.0) == calculate_stop_loss(0.0)
        assert calculate_take_profit(-0.3) == calculate_take_profit(0.0)

        # Values above 1 should be treated as 1
        assert calculate_position_size(1.5) == calculate_position_size(1.0)
        assert calculate_stop_loss(2.0) == calculate_stop_loss(1.0)
        assert calculate_take_profit(1.1) == calculate_take_profit(1.0)


# =============================================================================
# TEST: Trait Determinism
# =============================================================================


class TestTraitDeterminism:
    """CONTRACT: Calculations are deterministic (no randomness in core functions)."""

    def test_position_size_determinism(self):
        """CONTRACT: Position size calculation is deterministic."""
        for _ in range(100):
            result1 = calculate_position_size(0.7)
            result2 = calculate_position_size(0.7)
            assert result1 == result2, "Position size should be deterministic"

    def test_stop_loss_determinism(self):
        """CONTRACT: Stop loss calculation is deterministic."""
        for _ in range(100):
            result1 = calculate_stop_loss(0.3)
            result2 = calculate_stop_loss(0.3)
            assert result1 == result2, "Stop loss should be deterministic"

    def test_take_profit_determinism(self):
        """CONTRACT: Take profit calculation is deterministic."""
        for _ in range(100):
            result1 = calculate_take_profit(0.6)
            result2 = calculate_take_profit(0.6)
            assert result1 == result2, "Take profit should be deterministic"

    def test_trading_parameters_determinism(self, default_traits):
        """CONTRACT: get_trading_parameters is deterministic for same traits."""
        # Derived traits have noise, so use same traits object
        params1 = get_trading_parameters(default_traits)
        params2 = get_trading_parameters(default_traits)

        assert params1["position_size_pct"] == params2["position_size_pct"]
        assert params1["stop_loss_pct"] == params2["stop_loss_pct"]
        assert params1["take_profit_pct"] == params2["take_profit_pct"]
        assert params1["max_hold_ms"] == params2["max_hold_ms"]

    def test_trait_generation_determinism_with_seed(self):
        """CONTRACT: Same seed produces identical traits."""
        traits1 = generate_all_traits(seed=42)
        traits2 = generate_all_traits(seed=42)
        assert traits_are_equal(traits1, traits2), "Same seed should produce identical traits"


# =============================================================================
# TEST: Derived Trait Consistency
# =============================================================================


class TestDerivedTraitConsistency:
    """CONTRACT: Derived traits are consistent with base traits."""

    def test_drawdown_sensitivity_inverse_of_risk(self):
        """CONTRACT: drawdown_sensitivity ≈ 1 - risk_tolerance (±5% noise)."""
        random.seed(42)  # Control noise

        for risk in [0.0, 0.25, 0.5, 0.75, 1.0]:
            base_traits = dict.fromkeys(BASE_TRAITS, 0.5)
            base_traits["risk_tolerance"] = risk

            derived = calculate_derived_traits(base_traits)
            expected = 1.0 - risk
            actual = derived["drawdown_sensitivity"]

            # Allow ±5% noise + clamping effects
            assert abs(actual - expected) <= 0.10, f"drawdown_sensitivity={actual} should be near {expected}"
            assert 0.0 <= actual <= 1.0, "Must be bounded"

    def test_stop_loss_tightness_inverse_of_risk(self):
        """CONTRACT: stop_loss_tightness ≈ 1 - risk_tolerance (±5% noise)."""
        random.seed(123)

        for risk in [0.0, 0.25, 0.5, 0.75, 1.0]:
            base_traits = dict.fromkeys(BASE_TRAITS, 0.5)
            base_traits["risk_tolerance"] = risk

            derived = calculate_derived_traits(base_traits)
            expected = 1.0 - risk
            actual = derived["stop_loss_tightness"]

            assert abs(actual - expected) <= 0.10, f"stop_loss_tightness={actual} should be near {expected}"
            assert 0.0 <= actual <= 1.0, "Must be bounded"

    def test_exit_aggression_inverse_of_hold_bias(self):
        """CONTRACT: exit_aggression ≈ 1 - hold_duration_bias (±5% noise)."""
        random.seed(456)

        for bias in [0.0, 0.25, 0.5, 0.75, 1.0]:
            base_traits = dict.fromkeys(BASE_TRAITS, 0.5)
            base_traits["hold_duration_bias"] = bias

            derived = calculate_derived_traits(base_traits)
            expected = 1.0 - bias
            actual = derived["exit_aggression"]

            assert abs(actual - expected) <= 0.10, f"exit_aggression={actual} should be near {expected}"
            assert 0.0 <= actual <= 1.0, "Must be bounded"

    def test_derived_traits_bounded_0_to_1(self):
        """CONTRACT: All derived traits in [0, 1] even with extreme base values."""
        # Test with extreme base trait values
        extreme_cases = [
            {"risk_tolerance": 0.0, "hold_duration_bias": 0.0},  # Both at min
            {"risk_tolerance": 1.0, "hold_duration_bias": 1.0},  # Both at max
            {"risk_tolerance": 0.0, "hold_duration_bias": 1.0},  # Mixed extremes
            {"risk_tolerance": 1.0, "hold_duration_bias": 0.0},  # Mixed extremes
        ]

        for extreme in extreme_cases:
            base_traits = dict.fromkeys(BASE_TRAITS, 0.5)
            base_traits.update(extreme)

            derived = calculate_derived_traits(base_traits)

            for trait_name in DERIVED_TRAITS:
                value = derived[trait_name]
                assert 0.0 <= value <= 1.0, f"{trait_name}={value} out of bounds with {extreme}"


# =============================================================================
# TEST: Mutation Stability
# =============================================================================


class TestMutationStability:
    """CONTRACT: Mutation rate stays within bounds."""

    def test_mutation_rate_below_15_percent(self):
        """CONTRACT: Default mutation rate is 10% (±10% change per trait)."""
        random.seed(42)
        original_value = 0.5

        # Track maximum deviation across many mutations
        max_deviation = 0.0
        for _ in range(1000):
            mutated = mutate_trait(original_value, mutation_rate=0.10)
            deviation = abs(mutated - original_value)
            max_deviation = max(max_deviation, deviation)

        # Maximum deviation should be ≤ mutation_rate (0.10)
        assert max_deviation <= 0.10 + 1e-9, f"Max deviation {max_deviation} exceeds mutation rate 0.10"

    def test_noise_distribution(self):
        """CONTRACT: Noise uniformly distributed around base value."""
        random.seed(42)
        original_value = 0.5
        mutations = [mutate_trait(original_value, mutation_rate=0.10) for _ in range(10000)]

        # Mean should be close to original (uniform distribution centered)
        mean_mutation = sum(mutations) / len(mutations)
        assert abs(mean_mutation - original_value) < 0.02, f"Mean {mean_mutation} should be close to {original_value}"

        # Should have roughly equal mutations above and below
        above = sum(1 for m in mutations if m > original_value)
        below = sum(1 for m in mutations if m < original_value)
        ratio = above / below if below > 0 else float("inf")
        assert 0.8 < ratio < 1.2, f"Ratio {ratio} should be near 1.0"

    def test_mutation_preserves_bounds(self):
        """CONTRACT: Mutation never produces out-of-bounds traits."""
        # Test mutations at boundaries
        edge_values = [0.0, 0.01, 0.99, 1.0]

        for value in edge_values:
            for _ in range(1000):
                mutated = mutate_trait(value, mutation_rate=0.10)
                assert 0.0 <= mutated <= 1.0, f"Mutated value {mutated} out of bounds from {value}"

    def test_full_traits_mutation_preserves_bounds(self, default_traits):
        """CONTRACT: mutate_traits preserves [0, 1] bounds for all traits."""
        for _ in range(100):
            mutated = mutate_traits(default_traits, mutation_rate=0.15)

            for trait_name, value in mutated.items():
                assert 0.0 <= value <= 1.0, f"{trait_name}={value} out of bounds after mutation"


# =============================================================================
# TEST: Trait Interaction
# =============================================================================


class TestTraitInteraction:
    """CONTRACT: Interactions between traits produce sensible parameters."""

    def test_high_risk_agent_parameters(self, high_risk_traits):
        """CONTRACT: High risk → large positions, loose stops, high targets."""
        params = get_trading_parameters(high_risk_traits)

        # High risk should give larger positions
        assert params["position_size_pct"] > 0.05, (
            f"High risk should have >5% position, got {params['position_size_pct']}"
        )

        # High greed should give larger take profits
        assert params["take_profit_pct"] > 0.10, f"High greed should have >10% TP, got {params['take_profit_pct']}"

    def test_low_risk_agent_parameters(self, low_risk_traits):
        """CONTRACT: Low risk → small positions, tight stops, modest targets."""
        params = get_trading_parameters(low_risk_traits)

        # Low risk should give smaller positions
        assert params["position_size_pct"] < 0.03, (
            f"Low risk should have <3% position, got {params['position_size_pct']}"
        )

        # Low greed should give smaller take profits
        assert params["take_profit_pct"] < 0.08, f"Low greed should have <8% TP, got {params['take_profit_pct']}"

    def test_default_traits_produce_reasonable_params(self, default_traits):
        """CONTRACT: Default (0.5) traits produce middle-of-road params."""
        params = get_trading_parameters(default_traits)

        # Position size should be middle range
        assert 0.04 < params["position_size_pct"] < 0.07, (
            f"Default position size should be ~5.5%, got {params['position_size_pct']}"
        )

        # Take profit should be middle range
        assert 0.08 < params["take_profit_pct"] < 0.14, f"Default TP should be ~11%, got {params['take_profit_pct']}"


# =============================================================================
# TEST: All 22 Traits
# =============================================================================


class TestAll22Traits:
    """CONTRACT: All 22 traits are present and properly categorized."""

    def test_trait_count(self):
        """CONTRACT: Exactly 22 traits defined."""
        assert len(ALL_22_TRAITS) == 22, f"Expected 22 traits, got {len(ALL_22_TRAITS)}"

    def test_core_risk_traits(self):
        """CONTRACT: risk_tolerance, hold_duration_bias, volatility_seeking, profit_target_greed."""
        expected = ["risk_tolerance", "hold_duration_bias", "volatility_seeking", "profit_target_greed"]
        for trait in expected:
            assert trait in CORE_RISK_TRAITS, f"{trait} not in CORE_RISK_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_pattern_selection_traits(self):
        """CONTRACT: win_rate_preference, momentum_vs_reversion."""
        expected = ["win_rate_preference", "momentum_vs_reversion"]
        for trait in expected:
            assert trait in PATTERN_SELECTION_TRAITS, f"{trait} not in PATTERN_SELECTION_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_execution_trait(self):
        """CONTRACT: entry_aggression."""
        assert "entry_aggression" in EXECUTION_TRAITS
        assert "entry_aggression" in ALL_22_TRAITS

    def test_technical_trait(self):
        """CONTRACT: lookback_preference."""
        assert "lookback_preference" in TECHNICAL_TRAITS
        assert "lookback_preference" in ALL_22_TRAITS

    def test_sentiment_traits(self):
        """CONTRACT: sentiment_weight, news_reactivity, sentiment_contrarian."""
        expected = ["sentiment_weight", "news_reactivity", "sentiment_contrarian"]
        for trait in expected:
            assert trait in SENTIMENT_TRAITS, f"{trait} not in SENTIMENT_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_macro_traits(self):
        """CONTRACT: funding_rate_sensitivity, correlation_awareness."""
        expected = ["funding_rate_sensitivity", "correlation_awareness"]
        for trait in expected:
            assert trait in MACRO_TRAITS, f"{trait} not in MACRO_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_derived_traits(self):
        """CONTRACT: drawdown_sensitivity, stop_loss_tightness, exit_aggression."""
        expected = ["drawdown_sensitivity", "stop_loss_tightness", "exit_aggression"]
        for trait in expected:
            assert trait in DERIVED_TRAITS, f"{trait} not in DERIVED_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_additional_traits(self):
        """CONTRACT: Additional traits to reach 22."""
        expected = [
            "patience",
            "adaptability",
            "trend_following",
            "mean_reversion",
            "breakout_preference",
            "volume_sensitivity",
        ]
        for trait in expected:
            assert trait in ADDITIONAL_TRAITS, f"{trait} not in ADDITIONAL_TRAITS"
            assert trait in ALL_22_TRAITS, f"{trait} not in ALL_22_TRAITS"

    def test_no_duplicate_traits(self):
        """CONTRACT: No duplicate trait names."""
        assert len(ALL_22_TRAITS) == len(set(ALL_22_TRAITS)), "Duplicate traits detected"

    def test_generated_traits_complete(self):
        """CONTRACT: generate_all_traits produces all 22."""
        traits = generate_all_traits(seed=42)
        for trait_name in ALL_22_TRAITS:
            assert trait_name in traits, f"Generated traits missing {trait_name}"
            assert 0.0 <= traits[trait_name] <= 1.0, f"{trait_name} out of bounds"


# =============================================================================
# TEST: Edge Cases
# =============================================================================


class TestEdgeCases:
    """CONTRACT: Edge cases and boundary conditions."""

    def test_none_trait_values_in_trading_params(self):
        """CONTRACT: None values in traits use defaults (0.5)."""
        traits_with_none = {
            "risk_tolerance": None,
            "stop_loss_tightness": None,
            "profit_target_greed": None,
            "hold_duration_bias": None,
        }

        params = get_trading_parameters(traits_with_none)

        # Should use default 0.5 values
        expected_pos = calculate_position_size(0.5)
        expected_sl = calculate_stop_loss(0.5)
        expected_tp = calculate_take_profit(0.5)

        assert params["position_size_pct"] == expected_pos
        assert params["stop_loss_pct"] == expected_sl
        assert params["take_profit_pct"] == expected_tp

    def test_missing_trait_keys_in_trading_params(self):
        """CONTRACT: Missing trait keys use defaults."""
        empty_traits = {}
        params = get_trading_parameters(empty_traits)

        # Should use default 0.5 values
        assert params["position_size_pct"] == calculate_position_size(0.5)
        assert params["stop_loss_pct"] == calculate_stop_loss(0.5)
        assert params["take_profit_pct"] == calculate_take_profit(0.5)

    def test_float_precision(self):
        """CONTRACT: Results have reasonable float precision."""
        # Test that calculations produce values close to expected
        # (allowing for normal IEEE 754 floating-point representation)
        pos_size = calculate_position_size(0.5)
        stop_loss = calculate_stop_loss(0.5)
        take_profit = calculate_take_profit(0.5)

        # Values should be very close to expected (within floating-point tolerance)
        assert abs(pos_size - 0.055) < 1e-9, f"Position size should be ~0.055, got {pos_size}"
        assert abs(stop_loss - 0.055) < 1e-9, f"Stop loss should be ~0.055, got {stop_loss}"
        assert abs(take_profit - 0.11) < 1e-9, f"Take profit should be ~0.11, got {take_profit}"

    def test_trait_validation_rejects_invalid(self):
        """CONTRACT: validate_trait_value rejects invalid inputs."""
        # None
        is_valid, _ = validate_trait_value(None)
        assert not is_valid

        # NaN
        is_valid, _ = validate_trait_value(float("nan"))
        assert not is_valid

        # Infinity
        is_valid, _ = validate_trait_value(float("inf"))
        assert not is_valid

        # Out of bounds
        is_valid, _ = validate_trait_value(-0.1)
        assert not is_valid

        is_valid, _ = validate_trait_value(1.1)
        assert not is_valid

        # Non-numeric
        is_valid, _ = validate_trait_value("0.5")
        assert not is_valid

    def test_trait_validation_accepts_valid(self):
        """CONTRACT: validate_trait_value accepts valid inputs."""
        valid_values = [0.0, 0.5, 1.0, 0.123456789, 0]

        for value in valid_values:
            is_valid, error = validate_trait_value(value)
            assert is_valid, f"Value {value} should be valid: {error}"

    def test_clamp_traits_handles_extremes(self):
        """CONTRACT: clamp_traits handles out-of-bounds values."""
        bad_traits = {
            "risk_tolerance": -0.5,
            "hold_duration_bias": 1.5,
            "volatility_seeking": 0.5,
        }

        clamped = clamp_traits(bad_traits)

        assert clamped["risk_tolerance"] == 0.0
        assert clamped["hold_duration_bias"] == 1.0
        assert clamped["volatility_seeking"] == 0.5


# =============================================================================
# TEST: Crossover
# =============================================================================


class TestCrossover:
    """CONTRACT: Crossover produces valid offspring."""

    def test_crossover_produces_average(self):
        """CONTRACT: Crossover averages parent traits."""
        parent_a = dict.fromkeys(BASE_TRAITS, 0.2)
        parent_b = dict.fromkeys(BASE_TRAITS, 0.8)

        child = crossover_traits(parent_a, parent_b)

        for trait_name in BASE_TRAITS:
            # Child should be average of parents
            expected = 0.5
            actual = child[trait_name]
            assert abs(actual - expected) < 1e-9, f"{trait_name}: expected {expected}, got {actual}"

    def test_crossover_includes_derived(self):
        """CONTRACT: Crossover produces derived traits."""
        parent_a = dict.fromkeys(BASE_TRAITS, 0.3)
        parent_b = dict.fromkeys(BASE_TRAITS, 0.7)

        child = crossover_traits(parent_a, parent_b)

        for trait_name in DERIVED_TRAITS:
            assert trait_name in child, f"Missing derived trait {trait_name}"
            assert 0.0 <= child[trait_name] <= 1.0, f"{trait_name} out of bounds"

    def test_crossover_and_mutate_bounded(self):
        """CONTRACT: crossover_and_mutate produces bounded traits."""
        parent_a = dict.fromkeys(ALL_22_TRAITS, 0.1)
        parent_b = dict.fromkeys(ALL_22_TRAITS, 0.9)

        for _ in range(100):
            child = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.15)

            for trait_name, value in child.items():
                assert 0.0 <= value <= 1.0, f"{trait_name}={value} out of bounds"

    def test_crossover_deterministic_with_seed(self):
        """CONTRACT: Same seed produces same offspring."""
        parent_a = dict.fromkeys(BASE_TRAITS, 0.3)
        parent_b = dict.fromkeys(BASE_TRAITS, 0.7)

        child1 = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.10, seed=42)
        child2 = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.10, seed=42)

        assert traits_are_equal(child1, child2), "Same seed should produce same offspring"


# =============================================================================
# TEST: Fill Missing Traits
# =============================================================================


class TestFillMissingTraits:
    """CONTRACT: fill_missing_traits completes partial trait sets."""

    def test_fill_missing_adds_all_traits(self):
        """CONTRACT: Partial traits become complete."""
        partial = {"risk_tolerance": 0.7}

        complete = fill_missing_traits(partial, seed=42)

        # Should have all 22 traits
        for trait_name in ALL_22_TRAITS:
            assert trait_name in complete, f"Missing {trait_name}"

        # Original trait preserved
        assert complete["risk_tolerance"] == 0.7

    def test_fill_missing_deterministic_with_seed(self):
        """CONTRACT: Same seed fills same values."""
        partial = {"risk_tolerance": 0.5}

        complete1 = fill_missing_traits(partial, seed=42)
        complete2 = fill_missing_traits(partial, seed=42)

        # Note: Derived traits have noise, so check base traits
        for trait_name in BASE_TRAITS:
            assert complete1[trait_name] == complete2[trait_name], f"{trait_name} differs with same seed"

    def test_fill_missing_bounded(self):
        """CONTRACT: Filled traits are bounded [0, 1]."""
        for _ in range(100):
            complete = fill_missing_traits({})

            for trait_name, value in complete.items():
                assert 0.0 <= value <= 1.0, f"{trait_name}={value} out of bounds"
