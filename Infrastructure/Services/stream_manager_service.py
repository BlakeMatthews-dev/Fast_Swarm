import asyncio
import logging

from Fast_Swarm.exchanges.base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    KlineData,
    NormalizedOrderBook,
    NormalizedTrade,
)
from Fast_Swarm.exchanges.binance_ws import BinanceWebSocket
from Fast_Swarm.exchanges.coinbase_ws import CoinbaseWebSocket
from Fast_Swarm.exchanges.dydx_ws import DydxWebSocket
from Fast_Swarm.exchanges.hyperliquid_ws import HyperliquidWebSocket

logger = logging.getLogger(__name__)


class StreamManagerService:
    """
    Unified WebSocket Stream Manager Service.
    Handles multiple exchange connections and dispatches data to collectors.
    """

    def __init__(self):
        self.clients: dict[str, BaseWebSocketClient] = {
            "binance": BinanceWebSocket(),
            "coinbase": CoinbaseWebSocket(),
            "hyperliquid": HyperliquidWebSocket(),
            "dydx": DydxWebSocket(),
        }
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._callbacks = {
            "trade": [],
            "kline": [],
            "ticker": [],
            "order_book": [],
        }

    def on_trade(self, callback):
        self._callbacks["trade"].append(callback)

    def on_kline(self, callback):
        self._callbacks["kline"].append(callback)

    def on_ticker(self, callback):
        self._callbacks["ticker"].append(callback)

    def on_order_book(self, callback):
        self._callbacks["order_book"].append(callback)

    async def start(self, symbols: dict[str, list[str]]):
        """
        Start all exchange streams.
        symbols: {'binance': ['BTCUSDT'], 'coinbase': ['BTC-USD']}
        """
        self._running = True
        logger.info("Starting StreamManagerService...")

        # Setup callbacks for each client
        for name, client in self.clients.items():
            client.on_trade(self._handle_trade)
            client.on_kline(self._handle_kline)
            client.on_book_ticker(self._handle_ticker)
            client.on_order_book(self._handle_order_book)

            # Subscribe to requested symbols
            if name in symbols:
                await client.subscribe_trades(symbols[name])
                # Only subscribe to klines if the client supports it
                if hasattr(client, "subscribe_klines"):
                    await client.subscribe_klines(symbols[name])
                await client.subscribe_order_book(symbols[name])

            # Run connection in background task
            task = asyncio.create_task(client.connect())
            self._tasks.append(task)

    async def stop(self):
        """Gracefully stop all streams."""
        self._running = False
        for name, client in self.clients.items():
            await client.disconnect()

        for task in self._tasks:
            task.cancel()

        logger.info("StreamManagerService stopped.")

    def _handle_trade(self, trade: NormalizedTrade):
        for cb in self._callbacks["trade"]:
            cb(trade)

    def _handle_kline(self, kline: KlineData):
        for cb in self._callbacks["kline"]:
            cb(kline)

    def _handle_ticker(self, ticker: BookTickerData):
        for cb in self._callbacks["ticker"]:
            cb(ticker)

    def _handle_order_book(self, order_book: NormalizedOrderBook):
        for cb in self._callbacks["order_book"]:
            cb(order_book)

    def get_status(self) -> dict:
        return {name: client.get_status() for name, client in self.clients.items()}
