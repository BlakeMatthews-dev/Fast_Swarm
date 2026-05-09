#!/usr/bin/env python3
"""
OHLCV Backfill Script for PostgreSQL (Fast_Swarm)

Improvements over original:
1. PostgreSQL via psycopg3 (not SQLite)
2. Concurrent downloads with asyncio.Semaphore
3. Batch upserts (1000 rows at once)
4. Targets enhanced_candles table
5. Can be called from server startup

Usage:
    python backfill_ohlcv_pg.py                    # Backfill all trio assets
    python backfill_ohlcv_pg.py --asset BTC        # Single asset
    python backfill_ohlcv_pg.py --all              # ALL assets (60+)
    python backfill_ohlcv_pg.py --timeframe 15m    # Specific timeframe
    python backfill_ohlcv_pg.py --concurrent 5     # 5 parallel downloads
"""

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

# Add project paths
script_dir = Path(__file__).parent
project_root = script_dir.parent
parent_of_project = project_root.parent
sys.path.insert(0, str(parent_of_project))
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / "local-utilities" / ".env")

import psycopg  # psycopg3 (modern)
from psycopg.rows import dict_row

# --- Configuration ---
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "coinswarm"),
    "user": os.getenv("POSTGRES_USER", "coinswarm"),
    "password": os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024"),
}

# API endpoints
BINANCE_BASE = "https://api.binance.us/api/v3/klines"
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

# Rate limits (requests per minute) - CONSERVATIVE
BINANCE_RPM = 15  # Binance.US is stricter than Binance.com
CRYPTOCOMPARE_RPM = 5  # Free tier ~100/day
YAHOO_RPM = 10

# Timeframe mappings
BINANCE_INTERVALS = {"1d": "1d", "4h": "4h", "1h": "1h", "15m": "15m", "5m": "5m", "1m": "1m"}
CRYPTOCOMPARE_ENDPOINTS = {"1d": "histoday", "1h": "histohour", "15m": "histominute"}
YAHOO_INTERVALS = {"1d": "1d", "1h": "1h"}

# Trio assets (highest priority)
TRIO_ASSETS = ["BTC", "ETH", "SOL"]

# All supported assets
ALL_ASSETS = [
    # Tier 1: Major
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    # Tier 2: Large caps
    "ADA",
    "AVAX",
    "DOT",
    "LINK",
    "MATIC",
    # Tier 3: Established
    "UNI",
    "ATOM",
    "NEAR",
    "LTC",
    "BCH",
    # Tier 4: Popular
    "DOGE",
    "FIL",
    "APT",
    "ARB",
    "OP",
    # Tier 5: Additional
    "ETC",
    "XLM",
    "NEO",
    "VET",
    "COMP",
    "HNT",
    "MKR",
    "AAVE",
    "CRV",
    "AXS",
    # Tier 6: Mid caps
    "1INCH",
    "ORCA",
    "RAY",
    "MANA",
    "ALGO",
    "ZEC",
    "ENJ",
    "GRT",
    "SUSHI",
    "SNX",
    "IMX",
    "EOS",
    "RNDR",
    "LDO",
    "FTM",
    "SAND",
    # Tier 7: Newer
    "BONK",
    "DASH",
    "IOTA",
    "XTZ",
    "SUI",
    "PYTH",
    "WIF",
    "JTO",
    "JUP",
    "W",
    "DRIFT",
    "TRX",
    "ENA",
    "SEI",
    "CAKE",
]

# Asset-specific start dates
ASSET_START_DATES = {
    "BTC": datetime(2013, 1, 1, tzinfo=UTC),
    "ETH": datetime(2015, 8, 7, tzinfo=UTC),
    "LTC": datetime(2013, 4, 28, tzinfo=UTC),
    "SOL": datetime(2020, 4, 10, tzinfo=UTC),
    "BNB": datetime(2017, 7, 25, tzinfo=UTC),
    "ADA": datetime(2017, 10, 1, tzinfo=UTC),
    "DOT": datetime(2020, 8, 22, tzinfo=UTC),
    "AVAX": datetime(2020, 9, 21, tzinfo=UTC),
    "LINK": datetime(2017, 9, 21, tzinfo=UTC),
    "ATOM": datetime(2019, 3, 14, tzinfo=UTC),
    "ARB": datetime(2023, 3, 23, tzinfo=UTC),
    "OP": datetime(2022, 6, 1, tzinfo=UTC),
    "JUP": datetime(2024, 1, 31, tzinfo=UTC),
    "DRIFT": datetime(2024, 5, 16, tzinfo=UTC),
    # Add more as needed...
}

