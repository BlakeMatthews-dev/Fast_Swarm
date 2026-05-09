# Coinswarm Data Pipeline

> **Complete data acquisition, storage, and distribution architecture for the Coinswarm trading system.**

This document specifies how data flows from external sources through the hierarchical decision system. All data pathways are **append-only** and **versioned**, enabling reconstruction of context at any point in time.

---

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [Data Sources](#data-sources)
3. [Layer-Specific Data Feeds](#layer-specific-data-feeds)
4. [Storage Architecture](#storage-architecture)
5. [Cloudflare Workers Pipeline](#cloudflare-workers-pipeline)
6. [Data Quality & Validation](#data-quality--validation)
7. [Rate Limits & Optimization](#rate-limits--optimization)
8. [Schema Reference](#schema-reference)

---

## Pipeline Overview

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA ACQUISITION LAYER                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Exchanges│  │   News   │  │ On-Chain │  │   Macro  │       │
│  │ REST/WS  │  │Sentiment │  │  Funding │  │  FX/Rates│       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼──────────────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STORAGE & ROUTING                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ D1 SQLite    │  │  KV Cache    │  │  R2 Storage  │         │
│  │ (Cloudflare) │  │ (hot data)   │  │ (historical) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    HIERARCHICAL LAYERS                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ PLANNERS (15min-6h)                                       │  │
│  │ ← Sentiment, Funding, Macro, OHLCV-1h/1d                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ COMMITTEE (ms-s)                                          │  │
│  │ ← LOB ticks, trades, spreads, imbalance                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ MEMORY OPTIMIZER (continuous)                             │  │
│  │ ← Execution logs, micro-performance metrics              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principle

All data pathways are **append-only** and **versioned**, enabling planners to reconstruct context at any point in time and verify that medium/long-term decisions are built on the same factual base the short-term memory experienced.

---

## Data Sources

### Exchange APIs (Primary)

| Exchange | REST | WebSocket | Data Types | Rate Limits | Status |
|----------|------|-----------|------------|-------------|--------|
| **Binance** | ✓ | ✓ | OHLCV, Trades, L2, Funding | 1200 weight/min | **Active** |
| **CoinGecko** | ✓ | - | OHLCV (daily), Market Cap | 30 calls/min (free) | **Active** |
| **CryptoCompare** | ✓ | ✓ | OHLCV (minute), Social | 30 calls/min (free) | **Active** |
| **Kraken** | ✓ | ✓ | OHLCV, Trades, L2 | 720 candles/req | **Active** |
| **Coinbase** | ✓ | ✓ | OHLCV, Trades, L2 | 10/s public | **Planned** |

### Sentiment & News

| Source | Type | Frequency | Coverage | Status |
|--------|------|-----------|----------|--------|
| **Fear & Greed Index** | REST | Daily | BTC sentiment | **Active** |
| **NewsAPI** | REST | Real-time | Crypto news | Optional |
| **FRED** | REST | Daily | Macro indicators | Optional |

### Tokens Tracked

```
Primary: BTC, ETH, SOL, BNB, ADA, DOT
Quote: USDT, USDC, BUSD
Cross: BTC-SOL, ETH-BTC
```

---

## Layer-Specific Data Feeds

### 1. Planners (Long/Medium-Term)

**Purpose:** Detect regime and sentiment shifts for committee re-weighting.

| Data Type | Frequency | Source | Storage |
|-----------|-----------|--------|---------|
| OHLCV (1h, 4h, 1d) | Every 15min | Binance | D1 |
| Funding rates | Hourly | Binance/Bybit | D1 |
| Fear & Greed | Daily | alternative.me | D1 |
| Sentiment embeddings | Hourly | NewsAPI | D1 |
| Macro indicators | Daily | FRED | D1 |

**Access Pattern:**
```python
# Planners pull rolling windows
data = planner_data_client.get_features(
    symbols=["BTC-USD", "ETH-USD"],
    sources=["funding", "sentiment", "macro"],
    window_days=30,
    granularity="1h"
)
```

### 2. Committee Agents (Intra-Day Tactical)

**Purpose:** Respond to real-time order-book and flow conditions.

| Data Type | Frequency | Source | Storage |
|-----------|-----------|--------|---------|
| Tick trades | Milliseconds | Binance WS | Redis Streams |
| L2 order book | Real-time | Binance WS | KV (hot cache) |
| Spread & imbalance | Real-time | Derived | In-memory |
| Price snapshots | Every minute | Multi-source | D1 |

**Access Pattern:**
```python
# Committee agents subscribe to real-time streams
async for message in committee_data_client.subscribe("BTC-USD:trades"):
    trade = parse_trade(message)
    features = extract_features(trade, lookback_window="10s")
    action = agent.decide(features)
```

### 3. Memory Optimizer (Adaptive)

**Purpose:** Refine execution tactics and pattern clustering.

| Data Type | Frequency | Source | Storage |
|-----------|-----------|--------|---------|
| (state, action, reward) | Per trade | Execution | Redis Vector |
| Trade P&L | Per trade | Execution | D1 |
| Slippage metrics | Per trade | Execution | D1 |
| Pattern clusters | Continuous | ML | Redis |

**Access Pattern:**
```python
# Memory optimizer writes after each trade
memory_optimizer.record_episode(
    state_vector=phi_t,
    action=action,
    reward=pnl,
    metadata={"slippage_bps": slippage, "latency_ms": latency}
)
```

### 4. Self-Reflection (Governance)

**Purpose:** Audit performance and trigger meta-learning.

| Data Type | Frequency | Source | Storage |
|-----------|-----------|--------|---------|
| Realized vs expected P&L | Hourly | Aggregated | D1 |
| Sharpe ratio drift | Daily | Calculated | D1 |
| Violation logs | Real-time | Risk system | D1 |
| Quorum outcomes | Per decision | Governance | D1 |

---

## Storage Architecture

### Cloudflare D1 (Primary)

**Purpose:** Persistent storage for all structured data.

```sql
-- Price data table (OHLCV)
CREATE TABLE price_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    timeframe TEXT NOT NULL,        -- '1m', '5m', '1h', '1d'
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    source TEXT DEFAULT 'binance',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(token, timestamp, timeframe, source)
);

-- Create indexes for fast queries
CREATE INDEX idx_price_token_ts ON price_data(token, timestamp DESC);
CREATE INDEX idx_price_timeframe ON price_data(timeframe, timestamp DESC);
```

### Cloudflare KV (Hot Cache)

**Purpose:** Sub-millisecond reads for frequently accessed data.

```typescript
// Cache structure
KV_MARKET: {
  "market:BTC-USD": { price: 50000, volume: 1234, timestamp: ... },
  "market:ETH-USD": { price: 3000, volume: 5678, timestamp: ... }
}

KV_PREDICTIONS: {
  "pred:BTC-USD": { signal: "BUY", confidence: 0.85, expires: 5s },
  "pred:ETH-USD": { signal: "HOLD", confidence: 0.72, expires: 5s }
}
```

**TTL Strategy:**
- Market data: 1-5 seconds
- Predictions: 5 seconds
- Patterns: 60 seconds

### Cloudflare R2 (Cold Storage)

**Purpose:** Long-term historical data archive.

```
r2://coinswarm-data/
├── historical/
│   ├── ohlcv/
│   │   ├── BTC-USD-2024-01.parquet
│   │   ├── BTC-USD-2024-02.parquet
│   │   └── ...
│   └── sentiment/
│       └── 2024-01-embeddings.parquet
├── backtests/
│   └── results/
└── exports/
```

---

## Cloudflare Workers Pipeline

### Historical Data Worker

**File:** `cloudflare-agents/historical-data-worker.ts`

```
┌─────────────────────────────────────────────────────────────┐
│              HISTORICAL DATA WORKER                          │
│                                                              │
│  Endpoints:                                                  │
│  ├── POST /fetch - Trigger historical data fetch            │
│  ├── GET /data/{pair}/{start}/{end} - Get cached data       │
│  ├── GET /random - Get random segment for testing           │
│  └── GET /pairs - List available pairs                      │
│                                                              │
│  Data Sources (5-source fallback):                          │
│  1. Binance.US (primary)                                    │
│  2. CryptoCompare (backup)                                  │
│  3. CoinGecko (daily only)                                  │
│  4. Kraken (limited pairs)                                  │
│  5. Fear & Greed (sentiment only)                           │
└─────────────────────────────────────────────────────────────┘
```

**Cron Schedule:** Hourly

### Evolution Agent Pipeline

**File:** `cloudflare-agents/evolution-agent-simple.ts`

```
┌─────────────────────────────────────────────────────────────┐
│              EVOLUTION AGENT DATA FLOW                       │
│                                                              │
│  Every 60 seconds:                                           │
│  1. Fetch real historical candles from D1                   │
│  2. Generate 50 random entry/exit trades                    │
│  3. Calculate technical indicators at entry:                │
│     - momentum_1, momentum_5                                │
│     - volatility                                            │
│     - price vs SMA10                                        │
│     - volume vs average                                     │
│  4. Record outcome (profitable: 0 or 1)                     │
│  5. Store in chaos_trades table                             │
│                                                              │
│  Every 5 cycles:                                             │
│  - Pattern discovery (statistical analysis)                 │
│  - Compare winners vs losers                                │
│  - Store patterns with positive edge                        │
│                                                              │
│  Every 10 cycles:                                            │
│  - Backtest patterns against historical data                │
│  - Update annualized_roi_pct, win_rate                      │
│  - Promote/demote patterns based on performance             │
└─────────────────────────────────────────────────────────────┘
```

**Cron Schedule:** Every minute (`* * * * *`)

### Real-Time Price Worker

**File:** `cloudflare-agents/realtime-price-cron.ts`

```
Algorithm: Leaky bucket with intelligent round-robin
Rate limits: 25% of each API max capacity

┌─────────────────────────────────────────────────────────────┐
│              REAL-TIME PRICE COLLECTION                      │
│                                                              │
│  Sources (round-robin):                                      │
│  ├── Binance (5 tokens/request)                             │
│  ├── CryptoCompare (3 tokens/request)                       │
│  └── CoinGecko (fallback)                                   │
│                                                              │
│  Output: D1 price_data table                                │
│  Endpoints:                                                  │
│  ├── /status - Collection status                            │
│  └── /latest - Latest prices                                │
└─────────────────────────────────────────────────────────────┘
```

**Cron Schedule:** Every minute

### Technical Indicators Worker

**File:** `cloudflare-agents/technical-indicators-agent.ts`

```
┌─────────────────────────────────────────────────────────────┐
│              TECHNICAL INDICATORS                            │
│                                                              │
│  Calculated hourly:                                          │
│  ├── SMA (10, 20, 50, 200)                                  │
│  ├── EMA (12, 26)                                           │
│  ├── RSI (14)                                               │
│  ├── MACD (12, 26, 9)                                       │
│  ├── Bollinger Bands (20, 2)                                │
│  ├── ATR (14)                                               │
│  └── Volume profile                                          │
│                                                              │
│  Storage: D1 technical_indicators table                     │
└─────────────────────────────────────────────────────────────┘
```

**Cron Schedule:** Hourly

---

## Data Quality & Validation

### Quality Checks

```typescript
interface DataQuality {
  completeness: number;    // 0-1: % of expected data points
  freshness: number;       // seconds since last update
  consistency: number;     // 0-1: cross-source agreement
  outliers: number;        // count of detected outliers
}

async function validateData(data: OHLCVCandle[]): DataQuality {
  return {
    completeness: checkGaps(data),
    freshness: Date.now() - data[data.length-1].timestamp,
    consistency: crossValidateSources(data),
    outliers: detectOutliers(data, 'close')
  };
}
```

### Gap Detection

```sql
-- Find gaps in price data
SELECT
    token,
    timestamp,
    LEAD(timestamp) OVER (PARTITION BY token ORDER BY timestamp) as next_ts,
    (LEAD(timestamp) OVER (PARTITION BY token ORDER BY timestamp) - timestamp) as gap_seconds
FROM price_data
WHERE gap_seconds > 120  -- More than 2 minutes
ORDER BY gap_seconds DESC;
```

### Outlier Detection

```python
def detect_outliers(data: List[float], field: str) -> List[int]:
    """IQR-based outlier detection"""
    values = [d[field] for d in data]
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [i for i, v in enumerate(values) if v < lower or v > upper]
```

---

## Rate Limits & Optimization

### API Rate Limits

| Source | Free Tier | Paid Tier | Strategy |
|--------|-----------|-----------|----------|
| **Binance** | 1200 weight/min | 2400/min | Batch requests, use weight efficiently |
| **CoinGecko** | 30/min | 500/min | Cache aggressively, daily data only |
| **CryptoCompare** | 100K/month | Unlimited | Use for minute data backup |
| **Kraken** | 15/sec | Same | Use for cross-validation |

### Optimization Strategies

**1. Batch Requests:**
```typescript
// Instead of 10 separate requests
const prices = await Promise.all(tokens.map(t => fetchPrice(t)));

// Use batch endpoint
const prices = await fetchPrices(tokens.join(','));  // 1 request for 10 tokens
```

**2. Aggressive Caching:**
```typescript
// KV cache with short TTL
const cached = await env.KV.get(`price:${symbol}`);
if (cached && JSON.parse(cached).timestamp > Date.now() - 5000) {
  return cached;  // Cache hit: 0 API calls
}
```

**3. Fallback Chain:**
```typescript
async function fetchWithFallback(symbol: string): Promise<Price> {
  try {
    return await binance.fetchPrice(symbol);
  } catch {
    try {
      return await cryptocompare.fetchPrice(symbol);
    } catch {
      return await coingecko.fetchPrice(symbol);
    }
  }
}
```

**4. Request Deduplication:**
```typescript
// Dedupe concurrent requests for same data
const pending = new Map<string, Promise<any>>();

async function fetchDeduped(key: string): Promise<any> {
  if (pending.has(key)) {
    return pending.get(key);
  }
  const promise = actualFetch(key);
  pending.set(key, promise);
  try {
    return await promise;
  } finally {
    pending.delete(key);
  }
}
```

---

## Schema Reference

### price_data

```sql
CREATE TABLE price_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,           -- 'BTC', 'ETH', 'SOL'
    timestamp INTEGER NOT NULL,    -- Unix timestamp (seconds)
    timeframe TEXT NOT NULL,       -- '1m', '5m', '1h', '1d'
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    source TEXT DEFAULT 'binance', -- Data source
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(token, timestamp, timeframe, source)
);
```

### chaos_trades

```sql
CREATE TABLE chaos_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    entry_time INTEGER NOT NULL,
    exit_time INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    profitable INTEGER NOT NULL,    -- 0 or 1
    pnl_pct REAL,

    -- Technical indicators at entry
    momentum_1 REAL,
    momentum_5 REAL,
    volatility REAL,
    volume_ratio REAL,
    rsi_14 REAL,
    sma_cross REAL,

    created_at TEXT DEFAULT (datetime('now'))
);
```

### discovered_patterns

```sql
CREATE TABLE discovered_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,             -- 'momentum_breakout_v1'
    conditions TEXT NOT NULL,       -- JSON conditions
    votes INTEGER DEFAULT 0,        -- Net votes from testing
    win_rate REAL,
    avg_return_pct REAL,
    annualized_roi_pct REAL,
    sample_size INTEGER DEFAULT 0,
    tested_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### technical_indicators

```sql
CREATE TABLE technical_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    timeframe TEXT NOT NULL,

    -- Moving averages
    sma_10 REAL,
    sma_20 REAL,
    sma_50 REAL,
    sma_200 REAL,
    ema_12 REAL,
    ema_26 REAL,

    -- Oscillators
    rsi_14 REAL,
    macd_line REAL,
    macd_signal REAL,
    macd_histogram REAL,

    -- Volatility
    atr_14 REAL,
    bb_upper REAL,
    bb_middle REAL,
    bb_lower REAL,

    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(token, timestamp, timeframe)
);
```

---

## Data Lineage

### Traceability

Every data point includes:
```json
{
  "source": "binance",
  "symbol": "BTC-USD",
  "timeframe": "1m",
  "timestamp": 1698765432000,
  "ingested_at": "2025-10-31T12:00:00Z",
  "quality_score": 0.98,
  "version": "v1.2"
}
```

### Audit Trail

```sql
-- Track all data mutations
CREATE TABLE data_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    operation TEXT NOT NULL,        -- INSERT, UPDATE, DELETE
    old_value TEXT,
    new_value TEXT,
    performed_by TEXT,
    performed_at TEXT DEFAULT (datetime('now'))
);
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture overview
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [AGENTS.md](AGENTS.md) - Agent implementation details

---

*Last Updated: 2025-11-29*
*Consolidated from data-feeds-architecture.md and related sources*
# Coinswarm D1 Database Sharding Strategy

**Version:** 1.0.0
**Created:** 2025-11-30
**Status:** Ready for Implementation

---

## Overview

This document describes the D1 database sharding strategy for storing 5+ years of OHLCV data across 142 token pairs and 8 timeframes.

### Why Sharding?

Cloudflare D1 has practical limits that require distributing data across multiple databases:

| Limit | D1 Value | Our Need | Solution |
|-------|----------|----------|----------|
| Max database size | 10GB | ~100GB total | 4 shards |
| Rows per query | 1000 | Variable | Pagination |
| Write throughput | 100k rows/sec | High during backfill | Queue batching |

### Sharding Goals

1. **Isolate hot data** - BTC/ETH get most queries, keep them separate
2. **Group by access pattern** - TradFi has different hours than crypto
3. **Balance load** - Distribute pairs evenly across shards
4. **Enable parallelism** - Backfill/collection can run per-shard

---

## Shard Architecture

**Hot Shards (1-4):** 1m, 15m, 1h, 1d - organized by ecosystem
**Cold Shard (5):** 1w - all tokens, separated for access latency
**Total Storage: ~4-5 GB** across 5 shards

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COINSWARM DATA SHARDS (Hot/Cold Split)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ══════════════════════════ HOT SHARDS (1-4) ══════════════════════════════ │
│                                                                              │
│  SHARD 1: MAJORS + ETH        SHARD 2: TRADFI + L2s                         │
│  ┌─────────────────────┐      ┌─────────────────────┐                       │
│  │ 55 pairs            │      │ 17 pairs            │                       │
│  │ BTC, ETH, XRP, SOL  │      │ MSTR, IBIT, FBTC    │                       │
│  │ + 11 other majors   │      │ GBTC, ETHE + L2s    │                       │
│  │ PEPE, SHIB, FLOKI   │      │                     │                       │
│  │                     │      │ Timeframes: 1h, 1d  │                       │
│  │ BTC/ETH: 1m,15m,1h, │      │ Source: Yahoo/      │                       │
│  │          1d FOREVER │      │         Binance     │                       │
│  │ Others: 1h,1d (5y)  │      │ Est: ~150 MB        │                       │
│  │ Est: ~1.5 GB        │      │                     │                       │
│  └─────────────────────┘      └─────────────────────┘                       │
│                                                                              │
│  SHARD 3: SOLANA ECOSYSTEM    SHARD 4: BNB ECOSYSTEM                        │
│  ┌─────────────────────┐      ┌─────────────────────┐                       │
│  │ 105 pairs           │      │ 46 pairs            │                       │
│  │ RAY, JUP, BONK...   │      │ BNB, CAKE, XVS      │                       │
│  │ + Educational:      │      │ + Educational:      │                       │
│  │   Rugs, Flops, Meh  │      │   Rugs, Flops, Meh  │                       │
│  │                     │      │                     │                       │
│  │ SOL: 1m,15m,1h,1d   │      │ Timeframes: 1h, 1d  │                       │
│  │      FOREVER        │      │ Source: Binance     │                       │
│  │ Others: 1h,1d (5y)  │      │ Est: ~600 MB        │                       │
│  │ Est: ~1.5 GB        │      │                     │                       │
│  └─────────────────────┘      └─────────────────────┘                       │
│                                                                              │
│  ══════════════════════════ COLD SHARD (5) ════════════════════════════════ │
│                                                                              │
│  SHARD 5: WEEKLY DATA (ALL TOKENS)                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 223 pairs (ALL ecosystems)                                          │    │
│  │ Timeframe: 1w only                                                  │    │
│  │ Retention: 5 years                                                  │    │
│  │ Purpose: Long-term trend analysis, separate from hot query paths    │    │
│  │ Est: ~15 MB (261 rows/pair × 223 pairs × 200B)                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Design: Educational tokens mixed with production for ML pattern training   │
│  Cost: ~$5-10/mo (storage + reads under free tier)                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Shard Details

### Shard 1: coinswarm-data-shard-1 (Majors + ETH Memes)

**Purpose:** High-traffic major cryptocurrency pairs and ETH-based memes

| Attribute | Value |
|-----------|-------|
| Database Name | `coinswarm-data-shard-1` |
| Pair Count | 55 |
| Categories | majors, ethMemes |
| Est. Size | 35GB (all timeframes) |
| Access Pattern | HIGH - Most queries hit this shard |
| Worker | `coinswarm-binance-data` |

**Major Pairs (45):**
```
BTC/USDT, BTC/USDC, BTC/BUSD
ETH/USDT, ETH/USDC, ETH/BUSD
XRP/USDT, XRP/USDC, XRP/BUSD
SOL/USDT, SOL/USDC, SOL/BUSD
DOGE/USDT, DOGE/USDC, DOGE/BUSD
... (15 tokens × 3 bases)
```

**ETH Memes (10):**
```
PEPE/USDT, PEPE/ETH
SHIB/USDT, SHIB/ETH
FLOKI/USDT, FLOKI/ETH
MEME/USDT, MEME/ETH
COQ/USDT, COQ/ETH
```

---

### Shard 2: coinswarm-data-shard-2 (TradFi + L2s)

**Purpose:** Traditional finance assets and Ethereum L2 tokens

| Attribute | Value |
|-----------|-------|
| Database Name | `coinswarm-data-shard-2` |
| Pair Count | 15 |
| Categories | tradfi, l2 |
| Est. Size | 10GB |
| Access Pattern | MEDIUM - TradFi during market hours |

**TradFi Pairs:**
```
MSTR/USD, IBIT/USD, FBTC/USD, GBTC/USD, ETHE/USD
```

**L2 Pairs:**
```
ARB/USDT, ARB/USDC
OP/USDT, OP/USDC
BASE/USDT, BASE/USDC
ZK/USDT, ZK/USDC
STRK/USDT, STRK/USDC
```

**Special Considerations:**
- TradFi data only collected during US market hours
- ETFs (IBIT, FBTC, GBTC, ETHE) launched January 2024
- MSTR has full 5+ year history

---

### Shard 3: coinswarm-data-shard-3 (Solana Ecosystem)

**Purpose:** Solana ecosystem tokens including DEX, memes, and educational tokens

| Attribute | Value |
|-----------|-------|
| Database Name | `coinswarm-data-shard-3` |
| Pair Count | 105 |
| Categories | solana, solanaRugs, solanaFlops, solanaMeh |
| Est. Size | 40GB |
| Access Pattern | HIGH - Growing Solana interest |
| Worker | `coinswarm-solana-data` |

**Production Solana Tokens (63 pairs):**
```
RAY/USDT, RAY/USDC, RAY/SOL
JTO/USDT, JTO/USDC, JTO/SOL
JUP/USDT, JUP/USDC, JUP/SOL
BONK/USDT, BONK/USDC, BONK/SOL
WIF/USDT, WIF/USDC, WIF/SOL
... (21 tokens × 3 bases)
```

**Educational Tokens (42 pairs - MIXED WITH PRODUCTION):**

ML Training Design: Educational tokens (rugs, flops, meh) are intentionally mixed with production tokens for better pattern recognition training.

- **Rugs (10):** HAWK, QUANT, SHAR, CIF, M3M3, SLERF_FAKE, LIBRA, MELANIA, PNUT_RUG, CASH
- **Flops (7):** AURY, GENE, PRT, APT, SBR, GST, LFNTY
- **Meh (4):** MNDE, SLERF, GMT, COPE

---

### Shard 4: coinswarm-data-shard-4 (BNB Ecosystem)

**Purpose:** BNB Smart Chain ecosystem tokens

| Attribute | Value |
|-----------|-------|
| Database Name | `coinswarm-data-shard-4` |
| Pair Count | 16 |
| Categories | bnbEcosystem |
| Est. Size | 10GB |
| Access Pattern | MEDIUM |
| Worker | `coinswarm-binance-data` |

**BNB Ecosystem (16 pairs):**
```
BNB/USDT, BNB/BUSD
CAKE/USDT, CAKE/BUSD     (PancakeSwap)
XVS/USDT, XVS/BUSD       (Venus Protocol)
ALPACA/USDT, ALPACA/BUSD (Alpaca Finance)
BAKE/USDT, BAKE/BUSD     (BakerySwap)
BURGER/USDT, BURGER/BUSD (BurgerSwap)
TWT/USDT, TWT/BUSD       (Trust Wallet)
VIDT/USDT, VIDT/BUSD     (VIDT Datalink)
```

---

### Shard 5: coinswarm-data-shard-5 (Cold Weekly Data)

**Purpose:** Weekly timeframe data for ALL tokens - separated for access latency optimization

| Attribute | Value |
|-----------|-------|
| Database Name | `coinswarm-data-shard-5` |
| Pair Count | 223 (ALL) |
| Timeframes | 1w only |
| Est. Size | ~15 MB |
| Access Pattern | LOW - Long-term trend analysis |
| Worker | ALL workers write here |

**Design Rationale:**
- Weekly data rarely queried during real-time trading
- Separating from hot shards reduces query latency for 1m/15m/1h/1d
- Single cold shard simplifies long-term trend queries across all ecosystems
- Minimal storage footprint (261 rows × 223 pairs × 200B ≈ 12MB)

**Tables:**
- `ohlcv_1w` - Weekly candles for all 223 pairs
- `pair_metadata` - Subset for weekly data tracking

---

## Schema Design

All shards use identical schema for consistency:

### OHLCV Tables (8 per shard)

```sql
-- One table per timeframe for query efficiency
CREATE TABLE IF NOT EXISTS ohlcv_1m (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    quote_volume REAL,
    trades INTEGER,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(pair, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_1m_pair_ts ON ohlcv_1m(pair, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_1m_ts ON ohlcv_1m(timestamp DESC);

-- Repeat for: ohlcv_5m, ohlcv_15m, ohlcv_1h, ohlcv_6h, ohlcv_1d, ohlcv_1w, ohlcv_1M
```

### Metadata Table

```sql
CREATE TABLE IF NOT EXISTS pair_metadata (
    pair TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    shard TEXT NOT NULL,
    first_candle INTEGER,
    last_candle INTEGER,
    total_candles_1m INTEGER DEFAULT 0,
    total_candles_1h INTEGER DEFAULT 0,
    total_candles_1d INTEGER DEFAULT 0,
    source_primary TEXT NOT NULL,
    source_fallback TEXT,
    is_active INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### Backfill Progress Table

```sql
CREATE TABLE IF NOT EXISTS backfill_progress (
    pair TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_pct INTEGER DEFAULT 0,
    candles_loaded INTEGER DEFAULT 0,
    last_timestamp INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (pair, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_backfill_status ON backfill_progress(status);
```

### Collection Log Table

```sql
CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candles_added INTEGER NOT NULL,
    source TEXT NOT NULL,
    duration_ms INTEGER,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_collection_recent ON collection_log(created_at DESC);
```

---

## Query Routing

Workers must route queries to the correct shard based on pair category AND timeframe:

```typescript
import tokenConfig from '../config/tokens.json';

// Hot data (1m, 15m, 1h, 1d) - route by ecosystem
function getHotShardForPair(pair: string): string {
  const [base, quote] = pair.split('/');

  for (const [categoryName, category] of Object.entries(tokenConfig.categories)) {
    if (category.tokens.includes(base)) {
      return category.shard;
    }
  }
  throw new Error(`Unknown pair: ${pair}`);
}

// Cold data (1w) - always goes to shard-5
function getShardForQuery(pair: string, timeframe: string): string {
  if (timeframe === '1w') {
    return 'coinswarm-data-shard-5';  // Cold shard for weekly
  }
  return getHotShardForPair(pair);     // Hot shard by ecosystem
}

// Usage
getShardForQuery('BTC/USDT', '1h');  // 'coinswarm-data-shard-1' (hot)
getShardForQuery('BTC/USDT', '1w');  // 'coinswarm-data-shard-5' (cold)
getShardForQuery('BONK/SOL', '1d');  // 'coinswarm-data-shard-3' (hot)
getShardForQuery('BONK/SOL', '1w');  // 'coinswarm-data-shard-5' (cold)
```

---

## Capacity Planning

### Storage Estimates

| Timeframe | Rows/Pair (5yr) | Bytes/Row | Per Pair | All 142 Pairs |
|-----------|-----------------|-----------|----------|---------------|
| 1m | 2,628,000 | 200 | 526 MB | 74.6 GB |
| 5m | 525,600 | 200 | 105 MB | 14.9 GB |
| 15m | 175,200 | 200 | 35 MB | 5.0 GB |
| 1h | 43,800 | 200 | 8.8 MB | 1.2 GB |
| 6h | 7,300 | 200 | 1.5 MB | 210 MB |
| 1d | 1,825 | 200 | 365 KB | 52 MB |
| 1w | 261 | 200 | 52 KB | 7 MB |
| 1M | 60 | 200 | 12 KB | 2 MB |

**Total estimated:** ~96 GB across all shards

### Per-Shard Estimates (Hot/Cold Split)

| Shard | Type | Pairs | Timeframes | Est. Size | Worker |
|-------|------|-------|------------|-----------|--------|
| 1 (Majors+ETH) | HOT | 55 | 1m,15m,1h,1d (BTC/ETH forever) | ~1.5 GB | coinswarm-binance-data |
| 2 (TradFi+L2) | HOT | 17 | 1h,1d | ~150 MB | coinswarm-binance-data |
| 3 (Solana) | HOT | 105 | 1m,15m,1h,1d (SOL forever) | ~1.5 GB | coinswarm-solana-data |
| 4 (BNB) | HOT | 46 | 1h,1d | ~600 MB | coinswarm-binance-data |
| 5 (Weekly) | COLD | 223 | 1w only | ~15 MB | ALL workers |

**Total: 223 pairs across 5 shards (~4-5 GB)**

### Cost Estimate (Workers Paid $5/mo base)

| Resource | Usage | Cost |
|----------|-------|------|
| Storage | ~4 GB (5 GB free per db) | $0 |
| Rows read | <25B/mo | $0 |
| Rows written | ~10M/mo | $0 |
| **Total** | | **~$5-10/mo** |

---

## Operations

### Creating Shards

```bash
# Create all databases (Hot shards 1-4, Cold shard 5)
npx wrangler d1 create coinswarm-data-shard-1  # Majors + ETH
npx wrangler d1 create coinswarm-data-shard-2  # TradFi + L2
npx wrangler d1 create coinswarm-data-shard-3  # Solana ecosystem
npx wrangler d1 create coinswarm-data-shard-4  # BNB ecosystem
npx wrangler d1 create coinswarm-data-shard-5  # Cold weekly data (all tokens)

# Apply schema to each (hot shards get full schema, cold shard only needs ohlcv_1w)
npx wrangler d1 execute coinswarm-data-shard-1 --file database/migrations/data-schema.sql --remote
npx wrangler d1 execute coinswarm-data-shard-2 --file database/migrations/data-schema.sql --remote
npx wrangler d1 execute coinswarm-data-shard-3 --file database/migrations/data-schema.sql --remote
npx wrangler d1 execute coinswarm-data-shard-4 --file database/migrations/data-schema.sql --remote
npx wrangler d1 execute coinswarm-data-shard-5 --file database/migrations/data-schema.sql --remote
```

### Monitoring Shard Health

```sql
-- Check row counts per table
SELECT
    'ohlcv_1d' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT pair) as pairs
FROM ohlcv_1d;

-- Check backfill progress
SELECT
    status,
    COUNT(*) as count,
    AVG(progress_pct) as avg_progress
FROM backfill_progress
GROUP BY status;

-- Find stale data
SELECT pair, MAX(timestamp) as last_update
FROM ohlcv_1h
GROUP BY pair
HAVING last_update < strftime('%s', 'now') - 7200;
```

### Backup Strategy

```bash
# Export each shard (run periodically)
npx wrangler d1 export coinswarm-data-shard-1 --output ./backups/shard-1-$(date +%Y%m%d).sql
npx wrangler d1 export coinswarm-data-shard-2 --output ./backups/shard-2-$(date +%Y%m%d).sql
npx wrangler d1 export coinswarm-data-shard-3 --output ./backups/shard-3-$(date +%Y%m%d).sql
npx wrangler d1 export coinswarm-data-shard-4 --output ./backups/shard-4-$(date +%Y%m%d).sql
npx wrangler d1 export coinswarm-data-shard-5 --output ./backups/shard-5-weekly-$(date +%Y%m%d).sql
```

---

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2025-12-01 | 1.1.0 | Added shard-5 for cold weekly data (hot/cold split) |
| 2025-11-30 | 1.0.0 | Initial sharding strategy |
# DATA SOURCES - Complete Documentation

**Consolidated from 3 source files covering market data feeds and information architecture.**

---

# TABLE OF CONTENTS

- [PART 1: Data Sources Overview](#part-1-data-sources-overview)
- [PART 2: Data Feeds Architecture](#part-2-data-feeds-architecture)
- [PART 3: Information Sources Strategy](#part-3-information-sources-strategy)

---

# PART 1: Data Sources Overview

*Source: DATA_SOURCES.md*

## Data Shards (D1 Databases)

| Binding | Database | Size | Contents | Status |
|---------|----------|------|----------|--------|
| `DATA_SHARD_1` | coinswarm-data-shard-1 | 2GB | Major cryptos: ADA, ATOM, AVAX, BCH, BNB, BTC, DOGE, DOT, ETH + more | **ACTIVE** |
| `DATA_SHARD_2` | coinswarm-data-shard-2 | 2.5MB | ARB, ETFs (ARKB, BITO, ETHE, FBTC, GBTC, IBIT, MSTR), OP, STRK, ZK, IMX | **ACTIVE** |
| `DATA_SHARD_3` | coinswarm-data-shard-3 | 1MB | Solana tokens (see config/solana-tokens-educational-dataset.json) | **PENDING** |
| `DATA_SHARD_4` | coinswarm-data-shard-4 | 1.5MB | BSC DeFi: ALPACA, BAKE, BNB, CAKE, XVS | **ACTIVE** |
| `DATA_SHARD_5` | coinswarm-data-shard-5 | 200KB | Schema only - reserved for future pairs | EMPTY |
| `DB` | coinswarm-evolution | 700MB | Main DB: chaos_trades, patterns, price_data, news | **ACTIVE** |

## OHLCV Tables (in ALL data shards)

```sql
-- Each shard has these timeframe tables:
ohlcv_1h   -- 1-hour candles (324K+ rows in shard 1)
ohlcv_6h   -- 6-hour candles
ohlcv_1d   -- Daily candles (21K+ rows in shard 1)
```

## Solana Token Dataset (DATA_SHARD_3)

### Part 1: Major SOL Trading Pairs (CEX + DEX)

**Centralized Exchange Pairs (Coinbase/Binance):**
- SOL/USD, SOL/USDT, SOL/USDC, SOL/BUSD
- SOL/BTC, SOL/ETH
- SOL/EUR, SOL/GBP

**Major Solana Ecosystem Tokens:**

| Token | Name | Category |
|-------|------|----------|
| JUP | Jupiter | DEX Aggregator |
| RAY | Raydium | AMM/DEX |
| ORCA | Orca | DEX |
| PYTH | Pyth Network | Oracle |
| JTO | Jito | MEV/Staking |
| W | Wormhole | Bridge |
| HNT | Helium | IoT Infrastructure |
| RNDR | Render | GPU Computing |
| DRIFT | Drift Protocol | Derivatives |
| MNGO | Mango Markets | DeFi |

### Part 2: Educational Pattern Dataset (Rugs/Flops/Meh)

**Rug Pulls (10 tokens):** HAWK, QUANT, MELANIA, LIBRA, M3M3, CIF, SHAR, PNUT_RUG, CASH, SLERF_FAKE

**Legitimate Flops (10 tokens):** AURY, GENE, ATLAS, PRT, PORT, APT, SBR, FIDA, GST-SOL, LFNTY

**Meh Coins (12 tokens):** RAY, BONK, WIF, SAMO, MYRO, ORCA, SLERF, GMT, MNDE, COPE

**Key Patterns for ML Training:**
- Celebrity endorsements = high rug risk
- Insider wallet clustering = coordinated dumps
- GameFi/Move-to-earn = 93% sector failure rate
- Inflationary tokenomics = long-term value decay
- Token-protocol disconnect = good product != good token

---

# PART 2: Data Feeds Architecture

*Source: data-feeds-architecture.md*

## Real-Time Data Feeds

### Exchange WebSocket Feeds

**Coinbase Advanced Trade**
```typescript
// Market data channels
const channels = [
  'ticker',      // Price updates (every trade)
  'level2',      // Order book (top 50 levels)
  'matches',     // Trade executions
  'heartbeats'   // Connection health
];
```

**Binance**
```typescript
// Streams
const streams = [
  '<symbol>@trade',      // Individual trades
  '<symbol>@kline_1m',   // 1-minute candles
  '<symbol>@depth20',    // Order book depth
  '<symbol>@ticker'      // 24h ticker
];
```

### Data Normalization

```typescript
interface NormalizedTick {
  timestamp: number;      // Unix ms
  symbol: string;         // Normalized: BTC-USD
  price: number;
  volume: number;
  bid: number;
  ask: number;
  source: 'coinbase' | 'binance' | 'alpaca';
}
```

## Historical Data Storage

### D1 Schema

```sql
CREATE TABLE ohlcv_1h (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol, timestamp)
);

CREATE INDEX idx_ohlcv_1h_symbol_time ON ohlcv_1h(symbol, timestamp);
```

### Data Retention Policy

| Timeframe | Retention | Granularity |
|-----------|-----------|-------------|
| 1-minute | 30 days | Every tick aggregated |
| 1-hour | 2 years | All candles |
| 1-day | Forever | All candles |

## Data Ingestion Pipeline

```
Exchange APIs → Workers → D1 Shards → KV Cache → Agents
     │              │          │           │          │
     │              │          │           │          └─ Pattern matching
     │              │          │           └─ Hot data (1s TTL)
     │              │          └─ Cold storage (partitioned)
     │              └─ Normalization, validation
     └─ WebSocket/REST
```

---

# PART 3: Information Sources Strategy

*Source: information-sources.md*

## Information Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Agent System                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Market      │  │  Sentiment   │  │  Pattern Learning    │  │
│  │  Analysis    │  │  Analysis    │  │  Agent               │  │
│  │  Agent       │  │  Agent       │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└────────┬────────────────────┬──────────────────┬────────────────┘
         │                    │                  │
         ▼                    ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Data Aggregation Layer                       │
│  - Normalization  - Validation  - Caching  - Rate Limiting      │
└─────────┬───────────────────┬───────────────────┬───────────────┘
          │                   │                   │
    ┌─────▼─────┐      ┌──────▼──────┐     ┌────▼─────┐
    │  Market   │      │  Sentiment  │     │  On-Chain│
    │  Data     │      │  Data       │     │  Data    │
    └───────────┘      └─────────────┘     └──────────┘
```

## 1. Market Data Sources

### Primary Exchange Data (via MCP)

**Coinbase Advanced**
- Real-time: Level 2 order book, trade executions, ticker updates
- Historical: OHLCV candles (1m, 5m, 15m, 1h, 4h, 1d), trade history
- Update Frequency: Real-time via WebSocket

**Alpaca**
- Real-time: Stock quotes, trade executions, bars
- Historical: Daily bars (5+ years), intraday bars (30 days)
- Coverage: All U.S. equities

### Supplementary Market Data

| Source | Data Types | Cost | Use Case |
|--------|-----------|------|----------|
| **Yahoo Finance** | Historical prices, fundamentals | Free | Long-term analysis |
| **CoinGecko** | Cross-exchange prices, market cap | Free tier (10-50 calls/min) | Price validation |
| **CoinMarketCap** | Broad coverage, detailed metrics | Free tier (333 calls/day) | Backup validation |
| **TradingView** | Pre-calculated indicators | Free (unofficial) | Technical shortcuts |

## 2. Sentiment & Social Data Sources

### News Aggregators

| Source | Coverage | Free Tier | Paid |
|--------|----------|-----------|------|
| **NewsAPI** | 80k+ sources | 100 req/day | $449/mo |
| **Google News RSS** | Global | Unlimited | Free |
| **Alpha Vantage News** | Financial | Limited | $50/mo |
| **Finnhub** | Company news, earnings | Limited | Varies |

### Social Media

**Twitter/X API**
- Essential (Free): 1,500 tweets/month
- Basic ($100/mo): 10,000 tweets/month, real-time stream
- Use: Real-time sentiment, breaking news detection

**Reddit API (PRAW)**
- Key Subreddits: r/CryptoCurrency, r/Bitcoin, r/wallstreetbets
- Data: Post sentiment, comment analysis, submission volume
- Cost: Free (60 req/min)

**Other Sources**
- StockTwits: Trader sentiment (bullish/bearish tags)
- Google Trends: Retail interest indicator
- Fear & Greed Index: alternative.me (crypto), CNN (stocks)

## 3. On-Chain Data (Crypto)

### Blockchain Explorers

| Source | Blockchain | Data | Free Tier |
|--------|-----------|------|-----------|
| **Etherscan** | Ethereum | Transactions, contracts, tokens | 5 calls/sec |
| **Blockchain.com** | Bitcoin | TX volume, hash rate, mempool | Unlimited |

### On-Chain Analytics

| Source | Metrics | Cost |
|--------|---------|------|
| **Glassnode** | Exchange flows, whale activity | $29-$799/mo |
| **CryptoQuant** | Exchange reserves, miner flows | Free tier |
| **Dune Analytics** | Custom queries, DEX volume | Free (public) |
| **DeFi Llama** | TVL, protocol revenues | Free |
| **The Graph** | Protocol-specific GraphQL | Free (limited) |

## 4. Fundamental Data

### Equity Fundamentals

| Source | Data | Free Tier |
|--------|------|-----------|
| **Alpha Vantage** | Financials, earnings | 25 req/day |
| **Financial Modeling Prep** | Statements, ratios, DCF | Limited |
| **SEC EDGAR** | 10-K, 10-Q, 8-K filings | Unlimited |

### Crypto Fundamentals

| Source | Data | Cost |
|--------|------|------|
| **Messari** | Token metrics, governance | Free tier |
| **TokenTerminal** | Protocol revenue, P/F ratios | Free tier |

## 5. Economic & Macro Data

### Economic Indicators

| Source | Data | Cost |
|--------|------|------|
| **FRED** | Interest rates, inflation, GDP, money supply | Free |
| **BLS** | Employment, wages, productivity | Free |
| **Federal Reserve** | FOMC minutes, projections | Free |
| **ECB** | EU monetary policy | Free |

### Options & Derivatives

| Source | Data | Use Case |
|--------|------|----------|
| **CBOE** | VIX, put/call ratios | Market fear gauge |
| **Skew** | BTC futures, options flow | Crypto derivatives |

## Data Pipeline Implementation

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any

class DataSource(ABC):
    """Base class for all data sources"""

    def __init__(self, config: dict):
        self.config = config
        self.rate_limiter = RateLimiter(
            config.get('rate_limit', 60),
            config.get('rate_period', 60)
        )

    @abstractmethod
    async def fetch(self, params: dict) -> Dict[str, Any]:
        """Fetch data from source"""
        pass

    @abstractmethod
    async def stream(self, params: dict) -> AsyncIterator[Dict[str, Any]]:
        """Stream real-time data"""
        pass

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate data quality"""
        pass

    async def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize to common format"""
        pass
```

## Data Refresh Cadence

| Frequency | Data Type |
|-----------|-----------|
| Real-time (WebSocket) | Market prices, order book, trades |
| High (1-5 min) | Ticker snapshots, social sentiment |
| Medium (15-60 min) | News articles, Reddit posts, Fear & Greed |
| Low (hourly/daily) | Fundamentals, on-chain, economic |

## Cost Management

### Free Tier Optimization

| Source | Free Limit | Strategy |
|--------|------------|----------|
| NewsAPI | 100 req/day | Cache aggressively, fetch hourly |
| Twitter | 1,500 tweets/mo | Target high-value accounts only |
| Alpha Vantage | 25 req/day | Spread endpoints, cache results |
| CoinGecko | 10-50 calls/min | Strict rate limiting |
| Reddit | 60 req/min | Generous, no concerns |

### Budget Allocation

| Phase | Budget | Services |
|-------|--------|----------|
| Phase 0 | $0/mo | Free tiers only, Coinbase + Alpaca native |
| Phase 1 | $100/mo | + Twitter Basic API |
| Phase 2 | $500/mo | + NewsAPI Commercial |
| Phase 3 | $1000+/mo | + Premium sources as ROI justifies |

---

# END OF CONSOLIDATED DOCUMENT

**Original Source Files:**
1. DATA_SOURCES.md
2. data-feeds-architecture.md
3. information-sources.md
# EMBEDDINGS & VECTORIZE - Complete Documentation

**Consolidated from 12 source files covering the temporal embedding and vector search system.**

---

# TABLE OF CONTENTS

- [PART 1: Overview & Quick Start](#part-1-overview--quick-start)
- [PART 2: System Setup Guide](#part-2-system-setup-guide)
- [PART 3: Model Selection Guide](#part-3-model-selection-guide)
- [PART 4: Embedding Strategy - Daily Aggregation](#part-4-embedding-strategy---daily-aggregation)
- [PART 5: Temporal Embedding Strategies](#part-5-temporal-embedding-strategies)
- [PART 6: Dual Embedding Strategy (Pure + Smoothed)](#part-6-dual-embedding-strategy-pure--smoothed)
- [PART 7: Complete System Summary](#part-7-complete-system-summary)
- [PART 8: Hybrid Vector-D1 Search Architecture](#part-8-hybrid-vector-d1-search-architecture)
- [PART 9: Fast Metadata Matching (No Vector Search)](#part-9-fast-metadata-matching-no-vector-search)
- [PART 10: Vectorize Metadata Templates](#part-10-vectorize-metadata-templates)
- [PART 11: Vectorize Schema Rules & Constraints](#part-11-vectorize-schema-rules--constraints)

---

# PART 1: Overview & Quick Start

*Source: EMBEDDINGS_README.md*

## Time Period Embedding System

**Ultra-fast semantic search for finding similar historical market conditions**

### TL;DR

- **What**: Find historical time periods similar to current market conditions in 30-60ms
- **Why**: Help AI agents identify patterns by matching current setups to past scenarios
- **How**: Embed market snapshots (news + sentiment + technicals) into 384-dim vectors, store in Vectorize, query by similarity
- **Speed**: 30-60ms per query (median ~40ms), returns timestamps + full metadata in one operation
- **Cost**: ~$1-5/month for typical usage

### The Problem This Solves

Your AI trading agents need to answer: **"When in the past did we see conditions like this?"**

Instead of manually coding rules or searching through SQL databases, you:
1. Embed snapshots of market conditions (news, sentiment, technicals) into vectors
2. Store them with timestamps in Vectorize
3. Query: "What historical periods are similar to RIGHT NOW?"
4. Get back: Timestamps + full context in <5ms

### Files Structure

```
pyswarm/
├── Cloudflare_Services/
│   ├── cloudflare_ai_service.py          # Python wrapper for Workers AI
│   └── cloudflare_vectorize_service.py   # Python wrapper for Vectorize
├── examples/
│   └── embedding_pipeline_example.py     # Complete usage examples
├── embedding_worker.ts                   # TypeScript worker (AI + Vectorize)
├── wrangler_embeddings.toml             # Worker configuration
```

### Quick Start

#### 1. Deploy the System

```bash
# Create Vectorize index
wrangler vectorize create pyswarm-time-periods \
  --dimensions=384 \
  --metric=cosine

# Deploy embedding worker
cd pyswarm
wrangler deploy --config wrangler_embeddings.toml

# Note your worker URL
# https://pyswarm-embeddings.YOUR_SUBDOMAIN.workers.dev
```

#### 2. Store Historical Snapshots

```python
import aiohttp
import asyncio
from datetime import datetime

WORKER_URL = "https://pyswarm-embeddings.YOUR_SUBDOMAIN.workers.dev"

async def store_period():
    snapshot = {
        "timestamp": int(datetime(2024, 1, 15).timestamp()),
        "news_summary": "Bitcoin ETF approved, institutional buying surge",
        "sentiment_score": 0.82,
        "technical_setup": "Strong bullish momentum, RSI 72, breaking $45k resistance",
        "social_summary": "Extremely bullish on Twitter/Reddit",
        "market_conditions": "Bull market confirmed, high volume",
        "store_in_vectorize": True,
        "metadata": {
            "btc_price": 45000,
            "volume_24h": 35000000000
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{WORKER_URL}/embed/snapshot", json=snapshot) as resp:
            print(await resp.json())

asyncio.run(store_period())
```

#### 3. Find Similar Periods

```python
async def find_similar():
    # Current market state
    current = {
        "timestamp": int(datetime.now().timestamp()),
        "news_summary": "Market consolidating, ETF volumes strong",
        "sentiment_score": 0.65,
        "technical_setup": "Bullish divergence, support at $42k"
    }

    query = {
        "current_snapshot": current,
        "top_k": 10,
        "min_similarity": 0.6,
        "exclude_recent_days": 30
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{WORKER_URL}/search/similar", json=query) as resp:
            result = await resp.json()

    # ONE QUERY returns: timestamps, similarity scores, full metadata
    for period in result["similar_periods"]:
        print(f"\n{period['timestamp']} - Similarity: {period['similarity_score']:.3f}")
        print(f"News: {period['news_summary']}")
        print(f"Technical: {period['technical_setup']}")
        print(f"BTC Price: ${period['metadata']['btc_price']:,}")

asyncio.run(find_similar())
```

### How It Works

#### The Magic: No Additional Lookups Needed!

Many developers think they need:
```
Vector DB → Get similar IDs → Lookup metadata in KV/D1 → Return data
(5ms)         (5-10ms)                                    = 10-15ms total
```

But Vectorize stores metadata WITH the vector:
```
Vectorize → Get similar vectors + metadata + timestamps
(2-5ms)                                      = 2-5ms total
```

#### Data Flow

```
1. Market State → Text Representation
   "News: ETF approval | Sentiment: bullish (0.82) | Technical: RSI 72, breaking resistance"

2. Text → Embedding (Workers AI)
   [0.123, -0.456, 0.789, ...] (384 numbers)

3. Store in Vectorize
   ID: "2024-01-15T12:00:00Z"
   Values: [0.123, -0.456, ...]
   Metadata: {timestamp, news, sentiment, technical, price, volume, ...}

4. Query with Current State
   Input: Current embedding [0.111, -0.444, ...]
   Output: Most similar vectors (cosine similarity)
   Returns: {id, similarity_score, metadata} × 10

5. Use Results
   - You have timestamps of similar periods
   - You have full context (news, sentiment, technicals)
   - You can look up what happened AFTER those periods
   - Make decisions based on historical patterns
```

### Speed Optimizations

#### Why It's Fast

1. **Small embeddings (384 dims)**: Using `bge-small-en-v1.5`
   - 3x faster than 1024-dim models
   - Still captures semantic meaning well

2. **No extra lookups**: Everything in one query
   - Timestamps stored as vector IDs
   - Metadata stored with vectors
   - No KV, D1, or secondary queries needed

3. **Lower similarity threshold (0.6)**:
   - Gets more results quickly
   - Trades perfect accuracy for speed

4. **Edge-native**:
   - Runs on Cloudflare's global network
   - In-memory vector index
   - Optimized approximate nearest neighbor search

#### Performance Numbers

**Query Latency** (based on Cloudflare benchmarks):
- p50 (median): **30-40ms**
- p95: 50-80ms (estimated)
- p99: 80-120ms (estimated)

**Throughput**:
- **1000+ queries/second** per worker
- Auto-scales globally

### Available Models (Speed vs Accuracy)

| Model | Dimensions | Query Speed | Use Case |
|-------|-----------|-------------|----------|
| **bge-small-en** | 384 | 2-5ms | **Default - Speed priority** |
| bge-base-en | 768 | 5-10ms | Balanced speed/accuracy |
| bge-large-en | 1024 | 10-20ms | Maximum accuracy |
| bge-m3 | 1024 | 10-20ms | Multilingual content |

### Cost Breakdown

#### Cloudflare Workers AI
- Embedding generation: ~$0.44 per 10k snapshots
- Using `bge-small-en-v1.5`

#### Vectorize
- Storage: 10M dimensions free (26k vectors @ 384-dim)
- Queries: 5M dimensions/month free (13k queries @ 384-dim)
- Additional: $0.040 per 1M queried dimensions

#### Total Monthly Cost Estimates

| Usage | Snapshots/Month | Queries/Month | Cost |
|-------|----------------|---------------|------|
| Light | 1,000 | 10,000 | **$0** (free tier) |
| Moderate | 10,000 | 100,000 | **$1-2** |
| Heavy | 30,000 | 1,000,000 | **$5-10** |

### API Reference

#### POST /embed/snapshot

Store a time period snapshot.

**Request**:
```json
{
  "timestamp": 1705320000,
  "news_summary": "Bitcoin ETF approval drives rally",
  "sentiment_score": 0.75,
  "technical_setup": "Bullish momentum, RSI at 65",
  "social_summary": "Positive sentiment",
  "market_conditions": "Strong uptrend",
  "store_in_vectorize": true,
  "metadata": {
    "btc_price": 45000,
    "volume_24h": 35000000000
  }
}
```

**Response**:
```json
{
  "success": true,
  "id": "2024-01-15T12:00:00Z",
  "embedding": [...],
  "dimensions": 384,
  "stored_in_vectorize": true
}
```

#### POST /search/similar

Find similar historical periods.

**Request**:
```json
{
  "current_snapshot": {
    "timestamp": 1731359999,
    "news_summary": "Market consolidating",
    "sentiment_score": 0.65,
    "technical_setup": "Bullish divergence"
  },
  "top_k": 10,
  "min_similarity": 0.6,
  "exclude_recent_days": 30
}
```

**Response**:
```json
{
  "success": true,
  "similar_periods": [
    {
      "id": "2024-01-15T12:00:00Z",
      "similarity_score": 0.87,
      "timestamp": 1705320000,
      "news_summary": "Bitcoin ETF approval...",
      "sentiment_score": 0.75,
      "technical_setup": "Bullish momentum...",
      "metadata": {
        "btc_price": 45000,
        "volume_24h": 35000000000
      }
    }
  ],
  "count": 10
}
```

### Integration with Trading Agents

#### Pattern: Historical Context Search

```python
class TradingAgent:
    """
    Agent that uses historical pattern matching for decisions
    """

    async def should_enter_trade(self, current_conditions):
        # Step 1: Find similar historical periods (< 5ms)
        similar = await self.find_similar_periods(current_conditions)

        # Step 2: Analyze outcomes after those periods
        outcomes = []
        for period in similar:
            # What happened 1-7 days after this period?
            future_price = self.get_price_after(period['timestamp'], days=7)
            outcome = {
                'period': period,
                'return_7d': future_price / period['metadata']['btc_price'] - 1
            }
            outcomes.append(outcome)

        # Step 3: Make decision based on historical patterns
        avg_return = sum(o['return_7d'] for o in outcomes) / len(outcomes)
        win_rate = sum(1 for o in outcomes if o['return_7d'] > 0) / len(outcomes)

        return {
            'should_trade': avg_return > 0.05 and win_rate > 0.6,
            'confidence': win_rate,
            'expected_return': avg_return,
            'historical_precedents': len(outcomes)
        }
```

#### Pattern: Real-Time Market Regime Detection

```python
async def detect_market_regime(current_state):
    """
    Identify current market regime by finding similar past periods
    """
    similar_periods = await find_similar_periods(current_state, top_k=20)

    # Cluster similar periods by their outcomes
    regimes = {
        'bull_rally': [],
        'bear_dump': [],
        'sideways': [],
        'volatile': []
    }

    for period in similar_periods:
        # Classify based on what happened after
        outcome = analyze_period_outcome(period)
        regimes[outcome['regime']].append(period)

    # Current regime = most common historical outcome
    likely_regime = max(regimes, key=lambda k: len(regimes[k]))

    return {
        'regime': likely_regime,
        'confidence': len(regimes[likely_regime]) / len(similar_periods),
        'similar_count': len(similar_periods)
    }
```

---

# PART 2: System Setup Guide

*Source: EMBEDDING_SYSTEM_SETUP.md*

## Overview

This system provides **ultra-fast temporal similarity search** for finding historical market periods similar to current conditions. Optimized for **speed over perfect accuracy**.

### Performance Targets
- **Query Speed**: 30-60ms per similarity search (median ~40ms)
- **Throughput**: 20-30 queries/second per worker (Cloudflare benchmark: 300 concurrent)
- **Cost**: ~$1-5/month for typical usage
- **Comparison**: 5-10x faster than D1 queries + similarity calculations

## Architecture

```
┌─────────────────┐
│  Python Code    │  Your trading agents/analysis
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Embedding Worker│  TypeScript worker (AI + Vectorize)
│  (TypeScript)   │  - Generates embeddings via Workers AI
└────────┬────────┘  - Stores/queries via Vectorize
         │
         ▼
┌─────────────────┐
│   Vectorize DB  │  Vector database
│   384-dim       │  - Stores embeddings + metadata
└─────────────────┘  - Returns timestamps instantly
```

## Setup Steps

### 1. Create Vectorize Index

```bash
wrangler vectorize create pyswarm-time-periods \
  --dimensions=384 \
  --metric=cosine \
  --description="Time period embeddings (speed-optimized)"
```

### 2. Deploy Embedding Worker

```bash
cd pyswarm
wrangler deploy --config wrangler_embeddings.toml
```

### 3. Test the System

```bash
# Health check
curl https://pyswarm-embeddings.YOUR_SUBDOMAIN.workers.dev/health

# List available models
curl https://pyswarm-embeddings.YOUR_SUBDOMAIN.workers.dev/models
```

## Speed Optimization Details

### Why It's Fast

1. **Small Embeddings (384 dims)**:
   - Using `bge-small-en-v1.5` instead of `bge-large-en-v1.5`
   - 3x faster than 1024-dim embeddings
   - Still captures semantic meaning well

2. **No Additional Lookups**:
   - Vectorize returns timestamps + metadata in one query
   - No KV, D1, or secondary lookups needed

3. **Global Edge Network**:
   - Vectorize runs on Cloudflare's global network
   - Low latency worldwide

4. **In-Memory Index**:
   - Vector index is kept in memory
   - Approximate nearest neighbor search is highly optimized

### Performance Benchmarks

**Query Latency** (single similarity search, based on Cloudflare official benchmarks):
- p50 (median): 30-40ms (warm cache)
- p95: 50-80ms (estimated)
- p99: 80-120ms (estimated)
- Cold cache: 50-150ms

**Throughput**:
- 1000+ queries/second per worker
- Auto-scales globally

## Configuration for Speed vs Accuracy

### Speed Priority (Default)

```python
# FAST: 2-5ms queries, broader matches
{
    "model": "bge-small-en",       # 384 dimensions
    "top_k": 10,                    # Top 10 results
    "min_similarity": 0.6,          # Lower threshold = more results
    "exclude_recent_days": 30
}
```

### Balanced Speed & Accuracy

```python
# BALANCED: 5-10ms queries, more precise matches
{
    "model": "bge-base-en",        # 768 dimensions
    "top_k": 5,
    "min_similarity": 0.7,
    "exclude_recent_days": 30
}
```

### Maximum Accuracy

```python
# ACCURATE: 10-20ms queries, most precise matches
{
    "model": "bge-large-en",       # 1024 dimensions
    "top_k": 3,
    "min_similarity": 0.8,
    "exclude_recent_days": 30
}
```

## Cost Analysis

### Cloudflare Workers AI (Embedding Generation)
- **Free Tier**: 10,000 neurons/day
- **Paid**: $0.011 per 1,000 neurons
- `bge-small-en-v1.5` ≈ 400 neurons per request
- **Cost**: ~10,000 embeddings/month = ~$0.44/month

### Vectorize (Storage + Queries)
- **Free Tier**:
  - 10M stored dimensions (26,000 vectors @ 384-dim)
  - 5M queried dimensions/month (13,000 queries @ 384-dim)
- **Paid**: $0.040 per 1M queried dimensions
- **Cost**: 100,000 queries/month = ~$0.30/month

### Workers Requests
- **Free Tier**: 100,000 requests/day
- **Paid**: $0.50 per 1M requests
- **Cost**: Usually within free tier

### Total Estimated Cost
- Light usage (10k queries/month): **$0** (free tier)
- Moderate usage (100k queries/month): **$1-2/month**
- Heavy usage (1M queries/month): **$5-10/month**

## Monitoring & Debugging

### Check Index Status

```bash
wrangler vectorize get pyswarm-time-periods
```

### View Logs

```bash
wrangler tail pyswarm-embeddings
```

### Test Query Performance

```python
import time
import asyncio
import aiohttp

async def benchmark():
    WORKER_URL = "https://pyswarm-embeddings.YOUR_SUBDOMAIN.workers.dev"

    query = {
        "current_snapshot": {
            "timestamp": int(time.time()),
            "news_summary": "Test query",
            "sentiment_score": 0.5,
            "technical_setup": "Test"
        },
        "top_k": 10
    }

    # Run 10 queries and measure time
    times = []
    async with aiohttp.ClientSession() as session:
        for _ in range(10):
            start = time.perf_counter()
            async with session.post(f"{WORKER_URL}/search/similar", json=query) as resp:
                await resp.json()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

    print(f"Average: {sum(times)/len(times):.2f}ms")
    print(f"Min: {min(times):.2f}ms")
    print(f"Max: {max(times):.2f}ms")

asyncio.run(benchmark())
```

## Troubleshooting

### Slow Queries (>20ms)

1. Check if using correct model (should be `bge-small-en`)
2. Reduce `top_k` value
3. Lower `min_similarity` threshold
4. Check Vectorize index dimensions (should be 384)

### Empty Results

1. Ensure historical data is loaded
2. Lower `min_similarity` (try 0.5 or 0.4)
3. Increase `top_k`
4. Check timestamp filtering isn't too restrictive

### Deployment Issues

```bash
# Check if Vectorize index exists
wrangler vectorize list

# Recreate index if needed
wrangler vectorize delete pyswarm-time-periods
wrangler vectorize create pyswarm-time-periods --dimensions=384 --metric=cosine

# Redeploy worker
wrangler deploy --config pyswarm/wrangler_embeddings.toml
```

---

# PART 3: Model Selection Guide

*Source: MODEL_SELECTION_GUIDE.md*

## Available Models

| Model | Dimensions | Query Speed | Accuracy | Cost Factor | Use Case |
|-------|-----------|-------------|----------|-------------|----------|
| **bge-small-en-v1.5** | 384 | ~30-40ms | Good | 1x | High-frequency queries |
| **bge-base-en-v1.5** | 768 | ~50-70ms | Better | 2x | Balanced performance |
| **bge-large-en-v1.5** | 1024 | ~60-90ms | Best | 2.7x | **Maximum accuracy (RECOMMENDED)** |

## Recommendation: bge-large-en-v1.5

**For time period similarity search with low query frequency, bge-large is optimal.**

### Why bge-large?

**Best semantic understanding**
- 1024 dimensions = maximum nuance capture
- Best at understanding complex market narratives
- Highest similarity scores for matching periods
- "Bitcoin ETF approval" vs "Institutional adoption via spot ETF" → 0.92 similarity (vs 0.87 for base)

**Low query frequency = speed doesn't matter**
- 60-90ms query time
- Running only a few times per day? Extra 20-40ms is completely negligible
- Accuracy matters far more than milliseconds for daily trading decisions

**Minimal cost increase for this use case**
- 300 queries/month: $0.86 vs $0.64 for base = +$0.22/month
- That's $2.64/year for maximum accuracy
- Better pattern matching = better trading decisions = ROI justified

**Future-proof for agent memory**
- For high-frequency agent memory queries, can switch to bge-base-en or bge-small-en
- This keeps news/sentiment search at maximum accuracy
- Agent memory is a different optimization problem (milliseconds matter there)

## Cost Analysis

### Query Volume: 300 queries/month (10/day × 30 days)

| Model | Query Cost | Storage Cost (2,190 vectors) | Total/Month |
|-------|-----------|------------------------------|-------------|
| Small (384) | $0.10 | $0.22 | **$0.32** |
| Base (768) | $0.20 | $0.44 | **$0.64** |
| Large (1024) | $0.27 | $0.59 | **$0.86** |

**Cost difference: $0.32/month for better accuracy** → Totally worth it!

### Query Volume: 3,000 queries/month (100/day × 30 days)

| Model | Total/Month |
|-------|-------------|
| Small (384) | $3.10 |
| Base (768) | $6.20 |
| Large (1024) | $8.30 |

**Cost difference: $3.10/month for better accuracy** → Still very reasonable!

## Performance Comparison

### Query Latency (from Cloudflare benchmarks)

**bge-small-en-v1.5 (384 dims)**:
- p50: 30-40ms
- p95: 50-70ms
- p99: 80-100ms

**bge-base-en-v1.5 (768 dims)**:
- p50: 50-70ms
- p95: 80-100ms
- p99: 120-150ms

**bge-large-en-v1.5 (1024 dims)**: RECOMMENDED
- p50: 60-90ms (estimated)
- p95: 100-130ms (estimated)
- p99: 150-200ms (estimated)

## Semantic Understanding Examples

### Example 1: "Bitcoin ETF approval drives rally"

**Similar headlines found (similarity scores)**:

| Headline | Small (384) | Base (768) | Large (1024) |
|----------|-------------|------------|--------------|
| "SEC approves spot Bitcoin ETF applications" | 0.78 | 0.87 | 0.92 |
| "Institutional adoption via spot ETF products" | 0.71 | 0.82 | 0.88 |
| "Major banks offer crypto custody services" | 0.65 | 0.76 | 0.83 |
| "Regulatory clarity improves market sentiment" | 0.62 | 0.73 | 0.79 |

**Impact**: Base and Large models find more relevant matches with higher confidence.

### Example 2: "Sentiment improving but RSI overbought"

**Similar setups found**:

| Description | Small (384) | Base (768) | Large (1024) |
|-------------|-------------|------------|--------------|
| "Positive sentiment with technical caution" | 0.69 | 0.79 | 0.85 |
| "Bullish news but extended momentum" | 0.64 | 0.74 | 0.81 |
| "Fear of missing out despite high valuations" | 0.58 | 0.69 | 0.76 |

**Impact**: Base model better understands the contradiction/nuance.

## When to Use Each Model

### Use bge-small-en-v1.5 (384 dims) if:
- You need sub-50ms query times consistently
- Running thousands of queries per day
- Cost is extremely tight
- Basic semantic matching is sufficient
- **Best for agent memory / high-frequency queries**

### Use bge-base-en-v1.5 (768 dims) if:
- Querying frequently (100+ times per day)
- Speed optimization is important
- Good semantic understanding is sufficient
- Want balanced cost/performance

### Use bge-large-en-v1.5 (1024 dims) if: **RECOMMENDED**
- Maximum accuracy is critical
- Querying infrequently (few times per day)
- 60-90ms latency is acceptable
- Complex narratives need deep understanding
- Cost difference ($0.22/month) is negligible
- **This is your use case for news/sentiment search!**

## Summary Table

| Factor | Small | Base | Large |
|--------|-------|------|-------|
| **Dimensions** | 384 | 768 | 1024 |
| **Query Speed** | 30-40ms | 50-70ms | 60-90ms |
| **Semantic Accuracy** | Good | Better | Best |
| **Cost (300 queries/month)** | $0.32 | $0.64 | $0.86 |
| **News/Sentiment Search (low freq)** | No | Good | **Perfect** |
| **Agent Memory (high freq)** | **Perfect** | Good | No |

---

# PART 4: Embedding Strategy - Daily Aggregation

*Source: EMBEDDING_STRATEGY_GUIDE.md*

**Model Choice**: Using **bge-large-en-v1.5 (1024 dims)** for maximum accuracy on low-frequency queries.

## Recommended Approach: Smart Daily Aggregation

### Core Concept

**One embedding per day** that intelligently captures:
- Key news headlines (top 3-5 most important)
- Overall market narrative/theme
- Sentiment direction and momentum
- Technical setup summary
- Social media vibe
- Market context

### Embedding Text Construction

```python
def build_embedding_text(date: datetime) -> str:
    """
    Construct rich embedding text that captures the day's "market vibe"
    """

    # 1. Get data
    headlines = get_top_headlines(date, limit=5, min_importance=0.6)
    sentiment = get_sentiment_snapshot(date)
    technicals = get_technical_snapshot(date)
    social = get_social_snapshot(date)

    # 2. Identify primary theme/narrative
    theme = identify_primary_theme(headlines)
    # e.g., "institutional_adoption", "regulation", "macro_uncertainty", etc.

    # 3. Construct embedding text
    text = f"""
{theme.upper()}: {headlines[0]['title']}

Key Events:
- {headlines[0]['title']}
- {headlines[1]['title']}
- {headlines[2]['title']}

Market Narrative: {summarize_narrative(headlines)}

Sentiment: {sentiment['regime']} ({sentiment['score']:.2f})
- Direction: {sentiment['direction']} (velocity: {sentiment['velocity']:.3f})
- Fear/Greed: {sentiment['fear_greed']} ({classify_fear_greed(sentiment['fear_greed'])})
- News tone: {sentiment['news_sentiment_1hr']:.2f}

Technical Setup:
- Trend: {technicals['trend']} ({technicals['trend_strength']:.1f})
- RSI: {technicals['rsi']} ({classify_rsi(technicals['rsi'])})
- MACD: {technicals['macd_signal']} crossover
- Volatility: {technicals['volatility']} regime

Social: {social['mentions']:,} mentions, {classify_social_sentiment(social['sentiment'])} sentiment

Market Phase: {get_market_phase(date)}
    """.strip()

    return text
```

### Example Output

```python
# 2024-01-15 snapshot
embedding_text = """
INSTITUTIONAL_ADOPTION: SEC approves Bitcoin spot ETF applications from BlackRock and Fidelity

Key Events:
- SEC approves Bitcoin spot ETF applications from BlackRock and Fidelity
- Major banks announce cryptocurrency custody services
- Institutional buying surge drives price above $45k

Market Narrative: Regulatory clarity drives institutional adoption. First spot Bitcoin ETF approval
marks turning point for mainstream acceptance. Strong institutional demand with minimal selling pressure.

Sentiment: bullish (0.82)
- Direction: improving (velocity: 0.08)
- Fear/Greed: 75 (greed)
- News tone: 0.78

Technical Setup:
- Trend: uptrend (0.75)
- RSI: 72 (overbought)
- MACD: bullish crossover
- Volatility: medium regime

Social: 45,200 mentions, extremely positive sentiment

Market Phase: bull_rally
"""
```

## Alternative Structures

### A. Multi-Coin Support

If tracking multiple coins, use coin-prefixed IDs:

```python
{
    "id": "2024-01-15-BTC",
    "embedding": embed("BTC: ETF approval drives rally..."),
    "metadata": {
        "coin": "BTC",
        "timestamp": ...,
        # ... BTC-specific indicators
    }
}

{
    "id": "2024-01-15-SOL",
    "embedding": embed("SOL: Ecosystem growth continues..."),
    "metadata": {
        "coin": "SOL",
        "timestamp": ...,
        # ... SOL-specific indicators
    }
}
```

Then query with metadata filter:
```python
results = await vectorize.query(
    vector=current_embedding,
    filter={"coin": {"$eq": "BTC"}},
    topK=10
)
```

### B. Intraday Windows (Optional)

For intraday trading, create snapshots at key times:

```python
# Market open (9:30 AM ET)
{
    "id": "2024-01-15T09:30:00Z",
    "embedding": embed("Market open: Overnight ETF news drives strong pre-market..."),
    "metadata": {
        "period": "market_open",
        "timestamp": ...,
    }
}

# Midday (12:00 PM ET)
{
    "id": "2024-01-15T12:00:00Z",
    "embedding": embed("Midday: Rally sustained, institutional buying continues..."),
    "metadata": {
        "period": "midday",
        "timestamp": ...,
    }
}
```

### C. Event-Based Snapshots

For major events, create dedicated snapshots:

```python
{
    "id": "2024-01-15-event-etf-approval",
    "embedding": embed("MAJOR EVENT: SEC approves first Bitcoin spot ETF..."),
    "metadata": {
        "event_type": "regulatory_approval",
        "importance": 0.98,
        "timestamp": ...,
    }
}
```

## Implementation Strategy

### Step 1: Smart Headline Aggregation

```python
def get_top_headlines(date: datetime, limit: int = 5, min_importance: float = 0.6) -> list:
    """
    Get most important headlines for the day
    """
    headlines = fetch_headlines(date)

    # Score by importance
    scored = []
    for h in headlines:
        score = calculate_importance(h)
        if score >= min_importance:
            scored.append((score, h))

    # Sort by importance, take top N
    scored.sort(reverse=True)
    return [h for score, h in scored[:limit]]


def calculate_importance(headline: dict) -> float:
    """
    Score headline importance (0-1)
    """
    score = 0.0

    # Source quality
    if headline['source'] in ['bloomberg', 'reuters', 'wsj']:
        score += 0.3
    elif headline['source'] in ['coindesk', 'cointelegraph']:
        score += 0.2

    # Engagement
    if headline['views'] > 10000:
        score += 0.2

    # Keywords
    important_keywords = ['sec', 'etf', 'regulation', 'hack', 'bankruptcy']
    if any(kw in headline['title'].lower() for kw in important_keywords):
        score += 0.3

    # Sentiment extreme
    if abs(headline['sentiment']) > 0.7:
        score += 0.2

    return min(score, 1.0)
```

### Step 2: Theme Identification

```python
def identify_primary_theme(headlines: list) -> str:
    """
    Identify primary market theme from headlines
    """
    themes = {
        'institutional_adoption': ['etf', 'institutional', 'bank', 'custody', 'fidelity', 'blackrock'],
        'regulation': ['sec', 'cftc', 'regulation', 'law', 'compliance', 'legal'],
        'technical_rally': ['breakout', 'resistance', 'support', 'rally', 'surge'],
        'hack_security': ['hack', 'exploit', 'security', 'breach', 'stolen'],
        'macro_uncertainty': ['fed', 'inflation', 'recession', 'unemployment', 'rates'],
        'ecosystem_growth': ['dex', 'defi', 'tvl', 'volume', 'adoption'],
    }

    theme_scores = {theme: 0 for theme in themes}

    for headline in headlines:
        text = headline['title'].lower()
        for theme, keywords in themes.items():
            for keyword in keywords:
                if keyword in text:
                    theme_scores[theme] += 1

    # Return theme with highest score
    return max(theme_scores, key=theme_scores.get)
```

## Query Examples

### Find Similar Market Narratives

```python
# Current market
current_text = build_embedding_text(datetime.now())
current_embedding = await generate_embedding(current_text)

# Find similar
results = await vectorize.query(
    vector=current_embedding,
    filter={
        "primary_theme": {"$eq": "institutional_adoption"},  # Same theme
        "profitable_7d": {"$eq": 1}  # Only winners
    },
    topK=10
)

# Results: Periods with similar "institutional adoption" narratives that won
```

### Find Similar Technical Setups (Regardless of News)

```python
# Find by metadata only (ignore news narrative)
results = await vectorize.query(
    vector=[0] * 768,  # Dummy vector
    filter={
        "rsi": {"$gte": 65, "$lte": 75},
        "sentiment_velocity": {"$gte": 0.05},
        "trend": {"$eq": "uptrend"}
    },
    topK=100
)

# Results: Periods matching technical conditions (any news theme)
```

### Hybrid: Similar Theme + Technical Range

```python
# Combine semantic + metadata
results = await vectorize.query(
    vector=current_embedding,  # Similar narratives
    filter={
        "rsi": {"$gte": 60, "$lte": 80},  # Technical range
        "profitable_7d": {"$eq": 1}  # Only winners
    },
    topK=20
)

# Results: Similar narratives within technical range that won
```

## Storage Requirements

### Daily Snapshots
- 365 days/year × 6 years = **2,190 snapshots**
- 768 dimensions each
- **Total**: 1.68M dimensions stored
- **Cost**: ~$0.07/month storage

### Per-Coin (if needed)
- 3 coins (BTC, ETH, SOL) × 365 days × 6 years = **6,570 snapshots**
- **Total**: 5.05M dimensions stored
- **Cost**: ~$0.20/month storage

All well within Vectorize limits (10M stored dimensions free tier)!

## Recommendation Summary

**Use: Smart Daily Aggregation**

1. One embedding per day
2. Combine top 3-5 headlines
3. Add narrative summary
4. Include sentiment + technical context
5. Store theme/category in metadata
6. Attach all indicators + outcomes

**Benefits**:
- Captures overall "market vibe"
- Manageable dataset size (2,190 snapshots)
- Fast queries (<70ms)
- Perfect for daily trading decisions
- Can still filter by theme/coin/technical via metadata

---

# PART 5: Temporal Embedding Strategies

*Source: TEMPORAL_EMBEDDING_STRATEGIES.md*

## The Core Question

How do we construct embeddings that capture:
1. **Current state**: Today's headlines, sentiment, technicals
2. **Recent context**: Important events from past few days
3. **Temporal continuity**: Smooth transitions vs. sharp regime changes
4. **Long-term memory**: Major events that influence markets for weeks

## Strategy 1: Simple Daily Snapshot

### How It Works
```python
def simple_daily_embedding(date):
    headlines = get_top_headlines(date, limit=5)
    sentiment = get_sentiment(date)
    technical = get_technicals(date)

    text = f"""
    Headlines: {headlines[0]}, {headlines[1]}, {headlines[2]}
    Sentiment: {sentiment.score} ({sentiment.direction})
    Technical: RSI {technical.rsi}, MACD {technical.macd}
    """

    return embed(text)
```

### Characteristics
- Clean separation between days
- Easy to understand what each embedding represents
- Can spot exact day when regime changed
- No memory of previous days
- "ETF approval day" and "day after ETF approval" seem unrelated
- Discontinuous jumps between consecutive days

**Best For**: Identifying specific events, backtesting discrete signals

---

## Strategy 2: Sliding Window with Text Decay

### How It Works
```python
def sliding_window_embedding(date, lookback_days=7):
    # Current day (full weight)
    today = {
        'headlines': get_headlines(date),
        'sentiment': get_sentiment(date),
        'technical': get_technicals(date),
        'weight': 1.0
    }

    # Historical headlines with importance threshold and decay
    historical_headlines = []
    for days_ago in range(1, lookback_days + 1):
        past_date = date - timedelta(days=days_ago)

        # Only include important headlines (importance > 0.7)
        important = get_headlines(past_date, min_importance=0.7)

        # Apply exponential decay
        decay_factor = 0.5 ** days_ago
        # Day -1: 0.5x, Day -2: 0.25x, Day -3: 0.125x, etc.

        for headline in important:
            historical_headlines.append({
                'title': headline['title'],
                'weight': headline['importance'] * decay_factor,
                'days_ago': days_ago
            })

    # Build composite text with weighted repetition
    text_components = []

    # Today's content
    text_components.append(f"TODAY: {format_daily_summary(today)}")

    # Historical context (weighted by importance * decay)
    if historical_headlines:
        historical_headlines.sort(key=lambda x: x['weight'], reverse=True)
        for h in historical_headlines[:3]:
            text_components.append(
                f"CONTEXT ({h['days_ago']}d ago, weight={h['weight']:.2f}): {h['title']}"
            )

    combined_text = " | ".join(text_components)
    return embed(combined_text)
```

### Characteristics
- Important events persist for multiple days
- Natural decay - old news becomes less relevant
- Still text-based, easy to debug
- "ETF approval" is in embeddings for the next week

**Best For**: Capturing event persistence, understanding market "regimes"

---

## Strategy 3: Categorical Persistence

### How It Works

Different event types have different half-lives:

```python
EVENT_PERSISTENCE = {
    'regulatory_approval': 14,     # ETF approvals, legal clarity
    'regulatory_crackdown': 7,     # SEC lawsuits, enforcement
    'major_hack': 5,               # Exchange hacks, exploits
    'institutional_adoption': 10,  # Major companies buying
    'technical_breakout': 2,       # Resistance breaks, ATH
    'macro_news': 21,              # Fed policy, recession
    'protocol_upgrade': 7,         # Ethereum merge, halving
    'social_trend': 1,             # Twitter hype, Reddit trends
}
```

### Characteristics
- Event-specific decay rates (very realistic)
- Macro news persists longer than social trends
- Captures that some events have longer impact
- Requires event categorization

**Best For**: Realistic market modeling, different trading timeframes

---

## Strategy 4: Vector Arithmetic Blending

### How It Works

Instead of including past events in text, directly blend embeddings:

```python
def vector_blending_embedding(date, history_weight=0.3):
    # Generate today's raw embedding
    today_text = build_daily_text(date)
    today_raw = embed(today_text)

    # Get yesterday's FINAL embedding (already blended)
    yesterday_final = get_stored_embedding(date - 1_day)

    if yesterday_final is None:
        return today_raw  # First day

    # Blend: 70% today, 30% yesterday
    today_final = (today_raw * (1 - history_weight) +
                   yesterday_final * history_weight)

    # Normalize to unit length (important for cosine similarity)
    today_final = normalize(today_final)

    return today_final
```

### What This Creates: Cascading Memory

Since yesterday's embedding already contains the day before, this creates a chain:

```
Day 0: 100% of Day 0
Day 1: 70% of Day 1 + 30% of Day 0
Day 2: 70% of Day 2 + 30% of (70% Day 1 + 30% Day 0)
     = 70% Day 2 + 21% Day 1 + 9% Day 0
Day 3: 70% Day 3 + 21% Day 2 + 9% Day 1 + 2.7% Day 0
```

**Decay Formula**: Weight of day N days ago = `(history_weight)^N * (1 - history_weight)`

With `history_weight = 0.3`:
- Day -1: 21%
- Day -2: 9%
- Day -3: 2.7%
- Day -7: 0.02%

### Characteristics
- Extremely smooth temporal transitions
- Automatic exponential decay (no manual tuning)
- Every embedding contains market "history"
- Over-smoothing can hide regime changes

**Best For**: Modeling persistent market regimes, smooth transitions

---

## Strategy 5: Hybrid Approach (RECOMMENDED)

### How It Works

Combine text-based persistence with light vector blending:

```python
def hybrid_temporal_embedding(date):
    # STEP 1: Build composite text with explicit persistence
    today_headlines = get_top_headlines(date, limit=5)
    today_sentiment = get_sentiment(date)
    today_technical = get_technicals(date)

    # Important historical headlines (7-day window)
    historical_headlines = []
    for days_ago in range(1, 8):
        past_date = date - timedelta(days=days_ago)
        important = get_headlines(past_date, min_importance=0.75)

        for h in important:
            category = categorize_event(h)
            max_persist = EVENT_PERSISTENCE.get(category, 7)

            if days_ago <= max_persist:
                decay = 1.0 - (days_ago / max_persist)
                historical_headlines.append({
                    'title': h['title'],
                    'weight': h['importance'] * decay,
                    'category': category,
                    'days_ago': days_ago
                })

    # Build rich text representation
    text_parts = []
    text_parts.append(f"PRIMARY ({date}): Headlines, Sentiment, Technical...")

    if historical_headlines:
        historical_headlines.sort(key=lambda x: x['weight'], reverse=True)
        for h in historical_headlines[:3]:
            text_parts.append(
                f"CONTEXT (-{h['days_ago']}d, {h['category']}, w={h['weight']:.2f}): {h['title']}"
            )

    combined_text = "\n".join(text_parts)

    # STEP 2: Generate embedding from composite text
    today_raw = embed(combined_text)

    # STEP 3: Light vector blending for continuity
    yesterday_final = get_stored_embedding(date - 1_day)

    if yesterday_final:
        # Very light blending (10-15%) just for smoothness
        blend_weight = 0.15
        today_final = (today_raw * (1 - blend_weight) +
                       yesterday_final * blend_weight)
        today_final = normalize(today_final)
    else:
        today_final = today_raw

    return today_final
```

### What This Achieves

1. **Explicit Text Persistence** (Step 1)
   - Important events from past week included in text
   - Category-specific decay (regulatory news persists 14d, social trends 1d)
   - Human-readable, debuggable

2. **Semantic Richness** (Step 2)
   - Model naturally understands "post-ETF rally" is similar to "ETF approval"
   - Related events cluster together

3. **Temporal Smoothing** (Step 3)
   - 15% blend with yesterday prevents discontinuous jumps
   - But not so much that regime changes are hidden

### Characteristics
- Best of both worlds: explicit + implicit persistence
- Human-readable (text-based) + smooth (vector blend)
- Can still detect regime changes (85% new content)
- Debuggable: can inspect what's in each embedding

**Best For**: Production trading systems (recommended)

## Comparison Table

| Strategy | Explainability | Regime Persistence | Detects Sharp Changes | Complexity | Recommended For |
|----------|---------------|-------------------|----------------------|------------|-----------------|
| **Simple Daily** | ★★★★★ | ★ | ★★★★★ | ★ | Backtesting discrete signals |
| **Sliding Window** | ★★★★ | ★★★ | ★★★★ | ★★ | Understanding event impact |
| **Categorical Persistence** | ★★★★ | ★★★★ | ★★★ | ★★★ | Realistic market modeling |
| **Vector Blending** | ★ | ★★★★★ | ★ | ★★ | Regime-persistent markets |
| **Hybrid** ★ | ★★★ | ★★★★ | ★★★ | ★★★★ | **Production systems** |

---

# PART 6: Dual Embedding Strategy (Pure + Smoothed)

*Source: DUAL_EMBEDDING_STRATEGY.md*

## Overview

Combines two pieces of expert advice into a production-ready system:

**Advice 1**: "You cannot embed an embedding. Maintain numerical continuity, not textual injection."
- Blend vectors in vector space: `v_t = α*v_{t-1} + (1-α)*embed(text_t)`
- Creates cascading memory with exponential decay

**Advice 2**: "Keep both the pure embedding and a smoothed one."
- Pure: Sharp transitions, event detection
- Smoothed: Emotional persistence, regime matching
- Use for different retrieval purposes

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Daily Market Data                        │
│  (Headlines, Sentiment, Technical Indicators)               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│             Generate Dual Embeddings                        │
│                                                             │
│  Pure:     embed(today's headlines only)                   │
│            → Sharp transitions, event detection             │
│                                                             │
│  Smoothed: α * yesterday_smoothed + (1-α) * pure           │
│            → Emotional persistence, regime matching         │
│            → α ≈ 0.2-0.4 (decay factor)                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   Storage Layer                             │
│                                                             │
│  Vectorize:  Store smoothed embedding in 'values'          │
│              Store pure embedding in metadata               │
│              (1024 dims, bge-large-en-v1.5)                │
│                                                             │
│  D1:         Store technical indicators, outcomes           │
│              (for numeric similarity filtering)             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                  Retrieval Layer                            │
│                                                             │
│  1. Query Vectorize with today's embedding                 │
│  2. Get top-K by cosine similarity                         │
│  3. Re-score with numeric filters (RSI, volume, etc.)      │
│  4. Return best matches with metadata                      │
└─────────────────────────────────────────────────────────────┘
```

## Why Dual Embeddings?

### Pure Embedding
```python
pure = embed("Bitcoin rallies 12% on ETF approval")
```

**Characteristics:**
- Sharp transitions (detects sudden regime changes)
- Event-specific (captures exact day of news)
- Independent (each day stands alone)
- No memory (yesterday's ETF news forgotten today)

**Use Cases:**
- Event detection: "When did the rally start?"
- Exact pattern matching: "Find days exactly like ETF approval day"
- Regime change detection: Spot large jumps in embedding

### Smoothed Embedding
```python
# Day 0: ETF approval
smoothed_0 = pure_0  # First day

# Day 1: Rally continues
pure_1 = embed("Bitcoin rallies 15% on institutional flows")
smoothed_1 = 0.3 * smoothed_0 + 0.7 * pure_1
# → Still contains 30% of ETF approval news

# Day 2: More rally
pure_2 = embed("Institutional buying continues")
smoothed_2 = 0.3 * smoothed_1 + 0.7 * pure_2
# → Contains 9% of ETF news (0.3 * 0.3)
```

**Characteristics:**
- Emotional persistence (news lingers)
- Smooth transitions (consecutive days similar)
- Regime coherence (bull markets feel related)
- Automatic decay (old news fades exponentially)

**Use Cases:**
- Regime matching: "Find other bull rallies"
- Emotional similarity: "When was market sentiment like this?"
- Trend following: Gradual narrative evolution

## Decay Parameter (α) Tuning

The decay parameter α controls how much "memory" the system has:

```
α = 0.1  →  90% today, 10% yesterday (very reactive)
α = 0.2  →  80% today, 20% yesterday (recommended for crypto)
α = 0.3  →  70% today, 30% yesterday (balanced)
α = 0.4  →  60% today, 40% yesterday (recommended for equities)
α = 0.5  →  50% today, 50% yesterday (very smooth)
```

### Cascading Decay Table

| Days Ago | α=0.1 | α=0.2 | α=0.3 | α=0.4 | α=0.5 |
|----------|-------|-------|-------|-------|-------|
| -1       | 10%   | 20%   | 30%   | 40%   | 50%   |
| -2       | 1%    | 4%    | 9%    | 16%   | 25%   |
| -3       | 0.1%  | 0.8%  | 2.7%  | 6.4%  | 12.5% |
| -7       | ~0%   | 0.02% | 0.05% | 0.3%  | 0.8%  |
| -14      | ~0%   | ~0%   | ~0%   | 0.01% | 0.006%|

### Recommended Values

**Crypto (Bitcoin, Ethereum):**
- α = 0.2-0.3
- Rationale: Fast-moving narratives, news cycles measured in days
- 20% decay = news persists ~3-5 days

**Equities:**
- α = 0.3-0.5
- Rationale: Slower narratives, earnings/macro cycles
- 40% decay = news persists ~1-2 weeks

**Forex:**
- α = 0.4-0.5
- Rationale: Central bank policy has long-lasting effects
- 50% decay = news persists weeks to months

## Query Strategies

### Strategy 1: Pure Embedding Query
```python
# Find exact event matches
similar = find_similar(
    query_embedding=today.pure_embedding,
    index_contains='smoothed',
    top_k=10
)
# Use case: "Find days exactly like today's headlines"
```

### Strategy 2: Smoothed Embedding Query
```python
# Find regime matches
similar = find_similar(
    query_embedding=today.smoothed_embedding,
    index_contains='smoothed',
    top_k=10
)
# Use case: "Find periods with similar emotional context"
```

### Strategy 3: Combined Scoring
```python
# Semantic + numeric similarity
candidates = find_similar(today.smoothed_embedding, top_k=30)

for candidate in candidates:
    semantic_score = candidate.similarity

    # Numeric similarity
    rsi_score = 1 - abs(today.rsi - candidate.rsi) / 20
    volume_score = 1 - abs(today.volume_ratio - candidate.volume_ratio)

    # Combined
    combined = (0.4 * semantic_score +
                0.3 * rsi_score +
                0.3 * volume_score)

    candidate.final_score = combined
```

## Implementation

### Daily Workflow

```python
from temporal_embedding_retrieval_system import TemporalEmbeddingRetriever

# Initialize (once)
retriever = TemporalEmbeddingRetriever(
    vectorize_index=env.VECTORIZE,
    d1_database=env.DB,
    embedding_function=lambda text: ai.run("@cf/baai/bge-large-en-v1.5", {"text": [text]}),
    alpha=0.25  # Crypto-optimized
)

# Each day:
# 1. Create snapshot (generates dual embeddings automatically)
snapshot = await retriever.create_daily_snapshot(
    date=today,
    headlines=[...],
    indicators={...},
    sentiment={...}
)

# 2. Store (Vectorize + D1)
await retriever.store_snapshot(snapshot)

# 3. Query for similar periods
similar = await retriever.find_similar_with_numeric_filter(
    current_snapshot=snapshot,
    top_k=10,
    rsi_tolerance=10,
    volume_tolerance=0.5
)

# 4. Get prediction from analogs
prediction = await retriever.get_historical_analog_prediction(
    current_snapshot=snapshot,
    lookahead_days=7,
    top_k=10
)

print(f"Expected 7d return: {prediction['expected_return']:.2%}")
print(f"Confidence: {prediction['confidence']:.3f}")
```

## Key Rules

### DO

1. **Blend in vector space**
   ```python
   smoothed = normalize(α * prev_smoothed + (1-α) * pure)
   ```

2. **Normalize after blending**
   ```python
   vec = vec / np.linalg.norm(vec)
   ```

3. **Store dual embeddings**
   - Pure for event detection
   - Smoothed for regime matching

4. **Combine semantic + numeric similarity**
   - Headlines alone miss technical setup
   - Technicals alone miss narrative

5. **Re-evaluate α per asset**
   - Crypto: 0.2-0.3 (fast-moving)
   - Equities: 0.3-0.5 (slower)

### DON'T

1. **Embed an embedding**
   ```python
   # WRONG
   yesterday_text = str(yesterday_embedding)
   today_text = headline + yesterday_text
   embedding = embed(today_text)

   # CORRECT
   pure = embed(headline)
   smoothed = α * yesterday_smoothed + (1-α) * pure
   ```

2. **Skip normalization**
   - Embeddings will drift in magnitude
   - Cosine similarity scores become unreliable

3. **Use same α for all assets**
   - Crypto ≠ equities ≠ forex
   - Tune per market

4. **Predict directly from embedding**
   - Embeddings are contextual features
   - Use for retrieval, not prediction input

---

# PART 7: Complete System Summary

*Source: TEMPORAL_EMBEDDING_SUMMARY.md*

## What We Built

A production-ready system for finding similar historical market periods using **dual embeddings** (pure + smoothed) with **categorical persistence** and **retrieval-based pattern matching**.

## The Three Key Insights

### 1. Never Embed an Embedding
```python
# WRONG: Mixing text and vectors
yesterday_text = str(yesterday_embedding)
text = f"Today: {headline} | Yesterday: {yesterday_text}"
embedding = embed(text)

# CORRECT: Blend in vector space
pure = embed(headline)
smoothed = normalize(α * yesterday_smoothed + (1-α) * pure)
```

### 2. Dual Embeddings
```python
# Generate both per day
pure_embedding = embed(today_headlines)      # Sharp transitions
smoothed_embedding = blend(pure, yesterday)  # Emotional persistence

# Store both, query based on use case
```

### 3. Categorical Persistence
```python
# Different events persist differently
EVENT_PERSISTENCE = {
    'regulatory_approval': 14,  # ETF approvals
    'major_hack': 5,           # Exchange hacks
    'macro_news': 21,          # Fed policy
    'social_trend': 1          # Twitter hype
}
```

## Alpha Parameter Cheat Sheet

| Asset Class | α Value | Decay Rate | News Persists |
|-------------|---------|------------|---------------|
| Crypto | 0.20-0.30 | Fast | 3-5 days |
| Equities | 0.30-0.40 | Medium | 1-2 weeks |
| Forex | 0.40-0.50 | Slow | 2-4 weeks |

## Query Strategy Decision Tree

```
Need to find similar periods?
│
├─ Looking for exact event match?
│  └─ Use PURE embedding
│      Example: "Find other ETF approval days"
│
├─ Looking for similar regime?
│  └─ Use SMOOTHED embedding
│      Example: "Find other bull rallies"
│
└─ Need high precision?
   └─ Use COMBINED scoring (semantic + numeric)
       Example: "Find bull rallies with overbought RSI"
```

## Strategy Pattern Examples

### Historical Analogs
```python
# Average outcomes of top-10 similar periods
prediction = await retriever.get_historical_analog_prediction(
    current_snapshot=today,
    lookahead_days=7,
    top_k=10
)

if prediction['expected_return'] > 0.05 and prediction['confidence'] > 0.8:
    action = "STRONG BUY"
elif prediction['expected_return'] < -0.05 and prediction['confidence'] > 0.8:
    action = "STRONG SELL"
else:
    action = "WAIT"
```

### Regime Detection
```python
# Classify current market regime
regime, confidence = await retriever.classify_regime(
    current_snapshot=today,
    regime_examples={
        'bull_rally': ['2024-01-10', '2023-10-15'],
        'bear_capitulation': ['2022-11-09', '2022-06-13'],
        'consolidation': ['2024-01-05', '2023-12-20']
    }
)

# Adjust position sizing based on regime
position_sizes = {
    'bull_rally': 1.0,           # Full allocation
    'bear_capitulation': 0.0,    # Exit
    'consolidation': 0.5         # Neutral
}
```

## Performance Metrics

### Latency (with bge-large-en-v1.5)
```
Embedding generation:  50-100ms  (Workers AI)
Vectorize query:       60-90ms   (top-10, cosine)
D1 metadata:           10-20ms   (outcomes, indicators)
───────────────────────────────────────────────
Total end-to-end:      120-210ms
```

### Storage Costs (6 years, 2,190 days)
```
Smoothed embeddings:   2.24M dimensions (in values)
Pure embeddings:       2.24M dimensions (in metadata)
Total:                 4.48M dimensions
───────────────────────────────────────────────
Cost:                  ~$0.18/month

Cloudflare free tier:  10M stored dimensions
Remaining capacity:    5.52M dimensions (55% free)
```

## Common Pitfalls to Avoid

### DON'T: Embed an Embedding
```python
# WRONG
yesterday_str = str(yesterday_embedding)
text = f"Today: {headline} | Yesterday: {yesterday_str}"
embedding = embed(text)
```

### DO: Blend in Vector Space
```python
# CORRECT
pure = embed(headline)
smoothed = normalize(α * yesterday_smoothed + (1-α) * pure)
```

### DON'T: Skip Normalization
```python
# WRONG - embeddings drift in magnitude
smoothed = α * yesterday + (1-α) * pure
```

### DO: Always Normalize
```python
# CORRECT
smoothed = normalize(α * yesterday + (1-α) * pure)
```

## Key Rules Summary

1. **Blend in vector space, never in text**
2. **Normalize after every blend**
3. **Store dual embeddings (pure + smoothed)**
4. **Tune α per asset class**
5. **Combine semantic + numeric similarity**
6. **Use for retrieval, not direct prediction**
7. **Track similarity drift for regime shifts**

---

# PART 8: Hybrid Vector-D1 Search Architecture

*Source: HYBRID_SEARCH_ARCHITECTURE.md*

## Overview

Two-stage search combining semantic understanding (Vectorize) with technical pattern matching (D1) for maximum coverage and statistical significance.

## Problem Statement

**Goal**: Find historical periods similar to current conditions to predict outcomes.

**Challenge**:
- Pure semantic search (Vectorize only): Small sample size (5-10 periods)
- Pure technical search (D1 only): Misses semantic context, hard to define "similar"
- Need: Large sample size + semantic understanding

**Solution**: Two-stage hybrid search

## Architecture

```
Current Market State
├─ News: "Bitcoin ETF approval drives institutional buying"
├─ Sentiment: 0.72
└─ Technical: RSI 68, MACD bullish, sentiment velocity 0.08

                    ↓

┌────────────────────────────────────────────────────────────────┐
│ STAGE 1: SEMANTIC SIMILARITY (Vectorize)                      │
│ Time: ~40ms                                                    │
├────────────────────────────────────────────────────────────────┤
│ Embed current news → Query Vectorize for similar narratives   │
│ Returns: 5-10 "anchor" periods with metadata                  │
└────────────────────────────────────────────────────────────────┘

                    ↓

┌────────────────────────────────────────────────────────────────┐
│ PATTERN EXTRACTION                                             │
├────────────────────────────────────────────────────────────────┤
│ Extract metadata patterns with tolerance:                     │
│ Pattern 1: RSI: 67-77, MACD: bullish, Sentiment vel: 0.06-0.10│
│ Pattern 2: RSI: 63-73, MACD: bullish, Sentiment vel: 0.10-0.14│
│ Pattern 3: RSI: 70-80, MACD: bullish, Sentiment vel: 0.04-0.08│
└────────────────────────────────────────────────────────────────┘

                    ↓

┌────────────────────────────────────────────────────────────────┐
│ STAGE 2: TECHNICAL PATTERN EXPANSION (D1)                     │
│ Time: ~50-100ms per pattern                                   │
├────────────────────────────────────────────────────────────────┤
│ For each pattern, query D1 for ALL matching periods:          │
│ SQL: SELECT * FROM chaos_trades                               │
│      WHERE entry_rsi_14 BETWEEN 67 AND 77                     │
│        AND entry_macd_bullish_cross = 1                       │
│        AND sentiment_velocity BETWEEN 0.06 AND 0.10           │
│                                                                │
│ Returns: 52 + 61 + 48 = 161 periods (156 after dedup)        │
└────────────────────────────────────────────────────────────────┘

                    ↓

┌────────────────────────────────────────────────────────────────┐
│ OUTCOME ANALYSIS                                               │
├────────────────────────────────────────────────────────────────┤
│ Analyze what happened after all 156 periods:                  │
│ • Total periods: 156                                           │
│ • Profitable: 102 (65.4% win rate)                            │
│ • Avg 7-day return: +8.3%                                     │
│ • Sharpe ratio: 1.8                                           │
│                                                                │
│ Decision: BULLISH signal with strong historical precedent     │
└────────────────────────────────────────────────────────────────┘
```

## Why This Works

### Stage 1: Vectorize (Semantic Anchor)

**Advantages**:
- Semantic understanding: "ETF approval" ≈ "Institutional adoption"
- Fast: ~40ms for top-10 results
- Quality: Returns truly similar market narratives

**Limitations**:
- Small sample: Only 5-10 periods
- Limited statistical significance

### Stage 2: D1 (Technical Expansion)

**Advantages**:
- Large sample: 50-200+ periods
- Statistical significance
- Finds periods you might have missed

**Limitations**:
- Slower: 50-100ms per pattern query
- No semantic understanding

### Combined: Best of Both Worlds

| Metric | Vectorize Only | D1 Only | Hybrid |
|--------|---------------|---------|--------|
| Sample size | 5-10 | ??? | 50-200+ |
| Semantic understanding | Yes | No | Yes |
| Statistical significance | No | Yes | Yes |
| Speed | 40ms | 50-100ms | 200-400ms total |

**Result**: 19x larger sample size vs Vectorize alone

## Performance

### Latency Breakdown

```
Stage 1: Vectorize semantic search          40ms
Stage 2: Extract patterns                    2ms
Stage 3: D1 queries (3 patterns × 60ms)   180ms
Stage 4: Deduplicate & analyze               8ms
────────────────────────────────────────────────
TOTAL:                                     230ms
```

**Still fast enough for real-time trading decisions!**

---

# PART 9: Fast Metadata Matching (No Vector Search)

*Source: FAST_METADATA_MATCHING.md*

## Overview

For finding historical periods by exact metadata conditions (RSI, sentiment velocity, etc.) with outcomes, **you don't need vector embeddings or semantic search**.

Simple indexed database queries are sufficient and fast.

## The Simple Approach: D1 with Proper Indexes

### Step 1: Add Indexes to D1

```sql
-- Individual indexes for common filters
CREATE INDEX IF NOT EXISTS idx_rsi
  ON chaos_trades(entry_rsi_14);

CREATE INDEX IF NOT EXISTS idx_sentiment_velocity
  ON chaos_trades(sentiment_velocity);

CREATE INDEX IF NOT EXISTS idx_fear_greed
  ON chaos_trades(sentiment_fear_greed);

CREATE INDEX IF NOT EXISTS idx_macd
  ON chaos_trades(entry_macd_bullish_cross);

CREATE INDEX IF NOT EXISTS idx_volatility
  ON chaos_trades(entry_volatility_regime);

CREATE INDEX IF NOT EXISTS idx_trend
  ON chaos_trades(entry_trend_regime);

CREATE INDEX IF NOT EXISTS idx_profitable
  ON chaos_trades(profitable);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_rsi_sentiment_profitable
  ON chaos_trades(
    entry_rsi_14,
    sentiment_velocity,
    profitable
  );
```

### Step 2: Query for Matching Periods

```python
async def find_matching_periods(
    d1: CloudflareD1Service,
    rsi_range: tuple[float, float],
    sentiment_velocity_range: tuple[float, float],
    fear_greed_range: tuple[int, int],
    only_profitable: bool = False
) -> list[dict]:
    """
    Find all historical periods matching metadata conditions.
    Returns with outcomes already attached.

    Typical query time: 10-50ms
    """
    sql = """
        SELECT
            id, entry_time, exit_time,
            entry_rsi_14 as rsi,
            entry_macd_bullish_cross,
            sentiment_velocity,
            sentiment_fear_greed as fear_greed,
            entry_price, exit_price,
            pnl_pct as outcome_7d,
            profitable as profitable_7d
        FROM chaos_trades
        WHERE entry_rsi_14 BETWEEN ? AND ?
          AND sentiment_velocity BETWEEN ? AND ?
          AND sentiment_fear_greed BETWEEN ? AND ?
    """

    params = [
        rsi_range[0], rsi_range[1],
        sentiment_velocity_range[0], sentiment_velocity_range[1],
        fear_greed_range[0], fear_greed_range[1]
    ]

    if only_profitable:
        sql += " AND profitable = 1"

    return await d1.query(sql, params)
```

## Performance

With proper indexes, D1 queries are fast:

| Query Type | Latency | Notes |
|------------|---------|-------|
| Simple filter (1-2 conditions) | 10-30ms | Using single index |
| Complex filter (3-5 conditions) | 30-50ms | Using composite index |
| Full scan (no indexes) | 200-500ms | Don't do this! |

**Key**: Make sure your WHERE clauses use indexed columns!

## Summary

**You don't need Vectorize or embeddings at all for pure technical matching!**

Simple solution:
1. Store indicators + outcomes in D1 (you already have this)
2. Add proper indexes (one-time setup)
3. Query by metadata ranges (10-50ms)
4. Outcomes already attached (no lookups)

Query example:
```sql
-- Find matching periods (returns in 20-40ms)
SELECT * FROM chaos_trades
WHERE entry_rsi_14 BETWEEN 65 AND 75
  AND sentiment_velocity BETWEEN 0.06 AND 0.10
  AND sentiment_fear_greed BETWEEN 62 AND 82
  AND profitable = 1;
-- Returns 100+ matches with outcomes instantly!
```

---

# PART 10: Vectorize Metadata Templates

*Source: VECTORIZE_METADATA_TEMPLATE.md & VECTORIZE_METADATA_WITH_OUTCOMES.md*

## Overview

**Key Concept**: Store CURRENT indicators, then look FORWARD from timestamps to see outcomes.

## Complete Metadata Template (Without Outcomes)

```python
{
    "id": "2024-01-15T12:00:00Z",
    "values": [...],  # 384-dim embedding

    "metadata": {
        # TEMPORAL
        "timestamp": 1705320000,
        "day_of_week": 1,
        "hour_of_day": 14,
        "month": 1,

        # TREND & MOMENTUM
        "rsi": 68,
        "rsi_range": "neutral",
        "rsi_slope": 0.5,
        "macd_histogram": 450.5,
        "macd_signal": "bullish",
        "momentum_5": 0.032,
        "trend": "uptrend",
        "trend_strength": 0.75,

        # MOVING AVERAGES
        "sma_20": 43500,
        "sma_50": 42000,
        "sma_200": 38000,
        "price_vs_sma200": 1.18,
        "sma_alignment": "golden_cross",

        # VOLATILITY
        "atr_pct": 0.028,
        "volatility": "medium",
        "bb_position": 0.85,

        # VOLUME
        "volume_ratio": 1.45,
        "volume_spike": 1,

        # SENTIMENT (THE GOLD!)
        "sentiment_score": 0.65,
        "sentiment_velocity": 0.08,
        "sentiment_acceleration": 0.02,
        "fear_greed": 72,

        # NEWS
        "news_volume_1hr": 8,
        "primary_category": "regulation",

        # PRICE
        "btc_price": 45000,

        # TEXT SUMMARIES (for embedding)
        "news_summary": "Bitcoin ETF approval drives rally",
        "technical_setup": "Strong bullish momentum"
    }
}
```

## Complete Metadata Template (With Outcomes)

```python
{
    "id": "2024-01-15T14:00:00Z",
    "values": [...],

    "metadata": {
        # [All current state indicators from above...]

        # OUTCOMES (filled in after time passes)

        # 1-Day Outcomes
        "outcome_1d": 0.023,
        "profitable_1d": 1,
        "max_drawdown_1d": -0.012,
        "peak_return_1d": 0.035,

        # 7-Day Outcomes
        "outcome_7d": 0.083,
        "profitable_7d": 1,
        "max_drawdown_7d": -0.025,
        "peak_return_7d": 0.112,
        "days_to_peak": 5,
        "volatility_7d": 0.035,
        "sharpe_7d": 2.3,

        # 30-Day Outcomes
        "outcome_30d": 0.156,
        "profitable_30d": 1,
        "max_drawdown_30d": -0.048,

        # Outcome Classification
        "outcome_class_7d": "strong_win",
        "trend_after_7d": "continued"
    }
}
```

## Why Outcomes in Metadata?

### Before (Two-Step Lookup):
```python
# 1. Find similar periods
similar = await vectorize.query(current_embedding)
# Returns: [T1, T2, T3, ...]

# 2. Look up outcomes separately (slow!)
for ts in similar:
    outcome = await d1.query("SELECT * WHERE timestamp = ?", [ts])
```

### After (Outcomes in Metadata):
```python
# 1. Find similar periods (same query)
similar = await vectorize.query(current_embedding)

# 2. Outcomes already included!
for period in similar:
    print(f"Setup: RSI {period.rsi}, sentiment velocity {period.sentiment_velocity}")
    print(f"Outcome: {period.outcome_7d:.1%}")  # Already here!
    # No additional lookups needed!
```

## Two-Phase Storage Strategy

### Phase 1: Create Snapshot (Time T)
Store current market state with NULL outcomes

### Phase 2: Update with Outcomes (Time T + 7/30 days)
Fill in what actually happened after this period

```python
async def backfill_outcomes():
    """
    Run daily to update records with outcomes.
    Updates records that are 7/30 days old.
    """
    seven_days_ago = int(time.time()) - (7 * 24 * 60 * 60)
    records_to_update = await get_records_from_timestamp(seven_days_ago)

    for record in records_to_update:
        entry_timestamp = record.metadata["timestamp"]
        entry_price = record.metadata["btc_price"]

        # Calculate outcomes
        prices_7d = get_prices_for_period(entry_timestamp, days=7)
        outcome_7d = (prices_7d[-1] - entry_price) / entry_price
        max_drawdown = calculate_max_drawdown(prices_7d, entry_price)

        # Update the record in Vectorize
        updated_metadata = {
            **record.metadata,
            "outcome_7d": outcome_7d,
            "profitable_7d": 1 if outcome_7d > 0 else 0,
            "max_drawdown_7d": max_drawdown,
        }

        await vectorize.upsert([{
            "id": record.id,
            "values": record.values,
            "metadata": updated_metadata
        }])
```

## Priority Metadata Indexes (Top 10)

```bash
wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=timestamp --type=number

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=rsi --type=number

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=sentiment_velocity --type=number

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=fear_greed --type=number

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=trend --type=string

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=macd_signal --type=string

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=volatility --type=string

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=profitable_7d --type=boolean

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=outcome_7d --type=number

wrangler vectorize create-metadata-index pyswarm-time-periods \
  --property-name=day_of_week --type=number
```

---

# PART 11: Vectorize Schema Rules & Constraints

*Source: VECTORIZE_SCHEMA_RULES.md*

## Quick Reference Card

| Component | Limit | Notes |
|-----------|-------|-------|
| **Metadata per vector** | 10 KiB | Total JSON size |
| **Vector ID** | 64 bytes | String identifier |
| **Dimensions** | 1536 max | 32-bit precision |
| **Vectors per index** | 5,000,000 | Hard limit |
| **Metadata indexes** | 10 per index | Must create before inserting vectors |
| **Index name** | 64 bytes | Account-wide unique |
| **Filter JSON** | 2,048 bytes | Compact representation |
| **Property names** | 512 chars max | No dots, spaces, $, pipes |

## Index Configuration (One-Time Setup)

### Creating an Index

```bash
wrangler vectorize create INDEX_NAME \
  --dimensions=384 \
  --metric=cosine \
  --description="Optional description"
```

**Rules**:
- Index name: **64 bytes max**
- Dimensions: **Fixed at creation** (cannot change later)
- Metric: `cosine`, `euclidean`, or `dot-product`
- **Cannot change dimensions or metric after creation!**

### Account Limits

- **Workers Paid**: 50,000 indexes
- **Workers Free**: 100 indexes
- **Namespaces**: 50,000 per index (Paid only)

## Vector Structure

### Vector Object Schema

```typescript
{
  id: string,              // Required, max 64 bytes
  values: number[],        // Required, must match index dimensions
  metadata?: object,       // Optional, max 10 KiB JSON
  namespace?: string       // Optional (Paid plan only)
}
```

## Metadata Rules

### Supported Data Types

| Type | Example | Notes |
|------|---------|-------|
| `string` | `"Bitcoin rally"` | Indexed to first 64 bytes |
| `number` | `45000` or `0.75` | Float64 precision |
| `boolean` | `true` or `false` | - |
| `null` | `null` | - |
| Arrays | `[1, 2, 3]` | Only for `$in`/`$nin` operators |
| Objects | `{price: 45000}` | Nestable |

### Property Name Rules

**CANNOT contain**:
- `.` (dot) - Reserved for nested access
- ` ` (space)
- `|` (pipe)
- `$` (dollar sign) at start
- Empty strings

**MUST**: Be ≤ 512 characters

## Query Filters

### Supported Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equals | `{"sentiment_score": {"$eq": 0.75}}` |
| `$ne` | Not equals | `{"market_phase": {"$ne": "bear"}}` |
| `$in` | In array | `{"phase": {"$in": ["bull", "neutral"]}}` |
| `$nin` | Not in array | `{"phase": {"$nin": ["bear"]}}` |
| `$gt` | Greater than | `{"timestamp": {"$gt": 1705320000}}` |
| `$gte` | Greater than or equal | `{"sentiment": {"$gte": 0.5}}` |
| `$lt` | Less than | `{"timestamp": {"$lt": 1705400000}}` |
| `$lte` | Less than or equal | `{"sentiment": {"$lte": 0.8}}` |

### Filter Examples

```typescript
// Simple equality
filter: { "market_phase": { "$eq": "bull_rally" } }

// Range query
filter: { "sentiment_score": { "$gte": 0.5, "$lte": 0.9 } }

// Multiple conditions (AND logic)
filter: {
  "timestamp": { "$gte": 1705320000, "$lt": 1705406400 },
  "sentiment_score": { "$gte": 0.5 }
}

// Array membership
filter: { "market_phase": { "$in": ["bull_rally", "accumulation"] } }

// Nested properties
filter: { "technical.rsi": { "$gte": 60, "$lte": 80 } }
```

### Filter Constraints

**Allowed**:
- Multiple properties (AND logic)
- Range queries (combining `$gte` and `$lte` on same field)
- Nested property access

**NOT Allowed**:
- OR logic between properties (use multiple queries instead)
- Filtering on non-indexed properties (will be ignored)

## Query Limits

### topK Limits

| Returns Metadata/Values | Max topK |
|-------------------------|----------|
| **Yes** (returnMetadata: true) | 20 |
| **No** (returnMetadata: false) | 100 |

### Batch Operations

| Operation | Workers API | HTTP API |
|-----------|-------------|----------|
| **Upsert batch** | 1,000 vectors | 5,000 vectors |
| **Delete batch** | 1,000 IDs | 1,000 IDs |

## Common Pitfalls to Avoid

### DON'T

```typescript
// Metadata too large (>10 KiB)
metadata: { full_article_text: "..." }  // 50 KB article

// Property name with dot
metadata: { "btc.price": 45000 }  // Use btc_price or nested object

// Filtering without index
filter: { "sentiment_score": { "$gte": 0.5 } }  // Won't work without index!

// Wrong dimension count
values: new Array(768).fill(0)  // Dimension mismatch if index is 384!

// Using OR logic
filter: { "$or": [...] }  // OR not supported!
```

### DO

```typescript
// Store summary, link to full text elsewhere
metadata: {
  news_summary: "Bitcoin ETF approved...",  // <1 KB
  article_id: "abc123"  // Look up full text in D1/KV
}

// Use underscore or nested object
metadata: {
  btc_price: 45000,
  market: { btc: { price: 45000 } }
}

// Create index FIRST, then insert vectors
// wrangler vectorize create-metadata-index ... (first!)
// Then insert vectors with that metadata

// Use $in for OR logic
filter: { "phase": {"$in": ["bull", "accumulation"]} }
```

## Summary Checklist

Before deploying:

- [ ] Decided on dimensions (384, 768, or 1024) - **cannot change later!**
- [ ] Identified which metadata fields need filtering
- [ ] Created metadata indexes BEFORE inserting vectors
- [ ] Property names avoid dots, spaces, $, pipes
- [ ] Metadata size <10 KiB per vector
- [ ] Vector IDs <64 bytes
- [ ] Filter JSON <2,048 bytes
- [ ] Batch operations ≤1,000 vectors (Workers API)
- [ ] topK ≤20 when returning metadata

---

# END OF CONSOLIDATED DOCUMENT

**Original Source Files:**
1. EMBEDDINGS_README.md
2. EMBEDDING_SYSTEM_SETUP.md
3. EMBEDDING_STRATEGY_GUIDE.md
4. DUAL_EMBEDDING_STRATEGY.md
5. MODEL_SELECTION_GUIDE.md
6. TEMPORAL_EMBEDDING_STRATEGIES.md
7. TEMPORAL_EMBEDDING_SUMMARY.md
8. HYBRID_SEARCH_ARCHITECTURE.md
9. FAST_METADATA_MATCHING.md
10. VECTORIZE_METADATA_TEMPLATE.md
11. VECTORIZE_METADATA_WITH_OUTCOMES.md
12. VECTORIZE_SCHEMA_RULES.md
# SHARD ARCHITECTURE - Complete Documentation

**Consolidated from 2 source files covering database sharding.**

---

# TABLE OF CONTENTS

- [PART 1: Migration Guide](#part-1-migration-guide)
- [PART 2: Quick Reference](#part-2-quick-reference)

---

# PART 1: Migration Guide

*Source: SHARD_MIGRATION_GUIDE.md*

## Overview

The refactoring separates the monolithic `coinswarm-evolution` database into specialized shards:

| Shard | Binding | Tables | Purpose |
|-------|---------|--------|---------|
| Main Evolution | `env.DB` | trading_agents, patterns, chaos_trades | Core agents |
| Wisdom | `env.WISDOM_DB` | wisdom_contributions, agent_wisdom_knowledge | Wisdom system |
| Planners | `env.PLANNERS_DB` | planner_agents, committee_members, votes | Planners & voting |
| Grand Challenge | `env.GRAND_CHALLENGE_DB` | grand_challenge_entries | Elite competitions |
| Data Shards 1-4 | `env.DATA_SHARD_1-4` | ohlcv_* | OHLCV candle data |

## Environment Interface

```typescript
import type { Env } from './types/env';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Access databases:
    // env.DB - Main evolution
    // env.WISDOM_DB - Wisdom system
    // env.PLANNERS_DB - Planners/Committee
    // env.GRAND_CHALLENGE_DB - Grand Challenge
    // env.DATA_SHARD_1 - OHLCV data
    // env.AI - AI binding
  }
}
```

## Worker → Shard Mapping

| Worker | Shard Binding |
|--------|---------------|
| wisdom-distillation.ts, wisdom-worker.ts | `env.WISDOM_DB` |
| planner-orchestrator.ts, committee-voting.ts | `env.PLANNERS_DB` |
| grand-challenge-manager.ts | `env.GRAND_CHALLENGE_DB` |
| pattern-slot-manager.ts | `env.DB` (main) |
| dashboards-worker.ts | All shards |

## Worker-by-Worker Changes

### Wisdom Workers
```typescript
// Before
export async function processWisdomDistillation(db: D1Database, ai: any) { }

// After
export async function processWisdomDistillation(
  wisdomDb: D1Database,    // WISDOM_DB shard
  evolutionDb: D1Database, // DB shard
  ai: any
) {
  // Use wisdomDb for wisdom tables
  // Use evolutionDb for trading_agents
}
```

### Multi-Shard Dashboard
```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (url.pathname === '/api/agents') {
      return Response.json(await env.DB.prepare('...').all());
    }
    if (url.pathname === '/api/wisdom') {
      return Response.json(await env.WISDOM_DB.prepare('...').all());
    }
    if (url.pathname === '/api/stats') {
      const [agents, wisdom, planners] = await Promise.all([
        env.DB.prepare('SELECT COUNT(*) FROM trading_agents').first(),
        env.WISDOM_DB.prepare('SELECT COUNT(*) FROM wisdom_contributions').first(),
        env.PLANNERS_DB.prepare('SELECT COUNT(*) FROM planner_agents').first()
      ]);
      return Response.json({ agents, wisdom, planners });
    }
  }
}
```

## Common Pitfalls

### Wrong Database Binding
```typescript
// WRONG
await env.DB.prepare('SELECT * FROM wisdom_contributions').all();

// RIGHT
await env.WISDOM_DB.prepare('SELECT * FROM wisdom_contributions').all();
```

### Cross-Shard JOINs (Not Supported)
```typescript
// WRONG - Can't JOIN across shards
SELECT ta.agent_name, wc.wisdom_id
FROM trading_agents ta
JOIN wisdom_contributions wc ON ta.agent_id = wc.contributor_agent_id

// RIGHT - Query separately, join in code
const agents = await env.DB.prepare('SELECT agent_id, agent_name FROM trading_agents').all();
const wisdom = await env.WISDOM_DB.prepare('SELECT wisdom_id, contributor_agent_id FROM wisdom_contributions').all();

const combined = agents.results.map(agent => ({
  ...agent,
  wisdom: wisdom.results.filter(w => w.contributor_agent_id === agent.agent_id)
}));
```

## Deployment Checklist

- [ ] Create D1 shards with `create-shards.ps1`
- [ ] Update `wrangler.toml` with database IDs
- [ ] Run migrations with `migrate-shards.ps1`
- [ ] Update all worker files to use `env.*_DB` bindings
- [ ] Test locally with `wrangler dev`
- [ ] Deploy with `wrangler deploy`
- [ ] Verify queries work in production

---

# PART 2: Quick Reference

*Source: SHARD_QUICK_REFERENCE.md*

## Database Bindings

| Shard | Binding | Tables | Use For |
|-------|---------|--------|---------|
| **coinswarm-evolution** | `env.DB` | trading_agents, patterns, chaos_trades | Core agents |
| **coinswarm-data-shard-1** | `env.DATA_SHARD_1` | ohlcv_* | OHLCV data |
| **coinswarm-wisdom** | `env.WISDOM_DB` | wisdom_contributions, etc | Wisdom |
| **coinswarm-planners** | `env.PLANNERS_DB` | planner_agents, committee_* | Voting |
| **coinswarm-grand-challenge** | `env.GRAND_CHALLENGE_DB` | grand_challenge_entries | Competitions |

## Quick Commands

```powershell
# Create shards
cd cloudflare-agents
.\scripts\create-shards.ps1

# Migrate schemas
.\scripts\migrate-shards.ps1

# Test locally
wrangler dev

# Deploy
wrangler deploy

# Query a shard
wrangler d1 execute coinswarm-wisdom --command="SELECT COUNT(*) FROM wisdom_contributions"
```

## Common Patterns

### Single Shard Query
```typescript
const agents = await env.DB.prepare(
  'SELECT * FROM trading_agents WHERE status = ?'
).bind('active').all();
```

### Cross-Shard Operation
```typescript
// Get agent from main shard
const agent = await env.DB.prepare(
  'SELECT * FROM trading_agents WHERE agent_id = ?'
).bind(agentId).first();

// Create wisdom from Grand Challenge
await env.WISDOM_DB.prepare(
  'INSERT INTO wisdom_contributions (...) VALUES (...)'
).bind(...).run();
```

### Parallel Multi-Shard Query
```typescript
const [agents, wisdom, planners] = await Promise.all([
  env.DB.prepare('SELECT COUNT(*) FROM trading_agents').first(),
  env.WISDOM_DB.prepare('SELECT COUNT(*) FROM wisdom_contributions').first(),
  env.PLANNERS_DB.prepare('SELECT COUNT(*) FROM planner_agents').first()
]);
```

## Status Check

```bash
# List all databases
wrangler d1 list

# Check table counts
wrangler d1 execute coinswarm-evolution --command="SELECT COUNT(*) FROM trading_agents"
wrangler d1 execute coinswarm-wisdom --command="SELECT COUNT(*) FROM wisdom_contributions"
wrangler d1 execute coinswarm-planners --command="SELECT COUNT(*) FROM planner_agents"
```

---

# END OF CONSOLIDATED DOCUMENT

**Original Source Files:**
1. SHARD_MIGRATION_GUIDE.md
2. SHARD_QUICK_REFERENCE.md
