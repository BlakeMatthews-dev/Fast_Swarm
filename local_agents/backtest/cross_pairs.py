"""
Cross-Pair Synthesizer and Multi-Asset Data Handler.

Synthesizes cross-pair candles (ETH/BTC, SOL/BTC, SOL/ETH) from USD pairs
for historical backfill. Marks synthetic vs real exchange data.

Strategy: Trio Rotation Arbitrage
- Always hold one of BTC/ETH/SOL
- Rotate based on which is relatively cheapest
- Goal: Accumulate more BTC over time
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class DataSource(Enum):
    """Source of candle data."""

    EXCHANGE = "exchange"  # Real exchange data (actual traded prices)
    SYNTHETIC = "synthetic"  # Calculated from USD pairs (backfill only)


# The sacred trio - assets we accumulate forever
TRIO_ASSETS = {"BTC", "ETH", "SOL"}

# All possible pairs within the trio
TRIO_USD_PAIRS = {"BTC-USD", "ETH-USD", "SOL-USD"}
TRIO_CROSS_PAIRS = {
    "ETH/BTC": ("ETH-USD", "BTC-USD"),  # ETH priced in BTC
    "SOL/BTC": ("SOL-USD", "BTC-USD"),  # SOL priced in BTC
    "SOL/ETH": ("SOL-USD", "ETH-USD"),  # SOL priced in ETH
}


@dataclass
class CrossPairCandle:
    """A single candle for a cross pair."""

    timestamp: int
    pair: str  # e.g., 'ETH/BTC'
    open: float
    high: float
    low: float
    close: float
    volume: float  # Volume in base asset terms
    source: DataSource  # EXCHANGE or SYNTHETIC

    # For synthetic candles, track component quality
    base_usd_volume: float | None = None  # Volume in base-USD pair
    quote_usd_volume: float | None = None  # Volume in quote-USD pair


def synthesize_cross_pair_candle(
    base_candle: dict,  # e.g., ETH-USD candle
    quote_candle: dict,  # e.g., BTC-USD candle
    pair_name: str,  # e.g., 'ETH/BTC'
) -> CrossPairCandle:
    """
    Synthesize a cross-pair candle from two USD candles.

    For ETH/BTC:
    - base = ETH-USD
    - quote = BTC-USD
    - ETH/BTC price = ETH-USD / BTC-USD

    Note: This is an approximation. Real exchange cross-pairs have:
    - Their own order books with spreads
    - Different liquidity characteristics
    - Arbitrage keeping them close but not identical

    Use synthetic data ONLY for historical backfill where real data unavailable.
    """
    # Calculate OHLC by dividing base by quote
    synth_open = base_candle["open"] / quote_candle["open"]
    synth_close = base_candle["close"] / quote_candle["close"]

    # High/Low are tricky - can't just divide highs and lows
    # Approximate: use the range of close-to-close ratios
    # More accurate: would need tick data
    ratio_at_open = base_candle["open"] / quote_candle["open"]
    ratio_at_close = base_candle["close"] / quote_candle["close"]

    # Estimate high/low from the range
    synth_high = max(ratio_at_open, ratio_at_close) * (1 + 0.001)  # Small buffer
    synth_low = min(ratio_at_open, ratio_at_close) * (1 - 0.001)

    # Volume: use base asset volume (e.g., ETH volume for ETH/BTC)
    synth_volume = base_candle.get("volume", 0)

    return CrossPairCandle(
        timestamp=base_candle["timestamp"],
        pair=pair_name,
        open=synth_open,
        high=synth_high,
        low=synth_low,
        close=synth_close,
        volume=synth_volume,
        source=DataSource.SYNTHETIC,
        base_usd_volume=base_candle.get("volume"),
        quote_usd_volume=quote_candle.get("volume"),
    )


def synthesize_cross_pairs_df(
    btc_usd_df: pd.DataFrame,
    eth_usd_df: pd.DataFrame,
    sol_usd_df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Synthesize all trio cross-pair DataFrames from USD pair DataFrames.

    Args:
        btc_usd_df: BTC-USD candles with columns [timestamp, open, high, low, close, volume]
        eth_usd_df: ETH-USD candles
        sol_usd_df: SOL-USD candles

    Returns:
        Dict of {pair_name: DataFrame} for ETH/BTC, SOL/BTC, SOL/ETH
    """
    # Align all DataFrames by timestamp
    btc = btc_usd_df.set_index("timestamp")
    eth = eth_usd_df.set_index("timestamp")
    sol = sol_usd_df.set_index("timestamp")

    # Find common timestamps
    common_idx = btc.index.intersection(eth.index).intersection(sol.index)

    btc = btc.loc[common_idx]
    eth = eth.loc[common_idx]
    sol = sol.loc[common_idx]

    result = {}

    # ETH/BTC = ETH-USD / BTC-USD
    eth_btc = pd.DataFrame(
        {
            "timestamp": common_idx,
            "open": eth["open"] / btc["open"],
            "high": eth["high"] / btc["low"],  # Max ratio when ETH high, BTC low
            "low": eth["low"] / btc["high"],  # Min ratio when ETH low, BTC high
            "close": eth["close"] / btc["close"],
            "volume": eth["volume"],  # Volume in ETH
            "source": "synthetic",
        }
    ).reset_index(drop=True)
    result["ETH/BTC"] = eth_btc

    # SOL/BTC = SOL-USD / BTC-USD
    sol_btc = pd.DataFrame(
        {
            "timestamp": common_idx,
            "open": sol["open"] / btc["open"],
            "high": sol["high"] / btc["low"],
            "low": sol["low"] / btc["high"],
            "close": sol["close"] / btc["close"],
            "volume": sol["volume"],  # Volume in SOL
            "source": "synthetic",
        }
    ).reset_index(drop=True)
    result["SOL/BTC"] = sol_btc

    # SOL/ETH = SOL-USD / ETH-USD
    sol_eth = pd.DataFrame(
        {
            "timestamp": common_idx,
            "open": sol["open"] / eth["open"],
            "high": sol["high"] / eth["low"],
            "low": sol["low"] / eth["high"],
            "close": sol["close"] / eth["close"],
            "volume": sol["volume"],  # Volume in SOL
            "source": "synthetic",
        }
    ).reset_index(drop=True)
    result["SOL/ETH"] = sol_eth

    return result


