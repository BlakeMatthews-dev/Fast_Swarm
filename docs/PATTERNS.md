# Fast_Swarm Patterns

**Definition**: Trading rules with entry/exit conditions in JSON format
**Discovery**: Chaos Analysis (fully wired), Genesis seeds
**Ranking**: 5-Tier Quintile system with regime-based fitness

---

## Pattern Model

```python
class Pattern(SQLModel, table=True):
    # Identity
    pattern_id: str = Field(primary_key=True)
    name: str
    origin: str  # 'chaos_analysis', 'genesis', 'mutation'

    # Configuration
    symbol: str  # BTC, ETH, SOL, etc.
    timeframe: str  # 1h, 6h, 1d
    conditions: Dict[str, Any] = Field(sa_column=Column(JSONB))

    # Performance
    fitness_score: float = Field(default=0.0)
    fitness_by_regime: Dict[str, float] = Field(default={}, sa_column=Column(JSONB))
    tier: int = Field(default=2)  # 0-4 quintile

    # Status
    is_active: bool = Field(default=True)
    backtest_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## Pattern Conditions Format

Patterns use JSON-based indicator conditions:

```json
{
  "entry": {
    "operator": "AND",
    "conditions": [
      {"indicator": "rsi_14", "comparison": "<", "value": 30},
      {"indicator": "close", "comparison": ">", "value": "sma_20"},
      {"indicator": "macd", "comparison": ">", "value": 0}
    ]
  },
  "exit": {
    "operator": "OR",
    "conditions": [
      {"indicator": "rsi_14", "comparison": ">", "value": 70},
      {"indicator": "pnl_pct", "comparison": ">", "value": 0.08},
      {"indicator": "pnl_pct", "comparison": "<", "value": -0.05}
    ]
  },
  "filters": {
    "min_volume": 1000000,
    "session": "asian",
    "regime": ["bull", "chop"]
  }
}
```

### Supported Indicators

| Indicator | Description | Example Condition |
|-----------|-------------|-------------------|
| `rsi_14` | 14-period RSI | `{"indicator": "rsi_14", "comparison": "<", "value": 30}` |
| `sma_20` | 20-period SMA | `{"indicator": "close", "comparison": ">", "value": "sma_20"}` |
| `sma_50` | 50-period SMA | Cross detection |
| `ema_12` | 12-period EMA | MACD component |
| `ema_26` | 26-period EMA | MACD component |
| `macd` | MACD line | Momentum direction |
| `macd_signal` | MACD signal line | Crossover detection |
| `bb_upper` | Bollinger upper | Overbought detection |
| `bb_lower` | Bollinger lower | Oversold detection |
| `atr_14` | 14-period ATR | Volatility filter |
| `aroon_osc` | Aroon Oscillator | Trend strength |
| `volume` | Current volume | Activity filter |
| `close` | Close price | Price comparisons |
| `pnl_pct` | Current P&L % | Exit conditions |

### Comparison Operators

| Operator | Description |
|----------|-------------|
| `>` | Greater than |
| `<` | Less than |
| `>=` | Greater than or equal |
| `<=` | Less than or equal |
| `==` | Equal to |
| `crosses_above` | Crossover detection |
| `crosses_below` | Crossunder detection |

---

## Pattern Slot System

Agents use a **dual-tier pattern system**:

### Base Patterns (2-5 slots)
- **Permanent** assignments
- Gained through evolution (parent inheritance)
- Only changed when agent is promoted/demoted
- Core identity of the agent

### Situational Patterns (0-5 slots)
- **Weekly rotation**
- Swapped based on market regime
- Tested on recent data before activation
- Allow regime adaptation without losing core identity

```python
class AgentPatternConfig:
    """Agent's pattern slot configuration."""

    # Base patterns - permanent core identity
    base_patterns: List[str] = []  # 2-5 pattern IDs
    base_weights: Dict[str, float] = {}  # Weight per pattern

    # Situational patterns - weekly rotation
    situational_patterns: List[str] = []  # 0-5 pattern IDs
    situational_weights: Dict[str, float] = {}

    # Slot limits grow with tier
    @property
    def max_base_slots(self) -> int:
        return 2 + self.tier  # Tier 0 = 2, Tier 4 = 6

    @property
    def max_situational_slots(self) -> int:
        return self.tier  # Tier 0 = 0, Tier 4 = 4
```

### Slot Growth by Tier

| Tier | Base Slots | Situational Slots | Total |
|------|------------|-------------------|-------|
| 0 | 2 | 0 | 2 |
| 1 | 3 | 1 | 4 |
| 2 | 4 | 2 | 6 |
| 3 | 5 | 3 | 8 |
| 4 | 6 | 4 | 10 |

---

## Pattern Discovery: Chaos Analysis

The primary (and currently only fully wired) pattern discovery method:

### How It Works

1. **Random Window Selection**: Pick random historical periods
2. **Indicator Combination**: Generate random indicator conditions
3. **Quick Backtest**: Test pattern on the window
4. **Survival**: Keep patterns that show promise (positive expectancy)
5. **Refinement**: Successful patterns get more testing

```python
async def chaos_pattern_discovery():
    """
    Discover patterns through randomized exploration.

    Philosophy: Signal emerges from noise - the randomness IS the point.
    """
    for _ in range(PATTERNS_PER_CYCLE):
        # Generate random conditions
        entry_conditions = generate_random_conditions(
            indicator_pool=AVAILABLE_INDICATORS,
            num_conditions=random.randint(2, 4)
        )

        exit_conditions = generate_exit_conditions(
            stop_loss_range=(-0.03, -0.07),
            take_profit_range=(0.05, 0.12)
        )

        pattern = Pattern(
            pattern_id=generate_id(),
            name=generate_pattern_name(),
            origin='chaos_analysis',
            conditions={
                'entry': entry_conditions,
                'exit': exit_conditions
            }
        )

        # Quick fitness test
        fitness = await quick_backtest(pattern)

        # Only keep promising patterns
        if fitness > CHAOS_THRESHOLD:
            await save_pattern(pattern)
