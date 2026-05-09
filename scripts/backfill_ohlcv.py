#!/usr/bin/env python3
"""
Coinswarm OHLCV Backfill Script with Live Progress Dashboard

Fetches historical OHLCV data from multiple APIs in parallel and stores in local SQLite.
APIs: Binance (major pairs), Birdeye (Solana), CryptoCompare (fallback)

Usage:
    python backfill_ohlcv.py                    # Backfill all assets
    python backfill_ohlcv.py --asset BTC        # Backfill single asset
    python backfill_ohlcv.py --tier 1           # Backfill tier 1 only
    python backfill_ohlcv.py --timeframe 1d     # Backfill daily only
    python backfill_ohlcv.py --upload           # Upload to V3 after backfill
"""

import argparse
import asyncio
import json
import sqlite3
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from logging_config import LogContext, ctx, ctx_exception, get_logger

logger = get_logger(__name__)

# --- Configuration ---
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
TOKENS_CONFIG = PROJECT_ROOT / "config" / "tokens" / "tokens.json"
DB_PATH = SCRIPT_DIR / "coinswarm_ohlcv.sqlite"

# API endpoints
BINANCE_BASE = "https://api.binance.us/api/v3/klines"
BIRDEYE_BASE = "https://public-api.birdeye.so/defi/ohlcv"
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

# Rate limits (requests per minute)
BINANCE_RPM = 20  # Conservative, actual limit is 1200 weight/min
BIRDEYE_RPM = 30  # 60 rpm account limit, 100 rps OHLCV
CRYPTOCOMPARE_RPM = 5  # ~100/day on free tier with API key
YAHOO_RPM = 10  # Conservative for Yahoo Finance

# Timeframe mappings
BINANCE_INTERVALS = {"1d": "1d", "1h": "1h", "6h": "6h", "15m": "15m", "5m": "5m", "1m": "1m"}
BIRDEYE_INTERVALS = {"1d": "1D", "1h": "1H", "6h": "6H", "15m": "15m", "5m": "5m", "1m": "1m"}
CRYPTOCOMPARE_ENDPOINTS = {
    "1d": "histoday",
    "1h": "histohour",
    "15m": "histominute",
    "5m": "histominute",
    "1m": "histominute",
}

# Canonical periods for testing - priority backfill for minute data
CANONICAL_PERIODS = {
    # === CRASHES (highest priority - need minute data) ===
    "crash_2020_covid": ("2020-03-08", "2020-03-15"),  # -50% in 1 WEEK (COVID black swan)
    "crash_2022_luna": ("2022-05-07", "2022-05-12"),  # Luna/UST death spiral
    "crash_2022_ftx": ("2022-11-06", "2022-11-09"),  # -25% FTX collapse
    "crash_2021_may": ("2021-05-12", "2021-05-19"),  # -30% China ban + Elon tweet
    "crash_2018_jan": ("2018-01-06", "2018-02-06"),  # -65% in 1 month post-2017 ATH
    # === BLOW-OFF TOPS ===
    "blowoff_2017_dec": ("2017-12-01", "2017-12-17"),  # $19,783 ATH then -65%
    "blowoff_2021_apr": ("2021-04-01", "2021-04-14"),  # $64k ATH, Tesla hype
    "blowoff_2021_nov": ("2021-11-01", "2021-11-10"),  # $68k ATH
    # === RECOVERY ===
    "recovery_2020_post_covid": ("2020-03-16", "2020-07-31"),  # $5k -> $12k
    "recovery_2023": ("2023-01-01", "2023-03-31"),  # Post-FTX bounce
    # === BULL RUNS ===
    "bull_2020_q4": ("2020-10-01", "2020-12-31"),  # $10k -> $29k
    "bull_2021_q1": ("2021-01-01", "2021-03-31"),  # $29k -> $60k
}

# Historical depth - go back as far as data exists!
# BTC launched 2009, but meaningful trading data from 2013
# Most altcoins have data from 2017+ (Binance launch)
BACKFILL_START = datetime(2013, 1, 1)  # Maximum historical depth
BACKFILL_END = datetime.now()
# Global flag for full historical backfill
FORCE_FULL_HISTORY = False

