# Coinswarm System API Map

Complete reference for MCP server integration.

---

## 0. PATTERN ENTRY POINTS (Layer 2)

Five distinct sources feed patterns into the evolution system:

### 0.1 CHAOS (Random Discovery)

**Files:**
- `chaos_trade_generator.py` - Generate random trades on real OHLCV
- `generators/primary/generate_chaos_discovered_patterns.py` - Extract patterns from winners
- `generators/evolution/pg_evolution.py` - PostgreSQL evolution engine

**Functions:**
```python
# Generate random trades
generate_chaos_trades(num_trades=900, assets=['BTC','ETH'], timeframe='1h') -> List[ChaosTrade]

# Discover patterns from winners/losers
discover_patterns_from_chaos(trades, min_win_rate=0.55) -> List[Pattern]

# Create single rule pattern
create_single_rule_pattern(rule: Dict, exit_config: Dict) -> Pattern

# Create combo pattern (multiple conditions)
create_combo_pattern(rules: List[Dict], exit_config: Dict) -> Pattern
```

**CLI:** `python chaos_trade_generator.py --trades 900 --discover`

---

### 0.2 ACADEMIC (Research-Based)

**Files:**
- `generators/academic/academic_pattern_generator.py` - Peer-reviewed patterns with citations
- `generators/academic/paper_distiller.py` - LLM-powered paper extraction

**Functions:**
```python
# Generate academic patterns with citations
generate_academic_patterns() -> List[AcademicPattern]

# Categories: calendar, technical, microstructure, crypto
# - Monday effect, January effect
# - RSI, MACD, Bollinger strategies
# - Order flow, spread patterns
# - Crypto-specific anomalies

# Distill paper to patterns (LLM-powered)
distill_paper(pdf_path: str, model='claude-3-opus') -> Distillation
generate_patterns(distillation: Distillation) -> PatternSet
```

**CLI:** `python generators/academic/paper_distiller.py --pdf paper.pdf`

---

### 0.3 TECHNICAL (Classic TA Combos)

**Files:**
- `generators/primary/generate_multi_indicator_combos.py` - TA combinations
- `generators/primary/generate_data_driven_patterns.py` - Data-driven discovery
- `generators/primary/generate_fg_patterns.py` - Fear & Greed patterns

**Functions:**
```python
# Generate strategic indicator combos
generate_strategic_combo(indicators, direction='long', exit_style='balanced') -> Pattern

# Generate single indicator patterns
generate_single_indicator_patterns(data: Dict, count=50) -> List[Pattern]

# Generate affinity patterns (indicator pairs that work together)
generate_affinity_patterns(data: Dict, count=100) -> List[Pattern]

# Generate regime-specific patterns
generate_regime_patterns(data, regime='bull', count=50) -> List[Pattern]

# Fear & Greed patterns
generate_fg_patterns(num_per_template=20) -> List[Pattern]
```

**CLI:** `python generators/primary/generate_data_driven_patterns.py --count 300`

---

### 0.4 AI/ML (Machine Learning Discovery)

**Files:**
- `generators/primary/generate_ml_patterns_pg.py` - ML-discovered indicators

**Functions:**
```python
# ML indicators selected by Cohen's d effect size
ML_INDICATORS = [
    {'name': 'pvo', 'cohens_d': 0.153, 'direction': 'higher'},
    {'name': 'kdj_k', 'cohens_d': -0.114, 'direction': 'lower'},
    {'name': 'supertrend_direction', 'cohens_d': -0.128},
    # ... 20+ indicators with statistical significance
]

# Generate ML patterns
generate_patterns(count=200) -> List[Pattern]
generate_single_indicator_pattern(indicator: Dict) -> Pattern
generate_combo_pattern(indicators: List[Dict]) -> Pattern
```

**CLI:** `python generators/primary/generate_ml_patterns_pg.py --count 200`

---

### 0.5 HYBRID (Combinators)

**Files:**
- `generators/combinators/microstructure_combinator.py` - Tick + orderbook
- `generators/combinators/candle_tick_combinator.py` - Candle + tick hybrid
- `generators/combinators/entry_exit_combinator.py` - Entry/exit separation

**Functions:**
```python
# Microstructure patterns (tick-level)
generate_micro_patterns(num_tick_conditions=2, mode='always_long') -> List[Pattern]

# Tick indicators: cvd_1min, buy_sell_ratio, price_momentum, trade_count
# Orderbook: spread_bps, order_book_imbalance, bid_vol_10, ask_vol_10

# Momentum divergence patterns
generate_momentum_divergence_patterns() -> List[Pattern]

# Always-long accumulation patterns (never go to 0%)
generate_always_long_patterns() -> List[Pattern]

# Discoverable exits (evolution finds optimal)
generate_discoverable_exit() -> Dict
# Returns: stop_loss, take_profit, trailing_stop, scale_out_levels
```

