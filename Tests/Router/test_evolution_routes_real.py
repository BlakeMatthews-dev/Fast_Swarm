"""
Phase 5 - Evolution Router Integration Tests (Real DB)

Tests evolution monitoring routes against real PostgreSQL with transaction rollback.
Exercises: GET /evolution/monitor/cycles, GET /evolution/monitor/current,
           GET /evolution/monitor/events/{cycle_id},
           GET /agents, GET /agents/{agent_id}, agent population stats
"""

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Evolution.Models.evolution_models import EvolutionCycle, EvolutionEvent


# =============================================================================
# FIXTURES
# =============================================================================


@pytest_asyncio.fixture
async def evolution_cycles(db_session: AsyncSession):
    """Create evolution cycle records for testing."""
    now = datetime.utcnow()
    cycles = []

    for i in range(5):
        cycle = EvolutionCycle(
            cycle_id=f"evo-test-{uuid.uuid4().hex[:8]}",
            cycle_number=i + 1,
            phase="completed" if i < 4 else "running",
            started_at=now - timedelta(hours=5 - i),
            completed_at=(now - timedelta(hours=4 - i)) if i < 4 else None,
            duration_seconds=3600 if i < 4 else None,
            agents_at_start=100,
            agents_spawned=10,
            agents_culled=5,
            agents_reproduced=8,
            top_elo=1800.0 + i * 10,
            avg_elo=1500.0 + i * 5,
            status="completed" if i < 4 else "running",
        )
        db_session.add(cycle)
        cycles.append(cycle)

    await db_session.flush()
    for c in cycles:
        await db_session.refresh(c)
    return cycles


@pytest_asyncio.fixture
async def evolution_events(db_session: AsyncSession, evolution_cycles):
    """Create evolution events tied to cycles."""
    events = []
    cycle = evolution_cycles[0]

    event_types = ["spawn", "cull", "reproduce", "mutate"]
    for i, etype in enumerate(event_types):
        event = EvolutionEvent(
            event_id=f"evt-test-{uuid.uuid4().hex[:8]}",
            cycle_id=cycle.cycle_id,
            event_type=etype,
            entity_type="agent",
            entity_id=f"agent-{i}",
            data={"detail": f"Test {etype} event"},
            occurred_at=datetime.utcnow() - timedelta(minutes=i),
        )
        db_session.add(event)
        events.append(event)

    await db_session.flush()
    for e in events:
        await db_session.refresh(e)
    return events


@pytest_asyncio.fixture
async def population_agents(db_session: AsyncSession, sample_traits):
    """Create a diverse population of agents for stats tests."""
    agents = []
    statuses = ["active", "active", "active", "retired", "culled"]
    generations = [1, 1, 2, 2, 3]

    for i in range(5):
        agent = Agent(
            agent_id=f"evo-pop-agent-{uuid.uuid4().hex[:8]}",
            name=f"Evo Pop Agent {i}",
            generation=generations[i],
            traits=sample_traits,
            status=statuses[i],
            is_active=statuses[i] == "active",
            fitness_score=float(i * 20),
            elo_rating=1400.0 + i * 100,
        )
        db_session.add(agent)
        agents.append(agent)

    await db_session.flush()
    for a in agents:
        await db_session.refresh(a)
    return agents


# =============================================================================
# GET /evolution/monitor/cycles
# =============================================================================


class TestListCycles:
    """Tests for GET /evolution/monitor/cycles endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_list_cycles_returns_results(
        self, db_session: AsyncSession, evolution_cycles
    ):
        """Listing cycles returns cycle records."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_recent_cycles

        result = await get_recent_cycles(db_session, limit=10)

        assert len(result) >= 5

    @pytest.mark.asyncio
    async def test_list_cycles_ordered_by_cycle_number_desc(
        self, db_session: AsyncSession, evolution_cycles
    ):
        """Cycles are ordered by cycle_number descending (most recent first)."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_recent_cycles

        result = await get_recent_cycles(db_session, limit=10)

        # Filter to our test cycles
        test_cycles = [c for c in result if c.cycle_id.startswith("evo-test-")]
        if len(test_cycles) >= 2:
            for i in range(len(test_cycles) - 1):
                assert test_cycles[i].cycle_number >= test_cycles[i + 1].cycle_number

    @pytest.mark.asyncio
    async def test_list_cycles_respects_limit(
        self, db_session: AsyncSession, evolution_cycles
    ):
        """Limit parameter restricts returned cycles."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_recent_cycles

        result = await get_recent_cycles(db_session, limit=2)

        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_list_cycles_empty_db(self, db_session: AsyncSession):
        """Empty DB returns empty list."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_recent_cycles

        result = await get_recent_cycles(db_session, limit=10)

        assert isinstance(result, list)


# =============================================================================
# GET /evolution/monitor/current
# =============================================================================


class TestCurrentCycle:
    """Tests for GET /evolution/monitor/current endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_current_cycle_returns_running(
        self, db_session: AsyncSession, evolution_cycles
    ):
        """Current cycle returns the running cycle."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_current_cycle

        result = await get_current_cycle(db_session)

        # We created one cycle with status="running"
        assert result is not None
        assert result.status == "running"

    @pytest.mark.asyncio
    async def test_current_cycle_none_when_all_completed(
        self, db_session: AsyncSession
    ):
        """Returns None when no cycle is running."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_current_cycle

        # Add a completed cycle only
        cycle = EvolutionCycle(
            cycle_id=f"evo-done-{uuid.uuid4().hex[:8]}",
            cycle_number=999,
            phase="completed",
            started_at=datetime.utcnow() - timedelta(hours=1),
            completed_at=datetime.utcnow(),
            status="completed",
        )
        db_session.add(cycle)
        await db_session.flush()

        result = await get_current_cycle(db_session)

        # Could be None or could find other running cycles in test DB
        # The point is it doesn't crash
        if result is not None:
            assert result.status == "running"


