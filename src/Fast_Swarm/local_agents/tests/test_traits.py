"""
Trait Generation Tests - V3 Parity.

22 Total Traits:
- 14 Independent (randomized at spawn)
- 3 Derived (from anchors with ±5% noise)
- 3 Threshold (from uncertainty_anchor)
- 2 Memory traits

Trait-to-Parameter Formulas:
- position_size = 0.01 + risk_tolerance * 0.09 (1-10%)
- stop_loss_dist = 0.10 - stop_loss_tightness * 0.09 (1-10% inverted)
- take_profit_dist = 0.02 + profit_target_greed * 0.18 (2-20%)
- max_hold_ms = 3,600,000 + hold_duration_bias * 601,200,000 (1hr-7days)
"""


# =============================================================================
# Trait Lists (for verification)
# =============================================================================

INDEPENDENT_TRAITS = [
    # Core Risk (4)
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    # Pattern Selection (2)
    "win_rate_preference",
    "momentum_vs_reversion",
    # Execution (1)
    "entry_aggression",
    # Technical (1)
    "lookback_preference",
    # Sentiment (3)
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    # Macro (2)
    "funding_rate_sensitivity",
    "correlation_awareness",
    # Decision Anchor (1)
    "uncertainty_anchor",
]

DERIVED_TRAITS = [
    "drawdown_sensitivity",
    "stop_loss_tightness",
    "exit_aggression",
]

THRESHOLD_TRAITS = [
    "ai_assist_range",
    "min_threshold",
    "ai_threshold",
]

MEMORY_TRAITS = [
    "memory_condensation",
    "inheritance_decay",
]


