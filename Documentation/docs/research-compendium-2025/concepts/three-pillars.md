# Three Pillars

> **Technical (40%) + Sentiment (30%) + Fundamental (30%)**
>
> Multi-modal signal fusion for robust trading decisions.

---

## Overview

The Three Pillars framework combines different types of market information:

1. **Technical Analysis**: Price patterns, indicators, volume
2. **Sentiment Analysis**: Market mood, fear/greed, social signals
3. **Fundamental Analysis**: On-chain data, tokenomics, macro factors

```
┌─────────────────────────────────────────────────────────────────┐
│                    THREE PILLARS FUSION                          │
│                                                                  │
│     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│     │  TECHNICAL   │  │  SENTIMENT   │  │ FUNDAMENTAL  │       │
│     │     40%      │  │     30%      │  │     30%      │       │
│     └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│            │                 │                 │                │
│            │    ┌────────────┼────────────┐    │                │
│            │    │            │            │    │                │
│            ▼    ▼            ▼            ▼    ▼                │
│     ┌─────────────────────────────────────────────────┐        │
│     │            WEIGHTED SIGNAL FUSION               │        │
│     │                                                 │        │
│     │  Final = 0.4*Tech + 0.3*Sent + 0.3*Fund        │        │
│     └───────────────────────┬─────────────────────────┘        │
│                             │                                   │
│                             ▼                                   │
│                    ┌────────────────┐                           │
│                    │ TRADE DECISION │                           │
│                    │  BUY/SELL/HOLD │                           │
│                    └────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Source Papers

| Paper | Key Contribution | Path |
|-------|------------------|------|
| MAT Three Pillars | Inter-modal fusion | [../papers/arxiv-2310.01232-mat-three-pillars.md](../papers/arxiv-2310.01232-mat-three-pillars.md) |
| TradingAgents | Role specialization | [../papers/arxiv-2412.20138-trading-agents.md](../papers/arxiv-2412.20138-trading-agents.md) |
| FinAgent | Multi-source integration | [../papers/arxiv-2512.02227-finagent.md](../papers/arxiv-2512.02227-finagent.md) |

---

## Pillar 1: Technical Analysis (40%)

### Components

| Category | Indicators | Weight |
|----------|------------|--------|
| **Trend** | EMA cross, ADX, Price vs SMAs | 35% |
| **Momentum** | RSI, MACD, Stochastic | 30% |
| **Volatility** | Bollinger Bands, ATR, Keltner | 20% |
| **Volume** | OBV, Volume Ratio, MFI | 15% |

### Signal Generation

```python
def calculate_technical_signal(
    price_data: pd.DataFrame,
    lookback: int = 20
) -> dict:
    """
    Generate technical analysis signal.

    Returns:
        {
            'signal': float,  # -1 to +1 (bearish to bullish)
            'confidence': float,  # 0 to 1
            'components': dict,  # Individual indicator signals
        }
    """
    close = price_data['close']
    high = price_data['high']
    low = price_data['low']
    volume = price_data['volume']

    components = {}

    # === TREND (35%) ===
    ema_20 = close.ewm(span=20).mean()
    ema_50 = close.ewm(span=50).mean()
    price_vs_ema = (close.iloc[-1] - ema_20.iloc[-1]) / ema_20.iloc[-1]
    ema_cross = (ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1]

    # Trend signal: -1 to +1
    trend_signal = np.tanh(price_vs_ema * 10 + ema_cross * 20)
    components['trend'] = trend_signal

    # === MOMENTUM (30%) ===
    rsi = calculate_rsi(close, 14)
    rsi_signal = (rsi - 50) / 50  # Normalize to -1 to +1

    macd_line, macd_signal, macd_hist = calculate_macd(close)
    macd_signal_val = np.tanh(macd_hist.iloc[-1] * 100)

    momentum_signal = 0.5 * rsi_signal + 0.5 * macd_signal_val
    components['momentum'] = momentum_signal

    # === VOLATILITY (20%) ===
    bb_upper, bb_middle, bb_lower = calculate_bollinger(close)
    bb_position = (close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])
    # At lower band = potential buy, at upper = potential sell
    vol_signal = (bb_position - 0.5) * -2  # Inverted: low = bullish
    components['volatility'] = vol_signal

    # === VOLUME (15%) ===
    obv = calculate_obv(close, volume)
    obv_trend = (obv.iloc[-1] - obv.iloc[-lookback]) / abs(obv.iloc[-lookback])
    vol_ratio = volume.iloc[-5:].mean() / volume.iloc[-20:].mean()

    # High volume confirms moves
    volume_signal = np.tanh(obv_trend) * min(vol_ratio, 2) / 2
    components['volume'] = volume_signal

    # === WEIGHTED COMBINATION ===
    final_signal = (
        0.35 * trend_signal +
        0.30 * momentum_signal +
        0.20 * vol_signal +
        0.15 * volume_signal
    )

    # Confidence based on agreement
    signals = [trend_signal, momentum_signal, vol_signal, volume_signal]
    agreement = sum(1 for s in signals if s * final_signal > 0) / len(signals)
    confidence = agreement * abs(final_signal)

    return {
        'signal': float(np.clip(final_signal, -1, 1)),
        'confidence': float(np.clip(confidence, 0, 1)),
        'components': components,
    }
