"""
OHLCV Data Loader for Local Backtesting.

Loads candle data from PostgreSQL enhanced_candles table (5.2M+ rows).
All indicators are pre-computed in the database.

Uses SYNC database connection to avoid async/event loop conflicts.
"""

import math
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import create_engine, func, text
from sqlmodel import select


# === Global Enrichment Locks ===
# Prevents concurrent enrichment of the same symbol/timeframe
# When one thread enriches, others wait then get already-enriched data from DB
_enrichment_locks: dict[tuple[str, str], threading.Lock] = {}
_enrichment_locks_lock = threading.Lock()  # Lock for accessing the dict

# === Global Progress Tracker ===
# Updated when enrichment makes progress - orchestrator checks this to extend timeouts
_enrichment_last_progress: float = 0.0  # time.time() when last progress was made
_enrichment_progress_lock = threading.Lock()


def get_enrichment_last_progress() -> float:
    """Get timestamp of last enrichment progress (for orchestrator timeout reset)."""
    return _enrichment_last_progress


def _update_enrichment_progress():
    """Update the global progress timestamp (called after each batch persist)."""
    global _enrichment_last_progress
    import time
    with _enrichment_progress_lock:
        _enrichment_last_progress = time.time()


def _get_enrichment_lock(symbol: str, timeframe: str) -> threading.Lock:
    """Get or create a lock for enriching a specific symbol/timeframe."""
    key = (symbol, timeframe)
    with _enrichment_locks_lock:
        if key not in _enrichment_locks:
            _enrichment_locks[key] = threading.Lock()
        return _enrichment_locks[key]

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle
from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import (
    compute_derived_for_candle,
    enrich_candle_dict,
)
from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import calculate_indicators_fast


