"""
Crypto.com Exchange WebSocket client for live trade and order book data.

API Documentation: https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html

Endpoints:
- Market Data: wss://stream.crypto.com/exchange/v1/market
- User API: wss://stream.crypto.com/exchange/v1/user

Message format uses JSON with:
- Trade channel: trade.{instrument_name}
- Order book channel: book.{instrument_name}.{depth}
"""

import asyncio
import time
from typing import Any

from Fast_Swarm.logging_config_postgres import LogContext, ctx, get_logger

from .base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    KlineData,
    MarkPriceData,
    NormalizedOrderBook,
    NormalizedTrade,
)

logger = get_logger(__name__)


class CryptoComWebSocket(BaseWebSocketClient):
    """
    Crypto.com Exchange WebSocket client for market data.

    Supports:
    - Trade feeds (aggressor side, price, size)
    - Order book snapshots (10 or 50 levels)
    - Mark price feeds (for perpetuals)
    - Candlestick/kline feeds
    """

    EXCHANGE_NAME = "crypto.com"
    WS_URL = "wss://stream.crypto.com/exchange/v1/market"
    PING_INTERVAL = 30.0  # Crypto.com heartbeat is 30 seconds
    RECONNECT_DELAY = 5.0
    MAX_RECONNECT_ATTEMPTS = 10

    # UAT sandbox for testing
    UAT_WS_URL = "wss://uat-stream.3ona.co/exchange/v1/market"

    def __init__(self, use_sandbox: bool = False):
        """
        Initialize crypto.com WebSocket client.

        Args:
            use_sandbox: If True, connect to UAT sandbox instead of production
        """
        super().__init__()
        if use_sandbox:
            self.WS_URL = self.UAT_WS_URL

        self._request_id = 1
        self._order_books: dict[str, dict] = {}
        self._connected_at: float = 0

    async def connect(self):
        """
        Connect to WebSocket with recommended 1-second delay.

        Crypto.com recommends adding a 1-second sleep after establishing
        connection before sending requests to avoid rate limit issues.
        """
        self._connected_at = time.time()
        await super().connect()

    async def _resubscribe(self):
        """Resubscribe to all channels after reconnect with rate limit delay."""
        # Crypto.com recommends 1-second delay after connection
        await asyncio.sleep(1.0)
        await super()._resubscribe()

    # =========================================================================
    # Subscription Methods
    # =========================================================================

    async def _subscribe_trades_impl(self, symbols: list[str]):
        """
        Subscribe to trade streams.

        Channel format: trade.{instrument_name}
        Example: trade.BTCUSD-PERP, trade.BTC_USDT
        """
        channels = [f"trade.{s}" for s in symbols]
        message = {
            "id": self._request_id,
            "method": "subscribe",
            "params": {
                "channels": channels,
            },
        }
        self._request_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to trades",
            extra=ctx(
                LogContext.WS_CONNECTED,
                exchange=self.EXCHANGE_NAME,
                channels=["trades"],
                symbols=symbols,
            ),
        )

    async def _subscribe_order_book_impl(self, symbols: list[str], depth: int = 10):
        """
        Subscribe to order book depth streams.

        Channel format: book.{instrument_name}.{depth}
        Supported depths: 10, 50

        Args:
            symbols: List of instrument names
            depth: Order book depth (10 or 50)
        """
        channels = [f"book.{s}.{depth}" for s in symbols]
        message = {
            "id": self._request_id,
            "method": "subscribe",
            "params": {
                "channels": channels,
            },
        }
        self._request_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to order book",
            extra=ctx(
                LogContext.WS_CONNECTED,
                exchange=self.EXCHANGE_NAME,
                channels=["order_book"],
                symbols=symbols,
                depth=depth,
            ),
        )

    async def subscribe_mark_price(self, symbols: list[str]):
        """
        Subscribe to mark price updates (perpetuals only).

        Channel format: mark_price.{instrument_name}
        """
        self._subscriptions.setdefault("mark_price", set()).update(symbols)
        if self.state.value == "connected":
            await self._subscribe_mark_price_impl(symbols)

    async def _subscribe_mark_price_impl(self, symbols: list[str]):
        """Subscribe to mark price channel."""
        channels = [f"mark_price.{s}" for s in symbols]
        message = {
            "id": self._request_id,
            "method": "subscribe",
            "params": {
                "channels": channels,
            },
        }
        self._request_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to mark price",
            extra=ctx(
                LogContext.WS_CONNECTED,
                exchange=self.EXCHANGE_NAME,
                channels=["mark_price"],
                symbols=symbols,
            ),
        )

    async def subscribe_klines(self, symbols: list[str], timeframes: list[str] | None = None):
        """
        Subscribe to candlestick/kline streams.

        Channel format: candlestick.{timeframe}.{instrument_name}
        Supported timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 6h, 12h, 1D, 7D, 14D, 1M

        Args:
            symbols: List of instrument names
            timeframes: List of timeframes (defaults to ['1m', '5m', '15m', '1h'])
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h"]

        self._subscriptions.setdefault("klines", set())
        for symbol in symbols:
            for tf in timeframes:
                self._subscriptions["klines"].add(f"{symbol}:{tf}")

        if self.state.value == "connected":
            await self._subscribe_klines_impl(symbols, timeframes)

    async def _subscribe_klines_impl(self, symbols: list[str], timeframes: list[str]):
        """Subscribe to kline channels."""
        channels = []
        for symbol in symbols:
            for tf in timeframes:
                # Crypto.com uses candlestick.{timeframe}.{instrument}
                channels.append(f"candlestick.{tf}.{symbol}")

        message = {
            "id": self._request_id,
            "method": "subscribe",
            "params": {
                "channels": channels,
            },
        }
        self._request_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to klines",
            extra=ctx(
                LogContext.WS_CONNECTED,
                exchange=self.EXCHANGE_NAME,
                channels=["klines"],
                symbols=symbols,
                timeframes=timeframes,
            ),
        )

    # =========================================================================
    # Message Parsing
    # =========================================================================

    def _parse_message(self, data: dict) -> Any | None:
        """
        Parse Crypto.com WebSocket message.

        Message structure:
        {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "...",
                "subscription": "...",
                "channel": "...",
                "data": [...]
            }
        }
        """
        # Check for heartbeat
        if data.get("method") == "public/heartbeat":
            return self._handle_heartbeat(data)

        # Check for subscription response
        result = data.get("result")
        if not result:
            # Handle subscription confirmations or errors
            if "code" in data:
                code = data.get("code", 0)
                if code != 0:
                    logger.warning(
                        "Crypto.com subscription error",
                        extra=ctx(
                            LogContext.API_ERROR,
                            exchange=self.EXCHANGE_NAME,
                            code=code,
                            message=data.get("message"),
                        ),
                    )
            return None

        channel = result.get("channel", "")
        instrument = result.get("instrument_name", "")
        message_data = result.get("data", [])

        if not message_data:
            return None

        # Route to appropriate parser based on channel
        if channel == "trade":
            return self._parse_trade(message_data, instrument)
        elif channel == "book":
            return self._parse_order_book(message_data, instrument)
        elif channel == "book.update":
            return self._parse_order_book_update(message_data, instrument)
        elif channel == "mark_price":
            return self._parse_mark_price(message_data, instrument)
        elif channel.startswith("candlestick"):
            return self._parse_kline(message_data, instrument, channel)

        return None

    def _handle_heartbeat(self, data: dict) -> None:
        """
        Respond to heartbeat message.

        Crypto.com requires response within 5 seconds.
        """
        response = {
            "id": data.get("id"),
            "method": "public/respond-heartbeat",
        }
        # Queue heartbeat response (will be sent asynchronously)
        asyncio.create_task(self._send(response))
        return None

    def _parse_trade(self, data: list, instrument: str) -> NormalizedTrade | None:
        """
        Parse trade message.

        Trade fields:
        - d: Trade ID
        - t: Unix timestamp (milliseconds)
        - p: Price
        - q: Quantity
        - s: Side (BUY or SELL)
        - i: Instrument name
        """
        if not data:
            return None

        # Usually returns array of trades, take most recent
        trade = data[-1] if isinstance(data, list) else data

        side = trade.get("s", "").lower()
        if side not in ("buy", "sell"):
            side = "buy"  # Default

        return NormalizedTrade(
            exchange=self.EXCHANGE_NAME,
            symbol=trade.get("i", instrument),
            trade_id=str(trade.get("d", "")),
            timestamp=int(trade.get("t", 0)),
            price=float(trade.get("p", 0)),
            size=float(trade.get("q", 0)),
            side=side,
        )

    def _parse_order_book(self, data: list, instrument: str) -> NormalizedOrderBook | None:
        """
        Parse order book snapshot message.

        Book fields:
        - asks: [[price, size, count], ...]
        - bids: [[price, size, count], ...]
        - t: Publish timestamp (ms)
        - tt: Last update timestamp (ms)
        - u: Update sequence number
        """
        if not data:
            return None

        book = data[0] if isinstance(data, list) else data

        # Parse bids and asks - crypto.com format: [price, size, count]
        bids = []
        for level in book.get("bids", []):
            if len(level) >= 2:
                price = float(level[0])
                size = float(level[1])
                bids.append((price, size))

        asks = []
        for level in book.get("asks", []):
            if len(level) >= 2:
                price = float(level[0])
                size = float(level[1])
                asks.append((price, size))

        # Store for delta updates
        self._order_books[instrument] = {
            "bids": {str(b[0]): b[1] for b in bids},
            "asks": {str(a[0]): a[1] for a in asks},
            "sequence": book.get("u", 0),
        }

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=instrument,
            timestamp=int(book.get("t", time.time() * 1000)),
            bids=bids,
            asks=asks,
        )

    def _parse_order_book_update(self, data: list, instrument: str) -> NormalizedOrderBook | None:
        """
        Parse order book delta update.

        Applied incrementally to stored snapshot.
        """
        if not data or instrument not in self._order_books:
            return None

        update = data[0] if isinstance(data, list) else data
        stored = self._order_books[instrument]

        # Apply bid updates
        for level in update.get("update", {}).get("bids", []):
            if len(level) >= 2:
                price_str = str(level[0])
                size = float(level[1])
                if size == 0:
                    stored["bids"].pop(price_str, None)
                else:
                    stored["bids"][price_str] = size

        # Apply ask updates
        for level in update.get("update", {}).get("asks", []):
            if len(level) >= 2:
                price_str = str(level[0])
                size = float(level[1])
                if size == 0:
                    stored["asks"].pop(price_str, None)
                else:
                    stored["asks"][price_str] = size

        # Rebuild sorted lists
        bids = [(float(p), s) for p, s in stored["bids"].items()]
        bids.sort(key=lambda x: x[0], reverse=True)

        asks = [(float(p), s) for p, s in stored["asks"].items()]
        asks.sort(key=lambda x: x[0])

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=instrument,
            timestamp=int(update.get("t", time.time() * 1000)),
            bids=bids[:50],  # Limit depth
            asks=asks[:50],
        )

    def _parse_mark_price(self, data: list, instrument: str) -> MarkPriceData | None:
        """
        Parse mark price message (perpetuals).

        Fields:
        - v: Mark price
        - t: Timestamp
        """
        if not data:
            return None

        mp = data[0] if isinstance(data, list) else data

        return MarkPriceData(
            exchange=self.EXCHANGE_NAME,
            symbol=instrument,
            timestamp=int(mp.get("t", time.time() * 1000)),
            mark_price=float(mp.get("v", 0)),
            index_price=float(mp.get("ip", 0)) if mp.get("ip") else None,
            funding_rate=float(mp.get("fr", 0)) if mp.get("fr") else None,
        )

    def _parse_kline(self, data: list, instrument: str, channel: str) -> KlineData | None:
        """
        Parse candlestick/kline message.

        Channel format: candlestick.{timeframe}.{instrument}
        Fields:
        - o: Open
        - h: High
        - l: Low
        - c: Close
        - v: Volume
        - t: Start timestamp
        """
        if not data:
            return None

        kline = data[0] if isinstance(data, list) else data

        # Extract timeframe from channel name
        # Format: candlestick.1m.BTC_USDT
        parts = channel.split(".")
        timeframe = parts[1] if len(parts) > 1 else "1m"

        return KlineData(
            exchange=self.EXCHANGE_NAME,
            symbol=instrument,
            timestamp=int(kline.get("t", 0)),
            timeframe=timeframe,
            open=float(kline.get("o", 0)),
            high=float(kline.get("h", 0)),
            low=float(kline.get("l", 0)),
            close=float(kline.get("c", 0)),
            volume=float(kline.get("v", 0)),
            quote_volume=float(kline.get("vv", 0)) if kline.get("vv") else None,
            is_closed=False,  # Crypto.com doesn't indicate candle close
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Normalize symbol to crypto.com format.

        Crypto.com uses:
        - Spot: BTC_USDT (underscore separator)
        - Perpetual: BTCUSD-PERP

        Args:
            symbol: Symbol in any format (BTCUSDT, BTC/USDT, etc.)

        Returns:
            Crypto.com formatted symbol
        """
        # Remove common separators
        clean = symbol.upper().replace("/", "").replace("-", "")

        # Check if it's a perpetual
        if clean.endswith("PERP"):
            return clean.replace("PERP", "-PERP")

        # For spot, assume USDT quote and add underscore
        if "USDT" in clean:
            base = clean.replace("USDT", "")
            return f"{base}_USDT"
        elif "USD" in clean:
            base = clean.replace("USD", "")
            return f"{base}USD-PERP"  # Assume perpetual for USD

        return symbol  # Return as-is if can't normalize

    def get_status(self) -> dict[str, Any]:
        """Get extended client status."""
        status = super().get_status()
        status.update({
            "order_books_cached": len(self._order_books),
            "request_id": self._request_id,
            "connected_duration_sec": time.time() - self._connected_at if self._connected_at else 0,
        })
        return status
