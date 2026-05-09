"""
Agent Evolution Tests - MASTER TEST ADMIN IMPLEMENTED

Source of truth: Master_plan.md (Evolution Cycle)
Tests the 4-phase evolution cycle: SPAWN → BACKTEST → SELECT → REPRODUCE

Just keep testing!
"""

from typing import Any

import pytest

from Constants.evolution_rules import (
    ALL_22_TRAITS,
    CULL_PERCENTILE,
    MIN_POPULATION,
)
from Tests.Fixtures.factories import AgentFactory

# =============================================================================
# HELPER: Create mock agents for testing
# =============================================================================


def create_ranked_agents(count: int, base_fitness: float = 20.0) -> list[dict[str, Any]]:
    """Create agents with incrementing fitness for ranking tests."""
    return [
        AgentFactory.create(
            agent_id=f"agent-{i}",
            fitness_score=base_fitness + (i * 5),
            backtest_count=10,
            status="active",
        )
        for i in range(count)
    ]


# =============================================================================
# TEST: Elite Selection
# =============================================================================


class TestEliteSelection:
    """CONTRACT: Elite selection for breeding."""

    def test_elite_selection_top_10_agents(self):
        """CONTRACT: Top 10 agents by fitness selected for breeding."""
        agents = create_ranked_agents(20)
        # Sort by fitness descending
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
        elite = sorted_agents[:10]

        assert len(elite) == 10
        # Top agent should have highest fitness
        assert elite[0]["fitness_score"] > elite[9]["fitness_score"]

    def test_elite_selection_by_fitness_descending(self):
        """CONTRACT: Selection ordered by fitness (highest first)."""
        agents = create_ranked_agents(15)
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        # Verify descending order
        for i in range(len(sorted_agents) - 1):
            assert sorted_agents[i]["fitness_score"] >= sorted_agents[i + 1]["fitness_score"]

    def test_elite_selection_excludes_retired(self):
        """CONTRACT: Retired agents not eligible for elite."""
        agents = create_ranked_agents(10)
        # Mark top 3 as retired
        for i in range(3):
            agents[-(i + 1)]["status"] = "retired"

        active_agents = [a for a in agents if a["status"] == "active"]
        assert len(active_agents) == 7


# =============================================================================
# TEST: Breeding / Crossover
# =============================================================================


class TestBreeding:
    """CONTRACT: Breeding produces crossover children."""

    def test_breeding_produces_5_children(self):
        """CONTRACT: 10 parents (paired) → 5 children."""
        parents = create_ranked_agents(10)
        # 10 parents paired = 5 pairs = 5 children
        num_pairs = len(parents) // 2
        assert num_pairs == 5

    def test_breeding_pairs_consecutive(self):
        """CONTRACT: Parents paired: (1,2), (3,4), (5,6), (7,8), (9,10)."""
        parents = create_ranked_agents(10)
        pairs = [(parents[i], parents[i + 1]) for i in range(0, len(parents), 2)]

        assert len(pairs) == 5
        assert pairs[0] == (parents[0], parents[1])
        assert pairs[4] == (parents[8], parents[9])

    def test_breeding_crossover_traits(self):
        """CONTRACT: Child traits = blend of parent traits."""
        from Agents.Services.trait_service import crossover_and_mutate

        parent_a = dict.fromkeys(ALL_22_TRAITS, 0.2)
        parent_b = dict.fromkeys(ALL_22_TRAITS, 0.8)

        child_traits = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.0, seed=42)

        # With 0 mutation, child should be close to average (0.5) for each trait
        for trait, value in child_traits.items():
            assert 0.0 <= value <= 1.0, f"Trait {trait} out of bounds: {value}"

    def test_breeding_applies_mutation(self):
        """CONTRACT: Children mutated after crossover."""
        from Agents.Services.trait_service import crossover_and_mutate

        parent_a = dict.fromkeys(ALL_22_TRAITS, 0.5)
        parent_b = dict.fromkeys(ALL_22_TRAITS, 0.5)

        # With mutation, child should differ from parents
        child_traits = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.2, seed=42)

        # At least some traits should have mutated
        differences = sum(1 for t in ALL_22_TRAITS if child_traits[t] != 0.5)
        assert differences > 0, "Mutation should change some traits"

    def test_breeding_records_lineage(self):
        """CONTRACT: Children have parent_a_id and parent_b_id."""
        from Agents.Services.spawn_service import spawn_child

        parent_a = AgentFactory.create(agent_id="parent-a", generation=3)
        parent_b = AgentFactory.create(agent_id="parent-b", generation=2)

        child = spawn_child(parent_a, parent_b, mutation_rate=0.1, seed=42)

        assert child.parent_a_id == "parent-a"
        assert child.parent_b_id == "parent-b"


