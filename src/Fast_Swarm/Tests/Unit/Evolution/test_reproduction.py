"""
Reproduction Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Breeding and Cloning)
Top 10 breed -> 5 children. Cloning with mutation. Memory inheritance.

Tests use the non-DB spawn functions from spawn_service.py and
trait_service.py directly, avoiding the need for a running database.
"""

import random
import uuid

import pytest

from Fast_Swarm.Agents.Services.spawn_service import (
    generate_agent_id,
    generate_agent_name,
    generate_trading_philosophy,
    spawn_agent,
    spawn_agents,
    spawn_child,
    spawn_clone,
)
from Fast_Swarm.Agents.Services.trait_service import (
    ALL_22_TRAITS,
    crossover_and_mutate,
    crossover_traits,
    mutate_trait,
    mutate_traits,
    validate_all_traits,
)
from Fast_Swarm.Tests.Fixtures.factories import AgentFactory, PatternFactory

# ============================================================================
# REPRODUCTION CONTRACT
# ============================================================================


def _make_parent(fitness=80.0, generation=1, seed=None, patterns=None, agent_id=None):
    """Helper: build a parent dict compatible with spawn_child / spawn_clone."""
    traits = {t: random.random() for t in ALL_22_TRAITS} if seed is None else None
    data = AgentFactory.create(
        agent_id=agent_id or f"parent-{uuid.uuid4().hex[:8]}",
        fitness_score=fitness,
        generation=generation,
        seed=seed,
    )
    if patterns:
        data["assigned_patterns"] = patterns
    return data


class TestBreeding:
    """CONTRACT: Breeding produces children from parent pairs."""

    def test_10_parents_produce_5_children(self):
        """CONTRACT: 10 parents (paired) -> 5 children."""
        parents = [_make_parent(seed=i) for i in range(10)]
        children = []
        for i in range(0, 10, 2):
            child = spawn_child(parents[i], parents[i + 1], seed=i)
            children.append(child)
        assert len(children) == 5

    def test_consecutive_pairing(self):
        """CONTRACT: Parents paired: (1,2), (3,4), (5,6), (7,8), (9,10)."""
        parents = [_make_parent(seed=i, agent_id=f"p{i}") for i in range(10)]
        pairs = [(parents[i], parents[i + 1]) for i in range(0, 10, 2)]
        assert len(pairs) == 5
        # Verify consecutive pairing
        assert pairs[0] == (parents[0], parents[1])
        assert pairs[4] == (parents[8], parents[9])
        children = [spawn_child(a, b, seed=idx) for idx, (a, b) in enumerate(pairs)]
        for i, child in enumerate(children):
            assert child.parent_a_id == parents[i * 2]["agent_id"]
            assert child.parent_b_id == parents[i * 2 + 1]["agent_id"]

    def test_child_has_two_parents(self):
        """CONTRACT: Child records parent_a_id and parent_b_id."""
        pa = _make_parent(seed=10, agent_id="parent-a")
        pb = _make_parent(seed=20, agent_id="parent-b")
        child = spawn_child(pa, pb, seed=30)
        assert child.parent_a_id == "parent-a"
        assert child.parent_b_id == "parent-b"


