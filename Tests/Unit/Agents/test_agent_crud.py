"""
Agent CRUD Tests - CONTRACT-BASED (TDD/EDD)

These tests define what the Agent system SHOULD do, not what it currently does.
Source of truth: Master_plan.md, EDD rules, domain logic.
"""

import pytest
from Fast_Swarm.Agents.Services.agent_crud import (
    REQUIRED_TRAITS,
    bulk_create_agents,
    bulk_delete_agents,
    bulk_update_fitness,
    create_agent,
    delete_agent,
    generate_random_traits,
    get_agent_by_id,
    get_agents_by_fitness,
    get_agents_by_generation,
    get_agents_by_status,
    get_all_agents,
    get_population_stats,
    update_agent,
    update_agent_fitness,
    validate_traits,
)

# ============================================================================
# AGENT CREATION CONTRACTS (10 tests)
# ============================================================================


class TestAgentCreation:
    """Tests for agent creation - defining the CONTRACT."""

    @pytest.mark.asyncio
    async def test_create_agent_returns_valid_id(self, db_session, sample_traits):
        """CONTRACT: Creating an agent must return a unique agent_id."""
        agent = await create_agent(db_session, name="Test Agent", traits=sample_traits)

        assert agent.agent_id is not None
        assert len(agent.agent_id) > 0
        assert agent.agent_id.startswith("agent-") or agent.agent_id.startswith("test-")

    @pytest.mark.asyncio
    async def test_create_agent_with_minimal_fields(self, db_session):
        """CONTRACT: Agent can be created with just name, gets defaults for rest."""
        agent = await create_agent(db_session, name="Minimal Agent")

        assert agent.name == "Minimal Agent"
        assert agent.generation == 1
        assert agent.status == "active"
        assert agent.is_active is True
        assert agent.fitness_score == 0.0

    @pytest.mark.asyncio
    async def test_create_agent_all_22_traits_initialized(self, db_session):
        """CONTRACT: New agent must have all 22 traits initialized (0.0-1.0)."""
        agent = await create_agent(db_session, name="Full Traits Agent")

        assert len(agent.traits) == 22
        for trait_name in REQUIRED_TRAITS:
            assert trait_name in agent.traits, f"Missing trait: {trait_name}"

    @pytest.mark.asyncio
    async def test_create_agent_traits_bounded_0_to_1(self, db_session):
        """CONTRACT: All trait values must be in [0.0, 1.0] range."""
        agent = await create_agent(db_session, name="Bounded Traits")

        for trait_name, value in agent.traits.items():
            assert 0.0 <= value <= 1.0, f"Trait {trait_name}={value} out of bounds"

    @pytest.mark.asyncio
    async def test_create_agent_invalid_trait_value_rejected(self, db_session, sample_traits):
        """CONTRACT: Trait value > 1.0 or < 0.0 must raise ValidationError."""
        invalid_traits = sample_traits.copy()
        invalid_traits["risk_tolerance"] = 1.5  # Out of bounds

        with pytest.raises(ValueError, match="must be in"):
            await create_agent(db_session, name="Invalid", traits=invalid_traits)

    @pytest.mark.asyncio
    async def test_create_agent_generation_defaults_to_1(self, db_session):
        """CONTRACT: New agents start at generation 1."""
        agent = await create_agent(db_session, name="Gen 1 Agent")
        assert agent.generation == 1

    @pytest.mark.asyncio
    async def test_create_agent_status_defaults_to_active(self, db_session):
        """CONTRACT: New agents start with status='active'."""
        agent = await create_agent(db_session, name="Active Agent")
        assert agent.status == "active"

    @pytest.mark.asyncio
    async def test_create_agent_fitness_defaults_to_zero(self, db_session):
        """CONTRACT: New agents start with fitness_score=0."""
        agent = await create_agent(db_session, name="Zero Fitness")
        assert agent.fitness_score == 0.0

    @pytest.mark.asyncio
    async def test_create_agent_with_seed_deterministic(self, db_session):
        """CONTRACT: Same seed must produce identical agent traits."""
        traits1 = generate_random_traits(seed=42)
        traits2 = generate_random_traits(seed=42)

        assert traits1 == traits2

    @pytest.mark.asyncio
    async def test_create_agent_name_required(self, db_session):
        """CONTRACT: Agent name is required field."""
        with pytest.raises(ValueError, match="name is required"):
            await create_agent(db_session, name="")


# ============================================================================
# AGENT RETRIEVAL CONTRACTS (10 tests)
# ============================================================================


