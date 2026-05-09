# 5-Layer Cognitive Hierarchy

> **Planners → Coaches → Committee → Agents → Patterns**
>
> This document describes the cognitive layers within the trading roster, from high-level planning to atomic pattern matching.

---

## Overview

The 5-layer hierarchy provides different levels of abstraction for trading decisions:

```
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 5: PLANNERS                        │
│     Long-term strategy, regime awareness, goal setting      │
│                                                             │
│  Think: "What market are we in? What's our objective?"      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 4: COACHES                         │
│     Roster selection, agent development, trait optimization │
│                                                             │
│  Think: "Which agents should play? How should they evolve?" │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 3: COMMITTEE                       │
│     Vote aggregation, conflict resolution, consensus        │
│                                                             │
│  Think: "What does the group decide? How confident?"        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 2: AGENTS                          │
│     Individual traders with personalities (16 traits)       │
│                                                             │
│  Think: "Given my traits, what do I recommend?"             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 1: PATTERNS                        │
│     Atomic trading rules discovered through evolution       │
│                                                             │
│  Think: "IF conditions THEN signal (entry/exit)"            │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 5: Planners

### Purpose
Set long-term objectives and strategic context.

### Responsibilities

1. **Goal Setting**: Define success metrics (Sharpe > 1.5, max DD < 15%)
2. **Regime Strategy**: Map regimes to strategies (bull → aggressive, bear → defensive)
3. **Time Horizon**: Set planning window (1 week, 1 month)
4. **Capital Allocation**: Distribute capital across strategies

### Intelligence Type
- Meta-cognitive: Thinking about thinking
- Long time horizon (weeks to months)
- Rarely changes decisions

### Paper References

| Paper | Contribution |
|-------|-------------|
| MASA | Multi-agent strategic coordination |
| MacroHFT | Regime-aware planning |

---

## Layer 4: Coaches

### Purpose
Manage agent roster and drive evolution.

### Responsibilities

1. **Roster Selection**: Choose 5-10 agents from pool of 50+
2. **Trait Optimization**: Tune agent traits based on performance
3. **Agent Development**: Spawn, clone, retire agents
4. **Regime Affinity**: Track which agents excel in which regimes

### Intelligence Type
- Managerial: Resource allocation
- Medium time horizon (days to weeks)
- Adapts to regime changes

### Roster Selection Algorithm

```python
def select_roster(
    available_agents: list[Agent],
    current_regime: str,
    roster_size: int = 10
) -> list[Agent]:
    """
    Select agents for active trading roster.

    Selection criteria:
    1. Regime affinity (60% weight)
    2. Recent performance (30% weight)
    3. Diversity bonus (10% weight) - avoid similar traits

    Paper Reference: MASA - Multi-agent selection
    """
    scored_agents = []

    for agent in available_agents:
        # Regime fit
        regime_score = agent.regime_affinity.get(current_regime, 0.5)

        # Recent performance (Sharpe over last 50 trades)
        perf_score = normalize_sharpe(agent.recent_sharpe)

        # Diversity (penalize if too similar to already selected)
        diversity_score = calculate_diversity(agent, scored_agents)

        total_score = (
            0.60 * regime_score +
            0.30 * perf_score +
            0.10 * diversity_score
        )

        scored_agents.append((agent, total_score))

    # Select top N by score
    scored_agents.sort(key=lambda x: -x[1])
    return [a for a, _ in scored_agents[:roster_size]]
```

### Affinity Evolution

```
Agent A: regime_affinity = {
    'bull_volatile': 0.82,   # Excels here
    'bull_calm': 0.65,
    'bear_volatile': 0.31,   # Struggles here
    'bear_calm': 0.45,
    'sideways': 0.55
}

After each trade in regime X:
  - If profitable: affinity[X] += 0.1 * tanh(pnl)
  - If loss: affinity[X] -= 0.1 * tanh(abs(pnl))
  - Bounded to [0.0, 1.0]