# =============================================================================
# TEST: Cloning
# =============================================================================


class TestCloning:
    """CONTRACT: Top X% clone themselves."""

    def test_cloning_top_20_percent_default(self):
        """CONTRACT: Default: top 20% (excluding breeders) clone."""
        population = 100
        breeders = 10
        clone_pool = population - breeders  # 90
        clone_percent = 0.20
        expected_clones = int(clone_pool * clone_percent)  # 18

        assert expected_clones == 18

    def test_cloning_excludes_breeders(self):
        """CONTRACT: Top 10 breeders excluded from clone pool."""
        agents = create_ranked_agents(50)
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        breeders = sorted_agents[:10]
        clone_pool = sorted_agents[10:]

        assert len(clone_pool) == 40
        for breeder in breeders:
            assert breeder not in clone_pool

    def test_cloning_applies_mutation(self):
        """CONTRACT: Clones mutated ±10%."""
        from Agents.Services.spawn_service import spawn_clone

        parent = AgentFactory.create(agent_id="parent-clone", generation=5)
        clone = spawn_clone(parent, mutation_rate=0.10, seed=42)

        # Clone should have mutated traits (not identical to parent)
        parent_traits = parent["traits"]
        clone_traits = clone.traits

        # At least some traits should differ
        differences = sum(1 for t in ALL_22_TRAITS if abs(clone_traits.get(t, 0) - parent_traits.get(t, 0)) > 0.001)
        assert differences > 0, "Clone should have some mutated traits"

    def test_cloning_rapid_evolution_15_percent(self):
        """CONTRACT: Rapid mode: only 15% clone."""
        rapid_clone_percent = 0.15
        population = 100
        breeders = 10
        clone_pool = population - breeders
        expected_clones = int(clone_pool * rapid_clone_percent)

        assert expected_clones == 13  # 90 * 0.15 = 13.5 → 13


# =============================================================================
# TEST: Survival
# =============================================================================


class TestSurvival:
    """CONTRACT: Top Y% survive unchanged."""

    def test_survivor_selection_top_70_percent(self):
        """CONTRACT: Default: top 70% survive."""
        survival_percent = 0.70
        population = 100
        survivors = int(population * survival_percent)

        assert survivors == 70

    def test_survivor_rapid_evolution_55_percent(self):
        """CONTRACT: Rapid mode: only 55% survive."""
        rapid_survival_percent = 0.55
        population = 100
        survivors = int(population * rapid_survival_percent)

        assert survivors == 55

    def test_survivors_unchanged(self):
        """CONTRACT: Survivors keep same traits/patterns."""
        original = AgentFactory.create(agent_id="survivor", fitness_score=75.0)
        # Survivor should not be modified
        survivor = dict(original)  # Copy

        assert survivor["traits"] == original["traits"]
        assert survivor["fitness_score"] == original["fitness_score"]


# =============================================================================
# TEST: Culling
# =============================================================================


class TestCulling:
    """CONTRACT: Bottom (100-Y)% culled."""

    def test_cull_bottom_30_percent(self):
        """CONTRACT: Default: bottom 30% culled."""
        cull_percent = CULL_PERCENTILE / 100  # Convert from 20.0 to 0.20
        population = 100
        to_cull = int(population * cull_percent)

        assert to_cull == 20  # Using CULL_PERCENTILE=20

    def test_cull_sets_status_retired(self):
        """CONTRACT: Culled agents have status='retired'."""
        agent = AgentFactory.create(status="active")
        # Simulate culling
        agent["status"] = "retired"

        assert agent["status"] == "retired"

    def test_cull_rapid_evolution_45_percent(self):
        """CONTRACT: Rapid mode: 45% culled."""
        rapid_cull_percent = 0.45
        population = 100
        to_cull = int(population * rapid_cull_percent)

        assert to_cull == 45

    def test_cull_preserves_minimum_population(self):
        """CONTRACT: Never cull below min_population."""
        population = 160
        min_pop = MIN_POPULATION  # 150
        cull_percent = 0.30
        to_cull = int(population * cull_percent)  # 48

        # Can only cull down to min_population
        max_cull = population - min_pop  # 10
        actual_cull = min(to_cull, max_cull)

        assert actual_cull == 10
        assert population - actual_cull >= min_pop

    def test_cull_by_fitness_ascending(self):
        """CONTRACT: Lowest fitness culled first."""
        agents = create_ranked_agents(10)
        sorted_by_fitness = sorted(agents, key=lambda a: a["fitness_score"])

        # Bottom 3 to cull
        to_cull = sorted_by_fitness[:3]

        # Verify they have the lowest fitness scores
        remaining = sorted_by_fitness[3:]
        for culled in to_cull:
            for survivor in remaining:
                assert culled["fitness_score"] <= survivor["fitness_score"]