**Strategy Modes:**
- `flat_to_long`: Traditional cash → position → exit
- `always_long`: Always hold BTC, patterns signal ADD or REDUCE

**CLI:** `python generators/combinators/microstructure_combinator.py --mode always_long`

---

### 0.6 VARIATIONS (Threshold Mutations)

**Files:**
- `generators/variations/threshold_variation_generator.py`
- `generators/variations/generate_entry_variations.py`
- `generators/variations/generate_exit_variations.py`

**Functions:**
```python
# Generate threshold variations
generate_threshold_variations(indicators, num_variations=100) -> List[Pattern]

# Generate entry/exit variations from base pattern
generate_entry_variations(base_pattern, num=10) -> List[Pattern]
generate_exit_variations(base_pattern, num=10) -> List[Pattern]
```

---

### 0.7 MASTER ORCHESTRATOR

**File:** `generators/run_all.py`, `generators/combine_patterns.py`

```python
# Run all generators
run_all_generators(chaos=200, academic=True, ml=200, micro=300) -> Dict[str, int]

# Combine all pattern files
combine_patterns(input_dir, output_file, dedupe=True) -> int
```

**CLI:** `python generators/run_all.py --all`

---

## 1. PATTERNS

### Database: `discovered_patterns` (PostgreSQL + D1)

| Column | Type | Description |
|--------|------|-------------|
| pattern_id | TEXT | Primary key |
| name | TEXT | Human-readable name |
| entry_conditions | JSON | Array of conditions |
| exit_conditions | JSON | Stop loss, take profit, etc. |
| fitness_score | REAL | 0-100, bounded |
| tier | INT | 1=Elite, 2=Proven, 3=Untested |
| status | TEXT | active, testing, archived, retired |
| number_of_runs | INT | Backtest count |
| benchmark_beats | INT | Times beat buy-and-hold |
| total_roi_pct | REAL | Cumulative ROI |
| sharpe_ratio | REAL | Risk-adjusted return |
| win_rate | REAL | 0-1 |
| origin | TEXT | chaos, academic, technical, ai, hybrid |

### Pattern Functions

```python
# List patterns
list_patterns(tier=None, min_fitness=None, limit=100) -> List[Pattern]

# Get single pattern
get_pattern(pattern_id: str) -> Pattern

# Get top patterns
get_top_patterns(n=20, sort_by='fitness_score') -> List[Pattern]

# Create pattern
create_pattern(name, entry_conditions, exit_conditions, origin) -> Pattern

# Update pattern stats
update_pattern_stats(pattern_id, stats: dict) -> None

# Delete pattern
delete_pattern(pattern_id) -> None

# Backtest pattern
backtest_pattern(pattern_id, asset, timeframe, start, end) -> BacktestResult

# Get pattern runs
get_pattern_runs(pattern_id, limit=50) -> List[BacktestRun]
```

---

## 2. AGENTS

### Database: `agents.db` (SQLite) + `agents` table (PostgreSQL)

| Column | Type | Description |
|--------|------|-------------|
| agent_id | TEXT | Primary key |
| name | TEXT | Generated name |
| generation | INT | Evolutionary generation |
| fitness_score | REAL | 0-100 |
| status | TEXT | active, testing, retired |
| traits | JSON | 22 personality traits |
| pattern_ids | JSON | Assigned patterns |
| elo_rating | REAL | Trust score (starts 1500) |
| total_trades | INT | Trade count |
| winning_trades | INT | Wins |
| total_roi_pct | REAL | Cumulative ROI |

### 22 Agent Traits

```python
# Core Risk (1-4)
risk_tolerance: float          # 0-1
hold_duration_bias: float
volatility_seeking: float
profit_target_greed: float

# Pattern Selection (5-7)
win_rate_preference: float
drawdown_sensitivity: float    # Derived from risk_tolerance
momentum_vs_reversion: float

# Execution (8-10)
stop_loss_tightness: float     # Derived from risk_tolerance
entry_aggression: float
exit_aggression: float         # Derived from entry_aggression

# Technical (11)
lookback_preference: float

# Sentiment (12-14)
sentiment_weight: float
news_reactivity: float
sentiment_contrarian: float

# Macro (15-16)
funding_rate_sensitivity: float
correlation_awareness: float

# Decision & Memory (17-22)
uncertainty_anchor: float
ai_assist_range: float
min_threshold: float
ai_threshold: float
memory_condensation: float
inheritance_decay: float
```

### Agent Functions

