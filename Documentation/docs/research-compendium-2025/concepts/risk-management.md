# Risk Management

> **Stop Losses, Circuit Breakers, and Drawdown Control**
>
> Protecting capital while allowing profitable trades to develop.

---

## Overview

Risk management operates at multiple levels:
1. **Trade Level**: Stop losses, take profits
2. **Daily Level**: Circuit breakers, loss limits
3. **Portfolio Level**: Correlation limits, total exposure

---

## Source Papers

| Paper | Key Contribution | Path |
|-------|------------------|------|
| Stop-Loss Papers | Optimal stop placement | Various |
| MASA | Multi-agent risk parity | [../papers/arxiv-2402.00515-masa.md](../papers/arxiv-2402.00515-masa.md) |
| MacroHFT | Regime-aware risk | [../papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) |

---

## Stop Loss Strategies

### ATR-Based Stops

Most robust approach - adapts to market volatility.

```python
def calculate_atr_stop(
    entry_price: float,
    atr: float,
    direction: str,
    atr_multiplier: float = 2.0
) -> float:
    """
    Calculate stop loss based on Average True Range.

    ATR naturally adapts to volatility:
    - High volatility = wider stops
    - Low volatility = tighter stops

    Paper Reference: Various stop-loss studies
    """
    stop_distance = atr * atr_multiplier

    if direction == 'long':
        return entry_price - stop_distance
    else:  # short
        return entry_price + stop_distance


def calculate_dynamic_atr_multiplier(
    agent_traits: dict,
    regime: str,
    signal_confidence: float
) -> float:
    """
    Adjust ATR multiplier based on context.

    Trait #8 (stop_loss_tightness): Higher = tighter stops
    Regime: Volatile regimes need wider stops
    Confidence: Higher confidence = can afford tighter stops
    """
    # Base multiplier from trait
    # stop_loss_tightness 0.0 = 3.0x ATR (wide)
    # stop_loss_tightness 1.0 = 1.0x ATR (tight)
    base = 3.0 - (agent_traits['stop_loss_tightness'] * 2.0)

    # Regime adjustment
    regime_adj = {
        'bull_volatile': 1.3,
        'bear_volatile': 1.5,
        'bull_calm': 0.8,
        'bear_calm': 1.0,
        'sideways': 1.0,
    }.get(regime, 1.0)

    # Confidence adjustment
    # Low confidence = wider stops (more room for error)
    conf_adj = 1.5 - (signal_confidence * 0.5)

    return base * regime_adj * conf_adj
```

### Percentage-Based Stops

Simpler but less adaptive:

```python
def calculate_percentage_stop(
    entry_price: float,
    direction: str,
    stop_pct: float = 0.02  # 2% default
) -> float:
    """
    Fixed percentage stop loss.

    Simple but doesn't adapt to volatility.
    Use ATR-based for production.
    """
    if direction == 'long':
        return entry_price * (1 - stop_pct)
    else:
        return entry_price * (1 + stop_pct)
```

### Chandelier Exit (Trailing Stop)

```python
def chandelier_exit(
    high_since_entry: float,
    low_since_entry: float,
    atr: float,
    direction: str,
    multiplier: float = 3.0
) -> float:
    """
    Trailing stop based on highest high / lowest low.

    Locks in profits as trade moves in our favor.

    Paper Reference: Classic technical analysis
    """
    if direction == 'long':
        # Trail below highest high
        return high_since_entry - (atr * multiplier)
    else:
        # Trail above lowest low
        return low_since_entry + (atr * multiplier)
```

---

## Circuit Breakers

### Daily Loss Limits

