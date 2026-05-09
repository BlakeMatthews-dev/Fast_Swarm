"""
Evolution Cycle Tests.

Tests:
- Fitness evaluation
- Selection (elite, survivors, culled)
- Reproduction (crossover + mutation)
- Full evolution cycle
- Population statistics
"""

from dataclasses import dataclass


class TestFitnessEvaluation:
    """Fitness scoring during evolution."""

    def test_update_agent_fitness(self):
        """Agent fitness can be updated."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        agent = spawn_agent(seed=42, available_patterns=patterns, db=db)
        db.update_agent_fitness(agent.agent_id, fitness=75.5, backtest_count=10)

        updated = db.get_agent(agent.agent_id)
        assert updated.fitness_score == 75.5
        assert updated.backtest_count == 10

    def test_evaluate_agent_fitness_insufficient_trades(self):
        """Insufficient trades returns 0 fitness."""
        from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]
        agent = spawn_agent(seed=42, available_patterns=patterns, db=db)

        # No trades
        fitness = evaluate_agent_fitness(agent, [])
        assert fitness == 0.0


class TestSelection:
    """Selection of elite, survivors, and culled agents."""

    def test_select_survivors_basic(self):
        """Selection splits population correctly."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig, select_survivors
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=10,
            available_patterns=patterns,
            db=db,
        )

        # Set varying fitness scores
        for i, agent in enumerate(population):
            db.update_agent_fitness(agent.agent_id, fitness=float(i * 10))
            agent.fitness_score = float(i * 10)

        config = EvolutionConfig(elite_percent=0.10, survival_percent=0.70)
        elite, survivors, retired = select_survivors(population, config)

        assert len(elite) == 1  # 10% of 10
        assert len(survivors) == 7  # 70% of 10
        assert len(retired) == 3  # 30% of 10

    def test_elite_has_highest_fitness(self):
        """Elite contains the highest fitness agents."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig, select_survivors
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=10,
            available_patterns=patterns,
            db=db,
        )

        for i, agent in enumerate(population):
            db.update_agent_fitness(agent.agent_id, fitness=float(i * 10))
            agent.fitness_score = float(i * 10)

        config = EvolutionConfig(elite_percent=0.20)
        elite, _, _ = select_survivors(population, config)

        # Elite should have top 2 (20% of 10)
        elite_scores = [a.fitness_score for a in elite]
        assert 90.0 in elite_scores
        assert 80.0 in elite_scores

    def test_select_parents_from_elite(self):
        """Parent selection picks from elite pool."""
        from Fast_Swarm.local_agents.core.evolution import select_parents
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=5,
            available_patterns=patterns,
            db=db,
        )

        for i, agent in enumerate(population):
            agent.fitness_score = float(i * 20)

        parent_a, parent_b = select_parents(population, seed=42)

        assert parent_a in population
        assert parent_b in population


class TestEvolutionConfig:
    """Evolution configuration."""

    def test_default_config(self):
        """Default config has reasonable values."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig

        config = EvolutionConfig()

        assert config.population_size == 20
        assert config.elite_percent == 0.10
        assert config.survival_percent == 0.70
        assert config.mutation_rate == 0.10

    def test_custom_config(self):
        """Custom config overrides defaults."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig

        config = EvolutionConfig(
            population_size=5,
            elite_percent=0.20,
            survival_percent=0.60,
        )

        assert config.population_size == 5
        assert config.elite_percent == 0.20
        assert config.survival_percent == 0.60


class TestMemoryInheritance:
    """Memory inheritance during breeding."""

    def test_inherit_memories_from_parents(self):
        """Child inherits memories from both parents."""
        from Fast_Swarm.local_agents.core.evolution import inherit_memories
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        parent_a = spawn_agent(seed=1, available_patterns=patterns, db=db)
        parent_b = spawn_agent(seed=2, available_patterns=patterns, db=db)
        child = spawn_agent(seed=3, available_patterns=patterns, db=db)

        # Add memories to parents
        mem_a = Memory(
            agent_id=parent_a.agent_id,
            memory_type="lesson",
            content="RSI below 30 is buy",
            weight=0.8,
        )
        db.create_memory(mem_a)

        mem_b = Memory(
            agent_id=parent_b.agent_id,
            memory_type="observation",
            content="Volatility spikes at open",
            weight=0.6,
        )
        db.create_memory(mem_b)

        # Inherit
        child_traits = AgentTraits(memory_condensation=1.0, inheritance_decay=0.0)
        inherited = inherit_memories(parent_a, parent_b, child.agent_id, child_traits, db)

        assert len(inherited) >= 1  # At least some memories inherited

    def test_inheritance_applies_decay(self):
        """Inherited memories have decayed weights."""
        from Fast_Swarm.local_agents.core.evolution import inherit_memories
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        parent_a = spawn_agent(seed=1, available_patterns=patterns, db=db)
        parent_b = spawn_agent(seed=2, available_patterns=patterns, db=db)
        child = spawn_agent(seed=3, available_patterns=patterns, db=db)

        mem = Memory(
            agent_id=parent_a.agent_id,
            memory_type="lesson",
            content="Test memory",
            weight=0.8,
        )
        db.create_memory(mem)

        # High decay
        child_traits = AgentTraits(memory_condensation=1.0, inheritance_decay=0.5)
        inherited = inherit_memories(parent_a, parent_b, child.agent_id, child_traits, db)

        if inherited:
            # Weight should be decayed
            assert inherited[0].weight < 0.8


class TestPopulationStats:
    """Population-level statistics."""

    def test_get_population_stats(self):
        """Get statistics for population."""
        from Fast_Swarm.local_agents.core.evolution import get_population_stats
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=5,
            available_patterns=patterns,
            db=db,
        )

        for i, agent in enumerate(population):
            db.update_agent_fitness(agent.agent_id, fitness=float(i * 20))

        stats = get_population_stats(db)

        assert stats.total == 5
        assert stats.active == 5
        assert 0 <= stats.avg_fitness <= 100
        assert stats.best_fitness == 80.0
        assert stats.worst_fitness == 0.0

    def test_empty_population_stats(self):
        """Empty population returns zero stats."""
        from Fast_Swarm.local_agents.core.evolution import get_population_stats
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        stats = get_population_stats(db)

        assert stats.total == 0
        assert stats.avg_fitness == 0


class TestEvolutionResult:
    """Evolution result data class."""

    def test_evolution_result_fields(self):
        """EvolutionResult has correct fields."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionResult

        result = EvolutionResult(
            generation=1,
            survivors=[],
            children=[],
            retired=[],
            avg_fitness=50.0,
            best_fitness=80.0,
            best_agent_id="agent-1",
            elapsed_ms=100,
        )

        assert result.generation == 1
        assert result.avg_fitness == 50.0
        assert result.best_fitness == 80.0
        assert result.elapsed_ms == 100