# Asset-specific start dates (when they became tradeable)
ASSET_START_DATES = {
    # === OG COINS (pre-2017) ===
    "BTC": datetime(2013, 1, 1),  # CryptoCompare has data from 2010, but 2013 has better liquidity
    "ETH": datetime(2015, 8, 7),  # ETH launched Aug 2015
    "LTC": datetime(2013, 4, 28),  # LTC launched 2011, good data from 2013
    "XRP": datetime(2014, 1, 1),  # XRP traded on exchanges from 2013
    "DOGE": datetime(2013, 12, 15),  # Launched Dec 2013
    "XMR": datetime(2014, 4, 18),  # Monero launched Apr 2014
    "DASH": datetime(2014, 1, 18),  # Dash (Darkcoin) launched Jan 2014
    "XLM": datetime(2014, 8, 1),  # Stellar launched Aug 2014
    "NEO": datetime(2016, 9, 9),  # NEO (Antshares) Sep 2016
    "ETC": datetime(2016, 7, 24),  # ETH Classic fork Jul 2016
    "ZEC": datetime(2016, 10, 28),  # Zcash launched Oct 2016
    # === 2017 ERA (ICO boom) ===
    "BNB": datetime(2017, 7, 25),  # Binance launch
    "ADA": datetime(2017, 10, 1),  # Cardano ICO Oct 2017
    "TRX": datetime(2017, 9, 13),  # Tron ICO Sep 2017
    "EOS": datetime(2017, 7, 1),  # EOS ICO Jul 2017
    "LINK": datetime(2017, 9, 21),  # Chainlink ICO Sep 2017
    "VET": datetime(2017, 8, 22),  # VeChain ICO Aug 2017 (was VEN)
    "XTZ": datetime(2018, 7, 1),  # Tezos mainnet Jul 2018
    "IOTA": datetime(2017, 6, 13),  # IOTA traded Jun 2017
    "BCH": datetime(2017, 8, 1),  # Bitcoin Cash fork Aug 2017
    # === 2018-2019 ERA ===
    "ATOM": datetime(2019, 3, 14),  # Cosmos launch Mar 2019
    "MATIC": datetime(2019, 4, 28),  # Polygon (MATIC) ICO Apr 2019
    "ALGO": datetime(2019, 6, 19),  # Algorand mainnet Jun 2019
    "FTM": datetime(2018, 10, 29),  # Fantom ICO Oct 2018
    "MKR": datetime(2017, 12, 18),  # Maker DAO Dec 2017
    "COMP": datetime(2020, 6, 15),  # Compound token Jun 2020
    "SNX": datetime(2018, 3, 1),  # Synthetix (was Havven) Mar 2018
    # === 2020 ERA (DeFi summer) ===
    "SOL": datetime(2020, 4, 10),  # Solana mainnet beta Apr 2020
    "DOT": datetime(2020, 8, 22),  # Polkadot launch Aug 2020
    "AVAX": datetime(2020, 9, 21),  # Avalanche mainnet Sep 2020
    "UNI": datetime(2020, 9, 17),  # Uniswap token launch Sep 2020
    "SUSHI": datetime(2020, 8, 28),  # SushiSwap launch Aug 2020
    "AAVE": datetime(2020, 10, 2),  # AAVE v2 launch Oct 2020 (was LEND)
    "CRV": datetime(2020, 8, 13),  # Curve token Aug 2020
    "FIL": datetime(2020, 10, 15),  # Filecoin mainnet Oct 2020
    "NEAR": datetime(2020, 10, 13),  # NEAR mainnet Oct 2020
    "GRT": datetime(2020, 12, 17),  # The Graph Dec 2020
    "1INCH": datetime(2020, 12, 25),  # 1inch airdrop Dec 2020
    "HNT": datetime(2020, 8, 1),  # Helium network token
    "RNDR": datetime(2020, 6, 10),  # Render token
    "CAKE": datetime(2020, 9, 28),  # PancakeSwap launch Sep 2020
    "XVS": datetime(2020, 10, 7),  # Venus launch Oct 2020
    "BAKE": datetime(2020, 9, 24),  # BakerySwap Sep 2020
    # === 2021 ERA ===
    "AXS": datetime(2020, 11, 4),  # Axie Infinity Nov 2020
    "SAND": datetime(2020, 8, 14),  # The Sandbox Aug 2020
    "MANA": datetime(2017, 9, 18),  # Decentraland ICO Sep 2017
    "ENJ": datetime(2017, 11, 1),  # Enjin Nov 2017
    "IMX": datetime(2021, 11, 5),  # Immutable X Nov 2021
    "LDO": datetime(2021, 1, 5),  # Lido Jan 2021
    "DYDX": datetime(2021, 9, 8),  # dYdX token Sep 2021
    "RAY": datetime(2021, 2, 21),  # Raydium launch Feb 2021
    "ORCA": datetime(2021, 8, 9),  # Orca launch Aug 2021
    "ALPACA": datetime(2021, 2, 26),  # Alpaca Finance Feb 2021
    "STX": datetime(2019, 10, 28),  # Stacks mainnet Oct 2019
    # === 2022 ERA ===
    "OP": datetime(2022, 6, 1),  # Optimism airdrop Jun 2022
    "APT": datetime(2022, 10, 18),  # Aptos mainnet Oct 2022
    "GMX": datetime(2021, 9, 1),  # GMX Sep 2021 (on Arbitrum)
    "RPL": datetime(2017, 9, 11),  # Rocket Pool ICO 2017, token traded later
    "BONK": datetime(2022, 12, 25),  # Bonk launch Dec 2022
    # === 2023 ERA ===
    "ARB": datetime(2023, 3, 23),  # Arbitrum airdrop Mar 2023
    "SUI": datetime(2023, 5, 3),  # Sui mainnet May 2023
    "SEI": datetime(2023, 8, 15),  # Sei mainnet Aug 2023
    "INJ": datetime(2020, 10, 19),  # Injective Oct 2020 (token)
    "PYTH": datetime(2023, 11, 20),  # Pyth airdrop Nov 2023
    "JTO": datetime(2023, 12, 7),  # Jito airdrop Dec 2023
    "WIF": datetime(2023, 12, 15),  # WIF launch Dec 2023
    "PENDLE": datetime(2021, 4, 28),  # Pendle Apr 2021
    # === 2024 ERA ===
    "JUP": datetime(2024, 1, 31),  # Jupiter airdrop Jan 2024
    "W": datetime(2024, 4, 3),  # Wormhole airdrop Apr 2024
    "DRIFT": datetime(2024, 5, 16),  # Drift airdrop May 2024
    "ENA": datetime(2024, 4, 2),  # Ethena airdrop Apr 2024
    # === TRADFI/STOCKS (via Alpha Vantage) ===
    "MSTR": datetime(2013, 1, 1),  # MicroStrategy stock
}


# =============================================================================
# Progress Dashboard
# =============================================================================


@dataclass
class APIStats:
    """Stats for a single API."""

    name: str
    rpm_limit: int
    requests_made: int = 0
    candles_fetched: int = 0
    errors: list[str] = field(default_factory=list)
    last_request_time: float = 0
    request_times: deque = field(default_factory=lambda: deque(maxlen=60))  # Last 60 requests

    @property
    def current_rpm(self) -> float:
        """Calculate current requests per minute."""
        now = time.time()
        # Count requests in last 60 seconds
        recent = [t for t in self.request_times if now - t < 60]
        return len(recent)

    @property
    def rpm_usage_pct(self) -> float:
        """Percentage of rate limit used."""
        return (self.current_rpm / self.rpm_limit) * 100 if self.rpm_limit > 0 else 0


@dataclass
class ProgressStats:
    """Overall progress statistics."""

    total_assets: int = 0
    completed_assets: int = 0
    current_asset: str = ""
    current_timeframe: str = ""
    current_source: str = ""
    total_candles_inserted: int = 0
    total_candles_skipped: int = 0
    start_time: float = field(default_factory=time.time)
    api_stats: dict[str, APIStats] = field(default_factory=dict)

    def __post_init__(self):
        self.api_stats = {
            "binance": APIStats("Binance", BINANCE_RPM),
            "birdeye": APIStats("Birdeye", BIRDEYE_RPM),
            "cryptocompare": APIStats("CryptoCompare", CRYPTOCOMPARE_RPM),
            "yahoo": APIStats("Yahoo Finance", YAHOO_RPM),
        }

    @property
    def elapsed_time(self) -> str:
        """Format elapsed time."""
        elapsed = time.time() - self.start_time
        mins, secs = divmod(int(elapsed), 60)
        return f"{mins}m {secs}s"

    @property
    def progress_pct(self) -> float:
        """Overall progress percentage."""
        return (self.completed_assets / self.total_assets * 100) if self.total_assets > 0 else 0


