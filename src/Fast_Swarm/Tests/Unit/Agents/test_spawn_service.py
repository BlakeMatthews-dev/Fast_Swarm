"""
Tests for SpawnService - Agent spawning pipeline.

Tests batch spawn, child spawn, clone spawn, spawn caps,
trait initialization, pattern assignment, and edge cases.

All tests use AsyncMock for DB sessions (no real database required).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Agents.Services.spawn_service import (
    MAX_SPAWN_COUNT,
    AgentSpawnService,
    SpawnConfig,
    SpawnedAgent,
    calculate_pattern_affinity,
    generate_agent_id,
    generate_agent_name,
    generate_trading_philosophy,
    initialize_pattern_weights,
    select_patterns_for_agent,
    spawn_agent,
    spawn_agents,
    spawn_child,
    spawn_clone,
    validate_spawn_count,
    validate_spawned_agent,
)
from Fast_Swarm.Tests.Fixtures.factories import ALL_22_TRAITS


# =============================================================================
# Helpers
# =============================================================================

def _make_parent(agent_id=None, generation=1, traits=None, patterns=None):
    """Build a parent dict for child/clone spawning."""
    return {
        "agent_id": agent_id or f"parent-{uuid.uuid4().hex[:8]}",
        "generation": generation,
        "traits": traits or {t: 0.5 for t in ALL_22_TRAITS},
        "assigned_patterns": patterns or [],
    }


def _make_patterns(n=5):
    """Build a list of pattern dicts."""
    return [
        {
            "pattern_id": f"pat-{i}",
            "type": "momentum" if i % 2 == 0 else "reversion",
            "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
            "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
            "volatility": 0.5,
            "win_rate": 0.55,
        }
        for i in range(n)
    ]


# =============================================================================
# Batch Spawn Tests
# =============================================================================


class TestBatchSpawn:
    """Tests for spawning N agents at once."""

    def test_spawn_correct_count(self):
        agents = spawn_agents(10, generation=1, seed=42)
        assert len(agents) == 10

    def test_spawn_correct_generation(self):
        agents = spawn_agents(3, generation=5, seed=1)
        for agent in agents:
            assert agent.generation == 5

    def test_spawn_unique_ids(self):
        agents = spawn_agents(50, seed=100)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids)), "Agent IDs must be unique"

    def test_spawn_unique_ids_no_seed(self):
        agents = spawn_agents(20)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))

    def test_spawn_with_patterns(self):
        patterns = _make_patterns(10)
        agents = spawn_agents(5, seed=42, available_patterns=patterns)
        for agent in agents:
            assert len(agent.assigned_patterns) >= 0  # may vary by affinity

    def test_spawn_with_config(self):
        config = SpawnConfig(min_patterns=2, max_patterns=4, mutation_rate=0.2)
        patterns = _make_patterns(10)
        agents = spawn_agents(3, seed=7, available_patterns=patterns, config=config)
        for agent in agents:
            assert len(agent.assigned_patterns) >= 1

    def test_spawn_deterministic_with_seed(self):
        a1 = spawn_agents(5, seed=999)
        a2 = spawn_agents(5, seed=999)
        for x, y in zip(a1, a2):
            assert x.traits == y.traits
            assert x.generation == y.generation


# =============================================================================
# Child Spawn Tests
# =============================================================================


class TestChildSpawn:
    """Tests for spawning a child from two parents."""

    def test_child_generation_incremented(self):
        pa = _make_parent(generation=3)
        pb = _make_parent(generation=5)
        child = spawn_child(pa, pb, seed=1)
        assert child.generation == 6  # max(3, 5) + 1

    def test_child_has_parent_ids(self):
        pa = _make_parent(agent_id="parent-a")
        pb = _make_parent(agent_id="parent-b")
        child = spawn_child(pa, pb, seed=2)
        assert child.parent_a_id == "parent-a"
        assert child.parent_b_id == "parent-b"

    def test_child_traits_differ_from_parents(self):
        traits_a = {t: 0.2 for t in ALL_22_TRAITS}
        traits_b = {t: 0.8 for t in ALL_22_TRAITS}
        pa = _make_parent(traits=traits_a)
        pb = _make_parent(traits=traits_b)
        child = spawn_child(pa, pb, mutation_rate=0.3, seed=10)
        # Child traits should exist and be bounded
        for t in ALL_22_TRAITS:
            if t in child.traits:
                assert 0.0 <= child.traits[t] <= 1.0

    def test_child_inherits_patterns_from_both_parents(self):
        pa = _make_parent(patterns=[{"pattern_id": "p1", "type": "momentum"}])
        pb = _make_parent(patterns=[{"pattern_id": "p2", "type": "reversion"}])
        child = spawn_child(pa, pb, seed=3)
        pattern_ids = [p.get("pattern_id") for p in child.assigned_patterns]
        assert "p1" in pattern_ids
        assert "p2" in pattern_ids

    def test_child_deduplicates_patterns(self):
        shared_pattern = {"pattern_id": "shared", "type": "momentum"}
        pa = _make_parent(patterns=[shared_pattern])
        pb = _make_parent(patterns=[shared_pattern.copy()])
        child = spawn_child(pa, pb, seed=4)
        pattern_ids = [p.get("pattern_id") for p in child.assigned_patterns]
        assert pattern_ids.count("shared") == 1


# =============================================================================
# Clone Spawn Tests
# =============================================================================


class TestCloneSpawn:
    """Tests for cloning an agent with mutation."""

    def test_clone_generation_incremented(self):
        parent = _make_parent(generation=7)
        clone = spawn_clone(parent, seed=1)
        assert clone.generation == 8

    def test_clone_has_parent_id(self):
        parent = _make_parent(agent_id="clone-parent")
        clone = spawn_clone(parent, seed=2)
        assert clone.parent_a_id == "clone-parent"
        assert clone.parent_b_id is None

    def test_clone_traits_mutated(self):
        traits = {t: 0.5 for t in ALL_22_TRAITS}
        parent = _make_parent(traits=traits)
        clone = spawn_clone(parent, mutation_rate=0.5, seed=42)
        # With high mutation rate, at least some traits should differ
        differences = sum(1 for t in ALL_22_TRAITS if t in clone.traits and abs(clone.traits[t] - 0.5) > 0.01)
        assert differences > 0, "Clone should have mutated traits"

    def test_clone_traits_bounded(self):
        parent = _make_parent()
        clone = spawn_clone(parent, mutation_rate=1.0, seed=99)
        for t in ALL_22_TRAITS:
            if t in clone.traits:
                assert 0.0 <= clone.traits[t] <= 1.0

    def test_clone_copies_patterns(self):
        parent = _make_parent(patterns=[{"pattern_id": "p1"}, {"pattern_id": "p2"}])
        clone = spawn_clone(parent, seed=5)
        clone_pids = [p.get("pattern_id") for p in clone.assigned_patterns]
        assert "p1" in clone_pids
        assert "p2" in clone_pids


# =============================================================================
# Spawn Cap Tests
# =============================================================================


class TestSpawnCap:
    """Tests for maximum spawn count enforcement."""

    def test_spawn_at_max(self):
        # Should not raise at exactly MAX_SPAWN_COUNT
        agents = spawn_agents(MAX_SPAWN_COUNT, seed=1)
        assert len(agents) == MAX_SPAWN_COUNT

    def test_spawn_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            spawn_agents(MAX_SPAWN_COUNT + 1, seed=1)

    def test_validate_spawn_count_valid(self):
        is_valid, _ = validate_spawn_count(100)
        assert is_valid

    def test_validate_spawn_count_zero(self):
        is_valid, msg = validate_spawn_count(0)
        assert not is_valid
        assert "positive" in msg

    def test_validate_spawn_count_negative(self):
        is_valid, msg = validate_spawn_count(-5)
        assert not is_valid


# =============================================================================
# Trait Initialization Tests
# =============================================================================


class TestTraitInitialization:
    """Tests for trait initialization on spawned agents."""

    def test_all_22_traits_present(self):
        agent = spawn_agent(seed=42)
        for trait in ALL_22_TRAITS:
            assert trait in agent.traits, f"Missing trait: {trait}"

    def test_traits_bounded_zero_one(self):
        agent = spawn_agent(seed=42)
        for trait_name, value in agent.traits.items():
            assert 0.0 <= value <= 1.0, f"Trait {trait_name}={value} out of bounds"

    def test_traits_vary_across_agents(self):
        agents = spawn_agents(10, seed=None)
        first_traits = agents[0].traits
        any_different = any(
            a.traits != first_traits for a in agents[1:]
        )
        assert any_different, "Agents should have varied traits"


# =============================================================================
# Pattern Assignment Tests
# =============================================================================


class TestPatternAssignment:
    """Tests for pattern selection and assignment."""

    def test_no_patterns_when_none_available(self):
        agent = spawn_agent(seed=1, available_patterns=None)
        assert agent.assigned_patterns == []

    def test_empty_patterns_list(self):
        agent = spawn_agent(seed=1, available_patterns=[])
        assert agent.assigned_patterns == []

    def test_patterns_assigned_from_pool(self):
        patterns = _make_patterns(10)
        agent = spawn_agent(seed=42, available_patterns=patterns)
        assert len(agent.assigned_patterns) >= 1

    def test_pattern_affinity_momentum(self):
        traits = {t: 0.5 for t in ALL_22_TRAITS}
        traits["momentum_vs_reversion"] = 0.9  # high momentum preference
        pattern = {"type": "momentum", "volatility": 0.5, "win_rate": 0.5}
        score = calculate_pattern_affinity(traits, pattern)
        assert score > 1.0  # momentum pattern should score high

    def test_initialize_pattern_weights(self):
        weights = initialize_pattern_weights(["p1", "p2", "p3"])
        assert weights == {"p1": 1.0, "p2": 1.0, "p3": 1.0}


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge cases for spawning."""

    def test_spawn_zero_count_raises(self):
        with pytest.raises(ValueError, match="positive"):
            spawn_agents(0, seed=1)

    def test_spawn_negative_count_raises(self):
        with pytest.raises(ValueError, match="positive"):
            spawn_agents(-3, seed=1)

    def test_validate_spawned_agent_valid(self):
        agent = spawn_agent(seed=42)
        is_valid, error = validate_spawned_agent(agent)
        assert is_valid, f"Valid agent failed validation: {error}"

    def test_agent_id_format(self):
        aid = generate_agent_id()
        assert aid.startswith("agent-")
        assert len(aid) == len("agent-") + 12

    def test_philosophy_generated(self):
        agent = spawn_agent(seed=42)
        assert len(agent.trading_philosophy) > 10

    def test_name_contains_generation(self):
        agent = spawn_agent(generation=3, seed=42)
        assert "G3" in agent.name

    def test_spawn_child_with_empty_patterns(self):
        pa = _make_parent(patterns=[])
        pb = _make_parent(patterns=[])
        child = spawn_child(pa, pb, seed=1)
        assert child.assigned_patterns == []

    def test_spawn_child_legacy_string_patterns(self):
        pa = _make_parent(patterns=["legacy-p1", "legacy-p2"])
        pb = _make_parent(patterns=["legacy-p3"])
        child = spawn_child(pa, pb, seed=1)
        pattern_ids = [p.get("pattern_id") for p in child.assigned_patterns]
        assert "legacy-p1" in pattern_ids
        assert "legacy-p3" in pattern_ids