```

---

## Pillar 2: Sentiment Analysis (30%)

### Components

| Source | Data Type | Weight |
|--------|-----------|--------|
| **Fear & Greed Index** | Aggregated sentiment | 35% |
| **Social Volume** | Twitter/Nostr mentions | 25% |
| **Funding Rate** | Market positioning | 20% |
| **Long/Short Ratio** | Exchange data | 20% |

### Signal Generation

```python
def calculate_sentiment_signal(
    fear_greed: int,            # 0-100
    funding_rate: float,        # Typically -0.1% to +0.1%
    long_short_ratio: float,    # Typically 0.5 to 2.0
    social_sentiment: float,    # -1 to +1 from NLP
    agent_traits: dict
) -> dict:
    """
    Generate sentiment analysis signal.

    Returns:
        {
            'signal': float,  # -1 to +1
            'confidence': float,
            'components': dict,
        }
    """
    components = {}

    # === FEAR & GREED (35%) ===
    # 0-25: Extreme Fear (potential buy)
    # 75-100: Extreme Greed (potential sell)
    fg_signal = (50 - fear_greed) / 50  # Inverted: fear = bullish
    components['fear_greed'] = fg_signal

    # === FUNDING RATE (20%) ===
    # Negative funding = shorts paying longs (potential bottom)
    # Positive funding = longs paying shorts (potential top)
    funding_signal = -np.tanh(funding_rate * 1000)
    components['funding'] = funding_signal

    # === LONG/SHORT RATIO (20%) ===
    # High ratio = crowded longs (contrarian bearish)
    # Low ratio = crowded shorts (contrarian bullish)
    ls_signal = -(long_short_ratio - 1) / 1  # Inverted
    ls_signal = np.clip(ls_signal, -1, 1)
    components['long_short'] = ls_signal

    # === SOCIAL SENTIMENT (25%) ===
    components['social'] = social_sentiment

    # === CONTRARIAN ADJUSTMENT ===
    # Agent trait #14: sentiment_contrarian
    # High = go against sentiment
    contrarian_factor = agent_traits.get('sentiment_contrarian', 0.5)

    # Base signal (non-contrarian)
    base_signal = (
        0.35 * fg_signal +
        0.20 * funding_signal +
        0.20 * ls_signal +
        0.25 * social_sentiment
    )

    # Apply contrarian factor
    # contrarian_factor 0.0 = follow sentiment
    # contrarian_factor 1.0 = go against sentiment
    if contrarian_factor > 0.5:
        # Partial to full inversion
        inversion = (contrarian_factor - 0.5) * 2
        final_signal = base_signal * (1 - inversion * 2)
    else:
        final_signal = base_signal

    # === SENTIMENT WEIGHT FROM TRAIT ===
    # Trait #12: sentiment_weight
    # Some agents care more about sentiment than others
    sentiment_weight = agent_traits.get('sentiment_weight', 0.5)

    # Confidence scales with how much agent values sentiment
    confidence = abs(final_signal) * sentiment_weight

    return {
        'signal': float(np.clip(final_signal, -1, 1)),
        'confidence': float(np.clip(confidence, 0, 1)),
        'components': components,
    }