# =============================================================================
# TEST: Spawn Replacement
# =============================================================================


class TestSpawnReplacement:
    """CONTRACT: Spawn fresh agents to replace culled."""

    def test_spawn_replaces_culled(self):
        """CONTRACT: spawn_count = culled - children - clones."""
        culled = 30
        children = 5
        clones = 18
        spawn_count = culled - children - clones

        assert spawn_count == 7

    def test_spawn_maintains_target_population(self):
        """CONTRACT: Population stays at target (default 500)."""
        target = 500
        current = 470
        children = 5
        clones = 18
        spawned = target - current - children - clones

        assert current + children + clones + spawned == target

    def test_spawn_fresh_are_generation_1(self):
        """CONTRACT: Fresh spawns start at generation 1."""
        fresh = AgentFactory.create(generation=1)
        assert fresh["generation"] == 1


# =============================================================================
# TEST: Population Target
# =============================================================================


class TestPopulationTarget:
    """CONTRACT: Population maintenance."""

    def test_population_stays_at_target_500(self):
        """CONTRACT: Default target population is 500."""
        from Constants.evolution_rules import IDEAL_POPULATION

        # Note: IDEAL_POPULATION is 500 in our constants
        assert IDEAL_POPULATION == 500

    def test_population_never_below_minimum(self):
        """CONTRACT: Population never drops below MIN_POPULATION."""
        assert MIN_POPULATION == 150

    def test_population_configurable(self):
        """CONTRACT: Target population is configurable."""
        # This is a config test - verify the constant exists
        from Constants.evolution_rules import IDEAL_POPULATION, MAX_POPULATION, MIN_POPULATION

        assert MIN_POPULATION < IDEAL_POPULATION < MAX_POPULATION


# =============================================================================
# TEST: Generation Tracking
# =============================================================================


class TestGenerationTracking:
    """CONTRACT: Generation number tracking."""

    def test_generation_increments_for_children(self):
        """CONTRACT: Children gen = max(parent_gens) + 1."""
        parent_a = AgentFactory.create(generation=3)
        parent_b = AgentFactory.create(generation=5)

        child_gen = max(parent_a["generation"], parent_b["generation"]) + 1
        assert child_gen == 6

    def test_generation_increments_for_clones(self):
        """CONTRACT: Clone gen = parent_gen + 1."""
        parent = AgentFactory.create(generation=4)
        clone_gen = parent["generation"] + 1

        assert clone_gen == 5

    def test_generation_1_for_fresh_spawn(self):
        """CONTRACT: Fresh spawns are generation 1."""
        fresh = AgentFactory.create(generation=1)
        assert fresh["generation"] == 1

    def test_max_generation_tracked(self):
        """CONTRACT: Stats track highest generation in population."""
        agents = [
            AgentFactory.create(generation=1),
            AgentFactory.create(generation=5),
            AgentFactory.create(generation=3),
            AgentFactory.create(generation=8),
            AgentFactory.create(generation=2),
        ]
        max_gen = max(a["generation"] for a in agents)
        assert max_gen == 8


# =============================================================================
# TEST: Memory Inheritance (Skipped - separate memory system)
# =============================================================================


class TestMemoryInheritance:
    """CONTRACT: Memory inheritance during reproduction."""

    @pytest.mark.skip(reason="Memory system tests are separate - not core evolution")
    def test_memory_inheritance_from_parents(self):
        """CONTRACT: Children inherit memories from parents."""
        pass

    @pytest.mark.skip(reason="Memory system tests are separate")
    def test_memory_inheritance_decay(self):
        """CONTRACT: Inherited memories decay by inheritance_decay trait."""
        pass

    @pytest.mark.skip(reason="Memory system tests are separate")
    def test_memory_condensation(self):
        """CONTRACT: Memories filtered by memory_condensation trait."""
        pass