class TrioDataBundle:
    """
    Bundle of all 6 pairs for the sacred trio at a single timestamp.

    Enables agents to see the full picture and make rotation decisions.
    """

    def __init__(
        self,
        timestamp: int,
        btc_usd: dict,
        eth_usd: dict,
        sol_usd: dict,
        eth_btc: dict,
        sol_btc: dict,
        sol_eth: dict,
    ):
        self.timestamp = timestamp

        # USD pairs
        self.btc_usd = btc_usd
        self.eth_usd = eth_usd
        self.sol_usd = sol_usd

        # Cross pairs
        self.eth_btc = eth_btc
        self.sol_btc = sol_btc
        self.sol_eth = sol_eth

    def get_pair(self, pair: str) -> dict:
        """Get candle data for a specific pair."""
        pair_map = {
            "BTC-USD": self.btc_usd,
            "BTC/USD": self.btc_usd,
            "BTCUSD": self.btc_usd,
            "ETH-USD": self.eth_usd,
            "ETH/USD": self.eth_usd,
            "ETHUSD": self.eth_usd,
            "SOL-USD": self.sol_usd,
            "SOL/USD": self.sol_usd,
            "SOLUSD": self.sol_usd,
            "ETH/BTC": self.eth_btc,
            "ETH-BTC": self.eth_btc,
            "ETHBTC": self.eth_btc,
            "SOL/BTC": self.sol_btc,
            "SOL-BTC": self.sol_btc,
            "SOLBTC": self.sol_btc,
            "SOL/ETH": self.sol_eth,
            "SOL-ETH": self.sol_eth,
            "SOLETH": self.sol_eth,
        }
        return pair_map.get(pair.upper())

    def get_relative_strength(self) -> dict[str, float]:
        """
        Calculate relative strength of each asset vs the others.

        Returns z-scores of cross-pair prices vs their recent means.
        Positive = asset is relatively expensive
        Negative = asset is relatively cheap (buy opportunity)
        """
        # Simple implementation: compare current close to open
        # More sophisticated: use rolling z-score
        return {
            "ETH_vs_BTC": (self.eth_btc["close"] - self.eth_btc["open"]) / self.eth_btc["open"] * 100,
            "SOL_vs_BTC": (self.sol_btc["close"] - self.sol_btc["open"]) / self.sol_btc["open"] * 100,
            "SOL_vs_ETH": (self.sol_eth["close"] - self.sol_eth["open"]) / self.sol_eth["open"] * 100,
        }

    def suggest_rotation(self, current_holding: str) -> tuple[str, str, float] | None:
        """
        Suggest a rotation trade if one asset is significantly cheaper.

        Args:
            current_holding: What asset you currently hold ('BTC', 'ETH', 'SOL')

        Returns:
            Tuple of (sell_asset, buy_asset, strength) or None if no rotation suggested
        """
        rs = self.get_relative_strength()

        # Thresholds for suggesting rotation (in %)
        ROTATION_THRESHOLD = -2.0  # Asset must be 2%+ cheaper to rotate

        suggestions = []

        if current_holding == "BTC":
            if rs["ETH_vs_BTC"] < ROTATION_THRESHOLD:
                suggestions.append(("BTC", "ETH", abs(rs["ETH_vs_BTC"])))
            if rs["SOL_vs_BTC"] < ROTATION_THRESHOLD:
                suggestions.append(("BTC", "SOL", abs(rs["SOL_vs_BTC"])))

        elif current_holding == "ETH":
            if rs["ETH_vs_BTC"] > -ROTATION_THRESHOLD:  # ETH expensive vs BTC
                suggestions.append(("ETH", "BTC", abs(rs["ETH_vs_BTC"])))
            if rs["SOL_vs_ETH"] < ROTATION_THRESHOLD:
                suggestions.append(("ETH", "SOL", abs(rs["SOL_vs_ETH"])))

        elif current_holding == "SOL":
            if rs["SOL_vs_BTC"] > -ROTATION_THRESHOLD:  # SOL expensive vs BTC
                suggestions.append(("SOL", "BTC", abs(rs["SOL_vs_BTC"])))
            if rs["SOL_vs_ETH"] > -ROTATION_THRESHOLD:  # SOL expensive vs ETH
                suggestions.append(("SOL", "ETH", abs(rs["SOL_vs_ETH"])))

        if suggestions:
            # Return strongest suggestion
            return max(suggestions, key=lambda x: x[2])
        return None


