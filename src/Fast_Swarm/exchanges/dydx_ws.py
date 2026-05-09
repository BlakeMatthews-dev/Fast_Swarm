"""dYdX v4 WebSocket client for live trade and order book data."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from Fast_Swarm.logging_config_postgres import LogContext, ctx, ctx_exception, get_logger

from .base_ws import (
    BaseWebSocketClient,
    MarkPriceData,
    NormalizedOrderBook,
    NormalizedTrade,
)

logger = get_logger(__name__)


@dataclass
class FundingData:
    """Funding rate data from dYdX."""

    symbol: str
    rate: float
    timestamp: int


@dataclass
class OpenInterestData:
    """Open interest data from dYdX."""

    symbol: str
    oi_usd: float
    timestamp: int


FundingCallback = Callable[[FundingData], None]
OICallback = Callable[[OpenInterestData], None]


class DydxWebSocket(BaseWebSocketClient):
    """dYdX v4 WebSocket client for trades, order book, funding, and OI."""

    EXCHANGE_NAME = "dydx"
    WS_URL = "wss://indexer.dydx.trade/v4/ws"
    REST_URL = "https://indexer.dydx.trade/v4"
    PING_INTERVAL = 30.0

    def __init__(self):
        super().__init__()
        self._order_books: dict[str, dict] = {}
        self._funding_callbacks: list[FundingCallback] = []
        self._oi_callbacks: list[OICallback] = []
        self._polling_task: asyncio.Task | None = None
        self._poll_interval = 60

    def on_funding(self, callback: FundingCallback):
        """Register callback for funding rate updates."""
        self._funding_callbacks.append(callback)

    def on_open_interest(self, callback: OICallback):
        """Register callback for open interest updates."""
        self._oi_callbacks.append(callback)

    async def start_polling(self, symbols: list[str]):
        """Start polling for funding rates and OI."""
        if self._polling_task:
            self._polling_task.cancel()

        self._polling_task = asyncio.create_task(self._poll_loop(symbols))
        logger.info("Started REST polling", extra=ctx(LogContext.WS_CONNECTED, exchange="dydx", symbols=symbols))

    async def _poll_loop(self, symbols: list[str]):
        """Background loop to poll REST API."""
        while True:
            try:
                await self._fetch_markets_data(symbols)
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Polling error",
                    extra=ctx_exception(e, function_name="_poll_loop", operation="fetch_markets_data"),
                    exc_info=True,
                )
                await asyncio.sleep(10)

    async def _fetch_markets_data(self, symbols: list[str]):
        """Fetch funding rates and OI from REST API."""
        try:
            async with aiohttp.ClientSession() as session, session.get(f"{self.REST_URL}/perpetualMarkets") as resp:
                if resp.status != 200:
                    logger.error(
                        "REST API error", extra=ctx(LogContext.API_ERROR, exchange="dydx", status_code=resp.status)
                    )
                    return

                data = await resp.json()

            timestamp = int(time.time() * 1000)
            markets = data.get("markets", {})

            for market_id, market in markets.items():
                if market_id not in symbols:
                    continue

                # Funding rate (hourly)
                funding_rate = float(market.get("nextFundingRate", 0))
                funding_data = FundingData(
                    symbol=market_id,
                    rate=funding_rate,
                    timestamp=timestamp,
                )
                for callback in self._funding_callbacks:
                    try:
                        callback(funding_data)
                    except Exception as e:
                        logger.error(
                            "Funding callback error",
                            extra=ctx_exception(e, function_name="_fetch_markets_data", operation="funding_callback"),
                            exc_info=True,
                        )

                # Open interest
                oi = float(market.get("openInterest", 0))
                oracle_price = float(market.get("oraclePrice", 0))
                oi_usd = oi * oracle_price

                oi_data = OpenInterestData(
                    symbol=market_id,
                    oi_usd=oi_usd,
                    timestamp=timestamp,
                )
                for callback in self._oi_callbacks:
                    try:
                        callback(oi_data)
                    except Exception as e:
                        logger.error(
                            "OI callback error",
                            extra=ctx_exception(e, function_name="_fetch_markets_data", operation="oi_callback"),
                            exc_info=True,
                        )

                # Mark price (oracle price in dYdX)
                if oracle_price > 0:
                    mark_data = MarkPriceData(
                        exchange=self.EXCHANGE_NAME,
                        symbol=market_id,
                        timestamp=timestamp,
                        mark_price=oracle_price,
                        funding_rate=funding_rate,
                    )
                    for callback in self._mark_price_callbacks:
                        try:
                            callback(mark_data)
                        except Exception as e:
                            logger.error(
                                "Mark price callback error",
                                extra=ctx_exception(
                                    e, function_name="_fetch_markets_data", operation="markprice_callback"
                                ),
                                exc_info=True,
                            )

        except Exception as e:
            logger.error(
                "REST fetch error",
                extra=ctx_exception(e, function_name="_fetch_markets_data", operation="rest_fetch"),
                exc_info=True,
            )

    async def _subscribe_trades_impl(self, symbols: list[str]):
        """Subscribe to trade streams."""
        for symbol in symbols:
            message = {"type": "subscribe", "channel": "v4_trades", "id": symbol}
            await self._send(message)
        logger.info(
            "Subscribed to trades",
            extra=ctx(LogContext.WS_CONNECTED, exchange="dydx", channels=["v4_trades"], symbols=symbols),
        )

    async def _subscribe_order_book_impl(self, symbols: list[str]):
        """Subscribe to order book streams."""
        for symbol in symbols:
            message = {"type": "subscribe", "channel": "v4_orderbook", "id": symbol}
            await self._send(message)
        logger.info(
            "Subscribed to order book",
            extra=ctx(LogContext.WS_CONNECTED, exchange="dydx", channels=["v4_orderbook"], symbols=symbols),
        )

    def _parse_message(self, data: dict) -> Any | None:
        """Parse dYdX WebSocket message."""
        msg_type = data.get("type")
        channel = data.get("channel")

        if msg_type == "channel_data":
            if channel == "v4_trades":
                contents = data.get("contents", {})
                trades = contents.get("trades", [])
                if trades:
                    return self._parse_trade(trades[-1], data.get("id", ""))

            elif channel == "v4_orderbook":
                return self._parse_order_book(data)

        elif msg_type == "subscribed":
            logger.debug(
                "Subscribed to channel",
                extra=ctx(LogContext.WS_CONNECTED, exchange="dydx", channel=data.get("channel")),
            )

        elif msg_type == "error":
            logger.error(
                "WebSocket error", extra=ctx(LogContext.API_ERROR, exchange="dydx", message=data.get("message"))
            )

        return None

    def _parse_trade(self, data: dict, symbol: str) -> NormalizedTrade:
        """Parse trade message."""
        side_raw = data.get("side", "BUY")
        side = "buy" if side_raw == "BUY" else "sell"

        created_at = data.get("createdAt", "")
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1000)
        except Exception:
            timestamp = int(time.time() * 1000)

        return NormalizedTrade(
            exchange=self.EXCHANGE_NAME,
            symbol=symbol,
            trade_id=str(data.get("id", "")),
            timestamp=timestamp,
            price=float(data.get("price", 0)),
            size=float(data.get("size", 0)),
            side=side,
        )

    def _parse_order_book(self, data: dict) -> NormalizedOrderBook:
        """Parse order book message."""
        symbol = data.get("id", "")
        contents = data.get("contents", {})

        bids = []
        for level in contents.get("bids", []):
            bids.append((float(level.get("price", 0)), float(level.get("size", 0))))

        asks = []
        for level in contents.get("asks", []):
            asks.append((float(level.get("price", 0)), float(level.get("size", 0))))

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bids=bids[:20],
            asks=asks[:20],
        )

    async def disconnect(self):
        """Disconnect and stop polling."""
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        await super().disconnect()
