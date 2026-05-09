# κ (Kappa) Abstraction Guide for Coinswarm

> **Status**: Design document - guides future development
> **Source**: kappaTune research (arxiv:2506.16289)
> **Created**: 2025-12-27

---

## Core Principle

**κ measures how "proven" something is. Proven things should be protected; unproven things should be updated freely.**

From neural network fine-tuning:
- **High κ** = Specialized, converged, proven → **PROTECT** (lower mutation/decay)
- **Low κ** = General, exploratory, unproven → **UPDATE FREELY** (higher mutation/decay)

This principle applies abstractly to ALL Coinswarm components, not just neural networks.

---

## Component-by-Component κ Mappings

### 1. Agent Traits

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Trait variance across elite agents | Low variance = converged = high κ |
| **Current gap** | Uniform 10% mutation for all traits | Ignores convergence |
| **κ-inspired fix** | Adaptive mutation: 2-15% based on trait variance | Protect converged traits |

```python
# Future implementation
def calculate_trait_kappa(trait: str, elite_agents: List[Agent]) -> float:
    values = [a.traits[trait] for a in elite_agents]
    variance = np.var(values)
    fitness_correlation = pearsonr([a.traits[trait] for a in elite_agents],
                                    [a.fitness for a in elite_agents])[0]
    # High correlation + low variance = specialized = high κ
    return abs(fitness_correlation) / (variance + 0.01)

def get_mutation_rate(trait: str, kappa: float) -> float:
    # High κ = mutate less (0.02), Low κ = mutate more (0.15)
    return 0.15 / (1 + kappa)
```

---

### 2. Patterns

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Fitness consistency across backtests | Low variance = stable = high κ |
| **Current gap** | Selection uses raw fitness only | Ignores stability |
| **κ-inspired fix** | Protect patterns with consistent performance | Stability bonus in selection |

```python
# Future implementation
def calculate_pattern_kappa(runs: List[BacktestRun]) -> float:
    fitness_values = [r.fitness for r in runs]
    mean = np.mean(fitness_values)
    std = np.std(fitness_values)
    cv = std / (mean + 0.01)  # Coefficient of variation
    # Low CV = stable = high κ
    return 1 / (cv + 0.01)

def should_protect_pattern(kappa: float) -> bool:
    return kappa > 5  # Fitness varies less than 20%

def calculate_pruning_threshold(base_threshold: float, kappa: float) -> float:
    # Stable patterns get lower threshold (harder to kill)
    protection = min(10, kappa)
    return base_threshold - protection  # 30-40 depending on stability
```

---

### 3. Memory System

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Access frequency × reinforcement count | High usage = proven = high κ |
| **Current gap** | Uniform relevance decay | Ignores usage patterns |
| **κ-inspired fix** | Proven memories decay slower | Tier-aware decay rates |

```python
# Future implementation
def calculate_memory_kappa(memory: MemoryRecord) -> float:
    access_signal = math.log1p(memory.access_count)
    reinforcement_signal = memory.reinforcement_count * 2
    age_penalty = 1 / (1 + memory.age_days / 30)
    return (access_signal + reinforcement_signal) * age_penalty

def decay_relevance(memory: MemoryRecord) -> float:
    kappa = calculate_memory_kappa(memory)
    # High κ = decay 10x slower
    decay_rate = 0.01 / (1 + kappa)
    return memory.relevance_score * (1 - decay_rate)
```

---

### 4. Evolution Phases

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Phase maturity / cycle number | Later = more converged = high κ |
| **Current gap** | Same mutation rate all phases | Ignores evolution progress |
| **κ-inspired fix** | Early = aggressive, Late = conservative | Phase-aware mutation |

```python
# Future implementation
def get_phase_kappa(phase: str, cycle_number: int) -> float:
    base_cycles = 10
    phase_base = {'chaos': 0.1, 'discovery': 0.3, 'backtest': 0.5, 'selection': 0.8}
    return phase_base[phase] + (cycle_number / base_cycles) * 0.2

def get_mutation_rate(phase: str, cycle_number: int) -> float:
    kappa = get_phase_kappa(phase, cycle_number)
    return 0.15 / (1 + kappa)  # 0.15 early → 0.05 late
```

---

### 5. Market Regimes

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Regime persistence / stability | Long-lasting = established = high κ |
| **Current gap** | No regime-aware pattern weighting | All patterns treated equally |
| **κ-inspired fix** | Trust regime-specific patterns more in stable regimes | Dynamic pattern weighting |

