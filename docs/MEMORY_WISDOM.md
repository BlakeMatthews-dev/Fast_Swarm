# Memory & Wisdom System

The 7-tier memory system enables agents to learn from experience and accumulate knowledge across generations.

## The 7 Memory Tiers

| Tier | Type | Weight Range | Priority | Purpose |
|------|------|--------------|----------|---------|
| 1 | `observation` | 0.1 - 0.5 | 1 | Neutral patterns noticed |
| 2 | `counterfactual` | 0.2 - 0.6 | 2 | What-if analysis |
| 3 | `opinion` | 0.3 - 0.8 | 3 | Beliefs with confidence |
| 4 | `lesson` | 0.5 - 0.9 | 4 | Actionable takeaways |
| 5 | `regret` | 0.6 - 1.0 | 5 | Decisions to NOT repeat |
| 6 | `affirmation` | 0.6 - 1.0 | 5 | Decisions to repeat |
| 7 | `wisdom` | N/A | N/A | Distilled from Crucible (system-level) |

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         7-TIER MEMORY PYRAMID                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                            ┌─────────┐                                  │
│                       7    │ WISDOM  │  ← Crucible distillation (vLLM)  │
│                            └────┬────┘                                  │
│                                 │                                        │
│                    ┌────────────┴────────────┐                          │
│               5-6  │  REGRET  │ AFFIRMATION  │  ← Strong beliefs        │
│                    └────────────┬────────────┘                          │
│                                 │                                        │
│                         ┌───────┴───────┐                               │
│                    4    │    LESSON     │  ← Actionable takeaways       │
│                         └───────┬───────┘                               │
│                                 │                                        │
│                         ┌───────┴───────┐                               │
│                    3    │    OPINION    │  ← Beliefs + confidence       │
│                         └───────┬───────┘                               │
│                                 │                                        │
│                         ┌───────┴───────┐                               │
│                    2    │COUNTERFACTUAL │  ← What-if analysis           │
│                         └───────┬───────┘                               │
│                                 │                                        │
│                         ┌───────┴───────┐                               │
│                    1    │  OBSERVATION  │  ← Raw pattern notices        │
│                         └───────────────┘                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Memory Creation Triggers

### Per Backtest Session

After each agent's backtest batch completes (`backtest_service.py`):

| Trigger | Memory Type | Condition |
|---------|-------------|-----------|
| Win streak | `affirmation` | 3+ consecutive wins |
| Loss streak | `regret` | 2+ consecutive losses |
| Big win | `lesson` | Trade PnL > 5% |
| Big loss | `regret` | Trade PnL < -3% |
| Batch summary | `observation` | 5+ trades in batch |

### Memory Review (Every 50 Backtests)

When `backtest_count % 50 == 0`:
- Weak memories (weight < 0.15) are flagged
- vLLM reviews and can: REINFORCE, FORGET, IMPROVE, or COMBINE

## Memory Inheritance

When agents spawn (clone or crossover), they inherit memories from parents:

### Clone (Single Parent)
```
Parent memories → filter by condensation_rate → decay weight → Child
```

### Crossover (Two Parents)
```
Parent A memories ─┐
                   ├─→ filter by condensation_rate (higher) → decay → Child
Parent B memories ─┘
```

### Inheritance Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `condensation_rate` | 0.5 | Fraction of memories to keep (0=all, 1=none) |
| `decay_rate` | 0.2 | Weight reduction on inheritance |
| `max_memories` | 50 | Max memories to inherit |

Controlled by agent traits:
- `memory_condensation`: 0.3-0.7 (how selective)
- `inheritance_decay`: 0.1-0.3 (weight reduction)

## Wisdom Generation (Tier 7)

Wisdom is the 7th and highest tier, generated when an agent completes the Crucible.

### Requirements

- **vLLM required** - No heuristic fallback
- Agent must reach Crucible threshold (dynamic: 5→30 based on leaderboard size)
- Agent must complete Crucible test across all regimes

### Generation Process