def merge_real_and_synthetic(
    real_df: pd.DataFrame | None,
    synthetic_df: pd.DataFrame,
    pair_name: str,
) -> pd.DataFrame:
    """
    Merge real exchange data with synthetic backfill.

    Real data takes priority where available.
    Synthetic only fills gaps in historical data.

    Args:
        real_df: DataFrame from actual exchange (may be None or partial)
        synthetic_df: DataFrame calculated from USD pairs
        pair_name: Name of the pair (for logging)

    Returns:
        Merged DataFrame with 'source' column indicating origin
    """
    if real_df is None or len(real_df) == 0:
        # No real data - use all synthetic
        synthetic_df["source"] = "synthetic"
        return synthetic_df

    # Ensure both have timestamp index
    real = real_df.copy()
    synth = synthetic_df.copy()

    if "source" not in real.columns:
        real["source"] = "exchange"
    if "source" not in synth.columns:
        synth["source"] = "synthetic"

    # Find timestamps only in synthetic (gaps in real data)
    real_timestamps = set(real["timestamp"])
    synth_only = synth[~synth["timestamp"].isin(real_timestamps)]

    # Combine: real data + synthetic gap fill
    merged = pd.concat([real, synth_only], ignore_index=True)
    merged = merged.sort_values("timestamp").reset_index(drop=True)

    # Log merge stats
    n_real = len(real)
    n_synth = len(synth_only)
    print(f"[{pair_name}] Merged: {n_real} real + {n_synth} synthetic = {len(merged)} total")

    return merged


