# Fast_Swarm Database Schema Reference

> **Generated from live PostgreSQL database inspection**
> Last updated: 2026-01-06

---

## Overview

The Coinswarm PostgreSQL database contains **77 tables** - significantly more than documented in the schema migration files. This document reflects the **actual live database state**.

---

## Table Inventory (77 tables)

### Core Trading Tables
| Table | Size | Rows | Purpose |
|-------|------|------|---------|
| `agents` | 8,962 MB | 1,917 | Trading agents with traits, memory, performance |
| `patterns` | 15 MB | 180 | Trading pattern definitions and fitness |
| `backtest_trades_unified` | 1,623 MB | - | Consolidated backtest/simulated trades |
| `backtest_results` | 3,568 KB | - | Historical backtest runs per pattern |
| `chaos_trades` | 2,440 KB | - | Random trades for pattern discovery |
| `agent_trades` | - | - | Individual agent trade history |

### Market Data Tables (TimescaleDB Hypertables)
| Table | Size | Rows | Date Range | Purpose |
|-------|------|------|------------|---------|
| `enhanced_candles` | **5.8 GB** (compressed) | **5,281,846** | 2017-01 to 2025-12 | OHLCV + 200+ pre-computed indicators |
| `exchange_ticks` | 2,740 MB | **12,506,501** | 2025-06 to 2026-01 | Real-time trades from exchanges |
| `agent_trades` | **18 GB** | - | - | Individual agent trade history (backtests) |
| `order_book_snapshots` | 284 MB | - | - | L2 orderbook snapshots |
| `market_trades` | 140 MB | - | - | Raw exchange trades for CVD |
| `funding_rates` | 46 MB | - | - | Perpetuals funding rates (hypertable) |
| `cvd_1min` | 43 MB | - | - | Cumulative volume delta |
| `candles` | 0 | 0 | - | Legacy table (empty, use `enhanced_candles`) |
| `exchange_candles` | 0 | 0 | - | Legacy table (empty) |
| `tickers` | 0 | 0 | - | Real-time ticker snapshots (empty) |
| `klines` | - | - | - | Kline data |
| `klines_hist` | 1,408 KB | - | - | Historical klines |
| `book_ticker` | - | - | - | Best bid/ask |
| `mark_price` | - | - | - | Mark price data |

### Sentiment & Macro Tables
| Table | Purpose |
|-------|---------|
| `fear_greed_index` | Crypto fear & greed index |
| `market_sentiment` | Aggregated sentiment scores |
| `btc_dominance` | BTC market dominance % |
| `defi_tvl` | DeFi total value locked |
| `tradfi_prices` | Traditional finance prices |
| `gas_prices` | Ethereum gas prices |
| `long_short_ratio` | Long/short ratio data |
| `long_short_ratios` | Historical L/S ratios |
| `open_interest` | Open interest snapshots |
| `open_interest_hist` | Historical OI |
| `funding_rates` | Perpetuals funding rates |
| `funding_rates_hist` | Historical funding |
| `liquidations` | Liquidation events |
| `large_trades` | Whale trade detection |

### Memory System Tables
| Table | Size | Rows | Purpose |
|-------|------|------|---------|
| `agent_memories` | 112 KB | 45 | Typed episodic memories |
| `wisdom` | - | - | Distilled swarm wisdom |
| `distillations` | - | - | Knowledge distillation records |

### Committee/Governance Tables
| Table | Purpose |
|-------|---------|
| `committees` | Multi-agent voting committees |
| `committee_votes` | Individual agent votes |
| `committee_decisions` | Aggregated decisions (BUY/SELL/HOLD) |
| `vote_outcomes` | Vote accuracy tracking |
| `agent_vote_accuracy` | Per-agent accuracy stats |
| `coaches` | Agent managers (roster selection) |
| `coach_rosters` | Coach-agent assignments |

### Evolution Tables
| Table | Size | Rows | Purpose |
|-------|------|------|---------|
| `evolution_cycles` | 96 KB | 43 | Evolution cycle state |
| `evolution_events` | - | - | Detailed evolution log |
| `walk_forward_results` | - | - | Train/test validation |
| `canonical_periods` | - | - | Defined test periods |

### Live/Paper Trading Tables
| Table | Purpose |
|-------|---------|
| `live_positions` | Current open live positions |
| `live_trades_unified` | Historical live executions |
| `live_trade_history` | Live trade audit log |
| `paper_trades` | Paper trading records |
| `paper_positions` | Open paper positions |
| `crucible_entries` | Agent qualification attempts |

