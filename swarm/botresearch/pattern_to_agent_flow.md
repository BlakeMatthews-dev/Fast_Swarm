# PATTERN -> AGENT FLOW AUDIT
**Date**: 2026-01-21
**Status**: WORKING AS DESIGNED

## EXECUTIVE SUMMARY

**Regime-specific fitness IS used for pattern selection** - this is the core purpose of the system.

## VERIFIED WORKING

### Regime Fitness Calculated (OK)
- Patterns tested across 9 canonical regimes + 6 random timeframes
- Each regime: fitness, trades, win_rate, sharpe, sortino, max_drawdown
- Stored in `fitness_by_regime` JSONB

### Regime Fitness USED in Spawn (OK)
**File**: `evolution_cycle_service.py` lines 264-268
```python
from ...Agents.Services.spawn_service import get_regime_priority_patterns

regime_patterns = await get_regime_priority_patterns(
    session, categories=weak_regimes, limit=patterns_per_regime
)
```

The function `get_regime_priority_patterns()` IS called during evolution to:
- Find 5 weakest regimes in the population
- Select top patterns FOR EACH weak regime
- This is the whole point of regime fitness!

### Regime Weights Applied (OK)
```
crash: 3.0 (hardest, most important)
sideways: 2.5
bear: 2.0
bull: 0.5 (easiest)
```

### Culling Uses Best Regime Fitness (OK)
**File**: `cull_service.py` lines 17-39
```python
def get_best_regime_fitness(agent: Agent) -> float:
    regime_fitness = agent.fitness_by_regime or {}
    if regime_fitness:
        valid_scores = [v for v in regime_fitness.values() ...]
        return max(valid_scores)  # Protects specialists
```

### Trait Affinity Matching (OK)
- `momentum_vs_reversion` -> momentum/reversion patterns
- `volatility_seeking` -> high/low vol patterns
- `risk_tolerance` -> aggressive/conservative patterns

## PREVIOUS INCORRECT CLAIM

The earlier audit incorrectly stated that `get_regime_priority_patterns()` was "dead code" and "never called". This was wrong - it IS called from evolution_cycle_service.py during the spawn phase.

## CONCLUSION

The pattern -> agent flow is **working as designed**:
1. Patterns backtested per regime -> fitness_by_regime stored
2. Evolution identifies weak regimes in population
3. `get_regime_priority_patterns()` selects patterns strong in weak regimes
4. Agents spawned with regime-appropriate patterns
5. Culling protects regime specialists via `get_best_regime_fitness()`

No fixes required.
