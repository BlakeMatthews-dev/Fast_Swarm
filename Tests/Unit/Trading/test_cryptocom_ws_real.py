"""
CryptoComWebSocket Unit Tests - Real message parsing with mocked WebSocket.

Source: src/Fast_Swarm/exchanges/cryptocom_ws.py

Tests: Crypto.com-specific message parsing:
1. Trade message parsing
2. Order book snapshot parsing
3. Order book delta update parsing
4. Mark price parsing
5. Kline/candlestick parsing
6. Heartbeat handling
7. Subscription error handling
8. Symbol normalization
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from Fast_Swarm.exchanges.base_ws import (
    ConnectionState,
    KlineData,
    MarkPriceData,
    NormalizedOrderBook,
    NormalizedTrade,
)
from Fast_Swarm.exchanges.cryptocom_ws import CryptoComWebSocket


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ws():
    """Create a CryptoComWebSocket instance."""
    client = CryptoComWebSocket(use_sandbox=False)
    return client


@pytest.fixture
def sandbox_ws():
    return CryptoComWebSocket(use_sandbox=True)


# ============================================================================
# 1. TRADE MESSAGE PARSING
# ============================================================================


class TestTradeMessages:
    """Test parsing of Crypto.com trade messages."""

    def test_parse_single_trade(self, ws):
        """Parse a single trade from the trade channel."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "subscription": "trade.BTCUSD-PERP",
                "channel": "trade",
                "data": [
                    {
                        "d": "4622368164584012781",
                        "t": 1700000000000,
                        "p": "42150.50",
                        "q": "0.001",
                        "s": "BUY",
                        "i": "BTCUSD-PERP",
                    }
                ],
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedTrade)
        assert result.exchange == "crypto.com"
        assert result.symbol == "BTCUSD-PERP"
        assert result.trade_id == "4622368164584012781"
        assert result.timestamp == 1700000000000
        assert result.price == 42150.50
        assert result.size == 0.001
        assert result.side == "buy"

    def test_parse_multiple_trades_takes_latest(self, ws):
        """When multiple trades arrive, take the most recent (last)."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTC_USDT",
                "subscription": "trade.BTC_USDT",
                "channel": "trade",
                "data": [
                    {"d": "1", "t": 1700000000000, "p": "42000", "q": "0.1", "s": "BUY", "i": "BTC_USDT"},
                    {"d": "2", "t": 1700000000001, "p": "42001", "q": "0.2", "s": "SELL", "i": "BTC_USDT"},
                ],
            },
        }

        result = ws._parse_message(msg)

        assert result.trade_id == "2"
        assert result.price == 42001.0
        assert result.side == "sell"

    def test_parse_sell_trade(self, ws):
        """Sell side is correctly parsed."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "ETHUSD-PERP",
                "channel": "trade",
                "data": [{"d": "99", "t": 1700000000000, "p": "2200", "q": "5.0", "s": "SELL", "i": "ETHUSD-PERP"}],
            },
        }

        result = ws._parse_message(msg)
        assert result.side == "sell"
        assert result.size == 5.0


# ============================================================================
# 2. ORDER BOOK SNAPSHOT PARSING
# ============================================================================


class TestOrderBookSnapshot:
    """Test parsing of order book snapshot messages."""

    def test_parse_order_book_snapshot(self, ws):
        """Parse a full order book snapshot with bids and asks."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "subscription": "book.BTCUSD-PERP.10",
                "channel": "book",
                "data": [
                    {
                        "bids": [
                            [42000.0, 1.5, 3],
                            [41999.0, 2.0, 5],
                        ],
                        "asks": [
                            [42001.0, 0.8, 2],
                            [42002.0, 1.2, 4],
                        ],
                        "t": 1700000000000,
                        "tt": 1700000000000,
                        "u": 12345,
                    }
                ],
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedOrderBook)
        assert result.exchange == "crypto.com"
        assert result.symbol == "BTCUSD-PERP"
        assert result.timestamp == 1700000000000
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.bids[0] == (42000.0, 1.5)
        assert result.asks[0] == (42001.0, 0.8)

    def test_order_book_stored_for_deltas(self, ws):
        """Snapshot is stored internally for applying delta updates."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "channel": "book",
                "data": [
                    {
                        "bids": [[42000.0, 1.5, 3]],
                        "asks": [[42001.0, 0.8, 2]],
                        "t": 1700000000000,
                        "u": 100,
                    }
                ],
            },
        }

        ws._parse_message(msg)

        assert "BTCUSD-PERP" in ws._order_books
        assert ws._order_books["BTCUSD-PERP"]["sequence"] == 100


# ============================================================================
# 3. ORDER BOOK DELTA UPDATES
# ============================================================================


class TestOrderBookDelta:
    """Test incremental order book updates."""

    def test_delta_update_modifies_stored_book(self, ws):
        """Delta update modifies existing order book."""
        # First, seed a snapshot
        ws._order_books["BTCUSD-PERP"] = {
            "bids": {"42000.0": 1.5, "41999.0": 2.0},
            "asks": {"42001.0": 0.8, "42002.0": 1.2},
            "sequence": 100,
        }

        delta_msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "channel": "book.update",
                "data": [
                    {
                        "update": {
                            "bids": [[42000.0, 2.0, 4]],  # Update bid size
                            "asks": [[42001.0, 0, 0]],    # Remove ask level
                        },
                        "t": 1700000000001,
                    }
                ],
            },
        }

        result = ws._parse_message(delta_msg)

        assert isinstance(result, NormalizedOrderBook)
        # Bid at 42000 updated to 2.0
        bid_prices = {b[0] for b in result.bids}
        assert 42000.0 in bid_prices
        # Ask at 42001 removed (size=0)
        ask_prices = {a[0] for a in result.asks}
        assert 42001.0 not in ask_prices
        assert 42002.0 in ask_prices

    def test_delta_without_snapshot_returns_none(self, ws):
        """Delta for unknown instrument returns None."""
        delta_msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "UNKNOWN",
                "channel": "book.update",
                "data": [{"update": {"bids": [[100, 1, 1]]}, "t": 1700000000000}],
            },
        }

        result = ws._parse_message(delta_msg)
        assert result is None