### Pattern Analysis Tables
| Table | Purpose |
|-------|---------|
| `entries` | Entry signal definitions |
| `exits` | Exit signal definitions |
| `pattern_runs` | Individual pattern test runs |
| `translated_patterns` | Human-readable pattern translations |
| `indicator_affinity` | Indicator correlation analysis |
| `trailing_stops` | Trailing stop configurations |
| `dynamic_trailing_stops` | Dynamic trail parameters |
| `atr_chandelier_stops` | ATR-based stop logic |
| `execution_stats` | Execution performance metrics |
| `ml_backtest_results` | ML-enhanced backtest data |

### Nostr Integration Tables
| Table | Purpose |
|-------|---------|
| `relays` | Nostr relay discovery |
| `accounts` | Nostr accounts/pubkeys |
| `relay_account_edges` | Account-relay relationships |
| `follow_graph` | PageRank follow data |
| `nostr_events` | Nostr event stream |

### Vector Embeddings Tables
| Table | Purpose |
|-------|---------|
| `pattern_embeddings` | Pattern similarity vectors |
| `account_embeddings` | Account ML predictors |
| `nostr_post_embeddings` | Nostr content embeddings |

### Infrastructure Tables
| Table | Purpose |
|-------|---------|
| `exchange_state` | Exchange connection state |
| `trades_live` | Live trade stream |
| `data_sources` | Data source health tracking |
| `daemon_state` | Daemon heartbeat/coordination |
| `backfill_progress` | Data backfill tracking |
| `papers` | Research paper references |

---

## Key Schema Differences: Model vs Database

### `candles` vs `exchange_candles`

**`candles` table (what Fast_Swarm model expects):**
```
id, asset, timeframe, timestamp (int), open, high, low, close, volume, exchange, quote_volume, is_closed
```

**`exchange_candles` table (TimescaleDB hypertable):**
```
time (timestamptz), exchange, symbol, timeframe, open, high, low, close, volume, trades
```

**Key differences:**
- `candles.timestamp` = integer (epoch), `exchange_candles.time` = timestamptz
- `candles.asset` vs `exchange_candles.symbol`
- Both are currently **empty** (0 rows)

### `agents` table (actual schema)
```sql
id, agent_id, name, elo_rating (default 1500), generation, is_active,
traits (JSONB), assigned_patterns (JSONB), coach_id,
total_trades, winning_trades, total_pnl, win_rate,
episodic_memory (JSONB), semantic_memory (JSONB), wisdom (JSONB),
created_at, updated_at, fitness, fitness_score, sharpe_ratio, max_drawdown_pct,
backtest_stats (JSONB), backtest_runs, sortino_ratio, calmar_ratio,
annualized_roi_pct, last_backtest_at, level, status, pattern_weights (JSONB),
parent_a_id, parent_b_id, trading_philosophy, backtest_count
```

**Note:** The `agents` table stores memory as JSONB columns (`episodic_memory`, `semantic_memory`, `wisdom`) in addition to the separate `agent_memories` table.

---

## Data Population Status

| Category | Status |
|----------|--------|
| Agents | ✅ 1,917 agents |
| Patterns | ✅ 180 patterns (pg_stat shows 180, actual may differ) |
| Agent Memories | ✅ 45 memories |
| Evolution Cycles | ✅ 43 cycles |
| Exchange Ticks | ✅ 2.7 GB of tick data |
| Backtest Trades | ✅ 1.6 GB unified trades |
| Candles (both tables) | ❌ Empty |
| Tickers | ❌ Empty |
| Live Trades | ❌ Empty |

---

## Fast_Swarm Model Compatibility

| Model | `__tablename__` | DB Table Exists | Data? | Compatible? |
|-------|-----------------|-----------------|-------|-------------|
| `Agent` | `agents` | ✅ | ✅ 1,917 | ✅ Yes |
| `Pattern` | `patterns` | ✅ | ✅ 180+ | ✅ Yes |
| `Candle` | `candles` | ✅ | ❌ Empty | ⚠️ Schema match, no data |
| `Ticker` | `tickers` | ✅ | ❌ Empty | ⚠️ Schema match, no data |
| `AgentMemory` | `agent_memories` | ✅ | ✅ 45 | ✅ Yes |
| `Wisdom` | `wisdom` | ✅ | ? | ✅ Yes |
| `ExchangeState` | `exchange_state` | ✅ | ? | ✅ Yes |
| `Trade` (exchange) | `trades_live` | ✅ | ❌ Empty | ✅ Yes |
| `BacktestTrade` | `backtest_trades_unified` | ✅ | ✅ Large | ✅ Yes |
| `Committee` | `committees` | ✅ | ? | ✅ Yes |
| `CommitteeVote` | `committee_votes` | ✅ | ? | ✅ Yes |
| `CommitteeDecision` | `committee_decisions` | ✅ | ? | ✅ Yes |
| `EvolutionCycle` | `evolution_cycles` | ✅ | ✅ 43 | ✅ Yes |
| `CrucibleEntry` | `crucible_entries` | ✅ | ? | ✅ Yes |

