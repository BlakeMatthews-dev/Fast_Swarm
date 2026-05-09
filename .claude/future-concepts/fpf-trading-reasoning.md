# FPF Trading Reasoning Engine: Concept Document

**Status:** Future Implementation
**Priority:** High - Core to Agent Intelligence
**Source Repository:** https://github.com/m0n0x41d/quint-code
**Saved:** 2025-12-21

---

## Executive Summary

Apply the **First Principles Framework (FPF)** methodology from quint-code to trading decisions, creating a structured reasoning → outcome → memory → reinforcement learning loop.

**Core Insight:** Every trade is a hypothesis. The outcome is evidence. Over time, the agent learns *which reasoning patterns lead to correct decisions* - not just which trades win.

---

## The Concept

### Traditional Trading Agent
```
Signal → Decision → Outcome → Update weights
         (black box)
```

### FPF Trading Agent
```
Signal → Hypotheses → Evidence → Reasoning → Decision → Outcome
                                    ↓                       ↓
                              STORED AS               VALIDATES OR
                              RATIONALE               INVALIDATES
                                    ↓                       ↓
                              MEMORY TIER ←←←←←←←←←←←←←←←←←←
                                    ↓
                              INFORMS FUTURE REASONING
                                    ↓
                              REINFORCEMENT LEARNING
```

**The key difference:** We don't just learn "BUY worked" - we learn "*why* BUY worked" and whether our reasoning was sound.

---

## Mapping FPF to Trading

### Knowledge Layers → Confidence Tiers

| FPF Layer | Trading Equivalent | Example |
|-----------|-------------------|---------|
| **L0** (Unverified) | Signal detected, no confirmation | "RSI crossed 30" |
| **L1** (Logically verified) | Multiple indicators align | "RSI + MACD + Volume confirm" |
| **L2** (Empirically verified) | Pattern has historical edge | "This setup won 67% over 500 trades" |
| **Invalid** | Disproven hypothesis | "Thought it was reversal, was dead cat bounce" |

### Evidence Types for Trading

```python
class TradingEvidence:
    # Internal evidence (from our system)
    BACKTEST = "backtest"           # Historical pattern performance
    LIVE_TRADE = "live_trade"       # Actual trade outcome
    PAPER_TRADE = "paper_trade"     # Simulated execution

    # External evidence (from outside)
    MARKET_STRUCTURE = "market"     # Macro conditions matched
    SENTIMENT = "sentiment"         # Social/news aligned
    FUNDAMENTAL = "fundamental"     # On-chain/earnings data

    # Meta evidence (about our reasoning)
    REASONING_VALIDATED = "reasoning_validated"  # Our logic was correct
    REASONING_FLAWED = "reasoning_flawed"        # Right outcome, wrong reason
```

### The Critical Distinction: Outcome vs Reasoning Quality

```
SCENARIO 1: Right decision, right reasoning
├── Trade: BUY BTC at $40k
├── Reasoning: "Accumulation pattern + whale inflows + sentiment shift"
├── Outcome: +15%
└── Learning: REINFORCE this reasoning pattern (high weight)

SCENARIO 2: Right decision, WRONG reasoning
├── Trade: BUY BTC at $40k
├── Reasoning: "RSI oversold bounce play"
├── Outcome: +15% (but it was actually macro-driven rally)
└── Learning: WEAK reinforcement - got lucky, reasoning was incomplete

SCENARIO 3: Wrong decision, right reasoning
├── Trade: SHORT BTC at $40k
├── Reasoning: "Distribution pattern, whale outflows, sentiment peak"
├── Outcome: -10% (unexpected ETF approval)
└── Learning: Reasoning was VALID, outcome was exogenous shock
              Don't punish the reasoning - flag as "black swan override"

SCENARIO 4: Wrong decision, wrong reasoning
├── Trade: BUY SHITCOIN
├── Reasoning: "Number go up"
├── Outcome: -80%
└── Learning: INVALIDATE this reasoning pattern completely
```

**This is the core insight:** We're not doing RL on outcomes alone. We're doing RL on *reasoning quality*, using outcomes as a validation signal.

---

## The Memory Integration

### Mapping to Coinswarm's 3-Tier Memory

