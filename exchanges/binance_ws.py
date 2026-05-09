"""Binance WebSocket client for live trade and order book data."""

import time
from typing import Any

from Fast_Swarm.logging_config_postgres import LogContext, ctx, get_logger

from .base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    KlineData,
    NormalizedOrderBook,
    NormalizedTrade,
)

logger = get_logger(__name__)


class BinanceWebSocket(BaseWebSocketClient):
    """Binance WebSocket client for trades and order book."""

    EXCHANGE_NAME = "binance"
    WS_URL = "wss://stream.binance.us:9443/ws"
    PING_INTERVAL = 20.0

    def __init__(self, use_global: bool = False):
        super().__init__()
        if use_global:
            self.WS_URL = "wss://stream.binance.com:9443/ws"
        self._order_books: dict[str, dict] = {}
        self._stream_id = 1

    def _get_stream_url(self, streams: list[str]) -> str:
        """Build combined stream URL."""
        base = self.WS_URL.replace("/ws", "")
        if len(streams) == 1:
            return f"{base}/ws/{streams[0]}"
        else:
            combined = "/".join(streams)
            return f"{base}/stream?streams={combined}"

    async def _subscribe_trades_impl(self, symbols: list[str]):
        """Subscribe to trade streams."""
        streams = [f"{s.lower()}@trade" for s in symbols]
        message = {"method": "SUBSCRIBE", "params": streams, "id": self._stream_id}
        self._stream_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to trades",
            extra=ctx(LogContext.WS_CONNECTED, exchange="binance", channels=["trades"], symbols=symbols),
        )

    async def _subscribe_order_book_impl(self, symbols: list[str]):
        """Subscribe to order book depth streams."""
        streams = [f"{s.lower()}@depth20@100ms" for s in symbols]
        message = {"method": "SUBSCRIBE", "params": streams, "id": self._stream_id}
        self._stream_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to order book",
            extra=ctx(LogContext.WS_CONNECTED, exchange="binance", channels=["order_book"], symbols=symbols),
        )

    async def subscribe_book_ticker(self, symbols: list[str]):
        """Subscribe to book ticker (best bid/ask) updates."""
        self._subscriptions.setdefault("book_ticker", set()).update(symbols)
        if self.state.value == "connected":
            await self._subscribe_book_ticker_impl(symbols)

    async def _subscribe_book_ticker_impl(self, symbols: list[str]):
        """Subscribe to book ticker stream."""
        streams = [f"{s.lower()}@bookTicker" for s in symbols]
        message = {"method": "SUBSCRIBE", "params": streams, "id": self._stream_id}
        self._stream_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to book ticker",
            extra=ctx(LogContext.WS_CONNECTED, exchange="binance", channels=["book_ticker"], symbols=symbols),
        )

    async def subscribe_klines(self, symbols: list[str], timeframes: list[str] = None):
        """Subscribe to kline/candlestick streams."""
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h"]

        self._subscriptions.setdefault("klines", set())
        for symbol in symbols:
            for tf in timeframes:
                self._subscriptions["klines"].add(f"{symbol}:{tf}")

        if self.state.value == "connected":
            await self._subscribe_klines_impl(symbols, timeframes)

    async def _subscribe_klines_impl(self, symbols: list[str], timeframes: list[str]):
        """Subscribe to kline streams."""
        streams = []
        for symbol in symbols:
            for tf in timeframes:
                streams.append(f"{symbol.lower()}@kline_{tf}")

        message = {"method": "SUBSCRIBE", "params": streams, "id": self._stream_id}
        self._stream_id += 1
        await self._send(message)
        logger.info(
            "Subscribed to klines",
            extra=ctx(
                LogContext.WS_CONNECTED, exchange="binance", channels=["klines"], symbols=symbols, timeframes=timeframes
            ),
        )

    def _parse_message(self, data: dict) -> Any | None:
        """Parse Binance WebSocket message."""
        if "stream" in data:
            stream = data.get("stream", "")
            data = data.get("data", {})

            if "@trade" in stream:
                return self._parse_trade(data)
            elif "@depth" in stream:
                return self._parse_order_book(data)
            elif "@bookTicker" in stream:
                return self._parse_book_ticker(data)
            elif "@kline" in stream:
                return self._parse_kline(data)

        event_type = data.get("e")

        if event_type == "trade":
            return self._parse_trade(data)
        elif event_type == "depthUpdate":
            return self._parse_order_book(data)
        elif event_type == "bookTicker" or ("b" in data and "a" in data and "s" in data and "e" not in data):
            return self._parse_book_ticker(data)
        elif event_type == "kline":
            return self._parse_kline(data)

        if "result" in data and data.get("id"):
            logger.debug(
                "Subscription response received",
                extra=ctx(LogContext.WS_CONNECTED, exchange="binance", response_id=data.get("id")),
            )

        return None

    def _parse_trade(self, data: dict) -> NormalizedTrade:
        """Parse trade message."""
        is_buyer_maker = data.get("m", False)
        aggressive_side = "sell" if is_buyer_maker else "buy"

        return NormalizedTrade(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("s", ""),
            trade_id=str(data.get("t", "")),
            timestamp=int(data.get("T", 0)),
            price=float(data.get("p", 0)),
            size=float(data.get("q", 0)),
            side=aggressive_side,
        )

    def _parse_order_book(self, data: dict) -> NormalizedOrderBook:
        """Parse order book depth message."""
        symbol = data.get("s", "")

        bids = [(float(price), float(size)) for price, size in data.get("bids", [])]

        asks = [(float(price), float(size)) for price, size in data.get("asks", [])]

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks,
        )

    def _parse_book_ticker(self, data: dict) -> BookTickerData:
        """Parse book ticker (best bid/ask) message."""
        best_bid = float(data.get("b", 0))
        best_ask = float(data.get("a", 0))

        return BookTickerData(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("s", ""),
            timestamp=int(time.time() * 1000),
            best_bid=best_bid,
            best_bid_qty=float(data.get("B", 0)),
            best_ask=best_ask,
            best_ask_qty=float(data.get("A", 0)),
        )

    def _parse_kline(self, data: dict) -> KlineData:
        """Parse kline/candlestick message."""
        kline = data.get("k", {})

        return KlineData(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("s", kline.get("s", "")),
            timestamp=int(kline.get("t", 0)),
            timeframe=kline.get("i", "1m"),
            open=float(kline.get("o", 0)),
            high=float(kline.get("h", 0)),
            low=float(kline.get("l", 0)),
            close=float(kline.get("c", 0)),
            volume=float(kline.get("v", 0)),
            quote_volume=float(kline.get("q", 0)) if kline.get("q") else None,
            trades=int(kline.get("n", 0)) if kline.get("n") else None,
            is_closed=bool(kline.get("x", False)),
        )
