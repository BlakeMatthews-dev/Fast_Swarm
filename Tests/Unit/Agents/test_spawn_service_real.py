"""
Real-DB integration tests for AgentSpawnService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests spawn_agent, spawn_child, spawn_clone and DB persistence.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.spawn_service import (
    AgentSpawnService,
    SpawnConfig,
    generate_agent_id,
    generate_agent_name,
    generate_trading_philosophy,
    spawn_agent,
    spawn_and_persist,
    spawn_child,
    spawn_clone,
    validate_spawn_count,
    validate_spawned_agent,
)
from Fast_Swarm.Agents.Services.trait_service import ALL_22_TRAITS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_traits() -> dict[str, float]:
    return {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


SAMPLE_PATTERNS = [
    {
        "pattern_id": "pat-test-001",
        "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 35}],
        "exit_conditions": [{"indicator": "rsi", "min": 65, "max": 80}],
        "type": "technical",
        "fitness_score": 70.0,
        "win_rate": 0.6,
        "volatility": 0.5,
    },
    {
        "pattern_id": "pat-test-002",
        "entry_conditions": [{"indicator": "macd", "min": 0, "max": 100}],
        "exit_conditions": [{"indicator": "macd", "min": -50, "max": 0}],
        "type": "momentum",
        "fitness_score": 65.0,
        "win_rate": 0.55,
        "volatility": 0.6,
    },
]


def _make_parent(
    agent_id: str | None = None,
    fitness: float = 70.0,
    generation: int = 2,
    level: int = 3,
) -> Agent:
    return Agent(
        agent_id=agent_id or f"parent-{uuid.uuid4().hex[:8]}",
        name="Parent Agent",
        generation=generation,
        level=level,
        traits=_default_traits(),
        assigned_patterns={"base": SAMPLE_PATTERNS},
        status="active",
        is_active=True,
        fitness_score=Decimal(str(fitness)),
        elo_rating=Decimal("1500"),
    )


# ---------------------------------------------------------------------------
# Pure Function Tests (no DB needed, but included for completeness)
# ---------------------------------------------------------------------------


class TestSpawnPureFunctions:
    """Tests for non-DB spawn functions."""

    def test_spawn_agent_has_22_traits(self):
        """A freshly spawned agent must have exactly 22 traits."""
        agent = spawn_agent(generation=1, seed=42)
        assert len(agent.traits) == 22
        for trait in ALL_22_TRAITS:
            assert trait in agent.traits
            assert 0.0 <= agent.traits[trait] <= 1.0

    def test_spawn_agent_has_unique_id(self):
        """Each spawn should generate a unique agent_id."""
        ids = {spawn_agent(generation=1).agent_id for _ in range(20)}
        assert len(ids) == 20

    def test_spawn_agent_with_patterns(self):
        """When patterns are provided, agents should receive assignments."""
        agent = spawn_agent(generation=1, seed=42, available_patterns=SAMPLE_PATTERNS)
        assert len(agent.assigned_patterns) > 0

    def test_spawn_child_inherits_from_both_parents(self):
        """Child should have generation = max(parents) + 1 and both parent IDs."""
        parent_a = {"agent_id": "pa", "traits": _default_traits(), "generation": 2, "assigned_patterns": []}
        parent_b = {"agent_id": "pb", "traits": _default_traits(), "generation": 3, "assigned_patterns": []}

        child = spawn_child(parent_a, parent_b, mutation_rate=0.1, seed=42)
        assert child.generation == 4  # max(2,3) + 1
        assert child.parent_a_id == "pa"
        assert child.parent_b_id == "pb"
        assert len(child.traits) == 22

    def test_spawn_clone_has_mutated_traits(self):
        """Clone traits should differ from parent due to mutation."""
        parent = {"agent_id": "p1", "traits": _default_traits(), "generation": 5, "assigned_patterns": []}
        clone = spawn_clone(parent, mutation_rate=0.5, seed=42)

        assert clone.generation == 6
        assert clone.parent_a_id == "p1"
        assert clone.parent_b_id is None

        # At least some traits should differ with high mutation rate
        diffs = sum(1 for t in ALL_22_TRAITS if clone.traits[t] != parent["traits"][t])
        assert diffs > 0

    def test_validate_spawn_count_bounds(self):
        """Spawn count must be positive and <= MAX_SPAWN_COUNT."""
        ok, _ = validate_spawn_count(10)
        assert ok is True

        ok, msg = validate_spawn_count(0)
        assert ok is False

        ok, msg = validate_spawn_count(-1)
        assert ok is False

        ok, msg = validate_spawn_count(1001)
        assert ok is False

    def test_validate_spawned_agent_checks_traits(self):
        """Validation should catch invalid trait values."""
        agent = spawn_agent(generation=1, seed=42)
        ok, _ = validate_spawned_agent(agent)
        assert ok is True

    def test_generate_agent_name_format(self):
        """Name should follow {Trait}_{Trait}_{Name}_G{gen} format."""
        traits = _default_traits()
        traits["risk_tolerance"] = 0.9  # High
        traits["momentum_vs_reversion"] = 0.1  # Low
        name = generate_agent_name(traits, generation=3, seed=42)
        assert "_G3" in name

    def test_generate_trading_philosophy_varies(self):
        """Different traits should produce different philosophies."""
        traits_aggressive = _default_traits()
        traits_aggressive["risk_tolerance"] = 0.9
        traits_aggressive["momentum_vs_reversion"] = 0.9

        traits_conservative = _default_traits()
        traits_conservative["risk_tolerance"] = 0.1
        traits_conservative["momentum_vs_reversion"] = 0.1

        phil_a = generate_trading_philosophy(traits_aggressive)
        phil_c = generate_trading_philosophy(traits_conservative)
        assert phil_a != phil_c


# ---------------------------------------------------------------------------
# Database Persistence Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestSpawnServiceDB:
    """Tests for spawn operations that persist to PostgreSQL."""

    async def test_spawn_and_persist_creates_agents(self, db_session: AsyncSession):
        """spawn_and_persist should insert agents into the agents table."""
        ids = await spawn_and_persist(db_session, count=5, generation=1)
        assert len(ids) == 5

        for aid in ids:
            result = await db_session.execute(select(Agent).where(Agent.agent_id == aid))
            agent = result.scalars().first()
            assert agent is not None
            assert agent.status == "active"
            assert agent.is_active is True
            assert len(agent.traits) == 22
            assert float(agent.fitness_score) == 0.0
            assert float(agent.elo_rating) == 1500.0

    async def test_spawn_and_persist_with_patterns(self, db_session: AsyncSession):
        """Spawned agents should have patterns stored in assigned_patterns."""
        ids = await spawn_and_persist(
            db_session, count=2, generation=1, available_patterns=SAMPLE_PATTERNS
        )

        for aid in ids:
            result = await db_session.execute(select(Agent).where(Agent.agent_id == aid))
            agent = result.scalars().first()
            # assigned_patterns should be {"base": [...]}
            assert "base" in agent.assigned_patterns
            assert len(agent.assigned_patterns["base"]) > 0

    async def test_spawn_child_and_persist_creates_child(self, db_session: AsyncSession):
        """spawn_child should create a child agent linked to both parents."""
        parent_a = _make_parent()
        parent_b = _make_parent()
        db_session.add_all([parent_a, parent_b])
        await db_session.flush()

        svc = AgentSpawnService()
        child_id = await svc.spawn_child(
            session=db_session,
            parent_a_id=parent_a.agent_id,
            parent_b_id=parent_b.agent_id,
        )

        result = await db_session.execute(select(Agent).where(Agent.agent_id == child_id))
        child = result.scalars().first()
        assert child is not None
        assert child.parent_a_id == parent_a.agent_id
        assert child.parent_b_id == parent_b.agent_id
        assert child.generation == parent_a.generation + 1

    async def test_spawn_clone_creates_single_parent_child(self, db_session: AsyncSession):
        """spawn_clone should create an agent with only parent_a_id set."""
        parent = _make_parent(level=5)
        db_session.add(parent)
        await db_session.flush()

        svc = AgentSpawnService()
        clone_id = await svc.spawn_clone(
            session=db_session,
            parent_id=parent.agent_id,
            mutation_rate=0.1,
        )

        result = await db_session.execute(select(Agent).where(Agent.agent_id == clone_id))
        clone = result.scalars().first()
        assert clone is not None
        assert clone.parent_a_id == parent.agent_id
        assert clone.parent_b_id is None
        assert clone.generation == parent.generation + 1

        # Parent should have leveled up
        await db_session.refresh(parent)
        assert parent.level == 6

    async def test_spawn_children_single_parent_clones(self, db_session: AsyncSession):
        """spawn_children with 1 parent should clone."""
        parent = _make_parent()
        db_session.add(parent)
        await db_session.flush()

        svc = AgentSpawnService()
        ids = await svc.spawn_children(
            session=db_session,
            parent_ids=[parent.agent_id],
            mutation_rate=0.1,
        )
        assert len(ids) == 1

    async def test_spawn_children_two_parents_crossover(self, db_session: AsyncSession):
        """spawn_children with 2 parents should crossover."""
        pa = _make_parent()
        pb = _make_parent()
        db_session.add_all([pa, pb])
        await db_session.flush()

        svc = AgentSpawnService()
        ids = await svc.spawn_children(
            session=db_session,
            parent_ids=[pa.agent_id, pb.agent_id],
            mutation_rate=0.1,
        )
        assert len(ids) == 1

        result = await db_session.execute(select(Agent).where(Agent.agent_id == ids[0]))
        child = result.scalars().first()
        assert child.parent_a_id == pa.agent_id
        assert child.parent_b_id == pb.agent_id

    async def test_spawn_child_missing_parent_raises(self, db_session: AsyncSession):
        """Spawning with a non-existent parent should raise ValueError."""
        parent = _make_parent()
        db_session.add(parent)
        await db_session.flush()

        svc = AgentSpawnService()
        with pytest.raises(ValueError, match="Both parents must exist"):
            await svc.spawn_child(
                session=db_session,
                parent_a_id=parent.agent_id,
                parent_b_id="nonexistent-parent-id",
            )

    async def test_spawn_new_agents_alias(self, db_session: AsyncSession):
        """spawn_new_agents is an alias for spawn_agents."""
        svc = AgentSpawnService()
        ids = await svc.spawn_new_agents(session=db_session, count=3, generation=2)
        assert len(ids) == 3

        for aid in ids:
            result = await db_session.execute(select(Agent).where(Agent.agent_id == aid))
            agent = result.scalars().first()
            assert agent.generation == 2