class Dashboard:
    """Live terminal dashboard for backfill progress."""

    def __init__(self, stats: ProgressStats):
        self.stats = stats
        self.last_render = 0
        self.render_interval = 0.5  # Render every 0.5 seconds

    def render(self, force: bool = False):
        """Render the dashboard to terminal."""
        now = time.time()
        if not force and now - self.last_render < self.render_interval:
            return
        self.last_render = now

        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="")

        s = self.stats

        # Header
        print("=" * 70)
        print("  COINSWARM OHLCV BACKFILL - LIVE DASHBOARD")
        print("=" * 70)

        # Overall Progress
        print("\n[PROGRESS]")
        print(f"   Elapsed: {s.elapsed_time}")
        print(f"   Assets:  {s.completed_assets}/{s.total_assets} ({s.progress_pct:.1f}%)")
        print(f"   Current: {s.current_asset} {s.current_timeframe} via {s.current_source}")
        print(f"   Candles: {s.total_candles_inserted:,} inserted, {s.total_candles_skipped:,} skipped")

        # Progress bar
        bar_width = 50
        filled = int(bar_width * s.progress_pct / 100)
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\n   [{bar}] {s.progress_pct:.1f}%")

        # API Rate Limits
        print("\n[API RATE LIMITS]")
        print(f"   {'API':<15} {'RPM':<10} {'Usage':<22} {'Requests':<10} {'Candles':<10}")
        print(f"   {'-' * 67}")

        for name, api in s.api_stats.items():
            rpm_bar_width = 20
            rpm_filled = int(rpm_bar_width * min(api.rpm_usage_pct, 100) / 100)
            rpm_bar = "=" * rpm_filled + "." * (rpm_bar_width - rpm_filled)

            # Color based on usage (ANSI codes work on Windows 10+)
            if api.rpm_usage_pct >= 90:
                color = "\033[91m"  # Red
            elif api.rpm_usage_pct >= 70:
                color = "\033[93m"  # Yellow
            else:
                color = "\033[92m"  # Green
            reset = "\033[0m"

            print(
                f"   {name:<15} {api.rpm_limit:<10} {color}[{rpm_bar}]{reset} {api.requests_made:<10} {api.candles_fetched:<10}"
            )

        # Recent Errors
        all_errors = []
        for api in s.api_stats.values():
            for err in api.errors[-3:]:  # Last 3 errors per API
                all_errors.append(f"[{api.name}] {err}")

        if all_errors:
            print(f"\n[ERRORS] ({len(all_errors)} recent)")
            for err in all_errors[-5:]:  # Show last 5 total
                print(f"   {err[:65]}")
        else:
            print("\n[OK] No errors")

        print("\n" + "=" * 70)
        print("  Press Ctrl+C to stop")
        print("=" * 70)

        sys.stdout.flush()


# Global stats and dashboard
STATS = ProgressStats()
DASHBOARD: Dashboard | None = None


