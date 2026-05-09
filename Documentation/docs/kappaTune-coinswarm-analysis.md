# kappaTune ↔ Coinswarm: Comprehensive Analysis

## Executive Summary

**kappaTune** is a PyTorch optimizer wrapper that uses **condition number (κ) analysis** to selectively fine-tune neural network parameters, preventing catastrophic forgetting during continual learning.

**Core insight**: The condition number of a weight matrix reveals how "specialized" that neural unit has become:
- **High κ** = Anisotropic singular values = Specialized for learned task = **FREEZE**
- **Low κ** = Uniform singular values = General-purpose = **SAFE TO UPDATE**

This document analyzes how this principle applies to Coinswarm at two levels:
1. **Conceptual Level**: Parallels across all system components
2. **Fine-tuning Level**: Specific applications when training/adapting LLMs

---

## Part 1: Conceptual Analysis

### 1.1 The κ Principle in Abstract

Before diving into specifics, let's formalize what kappaTune teaches us:

```
κ(W) = σ_max / σ_min   (ratio of largest to smallest singular value)

High κ means:
- Matrix has learned to AMPLIFY certain input directions
- Matrix has learned to SUPPRESS other input directions
- This specialization encodes task-specific knowledge
- Updating it risks destroying learned discriminative features

Low κ means:
- Matrix treats all input directions similarly
- Less task-specific encoding
- More "general purpose" transformation
- Safe to update for new tasks
```

**The meta-principle**: In any learning system, identify what has become specialized through training, and protect it while adapting the generalizable components.

---

### 1.2 Agent Traits (22 Traits)

#### Current System
```typescript
// spawning/types.ts - 22 traits total
interface AgentTraits {
  // 14 INDEPENDENT traits (mutate directly)
  risk_tolerance, hold_duration_bias, volatility_seeking, profit_target_greed,
  win_rate_preference, momentum_vs_reversion, entry_aggression, lookback_preference,
  sentiment_weight, news_reactivity, sentiment_contrarian,
  funding_rate_sensitivity, correlation_awareness, uncertainty_anchor,
  memory_condensation, inheritance_decay

  // 3 DERIVED traits (from anchors)
  drawdown_sensitivity ≈ 1 - risk_tolerance
  stop_loss_tightness ≈ 1 - risk_tolerance
  exit_aggression ≈ 1 - hold_duration_bias

  // 3 THRESHOLD traits (from uncertainty_anchor)
  ai_assist_range, min_threshold, ai_threshold
}
```

#### κ Parallel

| Trait Characteristic | Neural Network Equivalent | κ Interpretation |
|---------------------|---------------------------|------------------|
| Trait with LOW variance across top agents | Layer that converged during training | High κ = specialized |
| Trait with HIGH variance across top agents | Layer still being optimized | Low κ = generalizable |
| Derived traits (coupled to anchors) | Residual connections | Inherit κ from source |
| Threshold traits | Activation function parameters | Task-specific = high κ |

#### Proposed Enhancement: Trait Condition Number

```typescript
interface TraitConditionAnalysis {
  trait: keyof AgentTraits;

  // Calculated from top-performing agents
  meanValueInElite: number;      // What value do winners converge to?
  varianceInElite: number;       // How much do winners vary?
  fitnessCorrelation: number;    // Pearson r with fitness score

  // The "condition number" analog
  specialization: number;        // 0 = unexplored, 1 = converged

  // Derived mutation rate
  mutationRate: number;          // Lower for specialized traits
}

// Example calculations:
// If top 20% of agents all have risk_tolerance ≈ 0.3 (±0.05)
//   → Low variance → High specialization → Low mutation rate
// If top 20% of agents have sentiment_weight spread from 0.1 to 0.9
//   → High variance → Low specialization → Normal mutation rate
```

#### Why This Matters

Current system uses **uniform 10% mutation** for all independent traits:

```typescript
// trait-mutation.ts:119
export function mutateTrait(original: number, mutationRate: number, seed: number): number {
  const delta = (randomValue * 2 - 1) * mutationRate;  // Always ±10%
  return Math.max(0, Math.min(1, original + delta));
}
```

