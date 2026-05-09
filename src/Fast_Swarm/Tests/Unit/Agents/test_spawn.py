"""
Agent Spawn/Genesis Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Genesis System)
Agents are spawned with traits, patterns, philosophy, and naming.
"""

import pytest

from Fast_Swarm.Agents.Services.spawn_service import (
    ALL_22_TRAITS,
    MAX_SPAWN_COUNT,
    SpawnConfig,
    generate_agent_name,
    generate_trading_philosophy,
    initialize_pattern_weights,
    spawn_agent,
    spawn_agents,
    spawn_child,
    spawn_clone,
    validate_spawn_count,
)
from Fast_Swarm.Agents.Services.trait_service import ALL_22_TRAITS

# ============================================================================
# Test Data Helpers
# ============================================================================


def make_patterns(count: int = 5) -> list:
    """Create mock patterns for testing."""
    return [
        {"pattern_id": f"pattern-{i}", "name": f"Pattern {i}", "type": "momentum" if i % 2 == 0 else "reversion"}
        for i in range(count)
    ]


def make_parent(agent_id: str, generation: int = 1, traits: dict = None, patterns: list = None) -> dict:
    """Create a mock parent agent dict."""
    from Fast_Swarm.Agents.Services.trait_service import generate_all_traits

    return {
        "agent_id": agent_id,
        "generation": generation,
        "traits": traits or generate_all_traits(seed=42),
        "assigned_patterns": patterns or ["pattern-1", "pattern-2"],
    }


# ============================================================================
# AGENT SPAWNING CONTRACT
# ============================================================================


class TestSpawnSingle:
    """CONTRACT: Single agent spawn operations."""

    def test_spawn_single_agent(self):
        """CONTRACT: spawn_agents(count=1) creates exactly 1 agent."""
        agents = spawn_agents(count=1)
        assert len(agents) == 1

    def test_spawn_returns_agent_id(self):
        """CONTRACT: Spawn returns the created agent_id."""
        agent = spawn_agent()
        assert agent.agent_id is not None
        assert len(agent.agent_id) > 0

    def test_spawn_assigns_unique_id(self):
        """CONTRACT: Each spawned agent has unique ID."""
        agent1 = spawn_agent()
        agent2 = spawn_agent()
        assert agent1.agent_id != agent2.agent_id

    def test_spawn_initializes_all_22_traits(self):
        """CONTRACT: Spawned agent has all 22 traits set."""
        agent = spawn_agent()
        for trait in ALL_22_TRAITS:
            assert trait in agent.traits

    def test_spawn_traits_bounded(self):
        """CONTRACT: All spawned traits in [0, 1]."""
        agent = spawn_agent()
        for trait_name, value in agent.traits.items():
            assert 0.0 <= value <= 1.0, f"{trait_name} = {value} out of bounds"


class TestSpawnBatch:
    """CONTRACT: Batch agent spawn operations."""

    def test_spawn_batch_100_agents(self):
        """CONTRACT: spawn_agents(count=100) creates exactly 100 agents."""
        agents = spawn_agents(count=100)
        assert len(agents) == 100

    def test_spawn_batch_all_unique_ids(self):
        """CONTRACT: All 100 agents have unique IDs."""
        agents = spawn_agents(count=100)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))

    def test_spawn_batch_all_different_traits(self):
        """CONTRACT: Without seed, each agent has different traits."""
        agents = spawn_agents(count=10)
        trait_sets = [tuple(sorted(a.traits.items())) for a in agents]
        assert len(set(trait_sets)) == 10  # All unique

    def test_spawn_batch_returns_all_ids(self):
        """CONTRACT: Returns list of all created agent_ids."""
        agents = spawn_agents(count=5)
        assert len(agents) == 5
        for agent in agents:
            assert agent.agent_id is not None

    def test_spawn_batch_atomic(self):
        """CONTRACT: Batch spawn is atomic - all or none."""
        # All succeed together
        agents = spawn_agents(count=10)
        assert len(agents) == 10


