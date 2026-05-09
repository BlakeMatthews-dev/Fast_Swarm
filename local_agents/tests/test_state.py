"""
State Persistence Tests - SQLite Storage.

Tests AgentDatabase for:
- Agent CRUD operations
- Memory CRUD operations
- Trade recording
- Population statistics
"""


class TestAgentCRUD:
    """Agent create, read, update, delete operations."""

    def test_create_agent(self):
        """Create agent and verify fields."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")

        traits = AgentTraits(risk_tolerance=0.8, momentum_vs_reversion=0.3)
        record = db.create_agent(
            agent_name="Test_Agent_G1",
            traits=traits,
            pattern_ids=["p1", "p2"],
            generation=1,
            pattern_weights={"p1": 0.6, "p2": 0.4},
            trading_philosophy="Buy low, sell high.",
        )

        assert record.agent_id is not None
        assert record.agent_name == "Test_Agent_G1"
        assert record.generation == 1
        assert record.pattern_ids == ["p1", "p2"]
        assert record.status == "active"

    def test_get_agent(self):
        """Retrieve agent by ID."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")

        traits = AgentTraits()
        created = db.create_agent(
            agent_name="Retrieve_Test",
            traits=traits,
            pattern_ids=["p1"],
        )

        retrieved = db.get_agent(created.agent_id)

        assert retrieved is not None
        assert retrieved.agent_id == created.agent_id
        assert retrieved.agent_name == "Retrieve_Test"

    def test_get_agent_not_found(self):
        """Get non-existent agent returns None."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase(":memory:")
        result = db.get_agent("non-existent-id")

        assert result is None

    def test_update_agent_fitness(self):
        """Update agent fitness score."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")

        traits = AgentTraits()
        agent = db.create_agent(
            agent_name="Fitness_Test",
            traits=traits,
            pattern_ids=["p1"],
        )

        db.update_agent_fitness(agent.agent_id, fitness=75.5, backtest_count=10)

        updated = db.get_agent(agent.agent_id)
        assert updated.fitness_score == 75.5
        assert updated.backtest_count == 10

    def test_update_agent_status(self):
        """Update agent status (active, retired, dead)."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")

        traits = AgentTraits()
        agent = db.create_agent(
            agent_name="Status_Test",
            traits=traits,
            pattern_ids=["p1"],
        )

        db.update_agent_status(agent.agent_id, "retired")

        updated = db.get_agent(agent.agent_id)
        assert updated.status == "retired"

    def test_get_agents_by_status(self):
        """Filter agents by status."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        # Create 3 active, 2 retired
        for i in range(3):
            db.create_agent(f"Active_{i}", traits, ["p1"])

        for i in range(2):
            agent = db.create_agent(f"Retired_{i}", traits, ["p1"])
            db.update_agent_status(agent.agent_id, "retired")

        active = db.get_agents_by_status("active")
        retired = db.get_agents_by_status("retired")

        assert len(active) == 3
        assert len(retired) == 2

    def test_get_all_active_agents(self):
        """Get all active agents."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        db.create_agent("Agent1", traits, ["p1"])
        db.create_agent("Agent2", traits, ["p1"])

        active = db.get_all_active_agents()
        assert len(active) == 2

    def test_traits_preserved(self):
        """Traits are serialized/deserialized correctly."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")

        original_traits = AgentTraits(
            risk_tolerance=0.75,
            momentum_vs_reversion=0.25,
            volatility_seeking=0.9,
        )

        agent = db.create_agent(
            agent_name="Traits_Test",
            traits=original_traits,
            pattern_ids=["p1"],
        )

        retrieved = db.get_agent(agent.agent_id)

        assert retrieved.traits["risk_tolerance"] == 0.75
        assert retrieved.traits["momentum_vs_reversion"] == 0.25
        assert retrieved.traits["volatility_seeking"] == 0.9


class TestMemoryCRUD:
    """Memory create, read, update, delete operations."""

    def test_create_memory(self):
        """Create memory for agent."""
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Memory_Agent", traits, ["p1"])

        memory = Memory(
            agent_id=agent.agent_id,
            memory_type="lesson",
            content="RSI below 30 is a buy signal",
            weight=0.7,
        )

        memory_id = db.create_memory(memory)
        assert memory_id is not None

    def test_get_agent_memories(self):
        """Get all memories for an agent."""
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Memory_Agent", traits, ["p1"])

        # Create 3 memories
        for i in range(3):
            mem = Memory(
                agent_id=agent.agent_id,
                memory_type="observation",
                content=f"Observation {i}",
                weight=0.5,
            )
            db.create_memory(mem)

        memories = db.get_agent_memories(agent.agent_id)
        assert len(memories) == 3

    def test_get_memories_by_type(self):
        """Filter memories by type."""
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Memory_Agent", traits, ["p1"])

        # Create 2 lessons, 1 observation
        for i in range(2):
            mem = Memory(agent_id=agent.agent_id, memory_type="lesson", content=f"Lesson {i}", weight=0.7)
            db.create_memory(mem)

        mem = Memory(agent_id=agent.agent_id, memory_type="observation", content="Obs 1", weight=0.3)
        db.create_memory(mem)

        lessons = db.get_agent_memories(agent.agent_id, memory_type="lesson")
        observations = db.get_agent_memories(agent.agent_id, memory_type="observation")

        assert len(lessons) == 2
        assert len(observations) == 1

    def test_update_memory(self):
        """Update memory weight and content."""
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Memory_Agent", traits, ["p1"])

        mem = Memory(agent_id=agent.agent_id, memory_type="lesson", content="Original", weight=0.5)
        memory_id = db.create_memory(mem)

        db.update_memory(memory_id, weight=0.8, reinforcement_count=3)

        updated = db.get_memory(memory_id)
        assert updated.weight == 0.8
        assert updated.reinforcement_count == 3

    def test_delete_memory(self):
        """Soft delete memory."""
        from Fast_Swarm.local_agents.core.memory import Memory
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Memory_Agent", traits, ["p1"])

        mem = Memory(agent_id=agent.agent_id, memory_type="observation", content="To delete", weight=0.3)
        memory_id = db.create_memory(mem)

        db.delete_memory(memory_id)

        # Should not appear in get_agent_memories
        memories = db.get_agent_memories(agent.agent_id)
        assert len(memories) == 0

        # But get_memory also returns None for deleted
        deleted = db.get_memory(memory_id)
        assert deleted is None


