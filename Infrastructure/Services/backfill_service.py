"""
Historical Data Backfill Service.

Fetches historical OHLCV data from exchanges using ccxt and populates
the enhanced_candles table. Runs on server startup to ensure data coverage.

Supports:
- Multiple exchanges (Binance, Coinbase, etc.)
- Multiple timeframes (1m, 15m, 1h, 4h, 1d)
- Gap detection and filling
- Rate limiting to avoid API bans
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

import ccxt.async_support as ccxt
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle

logger = logging.getLogger("backfill")


class BackfillPriority(Enum):
    """Priority levels for backfill tasks."""

    CRITICAL = 1  # BTC, ETH, SOL - trio assets
    HIGH = 2  # Major alts
    MEDIUM = 3  # Secondary assets
    LOW = 4  # Everything else


@dataclass
class BackfillTask:
    """A single backfill task."""

    symbol: str
    timeframe: str
    exchange: str
    start_ts: int  # Unix timestamp ms
    end_ts: int  # Unix timestamp ms
    priority: BackfillPriority


# Trio assets get highest priority
TRIO_ASSETS = {"BTC", "ETH", "SOL"}

# All supported assets (60+)
ALL_ASSETS = [
    # Tier 1: Major (CRITICAL priority)
    "BTC",
    "ETH",
    "SOL",
    # Tier 2: Large caps (HIGH priority)
    "BNB",
    "XRP",
    "ADA",
    "AVAX",
    "DOT",
    "LINK",
    "MATIC",
    # Tier 3: Established (MEDIUM priority)
    "UNI",
    "ATOM",
    "NEAR",
    "LTC",
    "BCH",
    "DOGE",
    "FIL",
    "APT",
    "ARB",
    "OP",
    # Tier 4: Mid caps (LOW priority)
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

# Asset-specific start dates (when the asset became available)
ASSET_START_DATES = {
    "BTC": datetime(2017, 1, 1, tzinfo=UTC),
    "ETH": datetime(2017, 1, 1, tzinfo=UTC),
    "LTC": datetime(2017, 1, 1, tzinfo=UTC),
    "SOL": datetime(2020, 4, 10, tzinfo=UTC),
    "BNB": datetime(2017, 7, 25, tzinfo=UTC),
    "ADA": datetime(2017, 10, 1, tzinfo=UTC),
    "DOT": datetime(2020, 8, 22, tzinfo=UTC),
    "AVAX": datetime(2020, 9, 21, tzinfo=UTC),
    "LINK": datetime(2017, 9, 21, tzinfo=UTC),
    "ATOM": datetime(2019, 3, 14, tzinfo=UTC),
    "MATIC": datetime(2019, 4, 26, tzinfo=UTC),
    "UNI": datetime(2020, 9, 17, tzinfo=UTC),
    "NEAR": datetime(2020, 10, 14, tzinfo=UTC),
    "ARB": datetime(2023, 3, 23, tzinfo=UTC),
    "OP": datetime(2022, 6, 1, tzinfo=UTC),
    "APT": datetime(2022, 10, 19, tzinfo=UTC),
    "SUI": datetime(2023, 5, 3, tzinfo=UTC),
    "JUP": datetime(2024, 1, 31, tzinfo=UTC),
    "JTO": datetime(2023, 12, 7, tzinfo=UTC),
    "PYTH": datetime(2023, 11, 20, tzinfo=UTC),
    "W": datetime(2024, 4, 3, tzinfo=UTC),
    "DRIFT": datetime(2024, 5, 16, tzinfo=UTC),
    "ENA": datetime(2024, 4, 2, tzinfo=UTC),
    "SEI": datetime(2023, 8, 15, tzinfo=UTC),
}

# Default start for assets not in the list
DEFAULT_START = datetime(2020, 1, 1, tzinfo=UTC)

# Timeframes to backfill (in order of importance for backtesting)
# 1h is most important, then shorter timeframes for granular testing
BACKFILL_TIMEFRAMES = ["1h", "4h", "1d", "15m", "5m", "1m"]


# Symbol mapping: internal -> exchange format (auto-generated for most)
def get_exchange_symbol(symbol: str, exchange: str) -> str:
    """Get the exchange-specific symbol format."""
    if exchange == "coinbase":
        return f"{symbol}/USD"
    return f"{symbol}/USDT"  # Default for Binance and most others


class BackfillService:
    """
    Service for backfilling historical OHLCV data.

    Uses ccxt to fetch data from multiple exchanges and stores
    in the enhanced_candles table.
    """

    def __init__(
        self,
        exchanges: list[str] | None = None,
        rate_limit_ms: int = 100,
        batch_size: int = 1000,
    ):
        """
        Initialize backfill service.

        Args:
            exchanges: List of exchanges to use (default: ['binance'])
            rate_limit_ms: Minimum ms between API calls
            batch_size: Max candles per API call
        """
        self.exchanges = exchanges or ["binance"]
        self.rate_limit_ms = rate_limit_ms
        self.batch_size = batch_size
        self._exchange_clients: dict[str, ccxt.Exchange] = {}
        self._running = False

    async def _get_exchange(self, exchange_name: str) -> ccxt.Exchange:
        """Get or create exchange client."""
        if exchange_name not in self._exchange_clients:
            if exchange_name == "binance":
                client = ccxt.binanceus(
                    {  # US API (binance.com blocked in US)
                        "enableRateLimit": True,
                        "rateLimit": self.rate_limit_ms,
                    }
                )
            elif exchange_name == "coinbase":
                client = ccxt.coinbase(
                    {
                        "enableRateLimit": True,
                        "rateLimit": self.rate_limit_ms,
                    }
                )
            else:
                raise ValueError(f"Unknown exchange: {exchange_name}")

            self._exchange_clients[exchange_name] = client

        return self._exchange_clients[exchange_name]

    async def close(self):
        """Close all exchange connections."""
        for client in self._exchange_clients.values():
            await client.close()
        self._exchange_clients.clear()

    async def get_data_coverage(
        self,
        symbols: list[str],
        timeframe: str = "1h",
    ) -> dict[str, tuple[datetime | None, datetime | None, int]]:
        """
        Get current data coverage for symbols.

        Returns:
            Dict of symbol -> (earliest_date, latest_date, candle_count)
        """
        coverage = {}

        async with async_session_maker() as session:
            for symbol in symbols:
                stmt = (
                    select(func.min(EnhancedCandle.time), func.max(EnhancedCandle.time), func.count())
                    .where(EnhancedCandle.symbol == symbol)
                    .where(EnhancedCandle.timeframe == timeframe)
                )
                result = await session.exec(stmt)
                row = result.one()
                coverage[symbol] = (row[0], row[1], row[2] or 0)

        return coverage

    async def detect_gaps(
        self,
        symbol: str,
        timeframe: str,
        exchange: str = "binance",
    ) -> list[BackfillTask]:
        """
        Detect gaps in historical data that need backfilling.

        Returns list of BackfillTask objects for missing ranges.
        """
        tasks = []
        priority = BackfillPriority.CRITICAL if symbol in TRIO_ASSETS else BackfillPriority.MEDIUM

        # Get current coverage
        coverage = await self.get_data_coverage([symbol], timeframe)
        earliest, latest, count = coverage.get(symbol, (None, None, 0))

        now = datetime.now(UTC)

        # Get asset-specific start date (when the asset first became available)
        asset_start = ASSET_START_DATES.get(symbol, DEFAULT_START)

        # Target based on timeframe, but never before asset existed
        if timeframe == "1h":
            target_start = max(asset_start, now - timedelta(days=365 * 3))
        elif timeframe == "15m":
            target_start = max(asset_start, now - timedelta(days=365))
        elif timeframe == "4h":
            target_start = max(asset_start, now - timedelta(days=365 * 3))
        elif timeframe == "1d":
            target_start = max(asset_start, now - timedelta(days=365 * 5))
        else:
            target_start = max(asset_start, now - timedelta(days=365))

        target_start_ts = int(target_start.timestamp() * 1000)
        now_ts = int(now.timestamp() * 1000)

        if earliest is None:
            # No data at all - full backfill needed
            logger.info(f"[{symbol}] {timeframe}: No data found, scheduling full backfill")
            tasks.append(
                BackfillTask(
                    symbol=symbol,
                    timeframe=timeframe,
                    exchange=exchange,
                    start_ts=target_start_ts,
                    end_ts=now_ts,
                    priority=priority,
                )
            )
        else:
            earliest_ts = int(earliest.timestamp() * 1000)
            latest_ts = int(latest.timestamp() * 1000)

            # Check if we need older data
            if earliest_ts > target_start_ts:
                gap_days = (earliest_ts - target_start_ts) / (1000 * 60 * 60 * 24)
                logger.info(f"[{symbol}] {timeframe}: Need {gap_days:.0f} days of older data")
                tasks.append(
                    BackfillTask(
                        symbol=symbol,
                        timeframe=timeframe,
                        exchange=exchange,
                        start_ts=target_start_ts,
                        end_ts=earliest_ts,
                        priority=priority,
                    )
                )

            # Check if we need newer data (gap to now)
            # Allow 2 hours of staleness for 1h, 30 mins for 15m
            stale_threshold_ms = 2 * 60 * 60 * 1000 if timeframe == "1h" else 30 * 60 * 1000
            if now_ts - latest_ts > stale_threshold_ms:
                gap_hours = (now_ts - latest_ts) / (1000 * 60 * 60)
                logger.info(f"[{symbol}] {timeframe}: Need {gap_hours:.1f} hours of recent data")
                tasks.append(
                    BackfillTask(
                        symbol=symbol,
                        timeframe=timeframe,
                        exchange=exchange,
                        start_ts=latest_ts,
                        end_ts=now_ts,
                        priority=priority,
                    )
                )

        return tasks

    async def fetch_ohlcv(
        self,
        task: BackfillTask,
    ) -> list[dict]:
        """
        Fetch OHLCV data from exchange for a backfill task.

        Returns list of candle dicts ready for database insert.
        """
        exchange = await self._get_exchange(task.exchange)

        # Get exchange symbol format using the helper function
        exchange_symbol = get_exchange_symbol(task.symbol, task.exchange)

        all_candles = []
        since = task.start_ts

        logger.info(f"Fetching {task.symbol} {task.timeframe} from {task.exchange}...")

        while since < task.end_ts:
            try:
                ohlcv = await exchange.fetch_ohlcv(
                    exchange_symbol,
                    task.timeframe,
                    since=since,
                    limit=self.batch_size,
                )

                if not ohlcv:
                    break

                for candle in ohlcv:
                    ts, o, h, l, c, v = candle
                    if ts >= task.end_ts:
                        break
                    all_candles.append(
                        {
                            "time": datetime.fromtimestamp(ts / 1000, tz=UTC),
                            "symbol": task.symbol,
                            "timeframe": task.timeframe,
                            "exchange": task.exchange,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                        }
                    )

                # Move forward
                since = ohlcv[-1][0] + 1

                # Rate limit
                await asyncio.sleep(self.rate_limit_ms / 1000)

            except Exception as e:
                logger.error(f"Error fetching {task.symbol}: {e}")
                break

        logger.info(f"Fetched {len(all_candles)} candles for {task.symbol} {task.timeframe}")
        return all_candles

    async def store_candles_batch(
        self,
        candles: list[dict],
    ) -> tuple[int, int]:
        """
        Store candles in database using batch insert with ON CONFLICT DO NOTHING.

        Much faster than one-at-a-time inserts (10-100x speedup).

        Returns:
            Tuple of (inserted_count, skipped_count)
        """
        if not candles:
            return 0, 0

        # Batch insert using raw SQL with ON CONFLICT
        async with async_session_maker() as session:
            # Process in batches of 500 to avoid memory issues
            batch_size = 500
            total_inserted = 0

            for i in range(0, len(candles), batch_size):
                batch = candles[i : i + batch_size]

                # Build VALUES clause for batch
                values_list = []
                params = {}
                for j, c in enumerate(batch):
                    prefix = f"p{j}_"
                    values_list.append(
                        f"(:{prefix}time, :{prefix}symbol, :{prefix}timeframe, "
                        f":{prefix}exchange, :{prefix}open, :{prefix}high, "
                        f":{prefix}low, :{prefix}close, :{prefix}volume)"
                    )
                    params[f"{prefix}time"] = c["time"]
                    params[f"{prefix}symbol"] = c["symbol"]
                    params[f"{prefix}timeframe"] = c["timeframe"]
                    params[f"{prefix}exchange"] = c["exchange"]
                    params[f"{prefix}open"] = float(c["open"])
                    params[f"{prefix}high"] = float(c["high"])
                    params[f"{prefix}low"] = float(c["low"])
                    params[f"{prefix}close"] = float(c["close"])
                    params[f"{prefix}volume"] = float(c["volume"])

                sql = text(f"""
                    INSERT INTO enhanced_candles
                        (time, symbol, timeframe, exchange, open, high, low, close, volume)
                    VALUES {", ".join(values_list)}
                    ON CONFLICT (symbol, timeframe, time) DO NOTHING
                """)

                result = await session.execute(sql, params)
                total_inserted += result.rowcount
                await session.commit()

        skipped = len(candles) - total_inserted
        return total_inserted, skipped

    async def store_candles(
        self,
        candles: list[dict],
        session: AsyncSession | None = None,
    ) -> int:
        """
        Store candles using batch insert (wrapper for backward compatibility).

        Returns number of candles inserted.
        """
        inserted, _ = await self.store_candles_batch(candles)
        return inserted

    async def _process_task(
        self,
        task: BackfillTask,
        semaphore: asyncio.Semaphore,
        results: dict[str, int],
    ) -> None:
        """Process a single backfill task with semaphore-controlled concurrency."""
        async with semaphore:
            if not self._running:
                return

            try:
                candles = await self.fetch_ohlcv(task)
                inserted, skipped = await self.store_candles_batch(candles)

                key = f"{task.symbol}_{task.timeframe}"
                results[key] = results.get(key, 0) + inserted

                logger.info(f"[{task.symbol}] {task.timeframe}: +{inserted} inserted, {skipped} skipped")

            except Exception as e:
                logger.error(f"Backfill error for {task.symbol} {task.timeframe}: {e}")

    async def run_backfill(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        concurrent: int = 3,
    ) -> dict[str, int]:
        """
        Run backfill for specified symbols and timeframes.

        Uses asyncio.Semaphore for concurrent downloads within rate limits.

        Args:
            symbols: Symbols to backfill (default: ALL_ASSETS - 60+)
            timeframes: Timeframes to backfill (default: BACKFILL_TIMEFRAMES - all 6)
            concurrent: Maximum concurrent downloads (default: 3)

        Returns:
            Dict of symbol_timeframe -> candles inserted
        """
        symbols = symbols or ALL_ASSETS
        timeframes = timeframes or BACKFILL_TIMEFRAMES

        self._running = True
        results = {}

        logger.info("=" * 60)
        logger.info(f"BACKFILL: {len(symbols)} symbols x {len(timeframes)} timeframes")
        logger.info(f"Concurrent downloads: {concurrent}")
        logger.info("=" * 60)

        # Detect all gaps first
        all_tasks = []
        for symbol in symbols:
            for timeframe in timeframes:
                tasks = await self.detect_gaps(symbol, timeframe)
                all_tasks.extend(tasks)

        # Sort by priority (CRITICAL first)
        all_tasks.sort(key=lambda t: t.priority.value)

        if not all_tasks:
            logger.info("No gaps detected - data is up to date!")
            return results

        logger.info(f"Detected {len(all_tasks)} backfill tasks")

        # Process tasks concurrently with semaphore
        semaphore = asyncio.Semaphore(concurrent)
        tasks = [self._process_task(task, semaphore, results) for task in all_tasks]
        await asyncio.gather(*tasks)

        await self.close()

        # Summary
        total = sum(results.values())
        logger.info("=" * 60)
        logger.info(f"BACKFILL COMPLETE: {total:,} total candles inserted")
        logger.info("=" * 60)

        return results

    def stop(self):
        """Stop running backfill."""
        self._running = False


# Global singleton
backfill_service = BackfillService()


async def startup_backfill(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    background: bool = True,
):
    """
    Run backfill on server startup.

    Args:
        symbols: Symbols to backfill (default: ALL_ASSETS - 60+)
        timeframes: Timeframes to backfill (default: BACKFILL_TIMEFRAMES - all 6)
        background: Run in background task (default: True)
    """
    symbols = symbols or ALL_ASSETS
    timeframes = timeframes or BACKFILL_TIMEFRAMES

    async def _run():
        logger.info("=" * 60)
        logger.info("STARTUP BACKFILL: Checking data coverage...")
        logger.info("=" * 60)

        # Show coverage for trio assets (quick check)
        coverage = await backfill_service.get_data_coverage(list(TRIO_ASSETS), "1h")
        for symbol, (earliest, latest, count) in coverage.items():
            if earliest:
                logger.info(f"  {symbol}: {count:,} candles ({earliest.date()} to {latest.date()})")
            else:
                logger.info(f"  {symbol}: NO DATA")

        # Run backfill for ALL assets and timeframes
        results = await backfill_service.run_backfill(
            symbols=symbols,
            timeframes=timeframes,
        )

        total = sum(results.values())
        logger.info(f"Backfill complete: {total:,} total candles inserted")

    if background:
        asyncio.create_task(_run())
    else:
        await _run()