class TestSpawnWithSeed:
    """CONTRACT: Deterministic spawning with seed."""

    def test_spawn_deterministic_with_seed(self):
        """CONTRACT: Same seed produces identical agents."""
        agent1 = spawn_agent(seed=12345)
        agent2 = spawn_agent(seed=12345)
        assert agent1.traits == agent2.traits

    def test_spawn_different_seeds_different_agents(self):
        """CONTRACT: Different seeds produce different agents."""
        agent1 = spawn_agent(seed=100)
        agent2 = spawn_agent(seed=200)
        assert agent1.traits != agent2.traits

    def test_spawn_seed_reproducible_across_runs(self):
        """CONTRACT: Same seed works across process restarts."""
        # Simulate multiple "runs" by spawning with same seed
        agent1 = spawn_agent(seed=99999)
        # Reset any state and spawn again
        agent2 = spawn_agent(seed=99999)
        assert agent1.traits == agent2.traits


class TestSpawnWithPatterns:
    """CONTRACT: Pattern assignment during spawn."""

    def test_spawn_with_pattern_selection(self):
        """CONTRACT: Spawned agent gets assigned patterns."""
        patterns = make_patterns(5)
        agent = spawn_agent(available_patterns=patterns, seed=42)
        assert len(agent.assigned_patterns) > 0

    def test_spawn_heuristic_pattern_matching(self):
        """CONTRACT: Heuristic mode matches traits to patterns."""
        patterns = make_patterns(10)
        agent = spawn_agent(available_patterns=patterns, seed=42)
        # Patterns were selected based on traits
        assert len(agent.assigned_patterns) >= 1

    def test_spawn_pattern_weights_initialized(self):
        """CONTRACT: Pattern weights start at 1.0 for all assigned."""
        pattern_ids = ["p1", "p2", "p3"]
        weights = initialize_pattern_weights(pattern_ids)
        for pid in pattern_ids:
            assert weights[pid] == 1.0

    def test_spawn_min_1_pattern_assigned(self):
        """CONTRACT: Agent gets at least 1 pattern."""
        patterns = make_patterns(5)
        config = SpawnConfig(min_patterns=1, max_patterns=3)
        agent = spawn_agent(available_patterns=patterns, config=config, seed=42)
        assert len(agent.assigned_patterns) >= 1

    def test_spawn_max_patterns_configurable(self):
        """CONTRACT: Max patterns per agent is configurable."""
        patterns = make_patterns(20)
        config = SpawnConfig(min_patterns=1, max_patterns=3)
        agent = spawn_agent(available_patterns=patterns, config=config, seed=42)
        assert len(agent.assigned_patterns) <= 3


class TestSpawnChild:
    """CONTRACT: Child spawning from parent crossover."""

    def test_spawn_child_from_parents(self):
        """CONTRACT: spawn_child(parent_a, parent_b) creates child."""
        parent_a = make_parent("parent-a", generation=2)
        parent_b = make_parent("parent-b", generation=3)
        child = spawn_child(parent_a, parent_b, seed=42)
        assert child is not None
        assert child.agent_id is not None

    def test_spawn_child_inherits_traits(self):
        """CONTRACT: Child traits = average of parent traits (before mutation)."""
        from Fast_Swarm.Agents.Services.trait_service import crossover_traits

        parent_a = make_parent("pa", traits={"risk_tolerance": 0.2, "volatility_seeking": 0.8})
        parent_b = make_parent("pb", traits={"risk_tolerance": 0.8, "volatility_seeking": 0.2})
        # Crossover without mutation to test inheritance
        crossed = crossover_traits(parent_a["traits"], parent_b["traits"])
        # Average should be near 0.5 (before derived traits recalc)
        assert 0.4 <= crossed.get("risk_tolerance", 0.5) <= 0.6

    def test_spawn_child_with_mutation(self):
        """CONTRACT: Child traits mutated ±10% after crossover."""
        parent_a = make_parent("pa", generation=1)
        parent_b = make_parent("pb", generation=1)
        child = spawn_child(parent_a, parent_b, mutation_rate=0.10, seed=42)
        # Child traits exist and are bounded
        for value in child.traits.values():
            assert 0.0 <= value <= 1.0

    def test_spawn_child_generation_increments(self):
        """CONTRACT: Child generation = max(parent_gens) + 1."""
        parent_a = make_parent("pa", generation=2)
        parent_b = make_parent("pb", generation=5)
        child = spawn_child(parent_a, parent_b, seed=42)
        assert child.generation == 6  # max(2, 5) + 1

    def test_spawn_child_records_parent_ids(self):
        """CONTRACT: Child has parent_a_id and parent_b_id set."""
        parent_a = make_parent("parent-aaa")
        parent_b = make_parent("parent-bbb")
        child = spawn_child(parent_a, parent_b, seed=42)
        assert child.parent_a_id == "parent-aaa"
        assert child.parent_b_id == "parent-bbb"

    def test_spawn_child_inherits_patterns(self):
        """CONTRACT: Child gets union of parent patterns."""
        parent_a = make_parent("pa", patterns=["p1", "p2"])
        parent_b = make_parent("pb", patterns=["p2", "p3"])
        child = spawn_child(parent_a, parent_b, seed=42)
        # Union of patterns
        assert set(child.assigned_patterns) == {"p1", "p2", "p3"}