class TestTradeCRUD:
    """Trade recording operations."""

    def test_create_trade(self):
        """Record a trade."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase, TradeRecord
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Trade_Agent", traits, ["p1"])

        trade = TradeRecord(
            trade_id="trade-001",
            agent_id=agent.agent_id,
            pattern_id="p1",
            asset="BTC",
            direction="long",
            entry_price=50000.0,
            exit_price=52000.0,
            pnl_pct=4.0,
            entry_confidence=0.75,
            decision_zone="execute",
        )

        trade_id = db.create_trade(trade)
        assert trade_id == "trade-001"

    def test_get_agent_trades(self):
        """Get trades for an agent."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase, TradeRecord
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Trade_Agent", traits, ["p1"])

        # Create 5 trades
        for i in range(5):
            trade = TradeRecord(
                trade_id=f"trade-{i:03d}",
                agent_id=agent.agent_id,
                pattern_id="p1",
                asset="ETH",
                direction="long",
                pnl_pct=float(i),
            )
            db.create_trade(trade)

        trades = db.get_agent_trades(agent.agent_id)
        assert len(trades) == 5

    def test_get_trades_by_pattern(self):
        """Get trades for a specific pattern."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase, TradeRecord
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        agent = db.create_agent("Trade_Agent", traits, ["p1", "p2"])

        # 3 trades with p1, 2 with p2
        for i in range(3):
            trade = TradeRecord(
                trade_id=f"p1-trade-{i}",
                agent_id=agent.agent_id,
                pattern_id="p1",
                asset="BTC",
                direction="long",
            )
            db.create_trade(trade)

        for i in range(2):
            trade = TradeRecord(
                trade_id=f"p2-trade-{i}",
                agent_id=agent.agent_id,
                pattern_id="p2",
                asset="ETH",
                direction="short",
            )
            db.create_trade(trade)

        p1_trades = db.get_trades_by_pattern("p1")
        p2_trades = db.get_trades_by_pattern("p2")

        assert len(p1_trades) == 3
        assert len(p2_trades) == 2


class TestPopulationStats:
    """Population-level statistics."""

    def test_get_population_stats(self):
        """Get overall population statistics."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        # Create 5 agents, 3 active, 1 retired, 1 dead
        for i in range(3):
            agent = db.create_agent(f"Active_{i}", traits, ["p1"], generation=i + 1)
            db.update_agent_fitness(agent.agent_id, fitness=50.0 + i * 10)

        retired = db.create_agent("Retired", traits, ["p1"])
        db.update_agent_status(retired.agent_id, "retired")

        dead = db.create_agent("Dead", traits, ["p1"])
        db.update_agent_status(dead.agent_id, "dead")

        stats = db.get_population_stats()

        assert stats["total_agents"] == 5
        assert stats["active"] == 3
        assert stats["retired"] == 1
        assert stats["dead"] == 1
        assert stats["max_generation"] == 3

    def test_get_top_agents(self):
        """Get top agents by fitness."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        # Create 10 agents with varying fitness
        for i in range(10):
            agent = db.create_agent(f"Agent_{i}", traits, ["p1"])
            db.update_agent_fitness(agent.agent_id, fitness=float(i * 10))

        top_5 = db.get_top_agents(limit=5)

        assert len(top_5) == 5
        # Should be sorted by fitness descending
        assert top_5[0].fitness_score == 90.0
        assert top_5[4].fitness_score == 50.0

    def test_clear_all(self):
        """Clear all data (for testing)."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        db.create_agent("Agent1", traits, ["p1"])
        db.create_agent("Agent2", traits, ["p1"])

        db.clear_all()

        agents = db.get_all_active_agents()
        assert len(agents) == 0


class TestDatabasePersistence:
    """Database connection and persistence."""

    def test_in_memory_database(self):
        """In-memory database works across operations."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        # Multiple operations on same in-memory db
        agent = db.create_agent("Test", traits, ["p1"])
        db.update_agent_fitness(agent.agent_id, 50.0)
        retrieved = db.get_agent(agent.agent_id)

        assert retrieved.fitness_score == 50.0

    def test_parent_ids_stored(self):
        """Parent IDs are stored correctly."""
        from Fast_Swarm.local_agents.core.state import AgentDatabase
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        db = AgentDatabase(":memory:")
        traits = AgentTraits()

        parent_a = db.create_agent("Parent_A", traits, ["p1"])
        parent_b = db.create_agent("Parent_B", traits, ["p1"])

        child = db.create_agent(
            "Child",
            traits,
            ["p1"],
            parent_a_id=parent_a.agent_id,
            parent_b_id=parent_b.agent_id,
        )

        retrieved = db.get_agent(child.agent_id)
        assert retrieved.parent_a_id == parent_a.agent_id
        assert retrieved.parent_b_id == parent_b.agent_id