```

### Chaos Discovery Loop

Runs every 6 hours in the background:

```python
# Main.py lifespan
asyncio.create_task(pattern_discovery_loop())  # Every 6 hours
asyncio.create_task(pattern_backtest_loop())   # Every 10 minutes
```

---

## Pattern Performance Tracking

### Regime-Based Fitness

Patterns are evaluated separately per market regime:

```python
pattern.fitness_by_regime = {
    "bull": 0.85,   # Great in uptrends
    "bear": 0.32,   # Poor in downtrends
    "chop": 0.61,   # Decent in sideways volatile
    "flat": 0.45    # Below average in quiet markets
}
```

### Divergence Alerts

Monitor live vs backtest performance divergence:

```python
class DivergenceAlert:
    """Alert when pattern performance diverges from expectations."""

    pattern_id: str
    expected_win_rate: float  # From backtests
    actual_win_rate: float    # From recent live/paper trades
    divergence_pct: float     # (actual - expected) / expected
    alert_level: str          # 'warning', 'critical'

def check_divergence(pattern: Pattern, recent_trades: List[Trade]) -> Optional[DivergenceAlert]:
    """
    Check if pattern is diverging from expected performance.

    Triggers:
    - Warning: > 20% divergence
    - Critical: > 40% divergence
    """
    if len(recent_trades) < 20:
        return None  # Need more data

    actual_win_rate = sum(1 for t in recent_trades if t.pnl > 0) / len(recent_trades)
    expected_win_rate = pattern.expected_win_rate

    divergence = abs(actual_win_rate - expected_win_rate) / expected_win_rate

    if divergence > 0.4:
        return DivergenceAlert(
            pattern_id=pattern.pattern_id,
            expected_win_rate=expected_win_rate,
            actual_win_rate=actual_win_rate,
            divergence_pct=divergence,
            alert_level='critical'
        )
    elif divergence > 0.2:
        return DivergenceAlert(..., alert_level='warning')

    return None
```

---

## Top Performing Pattern Characteristics

From evolution run analysis:

### Winning Entry Conditions
- **AroonOsc > 50**: Bullish Aroon (appears in top patterns)
- **EMA crossovers (13/55)**: With MACD confirmation
- **RSI < 35**: Oversold entries in uptrends
- **Session timing**: Asian session filter effective

### Winning Exit Conditions
- **Stop loss**: -3% to -7% (tight stops)
- **Take profit**: +8% to +12% (let winners run)
- **Trailing stops**: After +5% gain, trail at 2%

### Example High-Performing Pattern

```json
{
  "name": "Alpha Break v344",
  "entry": {
    "operator": "AND",
    "conditions": [
      {"indicator": "aroon_osc", "comparison": ">", "value": 50},
      {"indicator": "ema_13", "comparison": "crosses_above", "value": "ema_55"},
      {"indicator": "macd", "comparison": ">", "value": 0}
    ]
  },
  "exit": {
    "operator": "OR",
    "conditions": [
      {"indicator": "pnl_pct", "comparison": ">", "value": 0.10},
      {"indicator": "pnl_pct", "comparison": "<", "value": -0.05},
      {"indicator": "aroon_osc", "comparison": "<", "value": 0}
    ]
  },
  "stats": {
    "trades": 302,
    "avg_pnl": "+4.39%",
    "win_rate": "59.3%",
    "avg_confidence": 0.72
  }
}
```

---

## Pattern API Endpoints

### List Patterns

```bash
GET /patterns?is_active=true&tier=4&limit=20

Response:
{
    "patterns": [
        {
            "pattern_id": "chaos-abc123",
            "name": "Alpha Break v344",
            "origin": "chaos_analysis",
            "symbol": "BTC",
            "timeframe": "1h",
            "fitness_score": 0.78,
            "tier": 4,
            "is_active": true
        }
    ],
    "total": 150
}
```

### Get Pattern Details

```bash
GET /patterns/{pattern_id}

Response:
{
    "pattern_id": "chaos-abc123",
    "name": "Alpha Break v344",
    "origin": "chaos_analysis",
    "conditions": {...},
    "fitness_score": 0.78,
    "fitness_by_regime": {
        "bull": 0.85,
        "bear": 0.45,
        "chop": 0.72,
        "flat": 0.61
    },
    "tier": 4,
    "backtest_count": 47,
    "is_active": true
}
```

---

## Pattern Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    PATTERN LIFECYCLE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. DISCOVERY                                                    │
│     └─ Chaos Analysis generates random patterns                 │
│                                                                  │
│  2. VALIDATION                                                   │
│     └─ Quick backtest on random windows                         │
│     └─ Patterns with positive expectancy survive                │
│                                                                  │
│  3. ASSIGNMENT                                                   │
│     └─ Assigned to agents as base or situational patterns       │
│     └─ Weights set based on regime compatibility                │
│                                                                  │
│  4. TESTING                                                      │
│     └─ Continuous backtesting across windows                    │
│     └─ Fitness updated per regime                               │
│                                                                  │
│  5. PROMOTION/DEMOTION                                          │
│     └─ Tier adjusts based on quintile ranking                   │
│     └─ Top patterns get more agent assignments                  │
│                                                                  │
│  6. RETIREMENT                                                   │
│     └─ Alpha decay < 0.5 for 60+ days                           │
│     └─ Pattern deactivated, preserved for analysis              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

*Last Updated: 2026-01-13*