```

---

## Layer 3: Committee

### Purpose
Aggregate individual agent recommendations into group decisions.

### Responsibilities

1. **Vote Collection**: Gather votes from active agents
2. **Conflict Resolution**: Handle disagreements (bull vs bear)
3. **Confidence Estimation**: Calculate group confidence
4. **Debate Orchestration**: Facilitate argument exchange

### Voting Mechanisms

| Method | Description | Use Case |
|--------|-------------|----------|
| **Majority** | >50% agreement | Simple decisions |
| **Supermajority** | >66% agreement | High-risk trades |
| **Weighted** | Vote * agent_weight | Performance-based |
| **Bayesian** | Update beliefs iteratively | Complex signals |

### Bull vs Bear Debate

```
┌─────────────────────────────────────────────────────────────┐
│                      DEBATE ROUND 1                         │
├──────────────────────────┬──────────────────────────────────┤
│         BULLS            │            BEARS                 │
├──────────────────────────┼──────────────────────────────────┤
│ "RSI oversold (28),      │ "Death cross on daily,          │
│  price at support,       │  volume declining,              │
│  MACD histogram turning" │  sentiment negative"            │
└──────────────────────────┴──────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      DEBATE ROUND 2                         │
├──────────────────────────┬──────────────────────────────────┤
│     BULL REBUTTAL        │         BEAR REBUTTAL           │
├──────────────────────────┼──────────────────────────────────┤
│ "Death cross lagging,    │ "RSI can stay oversold,         │
│  last 3 death crosses    │  'catching falling knife'       │
│  were false signals"     │  is dangerous here"             │
└──────────────────────────┴──────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FINAL VOTE                               │
│                                                             │
│  Bulls: 3 votes, avg confidence 0.72                        │
│  Bears: 2 votes, avg confidence 0.65                        │
│                                                             │
│  Decision: BUY (weak)                                       │
│  Group Confidence: 0.54                                     │
│  Position Size: Reduced due to low confidence               │
└─────────────────────────────────────────────────────────────┘
```

### Paper References

| Paper | Contribution |
|-------|-------------|
| TradingAgents | Bull/bear debate mechanism |
| FinAgent | Confidence aggregation |

---

## Layer 2: Agents

### Purpose
Individual trading entities with distinct personalities.

### The 16 Traits

| # | Trait | Range | Description |
|---|-------|-------|-------------|
| 1 | `risk_tolerance` | 0-1 | Willingness to take large positions |
| 2 | `hold_duration_bias` | 0-1 | Preference for longer holds |
| 3 | `volatility_seeking` | 0-1 | Attraction to volatile assets |
| 4 | `profit_target_greed` | 0-1 | How far to let winners run |
| 5 | `win_rate_preference` | 0-1 | Many small wins vs few big wins |
| 6 | `drawdown_sensitivity` | 0-1 | Pain from unrealized losses |
| 7 | `momentum_vs_reversion` | 0-1 | Trend following vs mean reversion |
| 8 | `stop_loss_tightness` | 0-1 | How tight to set stops |
| 9 | `entry_aggression` | 0-1 | Chase entries vs wait |
| 10 | `exit_aggression` | 0-1 | Quick exits vs hold |
| 11 | `lookback_preference` | 0-1 | Short vs long indicator periods |
| 12 | `sentiment_weight` | 0-1 | How much to weight sentiment |
| 13 | `news_reactivity` | 0-1 | React to news quickly vs ignore |
| 14 | `sentiment_contrarian` | 0-1 | Go against crowd sentiment |
| 15 | `funding_rate_sensitivity` | 0-1 | Use funding rate in decisions |
| 16 | `correlation_awareness` | 0-1 | Consider portfolio correlation |

### Trait Coupling (Derived Traits)

Some traits are derived to prevent contradictions:

```python
# Derived traits
drawdown_sensitivity = 1 - risk_tolerance * 0.5   # Inversely related
stop_loss_tightness = drawdown_sensitivity * 0.8  # Sensitive agents use tight stops
exit_aggression = (1 - hold_duration_bias) * 0.6  # Short-term traders exit fast
```

### Agent Lifecycle

```
SPAWN (random traits)
    │
    ▼
COMPETE (trade with live roster)
    │
    ├─── Poor performance ───► RETIRE (removed from pool)
    │
    ├─── Good performance ───► SURVIVE (continue trading)
    │
    └─── Excellent performance ───► CLONE (spawn offspring)
                                        │
                                        ▼
                              MUTATE (±10% trait variation)
                                        │
                                        ▼
                              NEW AGENT (joins pool)
```

---

## Layer 1: Patterns

### Purpose
Atomic trading rules that generate signals.

### Pattern Structure

```python
@dataclass
class Pattern:
    """
    Atomic trading pattern discovered through evolution.

    Entry/exit conditions are ranges discovered by competition,
    NOT predefined buckets.
    """
    pattern_id: str
    name: str
    origin: str  # 'chaos', 'academic', 'technical', 'ai', 'hybrid'

    # Entry conditions (all must be true)
    entry_conditions: list[Condition]
    # Example: [
    #   Condition('rsi', 22.0, 35.0),      # RSI between 22-35
    #   Condition('macd_histogram', -0.5, 0.0),  # MACD hist negative but rising
    #   Condition('volume_ratio', 1.2, 3.0),     # Volume 1.2-3x average
    # ]

    # Exit conditions (any triggers exit)
    exit_conditions: list[Condition]

    # Performance metrics (from backtesting)
    fitness_score: float        # 0-100
    total_roi_pct: float
    sharpe_ratio: float
    win_rate: float
    number_of_runs: int
```

### Pattern Tiers

```
TIER 3 (Untested)
    │  Fitness: 0-39 or < 30 trades
    │  Action: Continue testing
    │
    ▼
TIER 2 (Proven)
    │  Fitness: 40-79 with 30+ trades
    │  Action: Eligible for agent assignment
    │
    ▼
TIER 1 (Elite)
       Fitness: 80+ with 100+ trades
       Action: Priority assignment, used as templates
```

### Pattern Discovery Sources

| Origin | Description | Example |
|--------|-------------|---------|
| `chaos` | Random trades analyzed | "RSI 22-35 worked in Jan" |
| `academic` | From research papers | "Kelly sizing formula" |
| `technical` | Classic TA patterns | "Double bottom" |
| `ai` | ML/LLM discovered | "GPT-4 found correlation" |
| `hybrid` | Combined sources | "Academic + evolved ranges" |

---

## Inter-Layer Communication

### Upward Flow (Feedback)

```
Patterns → Agents: Pattern signals
Agents → Committee: Individual votes
Committee → Coaches: Trade outcomes
Coaches → Planners: Agent performance stats
```

### Downward Flow (Constraints)

```
Planners → Coaches: Strategic goals, regime
Coaches → Committee: Active roster, risk limits
Committee → Agents: Decision context
Agents → Patterns: Which patterns to evaluate
```

---

## Related Files

- [3-tier-execution.md](3-tier-execution.md) - How this maps to execution tiers
- [data-schemas.md](data-schemas.md) - Data structures for each layer
- [../meta/traits.md](../meta/traits.md) - Complete trait documentation

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial hierarchy document |