class TrioDataLoader:
    """
    Load trio data (BTC, ETH, SOL) from PostgreSQL and synthesize cross-pairs.

    Loads USD pairs from enhanced_candles and synthesizes:
    - ETH/BTC = ETH-USD / BTC-USD
    - SOL/BTC = SOL-USD / BTC-USD
    - SOL/ETH = SOL-USD / ETH-USD

    Returns TrioDataBundle objects for backtesting.
    """

    def __init__(self, timeframe: str = "1h"):
        """
        Initialize the loader.

        Args:
            timeframe: Candle timeframe ("1h", "15m", "1d", etc.)
        """
        self.timeframe = timeframe
        self._btc_df: pd.DataFrame | None = None
        self._eth_df: pd.DataFrame | None = None
        self._sol_df: pd.DataFrame | None = None
        self._cross_pairs: dict[str, pd.DataFrame] | None = None

    def load(
        self,
        limit: int | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list["TrioDataBundle"]:
        """
        Load trio data and return list of TrioDataBundle objects.

        Args:
            limit: Max candles to load per asset
            start_ts: Start timestamp in ms
            end_ts: End timestamp in ms

        Returns:
            List of TrioDataBundle, one per timestamp, sorted chronologically
        """
        import asyncio

        from Fast_Swarm.local_agents.backtest.data import AsyncOHLCVLoader

        async def _load_all():
            loader = AsyncOHLCVLoader()

            # Load all 3 USD pairs in parallel
            btc_task = loader.load_candles(
                asset="BTC", timeframe=self.timeframe, start_ts=start_ts, end_ts=end_ts, limit=limit
            )
            eth_task = loader.load_candles(
                asset="ETH", timeframe=self.timeframe, start_ts=start_ts, end_ts=end_ts, limit=limit
            )
            sol_task = loader.load_candles(
                asset="SOL", timeframe=self.timeframe, start_ts=start_ts, end_ts=end_ts, limit=limit
            )

            return await asyncio.gather(btc_task, eth_task, sol_task)

        # Run async loading
        try:
            loop = asyncio.get_running_loop()
            # Inside async context - need nest_asyncio
            import nest_asyncio

            nest_asyncio.apply()
            btc_df, eth_df, sol_df = loop.run_until_complete(_load_all())
        except RuntimeError:
            # No running loop
            btc_df, eth_df, sol_df = asyncio.run(_load_all())

        if btc_df.empty or eth_df.empty or sol_df.empty:
            print(f"[TrioLoader] Warning: Missing data - BTC:{len(btc_df)}, ETH:{len(eth_df)}, SOL:{len(sol_df)}")
            return []

        # Store for reference
        self._btc_df = btc_df
        self._eth_df = eth_df
        self._sol_df = sol_df

        # Synthesize cross pairs
        self._cross_pairs = synthesize_cross_pairs_df(btc_df, eth_df, sol_df)

        # Build bundles - one per timestamp
        return self._build_bundles()

    def _build_bundles(self) -> list["TrioDataBundle"]:
        """Build TrioDataBundle objects from loaded DataFrames."""
        if self._btc_df is None or self._cross_pairs is None:
            return []

        # Get common timestamps across all USD pairs
        btc_ts = set(self._btc_df["timestamp"])
        eth_ts = set(self._eth_df["timestamp"])
        sol_ts = set(self._sol_df["timestamp"])
        common_ts = btc_ts & eth_ts & sol_ts

        if not common_ts:
            print("[TrioLoader] No common timestamps across USD pairs")
            return []

        # Index DataFrames by timestamp for fast lookup
        btc_by_ts = self._btc_df.set_index("timestamp").to_dict("index")
        eth_by_ts = self._eth_df.set_index("timestamp").to_dict("index")
        sol_by_ts = self._sol_df.set_index("timestamp").to_dict("index")

        # Index cross-pair DataFrames
        eth_btc_by_ts = self._cross_pairs["ETH/BTC"].set_index("timestamp").to_dict("index")
        sol_btc_by_ts = self._cross_pairs["SOL/BTC"].set_index("timestamp").to_dict("index")
        sol_eth_by_ts = self._cross_pairs["SOL/ETH"].set_index("timestamp").to_dict("index")

        bundles = []
        for ts in sorted(common_ts):
            # Skip if cross-pair data missing for this timestamp
            if ts not in eth_btc_by_ts or ts not in sol_btc_by_ts or ts not in sol_eth_by_ts:
                continue

            bundle = TrioDataBundle(
                timestamp=int(ts),
                btc_usd=self._to_candle_dict(btc_by_ts[ts], "BTC-USD"),
                eth_usd=self._to_candle_dict(eth_by_ts[ts], "ETH-USD"),
                sol_usd=self._to_candle_dict(sol_by_ts[ts], "SOL-USD"),
                eth_btc=self._to_candle_dict(eth_btc_by_ts[ts], "ETH/BTC"),
                sol_btc=self._to_candle_dict(sol_btc_by_ts[ts], "SOL/BTC"),
                sol_eth=self._to_candle_dict(sol_eth_by_ts[ts], "SOL/ETH"),
            )
            bundles.append(bundle)

        print(f"[TrioLoader] Built {len(bundles)} bundles from {len(common_ts)} common timestamps")
        return bundles

    def _to_candle_dict(self, row: dict, pair: str) -> dict:
        """Convert DataFrame row to candle dictionary."""
        # Extract OHLCV + indicators
        candle = {
            "pair": pair,
            "open": float(row.get("open", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
            "source": row.get("source", "exchange"),
        }

        # Add any indicators present
        indicator_keys = [
            "rsi_14",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "bb_upper",
            "bb_lower",
            "bb_middle",
            "bb_width",
            "bb_pct",
            "atr_14",
            "atr_7",
            "adx_14",
            "plus_di",
            "minus_di",
            "stoch_k",
            "stoch_d",
            "ema_9",
            "ema_21",
            "sma_20",
            "sma_50",
            "obv",
            "mfi_14",
            "cmf_20",
            "fear_greed_value",
        ]
        for key in indicator_keys:
            if key in row and row[key] is not None:
                try:
                    val = float(row[key])
                    if not (np.isnan(val) or np.isinf(val)):
                        candle[key] = val
                except (ValueError, TypeError):
                    pass

        return candle

    def get_stats(self) -> dict:
        """Get statistics about loaded data."""
        if self._btc_df is None:
            return {"status": "not_loaded"}

        return {
            "timeframe": self.timeframe,
            "btc_candles": len(self._btc_df),
            "eth_candles": len(self._eth_df),
            "sol_candles": len(self._sol_df),
            "cross_pairs": list(self._cross_pairs.keys()) if self._cross_pairs else [],
            "eth_btc_candles": len(self._cross_pairs.get("ETH/BTC", [])) if self._cross_pairs else 0,
            "sol_btc_candles": len(self._cross_pairs.get("SOL/BTC", [])) if self._cross_pairs else 0,
            "sol_eth_candles": len(self._cross_pairs.get("SOL/ETH", [])) if self._cross_pairs else 0,
        }
