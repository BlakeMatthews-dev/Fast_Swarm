"""
BinanceWebSocket Unit Tests - Real message parsing with mocked WebSocket.

Source: src/Fast_Swarm/exchanges/binance_ws.py

Tests: Binance-specific message format parsing:
1. Trade messages (single stream and combined stream)
2. Depth/orderbook updates
3. Book ticker (best bid/ask)
4. Kline/candlestick messages
5. Subscription responses
6. Buyer-maker side logic
"""

import time
from unittest.mock import AsyncMock

import pytest

from Fast_Swarm.exchanges.base_ws import (
    BookTickerData,
    ConnectionState,
    KlineData,
    NormalizedOrderBook,
    NormalizedTrade,
)
from Fast_Swarm.exchanges.binance_ws import BinanceWebSocket


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ws():
    return BinanceWebSocket(use_global=False)


@pytest.fixture
def global_ws():
    return BinanceWebSocket(use_global=True)


# ============================================================================
# 1. TRADE MESSAGES
# ============================================================================


class TestTradeMessages:
    def test_parse_trade_direct_stream(self, ws):
        """Parse trade from single-stream format (event type 'trade')."""
        msg = {
            "e": "trade",
            "E": 1700000000123,
            "s": "BTCUSDT",
            "t": 3314562,
            "p": "42150.50",
            "q": "0.001",
            "T": 1700000000100,
            "m": False,  # buyer is taker (aggressive buy)
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedTrade)
        assert result.exchange == "binance"
        assert result.symbol == "BTCUSDT"
        assert result.trade_id == "3314562"
        assert result.timestamp == 1700000000100
        assert result.price == 42150.50
        assert result.size == 0.001
        assert result.side == "buy"  # m=False -> buyer is taker -> aggressive buy

    def test_parse_trade_buyer_maker(self, ws):
        """When m=True, buyer is maker, so aggressor side is 'sell'."""
        msg = {
            "e": "trade",
            "s": "ETHUSDT",
            "t": 999,
            "p": "2200.00",
            "q": "5.0",
            "T": 1700000000000,
            "m": True,  # buyer is maker -> aggressive sell
        }

        result = ws._parse_message(msg)
        assert result.side == "sell"

    def test_parse_trade_combined_stream(self, ws):
        """Parse trade from combined-stream format (with 'stream' wrapper)."""
        msg = {
            "stream": "btcusdt@trade",
            "data": {
                "e": "trade",
                "s": "BTCUSDT",
                "t": 100,
                "p": "42000",
                "q": "0.5",
                "T": 1700000000000,
                "m": False,
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedTrade)
        assert result.symbol == "BTCUSDT"
        assert result.price == 42000.0


# ============================================================================
# 2. ORDER BOOK DEPTH UPDATES
# ============================================================================


class TestDepthMessages:
    def test_parse_depth_update(self, ws):
        """Parse depth update message."""
        msg = {
            "e": "depthUpdate",
            "s": "BTCUSDT",
            "bids": [
                ["42000.00", "1.500"],
                ["41999.00", "2.300"],
            ],
            "asks": [
                ["42001.00", "0.800"],
                ["42002.00", "1.200"],
            ],
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedOrderBook)
        assert result.exchange == "binance"
        assert result.symbol == "BTCUSDT"
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.bids[0] == (42000.0, 1.5)
        assert result.asks[0] == (42001.0, 0.8)

    def test_parse_depth_combined_stream(self, ws):
        """Parse depth from combined stream wrapper."""
        msg = {
            "stream": "btcusdt@depth20@100ms",
            "data": {
                "e": "depthUpdate",
                "s": "BTCUSDT",
                "bids": [["42000.00", "1.0"]],
                "asks": [["42001.00", "0.5"]],
            },
        }

        result = ws._parse_message(msg)
        assert isinstance(result, NormalizedOrderBook)
        assert result.symbol == "BTCUSDT"


# ============================================================================
# 3. BOOK TICKER
# ============================================================================


class TestBookTicker:
    def test_parse_book_ticker_event(self, ws):
        """Parse bookTicker event type message."""
        msg = {
            "e": "bookTicker",
            "s": "BTCUSDT",
            "b": "42000.00",
            "B": "1.500",
            "a": "42001.00",
            "A": "0.800",
        }

        result = ws._parse_message(msg)

        assert isinstance(result, BookTickerData)
        assert result.exchange == "binance"
        assert result.symbol == "BTCUSDT"
        assert result.best_bid == 42000.0
        assert result.best_bid_qty == 1.5
        assert result.best_ask == 42001.0
        assert result.best_ask_qty == 0.8

    def test_parse_book_ticker_no_event_field(self, ws):
        """Parse book ticker without explicit 'e' field (legacy format)."""
        msg = {
            "s": "ETHUSDT",
            "b": "2200.00",
            "B": "10.0",
            "a": "2201.00",
            "A": "5.0",
        }

        result = ws._parse_message(msg)

        assert isinstance(result, BookTickerData)
        assert result.symbol == "ETHUSDT"
        assert result.best_bid == 2200.0

    def test_parse_book_ticker_combined_stream(self, ws):
        """Parse book ticker from combined stream."""
        msg = {
            "stream": "btcusdt@bookTicker",
            "data": {
                "s": "BTCUSDT",
                "b": "42000.00",
                "B": "1.0",
                "a": "42001.00",
                "A": "0.5",
            },
        }

        result = ws._parse_message(msg)
        assert isinstance(result, BookTickerData)

    def test_book_ticker_spread_bps(self, ws):
        """Verify spread calculation from parsed book ticker."""
        msg = {
            "e": "bookTicker",
            "s": "BTCUSDT",
            "b": "42000.00",
            "B": "1.0",
            "a": "42010.00",
            "A": "1.0",
        }

        result = ws._parse_message(msg)
        mid = (42000.0 + 42010.0) / 2
        expected_bps = (10.0 / mid) * 10000
        assert abs(result.spread_bps - expected_bps) < 0.01


# ============================================================================
# 4. KLINE / CANDLESTICK
# ============================================================================


class TestKlineMessages:
    def test_parse_kline(self, ws):
        """Parse kline/candlestick message."""
        msg = {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1700000000000,
                "s": "BTCUSDT",
                "i": "5m",
                "o": "42000.00",
                "h": "42100.00",
                "l": "41950.00",
                "c": "42050.00",
                "v": "123.456",
                "q": "5189102.50",
                "n": 1500,
                "x": True,
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, KlineData)
        assert result.exchange == "binance"
        assert result.symbol == "BTCUSDT"
        assert result.timeframe == "5m"
        assert result.open == 42000.0
        assert result.high == 42100.0
        assert result.low == 41950.0
        assert result.close == 42050.0
        assert result.volume == 123.456
        assert result.quote_volume == 5189102.50
        assert result.trades == 1500
        assert result.is_closed is True

    def test_parse_kline_not_closed(self, ws):
        """Parse in-progress kline (x=False)."""
        msg = {
            "e": "kline",
            "s": "ETHUSDT",
            "k": {
                "t": 1700000000000,
                "i": "1m",
                "o": "2200",
                "h": "2210",
                "l": "2190",
                "c": "2205",
                "v": "50",
                "x": False,
            },
        }

        result = ws._parse_message(msg)
        assert result.is_closed is False
        assert result.timeframe == "1m"


# ============================================================================
# 5. SUBSCRIPTION RESPONSES
# ============================================================================


class TestSubscriptionResponses:
    def test_subscription_ack_returns_none(self, ws):
        """Subscription acknowledgement returns None (no data)."""
        msg = {"result": None, "id": 1}

        result = ws._parse_message(msg)
        assert result is None

    def test_unknown_event_returns_none(self, ws):
        """Unknown event type returns None."""
        msg = {"e": "someUnknownEvent", "data": {}}

        result = ws._parse_message(msg)
        assert result is None


# ============================================================================
# 6. CLIENT CONFIGURATION
# ============================================================================


class TestClientConfig:
    def test_us_endpoint(self, ws):
        assert ws.WS_URL == "wss://stream.binance.us:9443/ws"

    def test_global_endpoint(self, global_ws):
        assert global_ws.WS_URL == "wss://stream.binance.com:9443/ws"

    def test_stream_url_single(self, ws):
        url = ws._get_stream_url(["btcusdt@trade"])
        assert url == "wss://stream.binance.us:9443/ws/btcusdt@trade"

    def test_stream_url_combined(self, ws):
        url = ws._get_stream_url(["btcusdt@trade", "ethusdt@trade"])
        assert "stream?streams=" in url
        assert "btcusdt@trade/ethusdt@trade" in url
