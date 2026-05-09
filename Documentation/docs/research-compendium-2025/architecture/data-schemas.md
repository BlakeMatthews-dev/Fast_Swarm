# Data Schemas

> **Core data structures for the Coinswarm trading system**
>
> This document defines the schemas for trades, patterns, agents, and memory.

---

## Overview

All data flows through these core schemas:

```
MarketData → Pattern → Signal → Trade → Memory
```

---

## FullTradeRecord

The canonical trade record capturing all information for analysis and learning.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"

class TradeStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"

@dataclass
class FullTradeRecord:
    """
    Complete trade record for learning and analysis.

    Design Principles:
    1. Store RAW values, never buckets (evolution discovers boundaries)
    2. Capture everything needed to replay the decision
    3. Include both entry and exit context
    4. Track which patterns/agents contributed

    Paper References:
    - MacroHFT: Memory structure M=(K,E,V)
    - FinAgent: Trade UUID for memory retrieval
    """

    # === IDENTIFICATION ===
    trade_id: str                      # UUID, unique across all trades
    agent_id: str                      # Agent that executed this trade
    pattern_id: str                    # Pattern that triggered entry
    roster_session_id: str             # Which roster session this belongs to

    # === ASSET & TIMING ===
    asset: str                         # e.g., "BTC", "ETH"
    timeframe: str                     # e.g., "1h", "4h", "1d"
    direction: TradeDirection
    status: TradeStatus

    entry_time: datetime
    exit_time: Optional[datetime] = None
    hold_duration_seconds: Optional[int] = None

    # === PRICES (all raw floats) ===
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

    # === POSITION ===
    position_size: float               # As fraction of portfolio (0.0-1.0)
    position_value_usd: float          # Absolute value at entry
    leverage: float = 1.0              # 1.0 = no leverage

    # === P&L (calculated on close) ===
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    roi_pct: Optional[float] = None    # pnl_pct adjusted for position size

    # === FEES & SLIPPAGE ===
    entry_fee_usd: float = 0.0
    exit_fee_usd: float = 0.0
    total_fees_usd: float = 0.0
    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0

    # === RAW MARKET CONTEXT AT ENTRY ===
    # Store raw values - never buckets!
    entry_context: dict = field(default_factory=dict)
    # Example entry_context:
    # {
    #     'rsi_14': 28.3,
    #     'macd_line': -0.0023,
    #     'macd_signal': -0.0031,
    #     'macd_histogram': 0.0008,
    #     'bb_position': 0.12,        # 0=lower band, 1=upper band
    #     'atr_14': 245.50,
    #     'volume_ratio': 1.45,       # vs 20-period average
    #     'price_vs_ema_20': -0.023,  # % distance from EMA
    #     'price_vs_ema_50': -0.045,
    #     'hour_of_day': 14,
    #     'day_of_week': 2,           # 0=Monday
    #     'regime': 'bear_volatile',
    #     'fear_greed_index': 23,
    #     'funding_rate': -0.0001,
    #     'open_interest_change_pct': 0.05,
    # }

    # === RAW MARKET CONTEXT AT EXIT ===
    exit_context: dict = field(default_factory=dict)

    # === COMMITTEE CONTEXT ===
    committee_vote: dict = field(default_factory=dict)
    # Example:
    # {
    #     'decision': 'BUY',
    #     'confidence': 0.72,
    #     'bull_votes': 3,
    #     'bear_votes': 2,
    #     'agent_votes': {
    #         'agent_001': {'vote': 'BUY', 'confidence': 0.85},
    #         'agent_002': {'vote': 'HOLD', 'confidence': 0.60},
    #     }
    # }

    # === AGENT TRAITS AT TRADE TIME ===
    agent_traits: dict = field(default_factory=dict)
    # Snapshot of the 16 traits when trade was placed

    # === EXIT REASON ===
    exit_reason: Optional[str] = None
    # 'take_profit', 'stop_loss', 'pattern_exit', 'manual', 'timeout'

    # === TAGS & METADATA ===
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### SQL Schema (D1)