# Default start for assets not in the list
DEFAULT_START = datetime(2017, 1, 1, tzinfo=UTC)

# All timeframes to backfill
ALL_TIMEFRAMES = ["1d", "4h", "1h", "15m"]

# Yahoo Finance symbol mappings
YAHOO_SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "LTC": "LTC-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "DOT": "DOT-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "ATOM": "ATOM-USD",
    "BNB": "BNB-USD",
}


@dataclass
class BackfillStats:
    """Track backfill progress."""

    total_assets: int = 0
    completed_assets: int = 0
    current_asset: str = ""
    current_timeframe: str = ""
    current_source: str = ""
    total_inserted: int = 0
    total_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def log_progress(self):
        elapsed = time.time() - self.start_time
        pct = (self.completed_assets / self.total_assets * 100) if self.total_assets else 0
        print(
            f"[{elapsed:.0f}s] {self.current_asset} {self.current_timeframe} via {self.current_source} "
            f"| {self.completed_assets}/{self.total_assets} ({pct:.0f}%) "
            f"| +{self.total_inserted:,} inserted"
        )


STATS = BackfillStats()


class RateLimiter:
    """Token bucket rate limiter with burst support."""

    def __init__(self, rpm: int, name: str, burst: int = 3):
        self.rpm = rpm
        self.name = name
        self.interval = 60.0 / rpm
        self.tokens = burst
        self.max_tokens = burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            # Refill tokens based on time elapsed
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed / self.interval)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) * self.interval
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


# Global rate limiters
RATE_LIMITERS = {
    "binance": RateLimiter(BINANCE_RPM, "binance"),
    "cryptocompare": RateLimiter(CRYPTOCOMPARE_RPM, "cryptocompare"),
    "yahoo": RateLimiter(YAHOO_RPM, "yahoo"),
}


def get_pg_connection():
    """Get a sync PostgreSQL connection."""
    return psycopg.connect(**POSTGRES_CONFIG, row_factory=dict_row)


def get_existing_range(conn, asset: str, timeframe: str) -> tuple[int | None, int | None]:
    """Get min/max timestamps for existing data."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                EXTRACT(EPOCH FROM MIN(time))::bigint * 1000,
                EXTRACT(EPOCH FROM MAX(time))::bigint * 1000
            FROM enhanced_candles
            WHERE symbol = %s AND timeframe = %s
        """,
            (asset, timeframe),
        )
        row = cur.fetchone()
        if row and row["min"] is not None:
            return (row["min"], row["max"])
        return (None, None)


def batch_upsert_candles(conn, candles: list[dict], source: str) -> tuple[int, int]:
    """
    Batch upsert candles using ON CONFLICT DO NOTHING.

    Much faster than one-at-a-time inserts.
    """
    if not candles:
        return 0, 0

    # Prepare batch data
    values = []
    for c in candles:
        ts = datetime.fromtimestamp(c["timestamp"] / 1000, tz=UTC)
        values.append(
            (
                ts,
                c["asset"],
                c["timeframe"],
                "binance",  # exchange
                float(c["open"]),
                float(c["high"]),
                float(c["low"]),
                float(c["close"]),
                float(c["volume"]),
            )
        )

    inserted = 0
    with conn.cursor() as cur:
        # Use executemany with ON CONFLICT DO NOTHING
        cur.executemany(
            """
            INSERT INTO enhanced_candles
                (time, symbol, timeframe, exchange, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, time) DO NOTHING
        """,
            values,
        )
        inserted = cur.rowcount

    conn.commit()
    return inserted, len(candles) - inserted


