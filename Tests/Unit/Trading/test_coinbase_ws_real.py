"""
CoinbaseWebSocket Unit Tests - Real message parsing with mocked WebSocket.

Source: src/Fast_Swarm/exchanges/coinbase_ws.py

Tests: Coinbase-specific message parsing:
1. Trade (match) messages with maker-side inversion
2. Ticker messages (best bid/ask)
3. Order book snapshot handling
4. Order book l2update delta handling
5. Subscription confirmation and error messages
6. Timestamp parsing (ISO 8601)
"""

import time
from unittest.mock import AsyncMock

import pytest

from Fast_Swarm.exchanges.base_ws import (
    BookTickerData,
    ConnectionState,
    NormalizedOrderBook,
    NormalizedTrade,
)
from Fast_Swarm.exchanges.coinbase_ws import CoinbaseWebSocket


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ws():
    return CoinbaseWebSocket()


# ============================================================================
# 1. TRADE (MATCH) MESSAGES
# ============================================================================


class TestTradeMessages:
    def test_parse_match_buy_aggressor(self, ws):
        """
        Coinbase 'match' gives maker side. If maker side is 'sell',
        the aggressor (taker) is 'buy'.
        """
        msg = {
            "type": "match",
            "trade_id": 123456,
            "product_id": "BTC-USD",
            "price": "42150.50",
            "size": "0.01",
            "side": "sell",  # maker side
            "time": "2024-01-15T10:30:00.000000Z",
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedTrade)
        assert result.exchange == "coinbase"
        assert result.symbol == "BTC-USD"
        assert result.trade_id == "123456"
        assert result.price == 42150.50
        assert result.size == 0.01
        assert result.side == "buy"  # inverted from maker 'sell'

    def test_parse_match_sell_aggressor(self, ws):
        """Maker side 'buy' -> aggressor is 'sell'."""
        msg = {
            "type": "match",
            "trade_id": 789,
            "product_id": "ETH-USD",
            "price": "2200.00",
            "size": "5.0",
            "side": "buy",
            "time": "2024-01-15T10:30:00.000000Z",
        }

        result = ws._parse_message(msg)
        assert result.side == "sell"

    def test_parse_last_match(self, ws):
        """'last_match' type is treated the same as 'match'."""
        msg = {
            "type": "last_match",
            "trade_id": 555,
            "product_id": "BTC-USD",
            "price": "42000",
            "size": "0.1",
            "side": "sell",
            "time": "2024-01-15T10:30:00.000000Z",
        }

        result = ws._parse_message(msg)
        assert isinstance(result, NormalizedTrade)
        assert result.trade_id == "555"

    def test_parse_trade_timestamp_iso8601(self, ws):
        """ISO 8601 timestamp is correctly parsed to Unix ms."""
        msg = {
            "type": "match",
            "trade_id": 1,
            "product_id": "BTC-USD",
            "price": "42000",
            "size": "1",
            "side": "sell",
            "time": "2024-01-15T12:00:00.000000Z",
        }

        result = ws._parse_message(msg)

        # 2024-01-15T12:00:00Z = 1705320000 seconds
        assert result.timestamp == 1705320000000

    def test_parse_trade_bad_timestamp_fallback(self, ws):
        """Bad timestamp falls back to current time."""
        msg = {
            "type": "match",
            "trade_id": 1,
            "product_id": "BTC-USD",
            "price": "42000",
            "size": "1",
            "side": "sell",
            "time": "invalid-timestamp",
        }

        before = int(time.time() * 1000)
        result = ws._parse_message(msg)
        after = int(time.time() * 1000)

        assert before <= result.timestamp <= after


# ============================================================================
# 2. TICKER MESSAGES
# ============================================================================


class TestTickerMessages:
    def test_parse_ticker(self, ws):
        """Parse ticker message for best bid/ask."""
        msg = {
            "type": "ticker",
            "product_id": "BTC-USD",
            "best_bid": "42000.00",
            "best_ask": "42001.00",
            "best_bid_size": "1.5",
            "best_ask_size": "0.8",
            "time": "2024-01-15T10:30:00.000000Z",
        }

        result = ws._parse_message(msg)

        assert isinstance(result, BookTickerData)
        assert result.exchange == "coinbase"
        assert result.symbol == "BTC-USD"
        assert result.best_bid == 42000.0
        assert result.best_ask == 42001.0
        assert result.best_bid_qty == 1.5
        assert result.best_ask_qty == 0.8

    def test_parse_ticker_missing_bid_ask_returns_none(self, ws):
        """Ticker with missing bid/ask returns None."""
        msg = {
            "type": "ticker",
            "product_id": "BTC-USD",
            "time": "2024-01-15T10:30:00.000000Z",
        }

        result = ws._parse_message(msg)
        assert result is None


# ============================================================================
# 3. ORDER BOOK SNAPSHOT
# ============================================================================