```sql
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    pattern_id TEXT NOT NULL,
    roster_session_id TEXT,

    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    status TEXT NOT NULL,

    entry_time TEXT NOT NULL,
    exit_time TEXT,
    hold_duration_seconds INTEGER,

    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_loss_price REAL,
    take_profit_price REAL,

    position_size REAL NOT NULL,
    position_value_usd REAL NOT NULL,
    leverage REAL DEFAULT 1.0,

    pnl_usd REAL,
    pnl_pct REAL,
    roi_pct REAL,

    entry_fee_usd REAL DEFAULT 0,
    exit_fee_usd REAL DEFAULT 0,
    total_fees_usd REAL DEFAULT 0,
    entry_slippage_bps REAL DEFAULT 0,
    exit_slippage_bps REAL DEFAULT 0,

    entry_context TEXT,  -- JSON
    exit_context TEXT,   -- JSON
    committee_vote TEXT, -- JSON
    agent_traits TEXT,   -- JSON

    exit_reason TEXT,
    tags TEXT,           -- JSON array
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for common queries
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (pattern_id) REFERENCES patterns(pattern_id)
);

CREATE INDEX idx_trades_agent ON trades(agent_id);
CREATE INDEX idx_trades_pattern ON trades(pattern_id);
CREATE INDEX idx_trades_asset ON trades(asset);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
CREATE INDEX idx_trades_status ON trades(status);
```

---

## Pattern Schema

```python
@dataclass
class Condition:
    """Single condition for pattern matching."""
    indicator: str      # e.g., 'rsi_14', 'macd_histogram'
    min_value: float    # Minimum bound (inclusive)
    max_value: float    # Maximum bound (inclusive)
    timeframe: str = "1h"  # Which timeframe's data

@dataclass
class Pattern:
    """
    Atomic trading pattern discovered through evolution.

    Paper References:
    - CGA-Agent: Genetic pattern evolution
    - M3T: Hierarchical pattern matching
    """
    pattern_id: str
    name: str
    description: str
    origin: str  # 'chaos', 'academic', 'technical', 'ai', 'hybrid'

    # Conditions
    entry_conditions: list[Condition]
    exit_conditions: list[Condition]

    # Fitness & Performance
    tier: int                    # 1=Elite, 2=Proven, 3=Untested
    fitness_score: float         # 0-100
    total_roi_pct: float
    annualized_roi_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    number_of_runs: int
    benchmark_beats: int

    # Metadata
    created_at: datetime
    last_updated: datetime
    tags: list[str]
    parent_pattern_id: Optional[str] = None  # For evolved patterns
```

### SQL Schema

```sql
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    origin TEXT NOT NULL,

    entry_conditions TEXT NOT NULL,  -- JSON
    exit_conditions TEXT NOT NULL,   -- JSON

    tier INTEGER DEFAULT 3,
    fitness_score REAL DEFAULT 0,
    total_roi_pct REAL DEFAULT 0,
    annualized_roi_pct REAL DEFAULT 0,
    sharpe_ratio REAL DEFAULT 0,
    sortino_ratio REAL DEFAULT 0,
    max_drawdown_pct REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    profit_factor REAL DEFAULT 0,
    number_of_runs INTEGER DEFAULT 0,
    benchmark_beats INTEGER DEFAULT 0,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    tags TEXT,  -- JSON array
    parent_pattern_id TEXT,

    FOREIGN KEY (parent_pattern_id) REFERENCES patterns(pattern_id)
);

CREATE INDEX idx_patterns_fitness ON patterns(fitness_score);
CREATE INDEX idx_patterns_tier ON patterns(tier);
CREATE INDEX idx_patterns_origin ON patterns(origin);
```

---

## Agent Schema

```python
@dataclass
class Agent:
    """
    Trading agent with personality traits.

    Paper References:
    - TradingAgents: Role specialization
    - MacroHFT: Agent memory architecture
    """
    agent_id: str
    name: str
    generation: int  # Which evolution generation

    # 16 Personality Traits (all 0.0-1.0)
    traits: dict[str, float]
    # {
    #     'risk_tolerance': 0.65,
    #     'hold_duration_bias': 0.40,
    #     'volatility_seeking': 0.72,
    #     'profit_target_greed': 0.55,
    #     'win_rate_preference': 0.48,
    #     'drawdown_sensitivity': 0.35,
    #     'momentum_vs_reversion': 0.80,
    #     'stop_loss_tightness': 0.42,
    #     'entry_aggression': 0.60,
    #     'exit_aggression': 0.45,
    #     'lookback_preference': 0.30,
    #     'sentiment_weight': 0.55,
    #     'news_reactivity': 0.70,
    #     'sentiment_contrarian': 0.25,
    #     'funding_rate_sensitivity': 0.40,
    #     'correlation_awareness': 0.50,
    # }

    # Regime Affinity Scores
    regime_affinity: dict[str, float]
    # {
    #     'bull_volatile': 0.82,
    #     'bull_calm': 0.65,
    #     'bear_volatile': 0.31,
    #     'bear_calm': 0.45,
    #     'sideways': 0.55,
    # }

    # Performance
    total_trades: int
    total_pnl_usd: float
    sharpe_ratio: float
    win_rate: float
    avg_hold_duration_hours: float

    # Status
    status: str  # 'active', 'benched', 'retired'
    parent_agent_id: Optional[str] = None

    # Timestamps
    created_at: datetime
    last_trade_at: Optional[datetime] = None
```

