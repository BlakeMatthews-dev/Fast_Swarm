# Memory Systems

> **Episodic → Semantic → Wisdom**
>
> Three-tier memory architecture for learning from trading experience.

---

## Overview

Trading agents need memory to:
1. Learn from specific experiences (episodic)
2. Build general knowledge (semantic)
3. Develop trading philosophy (wisdom)

```
┌─────────────────────────────────────────────────────────────┐
│                    WISDOM MEMORY                            │
│     "What I believe" - High-level trading philosophy        │
│     Storage: Lifetime | Format: WHEN-DO-BECAUSE rules      │
│                                                             │
│     Triggers: Losing streaks, regime changes, breakthroughs │
└────────────────────────┬────────────────────────────────────┘
                         ▲
                         │ Distillation (every N episodes)
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   SEMANTIC MEMORY                           │
│     "What I've learned" - Aggregated statistics             │
│     Storage: Lifetime | Format: Pattern/Regime stats       │
│                                                             │
│     Updates: Every 50 trades per pattern                    │
└────────────────────────┬────────────────────────────────────┘
                         ▲
                         │ Aggregation
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   EPISODIC MEMORY                           │
│     "What happened" - Specific trade memories               │
│     Storage: ~7 days / ~100 trades | Format: Trade records │
│                                                             │
│     Triggers: Every completed trade                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Source Papers

| Paper | Memory Contribution | Path |
|-------|---------------------|------|
| MacroHFT | M=(K,E,V) memory structure | [../papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) |
| FinAgent | Memory UUID for retrieval | [../papers/arxiv-2512.02227-finagent.md](../papers/arxiv-2512.02227-finagent.md) |
| Reflect Agent | Verbal feedback to wisdom | [../papers/arxiv-2510.08068-reflect-agent.md](../papers/arxiv-2510.08068-reflect-agent.md) |

---

## Episodic Memory

### Purpose
Store specific trading experiences for pattern matching and similar situation retrieval.

### MacroHFT M=(K,E,V) Mapping

From the MacroHFT paper:
- **K (Key)**: Context vector for similarity matching
- **E (Event)**: What action was taken
- **V (Value)**: Outcome/reward

```python
@dataclass
class EpisodicMemory:
    """
    Single episodic memory entry.

    Paper Reference: MacroHFT arxiv-2406.14537
    "Memory structure M=(K,E,V) where K enables retrieval,
     E captures the decision, V stores the outcome"
    """
    memory_id: str
    agent_id: str
    trade_id: str

    # K = Key (for similarity retrieval)
    key_vector: list[float]  # Embedding of trade context
    key_features: dict       # Raw features for interpretability
    # Example key_features:
    # {
    #     'rsi': 28.3,
    #     'regime': 'bear_volatile',
    #     'trend': 'down',
    #     'volume_ratio': 1.45,
    # }

    # E = Event (what happened)
    action: str              # 'BUY', 'SELL', 'HOLD'
    pattern_used: str        # Pattern that triggered
    position_size: float
    entry_price: float

    # V = Value (outcome)
    pnl_pct: float
    outcome_label: str       # 'big_win', 'small_win', etc.
    sharpe_contribution: float

    # Metadata
    timestamp: datetime
    ttl_hours: int = 168     # 7 days
```

### Retrieval Mechanism

```python
def retrieve_similar_episodes(
    current_context: dict,
    memory_store: list[EpisodicMemory],
    k: int = 5,
    similarity_threshold: float = 0.7
) -> list[EpisodicMemory]:
    """
    Retrieve k most similar past episodes.

    Paper Reference: FinAgent arxiv-2512.02227
    "Similarity-based retrieval enables learning from
     analogous historical situations"

    Uses cosine similarity on key vectors.
    """
    current_vector = embed_context(current_context)

    similarities = []
    for memory in memory_store:
        sim = cosine_similarity(current_vector, memory.key_vector)
        if sim >= similarity_threshold:
            similarities.append((memory, sim))

    # Sort by similarity, return top k
    similarities.sort(key=lambda x: -x[1])
    return [mem for mem, _ in similarities[:k]]
```

### Memory Decay

Episodic memories have limited lifetime to:
1. Keep memory size manageable
2. Prioritize recent market conditions
3. Forget outdated patterns

```python
def decay_episodic_memories(
    memories: list[EpisodicMemory],
    current_time: datetime
) -> list[EpisodicMemory]:
    """
    Remove expired memories, keeping at most MAX_EPISODES.

    Retention rules:
    - TTL expired: Remove
    - Big wins: Keep 2x longer
    - Big losses: Keep 1.5x longer (learn from mistakes)
    """
    MAX_EPISODES = 100

    surviving = []
    for mem in memories:
        age_hours = (current_time - mem.timestamp).total_seconds() / 3600
        effective_ttl = mem.ttl_hours

        # Extend TTL for significant outcomes
        if mem.outcome_label == 'big_win':
            effective_ttl *= 2.0
        elif mem.outcome_label == 'big_loss':
            effective_ttl *= 1.5

        if age_hours < effective_ttl:
            surviving.append(mem)

    # Keep most recent if over limit
    surviving.sort(key=lambda x: x.timestamp, reverse=True)
    return surviving[:MAX_EPISODES]