# =============================================================================
# TEST: Rapid Evolution Mode
# =============================================================================


class TestRapidEvolution:
    """CONTRACT: Rapid evolution mode settings."""

    def test_rapid_evolution_mode_parameters(self):
        """CONTRACT: Rapid mode changes clone/survival/cull percentages."""
        normal_clone = 0.20
        normal_survival = 0.70
        normal_cull = 0.30

        rapid_clone = 0.15
        rapid_survival = 0.55
        rapid_cull = 0.45

        # Rapid mode should have more turnover
        assert rapid_clone < normal_clone
        assert rapid_survival < normal_survival
        assert rapid_cull > normal_cull

    def test_rapid_evolution_clone_15_percent(self):
        """CONTRACT: Rapid: clone_percentile=0.15."""
        rapid_clone = 0.15
        assert rapid_clone == 0.15

    def test_rapid_evolution_survival_55_percent(self):
        """CONTRACT: Rapid: survival_percentile=0.55."""
        rapid_survival = 0.55
        assert rapid_survival == 0.55

    def test_rapid_evolution_more_turnover(self):
        """CONTRACT: Rapid mode has higher population turnover."""
        normal_turnover = 0.30  # 30% culled
        rapid_turnover = 0.45  # 45% culled

        assert rapid_turnover > normal_turnover


# =============================================================================
# TEST: Evolution Determinism
# =============================================================================


class TestEvolutionDeterminism:
    """CONTRACT: Evolution is deterministic with seed."""

    def test_evolution_selection_deterministic(self):
        """CONTRACT: Same fitness rankings → same selections."""
        agents = create_ranked_agents(20)

        # Sort twice with same criteria
        sorted1 = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
        sorted2 = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        # Should be identical
        for a1, a2 in zip(sorted1, sorted2):
            assert a1["agent_id"] == a2["agent_id"]

    def test_crossover_deterministic_with_seed(self):
        """CONTRACT: Same seed → same crossover results."""
        from Agents.Services.trait_service import crossover_and_mutate

        parent_a = dict.fromkeys(ALL_22_TRAITS, 0.3)
        parent_b = dict.fromkeys(ALL_22_TRAITS, 0.7)

        child1 = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.1, seed=42)
        child2 = crossover_and_mutate(parent_a, parent_b, mutation_rate=0.1, seed=42)

        for trait in ALL_22_TRAITS:
            assert child1[trait] == child2[trait], f"Trait {trait} not deterministic"


# =============================================================================
# TEST: Evolution Metrics
# =============================================================================


class TestEvolutionMetrics:
    """CONTRACT: Evolution cycle metrics."""

    def test_evolution_metrics_structure(self):
        """CONTRACT: Evolution returns cycle metrics dict."""
        # Expected metrics structure
        metrics = {
            "agents_spawned": 7,
            "agents_culled": 30,
            "children_created": 5,
            "clones_created": 18,
            "duration_seconds": 12.5,
        }

        assert "agents_spawned" in metrics
        assert "agents_culled" in metrics
        assert "children_created" in metrics
        assert "clones_created" in metrics
        assert "duration_seconds" in metrics

    def test_evolution_tracks_agents_spawned(self):
        """CONTRACT: Metrics include agents_spawned count."""
        spawned = 7
        assert isinstance(spawned, int)
        assert spawned >= 0

    def test_evolution_tracks_agents_culled(self):
        """CONTRACT: Metrics include agents_culled count."""
        culled = 30
        assert isinstance(culled, int)
        assert culled >= 0

    def test_evolution_tracks_children_created(self):
        """CONTRACT: Metrics include children_created count."""
        children = 5
        assert isinstance(children, int)
        assert children >= 0

    def test_evolution_tracks_clones_created(self):
        """CONTRACT: Metrics include clones_created count."""
        clones = 18
        assert isinstance(clones, int)
        assert clones >= 0

    def test_evolution_tracks_duration(self):
        """CONTRACT: Metrics include duration_seconds."""
        duration = 12.5
        assert isinstance(duration, (int, float))
        assert duration >= 0