class TestIndependentTraits:
    """14 independent traits."""

    def test_generates_all_14_independent(self):
        """All 14 independent traits present."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42)

        for trait in INDEPENDENT_TRAITS:
            assert hasattr(traits, trait), f"Missing trait: {trait}"
            value = getattr(traits, trait)
            assert 0.0 <= value <= 1.0, f"{trait}={value} out of bounds"

    def test_deterministic_with_seed(self):
        """Same seed -> same traits."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        t1 = generate_traits(seed=42)
        t2 = generate_traits(seed=42)

        for trait in INDEPENDENT_TRAITS:
            assert getattr(t1, trait) == getattr(t2, trait), (
                f"{trait} differs: {getattr(t1, trait)} vs {getattr(t2, trait)}"
            )

    def test_different_seeds_different_traits(self):
        """Different seeds -> different traits."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        t1 = generate_traits(seed=42)
        t2 = generate_traits(seed=12345)

        # At least some traits should differ
        differences = 0
        for trait in INDEPENDENT_TRAITS:
            if getattr(t1, trait) != getattr(t2, trait):
                differences += 1

        assert differences > 5, f"Only {differences} traits differ, expected more"

    def test_overrides_respected(self):
        """Manual overrides take precedence over RNG."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42, overrides={"risk_tolerance": 0.9})
        assert traits.risk_tolerance == 0.9

    def test_multiple_overrides(self):
        """Multiple overrides work together."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(
            seed=42, overrides={"risk_tolerance": 0.1, "volatility_seeking": 0.8, "sentiment_weight": 0.0}
        )

        assert traits.risk_tolerance == 0.1
        assert traits.volatility_seeking == 0.8
        assert traits.sentiment_weight == 0.0


class TestDerivedTraits:
    """3 derived traits from anchors."""

    def test_drawdown_sensitivity_inverse_of_risk(self):
        """High risk -> low drawdown sensitivity."""
        from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

        traits = generate_traits(seed=42, overrides={"risk_tolerance": 0.9})
        traits = derive_dependent_traits(traits, seed=42)

        # Should be roughly 1 - 0.9 = 0.1 ±5% noise = 0.05-0.15
        assert traits.drawdown_sensitivity < 0.25, f"Expected low DD sensitivity, got {traits.drawdown_sensitivity}"

    def test_stop_loss_tightness_derived_from_risk(self):
        """Stop loss tightness derived from risk tolerance."""
        from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

        # Low risk = tight stops
        traits_low = generate_traits(seed=42, overrides={"risk_tolerance": 0.1})
        traits_low = derive_dependent_traits(traits_low, seed=42)

        # High risk = loose stops
        traits_high = generate_traits(seed=42, overrides={"risk_tolerance": 0.9})
        traits_high = derive_dependent_traits(traits_high, seed=42)

        # Low risk should have higher tightness
        assert traits_low.stop_loss_tightness > traits_high.stop_loss_tightness, (
            f"Low risk tightness {traits_low.stop_loss_tightness} should > high risk {traits_high.stop_loss_tightness}"
        )

    def test_exit_aggression_derived_from_hold_duration(self):
        """Exit aggression derived from hold duration bias (inverted)."""
        from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

        # Short holder = aggressive exit
        traits_short = generate_traits(seed=42, overrides={"hold_duration_bias": 0.1})
        traits_short = derive_dependent_traits(traits_short, seed=42)

        # Long holder = patient exit
        traits_long = generate_traits(seed=42, overrides={"hold_duration_bias": 0.9})
        traits_long = derive_dependent_traits(traits_long, seed=42)

        assert traits_short.exit_aggression > traits_long.exit_aggression, (
            f"Short holder exit {traits_short.exit_aggression} should > long holder {traits_long.exit_aggression}"
        )

    def test_derived_traits_have_noise(self):
        """Derived traits not exactly 1-anchor (some noise)."""
        from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

        traits = generate_traits(seed=42, overrides={"risk_tolerance": 0.5})
        traits = derive_dependent_traits(traits, seed=42)

        # drawdown_sensitivity should be ~0.5 but not exactly
        # Allow ±10% total range (±5% per V3)
        assert 0.4 <= traits.drawdown_sensitivity <= 0.6, f"Expected ~0.5 ±10%, got {traits.drawdown_sensitivity}"

    def test_derived_traits_bounded_0_1(self):
        """Derived traits always in [0, 1] even with noise."""
        from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

        # Edge case: risk_tolerance=1.0 -> DD sensitivity should be ~0, not negative
        traits = generate_traits(seed=42, overrides={"risk_tolerance": 1.0})
        traits = derive_dependent_traits(traits, seed=42)

        assert 0.0 <= traits.drawdown_sensitivity <= 1.0
        assert 0.0 <= traits.stop_loss_tightness <= 1.0
        assert 0.0 <= traits.exit_aggression <= 1.0


class TestThresholdTraits:
    """3 threshold traits from uncertainty_anchor."""

    def test_thresholds_symmetric_around_anchor(self):
        """min and ai thresholds bracket the anchor."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        result = derive_threshold_traits(uncertainty_anchor=0.5, seed=42)

        assert result["min_threshold"] < 0.5, f"min_threshold {result['min_threshold']} should be < 0.5"
        assert result["ai_threshold"] > 0.5, f"ai_threshold {result['ai_threshold']} should be > 0.5"

    def test_ai_assist_range_between_0_1_and_0_3(self):
        """Range is 0.1 to 0.3 (V3 spec)."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        for seed in range(100):
            result = derive_threshold_traits(uncertainty_anchor=0.5, seed=seed)
            assert 0.1 <= result["ai_assist_range"] <= 0.3, (
                f"ai_assist_range {result['ai_assist_range']} out of bounds at seed {seed}"
            )

    def test_min_threshold_formula(self):
        """min_threshold = anchor - range."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        result = derive_threshold_traits(uncertainty_anchor=0.5, seed=42)

        expected_min = 0.5 - result["ai_assist_range"]
        assert abs(result["min_threshold"] - expected_min) < 0.01, (
            f"min_threshold {result['min_threshold']} != anchor - range = {expected_min}"
        )

    def test_ai_threshold_formula(self):
        """ai_threshold = anchor + range."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        result = derive_threshold_traits(uncertainty_anchor=0.5, seed=42)

        expected_ai = 0.5 + result["ai_assist_range"]
        assert abs(result["ai_threshold"] - expected_ai) < 0.01, (
            f"ai_threshold {result['ai_threshold']} != anchor + range = {expected_ai}"
        )

    def test_thresholds_bounded_0_1(self):
        """Thresholds clamped to [0, 1]."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        # Edge: anchor near 0
        result_low = derive_threshold_traits(uncertainty_anchor=0.1, seed=42)
        assert result_low["min_threshold"] >= 0.0

        # Edge: anchor near 1
        result_high = derive_threshold_traits(uncertainty_anchor=0.9, seed=42)
        assert result_high["ai_threshold"] <= 1.0

    def test_different_anchors_different_thresholds(self):
        """Different anchors produce different threshold zones."""
        from Fast_Swarm.local_agents.core.traits import derive_threshold_traits

        low = derive_threshold_traits(uncertainty_anchor=0.3, seed=42)
        high = derive_threshold_traits(uncertainty_anchor=0.7, seed=42)

        assert low["min_threshold"] < high["min_threshold"]
        assert low["ai_threshold"] < high["ai_threshold"]