```python
@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""

    # Loss thresholds (as fraction of portfolio)
    warning_threshold: float = 0.03     # 3% - reduce size
    caution_threshold: float = 0.05     # 5% - close new positions
    halt_threshold: float = 0.08        # 8% - close all positions
    emergency_threshold: float = 0.10   # 10% - halt trading 24h

    # Cooldown periods
    warning_cooldown_hours: int = 2
    caution_cooldown_hours: int = 8
    halt_cooldown_hours: int = 24


class CircuitBreaker:
    """
    Portfolio-level circuit breaker system.

    Paper Reference: Risk management best practices
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.daily_pnl = 0.0
        self.status = 'normal'
        self.last_trigger_time = None

    def update(self, trade_pnl_pct: float) -> str:
        """
        Update with new trade P&L and return current status.

        Returns: 'normal', 'warning', 'caution', 'halt', 'emergency'
        """
        self.daily_pnl += trade_pnl_pct

        if self.daily_pnl <= -self.config.emergency_threshold:
            self.status = 'emergency'
            self._trigger_emergency()
        elif self.daily_pnl <= -self.config.halt_threshold:
            self.status = 'halt'
            self._trigger_halt()
        elif self.daily_pnl <= -self.config.caution_threshold:
            self.status = 'caution'
        elif self.daily_pnl <= -self.config.warning_threshold:
            self.status = 'warning'
        else:
            self.status = 'normal'

        return self.status

    def check_can_trade(self) -> tuple[bool, str]:
        """
        Check if new trades are allowed.

        Returns:
            (can_trade, reason)
        """
        if self.status == 'emergency':
            return False, "Emergency halt - trading suspended 24h"
        elif self.status == 'halt':
            return False, "Halt - daily loss limit reached"
        elif self.status == 'caution':
            return False, "Caution - no new positions"
        else:
            return True, "OK"

    def get_position_multiplier(self) -> float:
        """
        Get position size multiplier based on status.
        """
        multipliers = {
            'normal': 1.0,
            'warning': 0.5,
            'caution': 0.0,  # No new positions
            'halt': 0.0,
            'emergency': 0.0,
        }
        return multipliers.get(self.status, 0.0)
```

### Consecutive Loss Tracking

```python
class LossStreakTracker:
    """
    Track consecutive losses and adjust behavior.

    Paper Reference: Behavioral finance, risk management
    """

    def __init__(self, max_consecutive: int = 5):
        self.consecutive_losses = 0
        self.max_consecutive = max_consecutive

    def record_trade(self, pnl: float) -> dict:
        """
        Record trade outcome and return guidance.

        Returns:
            {
                'consecutive_losses': int,
                'action': str,  # 'continue', 'reduce', 'pause'
                'size_multiplier': float,
            }
        """
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self.consecutive_losses >= self.max_consecutive:
            return {
                'consecutive_losses': self.consecutive_losses,
                'action': 'pause',
                'size_multiplier': 0.0,
            }
        elif self.consecutive_losses >= 3:
            return {
                'consecutive_losses': self.consecutive_losses,
                'action': 'reduce',
                'size_multiplier': 0.5,
            }
        else:
            return {
                'consecutive_losses': self.consecutive_losses,
                'action': 'continue',
                'size_multiplier': 1.0,
            }
```

---

## Drawdown Management

### Maximum Drawdown Tracking

```python
def calculate_drawdown(
    equity_curve: list[float]
) -> tuple[float, float, int]:
    """
    Calculate current and maximum drawdown.

    Returns:
        (current_drawdown, max_drawdown, days_in_drawdown)
    """
    peak = equity_curve[0]
    max_dd = 0.0
    current_dd = 0.0
    days_in_dd = 0

    for equity in equity_curve:
        if equity > peak:
            peak = equity
            days_in_dd = 0
        else:
            days_in_dd += 1

        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
        current_dd = dd

    return current_dd, max_dd, days_in_dd


class DrawdownManager:
    """
    Manage trading behavior based on drawdown state.
    """

    def __init__(
        self,
        warning_dd: float = 0.10,    # 10%
        serious_dd: float = 0.15,    # 15%
        critical_dd: float = 0.20,   # 20%
    ):
        self.warning_dd = warning_dd
        self.serious_dd = serious_dd
        self.critical_dd = critical_dd

    def get_risk_adjustment(
        self,
        current_dd: float,
        days_in_dd: int
    ) -> dict:
        """
        Get risk adjustments based on drawdown state.

        Returns:
            {
                'status': str,
                'position_mult': float,
                'new_trades_allowed': bool,
                'guidance': str,
            }
        """
        if current_dd >= self.critical_dd:
            return {
                'status': 'critical',
                'position_mult': 0.0,
                'new_trades_allowed': False,
                'guidance': 'Critical drawdown - halt trading, review strategy',
            }
        elif current_dd >= self.serious_dd:
            return {
                'status': 'serious',
                'position_mult': 0.25,
                'new_trades_allowed': False,
                'guidance': 'Serious drawdown - close positions opportunistically',
            }
        elif current_dd >= self.warning_dd:
            return {
                'status': 'warning',
                'position_mult': 0.5,
                'new_trades_allowed': True,
                'guidance': 'Warning drawdown - reduce size, tighten stops',
            }
        else:
            return {
                'status': 'normal',
                'position_mult': 1.0,
                'new_trades_allowed': True,
                'guidance': 'Normal operations',
            }
```