```python
# Future implementation
def calculate_regime_kappa(regime: MarketRegime, history: RegimeHistory) -> float:
    duration_hours = (time.time() - regime.start_time) / 3600
    stability = 1 / (1 + history.transitions_last_week)
    return math.log1p(duration_hours) * stability

def weight_pattern_for_regime(pattern: Pattern, regime_kappa: float) -> float:
    if pattern.optimized_for_regime == current_regime:
        return pattern.fitness * (1 + regime_kappa * 0.2)  # Boost regime-specific
    else:
        return pattern.fitness * (1 - regime_kappa * 0.1)  # Prefer agnostic in new regimes
```

---

### 6. Intelligence Signals

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Historical accuracy of signal source | High accuracy = reliable = high κ |
| **Current gap** | All sources weighted equally | Ignores track record |
| **κ-inspired fix** | Weight by historical accuracy | Credibility-weighted signals |

```python
# Future implementation
def calculate_signal_kappa(source: SignalSource) -> float:
    sample_confidence = min(1, source.sample_size / 50)
    recency_weight = 1 / (1 + source.days_since_evaluation / 7)
    return source.accuracy * sample_confidence * recency_weight

def weighted_intelligence(signals: List[Signal]) -> float:
    weighted = [(s.value, calculate_signal_kappa(s.source)) for s in signals]
    total_weight = sum(w for _, w in weighted)
    return sum(v * w for v, w in weighted) / total_weight
```

---

### 7. Exchange Execution

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Fill rate × slippage × uptime | High reliability = trusted = high κ |
| **Current gap** | First available exchange used | Ignores execution quality |
| **κ-inspired fix** | Route to highest-κ exchanges | Quality-weighted routing |

```python
# Future implementation
def calculate_exchange_kappa(exchange: Exchange) -> float:
    fill_score = exchange.fill_rate
    slippage_score = 1 / (1 + exchange.avg_slippage_bps / 10)
    uptime_score = exchange.uptime_percent / 100
    return fill_score * slippage_score * uptime_score

def route_order(order: Order, exchanges: List[Exchange]) -> Exchange:
    scored = [(ex, calculate_exchange_kappa(ex) - ex.fee_bps / 100) for ex in exchanges]
    return max(scored, key=lambda x: x[1])[0]
```

---

### 8. Coaches (Layer 6 - Future)

| Aspect | Current State | κ Interpretation |
|--------|---------------|------------------|
| **What κ measures** | Roster stability / agent retention | Stable roster = confident = high κ |
| **Current gap** | Not yet implemented | - |
| **κ-inspired fix** | Stable coaches get more voting power | Credibility-weighted committee |

```python
# Future implementation
def calculate_coach_kappa(coach: Coach, history: CoachHistory) -> float:
    stability = history.roster_overlap_pct(cycles_ago=5)
    retention = history.agent_retention_rate
    success = history.cumulative_fitness / history.total_cycles
    return stability * retention * math.log1p(success)

def weight_coach_vote(coach: Coach) -> float:
    kappa = calculate_coach_kappa(coach, coach.history)
    return coach.base_vote_weight * (1 + kappa)
```

---

## Summary Table

| Component | What κ Measures | Low κ Behavior | High κ Behavior |
|-----------|-----------------|----------------|-----------------|
| **Traits** | Variance across elite agents | Mutate aggressively (15%) | Preserve (2%) |
| **Patterns** | Fitness consistency | Prune cautiously | Protect from pruning |
| **Memory** | Access × reinforcement | Decay normally | Slow decay (10x) |
| **Evolution** | Phase maturity | Wild exploration | Conservative refinement |
| **Regimes** | Persistence | Weight regime-agnostic | Trust regime-specific |
| **Signals** | Historical accuracy | Weight cautiously | Weight heavily |
| **Exchanges** | Execution reliability | Route small orders | Prefer for execution |
| **Coaches** | Roster stability | Reduce vote weight | Increase vote weight |

---

## Implementation Priority

When implementing κ-inspired changes, prioritize by impact:

1. **High Impact, Low Effort**: Pattern stability scoring (add fitness variance metric)
2. **High Impact, Medium Effort**: Trait-level adaptive mutation
3. **Medium Impact, Low Effort**: Memory tier-aware decay
4. **Medium Impact, Medium Effort**: Phase-aware mutation rates
5. **Lower Priority**: Regime weighting, signal credibility, exchange routing

---

## References

- **kappaTune Paper**: arxiv:2506.16289 - "The Condition Number as a Scale-Invariant Proxy for Information Encoding in Neural Units"
- **Repository**: https://github.com/oswaldoludwig/kappaTune
- **Core Insight**: Condition number reveals specialization; specialized knowledge should be protected during adaptation

---

*This document guides future development. Implementation should be incremental, starting with highest-impact, lowest-effort changes.*