```

---

## Semantic Memory

### Purpose
Aggregated statistics from many episodes - "what works in general".

### Structure

```python
@dataclass
class SemanticMemory:
    """
    Aggregated knowledge from episodic memories.

    Unlike episodic memory which stores specific events,
    semantic memory stores statistical summaries.

    Paper Reference: MacroHFT
    "Semantic layer aggregates episodic experiences into
     generalizable trading knowledge"
    """
    agent_id: str

    # Per-pattern statistics
    pattern_stats: dict[str, PatternStats]

    # Per-regime statistics
    regime_stats: dict[str, RegimeStats]

    # Time-based statistics
    time_of_day_stats: dict[int, TimeStats]  # Hour -> stats
    day_of_week_stats: dict[int, DayStats]   # 0-6 -> stats

    last_updated: datetime


@dataclass
class PatternStats:
    """Statistics for a single pattern."""
    pattern_id: str
    trade_count: int
    win_count: int
    win_rate: float
    avg_pnl_pct: float
    total_pnl_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float

    # Regime breakdown
    performance_by_regime: dict[str, float]
    # {'bull_volatile': 0.82, 'bear_calm': 0.31, ...}

    best_regime: str
    worst_regime: str
```

### Aggregation Flow

```python
def aggregate_to_semantic(
    episodic_memories: list[EpisodicMemory],
    existing_semantic: SemanticMemory
) -> SemanticMemory:
    """
    Aggregate recent episodes into semantic memory.

    Called periodically (e.g., every 50 new trades).

    Paper Reference: MacroHFT
    "Periodic aggregation prevents memory explosion while
     preserving statistical patterns"
    """
    # Group episodes by pattern
    by_pattern = defaultdict(list)
    for mem in episodic_memories:
        by_pattern[mem.pattern_used].append(mem)

    # Calculate stats for each pattern
    for pattern_id, memories in by_pattern.items():
        pnls = [m.pnl_pct for m in memories]
        wins = [m for m in memories if m.pnl_pct > 0]

        stats = PatternStats(
            pattern_id=pattern_id,
            trade_count=len(memories),
            win_count=len(wins),
            win_rate=len(wins) / len(memories) if memories else 0,
            avg_pnl_pct=np.mean(pnls) if pnls else 0,
            total_pnl_pct=sum(pnls),
            sharpe_ratio=calculate_sharpe(pnls),
            max_drawdown_pct=calculate_max_drawdown(pnls),
            performance_by_regime=calculate_regime_performance(memories),
            best_regime=find_best_regime(memories),
            worst_regime=find_worst_regime(memories),
        )

        # Merge with existing stats (EMA blend)
        existing_semantic.pattern_stats[pattern_id] = merge_stats(
            existing_semantic.pattern_stats.get(pattern_id),
            stats,
            alpha=0.3  # 30% weight to new data
        )

    existing_semantic.last_updated = datetime.utcnow()
    return existing_semantic
```

---

## Wisdom Memory

### Purpose
High-level trading philosophy extracted from patterns in semantic memory.

### WHEN-DO-BECAUSE Rules

```python
@dataclass
class WisdomRule:
    """
    High-level trading belief.

    Format: WHEN <condition> DO <action> BECAUSE <reason>

    Paper Reference: Reflect Agent arxiv-2510.08068
    "Verbal feedback loop enables agents to articulate
     and refine their trading philosophy"
    """
    rule_id: str
    agent_id: str

    # Rule components
    when_condition: str   # Natural language + structured
    do_action: str        # Recommended action
    because_reason: str   # Evidence-based justification

    # Structured condition (for matching)
    condition_struct: dict
    # {
    #     'rsi': {'op': '<', 'value': 25},
    #     'regime': {'op': '==', 'value': 'bear_volatile'},
    # }

    # Confidence and evidence
    confidence: float           # 0-1
    supporting_trades: int      # How many trades support this
    contradicting_trades: int   # How many contradict
    last_validated: datetime

    # Origin
    trigger_type: str  # 'losing_streak', 'regime_shift', 'pattern_discovery'
    created_at: datetime
