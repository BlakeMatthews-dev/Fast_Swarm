"""Coinbase WebSocket client for live trade and order book data."""

import time
from typing import Any

from Fast_Swarm.logging_config_postgres import LogContext, ctx, get_logger

from .base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    NormalizedOrderBook,
    NormalizedTrade,
)

logger = get_logger(__name__)


class CoinbaseWebSocket(BaseWebSocketClient):
    """Coinbase WebSocket client for trades and order book."""

    EXCHANGE_NAME = "coinbase"
    WS_URL = "wss://ws-feed.exchange.coinbase.com"
    PING_INTERVAL = 30.0

    def __init__(self):
        super().__init__()
        self._order_books: dict[str, dict] = {}

    async def _subscribe_trades_impl(self, symbols: list[str]):
        """Subscribe to trade (matches) channel."""
        message = {"type": "subscribe", "product_ids": symbols, "channels": ["matches"]}
        await self._send(message)
        logger.info(
            "Subscribed to trades",
            extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", channels=["matches"], symbols=symbols),
        )

    async def _subscribe_order_book_impl(self, symbols: list[str]):
        """Subscribe to level2 order book channel."""
        message = {"type": "subscribe", "product_ids": symbols, "channels": ["level2_batch"]}
        await self._send(message)
        logger.info(
            "Subscribed to order book",
            extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", channels=["level2_batch"], symbols=symbols),
        )

    async def subscribe_ticker(self, symbols: list[str]):
        """Subscribe to ticker (best bid/ask) updates."""
        self._subscriptions.setdefault("ticker", set()).update(symbols)
        if self.state.value == "connected":
            await self._subscribe_ticker_impl(symbols)

    async def _subscribe_ticker_impl(self, symbols: list[str]):
        """Subscribe to ticker channel for best bid/ask updates."""
        message = {"type": "subscribe", "product_ids": symbols, "channels": ["ticker"]}
        await self._send(message)
        logger.info(
            "Subscribed to ticker",
            extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", channels=["ticker"], symbols=symbols),
        )

    def _parse_message(self, data: dict) -> Any | None:
        """Parse Coinbase WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "match" or msg_type == "last_match":
            return self._parse_trade(data)

        elif msg_type == "ticker":
            return self._parse_ticker(data)

        elif msg_type == "snapshot":
            self._handle_order_book_snapshot(data)
            return self._build_order_book(data.get("product_id"))

        elif msg_type == "l2update":
            self._handle_order_book_update(data)
            return self._build_order_book(data.get("product_id"))

        elif msg_type == "subscriptions":
            logger.info(
                "Subscriptions confirmed",
                extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", channels=data.get("channels", [])),
            )

        elif msg_type == "error":
            logger.error(
                "Coinbase WebSocket error",
                extra=ctx(LogContext.API_ERROR, exchange="coinbase", message=data.get("message")),
            )

        return None

    def _parse_trade(self, data: dict) -> NormalizedTrade:
        """Parse trade message."""
        maker_side = data.get("side", "")
        aggressive_side = "buy" if maker_side == "sell" else "sell"

        time_str = data.get("time", "")
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1000)
        except Exception:
            timestamp = int(time.time() * 1000)

        return NormalizedTrade(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("product_id", ""),
            trade_id=str(data.get("trade_id", "")),
            timestamp=timestamp,
            price=float(data.get("price", 0)),
            size=float(data.get("size", 0)),
            side=aggressive_side,
        )

    def _parse_ticker(self, data: dict) -> BookTickerData | None:
        """Parse ticker message for best bid/ask."""
        time_str = data.get("time", "")
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1000)
        except Exception:
            timestamp = int(time.time() * 1000)

        best_bid = data.get("best_bid")
        best_ask = data.get("best_ask")

        if not best_bid or not best_ask:
            return None

        return BookTickerData(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("product_id", ""),
            timestamp=timestamp,
            best_bid=float(best_bid),
            best_bid_qty=float(data.get("best_bid_size", 0)),
            best_ask=float(best_ask),
            best_ask_qty=float(data.get("best_ask_size", 0)),
        )

    def _handle_order_book_snapshot(self, data: dict):
        """Handle full order book snapshot."""
        symbol = data.get("product_id", "")

        self._order_books[symbol] = {
            "bids": {},
            "asks": {},
        }

        for price, size in data.get("bids", []):
            self._order_books[symbol]["bids"][float(price)] = float(size)

        for price, size in data.get("asks", []):
            self._order_books[symbol]["asks"][float(price)] = float(size)

        logger.debug(
            "Order book snapshot received", extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", asset=symbol)
        )

    def _handle_order_book_update(self, data: dict):
        """Handle order book delta update."""
        symbol = data.get("product_id", "")

        if symbol not in self._order_books:
            logger.warning(
                "Order book update for unknown symbol",
                extra=ctx(LogContext.WS_CONNECTED, exchange="coinbase", asset=symbol),
            )
            return

        for side, price, size in data.get("changes", []):
            price = float(price)
            size = float(size)
            book_side = "bids" if side == "buy" else "asks"

            if size == 0:
                self._order_books[symbol][book_side].pop(price, None)
            else:
                self._order_books[symbol][book_side][price] = size

    def _build_order_book(self, symbol: str) -> NormalizedOrderBook | None:
        """Build normalized order book from internal state."""
        if symbol not in self._order_books:
            return None

        book = self._order_books[symbol]

        bids = sorted([(p, s) for p, s in book["bids"].items()], key=lambda x: x[0], reverse=True)[:20]

        asks = sorted([(p, s) for p, s in book["asks"].items()], key=lambda x: x[0])[:20]

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks,
        )