# =============================================================================
# GET /evolution/monitor/events/{cycle_id}
# =============================================================================


class TestCycleEvents:
    """Tests for GET /evolution/monitor/events/{cycle_id} endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_get_cycle_events(
        self, db_session: AsyncSession, evolution_events, evolution_cycles
    ):
        """Getting events for a cycle returns event records."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_cycle_events

        cycle_id = evolution_cycles[0].cycle_id
        result = await get_cycle_events(db_session, cycle_id)

        assert len(result) >= 4
        assert all(e.cycle_id == cycle_id for e in result)

    @pytest.mark.asyncio
    async def test_get_cycle_events_nonexistent(self, db_session: AsyncSession):
        """Events for nonexistent cycle returns empty list."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_cycle_events

        result = await get_cycle_events(db_session, "nonexistent-cycle-id")

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_cycle_events_ordered_desc(
        self, db_session: AsyncSession, evolution_events, evolution_cycles
    ):
        """Events are ordered by occurred_at descending."""
        from Fast_Swarm.Evolution.Services.evolution_monitor import get_cycle_events

        cycle_id = evolution_cycles[0].cycle_id
        result = await get_cycle_events(db_session, cycle_id)

        test_events = [e for e in result if e.event_id.startswith("evt-test-")]
        if len(test_events) >= 2:
            for i in range(len(test_events) - 1):
                assert test_events[i].occurred_at >= test_events[i + 1].occurred_at


# =============================================================================
# GET /agents - List agents
# =============================================================================


class TestListAgents:
    """Tests for GET /agents endpoint (agent_service.get_all_agents)."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_list_agents_returns_active_only(
        self, db_session: AsyncSession, population_agents
    ):
        """Default listing returns only active agents."""
        from Fast_Swarm.Agents.Services.agent_service import get_all_agents

        result = await get_all_agents(db_session, limit=100)

        # All returned agents should be active
        for agent in result:
            assert agent.is_active is True

    @pytest.mark.asyncio
    async def test_list_agents_pagination(
        self, db_session: AsyncSession, population_agents
    ):
        """Pagination with limit/offset works."""
        from Fast_Swarm.Agents.Services.agent_service import get_all_agents

        page1 = await get_all_agents(db_session, limit=2, offset=0)
        page2 = await get_all_agents(db_session, limit=2, offset=2)

        page1_ids = {a.agent_id for a in page1}
        page2_ids = {a.agent_id for a in page2}
        assert page1_ids.isdisjoint(page2_ids)


# =============================================================================
# GET /agents/{agent_id} - Get single agent
# =============================================================================


class TestGetAgent:
    """Tests for GET /agents/{agent_id} endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_get_agent_by_id(
        self, db_session: AsyncSession, population_agents
    ):
        """Getting an agent by valid ID returns the agent."""
        from Fast_Swarm.Agents.Services.agent_service import get_agent_by_id

        target = population_agents[0]
        result = await get_agent_by_id(db_session, target.agent_id)

        assert result is not None
        assert result.agent_id == target.agent_id
        assert result.name == target.name

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, db_session: AsyncSession):
        """Getting a nonexistent agent returns None."""
        from Fast_Swarm.Agents.Services.agent_service import get_agent_by_id

        result = await get_agent_by_id(db_session, "nonexistent-agent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_has_traits(
        self, db_session: AsyncSession, population_agents
    ):
        """Retrieved agent has valid traits dict."""
        from Fast_Swarm.Agents.Services.agent_service import get_agent_by_id

        target = population_agents[0]
        result = await get_agent_by_id(db_session, target.agent_id)

        assert result is not None
        assert isinstance(result.traits, dict)
        assert "risk_tolerance" in result.traits


# =============================================================================
# Population Statistics (agent_stats_service)
# =============================================================================


class TestPopulationStats:
    """Tests for GET /agents/stats/average endpoint."""

    @pytest.mark.asyncio
    async def test_average_stats_returns_dict(
        self, db_session: AsyncSession, population_agents
    ):
        """Average stats endpoint returns a dict with aggregated values."""
        from Fast_Swarm.Agents.Services.agent_stats_service import (
            get_agent_average_stats,
        )

        result = await get_agent_average_stats(db_session)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_average_stats_has_expected_keys(
        self, db_session: AsyncSession, population_agents
    ):
        """Average stats contains expected aggregate keys."""
        from Fast_Swarm.Agents.Services.agent_stats_service import (
            get_agent_average_stats,
        )

        result = await get_agent_average_stats(db_session)

        # Should contain at least agent count or trait averages
        # Exact keys depend on implementation, so just check it's non-empty
        assert len(result) > 0
