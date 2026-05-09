"""
Agent Memory System - V3 Parity + Enhancement.

Memory Types:
- observation: Neutral pattern noticed (weight 0.1-0.5)
- opinion: Belief + confidence (weight 0.3-0.8)
- lesson: Actionable takeaway (weight 0.5-0.9)
- counterfactual: What-if analysis (weight 0.2-0.6)
- regret: Decision to not repeat (weight 0.6-1.0)
- affirmation: Decision to repeat (weight 0.6-1.0)

Priority for Inheritance:
- affirmation: 5
- regret: 5
- lesson: 4
- opinion: 3
- counterfactual: 2
- observation: 1

Conflict Detection: 60% Jaccard word similarity
Memory Review: Weak memories (< 0.15 weight) surfaced for LLM review
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

# =============================================================================
# Constants
# =============================================================================

# Weight ranges by memory type
WEIGHT_RANGES = {
    "observation": (0.1, 0.5),
    "opinion": (0.3, 0.8),
    "lesson": (0.5, 0.9),
    "counterfactual": (0.2, 0.6),
    "regret": (0.6, 1.0),
    "affirmation": (0.6, 1.0),
}

# Inheritance priority (higher = keep)
PRIORITY = {
    "affirmation": 5,
    "regret": 5,
    "lesson": 4,
    "opinion": 3,
    "counterfactual": 2,
    "observation": 1,
}

# Valid memory types
VALID_MEMORY_TYPES = list(WEIGHT_RANGES.keys())

# Conflict detection threshold
JACCARD_CONFLICT_THRESHOLD = 0.60

# Minimum weight floor
MIN_WEIGHT_FLOOR = 0.1

# Review thresholds
REVIEW_WEAK_THRESHOLD = 0.15
REVIEW_BACKTEST_INTERVAL = 50
REVIEW_MEMORY_COUNT_THRESHOLD = 100
REVIEW_WEAK_MEMORY_COUNT = 10

# Reinforcement/contradiction deltas
REINFORCE_DELTA = 0.05
CONTRADICT_DELTA = 0.05

# =============================================================================
# In-Memory Storage (for testing - will be replaced with DB)
# =============================================================================

_memory_store: dict[str, "Memory"] = {}


# =============================================================================
# Data Classes
# =============================================================================

MemoryType = Literal["observation", "opinion", "lesson", "counterfactual", "regret", "affirmation"]


@dataclass
class Memory:
    """Agent memory entry."""

    memory_id: str = ""
    agent_id: str = ""
    memory_type: str = "observation"
    content: str = ""
    weight: float = 0.5
    confidence: float = 0.5
    linked_trade_ids: list = field(default_factory=list)
    linked_memory_ids: list = field(default_factory=list)
    spawned_from: str | None = None
    context_snapshot: dict = field(default_factory=dict)
    created_at: int = 0
    last_accessed_at: int = 0
    reinforcement_count: int = 0
    contradiction_count: int = 0
    deleted: bool = False


# =============================================================================
# CRUD Operations
# =============================================================================


def create_memory(
    agent_id: str,
    memory_type: str,
    content: str,
    weight: float | None = None,
    confidence: float = 0.5,
    linked_trade_ids: list | None = None,
    linked_memory_ids: list | None = None,
    context_snapshot: dict | None = None,
) -> Memory:
    """
    Create a new memory.

    Args:
        agent_id: Agent ID.
        memory_type: One of the valid memory types.
        content: Memory content text.
        weight: Weight (will be clamped to type bounds).
        confidence: Confidence for opinions.
        linked_trade_ids: Trade IDs that spawned this.
        linked_memory_ids: Related memory IDs.
        context_snapshot: Context at creation time.

    Returns:
        Created Memory object.

    Raises:
        ValueError: If memory_type is invalid.
    """
    # Validate type
    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"Invalid memory type: {memory_type}")

    # Get weight bounds
    min_weight, max_weight = WEIGHT_RANGES[memory_type]

    # Default weight to middle of range
    if weight is None:
        weight = (min_weight + max_weight) / 2

    # Clamp weight to type bounds
    weight = max(min_weight, min(max_weight, weight))

    now = int(time.time() * 1000)

    mem = Memory(
        memory_id=str(uuid.uuid4()),
        agent_id=agent_id,
        memory_type=memory_type,
        content=content,
        weight=weight,
        confidence=confidence,
        linked_trade_ids=linked_trade_ids or [],
        linked_memory_ids=linked_memory_ids or [],
        context_snapshot=context_snapshot or {},
        created_at=now,
        last_accessed_at=now,
    )

    # Store in memory
    _memory_store[mem.memory_id] = mem

    return mem


def get_memory(memory_id: str) -> Memory | None:
    """Get memory by ID."""
    mem = _memory_store.get(memory_id)
    if mem and not mem.deleted:
        return mem
    return None


def update_memory(memory_id: str, **updates) -> Memory | None:
    """
    Update memory fields.

    Args:
        memory_id: Memory ID.
        **updates: Fields to update.

    Returns:
        Updated memory or None if not found.
    """
    mem = get_memory(memory_id)
    if not mem:
        return None

    for key, value in updates.items():
        if hasattr(mem, key):
            setattr(mem, key, value)

    # Update access time
    mem.last_accessed_at = int(time.time() * 1000)

    return mem


def delete_memory(memory_id: str) -> bool:
    """
    Delete memory by ID.

    Args:
        memory_id: Memory ID.

    Returns:
        True if deleted, False if not found.
    """
    mem = _memory_store.get(memory_id)
    if mem:
        mem.deleted = True
        return True
    return False


def access_memory(memory_id: str) -> Memory | None:
    """
    Access memory (updates last_accessed_at).

    Args:
        memory_id: Memory ID.

    Returns:
        Memory with updated access time.
    """
    mem = get_memory(memory_id)
    if mem:
        mem.last_accessed_at = int(time.time() * 1000)
    return mem


# =============================================================================
# Linking Operations
# =============================================================================


def link_to_trade(memory_id: str, trade_id: str) -> Memory | None:
    """Link memory to a trade."""
    mem = get_memory(memory_id)
    if mem and trade_id not in mem.linked_trade_ids:
        mem.linked_trade_ids.append(trade_id)
    return mem


def link_to_memory(memory_id: str, other_memory_id: str) -> Memory | None:
    """Link memory to another memory."""
    mem = get_memory(memory_id)
    if mem and other_memory_id not in mem.linked_memory_ids:
        mem.linked_memory_ids.append(other_memory_id)
    return mem


def create_derived_memory(parent_id: str, agent_id: str, memory_type: str, content: str, **kwargs) -> Memory:
    """
    Create a memory derived from another.

    Sets spawned_from and links to parent.
    """
    mem = create_memory(agent_id=agent_id, memory_type=memory_type, content=content, **kwargs)
    mem.spawned_from = parent_id
    mem.linked_memory_ids.append(parent_id)
    return mem


# =============================================================================
# Conflict Detection
# =============================================================================


def calculate_jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Calculate Jaccard similarity between two texts.

    Jaccard = |intersection| / |union|

    Args:
        text_a: First text.
        text_b: Second text.

    Returns:
        Similarity score 0-1.
    """
    if not text_a or not text_b:
        return 0.0

    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())

    if not words_a or not words_b:
        return 0.0

    intersection = len(words_a & words_b)
    union = len(words_a | words_b)

    if union == 0:
        return 0.0

    return intersection / union