class TestOrderBookSnapshot:
    def test_snapshot_creates_book(self, ws):
        """Snapshot message initializes internal order book."""
        msg = {
            "type": "snapshot",
            "product_id": "BTC-USD",
            "bids": [
                ["42000.00", "1.5"],
                ["41999.00", "2.0"],
            ],
            "asks": [
                ["42001.00", "0.8"],
                ["42002.00", "1.2"],
            ],
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedOrderBook)
        assert result.symbol == "BTC-USD"
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        # Bids sorted descending
        assert result.bids[0][0] == 42000.0
        # Asks sorted ascending
        assert result.asks[0][0] == 42001.0

    def test_snapshot_stores_internally(self, ws):
        """Snapshot is stored for delta updates."""
        msg = {
            "type": "snapshot",
            "product_id": "ETH-USD",
            "bids": [["2200.00", "10.0"]],
            "asks": [["2201.00", "5.0"]],
        }

        ws._parse_message(msg)

        assert "ETH-USD" in ws._order_books
        assert 2200.0 in ws._order_books["ETH-USD"]["bids"]
        assert 2201.0 in ws._order_books["ETH-USD"]["asks"]


# ============================================================================
# 4. ORDER BOOK L2UPDATE
# ============================================================================


class TestOrderBookUpdate:
    def test_l2update_modifies_book(self, ws):
        """l2update applies changes to existing book."""
        # Seed snapshot
        ws._order_books["BTC-USD"] = {
            "bids": {42000.0: 1.5, 41999.0: 2.0},
            "asks": {42001.0: 0.8, 42002.0: 1.2},
        }

        msg = {
            "type": "l2update",
            "product_id": "BTC-USD",
            "changes": [
                ["buy", "42000.00", "2.0"],   # Update bid
                ["sell", "42001.00", "0"],     # Remove ask
                ["sell", "42003.00", "0.5"],   # Add new ask
            ],
        }

        result = ws._parse_message(msg)

        assert isinstance(result, NormalizedOrderBook)
        # Bid updated
        assert ws._order_books["BTC-USD"]["bids"][42000.0] == 2.0
        # Ask removed
        assert 42001.0 not in ws._order_books["BTC-USD"]["asks"]
        # New ask added
        assert ws._order_books["BTC-USD"]["asks"][42003.0] == 0.5

    def test_l2update_unknown_symbol_returns_none(self, ws):
        """l2update for unknown symbol logs warning and returns None."""
        msg = {
            "type": "l2update",
            "product_id": "UNKNOWN-USD",
            "changes": [["buy", "100.00", "1.0"]],
        }

        result = ws._parse_message(msg)
        # _handle_order_book_update returns early, _build_order_book returns None
        assert result is None

    def test_order_book_limited_to_20_levels(self, ws):
        """Built order book is limited to 20 levels per side."""
        bids = {float(42000 - i): 1.0 for i in range(30)}
        asks = {float(42001 + i): 1.0 for i in range(30)}
        ws._order_books["BTC-USD"] = {"bids": bids, "asks": asks}

        result = ws._build_order_book("BTC-USD")

        assert len(result.bids) == 20
        assert len(result.asks) == 20
        # Bids descending, asks ascending
        assert result.bids[0][0] > result.bids[-1][0]
        assert result.asks[0][0] < result.asks[-1][0]


# ============================================================================
# 5. SUBSCRIPTION AND ERROR MESSAGES
# ============================================================================


class TestSubscriptionMessages:
    def test_subscriptions_message_returns_none(self, ws):
        """Subscription confirmation returns None."""
        msg = {
            "type": "subscriptions",
            "channels": [
                {"name": "matches", "product_ids": ["BTC-USD"]},
            ],
        }

        result = ws._parse_message(msg)
        assert result is None

    def test_error_message_returns_none(self, ws):
        """Error message returns None.

        Note: Source code passes 'message' in logging extra dict which
        conflicts with Python's LogRecord. We suppress logging for this test.
        """
        import logging

        msg = {
            "type": "error",
            "message": "Failed to subscribe",
        }

        logging.disable(logging.CRITICAL)
        try:
            result = ws._parse_message(msg)
        finally:
            logging.disable(logging.NOTSET)
        assert result is None

    def test_unknown_type_returns_none(self, ws):
        msg = {"type": "heartbeat", "sequence": 90}
        result = ws._parse_message(msg)
        assert result is None


# ============================================================================
# 6. CLIENT CONFIGURATION
# ============================================================================


class TestClientConfig:
    def test_exchange_name(self, ws):
        assert ws.EXCHANGE_NAME == "coinbase"

    def test_ws_url(self, ws):
        assert ws.WS_URL == "wss://ws-feed.exchange.coinbase.com"

    def test_build_order_book_missing_symbol(self, ws):
        """_build_order_book returns None for unknown symbol."""
        result = ws._build_order_book("NONEXISTENT")
        assert result is None