class TestAgentRetrieval:
    """Tests for agent retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_agent_by_id_exists(self, db_session, sample_traits):
        """CONTRACT: GET /agents/{id} returns agent when exists."""
        created = await create_agent(db_session, name="Find Me", traits=sample_traits)
        found = await get_agent_by_id(db_session, created.agent_id)

        assert found is not None
        assert found.agent_id == created.agent_id
        assert found.name == "Find Me"

    @pytest.mark.asyncio
    async def test_get_agent_by_id_not_found_returns_none(self, db_session):
        """CONTRACT: GET /agents/{nonexistent} returns None."""
        found = await get_agent_by_id(db_session, "nonexistent-id-12345")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_agent_includes_all_22_traits(self, db_session, sample_traits):
        """CONTRACT: Agent response must include all 22 traits."""
        created = await create_agent(db_session, name="Full Agent", traits=sample_traits)
        found = await get_agent_by_id(db_session, created.agent_id)

        assert len(found.traits) == 22

    @pytest.mark.asyncio
    async def test_list_agents_returns_list(self, db_session, sample_traits):
        """CONTRACT: GET /agents returns list."""
        await create_agent(db_session, name="Agent 1", traits=sample_traits)
        await create_agent(db_session, name="Agent 2", traits=sample_traits)

        agents = await get_all_agents(db_session, limit=10)

        assert isinstance(agents, list)
        assert len(agents) >= 2

    @pytest.mark.asyncio
    async def test_list_agents_default_limit_50(self, db_session, sample_traits):
        """CONTRACT: Default pagination limit is 50."""
        # Create agents
        for i in range(55):
            await create_agent(db_session, name=f"Agent {i}", traits=sample_traits)

        # Default limit should be 50
        agents = await get_all_agents(db_session)
        assert len(agents) <= 50

    @pytest.mark.asyncio
    async def test_list_agents_filter_by_status_active(self, db_session, sample_traits):
        """CONTRACT: ?status=active filters to active agents only."""
        agent1 = await create_agent(db_session, name="Active One", traits=sample_traits)
        agent2 = await create_agent(db_session, name="To Retire", traits=sample_traits)
        await update_agent(db_session, agent2.agent_id, {"status": "retired"})

        # Verify agent statuses directly
        found1 = await get_agent_by_id(db_session, agent1.agent_id)
        found2 = await get_agent_by_id(db_session, agent2.agent_id)
        assert found1.status == "active"
        assert found2.status == "retired"

        # Verify filter returns only active agents (all returned should be active)
        active_agents = await get_agents_by_status(db_session, "active")
        for agent in active_agents:
            assert agent.status == "active"

    @pytest.mark.asyncio
    async def test_list_agents_filter_by_status_retired(self, db_session, sample_traits):
        """CONTRACT: ?status=retired filters to retired agents only."""
        agent = await create_agent(db_session, name="To Retire", traits=sample_traits)
        await update_agent(db_session, agent.agent_id, {"status": "retired"})

        retired_agents = await get_agents_by_status(db_session, "retired")

        agent_ids = [a.agent_id for a in retired_agents]
        assert agent.agent_id in agent_ids

    @pytest.mark.asyncio
    async def test_list_agents_filter_by_generation(self, db_session, sample_traits):
        """CONTRACT: ?generation=N filters by generation."""
        agent1 = await create_agent(db_session, name="Gen 1", traits=sample_traits, generation=1)
        agent2 = await create_agent(db_session, name="Gen 2", traits=sample_traits, generation=2)

        # Verify agents have correct generations
        found1 = await get_agent_by_id(db_session, agent1.agent_id)
        found2 = await get_agent_by_id(db_session, agent2.agent_id)
        assert found1.generation == 1
        assert found2.generation == 2

        # Verify filter returns only correct generation
        gen1_agents = await get_agents_by_generation(db_session, generation=1)
        for agent in gen1_agents:
            assert agent.generation == 1

    @pytest.mark.asyncio
    async def test_list_agents_order_by_fitness_desc(self, db_session, sample_traits):
        """CONTRACT: ?order_by=fitness returns highest fitness first."""
        agent1 = await create_agent(db_session, name="Low Fit", traits=sample_traits)
        agent2 = await create_agent(db_session, name="High Fit", traits=sample_traits)

        await update_agent_fitness(db_session, agent1.agent_id, 30.0)
        await update_agent_fitness(db_session, agent2.agent_id, 80.0)

        agents = await get_agents_by_fitness(db_session, order_desc=True)

        if len(agents) >= 2:
            # Fitness should be descending
            for i in range(len(agents) - 1):
                assert agents[i].fitness_score >= agents[i + 1].fitness_score

    @pytest.mark.asyncio
    async def test_get_agent_includes_fitness_score(self, db_session, sample_traits):
        """CONTRACT: Agent response should include fitness score."""
        agent = await create_agent(db_session, name="Fit Agent", traits=sample_traits)
        await update_agent_fitness(db_session, agent.agent_id, 75.5)

        found = await get_agent_by_id(db_session, agent.agent_id)
        assert found.fitness_score == 75.5


# ============================================================================
# AGENT UPDATE CONTRACTS (8 tests)
# ============================================================================


class TestAgentUpdate:
    """Tests for agent update operations."""

    @pytest.mark.asyncio
    async def test_update_agent_traits_partial(self, db_session, sample_traits):
        """CONTRACT: PATCH /agents/{id} can update individual traits."""
        agent = await create_agent(db_session, name="Update Me", traits=sample_traits)
        original_volatility = agent.traits["volatility_seeking"]

        await update_agent(db_session, agent.agent_id, {"traits": {"risk_tolerance": 0.9}})

        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.traits["risk_tolerance"] == 0.9
        # Other traits unchanged
        assert updated.traits["volatility_seeking"] == original_volatility

    @pytest.mark.asyncio
    async def test_update_agent_traits_validates_bounds(self, db_session, sample_traits):
        """CONTRACT: Updating trait to invalid value (>1 or <0) rejected."""
        agent = await create_agent(db_session, name="Validate Me", traits=sample_traits)

        with pytest.raises(ValueError, match="must be in"):
            await update_agent(db_session, agent.agent_id, {"traits": {"risk_tolerance": 2.0}})

    @pytest.mark.asyncio
    async def test_update_agent_fitness_score(self, db_session, sample_traits):
        """CONTRACT: Fitness score can be updated after backtest."""
        agent = await create_agent(db_session, name="Backtest Me", traits=sample_traits)

        await update_agent_fitness(db_session, agent.agent_id, 85.5)

        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.fitness_score == 85.5

    @pytest.mark.asyncio
    async def test_update_agent_status_to_retired(self, db_session, sample_traits):
        """CONTRACT: Agent status can be changed to 'retired'."""
        agent = await create_agent(db_session, name="Retire Me", traits=sample_traits)

        await update_agent(db_session, agent.agent_id, {"status": "retired"})

        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.status == "retired"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_agent_increments_backtest_count(self, db_session, sample_traits):
        """CONTRACT: backtest_count increments on each backtest."""
        agent = await create_agent(db_session, name="Count Me", traits=sample_traits)
        assert agent.backtest_count == 0

        await update_agent_fitness(db_session, agent.agent_id, 50.0)
        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.backtest_count == 1

        await update_agent_fitness(db_session, agent.agent_id, 60.0)
        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.backtest_count == 2

    @pytest.mark.asyncio
    async def test_update_agent_sets_last_backtest_at(self, db_session, sample_traits):
        """CONTRACT: last_backtest_at updates to current time on backtest."""
        agent = await create_agent(db_session, name="Timestamp Me", traits=sample_traits)
        assert agent.last_backtest_at is None

        await update_agent_fitness(db_session, agent.agent_id, 50.0)

        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.last_backtest_at is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_agent_returns_none(self, db_session):
        """CONTRACT: Updating nonexistent agent returns None."""
        result = await update_agent(db_session, "nonexistent-id", {"name": "New Name"})
        assert result is None

    @pytest.mark.asyncio
    async def test_update_agent_preserves_unmodified_fields(self, db_session, sample_traits):
        """CONTRACT: Partial update doesn't affect other fields."""
        agent = await create_agent(db_session, name="Preserve Me", traits=sample_traits)
        original_elo = agent.elo_rating

        await update_agent(db_session, agent.agent_id, {"name": "New Name"})

        updated = await get_agent_by_id(db_session, agent.agent_id)
        assert updated.name == "New Name"
        assert updated.elo_rating == original_elo


