"""Hyperliquid WebSocket client for live trade and order book data."""

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
    """Funding rate data from Hyperliquid."""

    symbol: str
    rate: float
    timestamp: int


@dataclass
class OpenInterestData:
    """Open interest data from Hyperliquid."""

    symbol: str
    oi_usd: float
    timestamp: int


FundingCallback = Callable[[FundingData], None]
OICallback = Callable[[OpenInterestData], None]


class HyperliquidWebSocket(BaseWebSocketClient):
    """Hyperliquid WebSocket client for trades, order book, funding, and OI."""

    EXCHANGE_NAME = "hyperliquid"
    WS_URL = "wss://api.hyperliquid.xyz/ws"
    REST_URL = "https://api.hyperliquid.xyz/info"
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
        logger.info("Started REST polling", extra=ctx(LogContext.WS_CONNECTED, exchange="hyperliquid", symbols=symbols))

    async def _poll_loop(self, symbols: list[str]):
        """Background loop to poll REST API."""
        while True:
            try:
                await self._fetch_meta_data(symbols)
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Polling error",
                    extra=ctx_exception(e, function_name="_poll_loop", operation="fetch_meta_data"),
                    exc_info=True,
                )
                await asyncio.sleep(10)

    async def _fetch_meta_data(self, symbols: list[str]):
        """Fetch funding rates and OI from REST API."""
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(self.REST_URL, json={"type": "metaAndAssetCtxs"}) as resp,
            ):
                if resp.status != 200:
                    logger.error(
                        "REST API error",
                        extra=ctx(LogContext.API_ERROR, exchange="hyperliquid", status_code=resp.status),
                    )
                    return

                data = await resp.json()

            if len(data) < 2:
                return

            timestamp = int(time.time() * 1000)
            asset_contexts = data[1]

            for ctx_data in asset_contexts:
                coin = ctx_data.get("coin", "")
                if coin not in symbols:
                    continue

                # Funding rate
                funding_rate = float(ctx_data.get("funding", 0))
                funding_data = FundingData(
                    symbol=coin,
                    rate=funding_rate,
                    timestamp=timestamp,
                )
                for callback in self._funding_callbacks:
                    try:
                        callback(funding_data)
                    except Exception as e:
                        logger.error(
                            "Funding callback error",
                            extra=ctx_exception(e, function_name="_fetch_meta_data", operation="funding_callback"),
                            exc_info=True,
                        )

                # Open interest
                oi = float(ctx_data.get("openInterest", 0))
                mark_px = float(ctx_data.get("markPx", 0))
                oi_usd = oi * mark_px

                oi_data = OpenInterestData(
                    symbol=coin,
                    oi_usd=oi_usd,
                    timestamp=timestamp,
                )
                for callback in self._oi_callbacks:
                    try:
                        callback(oi_data)
                    except Exception as e:
                        logger.error(
                            "OI callback error",
                            extra=ctx_exception(e, function_name="_fetch_meta_data", operation="oi_callback"),
                            exc_info=True,
                        )

                # Mark price
                if mark_px > 0:
                    mark_data = MarkPriceData(
                        exchange=self.EXCHANGE_NAME,
                        symbol=coin,
                        timestamp=timestamp,
                        mark_price=mark_px,
                        funding_rate=funding_rate,
                    )
                    for callback in self._mark_price_callbacks:
                        try:
                            callback(mark_data)
                        except Exception as e:
                            logger.error(
                                "Mark price callback error",
                                extra=ctx_exception(
                                    e, function_name="_fetch_meta_data", operation="markprice_callback"
                                ),
                                exc_info=True,
                            )

        except Exception as e:
            logger.error(
                "REST fetch error",
                extra=ctx_exception(e, function_name="_fetch_meta_data", operation="rest_fetch"),
                exc_info=True,
            )

    async def _subscribe_trades_impl(self, symbols: list[str]):
        """Subscribe to trade streams."""
        for symbol in symbols:
            message = {"method": "subscribe", "subscription": {"type": "trades", "coin": symbol}}
            await self._send(message)
        logger.info(
            "Subscribed to trades",
            extra=ctx(LogContext.WS_CONNECTED, exchange="hyperliquid", channels=["trades"], symbols=symbols),
        )

    async def _subscribe_order_book_impl(self, symbols: list[str]):
        """Subscribe to order book streams."""
        for symbol in symbols:
            message = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": symbol}}
            await self._send(message)
        logger.info(
            "Subscribed to order book",
            extra=ctx(LogContext.WS_CONNECTED, exchange="hyperliquid", channels=["l2Book"], symbols=symbols),
        )

    def _parse_message(self, data: dict) -> Any | None:
        """Parse Hyperliquid WebSocket message."""
        channel = data.get("channel")

        if channel == "trades":
            trades_data = data.get("data", [])
            if trades_data:
                return self._parse_trade(trades_data[-1])

        elif channel == "l2Book":
            return self._parse_order_book(data.get("data", {}))

        elif channel == "subscriptionResponse":
            logger.debug("Subscription response", extra=ctx(LogContext.WS_CONNECTED, exchange="hyperliquid"))

        elif channel == "error":
            logger.error(
                "WebSocket error", extra=ctx(LogContext.API_ERROR, exchange="hyperliquid", message=data.get("data"))
            )

        return None

    def _parse_trade(self, data: dict) -> NormalizedTrade:
        """Parse trade message."""
        side_raw = data.get("side", "B")
        side = "buy" if side_raw == "B" else "sell"

        return NormalizedTrade(
            exchange=self.EXCHANGE_NAME,
            symbol=data.get("coin", ""),
            trade_id=str(data.get("tid", data.get("hash", ""))),
            timestamp=int(data.get("time", 0)),
            price=float(data.get("px", 0)),
            size=float(data.get("sz", 0)),
            side=side,
        )

    def _parse_order_book(self, data: dict) -> NormalizedOrderBook:
        """Parse order book message."""
        symbol = data.get("coin", "")
        levels = data.get("levels", [[], []])

        bids = []
        if len(levels) > 0:
            for level in levels[0]:
                bids.append((float(level.get("px", 0)), float(level.get("sz", 0))))

        asks = []
        if len(levels) > 1:
            for level in levels[1]:
                asks.append((float(level.get("px", 0)), float(level.get("sz", 0))))

        return NormalizedOrderBook(
            exchange=self.EXCHANGE_NAME,
            symbol=symbol,
            timestamp=int(data.get("time", time.time() * 1000)),
            bids=bids,
            asks=asks,
        )

    async def disconnect(self):
        """Disconnect and stop polling."""
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        await super().disconnect()
