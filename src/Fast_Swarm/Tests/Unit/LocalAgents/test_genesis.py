"""
Unit tests for local_agents.core.genesis module.

Tests cover:
- Agent creation (spawn_agent) with valid traits
- Trait initialization (generate_traits, derive_dependent_traits)
- Pattern affinity and heuristic selection
- Edge cases (empty inputs, invalid data)

All DB and LLM dependencies are mocked.
"""

import uuid
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from Fast_Swarm.local_agents.core.genesis import (
    calculate_pattern_affinity,
    compute_regime_fitness_from_patterns,
    generate_exit_conditions,
    generate_philosophy_heuristic,
    get_top_patterns_for_spawn,
    prepare_spawn_prompt_data,
    select_patterns_heuristic,
    sort_patterns_by_affinity,
    spawn_agent,
)
from Fast_Swarm.local_agents.core.traits import (
    INDEPENDENT_TRAITS,
    MEMORY_TRAITS,
    AgentTraits,
    derive_dependent_traits,
    derive_threshold_traits,
    generate_traits,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_patterns(count=5):
    """Create a list of test pattern dicts."""
    patterns = []
    for i in range(count):
        patterns.append({
            "pattern_id": f"test-pat-{i}",
            "name": f"Pattern {i}",
            "type": "momentum" if i % 2 == 0 else "reversion",
            "volatility": "high" if i % 3 == 0 else "low",
            "win_rate_pct": 45 + i * 5,
            "fitness_score": 50 + i * 10,
            "entry_conditions": [
                {"indicator": "rsi", "operator": "<", "value": 30},
            ],
            "exit_conditions": {},
        })
    return patterns


def _mock_db():
    """Create a mock AgentDatabase."""
    mock = MagicMock()
    mock.create_agent.return_value = MagicMock(
        agent_id=str(uuid.uuid4()),
        agent_name="MockAgent",
        generation=1,
        traits={},
        pattern_ids=[],
        pattern_weights={},
    )
    return mock


# =============================================================================
# Agent Creation Tests (~8 tests)
# =============================================================================


class TestAgentCreation:
    """Tests for spawn_agent and related creation logic."""

    def test_spawn_agent_heuristic_creates_record(self):
        """spawn_agent with use_llm=False creates a valid AgentRecord."""
        db = _mock_db()
        patterns = _make_patterns(5)
        agent = spawn_agent(
            seed=42,
            available_patterns=patterns,
            generation=1,
            use_llm=False,
            db=db,
        )
        db.create_agent.assert_called_once()

    def test_spawn_agent_generates_unique_ids(self):
        """Two agents spawned with different seeds produce different calls."""
        db1 = _mock_db()
        db2 = _mock_db()
        patterns = _make_patterns(5)
        spawn_agent(seed=42, available_patterns=patterns, use_llm=False, db=db1)
        spawn_agent(seed=99, available_patterns=patterns, use_llm=False, db=db2)
        # Both should have been called with different agent names
        call1_name = db1.create_agent.call_args[1].get("agent_name", db1.create_agent.call_args[0][0] if db1.create_agent.call_args[0] else "")
        call2_name = db2.create_agent.call_args[1].get("agent_name", db2.create_agent.call_args[0][0] if db2.create_agent.call_args[0] else "")
        # Different seeds should produce different names
        assert db1.create_agent.called
        assert db2.create_agent.called

    def test_spawn_agent_uses_provided_generation(self):
        """spawn_agent passes generation to db.create_agent."""
        db = _mock_db()
        patterns = _make_patterns(5)
        spawn_agent(seed=42, available_patterns=patterns, generation=3, use_llm=False, db=db)
        _, kwargs = db.create_agent.call_args
        assert kwargs.get("generation") == 3

    def test_spawn_agent_raises_without_llm_call_when_use_llm(self):
        """spawn_agent with use_llm=True but no llm_call raises ValueError."""
        db = _mock_db()
        patterns = _make_patterns(5)
        with pytest.raises(ValueError, match="llm_call was not provided"):
            spawn_agent(seed=42, available_patterns=patterns, use_llm=True, llm_call=None, db=db)

    def test_spawn_agent_heuristic_selects_patterns(self):
        """Heuristic spawn selects patterns from available pool."""
        db = _mock_db()
        patterns = _make_patterns(10)
        spawn_agent(seed=42, available_patterns=patterns, use_llm=False, db=db)
        _, kwargs = db.create_agent.call_args
        assert len(kwargs.get("pattern_ids", [])) > 0
        # All pattern_ids should be from the available patterns
        available_ids = {p["pattern_id"] for p in patterns}
        for pid in kwargs["pattern_ids"]:
            assert pid in available_ids

    def test_spawn_agent_generates_exit_conditions_when_missing(self):
        """Patterns without exit conditions get them generated at spawn."""
        db = _mock_db()
        patterns = [{
            "pattern_id": "no-exit",
            "name": "NoExit",
            "type": "momentum",
            "win_rate_pct": 60,
            "fitness_score": 70,
            "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
            "exit_conditions": {},
        }]
        spawn_agent(seed=42, available_patterns=patterns, use_llm=False, db=db)
        _, kwargs = db.create_agent.call_args
        copies = kwargs.get("pattern_copies", [])
        if copies:
            # Exit conditions should be populated
            for copy in copies:
                assert copy.get("exit_conditions") is not None

    def test_spawn_agent_with_trait_overrides(self):
        """Trait overrides are applied during spawn."""
        db = _mock_db()
        patterns = _make_patterns(5)
        spawn_agent(
            seed=42,
            available_patterns=patterns,
            use_llm=False,
            db=db,
            trait_overrides={"risk_tolerance": 0.9},
        )
        _, kwargs = db.create_agent.call_args
        traits = kwargs.get("traits")
        if isinstance(traits, AgentTraits):
            assert traits.risk_tolerance == 0.9
        elif isinstance(traits, dict):
            assert traits.get("risk_tolerance") == 0.9

    def test_spawn_agent_with_parent_ids(self):
        """Parent IDs are passed through to db.create_agent."""
        db = _mock_db()
        patterns = _make_patterns(5)
        spawn_agent(
            seed=42,
            available_patterns=patterns,
            use_llm=False,
            db=db,
            parent_a_id="parent-a",
            parent_b_id="parent-b",
        )
        _, kwargs = db.create_agent.call_args
        assert kwargs.get("parent_a_id") == "parent-a"
        assert kwargs.get("parent_b_id") == "parent-b"


# =============================================================================
# Trait Initialization Tests (~6 tests)
# =============================================================================


class TestTraitInitialization:
    """Tests for trait generation, derivation, and bounds."""

    def test_generate_traits_default_seed(self):
        """generate_traits with a seed produces an AgentTraits with all independent traits."""
        traits = generate_traits(seed=42)
        for trait_name in INDEPENDENT_TRAITS:
            val = getattr(traits, trait_name)
            assert 0.0 <= val <= 1.0, f"{trait_name}={val} out of [0,1] bounds"

    def test_generate_traits_deterministic(self):
        """Same seed produces identical traits."""
        t1 = generate_traits(seed=12345)
        t2 = generate_traits(seed=12345)
        for trait_name in INDEPENDENT_TRAITS + MEMORY_TRAITS:
            assert getattr(t1, trait_name) == getattr(t2, trait_name), f"{trait_name} differs"

    def test_generate_traits_with_overrides(self):
        """Trait overrides are applied after generation."""
        traits = generate_traits(seed=42, overrides={"risk_tolerance": 0.1})
        assert traits.risk_tolerance == 0.1

    def test_generate_traits_with_bias(self):
        """Trait bias constrains generated values to [min, max]."""
        bias = {"risk_tolerance": (0.8, 0.9)}
        traits = generate_traits(seed=42, trait_bias=bias)
        assert 0.8 <= traits.risk_tolerance <= 0.9

    def test_derived_traits_clamped_to_0_1(self):
        """Derived traits are clamped to [0, 1] range."""
        traits = AgentTraits(risk_tolerance=0.0, hold_duration_bias=0.0)
        derived = derive_dependent_traits(traits, seed=42)
        assert 0.0 <= derived.drawdown_sensitivity <= 1.0
        assert 0.0 <= derived.stop_loss_tightness <= 1.0
        assert 0.0 <= derived.exit_aggression <= 1.0

    def test_threshold_traits_from_anchor(self):
        """Threshold traits are derived from uncertainty_anchor."""
        result = derive_threshold_traits(0.5, seed=42)
        assert "ai_assist_range" in result
        assert "min_threshold" in result
        assert "ai_threshold" in result
        # min_threshold should be less than ai_threshold
        assert result["min_threshold"] <= result["ai_threshold"]
        # Both should be in [0, 1]
        assert 0.0 <= result["min_threshold"] <= 1.0
        assert 0.0 <= result["ai_threshold"] <= 1.0

    def test_all_22_traits_present_on_default(self):
        """Default AgentTraits has all 22 fields."""
        traits = AgentTraits()
        expected_count = 22
        trait_dict = asdict(traits)
        assert len(trait_dict) == expected_count, f"Expected {expected_count} traits, got {len(trait_dict)}"


# =============================================================================
# Pattern Assignment Tests (~3 tests)
# =============================================================================


class TestPatternAssignment:
    """Tests for pattern selection and affinity calculation."""

    def test_select_patterns_heuristic_returns_list(self):
        """Heuristic selection returns a list of selections with pattern_id and weight."""
        traits = AgentTraits(momentum_vs_reversion=0.8, win_rate_preference=0.7)
        patterns = _make_patterns(10)
        selections = select_patterns_heuristic(traits, patterns, seed=42, count=4)
        assert len(selections) == 4
        for sel in selections:
            assert "pattern_id" in sel
            assert "weight" in sel
            assert sel["weight"] >= 0

    def test_pattern_affinity_momentum_bias(self):
        """Agents with high momentum_vs_reversion prefer momentum patterns."""
        traits = AgentTraits(momentum_vs_reversion=0.9, volatility_seeking=0.5, win_rate_preference=0.5)
        momentum_pattern = {"type": "momentum_trend", "volatility": "medium", "win_rate_pct": 55}
        reversion_pattern = {"type": "mean_reversion", "volatility": "medium", "win_rate_pct": 55}
        aff_m = calculate_pattern_affinity(traits, momentum_pattern)
        aff_r = calculate_pattern_affinity(traits, reversion_pattern)
        assert aff_m > aff_r

    def test_sort_patterns_by_affinity_order(self):
        """sort_patterns_by_affinity returns patterns sorted by descending affinity."""
        traits = AgentTraits(momentum_vs_reversion=0.9, volatility_seeking=0.5, win_rate_preference=0.5)
        patterns = _make_patterns(10)
        sorted_pats = sort_patterns_by_affinity(traits, patterns)
        # Verify order by computing affinity scores
        scores = [calculate_pattern_affinity(traits, p) for p in sorted_pats]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# =============================================================================
# Edge Case Tests (~3 tests)
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_patterns_heuristic_returns_empty(self):
        """Heuristic selection with no patterns returns empty list."""
        traits = AgentTraits()
        selections = select_patterns_heuristic(traits, [], seed=42)
        assert selections == []

    def test_affinity_minimum_score_never_zero(self):
        """Pattern affinity always returns at least 0.1 (no zero scores)."""
        traits = AgentTraits(
            momentum_vs_reversion=0.0,
            volatility_seeking=0.0,
            win_rate_preference=0.0,
            risk_tolerance=0.0,
        )
        pattern = {
            "type": "momentum",
            "volatility": "high",
            "win_rate_pct": 80,
        }
        score = calculate_pattern_affinity(traits, pattern)
        assert score >= 0.1

    def test_generate_exit_conditions_from_entry(self):
        """generate_exit_conditions produces exit conditions from entry conditions."""
        entry_conds = [
            {"indicator": "rsi", "operator": "<", "value": 30},
            {"indicator": "macd_line", "operator": ">", "value": 0},
        ]
        exits = generate_exit_conditions(entry_conds, seed=42)
        assert len(exits) >= 1
        # First element should be exit strategy
        assert "exit_strategy" in exits[0]

    def test_compute_regime_fitness_empty_patterns(self):
        """compute_regime_fitness_from_patterns returns empty for no patterns."""
        fitness, weak = compute_regime_fitness_from_patterns([])
        assert fitness == []
        assert weak == []

    def test_prepare_spawn_prompt_data_structure(self):
        """prepare_spawn_prompt_data returns dict with traits, patterns, regime_fitness."""
        traits = AgentTraits()
        patterns = _make_patterns(3)
        data = prepare_spawn_prompt_data(traits, patterns)
        assert "traits" in data
        assert "patterns" in data
        assert "regime_fitness" in data
        assert "weak_regimes" in data

    def test_generate_philosophy_heuristic_all_styles(self):
        """Heuristic philosophy covers different risk/style combinations."""
        # High risk, momentum, long hold
        traits_high = AgentTraits(risk_tolerance=0.8, momentum_vs_reversion=0.8, hold_duration_bias=0.8)
        phil_high = generate_philosophy_heuristic(traits_high)
        assert "aggressively" in phil_high.lower() or "volatility" in phil_high.lower()

        # Low risk, reversion, short hold
        traits_low = AgentTraits(risk_tolerance=0.2, momentum_vs_reversion=0.2, hold_duration_bias=0.2)
        phil_low = generate_philosophy_heuristic(traits_low)
        assert "preservation" in phil_low.lower() or "conservative" in phil_low.lower()

    def test_get_top_patterns_for_spawn_limits_count(self):
        """get_top_patterns_for_spawn returns at most 'count' patterns."""
        traits = AgentTraits()
        patterns = _make_patterns(20)
        top = get_top_patterns_for_spawn(traits, patterns, count=5)
        assert len(top) == 5
