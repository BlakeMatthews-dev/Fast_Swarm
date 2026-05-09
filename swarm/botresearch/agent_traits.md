# AGENT TRAITS AUDIT
**Date**: 2026-01-21
**Status**: 6 CRITICAL/HIGH ISSUES

## EXECUTIVE SUMMARY

Traits enter system through 5+ unvalidated pathways, creating corruption opportunities.

## CRITICAL FINDINGS

### [CRITICAL] Unvalidated Database Load
**File**: backtest_service.py:365
```python
traits_dict = agent.traits if isinstance(agent.traits, dict) else agent.traits.__dict__
agent_traits = AgentTraits(**filtered_traits)  # NO VALIDATION!
```
**CONSEQUENCE**: Corrupted DB data (e.g., `risk_tolerance: 1.5`) flows to calculations.

### [CRITICAL] Missing Trait Key Crashes Backtest
**File**: trio_engine.py:265
```python
exit_threshold = agent.traits["exit_threshold"]  # KeyError if missing!
```
**CONSEQUENCE**: Missing key crashes entire evolution cycle.

### [CRITICAL] Mutation Breaks Derived Trait Contracts
**File**: evolution_service.py:323-327
```python
mutated_traits[key] = max(0, min(1, value + mutation))
# BUG: If key="risk_tolerance", it's mutated
# But "drawdown_sensitivity" is NOT recalculated!
```
**CONSEQUENCE**: Derived traits no longer follow their formulas after mutation.

### [CRITICAL] Crossover Defaults Missing Traits to 0.0
**File**: evolution_service.py:420-428
```python
val_b = traits_b.get(key, 0)  # Default 0 if missing!
```
**CONSEQUENCE**: Traits regress toward 0.0 over generations.

### [HIGH] Calculation Functions Accept Invalid Input Silently
**File**: agent_service.py:20-36
```python
clamped = max(0.0, min(1.0, risk_tolerance))  # Silently clamps!
```
**CONSEQUENCE**: Bugs never caught, errors compound through generations.

### [HIGH] Derived Traits Use Uncontrolled Global Randomness
**File**: agent_service.py:98-129
Same input produces different output each call (non-deterministic).

## ROOT CAUSE

Traits enter system through multiple unvalidated pathways:
- Spawn (validated)
- Database load (NOT validated)
- Mutation (partial)
- Crossover (NOT validated)
- API updates (NOT validated)

## RECOMMENDED FIX

Add SQLModel validator to Agent class:
```python
@validator("traits", pre=True, always=True)
def validate_traits_on_set(cls, v):
    is_valid, error = validate_all_traits(v)
    if not is_valid:
        raise ValueError(f"Invalid agent traits: {error}")
    return v
```

This ensures NO invalid traits enter or leave the system.
