"""
Real-DB integration tests for CrucibleEntryService and CrucibleTestService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests crucible entry eligibility, snapshot creation, and test lifecycle.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.System.Models.crucible_models import CrucibleEntry
from Fast_Swarm.System.Services.crucible_entry_service import CrucibleEntryService
from Fast_Swarm.System.Services.crucible_test_service import CrucibleTestService


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


def _make_agent(
    agent_id: str | None = None,
    generation: int = 1,
    level: int = 1,
    fitness: float = 50.0,
) -> Agent:
    return Agent(
        agent_id=agent_id or f"test-{uuid.uuid4().hex[:8]}",
        name=f"CrucibleAgent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        level=level,
        traits=_default_traits(),
        assigned_patterns={"base": [{"pattern_id": "p1"}, {"pattern_id": "p2"}]},
        pattern_weights={"p1": 1.0, "p2": 0.8},
        status="active",
        is_active=True,
        fitness_score=Decimal(str(fitness)),
        elo_rating=Decimal("1500"),
    )


# ---------------------------------------------------------------------------
# Entry Eligibility Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCrucibleEntryEligibility:
    """Tests for Crucible entry eligibility logic."""

    async def test_gen3_agent_eligible_for_first_entry(self, db_session: AsyncSession):
        """Generation >= 3 qualifies for first Crucible entry."""
        agent = _make_agent(generation=3, level=1)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        assert entry is not None
        assert entry.agent_id == agent.agent_id
        assert entry.level_at_entry == 1
        assert entry.status == "pending"

    async def test_high_level_agent_eligible_for_first_entry(self, db_session: AsyncSession):
        """Level >= dynamic threshold qualifies (threshold starts at 5)."""
        agent = _make_agent(generation=1, level=5)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        assert entry is not None
        assert entry.level_at_entry == 5

    async def test_low_gen_low_level_not_eligible(self, db_session: AsyncSession):
        """Gen 1, level 2 should NOT be eligible."""
        agent = _make_agent(generation=1, level=2)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry is None

    async def test_subsequent_entry_requires_5_levels(self, db_session: AsyncSession):
        """After first entry, next requires level >= last_entry_level + 5."""
        agent = _make_agent(generation=3, level=10)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()

        # First entry at level 10
        entry1 = await svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry1 is not None

        # Same level - should NOT get a second entry
        entry2 = await svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry2 is None

        # Level up to 14 - still not enough
        agent.level = 14
        db_session.add(agent)
        await db_session.commit()

        entry3 = await svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry3 is None

        # Level 15 - should qualify (10 + 5)
        agent.level = 15
        db_session.add(agent)
        await db_session.commit()

        entry4 = await svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry4 is not None
        assert entry4.level_at_entry == 15

    async def test_nonexistent_agent_returns_none(self, db_session: AsyncSession):
        """Checking a non-existent agent_id should return None."""
        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, "fake-agent-id")
        assert entry is None


# ---------------------------------------------------------------------------
# Snapshot Integrity Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCrucibleSnapshot:
    """Tests for frozen snapshot data in CrucibleEntry."""

    async def test_entry_snapshot_freezes_traits(self, db_session: AsyncSession):
        """Entry should contain a frozen copy of the agent's traits."""
        agent = _make_agent(generation=4, level=3)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        assert entry is not None
        assert entry.traits == agent.traits
        assert entry.assigned_patterns == agent.assigned_patterns

    async def test_entry_snapshot_has_correct_balance(self, db_session: AsyncSession):
        """Entry should start with $50k balance."""
        agent = _make_agent(generation=5)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        assert entry is not None
        assert float(entry.starting_balance) == 50000.0
        assert float(entry.current_balance) == 50000.0

    async def test_entry_has_unique_snapshot_id(self, db_session: AsyncSession):
        """Each entry should have a unique snapshot_id (UUID)."""
        agent = _make_agent(generation=3, level=5)
        db_session.add(agent)
        await db_session.flush()

        svc = CrucibleEntryService()
        entry1 = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        agent.level = 10
        db_session.add(agent)
        await db_session.commit()
        entry2 = await svc.check_and_enter_crucible(db_session, agent.agent_id)

        assert entry1 is not None
        assert entry2 is not None
        assert entry1.snapshot_id != entry2.snapshot_id


# ---------------------------------------------------------------------------
# Batch Check Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCrucibleBatchCheck:
    """Tests for check_agents_batch."""

    async def test_batch_check_mixed_eligibility(self, db_session: AsyncSession):
        """Batch check should return entries only for eligible agents."""
        eligible = _make_agent(generation=5, level=10)
        not_eligible = _make_agent(generation=1, level=1)
        db_session.add_all([eligible, not_eligible])
        await db_session.flush()

        svc = CrucibleEntryService()
        entries = await svc.check_agents_batch(
            db_session,
            [eligible.agent_id, not_eligible.agent_id],
        )

        assert len(entries) == 1
        assert entries[0].agent_id == eligible.agent_id

    async def test_batch_check_empty_list(self, db_session: AsyncSession):
        """Empty agent list should return empty entries."""
        svc = CrucibleEntryService()
        entries = await svc.check_agents_batch(db_session, [])
        assert entries == []

    async def test_get_pending_entries(self, db_session: AsyncSession):
        """get_pending_entries should return all pending crucible entries."""
        # Create two eligible agents
        a1 = _make_agent(generation=4)
        a2 = _make_agent(generation=5)
        db_session.add_all([a1, a2])
        await db_session.flush()

        svc = CrucibleEntryService()
        await svc.check_and_enter_crucible(db_session, a1.agent_id)
        await svc.check_and_enter_crucible(db_session, a2.agent_id)

        pending = await svc.get_pending_entries(db_session)
        assert len(pending) == 2
        assert all(e.status == "pending" for e in pending)


# ---------------------------------------------------------------------------
# CrucibleTestService Metrics Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCrucibleTestMetrics:
    """Tests for CrucibleTestService metric calculation (no external deps)."""

    async def test_empty_trades_returns_zero_fitness(self, db_session: AsyncSession):
        """No trades should produce zero fitness across all regimes."""
        svc = CrucibleTestService()
        metrics = svc._calculate_crucible_metrics([])

        assert metrics["overall_fitness"] == 0.0
        assert metrics["total_pnl_pct"] == 0.0
        assert metrics["regime_scores"]["bull"] == 0.0
        assert metrics["regime_scores"]["bear"] == 0.0
        assert metrics["regime_scores"]["chop"] == 0.0
        assert metrics["regime_scores"]["lowvol"] == 0.0

    async def test_crucible_test_entry_not_found_raises(self, db_session: AsyncSession):
        """run_crucible_test with invalid entry_id should raise ValueError."""
        svc = CrucibleTestService()
        with pytest.raises(ValueError, match="not found"):
            await svc.run_crucible_test(db_session, entry_id=999999)

    async def test_crucible_test_already_completed_skips(self, db_session: AsyncSession):
        """A completed entry should not be re-tested."""
        agent = _make_agent(generation=4)
        db_session.add(agent)
        await db_session.flush()

        entry_svc = CrucibleEntryService()
        entry = await entry_svc.check_and_enter_crucible(db_session, agent.agent_id)
        assert entry is not None

        # Manually mark as completed
        entry.status = "completed"
        db_session.add(entry)
        await db_session.commit()

        test_svc = CrucibleTestService()
        result = await test_svc.run_crucible_test(db_session, entry.id)
        assert result["status"] == "completed"
        assert "already started" in result.get("message", "").lower()