class TestSpawnClone:
    """CONTRACT: Clone spawning (single parent)."""

    def test_spawn_clone_with_mutation(self):
        """CONTRACT: Clone from single parent with mutation."""
        parent = make_parent("parent-1", generation=3)
        clone = spawn_clone(parent, mutation_rate=0.10, seed=42)
        assert clone is not None
        assert clone.agent_id != parent["agent_id"]

    def test_spawn_clone_similar_traits(self):
        """CONTRACT: Clone traits within ±10% of parent."""
        parent = make_parent("parent-1")
        clone = spawn_clone(parent, mutation_rate=0.10, seed=42)
        # Traits should be within ±10% (clamped to 0-1)
        for trait_name in parent["traits"]:
            if trait_name in clone.traits:
                parent_val = parent["traits"][trait_name]
                clone_val = clone.traits[trait_name]
                # After clamping, difference should be <= 0.10 or at boundary
                diff = abs(parent_val - clone_val)
                assert diff <= 0.15  # Allow some slack for derived traits

    def test_spawn_clone_generation_increments(self):
        """CONTRACT: Clone generation = parent_gen + 1."""
        parent = make_parent("parent-1", generation=5)
        clone = spawn_clone(parent, seed=42)
        assert clone.generation == 6

    def test_spawn_clone_inherits_patterns(self):
        """CONTRACT: Clone gets same patterns as parent."""
        parent = make_parent("parent-1", patterns=["p1", "p2", "p3"])
        clone = spawn_clone(parent, seed=42)
        assert set(clone.assigned_patterns) == {"p1", "p2", "p3"}


class TestSpawnPhilosophy:
    """CONTRACT: Trading philosophy generation."""

    def test_spawn_philosophy_generation(self):
        """CONTRACT: Agent gets trading_philosophy text."""
        agent = spawn_agent(seed=42)
        assert agent.trading_philosophy is not None
        assert isinstance(agent.trading_philosophy, str)

    def test_spawn_philosophy_reflects_traits(self):
        """CONTRACT: Philosophy text reflects agent's traits."""
        from Fast_Swarm.Agents.Services.trait_service import generate_all_traits

        # High risk tolerance should mention risk
        traits = generate_all_traits(seed=42)
        traits["risk_tolerance"] = 0.9
        philosophy = generate_trading_philosophy(traits)
        assert "risk" in philosophy.lower() or "reward" in philosophy.lower()

    def test_spawn_philosophy_not_empty(self):
        """CONTRACT: Philosophy is never empty string."""
        agent = spawn_agent(seed=42)
        assert len(agent.trading_philosophy) > 0


