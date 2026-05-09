"""
Memory Integration Service - Wire memories into backtest and spawn flows.

This service provides the glue between:
- Backtest outcomes -> Memory creation (lessons, affirmations, regrets)
- Spawning -> Memory inheritance from parents
- Memory review triggers -> LLM consolidation

Memory Types Created from Backtests:
- affirmation: From winning trades (what worked)
- regret: From losing trades (what to avoid)
- lesson: From patterns in outcomes (generalized learnings)
- observation: From market conditions (neutral facts)
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from ..Models.memory_models import MemoryType
from .memory_service import (
    create_memory,
    get_agent_memories,
    get_weak_memories,
    inherit_memories_for_child,
    should_trigger_review,
    update_memory_weight,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants for Memory Creation
# =============================================================================

# Thresholds for creating memories from trades
WIN_STREAK_THRESHOLD = 3  # Create affirmation after 3 wins
LOSS_STREAK_THRESHOLD = 2  # Create regret after 2 losses
BIG_WIN_THRESHOLD = 5.0  # Create lesson for wins > 5%
BIG_LOSS_THRESHOLD = -3.0  # Create regret for losses > 3%
TRADE_BATCH_SIZE = 10  # Process memories every N trades


# =============================================================================
# Memory Creation from Backtest Trades
# =============================================================================


async def create_memories_from_trades(
    session: AsyncSession,
    agent_id: str,
    trades: list[dict],
    regime: str = "unknown",
    timeframe: str = "1h",
) -> list[str]:
    """
    Create memories from backtest trade outcomes.

    Analyzes trade results to create:
    - Affirmations: Patterns/conditions that led to wins
    - Regrets: Patterns/conditions that led to losses
    - Lessons: Generalized insights from trade patterns
    - Observations: Notable market conditions

    Args:
        session: Database session
        agent_id: Agent ID to create memories for
        trades: List of trade dicts with pnl_pct, pattern_id, etc.
        regime: Market regime during these trades
        timeframe: Timeframe of the trades

    Returns:
        List of created memory IDs
    """
    if not trades:
        return []

    created_memory_ids = []

    # Track streaks and patterns
    win_streak = 0
    loss_streak = 0
    winning_patterns = {}  # pattern_id -> count
    losing_patterns = {}  # pattern_id -> count
    big_wins = []
    big_losses = []

    for trade in trades:
        pnl_pct = trade.get("pnl_pct", 0) or 0
        pattern_id = trade.get("pattern_id", "unknown")

        if pnl_pct > 0:
            # Winning trade
            win_streak += 1
            loss_streak = 0
            winning_patterns[pattern_id] = winning_patterns.get(pattern_id, 0) + 1

            if pnl_pct >= BIG_WIN_THRESHOLD:
                big_wins.append(trade)

        elif pnl_pct < 0:
            # Losing trade
            loss_streak += 1
            win_streak = 0
            losing_patterns[pattern_id] = losing_patterns.get(pattern_id, 0) + 1

            if pnl_pct <= BIG_LOSS_THRESHOLD:
                big_losses.append(trade)

    # Create affirmation for win streaks
    if win_streak >= WIN_STREAK_THRESHOLD:
        memory = await create_memory(
            session=session,
            agent_id=agent_id,
            memory_type=MemoryType.AFFIRMATION,
            content=f"Winning streak of {win_streak} trades in {regime} regime on {timeframe}. "
                    f"Trust this setup when conditions align.",
            weight=min(1.0, 0.7 + (win_streak * 0.05)),  # Higher weight for longer streaks, capped
            confidence=0.8,
            context_snapshot={
                "regime": regime,
                "timeframe": timeframe,
                "streak_length": win_streak,
                "trade_count": len(trades),
            },
        )
        created_memory_ids.append(memory.memory_id)
        logger.info(f"[Memory] Created affirmation for {agent_id}: {win_streak}-trade win streak")

    # Create regret for loss streaks
    if loss_streak >= LOSS_STREAK_THRESHOLD:
        memory = await create_memory(
            session=session,
            agent_id=agent_id,
            memory_type=MemoryType.REGRET,
            content=f"Loss streak of {loss_streak} trades in {regime} regime on {timeframe}. "
                    f"Be more cautious in similar conditions.",
            weight=min(1.0, 0.7 + (loss_streak * 0.05)),
            confidence=0.8,
            context_snapshot={
                "regime": regime,
                "timeframe": timeframe,
                "streak_length": loss_streak,
                "trade_count": len(trades),
            },
        )
        created_memory_ids.append(memory.memory_id)
        logger.info(f"[Memory] Created regret for {agent_id}: {loss_streak}-trade loss streak")

    # Create lessons from big wins
    for trade in big_wins[:2]:  # Limit to 2 per batch
        pattern_id = trade.get("pattern_id", "unknown")
        pnl_pct = trade.get("pnl_pct", 0)
        memory = await create_memory(
            session=session,
            agent_id=agent_id,
            memory_type=MemoryType.LESSON,
            content=f"Big win ({pnl_pct:.1f}%) with pattern {pattern_id[:8]} in {regime} {timeframe}. "
                    f"This pattern works well in these conditions.",
            weight=0.7,
            confidence=0.9,
            linked_trade_ids=[trade.get("trade_id", "")],
            context_snapshot={
                "regime": regime,
                "timeframe": timeframe,
                "pattern_id": pattern_id,
                "pnl_pct": pnl_pct,
            },
        )
        created_memory_ids.append(memory.memory_id)

    # Create regrets from big losses
    for trade in big_losses[:2]:  # Limit to 2 per batch
        pattern_id = trade.get("pattern_id", "unknown")
        pnl_pct = trade.get("pnl_pct", 0)
        memory = await create_memory(
            session=session,
            agent_id=agent_id,
            memory_type=MemoryType.REGRET,
            content=f"Big loss ({pnl_pct:.1f}%) with pattern {pattern_id[:8]} in {regime} {timeframe}. "
                    f"Avoid this pattern in similar conditions.",
            weight=0.8,
            confidence=0.9,
            linked_trade_ids=[trade.get("trade_id", "")],
            context_snapshot={
                "regime": regime,
                "timeframe": timeframe,
                "pattern_id": pattern_id,
                "pnl_pct": pnl_pct,
            },
        )
        created_memory_ids.append(memory.memory_id)

    # Create observation about regime performance
    total_pnl = sum(t.get("pnl_pct", 0) or 0 for t in trades)
    win_rate = sum(1 for t in trades if (t.get("pnl_pct", 0) or 0) > 0) / len(trades) if trades else 0

    if len(trades) >= 5:  # Only create observation with enough data
        memory = await create_memory(
            session=session,
            agent_id=agent_id,
            memory_type=MemoryType.OBSERVATION,
            content=f"In {regime} regime on {timeframe}: {len(trades)} trades, "
                    f"{win_rate*100:.0f}% win rate, {total_pnl:.1f}% total PnL.",
            weight=0.3,
            confidence=0.7,
            context_snapshot={
                "regime": regime,
                "timeframe": timeframe,
                "trade_count": len(trades),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
            },
        )
        created_memory_ids.append(memory.memory_id)

    if created_memory_ids:
        await session.commit()
        logger.info(f"[Memory] Created {len(created_memory_ids)} memories for agent {agent_id}")

    return created_memory_ids


# =============================================================================
# Memory Inheritance for Spawning
# =============================================================================


async def inherit_memories_on_spawn(
    session: AsyncSession,
    parent_id: str,
    child_id: str,
    condensation_rate: float = 0.5,
    decay_rate: float = 0.2,
) -> int:
    """
    Inherit memories from parent to child agent during spawning.

    Uses the agent's condensation_rate trait to determine how many
    memories to inherit, and decay_rate to reduce weight.

    Args:
        session: Database session
        parent_id: Parent agent ID
        child_id: Child agent ID
        condensation_rate: How selective to be (0=all, 1=none)
        decay_rate: Weight reduction for inherited memories

    Returns:
        Number of memories inherited
    """
    inherited = await inherit_memories_for_child(
        session=session,
        parent_agent_id=parent_id,
        child_agent_id=child_id,
        condensation_rate=condensation_rate,
        decay_rate=decay_rate,
        max_memories=50,
    )

    if inherited:
        await session.commit()
        logger.info(
            f"[Memory] Inherited {len(inherited)} memories from {parent_id[:8]} to {child_id[:8]}"
        )

    return len(inherited)


async def inherit_memories_from_both_parents(
    session: AsyncSession,
    parent_a_id: str,
    parent_b_id: str,
    child_id: str,
    condensation_rate: float = 0.5,
    decay_rate: float = 0.2,
) -> int:
    """
    Inherit memories from both parents for crossover children.

    Takes memories from both parents with higher condensation
    to avoid overwhelming the child with too many memories.

    Args:
        session: Database session
        parent_a_id: First parent agent ID
        parent_b_id: Second parent agent ID
        child_id: Child agent ID
        condensation_rate: Base condensation rate (increased for dual inheritance)
        decay_rate: Weight reduction for inherited memories

    Returns:
        Total memories inherited from both parents
    """
    # Higher condensation when inheriting from two parents
    dual_condensation = min(1.0, condensation_rate + 0.2)

    count_a = await inherit_memories_on_spawn(
        session, parent_a_id, child_id, dual_condensation, decay_rate
    )
    count_b = await inherit_memories_on_spawn(
        session, parent_b_id, child_id, dual_condensation, decay_rate
    )

    return count_a + count_b


# =============================================================================
# Memory Review Trigger
# =============================================================================


async def maybe_trigger_memory_review(
    session: AsyncSession,
    agent_id: str,
    backtest_count: int,
) -> bool:
    """
    Check if agent should undergo memory review and queue if needed.

    Memory review is triggered:
    - Every 50 backtests
    - When memory count exceeds 100

    Args:
        session: Database session
        agent_id: Agent ID
        backtest_count: Current backtest count

    Returns:
        True if review should be triggered
    """
    should_review = await should_trigger_review(session, agent_id, backtest_count)

    if should_review:
        # Get weak memories for review
        weak_memories = await get_weak_memories(session, agent_id)

        if weak_memories:
            logger.info(
                f"[Memory] Agent {agent_id[:8]} has {len(weak_memories)} weak memories "
                f"needing review at backtest #{backtest_count}"
            )
            # Queue weak memories for LLM review
            await queue_weak_memories_for_review(session, agent_id)
            return True

    return False


# =============================================================================
# Memory Stats for Dashboard
# =============================================================================


async def get_agent_memory_stats(
    session: AsyncSession,
    agent_id: str,
) -> dict[str, Any]:
    """
    Get memory statistics for an agent.

    Returns:
        Dict with memory counts, type breakdown, avg weight, etc.
    """
    memories = await get_agent_memories(session, agent_id, limit=1000)

    if not memories:
        return {
            "total": 0,
            "by_type": {},
            "avg_weight": 0.0,
            "weak_count": 0,
            "inherited_count": 0,
        }

    # Count by type
    by_type = {}
    for mem in memories:
        mtype = mem.memory_type
        by_type[mtype] = by_type.get(mtype, 0) + 1

    # Calculate stats
    total_weight = sum(m.weight for m in memories)
    weak_count = sum(1 for m in memories if m.weight < 0.15)
    inherited_count = sum(1 for m in memories if m.spawned_from is not None)

    return {
        "total": len(memories),
        "by_type": by_type,
        "avg_weight": total_weight / len(memories),
        "weak_count": weak_count,
        "inherited_count": inherited_count,
        "oldest": memories[-1].created_at.isoformat() if memories else None,
        "newest": memories[0].created_at.isoformat() if memories else None,
    }


# =============================================================================
# LLM Review Queue
# =============================================================================


@dataclass
class MemoryReviewRequest:
    """Request to review a weak memory via LLM."""

    memory_id: str
    agent_id: str
    content: str
    memory_type: str
    current_weight: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class MemoryReviewResult:
    """Result of LLM memory review."""

    memory_id: str
    action: str  # "keep", "strengthen", "weaken", "delete"
    new_weight: float | None
    reasoning: str
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryReviewQueue:
    """
    Queue for LLM-based memory review.

    Manages pending memory reviews and processes them via vLLM.
    Uses an in-memory queue with async processing.
    """

    def __init__(self, max_queue_size: int = 1000):
        self._queue: deque[MemoryReviewRequest] = deque(maxlen=max_queue_size)
        self._results: deque[MemoryReviewResult] = deque(maxlen=1000)
        self._processing = False
        self._vllm_client = None

    def queue_for_review(self, request: MemoryReviewRequest) -> bool:
        """
        Add a memory to the review queue.

        Returns True if queued successfully.
        """
        # Avoid duplicates
        existing_ids = {r.memory_id for r in self._queue}
        if request.memory_id in existing_ids:
            return False

        self._queue.append(request)
        logger.debug(
            "[Memory] Queued memory %s for LLM review (queue size: %d)",
            request.memory_id[:8],
            len(self._queue),
        )
        return True

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    def get_recent_results(self, limit: int = 10) -> list[MemoryReviewResult]:
        """Get recent review results."""
        return list(self._results)[-limit:]

    async def process_queue(
        self,
        session_factory,
        batch_size: int = 5,
    ) -> list[MemoryReviewResult]:
        """
        Process pending reviews via vLLM.

        Args:
            session_factory: Async session factory for DB updates
            batch_size: Number of memories to process per batch

        Returns:
            List of review results
        """
        if self._processing:
            logger.debug("[Memory] Review processing already in progress")
            return []

        self._processing = True
        results = []

        try:
            # Initialize vLLM client if needed
            if self._vllm_client is None:
                try:
                    from Fast_Swarm.local_agents.shared.vllm_client import VLLMClient

                    self._vllm_client = VLLMClient()
                except ImportError:
                    logger.warning("[Memory] vLLM client not available, skipping review")
                    return []

            # Process batch
            batch = []
            for _ in range(min(batch_size, len(self._queue))):
                if self._queue:
                    batch.append(self._queue.popleft())

            if not batch:
                return []

            logger.info("[Memory] Processing %d memories for LLM review", len(batch))

            for request in batch:
                result = await self._review_memory(request, session_factory)
                if result:
                    results.append(result)
                    self._results.append(result)

        except Exception as e:
            logger.error("[Memory] Error processing review queue: %s", e)
        finally:
            self._processing = False

        return results

    async def _review_memory(
        self,
        request: MemoryReviewRequest,
        session_factory,
    ) -> MemoryReviewResult | None:
        """
        Review a single memory via LLM.

        Returns review result with action recommendation.
        """
        if self._vllm_client is None:
            return None

        # Build review prompt
        prompt = f"""Review this trading agent memory and decide its fate.