```python
# List agents
list_agents(status='active', limit=100) -> List[Agent]

# Get agent
get_agent(agent_id: str) -> Agent

# Get top agents
get_top_agents(n=10, sort_by='fitness_score') -> List[Agent]

# Spawn new agent
spawn_agent(traits=None, parent_ids=None) -> Agent

# Retire agent
retire_agent(agent_id: str) -> None

# Get agent trades
get_agent_trades(agent_id, limit=100) -> List[Trade]

# Get agent memory
get_agent_memory(agent_id) -> AgentMemory
  # .episodic: Recent trades (7 days)
  # .semantic: Lifetime stats
  # .wisdom: Beliefs and rules

# Update agent traits
update_agent_traits(agent_id, traits: dict) -> None

# Mutate agent (evolution)
mutate_agent(agent_id, mutation_rate=0.1) -> Agent
```

---

## 3. COACHES

### Database: `coaches.db` (SQLite)

| Column | Type | Description |
|--------|------|-------------|
| coach_id | TEXT | Primary key |
| name | TEXT | Coach name |
| traits | JSON | Coach-level traits |
| roster | JSON | List of agent_ids |
| elo_rating | REAL | Coach trust score |
| wins | INT | Winning decisions |
| losses | INT | Losing decisions |

### Coach Traits

```python
roster_size_preference: float   # Small focused vs large diverse
specialization_degree: float    # Specialist vs generalist
risk_management: float          # Aggressive vs conservative
regime_adaptivity: float        # Static vs dynamic roster
youth_preference: float         # Veterans vs new agents
min_elo_threshold: float        # Minimum agent ELO
```

### Coach Functions

```python
# List coaches
list_coaches(limit=50) -> List[Coach]

# Get coach
get_coach(coach_id: str) -> Coach

# Create coach
create_coach(name: str, traits=None) -> Coach

# Get roster
get_roster(coach_id: str) -> List[Agent]

# Select roster (from Crucible only!)
select_roster(coach_id: str, crucible_conn) -> List[str]

# Update coach ELO
update_coach_elo(coach_id, won: bool) -> None

# Evaluate roster performance
get_roster_performance(coach_id) -> RosterStats
```

---

## 4. COMMITTEE

### Committee Functions

```python
# Initialize committee
Committee(
    agent_conn,                    # SQLite connection to agents.db
    coach_conn,                    # SQLite connection to coaches.db
    quorum_threshold=0.5,          # Participation %
    min_quorum_voters=3,           # CRITICAL: minimum voters
    confidence_threshold=0.6,      # Min confidence to act
    max_position_usd=1000.0,
    max_portfolio_risk=0.1,
    use_ai=True,
    ai_confidence_threshold=0.4,
)

# Vote on signal
vote_on_signal(symbol: str, market_state: dict) -> CommitteeDecision

# Get vote breakdown
get_vote_breakdown(decision_id: str) -> VoteBreakdown

# Check quorum
check_quorum(votes: List[Vote]) -> bool

# Aggregate votes
aggregate_votes(votes: List[Vote]) -> CommitteeDecision
```

### CommitteeDecision Structure

```python
@dataclass
class CommitteeDecision:
    symbol: str
    direction: str           # "buy", "sell", "hold"
    confidence: float        # 0-1
    position_size: float     # USD
    roster_votes: List[RosterVote]
    total_for: int
    total_against: int
    total_abstain: int
    quorum_met: bool
    risk_approved: bool
```

---

## 5. EVOLUTION

### Evolution Functions

```python
# Run full 4-phase cycle
run_evolution_cycle() -> CycleResult

# Phase 1: Chaos (generate random trades)
run_chaos_phase(num_trades=900) -> List[ChaosTrade]

# Phase 2: Discovery (AI pattern extraction)
run_discovery_phase(trades: List[ChaosTrade]) -> List[Pattern]

# Phase 3: Backtest (test discovered patterns)
run_backtest_phase(patterns: List[Pattern]) -> List[BacktestResult]

# Phase 4: Selection (rank and cull)
run_selection_phase() -> SelectionResult
  # Returns: promoted, retired, survivors

# Prune low-fitness patterns
prune_patterns(min_fitness=40) -> int  # Returns count pruned

# Get evolution state
get_evolution_state() -> EvolutionState

# Reset evolution
reset_evolution() -> None
```

### Tier System

```python
# Tier promotion logic
TIER_3 = "untested"     # fitness < 40
TIER_2 = "proven"       # fitness 40-79, runs >= 100
TIER_1 = "elite"        # fitness >= 80, runs >= 50

# Promotion
promote_pattern(pattern_id, from_tier, to_tier) -> None

# Culling
cull_bottom_patterns(percentile=0.3) -> List[str]  # Returns culled IDs
```

---

## 6. TRADING

### Position Functions