```

---

## Pillar 3: Fundamental Analysis (30%)

### Components

| Category | Metrics | Weight |
|----------|---------|--------|
| **On-Chain** | Active addresses, NVT, SOPR | 40% |
| **Exchange Flows** | Inflow/outflow, reserve change | 30% |
| **Macro** | DXY, rates, liquidity | 30% |

### Signal Generation

```python
def calculate_fundamental_signal(
    nvt_ratio: float,           # Network Value to Transactions
    sopr: float,                # Spent Output Profit Ratio
    exchange_netflow: float,    # Positive = inflow (bearish)
    active_addresses_change: float,  # % change
    macro_conditions: dict      # DXY trend, rate expectations
) -> dict:
    """
    Generate fundamental analysis signal.

    Returns:
        {
            'signal': float,  # -1 to +1
            'confidence': float,
            'components': dict,
        }
    """
    components = {}

    # === NVT RATIO (20%) ===
    # High NVT = overvalued (bearish)
    # Low NVT = undervalued (bullish)
    # Typical range: 20-200
    nvt_signal = (100 - nvt_ratio) / 100
    nvt_signal = np.clip(nvt_signal, -1, 1)
    components['nvt'] = nvt_signal

    # === SOPR (20%) ===
    # SOPR > 1: coins moving in profit (potential selling pressure)
    # SOPR < 1: coins moving at loss (potential capitulation/bottom)
    sopr_signal = -(sopr - 1) * 5
    sopr_signal = np.clip(sopr_signal, -1, 1)
    components['sopr'] = sopr_signal

    # === EXCHANGE FLOWS (30%) ===
    # Positive netflow = coins moving to exchanges (bearish)
    # Negative netflow = coins leaving exchanges (bullish)
    flow_signal = -np.tanh(exchange_netflow * 10)
    components['exchange_flow'] = flow_signal

    # === ACTIVE ADDRESSES (10%) ===
    # Growing active addresses = adoption (bullish)
    addr_signal = np.tanh(active_addresses_change * 10)
    components['active_addresses'] = addr_signal

    # === MACRO (20%) ===
    dxy_trend = macro_conditions.get('dxy_trend', 0)  # -1 to +1
    rate_expectations = macro_conditions.get('rate_expectations', 0)

    # Strong dollar = risk-off (bearish for crypto)
    # Rising rates = tighter liquidity (bearish)
    macro_signal = -(0.6 * dxy_trend + 0.4 * rate_expectations)
    components['macro'] = macro_signal

    # === WEIGHTED COMBINATION ===
    final_signal = (
        0.20 * nvt_signal +
        0.20 * sopr_signal +
        0.30 * flow_signal +
        0.10 * addr_signal +
        0.20 * macro_signal
    )

    # Confidence based on data availability and agreement
    available_signals = [nvt_signal, sopr_signal, flow_signal, addr_signal, macro_signal]
    non_zero = [s for s in available_signals if abs(s) > 0.1]

    if len(non_zero) < 3:
        confidence = 0.3  # Low confidence with limited data
    else:
        agreement = sum(1 for s in non_zero if s * final_signal > 0) / len(non_zero)
        confidence = agreement * abs(final_signal)

    return {
        'signal': float(np.clip(final_signal, -1, 1)),
        'confidence': float(np.clip(confidence, 0, 1)),
        'components': components,
    }
```

---

## Three Pillars Fusion

### Static Weighting

```python
def fuse_three_pillars(
    technical: dict,
    sentiment: dict,
    fundamental: dict,
    weights: tuple[float, float, float] = (0.40, 0.30, 0.30)
) -> dict:
    """
    Combine three pillars into final signal.

    Default weights: Technical 40%, Sentiment 30%, Fundamental 30%

    Paper Reference: MAT Three Pillars
    "Inter-modal fusion captures complementary information"
    """
    tech_w, sent_w, fund_w = weights

    # Weighted signal
    final_signal = (
        tech_w * technical['signal'] +
        sent_w * sentiment['signal'] +
        fund_w * fundamental['signal']
    )

    # Confidence is minimum of confident pillars (weakest link)
    weighted_conf = (
        tech_w * technical['confidence'] +
        sent_w * sentiment['confidence'] +
        fund_w * fundamental['confidence']
    )

    # Agreement bonus
    signals = [technical['signal'], sentiment['signal'], fundamental['signal']]
    all_agree = all(s * final_signal > 0 for s in signals)
    if all_agree:
        weighted_conf *= 1.2  # 20% bonus for agreement

    return {
        'signal': float(np.clip(final_signal, -1, 1)),
        'confidence': float(np.clip(weighted_conf, 0, 1)),
        'pillars': {
            'technical': technical,
            'sentiment': sentiment,
            'fundamental': fundamental,
        },
        'all_pillars_agree': all_agree,
    }
