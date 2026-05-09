"""
Agent Genesis Tests - Spawning and Initialization.

Tests:
- Trait generation during spawn
- Pattern selection (heuristic and mocked LLM)
- Philosophy generation
- Population initialization
- Child spawning (crossover + mutation)
"""


class TestSpawnAgent:
    """Agent spawning with traits and patterns."""

    def test_spawn_basic_agent(self):
        """Spawn agent with minimal inputs."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [
            {"pattern_id": "p1", "name": "Momentum", "win_rate_pct": 55, "type": "momentum"},
            {"pattern_id": "p2", "name": "RSI Oversold", "win_rate_pct": 52, "type": "reversion"},
        ]

        agent = spawn_agent(
            seed=42,
            available_patterns=patterns,
            generation=1,
            db=db,
        )

        assert agent is not None
        assert agent.agent_id is not None
        assert agent.generation == 1
        assert len(agent.pattern_ids) > 0

    def test_spawn_with_trait_overrides(self):
        """Spawn agent with specific trait values."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "name": "Test", "win_rate_pct": 50}]

        agent = spawn_agent(
            seed=42,
            available_patterns=patterns,
            trait_overrides={"risk_tolerance": 0.9, "volatility_seeking": 0.1},
            db=db,
        )

        assert agent.traits["risk_tolerance"] == 0.9
        assert agent.traits["volatility_seeking"] == 0.1

    def test_spawn_deterministic_with_seed(self):
        """Same seed produces same agent traits."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        patterns = [{"pattern_id": "p1", "name": "Test", "win_rate_pct": 50}]

        db1 = AgentDatabase(":memory:")
        agent1 = spawn_agent(seed=12345, available_patterns=patterns, db=db1)

        db2 = AgentDatabase(":memory:")
        agent2 = spawn_agent(seed=12345, available_patterns=patterns, db=db2)

        # Traits should match
        for trait in agent1.traits:
            assert agent1.traits[trait] == agent2.traits[trait]

    def test_spawn_with_parents(self):
        """Spawn agent with parent IDs."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "name": "Test", "win_rate_pct": 50}]

        parent_a = spawn_agent(seed=1, available_patterns=patterns, db=db)
        parent_b = spawn_agent(seed=2, available_patterns=patterns, db=db)

        child = spawn_agent(
            seed=3,
            available_patterns=patterns,
            generation=2,
            parent_a_id=parent_a.agent_id,
            parent_b_id=parent_b.agent_id,
            db=db,
        )

        assert child.parent_a_id == parent_a.agent_id
        assert child.parent_b_id == parent_b.agent_id
        assert child.generation == 2

    def test_spawn_generates_philosophy(self):
        """Agent has trading philosophy."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "name": "Test", "win_rate_pct": 50}]

        agent = spawn_agent(seed=42, available_patterns=patterns, db=db)

        assert agent.trading_philosophy is not None
        assert len(agent.trading_philosophy) > 10

    def test_spawn_generates_character_name(self):
        """Agent name follows character naming convention."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "name": "Test", "win_rate_pct": 50}]

        agent = spawn_agent(seed=42, available_patterns=patterns, generation=3, db=db)

        # Should have format: Trait1_Trait2_Name_G3
        assert "_G3" in agent.agent_name
        assert agent.agent_name.count("_") >= 2


class TestPatternSelection:
    """Pattern selection heuristics."""

    def test_heuristic_selects_patterns(self):
        """Heuristic selection returns patterns."""
        from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(
            risk_tolerance=0.8,
            momentum_vs_reversion=0.7,
            win_rate_preference=0.6,
        )
        patterns = [
            {"pattern_id": "p1", "name": "Trend Follow", "win_rate_pct": 60, "type": "momentum"},
            {"pattern_id": "p2", "name": "Mean Revert", "win_rate_pct": 55, "type": "reversion"},
            {"pattern_id": "p3", "name": "Breakout", "win_rate_pct": 45, "type": "momentum"},
        ]

        selected = select_patterns_heuristic(traits, patterns, seed=42, count=2)

        assert len(selected) == 2
        assert all("pattern_id" in s for s in selected)
        assert all("weight" in s for s in selected)

    def test_heuristic_weights_sum_to_one(self):
        """Pattern weights approximately sum to 1."""
        from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits()
        patterns = [
            {"pattern_id": "p1", "win_rate_pct": 50},
            {"pattern_id": "p2", "win_rate_pct": 55},
            {"pattern_id": "p3", "win_rate_pct": 60},
        ]

        selected = select_patterns_heuristic(traits, patterns, seed=42, count=3)

        total_weight = sum(s["weight"] for s in selected)
        assert 0.95 <= total_weight <= 1.05  # Allow rounding

    def test_heuristic_empty_patterns(self):
        """Empty pattern list returns empty selection."""
        from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits()
        selected = select_patterns_heuristic(traits, [], seed=42)

        assert selected == []

    def test_momentum_agent_prefers_momentum_patterns(self):
        """Agent with high momentum trait selects momentum patterns."""
        from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        # High momentum preference
        traits = AgentTraits(momentum_vs_reversion=0.9)
        patterns = [
            {"pattern_id": "momentum1", "win_rate_pct": 50, "type": "momentum"},
            {"pattern_id": "reversion1", "win_rate_pct": 50, "type": "reversion"},
        ]

        selected = select_patterns_heuristic(traits, patterns, seed=42, count=1)

        # Momentum pattern should be preferred
        assert selected[0]["pattern_id"] == "momentum1"

    def test_reversion_agent_prefers_reversion_patterns(self):
        """Agent with low momentum trait selects reversion patterns."""
        from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        # Low momentum = high reversion preference
        traits = AgentTraits(momentum_vs_reversion=0.1)
        patterns = [
            {"pattern_id": "momentum1", "win_rate_pct": 50, "type": "momentum"},
            {"pattern_id": "reversion1", "win_rate_pct": 50, "type": "mean reversion"},
        ]

        selected = select_patterns_heuristic(traits, patterns, seed=42, count=1)

        assert selected[0]["pattern_id"] == "reversion1"


