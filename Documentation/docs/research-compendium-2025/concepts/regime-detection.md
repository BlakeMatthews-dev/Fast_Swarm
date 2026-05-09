# Regime Detection

> **Hidden Markov Models and Market State Classification**
>
> Identifying market regimes to adapt trading strategies.

---

## Overview

Markets exhibit different behavioral regimes:
- **Bull vs Bear**: Trending up or down
- **High vs Low Volatility**: Range of price movements
- **Trending vs Mean-Reverting**: Momentum or oscillation

Different trading strategies work in different regimes. Detecting the current regime enables strategy adaptation.

---

## Source Papers

| Paper | Key Contribution | Path |
|-------|------------------|------|
| MacroHFT | Regime-aware agent behavior | [../papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) |
| HMM Finance | Classic HMM for market states | Various |
| Regime Switching | Markov regime models | Various |

---

## Regime Types

### Primary Classification

```
              HIGH VOLATILITY
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    │  BULL         │         BEAR  │
    │  VOLATILE     │      VOLATILE │
    │               │               │
────┼───────────────┼───────────────┼────
    │               │               │
    │  BULL         │         BEAR  │
    │  CALM         │         CALM  │
    │               │               │
    └───────────────┼───────────────┘
                    │
              LOW VOLATILITY

                SIDEWAYS
           (Center of grid)
```

### Regime Labels

| Regime | Trend | Volatility | Optimal Strategy |
|--------|-------|------------|------------------|
| `bull_volatile` | Up | High | Momentum with tight stops |
| `bull_calm` | Up | Low | Trend following, wide stops |
| `bear_volatile` | Down | High | Defensive, small positions |
| `bear_calm` | Down | Low | Mean reversion, selective |
| `sideways` | None | Variable | Mean reversion, range trading |

---

## Hidden Markov Model Approach

### Concept

HMM assumes:
1. There are hidden "states" (regimes) we can't directly observe
2. Each state has characteristic observable outputs (returns, volatility)
3. States transition according to probabilities

```
┌─────────────────────────────────────────────────────────────────┐
│                    HIDDEN LAYER (Regimes)                       │
│                                                                 │
│     ┌──────┐    P(B→Bull)    ┌──────┐                          │
│     │ BEAR │ ◄──────────────►│ BULL │                          │
│     └──┬───┘                 └──┬───┘                          │
│        │                        │                               │
│        │ P(emit|Bear)          │ P(emit|Bull)                  │
│        │                        │                               │
│        ▼                        ▼                               │
│   ┌─────────┐              ┌─────────┐                         │
│   │ Returns │              │ Returns │                         │
│   │ Vol     │              │ Vol     │                         │
│   └─────────┘              └─────────┘                         │
│                                                                 │
│                    OBSERVABLE LAYER                             │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
from hmmlearn import GaussianHMM
import numpy as np

class RegimeClassifier:
    """
    HMM-based market regime classifier.

    Paper Reference: MacroHFT
    "Regime detection enables adaptive strategy selection"
    """

    def __init__(self, n_regimes: int = 4):
        """
        Initialize classifier.

        Args:
            n_regimes: Number of hidden states (typically 4-5)
        """
        self.n_regimes = n_regimes
        self.model = GaussianHMM(
            n_components=n_regimes,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )
        self.regime_labels = {}
        self.is_fitted = False

    def fit(self, returns: np.ndarray, volatility: np.ndarray):
        """
        Fit HMM on historical data.

        Args:
            returns: Array of log returns
            volatility: Array of realized volatility (e.g., ATR)
        """
        # Combine features
        X = np.column_stack([returns, volatility])

        # Fit HMM
        self.model.fit(X)
        self.is_fitted = True

        # Label regimes based on learned parameters
        self._label_regimes()

    def _label_regimes(self):
        """
        Assign human-readable labels to learned regimes.

        Based on the mean returns and volatility of each state.
        """
        means = self.model.means_

        for i in range(self.n_regimes):
            ret_mean = means[i, 0]  # Return mean
            vol_mean = means[i, 1]  # Volatility mean

            # Determine trend
            if ret_mean > 0.001:
                trend = 'bull'
            elif ret_mean < -0.001:
                trend = 'bear'
            else:
                trend = 'sideways'

            # Determine volatility level
            vol_threshold = np.median([m[1] for m in means])
            vol_level = 'volatile' if vol_mean > vol_threshold else 'calm'

            if trend == 'sideways':
                self.regime_labels[i] = 'sideways'
            else:
                self.regime_labels[i] = f'{trend}_{vol_level}'

    def predict(self, returns: np.ndarray, volatility: np.ndarray) -> str:
        """
        Predict current regime.

        Args:
            returns: Recent returns (last N periods)
            volatility: Recent volatility

        Returns:
            Regime label (e.g., 'bull_volatile')
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        X = np.column_stack([returns, volatility])

        # Get most likely state for last observation
        hidden_states = self.model.predict(X)
        current_state = hidden_states[-1]

        return self.regime_labels[current_state]

    def predict_proba(self, returns: np.ndarray, volatility: np.ndarray) -> dict:
        """
        Get probability distribution over regimes.

        Returns:
            Dict mapping regime labels to probabilities
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        X = np.column_stack([returns, volatility])

        # Get state probabilities
        posteriors = self.model.predict_proba(X)
        current_probs = posteriors[-1]

        return {
            self.regime_labels[i]: prob
            for i, prob in enumerate(current_probs)
        }
```