```

### Dynamic Weighting (Regime-Based)

```python
REGIME_PILLAR_WEIGHTS = {
    'bull_volatile': (0.45, 0.35, 0.20),   # Technical + sentiment matter more
    'bull_calm': (0.35, 0.25, 0.40),       # Fundamentals matter in calm
    'bear_volatile': (0.50, 0.35, 0.15),   # Technical dominates
    'bear_calm': (0.30, 0.30, 0.40),       # Balanced
    'sideways': (0.40, 0.30, 0.30),        # Default
}


def fuse_three_pillars_dynamic(
    technical: dict,
    sentiment: dict,
    fundamental: dict,
    regime: str
) -> dict:
    """
    Combine three pillars with regime-dependent weights.

    Paper Reference: MAT Three Pillars
    "Adaptive weighting based on market conditions"
    """
    weights = REGIME_PILLAR_WEIGHTS.get(regime, (0.40, 0.30, 0.30))
    return fuse_three_pillars(technical, sentiment, fundamental, weights)
```

---

## Agent Specialization

TradingAgents paper suggests specialized roles:

```python
def get_agent_pillar_focus(agent_traits: dict) -> dict:
    """
    Determine which pillar an agent should focus on based on traits.

    Returns weight overrides for this agent.
    """
    # Trait #12: sentiment_weight (high = focus on sentiment)
    # Trait #11: lookback_preference (high = longer-term = fundamental)

    sent_weight = agent_traits.get('sentiment_weight', 0.5)
    lookback = agent_traits.get('lookback_preference', 0.5)

    if sent_weight > 0.7:
        # Sentiment specialist
        return {'technical': 0.30, 'sentiment': 0.50, 'fundamental': 0.20}
    elif lookback > 0.7:
        # Fundamental/long-term specialist
        return {'technical': 0.25, 'sentiment': 0.25, 'fundamental': 0.50}
    else:
        # Technical/short-term specialist (default)
        return {'technical': 0.45, 'sentiment': 0.25, 'fundamental': 0.30}
```

---

## Implementation Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                      MARKET DATA INPUT                           │
└───────────────────────────────┬──────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   TECHNICAL   │      │   SENTIMENT   │      │  FUNDAMENTAL  │
│   ANALYSIS    │      │   ANALYSIS    │      │   ANALYSIS    │
│               │      │               │      │               │
│ RSI, MACD,    │      │ Fear/Greed,   │      │ NVT, SOPR,    │
│ Trend, Volume │      │ Funding, L/S  │      │ Exchange Flow │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                       │                       │
        │  signal: 0.6          │  signal: 0.3          │  signal: 0.4
        │  conf: 0.7            │  conf: 0.5            │  conf: 0.6
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                                ▼
                ┌───────────────────────────┐
                │   REGIME-BASED WEIGHTS    │
                │                           │
                │   bull_volatile:          │
                │   Tech 45% Sent 35%       │
                │   Fund 20%                │
                └───────────────┬───────────┘
                                │
                                ▼
                ┌───────────────────────────┐
                │     WEIGHTED FUSION       │
                │                           │
                │  0.45*0.6 + 0.35*0.3      │
                │  + 0.20*0.4 = 0.455       │
                │                           │
                │  Final Signal: 0.455      │
                │  (Moderately Bullish)     │
                └───────────────────────────┘
```

---

## Implementation Code

See [../code/three_pillars_fusion.py](../code/three_pillars_fusion.py) for production implementation.

---

## Related Files

- [../architecture/5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md) - Pillars in agent decisions
- [../papers/arxiv-2310.01232-mat-three-pillars.md](../papers/arxiv-2310.01232-mat-three-pillars.md) - MAT paper
- [../meta/traits.md](../meta/traits.md) - Trait definitions

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