def _vectorized_enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Vectorized enrichment - compute derived indicators using pandas operations.

    MUCH faster than row-by-row compute_derived_for_candle() calls.
    Computes the same indicators but using vectorized pandas operations.
    """
    close = df["close"].astype(float)

    # MA Cross signals (using ema_21 as proxy for ema_20)
    if "ema_21" in df.columns and "sma_50" in df.columns:
        ema_21 = df["ema_21"].astype(float)
        sma_50 = df["sma_50"].astype(float)
        df["ma_cross_20_50"] = ((ema_21 > sma_50).astype(int) - (ema_21 < sma_50).astype(int))

    if "sma_50" in df.columns and "sma_200" in df.columns:
        sma_50 = df["sma_50"].astype(float)
        sma_200 = df["sma_200"].astype(float)
        df["golden_cross"] = (sma_50 > sma_200).astype(int)
        df["death_cross"] = (sma_50 < sma_200).astype(int)

    # MACD Cross
    if "macd_line" in df.columns and "macd_signal" in df.columns:
        macd_line = df["macd_line"].astype(float)
        macd_signal = df["macd_signal"].astype(float)
        df["macd_cross"] = ((macd_line > macd_signal).astype(int) - (macd_line < macd_signal).astype(int))

    # Price vs MA percentages
    if "ema_9" in df.columns:
        ema_9 = df["ema_9"].astype(float)
        df["price_vs_ema_9_pct"] = ((close - ema_9) / ema_9.replace(0, float("nan"))) * 100
        df["price_above_ema_9"] = (close > ema_9).astype(int)

    if "ema_21" in df.columns:
        ema_21 = df["ema_21"].astype(float)
        df["price_vs_ema_20_pct"] = ((close - ema_21) / ema_21.replace(0, float("nan"))) * 100
        df["price_vs_ema_21_pct"] = df["price_vs_ema_20_pct"]
        df["price_above_ema_20"] = (close > ema_21).astype(int)
        df["price_above_ema_21"] = df["price_above_ema_20"]

    if "sma_50" in df.columns:
        sma_50 = df["sma_50"].astype(float)
        df["price_vs_sma_50_pct"] = ((close - sma_50) / sma_50.replace(0, float("nan"))) * 100
        df["price_above_sma_50"] = (close > sma_50).astype(int)

    if "sma_200" in df.columns:
        sma_200 = df["sma_200"].astype(float)
        df["price_vs_sma_200_pct"] = ((close - sma_200) / sma_200.replace(0, float("nan"))) * 100
        df["price_above_sma_200"] = (close > sma_200).astype(int)

    # RSI conditions
    if "rsi_14" in df.columns:
        rsi_14 = df["rsi_14"].astype(float)
        df["rsi_oversold"] = (rsi_14 < 30).astype(int)
        df["rsi_overbought"] = (rsi_14 > 70).astype(int)
        df["rsi_neutral"] = ((rsi_14 >= 30) & (rsi_14 <= 70)).astype(int)

    # Stochastic conditions
    if "stoch_k" in df.columns:
        stoch_k = df["stoch_k"].astype(float)
        df["stoch_oversold"] = (stoch_k < 20).astype(int)
        df["stoch_overbought"] = (stoch_k > 80).astype(int)

    # Trend strength
    if "adx_14" in df.columns:
        adx_14 = df["adx_14"].astype(float)
        df["strong_trend"] = (adx_14 > 25).astype(int)
        df["weak_trend"] = (adx_14 < 20).astype(int)

    # Volatility regime
    if "natr_14" in df.columns:
        natr_14 = df["natr_14"].astype(float)
        df["volatility_regime"] = "medium"  # Default
        df.loc[natr_14 < 2, "volatility_regime"] = "low"
        df.loc[natr_14 >= 5, "volatility_regime"] = "high"

    # Trend regime
    if all(c in df.columns for c in ["adx_14", "plus_di", "minus_di"]):
        adx_14 = df["adx_14"].astype(float)
        plus_di = df["plus_di"].astype(float)
        minus_di = df["minus_di"].astype(float)
        df["trend_regime"] = "sideways"  # Default
        df.loc[(adx_14 > 20) & (plus_di > minus_di), "trend_regime"] = "uptrend"
        df.loc[(adx_14 > 20) & (minus_di > plus_di), "trend_regime"] = "downtrend"

    # Bollinger conditions
    if "bb_upper" in df.columns and "bb_lower" in df.columns:
        bb_upper = df["bb_upper"].astype(float)
        bb_lower = df["bb_lower"].astype(float)
        df["price_at_bb_upper"] = (close >= bb_upper * 0.98).astype(int)
        df["price_at_bb_lower"] = (close <= bb_lower * 1.02).astype(int)

    if "bb_width" in df.columns:
        bb_width = df["bb_width"].astype(float)
        df["bb_squeeze"] = (bb_width < bb_width.rolling(20, min_periods=1).mean() * 0.5).astype(int)

    # Volume conditions
    if "volume" in df.columns and "volume_sma_20" in df.columns:
        volume = df["volume"].astype(float)
        volume_sma_20 = df["volume_sma_20"].astype(float)
        df["high_volume"] = (volume > volume_sma_20 * 1.5).astype(int)
        df["low_volume"] = (volume < volume_sma_20 * 0.5).astype(int)

    # === Day of Week indicators (from timestamp) ===
    # Try to get datetime from 'time' or 'timestamp' column
    dt_series = None
    if "time" in df.columns:
        dt_series = pd.to_datetime(df["time"], errors="coerce", utc=True)
    elif "timestamp" in df.columns:
        # timestamp is in milliseconds
        dt_series = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce", utc=True)

    if dt_series is not None and not dt_series.isna().all():
        # Day of week (0=Monday, 6=Sunday)
        dow = dt_series.dt.dayofweek

        df["isMonday"] = (dow == 0).astype(int)
        df["isTuesday"] = (dow == 1).astype(int)
        df["isWednesday"] = (dow == 2).astype(int)
        df["isThursday"] = (dow == 3).astype(int)
        df["isFriday"] = (dow == 4).astype(int)
        df["isSaturday"] = (dow == 5).astype(int)
        df["isSunday"] = (dow == 6).astype(int)
        df["isWeekend"] = ((dow == 5) | (dow == 6)).astype(int)
        df["isWeekday"] = ((dow >= 0) & (dow <= 4)).astype(int)

        # Hour of day (UTC)
        hour = dt_series.dt.hour

        # Trading sessions (approximate UTC ranges)
        # Asian: 00:00 - 08:00 UTC (Tokyo/Sydney)
        # London: 08:00 - 16:00 UTC
        # New York: 13:00 - 21:00 UTC (overlaps with London 13:00-16:00)
        df["isAsianSession"] = ((hour >= 0) & (hour < 8)).astype(int)
        df["isLondonSession"] = ((hour >= 8) & (hour < 16)).astype(int)
        df["isNYSession"] = ((hour >= 13) & (hour < 21)).astype(int)
        df["isLondonNYOverlap"] = ((hour >= 13) & (hour < 16)).astype(int)

        # Store hour/day for other potential uses
        df["hourOfDay"] = hour
        df["dayOfWeek"] = dow

    return df


# Build sync database URL
def _get_sync_db_url():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "coinswarm")
    password = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
    database = os.getenv("POSTGRES_DB", "coinswarm")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


# Singleton sync engine with connection pooling
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            _get_sync_db_url(),
            pool_size=10,  # Concurrent connections
            max_overflow=20,  # Extra connections under load
            pool_recycle=3600,  # Recycle connections after 1 hour
            pool_pre_ping=True,  # Verify connections are alive
        )
    return _sync_engine


class LazyCandleCache:
    """
    Lazy-loading candle cache that loads data on-demand instead of upfront.

    Implements dict-like interface for compatibility with engine.preloaded_candles.
    Caches loaded data for reuse within the same orchestrator batch.

    Thread-safe: uses locks to prevent concurrent loads of the same key.

    Example:
        cache = LazyCandleCache(windows)
        engine = LocalBacktestEngine(preloaded_candles=cache)
        # Candles loaded only when first accessed
    """

    def __init__(self, windows: list = None, loader: "OHLCVLoader" = None):
        import threading
        self._loader = loader or OHLCVLoader()
        self._cache: dict[str, pd.DataFrame] = {}
        self._ranges: dict[tuple, dict] = {}
        self._lock = threading.Lock()  # Prevents concurrent loads of same key
        self._loading: set[str] = set()  # Track keys currently being loaded

        # Precompute ranges from windows (but don't load data yet)
        if windows:
            for w in windows:
                key = (w.symbol, w.timeframe)
                if key not in self._ranges:
                    self._ranges[key] = {"min_ts": w.start_ts, "max_ts": w.end_ts}
                else:
                    self._ranges[key]["min_ts"] = min(self._ranges[key]["min_ts"], w.start_ts)
                    self._ranges[key]["max_ts"] = max(self._ranges[key]["max_ts"], w.end_ts)

    def __contains__(self, cache_key: str) -> bool:
        """Check if key is loadable (has range info) or already cached."""
        if cache_key in self._cache:
            return True
        # Parse key to check if we have range info
        parts = cache_key.rsplit("_", 1)
        if len(parts) == 2:
            symbol, timeframe = parts
            return (symbol, timeframe) in self._ranges
        return False

    def __getitem__(self, cache_key: str) -> "pd.DataFrame":
        """Load candles on first access, return cached data on subsequent access.

        WARNING: This is SYNC and will block the event loop.
        Use get_async() in async contexts for non-blocking loads.

        Returns a COPY of the cached DataFrame to prevent concurrent modification issues.
        Thread-safe: uses lock to ensure only ONE thread loads data.
        """
        import time

        # Fast path: already cached
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        # Acquire lock to determine if we should load or wait
        i_am_the_loader = False
        with self._lock:
            # Double-check after acquiring lock
            if cache_key in self._cache:
                return self._cache[cache_key].copy()

            # If another thread is loading, we'll wait
            if cache_key in self._loading:
                i_am_the_loader = False
            else:
                # We're the first - mark as loading
                self._loading.add(cache_key)
                i_am_the_loader = True

        # If we're NOT the loader, wait for the loader to finish
        if not i_am_the_loader:
            print(f"  [Lazy] {cache_key}: waiting for another thread to load...")
            wait_start = time.time()
            max_wait_seconds = 120  # 2 minutes timeout
            while cache_key not in self._cache:
                time.sleep(0.1)
                # Check if loader finished (either success or failure)
                if cache_key not in self._loading and cache_key not in self._cache:
                    # Loader finished but failed - we should try loading ourselves
                    print(f"  [Lazy] {cache_key}: previous loader failed, retrying...")
                    break
                # Timeout check
                if time.time() - wait_start > max_wait_seconds:
                    print(f"  [Lazy] {cache_key}: timeout waiting for load, will try ourselves")
                    break
            if cache_key in self._cache:
                return self._cache[cache_key].copy()
            # Fall through to load ourselves if we broke out of wait loop
            # Mark ourselves as the new loader
            with self._lock:
                if cache_key in self._cache:  # Double-check
                    return self._cache[cache_key].copy()
                self._loading.add(cache_key)

        # Parse key and load
        parts = cache_key.rsplit("_", 1)
        if len(parts) != 2:
            with self._lock:
                self._loading.discard(cache_key)
            raise KeyError(f"Invalid cache key: {cache_key}")

        symbol, timeframe = parts
        key = (symbol, timeframe)

        if key not in self._ranges:
            with self._lock:
                self._loading.discard(cache_key)
            raise KeyError(f"No range info for {cache_key}")

        try:
            ts_range = self._ranges[key]
            # Include 200 candles of warmup before window start
            # so indicators are fully cooked at the window's first candle
            WARMUP_CANDLES = 200
            tf_ms = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
            warmup_ms = WARMUP_CANDLES * tf_ms.get(timeframe, 3600000)
            load_start = ts_range["min_ts"] - warmup_ms

            print(f"  [Lazy] Loading {cache_key} (with 200-candle warmup)...")
            df = self._loader.load_candles(
                asset=symbol,
                timeframe=timeframe,
                start_ts=load_start,
                end_ts=ts_range["max_ts"],
                with_indicators=True,
            )
            self._cache[cache_key] = df
            print(f"  [Lazy] Loaded {cache_key}: {len(df)} candles")
        finally:
            with self._lock:
                self._loading.discard(cache_key)

        # Return a copy to prevent concurrent modification
        return df.copy()

    async def get_async(self, cache_key: str, default=None) -> "pd.DataFrame":
        """
        Async version of get() - runs sync DB load in thread pool.

        This allows asyncio.wait_for() timeouts to actually work because
        the blocking DB call runs in a separate thread, not blocking the event loop.

        Returns a COPY of the cached DataFrame to prevent concurrent modification issues.
        """
        import asyncio

        if cache_key in self._cache:
            # Return a copy to prevent concurrent threads from modifying the same object
            return self._cache[cache_key].copy()

        # Parse key
        parts = cache_key.rsplit("_", 1)
        if len(parts) != 2:
            return default

        symbol, timeframe = parts
        key = (symbol, timeframe)

        if key not in self._ranges:
            return default

        ts_range = self._ranges[key]
        print(f"  [Lazy] Loading {cache_key} (async)...")

        # Run sync loader in thread pool - this is the key fix!
        # Now asyncio.wait_for() can actually cancel this if it times out
        df = await asyncio.to_thread(
            self._loader.load_candles,
            asset=symbol,
            timeframe=timeframe,
            start_ts=ts_range["min_ts"],
            end_ts=ts_range["max_ts"],
            with_indicators=True,
        )

        self._cache[cache_key] = df
        print(f"  [Lazy] Loaded {cache_key}: {len(df)} candles")
        # Return a copy to prevent concurrent modification
        return df.copy()

    def get(self, cache_key: str, default=None):
        """Dict-compatible get method (SYNC - blocks event loop)."""
        try:
            return self[cache_key]
        except KeyError:
            return default

    def __len__(self) -> int:
        """Return number of cached (already loaded) entries."""
        return len(self._cache)

    def __bool__(self) -> bool:
        """Return True if cache has range info (can load data), even if empty."""
        return bool(self._ranges)

    def clear(self):
        """Clear the cache to free memory."""
        self._cache.clear()

    def preload_all(self):
        """
        Eagerly load ALL candles for registered windows.

        Call this at the START of a batch to load everything once,
        rather than lazy-loading per-request.
        """
        print(f"  [Cache] Preloading {len(self._ranges)} asset/timeframe pairs...")
        for (symbol, timeframe), ts_range in self._ranges.items():
            cache_key = f"{symbol}_{timeframe}"
            if cache_key not in self._cache:
                df = self._loader.load_candles(
                    asset=symbol,
                    timeframe=timeframe,
                    start_ts=ts_range["min_ts"],
                    end_ts=ts_range["max_ts"],
                    with_indicators=True,
                )
                self._cache[cache_key] = df
                print(f"  Preloaded {cache_key}: {len(df)} candles")
        print(f"  [Cache] Preload complete: {len(self._cache)} pairs loaded")


def preload_candles_for_windows(
    windows: list,
    loader: "OHLCVLoader" = None,
) -> dict:
    """
    Preload candle data for a list of windows.

    Loads each unique (symbol, timeframe) pair once with the full date range
    needed to cover all windows. Returns dict for use with engine.preloaded_candles.

    Args:
        windows: List of Window objects (from backtest.windows module)
        loader: Optional OHLCVLoader instance (creates one if not provided)

    Returns:
        Dict of "{symbol}_{timeframe}" -> DataFrame

    Example:
        from Fast_Swarm.local_agents.backtest.windows import get_windows
        from Fast_Swarm.local_agents.backtest.data import preload_candles_for_windows
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine

        windows = get_windows(count=100)
        preloaded = preload_candles_for_windows(windows)
        engine = LocalBacktestEngine(preloaded_candles=preloaded)

        # Now backtests won't hit DB - data is already loaded
        for agent in agents:
            trades = engine.run(agent, window.to_dataset())
    """
    if loader is None:
        loader = OHLCVLoader()

    # Group windows by (symbol, timeframe) and find min/max timestamps
    ranges = {}
    for w in windows:
        key = (w.symbol, w.timeframe)
        if key not in ranges:
            ranges[key] = {"min_ts": w.start_ts, "max_ts": w.end_ts}
        else:
            ranges[key]["min_ts"] = min(ranges[key]["min_ts"], w.start_ts)
            ranges[key]["max_ts"] = max(ranges[key]["max_ts"], w.end_ts)

    # Load each unique pair once
    preloaded = {}
    for (symbol, timeframe), ts_range in ranges.items():
        cache_key = f"{symbol}_{timeframe}"
        df = loader.load_candles(
            asset=symbol,
            timeframe=timeframe,
            start_ts=ts_range["min_ts"],
            end_ts=ts_range["max_ts"],
            with_indicators=True,
        )
        preloaded[cache_key] = df
        print(f"  Preloaded {cache_key}: {len(df)} candles")

    return preloaded


@dataclass
class Candle:
    """Single OHLCV candle with optional indicators."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    asset: str = ""
    timeframe: str = "1h"
    indicators: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "asset": self.asset,
            "timeframe": self.timeframe,
            **self.indicators,
        }


