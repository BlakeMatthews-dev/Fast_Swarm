"""
Agent Memory Service for Fast_Swarm.

Provides CRUD operations for agent memories with:
- Type-specific weight clamping
- Jaccard word similarity for conflict detection (60% threshold)
- Rank-based selection for inheritance
"""

import uuid
from datetime import datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..Models.memory_models import (
    INHERITANCE_PRIORITY,
    WEIGHT_BOUNDS,
    AgentMemory,
    MemoryConflict,
    MemoryInheritanceResult,
    MemoryType,
)

# Constants
CONFLICT_THRESHOLD = 0.60  # 60% Jaccard similarity triggers conflict
WEAK_MEMORY_THRESHOLD = 0.15  # Memories below this weight surface for review
REVIEW_TRADE_COUNT = 50  # Trigger review after this many backtests
MAX_MEMORIES_BEFORE_REVIEW = 100  # Force review when memory count exceeds this


def clamp_weight_for_type(memory_type: MemoryType, weight: float) -> float:
    """Clamp weight to the valid range for the given memory type."""
    min_w, max_w = WEIGHT_BOUNDS.get(memory_type, (0.0, 1.0))
    return max(min_w, min(max_w, weight))


def jaccard_similarity(text1: str, text2: str) -> float:
    """
    Calculate Jaccard word similarity between two texts.

    Returns value between 0.0 and 1.0.
    Empty texts return 0.0 to avoid division by zero.
    """
    if not text1 or not text2:
        return 0.0

    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    if union == 0:
        return 0.0

    return intersection / union


async def create_memory(
    session: AsyncSession,
    agent_id: str,
    memory_type: MemoryType,
    content: str,
    weight: float = 0.5,
    confidence: float = 0.5,
    linked_trade_ids: list[str] | None = None,
    context_snapshot: dict | None = None,
    spawned_from: str | None = None,
) -> AgentMemory:
    """
    Create a new memory with type-specific weight clamping.

    Args:
        session: Database session
        agent_id: ID of the agent owning this memory
        memory_type: Type of memory (affects weight bounds)
        content: The memory content text
        weight: Initial weight (will be clamped to type bounds)
        confidence: Confidence level 0-1
        linked_trade_ids: Trade IDs this memory relates to
        context_snapshot: JSONB context data
        spawned_from: Parent memory ID if inherited

    Returns:
        Created AgentMemory instance
    """
    # Clamp weight to type-specific bounds
    clamped_weight = clamp_weight_for_type(memory_type, weight)

    memory = AgentMemory(
        memory_id=str(uuid.uuid4()),
        agent_id=agent_id,
        memory_type=memory_type.value,
        content=content,
        weight=clamped_weight,
        confidence=max(0.0, min(1.0, confidence)),
        linked_trade_ids=linked_trade_ids or [],
        context_snapshot=context_snapshot or {},
        spawned_from=spawned_from,
        created_at=datetime.utcnow(),
        last_accessed_at=datetime.utcnow(),
    )

    session.add(memory)
    await session.flush()

    return memory


async def get_memory_by_id(
    session: AsyncSession,
    memory_id: str,
    include_deleted: bool = False,
) -> AgentMemory | None:
    """Fetch a specific memory by ID."""
    statement = select(AgentMemory).where(AgentMemory.memory_id == memory_id)
    if not include_deleted:
        statement = statement.where(AgentMemory.deleted.is_(False))

    result = await session.execute(statement)
    return result.scalars().first()