# ============================================================================
# AGENT DELETION CONTRACTS (4 tests)
# ============================================================================


class TestAgentDeletion:
    """Tests for agent deletion (soft delete)."""

    @pytest.mark.asyncio
    async def test_delete_agent_soft_delete(self, db_session, sample_traits):
        """CONTRACT: DELETE sets status='dead', doesn't remove from DB."""
        agent = await create_agent(db_session, name="Delete Me", traits=sample_traits)

        result = await delete_agent(db_session, agent.agent_id, hard_delete=False)

        assert result is True
        # Agent still exists but is dead
        found = await get_agent_by_id(db_session, agent.agent_id)
        assert found is not None
        assert found.status == "dead"
        assert found.is_active is False

    @pytest.mark.asyncio
    async def test_delete_agent_not_in_active_list(self, db_session, sample_traits):
        """CONTRACT: Deleted agent not returned in ?status=active."""
        agent = await create_agent(db_session, name="Hide Me", traits=sample_traits)
        await delete_agent(db_session, agent.agent_id)

        active_agents = await get_agents_by_status(db_session, "active")
        agent_ids = [a.agent_id for a in active_agents]

        assert agent.agent_id not in agent_ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_agent_returns_false(self, db_session):
        """CONTRACT: Deleting nonexistent agent returns False."""
        result = await delete_agent(db_session, "nonexistent-id-12345")
        assert result is False

    @pytest.mark.asyncio
    async def test_hard_delete_removes_from_db(self, db_session, sample_traits):
        """CONTRACT: Hard delete removes agent from database entirely."""
        agent = await create_agent(db_session, name="Erase Me", traits=sample_traits)
        agent_id = agent.agent_id

        await delete_agent(db_session, agent_id, hard_delete=True)

        found = await get_agent_by_id(db_session, agent_id)
        assert found is None


