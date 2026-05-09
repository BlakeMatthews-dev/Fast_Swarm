# LOOKAHEAD BIAS AUDIT REPORT
**Date**: 2026-01-21
**Status**: WORKING AS DESIGNED

## EXECUTIVE SUMMARY

**NO LOOKAHEAD BIAS IN DECISION-MAKING** - MFE/MAE retrospective calculation is INTENTIONAL for training data purposes.

## MFE/MAE: Training Data, Not Trading Metric

### Retrospective Calculation is Correct
**File**: `backtest_service.py` lines 100-131
**Status**: WORKING AS DESIGNED

```python
def calculate_mfe_mae(entry_price, price_history, direction):
    if direction == "long":
        best_price = max(price_history)   # Retrospective - INTENTIONAL
        worst_price = min(price_history)  # Retrospective - INTENTIONAL
```

**Why This is CORRECT**:

- MFE/MAE calculated AFTER trade exits for DATA TRAINING purposes
- Shows "best price ever" - useful for learning "how much profit left on table"
- Shows "worst price ever" - useful for learning "how close to disaster"
- NOT used for making trading decisions (no lookahead bias)
- IS used for post-hoc analysis to improve future agents

**Purpose**:

- **MFE (Maximum Favorable Excursion)**: "The trade went +15% at best - why did I exit at +8%?"
- **MAE (Maximum Adverse Excursion)**: "The trade went -12% at worst - my stop was at -10%, lucky it recovered"

## CRITICAL CAVEAT: MFE Must Not Inflate Fitness Directly

MFE/MAE in training data is fine **AS LONG AS**:

1. MFE is NOT added directly to fitness scores (would reward "what could have been")
2. MFE is only used in RATIO form like `exit_efficiency = pnl / mfe`

### Exit Efficiency (pnl/mfe) IS Used in Fitness - This is CORRECT

**File**: `pattern_matching.py` line 141-145
```python
def exit_efficiency(self) -> float:
    """How much of the max profit was captured (pnl / mfe)."""
    return min(1.0, max(-1.0, self.pnl_pct / self.mfe_pct))
```

This is **intentional and correct** because:

- It PENALIZES agents who exit poorly (captured 50% of potential = 0.5 score)
- It REWARDS agents who exit near the peak (captured 90% = 0.9 score)
- The ratio normalizes across different trade sizes
- Teaches agents optimal exit timing without lookahead in decision-making

## VERIFIED: No Direct MFE Inflation

Fitness uses exit_efficiency (ratio), NOT raw MFE. This means:

- Agent with +5% PnL and +10% MFE gets 0.5 efficiency (room to improve)
- Agent with +9% PnL and +10% MFE gets 0.9 efficiency (good exits)
- Raw MFE magnitude doesn't inflate scores

## VERIFIED CLEAN AREAS

| Area | Status | Notes |
|------|--------|-------|
| Entry at close price | CORRECT | Signal fires at close, entry at close |
| Trailing stop tracking | CORRECT | Tracks incrementally, no future data |
| Pattern evaluation | CORRECT | Uses current candle indicators only |
| Data loading | CORRECT | No future candles in evaluation window |
| Exit efficiency | CORRECT | Ratio form, not raw MFE |

## CONCLUSION

MFE/MAE retrospective calculation is **intentional design** for generating training data. The key safeguard is that MFE only enters fitness as a **ratio** (exit_efficiency = pnl/mfe), which measures exit quality rather than inflating scores based on unrealized potential.