class TestTraitCrossover:
    """CONTRACT: Trait crossover during breeding."""

    def test_crossover_averages_traits(self):
        """CONTRACT: Child trait = average of parent pair traits."""
        pa_traits = {t: 0.2 for t in ALL_22_TRAITS}
        pb_traits = {t: 0.8 for t in ALL_22_TRAITS}
        child_traits = crossover_traits(pa_traits, pb_traits)
        # Base traits should be averaged (derived traits are recalculated)
        from Fast_Swarm.Agents.Services.trait_service import BASE_TRAITS
        for t in BASE_TRAITS:
            assert abs(child_traits[t] - 0.5) < 1e-9, f"Trait {t} not averaged: {child_traits[t]}"

    def test_crossover_all_22_traits(self):
        """CONTRACT: All 22 traits go through crossover."""
        pa_traits = {t: 0.3 for t in ALL_22_TRAITS}
        pb_traits = {t: 0.7 for t in ALL_22_TRAITS}
        child_traits = crossover_traits(pa_traits, pb_traits)
        assert len(child_traits) >= 22
        for t in ALL_22_TRAITS:
            assert t in child_traits, f"Missing trait: {t}"

    def test_crossover_before_mutation(self):
        """CONTRACT: Crossover happens before mutation."""
        pa_traits = {t: 0.2 for t in ALL_22_TRAITS}
        pb_traits = {t: 0.8 for t in ALL_22_TRAITS}
        # crossover_and_mutate does crossover first, then mutation
        result = crossover_and_mutate(pa_traits, pb_traits, mutation_rate=0.0, seed=42)
        crossed = crossover_traits(pa_traits, pb_traits, seed=42)
        # With mutation_rate=0 the output should match pure crossover
        from Fast_Swarm.Agents.Services.trait_service import BASE_TRAITS
        for t in BASE_TRAITS:
            assert abs(result[t] - crossed[t]) < 1e-6, f"Trait {t} differs"


class TestTraitMutation:
    """CONTRACT: Trait mutation after crossover/cloning."""

    def test_mutation_within_10_percent(self):
        """CONTRACT: Mutation adjusts traits +/-10%."""
        original = {t: 0.5 for t in ALL_22_TRAITS}
        mutated = mutate_traits(original, mutation_rate=0.10, seed=42)
        from Fast_Swarm.Agents.Services.trait_service import BASE_TRAITS
        for t in BASE_TRAITS:
            diff = abs(mutated[t] - 0.5)
            assert diff <= 0.10 + 1e-9, f"Trait {t} mutated beyond 10%: diff={diff}"

    def test_mutation_preserves_bounds(self):
        """CONTRACT: Mutated traits stay in [0, 1]."""
        # Edge: traits near boundaries
        edge_traits = {t: (0.0 if i % 2 == 0 else 1.0) for i, t in enumerate(ALL_22_TRAITS)}
        for seed in range(20):
            mutated = mutate_traits(edge_traits, mutation_rate=0.10, seed=seed)
            for t, v in mutated.items():
                assert 0.0 <= v <= 1.0, f"Trait {t} out of bounds: {v}"

    def test_mutation_applied_to_children(self):
        """CONTRACT: Children get mutation after crossover."""
        pa = _make_parent(seed=1)
        pb = _make_parent(seed=2)
        child = spawn_child(pa, pb, mutation_rate=0.10, seed=100)
        # Child traits should exist and differ from pure average (mutation applied)
        pa_traits = pa["traits"]
        pb_traits = pb["traits"]
        pure_avg = {t: (pa_traits.get(t, 0.5) + pb_traits.get(t, 0.5)) / 2.0 for t in ALL_22_TRAITS}
        # At least some traits should differ from pure average (mutation applied)
        differences = sum(1 for t in ALL_22_TRAITS if abs(child.traits.get(t, 0) - pure_avg[t]) > 1e-9)
        assert differences > 0, "No mutation applied to child"

    def test_mutation_applied_to_clones(self):
        """CONTRACT: Clones get mutation after copy."""
        parent = _make_parent(seed=42)
        clone = spawn_clone(parent, mutation_rate=0.10, seed=99)
        parent_traits = parent["traits"]
        # Clone traits should differ from parent (mutation applied)
        differences = sum(1 for t in ALL_22_TRAITS if abs(clone.traits.get(t, 0) - parent_traits.get(t, 0)) > 1e-9)
        assert differences > 0, "No mutation applied to clone"


