# Research: Crypto Liquidation, Cointegration & VWAP

Research compiled: 2025-12-27

## Table of Contents
1. [Liquidation Heat Maps](#liquidation-heat-maps)
2. [CoinGlass API](#coinglass-api)
3. [CoinAnk Tools](#coinank-tools)
4. [Cointegration for Pairs Trading](#cointegration-for-pairs-trading)
5. [VWAP Trading](#vwap-trading)
6. [Integration with Coinswarm](#integration-with-coinswarm)

---

## Liquidation Heat Maps

### Overview

Liquidation heatmaps visualize price levels where leveraged traders face forced position closures. They estimate where large-scale liquidation events may occur, revealing key zones where long or short positions may be wiped out.

**Market Context (2025):**
- Bitcoin futures open interest: ~$94.12 billion (Oct 2025)
- Perpetual futures: ~75-80% of total crypto exchange volume
- Largest single-day wipeout: $2.0 billion across 391,000 traders (Nov 21, 2025)

### Calculation Methodology

#### Data Sources
- Real-time perpetual futures data from Binance, Bybit, OKX
- Open Interest (OI) changes correlated with price action
- Hyperliquid (decentralized, ~16% global OI share) provides transparent position data

#### Algorithm Logic
```
1. Monitor Open Interest changes with each candle
2. Bullish candle + increasing OI → Long positions opened
3. Bearish candle + increasing OI → Short positions opened
4. Estimate liquidation prices based on leverage distribution
5. Aggregate into heat map visualization
```

#### Liquidation Price Formula
For a position with leverage L:
```
Long Liquidation Price = Entry Price × (1 - 1/L + Maintenance Margin)
Short Liquidation Price = Entry Price × (1 + 1/L - Maintenance Margin)
```

Example at 10x leverage with 0.5% maintenance margin:
- Entry: $100,000
- Long liquidation: ~$90,500 (9.5% down)
- Short liquidation: ~$109,500 (9.5% up)

### Visualization Interpretation

| Color | Meaning |
|-------|---------|
| Yellow/Red (bright) | High liquidation density - magnet zones |
| Green/Blue | Medium density |
| Purple/Black | Minimal activity |

**Liquidation Walls:**
- Below spot price: Long liquidation zones
- Above spot price: Short liquidation zones
- Step heights = cumulative liquidation volume

### Trading Strategies

**Magnet Effect:** Price tends to move toward high-liquidity clusters because:
- Market makers target these zones
- Algorithms push prices to trigger stop-losses
- Cascading liquidations create momentum

**Strategy Applications:**
1. **Scalping:** Buy below liquidation pools, sell above clusters
2. **Day Trading:** Trade breakouts/rejections at major clusters
3. **Swing Trading:** Use clusters as confluence with S/R levels
4. **Stop Placement:** Avoid placing stops at obvious liquidation clusters

---

## CoinGlass API

### Overview
CoinGlass aggregates derivatives data across major exchanges with 100+ API endpoints.

**Coverage:**
- 1.5 billion+ API calls per month
- 6+ years historical data
- 1000+ institutional clients

### Authentication
```bash
curl --request GET \
  --url 'https://open-api.coinglass.com/api/futures/supported-coins' \
  --header 'CG-API-KEY: YOUR_API_KEY'
```

### Data Categories

| Category | Endpoints |
|----------|-----------|
| Derivatives | Funding rates, open interest, liquidations, long/short ratios |
| Market Data | Spot volumes, options, real-time prices |
| Historical | 6+ years for backtesting |
| On-Chain | Exchange balances, wallet flows |
| Indicators | MACD, RSI, volatility, ETF flows |

### Key Endpoints (Expected)
```
GET /api/futures/supported-coins
GET /api/futures/liquidation/history
GET /api/futures/openInterest/history
GET /api/futures/fundingRate/history
GET /api/futures/longShort/ratio
```

### Pricing
- Documentation: https://docs.coinglass.com/
- Pricing page: https://www.coinglass.com/pricing
- Free tier available with rate limits

---

## CoinAnk Tools

### Available Analytics

**Liquidation Analytics:**
- Liquidation Data & Funding Rate tracking
- Liquidation Heatmap visualization
- Liquidation Map (geographic/exchange-based)

**Funding Rate Instruments:**
- Current funding rates across exchanges
- Funding Rate Heatmap
- Accumulated Funding Rate historical data

**Position Tracking:**
- Long vs short ratio analysis
- Population ratio metrics (traders holding positions)
- Top trader positions (Binance, Huobi, OKX)

**Order Book Data:**
- Open interest contract analysis
- Order book visualization

### API Access
- OpenAPI available (referenced as "openApi")
- Data export/download functionality
- Real-time 24-hour metrics

---

## Cointegration for Pairs Trading

### Concept vs Correlation

| Correlation | Cointegration |
|-------------|---------------|
| Short-term relationship between returns | Long-term relationship between prices |
| Can break down over time | More stable, mean-reverting |
| Measures direction similarity | Measures equilibrium deviation |

**Key Insight:** Two assets can be uncorrelated but cointegrated, or correlated but not cointegrated.

### Engle-Granger Test

#### Three-Step Process
1. Test order of integration (both series must be I(1))
2. Run regression: `x_t = a_0 + a_1 × y_t + e_t`
3. Test residuals for stationarity (ADF test)

If residuals are stationary → series are cointegrated.

#### Python Implementation
```python
from arbitragelab.cointegration_approach.engle_granger import EngleGrangerPortfolio
import pandas as pd

# Load price data
data = pd.read_csv('crypto_prices.csv', index_col=0, parse_dates=[0])

# Fit cointegration model
portfolio = EngleGrangerPortfolio()
portfolio.fit(data)

# Results
adf_statistics = portfolio.adf_statistics        # Stationarity test stats
cointegration_vectors = portfolio.cointegration_vectors
hedge_ratios = portfolio.hedge_ratios            # For position sizing
```

#### Spread Formula (Crypto)
For coin pair i with BTC as base:
```
Spread_t = BTC_t - β × Coin_t
```
Where β is the hedge ratio from regression.

### Johansen Test

#### Advantages over Engle-Granger
- Works with multiple assets (>2)
- Order-independent
- Finds multiple cointegrating relationships

#### Formula
```
ΔY(t) = Λ × Y(t-1) + M + A₁ × ΔY(t-1) + ... + Aₖ × ΔY(t-k) + ε_t
```
Rank of Λ determines number of mean-reverting portfolios possible.

#### Python Implementation
```python
from arbitragelab.cointegration_approach.johansen import JohansenPortfolio

portfolio = JohansenPortfolio()
portfolio.fit(data)

eigenvalue_statistics = portfolio.johansen_trace_statistic
trace_statistics = portfolio.johansen_eigen_statistic
cointegration_vectors = portfolio.cointegration_vectors
hedge_ratios = portfolio.hedge_ratios
```

### Trading Signal Generation

#### Half-Life of Mean Reversion
```
Half-life = -log(2) / λ
```
Where λ is the mean-reversion coefficient from Ornstein-Uhlenbeck process.

- Use half-life to set lookback windows
- λ > 0 → non-mean-reverting (avoid)
- λ ≈ 0 → slow reversion (unprofitable)
- Optimal: half-life of 1-50 days

#### Entry/Exit Rules
```
Spread = Current_Spread - Mean_Spread
Z-Score = Spread / Std_Dev

Entry Long:  Z-Score < -1.0  (spread unusually low)
Entry Short: Z-Score > +1.0  (spread unusually high)
Exit:        Z-Score crosses 0
Stop-Loss:   Z-Score > 5 or < -5, or 5% drawdown
```

### Crypto Pairs Trading Performance

Research findings (arXiv:2109.10662):
- Dynamic cointegration outperformed buy-and-hold on Bitmex
- Using multiple coins in spread improved risk-adjusted returns
- Best pairs: high-correlation altcoins vs BTC/ETH
- Minute-level signals during formation, hourly execution

---

## VWAP Trading

### Formula

```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

**Cumulative calculation** (builds throughout session):
```
VWAP_t = (VWAP_{t-1} × Cumulative_Volume_{t-1} + Price_t × Volume_t) / Cumulative_Volume_t
```

### Example Calculation
| Price | Volume | Price × Volume |
|-------|--------|----------------|
| $105 | 1 | $105 |
| $108 | 2 | $216 |
| $110 | 3 | $330 |
| $112 | 2 | $224 |

VWAP = ($105 + $216 + $330 + $224) / (1 + 2 + 3 + 2) = $109.29

Note: Simple average = $108.75, but VWAP is higher because more volume traded at higher prices.

### Key Properties

| Property | Description |
|----------|-------------|
| Cumulative | Builds over time, not rolling window |
| Volume-weighted | Larger trades have more impact |
| Inertia | Resistant to random oscillations |
| Consistent | Same value regardless of chart timeframe |

### Standard Deviation Bands

```
Upper Band = VWAP + (n × Standard Deviation)
Lower Band = VWAP - (n × Standard Deviation)
```

Typical bands: ±1σ, ±2σ, ±3σ

**Interpretation:**
- Price at +2σ: Unusually high, potential mean reversion
- Price at -2σ: Unusually low, potential bounce
- Creates objective "grid system" for trading zones

### Trading Applications

**Institutional Benchmarking:**
- Execution at/below VWAP = good fill
- Execution above VWAP = poor fill

**Trend Identification:**
- Price above VWAP: Bullish intraday bias
- Price below VWAP: Bearish intraday bias

**Anchored VWAP:**
- Anchor to specific events (earnings, gaps, highs/lows)
- Creates dynamic support/resistance levels

**Debunked Myth:** VWAP is NOT always a "magnet." In trending markets, price can stay persistently above or below VWAP.

---

## Integration with Coinswarm (Local Python Utilities)

### Pattern Data Classes

#### Liquidation-Based Patterns
```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class LiquidationPattern:
    """Pattern based on liquidation cluster proximity."""
    pattern_type: str = 'LIQUIDATION_CLUSTER'
    distance_to_cluster_pct: float = 0.0   # % distance to nearest cluster
    cluster_intensity: float = 0.0          # 0-1 normalized
    position_type: Literal['long', 'short'] = 'long'
    entry_strategy: Literal['fade', 'breakout'] = 'fade'
```

#### Cointegration-Based Patterns
```python
@dataclass
class CointegrationPattern:
    """Pairs trading pattern using cointegration."""
    pattern_type: str = 'PAIR_SPREAD'
    base_asset: str = 'BTC'
    quote_asset: str = 'ETH'
    hedge_ratio: float = 1.0
    z_score_entry: float = 2.0
    z_score_exit: float = 0.0
    half_life_hours: float = 24.0
```

#### VWAP-Based Patterns
```python
@dataclass
class VWAPPattern:
    """Pattern based on VWAP deviation."""
    pattern_type: str = 'VWAP_DEVIATION'
    anchor_type: Literal['session', 'event', 'high', 'low'] = 'session'
    std_dev_entry: float = 2.0    # e.g., 2.0 for mean reversion
    direction: Literal['long', 'short'] = 'long'
    use_as_stop: bool = False
```

### CoinGlass API Client

```python
import requests
from typing import Optional
from dataclasses import dataclass

@dataclass
class DerivativesData:
    """Cached derivatives data from CoinGlass."""
    open_interest: float
    funding_rate: float
    long_short_ratio: float
    liquidation_levels: list[dict]
    last_updated: int

class CoinGlassClient:
    """Client for CoinGlass API."""

    BASE_URL = "https://open-api.coinglass.com/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"CG-API-KEY": api_key}

    def get_liquidation_data(self, symbol: str = "BTC") -> dict:
        """Fetch liquidation levels for a symbol."""
        resp = requests.get(
            f"{self.BASE_URL}/futures/liquidation/history",
            headers=self.headers,
            params={"symbol": symbol}
        )
        return resp.json()

    def get_funding_rates(self, symbol: str = "BTC") -> dict:
        """Fetch current funding rates across exchanges."""
        resp = requests.get(
            f"{self.BASE_URL}/futures/fundingRate/history",
            headers=self.headers,
            params={"symbol": symbol}
        )
        return resp.json()

    def get_open_interest(self, symbol: str = "BTC") -> dict:
        """Fetch open interest history."""
        resp = requests.get(
            f"{self.BASE_URL}/futures/openInterest/history",
            headers=self.headers,
            params={"symbol": symbol}
        )
        return resp.json()
```

### Cointegration Discovery

```python
import numpy as np
import pandas as pd
from itertools import combinations
from typing import Optional

# Using arbitragelab (pip install arbitragelab)
from arbitragelab.cointegration_approach.engle_granger import EngleGrangerPortfolio
from arbitragelab.cointegration_approach.johansen import JohansenPortfolio

def discover_cointegrated_pairs(
    prices_df: pd.DataFrame,
    p_value_threshold: float = 0.05
) -> list[dict]:
    """
    Discover cointegrated pairs from a DataFrame of asset prices.

    Args:
        prices_df: DataFrame with columns as asset names, rows as timestamps
        p_value_threshold: Maximum p-value to consider cointegrated

    Returns:
        List of cointegrated pairs with hedge ratios and statistics
    """
    assets = prices_df.columns.tolist()
    results = []

    for asset_a, asset_b in combinations(assets, 2):
        pair_data = prices_df[[asset_a, asset_b]].dropna()

        if len(pair_data) < 100:  # Need sufficient data
            continue

        try:
            portfolio = EngleGrangerPortfolio()
            portfolio.fit(pair_data)

            # Check if cointegrated (ADF statistic significant)
            adf_stat = portfolio.adf_statistics
            hedge_ratio = portfolio.hedge_ratios

            # Calculate half-life of mean reversion
            spread = pair_data[asset_a] - hedge_ratio[1] * pair_data[asset_b]
            half_life = calculate_half_life(spread)

            if adf_stat < -2.86:  # 5% critical value (approximate)
                results.append({
                    'base_asset': asset_a,
                    'quote_asset': asset_b,
                    'hedge_ratio': float(hedge_ratio[1]),
                    'adf_statistic': float(adf_stat),
                    'half_life_periods': half_life,
                    'cointegration_vector': hedge_ratio.tolist()
                })
        except Exception as e:
            continue

    return sorted(results, key=lambda x: x['adf_statistic'])


def calculate_half_life(spread: pd.Series) -> float:
    """Calculate half-life of mean reversion using OLS."""
    spread_lag = spread.shift(1).dropna()
    spread_diff = spread.diff().dropna()

    # Align series
    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]

    # OLS: spread_diff = lambda * spread_lag + epsilon
    # half_life = -log(2) / lambda
    if len(spread_lag) < 2:
        return np.inf

    lambda_coef = np.polyfit(spread_lag, spread_diff, 1)[0]

    if lambda_coef >= 0:
        return np.inf  # Not mean-reverting

    return -np.log(2) / lambda_coef


def generate_spread_signals(
    prices_df: pd.DataFrame,
    base_asset: str,
    quote_asset: str,
    hedge_ratio: float,
    lookback: int = 20,
    entry_z: float = 2.0,
    exit_z: float = 0.0
) -> pd.DataFrame:
    """
    Generate trading signals for a cointegrated pair.

    Returns DataFrame with spread, z-score, and signals.
    """
    spread = prices_df[base_asset] - hedge_ratio * prices_df[quote_asset]

    # Rolling z-score
    spread_mean = spread.rolling(lookback).mean()
    spread_std = spread.rolling(lookback).std()
    z_score = (spread - spread_mean) / spread_std

    # Generate signals
    signals = pd.DataFrame(index=prices_df.index)
    signals['spread'] = spread
    signals['z_score'] = z_score
    signals['signal'] = 0

    # Long spread when z < -entry_z, short when z > entry_z
    signals.loc[z_score < -entry_z, 'signal'] = 1   # Long spread
    signals.loc[z_score > entry_z, 'signal'] = -1   # Short spread
    signals.loc[abs(z_score) < exit_z, 'signal'] = 0  # Exit

    return signals
```

### VWAP Calculator

```python
import pandas as pd
import numpy as np
from typing import Optional

def calculate_vwap(
    df: pd.DataFrame,
    price_col: str = 'close',
    volume_col: str = 'volume',
    anchor_idx: Optional[int] = None
) -> pd.Series:
    """
    Calculate cumulative VWAP.

    Args:
        df: DataFrame with price and volume columns
        price_col: Name of price column
        volume_col: Name of volume column
        anchor_idx: Optional starting index for anchored VWAP

    Returns:
        Series of VWAP values
    """
    if anchor_idx is not None:
        df = df.iloc[anchor_idx:].copy()

    typical_price = df[price_col]  # Can also use (H+L+C)/3
    cumulative_tp_vol = (typical_price * df[volume_col]).cumsum()
    cumulative_vol = df[volume_col].cumsum()

    vwap = cumulative_tp_vol / cumulative_vol
    return vwap


def calculate_vwap_bands(
    df: pd.DataFrame,
    price_col: str = 'close',
    volume_col: str = 'volume',
    num_std: list[float] = [1.0, 2.0, 3.0]
) -> pd.DataFrame:
    """
    Calculate VWAP with standard deviation bands.

    Returns DataFrame with VWAP and bands.
    """
    vwap = calculate_vwap(df, price_col, volume_col)

    # Calculate cumulative standard deviation
    typical_price = df[price_col]
    cumulative_vol = df[volume_col].cumsum()

    # Variance = E[X^2] - E[X]^2 (volume-weighted)
    cumulative_tp2_vol = ((typical_price ** 2) * df[volume_col]).cumsum()
    variance = (cumulative_tp2_vol / cumulative_vol) - (vwap ** 2)
    std_dev = np.sqrt(variance.clip(lower=0))

    result = pd.DataFrame(index=df.index)
    result['vwap'] = vwap
    result['std_dev'] = std_dev

    for n in num_std:
        result[f'upper_{n}'] = vwap + n * std_dev
        result[f'lower_{n}'] = vwap - n * std_dev

    return result


def vwap_signals(
    df: pd.DataFrame,
    entry_std: float = 2.0,
    exit_std: float = 0.5
) -> pd.DataFrame:
    """
    Generate mean-reversion signals based on VWAP deviation.
    """
    bands = calculate_vwap_bands(df)

    signals = pd.DataFrame(index=df.index)
    signals['price'] = df['close']
    signals['vwap'] = bands['vwap']
    signals['z_score'] = (df['close'] - bands['vwap']) / bands['std_dev']
    signals['signal'] = 0

    # Mean reversion: long when below lower band, short when above upper
    signals.loc[signals['z_score'] < -entry_std, 'signal'] = 1   # Long
    signals.loc[signals['z_score'] > entry_std, 'signal'] = -1   # Short
    signals.loc[abs(signals['z_score']) < exit_std, 'signal'] = 0  # Exit

    return signals
```

### Fitness Metrics Extensions

| Metric | Weight | Description |
|--------|--------|-------------|
| liq_cluster_accuracy | 15% | Correctly predicted price reaching cluster |
| spread_reversion_rate | 20% | % of cointegrated trades that mean-reverted |
| vwap_band_respect | 10% | % of VWAP band touches that reversed |
| combined_signal_alpha | 25% | Alpha when multiple signals align |

### Dependencies (requirements.txt additions)
```
arbitragelab>=1.0.0
requests>=2.28.0
pandas>=2.0.0
numpy>=1.24.0
statsmodels>=0.14.0
```

---

## Sources

### Liquidation Heat Maps
- [CoinGlass Liquidation Heatmap](https://www.coinglass.com/pro/futures/LiquidationHeatMap)
- [CoinAnk Liquidation Heatmap](https://coinank.com/chart/derivatives/liq-heat-map)
- [Glassnode - Pressure Points: Liquidation Heatmaps](https://insights.glassnode.com/liquidation-heatmaps/)
- [Quadcode - Bitcoin Liquidation Heatmap Trading Guide](https://quadcode.com/blog/bitcoin-liquidation-heatmap-and-how-to-use-it-for-profitable-trading)

### APIs
- [CoinGlass API](https://www.coinglass.com/CryptoApi) - 100+ endpoints, 6 years history
- [CoinAnk Tools](https://coinank.com/tool) - Derivatives analytics suite

### Cointegration
- [Hudson & Thames - Introduction to Cointegration](https://hudsonthames.org/an-introduction-to-cointegration/)
- [ArbitrageLab Cointegration Tests Documentation](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/cointegration_approach/cointegration_tests.html)
- [arXiv:2109.10662 - Dynamic Cointegration Pairs Trading in Crypto](https://arxiv.org/abs/2109.10662)
- [Copula-based Cointegrated Crypto Pairs Trading](https://link.springer.com/article/10.1186/s40854-024-00702-7)

### VWAP
- [TheVWAP - Complete VWAP Guide](https://thevwap.com/vwap/)
