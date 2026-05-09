# Data Collection Specification for ML Trading Intelligence

**Version**: 1.0
**Date**: 2025-12-24
**Purpose**: Comprehensive specification for data collection team to enable ML-based trading intelligence

---

## Executive Summary

We are building a supervised ML pipeline that predicts trading outcomes. To train these models, we need to capture **~100 features per trade** at multiple points in time: entry, maximum favorable excursion (MFE), maximum adverse excursion (MAE), and exit.

**The Goal**: Collect enough high-quality trade data (50K-500K+ trades) to train models that answer:
1. "Should I enter this trade?" (Entry prediction)
2. "Should I exit now?" (Exit optimization)
3. "How much should I risk?" (Position sizing)

---

## Table of Contents

1. [Data Collection Overview](#1-data-collection-overview)
2. [Required Data Sources](#2-required-data-sources)
3. [Feature Specifications](#3-feature-specifications)
4. [Trade Record Schema](#4-trade-record-schema)
5. [Data Quality Requirements](#5-data-quality-requirements)
6. [Collection Priorities](#6-collection-priorities)
7. [Existing Infrastructure](#7-existing-infrastructure)
8. [Gap Analysis](#8-gap-analysis)

---

## 1. Data Collection Overview

### What We're Collecting

| Data Type | Purpose | Volume Target |
|-----------|---------|---------------|
| **Trade Records** | ML training labels | 50K-500K trades |
| **Technical Indicators** | Entry/exit features | ~50 per timeframe |
| **Multi-Timeframe Context** | Higher-TF confirmation | 15m, 1h, 4h, 1d |
| **Cross-Asset Metrics** | Correlation/beta | BTC, ETH, SOL pairs |
| **Sentiment Data** | Fear/greed, funding | Real-time when available |
| **Order Book Snapshots** | Microstructure | Live trading only |

### Data Flow

```
Raw OHLCV Data (Binance/Coinbase/etc.)
         ↓
    Indicator Calculation (130+ indicators via pandas_ta)
         ↓
    Enriched Candles (219 columns per candle)
         ↓
    Backtest Engine (pattern matching, trade simulation)
         ↓
    ML Trade Records (~100 features per trade)
         ↓
    Training Dataset (parquet/CSV export)
```

---

## 2. Required Data Sources

### 2.1 OHLCV Candle Data (PRIORITY: CRITICAL)

**What**: Open, High, Low, Close, Volume for each asset/timeframe combination.

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `asset` | string | Trading pair symbol (e.g., "BTC", "ETH") | YES |
| `timeframe` | string | Candle period: "1h", "4h", "1d" | YES |
| `timestamp` | int | Unix timestamp (seconds) | YES |
| `open` | float | Opening price | YES |
| `high` | float | Highest price in period | YES |
| `low` | float | Lowest price in period | YES |
| `close` | float | Closing price | YES |
| `volume` | float | Trading volume in base asset | YES |

**Assets Required** (Priority Order):

| Tier | Assets | Reason |
|------|--------|--------|
| 1 | BTC, ETH | Base pairs, always needed for cross-asset |
| 2 | SOL | Base pair for ecosystem analysis |
| 3 | AVAX, LINK, DOT, ATOM, ADA | Major L1s/DeFi |
| 4 | ARB, OP, MATIC | L2 ecosystem |
| 5 | All others in portfolio | Broader coverage |

**Timeframes Required**:

| Timeframe | Purpose | History Needed |
|-----------|---------|----------------|
| **1h** | Primary trading timeframe | 3+ years |
| **4h** | Medium-term context | 3+ years |
| **1d** | Long-term trend/regime | 5+ years |
| **15m** | Short-term momentum (optional) | 1+ year |

**Data Sources**:
- Binance API (primary) - 1000 candles per request, 1200 req/min
- Coinbase API (backup) - Good for US-based assets
- CryptoCompare (historical) - Deep history available

### 2.2 Cross-Asset Reference Prices (PRIORITY: HIGH)

For multi-denomination P&L (did we outperform BTC/SOL?), we need BTC and SOL prices at every trade entry/exit timestamp.

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `btc_usd_price` | float | BTC/USD at timestamp |
| `sol_usd_price` | float | SOL/USD at timestamp |
| `eth_usd_price` | float | ETH/USD at timestamp |

**Usage**: At trade entry and exit, capture these prices to calculate:
- `pnl_btc_pct` = Did we outperform just holding BTC?
- `pnl_sol_pct` = Did we outperform just holding SOL?

### 2.3 Sentiment Data (PRIORITY: MEDIUM)

**Fear & Greed Index**:

| Field | Type | Source | Update Frequency |
|-------|------|--------|------------------|
| `fear_greed_index` | int (0-100) | alternative.me | Daily |
| `fear_greed_class` | string | "Extreme Fear" to "Extreme Greed" | Daily |

**Funding Rates** (for perpetual futures):

| Field | Type | Source | Update Frequency |
|-------|------|--------|------------------|
| `funding_rate` | float | Binance Futures | 8-hourly |
| `next_funding_time` | int | Binance Futures | 8-hourly |
| `funding_rate_24h_avg` | float | Calculated | 8-hourly |

**Collection Method**: Store snapshots keyed by timestamp, interpolate for backtest.

### 2.4 Order Book Data (PRIORITY: LOW - Live Trading Only)

For live trading, capture order book state at trade execution time.

| Field | Type | Description |
|-------|------|-------------|
| `bid_price_1` | float | Best bid price |
| `ask_price_1` | float | Best ask price |
| `bid_depth_1pct` | float | Total bid volume within 1% of mid |
| `ask_depth_1pct` | float | Total ask volume within 1% of mid |
| `spread_pct` | float | (ask - bid) / mid * 100 |
| `order_imbalance` | float | (bid_depth - ask_depth) / total |

**Note**: NULL for historical backtests. Only populated for live/paper trading.

---

## 3. Feature Specifications

### 3.1 Technical Indicators (1h Timeframe) - ~50 Features

These are calculated from 1h OHLCV data using `pandas_ta` library.

#### Momentum Indicators

| Indicator | Pandas_ta Name | Formula/Description | Typical Range |
|-----------|----------------|---------------------|---------------|
| `rsi14` | RSI_14 | Relative Strength Index (14 period) | 0-100 |
| `rsi7` | RSI_7 | RSI with 7 period lookback | 0-100 |
| `macd_line` | MACD_12_26_9 | MACD line (12, 26 EMA diff) | -∞ to +∞ |
| `macd_signal` | MACDs_12_26_9 | MACD signal line | -∞ to +∞ |
| `macd_histogram` | MACDh_12_26_9 | MACD histogram | -∞ to +∞ |
| `stoch_k` | STOCHk_14_3_3 | Stochastic %K | 0-100 |
| `stoch_d` | STOCHd_14_3_3 | Stochastic %D | 0-100 |
| `cci20` | CCI_20 | Commodity Channel Index | -300 to +300 |
| `williams_r` | WILLR_14 | Williams %R | -100 to 0 |
| `roc12` | ROC_12 | Rate of Change (12 period) | -∞ to +∞ |
| `mfi14` | MFI_14 | Money Flow Index | 0-100 |

#### Trend Indicators

| Indicator | Pandas_ta Name | Formula/Description | Typical Range |
|-----------|----------------|---------------------|---------------|
| `adx14` | ADX_14 | Average Directional Index | 0-100 |
| `plus_di` | DMP_14 | Plus Directional Indicator | 0-100 |
| `minus_di` | DMN_14 | Minus Directional Indicator | 0-100 |
| `aroon_up` | AROONU_14 | Aroon Up | 0-100 |
| `aroon_down` | AROOND_14 | Aroon Down | 0-100 |
| `aroon_osc` | AROONOSC_14 | Aroon Oscillator | -100 to +100 |
| `ema20` | EMA_20 | 20-period EMA | Price level |
| `ema50` | EMA_50 | 50-period EMA | Price level |
| `sma20` | SMA_20 | 20-period SMA | Price level |
| `sma50` | SMA_50 | 50-period SMA | Price level |

#### Volatility Indicators

| Indicator | Pandas_ta Name | Formula/Description | Typical Range |
|-----------|----------------|---------------------|---------------|
| `atr14` | ATRr_14 | Average True Range (14) | 0 to +∞ |
| `bb_upper` | BBU_20_2.0 | Bollinger Upper Band | Price level |
| `bb_lower` | BBL_20_2.0 | Bollinger Lower Band | Price level |
| `bb_width` | BBB_20_2.0 | Bollinger Band Width | 0 to +∞ |
| `bb_position` | BBP_20_2.0 | Position within bands | 0-1 |
| `keltner_upper` | KCUe_20_2 | Keltner Channel Upper | Price level |
| `keltner_lower` | KCLe_20_2 | Keltner Channel Lower | Price level |
| `donchian_upper` | DCU_20_20 | Donchian Upper | Price level |
| `donchian_lower` | DCL_20_20 | Donchian Lower | Price level |

#### Volume Indicators

| Indicator | Pandas_ta Name | Formula/Description | Typical Range |
|-----------|----------------|---------------------|---------------|
| `obv` | OBV | On-Balance Volume | Cumulative |
| `ad` | AD | Accumulation/Distribution | Cumulative |
| `cmf20` | CMF_20 | Chaikin Money Flow | -1 to +1 |
| `vwap` | VWAP_D | Volume Weighted Avg Price | Price level |
| `volume_sma20` | Calculated | 20-period volume SMA | Volume units |
| `volume_ratio` | Calculated | current_vol / sma20_vol | 0 to +∞ |

#### Derived/Computed Indicators

| Indicator | Formula | Type | Range |
|-----------|---------|------|-------|
| `above_ema20` | close > ema20 | Binary | 0 or 1 |
| `above_sma50` | close > sma50 | Binary | 0 or 1 |
| `golden_cross` | ema20 > ema50 | Binary | 0 or 1 |
| `death_cross` | ema20 < ema50 | Binary | 0 or 1 |
| `rsi_oversold` | rsi14 < 30 | Binary | 0 or 1 |
| `rsi_overbought` | rsi14 > 70 | Binary | 0 or 1 |
| `macd_bullish` | macd_histogram > 0 | Binary | 0 or 1 |
| `adx_trending` | adx14 > 25 | Binary | 0 or 1 |
| `squeeze_on` | bb_width < keltner_width | Binary | 0 or 1 |
| `returns_1h` | (close - close[-1]) / close[-1] | Pct | -100 to +∞ |
| `returns_24h` | (close - close[-24]) / close[-24] | Pct | -100 to +∞ |
| `volatility_20` | std(closes[-20:]) / mean(closes[-20:]) | Ratio | 0 to +∞ |

### 3.2 Multi-Timeframe Indicators - ~15 Features

Capture context from higher timeframes at the 1h entry point.

#### From 15m Timeframe

| Indicator | Description | Purpose |
|-----------|-------------|---------|
| `rsi14_15m` | RSI on 15m candles | Short-term momentum |
| `volume_spike_15m` | Volume vs 20-period avg | Entry confirmation |
| `macd_histogram_15m` | MACD histogram | Momentum direction |

#### From 4h Timeframe

| Indicator | Description | Purpose |
|-----------|-------------|---------|
| `rsi14_4h` | RSI on 4h candles | Medium-term exhaustion |
| `trend_4h` | 1 if uptrend, -1 if downtrend | Trend context |
| `above_sma20_4h` | Price above 4h SMA20 | Support/resistance |
| `adx14_4h` | ADX on 4h | Trend strength |

#### From 1d Timeframe

| Indicator | Description | Purpose |
|-----------|-------------|---------|
| `rsi14_1d` | RSI on daily candles | Long-term sentiment |
| `trend_1d` | 1 if uptrend, -1 if downtrend | Major trend |
| `distance_from_ath_pct` | % below all-time high | Market phase |
| `above_sma200_1d` | Price above 200 SMA | Bull/bear regime |

### 3.3 Timing Features - ~5 Features

| Feature | Type | Values | Purpose |
|---------|------|--------|---------|
| `hour_of_day` | int | 0-23 | Session timing |
| `day_of_week` | int | 0-6 (Mon=0) | Weekend effects |
| `is_weekend` | binary | 0/1 | Lower liquidity flag |
| `is_us_market_hours` | binary | 0/1 | 14:00-21:00 UTC |
| `regime` | string | "bull"/"bear"/"sideways" | Market regime |

**Regime Classification Logic**:
```python
if close > sma20 > sma50:
    regime = "bull"
elif close < sma20 < sma50:
    regime = "bear"
else:
    regime = "sideways"
```

### 3.4 Cross-Asset Features - ~10 Features

| Feature | Calculation | Purpose |
|---------|-------------|---------|
| `btc_correlation_20` | corr(asset_returns, btc_returns, 20) | Systemic risk |
| `btc_beta` | cov(asset, btc) / var(btc) | Sensitivity to BTC |
| `eth_correlation_20` | corr(asset_returns, eth_returns, 20) | Alt correlation |
| `sol_correlation_20` | corr(asset_returns, sol_returns, 20) | Ecosystem ties |
| `relative_strength_btc` | asset_pct_change - btc_pct_change | Outperformance |
| `relative_strength_eth` | asset_pct_change - eth_pct_change | Outperformance |
| `market_breadth` | % of top 20 assets above SMA20 | Broad market |
| `avg_correlation` | Mean pairwise correlation | Risk-on/off |
| `sector_momentum` | Sector index change | Sector rotation |
| `dominance_btc` | BTC market cap % | Risk appetite |

### 3.5 Sentiment Features - ~4 Features

| Feature | Source | Update Freq | Range |
|---------|--------|-------------|-------|
| `fear_greed` | alternative.me | Daily | 0-100 |
| `funding_rate` | Binance Futures | 8h | -0.1% to +0.1% |
| `funding_rate_velocity` | 24h change in funding | 8h | Float |
| `sentiment_score` | News sentiment (future) | Hourly | -1 to +1 |

### 3.6 Order Book Features - ~6 Features (Live Only)

| Feature | Calculation | Purpose |
|---------|-------------|---------|
| `bid_ask_spread_pct` | (ask - bid) / mid * 100 | Liquidity |
| `bid_depth_1pct` | Sum of bids within 1% | Buy pressure |
| `ask_depth_1pct` | Sum of asks within 1% | Sell pressure |
| `order_imbalance` | (bid - ask) / total | Directional bias |
| `depth_ratio` | bid_depth / ask_depth | Support/resistance |
| `microprice` | bid*ask_size + ask*bid_size / total | Fair value |

---

## 4. Trade Record Schema

### 4.1 Complete Trade Record (ml_trades table)

Every trade captured must include ALL of these fields:

```sql
CREATE TABLE ml_trades (
    -- === IDENTIFIERS ===
    trade_id TEXT PRIMARY KEY,           -- Unique trade ID
    pattern_id TEXT NOT NULL,            -- Which pattern generated this trade
    asset TEXT NOT NULL,                 -- Trading pair (e.g., "ETH")
    base_unit TEXT DEFAULT 'USD',        -- Denomination: 'USD', 'BTC', 'SOL'

    -- === TIMESTAMPS ===
    entry_timestamp INTEGER NOT NULL,    -- Unix timestamp of entry
    exit_timestamp INTEGER NOT NULL,     -- Unix timestamp of exit
    mfe_timestamp INTEGER,               -- When max profit occurred
    mae_timestamp INTEGER,               -- When max drawdown occurred

    -- === PRICES (Multi-Denominated) ===
    entry_price_usd REAL NOT NULL,       -- Entry price in USD
    exit_price_usd REAL NOT NULL,        -- Exit price in USD
    entry_btc_price REAL,                -- BTC/USD at entry
    entry_sol_price REAL,                -- SOL/USD at entry
    exit_btc_price REAL,                 -- BTC/USD at exit
    exit_sol_price REAL,                 -- SOL/USD at exit

    -- === P&L (All Denominations) ===
    pnl_usd_pct REAL NOT NULL,           -- Profit/loss in USD terms
    pnl_btc_pct REAL,                    -- Did we outperform BTC?
    pnl_sol_pct REAL,                    -- Did we outperform SOL?

    -- === EXCURSIONS ===
    mfe_pct REAL,                        -- Max Favorable Excursion (best profit)
    mae_pct REAL,                        -- Max Adverse Excursion (worst drawdown)
    exit_efficiency REAL,                -- pnl / mfe (how much we captured)
    mfe_bars_from_entry INTEGER,         -- Bars until MFE
    mae_bars_from_entry INTEGER,         -- Bars until MAE

    -- === FEATURES (JSON Blobs) ===
    entry_features TEXT NOT NULL,        -- ~100 features at entry (JSON)
    mfe_features TEXT,                   -- Features at MFE point (JSON)
    mae_features TEXT,                   -- Features at MAE point (JSON)
    exit_features TEXT,                  -- Features at exit (JSON)
    cross_asset_features TEXT,           -- Cross-asset correlations (JSON)

    -- === EXIT METADATA ===
    exit_reason TEXT,                    -- 'stop_loss', 'take_profit', 'timeout', 'signal'
    duration_bars INTEGER,               -- Trade duration in bars

    -- === COSTS ===
    slippage_pct REAL,                   -- Estimated slippage
    fee_pct REAL,                        -- Trading fees
    spread_pct REAL,                     -- Bid-ask spread
    gross_pnl_pct REAL,                  -- P&L before costs

    -- === INDEXING ===
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX idx_ml_trades_pattern ON ml_trades(pattern_id);
CREATE INDEX idx_ml_trades_asset ON ml_trades(asset);
CREATE INDEX idx_ml_trades_timestamp ON ml_trades(entry_timestamp);
CREATE INDEX idx_ml_trades_pnl ON ml_trades(pnl_usd_pct);
CREATE INDEX idx_ml_trades_exit_reason ON ml_trades(exit_reason);
```

### 4.2 Feature JSON Structure

The `entry_features` JSON blob should contain:

```json
{
  // Technical 1h (~50 features)
  "rsi14": 32.5,
  "rsi7": 28.1,
  "macd_line": -0.0012,
  "macd_signal": -0.0008,
  "macd_histogram": -0.0004,
  "adx14": 28.3,
  "bb_position": 0.15,
  "bb_width": 0.042,
  "atr14": 0.0125,
  "volume_ratio": 1.35,
  // ... all 50 technical indicators

  // Multi-timeframe (~15 features)
  "rsi14_15m": 35.2,
  "rsi14_4h": 42.1,
  "rsi14_1d": 55.3,
  "trend_4h": 1,
  "trend_1d": 1,
  "above_sma20_4h": 1,
  "distance_from_ath_pct": 25.4,
  // ... all MTF features

  // Timing (~5 features)
  "hour_of_day": 14,
  "day_of_week": 2,
  "is_weekend": 0,
  "is_us_market_hours": 1,
  "regime_bull": 1,
  "regime_bear": 0,

  // Cross-asset (~10 features)
  "btc_correlation_20": 0.85,
  "btc_beta": 1.2,
  "eth_correlation_20": 0.78,
  "relative_strength_btc": -2.5,
  "market_breadth": 0.65,
  // ... all cross-asset features

  // Sentiment (~4 features, when available)
  "fear_greed": 35,
  "funding_rate": 0.0001,
  "sentiment_score": null  // null if not available
}
```

### 4.3 MFE/MAE Feature Capture

At the point of Maximum Favorable Excursion (best profit) and Maximum Adverse Excursion (worst drawdown), capture the same feature set. This enables the model to learn:

- **MFE features**: "What did the market look like at the optimal exit point?"
- **MAE features**: "What warning signs preceded the max drawdown?"

---

## 5. Data Quality Requirements

### 5.1 Completeness

| Requirement | Threshold | Action if Failed |
|-------------|-----------|------------------|
| No missing OHLCV data | 0 gaps | Backfill from alternate source |
| Indicator calculation success | >99% | Log failures, use NaN |
| Cross-asset price availability | 100% for BTC/SOL | Critical - block trade |
| Feature JSON completeness | >95% fields present | Log incomplete records |

### 5.2 Value Ranges & Validation

| Feature | Valid Range | Handling Invalid |
|---------|-------------|------------------|
| RSI | 0-100 | Clamp to range |
| ADX | 0-100 | Clamp to range |
| Prices | >0 | Reject record |
| Volume | >=0 | Reject if negative |
| Percentages | -100 to +∞ | Allow but flag outliers |
| Timestamps | Unix seconds | Reject if 0 or future |

### 5.3 NaN/Infinity Handling

```python
# Replace infinities with NaN
df = df.replace([np.inf, -np.inf], np.nan)

# For ML features, use neutral defaults
NEUTRAL_DEFAULTS = {
    'rsi14': 50.0,
    'adx14': 20.0,
    'bb_position': 0.5,
    'volume_ratio': 1.0,
    'fear_greed': 50,
}

# Fill NaN with defaults
for col, default in NEUTRAL_DEFAULTS.items():
    if col in df.columns:
        df[col] = df[col].fillna(default)
```

### 5.4 Timestamp Alignment

All features at a given timestamp must be from data available AT or BEFORE that timestamp. No lookahead bias.

```python
def get_candles_before(candles: List[dict], timestamp: int, count: int) -> List[dict]:
    """Get candles STRICTLY BEFORE timestamp (no lookahead)."""
    return [c for c in candles if c['timestamp'] < timestamp][-count:]
```

---

## 6. Collection Priorities

### Phase 1: Foundation (Week 1-2)

| Task | Priority | Owner | Status |
|------|----------|-------|--------|
| Verify OHLCV completeness for BTC/ETH/SOL | P0 | Data Team | |
| Verify 1h/4h/1d timeframes available | P0 | Data Team | |
| Test indicator calculation pipeline | P0 | Data Team | |
| Create ml_trades table schema | P0 | Data Team | |

### Phase 2: Core Collection (Week 3-4)

| Task | Priority | Owner | Status |
|------|----------|-------|--------|
| Backtest 500 patterns → generate 50K trades | P1 | Data Team | |
| Capture entry features for all trades | P1 | Data Team | |
| Capture MFE/MAE features | P1 | Data Team | |
| Add cross-asset BTC/SOL prices | P1 | Data Team | |

### Phase 3: Enrichment (Week 5-6)

| Task | Priority | Owner | Status |
|------|----------|-------|--------|
| Add multi-timeframe features | P2 | Data Team | |
| Add cross-asset correlation features | P2 | Data Team | |
| Historical fear/greed index backfill | P2 | Data Team | |
| Historical funding rate backfill | P2 | Data Team | |

### Phase 4: Scale (Week 7+)

| Task | Priority | Owner | Status |
|------|----------|-------|--------|
| Scale to 1000+ patterns → 100K trades | P3 | Data Team | |
| Add 15m timeframe features | P3 | Data Team | |
| Live order book capture setup | P4 | Data Team | |
| Real-time sentiment pipeline | P4 | Data Team | |

---

## 7. Existing Infrastructure

### 7.1 Already Built (Use These!)

| Component | File | Description |
|-----------|------|-------------|
| **Indicator Calculation** | `calculate_indicators.py` | 130+ indicators via pandas_ta |
| **Backtest Engine** | `local_backtest.py` | Full simulation with costs |
| **Fitness Scoring** | `fitness_calculator.py` | V2 signed risk formula |
| **Data Models** | `models.py` | SQLModel schemas |
| **OHLCV Backfill** | `backfill_ohlcv.py` | Multi-API data fetch |
| **Batch Runner** | `batch_backtest_patterns.py` | Parallel pattern testing |

### 7.2 Key Functions to Use

```python
# Load candles
from load_candles import load_candles, load_cross_asset_metrics

# Calculate indicators
from calculate_indicators import calculate_indicators, extract_indicators

# Run backtest
from local_backtest import run_simulation, calculate_metrics

# Fitness scoring
from fitness_calculator import calculate_fitness_v2
```

### 7.3 Database Location

- **Main DB**: `local-utilities/coinswarm_unified.db`
- **OHLCV DB**: `local-utilities/coinswarm_ohlcv.sqlite`
- **Enriched Candles**: `enriched_candles` table (219 columns)

---

## 8. Gap Analysis

### 8.1 What's Missing

| Gap | Impact | Solution |
|-----|--------|----------|
| **MFE/MAE capture** | Can't train exit models | Add to backtest engine |
| **Multi-denom P&L** | No BTC-relative performance | Add BTC/SOL price capture |
| **ml_trades table** | No ML-ready schema | Create new table |
| **Feature export** | Can't feed to ML | Build parquet exporter |

### 8.2 What's Partial

| Component | Current State | Needed |
|-----------|---------------|--------|
| **Sentiment** | Schema exists, no data | Historical backfill |
| **Funding rates** | Referenced but not fetched | API integration |
| **15m candles** | Code exists, not tested | Validation |
| **Order book** | Recorder exists, incomplete | Full implementation |

### 8.3 What's Complete

| Component | Status | Notes |
|-----------|--------|-------|
| OHLCV backfill | ✅ | 3+ years available |
| 1h/4h/1d timeframes | ✅ | All major assets |
| Technical indicators | ✅ | 130+ via pandas_ta |
| Backtest engine | ✅ | Full feature capture |
| Fitness calculation | ✅ | V2 formula |
| Pattern matching | ✅ | Supports all operators |

---

## Appendix A: Trading Cost Model

Realistic costs by liquidity tier:

| Tier | Assets | Slippage | Spread | Fees | Total Round-Trip |
|------|--------|----------|--------|------|------------------|
| 1 | BTC, ETH | 0.02% | 0.01% | 0.10% | 0.26% |
| 2 | SOL, BNB, XRP | 0.03% | 0.02% | 0.10% | 0.36% |
| 3 | DOT, LINK, ADA | 0.05% | 0.05% | 0.10% | 0.50% |
| 4 | Small caps | 0.15% | 0.15% | 0.10% | 0.90% |

---

## Appendix B: Canonical Test Periods

For regime testing, use these predefined periods:

| Period Name | Start | End | Type |
|-------------|-------|-----|------|
| COVID Crash | 2020-02-20 | 2020-03-23 | Crash |
| Post-COVID Recovery | 2020-03-24 | 2020-07-01 | Recovery |
| 2020-2021 Bull | 2020-10-01 | 2021-04-14 | Bull |
| May 2021 Crash | 2021-05-12 | 2021-05-23 | Crash |
| Summer 2021 Range | 2021-05-24 | 2021-07-20 | Sideways |
| Nov 2021 Blow-off | 2021-10-01 | 2021-11-10 | Bull |
| 2022 Bear | 2022-01-01 | 2022-06-18 | Bear |
| Luna Crash | 2022-05-05 | 2022-05-12 | Crash |
| FTX Crash | 2022-11-06 | 2022-11-14 | Crash |
| 2023 Recovery | 2023-01-01 | 2023-07-01 | Recovery |
| ETF Rally | 2024-01-01 | 2024-03-15 | Bull |

---

## Appendix C: Data Volume Targets

| ML Approach | Min Trades | Patterns Needed | Estimated Time |
|-------------|-----------|-----------------|----------------|
| XGBoost baseline | 50,000 | ~500 | 2-3 days |
| Feature importance | 100,000 | ~1,000 | 1 week |
| Neural models | 500,000+ | ~5,000+ | 2-4 weeks |

---

## Contact

For questions about this specification, contact the ML/Data team lead.

**Document Version History**:
- v1.0 (2024-12-24): Initial specification
