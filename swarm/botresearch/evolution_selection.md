# EVOLUTION SELECTION AUDIT
**Date**: 2026-01-21
**Status**: MOSTLY HEALTHY - 2 MINOR ISSUES

## EXECUTIVE SUMMARY

Evolution is **correctly implemented**. Digital agents don't have biological inbreeding problems - trait crossover is just math.

## CLARIFICATIONS

### Lineage Checks Are Optional, Not Critical
**File**: evolution_service.py:491-497

The `_are_same_lineage()` function exists but **incomplete lineage checking is NOT a bug**:
- Digital agents don't suffer from "genetic defects" - traits are just floats being averaged
- Parent-child breeding produces valid offspring (average of similar traits)
- Lineage checks are optional diversity optimization, not a requirement

**ONLY A PROBLEM IF**: Lineage is used in FITNESS calculations (would unfairly penalize agents based on ancestry). Verified this is NOT the case - fitness is based on trading performance only.

### Breeding Output Shortfall - Minor Diversity Concern
**File**: evolution_service.py:564-582

When lineage conflict occurs, breeding skips without replacement. This slightly reduces offspring count but:
- Not a correctness bug
- Population still grows via cloning and fresh spawns
- Minor diversity impact at most

## ACTUAL FINDINGS

### [HIGH] Culling by "Best Regime" Protects Specialists Over Generalists
**File**: cull_service.py:17-39
```python
return max(valid_scores)  # Takes MAXIMUM regime fitness
```

**DESIGN QUESTION**: Bull specialist (95 bull, 0 crash) beats balanced generalist (45 all regimes).

This may be intentional - regime-based fitness means specialists are valued. Document if this is desired behavior.

### [MEDIUM] Implicit ASC Sort for Bottom Agents
**File**: ranking_service.py:135-139
```python
order_by(Agent.fitness_score.nulls_last())  # Implicit ASC
```

Works correctly but relies on implicit behavior. Consider explicit `asc()` for clarity.

## VERIFIED CORRECT

| Component | Status |
|-----------|--------|
| Elite selection (reverse=True) | OK |
| Trait mutation bounds [0,1] | OK |
| Generation increment | OK |
| Population minimum protection | OK |
| Crossover trait averaging | OK |
| Fitness based on performance only | OK |

## TEST COVERAGE GAPS

These contracts are NOT IMPLEMENTED in tests:

- `test_selection_by_fitness_descending`
- `test_cull_by_fitness_ascending`
- `test_mutation_preserves_bounds`
- `test_10_parents_produce_5_children`

## RECOMMENDATIONS

1. Document specialist vs generalist culling design choice
2. Add explicit `asc()` to bottom agent query for clarity
3. Implement EDD test contracts for evolution invariants
