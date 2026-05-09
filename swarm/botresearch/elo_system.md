# ELO RATING SYSTEM AUDIT
**Date**: 2026-01-21
**Status**: 3 CRITICAL MATHEMATICAL ERRORS

## EXECUTIVE SUMMARY

ELO system has critical mathematical errors breaking zero-sum property and fairness.

## CRITICAL FINDINGS

### [CRITICAL] Non-Zero-Sum Transfer System (95% confidence)
**File**: elo_transfer_service.py:87-114
```python
base_change = ELO_K_BASE * scaled_pnl * confidence * elo_weight
return base_change if was_correct else -base_change
```
**PROBLEM**: Each agent's change calculated in isolation without considering opponents.

**PROOF**:
- Coach A (correct): +135 ELO
- Coach B (wrong): -57 ELO
- Coach C (correct): +35 ELO
- **Total: +109 ELO created from nothing!**

**CORRECT ELO**: Winner gains EXACTLY what loser loses.

### [CRITICAL] Missing Opponent Model (90% confidence)
**File**: elo_transfer_service.py:87-114
Standard ELO requires: `E_a = 1 / (1 + 10^((R_opponent - R_self) / 400))`

Current system has NO opponent ELO in formula. Confidence and PnL become only factors.

### [CRITICAL] Expected Score Uses Fixed Benchmark (100% confidence)
**File**: governance_service.py:312
```python
expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - old_elo) / 400.0))
```
Uses fixed 1500 benchmark instead of pairwise comparison.

## ADDITIONAL ISSUES

### [HIGH] Confidence Scaling Breaks ELO Theory
Standard ELO has no confidence parameter. Rating difference handles asymmetry.

### [HIGH] Floor/Ceiling Inconsistency
- Transfer service: Floor at 0
- Governance service: Floor at 1000, ceiling at 2500

### [MEDIUM] Variable K-Factor Not Implemented
Tests expect K=32 for new agents, K=16 for experienced. Code is static K=32.

## CORRECT ELO FORMULA

```python
# Pairwise calculation (CORRECT)
e_a = 1.0 / (1.0 + 10.0 ** ((opponent_elo - self_elo) / 400.0))
e_b = 1.0 - e_a  # Must sum to 1

delta_a = K * (actual_a - e_a)
delta_b = K * (actual_b - e_b)

# Guaranteed: delta_a + delta_b = 0 (ZERO-SUM)
```

## RECOMMENDATIONS

### P0 (CRITICAL)
1. Redesign to use pairwise ELO (4-6 hours)
2. Standardize floor/ceiling values
3. Remove confidence from K-factor scaling

### P1
4. Implement adaptive K-factor
5. Add zero-sum audit logging
6. Implement test contracts (currently `pytest.fail()`)

**Status**: Requires redesign before production use of Hivemind voting.