def detect_conflict(mem_a: Memory, mem_b: Memory) -> bool:
    """
    Detect if two memories conflict (>= 60% Jaccard similarity).

    Args:
        mem_a: First memory.
        mem_b: Second memory.

    Returns:
        True if conflict detected.
    """
    similarity = calculate_jaccard_similarity(mem_a.content, mem_b.content)
    return similarity >= JACCARD_CONFLICT_THRESHOLD


# =============================================================================
# Inheritance
# =============================================================================


def select_for_inheritance(memories: list[Memory], condensation: float) -> list[Memory]:
    """
    Select memories to inherit based on condensation rate.

    Higher priority types are more likely to be kept.

    Args:
        memories: List of parent memories.
        condensation: Fraction to keep (0-1).

    Returns:
        Selected memories for inheritance.
    """
    if condensation <= 0:
        return []
    if condensation >= 1:
        return list(memories)

    # Calculate effective scores (priority * weight)
    scored = []
    for mem in memories:
        priority = PRIORITY.get(mem.memory_type, 1)
        score = priority * mem.weight
        scored.append((score, mem))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Keep top N based on condensation
    keep_count = max(1, int(len(memories) * condensation))
    return [mem for _, mem in scored[:keep_count]]


def apply_inheritance_decay(memory: Memory, decay_rate: float) -> Memory:
    """
    Apply decay to inherited memory weight.

    Args:
        memory: Memory to decay.
        decay_rate: Decay factor (0-1, where 1 = full decay).

    Returns:
        Memory with decayed weight (floored at 0.1).
    """
    new_weight = memory.weight * (1 - decay_rate)
    memory.weight = max(MIN_WEIGHT_FLOOR, new_weight)
    return memory