async def fetch_binance(
    session: aiohttp.ClientSession,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> list[dict]:
    """Fetch candles from Binance US."""
    candles = []
    pair = f"{symbol}USDT"
    interval = BINANCE_INTERVALS.get(timeframe, "1d")
    current = start_ts

    while current < end_ts:
        await RATE_LIMITERS["binance"].acquire()

        params = {
            "symbol": pair,
            "interval": interval,
            "startTime": current,
            "endTime": end_ts,
            "limit": 1000,
        }

        try:
            async with session.get(BINANCE_BASE, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data:
                        break

                    for kline in data:
                        candles.append(
                            {
                                "asset": symbol,
                                "timeframe": timeframe,
                                "timestamp": kline[0],
                                "open": float(kline[1]),
                                "high": float(kline[2]),
                                "low": float(kline[3]),
                                "close": float(kline[4]),
                                "volume": float(kline[5]),
                            }
                        )

                    current = data[-1][0] + 1
                elif resp.status == 429:
                    STATS.errors.append(f"Binance rate limited for {symbol}")
                    await asyncio.sleep(60)
                else:
                    text = await resp.text()
                    STATS.errors.append(f"Binance {resp.status}: {text[:100]}")
                    break
        except Exception as e:
            STATS.errors.append(f"Binance error: {str(e)[:100]}")
            break

    return candles


async def fetch_yahoo(
    session: aiohttp.ClientSession,
    symbol: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
) -> list[dict]:
    """Fetch candles from Yahoo Finance (good for historical data)."""
    yahoo_symbol = YAHOO_SYMBOLS.get(symbol)
    if not yahoo_symbol or timeframe not in YAHOO_INTERVALS:
        return []

    candles = []
    interval = YAHOO_INTERVALS[timeframe]
    url = f"{YAHOO_BASE}/{yahoo_symbol}"

    start_sec = start_ts // 1000
    end_sec = end_ts // 1000

    # Yahoo limits range
    max_range = 3650 * 86400 if timeframe == "1d" else 730 * 86400
    current = start_sec

    headers = {"User-Agent": "Mozilla/5.0"}

    while current < end_sec:
        await RATE_LIMITERS["yahoo"].acquire()

        chunk_end = min(current + max_range, end_sec)
        params = {
            "period1": current,
            "period2": chunk_end,
            "interval": interval,
        }

        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("chart", {}).get("result", [])
                    if not result:
                        break

                    result = result[0]
                    timestamps = result.get("timestamp", [])
                    quote = result.get("indicators", {}).get("quote", [{}])[0]

                    if not timestamps:
                        current = chunk_end
                        continue

                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    volumes = quote.get("volume", [])

                    for i, ts in enumerate(timestamps):
                        if opens[i] is None or closes[i] is None:
                            continue
                        candles.append(
                            {
                                "asset": symbol,
                                "timeframe": timeframe,
                                "timestamp": ts * 1000,
                                "open": float(opens[i]),
                                "high": float(highs[i]) if highs[i] else float(opens[i]),
                                "low": float(lows[i]) if lows[i] else float(opens[i]),
                                "close": float(closes[i]),
                                "volume": float(volumes[i]) if volumes[i] else 0,
                            }
                        )

                    current = chunk_end
                else:
                    break
        except Exception as e:
            STATS.errors.append(f"Yahoo error: {str(e)[:100]}")
            break

    return candles


async def backfill_asset_timeframe(
    session: aiohttp.ClientSession,
    conn,
    asset: str,
    timeframe: str,
    semaphore: asyncio.Semaphore,
):
    """Backfill a single asset/timeframe with fallback."""
    async with semaphore:
        STATS.current_asset = asset
        STATS.current_timeframe = timeframe

        # Get asset start date
        asset_start = ASSET_START_DATES.get(asset, DEFAULT_START)
        start_ts = int(asset_start.timestamp() * 1000)
        end_ts = int(datetime.now(UTC).timestamp() * 1000)

        # Check existing data
        existing_min, existing_max = get_existing_range(conn, asset, timeframe)

        tasks = []

        # Need older data?
        if existing_min is None or existing_min > start_ts + 86400000:
            hist_end = existing_min if existing_min else end_ts
            tasks.append(("historical", start_ts, hist_end))

        # Need recent data?
        if existing_max is None or end_ts - existing_max > 7200000:  # 2 hours
            recent_start = existing_max + 1 if existing_max else start_ts
            tasks.append(("recent", recent_start, end_ts))

        if not tasks:
            STATS.total_skipped += 1
            return

        for task_type, t_start, t_end in tasks:
            STATS.current_source = f"binance ({task_type})"
            STATS.log_progress()

            # Try Binance first
            candles = await fetch_binance(session, asset, timeframe, t_start, t_end)

            # Fallback to Yahoo for historical if Binance didn't return much
            if len(candles) < 100 and task_type == "historical" and asset in YAHOO_SYMBOLS:
                STATS.current_source = f"yahoo ({task_type})"
                STATS.log_progress()
                yahoo_candles = await fetch_yahoo(session, asset, timeframe, t_start, t_end)
                if len(yahoo_candles) > len(candles):
                    candles = yahoo_candles

            if candles:
                inserted, skipped = batch_upsert_candles(conn, candles, STATS.current_source)
                STATS.total_inserted += inserted
                STATS.total_skipped += skipped


async def backfill_all(
    assets: list[str],
    timeframes: list[str],
    concurrent: int = 3,
):
    """
    Backfill all specified assets and timeframes.

    Uses semaphore to limit concurrent API calls.
    """
    global STATS
    STATS = BackfillStats()
    STATS.total_assets = len(assets) * len(timeframes)
    STATS.start_time = time.time()

    print("=" * 60)
    print("OHLCV BACKFILL (PostgreSQL)")
    print("=" * 60)
    print(f"Assets: {len(assets)} | Timeframes: {timeframes}")
    print(f"Concurrent: {concurrent}")
    print("=" * 60)

    conn = get_pg_connection()
    semaphore = asyncio.Semaphore(concurrent)

    async with aiohttp.ClientSession() as session:
        # Process by timeframe (daily first for max coverage)
        for timeframe in sorted(timeframes, key=lambda t: (0 if t == "1d" else 1)):
            tasks = []
            for asset in assets:
                task = backfill_asset_timeframe(session, conn, asset, timeframe, semaphore)
                tasks.append(task)

            # Run concurrently within rate limits
            await asyncio.gather(*tasks)
            STATS.completed_assets += len(assets)

    conn.close()

    # Final summary
    elapsed = time.time() - STATS.start_time
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Inserted: {STATS.total_inserted:,}")
    print(f"Skipped: {STATS.total_skipped:,}")
    if STATS.errors:
        print(f"Errors: {len(STATS.errors)}")
        for err in STATS.errors[-5:]:
            print(f"  - {err}")
    print("=" * 60)


async def startup_backfill():
    """
    Quick startup backfill - just trio assets + recent gaps.

    Call this from server startup for minimal delay.
    """
    print("[STARTUP] Quick backfill for trio assets...")
    await backfill_all(
        assets=TRIO_ASSETS,
        timeframes=["1h", "15m"],
        concurrent=2,
    )


def main():
    parser = argparse.ArgumentParser(description="OHLCV Backfill for PostgreSQL")
    parser.add_argument("--asset", help="Single asset to backfill")
    parser.add_argument("--all", action="store_true", help="Backfill ALL assets (60+)")
    parser.add_argument("--trio", action="store_true", help="Just BTC/ETH/SOL (default)")
    parser.add_argument("--timeframe", help="Specific timeframe (1d, 1h, 15m)")
    parser.add_argument("--concurrent", type=int, default=3, help="Concurrent downloads")
    args = parser.parse_args()

    # Determine assets
    if args.asset:
        assets = [args.asset.upper()]
    elif args.all:
        assets = ALL_ASSETS
    else:
        assets = TRIO_ASSETS

    # Determine timeframes
    if args.timeframe:
        timeframes = [args.timeframe]
    else:
        timeframes = ALL_TIMEFRAMES

    asyncio.run(backfill_all(assets, timeframes, args.concurrent))


if __name__ == "__main__":
    main()
