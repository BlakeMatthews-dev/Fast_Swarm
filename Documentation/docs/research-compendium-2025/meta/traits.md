# Agent Traits

> **The 16 personality parameters that define agent behavior**
>
> All traits are floats in [0.0, 1.0] range.

---

## Overview

Agents have 16 heritable traits that influence their trading decisions. Traits:
- Are initialized randomly at spawn
- Mutate ±10% per generation during reproduction
- Some are derived from others (trait coupling)
- Evolve over time as successful agents are cloned

---

## Trait Categories

| Category | Traits | Description |
|----------|--------|-------------|
| **Core Risk** | 1-4 | Fundamental risk preferences |
| **Pattern Selection** | 5-7 | How patterns are evaluated |
| **Trade Execution** | 8-10 | Entry/exit behavior |
| **Technical** | 11 | Indicator preferences |
| **Sentiment** | 12-14 | Sentiment data usage |
| **Macro** | 15-16 | Market-wide factors |

---

## Detailed Trait Specifications

### Trait 1: Risk Tolerance

**Range:** 0.0 (conservative) to 1.0 (aggressive)

**Affects:**
- Base position size multiplier
- Acceptable drawdown levels
- Pattern selection by risk profile

**Formula:**
```python
position_multiplier = 0.5 + risk_tolerance * 0.75
# 0.0 -> 0.5x position
# 0.5 -> 0.875x position
# 1.0 -> 1.25x position
```

**Coupling:** Anchor trait. Drawdown sensitivity derived from this.

---

### Trait 2: Hold Duration Bias

**Range:** 0.0 (short-term) to 1.0 (long-term)

**Affects:**
- Preferred trade duration
- Exit timing patience
- Pattern timeframe preferences

**Formula:**
```python
target_hold_hours = 4 + hold_duration_bias * 164
# 0.0 -> 4 hours
# 0.5 -> 86 hours (~3.5 days)
# 1.0 -> 168 hours (1 week)
```

**Coupling:** Affects exit_aggression derivation.

---

### Trait 3: Volatility Seeking

**Range:** 0.0 (prefers calm) to 1.0 (seeks volatility)

**Affects:**
- Asset selection in volatile vs calm markets
- Pattern preference for high-volatility setups
- Regime affinity for volatile regimes

**Formula:**
```python
volatility_preference = volatility_seeking * 2  # 0-2 multiplier
# Applied to volatile regime affinity bonus
```

---

### Trait 4: Profit Target Greed

**Range:** 0.0 (takes profits early) to 1.0 (lets winners run)

**Affects:**
- Take profit distance from entry
- Trailing stop behavior
- Exit timing on winners

**Formula:**
```python
take_profit_atr_mult = 2 + profit_target_greed * 4
# 0.0 -> 2x ATR take profit
# 0.5 -> 4x ATR
# 1.0 -> 6x ATR
```

---

### Trait 5: Win Rate Preference

**Range:** 0.0 (few big wins) to 1.0 (many small wins)

**Affects:**
- Pattern selection by win rate vs profit factor
- Risk/reward ratio preferences

**Formula:**
```python
min_acceptable_winrate = 0.30 + win_rate_preference * 0.30
# 0.0 -> accept 30% win rate patterns
# 0.5 -> accept 45% win rate patterns
# 1.0 -> require 60% win rate patterns
```

---

### Trait 6: Drawdown Sensitivity ⚠️ DERIVED

**Range:** 0.0 (pain tolerant) to 1.0 (pain averse)

**Derived From:** `1 - risk_tolerance * 0.5`

**Affects:**
- Position reduction during drawdowns
- Circuit breaker trigger sensitivity
- Stop loss tightness

**Formula:**
```python
drawdown_sensitivity = 1 - risk_tolerance * 0.5
# risk_tolerance 0.0 -> sensitivity 1.0
# risk_tolerance 0.5 -> sensitivity 0.75
# risk_tolerance 1.0 -> sensitivity 0.5
```

---

### Trait 7: Momentum vs Reversion

**Range:** 0.0 (mean reversion) to 1.0 (momentum/trend)

**Affects:**
- Pattern type preferences
- Entry signal interpretation
- Bull/bear camp assignment in debates

**Formula:**
```python
if momentum_vs_reversion > 0.6:
    # Prefer momentum patterns
    pattern_boost['breakout'] = 1.2
    pattern_boost['trend_following'] = 1.2
elif momentum_vs_reversion < 0.4:
    # Prefer mean reversion
    pattern_boost['mean_reversion'] = 1.2
    pattern_boost['dip_buying'] = 1.2
```

---

### Trait 8: Stop Loss Tightness ⚠️ DERIVED

**Range:** 0.0 (wide stops) to 1.0 (tight stops)

**Derived From:** `drawdown_sensitivity * 0.8`

**Affects:**
- ATR multiplier for stop loss placement

**Formula:**
```python
stop_loss_tightness = drawdown_sensitivity * 0.8

stop_loss_atr_mult = 3.0 - stop_loss_tightness * 2.0
# 0.0 -> 3.0x ATR (wide)
# 0.5 -> 2.0x ATR
# 1.0 -> 1.0x ATR (tight)
```

---

### Trait 9: Entry Aggression

**Range:** 0.0 (waits for perfect entry) to 1.0 (chases entries)

**Affects:**
- Slippage tolerance
- Entry signal threshold
- Willingness to market order vs limit

**Formula:**
```python
entry_confidence_threshold = 0.7 - entry_aggression * 0.3
# 0.0 -> requires 0.70 confidence
# 0.5 -> requires 0.55 confidence
# 1.0 -> requires 0.40 confidence
```

---