async def get_agent_memories(
    session: AsyncSession,
    agent_id: str,
    memory_type: MemoryType | None = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentMemory]:
    """
    Fetch all memories for an agent.

    Args:
        session: Database session
        agent_id: Agent to fetch memories for
        memory_type: Optional filter by type
        include_deleted: Whether to include soft-deleted memories
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of AgentMemory instances
    """
    statement = select(AgentMemory).where(AgentMemory.agent_id == agent_id)

    if memory_type:
        statement = statement.where(AgentMemory.memory_type == memory_type.value)

    if not include_deleted:
        statement = statement.where(AgentMemory.deleted.is_(False))

    statement = statement.order_by(AgentMemory.created_at.desc())
    statement = statement.offset(offset).limit(limit)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def detect_conflict(
    session: AsyncSession,
    agent_id: str,
    new_content: str,
    threshold: float = CONFLICT_THRESHOLD,
) -> list[MemoryConflict]:
    """
    Find existing memories that conflict with new content.

    Uses Jaccard word similarity with configurable threshold (default 60%).
    Higher similarity indicates potential contradiction or redundancy.

    Args:
        session: Database session
        agent_id: Agent to check memories for
        new_content: New memory content to check against
        threshold: Similarity threshold (0.6 = 60%)

    Returns:
        List of MemoryConflict objects for memories above threshold
    """
    # Get all active memories for this agent
    existing_memories = await get_agent_memories(session, agent_id, include_deleted=False, limit=1000)

    conflicts = []
    for memory in existing_memories:
        similarity = jaccard_similarity(new_content, memory.content)

        if similarity >= threshold:
            # Determine conflict type based on similarity level
            if similarity >= 0.9:
                conflict_type = "contradiction"  # Nearly identical
            elif similarity >= 0.75:
                conflict_type = "overlap"  # Significant overlap
            else:
                conflict_type = "refinement"  # Related but different

            conflicts.append(
                MemoryConflict(
                    conflicting_memory=memory,
                    similarity_score=similarity,
                    conflict_type=conflict_type,
                )
            )

    # Sort by similarity (highest first)
    conflicts.sort(key=lambda c: c.similarity_score, reverse=True)
    return conflicts


async def select_for_inheritance(
    session: AsyncSession,
    agent_id: str,
    condensation_rate: float,
    max_memories: int = 50,
) -> MemoryInheritanceResult:
    """
    Select memories for inheritance to child agent.

    Uses rank-based selection weighted by:
    1. Memory type priority (affirmation/regret > lesson > opinion > etc.)
    2. Memory weight (higher = more important)
    3. Condensation rate (agent trait controlling memory inheritance)

    Args:
        session: Database session
        agent_id: Parent agent ID
        condensation_rate: Agent trait 0-1 (higher = more selective)
        max_memories: Maximum memories to inherit

    Returns:
        MemoryInheritanceResult with selected memories
    """
    # Get all active, non-weak memories
    all_memories = await get_agent_memories(session, agent_id, include_deleted=False, limit=1000)

    # Filter out weak memories
    candidates = [m for m in all_memories if m.weight >= WEAK_MEMORY_THRESHOLD]
    total_candidates = len(candidates)

    if not candidates:
        return MemoryInheritanceResult(
            selected_memories=[],
            total_candidates=0,
            condensation_rate=condensation_rate,
            selection_method="none",
        )

    # Score each memory: priority * weight
    scored: list[tuple[float, AgentMemory]] = []
    for memory in candidates:
        mem_type = MemoryType(memory.memory_type)
        priority = INHERITANCE_PRIORITY.get(mem_type, 1)
        score = priority * memory.weight
        scored.append((score, memory))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Calculate how many to select based on condensation rate
    # Higher condensation = fewer memories passed on
    selection_count = int(len(scored) * (1.0 - condensation_rate))
    selection_count = max(1, min(selection_count, max_memories))

    selected = [memory for _, memory in scored[:selection_count]]

    return MemoryInheritanceResult(
        selected_memories=selected,
        total_candidates=total_candidates,
        condensation_rate=condensation_rate,
        selection_method="priority_weighted",
    )


async def reinforce_memory(
    session: AsyncSession,
    memory_id: str,
    weight_boost: float = 0.05,
) -> AgentMemory | None:
    """
    Reinforce a memory by incrementing its count and boosting weight.

    Args:
        session: Database session
        memory_id: Memory to reinforce
        weight_boost: Amount to increase weight (clamped to type bounds)

    Returns:
        Updated memory or None if not found
    """
    memory = await get_memory_by_id(session, memory_id)
    if not memory:
        return None

    # Increment reinforcement counter
    memory.reinforcement_count += 1

    # Boost weight (still clamped to type bounds)
    mem_type = MemoryType(memory.memory_type)
    new_weight = memory.weight + weight_boost
    memory.weight = clamp_weight_for_type(mem_type, new_weight)

    # Update access time
    memory.last_accessed_at = datetime.utcnow()

    await session.flush()
    return memory