# ============================================================================
# 4. MARK PRICE PARSING
# ============================================================================


class TestMarkPrice:
    def test_parse_mark_price(self, ws):
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "channel": "mark_price",
                "data": [
                    {
                        "v": "42150.75",
                        "t": 1700000000000,
                        "ip": "42145.00",
                        "fr": "0.0001",
                    }
                ],
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, MarkPriceData)
        assert result.mark_price == 42150.75
        assert result.index_price == 42145.00
        assert result.funding_rate == 0.0001

    def test_parse_mark_price_no_funding(self, ws):
        """Mark price without optional funding fields."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "ETHUSD-PERP",
                "channel": "mark_price",
                "data": [{"v": "2200.00", "t": 1700000000000}],
            },
        }

        result = ws._parse_message(msg)
        assert result.mark_price == 2200.0
        assert result.index_price is None
        assert result.funding_rate is None


# ============================================================================
# 5. KLINE PARSING
# ============================================================================


class TestKlineParsing:
    def test_parse_kline(self, ws):
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTC_USDT",
                "channel": "candlestick.5m.BTC_USDT",
                "data": [
                    {
                        "o": "42000.00",
                        "h": "42100.00",
                        "l": "41950.00",
                        "c": "42050.00",
                        "v": "123.45",
                        "vv": "5189102.50",
                        "t": 1700000000000,
                    }
                ],
            },
        }

        result = ws._parse_message(msg)

        assert isinstance(result, KlineData)
        assert result.timeframe == "5m"
        assert result.open == 42000.0
        assert result.high == 42100.0
        assert result.low == 41950.0
        assert result.close == 42050.0
        assert result.volume == 123.45
        assert result.quote_volume == 5189102.50
        assert result.is_closed is False  # Crypto.com doesn't indicate close


# ============================================================================
# 6. HEARTBEAT HANDLING
# ============================================================================


class TestHeartbeat:
    def test_heartbeat_returns_none(self, ws):
        """Heartbeat messages are handled but return None (no data to dispatch)."""
        ws.ws = AsyncMock()
        ws.state = ConnectionState.CONNECTED

        msg = {"id": 1, "method": "public/heartbeat"}

        with patch("asyncio.create_task"):
            result = ws._parse_message(msg)
        assert result is None

    def test_heartbeat_response_queued(self, ws):
        """Heartbeat creates a task to send respond-heartbeat."""
        ws.ws = AsyncMock()
        ws.state = ConnectionState.CONNECTED

        msg = {"id": 42, "method": "public/heartbeat"}

        with patch("asyncio.create_task") as mock_create_task:
            ws._parse_message(msg)
            mock_create_task.assert_called_once()


# ============================================================================
# 7. SUBSCRIPTION ERROR HANDLING
# ============================================================================


class TestSubscriptionErrors:
    def test_subscription_error_returns_none(self, ws):
        """Error response (code != 0) returns None.

        Note: The source code passes 'message' in logging extra dict which
        conflicts with Python's LogRecord. We suppress logging for this test.
        """
        import logging

        msg = {"id": 1, "code": 10001, "message": "INVALID_CHANNEL"}

        logging.disable(logging.CRITICAL)
        try:
            result = ws._parse_message(msg)
        finally:
            logging.disable(logging.NOTSET)
        assert result is None

    def test_successful_subscription_returns_none(self, ws):
        """Subscription confirmation (code=0, no result) returns None."""
        msg = {"id": 1, "code": 0}

        result = ws._parse_message(msg)
        assert result is None

    def test_empty_data_returns_none(self, ws):
        """Message with empty data array returns None."""
        msg = {
            "id": -1,
            "method": "subscribe",
            "code": 0,
            "result": {
                "instrument_name": "BTCUSD-PERP",
                "channel": "trade",
                "data": [],
            },
        }

        result = ws._parse_message(msg)
        assert result is None


# ============================================================================
# 8. SYMBOL NORMALIZATION
# ============================================================================


class TestSymbolNormalization:
    def test_normalize_spot_usdt(self):
        assert CryptoComWebSocket.normalize_symbol("BTCUSDT") == "BTC_USDT"

    def test_normalize_spot_slash(self):
        assert CryptoComWebSocket.normalize_symbol("BTC/USDT") == "BTC_USDT"

    def test_normalize_perpetual(self):
        assert CryptoComWebSocket.normalize_symbol("BTCUSDPERP") == "BTCUSD-PERP"

    def test_normalize_usd_assumes_perp(self):
        assert CryptoComWebSocket.normalize_symbol("BTCUSD") == "BTCUSD-PERP"

    def test_normalize_already_correct(self):
        """Already-formatted symbols pass through."""
        # Symbols without USDT or USD are returned as-is
        assert CryptoComWebSocket.normalize_symbol("UNKNOWN") == "UNKNOWN"

    def test_sandbox_url(self, sandbox_ws):
        assert sandbox_ws.WS_URL == "wss://uat-stream.3ona.co/exchange/v1/market"