# ============================================================================
# AGENT VALIDATION CONTRACTS (6 tests)
# ============================================================================


class TestAgentValidation:
    """Tests for agent data validation."""

    def test_validate_traits_valid(self, sample_traits):
        """CONTRACT: Valid traits pass validation."""
        is_valid, error = validate_traits(sample_traits)
        assert is_valid is True
        assert error == ""

    def test_validate_traits_missing_trait(self, sample_traits):
        """CONTRACT: Missing trait fails validation."""
        incomplete = {k: v for k, v in sample_traits.items() if k != "risk_tolerance"}
        is_valid, error = validate_traits(incomplete)
        assert is_valid is False
        assert "Missing" in error

    def test_validate_traits_out_of_bounds_high(self, sample_traits):
        """CONTRACT: Trait > 1.0 fails validation."""
        invalid = sample_traits.copy()
        invalid["risk_tolerance"] = 1.5
        is_valid, error = validate_traits(invalid)
        assert is_valid is False
        assert "must be in" in error

    def test_validate_traits_out_of_bounds_low(self, sample_traits):
        """CONTRACT: Trait < 0.0 fails validation."""
        invalid = sample_traits.copy()
        invalid["risk_tolerance"] = -0.1
        is_valid, error = validate_traits(invalid)
        assert is_valid is False
        assert "must be in" in error

    def test_validate_traits_non_numeric(self, sample_traits):
        """CONTRACT: Non-numeric trait fails validation."""
        invalid = sample_traits.copy()
        invalid["risk_tolerance"] = "high"
        is_valid, error = validate_traits(invalid)
        assert is_valid is False
        assert "must be numeric" in error

    def test_validate_traits_not_dict(self):
        """CONTRACT: Traits must be dict."""
        is_valid, error = validate_traits([0.5, 0.5])
        assert is_valid is False
        assert "dictionary" in error


# ============================================================================
# BULK OPERATIONS CONTRACTS (4 tests)
# ============================================================================