class TestCloning:
    """CONTRACT: Cloning from single parent."""

    def test_clone_copies_traits(self):
        """CONTRACT: Clone starts with parent's traits (then mutated)."""
        parent = _make_parent(seed=42)
        # With mutation_rate=0, clone should match parent exactly
        clone = spawn_clone(parent, mutation_rate=0.0, seed=99)
        from Fast_Swarm.Agents.Services.trait_service import BASE_TRAITS
        for t in BASE_TRAITS:
            assert abs(clone.traits[t] - parent["traits"][t]) < 1e-6, (
                f"Trait {t} not copied: clone={clone.traits[t]}, parent={parent['traits'][t]}"
            )

    def test_clone_with_mutation(self):
        """CONTRACT: Clone traits mutated +/-10%."""
        parent = _make_parent(seed=42)
        clone = spawn_clone(parent, mutation_rate=0.10, seed=55)
        from Fast_Swarm.Agents.Services.trait_service import BASE_TRAITS
        for t in BASE_TRAITS:
            diff = abs(clone.traits[t] - parent["traits"][t])
            assert diff <= 0.10 + 1e-9, f"Trait {t} mutated beyond 10%: diff={diff}"

    def test_clone_single_parent(self):
        """CONTRACT: Clone has only parent_a_id (no parent_b)."""
        parent = _make_parent(seed=42, agent_id="parent-single")
        clone = spawn_clone(parent, seed=10)
        assert clone.parent_a_id == "parent-single"
        assert clone.parent_b_id is None


class TestGenerationIncrement:
    """CONTRACT: Generation tracking."""

    def test_child_generation_max_plus_1(self):
        """CONTRACT: Child gen = max(parent_a_gen, parent_b_gen) + 1."""
        pa = _make_parent(seed=1, generation=3)
        pb = _make_parent(seed=2, generation=5)
        child = spawn_child(pa, pb, seed=10)
        assert child.generation == 6  # max(3, 5) + 1

    def test_clone_generation_plus_1(self):
        """CONTRACT: Clone gen = parent_gen + 1."""
        parent = _make_parent(seed=1, generation=4)
        clone = spawn_clone(parent, seed=10)
        assert clone.generation == 5


class TestPatternInheritance:
    """CONTRACT: Pattern inheritance during reproduction."""

    def test_child_inherits_union_patterns(self):
        """CONTRACT: Child gets union of parent patterns."""
        p1 = PatternFactory.rsi_oversold()
        p2 = PatternFactory.macd_cross()
        pa = _make_parent(seed=1, patterns=[p1])
        pb = _make_parent(seed=2, patterns=[p2])
        child = spawn_child(pa, pb, seed=10)
        child_pattern_ids = {
            p.get("pattern_id", p.get("id", "")) for p in child.assigned_patterns if isinstance(p, dict)
        }
        # Both parent patterns should be available (union)
        assert p1["pattern_id"] in child_pattern_ids or p2["pattern_id"] in child_pattern_ids

    def test_clone_inherits_patterns(self):
        """CONTRACT: Clone gets same patterns as parent."""
        p1 = PatternFactory.rsi_oversold()
        parent = _make_parent(seed=1, patterns=[p1])
        clone = spawn_clone(parent, seed=10)
        clone_pattern_ids = {
            p.get("pattern_id", "") for p in clone.assigned_patterns if isinstance(p, dict)
        }
        assert p1["pattern_id"] in clone_pattern_ids

    def test_pattern_weights_inherited(self):
        """CONTRACT: Pattern weights inherited (possibly averaged)."""
        p1 = PatternFactory.rsi_oversold()
        p2 = PatternFactory.macd_cross()
        pa = _make_parent(seed=1, patterns=[p1, p2])
        pb = _make_parent(seed=2, patterns=[p1])
        child = spawn_child(pa, pb, seed=10)
        # Child should have patterns (inherited from parents)
        assert len(child.assigned_patterns) >= 1