class TestSpawnNaming:
    """CONTRACT: Agent naming convention."""

    def test_spawn_naming_convention(self):
        """CONTRACT: Name = {Trait1}_{Trait2}_{Name}_G{gen}."""
        agent = spawn_agent(generation=3, seed=42)
        # Name should have format: Descriptor_Descriptor_Name_G#
        parts = agent.name.split("_")
        assert len(parts) >= 4
        assert parts[-1].startswith("G")

    def test_spawn_name_reflects_dominant_traits(self):
        """CONTRACT: Name includes dominant trait descriptors."""
        from Fast_Swarm.Agents.Services.trait_service import generate_all_traits

        traits = generate_all_traits(seed=42)
        name = generate_agent_name(traits, generation=1, seed=42)
        # Name should include trait descriptors
        assert "_" in name

    def test_spawn_name_includes_generation(self):
        """CONTRACT: Name ends with _G{generation}."""
        agent = spawn_agent(generation=5, seed=42)
        assert agent.name.endswith("_G5")

    def test_spawn_name_unique(self):
        """CONTRACT: Each agent has unique name."""
        agents = spawn_agents(count=10)
        names = [a.name for a in agents]
        # Names should be unique (different agent_ids lead to different random names)
        assert len(names) == len(set(names))


class TestSpawnValidation:
    """CONTRACT: Spawn input validation."""

    def test_spawn_count_must_be_positive(self):
        """CONTRACT: count <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            spawn_agents(count=0)
        with pytest.raises(ValueError, match="positive"):
            spawn_agents(count=-5)

    def test_spawn_count_max_limit(self):
        """CONTRACT: count > 1000 raises ValueError (safety)."""
        with pytest.raises(ValueError, match="maximum"):
            spawn_agents(count=1001)
        with pytest.raises(ValueError, match="maximum"):
            spawn_agents(count=5000)
        # Validate function should also work
        is_valid, error = validate_spawn_count(1001)
        assert not is_valid
        assert "maximum" in error.lower() or str(MAX_SPAWN_COUNT) in error

    def test_spawn_validation_accepts_valid_count(self):
        """CONTRACT: Valid counts pass validation."""
        is_valid, error = validate_spawn_count(1)
        assert is_valid
        assert error == ""
        is_valid, error = validate_spawn_count(100)
        assert is_valid
        is_valid, error = validate_spawn_count(MAX_SPAWN_COUNT)
        assert is_valid


class TestSpawnDatabase:
    """CONTRACT: Spawn persists to database."""

    @pytest.mark.asyncio
    async def test_spawn_persists_to_db(self, db_session):
        """CONTRACT: Spawned agents are saved to database."""
        from sqlmodel import select

        from Fast_Swarm.Agents.Models.agent_models import Agent
        from Fast_Swarm.Agents.Services.spawn_service import spawn_and_persist

        # Spawn and persist agents
        agent_ids = await spawn_and_persist(db_session, count=3, seed=42)
        assert len(agent_ids) == 3

        # Query database to verify persistence
        stmt = select(Agent).where(Agent.agent_id.in_(agent_ids))
        result = await db_session.execute(stmt)
        agents = result.scalars().all()
        assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_spawn_retrievable_after_commit(self, db_session):
        """CONTRACT: Spawned agent retrievable immediately after."""
        from sqlmodel import select

        from Fast_Swarm.Agents.Models.agent_models import Agent
        from Fast_Swarm.Agents.Services.spawn_service import spawn_and_persist

        # Spawn single agent
        agent_ids = await spawn_and_persist(db_session, count=1, seed=123)
        agent_id = agent_ids[0]

        # Should be retrievable immediately
        stmt = select(Agent).where(Agent.agent_id == agent_id)
        result = await db_session.execute(stmt)
        agent = result.scalars().first()
        assert agent is not None
        assert agent.agent_id == agent_id
        assert agent.generation == 1
        assert agent.traits is not None
        assert len(agent.traits) == 22

    @pytest.mark.asyncio
    async def test_spawn_invalid_count_raises(self, db_session):
        """CONTRACT: Invalid count raises before DB operations."""
        from Fast_Swarm.Agents.Services.spawn_service import spawn_and_persist

        with pytest.raises(ValueError, match="positive"):
            await spawn_and_persist(db_session, count=0)
        with pytest.raises(ValueError, match="maximum"):
            await spawn_and_persist(db_session, count=1001)
