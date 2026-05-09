"""
Crucible Entry Service - Handle agent entry into the Crucible.

Triggers when an agent reaches level 15-20, and every 5 levels thereafter.
Creates a frozen snapshot of the agent for mass walk-forward validation.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...Agents.Models.agent_models import Agent
from ..Models.crucible_models import CrucibleEntry


class CrucibleEntryService:
    """Service for managing entry into the Crucible."""

    async def check_and_enter_crucible(
        self,
        session: AsyncSession,
        agent_id: str,
    ) -> CrucibleEntry | None:
        """
        Check if an agent is eligible for Crucible and create an entry if so.

        Thresholds:
        - First entry: Level 15 (or configurable 15-20)
        - Subsequent: Every 5 levels after the first entry
        """
        # Get agent
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return None

        level = agent.level or 1

        # Eligibility logic
        is_eligible = False

        # Get existing entries for this agent to check frequency
        entry_result = await session.exec(
            select(CrucibleEntry)
            .where(CrucibleEntry.agent_id == agent_id)
            .order_by(CrucibleEntry.level_at_entry.desc())
        )
        existing_entries = entry_result.all()

        if not existing_entries:
            # First time entry threshold
            if level >= 15:
                is_eligible = True
        else:
            # Subsequent entry every 5 levels
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
        await session.commit()
        await session.refresh(entry)

        print(f"[Crucible] Agent {agent_id} entered Crucible at level {level}")
        return entry

    async def get_pending_entries(self, session: AsyncSession) -> list[CrucibleEntry]:
        """Get all entries waiting to be tested."""
        result = await session.exec(select(CrucibleEntry).where(CrucibleEntry.status == "pending"))
        return result.all()