```
┌─────────────────────────────────────────────────────────────────┐
│                         WISDOM TIER                              │
│   "WHEN-DO-BECAUSE" rules derived from validated reasoning      │
│                                                                  │
│   Example:                                                       │
│   WHEN: RSI < 25 AND volume_spike > 3x AND whale_accumulation   │
│   DO: Enter long with 2% position                                │
│   BECAUSE: This reasoning pattern validated in 47/52 instances  │
│   CONFIDENCE: 0.89 (from FPF reliability score)                 │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                    Promoted every 50 trades
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│                        SEMANTIC TIER                             │
│   Aggregated statistics about reasoning patterns                │
│                                                                  │
│   "accumulation_reversal_reasoning": {                          │
│       "times_used": 52,                                         │
│       "outcomes": {"win": 47, "loss": 5},                       │
│       "reasoning_validated": 44,  // Right for right reasons    │
│       "reasoning_lucky": 3,       // Right for wrong reasons    │
│       "avg_confidence_at_entry": 0.72,                          │
│       "confidence_vs_outcome_correlation": 0.81                 │
│   }                                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                    Aggregated every 50 trades
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│                        EPISODIC TIER                             │
│   Individual trade decisions with full reasoning chain          │
│                                                                  │
│   {                                                              │
│       "trade_id": "abc123",                                     │
│       "timestamp": "2025-01-15T14:30:00Z",                      │
│       "decision": "BUY",                                        │
│       "hypotheses_considered": [                                │
│           {"id": "h1", "title": "Accumulation reversal", ...},  │
│           {"id": "h2", "title": "Dead cat bounce", ...}         │
│       ],                                                         │
│       "chosen_hypothesis": "h1",                                │
│       "confidence_at_entry": 0.75,                              │
│       "reasoning_chain": [...],                                 │
│       "outcome": "+12.5%",                                      │
│       "reasoning_validated": true,                              │
│       "post_hoc_analysis": "Whale data confirmed accumulation"  │
│   }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Reinforcement Learning Loop

### What We're Actually Learning

Traditional RL: `state → action → reward → update policy`

FPF-Enhanced RL:
```
state → hypotheses → reasoning → action → outcome → reasoning_validation
                         ↓                               ↓
                    stored as                    validates/invalidates
                    rationale                    the reasoning
                         ↓                               ↓
                    ┌────────────────────────────────────┘
                    ↓
              UPDATE REASONING POLICY (not just action policy)
```

### Reward Shaping for Reasoning Quality

```python
def calculate_reasoning_reward(trade_result):
    """
    Reward structure that values correct reasoning over lucky outcomes.
    """
    outcome_reward = trade_result.pnl_normalized  # -1 to +1

    # Did our reasoning hold up?
    if trade_result.reasoning_validated:
        reasoning_bonus = 0.3
    elif trade_result.reasoning_partially_valid:
        reasoning_bonus = 0.1
    else:
        reasoning_bonus = -0.2  # Penalize even winning trades with bad reasoning

    # Confidence calibration reward
    # Were we appropriately confident given the outcome?
    confidence_error = abs(trade_result.entry_confidence - trade_result.actual_edge)
    calibration_reward = 1.0 - confidence_error  # Reward well-calibrated confidence

    # Combine with weights
    total_reward = (
        0.4 * outcome_reward +      # Outcomes still matter
        0.4 * reasoning_bonus +     # But reasoning matters equally
        0.2 * calibration_reward    # And knowing what you don't know
    )

    return total_reward
