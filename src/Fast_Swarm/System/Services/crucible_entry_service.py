"""
Crucible Entry Service - Handle agent entry into the Crucible.

Entry eligibility (first entry) - EITHER condition qualifies:
- Generation >= 3 (evolved agents have battle-tested traits), OR
- Level >= dynamic threshold (starts at 5, scales up as crucible fills)

Dynamic threshold scaling (for level-based entry):
- Starts at level 5 to seed the system quickly
- Scales up as more entries accumulate (10 entries -> level 10, 50 -> level 15)
- Every 50 additional entries, threshold increases by 5 (max 30)

Subsequent entries: Every 5 levels after first entry (all generations).

Creates a frozen snapshot of the agent for mass walk-forward validation.
Also creates an AgentTemplate for the coach system to copy from.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...Agents.Hivemind.Models.coach_models import AgentTemplate
from ...Agents.Models.agent_models import Agent
from ..Models.crucible_models import CrucibleEntry


class CrucibleEntryService:
    """Service for managing entry into the Crucible."""

    async def _get_dynamic_threshold(self, session: AsyncSession) -> int:
        """
        Calculate dynamic first-entry threshold based on total Crucible entries.

        Scaling:
        - 0-9 entries: level 5
        - 10-49 entries: level 10
        - 50-99 entries: level 15
        - 100-149 entries: level 20
        - 150-199 entries: level 25
        - 200+ entries: level 30 (max)
        """
        count_result = await session.execute(
            select(func.count()).select_from(CrucibleEntry)
        )
        total_entries = count_result.scalar() or 0

        if total_entries < 10:
            return 5
        elif total_entries < 50:
            return 10
        elif total_entries < 100:
            return 15
        elif total_entries < 150:
            return 20
        elif total_entries < 200:
            return 25
        else:
            return 30

    async def check_and_enter_crucible(
        self,
        session: AsyncSession,
        agent_id: str,
    ) -> CrucibleEntry | None:
        """
        Check if an agent is eligible for Crucible and create an entry if so.

        First entry eligibility (EITHER qualifies):
        - Generation >= 3 (evolved agents), OR
        - Level >= dynamic threshold (5 -> 10 -> 15 -> ... -> 30 max)

        Subsequent entries: Every 5 levels after first entry.
        """
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return None

        level = agent.level or 1
        generation = agent.generation or 1
        is_eligible = False

        entry_result = await session.exec(
            select(CrucibleEntry)
            .where(CrucibleEntry.agent_id == agent_id)
            .order_by(CrucibleEntry.level_at_entry.desc())
        )
        existing_entries = entry_result.all()

        if not existing_entries:
            # First entry: Gen 3+ OR Level >= threshold
            level_threshold = await self._get_dynamic_threshold(session)
            if generation >= 3 or level >= level_threshold:
                is_eligible = True
        else:
            # Subsequent entries: Every 5 levels after last entry
            last_entry_level = existing_entries[0].level_at_entry
            if level >= last_entry_level + 5:
                is_eligible = True

        if not is_eligible:
            return None

        # Create Crucible Entry (Frozen Snapshot)
        entry = CrucibleEntry(
            agent_id=agent.agent_id,
            snapshot_id=str(uuid.uuid4()),
            level_at_entry=level,
            traits=agent.traits,
            assigned_patterns=agent.assigned_patterns,
            pattern_weights=agent.pattern_weights or {},
            starting_balance=50000.0,
            current_balance=50000.0,
            status="pending",
            created_at=datetime.utcnow(),
        )

        session.add(entry)
        await session.flush()  # Get entry ID before creating template

        # Create AgentTemplate for coach system (agents spin off templates, keep evolving)
        template = AgentTemplate(
            template_id=str(uuid.uuid4()),
            origin_type="crucible",
            source_agent_id=agent.agent_id,
            source_crucible_entry_id=entry.id,
            name=f"{agent.name or agent.agent_id[:8]} (Crucible L{level})",
            traits=agent.traits.copy() if agent.traits else {},
            assigned_patterns=agent.assigned_patterns.copy() if agent.assigned_patterns else [],
            pattern_weights=agent.pattern_weights.copy() if agent.pattern_weights else {},
            overall_fitness=Decimal(str(agent.fitness_score or 0)),
            regime_scores=agent.fitness_by_regime.copy() if agent.fitness_by_regime else {},
            times_copied=0,
            created_at=datetime.utcnow(),
        )

        session.add(template)
        await session.commit()
        await session.refresh(entry)

        reason = f"gen {generation}" if generation >= 3 else f"level {level}"
        print(f"[Crucible] Agent {agent_id[:8]} entered Crucible ({reason}) -> Template {template.template_id[:8]}")
        return entry

    async def get_pending_entries(self, session: AsyncSession) -> list[CrucibleEntry]:
        """Get all entries waiting to be tested."""
        result = await session.exec(select(CrucibleEntry).where(CrucibleEntry.status == "pending"))
        return result.all()

    async def check_agents_batch(
        self,
        session: AsyncSession,
        agent_ids: list[str],
    ) -> list[CrucibleEntry]:
        """
        Check multiple agents for Crucible eligibility.

        Used by evolution cycle to batch-check agents that just leveled up.

        Args:
            session: Database session
            agent_ids: List of agent IDs to check

        Returns:
            List of CrucibleEntry objects created (agents that qualified)
        """
        entries_created = []

        for agent_id in agent_ids:
            try:
                entry = await self.check_and_enter_crucible(session, agent_id)
                if entry:
                    entries_created.append(entry)
            except Exception as err:
                print(f"[Crucible] Error checking agent {agent_id[:8]}: {err}")
                continue

        return entries_created
