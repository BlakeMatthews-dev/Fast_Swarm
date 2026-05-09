"""
Agent Memory SQLModel definitions for Fast_Swarm.

Implements typed episodic memory with weight clamping per type,
Jaccard-indexable content, and JSONB metadata for context snapshots.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class MemoryType(str, Enum):
    """Memory types with associated weight ranges and inheritance priority."""

    OBSERVATION = "observation"  # weight: 0.1-0.5, priority: 1
    OPINION = "opinion"  # weight: 0.3-0.8, priority: 3
    LESSON = "lesson"  # weight: 0.5-0.9, priority: 4
    COUNTERFACTUAL = "counterfactual"  # weight: 0.2-0.6, priority: 2
    REGRET = "regret"  # weight: 0.6-1.0, priority: 5
    AFFIRMATION = "affirmation"  # weight: 0.6-1.0, priority: 5


# Weight bounds per memory type (min, max)
WEIGHT_BOUNDS: dict[MemoryType, tuple[float, float]] = {
    MemoryType.OBSERVATION: (0.1, 0.5),
    MemoryType.OPINION: (0.3, 0.8),
    MemoryType.LESSON: (0.5, 0.9),
    MemoryType.COUNTERFACTUAL: (0.2, 0.6),
    MemoryType.REGRET: (0.6, 1.0),
    MemoryType.AFFIRMATION: (0.6, 1.0),
}

# Inheritance priority (higher = more likely to pass to children)
INHERITANCE_PRIORITY: dict[MemoryType, int] = {
    MemoryType.AFFIRMATION: 5,
    MemoryType.REGRET: 5,
    MemoryType.LESSON: 4,
    MemoryType.OPINION: 3,
    MemoryType.COUNTERFACTUAL: 2,
    MemoryType.OBSERVATION: 1,
}


class AgentMemory(SQLModel, table=True):
    """
    Episodic memory for agents with typed classification.

    Supports:
    - Type-specific weight clamping
    - Jaccard word similarity for conflict detection
    - Soft deletion for audit trails
    - JSONB metadata for context and trade linkage
    """

    __tablename__ = "agent_memories"

    id: int | None = Field(default=None, primary_key=True)
    memory_id: str = Field(unique=True, index=True)  # UUID string
    agent_id: str = Field(index=True)  # Foreign key to agents.agent_id

    # Core memory content
    memory_type: str = Field(index=True)  # MemoryType value
    content: str  # The actual memory text (Jaccard-indexed)

    # Confidence and weight (weight clamped to type bounds)
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # JSONB fields for complex data
    linked_trade_ids: list[str] = Field(default=[], sa_column=Column(JSONB))
    linked_memory_ids: list[str] = Field(default=[], sa_column=Column(JSONB))
    context_snapshot: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

    # Inheritance tracking
    spawned_from: str | None = None  # Parent memory_id if inherited

    # Lifecycle counters
    reinforcement_count: int = Field(default=0)  # Times this memory was confirmed
    contradiction_count: int = Field(default=0)  # Times this memory was contradicted

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = Field(default_factory=datetime.utcnow)

    # Soft delete flag (for audit trail)
    deleted: bool = Field(default=False)

    class Config:
        arbitrary_types_allowed = True


class MemoryConflict(SQLModel):
    """Response model for detected memory conflicts."""

    conflicting_memory: AgentMemory
    similarity_score: float
    conflict_type: str  # "contradiction", "overlap", "refinement"


class MemoryCreateRequest(SQLModel):
    """Request model for creating a new memory."""

    agent_id: str
    memory_type: MemoryType
    content: str
    weight: float = 0.5
    confidence: float = 0.5
    linked_trade_ids: list[str] = []
    context_snapshot: dict[str, Any] = {}


class MemoryInheritanceResult(SQLModel):
    """Result model for memory inheritance selection."""

    selected_memories: list[AgentMemory]
    total_candidates: int
    condensation_rate: float
    selection_method: str  # "priority_weighted", "random", "top_k"