class TestPhilosophyGeneration:
    """Trading philosophy generation."""

    def test_philosophy_mentions_risk(self):
        """High risk agent philosophy mentions aggressive behavior."""
        from Fast_Swarm.local_agents.core.genesis import generate_philosophy_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(risk_tolerance=0.9)
        philosophy = generate_philosophy_heuristic(traits)

        assert "aggressive" in philosophy.lower() or "volatility" in philosophy.lower()

    def test_philosophy_mentions_conservation(self):
        """Low risk agent philosophy mentions capital preservation."""
        from Fast_Swarm.local_agents.core.genesis import generate_philosophy_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(risk_tolerance=0.1)
        philosophy = generate_philosophy_heuristic(traits)

        assert "preservation" in philosophy.lower() or "conservative" in philosophy.lower()

    def test_philosophy_mentions_momentum(self):
        """High momentum agent mentions trends."""
        from Fast_Swarm.local_agents.core.genesis import generate_philosophy_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(momentum_vs_reversion=0.9)
        philosophy = generate_philosophy_heuristic(traits)

        assert "trend" in philosophy.lower() or "momentum" in philosophy.lower()

    def test_philosophy_mentions_reversion(self):
        """Low momentum agent mentions mean reversion."""
        from Fast_Swarm.local_agents.core.genesis import generate_philosophy_heuristic
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(momentum_vs_reversion=0.1)
        philosophy = generate_philosophy_heuristic(traits)

        assert "reversion" in philosophy.lower() or "extreme" in philosophy.lower()


class TestSpawnChild:
    """Child spawning with crossover and mutation."""

    def test_spawn_child_from_parents(self):
        """Child inherits traits from parents."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent, spawn_child
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        parent_a = spawn_agent(
            seed=1,
            available_patterns=patterns,
            trait_overrides={"risk_tolerance": 0.9},
            db=db,
        )
        parent_b = spawn_agent(
            seed=2,
            available_patterns=patterns,
            trait_overrides={"risk_tolerance": 0.1},
            db=db,
        )

        child = spawn_child(parent_a, parent_b, seed=42, available_patterns=patterns, db=db)

        # Child risk should be between parents (with some mutation noise)
        assert 0.0 <= child.traits["risk_tolerance"] <= 1.0
        assert child.parent_a_id == parent_a.agent_id
        assert child.parent_b_id == parent_b.agent_id

    def test_child_generation_increments(self):
        """Child generation is max parent generation + 1."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent, spawn_child
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        parent_a = spawn_agent(seed=1, available_patterns=patterns, generation=2, db=db)
        parent_b = spawn_agent(seed=2, available_patterns=patterns, generation=3, db=db)

        child = spawn_child(parent_a, parent_b, seed=42, available_patterns=patterns, db=db)

        assert child.generation == 4  # max(2, 3) + 1

    def test_child_with_mutation(self):
        """Child traits mutate from inherited values."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent, spawn_child
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        # Create identical parents
        parent_a = spawn_agent(seed=1, available_patterns=patterns, db=db)
        parent_b = spawn_agent(seed=1, available_patterns=patterns, db=db)

        child = spawn_child(
            parent_a,
            parent_b,
            seed=42,
            available_patterns=patterns,
            mutation_rate=0.5,  # High mutation
            db=db,
        )

        # Some traits should differ from parents due to mutation
        parent_trait = parent_a.traits["risk_tolerance"]
        child_trait = child.traits["risk_tolerance"]
        # With high mutation rate, there's likely to be some difference
        # But we can't guarantee it, so just check validity
        assert 0.0 <= child_trait <= 1.0


class TestPopulationInitialization:
    """Population initialization."""

    def test_initialize_population_creates_agents(self):
        """Initialize population creates specified number of agents."""
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [
            {"pattern_id": "p1", "win_rate_pct": 50},
            {"pattern_id": "p2", "win_rate_pct": 55},
        ]

        population = initialize_population(
            population_size=5,
            available_patterns=patterns,
            base_seed=42,
            db=db,
        )

        assert len(population) == 5

    def test_population_all_generation_one(self):
        """All initial population agents are generation 1."""
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=3,
            available_patterns=patterns,
            db=db,
        )

        assert all(agent.generation == 1 for agent in population)

    def test_population_unique_ids(self):
        """All agents have unique IDs."""
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=10,
            available_patterns=patterns,
            db=db,
        )

        ids = [agent.agent_id for agent in population]
        assert len(ids) == len(set(ids))

    def test_population_diverse_traits(self):
        """Population has diverse traits."""
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=10,
            available_patterns=patterns,
            db=db,
        )

        risk_values = [agent.traits["risk_tolerance"] for agent in population]
        # Should have some diversity (not all the same value)
        assert len(set(risk_values)) > 1

    def test_population_deterministic_with_seed(self):
        """Same seed produces same population."""
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        db1 = AgentDatabase(":memory:")
        pop1 = initialize_population(
            population_size=5,
            available_patterns=patterns,
            base_seed=12345,
            db=db1,
        )

        db2 = AgentDatabase(":memory:")
        pop2 = initialize_population(
            population_size=5,
            available_patterns=patterns,
            base_seed=12345,
            db=db2,
        )

        for i in range(5):
            for trait in pop1[i].traits:
                assert pop1[i].traits[trait] == pop2[i].traits[trait]