1. Agent completes Crucible entry
2. `WisdomTransferService.generate_wisdom_from_entry()` is called
3. Context compiled:
   - Agent's top 10 memories
   - Regime performance scores
   - Traits and philosophy
4. vLLM distills into wisdom JSON:

```json
{
    "title": "Level 5 Crash Specialist",
    "summary": "Agent excels in crash conditions with conservative risk.",
    "excels_in": ["crash", "bear"],
    "avoid_in": ["bull"],
    "key_patterns": ["momentum_reversal"],
    "lessons": [
        "Mean reversion works in crash regime",
        "Lower risk tolerance suits this profile"
    ],
    "confidence": 0.85
}
```

5. Wisdom stored in `wisdom` table

### Crucible Threshold (Dynamic)

| Leaderboard Entries | Level Required |
|---------------------|----------------|
| 0-9 | 5 |
| 10-49 | 10 |
| 50-99 | 15 |
| 100-149 | 20 |
| 150-199 | 25 |
| 200+ | 30 (max) |

## API Endpoints

### Memory Endpoints

```
GET /system/memory/{agent_id}        - Get agent's memories
GET /system/memory/{agent_id}/stats  - Memory statistics
GET /system/memory/{agent_id}/weak   - Weak memories needing review
```

### Wisdom Endpoints

```
GET /system/wisdom/latest?limit=5    - Latest wisdom entries
GET /system/crucible/leaderboard     - Crucible leaderboard with wisdom
```

## Database Tables

### `agent_memories`

| Column | Type | Description |
|--------|------|-------------|
| memory_id | UUID | Unique identifier |
| agent_id | VARCHAR | Owner agent |
| memory_type | ENUM | observation/opinion/lesson/counterfactual/regret/affirmation |
| content | TEXT | Memory content |
| weight | FLOAT | Belief strength (0-1, clamped by type) |
| confidence | FLOAT | Certainty (0-1) |
| reinforcement_count | INT | Times reinforced |
| contradiction_count | INT | Times contradicted |
| spawned_from | UUID | Parent memory (if inherited) |
| context_snapshot | JSONB | Market conditions when created |

### `wisdom`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| agent_id | VARCHAR | Source agent |
| crucible_entry_id | INT | FK to crucible_entries |
| title | VARCHAR | Short title |
| content | JSONB | Full wisdom structure |
| model_used | VARCHAR | vLLM model name |
| created_at | TIMESTAMP | Generation time |

## Key Files

| File | Purpose |
|------|---------|
| `Agents/Models/memory_models.py` | Memory SQLModel definitions |
| `Agents/Services/memory_service.py` | CRUD operations, conflict detection |
| `Agents/Services/memory_integration_service.py` | Backtest/spawn integration |
| `System/Services/wisdom_service.py` | Wisdom generation (7th tier) |
| `System/Services/crucible_entry_service.py` | Crucible threshold logic |
| `local_agents/core/memory.py` | In-memory version (for testing) |

## Configuration

### Memory Thresholds

```python
# memory_service.py
CONFLICT_THRESHOLD = 0.60      # Jaccard similarity for conflicts
WEAK_MEMORY_THRESHOLD = 0.15   # Memories below this need review
REVIEW_TRADE_COUNT = 50        # Trigger review every N backtests
MAX_MEMORIES_BEFORE_REVIEW = 100

# memory_integration_service.py
WIN_STREAK_THRESHOLD = 3       # Affirmation after N wins
LOSS_STREAK_THRESHOLD = 2      # Regret after N losses
BIG_WIN_THRESHOLD = 5.0        # Lesson for wins > N%
BIG_LOSS_THRESHOLD = -3.0      # Regret for losses < N%
```

### Weight Deltas

```python
REINFORCE_DELTA = 0.05   # Weight increase on reinforcement
CONTRADICT_DELTA = 0.05  # Weight decrease on contradiction
MIN_WEIGHT_FLOOR = 0.1   # Minimum weight after decay
```