async def contradict_memory(
    session: AsyncSession,
    memory_id: str,
    weight_penalty: float = 0.1,
) -> AgentMemory | None:
    """
    Record a contradiction against a memory.

    Args:
        session: Database session
        memory_id: Memory to contradict
        weight_penalty: Amount to decrease weight

    Returns:
        Updated memory or None if not found
    """
    memory = await get_memory_by_id(session, memory_id)
    if not memory:
        return None

    # Increment contradiction counter
    memory.contradiction_count += 1

    # Reduce weight (still clamped to type bounds)
    mem_type = MemoryType(memory.memory_type)
    new_weight = memory.weight - weight_penalty
    memory.weight = clamp_weight_for_type(mem_type, new_weight)

    # Update access time
    memory.last_accessed_at = datetime.utcnow()

    await session.flush()
    return memory


async def soft_delete_memory(
    session: AsyncSession,
    memory_id: str,
) -> bool:
    """
    Soft delete a memory (preserves for audit trail).

    Returns True if deleted, False if not found.
    """
    memory = await get_memory_by_id(session, memory_id, include_deleted=True)
    if not memory:
        return False

    memory.deleted = True
    await session.flush()
    return True


async def update_memory_weight(
    session: AsyncSession,
    memory_id: str,
    new_weight: float,
) -> AgentMemory | None:
    """
    Update a memory's weight directly (for LLM review).

    Args:
        session: Database session
        memory_id: Memory to update
        new_weight: New weight value (clamped to type bounds)

    Returns:
        Updated memory or None if not found
    """
    memory = await get_memory_by_id(session, memory_id)
    if not memory:
        return None

    # Clamp to type bounds
    mem_type = MemoryType(memory.memory_type)
    memory.weight = clamp_weight_for_type(mem_type, new_weight)

    # Update access time
    memory.last_accessed_at = datetime.utcnow()

    await session.flush()
    return memory


async def get_weak_memories(
    session: AsyncSession,
    agent_id: str,
    threshold: float = WEAK_MEMORY_THRESHOLD,
) -> list[AgentMemory]:
    """
    Get memories below the weak threshold for LLM review.

    These memories have low weight and may need:
    - Deletion if no longer relevant
    - Promotion if they should be strengthened
    - Merger if redundant with other memories
    """
    statement = (
        select(AgentMemory)
        .where(AgentMemory.agent_id == agent_id)
        .where(AgentMemory.deleted.is_(False))
        .where(AgentMemory.weight < threshold)
        .order_by(AgentMemory.weight.asc())
    )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def should_trigger_review(
    session: AsyncSession,
    agent_id: str,
    backtest_count: int,
) -> bool:
    """
    Determine if agent should undergo memory review.

    Triggers review if:
    - Backtest count is multiple of REVIEW_TRADE_COUNT (50)
    - Memory count exceeds MAX_MEMORIES_BEFORE_REVIEW (100)
    """
    if backtest_count > 0 and backtest_count % REVIEW_TRADE_COUNT == 0:
        return True

    memories = await get_agent_memories(session, agent_id, limit=MAX_MEMORIES_BEFORE_REVIEW + 1)
    return len(memories) > MAX_MEMORIES_BEFORE_REVIEW


# =============================================================================
# Memory Type Validation
# =============================================================================

VALID_MEMORY_TYPES = {m.value for m in MemoryType}


def validate_memory_type(memory_type: str) -> bool:
    """Check if a memory type string is valid."""
    return memory_type in VALID_MEMORY_TYPES


def get_memory_type_count() -> int:
    """Return the number of supported memory types (6)."""
    return len(MemoryType)


def get_weight_range(memory_type: MemoryType) -> tuple[float, float]:
    """Get the weight range for a memory type."""
    return WEIGHT_BOUNDS.get(memory_type, (0.0, 1.0))