```python
# Get open positions
get_open_positions(symbol=None) -> List[Position]

# Get position
get_position(position_id: str) -> Position

# Open position
open_position(
    symbol: str,
    side: str,           # "long" or "short"
    size_usd: float,
    entry_price: float,
    pattern_id: str = None,
    agent_id: str = None,
) -> Position

# Close position
close_position(
    position_id: str,
    exit_price: float,
    reason: str,         # "take_profit", "stop_loss", "signal", "timeout"
) -> Trade

# Update position (trailing stop, etc.)
update_position(position_id, updates: dict) -> Position
```

### Trade Functions

```python
# Get trades
get_trades(
    symbol=None,
    agent_id=None,
    pattern_id=None,
    start_time=None,
    end_time=None,
    limit=100
) -> List[Trade]

# Get trade
get_trade(trade_id: str) -> Trade

# Record trade
record_trade(trade: Trade) -> None

# Get trade stats
get_trade_stats(
    symbol=None,
    timeframe='all'
) -> TradeStats
```

### Exchange Functions

```python
# Get supported exchanges
get_exchanges() -> List[Exchange]
  # Returns: coinbase, binance, hyperliquid, dydx, bybit

# Get exchange fees
get_exchange_fees(exchange: str, tier: str = 'base') -> FeeStructure

# Execute order (via exchange)
execute_order(
    exchange: str,
    symbol: str,
    side: str,
    size: float,
    order_type: str = 'market',
) -> OrderResult

# Get order status
get_order_status(order_id: str) -> OrderStatus
```

---

## 7. DATA

### OHLCV Functions

```python
# Get candles
get_candles(
    symbol: str,
    timeframe: str,      # "1h", "6h", "1d"
    start: int = None,   # Unix timestamp
    end: int = None,
    limit: int = 1000,
) -> List[Candle]

# Get latest candle
get_latest_candle(symbol: str, timeframe: str) -> Candle

# Get available symbols
get_available_symbols() -> List[str]

# Get data coverage
get_data_coverage(symbol: str) -> DataCoverage
  # Returns: start_date, end_date, gaps, completeness_pct
```

### Tick Functions

```python
# Get ticks
get_ticks(
    symbol: str,
    start_ms: int,
    end_ms: int,
    limit: int = 10000,
) -> List[Tick]

# Get latest ticks
get_latest_ticks(symbol: str, count: int = 100) -> List[Tick]

# Aggregate ticks to candles
build_candles_from_ticks(
    ticks: List[Tick],
    timeframe: str,
) -> List[Candle]
```

### Indicator Functions

```python
# Calculate indicators for candles
calculate_indicators(candles: List[Candle]) -> EnhancedCandles
  # Adds 100+ indicators: RSI, MACD, EMA, Bollinger, ATR, etc.

# Get specific indicator
get_indicator(
    candles: List[Candle],
    indicator: str,      # "rsi14", "macd", "ema20", etc.
    params: dict = None,
) -> List[float]

# Available indicators
get_available_indicators() -> List[str]
  # Returns: rsi14, rsi21, macd, macdSignal, macdHistogram,
  #          ema9, ema20, ema50, ema200, sma20, sma50,
  #          bbUpper, bbMiddle, bbLower, atr14, adx14,
  #          stochK, stochD, williamsR, mfi14, obv,
  #          aroonUp, aroonDown, tsi, cmo, zscore,
  #          trend_regime, volatility_regime, ...
```

---

## 8. CRUCIBLE

### Crucible Functions

```python
# Get leaderboard
get_crucible_leaderboard(limit=100) -> List[CrucibleEntry]

# Get entry
get_crucible_entry(clone_id: str) -> CrucibleEntry

# Submit to crucible (one-shot test)
submit_to_crucible(agent_id: str) -> CrucibleResult

# Get regime performance
get_regime_performance(clone_id: str) -> Dict[str, RegimeStats]

# Get top for regime
get_top_for_regime(regime: str, limit=20) -> List[CrucibleEntry]
```

---

## 9. BACKTEST

### Backtest Functions

```python
# Run backtest
run_backtest(
    pattern_id: str,
    symbol: str,
    timeframe: str,
    start: int,
    end: int,
    initial_capital: float = 10000,
) -> BacktestResult

# Batch backtest
batch_backtest(
    pattern_ids: List[str],
    symbols: List[str],
    timeframe: str,
) -> List[BacktestResult]

# Get backtest queue
get_backtest_queue() -> List[QueuedBacktest]

# Add to queue
queue_backtest(pattern_id: str, priority: int = 5) -> None

# Walk-forward validation
walk_forward_test(
    pattern_id: str,
    symbol: str,
    train_pct: float = 0.7,
) -> WalkForwardResult
```

### BacktestResult Structure