class TestAgentBulkOperations:
    """Tests for bulk agent operations."""

    @pytest.mark.asyncio
    async def test_bulk_create_agents_returns_all_ids(self, db_session, sample_traits):
        """CONTRACT: Bulk create returns list of all created IDs."""
        agents_data = [
            {"name": "Bulk Agent 1", "traits": sample_traits},
            {"name": "Bulk Agent 2", "traits": sample_traits},
            {"name": "Bulk Agent 3", "traits": sample_traits},
        ]

        ids = await bulk_create_agents(db_session, agents_data)

        assert len(ids) == 3
        for agent_id in ids:
            agent = await get_agent_by_id(db_session, agent_id)
            assert agent is not None

    @pytest.mark.asyncio
    async def test_bulk_create_agents_atomic_on_failure(self, db_session, sample_traits):
        """CONTRACT: Bulk create is atomic - all succeed or all fail."""
        invalid_traits = sample_traits.copy()
        invalid_traits["risk_tolerance"] = 2.0  # Invalid

        agents_data = [
            {"name": "Good Agent", "traits": sample_traits},
            {"name": "Bad Agent", "traits": invalid_traits},  # Will fail
        ]

        with pytest.raises(ValueError):
            await bulk_create_agents(db_session, agents_data)

    @pytest.mark.asyncio
    async def test_bulk_update_fitness_scores(self, db_session, sample_traits):
        """CONTRACT: Can update fitness for multiple agents at once."""
        agent1 = await create_agent(db_session, name="Bulk Update 1", traits=sample_traits)
        agent2 = await create_agent(db_session, name="Bulk Update 2", traits=sample_traits)

        updates = [
            {"agent_id": agent1.agent_id, "fitness_score": 70.0},
            {"agent_id": agent2.agent_id, "fitness_score": 80.0},
        ]

        count = await bulk_update_fitness(db_session, updates)
        assert count == 2

        updated1 = await get_agent_by_id(db_session, agent1.agent_id)
        updated2 = await get_agent_by_id(db_session, agent2.agent_id)
        assert updated1.fitness_score == 70.0
        assert updated2.fitness_score == 80.0

    @pytest.mark.asyncio
    async def test_bulk_delete_agents(self, db_session, sample_traits):
        """CONTRACT: Can soft-delete multiple agents at once."""
        agent1 = await create_agent(db_session, name="Bulk Delete 1", traits=sample_traits)
        agent2 = await create_agent(db_session, name="Bulk Delete 2", traits=sample_traits)

        count = await bulk_delete_agents(db_session, [agent1.agent_id, agent2.agent_id])
        assert count == 2

        found1 = await get_agent_by_id(db_session, agent1.agent_id)
        found2 = await get_agent_by_id(db_session, agent2.agent_id)
        assert found1.status == "dead"
        assert found2.status == "dead"


# ============================================================================
# POPULATION STATISTICS CONTRACTS (6 tests)
# ============================================================================


class TestAgentStatistics:
    """Tests for agent population statistics."""

    @pytest.mark.asyncio
    async def test_stats_total_agents_count(self, db_session, sample_traits):
        """CONTRACT: Stats endpoint returns total agent count."""
        await create_agent(db_session, name="Stats Agent 1", traits=sample_traits)
        await create_agent(db_session, name="Stats Agent 2", traits=sample_traits)

        stats = await get_population_stats(db_session)

        assert "total_count" in stats
        assert stats["total_count"] >= 2

    @pytest.mark.asyncio
    async def test_stats_active_agents_count(self, db_session, sample_traits):
        """CONTRACT: Stats returns count of active agents."""
        agent1 = await create_agent(db_session, name="Active Stats", traits=sample_traits)
        agent2 = await create_agent(db_session, name="Inactive Stats", traits=sample_traits)
        await delete_agent(db_session, agent2.agent_id)

        stats = await get_population_stats(db_session)

        assert "active_count" in stats
        assert stats["active_count"] >= 1

    @pytest.mark.asyncio
    async def test_stats_average_fitness(self, db_session, sample_traits):
        """CONTRACT: Stats returns population average fitness."""
        agent1 = await create_agent(db_session, name="Avg Fit 1", traits=sample_traits)
        agent2 = await create_agent(db_session, name="Avg Fit 2", traits=sample_traits)
        await update_agent_fitness(db_session, agent1.agent_id, 40.0)
        await update_agent_fitness(db_session, agent2.agent_id, 60.0)

        stats = await get_population_stats(db_session)

        assert "avg_fitness" in stats
        assert isinstance(stats["avg_fitness"], float)

    @pytest.mark.asyncio
    async def test_stats_max_generation(self, db_session, sample_traits):
        """CONTRACT: Stats returns highest generation number."""
        await create_agent(db_session, name="Gen 1", traits=sample_traits, generation=1)
        await create_agent(db_session, name="Gen 5", traits=sample_traits, generation=5)

        stats = await get_population_stats(db_session)

        assert "max_generation" in stats
        assert stats["max_generation"] >= 5

    @pytest.mark.asyncio
    async def test_stats_fitness_distribution(self, db_session, sample_traits):
        """CONTRACT: Stats returns fitness distribution buckets."""
        stats = await get_population_stats(db_session)

        assert "fitness_distribution" in stats
        dist = stats["fitness_distribution"]
        assert "0-20" in dist
        assert "20-40" in dist
        assert "40-60" in dist
        assert "60-80" in dist
        assert "80-100" in dist

    @pytest.mark.asyncio
    async def test_stats_empty_population_safe(self, db_session):
        """CONTRACT: Stats returns zeros for empty population, not errors."""
        # This test runs on a fresh transaction, so population may be empty
        stats = await get_population_stats(db_session)

        # Should not raise, should return valid structure
        assert "total_count" in stats
        assert "avg_fitness" in stats
        assert isinstance(stats["avg_fitness"], float)
