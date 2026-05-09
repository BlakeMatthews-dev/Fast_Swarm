# κ-Inspired Adaptive Evolution for Coinswarm

> **TL;DR**: kappaTune uses condition numbers (κ) to identify which neural network layers are "specialized" vs "generalizable" and adjusts learning rates accordingly. We adapt this concept for trading pattern evolution: stable patterns get smaller mutations, variable patterns get larger mutations.

---

## Table of Contents

1. [What is kappaTune?](#what-is-kappatune)
2. [Why Apply This to Coinswarm?](#why-apply-this-to-coinswarm)
3. [Conceptual Mapping](#conceptual-mapping)
4. [What Applies](#what-applies)
5. [What Doesn't Apply](#what-doesnt-apply)
6. [Implementation Guide](#implementation-guide)
7. [Research & References](#research--references)
8. [Related Search Terms](#related-search-terms)

---

## What is kappaTune?

**Repository**: https://github.com/oswaldoludwig/kappaTune

**Paper**: [arXiv:2506.16289](https://arxiv.org/abs/2506.16289) - "kappaTune: Efficient Fine-Tuning of Large Language Models via Condition Number Analysis"

### Core Concept

kappaTune is a PyTorch optimizer wrapper that analyzes the **condition number (κ)** of weight matrices to determine which layers should be fine-tuned vs frozen during continual learning.

```
κ (condition number) = σ_max / σ_min
```

Where σ_max and σ_min are the largest and smallest singular values of a weight matrix.

### Key Insight

| κ Value | Meaning | Action |
|---------|---------|--------|
| **High κ** | Layer is specialized to current task | **Freeze** (don't update) |
| **Low κ** | Layer is generalizable | **Update** (fine-tune) |

This prevents **catastrophic forgetting** - when fine-tuning destroys previously learned knowledge.

### How It Works in Neural Networks

```python
# Simplified kappaTune logic
for layer in model.layers:
    U, S, V = torch.svd(layer.weight)  # Singular Value Decomposition
    kappa = S.max() / S.min()          # Condition number

    if kappa > threshold:
        layer.requires_grad = False    # Freeze specialized layers
    else:
        layer.requires_grad = True     # Update generalizable layers
```

---

## Why Apply This to Coinswarm?

### The Problem We're Solving

Coinswarm's evolution uses a **uniform 10% mutation rate** for all patterns:

```python
# OLD: Every pattern mutates the same way
MUTATION_RATE = 0.10  # Same for elite and exploratory patterns
```

This is suboptimal because:

1. **Elite patterns get destabilized** - Patterns that work consistently get mutated as aggressively as new patterns, potentially destroying what made them successful.

2. **Exploratory patterns don't explore enough** - Patterns with inconsistent performance (high variance) need MORE mutation to find better parameter regions, not the same amount.

3. **No memory of what works** - The system doesn't distinguish between "this pattern is stable because it's good" vs "this pattern is unstable because we haven't found the right parameters yet."

### The κ-Inspired Solution

Instead of SVD on weight matrices, we use **fitness variance** as our proxy for specialization:

```
κ_pattern = 1 / (1 + CV)

Where CV = coefficient of variation = std(fitness) / mean(fitness)
```

| Pattern Type | CV | κ | Mutation Rate |
|--------------|-----|---|---------------|
| Consistent performer | 0.1 | 0.91 | 3.6% |
| Moderate variance | 0.5 | 0.67 | 8.0% |
| High variance | 1.0 | 0.50 | 11.0% |
| Very unstable | 2.0 | 0.33 | 14.0% |

---

## Conceptual Mapping

### Neural Networks → Trading Patterns

| Neural Network Concept | Coinswarm Equivalent |
|------------------------|----------------------|
| Model weights | Pattern parameters (thresholds, operators) |
| Layer | Individual condition (e.g., RSI > 30) |
| Training epoch | Evolution generation |
| Loss function | Negative fitness score |
| Learning rate | Mutation rate |
| Condition number (κ) | Fitness stability (inverse CV) |
| Catastrophic forgetting | Destroying profitable patterns through over-mutation |
| Fine-tuning | Breeding/mutation of existing patterns |
| Pre-trained knowledge | Elite patterns from previous generations |

### Weight Matrix → Fitness Distribution

In kappaTune:
```
Weight Matrix W → SVD → σ_max, σ_min → κ = σ_max/σ_min
```

In Coinswarm:
```
Fitness History [f1, f2, ..., fn] → Stats → mean, std → CV = std/mean → κ = 1/(1+CV)
```

Both measure "how specialized/stable is this component?"

---

## What Applies

### 1. Adaptive Mutation Rates ✅

**Directly applicable.** The core insight transfers perfectly:

```python
# High κ (stable) → low mutation rate
# Low κ (unstable) → high mutation rate
mutation_rate = MAX_RATE - kappa * (MAX_RATE - MIN_RATE)
```

**Implementation**: `local-utilities/kappa_evolution.py` → `calculate_adaptive_mutation_rate()`

### 2. Protection Levels ✅

**Directly applicable.** Patterns earn protection based on stability + performance:

| Level | Criteria | Action |
|-------|----------|--------|
| `freeze` | κ ≥ 0.85 AND fitness ≥ 70 | No mutation, clone directly |
| `protect` | κ ≥ 0.70 AND fitness ≥ 60 | Minimal mutation (2-4%) |
| `normal` | Middle range | Standard mutation |
| `explore` | κ ≤ 0.30 | Aggressive mutation (15-20%) |

**Implementation**: `PatternSpecialization.protection_level`

### 3. Regime-Conditional Selection ✅

**Adaptation of the concept.** kappaTune adapts layers to new tasks. We adapt patterns to market regimes:

```python
# Pattern performs well in bull markets but poorly in crashes
profile = regime_tracker.get_profile(pattern_id)
# → Boost weight in bull regime, reduce in crash regime
```

**Implementation**: `RegimePerformanceTracker` class

### 4. Stability as Fitness Component ✅

**Extension of the concept.** Add stability to the fitness function:

```python
# V2 fitness formula + stability bonus
fitness = alpha(35) + sortino(14) + calmar(11) + expectancy(28) + drawdown(5) + stability(7)
```

Patterns that are both profitable AND consistent score higher.

**Implementation**: `calculate_fitness_with_stability()`

### 5. Cycle-Adaptive Parameters ✅

**Adaptation.** Early cycles need more exploration, mature cycles need exploitation:

```python
# Early cycles (gen 1-10): Higher mutation, more chaos
# Mature cycles (gen 40+): Lower mutation, stricter selection
maturity = 1 - exp(-cycle / 20)
mutation_rate = 0.10 - maturity * 0.05  # 10% → 5%
```

**Implementation**: `calculate_cycle_parameters()`

---

## What Doesn't Apply

### 1. Singular Value Decomposition ❌

**Not applicable.** SVD is specific to weight matrices in neural networks. Trading patterns don't have a natural matrix representation where singular values are meaningful.

**Why it fails**:
- Pattern conditions are heterogeneous (RSI, MACD, volume - different scales)
- No meaningful "matrix" structure
- SVD assumes linear relationships

**Our alternative**: Coefficient of variation (CV) of fitness scores

### 2. Gradient-Based Updates ❌

**Not applicable.** kappaTune adjusts gradient descent learning rates. Our evolution uses mutation/crossover, not gradients.

**Why it fails**:
- No differentiable loss function for pattern parameters
- Discrete search space (operators: >, <, >=, <=)
- Fitness is evaluated via backtesting, not forward pass

**Our alternative**: Mutation rate scaling

### 3. Layer-wise Analysis ❌

**Partially applicable.** Neural networks have clear layer hierarchy. Patterns have flat condition lists.

**Why it partially fails**:
- Patterns don't have "early" vs "late" layers
- Each condition is relatively independent

**Partial adaptation**: Could analyze per-indicator stability (e.g., "RSI conditions are more stable than volume conditions")

### 4. Pretraining Detection ❌

**Not applicable.** kappaTune assumes you have pretrained weights you want to preserve. We don't have a "pretrained" baseline.

**Our alternative**: Elite patterns from previous generations serve a similar role

### 5. Memory Efficiency Optimizations ❌

**Not applicable.** kappaTune's memory optimizations are specific to large transformer models with billions of parameters. Our patterns have ~5-10 parameters each.

---

## Implementation Guide

### File Structure

```
local-utilities/
├── kappa_evolution.py      # κ-inspired components (NEW)
├── local_evolution.py      # Main evolution loop (MODIFIED)
├── local_backtest.py       # Backtesting engine
└── models.py               # Database models
```

### Quick Start

```bash
cd local-utilities

# Run with κ-inspired evolution (default)
python local_evolution.py --generations 50

# Disable κ, use uniform 10% mutation
python local_evolution.py --generations 50 --no-kappa

# Analyze existing patterns for κ scores
python kappa_evolution.py --db coinswarm_unified.db --analyze --init
```

### Key Functions

#### 1. Calculate Pattern Specialization

```python
from kappa_evolution import analyze_pattern_specialization

# After backtesting across multiple periods
spec = analyze_pattern_specialization(
    pattern_id="pattern_abc123",
    period_results=[
        {'period_type': 'bull', 'fitness_score': 72},
        {'period_type': 'bear', 'fitness_score': 68},
        {'period_type': 'crash', 'fitness_score': 45},
        # ... more results
    ],
    min_runs=5,
)

print(f"κ: {spec.kappa:.2f}")           # e.g., 0.73
print(f"Mutation rate: {spec.recommended_mutation_rate:.1%}")  # e.g., 6.9%
print(f"Protection: {spec.protection_level}")  # e.g., "protect"
```

#### 2. Adaptive Mutation

```python
from kappa_evolution import mutate_with_kappa

# Instead of uniform mutation
child = mutate(parent, rate=0.10)  # OLD

# Use κ-aware mutation
child = mutate_with_kappa(parent, spec)  # NEW
# → High-κ parent: smaller mutations
# → Low-κ parent: larger mutations
```

#### 3. Track Regime Performance

```python
from kappa_evolution import RegimePerformanceTracker

tracker = RegimePerformanceTracker(db_path)

# After each backtest
tracker.update_from_backtest(
    pattern_id="pattern_abc123",
    regime="bull",
    fitness=72.5,
    alpha=15.3,
    pnl=23.1,
    win_rate=0.65,
)

# Get best patterns for current regime
best_for_crash = tracker.get_best_patterns_for_regime("crash", limit=20)
```

### Database Schema Additions

```sql
-- New columns on patterns table
ALTER TABLE patterns ADD COLUMN kappa_score REAL DEFAULT 0.5;
ALTER TABLE patterns ADD COLUMN stability_score REAL DEFAULT 50;
ALTER TABLE patterns ADD COLUMN regime_consistency REAL DEFAULT 0;
ALTER TABLE patterns ADD COLUMN mutation_rate REAL DEFAULT 0.1;
ALTER TABLE patterns ADD COLUMN protection_level TEXT DEFAULT 'normal';

-- New table for regime performance
CREATE TABLE pattern_regime_performance (
    pattern_id TEXT NOT NULL,
    regime TEXT NOT NULL,
    run_count INTEGER DEFAULT 0,
    avg_fitness REAL DEFAULT 0,
    avg_alpha REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    confidence REAL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(pattern_id, regime)
);
```

---

## Research & References

### Primary Sources

1. **kappaTune Repository**
   - URL: https://github.com/oswaldoludwig/kappaTune
   - Author: Oswaldo Ludwig
   - License: Apache 2.0

2. **kappaTune Paper**
   - Title: "kappaTune: Efficient Fine-Tuning of Large Language Models via Condition Number Analysis"
   - arXiv: https://arxiv.org/abs/2506.16289
   - Year: 2025

### Related Concepts

3. **Catastrophic Forgetting**
   - Kirkpatrick et al., "Overcoming catastrophic forgetting in neural networks" (2017)
   - https://arxiv.org/abs/1612.00796

4. **Elastic Weight Consolidation (EWC)**
   - Similar concept: protect important weights
   - https://arxiv.org/abs/1612.00796

5. **Condition Numbers in Optimization**
   - Numerical analysis concept measuring sensitivity to perturbations
   - High κ = ill-conditioned = sensitive = specialized
   - Low κ = well-conditioned = robust = generalizable

### Evolutionary Algorithms

6. **Adaptive Mutation Rates**
   - Rechenberg's 1/5 success rule (1973)
   - Self-adaptive mutation in Evolution Strategies
   - https://en.wikipedia.org/wiki/Evolution_strategy

7. **Fitness Landscape Theory**
   - Kauffman, "Origins of Order" (1993)
   - Rugged landscapes need more exploration

8. **Neuroevolution**
   - NEAT (NeuroEvolution of Augmenting Topologies)
   - https://nn.cs.utexas.edu/downloads/papers/stanley.ec02.pdf

---

## Related Search Terms

### For Understanding kappaTune

```
condition number neural network
SVD weight matrix analysis
selective fine-tuning LLM
catastrophic forgetting prevention
layer-wise learning rate
parameter-efficient fine-tuning PEFT
LoRA condition number
```

### For Our Adaptation

```
adaptive mutation rate evolutionary algorithm
fitness variance mutation scaling
regime-switching trading strategy
robustness vs overfitting trading
coefficient of variation fitness
population diversity evolution
exploitation exploration tradeoff
elite preservation evolutionary
```

### For Implementation

```
SQLite fitness tracking
pattern stability measurement
rolling window statistics python
numpy coefficient of variation
trading backtest regime detection
market regime classification
evolutionary hyperparameter adaptation
```

### Academic Keywords

```
meta-learning trading strategies
continual learning optimization
transfer learning financial markets
multi-task learning market regimes
online learning portfolio
adaptive optimization algorithms
evolutionary portfolio optimization
```

---

## Validation & Testing

### How to Know If It's Working

1. **κ Distribution Should Evolve**
   - Early generations: Mostly `explore` (0.3) and `normal` (0.5)
   - Mature generations: More `protect` (0.7) and `freeze` (0.85+)

2. **Elite Patterns Should Stabilize**
   - Top 5 patterns should have κ > 0.7 after 20+ generations
   - If top patterns have low κ, they're still being discovered

3. **Fitness Variance Should Decrease**
   - Average CV of population should decrease over generations
   - Indicates convergence toward stable strategies

4. **Regime Specialists Should Emerge**
   - Some patterns should excel in specific regimes
   - `regime_tracker.get_best_patterns_for_regime("crash")` should return different patterns than `get_best_patterns_for_regime("bull")`

### Metrics to Track

```python
# Per generation logging
print(f"[κ] Avg κ: {np.mean(kappas):.3f}")
print(f"[κ] κ std: {np.std(kappas):.3f}")  # Should decrease
print(f"[κ] Freeze: {freeze_count}, Protect: {protect_count}")  # Should increase
print(f"[κ] Avg mutation used: {np.mean(mutation_rates):.1%}")  # Should decrease
```

---

## Future Extensions

### 1. Per-Indicator κ Analysis

Analyze which indicator types are most stable:

```python
# Future: Track stability per indicator type
indicator_stability = {
    'rsi14': 0.82,       # Very stable
    'macdHistogram': 0.71,
    'volumeRatio': 0.45,  # Needs more exploration
}
```

### 2. Cross-Asset κ Transfer

Patterns that work across assets have higher κ:

```python
# Future: Boost κ for cross-asset consistency
if pattern.works_on(['BTC', 'ETH', 'SOL']):
    spec.kappa *= 1.2  # Bonus for generalization
```

### 3. Temporal κ Decay

Recent performance matters more:

```python
# Future: Exponentially weight recent runs
weights = [exp(-i/10) for i in range(len(runs))]
weighted_cv = weighted_std(fitness, weights) / weighted_mean(fitness, weights)
```

---

## Summary

| Aspect | kappaTune (Neural Networks) | Coinswarm Adaptation |
|--------|----------------------------|----------------------|
| **What** | Condition number of weight matrices | Stability of fitness across periods |
| **Why** | Prevent catastrophic forgetting | Preserve elite patterns, explore unstable ones |
| **How** | SVD → κ → learning rate | CV → κ → mutation rate |
| **Applies** | Adaptive rates, protection levels | Yes |
| **Doesn't Apply** | SVD, gradients, layer-wise | Use CV instead |

The key insight transfers: **measure stability, protect what's stable, explore what's unstable**.