---

## Why Dashboard Can't See Candle Data

**ROOT CAUSE: Table Name Mismatch**

The Fast_Swarm `Candle` model has `__tablename__ = "candles"`, but the actual data is stored in `enhanced_candles`:

| Model Expects | Actual Data Location | Status |
|---------------|---------------------|--------|
| `candles` | `enhanced_candles` | ❌ **Model points to empty table** |
| `tickers` | (none) | ❌ No real-time ticker snapshots |

**The Fix:** Change `Candle` model's `__tablename__` from `"candles"` to `"enhanced_candles"`, OR create a view.

### Data IS Available

| Data Type | Table | Rows | Coverage |
|-----------|-------|------|----------|
| OHLCV + Indicators | `enhanced_candles` | 5.2M | 2017-2025 |
| Tick Trades | `exchange_ticks` | 12.5M | 2025-06 to 2026-01 |
| Order Books | `order_book_snapshots` | - | - |
| Agent Trades | `agent_trades` | 18GB | Backtest history |

---

## `enhanced_candles` Schema (200+ Indicators)

The main candle table includes pre-computed technical indicators:

**Core OHLCV:** `time`, `exchange`, `symbol`, `timeframe`, `open`, `high`, `low`, `close`, `volume`

**Moving Averages:** `sma_20`, `sma_50`, `sma_200`, `ema_9`, `ema_12`, `ema_21`, `ema_26`, `hma_20`, `vwma_10`, `dema_21`, `tema_21`, `wma_20`, `kama_10`, `zlema_10`, `t3_10`

**Oscillators:** `rsi_7`, `rsi_14`, `rsi_21`, `stoch_k`, `stoch_d`, `stochrsi_k`, `stochrsi_d`, `cci_14`, `cci_20`, `willr_14`, `roc_10`, `mom_10`, `ao`, `uo`, `cmo_14`, `tsi`, `tsi_signal`

**MACD Family:** `macd_line`, `macd_signal`, `macd_histogram`, `ppo`, `ppo_hist`, `ppo_signal`

**Bollinger/Keltner:** `bb_upper`, `bb_middle`, `bb_lower`, `bb_width`, `bb_pct`, `kc_upper`, `kc_middle`, `kc_lower`

**Volatility:** `atr_7`, `atr_14`, `natr_14`, `true_range`, `stdev_14`, `zscore_14`, `zscore_30`, `zscore_50`, `chop_14`

**Volume:** `obv`, `volume_sma_20`, `obv_sma_20`, `cmf_20`, `mfi_14`, `pvt`, `nvi`, `pvi`, `ad`, `efi_13`, `eom_14`, `kvo`, `kvo_signal`

**Trend:** `adx_14`, `adxr_14`, `plus_di`, `minus_di`, `aroon_up`, `aroon_down`, `aroon_osc`, `supertrend`, `supertrend_direction`

**Ichimoku:** `ichi_tenkan`, `ichi_kijun`, `ichi_senkou_a`, `ichi_senkou_b`, `ichi_chikou`

**Other:** `vwap`, `fisher`, `fisher_signal`, `psar_long`, `psar_short`, `kdj_k`, `kdj_d`, `kdj_j`, `vortex_pos`, `vortex_neg`

**Heikin-Ashi:** `ha_open`, `ha_high`, `ha_low`, `ha_close`

**Cross-Asset:** `btc_eth_correlation_14d`, `eth_btc_ratio`, `alt_dominance_pct`, `btc_volume_dominance_pct`

**Sentiment:** `fear_greed_value`, `fear_greed_class`

**Regime:** `regime`, `regime_encoded`

**Tick Aggregates:** `tick_cvd_ratio`, `tick_trade_imbalance`, `tick_buy_volume_pct`, `tick_volatility`, `tick_momentum`, `tick_vwap_deviation`, `tick_large_trade_ratio`

**Order Book:** `book_avg_spread_bps`, `book_spread_volatility`, `book_avg_imbalance`, `book_imbalance_volatility`, `book_depth_ratio`

---

## Largest Tables (by size)

1. `agent_trades` - **18 GB** (hypertable, backtest trade history)
2. `agents` - **8.9 GB** (JSONB memory fields are huge)
3. `enhanced_candles` - **5.8 GB** compressed (5.2M candles with 200+ indicators)
4. `exchange_ticks` - **2.7 GB** (12.5M tick records)
5. `backtest_trades_unified` - **1.6 GB** (consolidated backtest trades)
6. `order_book_snapshots` - **284 MB**
7. `market_trades` - **140 MB**