```

### Wisdom Extraction Triggers

```python
def check_wisdom_triggers(
    recent_trades: list[FullTradeRecord],
    semantic_memory: SemanticMemory
) -> list[str]:
    """
    Check if conditions warrant wisdom extraction.

    Triggers:
    1. Losing streak (3+ consecutive losses)
    2. Regime change (market regime shifted)
    3. Pattern breakthrough (pattern exceeds expectations)
    4. Repeated failure (same mistake 5+ times)
    """
    triggers = []

    # Losing streak
    consecutive_losses = count_consecutive_losses(recent_trades)
    if consecutive_losses >= 3:
        triggers.append('losing_streak')

    # Regime change
    if detect_regime_change(recent_trades):
        triggers.append('regime_change')

    # Pattern breakthrough
    breakthrough = find_pattern_breakthroughs(semantic_memory)
    if breakthrough:
        triggers.append('pattern_breakthrough')

    return triggers
```

### Rule Generation (LLM-Assisted)

```python
def extract_wisdom_rule(
    trigger_type: str,
    context: dict,
    semantic_memory: SemanticMemory,
    llm_client: LLMClient
) -> WisdomRule:
    """
    Extract a wisdom rule from current situation.

    Uses LLM to articulate the pattern in natural language,
    then structures it for automated application.

    Paper Reference: Reflect Agent
    "LLM-based verbal reflection enables richer knowledge
     extraction than pure statistical methods"
    """
    # Build prompt with context
    prompt = f"""
    Analyze this trading situation and extract a wisdom rule.

    Trigger: {trigger_type}

    Recent Performance:
    - Last 10 trades: {context['recent_trades_summary']}
    - Current regime: {context['current_regime']}
    - Patterns used: {context['patterns_used']}

    Semantic Memory Insights:
    - Best performing pattern: {semantic_memory.best_pattern}
    - Worst performing regime: {semantic_memory.worst_regime}

    Generate a rule in this format:
    WHEN: [specific condition that led to this situation]
    DO: [recommended action to take]
    BECAUSE: [evidence from the data]

    Be specific and actionable.
    """

    response = llm_client.generate(prompt)

    # Parse response into structured rule
    rule = parse_wisdom_response(response)
    rule.confidence = calculate_rule_confidence(context, semantic_memory)
    rule.supporting_trades = count_supporting_evidence(context)

    return rule
```

### Rule Application

```python
def apply_wisdom_rules(
    current_context: MarketContext,
    wisdom_rules: list[WisdomRule],
    proposed_action: str
) -> tuple[str, list[str]]:
    """
    Check wisdom rules before executing trade.

    Returns modified action and list of triggered rules.

    Example:
    - Proposed: BUY
    - Triggered rule: "WHEN RSI<25 AND regime=bear_volatile DO reduce_size"
    - Result: BUY with 50% position size
    """
    triggered_rules = []
    modified_action = proposed_action

    for rule in wisdom_rules:
        if rule.confidence < 0.5:
            continue  # Skip low-confidence rules

        if matches_condition(current_context, rule.condition_struct):
            triggered_rules.append(rule)

            # Apply rule action
            if 'reduce_size' in rule.do_action:
                modified_action = modify_position_size(modified_action, 0.5)
            elif 'skip' in rule.do_action:
                modified_action = 'HOLD'
            elif 'increase_stop' in rule.do_action:
                modified_action = tighten_stop_loss(modified_action)

    return modified_action, triggered_rules
```

---

## Memory Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        TRADE COMPLETED                           │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     EPISODIC STORAGE                             │
│  1. Create episodic memory entry                                 │
│  2. Calculate key vector for retrieval                           │
│  3. Store with TTL                                               │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │  Every 50 trades?     │
                    └───────────┬───────────┘
                          YES   │   NO
                                │    └──────► Continue
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                   SEMANTIC AGGREGATION                           │
│  1. Group recent episodes by pattern/regime                      │
│  2. Calculate statistics (win rate, Sharpe, etc.)                │
│  3. Merge with existing semantic memory (EMA)                    │
│  4. Identify performance anomalies                               │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │  Wisdom trigger?      │
                    │  (losing streak,      │
                    │   regime change, etc.)│
                    └───────────┬───────────┘
                          YES   │   NO
                                │    └──────► Continue
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                   WISDOM EXTRACTION                              │
│  1. Analyze trigger context                                      │
│  2. Use LLM to articulate pattern                                │
│  3. Create WHEN-DO-BECAUSE rule                                  │
│  4. Validate against historical data                             │
│  5. Store if confidence > threshold                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Code

See [../code/memory_retrieval.py](../code/memory_retrieval.py) and [../code/wisdom_extraction.py](../code/wisdom_extraction.py) for production implementations.

---

## Related Files

- [../architecture/5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md) - Memory in cognitive hierarchy
- [../architecture/data-schemas.md](../architecture/data-schemas.md) - Memory data structures
- [../papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) - MacroHFT memory paper
- [../papers/arxiv-2510.08068-reflect-agent.md](../papers/arxiv-2510.08068-reflect-agent.md) - Reflect Agent wisdom

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