This is like fine-tuning ALL neural network layers equally - it works, but:
- **Wastes exploration budget** on already-optimized traits
- **Risks destroying** converged optimal values
- **Slows convergence** by re-exploring solved dimensions

---

### 1.3 Pattern Evolution

#### Current System

```
Tier 3 (Untested) → Tier 2 (Proven) → Tier 1 (Elite) → Agent Assignment

Fitness Components:
- Alpha: ±40 pts (outperformance vs buy-and-hold)
- Sortino: ±14 pts (downside risk-adjusted)
- Calmar: ±11 pts (return vs max drawdown)
- Expectancy: 0-30 pts (expected value per trade)
- Drawdown: 0-5 pts (bonus for low drawdown)

Pruning: LOG-SD threshold (1.5 SD in log space)
```

#### κ Parallel

| Pattern Characteristic | Neural Network Equivalent | κ Interpretation |
|-----------------------|---------------------------|------------------|
| Pattern with consistent fitness across backtests | Layer with stable gradients | Low κ = reliable |
| Pattern with high fitness variance | Layer with unstable gradients | High κ = overfitted? |
| Pattern that works across assets | General feature extractor | Low κ = generalizable |
| Pattern specific to BTC only | Task-specific head | High κ = specialized |

#### The Variance Paradox

Here's where kappaTune's insight gets nuanced. In neural networks:
- High κ = specialized = **GOOD** (learned something useful)

But in pattern evolution, high variance could mean:
- Pattern is **overfitted** to specific conditions (bad)
- Pattern captures **regime-specific** alpha (good)

**Resolution**: We need TWO κ-like metrics:

```typescript
interface PatternStabilityAnalysis {
  pattern_id: string;

  // Metric 1: Cross-temporal stability (like κ for generalization)
  temporalVariance: number;      // Fitness variance across time periods
  temporalκ: number;             // Low = stable across time = generalizable

  // Metric 2: Cross-asset stability
  assetVariance: number;         // Fitness variance across assets
  assetκ: number;                // Low = works on many assets = generalizable

  // Metric 3: Regime stability
  regimeVariance: number;        // Fitness variance across market regimes
  regimeκ: number;               // High might be OK if regime-specific

  // Combined interpretation
  isGeneralPattern: boolean;     // Low temporal + low asset κ
  isRegimeSpecialist: boolean;   // Low temporal + high regime κ
  isOverfitted: boolean;         // High temporal κ (unstable)
}
```

---

### 1.4 Memory System

#### Current System

```typescript
// agent-memory-do.ts
type MemoryType = 'episodic' | 'pattern' | 'regime' | 'behavioral';

interface MemoryRecord {
  memory_id: string;
  memory_type: MemoryType;
  content: string;
  relevance_score: number;    // 0-1, influences recall + prune resistance
  expires_at: number | null;  // TTL for episodic
  accessed_count: number;     // Frequency-based importance
}
```

#### κ Parallel

This is perhaps the **strongest parallel** to kappaTune:

| Memory Tier | Neural Network Equivalent | κ Interpretation |
|-------------|---------------------------|------------------|
| **Episodic** (7-day TTL, specific events) | Recent fine-tuning updates | Low κ = recent, updateable |
| **Pattern** (learned pattern behaviors) | Mid-layer representations | Medium κ |
| **Regime** (market regime observations) | Context encodings | Task-specific κ |
| **Behavioral** (agent decision tendencies) | Output layer biases | High κ = personality |
| **Wisdom** (philosophical principles) | Pre-trained foundation | Highest κ = FREEZE |

#### The Memory Consolidation Parallel

kappaTune's key insight: **Don't update what you've learned to rely on.**

Coinswarm's memory flow:
```
TRADE → EPISODIC → SEMANTIC (every 50 trades) → WISDOM (on triggers)
```

This is analogous to:
```
FINE-TUNE → SHORT-TERM WEIGHTS → CONSOLIDATED WEIGHTS → FROZEN FOUNDATION
```

#### Proposed Enhancement: κ-Guided Memory Updates