```python
@dataclass
class BacktestResult:
    pattern_id: str
    symbol: str
    timeframe: str
    start_time: int
    end_time: int

    # Metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_roi_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    profit_factor: float

    # Fitness (0-100)
    fitness_score: float

    # Comparison
    benchmark_roi: float     # Buy and hold
    alpha: float             # ROI - benchmark
    beat_benchmark: bool
```

---

## 10. SYSTEM / ADMIN

### System Functions

```python
# Get system status
get_system_status() -> SystemStatus

# Get database stats
get_db_stats() -> DbStats
  # Returns: pattern_count, agent_count, trade_count, etc.

# Get evolution stats
get_evolution_stats() -> EvolutionStats

# Health check
health_check() -> HealthResult

# Clear caches
clear_caches() -> None

# Backup databases
backup_databases(path: str) -> None
```

### Logging Functions

```python
# Get logs
get_logs(
    level: str = None,       # "info", "warn", "error"
    component: str = None,   # "committee", "evolution", etc.
    since: int = None,       # Unix timestamp
    limit: int = 100,
) -> List[LogEntry]

# Get errors
get_errors(since: int = None, limit=50) -> List[LogEntry]

# Prune old logs
prune_logs(older_than_days: int = 30) -> int
```

---

## Database Connections

### PostgreSQL (Primary)

```python
# Connection string
DATABASE_URL = os.getenv('DATABASE_URL')
# postgresql://user:pass@host:5432/coinswarm

# Tables: patterns, agents, trades, positions, ticks
```

### SQLite (Local)

```python
# Agents
AGENTS_DB = "local-utilities/agents.db"

# Coaches
COACHES_DB = "local-utilities/coaches.db"

# Live data
LIVE_DATA_DB = "local-utilities/live_data.db"

# Sentiment
SENTIMENT_DB = "local-utilities/coinswarm_sentiment.sqlite"
```

### Cloudflare D1 (V3)

```python
# Main evolution DB
DB = "coinswarm-evolution"  # 700MB

# Data shards (OHLCV)
DATA_SHARD_1 = "coinswarm-data-shard-1"  # 2GB - BTC, ETH, etc.
DATA_SHARD_2 = "coinswarm-data-shard-2"  # 2.5MB - ARB, ETFs
DATA_SHARD_3 = "coinswarm-data-shard-3"  # 1MB - Solana tokens
DATA_SHARD_4 = "coinswarm-data-shard-4"  # 1.5MB - BSC DeFi
```

---

## 11. POSITION MANAGEMENT

### Database: `live_positions`, `live_trade_history` (PostgreSQL)

| Column | Type | Description |
|--------|------|-------------|
| position_id | TEXT | Primary key |
| product_id | TEXT | Asset symbol (BTC-USD) |
| side | TEXT | "long" or "short" |
| size | NUMERIC | Position size (Decimal) |
| entry_price | NUMERIC | Average entry price |
| current_price | NUMERIC | Current market price |
| trading_mode | TEXT | "paper" or "live" |
| exchange | TEXT | coinbase, hyperliquid, binance |
| status | TEXT | pending, placed, accepted, open, closing, closed |

### Position Functions

```python
# Initialize position manager
PositionManager(
    limits=PositionLimits(
        max_position_size_usd=Decimal("100000.00"),
        max_positions=10,
        max_exposure_pct=Decimal("100.00"),
    ),
    trading_mode="paper",   # "paper" or "live"
    exchange="coinbase",    # Exchange name
)

# Process order fill
manager.on_fill(
    order_id: str,
    product_id: str,
    side: str,              # "buy" or "sell"
    size: Decimal,
    fill_price: Decimal,
    pattern_id: str = None,
) -> None

# Update price for P&L calculation
manager.update_price(product_id: str, price: Decimal) -> None

# Update position status
manager.update_status(product_id: str, status: str) -> None

# Close position
manager.close_position(
    product_id: str,
    exit_price: Decimal,
    exit_reason: str = "manual",  # stop_loss, take_profit, trailing_stop, signal
    order_id: str = None,
) -> None

# Query positions
manager.get_positions() -> List[Position]
manager.get_position(product_id: str) -> Optional[Position]
manager.get_trade_history() -> List[ClosedTrade]
manager.get_core_trades() -> List[CoreClosedTrade]  # For fitness calculation
manager.get_portfolio_summary() -> PortfolioSummary
manager.can_open_position(product_id, side, size, price) -> tuple[bool, str]
```

### Position Data Structures

```python
@dataclass
class Position:
    position_id: str
    product_id: str
    side: str               # "long" or "short"
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    opened_at: datetime
    pattern_id: Optional[str]
    trading_mode: str       # "paper" or "live"
    exchange: str
    status: str

@dataclass
class ClosedTrade:
    trade_id: str
    product_id: str
    side: str
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    pattern_id: Optional[str]
    exit_reason: str        # manual, stop_loss, take_profit, trailing_stop, signal
```

