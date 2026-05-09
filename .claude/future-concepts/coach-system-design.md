# Coach System Design

> **Status:** Design complete, implementation pending
> **Created:** 2026-01-18
> **Scope:** Starting with Short-Term coaches only

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Coach Archetypes](#coach-archetypes)
3. [Three-Stage Agent Lifecycle](#three-stage-agent-lifecycle)
4. [HivemindTrader Entity](#hivemindtrader-entity)
5. [ELO and Fitness](#elo-and-fitness)
6. [Roster Slot System](#roster-slot-system)
7. [Motion Derivatives (Regime Shift Detection)](#motion-derivatives-regime-shift-detection)
8. [Roster Swap Triggers](#roster-swap-triggers)
9. [Parked Questions](#parked-questions)
10. [Code Stubs](#code-stubs)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    COINSWARM COGNITIVE HIERARCHY                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LAYER 5: Planners (future)                                     │
│      ↓                                                          │
│  LAYER 4: COACHES ← WE ARE DESIGNING THIS                       │
│      ↓                                                          │
│  LAYER 3: Committee/Hivemind (exists)                           │
│      ↓                                                          │
│  LAYER 2: Agents (exists)                                       │
│      ↓                                                          │
│  LAYER 1: Patterns (exists)                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Decisions

| Decision | Choice |
|----------|--------|
| Starting archetype | Short-Term only |
| Coach pool size | Large (30-50) for max chaos |
| Configurability | Everything configurable |
| Coach lifecycle | Clone/mutate/die like agents |
| Coach locking | Locked to archetype (no spanning) |

---

## Coach Archetypes

Four archetypes based on **data timescale** (not hold duration):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COACH TIMESCALE ARCHETYPES                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  RAPID (Microstructure) - FUTURE                                            │
│  ══════════════════════                                                      │
│  Focus: Extract value from orderbook inefficiencies                          │
│  Primary Data: Ticks, L2 depth, spread, funding rate, 1m candles            │
│  Game: Zero-sum vs other traders                                             │
│  Feeds Needed: Orderbook, trades, funding, liquidations                      │
│                                                                              │
│  SHORT-TERM (Swing) - IMPLEMENTING NOW                                       │
│  ══════════════════                                                          │
│  Focus: Capture intraday/multi-day swings                                    │
│  Primary Data: 15m, 1h candles                                               │
│  Game: Riding momentum waves, mean reversion                                 │
│  Feeds Needed: OHLCV, volume profile, basic indicators                       │
│                                                                              │
│  MOMENTUM (Trend) - FUTURE                                                   │
│  ═════════════════                                                           │
│  Focus: Ride established trends, catch regime shifts early                   │
│  Primary Data: 1h, 4h candles                                                │
│  Game: Trend following, breakout capture                                     │
│  Feeds Needed: OHLCV, trend indicators, cross-asset correlation             │
│                                                                              │
│  POSITION (Macro) - FUTURE                                                   │
│  ═════════════════                                                           │
│  Focus: Large capital deployment on macro thesis                             │
│  Primary Data: 4h, 1d, 1w, 1M candles                                        │
│  Game: Macro positioning, sentiment cycles, fundamentals                     │
│  Feeds Needed: News, sentiment, Nostr, macro (Fed, M2), power law models    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Source Matrix

| Data Source | Rapid | Short-Term | Momentum | Position |
|-------------|-------|------------|----------|----------|
| Orderbook/L2 | ★★★ | ☆ | ☆ | ☆ |
| Tick data | ★★★ | ☆ | ☆ | ☆ |
| Funding rate | ★★★ | ★★ | ★ | ★ |
| 15m candles | ★★ | ★★★ | ★★ | ☆ |
| 1h candles | ★ | ★★★ | ★★★ | ★ |
| 4h candles | ☆ | ★★ | ★★★ | ★★★ |
| 1d+ candles | ☆ | ★ | ★★ | ★★★ |
| News/Sentiment | ★ | ★ | ★★ | ★★★ |
| Macro (Fed/M2) | ☆ | ☆ | ★ | ★★★ |

---

## Three-Stage Agent Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT CLASS HIERARCHY                         │
│                    (Semantic Mental Model)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                        BaseAgent                                 │
│                     (traits, patterns)                           │
│                            │                                     │
│          ┌─────────────────┼─────────────────┐                  │
│          ▼                 ▼                 ▼                  │
│                                                                  │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐          │
│   │  Backtest   │   │  Crucible   │   │  Hivemind   │          │
│   │   Agent     │   │  Template   │   │   Trader    │          │
│   ├─────────────┤   ├─────────────┤   ├─────────────┤          │
│   │ LIFECYCLE:  │   │ LIFECYCLE:  │   │ LIFECYCLE:  │          │
│   │ - Spawns    │   │ - Created   │   │ - Instanti- │          │
│   │ - Tests     │   │   from BA   │   │   ated by   │          │
│   │ - Evolves   │   │ - Runs once │   │   Coach     │          │
│   │ - Reproduces│   │ - Freezes   │   │ - Votes     │          │
│   │ - Dies      │   │ - Persists  │   │ - Trades    │          │
│   │             │   │   forever   │   │ - Lives/Dies│          │
│   ├─────────────┤   ├─────────────┤   ├─────────────┤          │
│   │ MUTABLE:    │   │ IMMUTABLE:  │   │ MUTABLE:    │          │
│   │ Yes, evolves│   │ No, frozen  │   │ Performance │          │
│   │             │   │ snapshot    │   │ + traits    │          │
│   └─────────────┘   └─────────────┘   └─────────────┘          │
│          │                 │                 ▲                  │
│          │   Level 15+     │    Coach        │                  │
│          └────────────────►│    selects      │                  │
│              "graduates"   └─────────────────┘                  │
│                                "instantiates"                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Properties

| Class | Purpose | Lifespan | Mutability |
|-------|---------|----------|------------|
| **BacktestAgent** | Evolution sandbox | Until culled | Evolves constantly |
| **CrucibleTemplate** | Proven blueprint | Forever | Frozen (traits immutable) |
| **HivemindTrader** | Live execution | Coach decides | ELO, trades, traits can drift |

### Lifecycle Flow

1. **BacktestAgent** evolves, reaches Level 15+
2. Creates **CrucibleTemplate** (frozen snapshot with regime_scores)
3. BacktestAgent continues evolving (can create more templates later)
4. **Coach** selects template from library
5. Coach instantiates **HivemindTrader** from template
6. Trader lives, votes, accumulates ELO and trades
7. On death → snapshot back to template library IF changed (skip if duplicate)

---

## HivemindTrader Entity

Explicit entity, not just FK composite.

```python
class HivemindTrader(SQLModel, table=True):
    __tablename__ = "hivemind_traders"

    instance_id: str = Field(primary_key=True)

    # ORIGIN (immutable)
    template_id: str = Field(foreign_key="crucible_templates.snapshot_id")
    coach_id: str = Field(foreign_key="coaches.coach_id")
    created_at: datetime
    original_traits: Dict[str, Any]  # Snapshot at instantiation

    # CURRENT STATE (mutable)
    current_traits: Dict[str, Any]  # Can drift over time

    # Performance
    elo_rating: float = 1500.0
    elo_peak: float = 1500.0
    elo_games: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl_pct: float = 0.0
    live_regime_scores: Dict[str, float]  # Diverges from template

    # Lifecycle
    status: str = "active"  # "active", "benched", "retired", "dead"
    status_reason: Optional[str] = None
```

### Trait Drift

Traits CAN drift. Mechanism TBD (LLM/ML/algo). Stubbed with multiplier interface:

```python
class TraitDriftStrategy(ABC):
    @abstractmethod
    def calculate_drift(self, trader, context) -> Dict[str, float]:
        """Returns multipliers: {"risk_tolerance": 1.05, "patience": 0.97}"""
        pass

class PlaceholderDriftStrategy(TraitDriftStrategy):
    """Stub - applies passed-in multipliers directly"""
    def __init__(self, multipliers: Dict[str, float] = None):
        self.multipliers = multipliers or {}

    def calculate_drift(self, trader, context) -> Dict[str, float]:
        return {trait: self.multipliers.get(trait, 1.0)
                for trait in trader.current_traits.keys()}
```

### Death Conditions

1. **ELO below threshold**: Coach trait `min_trader_elo` (e.g., 1200)
2. **Coach dies**: All traders snapshot back to library
3. **Manual retirement**: Coach decision

### Snapshot Back to Library

On death, trader becomes new template IF changed from original:

```python
def retire_trader(self, trader, reason):
    if self._is_duplicate_of_origin(trader):
        return None  # Skip, no new template

    return self._snapshot_to_template(trader)
```

---

## ELO and Fitness

### Bounded Adjustment Formula

ELO doesn't multiply fitness directly. It moves fitness **toward ceiling/floor**:

```
CEILING = 100 (max fitness)
FLOOR = 0 (min fitness)
BASELINE_ELO = 1500

If ELO > 1500 (outperforming):
    elo_pct = (elo - 1500) / 1500
    room_to_ceiling = 100 - original_fitness
    fitness_gain = room_to_ceiling × elo_pct
    new_fitness = original_fitness + fitness_gain

If ELO < 1500 (underperforming):
    elo_pct = (1500 - elo) / 1500
    room_to_floor = original_fitness - 0
    fitness_loss = room_to_floor × elo_pct
    new_fitness = original_fitness - fitness_loss
```

### Examples

| Original Fitness | ELO | ELO % | Room | Adjustment | New Fitness |
|------------------|-----|-------|------|------------|-------------|
| 80 | 1800 | +20% | 20 up | +4 | **84** |
| 80 | 1200 | -20% | 80 down | -16 | **64** |
| 95 | 1800 | +20% | 5 up | +1 | **96** |
| 30 | 1200 | -20% | 30 down | -6 | **24** |

### Key Property: Asymmetric Risk

- High fitness trader: less upside, more downside
- Low fitness trader: more upside, less downside
- Natural regression toward mean under neutral performance

### ELO Triggers

Traders compete **per-vote** (existing governance_service):
- Vote with winning side → ELO up
- Vote wrong → ELO down

---

## Roster Slot System

Roster is **multi-slot composition**, not just headcount.

### Slot Types

```python
class SlotType(str, Enum):
    TRADER = "trader"           # ✅ Implementing now
    SENTIMENT = "sentiment"     # ⬚ Future
    RISK = "risk"               # ⬚ Future (VETO power)
    MACRO = "macro"             # ⬚ Future
    ORDERFLOW = "orderflow"     # ⬚ Future
```

### Slot Behaviors

| Type | Behavior | Function |
|------|----------|----------|
| TRADER | VOTE | Direction signal (long/short/wait) |
| SENTIMENT | BIAS | Modifies confidence |
| RISK | VETO | Can block trades |
| MACRO | CONTEXT | Regime/timing info |
| ORDERFLOW | CONTEXT | Entry/exit timing |

### Slot Configuration

```python
SLOT_REGISTRY = {
    SlotType.TRADER: SlotConfig(
        behavior=SlotBehavior.VOTE,
        min_count=3,
        max_count=15,
        is_implemented=True,
        source_description="Crucible-graduated trading agents",
    ),
    SlotType.SENTIMENT: SlotConfig(
        behavior=SlotBehavior.BIAS,
        min_count=0,
        max_count=5,
        is_implemented=False,
        source_description="Social media sentiment analysis",
    ),
    # ... etc
}
```

### Coach Slot Allocations (Evolvable Trait)

```python
slot_allocations: Dict[SlotType, int]
# {SlotType.TRADER: 5, SlotType.SENTIMENT: 0, ...}
```

---

## Motion Derivatives (Regime Shift Detection)

Apply calculus to candle data to detect regime shifts early.

### The Math

```
CANDLES: C0 (now), C1 (-1h), C2 (-2h), C3 (-3h)

VELOCITY (Δ) - 2 candles
    v = C0 - C1

ACCELERATION (ΔΔ) - 3 candles
    a = C0 - 2·C1 + C2

JERK (ΔΔΔ) - 4 candles
    j = C0 - 3·C1 + 3·C2 - C3
```

### Interpretation

| Derivative | Meaning | Normal Range |
|------------|---------|--------------|
| Velocity | "How fast is it moving?" | Common, high threshold |
| Acceleration | "Is it speeding up?" | Less common, medium threshold |
| Jerk | "Is acceleration changing?" | Rare, **very low threshold** |

### Jerk = Regime Shift Detector

**Any significant jerk is suspicious.** In stable markets, acceleration changes smoothly (low jerk). High jerk = "something just changed."

### Accel-Jerk Divergence (Huge Signal!)

When acceleration and jerk point opposite directions:

```
accel > 0, jerk > 0  → Trend strengthening (stay in)
accel > 0, jerk < 0  → Trend WEAKENING (⚠️ WATCH)
accel < 0, jerk < 0  → Reversal strengthening (get out)
accel < 0, jerk > 0  → Reversal weakening (bottom forming?)
```

**Accel positive but jerk negative = leading indicator of reversal**

### Multi-Indicator Application

Apply derivatives to ALL indicators, look for divergences:

```
INDICATOR        VELOCITY    ACCEL    JERK    DIVERGENCE?
══════════════════════════════════════════════════════════
Price            +2.0%       +0.5%    -0.3%   ⚠️ accel↔jerk
Volume           +15%        +3%      +1%     ✓ aligned
RSI              +5pts       +2pts    -3pts   ⚠️ accel↔jerk
MACD             +0.02       +0.01    -0.02   ⚠️ accel↔jerk
OBV              +1.5%       -0.2%    -0.1%   ⚠️ price↔obv
```

### Cross-Indicator Divergences

| Divergence | Meaning |
|------------|---------|
| Price accel UP, Volume accel DOWN | Weak move, no follow-through |
| Price accel UP, RSI jerk NEGATIVE | Momentum exhaustion |
| Price accel UP, OBV accel DOWN | Distribution phase |
| Price accel DOWN, Funding jerk UP | Shorts overextended |

**Multiple divergences = strong regime shift signal**

---

## Roster Swap Triggers

### Trigger Conditions

1. **Jerk threshold exceeded** (very sensitive)
2. **Accel-jerk divergence** on any indicator
3. **Cross-indicator divergences** (≥2 indicators disagree)
4. **Composite regime shift score** above threshold
5. **Time-based fallback** (force review every N candles)

### Coach Trait Thresholds (Evolvable)

```python
DEFAULT_COACH_THRESHOLDS = {
    "velocity_threshold": 0.03,       # 3% - high, common
    "acceleration_threshold": 0.015,  # 1.5% - medium
    "jerk_threshold": 0.005,          # 0.5% - very low!
    "regime_shift_threshold": 1.0,    # Composite score
    "max_review_interval": 24,        # Force review every 24 candles
}
```

### LLM Roster Re-evaluation

When triggered, LLM evaluates:
- Current motion derivatives
- Trigger reason
- Current roster composition
- Available bench players
- Regime belief

Outputs: KEEP / SWAP / FULL_ROTATION with reasoning

---

## Parked Questions

### Q9: Coach ELO - How Coaches Compete

**Status:** Parked for tomorrow

Options discussed:
- Aggregate trader performance
- Portfolio P&L
- Head-to-head vs other coaches
- Regime prediction accuracy

### Q12: Coach Traits - Specific Traits for Short-Term

**Status:** Parked for tomorrow

Candidates:
- Slot allocations (how many of each type)
- Selection traits (regime_fit_weight, diversity_preference, elo_weight)
- Threshold traits (velocity, acceleration, jerk thresholds)
- Death threshold (min_trader_elo)

### Q13: Decision Aggregation - Votes → Final Trade

**Status:** Parked for tomorrow

Likely ties into existing governance_service voting system.

---

## Code Stubs

### Motion Derivatives

```python
@dataclass
class MotionDerivatives:
    velocity: float
    acceleration: float
    jerk: float

    @classmethod
    def from_candles(cls, candles: List[float]) -> "MotionDerivatives":
        c0, c1, c2, c3 = candles[0], candles[1], candles[2], candles[3]
        return cls(
            velocity=c0 - c1,
            acceleration=c0 - 2*c1 + c2,
            jerk=c0 - 3*c1 + 3*c2 - c3,
        )

    @property
    def accel_jerk_divergent(self) -> bool:
        return (self.acceleration > 0) != (self.jerk > 0)
```

### Multi-Indicator Snapshot

```python
@dataclass
class MarketMotionSnapshot:
    indicators: Dict[str, MotionDerivatives]
    timestamp: datetime

    def get_accel_jerk_divergences(self) -> List[str]:
        return [name for name, m in self.indicators.items()
                if m.accel_jerk_divergent]

    def regime_shift_score(self) -> float:
        score = sum(m.accel_jerk_divergence_strength
                   for m in self.indicators.values())
        score += len(self.get_cross_indicator_divergences()) * 0.5
        return score
```

### ELO → Fitness

```python
def elo_adjusted_fitness(
    original_fitness: float,
    elo: float,
    baseline_elo: float = 1500.0,
    ceiling: float = 100.0,
    floor: float = 0.0,
) -> float:
    if elo >= baseline_elo:
        elo_pct = (elo - baseline_elo) / baseline_elo
        room = ceiling - original_fitness
        return original_fitness + (room * elo_pct)
    else:
        elo_pct = (baseline_elo - elo) / baseline_elo
        room = original_fitness - floor
        return original_fitness - (room * elo_pct)
```

### Slot Provider Interface

```python
class BaseSlotProvider(ABC):
    @property
    @abstractmethod
    def slot_type(self) -> SlotType:
        pass

    @abstractmethod
    def get_signal(self, asset, timestamp, context) -> SlotSignal:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass
```

---

## Future Work

| Item | Priority | Notes |
|------|----------|-------|
| Other archetypes (Rapid/Momentum/Position) | Medium | After Short-Term proven |
| Other slot types (sentiment/risk/macro) | Medium | Plugs into existing interface |
| Schema migration (JSONB → columns) | Low | When traits stabilize |
| Trait drift mechanism | Low | LLM/ML/algo - currently stubbed |

---

*Last Updated: 2026-01-18*