```typescript
function updateMemoryWithKappaProtection(
  memory: MemoryRecord,
  newEvidence: Evidence,
  memoryκ: number  // Calculated from access patterns + reinforcement
): MemoryRecord {

  // High κ (frequently accessed, often reinforced) = protect
  const updateRate = 1 / (1 + memoryκ);

  // Wisdom memories have artificially inflated κ
  const effectiveκ = memory.memory_type === 'wisdom'
    ? memoryκ * 10
    : memoryκ;

  // Blend old and new based on κ
  const newRelevance = memory.relevance_score * (1 - updateRate)
                     + computeNewRelevance(newEvidence) * updateRate;

  return { ...memory, relevance_score: newRelevance };
}
```

---

### 1.5 Evolution Phases

#### Current System

```
Phase 1: CHAOS     - Generate random trades from real OHLCV
Phase 2: DISCOVERY - AI analyzes winners/losers for patterns
Phase 3: BACKTEST  - Test discovered patterns on historical data
Phase 4: SELECTION - Promote top 20%, retire bottom 30%
```

#### κ Parallel

| Evolution Phase | Training Equivalent | κ Role |
|-----------------|--------------------| -------|
| **CHAOS** | Random weight initialization | All κ ≈ 1 (isotropic) |
| **DISCOVERY** | Early training (high learning rate) | κ values diverging |
| **BACKTEST** | Validation pass | κ reveals what's learned |
| **SELECTION** | Pruning + architecture search | Use κ to decide what to keep |

#### The Selection Phase as κ-Guided Pruning

Current selection uses percentile-based thresholds:
```typescript
const PROMOTE_PERCENTILE = 80;  // Top 20% promoted
const KEEP_PERCENTILE = 30;     // Bottom 30% retired
```

κ-enhanced selection could consider **stability** not just **fitness**:

```typescript
interface SelectionCriteria {
  fitness: number;           // Current: primary metric
  stabilityκ: number;        // New: how consistent is this pattern?

  // Selection logic:
  // High fitness + Low κ (stable) → PROMOTE (reliable performer)
  // High fitness + High κ (unstable) → KEEP (might be overfitted, monitor)
  // Low fitness + Low κ (stable) → RETIRE (consistently bad)
  // Low fitness + High κ (unstable) → KEEP (might improve, still learning)
}
```

---

### 1.6 Fitness Calculation

#### Current System (V2 Signed Equation)

```typescript
// fitness-calculator.ts
Total = Alpha(±40) + Sortino(±14) + Calmar(±11) + Expectancy(0-30) + Drawdown(0-5)
Range: -65 to +100, clamped to 0-100
```

#### κ Parallel

The signed components are fascinating from a κ perspective:

| Component | Sign Behavior | κ Interpretation |
|-----------|---------------|------------------|
| **Alpha** | Can be -40 to +40 | Measures RELATIVE specialization vs benchmark |
| **Sortino** | Can be -14 to +14 | Penalizes downside specialization |
| **Calmar** | Can be -11 to +11 | Drawdown-adjusted specialization |
| **Expectancy** | 0 to +30 | Absolute quality (not κ-related) |
| **Drawdown** | 0 to +5 | Penalizes over-specialization to risky trades |

**Key insight**: The signed metrics already capture a form of κ analysis!

- **Negative Alpha** = Pattern "specialized" in the wrong direction (worse than benchmark)
- **Negative Sortino** = Pattern "specialized" in taking bad risks
- This is like a layer with high κ that's specialized for the WRONG task

---

### 1.7 Market Regimes

#### Current System

Coinswarm handles multiple market conditions:
- Bull markets (trending up)
- Bear markets (trending down)
- Sideways/ranging
- High volatility
- Low volatility

#### κ Parallel: Continual Learning Across Tasks

This is the **core problem kappaTune solves**:

| Market Scenario | Continual Learning Equivalent |
|-----------------|------------------------------|
| 2021 Bull Run | Task A: "Classify dogs" |
| 2022 Bear Market | Task B: "Classify cats" |
| 2023 Recovery | Task C: "Classify birds" |
| 2024 New Regime | Task D: New domain |

**The catastrophic forgetting problem**:
- Patterns that worked in 2021 might not work in 2022
- But you don't want to FORGET the 2021 patterns entirely
- Because the market WILL return to similar conditions

**κ-guided solution**:

```typescript
interface RegimeAwarePattern {
  pattern_id: string;

  // Performance by regime
  performanceByRegime: Map<MarketRegime, FitnessStats>;

  // κ analysis per regime
  regimeSpecialization: Map<MarketRegime, number>;

  // Cross-regime generalization
  generalκ: number;  // Low = works across regimes

  // Decision logic:
  // If generalκ is LOW → Trust this pattern in new regimes
  // If generalκ is HIGH → Only use in regimes where it's proven
}
```

---

### 1.8 Intelligence Integration

#### Current System

```typescript
// agent-do.ts:680-760
applyIntelligenceBoost(signal, intelligence): AggregatedSignal {
  // Sentiment alignment: +0.1 to +0.2 for Fear & Greed confirmation
  // Contrarian signal: Extreme fear/greed + contrarian trait
  // Macro alignment: +0.05 to +0.1 for Fed regime support
}
```

#### κ Parallel

The intelligence signals (sentiment, macro, news) are **external knowledge** that the agent can incorporate. This is like:

- **Pre-trained knowledge** (what the base model knows about trading)
- **Fine-tuned knowledge** (what the agent learned from backtests)
- **External signals** (real-time market intelligence)

κ can guide how much to trust each:

```typescript
interface IntelligenceWeighting {
  // Agent's trait-based preference (from traits.sentiment_weight)
  traitWeight: number;

  // Historical accuracy of this intelligence source
  historicalAccuracy: number;

  // κ-based trust: High κ = this signal has been reliable
  reliabilityκ: number;

  // Final weight = traitWeight * historicalAccuracy * (1 - 1/(1+reliabilityκ))
  effectiveWeight: number;
}
```

---

### 1.9 Exchange Execution

#### Current System

```
CEX: Coinbase, Kraken, Gemini, Binance US
DEX: Jupiter, Raydium, Orca, PancakeSwap
Perps: Hyperliquid, dYdX, Drift
```

#### κ Parallel: Domain Adaptation

Each exchange is a different "domain" with:
- Different fee structures
- Different liquidity profiles
- Different order types
- Different latency characteristics

An agent optimized for **Hyperliquid** (perps, low fees, high leverage) might fail on **Coinbase** (spot, higher fees, no leverage).

**κ-guided exchange adaptation**:

```typescript
interface ExchangeSpecialization {
  agent_id: string;

  // κ per exchange (how specialized is this agent for each?)
  exchangeκ: Map<Exchange, number>;

  // Strategy:
  // High κ for Hyperliquid + Low κ for others → Specialist
  // Low κ across all exchanges → Generalist
  // High κ for multiple → Multi-specialist (rare, valuable)
}
```

---

### 1.10 The Derived Traits Insight

#### Current System

```typescript
// 3 traits are DERIVED from anchor traits:
drawdown_sensitivity ≈ 1 - risk_tolerance  (±5% noise)
stop_loss_tightness ≈ 1 - risk_tolerance   (±5% noise)
exit_aggression ≈ 1 - hold_duration_bias   (±5% noise)
```

#### κ Parallel: Coupled Layers

This is analogous to **residual connections** or **tied weights** in neural networks:
- Some parameters are NOT independent
- Updating one affects others
- This creates implicit constraints

**κ interpretation**:
- The anchor traits (risk_tolerance, hold_duration_bias) have TRUE κ values
- The derived traits INHERIT their κ from anchors
- Mutating the anchor effectively mutates 3 traits at once

This is actually a **regularization technique** - it reduces the effective parameter count and prevents contradictory trait combinations.

---

## Part 2: Fine-tuning Specific Analysis

Now let's examine how kappaTune applies when Coinswarm uses **actual LLM fine-tuning**.

### 2.1 Where Coinswarm Uses/Will Use LLMs

| Component | LLM Role | Current Status |
|-----------|----------|----------------|
| Pattern Discovery | Analyze trades to find patterns | Active (AI pattern discovery) |
| AI Zone Decisions | Consult LLM for uncertain trades | Active (3-zone system) |
| Agent Philosophy | Generate trading philosophy at spawn | Planned |
| Market Analysis | Interpret news/events | Planned |
| Strategy Generation | Create new pattern hypotheses | Future |

### 2.2 Pattern Discovery LLM

#### Current Implementation