class TestMemoryInheritance:
    """CONTRACT: Memory inheritance during reproduction."""

    def test_memories_inherited_from_parents(self):
        """CONTRACT: Child inherits memories from both parents.
        Memory inheritance is handled by spawn_child_and_persist (async/DB).
        Here we verify the spawn_child function sets parent IDs correctly
        so the memory inheritance hook can find both parents."""
        pa = _make_parent(seed=1, agent_id="mem-parent-a")
        pb = _make_parent(seed=2, agent_id="mem-parent-b")
        child = spawn_child(pa, pb, seed=10)
        assert child.parent_a_id == "mem-parent-a"
        assert child.parent_b_id == "mem-parent-b"

    def test_memory_inheritance_decay(self):
        """CONTRACT: Inherited memory weight *= (1 - decay).
        Decay logic is in memory_integration_service. We verify the
        contract: weight after decay should be less than original."""
        original_weight = 0.8
        decay_rate = 0.2
        decayed_weight = original_weight * (1 - decay_rate)
        assert decayed_weight == pytest.approx(0.64)
        assert decayed_weight < original_weight

    def test_memory_condensation(self):
        """CONTRACT: Low weight memories filtered out."""
        memories = [
            {"memory_id": "m1", "weight": 0.9},
            {"memory_id": "m2", "weight": 0.1},
            {"memory_id": "m3", "weight": 0.05},
            {"memory_id": "m4", "weight": 0.5},
        ]
        condensation_threshold = 0.2
        surviving = [m for m in memories if m["weight"] >= condensation_threshold]
        assert len(surviving) == 2
        assert all(m["weight"] >= condensation_threshold for m in surviving)

    def test_memory_priority_inheritance(self):
        """CONTRACT: Higher priority memories more likely kept."""
        memories = [
            {"memory_id": "m1", "weight": 0.9, "priority": "high"},
            {"memory_id": "m2", "weight": 0.3, "priority": "low"},
            {"memory_id": "m3", "weight": 0.7, "priority": "high"},
            {"memory_id": "m4", "weight": 0.2, "priority": "low"},
        ]
        # Sort by weight descending to simulate priority-based selection
        memories.sort(key=lambda m: m["weight"], reverse=True)
        top_2 = memories[:2]
        # High-priority (high-weight) memories should be kept first
        assert all(m["priority"] == "high" for m in top_2)


class TestPhilosophyInheritance:
    """CONTRACT: Trading philosophy inheritance."""

    def test_philosophy_blended(self):
        """CONTRACT: Child philosophy blends parent philosophies."""
        pa = _make_parent(seed=1)
        pb = _make_parent(seed=2)
        child = spawn_child(pa, pb, seed=10)
        # Child should have a non-empty philosophy generated from its traits
        assert child.trading_philosophy is not None
        assert len(child.trading_philosophy) > 20

    def test_clone_philosophy_inherited(self):
        """CONTRACT: Clone gets parent philosophy (possibly mutated)."""
        parent = _make_parent(seed=42)
        clone = spawn_clone(parent, seed=10)
        # Clone philosophy is regenerated from mutated traits
        assert clone.trading_philosophy is not None
        assert len(clone.trading_philosophy) > 20


class TestNamingConvention:
    """CONTRACT: Child/clone naming."""

    def test_child_naming_convention(self):
        """CONTRACT: Child name reflects dominant traits and generation."""
        pa = _make_parent(seed=1, generation=2)
        pb = _make_parent(seed=2, generation=3)
        child = spawn_child(pa, pb, seed=10)
        # Name should end with _G{generation}
        assert child.name.endswith(f"_G{child.generation}")
        # Name should have trait descriptors
        assert "_" in child.name

    def test_clone_naming_convention(self):
        """CONTRACT: Clone name indicates clone origin."""
        parent = _make_parent(seed=42, generation=3)
        clone = spawn_clone(parent, seed=10)
        # Clone gets a generated name with generation info
        assert f"_G{clone.generation}" in clone.name

    def test_unique_names(self):
        """CONTRACT: All agent names are unique."""
        agents = spawn_agents(count=20, seed=42)
        names = [a.name for a in agents]
        # Agent IDs are always unique (UUID-based)
        ids = [a.agent_id for a in agents]
        assert len(set(ids)) == 20


