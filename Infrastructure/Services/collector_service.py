import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from ..Models.exchange_models import Trade
from ..Models.market_data_models import Candle, ExchangeTick, OrderBookSnapshot
from .market_data_service import MarketDataService

# Import normalized data structures from WebSocket layer
try:
    from Fast_Swarm.exchanges.base_ws import KlineData, NormalizedOrderBook, NormalizedTrade
except ImportError:
    # Fallback for when imports fail (testing, etc.)
    NormalizedTrade = Any
    NormalizedOrderBook = Any
    KlineData = Any

logger = logging.getLogger(__name__)


class DataCollectorService:
    """
    Data Collector Service.
    Aggregates live streams into OHLCV candles across multiple timeframes.
    Handles startup backfilling and database batching.
    """

    TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.market_service = MarketDataService()
        self._pending_candles: dict[str, Candle] = {}  # "(exchange, symbol, tf)" -> Candle
        self._write_queue_candles: list[Candle] = []
        self._write_queue_trades: list[Trade] = []
        self._write_queue_ticks: list[ExchangeTick] = []
        self._write_queue_orderbooks: list[OrderBookSnapshot] = []
        self._batch_size = 50
        self._tick_batch_size = 100  # Higher batch for high-frequency tick data

        # Track current minute candles being built from ticks
        # Key: "(exchange, symbol)" -> {"open": float, "high": float, "low": float, "close": float, "volume": float, "minute_ts": int}
        self._minute_candles: dict[str, dict] = {}

    async def verify_and_backfill(self, symbols: dict[str, list[str]]):
        """
        Check for gaps in historical data and run backfillers.
        """
        logger.info("Initializing Data Health Check...")
        for exchange, asset_list in symbols.items():
            for asset in asset_list:
                await self._check_asset_gaps(exchange, asset)
        logger.info("Data Health Check Complete.")

    async def _check_asset_gaps(self, exchange: str, asset: str):
        """Check for gaps in the last 24h for a specific asset."""
        # Simple implementation: check if we have any data in the last 1h
        now = int(datetime.utcnow().timestamp())
        async with self.session_factory() as session:
            latest = await self.market_service.get_recent_candles(session, asset, "1m", limit=1)
            if not latest or latest[0].timestamp < now - 3600:
                logger.warning(f"Gap detected for {exchange}:{asset}. Triggering backfill...")
                await self._trigger_backfill(exchange, asset, "1m")

    async def _trigger_backfill(self, exchange: str, asset: str, timeframe: str):
        """Simulate/Trigger external backfill script."""
        # In a real integrated system, this would call a method on backfiller_service
        logger.info(f"Backfilling {asset} on {exchange} for {timeframe}...")

    def handle_live_trade(self, trade_data: "NormalizedTrade"):
        """
        Process a live trade from StreamManager.

        Does two things:
        1. Queues the raw tick for batch write to exchange_ticks table
        2. Updates/creates the current 1-minute candle from ticks

        Args:
            trade_data: NormalizedTrade from WebSocket layer
        """
        # 1. Queue raw tick for batch write
        tick = ExchangeTick(
            exchange=trade_data.exchange,
            symbol=trade_data.symbol,
            trade_id=trade_data.trade_id,
            time=datetime.fromtimestamp(trade_data.timestamp / 1000, tz=UTC),
            price=trade_data.price,
            size=trade_data.size,
            side=trade_data.side,
        )
        self._write_queue_ticks.append(tick)

        # Check if we need to flush tick batch
        if len(self._write_queue_ticks) >= self._tick_batch_size:
            asyncio.create_task(self._flush_tick_batch())

        # 2. Build 1-minute candle from ticks
        key = f"{trade_data.exchange}:{trade_data.symbol}"
        trade_minute = (trade_data.timestamp // 60000) * 60  # Floor to minute (seconds)

        if key not in self._minute_candles:
            # Start new candle
            self._minute_candles[key] = {
                "exchange": trade_data.exchange,
                "symbol": trade_data.symbol,
                "open": trade_data.price,
                "high": trade_data.price,
                "low": trade_data.price,
                "close": trade_data.price,
                "volume": trade_data.size,
                "minute_ts": trade_minute,
                "trade_count": 1,
                "buy_volume": trade_data.size if trade_data.side == "buy" else 0,
                "sell_volume": trade_data.size if trade_data.side == "sell" else 0,
            }
        else:
            candle = self._minute_candles[key]

            # Check if we've moved to a new minute
            if trade_minute > candle["minute_ts"]:
                # Close the old candle and queue for write
                self._finalize_minute_candle(key, candle)

                # Start new candle
                self._minute_candles[key] = {
                    "exchange": trade_data.exchange,
                    "symbol": trade_data.symbol,
                    "open": trade_data.price,
                    "high": trade_data.price,
                    "low": trade_data.price,
                    "close": trade_data.price,
                    "volume": trade_data.size,
                    "minute_ts": trade_minute,
                    "trade_count": 1,
                    "buy_volume": trade_data.size if trade_data.side == "buy" else 0,
                    "sell_volume": trade_data.size if trade_data.side == "sell" else 0,
                }
            else:
                # Update current candle
                candle["high"] = max(candle["high"], trade_data.price)
                candle["low"] = min(candle["low"], trade_data.price)
                candle["close"] = trade_data.price
                candle["volume"] += trade_data.size
                candle["trade_count"] += 1
                if trade_data.side == "buy":
                    candle["buy_volume"] += trade_data.size
                else:
                    candle["sell_volume"] += trade_data.size

    def _finalize_minute_candle(self, key: str, candle: dict):
        """Convert accumulated tick data into a Candle and queue for write."""
        finished_candle = Candle(
            exchange=candle["exchange"],
            asset=candle["symbol"],
            timeframe="1m",
            timestamp=candle["minute_ts"],
            open=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
            volume=candle["volume"],
            is_closed=True,
        )
        self._write_queue_candles.append(finished_candle)

        # Log for visibility
        logger.debug(
            f"Finalized 1m candle: {candle['symbol']} "
            f"O={candle['open']:.2f} H={candle['high']:.2f} "
            f"L={candle['low']:.2f} C={candle['close']:.2f} V={candle['volume']:.4f}"
        )

        # Trigger aggregation to higher timeframes
        asyncio.create_task(self._aggregate_to_higher_timeframes(finished_candle))

    async def _flush_tick_batch(self):
        """Flush queued ticks to database."""
        if not self._write_queue_ticks:
            return

        # FIX: Atomic swap to prevent race condition (RACE-003)
        ticks_to_write, self._write_queue_ticks = self._write_queue_ticks, []

        try:
            async with self.session_factory() as session:
                for tick in ticks_to_write:
                    session.add(tick)
                await session.commit()
                logger.debug(f"Flushed {len(ticks_to_write)} ticks to exchange_ticks")
        except Exception as e:
            logger.error(f"Failed to flush ticks: {e}")
            # FIX: Bounded re-queue to prevent OOM on persistent failures (LEAK-003)
            MAX_QUEUE_SIZE = 10000
            combined = ticks_to_write + self._write_queue_ticks
            self._write_queue_ticks = combined[-MAX_QUEUE_SIZE:]  # Keep newest
            if len(combined) > MAX_QUEUE_SIZE:
                logger.warning(f"Tick queue overflow: dropped {len(combined) - MAX_QUEUE_SIZE} old ticks")

    def handle_live_kline(self, kline_data: "KlineData"):
        """
        Process a live kline from StreamManager.

        Handles kline data directly from exchange websocket (more efficient than
        building from ticks when exchange provides kline streams).

        Args:
            kline_data: KlineData from WebSocket layer
        """
        key = f"{kline_data.exchange}:{kline_data.symbol}:{kline_data.timeframe}"

        # Create or update pending candle
        candle = Candle(
            exchange=kline_data.exchange,
            asset=kline_data.symbol,
            timeframe=kline_data.timeframe,
            timestamp=kline_data.timestamp,
            open=kline_data.open,
            high=kline_data.high,
            low=kline_data.low,
            close=kline_data.close,
            volume=kline_data.volume,
            quote_volume=kline_data.quote_volume,
            is_closed=kline_data.is_closed,
        )

        if kline_data.is_closed:
            # Candle is complete - queue for write
            self._write_queue_candles.append(candle)

            # Remove from pending if exists
            if key in self._pending_candles:
                del self._pending_candles[key]

            # Trigger aggregation to higher timeframes for 1m candles
            if kline_data.timeframe == "1m":
                asyncio.create_task(self._aggregate_to_higher_timeframes(candle))

            # Check if we need to flush
            if len(self._write_queue_candles) >= self._batch_size:
                asyncio.create_task(self._flush_batches())

            logger.debug(
                f"Closed kline: {kline_data.symbol} {kline_data.timeframe} "
                f"O={kline_data.open:.2f} H={kline_data.high:.2f} "
                f"L={kline_data.low:.2f} C={kline_data.close:.2f}"
            )
        else:
            # Candle still forming - update pending
            self._pending_candles[key] = candle

    def handle_order_book(self, order_book_data: "NormalizedOrderBook"):
        """
        Process a live order book snapshot from StreamManager.

        Stores L2 order book snapshots with computed metrics (imbalance, spread).

        Args:
            order_book_data: NormalizedOrderBook from WebSocket layer
        """
        # Calculate top 10 level volumes
        bid_vol_10 = sum(size for _, size in order_book_data.bids[:10])
        ask_vol_10 = sum(size for _, size in order_book_data.asks[:10])

        snapshot = OrderBookSnapshot(
            exchange=order_book_data.exchange,
            symbol=order_book_data.symbol,
            timestamp=order_book_data.timestamp,
            bid_vol_10=bid_vol_10,
            ask_vol_10=ask_vol_10,
            imbalance=order_book_data.imbalance,
            spread_bps=order_book_data.spread_bps,
            mid_price=order_book_data.mid_price,
            created_at=datetime.now(UTC),
        )

        self._write_queue_orderbooks.append(snapshot)

        # Flush if batch full
        if len(self._write_queue_orderbooks) >= self._batch_size:
            asyncio.create_task(self._flush_orderbook_batch())

    async def _flush_orderbook_batch(self):
        """Flush queued order book snapshots to database."""
        if not self._write_queue_orderbooks:
            return

        snapshots_to_write = self._write_queue_orderbooks[:]
        self._write_queue_orderbooks = []

        try:
            async with self.session_factory() as session:
                for snapshot in snapshots_to_write:
                    session.add(snapshot)
                await session.commit()
                logger.debug(f"Flushed {len(snapshots_to_write)} order book snapshots")
        except Exception as e:
            logger.error(f"Failed to flush order book snapshots: {e}")
            # Re-queue failed snapshots
            self._write_queue_orderbooks = snapshots_to_write + self._write_queue_orderbooks

    async def _aggregate_to_higher_timeframes(self, candle_1m: Candle):
        """
        Aggregate a closed 1m candle into higher timeframes (5m, 15m, 1h, 4h, 1d).

        Uses the TIMEFRAMES dict to determine aggregation boundaries.
        """
        for tf, seconds in self.TIMEFRAMES.items():
            if tf == "1m":
                continue  # Skip 1m - that's what we're aggregating from

            # Calculate the timeframe bucket this 1m candle belongs to
            tf_bucket = (candle_1m.timestamp // seconds) * seconds
            key = f"{candle_1m.exchange}:{candle_1m.asset}:{tf}"

            if key not in self._pending_candles:
                # Start new higher timeframe candle
                self._pending_candles[key] = Candle(
                    exchange=candle_1m.exchange,
                    asset=candle_1m.asset,
                    timeframe=tf,
                    timestamp=tf_bucket,
                    open=candle_1m.open,
                    high=candle_1m.high,
                    low=candle_1m.low,
                    close=candle_1m.close,
                    volume=candle_1m.volume or 0,
                    is_closed=False,
                )
            else:
                pending = self._pending_candles[key]

                # Check if this 1m candle belongs to a new bucket
                if tf_bucket > pending.timestamp:
                    # Close the old candle
                    pending.is_closed = True
                    self._write_queue_candles.append(pending)

                    # Start new candle
                    self._pending_candles[key] = Candle(
                        exchange=candle_1m.exchange,
                        asset=candle_1m.asset,
                        timeframe=tf,
                        timestamp=tf_bucket,
                        open=candle_1m.open,
                        high=candle_1m.high,
                        low=candle_1m.low,
                        close=candle_1m.close,
                        volume=candle_1m.volume or 0,
                        is_closed=False,
                    )
                else:
                    # Update existing candle
                    pending.high = max(pending.high, candle_1m.high)
                    pending.low = min(pending.low, candle_1m.low)
                    pending.close = candle_1m.close
                    pending.volume = (pending.volume or 0) + (candle_1m.volume or 0)

    async def _flush_batches(self):
        """Periodically flush all write queues to database."""
        has_data = (
            self._write_queue_candles
            or self._write_queue_trades
            or self._write_queue_ticks
            or self._write_queue_orderbooks
        )
        if not has_data:
            return

        # Take snapshots and clear queues
        candles = self._write_queue_candles[:]
        trades = self._write_queue_trades[:]
        ticks = self._write_queue_ticks[:]
        orderbooks = self._write_queue_orderbooks[:]

        self._write_queue_candles = []
        self._write_queue_trades = []
        self._write_queue_ticks = []
        self._write_queue_orderbooks = []

        try:
            async with self.session_factory() as session:
                for c in candles:
                    session.add(c)
                for t in trades:
                    session.add(t)
                for tick in ticks:
                    session.add(tick)
                for ob in orderbooks:
                    session.add(ob)

                await session.commit()
                logger.debug(
                    f"Flushed batches: {len(candles)} candles, "
                    f"{len(trades)} trades, {len(ticks)} ticks, "
                    f"{len(orderbooks)} orderbooks"
                )
        except Exception as e:
            logger.error(f"Failed to flush batches: {e}")
            # Re-queue all failed items
            self._write_queue_candles = candles + self._write_queue_candles
            self._write_queue_trades = trades + self._write_queue_trades
            self._write_queue_ticks = ticks + self._write_queue_ticks
            self._write_queue_orderbooks = orderbooks + self._write_queue_orderbooks

    async def flush_all(self):
        """Force flush all pending data (call on shutdown)."""
        # Finalize any in-progress minute candles
        for key, candle_data in list(self._minute_candles.items()):
            self._finalize_minute_candle(key, candle_data)
        self._minute_candles.clear()

        # Close any pending higher-timeframe candles
        for key, candle in list(self._pending_candles.items()):
            candle.is_closed = True
            self._write_queue_candles.append(candle)
        self._pending_candles.clear()

        # Flush everything
        await self._flush_batches()
        logger.info("Flushed all pending collector data")