```

### The Meta-Learning Layer

Over time, the agent learns:

1. **Which reasoning patterns are reliable**
   - "Accumulation + whale inflows" → 85% reasoning accuracy
   - "RSI oversold alone" → 45% reasoning accuracy (often lucky)

2. **When to trust its own confidence**
   - "When I'm 90% confident, I'm actually right 87% of the time"
   - "When I'm 60% confident, I'm actually right 52% of the time"

3. **Which evidence types are most predictive**
   - "On-chain evidence validates reasoning 3x better than sentiment"
   - "Backtest evidence decays after 30 days in volatile markets"

4. **How to improve reasoning over time**
   - "Adding volume confirmation improves reasoning accuracy by 15%"
   - "Considering macro context reduces false positives by 22%"

---

## Implementation Sketch

### Phase 1: Structured Trade Decisions

```python
class TradingFPFEngine:
    """
    FPF-based trading decision engine.
    Every trade is a hypothesis that gets validated.
    """

    def __init__(self, agent_id: str, memory_store: AgentMemoryDO):
        self.agent_id = agent_id
        self.memory = memory_store
        self.active_hypotheses = {}
        self.decision_history = []

    def analyze_opportunity(self, market_state: MarketState) -> list[TradeHypothesis]:
        """
        Phase 1: ABDUCTION - Generate competing trade hypotheses.
        """
        hypotheses = []

        # Generate multiple interpretations of the same market state
        h1 = TradeHypothesis(
            action="BUY",
            reasoning="Accumulation pattern detected",
            assumptions=["Whales are accumulating", "Support will hold"],
            evidence_required=["volume_confirmation", "whale_flow_data"],
            confidence=0.0  # Will be calculated after evidence
        )

        h2 = TradeHypothesis(
            action="WAIT",
            reasoning="Unclear setup, could be distribution",
            assumptions=["Market is ranging", "No clear edge"],
            evidence_required=["trend_confirmation"],
            confidence=0.0
        )

        h3 = TradeHypothesis(
            action="SHORT",
            reasoning="Distribution pattern, lower highs",
            assumptions=["Smart money exiting", "Resistance will hold"],
            evidence_required=["whale_outflow", "sentiment_peak"],
            confidence=0.0
        )

        return [h1, h2, h3]

    def gather_evidence(self, hypothesis: TradeHypothesis, market_data: dict) -> float:
        """
        Phase 2-3: DEDUCTION + INDUCTION - Verify and gather evidence.
        """
        evidence_scores = []

        for required in hypothesis.evidence_required:
            evidence = self.fetch_evidence(required, market_data)
            if evidence:
                # Check congruence - does this evidence actually apply to our context?
                congruence = self.assess_congruence(evidence, market_data)

                # Check decay - is this evidence still fresh?
                decay_penalty = evidence.decay_penalty()

                score = evidence.base_score * congruence * (1 - decay_penalty)
                evidence_scores.append(score)
                hypothesis.evidence.append(evidence)

        # Weakest link principle
        hypothesis.confidence = min(evidence_scores) if evidence_scores else 0.0
        return hypothesis.confidence

    def decide(self, hypotheses: list[TradeHypothesis]) -> TradeDecision:
        """
        Phase 4-5: AUDIT + DECIDE - Pick the best hypothesis.
        """
        # Score all hypotheses
        scored = [(h, h.confidence) for h in hypotheses]
        scored.sort(key=lambda x: x[1], reverse=True)

        winner = scored[0][0]
        alternatives = [h for h, _ in scored[1:]]

        decision = TradeDecision(
            chosen=winner,
            alternatives=alternatives,
            rationale=self.generate_rationale(winner, alternatives),
            timestamp=datetime.now()
        )

        # Store in episodic memory
        self.memory.store_episodic(decision)

        return decision

    def record_outcome(self, decision: TradeDecision, outcome: TradeOutcome):
        """
        Critical: Validate the REASONING, not just the outcome.
        """
        # Did the trade win or lose?
        outcome_success = outcome.pnl > 0

        # But more importantly: was our reasoning correct?
        reasoning_validation = self.validate_reasoning(
            decision.chosen,
            outcome.post_trade_market_state
        )

        # Create learning record
        learning = LearningRecord(
            decision=decision,
            outcome=outcome,
            outcome_success=outcome_success,
            reasoning_validated=reasoning_validation.is_valid,
            reasoning_notes=reasoning_validation.notes,
            learning_type=self.categorize_learning(outcome_success, reasoning_validation)
        )

        # Update memory tiers
        self.memory.update_episodic(decision.id, learning)
        self.memory.maybe_promote_to_semantic()  # Every 50 trades
        self.memory.maybe_crystallize_wisdom()   # On significant patterns

        # RL reward signal
        reward = self.calculate_reasoning_reward(learning)
        self.update_policy(decision.chosen.reasoning_pattern, reward)

    def categorize_learning(self, outcome_success: bool, reasoning: ReasoningValidation) -> str:
        """Categorize the learning for appropriate weight updates."""
        if outcome_success and reasoning.is_valid:
            return "REINFORCE_STRONG"      # Right decision, right reasoning
        elif outcome_success and not reasoning.is_valid:
            return "REINFORCE_WEAK"        # Right decision, lucky/wrong reasoning
        elif not outcome_success and reasoning.is_valid:
            return "EXOGENOUS_SHOCK"       # Wrong outcome, but reasoning was sound
        else:
            return "INVALIDATE"            # Wrong decision, wrong reasoning