def load_config():
    """Load tokens configuration."""
    with open(TOKENS_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def load_api_keys():
    """Load API keys from environment files."""
    keys = {
        "binance_api": None,
        "binance_secret": None,
        "birdeye": None,
        "cryptocompare": None,
    }

    # Try .env.api-keys.backup first
    env_backup = PROJECT_ROOT / ".env.api-keys.backup"
    if env_backup.exists():
        with open(env_backup, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("BIRDEYE_API_KEY="):
                    keys["birdeye"] = line.split("=", 1)[1].strip()
                elif line.startswith("CRYPTOCOMPARE_API_KEY="):
                    keys["cryptocompare"] = line.split("=", 1)[1].strip()

    # Try .env.dont_delete_yet_human_said_so for Binance
    env_dont_delete = PROJECT_ROOT / ".env.dont_delete_yet_human_said_so"
    if env_dont_delete.exists():
        with open(env_dont_delete, encoding="utf-8") as f:
            content = f.read()
            # Look for API Key section
            if "API Key:" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.strip() == "API Key:":
                        if i + 1 < len(lines):
                            keys["binance_api"] = lines[i + 1].strip()
                    elif line.strip() == "Secret Key:":
                        if i + 1 < len(lines):
                            keys["binance_secret"] = lines[i + 1].strip()
            # Also get CryptoCompare if not found yet
            if not keys["cryptocompare"]:
                for line in content.split("\n"):
                    if line.startswith("CRYPTOCOMPARE_API_KEY="):
                        keys["cryptocompare"] = line.split("=", 1)[1].strip()

    return keys


def init_db():
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            source TEXT DEFAULT 'binance',
            fetched_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            UNIQUE(asset, timeframe, timestamp)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_candles_lookup
        ON candles(asset, timeframe, timestamp DESC)
    """)

    conn.commit()
    return conn


def get_existing_range(conn: sqlite3.Connection, asset: str, timeframe: str) -> tuple:
    """Get min/max timestamps for existing data."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT MIN(timestamp), MAX(timestamp)
        FROM candles
        WHERE asset = ? AND timeframe = ?
    """,
        (asset, timeframe),
    )
    row = cursor.fetchone()
    return (row[0], row[1]) if row[0] else (None, None)


def insert_candles(conn: sqlite3.Connection, candles: list, source: str) -> tuple:
    """Insert candles into database, ignoring duplicates. Returns (inserted, skipped)."""
    if not candles:
        return 0, 0

    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for c in candles:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO candles
                (asset, timeframe, timestamp, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    c["asset"],
                    c["timeframe"],
                    c["timestamp"],
                    c["open"],
                    c["high"],
                    c["low"],
                    c["close"],
                    c["volume"],
                    source,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    return inserted, skipped


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, rpm: int, api_name: str):
        self.rpm = rpm
        self.interval = 60.0 / rpm
        self.last_call = 0
        self.api_name = api_name

    async def wait(self):
        """Wait until next call is allowed."""
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self.last_call = time.time()

        # Update stats
        if self.api_name in STATS.api_stats:
            STATS.api_stats[self.api_name].request_times.append(time.time())
            STATS.api_stats[self.api_name].last_request_time = time.time()


class BinanceFetcher:
    """Fetch OHLCV data from Binance US."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None):
        self.session = session
        self.api_key = api_key
        self.rate_limiter = RateLimiter(BINANCE_RPM, "binance")
        self.api_stats = STATS.api_stats["binance"]

    async def fetch(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list:
        """Fetch candles from Binance."""
        candles = []
        pair = f"{symbol}USDT"
        interval = BINANCE_INTERVALS.get(timeframe, "1d")

        current_start = start_ts

        while current_start < end_ts:
            await self.rate_limiter.wait()

            params = {
                "symbol": pair,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_ts,
                "limit": 1000,
            }

            headers = {}
            if self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key

            try:
                self.api_stats.requests_made += 1
                async with self.session.get(BINANCE_BASE, params=params, headers=headers) as resp:
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

                        self.api_stats.candles_fetched += len(data)
                        current_start = data[-1][0] + 1

                        if DASHBOARD:
                            DASHBOARD.render()

                    elif resp.status == 429:
                        self.api_stats.errors.append(f"Rate limited at {datetime.now().strftime('%H:%M:%S')}")
                        await asyncio.sleep(60)
                    else:
                        text = await resp.text()
                        self.api_stats.errors.append(f"{resp.status}: {text[:100]}")
                        break
            except Exception as e:
                self.api_stats.errors.append(str(e)[:100])
                break

        return candles


class BirdeyeFetcher:
    """Fetch OHLCV data from Birdeye (Solana tokens)."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, token_mints: dict):
        self.session = session
        self.api_key = api_key
        self.token_mints = token_mints
        self.rate_limiter = RateLimiter(BIRDEYE_RPM, "birdeye")
        self.api_stats = STATS.api_stats["birdeye"]

    async def fetch(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list:
        """Fetch candles from Birdeye."""
        if symbol not in self.token_mints:
            self.api_stats.errors.append(f"No mint address for {symbol}")
            return []

        candles = []
        mint = self.token_mints[symbol]
        interval = BIRDEYE_INTERVALS.get(timeframe, "1D")

        start_sec = start_ts // 1000
        end_sec = end_ts // 1000

        await self.rate_limiter.wait()

        params = {
            "address": mint,
            "type": interval,
            "time_from": start_sec,
            "time_to": end_sec,
        }

        headers = {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
        }

        try:
            self.api_stats.requests_made += 1
            async with self.session.get(BIRDEYE_BASE, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("data", {}).get("items", [])

                    for item in items:
                        candles.append(
                            {
                                "asset": symbol,
                                "timeframe": timeframe,
                                "timestamp": item["unixTime"] * 1000,
                                "open": float(item["o"]),
                                "high": float(item["h"]),
                                "low": float(item["l"]),
                                "close": float(item["c"]),
                                "volume": float(item.get("v", 0)),
                            }
                        )

                    self.api_stats.candles_fetched += len(items)

                    if DASHBOARD:
                        DASHBOARD.render()
                else:
                    text = await resp.text()
                    self.api_stats.errors.append(f"{resp.status}: {text[:100]}")
        except Exception as e:
            self.api_stats.errors.append(str(e)[:100])

        return candles


class CryptoCompareFetcher:
    """Fetch OHLCV data from CryptoCompare (fallback)."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None):
        self.session = session
        self.api_key = api_key
        self.rate_limiter = RateLimiter(CRYPTOCOMPARE_RPM, "cryptocompare")
        self.api_stats = STATS.api_stats["cryptocompare"]

    async def fetch(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list:
        """Fetch candles from CryptoCompare."""
        if timeframe not in CRYPTOCOMPARE_ENDPOINTS:
            self.api_stats.errors.append(f"Unsupported timeframe: {timeframe}")
            return []

        candles = []
        endpoint = CRYPTOCOMPARE_ENDPOINTS[timeframe]
        url = f"{CRYPTOCOMPARE_BASE}/{endpoint}"

        current_end = end_ts // 1000
        start_sec = start_ts // 1000

        while current_end > start_sec:
            await self.rate_limiter.wait()

            params = {
                "fsym": symbol,
                "tsym": "USD",
                "limit": 2000,
                "toTs": current_end,
            }

            headers = {}
            if self.api_key:
                headers["authorization"] = f"Apikey {self.api_key}"

            try:
                self.api_stats.requests_made += 1
                async with self.session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("Data", {}).get("Data", [])

                        if not items:
                            break

                        for item in items:
                            if item["time"] >= start_sec:
                                candles.append(
                                    {
                                        "asset": symbol,
                                        "timeframe": timeframe,
                                        "timestamp": item["time"] * 1000,
                                        "open": float(item["open"]),
                                        "high": float(item["high"]),
                                        "low": float(item["low"]),
                                        "close": float(item["close"]),
                                        "volume": float(item.get("volumefrom", 0)),
                                    }
                                )

                        self.api_stats.candles_fetched += len(items)
                        current_end = items[0]["time"] - 1

                        if DASHBOARD:
                            DASHBOARD.render()
                    else:
                        text = await resp.text()
                        self.api_stats.errors.append(f"{resp.status}: {text[:100]}")
                        break
            except Exception as e:
                self.api_stats.errors.append(str(e)[:100])
                break

        return candles


# Yahoo Finance symbol mappings
YAHOO_SYMBOLS = {
    # Major cryptos
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "LTC": "LTC-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "SOL": "SOL-USD",
    "DOT": "DOT-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "MATIC": "MATIC-USD",
    "UNI": "UNI-USD",
    "ATOM": "ATOM-USD",
    "XLM": "XLM-USD",
    "ETC": "ETC-USD",
    "XMR": "XMR-USD",
    "BCH": "BCH-USD",
    "TRX": "TRX-USD",
    "EOS": "EOS-USD",
    "NEO": "NEO-USD",
    "DASH": "DASH-USD",
    "ZEC": "ZEC-USD",
    "IOTA": "IOTA-USD",
    "XTZ": "XTZ-USD",
    "VET": "VET-USD",
    "BNB": "BNB-USD",
    "FIL": "FIL-USD",
    "AAVE": "AAVE-USD",
    "MKR": "MKR-USD",
    "COMP": "COMP-USD",
    "SNX": "SNX-USD",
    "ALGO": "ALGO-USD",
    "FTM": "FTM-USD",
    "NEAR": "NEAR-USD",
    "GRT": "GRT-USD",
    "MANA": "MANA-USD",
    "SAND": "SAND-USD",
    "AXS": "AXS-USD",
    "ENJ": "ENJ-USD",
    "CRV": "CRV-USD",
    "SUSHI": "SUSHI-USD",
    # TradFi stocks
    "MSTR": "MSTR",
}

YAHOO_INTERVALS = {"1d": "1d", "1h": "1h"}


class YahooFinanceFetcher:
    """Fetch OHLCV data from Yahoo Finance (great for historical data)."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.rate_limiter = RateLimiter(YAHOO_RPM, "yahoo")
        self.api_stats = STATS.api_stats["yahoo"]
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async def fetch(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list:
        """Fetch candles from Yahoo Finance."""
        if timeframe not in YAHOO_INTERVALS:
            self.api_stats.errors.append(f"Unsupported timeframe: {timeframe}")
            return []

        yahoo_symbol = YAHOO_SYMBOLS.get(symbol)
        if not yahoo_symbol:
            self.api_stats.errors.append(f"No Yahoo symbol for {symbol}")
            return []

        candles = []
        interval = YAHOO_INTERVALS[timeframe]
        url = f"{YAHOO_BASE}/{yahoo_symbol}"

        # Yahoo Finance accepts timestamps in seconds
        start_sec = start_ts // 1000
        end_sec = end_ts // 1000

        # Yahoo limits range based on interval
        # For 1d: can fetch years at once
        # For 1h: limited to ~730 days per request
        max_range_days = 3650 if timeframe == "1d" else 730
        max_range_sec = max_range_days * 86400

        current_start = start_sec
        while current_start < end_sec:
            await self.rate_limiter.wait()

            chunk_end = min(current_start + max_range_sec, end_sec)

            params = {
                "period1": current_start,
                "period2": chunk_end,
                "interval": interval,
                "includePrePost": "false",
            }

            try:
                self.api_stats.requests_made += 1
                async with self.session.get(url, params=params, headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("chart", {}).get("result", [])
                        if not result:
                            break

                        result = result[0]
                        timestamps = result.get("timestamp", [])
                        quote = result.get("indicators", {}).get("quote", [{}])[0]

                        if not timestamps:
                            current_start = chunk_end
                            continue

                        opens = quote.get("open", [])
                        highs = quote.get("high", [])
                        lows = quote.get("low", [])
                        closes = quote.get("close", [])
                        volumes = quote.get("volume", [])

                        for i, ts in enumerate(timestamps):
                            # Skip invalid data points
                            if opens[i] is None or closes[i] is None:
                                continue

                            candles.append(
                                {
                                    "asset": symbol,
                                    "timeframe": timeframe,
                                    "timestamp": ts * 1000,  # Convert to ms
                                    "open": float(opens[i]),
                                    "high": float(highs[i]) if highs[i] else float(opens[i]),
                                    "low": float(lows[i]) if lows[i] else float(opens[i]),
                                    "close": float(closes[i]),
                                    "volume": float(volumes[i]) if volumes[i] else 0,
                                }
                            )

                        self.api_stats.candles_fetched += len(timestamps)
                        current_start = chunk_end

                        if DASHBOARD:
                            DASHBOARD.render()
                    elif resp.status == 404:
                        self.api_stats.errors.append(f"{symbol}: Not found on Yahoo")
                        break
                    else:
                        text = await resp.text()
                        self.api_stats.errors.append(f"{resp.status}: {text[:100]}")
                        break
            except Exception as e:
                self.api_stats.errors.append(str(e)[:100])
                break

        return candles


async def backfill_asset(
    conn: sqlite3.Connection,
    asset: str,
    timeframe: str,
    source: str,
    fetcher,
    start_dt: datetime,
    end_dt: datetime,
    fallback_fetcher=None,
):
    """Backfill a single asset/timeframe combination with fallback support."""
    global STATS

    STATS.current_asset = asset
    STATS.current_timeframe = timeframe
    STATS.current_source = source

    if DASHBOARD:
        DASHBOARD.render()

    # Use asset-specific start date if available (don't try to fetch data before asset existed)
    asset_start = ASSET_START_DATES.get(asset, start_dt)
    actual_start = max(asset_start, start_dt) if asset_start else start_dt

    start_ts = int(actual_start.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)

    # Check existing data
    existing_min, existing_max = get_existing_range(conn, asset, timeframe)

    # Determine what we need to fetch
    fetch_recent = True
    fetch_historical = True

    # Calculate gaps in days for meaningful comparison
    day_ms = 86400000  # 1 day in milliseconds

    # In full history mode, always fetch full range regardless of existing data
    if FORCE_FULL_HISTORY:
        if existing_min:
            historical_gap = (existing_min - start_ts) / day_ms
            if historical_gap > 7:
                logger.info(
                    f"Full history mode: {asset} {timeframe} - fetching {historical_gap:.0f} days before existing data"
                )

    if existing_min and existing_max and not FORCE_FULL_HISTORY:
        # Check if we have recent data (within last 2 days)
        recent_gap = (end_ts - existing_max) / day_ms
        if recent_gap < 2:
            fetch_recent = False

        # Check if we have historical data (within 7 days of target start)
        # This is the key fix - we were being too lenient before
        historical_gap = (existing_min - start_ts) / day_ms
        if historical_gap < 7:
            fetch_historical = False

        # If we have both, skip
        if not fetch_recent and not fetch_historical:
            STATS.total_candles_skipped += 1
            return

        # Log large historical gaps we're about to fill
        if fetch_historical and historical_gap > 30:
            logger.info(
                "Filling historical data gap",
                extra=ctx(
                    LogContext.DATA_FETCH,
                    asset=asset,
                    timeframe=timeframe,
                    gap_days=historical_gap,
                    data_type="historical_gap",
                ),
            )

    candles = []

    # Fetch recent gap (from last candle to now)
    if fetch_recent and existing_max:
        recent_candles = await fetcher.fetch(asset, timeframe, existing_max + 1, end_ts)
        candles.extend(recent_candles)

    # Fetch historical gap (from start to first candle)
    hist_candles = []
    if fetch_historical:
        hist_end = existing_min - day_ms if existing_min else end_ts  # Go up to 1 day before existing data

        # First try primary fetcher for historical data
        hist_candles = await fetcher.fetch(asset, timeframe, start_ts, hist_end)

        # If primary didn't return historical data, try fallback (Yahoo Finance)
        if not hist_candles and fallback_fetcher:
            STATS.current_source = f"{source}->yahoo"
            if DASHBOARD:
                DASHBOARD.render()
            hist_candles = await fallback_fetcher.fetch(asset, timeframe, start_ts, hist_end)

        candles.extend(hist_candles)

    # If still no data and we haven't fetched anything yet, try full range
    if not candles and not existing_min:
        candles = await fetcher.fetch(asset, timeframe, start_ts, end_ts)

    if candles:
        inserted, skipped = insert_candles(conn, candles, source)
        STATS.total_candles_inserted += inserted
        STATS.total_candles_skipped += skipped


async def backfill_tier(
    conn: sqlite3.Connection,
    tier: dict,
    timeframes: list,
    session: aiohttp.ClientSession,
    api_keys: dict,
    token_mints: dict,
    start_dt: datetime,
    end_dt: datetime,
):
    """Backfill all assets in a tier with fallback support.

    PRIORITY ORDER: Daily data for ALL assets first, then hourly.
    This ensures we get the most historical coverage before drilling into detail.

    FALLBACK CHAIN (updated to use Yahoo Finance for historical):
    - Binance → Yahoo Finance (Yahoo has data back to 2014 for major cryptos)
    - Birdeye → Binance (for Solana tokens that are also on Binance)
    - CryptoCompare → Yahoo Finance
    - Yahoo Finance is now the primary historical data source!
    """
    source = tier["source"]
    fallback_source = tier.get("fallback")
    symbols = tier["symbols"]

    # Create Yahoo fetcher (always available as ultimate fallback)
    yahoo_fetcher = YahooFinanceFetcher(session)

    # Create primary fetcher
    fetcher = None
    if source == "binance":
        fetcher = BinanceFetcher(session, api_keys.get("binance_api"))
    elif source == "birdeye":
        if not api_keys.get("birdeye"):
            STATS.api_stats["birdeye"].errors.append("No API key")
            return
        fetcher = BirdeyeFetcher(session, api_keys["birdeye"], token_mints)
    elif source == "cryptocompare":
        fetcher = CryptoCompareFetcher(session, api_keys.get("cryptocompare"))
    elif source == "yahoo":
        fetcher = yahoo_fetcher
    else:
        return

    # Create fallback fetcher - prefer Yahoo Finance for historical data
    fallback_fetcher = yahoo_fetcher  # Default to Yahoo as fallback
    if fallback_source == "cryptocompare":
        fallback_fetcher = CryptoCompareFetcher(session, api_keys.get("cryptocompare"))
    elif fallback_source == "binance":
        fallback_fetcher = BinanceFetcher(session, api_keys.get("binance_api"))

    # Process timeframes in priority order (daily first)
    # Sort so '1d' comes before '1h' and '6h'
    sorted_timeframes = sorted(timeframes, key=lambda t: (0 if t == "1d" else 1, t))

    for timeframe in sorted_timeframes:
        for symbol in symbols:
            await backfill_asset(
                conn, symbol, timeframe, source, fetcher, start_dt, end_dt, fallback_fetcher=fallback_fetcher
            )

            if DASHBOARD:
                DASHBOARD.render()

    # Mark assets completed (all timeframes done for all symbols in tier)
    STATS.completed_assets += len(symbols)


async def backfill_canonical_periods(
    conn: sqlite3.Connection,
    session: aiohttp.ClientSession,
    api_keys: dict,
    token_mints: dict,
    assets: list,
    minute_timeframes: list = None,
):
    """Backfill minute-level data for canonical periods (crashes, blow-offs, etc).

    This is PRIORITY backfill - we want minute data for key market events first.
    These periods are critical for training patterns that work in extreme conditions.

    Args:
        conn: SQLite connection
        session: aiohttp session
        api_keys: API keys dict
        token_mints: Solana token mints
        assets: List of assets to backfill (e.g., ['BTC', 'ETH', 'SOL'])
        minute_timeframes: List of minute timeframes ['1m', '5m', '15m']
    """
    global STATS

    if minute_timeframes is None:
        minute_timeframes = ["15m", "5m", "1m"]  # 15m first (less data), then drill down

    # Create fetchers with fallback chain
    binance_fetcher = BinanceFetcher(session, api_keys.get("binance_api"))
    cryptocompare_fetcher = CryptoCompareFetcher(session, api_keys.get("cryptocompare"))

    # Sort periods by importance (crashes first, as they're most critical for risk management)
    period_priority = [
        # Crashes - HIGHEST priority (extreme volatility, need minute data)
        ("crash_2020_covid", CANONICAL_PERIODS["crash_2020_covid"]),
        ("crash_2022_luna", CANONICAL_PERIODS["crash_2022_luna"]),
        ("crash_2022_ftx", CANONICAL_PERIODS["crash_2022_ftx"]),
        ("crash_2021_may", CANONICAL_PERIODS["crash_2021_may"]),
        ("crash_2018_jan", CANONICAL_PERIODS["crash_2018_jan"]),
        # Blow-off tops - HIGH priority
        ("blowoff_2021_nov", CANONICAL_PERIODS["blowoff_2021_nov"]),
        ("blowoff_2021_apr", CANONICAL_PERIODS["blowoff_2021_apr"]),
        ("blowoff_2017_dec", CANONICAL_PERIODS["blowoff_2017_dec"]),
        # Recovery and bull runs - MEDIUM priority
        ("recovery_2020_post_covid", CANONICAL_PERIODS["recovery_2020_post_covid"]),
        ("recovery_2023", CANONICAL_PERIODS["recovery_2023"]),
        ("bull_2020_q4", CANONICAL_PERIODS["bull_2020_q4"]),
        ("bull_2021_q1", CANONICAL_PERIODS["bull_2021_q1"]),
    ]

    total_periods = len(period_priority) * len(assets) * len(minute_timeframes)
    completed = 0

    logger.info(
        "Starting canonical period backfill",
        extra=ctx(
            LogContext.FUNC_ENTRY,
            function_name="backfill_canonical_periods",
            period_count=len(period_priority),
            assets=assets[:5],
            timeframes=minute_timeframes,
            total_tasks=total_periods,
        ),
    )

    for period_name, (start_str, end_str) in period_priority:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)  # Include end day

        logger.info(
            "Processing canonical period",
            extra=ctx(
                LogContext.BATCH_PROGRESS,
                period_name=period_name,
                start_date=start_str,
                end_date=end_str,
                operation="canonical_backfill",
            ),
        )

        for timeframe in minute_timeframes:
            for asset in assets:
                # Skip assets that didn't exist during this period
                asset_start = ASSET_START_DATES.get(asset, datetime(2017, 1, 1))
                if asset_start > end_dt:
                    completed += 1
                    continue

                STATS.current_asset = asset
                STATS.current_timeframe = timeframe
                STATS.current_source = f"canonical:{period_name}"

                if DASHBOARD:
                    DASHBOARD.render()

                # Determine appropriate fetcher based on asset and period
                # Binance has minute data from ~2017, CryptoCompare has older data
                fetcher = binance_fetcher
                fallback = cryptocompare_fetcher

                if start_dt.year < 2017:
                    # For pre-2017 data, use CryptoCompare as primary
                    fetcher = cryptocompare_fetcher
                    fallback = None

                # Check if we already have this data
                start_ts = int(start_dt.timestamp() * 1000)
                end_ts = int(end_dt.timestamp() * 1000)

                existing_min, existing_max = get_existing_range(conn, asset, timeframe)

                # If we have data covering this period, skip
                if existing_min and existing_max:
                    if existing_min <= start_ts and existing_max >= end_ts:
                        completed += 1
                        continue

                # Fetch the period data
                try:
                    candles = await fetcher.fetch(asset, timeframe, start_ts, end_ts)

                    # Try fallback if primary failed
                    if not candles and fallback:
                        STATS.current_source = f"canonical:{period_name}->fallback"
                        candles = await fallback.fetch(asset, timeframe, start_ts, end_ts)

                    if candles:
                        inserted, skipped = insert_candles(conn, candles, f"canonical_{period_name}")
                        STATS.total_candles_inserted += inserted
                        STATS.total_candles_skipped += skipped
                        logger.debug(
                            "Canonical period data inserted",
                            extra=ctx(
                                LogContext.DB_OPERATION,
                                asset=asset,
                                timeframe=timeframe,
                                period_name=period_name,
                                inserted=inserted,
                            ),
                        )
                    else:
                        logger.debug(
                            "No data available for canonical period",
                            extra=ctx(
                                LogContext.DATA_FETCH,
                                asset=asset,
                                timeframe=timeframe,
                                period_name=period_name,
                                data_type="no_data",
                            ),
                        )

                except Exception as e:
                    logger.error(
                        "Error fetching canonical period data",
                        extra=ctx_exception(
                            e,
                            function_name="backfill_canonical_periods",
                            asset=asset,
                            timeframe=timeframe,
                            period_name=period_name,
                        ),
                        exc_info=True,
                    )

                completed += 1

                # Brief delay to respect rate limits
                await asyncio.sleep(0.1)

    logger.info(
        "Canonical period backfill complete",
        extra=ctx(
            LogContext.FUNCTION_EXIT,
            function_name="backfill_canonical_periods",
            completed=completed,
            total=total_periods,
        ),
    )


async def upload_to_v3(conn: sqlite3.Connection, api_url: str, access_token: str):
    """Upload local data to V3 AssetPriceDO instances."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT asset, timeframe FROM candles")
    asset_timeframes = cursor.fetchall()

    async with aiohttp.ClientSession() as session:
        headers = {
            "Content-Type": "application/json",
            "CF-Access-Client-Id": access_token.split(":")[0] if ":" in access_token else access_token,
            "CF-Access-Client-Secret": access_token.split(":")[1] if ":" in access_token else "",
        }

        for asset, timeframe in asset_timeframes:
            cursor.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE asset = ? AND timeframe = ?
                ORDER BY timestamp
            """,
                (asset, timeframe),
            )
            rows = cursor.fetchall()

            if not rows:
                continue

            candles = [
                {
                    "timestamp": r[0],
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "volume": r[5],
                }
                for r in rows
            ]

            batch_size = 1000
            for i in range(0, len(candles), batch_size):
                batch = candles[i : i + batch_size]

                payload = {
                    "asset": asset,
                    "timeframe": timeframe,
                    "candles": batch,
                }

                url = f"{api_url}/api/price/{asset}-USD/candles/bulk"

                try:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            logger.error(
                                "Upload error",
                                extra=ctx(
                                    LogContext.API_ERROR,
                                    asset=asset,
                                    timeframe=timeframe,
                                    status_code=resp.status,
                                    response_text=text[:200],
                                ),
                            )
                except Exception as e:
                    logger.error(
                        "Upload exception",
                        extra=ctx_exception(e, function_name="upload_to_v3", asset=asset, timeframe=timeframe),
                        exc_info=True,
                    )


def launch_streamlit_dashboard():
    """Launch Streamlit dashboard in a new borderless browser window."""
    import platform
    import webbrowser

    dashboard_path = SCRIPT_DIR / "evolution_dashboard.py"
    if not dashboard_path.exists():
        logger.warning(
            "Dashboard file not found",
            extra=ctx(
                LogContext.FUNC_ENTRY,
                function_name="launch_streamlit_dashboard",
                file_path=str(dashboard_path),
                action="skipping",
            ),
        )
        return None

    # Find an available port
    port = 8501

    # Start Streamlit in background
    streamlit_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard_path),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--server.runOnSave",
        "true",
        "--theme.base",
        "dark",
        "--browser.gatherUsageStats",
        "false",
    ]

    try:
        # Start Streamlit process
        # Note: These are long-running server processes that should run indefinitely,
        # so we don't add timeout to the Popen itself. The process is returned for
        # caller to manage lifecycle. We use start_new_session/creationflags to detach.
        if platform.system() == "Windows":
            # On Windows, use CREATE_NEW_CONSOLE to detach
            proc = subprocess.Popen(
                streamlit_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc = subprocess.Popen(
                streamlit_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
            )

        # Wait a moment for server to start
        time.sleep(2)

        # Open in default browser (or use Chrome in app mode for borderless)
        url = f"http://localhost:{port}"

        # Try to launch Chrome/Edge in app mode (borderless window)
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]

        launched = False
        for chrome_path in chrome_paths:
            if Path(chrome_path).exists():
                try:
                    # Browser process - fire and forget, no timeout needed as it's user-interactive
                    # Using start_new_session on Unix to detach from parent
                    browser_kwargs = {
                        "stdout": subprocess.DEVNULL,
                        "stderr": subprocess.DEVNULL,
                    }
                    if platform.system() != "Windows":
                        browser_kwargs["start_new_session"] = True
                    subprocess.Popen(
                        [
                            chrome_path,
                            f"--app={url}",
                            "--window-size=1400,900",
                            "--window-position=100,50",
                        ],
                        **browser_kwargs,
                    )
                    launched = True
                    logger.info(
                        "Dashboard opened in borderless mode",
                        extra=ctx(
                            LogContext.FUNCTION_EXIT,
                            function_name="launch_streamlit_dashboard",
                            url=url,
                            mode="borderless",
                        ),
                    )
                    break
                except Exception:
                    continue

        if not launched:
            # Fallback: open in default browser
            webbrowser.open(url)
            logger.info(
                "Dashboard opened in default browser",
                extra=ctx(
                    LogContext.FUNCTION_EXIT,
                    function_name="launch_streamlit_dashboard",
                    url=url,
                    mode="default_browser",
                ),
            )

        return proc

    except Exception as e:
        logger.warning(
            "Failed to launch dashboard",
            extra=ctx_exception(e, function_name="launch_streamlit_dashboard"),
            exc_info=True,
        )
        return None


async def main():
    global STATS, DASHBOARD, FORCE_FULL_HISTORY

    parser = argparse.ArgumentParser(description="Coinswarm OHLCV Backfill")
    parser.add_argument("--asset", help="Backfill single asset")
    parser.add_argument("--tier", type=int, help="Backfill specific tier (1-4)")
    parser.add_argument("--timeframe", help="Backfill specific timeframe (1d, 1h, 6h, 15m, 5m, 1m)")
    parser.add_argument(
        "--canonical",
        action="store_true",
        help="Priority backfill minute data for canonical periods (crashes, blow-offs)",
    )
    parser.add_argument(
        "--canonical-assets",
        default="BTC,ETH,SOL,BNB,XRP",
        help="Assets for canonical period backfill (comma-separated)",
    )
    parser.add_argument("--upload", action="store_true", help="Upload to V3 after backfill")
    parser.add_argument("--upload-only", action="store_true", help="Only upload, no fetch")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable live dashboard")
    parser.add_argument("--no-streamlit", action="store_true", help="Don't auto-launch Streamlit dashboard")
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Force full historical backfill from asset start date, ignoring existing data",
    )
    parser.add_argument("--api-url", default="https://coinswarm-v3.blakematthews-spam.workers.dev", help="V3 API URL")
    args = parser.parse_args()
    # Set full history mode if requested
    if args.full_history:
        FORCE_FULL_HISTORY = True
        logger.info("Full history mode enabled - will fetch all available data")

    # Load configuration
    config = load_config()
    api_keys = load_api_keys()
    token_mints = config.get("solanaTokenMints", {})
    tiers = config["backfillPriority"]["tiers"]

    # Select timeframes
    timeframes = ["1d", "1h"]
    if args.timeframe:
        timeframes = [args.timeframe]

    # Count total assets
    total_assets = 0
    for tier in tiers:
        if args.tier and tier["priority"] != args.tier:
            continue
        if args.asset:
            if args.asset in tier["symbols"]:
                total_assets += 1
        else:
            total_assets += len(tier["symbols"])

    # Initialize stats
    STATS = ProgressStats()
    STATS.total_assets = total_assets
    STATS.start_time = time.time()

    # Initialize terminal dashboard
    if not args.no_dashboard and not args.upload_only:
        DASHBOARD = Dashboard(STATS)

    # Initialize database
    conn = init_db()

    # Launch Streamlit dashboard in borderless window
    streamlit_proc = None
    if not args.no_streamlit and not args.upload_only:
        streamlit_proc = launch_streamlit_dashboard()

    if not args.upload_only:
        if DASHBOARD:
            DASHBOARD.render(force=True)

        try:
            async with aiohttp.ClientSession() as session:
                # PRIORITY: Canonical periods first (minute-level data for crashes, etc)
                if args.canonical:
                    canonical_assets = [a.strip() for a in args.canonical_assets.split(",")]
                    await backfill_canonical_periods(
                        conn,
                        session,
                        api_keys,
                        token_mints,
                        assets=canonical_assets,
                        minute_timeframes=["15m", "5m", "1m"],
                    )

                # Then regular tier-based backfill
                for tier in tiers:
                    if args.tier and tier["priority"] != args.tier:
                        continue

                    if args.asset:
                        if args.asset not in tier["symbols"]:
                            continue
                        tier = {**tier, "symbols": [args.asset]}

                    await backfill_tier(
                        conn, tier, timeframes, session, api_keys, token_mints, BACKFILL_START, BACKFILL_END
                    )
        except KeyboardInterrupt:
            logger.info(
                "Backfill interrupted by user",
                extra=ctx(
                    LogContext.FUNCTION_EXIT,
                    function_name="main",
                    reason="keyboard_interrupt",
                    candles_inserted=STATS.total_candles_inserted,
                ),
            )

    # Final summary
    if DASHBOARD:
        DASHBOARD.render(force=True)

    print("\n\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM candles")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT asset, timeframe, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM candles
        GROUP BY asset, timeframe
        ORDER BY asset, timeframe
    """)

    print(f"\n  Total candles in database: {total:,}")
    print(f"  Time elapsed: {STATS.elapsed_time}")
    print("\n  Per-asset breakdown:")

    for row in cursor.fetchall():
        asset, tf, count, min_ts, max_ts = row
        min_dt = datetime.fromtimestamp(min_ts / 1000).strftime("%Y-%m-%d")
        max_dt = datetime.fromtimestamp(max_ts / 1000).strftime("%Y-%m-%d")
        print(f"    {asset:<6} {tf:<3}: {count:>6,} candles ({min_dt} to {max_dt})")

    # Upload if requested
    if args.upload or args.upload_only:
        local_env = SCRIPT_DIR / ".env"
        access_token = ""
        if local_env.exists():
            with open(local_env, encoding="utf-8") as f:
                client_id = ""
                for line in f:
                    if line.startswith("CF_ACCESS_CLIENT_ID="):
                        client_id = line.split("=", 1)[1].strip()
                    elif line.startswith("CF_ACCESS_CLIENT_SECRET="):
                        client_secret = line.split("=", 1)[1].strip()
                        access_token = f"{client_id}:{client_secret}"

        if access_token:
            print("\n  Uploading to V3...")
            await upload_to_v3(conn, args.api_url, access_token)
            print("  Upload complete!")
        else:
            print("\n  [SKIP] No CF Access credentials found in local-utilities/.env")

    conn.close()
    print("\n  Done!")
    print("=" * 70)

    # Note: Streamlit dashboard continues running for viewing results
    if streamlit_proc:
        print("\n  [DASHBOARD] Streamlit dashboard still running at http://localhost:8501")
        print("             Press Ctrl+C to stop it, or close the browser window.")


if __name__ == "__main__":
    asyncio.run(main())