---

## 12. RISK MANAGEMENT

### Database: `risk.db` (SQLite - state persistence)

### Risk Functions

```python
# Initialize risk manager
RiskManager(
    config=RiskConfig(...),
    initial_portfolio_value=Decimal("100000.00"),
    db_path="risk.db",
)

# Create risk config from agent traits (Evolution Discovers!)
create_risk_config_from_traits(traits: AgentTraits) -> RiskConfig

# Update portfolio value (triggers circuit breaker checks)
manager.update_portfolio_value(value: Decimal) -> None

# Set day start for daily loss limit
manager.set_day_start_value(value: Decimal) -> None

# Check trading status
manager.can_trade() -> bool
manager.get_risk_state() -> RiskState
manager.reset_circuit_breaker() -> None  # For paper trading

# Position risk management
manager.register_position(
    position_id, product_id, entry_price, size,
    side="long", stop_loss_price=None
) -> None
manager.update_position_price(position_id, price: Decimal) -> None
manager.get_stop_loss_alerts() -> List[PositionRisk]
manager.get_pending_close_orders() -> List[CloseOrder]

# Position sizing
manager.check_position_size(product_id, size, price) -> tuple[bool, Decimal, str]
manager.calculate_kelly_size(win_rate, avg_win, avg_loss) -> Decimal  # Kelly Criterion

# Metrics
manager.get_drawdown_metrics() -> DrawdownMetrics
manager.get_alerts() -> List[RiskAlert]
manager.can_open_position(product_id, size, price) -> tuple[bool, List[str]]
```

### Risk Config (Trait-Derived)

```python
@dataclass
class RiskConfig:
    max_portfolio_loss_pct: Decimal = Decimal("20.0")   # Stop at -20%
    max_position_loss_pct: Decimal = Decimal("15.0")    # Per-position stop
    max_daily_loss_pct: Decimal = Decimal("5.0")        # Daily limit
    max_position_size_pct: Decimal = Decimal("25.0")    # Max % of portfolio
    kelly_cap: Decimal = Decimal("0.25")                # Kelly fraction cap
    cooldown_minutes: int = 60                           # Post-trigger cooldown
    # Derived from agent traits:
    stop_loss_tightness: float = 0.5                    # 0=tight, 1=wide
    drawdown_sensitivity: float = 0.5                   # 0=tolerant, 1=sensitive

# Trait-derived mapping (risk_tolerance t = 0 to 1):
# t=0.1 (conservative): portfolio_loss=12%, daily=2.8%, position=7%
# t=0.5 (moderate):     portfolio_loss=20%, daily=5%,   position=15%
# t=0.9 (aggressive):   portfolio_loss=28%, daily=7.2%, position=23%
```

### Circuit Breaker States

```python
@dataclass
class RiskState:
    is_trading_enabled: bool
    circuit_breaker_triggered: bool
    reason: Optional[str]
    triggered_at: Optional[datetime]
    cooldown_ends_at: Optional[datetime]

@dataclass
class DrawdownMetrics:
    high_water_mark: Decimal
    current_drawdown_pct: Decimal
    max_drawdown_pct: Decimal
```

---

## 13. CANONICAL PERIODS (Regime Backtesting)

### 21+ Historical Periods Across 9 Regimes

```python
from canonical_periods import (
    CANONICAL_PERIODS,      # All 30+ periods
    get_periods_by_regime,
    get_periods_by_priority,
    get_period_by_id,
    ALL_REGIMES,
    PRIORITY_1,             # Must-test periods
    CRASH_PERIODS,
    BLOWOFF_PERIODS,
    BULL_PERIODS,
)

# Get periods for regime
crash_periods = get_periods_by_regime('crash')

# Get priority 1-2 periods only
important_periods = get_periods_by_priority(2)

# Get timestamps for backtest
period = get_period_by_id('crash_2020_mar')
start_ts, end_ts = period.to_timestamps()
```

### All 9 Regime Types

| Regime | Description | Example Periods |
|--------|-------------|-----------------|
| crash | Rapid violent drops | COVID Mar 2020 (-58%), LUNA May 2022 (-35%) |
| blowoff | Parabolic tops | Dec 2017 $20k, Nov 2021 $69k |
| recovery | V-shape rebounds | Post-COVID +163%, Post-FTX +88% |
| bull | Sustained uptrends | Q4 2017 +353%, 2024 ETF rally |
| bear | Extended grinds | 2018 full year -82%, 2022 H1 -63% |
| sideways | Range-bound | 2019 H2 $6.5k-$13k chop |
| volatile | High vol no direction | May 2021 China ban, Elon FUD |
| winter | Extended depression | Q4 2022 post-FTX malaise |
| transition | Regime changes | Oct 2020 bear-to-bull |