### Trait 10: Exit Aggression ⚠️ DERIVED

**Range:** 0.0 (patient exits) to 1.0 (quick exits)

**Derived From:** `(1 - hold_duration_bias) * 0.6 + 0.2`

**Affects:**
- Exit signal sensitivity
- Partial profit taking behavior
- Trailing stop tightness

**Formula:**
```python
exit_aggression = (1 - hold_duration_bias) * 0.6 + 0.2
# hold_duration 0.0 -> exit_aggression 0.8 (quick)
# hold_duration 0.5 -> exit_aggression 0.5
# hold_duration 1.0 -> exit_aggression 0.2 (patient)
```

---

### Trait 11: Lookback Preference

**Range:** 0.0 (short lookbacks) to 1.0 (long lookbacks)

**Affects:**
- RSI period selection
- Moving average periods
- Pattern timeframe preference

**Formula:**
```python
rsi_period = int(7 + lookback_preference * 21)
# 0.0 -> RSI-7
# 0.5 -> RSI-17
# 1.0 -> RSI-28

ema_fast = int(5 + lookback_preference * 15)
ema_slow = int(20 + lookback_preference * 30)
```

---

### Trait 12: Sentiment Weight

**Range:** 0.0 (ignores sentiment) to 1.0 (sentiment-focused)

**Affects:**
- Weight of sentiment pillar in Three Pillars fusion
- Fear & Greed influence on decisions

**Formula:**
```python
sentiment_pillar_weight = 0.15 + sentiment_weight * 0.30
# 0.0 -> 15% weight to sentiment
# 0.5 -> 30% weight
# 1.0 -> 45% weight
```

---

### Trait 13: News Reactivity

**Range:** 0.0 (ignores news) to 1.0 (news-driven)

**Affects:**
- Response speed to news events
- Position adjustment on news
- Confidence boost/reduction from news

**Formula:**
```python
news_adjustment_factor = news_reactivity * 0.5
# How much news affects confidence
```

---

### Trait 14: Sentiment Contrarian

**Range:** 0.0 (follows crowd) to 1.0 (contrarian)

**Affects:**
- Interpretation of Fear & Greed
- Funding rate signal inversion
- Social sentiment signal direction

**Formula:**
```python
if sentiment_contrarian > 0.5:
    inversion = (sentiment_contrarian - 0.5) * 2
    sentiment_signal *= (1 - inversion * 2)
# 0.5 -> no inversion
# 0.75 -> 50% inverted
# 1.0 -> fully inverted
```

---

### Trait 15: Funding Rate Sensitivity

**Range:** 0.0 (ignores funding) to 1.0 (funding-focused)

**Affects:**
- Weight of funding rate in sentiment pillar
- Trading decisions near extreme funding

**Formula:**
```python
funding_weight = funding_rate_sensitivity * 0.30
# 0.0 -> 0% weight
# 1.0 -> 30% weight in sentiment
```

---

### Trait 16: Correlation Awareness

**Range:** 0.0 (ignores correlation) to 1.0 (correlation-focused)

**Affects:**
- Portfolio correlation limits
- Diversification requirements
- Correlated position sizing

**Formula:**
```python
max_correlated_exposure = 0.80 - correlation_awareness * 0.40
# 0.0 -> allow 80% correlated exposure
# 0.5 -> allow 60%
# 1.0 -> allow 40%
```

---

## Trait Coupling Summary

Three traits are derived from anchor traits to prevent contradictions:

| Derived Trait | Formula | Anchor Trait |
|---------------|---------|--------------|
| drawdown_sensitivity (6) | `1 - risk_tolerance * 0.5` | risk_tolerance (1) |
| stop_loss_tightness (8) | `drawdown_sensitivity * 0.8` | drawdown_sensitivity (6) |
| exit_aggression (10) | `(1 - hold_duration_bias) * 0.6 + 0.2` | hold_duration_bias (2) |

This ensures:
- Risk-tolerant agents aren't overly drawdown-sensitive
- Drawdown-sensitive agents use appropriately tight stops
- Long-term holders don't exit aggressively

---

## Evolution Mechanics

### Mutation

Each trait mutates with:
- **Rate:** 10% probability per trait per generation
- **Strength:** ±10% maximum change

```python
def mutate_trait(value: float) -> float:
    if random.random() < 0.10:  # 10% mutation rate
        delta = random.uniform(-0.10, 0.10)
        return max(0.0, min(1.0, value + delta))
    return value
```

### Selection Pressure

Traits evolve toward values that improve fitness:
- Successful agents get cloned
- Unsuccessful agents retire
- Over generations, beneficial trait combinations emerge

---

## Trait Profiles

### The Momentum Trader

```yaml
risk_tolerance: 0.7
hold_duration_bias: 0.3
volatility_seeking: 0.8
momentum_vs_reversion: 0.9
entry_aggression: 0.7
```

### The Value Investor

```yaml
risk_tolerance: 0.4
hold_duration_bias: 0.9
volatility_seeking: 0.2
momentum_vs_reversion: 0.1
sentiment_contrarian: 0.8
lookback_preference: 0.9
```

### The Scalper

```yaml
risk_tolerance: 0.5
hold_duration_bias: 0.1
entry_aggression: 0.9
news_reactivity: 0.3
lookback_preference: 0.1
```

---

## Code Implementation

See [../code/affinity_mutation.py](../code/affinity_mutation.py) for trait mutation and coupling implementation.

---

## Related Files

- [../architecture/5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md) - Agents in hierarchy
- [../concepts/evolutionary-systems.md](../concepts/evolutionary-systems.md) - Trait evolution
- [glossary.md](glossary.md) - Term definitions

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial traits document |