---

## Portfolio Risk Limits

### Correlation-Based Limits

```python
def check_correlation_limit(
    new_position: str,
    current_positions: dict[str, float],
    correlation_matrix: pd.DataFrame,
    max_correlated_exposure: float = 0.60
) -> tuple[bool, float]:
    """
    Check if new position would exceed correlated exposure limit.

    Highly correlated positions compound risk - limit total exposure.

    Returns:
        (is_allowed, max_size_allowed)
    """
    if new_position not in correlation_matrix.index:
        return True, 1.0  # Unknown correlation, allow

    # Calculate correlated exposure
    correlated_exp = 0.0
    for asset, size in current_positions.items():
        if asset in correlation_matrix.index:
            corr = abs(correlation_matrix.loc[new_position, asset])
            if corr > 0.5:  # Significant correlation
                correlated_exp += size * corr

    # How much room left?
    remaining = max_correlated_exposure - correlated_exp

    if remaining <= 0:
        return False, 0.0
    else:
        return True, remaining
```

### Value at Risk (VaR) Limit

```python
def calculate_portfolio_var(
    positions: dict[str, float],
    returns_data: pd.DataFrame,
    confidence: float = 0.95
) -> float:
    """
    Calculate portfolio Value at Risk.

    VaR = how much we could lose with X% confidence

    Paper Reference: Standard risk management
    """
    # Calculate portfolio returns
    portfolio_returns = sum(
        returns_data[asset] * weight
        for asset, weight in positions.items()
        if asset in returns_data.columns
    )

    # VaR at confidence level
    var = np.percentile(portfolio_returns, (1 - confidence) * 100)

    return abs(var)


def check_var_limit(
    positions: dict[str, float],
    returns_data: pd.DataFrame,
    max_var: float = 0.02  # 2% daily VaR limit
) -> tuple[bool, float]:
    """
    Check if positions are within VaR limit.

    Returns:
        (within_limit, current_var)
    """
    current_var = calculate_portfolio_var(positions, returns_data)
    return current_var <= max_var, current_var
```

---

## Agent Trait Integration

Risk management is influenced by agent traits:

| Trait | Effect |
|-------|--------|
| `risk_tolerance` | Higher = accept larger drawdowns |
| `drawdown_sensitivity` | Higher = reduce faster in drawdown |
| `stop_loss_tightness` | Higher = tighter stops (less room) |
| `exit_aggression` | Higher = quicker to cut losses |

```python
def trait_adjusted_stop_loss(
    base_stop_distance: float,
    agent_traits: dict,
    current_drawdown: float
) -> float:
    """
    Adjust stop loss distance based on traits and state.
    """
    # Tightness from trait
    # 0.0 = wide stops (base * 1.5)
    # 1.0 = tight stops (base * 0.5)
    tightness = agent_traits['stop_loss_tightness']
    trait_factor = 1.5 - (tightness * 1.0)

    # Drawdown adjustment
    # In drawdown + sensitive = tighter stops
    if current_drawdown > 0.05:
        dd_sensitivity = agent_traits['drawdown_sensitivity']
        dd_factor = 1.0 - (dd_sensitivity * current_drawdown * 2)
    else:
        dd_factor = 1.0

    return base_stop_distance * trait_factor * dd_factor
```

---

## Risk Management Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                      TRADE SIGNAL RECEIVED                       │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  CHECK CIRCUIT BREAKERS                          │
│  - Daily loss status                                             │
│  - Consecutive loss count                                        │
│  - If triggered: REJECT trade                                    │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                   CHECK DRAWDOWN STATE                           │
│  - Current drawdown level                                        │
│  - Days in drawdown                                              │
│  - Adjust position size multiplier                               │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                CHECK PORTFOLIO LIMITS                            │
│  - Total exposure                                                │
│  - Correlated exposure                                           │
│  - VaR limit                                                     │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                   CALCULATE STOP LOSS                            │
│  - ATR-based stop                                                │
│  - Trait adjustment                                              │
│  - Regime adjustment                                             │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      EXECUTE TRADE                               │
│  With all risk parameters applied                                │
└──────────────────────────────────────────────────────────────────┘
```

---

## Related Files

- [position-sizing.md](position-sizing.md) - Kelly criterion
- [../architecture/3-tier-execution.md](../architecture/3-tier-execution.md) - Execution tier safety
- [../meta/traits.md](../meta/traits.md) - Trait definitions

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