---

## Simpler Approaches

For real-time classification without HMM complexity:

### Rule-Based Regime Detection

```python
def classify_regime_simple(
    price_data: pd.DataFrame,
    lookback: int = 20
) -> str:
    """
    Simple rule-based regime classification.

    Faster than HMM, easier to interpret.
    """
    # Calculate metrics
    returns = price_data['close'].pct_change()
    sma_20 = price_data['close'].rolling(20).mean()
    sma_50 = price_data['close'].rolling(50).mean()
    atr = calculate_atr(price_data, 14)
    atr_percentile = atr.rank(pct=True).iloc[-1]

    current_price = price_data['close'].iloc[-1]
    recent_return = returns.iloc[-lookback:].sum()

    # Trend detection
    if current_price > sma_20.iloc[-1] > sma_50.iloc[-1]:
        trend = 'bull'
    elif current_price < sma_20.iloc[-1] < sma_50.iloc[-1]:
        trend = 'bear'
    else:
        trend = 'sideways'

    # Volatility detection
    if atr_percentile > 0.7:
        volatility = 'volatile'
    else:
        volatility = 'calm'

    # Combine
    if trend == 'sideways':
        return 'sideways'
    else:
        return f'{trend}_{volatility}'
```

### Feature-Based Classification

```python
def extract_regime_features(price_data: pd.DataFrame) -> dict:
    """
    Extract features for regime classification.

    These features can feed into ML classifiers or rule systems.
    """
    close = price_data['close']
    returns = close.pct_change()

    features = {
        # Trend features
        'return_20d': returns.iloc[-20:].sum(),
        'return_5d': returns.iloc[-5:].sum(),
        'price_vs_sma20': close.iloc[-1] / close.rolling(20).mean().iloc[-1] - 1,
        'price_vs_sma50': close.iloc[-1] / close.rolling(50).mean().iloc[-1] - 1,
        'sma20_vs_sma50': (
            close.rolling(20).mean().iloc[-1] /
            close.rolling(50).mean().iloc[-1] - 1
        ),

        # Volatility features
        'volatility_20d': returns.iloc[-20:].std() * np.sqrt(252),
        'atr_percentile': calculate_atr_percentile(price_data),
        'range_avg': (
            (price_data['high'] - price_data['low']).iloc[-20:].mean() /
            close.iloc[-1]
        ),

        # Momentum features
        'rsi_14': calculate_rsi(close, 14),
        'macd_histogram': calculate_macd_histogram(close),

        # Volume features
        'volume_ratio': (
            price_data['volume'].iloc[-5:].mean() /
            price_data['volume'].iloc[-20:].mean()
        ),
    }

    return features
```

---

## Regime-Based Strategy Adaptation

### Strategy-Regime Matrix