def get_priority(memory_type: MemoryType) -> int:
    """Get the inheritance priority for a memory type."""
    return INHERITANCE_PRIORITY.get(memory_type, 1)


# =============================================================================
# Memory Inheritance Decay
# =============================================================================

WEIGHT_FLOOR = 0.1  # Minimum weight for inherited memories


def apply_inheritance_decay(
    weight: float,
    decay_rate: float,
) -> float:
    """
    Apply inheritance decay to a memory weight.

    Args:
        weight: Current memory weight
        decay_rate: Decay rate from agent's inheritance_decay trait (0-1)

    Returns:
        Decayed weight, floored at WEIGHT_FLOOR (0.1)
    """
    decayed = weight * (1.0 - decay_rate)
    return max(WEIGHT_FLOOR, decayed)


async def inherit_memories_for_child(
    session: AsyncSession,
    parent_agent_id: str,
    child_agent_id: str,
    condensation_rate: float,
    decay_rate: float,
    max_memories: int = 50,
) -> list[AgentMemory]:
    """
    Inherit memories from parent to child with decay and condensation.

    Args:
        session: Database session
        parent_agent_id: Parent agent ID
        child_agent_id: Child agent ID
        condensation_rate: Agent trait controlling how many memories pass on
        decay_rate: Agent trait controlling weight decay
        max_memories: Maximum memories to inherit

    Returns:
        List of created memories for child
    """
    # Select memories for inheritance
    inheritance_result = await select_for_inheritance(session, parent_agent_id, condensation_rate, max_memories)

    inherited = []
    for parent_memory in inheritance_result.selected_memories:
        # Apply decay to weight
        decayed_weight = apply_inheritance_decay(parent_memory.weight, decay_rate)

        # Create inherited memory for child
        child_memory = await create_memory(
            session=session,
            agent_id=child_agent_id,
            memory_type=MemoryType(parent_memory.memory_type),
            content=parent_memory.content,
            weight=decayed_weight,
            confidence=parent_memory.confidence,
            linked_trade_ids=[],  # Fresh linkage for child
            context_snapshot=parent_memory.context_snapshot.copy(),
            spawned_from=parent_memory.memory_id,
        )
        inherited.append(child_memory)

    return inherited


# =============================================================================
# Weak Memory Review Actions
# =============================================================================


class ReviewAction:
    """Possible actions for weak memory review."""

    REINFORCE = "REINFORCE"
    COMBINE = "COMBINE"
    FORGET = "FORGET"
    IMPROVE = "IMPROVE"


def get_review_actions() -> list[str]:
    """Get list of valid review actions."""
    return [ReviewAction.REINFORCE, ReviewAction.COMBINE, ReviewAction.FORGET, ReviewAction.IMPROVE]


def is_weak_memory(weight: float, threshold: float = WEAK_MEMORY_THRESHOLD) -> bool:
    """Check if a memory is weak (below threshold)."""
    return weight < threshold


async def apply_review_action(
    session: AsyncSession,
    memory_id: str,
    action: str,
    weight_boost: float = 0.1,
) -> AgentMemory | None:
    """
    Apply a review action to a weak memory.

    Args:
        session: Database session
        memory_id: Memory to act on
        action: One of REINFORCE, COMBINE, FORGET, IMPROVE
        weight_boost: Amount to boost weight if REINFORCE

    Returns:
        Updated memory or None if not found/deleted
    """
    if action == ReviewAction.REINFORCE:
        return await reinforce_memory(session, memory_id, weight_boost)
    elif action == ReviewAction.FORGET:
        await soft_delete_memory(session, memory_id)
        return None
    elif action == ReviewAction.IMPROVE:
        # For IMPROVE, we just access and mark for later update
        memory = await get_memory_by_id(session, memory_id)
        if memory:
            memory.last_accessed_at = datetime.utcnow()
            await session.flush()
        return memory
    elif action == ReviewAction.COMBINE:
        # COMBINE requires additional parameters - just return the memory
        return await get_memory_by_id(session, memory_id)

    return None