---

## Memory Schemas

### Episodic Memory

```python
@dataclass
class EpisodicMemory:
    """
    Short-term memory of specific events.

    Paper Reference: MacroHFT M=(K,E,V) where:
    - K = Key (trade context for similarity matching)
    - E = Event (what happened)
    - V = Value (outcome/reward)
    """
    memory_id: str
    agent_id: str
    trade_id: str

    # Key (K) - for similarity retrieval
    key_embedding: list[float]  # Vector embedding of trade context

    # Event (E) - what happened
    event_summary: str
    # "Entered BTC long at $42,500 on RSI oversold + MACD cross"

    # Value (V) - outcome
    outcome_pnl_pct: float
    outcome_label: str  # 'big_win', 'small_win', 'small_loss', 'big_loss'

    # Metadata
    timestamp: datetime
    regime: str
    ttl_hours: int = 168  # 7 days default
```

### Semantic Memory

```python
@dataclass
class SemanticMemory:
    """
    Aggregated knowledge from many episodes.

    Stored as statistical summaries, not individual events.
    """
    memory_id: str
    agent_id: str

    # Aggregated by pattern
    pattern_stats: dict[str, dict]
    # {
    #     'rsi_oversold_long': {
    #         'trades': 47,
    #         'win_rate': 0.62,
    #         'avg_pnl_pct': 2.3,
    #         'sharpe': 1.2,
    #         'best_regime': 'bull_volatile',
    #         'worst_regime': 'bear_calm',
    #     }
    # }

    # Aggregated by regime
    regime_stats: dict[str, dict]

    # Aggregated by time
    time_stats: dict[str, dict]
    # Hour of day, day of week performance

    last_updated: datetime
```

### Wisdom Memory

```python
@dataclass
class WisdomRule:
    """
    High-level belief/rule extracted from experience.

    Format: WHEN <condition> DO <action> BECAUSE <reason>

    Paper Reference: Reflect Agent - verbal feedback loop
    """
    rule_id: str
    agent_id: str

    when_condition: str   # "RSI < 25 AND regime = bear_volatile"
    do_action: str        # "reduce position size by 50%"
    because_reason: str   # "8 of last 10 trades in this condition lost money"

    confidence: float     # 0-1, how confident in this rule
    supporting_trades: int  # How many trades support this
    last_validated: datetime

    # Triggers for rule generation
    trigger_type: str  # 'losing_streak', 'regime_change', 'pattern_failure'
```

---

## Market Data Schemas

### OHLCV Candle

```python
@dataclass
class Candle:
    """Standard OHLCV candle."""
    asset: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
```

### Market Context

```python
@dataclass
class MarketContext:
    """
    Complete market context for decision making.

    This is the input to agents for each decision.
    """
    # Asset
    asset: str
    current_price: float
    timestamp: datetime

    # Technical indicators (raw values)
    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: float  # 0=lower, 1=upper
    atr_14: float
    volume_ratio: float  # vs 20-period SMA

    # Trend context
    price_vs_ema_20: float  # % distance
    price_vs_ema_50: float
    price_vs_ema_200: float
    trend_1h: str   # 'up', 'down', 'sideways'
    trend_4h: str
    trend_1d: str

    # Regime
    regime: str
    volatility_percentile: float  # 0-100

    # Sentiment (if available)
    fear_greed_index: Optional[int] = None
    funding_rate: Optional[float] = None
    open_interest_change_pct: Optional[float] = None

    # Time
    hour_of_day: int
    day_of_week: int
```

---

## Related Files

- [3-tier-execution.md](3-tier-execution.md) - How data flows through tiers
- [5-layer-hierarchy.md](5-layer-hierarchy.md) - Data at each cognitive layer
- [../concepts/memory-systems.md](../concepts/memory-systems.md) - Memory architecture

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial schema document |