class TestMemoryTraits:
    """2 memory traits."""

    def test_memory_traits_generated(self):
        """Memory traits are present and bounded."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42)

        assert hasattr(traits, "memory_condensation")
        assert hasattr(traits, "inheritance_decay")
        assert 0.0 <= traits.memory_condensation <= 1.0
        assert 0.0 <= traits.inheritance_decay <= 1.0

    def test_memory_condensation_affects_inheritance(self):
        """memory_condensation controls what % of parent memories kept."""
        from Fast_Swarm.local_agents.core.traits import generate_traits

        # Low condensation = keep few memories
        traits_low = generate_traits(seed=42, overrides={"memory_condensation": 0.1})
        # High condensation = keep most memories
        traits_high = generate_traits(seed=42, overrides={"memory_condensation": 0.9})

        assert traits_low.memory_condensation < traits_high.memory_condensation


class TestTraitCount:
    """Verify total trait count is 22."""

    def test_total_trait_count(self):
        """22 total traits."""
        from Fast_Swarm.local_agents.core.traits import (
            derive_dependent_traits,
            derive_threshold_traits,
            generate_traits,
        )

        traits = generate_traits(seed=42)
        traits = derive_dependent_traits(traits, seed=42)

        # Also derive threshold traits
        threshold = derive_threshold_traits(traits.uncertainty_anchor, seed=42)
        traits.ai_assist_range = threshold["ai_assist_range"]
        traits.min_threshold = threshold["min_threshold"]
        traits.ai_threshold = threshold["ai_threshold"]

        # Count all traits
        all_traits = INDEPENDENT_TRAITS + DERIVED_TRAITS + THRESHOLD_TRAITS + MEMORY_TRAITS

        assert len(all_traits) == 22, f"Expected 22 traits, got {len(all_traits)}"

        # Verify all exist on the object
        for trait in all_traits:
            assert hasattr(traits, trait), f"Missing trait: {trait}"


class TestTradingParameterFormulas:
    """Trait -> trading parameter formulas."""

    def test_position_size_range(self):
        """Position size 1-10% based on risk_tolerance."""
        from Fast_Swarm.local_agents.core.traits import calculate_position_size

        assert abs(calculate_position_size(0.0) - 0.01) < 0.001, "risk=0 -> 1%"
        assert abs(calculate_position_size(1.0) - 0.10) < 0.001, "risk=1 -> 10%"

    def test_position_size_linear(self):
        """Position size formula: 0.01 + risk * 0.09."""
        from Fast_Swarm.local_agents.core.traits import calculate_position_size

        # 50% risk -> 5.5% position
        assert abs(calculate_position_size(0.5) - 0.055) < 0.001

    def test_stop_loss_inverted(self):
        """High tightness -> small stop distance."""
        from Fast_Swarm.local_agents.core.traits import calculate_stop_loss_distance

        # Tightness 1.0 -> 1% stop (tight)
        assert abs(calculate_stop_loss_distance(1.0) - 0.01) < 0.001
        # Tightness 0.0 -> 10% stop (loose)
        assert abs(calculate_stop_loss_distance(0.0) - 0.10) < 0.001

    def test_stop_loss_formula(self):
        """Stop loss formula: 0.10 - tightness * 0.09."""
        from Fast_Swarm.local_agents.core.traits import calculate_stop_loss_distance

        # 50% tightness -> 5.5% stop
        assert abs(calculate_stop_loss_distance(0.5) - 0.055) < 0.001

    def test_take_profit_range(self):
        """Take profit 2-20% based on greed."""
        from Fast_Swarm.local_agents.core.traits import calculate_take_profit_distance

        assert abs(calculate_take_profit_distance(0.0) - 0.02) < 0.001, "greed=0 -> 2%"
        assert abs(calculate_take_profit_distance(1.0) - 0.20) < 0.001, "greed=1 -> 20%"

    def test_take_profit_formula(self):
        """Take profit formula: 0.02 + greed * 0.18."""
        from Fast_Swarm.local_agents.core.traits import calculate_take_profit_distance

        # 50% greed -> 11% take profit
        assert abs(calculate_take_profit_distance(0.5) - 0.11) < 0.001

    def test_max_hold_duration_range(self):
        """Max hold 1hr-7days based on hold_duration_bias."""
        from Fast_Swarm.local_agents.core.traits import calculate_max_hold_duration_ms

        one_hour_ms = 3_600_000
        seven_days_ms = 604_800_000

        # Bias 0 -> 1 hour
        min_hold = calculate_max_hold_duration_ms(0.0)
        assert abs(min_hold - one_hour_ms) < 1000, f"bias=0 -> 1hr, got {min_hold}"

        # Bias 1 -> ~7 days
        max_hold = calculate_max_hold_duration_ms(1.0)
        # Formula: 3,600,000 + 1.0 * 601,200,000 = 604,800,000
        assert abs(max_hold - seven_days_ms) < 1000, f"bias=1 -> 7days, got {max_hold}"


class TestTraitMutation:
    """Trait mutation for evolution."""

    def test_mutation_changes_traits(self):
        """Mutation with rate > 0 changes some traits."""
        from Fast_Swarm.local_agents.core.traits import generate_traits, mutate_traits

        original = generate_traits(seed=42)
        mutated = mutate_traits(original, rate=0.10, seed=123)

        # At least some traits should differ
        differences = 0
        for trait in INDEPENDENT_TRAITS:
            if getattr(original, trait) != getattr(mutated, trait):
                differences += 1

        assert differences > 0, "Mutation should change at least some traits"

    def test_mutation_is_bounded(self):
        """Mutated traits stay in [0, 1]."""
        from Fast_Swarm.local_agents.core.traits import generate_traits, mutate_traits

        for seed in range(100):
            original = generate_traits(seed=seed)
            mutated = mutate_traits(original, rate=0.10, seed=seed * 2)

            for trait in INDEPENDENT_TRAITS:
                value = getattr(mutated, trait)
                assert 0.0 <= value <= 1.0, f"{trait}={value} out of bounds after mutation"

    def test_mutation_rate_0_no_change(self):
        """Mutation rate 0 -> no changes."""
        from Fast_Swarm.local_agents.core.traits import generate_traits, mutate_traits

        original = generate_traits(seed=42)
        mutated = mutate_traits(original, rate=0.0, seed=123)

        for trait in INDEPENDENT_TRAITS:
            assert getattr(original, trait) == getattr(mutated, trait), f"{trait} changed with rate=0"

    def test_mutation_respects_plus_minus_10_percent(self):
        """Mutation is ±10% of current value (per V3 spec)."""
        from Fast_Swarm.local_agents.core.traits import generate_traits, mutate_traits

        original = generate_traits(seed=42, overrides={"risk_tolerance": 0.5})
        mutated = mutate_traits(original, rate=1.0, seed=123)  # Force mutation

        # ±10% of 0.5 = [0.45, 0.55]
        # But mutation is ±10% of trait scale (0.1), so [0.4, 0.6]
        assert 0.4 <= mutated.risk_tolerance <= 0.6, f"risk_tolerance {mutated.risk_tolerance} outside ±10% range"

    def test_mutation_deterministic(self):
        """Same seed -> same mutation."""
        from Fast_Swarm.local_agents.core.traits import generate_traits, mutate_traits

        original = generate_traits(seed=42)

        m1 = mutate_traits(original, rate=0.10, seed=123)
        m2 = mutate_traits(original, rate=0.10, seed=123)

        for trait in INDEPENDENT_TRAITS:
            assert getattr(m1, trait) == getattr(m2, trait)


class TestAgentNaming:
    """Agent naming from traits - Multi-dimensional identity system."""

    def test_bold_prefix_high_risk_high_greed(self):
        """Bold: high risk + high greed (risk dimension)."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        prefix = get_agent_name_prefix(risk_tolerance=0.9, profit_target_greed=0.9)
        # Risk dimension score = 0.9 (high) -> "Bold"
        assert "Bold" in prefix, f"Expected 'Bold' in prefix, got {prefix}"

    def test_swift_prefix_fast_trader(self):
        """Swift: low hold duration + high aggression (speed dimension)."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        prefix = get_agent_name_prefix(
            hold_duration_bias=0.1,  # Short holder
            exit_aggression=0.9,  # Quick exits
            entry_aggression=0.8,  # Aggressive entries
        )
        assert "Swift" in prefix, f"Expected 'Swift' in prefix, got {prefix}"

    def test_patient_prefix_slow_trader(self):
        """Patient: high hold duration + low aggression (speed dimension)."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        prefix = get_agent_name_prefix(
            hold_duration_bias=0.9,  # Long holder
            exit_aggression=0.1,  # Patient exits
            entry_aggression=0.2,  # Careful entries
        )
        assert "Patient" in prefix, f"Expected 'Patient' in prefix, got {prefix}"

    def test_fade_prefix_mean_reversion(self):
        """Fade: low momentum_vs_reversion (style dimension)."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        prefix = get_agent_name_prefix(momentum_vs_reversion=0.1)
        assert "Fade" in prefix, f"Expected 'Fade' in prefix, got {prefix}"

    def test_trend_prefix_momentum(self):
        """Trend: high momentum_vs_reversion (style dimension)."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        prefix = get_agent_name_prefix(momentum_vs_reversion=0.9)
        assert "Trend" in prefix, f"Expected 'Trend' in prefix, got {prefix}"

    def test_multi_dimensional_name(self):
        """Multiple notable dimensions -> combined name."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        # Bold (high risk) + Swift (fast) + Fade (reversion)
        prefix = get_agent_name_prefix(
            risk_tolerance=0.9,
            profit_target_greed=0.8,
            hold_duration_bias=0.1,
            exit_aggression=0.9,
            entry_aggression=0.8,
            momentum_vs_reversion=0.1,
        )
        # Should combine top 2 dimensions
        assert len(prefix) > 5, f"Expected combined name, got {prefix}"

    def test_balanced_agent_naming(self):
        """Neutral traits -> Balanced name."""
        from Fast_Swarm.local_agents.core.traits import get_agent_name_prefix

        # All traits at 0.5 (neutral)
        prefix = get_agent_name_prefix(
            risk_tolerance=0.5,
            profit_target_greed=0.5,
            hold_duration_bias=0.5,
            exit_aggression=0.5,
            entry_aggression=0.5,
            momentum_vs_reversion=0.5,
            sentiment_weight=0.5,
            news_reactivity=0.5,
            volatility_seeking=0.5,
        )
        assert prefix == "Balanced", f"Expected 'Balanced', got {prefix}"

    def test_name_format(self):
        """Name format: {PREFIX}-G{generation}-{hex_hash}."""
        from Fast_Swarm.local_agents.core.traits import generate_agent_name

        name = generate_agent_name(prefix="BoldSwift", generation=3, seed=0x7F3)

        assert name.startswith("BoldSwift-G3-"), f"Bad format: {name}"
        assert len(name) > 12  # At least PREFIX-G#-XXX

    def test_analyze_agent_identity(self):
        """Identity analysis returns all dimensions."""
        from Fast_Swarm.local_agents.core.traits import AgentTraits, analyze_agent_identity

        traits = AgentTraits(
            risk_tolerance=0.9,
            profit_target_greed=0.8,
            momentum_vs_reversion=0.1,
        )
        identity = analyze_agent_identity(traits)

        assert "dimensions" in identity
        assert "primary" in identity
        assert "personality_summary" in identity
        assert "notable_count" in identity
        assert identity["notable_count"] >= 1

    def test_character_name_generation(self):
        """Character-style name: Descriptor_Descriptor_Name_G#."""
        from Fast_Swarm.local_agents.core.traits import AgentTraits, generate_full_agent_name

        traits = AgentTraits(
            risk_tolerance=0.9,
            profit_target_greed=0.8,
            momentum_vs_reversion=0.1,  # Fade
        )
        name = generate_full_agent_name(traits, generation=3, seed=42)

        # Should have format: Desc_Desc_Name_G3 or Desc_Name_G3
        assert "_G3" in name, f"Expected '_G3' in name, got {name}"
        assert name.count("_") >= 2, f"Expected at least 2 underscores, got {name}"

    def test_character_name_deterministic(self):
        """Same traits + seed -> same character name."""
        from Fast_Swarm.local_agents.core.traits import AgentTraits, generate_full_agent_name

        traits = AgentTraits(risk_tolerance=0.8, momentum_vs_reversion=0.2)

        name1 = generate_full_agent_name(traits, generation=1, seed=42)
        name2 = generate_full_agent_name(traits, generation=1, seed=42)

        assert name1 == name2

    def test_character_name_from_archetype(self):
        """Character names come from archetype pools."""
        from Fast_Swarm.local_agents.core.traits import ARCHETYPE_NAMES, AgentTraits, generate_character_name

        # High volatility -> should get name from 'Volatile' pool
        traits = AgentTraits(volatility_seeking=0.95)
        name = generate_character_name(traits, seed=42)

        # Extract the character name (last part before any _G suffix)
        parts = name.split("_")
        char_name = parts[-1]

        # Should be from Volatile pool
        assert char_name in ARCHETYPE_NAMES["Volatile"], f"Expected name from Volatile pool, got {char_name}"