# =============================================================================
# Memory Review
# =============================================================================


def get_memories_for_review(memories: list[Memory], threshold: float = REVIEW_WEAK_THRESHOLD) -> list[Memory]:
    """
    Get weak memories that need review.

    Args:
        memories: List of memories.
        threshold: Weight threshold (default 0.15).

    Returns:
        Memories below threshold.
    """
    return [m for m in memories if m.weight < threshold]


def should_trigger_review(
    trigger: str,
    backtest_count: int = 0,
    memory_count: int = 0,
    weak_count: int = 0,
) -> bool:
    """
    Check if memory review should be triggered.

    Args:
        trigger: Trigger type (session_end, backtest_interval, on_birth,
                 memory_count, weak_memory_count).
        backtest_count: Number of backtests completed.
        memory_count: Total memory count.
        weak_count: Count of weak memories.

    Returns:
        True if review should trigger.
    """
    if trigger == "session_end" or trigger == "on_birth":
        return True
    elif trigger == "backtest_interval":
        return backtest_count > 0 and backtest_count % REVIEW_BACKTEST_INTERVAL == 0
    elif trigger == "memory_count":
        return memory_count >= REVIEW_MEMORY_COUNT_THRESHOLD
    elif trigger == "weak_memory_count":
        return weak_count >= REVIEW_WEAK_MEMORY_COUNT
    return False


def apply_review_action(
    memory: Memory,
    action: str,
    new_content: str | None = None,
    combine_with: Memory | None = None,
) -> Memory | None:
    """
    Apply review action to memory.

    Actions:
    - reinforce: Increase weight
    - forget: Delete memory
    - improve: Update content
    - combine: Merge with another memory

    Args:
        memory: Memory to act on.
        action: Action type.
        new_content: New content for 'improve'.
        combine_with: Memory to combine with.

    Returns:
        Updated memory or None if forgotten.
    """
    action = action.lower()

    if action == "reinforce":
        memory.weight = min(1.0, memory.weight + REINFORCE_DELTA)
        memory.reinforcement_count += 1
        return memory

    elif action == "forget":
        memory.deleted = True
        return None

    elif action == "improve":
        if new_content:
            memory.content = new_content
        return memory

    elif action == "combine":
        if combine_with:
            # Merge content
            memory.content = f"{memory.content}. {combine_with.content}"
            # Take max weight
            memory.weight = max(memory.weight, combine_with.weight)
            # Merge links
            memory.linked_memory_ids.extend(combine_with.linked_memory_ids)
            memory.linked_trade_ids.extend(combine_with.linked_trade_ids)
            # Mark combined memory as deleted
            combine_with.deleted = True
        return memory

    return memory


# =============================================================================
# Reinforcement/Contradiction
# =============================================================================


def reinforce_memory(memory_id: str) -> Memory | None:
    """
    Reinforce memory (increase weight).

    Args:
        memory_id: Memory ID.

    Returns:
        Updated memory.
    """
    mem = get_memory(memory_id)
    if not mem:
        return None

    # Get max weight for type
    _, max_weight = WEIGHT_RANGES.get(mem.memory_type, (0, 1))

    mem.weight = min(max_weight, mem.weight + REINFORCE_DELTA)
    mem.reinforcement_count += 1
    mem.last_accessed_at = int(time.time() * 1000)

    return mem


def contradict_memory(memory_id: str) -> Memory | None:
    """
    Contradict memory (decrease weight).

    Args:
        memory_id: Memory ID.

    Returns:
        Updated memory.
    """
    mem = get_memory(memory_id)
    if not mem:
        return None

    mem.weight = max(MIN_WEIGHT_FLOOR, mem.weight - CONTRADICT_DELTA)
    mem.contradiction_count += 1
    mem.last_accessed_at = int(time.time() * 1000)

    return mem


# =============================================================================
# Utility Functions
# =============================================================================


def clear_memory_store():
    """Clear all memories (for testing)."""
    _memory_store.clear()


def get_agent_memories(agent_id: str) -> list[Memory]:
    """Get all memories for an agent."""
    return [m for m in _memory_store.values() if m.agent_id == agent_id and not m.deleted]
