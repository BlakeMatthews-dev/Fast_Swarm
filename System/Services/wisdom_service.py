"""
Wisdom Transfer Service - Consolidate agent knowledge and generate wisdom.

This service takes agents that have completed the Crucible, summarizes their
performance and "memories" (trading results), uses an LLM to distill this into
actionable wisdom, and broadcasts it to the system.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ...Agents.Models.agent_models import Agent
from ..Models.crucible_models import CrucibleEntry, Wisdom

# Set up logging
logger = logging.getLogger(__name__)


class WisdomTransferService:
    """Service for distilling agent experience into shared wisdom."""

    async def generate_wisdom_from_entry(
        self,
        session: AsyncSession,
        entry_id: int,
        model_name: str = "gpt-4",  # Placeholder for LLM choice
    ) -> Wisdom | None:
        """
        Distill wisdom from a successful Crucible entry.
        """
        # 1. Get the entry and associated agent
        result = await session.exec(select(CrucibleEntry).where(CrucibleEntry.id == entry_id))
        entry = result.first()

        if not entry or entry.status != "completed":
            logger.warning(f"Crucible entry {entry_id} not found or not completed.")
            return None

        agent_result = await session.exec(select(Agent).where(Agent.agent_id == entry.agent_id))
        agent = agent_result.first()

        # 2. Prepare context for distillation
        # In a real system, we'd pull trade logs, regime performance, etc.
        context = {
            "agent_id": entry.agent_id,
            "level": entry.level_at_entry,
            "overall_fitness": entry.overall_fitness,
            "regime_scores": entry.regime_scores,
            "philosophy": agent.trading_philosophy if agent else "Unknown",
            "traits": entry.traits,
            "patterns": entry.assigned_patterns,
        }

        # 3. Call LLM to distill wisdom (Simulated for now)
        # In implementation, this would call an LLM utility
        wisdom_content = self._simulate_wisdom_generation(context)

        # 4. Create Wisdom record
        wisdom = Wisdom(
            agent_id=entry.agent_id,
            crucible_entry_id=entry.id,
            title=f"Wisdom from {entry.agent_id[:8]} (Level {entry.level_at_entry})",
            content=wisdom_content,
            model_used=model_name,
            created_at=datetime.utcnow(),
        )

        session.add(wisdom)
        await session.commit()
        await session.refresh(wisdom)

        logger.info(f"Generated wisdom {wisdom.id} from agent {entry.agent_id}")
        return wisdom

    def _simulate_wisdom_generation(self, context: dict) -> str:
        """Simulate LLM distillation logic."""
        best_regime = (
            max(context["regime_scores"], key=context["regime_scores"].get) if context["regime_scores"] else "general"
        )

        wisdom = (
            f"Agent {context['agent_id'][:8]} has mastered the {best_regime} regime. "
            f"With an overall fitness of {context['overall_fitness']:.2f}, "
            f"it suggests that a philosophy of '{context['philosophy']}' coupled with "
            f"patterns {context['patterns']} provides strong stability. "
            "Key takeaway: Prioritize low-volatility patterns when trend strength is ambiguous."
        )
        return wisdom

    async def get_latest_wisdom(self, session: AsyncSession, limit: int = 5) -> list[Wisdom]:
        """Retrieve recent pieces of wisdom."""
        result = await session.exec(select(Wisdom).order_by(desc(Wisdom.created_at)).limit(limit))
        return result.all()