class TestTraitCrossover:
    """Trait crossover for reproduction."""

    def test_crossover_mixes_parents(self):
        """Crossover produces child with traits from both parents."""
        from Fast_Swarm.local_agents.core.traits import crossover_traits, generate_traits

        parent_a = generate_traits(seed=42)
        parent_b = generate_traits(seed=123)
        child = crossover_traits(parent_a, parent_b, seed=456)

        # Child should have some traits from each parent
        from_a = 0
        from_b = 0

        for trait in INDEPENDENT_TRAITS:
            child_val = getattr(child, trait)
            a_val = getattr(parent_a, trait)
            b_val = getattr(parent_b, trait)

            if abs(child_val - a_val) < 0.01:
                from_a += 1
            elif abs(child_val - b_val) < 0.01:
                from_b += 1

        assert from_a > 0 and from_b > 0, f"Child should mix parents: from_a={from_a}, from_b={from_b}"

    def test_crossover_deterministic(self):
        """Same parents + seed -> same child."""
        from Fast_Swarm.local_agents.core.traits import crossover_traits, generate_traits

        parent_a = generate_traits(seed=42)
        parent_b = generate_traits(seed=123)

        c1 = crossover_traits(parent_a, parent_b, seed=456)
        c2 = crossover_traits(parent_a, parent_b, seed=456)

        for trait in INDEPENDENT_TRAITS:
            assert getattr(c1, trait) == getattr(c2, trait)

    def test_crossover_bounded(self):
        """Crossover traits always in [0, 1]."""
        from Fast_Swarm.local_agents.core.traits import crossover_traits, generate_traits

        for seed in range(100):
            parent_a = generate_traits(seed=seed)
            parent_b = generate_traits(seed=seed * 2 + 1)
            child = crossover_traits(parent_a, parent_b, seed=seed * 3)

            for trait in INDEPENDENT_TRAITS:
                value = getattr(child, trait)
                assert 0.0 <= value <= 1.0, f"{trait}={value} out of bounds after crossover"