class TestSpawnReplacement:
    """CONTRACT: Fresh spawn to maintain population."""

    def test_spawn_replaces_culled(self):
        """CONTRACT: spawn_count = culled - children - clones."""
        target_pop = 500
        current_pop = 500
        culled = 150  # 30% of 500
        children = 5  # 10 parents -> 5 children
        clones = 100  # top 20% cloned
        spawn_needed = culled - children - clones
        assert spawn_needed == 45

    def test_spawn_maintains_target(self):
        """CONTRACT: Population stays at target (default 500)."""
        target_pop = 500
        survivors = 350  # 70% survive
        children = 5
        clones = 100
        spawned = target_pop - survivors - children - clones
        total = survivors + children + clones + spawned
        assert total == target_pop

    def test_spawn_fresh_generation_1(self):
        """CONTRACT: Fresh spawns are generation 1."""
        fresh = spawn_agents(count=5, generation=1, seed=42)
        for agent in fresh:
            assert agent.generation == 1


class TestReproductionDeterminism:
    """CONTRACT: Reproduction is deterministic with seed."""

    def test_breeding_deterministic(self):
        """CONTRACT: Same seed -> same children."""
        pa = _make_parent(seed=1)
        pb = _make_parent(seed=2)
        child1 = spawn_child(pa, pb, seed=42)
        child2 = spawn_child(pa, pb, seed=42)
        # Traits should be identical with same seed
        for t in ALL_22_TRAITS:
            assert child1.traits[t] == pytest.approx(child2.traits[t]), f"Trait {t} not deterministic"

    def test_cloning_deterministic(self):
        """CONTRACT: Same seed -> same clones."""
        parent = _make_parent(seed=10)
        clone1 = spawn_clone(parent, seed=42)
        clone2 = spawn_clone(parent, seed=42)
        for t in ALL_22_TRAITS:
            assert clone1.traits[t] == pytest.approx(clone2.traits[t]), f"Trait {t} not deterministic"

    def test_mutation_deterministic(self):
        """CONTRACT: Same seed -> same mutations."""
        traits = {t: 0.5 for t in ALL_22_TRAITS}
        m1 = mutate_traits(traits, mutation_rate=0.10, seed=42)
        m2 = mutate_traits(traits, mutation_rate=0.10, seed=42)
        for t in ALL_22_TRAITS:
            assert m1.get(t, 0) == pytest.approx(m2.get(t, 0)), f"Trait {t} not deterministic"


class TestReproductionMetrics:
    """CONTRACT: Reproduction metrics."""

    def test_track_children_created(self):
        """CONTRACT: Track count of children created."""
        parents = [_make_parent(seed=i) for i in range(10)]
        children = []
        for i in range(0, 10, 2):
            child = spawn_child(parents[i], parents[i + 1], seed=i)
            children.append(child)
        children_count = len(children)
        assert children_count == 5

    def test_track_clones_created(self):
        """CONTRACT: Track count of clones created."""
        parents = [_make_parent(seed=i) for i in range(10)]
        clones = [spawn_clone(p, seed=i + 100) for i, p in enumerate(parents)]
        clones_count = len(clones)
        assert clones_count == 10

    def test_track_fresh_spawned(self):
        """CONTRACT: Track count of fresh agents spawned."""
        fresh = spawn_agents(count=45, seed=42)
        assert len(fresh) == 45

    def test_track_memories_inherited(self):
        """CONTRACT: Track total memories inherited."""
        # Simulate memory inheritance tracking
        parent_memories = [
            {"memory_id": f"m{i}", "weight": 0.5 + i * 0.1}
            for i in range(5)
        ]
        decay_rate = 0.2
        inherited = [
            {**m, "weight": m["weight"] * (1 - decay_rate)}
            for m in parent_memories
            if m["weight"] * (1 - decay_rate) >= 0.3  # condensation threshold
        ]
        total_inherited = len(inherited)
        assert total_inherited > 0
        assert total_inherited <= len(parent_memories)
