# Bear Protection Protocol

## Overview

A hierarchical risk management system where **bear protection has supreme veto power** over all pattern trades.

**Two Layers:**
1. **Bear Protection** = Insurance / Defense / Crash survival
2. **Patterns** = Opportunistic swing & scalp alpha generation

```
┌─────────────────────────────────────────────────────────────────┐
│                    BEAR PROTECTION LAYER                        │
│                    (Supreme Veto Power)                         │
│                                                                 │
│  Exit Signal: vel>0.5 AND acc<-1.5 AND adx_jerk<0              │
│  Entry Signal: vel<-1.5 AND acc>3.0                            │
│                                                                 │
│  When DEFENSIVE: Force reduce ALL positions to 25% max         │
│  This layer can OVERRIDE any pattern decision                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PATTERN LAYER                                │
│                    (Opportunistic Trading)                      │
│                                                                 │
│  Swing Patterns: Multi-day holds, trend following              │
│  Scalp Patterns: Short-term mean reversion, momentum           │
│                                                                 │
│  Patterns can freely adjust position 0-100% of allowed budget  │
│  But CANNOT exceed regime-imposed limits                       │
└─────────────────────────────────────────────────────────────────┘
```

## Regime States

| Regime | Trigger | Max Position | Pattern Freedom |
|--------|---------|--------------|-----------------|
| **DEFENSIVE** | Exit signal fires (any TF) | 25% | Limited - survival mode |
| **NEUTRAL** | No signal active | 50% | Normal - balanced |
| **AGGRESSIVE** | Entry signal fires (any TF) | 75% | Expanded - opportunity mode |

## Key Rules

### 1. Bear Protection Has VETO POWER

When the exit signal fires:
- ALL open positions must reduce to ≤25% immediately
- Patterns CANNOT override this
- This is a "circuit breaker" for crashes

```python
if regime == "DEFENSIVE":
    # Force liquidate excess
    for position in open_positions:
        if position.size > allowed_max * 0.25:
            reduce_to(position, allowed_max * 0.25)
```

### 2. Patterns Control Timing Within Regime

During NEUTRAL or AGGRESSIVE:
- Patterns decide WHEN to enter/exit
- Patterns decide position SIZE (within regime limit)
- Bear protection only intervenes on danger signal

### 3. Sticky Regime Until Opposite Signal

- DEFENSIVE stays until AGGRESSIVE signal fires
- AGGRESSIVE stays until DEFENSIVE signal fires
- Prevents whipsawing on noise

## Signal Definitions

### Exit (Danger) Signal - Go DEFENSIVE
```
ANY timeframe (1h, 4h, 1d) where:
  close_velocity_zscore > 0.5     (price rising fast)
  AND close_acceleration_zscore < -1.5  (momentum fading)
  AND adx_14_jerk_zscore < 0      (trend strength decelerating)
```

**Interpretation**: Price is up but momentum is exhausted. Top forming.

### Entry (Opportunity) Signal - Go AGGRESSIVE
```
ANY timeframe (1h, 4h, 1d) where:
  close_velocity_zscore < -1.5    (price falling fast)
  AND close_acceleration_zscore > 3.0   (deceleration = bottom forming)
```

**Interpretation**: Price crashed but selling exhausted. Bottom forming.

## Historical Performance

### Full History (2019-2026)

| Asset | Strategy Return | Buy & Hold | Improvement |
|-------|-----------------|------------|-------------|
| BTC | 23,992% | 861% | 25x |
| ETH | 82,643% | 1,483% | 52x |
| SOL | 155,458% | 4,383% | 35x |
| DOGE | 15,601,521% | 5,249% | 2,917x |

### By Time Period (Majors Average)

| Period | Strategy Beats B&H | Avg Improvement |
|--------|-------------------|-----------------|
| Last 1 Month (bull) | 21% | 0.96x |
| Last 3 Months (bear) | 93% | 1.33x |
| Last 6 Months (bear) | 100% | 1.78x |
| Last 1 Year | 100% | 4.06x |

**Key Insight**: Strategy underperforms in pure bull runs but massively outperforms during crashes. This is EXACTLY what bear protection should do.

## Integration with Pattern System

### Pattern Trade Flow

```python
def execute_pattern_trade(pattern, signal):
    # Step 1: Check regime (Bear Protection)
    regime = get_current_regime()  # DEFENSIVE/NEUTRAL/AGGRESSIVE
    max_allowed = REGIME_LIMITS[regime]  # 25%/50%/75%

    # Step 2: Pattern decides size within limit
    pattern_size = pattern.calculate_position_size(signal)
    actual_size = min(pattern_size, max_allowed)

    # Step 3: Execute
    if regime == "DEFENSIVE" and signal.is_long:
        # Even if pattern wants to buy, severely limit size
        actual_size = min(actual_size, max_allowed * 0.5)

    return execute(actual_size)
```

### Example Scenarios

**Scenario 1: Bull Market, Pattern Wants 80% Long**
- Regime: AGGRESSIVE (entry signal fired recently)
- Max allowed: 75%
- Pattern gets: 75% (capped by regime)

**Scenario 2: Crash Incoming, Pattern Wants to Hold**
- Exit signal fires → Regime: DEFENSIVE
- Max allowed: 25%
- All positions FORCE REDUCED to 25%, pattern overruled

**Scenario 3: Sideways Chop, Pattern Uncertain**
- Regime: NEUTRAL
- Max allowed: 50%
- Pattern can trade freely 0-50%

## Why This Works

1. **Bear markets destroy more than bulls create** - A 50% loss requires 100% gain to recover. Protecting downside is mathematically superior.

2. **Motion derivatives detect exhaustion EARLY** - Velocity + acceleration divergence catches tops/bottoms before price confirms.

3. **ADX jerk filters false signals** - Only exit when trend strength is also decelerating, not during healthy pullbacks.

4. **Patterns handle the alpha, protocol handles the beta** - Separation of concerns: patterns find opportunities, protocol manages risk.

## Implementation Checklist

- [ ] Add `regime` field to market state
- [ ] Create `BearProtectionService` that monitors signals
- [ ] Add `max_position_override` to all pattern executors
- [ ] Implement forced liquidation on regime change to DEFENSIVE
- [ ] Log all regime changes for analysis
- [ ] Create dashboard widget showing current regime

## Files

| File | Purpose |
|------|---------|
| `scripts/backtest_mtf_combinations.py` | Original signal discovery |
| `scripts/backtest_eth_16_combos.py` | Multi-asset validation |
| `scripts/simulate_regime_protocol.py` | Monte Carlo simulation |
| `docs/BEAR_PROTECTION_PROTOCOL.md` | This document |