class OHLCVLoader:
    """
    Load OHLCV data from PostgreSQL enhanced_candles table.

    The enhanced_candles table contains 5.2M+ rows with 60+ pre-computed indicators
    covering 2017-2025 across multiple timeframes (1m, 5m, 15m, 1h, 6h, 1d).

    All data comes from PostgreSQL - no SQLite fallback.
    """

    # Indicator columns available in EnhancedCandle (60+ columns)
    INDICATOR_COLUMNS = [
        # Moving Averages
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_9",
        "ema_12",
        "ema_21",
        "ema_26",
        # RSI
        "rsi_7",
        "rsi_14",
        "rsi_21",
        # MACD
        "macd_line",
        "macd_signal",
        "macd_histogram",
        # Bollinger Bands
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "bb_width",
        "bb_pct",
        # ATR/Volatility
        "atr_7",
        "atr_14",
        "natr_14",
        "true_range",
        # Stochastic
        "stoch_k",
        "stoch_d",
        "stochrsi_k",
        "stochrsi_d",
        # ADX/Trend
        "adx_14",
        "plus_di",
        "minus_di",
        # Volume indicators
        "obv",
        "volume_sma_20",
        "cmf_20",
        "mfi_14",
        # Sentiment/Regime
        "fear_greed_value",
        "fear_greed_class",
        "regime",
        "regime_encoded",
        # Tick aggregates
        "tick_cvd_ratio",
        "tick_trade_imbalance",
        "tick_buy_volume_pct",
        "tick_volatility",
        "tick_momentum",
        # Order book aggregates
        "book_avg_spread_bps",
        "book_avg_imbalance",
        "book_depth_ratio",
        # Cross-asset metrics
        "btc_eth_correlation_14d",
        "eth_btc_ratio",
        "alt_dominance_pct",
    ]

    def __init__(
        self,
        db_path: str | None = None,
        enhanced_db_path: str | None = None,
        use_enhanced: bool = True,
        ohlcv_db: str | None = None,
    ):
        """
        Initialize the loader.

        Note: db_path, enhanced_db_path, ohlcv_db parameters are ignored.
        All data comes from PostgreSQL enhanced_candles table.
        These parameters exist only for backward compatibility.
        """
        # Parameters kept for backward compatibility but ignored
        # All data comes from PostgreSQL
        self._assets_cache: list[str] | None = None

    def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get list of available assets in the database."""
        if self._assets_cache is not None:
            return self._assets_cache

        engine = _get_sync_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT DISTINCT symbol FROM enhanced_candles
                WHERE timeframe = :timeframe
            """),
                {"timeframe": timeframe},
            )
            assets = [row[0] for row in result.fetchall()]

        self._assets_cache = assets
        return assets

    def load_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """
        Load OHLCV candles as a DataFrame from PostgreSQL (SYNC).

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH").
            timeframe: Candle timeframe ("1h", "6h", "1d", "15m", etc.).
            start_ts: Start timestamp (ms).
            end_ts: End timestamp (ms).
            limit: Maximum number of candles.
            with_indicators: Whether to include indicators (always available from DB).

        Returns:
            DataFrame with OHLCV + indicators.
        """
        engine = _get_sync_engine()

        # Build query with parameters
        params = {"symbol": asset, "timeframe": timeframe}
        where_clauses = ["symbol = :symbol", "timeframe = :timeframe"]

        if start_ts is not None:
            start_dt = datetime.fromtimestamp(start_ts / 1000, tz=UTC)
            where_clauses.append("time >= :start_dt")
            params["start_dt"] = start_dt

        if end_ts is not None:
            end_dt = datetime.fromtimestamp(end_ts / 1000, tz=UTC)
            where_clauses.append("time <= :end_dt")
            params["end_dt"] = end_dt

        where_sql = " AND ".join(where_clauses)
        limit_sql = "LIMIT :limit_val" if limit else ""
        if limit:
            params["limit_val"] = limit

        query = text(f"""
            SELECT * FROM enhanced_candles
            WHERE {where_sql}
            ORDER BY time ASC
            {limit_sql}
        """)

        with engine.connect() as conn:
            result = conn.execute(query, params)
            rows = result.fetchall()
            columns = result.keys()

        if not rows:
            # Debug: log why no data found
            print(f"    [Loader] No data for {asset}/{timeframe} ts={start_ts}-{end_ts}")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=columns)

        # Convert time to timestamp in milliseconds for compatibility
        df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)

        # Add asset column for compatibility
        df["asset"] = asset

        # Ensure numeric types for OHLCV
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if not with_indicators:
            # Return only OHLCV columns
            cols = ["timestamp", "asset", "timeframe", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]

        # === ENRICHMENT WITH LOCKING ===
        # If enrichment is needed, acquire lock so only ONE thread enriches.
        # Other threads wait, then reload from DB (now enriched).

        core_base_indicators = ["rsi_14", "atr_14", "adx_14", "macd_line", "sma_50"]
        core_derived_cols = ["rsi_oversold", "ma_cross_20_50", "golden_cross", "strong_trend"]

        # Quick check if enrichment needed - use .any() to catch partial gaps
        # .all() was too permissive - only triggered when ALL rows null
        base_missing = any(
            col not in df.columns or df[col].isna().any()
            for col in core_base_indicators
        )
        derived_missing = any(
            col not in df.columns or df[col].isna().any()
            for col in core_derived_cols
        )

        needs_enrichment = (base_missing or derived_missing) and len(df) >= 200

        if needs_enrichment:
            # Acquire lock for this symbol/timeframe - other threads will wait
            lock = _get_enrichment_lock(asset, timeframe)
            print(f"    [Enrichment] {asset}/{timeframe} needs enrichment - acquiring lock...")

            with lock:
                # Re-check after acquiring lock (another thread may have enriched)
                # Reload from DB to see if data is now enriched
                with engine.connect() as conn2:
                    check_result = conn2.execute(
                        text("""
                            SELECT COUNT(*) as total,
                                   COUNT(rsi_14) as has_rsi,
                                   COUNT(rsi_oversold) as has_derived
                            FROM enhanced_candles
                            WHERE symbol = :symbol AND timeframe = :timeframe
                            LIMIT 1000
                        """),
                        {"symbol": asset, "timeframe": timeframe}
                    )
                    check_row = check_result.fetchone()

                # If another thread already enriched MOST rows, reload and return
                # Require >50% enriched to avoid false positives from partial enrichment
                if check_row and check_row[0] > 0 and check_row[1] > (check_row[0] * 0.5):
                    print(f"    [Enrichment] {asset}/{timeframe} already enriched by another thread - reloading")
                    # Reload the now-enriched data
                    with engine.connect() as conn3:
                        result3 = conn3.execute(query, params)
                        rows3 = result3.fetchall()
                        columns3 = result3.keys()
                    df = pd.DataFrame(rows3, columns=list(columns3))
                    df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)
                    df["asset"] = asset
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    return df

                # We're the first - compute and persist
                print(f"    [Enrichment] {asset}/{timeframe} - computing indicators (other threads waiting)...")

                # 1. Compute BASE indicators
                if base_missing:
                    try:
                        df = calculate_indicators_fast(df, verbose=False)
                        df.columns = [c.lower() for c in df.columns]
                        # NOTE: Do NOT dedup here - the rename below creates
                        # new duplicates (e.g. atrr_14 -> atr_14 when DB already
                        # has atr_14). Dedup must happen AFTER rename.

                        col_renames = {
                            # MACD
                            "macd_12_26_9": "macd_line",
                            "macds_12_26_9": "macd_signal",
                            "macdh_12_26_9": "macd_histogram",
                            # Bollinger Bands
                            "bbl_20_2.0": "bb_lower",
                            "bbm_20_2.0": "bb_middle",
                            "bbu_20_2.0": "bb_upper",
                            "bbb_20_2.0": "bb_width",
                            "bbp_20_2.0": "bb_pct",
                            # Stochastic
                            "stochk_14_3_3": "stoch_k",
                            "stochd_14_3_3": "stoch_d",
                            "stochrsik_14_14_3_3": "stochrsi_k",
                            "stochrsid_14_14_3_3": "stochrsi_d",
                            # ADX/DI
                            "dmp_14": "plus_di",
                            "dmn_14": "minus_di",
                            # ATR
                            "atrr_14": "atr_14",
                            "atrr_7": "atr_7",
                            "natr_14": "natr_14",
                            "truerange_14": "true_range",
                            # Aroon
                            "aroonosc_14": "aroon_osc",
                            "aroonu_14": "aroon_up",
                            "aroond_14": "aroon_down",
                            # Momentum indicators (computed by calculate_indicators_fast)
                            "cci_14": "cci_14",
                            "willr_14": "willr_14",
                            "roc_10": "roc_10",
                            "trix_14": "trix_14",
                            "cmo_14": "cmo_14",
                            "mfi_14": "mfi_14",
                            "cmf_20": "cmf_20",
                            "vhf_28": "vhf_28",
                            "emv_14": "emv_14",
                            # New indicators
                            "tsi_25_13": "tsi",
                            "fishert_9_1": "fisher",
                            "fisherts_9_1": "fisher_signal",
                            "mom_10": "mom_10",
                            "uo_7_14_28": "uo",
                            "dpo_14": "dpo",
                        }
                        df.rename(columns={k: v for k, v in col_renames.items() if k in df.columns}, inplace=True)
                        # NOW dedup - after rename creates duplicates (e.g. DB's atr_14 +
                        # computed atrr_14 renamed to atr_14). Keep LAST = computed values.
                        df = df.loc[:, ~df.columns.duplicated(keep='last')]
                        print(f"    [Enrichment] Computed base indicators for {len(df)} candles")
                    except Exception as e:
                        print(f"    [Enrichment] WARNING: Failed to compute base indicators: {e}")

                # 2. Compute DERIVED indicators
                if derived_missing or base_missing:
                    df = _vectorized_enrich(df)
                    print(f"    [Enrichment] Computed derived indicators")

                # 3. PERSIST to DB so other threads get enriched data
                print(f"    [Enrichment] Persisting to DB...")
                persisted = persist_enriched_candles_sync(df)
                print(f"    [Enrichment] Persisted {persisted} rows - releasing lock")

                df = df.reset_index(drop=True)

        return df

    def iter_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> Iterator[Candle]:
        """
        Iterate over candles one at a time.

        Useful for streaming backtests.
        """
        df = self.load_candles(
            asset=asset,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            with_indicators=True,
        )

        if df.empty:
            return

        # Get indicator columns
        base_cols = {
            "timestamp",
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "asset",
            "symbol",
            "timeframe",
            "exchange",
            "enriched_at",
        }
        indicator_cols = [c for c in df.columns if c not in base_cols]

        for _, row in df.iterrows():
            indicators = {}
            for col in indicator_cols:
                val = row.get(col)
                if val is not None and not pd.isna(val):
                    if isinstance(val, (int, float)):
                        if not (math.isnan(val) or math.isinf(val)):
                            indicators[col] = float(val)
                    else:
                        indicators[col] = val  # Keep strings (like regime)

            yield Candle(
                timestamp=int(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                asset=asset,
                timeframe=timeframe,
                indicators=indicators,
            )

    def get_date_range(self, asset: str, timeframe: str = "1h") -> tuple[int, int]:
        """Get the date range available for an asset."""

        async def _get_range():
            async with async_session_maker() as session:
                statement = (
                    select(func.min(EnhancedCandle.time), func.max(EnhancedCandle.time))
                    .where(EnhancedCandle.symbol == asset)
                    .where(EnhancedCandle.timeframe == timeframe)
                )
                result = await session.exec(statement)
                row = result.one_or_none()
                return row

        row = self._run_async(_get_range())

        if row and row[0] and row[1]:
            min_ts = int(row[0].timestamp() * 1000)
            max_ts = int(row[1].timestamp() * 1000)
            return (min_ts, max_ts)
        return (0, 0)

    def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get the number of candles available for an asset."""

        async def _get_count():
            async with async_session_maker() as session:
                statement = (
                    select(func.count())
                    .select_from(EnhancedCandle)
                    .where(EnhancedCandle.symbol == asset)
                    .where(EnhancedCandle.timeframe == timeframe)
                )
                result = await session.exec(statement)
                return result.one() or 0

        return self._run_async(_get_count())


class AsyncOHLCVLoader:
    """
    Async version of OHLCVLoader for use in async contexts.

    Use this directly in async code to avoid sync wrapper overhead.
    """

    INDICATOR_COLUMNS = OHLCVLoader.INDICATOR_COLUMNS

    async def get_available_assets(self, timeframe: str = "1h") -> list[str]:
        """Get list of available assets in the database."""
        async with async_session_maker() as session:
            statement = select(EnhancedCandle.symbol).where(EnhancedCandle.timeframe == timeframe).distinct()
            result = await session.exec(statement)
            return list(result.all())

    async def load_candles(
        self,
        asset: str,
        timeframe: str = "1h",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """Load OHLCV candles as a DataFrame from PostgreSQL."""
        async with async_session_maker() as session:
            statement = (
                select(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )

            if start_ts is not None:
                start_dt = datetime.fromtimestamp(start_ts / 1000, tz=UTC)
                statement = statement.where(EnhancedCandle.time >= start_dt)

            if end_ts is not None:
                end_dt = datetime.fromtimestamp(end_ts / 1000, tz=UTC)
                statement = statement.where(EnhancedCandle.time <= end_dt)

            statement = statement.order_by(EnhancedCandle.time.asc())

            if limit is not None:
                statement = statement.limit(limit)

            result = await session.exec(statement)
            candles = result.all()

        if not candles:
            return pd.DataFrame()

        # Convert to DataFrame
        data = [candle.model_dump() for candle in candles]
        df = pd.DataFrame(data)

        # Convert time to timestamp in milliseconds
        df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)
        df["asset"] = asset

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if not with_indicators:
            cols = ["timestamp", "asset", "timeframe", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]

        # Check if enrichment is needed
        core_base_indicators = ["rsi_14", "atr_14", "adx_14", "macd_line", "sma_50"]
        core_derived_cols = ["rsi_oversold", "ma_cross_20_50", "golden_cross", "strong_trend"]

        base_missing = any(col not in df.columns or df[col].isna().any() for col in core_base_indicators)
        derived_missing = any(col not in df.columns or df[col].isna().any() for col in core_derived_cols)

        needs_enrichment = (base_missing or derived_missing) and len(df) >= 200

        if needs_enrichment:
            # Delegate to sync loader which has proper locking for enrichment
            # This ensures all enrichment goes through the same lock mechanism
            import asyncio
            print(f"    [AsyncLoader] {asset}/{timeframe} needs enrichment - delegating to sync loader...")
            sync_loader = OHLCVLoader()
            df = await asyncio.to_thread(
                sync_loader.load_candles,
                asset=asset,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                limit=limit,
                with_indicators=True,
            )
            return df

        # Data is already enriched in DB, return as-is
        return df

    async def get_date_range(self, asset: str, timeframe: str = "1h") -> tuple[int, int]:
        """Get the date range available for an asset."""
        async with async_session_maker() as session:
            statement = (
                select(func.min(EnhancedCandle.time), func.max(EnhancedCandle.time))
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )
            result = await session.exec(statement)
            row = result.one_or_none()

        if row and row[0] and row[1]:
            min_ts = int(row[0].timestamp() * 1000)
            max_ts = int(row[1].timestamp() * 1000)
            return (min_ts, max_ts)
        return (0, 0)

    async def get_candle_count(self, asset: str, timeframe: str = "1h") -> int:
        """Get the number of candles available for an asset."""
        async with async_session_maker() as session:
            statement = (
                select(func.count())
                .select_from(EnhancedCandle)
                .where(EnhancedCandle.symbol == asset)
                .where(EnhancedCandle.timeframe == timeframe)
            )
            result = await session.exec(statement)
            return result.one() or 0


FAILED_ENRICHMENT_LOG = "data/failed_enrichments.jsonl"


def _log_failed_enrichment(row_data: dict, error: str):
    """
    Log a failed enrichment to JSONL for later retry.

    Args:
        row_data: Dict with candle data that failed to persist
        error: Error message
    """
    import json
    from pathlib import Path

    log_path = Path(FAILED_ENRICHMENT_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Build a serializable record
    record = {
        "time": str(row_data.get("time")),
        "exchange": row_data.get("exchange"),
        "symbol": row_data.get("symbol"),
        "timeframe": row_data.get("timeframe"),
        "error": error,
        "logged_at": datetime.now(UTC).isoformat(),
    }

    # Add derived values that were computed
    derived_cols = [
        "ma_cross_20_50", "golden_cross", "death_cross", "macd_cross",
        "price_vs_ema_9_pct", "price_vs_ema_20_pct", "price_vs_ema_21_pct",
        "price_vs_sma_50_pct", "price_vs_sma_200_pct",
        "price_above_ema_9", "price_above_ema_20", "price_above_ema_21",
        "price_above_sma_50", "price_above_sma_200",
        "rsi_oversold", "rsi_overbought", "rsi_neutral",
        "stoch_oversold", "stoch_overbought",
        "strong_trend", "weak_trend",
        "volatility_regime", "trend_regime",
        "is_asian_session", "is_london_session", "is_us_session", "is_us_market_hours",
        "price_at_bb_upper", "price_at_bb_lower", "bb_squeeze",
        "high_volume", "low_volume",
    ]

    derived = {}
    for col in derived_cols:
        val = row_data.get(col)
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            derived[col] = val
    record["derived"] = derived

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def persist_enriched_candles_sync(
    df: pd.DataFrame,
    batch_size: int = 50,  # Small batches = frequent commits = progress saved even if interrupted
) -> int:
    """
    Persist computed derived indicators back to the database (SYNC version).

    Call this after loading and enriching candles to save the computed
    values so they don't need to be recomputed on future loads.

    Failed persists are logged to data/failed_enrichments.jsonl for later retry.

    Args:
        df: DataFrame with candle data including derived indicators
        batch_size: Number of rows to update per transaction

    Returns:
        Number of rows updated
    """
    # Check required columns
    required = ["time", "exchange", "symbol", "timeframe"]
    if not all(col in df.columns for col in required):
        return 0

    # Only update rows that were computed in-memory (not from DB)
    if "derived_computed_at" not in df.columns:
        return 0

    unenriched_mask = df["derived_computed_at"].isna()
    rows_to_update = df[unenriched_mask]

    if rows_to_update.empty:
        return 0

    # BASE indicator columns (from calculate_indicators_fast)
    base_cols = [
        "sma_20", "sma_50", "sma_200",
        "ema_9", "ema_12", "ema_21", "ema_26",
        "rsi_7", "rsi_14", "rsi_21",
        "macd_line", "macd_signal", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower", "bb_bandwidth", "bb_percent",
        "atr_7", "atr_14", "natr_14", "true_range",
        "stoch_k", "stoch_d", "stochrsi_k", "stochrsi_d",
        "adx_14", "plus_di", "minus_di",
        "obv", "volume_sma_20", "cmf_20", "mfi_14",
        "aroon_up", "aroon_down", "aroon_osc",
        "cci_14", "willr_14", "roc_10",
        "emv", "emv_14",
        # VHF and motion derivatives (critical for chaos-generated patterns)
        "vhf_28",
        "close_velocity", "close_acceleration", "close_jerk",
        "close_velocity_zscore", "close_acceleration_zscore", "close_jerk_zscore",
    ]

    # DERIVED indicator columns (from _vectorized_enrich)
    derived_cols = [
        "ma_cross_20_50", "golden_cross", "death_cross", "macd_cross",
        "price_vs_ema_9_pct", "price_vs_ema_20_pct", "price_vs_ema_21_pct",
        "price_vs_sma_50_pct", "price_vs_sma_200_pct",
        "price_above_ema_9", "price_above_ema_20", "price_above_ema_21",
        "price_above_sma_50", "price_above_sma_200",
        "rsi_oversold", "rsi_overbought", "rsi_neutral",
        "stoch_oversold", "stoch_overbought",
        "strong_trend", "weak_trend",
        "volatility_regime", "trend_regime",
        "price_at_bb_upper", "price_at_bb_lower", "bb_squeeze",
        "high_volume", "low_volume",
        # Session/day columns - DataFrame uses camelCase, mapped to DB snake_case below
        "isAsianSession", "isLondonSession", "isNYSession",
        "isWeekend", "hourOfDay", "dayOfWeek",
    ]

    # Map DataFrame column names (camelCase) to DB column names (snake_case)
    col_name_map = {
        "isAsianSession": "is_asian_session",
        "isLondonSession": "is_london_session",
        "isNYSession": "is_us_session",  # DB uses is_us_session
        "isWeekend": "is_weekend",
        "hourOfDay": "hour_of_day",
        "dayOfWeek": "day_of_week",
    }

    # Combine all columns to persist
    all_cols = base_cols + derived_cols

    # Filter to columns that exist in the DataFrame
    available_cols = [c for c in all_cols if c in df.columns]
    if not available_cols:
        return 0

    global _sync_engine
    engine = _get_sync_engine()

    # Filter to columns that actually exist in the DB table (avoid UndefinedColumn errors)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'enhanced_candles'"
            ))
            db_columns = {row[0] for row in result}
            before_count = len(available_cols)
            available_cols = [c for c in available_cols if col_name_map.get(c, c) in db_columns]
            if len(available_cols) < before_count:
                print(f"    [Enrichment] Filtered {before_count - len(available_cols)} columns not in DB schema")
    except Exception as e:
        print(f"    [Enrichment] Warning: Could not check DB schema: {e}")
    updated = 0
    failed = 0
    total_rows = len(rows_to_update)

    # Get symbol/timeframe for logging
    symbol = df["symbol"].iloc[0] if "symbol" in df.columns and len(df) > 0 else "?"
    timeframe = df["timeframe"].iloc[0] if "timeframe" in df.columns and len(df) > 0 else "?"
    print(f"    [Enrichment] {symbol}/{timeframe}: Persisting {total_rows} rows...")

    # Time range of rows to update (for finding affected chunks)
    min_time = rows_to_update["time"].min()
    max_time = rows_to_update["time"].max()

    # === STEP 1: Decompress affected chunks ===
    # TimescaleDB compressed chunks don't support per-row UPDATEs.
    # We decompress first, update, then recompress.
    decompressed_chunks = []
    try:
        with engine.begin() as conn:
            # Find compressed chunks covering our time range
            try:
                chunk_result = conn.execute(text("""
                    SELECT chunk_schema || '.' || chunk_name as chunk_id,
                           is_compressed, range_start, range_end
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = 'enhanced_candles'
                      AND is_compressed = true
                      AND range_start <= :max_time
                      AND range_end >= :min_time
                """), {"min_time": min_time, "max_time": max_time})
                compressed_chunks = chunk_result.fetchall()

                if compressed_chunks:
                    print(f"    [Enrichment] Found {len(compressed_chunks)} compressed chunks to decompress")
                    for chunk in compressed_chunks:
                        chunk_id = chunk[0]
                        try:
                            conn.execute(text(
                                f"SELECT decompress_chunk('{chunk_id}'::regclass)"
                            ))
                            decompressed_chunks.append(chunk_id)
                        except Exception as e:
                            print(f"    [Enrichment] Failed to decompress {chunk_id}: {e}")
                    if decompressed_chunks:
                        print(f"    [Enrichment] Decompressed {len(decompressed_chunks)} chunks")
                else:
                    print(f"    [Enrichment] No compressed chunks in time range (all uncompressed)")

            except Exception as e:
                print(f"    [Enrichment] Chunk query failed (not TimescaleDB?): {e}")
                # Continue anyway - updates may still work on uncompressed chunks
    except Exception as e:
        print(f"    [Enrichment] Decompression connection failed: {e}")

    # === STEP 2: Batch UPDATE on now-uncompressed data ===
    report_interval = batch_size
    last_reported = 0

    try:
        for start_idx in range(0, total_rows, batch_size):
            batch = rows_to_update.iloc[start_idx : start_idx + batch_size]
            batch_num = start_idx // batch_size + 1

            try:
                with engine.begin() as conn:
                    for _, row in batch.iterrows():
                        try:
                            set_parts = []
                            params = {
                                "time_val": row["time"],
                                "exchange": row["exchange"],
                                "symbol": row["symbol"],
                                "timeframe": row["timeframe"],
                            }

                            for col in available_cols:
                                val = row.get(col)
                                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                    # Cast numpy scalars to Python natives for psycopg2
                                    if hasattr(val, 'item'):
                                        val = val.item()
                                    db_col = col_name_map.get(col, col)
                                    param_name = f"val_{db_col}"
                                    set_parts.append(f"{db_col} = :{param_name}")
                                    params[param_name] = val

                            if set_parts:
                                set_parts.append("derived_computed_at = NOW()")
                                set_clause = ", ".join(set_parts)

                                update_sql = text(f"""
                                    UPDATE enhanced_candles
                                    SET {set_clause}
                                    WHERE time = :time_val
                                      AND exchange = :exchange
                                      AND symbol = :symbol
                                      AND timeframe = :timeframe
                                      AND derived_computed_at IS NULL
                                """)

                                result = conn.execute(update_sql, params)
                                updated += result.rowcount

                        except Exception as row_err:
                            failed += 1
                            if failed <= 3:
                                print(f"    [Enrichment] Row persist error: {type(row_err).__name__}: {row_err}")

                # Report progress
                rows_processed = start_idx + len(batch)
                _update_enrichment_progress()
                if rows_processed - last_reported >= report_interval or rows_processed >= total_rows:
                    print(f"    [Enrichment] {symbol}/{timeframe}: {rows_processed}/{total_rows} ({updated} updated)")
                    last_reported = rows_processed

                # After first batch, check if decompression helped
                if batch_num == 1 and updated == 0 and failed >= len(batch) * 0.8:
                    print(f"    [Enrichment] Decompression didn't help - aborting persist")
                    failed = total_rows
                    break

            except Exception as batch_error:
                print(f"    [Enrichment] Batch {batch_num} failed: {batch_error}")
                try:
                    engine.dispose()
                    _sync_engine = None
                except Exception:
                    pass
                failed += len(batch)
                break

    except Exception as e:
        print(f"    [Enrichment] Persist failed entirely: {e}")
        try:
            engine.dispose()
            _sync_engine = None
        except Exception:
            pass

    # === STEP 3: Recompress chunks ===
    if decompressed_chunks:
        try:
            with engine.begin() as conn:
                for chunk_id in decompressed_chunks:
                    try:
                        conn.execute(text(
                            f"SELECT compress_chunk('{chunk_id}'::regclass)"
                        ))
                    except Exception as e:
                        print(f"    [Enrichment] Failed to recompress {chunk_id}: {e}")
                print(f"    [Enrichment] Recompressed {len(decompressed_chunks)} chunks")
        except Exception as e:
            print(f"    [Enrichment] Recompression connection failed: {e}")

    if failed > 0:
        print(f"    [Enrichment] {failed} rows failed to persist (compute-on-demand still works)")

    print(f"    [Enrichment] {symbol}/{timeframe}: Done - {updated}/{total_rows} rows persisted")
    return updated