### Period Data Structure

```python
@dataclass
class CanonicalPeriod:
    period_id: str          # "crash_2020_mar"
    start: str              # ISO date "2020-03-08"
    end: str                # ISO date "2020-03-15"
    regime: str             # "crash"
    asset: str              # "BTC" (primary)
    description: str        # "COVID Black Thursday -58%"
    priority: int           # 1=must test, 2=should, 3=nice to have

    def to_timestamps() -> tuple[int, int]   # Millisecond timestamps
    def duration_days() -> int
```

**CLI:** `python canonical_periods.py --regime crash --list`

---

## 14. LIVE DATA COLLECTION

### 5-Exchange WebSocket Collector

Connects simultaneously to:
- Coinbase (spot)
- Binance US (spot)
- Hyperliquid (perps)
- dYdX (perps)
- Crypto.com (spot)

### Database: `live_data.db` (SQLite)

Tables: `trades`, `order_book_snapshots`, `funding_rates`, `open_interest`, `mark_prices`, `large_trades`, `book_tickers`, `klines`, `liquidations`

### Collector Functions

```python
# Initialize collector
LiveCollector(
    symbols=["BTC", "ETH", "SOL"],
    db_path="live_data.db",
    enable_coinbase=True,
    enable_binance=True,
    enable_hyperliquid=True,
    enable_dydx=True,
    enable_crypto=True,
)

# Start collection
await collector.start()
await collector.stop()

# Symbol presets (from arbitrage_assets.json)
# tier0: 65 assets on ALL 5 exchanges
# tier1: 70 assets on 4+ exchanges
# core: Top 20 most liquid
# full: All 105+ multi-exchange assets
```

**CLI:**
```bash
python live_collector.py --preset tier0    # All 5 exchanges
python live_collector.py --symbols BTC,ETH,SOL
python live_collector.py --preset full     # 105+ assets
```

### Data Collectors

| Collector | Data Types | Exchange |
|-----------|------------|----------|
| `live_collector.py` | All data | All 5 |
| `coinbase_tick_collector.py` | Trades | Coinbase |
| `enhanced_collector.py` | Extended data | Multi |
| `data_collectors/hyperliquid_collector.py` | Perps, funding | Hyperliquid |
| `data_collectors/fear_greed_collector.py` | Fear & Greed index | Alternative.me |
| `data_collectors/long_short_collector.py` | Long/short ratio | Binance |

---

## 15. DASHBOARDS & ADMIN

### Available Dashboards

| Dashboard | Port | Purpose |
|-----------|------|---------|
| `dashboard_server.py` | 8080 | Fitness leaderboard |
| `live_dashboard.py` | 8081 | Live trading view |
| `backtest_dashboard.py` | 8082 | Backtest results |
| `evolution_dashboard.py` | 8083 | Evolution cycle status |
| `system_dashboard.py` | 8084 | System health |
| `streamlit_dashboard.py` | 8501 | Interactive Streamlit UI |

### Dashboard API Endpoints

```python
# dashboard_server.py endpoints
GET /api/leaderboard     # Top 50 patterns by fitness
GET /api/status          # System status

# Returns:
{
    "total_results": 1234,
    "unique_patterns": 89,
    "unique_assets": 12,
    "avg_fitness": 52.3,
    "max_fitness": 87.2,
    "patterns": [...]
}
```

**CLI:**
```bash
python dashboard_server.py        # Start server on port 8080
python streamlit_dashboard.py     # Interactive Streamlit
python leaderboard.pyw            # GUI leaderboard viewer
```

---

## 16. TICK-LEVEL INDICATORS

### CVD (Cumulative Volume Delta)

```python
from indicators.cvd import CVDAccumulator

cvd = CVDAccumulator()

# Update with trade data
cvd.update(
    exchange="coinbase",
    symbol="BTC",
    side="buy",             # or "sell"
    size=0.5,
    price=50000.0,
    timestamp_ms=1234567890000,
)

# Get metrics
cvd.get_cvd("coinbase", "BTC") -> float          # Current CVD
cvd.get_state("coinbase", "BTC") -> CVDState     # Full state
cvd.get_momentum("coinbase", "BTC", periods=5) -> float  # CVD momentum
cvd.get_all_states() -> Dict                      # All symbols
```

### Order Book Analysis