Memory Type: {request.memory_type}
Current Weight: {request.current_weight:.2f}
Content: {request.content}

Based on the memory content, decide:
- "keep": Memory is valid, maintain current weight
- "strengthen": Memory is valuable, increase weight by 0.1
- "weaken": Memory is questionable, decrease weight by 0.1
- "delete": Memory is harmful/outdated, mark for removal

Respond with JSON: {{"action": "keep|strengthen|weaken|delete", "reasoning": "brief explanation"}}"""

        system_prompt = """You are a trading memory curator. Your job is to evaluate trading lessons, affirmations, and regrets to determine if they are still valuable.

Criteria for evaluation:
- Is the memory specific and actionable?
- Does it reflect sound trading principles?
- Is it relevant to current market conditions?
- Could it lead to good trading decisions?

Be conservative - only weaken/delete clearly bad memories."""

        try:
            response = self._vllm_client.generate(
                prompt=prompt,
                system=system_prompt,
                max_tokens=256,
                json_mode=True,
            )

            if not response.success:
                logger.warning(
                    "[Memory] LLM review failed for %s: %s",
                    request.memory_id[:8],
                    response.error,
                )
                return None

            # Parse response
            parsed = response.parsed or {}
            action = parsed.get("action", "keep")
            reasoning = parsed.get("reasoning", "No reasoning provided")

            # Calculate new weight based on action
            new_weight = request.current_weight
            if action == "strengthen":
                new_weight = min(1.0, request.current_weight + 0.1)
            elif action == "weaken":
                new_weight = max(0.0, request.current_weight - 0.1)
            elif action == "delete":
                new_weight = 0.0

            # Update memory in database
            if action != "keep":
                async with session_factory() as session:
                    await update_memory_weight(
                        session,
                        request.memory_id,
                        new_weight,
                    )
                    await session.commit()
                    logger.info(
                        "[Memory] Updated memory %s: %s (weight %.2f -> %.2f)",
                        request.memory_id[:8],
                        action,
                        request.current_weight,
                        new_weight,
                    )

            return MemoryReviewResult(
                memory_id=request.memory_id,
                action=action,
                new_weight=new_weight if action != "keep" else None,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.error(
                "[Memory] Error reviewing memory %s: %s",
                request.memory_id[:8],
                e,
            )
            return None


# Global review queue instance
_review_queue: MemoryReviewQueue | None = None


def get_review_queue() -> MemoryReviewQueue:
    """Get or create the global memory review queue."""
    global _review_queue
    if _review_queue is None:
        _review_queue = MemoryReviewQueue()
    return _review_queue


async def queue_weak_memories_for_review(
    session: AsyncSession,
    agent_id: str,
) -> int:
    """
    Queue all weak memories for an agent for LLM review.

    Args:
        session: Database session
        agent_id: Agent ID

    Returns:
        Number of memories queued
    """
    queue = get_review_queue()
    weak_memories = await get_weak_memories(session, agent_id)

    queued_count = 0
    for memory in weak_memories:
        request = MemoryReviewRequest(
            memory_id=memory.memory_id,
            agent_id=agent_id,
            content=memory.content,
            memory_type=memory.memory_type,
            current_weight=memory.weight,
        )
        if queue.queue_for_review(request):
            queued_count += 1

    if queued_count > 0:
        logger.info(
            "[Memory] Queued %d weak memories for agent %s for LLM review",
            queued_count,
            agent_id[:8],
        )

    return queued_count


async def run_review_processor(
    session_factory,
    interval_seconds: int = 60,
    batch_size: int = 5,
):
    """
    Background task to process the review queue.

    Run this as an asyncio task from the main lifespan.

    Args:
        session_factory: Async session factory
        interval_seconds: How often to process (default 60s)
        batch_size: Memories to process per batch
    """
    queue = get_review_queue()
    logger.info("[Memory] Starting LLM review processor (interval=%ds)", interval_seconds)

    while True:
        try:
            if queue.get_queue_size() > 0:
                results = await queue.process_queue(session_factory, batch_size)
                if results:
                    actions = {}
                    for r in results:
                        actions[r.action] = actions.get(r.action, 0) + 1
                    logger.info(
                        "[Memory] Review batch complete: %s",
                        ", ".join(f"{k}={v}" for k, v in actions.items()),
                    )
        except Exception as e:
            logger.error("[Memory] Review processor error: %s", e)

        await asyncio.sleep(interval_seconds)
