# Fast_Swarm Crucible System

**Purpose**: Extract wisdom from elite performers and retire them gracefully
**Status**: 🔄 Partial Implementation (between concept and code)

---

## Overview

The Crucible is a **clone-and-retire** architecture that extracts actionable wisdom from top-performing agents before they're retired. This preserves institutional knowledge while making room for new agents.

```
┌─────────────────────────────────────────────────────────────────┐
│                      CRUCIBLE PIPELINE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Elite Agent (Tier 4)                                           │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              WISDOM EXTRACTION                           │    │
│  │  - Analyze trait combinations that led to success        │    │
│  │  - Extract pattern preferences and weights               │    │
│  │  - Identify regime-specific behaviors                    │    │
│  │  - Generate WHEN-DO-BECAUSE rules                        │    │
│  └───────────────────────────┬─────────────────────────────┘    │
│                              │                                   │
│       ┌──────────────────────┼──────────────────────┐           │
│       ▼                      ▼                      ▼           │
│  ┌─────────┐          ┌─────────────┐        ┌───────────┐      │
│  │ CLONE   │          │   WISDOM    │        │  RETIRE   │      │
│  │ (Spawn  │          │   STORE     │        │  (Soft    │      │
│  │ children)│          │  (Database) │        │  Delete)  │      │
│  └─────────┘          └─────────────┘        └───────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Wisdom Extraction

### WHEN-DO-BECAUSE Format

Extracted wisdom is stored as structured rules:

```python
class WisdomRule:
    """A single piece of extracted wisdom."""

    when: str        # Market condition
    do: str          # Action to take
    because: str     # Reasoning/evidence
    confidence: float  # 0-1 based on sample size
    source_agent: str  # Agent ID that generated this
    regime: str      # bull, bear, chop, flat
```

### Example Wisdom Rules

```json
{
  "rules": [
    {
      "when": "RSI < 30 AND price > SMA_20 AND regime = 'bull'",
      "do": "Enter long with 0.8x position size",
      "because": "Oversold bounce in uptrend has 73% win rate over 156 trades",
      "confidence": 0.85,
      "source_agent": "Stable_Patient_Steel_G1",
      "regime": "bull"
    },
    {
      "when": "Holding duration > 4 hours AND PnL > 5%",
      "do": "Trail stop to 2% below current price",
      "because": "Prevents giving back gains; improved Calmar by 0.4 in backtests",
      "confidence": 0.72,
      "source_agent": "Social_Bold_Beacon_G6",
      "regime": "all"
    }
  ]
}
```

---

## Clone-and-Retire Process

### Step 1: Identify Elite Agents

Agents qualify for Crucible when:
- Tier 4 (top 20%) for 5+ consecutive backtests
- Fitness score > 60
- Alpha > 10% (beats buy-hold significantly)
- Backtest count > 30 (sufficient sample)

```python
async def identify_crucible_candidates(session) -> List[Agent]:
    """Find agents ready for wisdom extraction."""
    return await session.exec(
        select(Agent)
        .where(Agent.status == "active")
        .where(Agent.level == 4)
        .where(Agent.fitness_score > 60)
        .where(Agent.alpha > 0.10)
        .where(Agent.backtest_count > 30)
    ).all()
```

### Step 2: Extract Wisdom

Analyze the agent's trading history to extract patterns:

```python
async def extract_wisdom(agent: Agent, trades: List[Trade]) -> List[WisdomRule]:
    """
    Extract actionable wisdom from elite agent's trade history.

    Analyzes:
    - Entry conditions that led to winners
    - Exit timing patterns
    - Regime-specific behavior
    - Position sizing effectiveness
    """
    rules = []

    # Group trades by outcome
    winners = [t for t in trades if t.pnl_pct > 0]
    losers = [t for t in trades if t.pnl_pct < 0]

    # Analyze winning patterns
    for regime in ['bull', 'bear', 'chop', 'flat']:
        regime_winners = [t for t in winners if t.regime == regime]
        if len(regime_winners) > 10:
            rule = analyze_winning_conditions(regime_winners, regime)
            rules.append(rule)

    # Analyze exit timing
    holding_analysis = analyze_holding_patterns(winners, losers)
    rules.extend(holding_analysis)

    return rules
```

### Step 3: Clone Children

Create offspring with the elite agent's DNA:

```python
async def clone_elite(agent: Agent, mutation_rate: float = 0.05) -> List[Agent]:
    """
    Create 2-3 children from elite agent with minor mutations.

    Children inherit:
    - Base traits (with small mutations)
    - Pattern weights
    - Trading philosophy seed
    """
    children = []

    for i in range(random.randint(2, 3)):
        child = Agent(
            agent_id=generate_id(),
            generation=agent.generation + 1,
            parent_a_id=agent.agent_id,
            parent_b_id=None,  # Asexual reproduction for elites
            traits=mutate_traits(agent.traits, mutation_rate),
            pattern_weights=agent.pattern_weights.copy(),
            status="active"
        )
        children.append(child)

    return children
```

### Step 4: Retire Elite

Soft-delete the original agent:

```python
async def retire_elite(session, agent: Agent, wisdom_rules: List[WisdomRule]) -> None:
    """
    Retire elite agent after extracting wisdom.

    - Mark as 'retired' (not 'culled' - honorable discharge)
    - Store final statistics
    - Link to wisdom rules
    """
    agent.status = "retired"
    agent.retirement_reason = "crucible_graduation"
    agent.wisdom_rule_count = len(wisdom_rules)

    await session.commit()
```

---

## Wisdom Storage

### Database Schema

```sql
CREATE TABLE wisdom_rules (
    id SERIAL PRIMARY KEY,
    source_agent_id VARCHAR(64) REFERENCES agents(agent_id),
    when_condition TEXT NOT NULL,
    do_action TEXT NOT NULL,
    because_reasoning TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    regime VARCHAR(10),  -- bull, bear, chop, flat, all
    sample_size INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_wisdom_regime ON wisdom_rules(regime);
CREATE INDEX idx_wisdom_confidence ON wisdom_rules(confidence DESC);
```

---

## Grand Challenge (Future)

The Crucible connects to a planned "Grand Challenge" system:

```
┌─────────────────────────────────────────────────────────────────┐
│                      GRAND CHALLENGE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Elite agents compete in special high-stakes backtests:         │
│                                                                  │
│  1. Extended historical periods (full 5-year history)           │
│  2. Multiple asset classes simultaneously                       │
│  3. Increased difficulty (tighter slippage, higher fees)        │
│  4. Head-to-head format with ELO-style ranking                  │
│                                                                  │
│  Winners get:                                                    │
│  - Wisdom extraction with higher confidence                      │
│  - More children (3-5 clones)                                   │
│  - Traits preserved in "Hall of Fame"                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Status and Roadmap

| Component | Status | Notes |
|-----------|--------|-------|
| Wisdom rule schema | 🔄 Partial | Model exists, not fully wired |
| Extraction logic | ❌ Planned | Needs trade analysis functions |
| Clone mechanism | ✅ Working | Uses spawn_service |
| Retirement flow | ✅ Working | Soft delete with reason |
| Grand Challenge | ❌ Planned | Not implemented |
| Wisdom application | ❌ Planned | How new agents use wisdom |

---

*Last Updated: 2026-01-13*
