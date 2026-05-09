#!/usr/bin/env python3
"""
Memory Retrieval Implementation.

This module provides episodic memory storage and similarity-based retrieval
for learning from past trading experiences.

Paper References:
- MacroHFT (arxiv-2406.14537): M=(K,E,V) memory structure
- FinAgent (arxiv-2512.02227): Memory UUID and retrieval

Related Concept: ../concepts/memory-systems.md
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class EpisodicMemory:
    """
    Single episodic memory entry.

    Based on MacroHFT M=(K,E,V) structure:
    - K (Key): Context vector for similarity matching
    - E (Event): What action was taken
    - V (Value): Outcome/reward
    """

    memory_id: str
    agent_id: str
    trade_id: str

    # K = Key (for similarity retrieval)
    key_features: dict[str, float]  # Raw features
    key_embedding: list[float] | None = None  # Vector embedding

    # E = Event (what happened)
    action: str  # 'BUY', 'SELL', 'HOLD'
    pattern_used: str  # Pattern that triggered
    position_size: float
    entry_price: float

    # V = Value (outcome)
    pnl_pct: float
    outcome_label: str  # 'big_win', 'small_win', 'breakeven', 'small_loss', 'big_loss'

    # Context
    regime: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Lifecycle
    ttl_hours: int = 168  # 7 days default
    access_count: int = 0
    last_accessed: datetime | None = None


@dataclass
class MemoryStore:
    """Container for episodic memories with retrieval capabilities."""

    agent_id: str
    memories: list[EpisodicMemory] = field(default_factory=list)
    max_memories: int = 100


# =============================================================================
# Memory Creation
# =============================================================================


def create_episodic_memory(
    agent_id: str,
    trade_id: str,
    trade_context: dict,
    action: str,
    pattern_used: str,
    position_size: float,
    entry_price: float,
    pnl_pct: float,
    regime: str,
) -> EpisodicMemory:
    """
    Create episodic memory from completed trade.

    Args:
        agent_id: Agent that made the trade
        trade_id: Unique trade identifier
        trade_context: Dict of market context at trade time
        action: Trade action taken
        pattern_used: Pattern that triggered trade
        position_size: Size of position
        entry_price: Entry price
        pnl_pct: Trade P&L percentage
        regime: Market regime at trade time

    Returns:
        New episodic memory entry
    """
    # Generate memory ID
    memory_id = hashlib.sha256(f"{agent_id}:{trade_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]

    # Classify outcome
    outcome_label = classify_outcome(pnl_pct)

    # Extract key features (normalized for comparison)
    key_features = normalize_context_features(trade_context)

    # Generate embedding (simple version - could use more sophisticated methods)
    key_embedding = generate_simple_embedding(key_features)

    # Adjust TTL based on outcome significance
    ttl_hours = calculate_ttl(outcome_label)

    return EpisodicMemory(
        memory_id=memory_id,
        agent_id=agent_id,
        trade_id=trade_id,
        key_features=key_features,
        key_embedding=key_embedding,
        action=action,
        pattern_used=pattern_used,
        position_size=position_size,
        entry_price=entry_price,
        pnl_pct=pnl_pct,
        outcome_label=outcome_label,
        regime=regime,
        ttl_hours=ttl_hours,
    )


def classify_outcome(pnl_pct: float) -> str:
    """Classify trade outcome by P&L magnitude."""
    if pnl_pct >= 0.05:  # 5%+
        return "big_win"
    elif pnl_pct >= 0.01:  # 1-5%
        return "small_win"
    elif pnl_pct >= -0.01:  # -1% to 1%
        return "breakeven"
    elif pnl_pct >= -0.05:  # -5% to -1%
        return "small_loss"
    else:  # < -5%
        return "big_loss"


def calculate_ttl(outcome_label: str) -> int:
    """
    Calculate time-to-live based on outcome significance.

    Significant outcomes (wins/losses) live longer for learning.
    """
    ttl_map = {
        "big_win": 336,  # 2 weeks
        "small_win": 168,  # 1 week
        "breakeven": 72,  # 3 days
        "small_loss": 240,  # 10 days (learn from mistakes)
        "big_loss": 336,  # 2 weeks (important to remember)
    }
    return ttl_map.get(outcome_label, 168)


def normalize_context_features(context: dict) -> dict[str, float]:
    """
    Normalize context features for comparison.

    Converts raw values to normalized 0-1 range where possible.
    """
    normalized = {}

    # RSI: already 0-100, normalize to 0-1
    if "rsi" in context:
        normalized["rsi"] = context["rsi"] / 100

    # Price vs EMAs: typically -0.1 to 0.1, normalize
    for ema_key in ["price_vs_ema_20", "price_vs_ema_50"]:
        if ema_key in context:
            normalized[ema_key] = (np.tanh(context[ema_key] * 10) + 1) / 2

    # Volume ratio: typically 0.5-3, normalize
    if "volume_ratio" in context:
        normalized["volume_ratio"] = min(1.0, context["volume_ratio"] / 3)

    # MACD histogram: normalize with tanh
    if "macd_histogram" in context:
        normalized["macd_histogram"] = (np.tanh(context["macd_histogram"] * 100) + 1) / 2

    # Hour of day: 0-23, normalize
    if "hour" in context:
        normalized["hour"] = context["hour"] / 24

    # Day of week: 0-6, normalize
    if "day_of_week" in context:
        normalized["day_of_week"] = context["day_of_week"] / 7

    # Pass through any values already in 0-1 range
    for key, value in context.items():
        if key not in normalized and isinstance(value, (int, float)):
            if 0 <= value <= 1:
                normalized[key] = float(value)

    return normalized


def generate_simple_embedding(features: dict[str, float]) -> list[float]:
    """
    Generate simple embedding vector from features.

    This is a basic implementation. For production, consider
    using learned embeddings or more sophisticated methods.
    """
    # Fixed feature order for consistent embeddings
    feature_order = [
        "rsi",
        "price_vs_ema_20",
        "price_vs_ema_50",
        "volume_ratio",
        "macd_histogram",
        "hour",
        "day_of_week",
    ]

    embedding = []
    for feature in feature_order:
        if feature in features:
            embedding.append(features[feature])
        else:
            embedding.append(0.5)  # Default neutral value

    return embedding


# =============================================================================
# Memory Retrieval
# =============================================================================


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    v1 = np.array(vec1)
    v2 = np.array(vec2)

    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def retrieve_similar_memories(
    current_context: dict,
    memory_store: MemoryStore,
    k: int = 5,
    similarity_threshold: float = 0.7,
    regime_filter: str | None = None,
) -> list[tuple[EpisodicMemory, float]]:
    """
    Retrieve k most similar past episodes.

    Args:
        current_context: Current market context
        memory_store: Store of episodic memories
        k: Number of memories to retrieve
        similarity_threshold: Minimum similarity to include
        regime_filter: Only retrieve from specific regime

    Returns:
        List of (memory, similarity_score) tuples

    Paper Reference: FinAgent - similarity-based retrieval
    """
    if not memory_store.memories:
        return []

    # Generate embedding for current context
    normalized = normalize_context_features(current_context)
    current_embedding = generate_simple_embedding(normalized)

    # Calculate similarities
    similarities = []

    for memory in memory_store.memories:
        # Regime filter
        if regime_filter and memory.regime != regime_filter:
            continue

        # Check if memory has embedding
        if memory.key_embedding is None:
            continue

        # Calculate similarity
        sim = cosine_similarity(current_embedding, memory.key_embedding)

        if sim >= similarity_threshold:
            similarities.append((memory, sim))

    # Sort by similarity and return top k
    similarities.sort(key=lambda x: x[1], reverse=True)

    # Update access counts
    for memory, _ in similarities[:k]:
        memory.access_count += 1
        memory.last_accessed = datetime.utcnow()

    return similarities[:k]


def retrieve_by_outcome(memory_store: MemoryStore, outcome: str, limit: int = 10) -> list[EpisodicMemory]:
    """
    Retrieve memories with specific outcome type.

    Useful for analyzing what leads to wins vs losses.
    """
    matching = [m for m in memory_store.memories if m.outcome_label == outcome]

    # Sort by recency
    matching.sort(key=lambda m: m.timestamp, reverse=True)

    return matching[:limit]


def retrieve_by_pattern(memory_store: MemoryStore, pattern_id: str, limit: int = 20) -> list[EpisodicMemory]:
    """
    Retrieve memories for specific pattern.

    Useful for evaluating pattern performance.
    """
    matching = [m for m in memory_store.memories if m.pattern_used == pattern_id]

    matching.sort(key=lambda m: m.timestamp, reverse=True)

    return matching[:limit]


# =============================================================================
# Memory Management
# =============================================================================


def add_memory(memory_store: MemoryStore, memory: EpisodicMemory) -> None:
    """Add memory to store, maintaining size limits."""
    memory_store.memories.append(memory)

    # Enforce max size
    if len(memory_store.memories) > memory_store.max_memories:
        # Remove oldest low-value memories first
        decay_memories(memory_store, datetime.utcnow())


def decay_memories(memory_store: MemoryStore, current_time: datetime) -> int:
    """
    Remove expired and low-value memories.

    Returns:
        Number of memories removed
    """
    original_count = len(memory_store.memories)
    surviving = []

    for memory in memory_store.memories:
        age_hours = (current_time - memory.timestamp).total_seconds() / 3600

        # Calculate effective TTL (significant outcomes live longer)
        effective_ttl = memory.ttl_hours

        # Frequently accessed memories live longer
        if memory.access_count > 3:
            effective_ttl *= 1.5

        # Check if expired
        if age_hours < effective_ttl:
            surviving.append(memory)

    # If still over limit, remove least valuable
    if len(surviving) > memory_store.max_memories:
        # Score memories by value
        scored = []
        for m in surviving:
            # Value = outcome significance * recency * access frequency
            significance = {"big_win": 1.0, "big_loss": 0.9, "small_loss": 0.7, "small_win": 0.6, "breakeven": 0.3}.get(
                m.outcome_label, 0.5
            )

            age_hours = (current_time - m.timestamp).total_seconds() / 3600
            recency = 1.0 / (1 + age_hours / 24)  # Decay over days

            access_bonus = min(0.3, m.access_count * 0.1)

            value = significance * recency + access_bonus
            scored.append((m, value))

        # Keep top memories by value
        scored.sort(key=lambda x: x[1], reverse=True)
        surviving = [m for m, _ in scored[: memory_store.max_memories]]

    memory_store.memories = surviving
    return original_count - len(surviving)


def get_memory_statistics(memory_store: MemoryStore) -> dict:
    """
    Calculate statistics about memory store.

    Useful for monitoring memory health.
    """
    if not memory_store.memories:
        return {"count": 0}

    outcomes = {}
    regimes = {}
    patterns = {}

    total_pnl = 0
    total_access = 0

    for m in memory_store.memories:
        outcomes[m.outcome_label] = outcomes.get(m.outcome_label, 0) + 1
        regimes[m.regime] = regimes.get(m.regime, 0) + 1
        patterns[m.pattern_used] = patterns.get(m.pattern_used, 0) + 1
        total_pnl += m.pnl_pct
        total_access += m.access_count

    ages = [(datetime.utcnow() - m.timestamp).total_seconds() / 3600 for m in memory_store.memories]

    return {
        "count": len(memory_store.memories),
        "max_capacity": memory_store.max_memories,
        "outcomes": outcomes,
        "regimes": regimes,
        "top_patterns": sorted(patterns.items(), key=lambda x: -x[1])[:5],
        "avg_pnl_pct": total_pnl / len(memory_store.memories),
        "total_access_count": total_access,
        "avg_age_hours": np.mean(ages),
        "oldest_hours": max(ages),
    }


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Create memory store
    store = MemoryStore(agent_id="agent_001", max_memories=50)

    # Simulate adding some memories
    print("Adding memories...")

    for i in range(15):
        context = {
            "rsi": np.random.uniform(20, 80),
            "price_vs_ema_20": np.random.uniform(-0.05, 0.05),
            "volume_ratio": np.random.uniform(0.5, 2.0),
            "macd_histogram": np.random.uniform(-0.01, 0.01),
            "hour": np.random.randint(0, 24),
        }

        memory = create_episodic_memory(
            agent_id="agent_001",
            trade_id=f"trade_{i}",
            trade_context=context,
            action="BUY" if np.random.random() > 0.5 else "SELL",
            pattern_used=f"pattern_{np.random.randint(1, 4)}",
            position_size=0.1,
            entry_price=50000 + np.random.uniform(-1000, 1000),
            pnl_pct=np.random.uniform(-0.05, 0.08),
            regime=np.random.choice(["bull_volatile", "bear_calm", "sideways"]),
        )

        add_memory(store, memory)

    # Retrieve similar memories
    print("\nRetrieving similar memories...")
    test_context = {
        "rsi": 35,
        "price_vs_ema_20": -0.02,
        "volume_ratio": 1.5,
        "macd_histogram": -0.005,
        "hour": 10,
    }

    similar = retrieve_similar_memories(test_context, store, k=3, similarity_threshold=0.5)
    print(f"Found {len(similar)} similar memories:")
    for mem, sim in similar:
        print(f"  {mem.memory_id}: sim={sim:.3f}, outcome={mem.outcome_label}, pnl={mem.pnl_pct:.2%}")

    # Get statistics
    print("\nMemory Statistics:")
    stats = get_memory_statistics(store)
    for key, value in stats.items():
        print(f"  {key}: {value}")
