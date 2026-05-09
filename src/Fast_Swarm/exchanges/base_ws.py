"""
Abstract base class for WebSocket exchange clients.

Provides common functionality for:
- Connection management with auto-reconnect
- Message handling and callbacks
- Heartbeat/ping-pong handling
- Graceful shutdown
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from Fast_Swarm.logging_config_postgres import LogContext, ctx, ctx_exception, get_logger

logger = get_logger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


@dataclass
class NormalizedTrade:
    """Trade normalized across all exchanges."""

    exchange: str
    symbol: str
    trade_id: str
    timestamp: int  # Unix milliseconds
    price: float
    size: float
    side: str  # 'buy' or 'sell' (aggressor side)

    @property
    def signed_size(self) -> float:
        """Positive for buy (aggressor), negative for sell."""
        return self.size if self.side == "buy" else -self.size


@dataclass
class NormalizedOrderBook:
    """Order book normalized across all exchanges."""

    exchange: str
    symbol: str
    timestamp: int
    bids: list[tuple]  # [(price, size), ...]
    asks: list[tuple]  # [(price, size), ...]

    @property
    def mid_price(self) -> float | None:
        if self.bids and self.asks:
            return (self.bids[0][0] + self.asks[0][0]) / 2
        return None

    @property
    def spread_bps(self) -> float | None:
        if self.bids and self.asks and self.mid_price:
            spread = self.asks[0][0] - self.bids[0][0]
            return (spread / self.mid_price) * 10000
        return None

    @property
    def imbalance(self) -> float:
        """Order book imbalance from top 10 levels."""
        bid_vol = sum(size for _, size in self.bids[:10])
        ask_vol = sum(size for _, size in self.asks[:10])
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0


@dataclass
class MarkPriceData:
    """Mark price data from derivatives exchanges."""

    exchange: str
    symbol: str
    timestamp: int
    mark_price: float
    index_price: float | None = None
    funding_rate: float | None = None
    next_funding_time: int | None = None


@dataclass
class BookTickerData:
    """Best bid/ask (book ticker) for fast spread tracking."""

    exchange: str
    symbol: str
    timestamp: int
    best_bid: float
    best_bid_qty: float
    best_ask: float
    best_ask_qty: float

    @property
    def spread_bps(self) -> float:
        """Spread in basis points."""
        mid = (self.best_bid + self.best_ask) / 2
        return ((self.best_ask - self.best_bid) / mid) * 10000 if mid > 0 else 0


@dataclass
class KlineData:
    """OHLCV candlestick data."""

    exchange: str
    symbol: str
    timestamp: int  # Candle open time
    timeframe: str  # '1m', '5m', '15m', '1h', etc.
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None = None
    trades: int | None = None
    is_closed: bool = False


TradeCallback = Callable[[NormalizedTrade], None]
OrderBookCallback = Callable[[NormalizedOrderBook], None]
MarkPriceCallback = Callable[[MarkPriceData], None]
BookTickerCallback = Callable[[BookTickerData], None]
KlineCallback = Callable[[KlineData], None]


class BaseWebSocketClient(ABC):
    """Abstract base class for exchange WebSocket clients."""

    # Override in subclasses
    EXCHANGE_NAME: str = "unknown"
    WS_URL: str = ""
    PING_INTERVAL: float = 30.0
    RECONNECT_DELAY: float = 5.0
    MAX_RECONNECT_ATTEMPTS: int = 10
    COOLDOWN_AFTER_MAX_RETRIES: float = 300.0  # 5 min before retrying after exhausting attempts

    def __init__(self):
        self.state = ConnectionState.DISCONNECTED
        self.ws: WebSocketClientProtocol | None = None
        self._subscriptions: dict[str, set] = {}  # channel -> set of symbols
        self._trade_callbacks: list[TradeCallback] = []
        self._order_book_callbacks: list[OrderBookCallback] = []
        self._mark_price_callbacks: list[MarkPriceCallback] = []
        self._book_ticker_callbacks: list[BookTickerCallback] = []
        self._kline_callbacks: list[KlineCallback] = []
        self._reconnect_count = 0
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._last_message_time = 0

    # ========== Public API ==========

    def on_trade(self, callback: TradeCallback):
        """Register a callback for trade events."""
        self._trade_callbacks.append(callback)

    def on_order_book(self, callback: OrderBookCallback):
        """Register a callback for order book updates."""
        self._order_book_callbacks.append(callback)

    def on_mark_price(self, callback: MarkPriceCallback):
        """Register a callback for mark price updates (derivatives only)."""
        self._mark_price_callbacks.append(callback)

    def on_book_ticker(self, callback: BookTickerCallback):
        """Register a callback for book ticker (best bid/ask) updates."""
        self._book_ticker_callbacks.append(callback)

    def on_kline(self, callback: KlineCallback):
        """Register a callback for kline/candlestick updates."""
        self._kline_callbacks.append(callback)

    COOLDOWN_AFTER_MAX_RETRIES: float = 300.0  # 5 minutes before retrying after exhausting attempts

    async def connect(self):
        """Connect to WebSocket and start message loop. Never dies permanently."""
        self._running = True
        self.state = ConnectionState.CONNECTING

        # Outer loop: ensures connection is retried indefinitely (with cooldowns)
        while self._running:
            # Inner loop: exponential backoff up to MAX_RECONNECT_ATTEMPTS
            while self._running and self._reconnect_count < self.MAX_RECONNECT_ATTEMPTS:
                try:
                    async with websockets.connect(
                        self.WS_URL,
                        ping_interval=self.PING_INTERVAL,
                        ping_timeout=10,
                        close_timeout=5,
                        open_timeout=20,
                        max_size=10 * 1024 * 1024,  # 10MB max message size
                    ) as ws:
                        self.ws = ws
                        self.state = ConnectionState.CONNECTED
                        self._reconnect_count = 0
                        logger.info(
                            "WebSocket connected to %s",
                            self.EXCHANGE_NAME,
                        )

                        # Resubscribe if reconnecting
                        await self._resubscribe()

                        # Start message loop
                        await self._message_loop()

                except websockets.ConnectionClosed as e:
                    logger.warning(
                        "WebSocket %s closed: %s",
                        self.EXCHANGE_NAME,
                        e,
                    )
                    await self._handle_disconnect()

                except (TimeoutError, asyncio.TimeoutError):
                    logger.warning(
                        "WebSocket %s connect timeout (attempt %d/%d)",
                        self.EXCHANGE_NAME,
                        self._reconnect_count + 1,
                        self.MAX_RECONNECT_ATTEMPTS,
                    )
                    await self._handle_disconnect()

                except (OSError, ConnectionError) as e:
                    logger.warning(
                        "WebSocket %s network error: %s (attempt %d/%d)",
                        self.EXCHANGE_NAME,
                        e,
                        self._reconnect_count + 1,
                        self.MAX_RECONNECT_ATTEMPTS,
                    )
                    await self._handle_disconnect()

                except Exception as e:
                    logger.error(
                        "WebSocket %s unexpected error: %s",
                        self.EXCHANGE_NAME,
                        e,
                        exc_info=True,
                    )
                    await self._handle_disconnect()

            # Exhausted MAX_RECONNECT_ATTEMPTS - cooldown then retry
            if self._running:
                logger.warning(
                    "WebSocket %s: %d attempts exhausted, cooling down %.0fs before retry",
                    self.EXCHANGE_NAME,
                    self.MAX_RECONNECT_ATTEMPTS,
                    self.COOLDOWN_AFTER_MAX_RETRIES,
                )
                self.state = ConnectionState.RECONNECTING
                await asyncio.sleep(self.COOLDOWN_AFTER_MAX_RETRIES)
                self._reconnect_count = 0

        self.state = ConnectionState.CLOSED

    async def disconnect(self):
        """Gracefully disconnect."""
        self._running = False
        self.state = ConnectionState.CLOSED

        for task in self._tasks:
            task.cancel()

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info(
            "WebSocket disconnected",
            extra=ctx(LogContext.WS_DISCONNECTED, exchange=self.EXCHANGE_NAME, reason="graceful_disconnect"),
        )

    async def subscribe_trades(self, symbols: list[str]):
        """Subscribe to trade updates for symbols."""
        self._subscriptions.setdefault("trades", set()).update(symbols)
        if self.state == ConnectionState.CONNECTED:
            await self._subscribe_trades_impl(symbols)

    async def subscribe_order_book(self, symbols: list[str]):
        """Subscribe to order book updates for symbols."""
        self._subscriptions.setdefault("order_book", set()).update(symbols)
        if self.state == ConnectionState.CONNECTED:
            await self._subscribe_order_book_impl(symbols)

    # ========== Abstract Methods ==========

    @abstractmethod
    async def _subscribe_trades_impl(self, symbols: list[str]):
        """Send trade subscription message to exchange."""
        pass

    @abstractmethod
    async def _subscribe_order_book_impl(self, symbols: list[str]):
        """Send order book subscription message to exchange."""
        pass

    @abstractmethod
    def _parse_message(self, data: dict) -> Any | None:
        """Parse a message from the exchange."""
        pass

    # ========== Internal Methods ==========

    async def _message_loop(self):
        """Main message receiving loop."""
        try:
            async for message in self.ws:
                self._last_message_time = time.time()

                try:
                    data = json.loads(message)
                    parsed = self._parse_message(data)

                    if isinstance(parsed, NormalizedTrade):
                        for callback in self._trade_callbacks:
                            try:
                                callback(parsed)
                            except Exception as e:
                                logger.error(
                                    "Trade callback error",
                                    extra=ctx_exception(e, function_name="callback", operation="trade_callback"),
                                    exc_info=True,
                                )

                    elif isinstance(parsed, NormalizedOrderBook):
                        for callback in self._order_book_callbacks:
                            try:
                                callback(parsed)
                            except Exception as e:
                                logger.error(
                                    "Order book callback error",
                                    extra=ctx_exception(e, function_name="callback", operation="orderbook_callback"),
                                    exc_info=True,
                                )

                    elif isinstance(parsed, MarkPriceData):
                        for callback in self._mark_price_callbacks:
                            try:
                                callback(parsed)
                            except Exception as e:
                                logger.error(
                                    "Mark price callback error",
                                    extra=ctx_exception(e, function_name="callback", operation="markprice_callback"),
                                    exc_info=True,
                                )

                    elif isinstance(parsed, BookTickerData):
                        for callback in self._book_ticker_callbacks:
                            try:
                                callback(parsed)
                            except Exception as e:
                                logger.error(
                                    "Book ticker callback error",
                                    extra=ctx_exception(e, function_name="callback", operation="bookticker_callback"),
                                    exc_info=True,
                                )

                    elif isinstance(parsed, KlineData):
                        for callback in self._kline_callbacks:
                            try:
                                callback(parsed)
                            except Exception as e:
                                logger.error(
                                    "Kline callback error",
                                    extra=ctx_exception(e, function_name="callback", operation="kline_callback"),
                                    exc_info=True,
                                )

                except json.JSONDecodeError:
                    logger.warning(
                        "Non-JSON WebSocket message", extra=ctx(LogContext.API_ERROR, exchange=self.EXCHANGE_NAME)
                    )
                except Exception as e:
                    logger.error(
                        "Message processing error",
                        extra=ctx_exception(e, function_name="_message_loop", exchange=self.EXCHANGE_NAME),
                        exc_info=True,
                    )

        except asyncio.CancelledError:
            logger.info(
                "Message loop cancelled",
                extra=ctx(LogContext.WS_DISCONNECTED, exchange=self.EXCHANGE_NAME, reason="cancelled"),
            )
            raise

    async def _handle_disconnect(self):
        """Handle disconnection with backoff."""
        self.state = ConnectionState.RECONNECTING
        self._reconnect_count += 1
        delay = min(self.RECONNECT_DELAY * (2 ** (self._reconnect_count - 1)), 60)
        logger.info(
            "Reconnecting to WebSocket",
            extra=ctx(
                LogContext.WS_DISCONNECTED,
                exchange=self.EXCHANGE_NAME,
                delay=delay,
                attempt=self._reconnect_count,
                action="reconnecting",
            ),
        )
        await asyncio.sleep(delay)

    async def _resubscribe(self):
        """Resubscribe to all channels after reconnect."""
        if "trades" in self._subscriptions:
            await self._subscribe_trades_impl(list(self._subscriptions["trades"]))
        if "order_book" in self._subscriptions:
            await self._subscribe_order_book_impl(list(self._subscriptions["order_book"]))

    async def _send(self, message: dict):
        """Send a JSON message."""
        if self.ws and self.state == ConnectionState.CONNECTED:
            await self.ws.send(json.dumps(message))

    # ========== Utility Methods ==========

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    @property
    def seconds_since_last_message(self) -> float:
        return time.time() - self._last_message_time if self._last_message_time else float("inf")

    def get_status(self) -> dict[str, Any]:
        """Get client status."""
        return {
            "exchange": self.EXCHANGE_NAME,
            "state": self.state.value,
            "subscriptions": {k: list(v) for k, v in self._subscriptions.items()},
            "reconnect_count": self._reconnect_count,
            "seconds_since_last_message": self.seconds_since_last_message,
        }