```

### Phase 2: Semantic Aggregation

```python
class ReasoningPatternAggregator:
    """
    Aggregates episodic trade decisions into semantic knowledge
    about which reasoning patterns actually work.
    """

    def aggregate_pattern(self, pattern_id: str, episodes: list[LearningRecord]) -> SemanticKnowledge:
        """
        Called every 50 trades or on significant events.
        """
        stats = {
            "pattern_id": pattern_id,
            "total_uses": len(episodes),
            "outcomes": {
                "win": sum(1 for e in episodes if e.outcome_success),
                "loss": sum(1 for e in episodes if not e.outcome_success)
            },
            "reasoning_quality": {
                "validated": sum(1 for e in episodes if e.reasoning_validated),
                "lucky": sum(1 for e in episodes if e.outcome_success and not e.reasoning_validated),
                "unlucky": sum(1 for e in episodes if not e.outcome_success and e.reasoning_validated),
                "flawed": sum(1 for e in episodes if not e.outcome_success and not e.reasoning_validated)
            },
            "confidence_calibration": self.calculate_calibration(episodes),
            "best_conditions": self.extract_best_conditions(episodes),
            "failure_modes": self.extract_failure_modes(episodes)
        }

        # Calculate reliability score (FPF style)
        reliability = self.calculate_pattern_reliability(stats)

        return SemanticKnowledge(
            pattern_id=pattern_id,
            stats=stats,
            reliability=reliability,
            last_updated=datetime.now()
        )
```

### Phase 3: Wisdom Crystallization

```python
class WisdomCrystallizer:
    """
    Promotes reliable semantic patterns to WHEN-DO-BECAUSE rules.
    """

    def maybe_crystallize(self, semantic: SemanticKnowledge) -> Optional[WisdomRule]:
        """
        If a pattern is reliable enough, crystallize it into a rule.
        """
        if semantic.reliability < 0.7:
            return None  # Not reliable enough yet

        if semantic.stats["total_uses"] < 30:
            return None  # Not enough data

        # Extract the conditions that led to success
        conditions = self.extract_winning_conditions(semantic)

        rule = WisdomRule(
            when=conditions,
            do=semantic.pattern_id,
            because=f"Validated in {semantic.stats['reasoning_quality']['validated']}/{semantic.stats['total_uses']} instances with {semantic.reliability:.0%} reliability",
            confidence=semantic.reliability,
            valid_until=datetime.now() + timedelta(days=90),  # Rules decay too
            contraindications=semantic.stats["failure_modes"]
        )

        return rule
```

### Phase 4: RL Policy Updates

```python
class ReasoningRL:
    """
    Reinforcement learning on reasoning patterns, not just actions.
    """

    def update_policy(self, pattern_id: str, reward: float, learning_type: str):
        """
        Update the policy based on reasoning quality, not just outcome.
        """
        # Get current pattern weights
        weights = self.policy.get_pattern_weights(pattern_id)

        # Adjust learning rate based on learning type
        lr_multipliers = {
            "REINFORCE_STRONG": 1.0,    # Full learning rate
            "REINFORCE_WEAK": 0.3,      # Reduced - we got lucky
            "EXOGENOUS_SHOCK": 0.1,     # Minimal - not our fault
            "INVALIDATE": 1.5           # Increased - learn from mistakes
        }

        effective_lr = self.base_lr * lr_multipliers[learning_type]

        # Update weights
        new_weights = weights + effective_lr * reward * self.get_gradient(pattern_id)
        self.policy.set_pattern_weights(pattern_id, new_weights)

        # Also update confidence calibration
        self.update_calibration_model(pattern_id, reward)
```

---

## Evidence Decay for Trading

### Time-Based Decay

```python
DECAY_RATES = {
    "backtest_crypto_volatile": 14,    # Days until 50% reliability
    "backtest_crypto_stable": 30,
    "backtest_tradfi": 90,
    "live_trade": 7,                   # Recent trades decay fast in changing markets
    "on_chain_data": 3,                # On-chain is very time-sensitive
    "sentiment": 1,                    # Sentiment changes hourly
    "fundamental": 30,                 # Fundamentals change slowly
    "macro": 60,                       # Macro regimes persist
}

def calculate_evidence_reliability(evidence: Evidence, current_time: datetime) -> float:
    """
    Evidence reliability decays exponentially.
    """
    age_days = (current_time - evidence.timestamp).days
    half_life = DECAY_RATES.get(evidence.type, 30)

    reliability = evidence.base_reliability * (0.5 ** (age_days / half_life))
    return max(0.1, reliability)  # Floor at 10%
```

### Market Regime Decay

```python
def apply_regime_decay(evidence: Evidence, current_regime: str) -> float:
    """
    Evidence from different market regimes is less relevant.
    """
    if evidence.market_regime == current_regime:
        return 1.0  # Full relevance

    # Cross-regime penalties
    penalties = {
        ("bull", "bear"): 0.3,
        ("bull", "crab"): 0.6,
        ("bear", "crab"): 0.6,
        ("high_vol", "low_vol"): 0.4,
    }

    key = (evidence.market_regime, current_regime)
    return penalties.get(key, penalties.get((key[1], key[0]), 0.5))