```python
from indicators.order_book import OrderBookAnalyzer

analyzer = OrderBookAnalyzer(depth=10, wall_threshold=3.0)

# Analyze order book
metrics = analyzer.analyze(
    exchange="coinbase",
    symbol="BTC",
    bids=[(49900, 1.5), (49800, 2.0)],
    asks=[(50100, 1.0), (50200, 3.0)],
    timestamp_ms=1234567890000,
)

# Get metrics
analyzer.get_imbalance("coinbase", "BTC") -> float      # -1 to 1
analyzer.get_spread("coinbase", "BTC") -> float         # In BPS
analyzer.get_average_imbalance(..., periods=5) -> float
analyzer.get_imbalance_momentum(..., periods=5) -> float
analyzer.get_summary() -> Dict                           # All symbols
```

### Order Book Metrics

```python
@dataclass
class OrderBookMetrics:
    imbalance: float        # -1 (asks dominate) to +1 (bids dominate)
    spread_bps: float       # Spread in basis points
    bid_depth: float        # Total bid volume at depth
    ask_depth: float        # Total ask volume at depth
    bid_wall: Optional[float]   # Price level of bid wall (if detected)
    ask_wall: Optional[float]   # Price level of ask wall (if detected)
    timestamp_ms: int
```

---

## 17. COMMITTEE TRADING (Live Integration)

### Three Phases of Committee Trading

| Phase | Name | Description |
|-------|------|-------------|
| Phase 1 | Patterns Only | Pattern matching + portfolio constraints |
| Phase 2 | Single Agent | Agent with patterns + 22 traits + memory |
| Phase 3 | Full Hivemind | Committee voting with coach rosters |

### Committee Paper Trader

```python
# Phase 1: Patterns + portfolio constraints
Phase1PatternTrader(
    patterns: List[Pattern],
    max_positions=5,
    max_position_size_usd=1000.0,
)

# Phase 2: Single agent with traits
Phase2AgentTrader(
    agent: Agent,              # With 22 traits
    patterns: List[Pattern],
    risk_config: RiskConfig,   # Trait-derived thresholds
)

# Phase 3: Full committee voting
Phase3CommitteeTrader(
    committee: Committee,
    coach_rosters: Dict[str, List[Agent]],
    risk_config: RiskConfig,
)
```

**CLI:**
```bash
python committee_paper_trader.py --phase 1 --symbol BTC-USD  # Patterns only
python committee_paper_trader.py --phase 2 --symbol BTC-USD  # Single agent
python committee_paper_trader.py --phase 3 --symbol BTC-USD  # Full hivemind
```

### Committee Tick Trader

```python
# Data flow:
# Tick Data -> MultiTimeframeCandleBuilder -> Indicators -> Committee Vote -> Trade

# Timeframes built from ticks: 1m, 5m, 15m, 1h, 4h, 1d (simultaneously)

# Replay historical ticks with committee voting
CommitteeTickTrader(
    symbol="BTC-USD",
    mode="replay",           # or "live"
    min_fitness=70,          # Minimum pattern fitness
    committee: Committee,
)

# Load ticks from PostgreSQL
load_ticks_from_db(symbol: str, limit: int = 100000) -> List[Dict]
```

**CLI:**
```bash
python committee_tick_trader.py --symbol BTC-USD --replay           # Replay mode
python committee_tick_trader.py --symbol BTC-USD --live             # Live mode
python committee_tick_trader.py --symbol BTC-USD --replay --min-fitness 70
```

### Multi-Timeframe Candle Building

```python
from tick_replay_trader import MultiTimeframeCandleBuilder, MTFIndicatorCache

# Build candles from ticks across all timeframes
mtf = MultiTimeframeCandleBuilder()
mtf.on_tick(price, size, timestamp_ms, side)

# Get candles for specific timeframe
candles_1h = mtf.get_candles("1h")
candles_1d = mtf.get_candles("1d")

# Get indicators across timeframes
cache = MTFIndicatorCache()
indicators = cache.get_indicators("1h")  # RSI, MACD, etc.
```

---

## MCP Tool Categories

For the MCP server, organize tools into these categories:

1. **patterns** - CRUD + backtest + stats
2. **agents** - CRUD + traits + memory
3. **coaches** - CRUD + roster selection
4. **committee** - Voting + decisions
5. **evolution** - Cycle control + selection
6. **trading** - Positions + orders + execution
7. **data** - OHLCV + ticks + indicators
8. **crucible** - Leaderboard + submissions
9. **backtest** - Run + queue + results
10. **system** - Status + logs + admin
11. **positions** - Position tracking + P&L
12. **risk** - Circuit breakers + limits + Kelly
13. **regimes** - Canonical periods + regime detection
14. **live** - Data collection + WebSocket feeds
15. **dashboard** - Leaderboard + status APIs
16. **indicators** - CVD + order book + tick metrics
17. **committee_trading** - Hivemind paper/live trading
