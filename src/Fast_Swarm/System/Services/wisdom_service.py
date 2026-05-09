"""
Wisdom Transfer Service - The 7th tier of the memory system.

The memory system has 7 tiers:
1. observation - Neutral patterns noticed (weight 0.1-0.5)
2. opinion - Beliefs with confidence (weight 0.3-0.8)
3. lesson - Actionable takeaways (weight 0.5-0.9)
4. counterfactual - What-if analysis (weight 0.2-0.6)
5. regret - Decisions to not repeat (weight 0.6-1.0)
6. affirmation - Decisions to repeat (weight 0.6-1.0)
7. WISDOM - Distilled from Crucible completion (this service)

Wisdom Flow:
1. Agent completes Crucible entry (tested across many regimes)
2. WisdomTransferService.generate_wisdom_from_entry() is called
3. Agent's memories, traits, and performance are compiled
4. vLLM distills this into actionable wisdom (LLM required, no fallback)
5. Wisdom is stored and broadcast to the system

NOTE: LLM is REQUIRED for wisdom generation. No heuristic fallback.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ...Agents.Models.agent_models import Agent
from ...Agents.Services.memory_service import get_agent_memories
from ..Models.crucible_models import CrucibleEntry, Wisdom

# Import vLLM client (required for wisdom generation)
try:
    from ...local_agents.shared.vllm_client import VLLMClient, check_vllm_available
    HAS_VLLM = True
except ImportError:
    HAS_VLLM = False
    VLLMClient = None

# Set up logging
logger = logging.getLogger(__name__)

# =============================================================================
# Wisdom Generation Prompts
# =============================================================================

WISDOM_SYSTEM_PROMPT = """You are a trading wisdom synthesizer for an evolutionary trading system.

Your job is to extract actionable insights from an agent's Crucible performance.
The agent has been tested across multiple market regimes (bull, bear, crash, sideways).

Focus on:
1. What conditions/regimes did the agent excel in?
2. What patterns or strategies worked best?
3. What should future agents learn from this?
4. What should be avoided?

Be concise but insightful. Focus on actionable takeaways.
Respond with JSON:
{
    "title": "Short title for this wisdom (max 10 words)",
    "summary": "1-2 sentence summary of key insight",
    "excels_in": ["list of regimes/conditions where agent excels"],
    "avoid_in": ["list of regimes/conditions to avoid"],
    "key_patterns": ["list of effective pattern types"],
    "lessons": ["list of 2-3 actionable lessons"],
    "confidence": 0.0-1.0
}
"""


class WisdomTransferService:
    """
    Service for distilling agent experience into shared wisdom (7th memory tier).

    Requires vLLM for wisdom generation - no heuristic fallback.
    If vLLM is unavailable, wisdom generation will fail gracefully.
    """

    def __init__(self):
        """Initialize wisdom service with vLLM client."""
        self._llm_client = None
        if HAS_VLLM:
            self._llm_client = VLLMClient(auto_start=True)  # Auto-start vLLM if not running

    async def generate_wisdom_from_entry(
        self,
        session: AsyncSession,
        entry_id: int,
        use_llm: bool = True,
    ) -> Wisdom | None:
        """
        Distill wisdom from a successful Crucible entry.

        Args:
            session: Database session
            entry_id: Crucible entry ID
            use_llm: Whether to use LLM (falls back to heuristic if unavailable)

        Returns:
            Created Wisdom record or None if entry not found/incomplete
        """
        # 1. Get the entry and associated agent
        result = await session.exec(select(CrucibleEntry).where(CrucibleEntry.id == entry_id))
        entry = result.first()

        if not entry or entry.status != "completed":
            logger.warning(f"Crucible entry {entry_id} not found or not completed.")
            return None

        agent_result = await session.exec(select(Agent).where(Agent.agent_id == entry.agent_id))
        agent = agent_result.first()

        # 2. Get agent's memories for richer context
        memories = []
        if agent:
            memories = await get_agent_memories(session, agent.agent_id, limit=20)

        # 3. Prepare context for distillation
        context = {
            "agent_id": entry.agent_id,
            "level": entry.level_at_entry,
            "overall_fitness": float(entry.overall_fitness),
            "regime_scores": entry.regime_scores or {},
            "philosophy": agent.trading_philosophy if agent else "Unknown",
            "traits": entry.traits or {},
            "patterns": entry.assigned_patterns or [],
            "memories": [
                {
                    "type": m.memory_type,
                    "content": m.content,
                    "weight": m.weight,
                }
                for m in memories[:10]  # Top 10 memories
            ],
        }

        # 4. Generate wisdom with vLLM (no fallback - LLM required)
        if not self._llm_client or not HAS_VLLM:
            logger.error("[Wisdom] vLLM client not available - wisdom generation requires LLM")
            return None

        if not check_vllm_available():
            logger.error("[Wisdom] vLLM server not running - wisdom generation requires LLM")
            return None

        try:
            wisdom_data = await self._generate_wisdom_with_llm(context)
            model_used = self._llm_client.model
        except Exception as e:
            logger.error(f"[Wisdom] LLM wisdom generation failed: {e}")
            return None  # No fallback - LLM is required

        # 5. Create Wisdom record
        wisdom = Wisdom(
            agent_id=entry.agent_id,
            crucible_entry_id=entry.id,
            title=wisdom_data.get("title", f"Wisdom from {entry.agent_id[:8]}"),
            content=json.dumps(wisdom_data),
            model_used=model_used,
            created_at=datetime.utcnow(),
        )

        session.add(wisdom)
        await session.commit()
        await session.refresh(wisdom)

        logger.info(f"[Wisdom] Generated wisdom {wisdom.id} from agent {entry.agent_id[:8]} using {model_used}")
        return wisdom

    async def _generate_wisdom_with_llm(self, context: dict) -> dict:
        """Generate wisdom using vLLM (required, no fallback)."""
        # Build prompt with agent context
        prompt = f"""## Agent Performance Summary

Agent ID: {context['agent_id'][:8]}
Level: {context['level']}
Overall Fitness: {context['overall_fitness']:.1f}

## Regime Performance
{json.dumps(context['regime_scores'], indent=2)}

## Trading Philosophy
{context['philosophy']}

## Key Traits
{json.dumps({k: round(v, 2) for k, v in list(context['traits'].items())[:5]}, indent=2)}

## Assigned Patterns
{len(context['patterns'])} patterns assigned

## Agent's Memories (Top Lessons/Insights)
"""
        for mem in context['memories'][:5]:
            prompt += f"- [{mem['type']}] {mem['content'][:100]}...\n"

        prompt += "\nDistill actionable wisdom from this agent's Crucible performance."

        # Call vLLM (async API)
        response = await self._llm_client.generate(
            prompt=prompt,
            system=WISDOM_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=500,
            json_mode=True,
        )

        if response.success and response.parsed:
            return response.parsed

        # If response succeeded but parsing failed, raise error (no fallback)
        raise ValueError(f"vLLM response invalid: {response.error or 'Could not parse JSON'}")

    async def get_latest_wisdom(self, session: AsyncSession, limit: int = 5) -> list[Wisdom]:
        """Retrieve recent pieces of wisdom."""
        result = await session.exec(select(Wisdom).order_by(desc(Wisdom.created_at)).limit(limit))
        return result.all()