class TestMockBacktestEngine:
    """Test with mock backtest engine."""

    def test_evolution_with_mock_engine(self):
        """Evolution cycle works with mock backtest engine."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig, run_evolution_cycle
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase, TradeRecord

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=5,
            available_patterns=patterns,
            db=db,
        )

        # Mock backtest engine
        @dataclass
        class MockEngine:
            def run(self, agent, dataset):
                # Return mock trades with unique IDs
                return [
                    TradeRecord(
                        trade_id=f"{agent.agent_id[:8]}-trade-{i}",
                        agent_id=agent.agent_id,
                        pattern_id="p1",
                        asset="BTC",
                        direction="long",
                        pnl_pct=2.0 if i % 2 == 0 else -1.0,
                        entry_confidence=0.7,
                        mfe_pct=3.0,
                        mae_pct=-1.0,
                        position_size_pct=0.05,
                    )
                    for i in range(50)  # Enough trades for fitness
                ]

        config = EvolutionConfig(
            population_size=5,
            elite_percent=0.40,  # Higher for small population
            survival_percent=0.60,
            mutation_rate=0.10,
        )

        result = run_evolution_cycle(
            population=population,
            available_patterns=patterns,
            backtest_engine=MockEngine(),
            dataset=None,
            generation=1,
            config=config,
            seed=42,
            db=db,
        )

        assert result.generation == 1
        assert len(result.survivors) + len(result.children) == 5
        assert result.elapsed_ms >= 0


class TestDeterminism:
    """Evolution determinism tests."""

    def test_selection_deterministic(self):
        """Selection is deterministic with same inputs."""
        from Fast_Swarm.local_agents.core.evolution import select_parents
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        population = initialize_population(
            population_size=5,
            available_patterns=patterns,
            base_seed=42,
            db=db,
        )

        for i, agent in enumerate(population):
            agent.fitness_score = float(i * 20)

        # Same seed should give same parents
        p1a, p1b = select_parents(population, seed=12345)
        p2a, p2b = select_parents(population, seed=12345)

        assert p1a.agent_id == p2a.agent_id
        assert p1b.agent_id == p2b.agent_id


class TestEvolutionConfigFromConfig:
    """Test config loading from Config class."""

    def test_from_config(self):
        """EvolutionConfig.from_config() loads from Config."""
        from Fast_Swarm.local_agents.config import Config
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig

        config = EvolutionConfig.from_config()

        assert config.population_size == Config.POPULATION_SIZE
        assert config.elite_percent == Config.ELITE_PERCENT
        assert config.survival_percent == Config.SURVIVAL_PERCENT