```python
REGIME_STRATEGY_MAP = {
    'bull_volatile': {
        'position_size_multiplier': 0.8,   # Reduce size
        'stop_loss_atr_mult': 2.0,         # Wider stops
        'preferred_patterns': ['momentum', 'breakout'],
        'avoid_patterns': ['mean_reversion'],
        'max_hold_hours': 48,
    },
    'bull_calm': {
        'position_size_multiplier': 1.2,   # Increase size
        'stop_loss_atr_mult': 3.0,         # Wide stops
        'preferred_patterns': ['trend_following', 'dip_buying'],
        'avoid_patterns': [],
        'max_hold_hours': 168,             # Hold longer
    },
    'bear_volatile': {
        'position_size_multiplier': 0.5,   # Much smaller
        'stop_loss_atr_mult': 1.5,         # Tight stops
        'preferred_patterns': ['mean_reversion'],
        'avoid_patterns': ['momentum', 'breakout'],
        'max_hold_hours': 24,              # Quick exits
    },
    'bear_calm': {
        'position_size_multiplier': 0.7,
        'stop_loss_atr_mult': 2.0,
        'preferred_patterns': ['mean_reversion', 'support_bounce'],
        'avoid_patterns': ['trend_following'],
        'max_hold_hours': 72,
    },
    'sideways': {
        'position_size_multiplier': 0.6,
        'stop_loss_atr_mult': 1.5,
        'preferred_patterns': ['range_trading', 'mean_reversion'],
        'avoid_patterns': ['trend_following', 'breakout'],
        'max_hold_hours': 48,
    },
}


def adapt_to_regime(
    base_signal: TradeSignal,
    current_regime: str
) -> TradeSignal:
    """
    Adapt trading signal based on current regime.

    Paper Reference: MacroHFT
    "Regime-aware trading significantly improves risk-adjusted returns"
    """
    strategy_params = REGIME_STRATEGY_MAP.get(current_regime, {})

    # Adjust position size
    base_signal.position_size *= strategy_params.get(
        'position_size_multiplier', 1.0
    )

    # Check if pattern is preferred/avoided
    if base_signal.pattern_type in strategy_params.get('avoid_patterns', []):
        base_signal.confidence *= 0.5  # Reduce confidence

    if base_signal.pattern_type in strategy_params.get('preferred_patterns', []):
        base_signal.confidence *= 1.2  # Increase confidence

    # Adjust stop loss
    base_signal.stop_loss_atr_mult = strategy_params.get(
        'stop_loss_atr_mult', 2.0
    )

    return base_signal
```

---

## Agent Affinity by Regime

Agents develop affinity scores for different regimes based on their performance:

```python
def update_regime_affinity(
    agent: Agent,
    trade: FullTradeRecord,
    regime: str,
    alpha: float = 0.1
) -> None:
    """
    Update agent's regime affinity based on trade outcome.

    Affinity increases for profitable trades in a regime,
    decreases for losses.

    Paper Reference: MacroHFT - adaptive agent specialization
    """
    current_affinity = agent.regime_affinity.get(regime, 0.5)

    # Calculate performance signal
    if trade.pnl_pct > 0:
        # Win: increase affinity
        delta = alpha * min(trade.pnl_pct, 0.1)  # Cap at 10% impact
    else:
        # Loss: decrease affinity
        delta = -alpha * min(abs(trade.pnl_pct), 0.1)

    # Update with bounds
    new_affinity = current_affinity + delta
    new_affinity = max(0.0, min(1.0, new_affinity))

    agent.regime_affinity[regime] = new_affinity
```

---

## Regime Transition Detection

Detecting when the regime is changing:

```python
def detect_regime_transition(
    regime_history: list[str],
    confidence_history: list[float],
    window: int = 5
) -> tuple[bool, str]:
    """
    Detect if a regime transition is occurring.

    Returns:
        (is_transitioning, likely_new_regime)
    """
    if len(regime_history) < window:
        return False, regime_history[-1] if regime_history else 'unknown'

    recent = regime_history[-window:]
    current = regime_history[-1]

    # Check for instability (multiple regime changes)
    unique_regimes = len(set(recent))
    if unique_regimes >= 3:
        return True, 'transitioning'

    # Check for sustained change
    if all(r == recent[-1] for r in recent[-3:]) and recent[-1] != recent[0]:
        return True, recent[-1]

    # Check for declining confidence
    recent_conf = confidence_history[-window:]
    if all(c < 0.6 for c in recent_conf):
        return True, 'uncertain'

    return False, current
```

---

## Implementation Code

See [../code/regime_classifier.py](../code/regime_classifier.py) for production implementation.

---

## Related Files

- [../architecture/3-tier-execution.md](../architecture/3-tier-execution.md) - Regime in strategic tier
- [../papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) - MacroHFT paper
- [risk-management.md](risk-management.md) - Risk adaptation by regime

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