```typescript
// evolution/ai-pattern-discovery.ts
// PatternDiscoveryDO analyzes winning/losing trades to find tag correlations:
// "rsi_oversold + macd_bullish_cross" → 65% win rate (vs 50% baseline)
```

#### Fine-tuning Scenario

You might fine-tune an LLM to:
1. Take raw trade data + indicators
2. Output pattern hypotheses
3. Improve over time as patterns are validated/invalidated

#### κ-Guided Fine-tuning Strategy

```
BASE MODEL (e.g., Llama 3, Claude)
├── Embedding layers (LOW κ, can update for domain vocab)
├── Early transformer blocks (LOW κ, general reasoning)
├── Middle transformer blocks (MEDIUM κ, emerging specialization)
├── Late transformer blocks (HIGH κ, task-specific patterns)
└── Output head (HIGHEST κ, pattern format knowledge)
```

**kappaTune approach**:
1. Compute κ for each layer after initial fine-tuning
2. Freeze layers with κ > threshold (they've learned pattern detection)
3. Continue updating low-κ layers with new trade data
4. Result: Model adapts to new market conditions without forgetting how to detect patterns

#### Concrete Example

```python
# kappaTune-style fine-tuning for pattern discovery
from selective_fine_tuning import SelectiveFineTuningOptimizer

model = load_pretrained_model("trading-pattern-detector")

# First fine-tuning pass: Let all layers learn
optimizer = AdamW(model.parameters(), lr=1e-4)
train(model, optimizer, initial_trade_data)

# Analyze which layers specialized
kappa_scores = analyze_condition_numbers(model)
# Result: Late attention layers have κ > 50 (specialized for pattern formats)
#         Early layers have κ < 10 (general reasoning)

# Subsequent fine-tuning: Protect specialized layers
selective_optimizer = SelectiveFineTuningOptimizer(
    model=model,
    base_optimizer=AdamW,
    top_n_trainable=10,  # Only update 10 lowest-κ layers
)
train(model, selective_optimizer, new_trade_data)
# Result: Model learns new patterns without forgetting old ones
```

---

### 2.3 AI Zone Consultation LLM

#### Current Implementation

```typescript
// agent-do.ts - 3-zone decision system
type DecisionZone = 'NO_TRADE' | 'AI_ZONE' | 'AUTO_ZONE';

// When confidence is between min_threshold and ai_threshold:
// → Consult AI for decision
```

#### Fine-tuning Scenario

You might fine-tune an LLM to:
1. Take market conditions + agent traits + pattern signals
2. Output BUY/SELL/HOLD recommendation
3. Improve based on trade outcomes

#### The Multi-Agent Challenge

Coinswarm has **many agents** with different traits. Fine-tuning options:

| Approach | Pros | Cons |
|----------|------|------|
| One model per agent | Perfect specialization | Expensive, doesn't scale |
| One model, agent conditioning | Efficient | Risk of trait interference |
| Shared base + agent adapters | Balanced | Complexity |

#### κ-Guided Solution: Shared Base + Trait Adapters

```
SHARED BASE MODEL (LOW κ layers)
├── Market understanding
├── Technical indicator interpretation
├── Risk/reward reasoning
│
├── AGENT ADAPTER 1 (HIGH κ, agent-specific)
│   └── Learned: This agent is risk-tolerant, momentum-focused
│
├── AGENT ADAPTER 2 (HIGH κ, agent-specific)
│   └── Learned: This agent is conservative, mean-reverting
│
└── AGENT ADAPTER N...
```

**Training strategy**:
1. Train shared base on all agent data (learns general trading)
2. Freeze shared base (it's now general-purpose, LOW κ maintained)
3. Train agent-specific adapters (they become HIGH κ)
4. Result: Each agent has specialized decision-making without interference

---

### 2.4 Regime Adaptation (The Core kappaTune Use Case)

#### The Problem

```
2023 Q1: Trained on recovery market → Model works well
2024 Q1: Market shifts to new regime → Model performance drops
Options:
  A) Retrain from scratch (expensive, loses 2023 knowledge)
  B) Fine-tune on 2024 data (risks forgetting 2023 patterns)
  C) kappaTune approach (selective update)
```

#### κ-Guided Regime Adaptation

```python
# Analyze what the model learned in 2023
kappa_2023 = analyze_condition_numbers(model)

# Layers with HIGH κ learned regime-specific patterns for 2023
# Layers with LOW κ learned general trading principles

# When 2024 regime arrives:
# Option 1: If we expect 2023 patterns to return
selective_optimizer = SelectiveFineTuningOptimizer(
    model=model,
    top_n_trainable=15,  # Only update lowest-κ layers
)
# Preserves 2023 patterns, adapts general reasoning

# Option 2: If 2024 is completely different regime
# Increase top_n_trainable, but still preserve SOME high-κ layers
selective_optimizer = SelectiveFineTuningOptimizer(
    model=model,
    top_n_trainable=30,  # Update more layers, but not all
)
```

#### Regime Detection Integration

```typescript
// Combine with Coinswarm's regime detection
interface RegimeAwareFinetuning {
  currentRegime: MarketRegime;

  // κ profiles from training in each regime
  regimeκProfiles: Map<MarketRegime, LayerκScores>;

  // When entering new regime:
  // 1. Check if we've seen this regime before
  // 2. If yes: Load that regime's κ profile, protect those layers
  // 3. If no: Use default κ-guided selective training
}
```

---

### 2.5 Memory-Augmented LLM Fine-tuning

#### Current Memory System

```
Episodic → Semantic → Wisdom (3-tier consolidation)
```

#### LLM Fine-tuning Parallel

```
Recent gradients → Weight updates → Consolidated knowledge

kappaTune's κ analysis tells us:
- Which weight updates should be "episodic" (temporary, updateable)
- Which should be "semantic" (medium-term, somewhat protected)
- Which should be "wisdom" (long-term, frozen)
```

#### Proposed Integration: κ-Tiered Training

```python
class KappaTieredTrainer:
    def __init__(self, model):
        self.model = model

    def train_step(self, data):
        # Forward pass
        loss = self.model(data)
        loss.backward()

        # κ-tiered gradient application
        for name, param in self.model.named_parameters():
            kappa = self.get_layer_kappa(name)

            if kappa > HIGH_THRESHOLD:
                # "Wisdom" layer - freeze completely
                param.grad = None

            elif kappa > MEDIUM_THRESHOLD:
                # "Semantic" layer - reduce learning rate
                param.grad *= 0.1

            else:
                # "Episodic" layer - full learning rate
                pass

        self.optimizer.step()
```

---

### 2.6 Pattern-Specific Fine-tuning

#### Scenario

Each pattern in Coinswarm might benefit from specialized LLM understanding:
- Momentum patterns need different reasoning than mean-reversion
- High-frequency patterns vs position trading patterns
- Crypto-specific patterns vs general TA patterns

#### κ-Guided Approach

```python
# Analyze which layers are pattern-type-agnostic
kappa_momentum = analyze_kappa_on_data(model, momentum_patterns)
kappa_reversion = analyze_kappa_on_data(model, reversion_patterns)

# Find layers that are CONSISTENTLY low-κ across pattern types
# These are the general trading layers - PROTECT THEM
general_layers = find_consistent_low_kappa(kappa_momentum, kappa_reversion)

# Find layers that diverge by pattern type
# These need pattern-specific adapters
specialized_layers = find_divergent_kappa(kappa_momentum, kappa_reversion)

# Create pattern-specific fine-tuning strategy
class PatternSpecificModel:
    def __init__(self):
        self.shared_base = load_base_model()  # Freeze general_layers
        self.momentum_adapter = Adapter()     # Specialized for momentum
        self.reversion_adapter = Adapter()    # Specialized for reversion
```

---

### 2.7 The Training Data Loop

#### How Coinswarm Generates Training Data

```
Evolution Cycle:
1. CHAOS: Generate random trades
2. DISCOVERY: AI finds patterns
3. BACKTEST: Validate patterns
4. SELECTION: Keep winners

This generates LABELED DATA:
- Winning trades (positive examples)
- Losing trades (negative examples)
- Pattern attributions (what pattern caused what outcome)
```

#### κ-Guided Training Data Usage

```python
# As Coinswarm runs evolution cycles, it generates training data
# Use κ analysis to determine what to learn from each cycle

class ContinualPatternLearner:
    def __init__(self, model):
        self.model = model
        self.kappa_history = []

    def learn_from_cycle(self, cycle_data):
        # Analyze current model specialization
        current_kappa = analyze_condition_numbers(self.model)
        self.kappa_history.append(current_kappa)

        # Determine training strategy
        if is_regime_shift(cycle_data):
            # New regime - allow more updates
            trainer = SelectiveFineTuningOptimizer(
                model=self.model,
                top_n_trainable=30,
            )
        else:
            # Same regime - protect learned patterns
            trainer = SelectiveFineTuningOptimizer(
                model=self.model,
                top_n_trainable=10,
            )

        # Train with κ protection
        self.train(trainer, cycle_data)

    def detect_forgetting(self):
        # Compare κ profiles over time
        # Sharp increases in κ might indicate forgetting
        # (layers re-specializing = lost generalization)
        return analyze_kappa_drift(self.kappa_history)
```

---

### 2.8 Model Architecture Implications

#### Current Coinswarm AI Usage

- Workers AI for live decisions (fast, cheap)
- Local Ollama for batch processing
- Claude for code generation

#### κ-Optimized Architecture

```
INFERENCE PATH (κ-aware):
┌─────────────────────────────────────────────────────────┐
│ Input: Market data + Agent traits + Pattern signals    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ FROZEN FOUNDATION LAYERS (Highest κ)                   │
│ - Pre-trained market understanding                     │
│ - Never updated after initial training                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ PROTECTED PATTERN LAYERS (High κ)                      │
│ - Learned pattern detection                            │
│ - Updated rarely, with κ protection                    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ ADAPTIVE REGIME LAYERS (Medium κ)                      │
│ - Current market regime understanding                  │
│ - Updated when regime shifts detected                  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ AGENT-SPECIFIC ADAPTERS (Variable κ)                   │
│ - Per-agent decision preferences                       │
│ - Updated based on agent's trade outcomes              │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ Output: Trade decision + Confidence                    │
└─────────────────────────────────────────────────────────┘
```

---

## Summary: The κ Principle Across Coinswarm

### Conceptual Level

| System Component | κ Equivalent | Protection Strategy |
|------------------|--------------|---------------------|
| Agent Traits | Trait fitness correlation | Adaptive mutation rates |
| Pattern Evolution | Fitness variance | Stability-aware selection |
| Memory System | Access frequency + reinforcement | Tier-based decay rates |
| Evolution Phases | Training epoch maturity | Phase-appropriate learning rates |
| Fitness Components | Signed risk metrics | Already captures specialization |
| Market Regimes | Task distribution | Regime-aware pattern activation |
| Intelligence Signals | External knowledge reliability | Historical accuracy weighting |
| Exchange Execution | Domain specialization | Exchange-specific routing |

### Fine-tuning Level

| LLM Use Case | κ Strategy |
|--------------|------------|
| Pattern Discovery | Freeze pattern-detection layers, adapt reasoning layers |
| AI Zone Decisions | Shared base + agent-specific adapters |
| Regime Adaptation | Selective unfreezing based on regime similarity |
| Memory Consolidation | κ-tiered gradient scaling |
| Pattern Specialization | Pattern-type-specific adapter layers |
| Continuous Learning | κ-drift monitoring to detect forgetting |

### Key Takeaways

1. **kappaTune's core insight applies broadly**: The principle of "protect what's specialized, update what's general" transcends neural networks.

2. **Coinswarm already has proto-κ systems**: Relevance scoring, derived traits, LOG-SD pruning all embody similar principles.

3. **The gap is explicit κ calculation**: Coinswarm doesn't currently MEASURE specialization directly - it relies on fitness as a proxy.

4. **Fine-tuning integration is straightforward**: When Coinswarm uses LLM fine-tuning, kappaTune is directly applicable with minimal adaptation.

5. **The biggest win is regime adaptation**: kappaTune's approach to continual learning across tasks maps perfectly to market regime changes.

---

## Recommended Next Steps

1. **Implement trait specialization metrics** - Calculate variance/correlation of traits across elite agents
2. **Add pattern stability scoring** - Track fitness variance as a first-class metric
3. **Pilot κ-guided fine-tuning** - When adding LLM fine-tuning, use kappaTune from the start
4. **Build regime-aware model management** - Store κ profiles per regime for smart adaptation