```

---

## Congruence Levels for Trading

How well does external evidence match our specific trading context?

| CL | Description | Example | Penalty |
|----|-------------|---------|---------|
| **3** | Exact match | Backtest on same asset, same timeframe, same conditions | 0% |
| **2** | Similar | Backtest on correlated asset or slightly different timeframe | 10% |
| **1** | Analogous | Academic paper about similar pattern in different market | 40% |
| **0** | Weak | General trading wisdom, untested assumptions | 90% |

```python
def assess_congruence(evidence: Evidence, current_context: TradingContext) -> int:
    """
    How well does this evidence apply to our current situation?
    """
    score = 3  # Start at max

    # Asset match
    if evidence.asset != current_context.asset:
        if is_correlated(evidence.asset, current_context.asset):
            score -= 1
        else:
            score -= 2

    # Timeframe match
    if evidence.timeframe != current_context.timeframe:
        score -= 1

    # Regime match
    if evidence.market_regime != current_context.market_regime:
        score -= 1

    # Recency
    if evidence.age_days > 30:
        score -= 1

    return max(0, score)
```

---

## Integration with Coinswarm Architecture

### Where This Lives

```
Coinswarm/
├── v3/cloudflare-agents/
│   ├── agents/
│   │   └── trading-reasoning-do.ts    # NEW: FPF reasoning engine
│   └── memory/
│       └── agent-memory-do.ts         # Existing: Add reasoning storage
│
├── local-utilities/
│   └── fpf_engine.py                  # Python implementation for dev decisions
│
└── .claude/
    └── future-concepts/
        └── fpf-trading-reasoning.md   # THIS DOCUMENT
```

### Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                         TRADING SIGNAL                                │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    TRADING REASONING DO                               │
│  1. Generate hypotheses (BUY/SELL/WAIT with reasoning)               │
│  2. Gather evidence (backtest, on-chain, sentiment)                  │
│  3. Calculate confidence (weakest-link principle)                    │
│  4. Make decision with full rationale                                │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      TRADE EXECUTION                                  │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
                            [TIME PASSES]
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      OUTCOME RECORDING                                │
│  1. Record PnL                                                        │
│  2. Validate reasoning against actual market behavior                │
│  3. Categorize learning (REINFORCE/INVALIDATE/etc)                   │
│  4. Update memory tiers                                              │
│  5. Send reward signal to RL                                         │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      AGENT MEMORY DO                                  │
│  Episodic → Semantic → Wisdom                                        │
│  (Enhanced with reasoning quality tracking)                          │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      RL POLICY UPDATE                                 │
│  Update reasoning pattern weights based on validated outcomes        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Why This Matters

### Traditional Trading Bot Problem

Most trading bots learn:
- "BUY when RSI < 30" → sometimes works
- No understanding of *why* it works
- Can't adapt when market regime changes
- Overfits to historical patterns

### FPF Trading Agent Advantage

FPF-enhanced agents learn:
- "BUY when RSI < 30 AND volume confirms AND whales accumulating"
- *Why* each component matters
- Which reasoning was actually predictive
- When their reasoning is likely to fail

**The agent develops genuine trading intuition backed by auditable evidence.**

### The RL Breakthrough

Instead of:
```
reward = profit_or_loss
```

We use:
```
reward = (
    profit_weight * outcome +
    reasoning_weight * reasoning_validation +
    calibration_weight * confidence_accuracy
)
```

This means the agent:
1. Still cares about making money
2. But ALSO cares about understanding *why*
3. And learns to know what it doesn't know

---

## Open Questions

1. **How to validate reasoning post-hoc?**
   - Compare predicted market behavior vs actual
   - Check if assumed conditions held
   - Need clear, testable assumptions

2. **How to handle conflicting evidence?**
   - Weakest-link is conservative
   - Maybe weighted average for some cases?

3. **How to bootstrap?**
   - Cold start problem
   - Use backtests as initial evidence
   - Gradually shift to live validation

4. **How to prevent gaming?**
   - Agent might construct reasoning to match outcomes
   - Need independent reasoning validation

5. **Computational cost?**
   - Generating multiple hypotheses per trade is expensive
   - Can we use Workers AI for fast hypothesis scoring?

---

## References

- **quint-code repository:** https://github.com/m0n0x41d/quint-code
- **FPF Methodology:** By Anatoly Levenchuk
- **Coinswarm Memory Tiers:** `.claude/Master_plan.md`

---

*This document captures the concept for future implementation. Next step: Build Python prototype in local-utilities/ for testing before Workers integration.*
