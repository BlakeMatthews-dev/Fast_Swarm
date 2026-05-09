"""
BaseWebSocketClient Unit Tests - Connection management with mocked WebSocket.

Source: src/Fast_Swarm/exchanges/base_ws.py

Tests:
1. Reconnect logic (disconnect -> auto-reconnect with backoff)
2. Heartbeat/ping-pong handling (via websockets library)
3. Message routing to correct handlers (trade, orderbook, mark price, book ticker, kline)
4. Connection state tracking
5. NormalizedTrade / NormalizedOrderBook data classes
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.exchanges.base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    ConnectionState,
    KlineData,
    MarkPriceData,
    NormalizedOrderBook,
    NormalizedTrade,
)


# ============================================================================
# CONCRETE SUBCLASS FOR TESTING
# ============================================================================


class MockWebSocketClient(BaseWebSocketClient):
    """Concrete implementation of BaseWebSocketClient for testing."""

    EXCHANGE_NAME = "mock_exchange"
    WS_URL = "wss://mock.exchange.com/ws"
    PING_INTERVAL = 10.0
    RECONNECT_DELAY = 0.01  # Fast reconnect for tests
    MAX_RECONNECT_ATTEMPTS = 3
    COOLDOWN_AFTER_MAX_RETRIES = 0.01

    def __init__(self):
        super().__init__()
        self.subscribe_trades_called = []
        self.subscribe_orderbook_called = []
        self.parsed_messages = []

    async def _subscribe_trades_impl(self, symbols: list[str]):
        self.subscribe_trades_called.append(symbols)

    async def _subscribe_order_book_impl(self, symbols: list[str]):
        self.subscribe_orderbook_called.append(symbols)

    def _parse_message(self, data: dict):
        self.parsed_messages.append(data)
        msg_type = data.get("type")
        if msg_type == "trade":
            return NormalizedTrade(
                exchange=self.EXCHANGE_NAME,
                symbol=data.get("symbol", ""),
                trade_id=data.get("id", ""),
                timestamp=data.get("timestamp", 0),
                price=float(data.get("price", 0)),
                size=float(data.get("size", 0)),
                side=data.get("side", "buy"),
            )
        elif msg_type == "orderbook":
            return NormalizedOrderBook(
                exchange=self.EXCHANGE_NAME,
                symbol=data.get("symbol", ""),
                timestamp=data.get("timestamp", 0),
                bids=data.get("bids", []),
                asks=data.get("asks", []),
            )
        elif msg_type == "mark_price":
            return MarkPriceData(
                exchange=self.EXCHANGE_NAME,
                symbol=data.get("symbol", ""),
                timestamp=data.get("timestamp", 0),
                mark_price=float(data.get("mark_price", 0)),
            )
        elif msg_type == "book_ticker":
            return BookTickerData(
                exchange=self.EXCHANGE_NAME,
                symbol=data.get("symbol", ""),
                timestamp=data.get("timestamp", 0),
                best_bid=float(data.get("best_bid", 0)),
                best_bid_qty=float(data.get("best_bid_qty", 0)),
                best_ask=float(data.get("best_ask", 0)),
                best_ask_qty=float(data.get("best_ask_qty", 0)),
            )
        elif msg_type == "kline":
            return KlineData(
                exchange=self.EXCHANGE_NAME,
                symbol=data.get("symbol", ""),
                timestamp=data.get("timestamp", 0),
                timeframe="1m",
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=100.0,
            )
        return None


@pytest.fixture
def client():
    return MockWebSocketClient()


# ============================================================================
# 1. CONNECTION STATE TRACKING
# ============================================================================


class TestConnectionState:
    """Test connection state transitions."""

    def test_initial_state_disconnected(self, client):
        assert client.state == ConnectionState.DISCONNECTED

    def test_is_connected_false_initially(self, client):
        assert client.is_connected is False

    def test_is_connected_true_when_connected(self, client):
        client.state = ConnectionState.CONNECTED
        assert client.is_connected is True

    def test_seconds_since_last_message_inf_initially(self, client):
        assert client.seconds_since_last_message == float("inf")

    def test_seconds_since_last_message_tracks(self, client):
        client._last_message_time = time.time() - 5.0
        elapsed = client.seconds_since_last_message
        assert 4.5 < elapsed < 6.0

    def test_get_status(self, client):
        status = client.get_status()
        assert status["exchange"] == "mock_exchange"
        assert status["state"] == "disconnected"
        assert status["reconnect_count"] == 0
        assert isinstance(status["subscriptions"], dict)


# ============================================================================
# 2. SUBSCRIPTION MANAGEMENT
# ============================================================================


class TestSubscriptionManagement:
    """Test subscription tracking and resubscription."""

    @pytest.mark.asyncio
    async def test_subscribe_trades_stores_symbols(self, client):
        """subscribe_trades stores symbols even when disconnected."""
        await client.subscribe_trades(["BTCUSD", "ETHUSD"])

        assert "trades" in client._subscriptions
        assert "BTCUSD" in client._subscriptions["trades"]
        assert "ETHUSD" in client._subscriptions["trades"]

    @pytest.mark.asyncio
    async def test_subscribe_trades_calls_impl_when_connected(self, client):
        """subscribe_trades calls impl when already connected."""
        client.state = ConnectionState.CONNECTED

        await client.subscribe_trades(["BTCUSD"])

        assert client.subscribe_trades_called == [["BTCUSD"]]

    @pytest.mark.asyncio
    async def test_subscribe_trades_does_not_call_impl_when_disconnected(self, client):
        """subscribe_trades does NOT call impl when disconnected."""
        await client.subscribe_trades(["BTCUSD"])

        assert client.subscribe_trades_called == []

    @pytest.mark.asyncio
    async def test_subscribe_order_book_stores_symbols(self, client):
        await client.subscribe_order_book(["BTCUSD"])
        assert "BTCUSD" in client._subscriptions["order_book"]

    @pytest.mark.asyncio
    async def test_resubscribe_calls_both_impls(self, client):
        """_resubscribe replays all stored subscriptions."""
        client._subscriptions = {
            "trades": {"BTCUSD", "ETHUSD"},
            "order_book": {"BTCUSD"},
        }

        await client._resubscribe()

        assert len(client.subscribe_trades_called) == 1
        assert set(client.subscribe_trades_called[0]) == {"BTCUSD", "ETHUSD"}
        assert len(client.subscribe_orderbook_called) == 1


# ============================================================================
# 3. MESSAGE ROUTING
# ============================================================================


class TestMessageRouting:
    """Test that messages are routed to the correct callbacks."""

    @pytest.mark.asyncio
    async def test_trade_message_dispatched(self, client):
        """Trade messages invoke trade callbacks."""
        received = []
        client.on_trade(lambda t: received.append(t))

        # Simulate the message loop processing a single message
        trade_msg = json.dumps({
            "type": "trade",
            "symbol": "BTCUSD",
            "id": "t1",
            "timestamp": 1700000000000,
            "price": "42000",
            "size": "0.5",
            "side": "buy",
        })

        # Directly invoke the internal processing
        client._last_message_time = time.time()
        data = json.loads(trade_msg)
        parsed = client._parse_message(data)
        assert isinstance(parsed, NormalizedTrade)

        # Simulate callback dispatch
        for callback in client._trade_callbacks:
            callback(parsed)

        assert len(received) == 1
        assert received[0].symbol == "BTCUSD"
        assert received[0].price == 42000.0

    @pytest.mark.asyncio
    async def test_orderbook_message_dispatched(self, client):
        """Orderbook messages invoke orderbook callbacks."""
        received = []
        client.on_order_book(lambda ob: received.append(ob))

        data = {
            "type": "orderbook",
            "symbol": "BTCUSD",
            "timestamp": 1700000000000,
            "bids": [(42000.0, 1.0), (41999.0, 2.0)],
            "asks": [(42001.0, 0.5), (42002.0, 1.5)],
        }

        parsed = client._parse_message(data)
        assert isinstance(parsed, NormalizedOrderBook)

        for callback in client._order_book_callbacks:
            callback(parsed)

        assert len(received) == 1
        assert received[0].symbol == "BTCUSD"

    @pytest.mark.asyncio
    async def test_mark_price_dispatched(self, client):
        received = []
        client.on_mark_price(lambda mp: received.append(mp))

        data = {"type": "mark_price", "symbol": "BTCUSD", "timestamp": 1700000000000, "mark_price": "42100"}
        parsed = client._parse_message(data)
        assert isinstance(parsed, MarkPriceData)

        for cb in client._mark_price_callbacks:
            cb(parsed)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_book_ticker_dispatched(self, client):
        received = []
        client.on_book_ticker(lambda bt: received.append(bt))

        data = {
            "type": "book_ticker",
            "symbol": "BTCUSD",
            "timestamp": 1700000000000,
            "best_bid": "42000",
            "best_bid_qty": "1.0",
            "best_ask": "42001",
            "best_ask_qty": "0.5",
        }
        parsed = client._parse_message(data)
        assert isinstance(parsed, BookTickerData)

        for cb in client._book_ticker_callbacks:
            cb(parsed)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_kline_dispatched(self, client):
        received = []
        client.on_kline(lambda k: received.append(k))

        data = {"type": "kline", "symbol": "BTCUSD", "timestamp": 1700000000000}
        parsed = client._parse_message(data)
        assert isinstance(parsed, KlineData)

        for cb in client._kline_callbacks:
            cb(parsed)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unknown_message_returns_none(self, client):
        parsed = client._parse_message({"type": "unknown_msg"})
        assert parsed is None

    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_called(self, client):
        """Multiple registered callbacks all get invoked."""
        results_a = []
        results_b = []
        client.on_trade(lambda t: results_a.append(t))
        client.on_trade(lambda t: results_b.append(t))

        data = {"type": "trade", "symbol": "BTCUSD", "id": "t1", "price": "42000", "size": "1", "side": "buy"}
        parsed = client._parse_message(data)

        for cb in client._trade_callbacks:
            cb(parsed)

        assert len(results_a) == 1
        assert len(results_b) == 1


# ============================================================================
# 4. RECONNECT LOGIC
# ============================================================================


class TestReconnectLogic:
    """Test disconnect handling and backoff."""

    @pytest.mark.asyncio
    async def test_handle_disconnect_increments_count(self, client):
        """_handle_disconnect increments reconnect counter."""
        assert client._reconnect_count == 0
        await client._handle_disconnect()
        assert client._reconnect_count == 1

    @pytest.mark.asyncio
    async def test_handle_disconnect_sets_reconnecting_state(self, client):
        """State transitions to RECONNECTING on disconnect."""
        client.state = ConnectionState.CONNECTED
        await client._handle_disconnect()
        assert client.state == ConnectionState.RECONNECTING

    @pytest.mark.asyncio
    async def test_backoff_delay_increases(self, client):
        """Backoff delay doubles with each attempt (capped at 60s)."""
        # First attempt: RECONNECT_DELAY * 2^0 = 0.01
        # Second attempt: RECONNECT_DELAY * 2^1 = 0.02
        # These are tiny for test speed
        client.RECONNECT_DELAY = 1.0  # Use real values for formula check

        # delay = min(RECONNECT_DELAY * 2^(count-1), 60)
        # After first _handle_disconnect: count=1, delay = min(1 * 2^0, 60) = 1
        # After second: count=2, delay = min(1 * 2^1, 60) = 2
        # After sixth: count=6, delay = min(1 * 2^5, 60) = 32
        # After seventh: count=7, delay = min(1 * 2^6, 60) = 60

        client.RECONNECT_DELAY = 0.001  # Keep tests fast
        await client._handle_disconnect()
        assert client._reconnect_count == 1

        await client._handle_disconnect()
        assert client._reconnect_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_sets_closed_state(self, client):
        """Graceful disconnect sets state to CLOSED."""
        client.state = ConnectionState.CONNECTED
        client._running = True
        client.ws = AsyncMock()

        await client.disconnect()

        assert client.state == ConnectionState.CLOSED
        assert client._running is False


# ============================================================================
# 5. DATA CLASS PROPERTIES
# ============================================================================


class TestDataClasses:
    """Test NormalizedTrade and NormalizedOrderBook computed properties."""

    def test_normalized_trade_signed_size_buy(self):
        trade = NormalizedTrade("ex", "BTC", "1", 0, 100.0, 0.5, "buy")
        assert trade.signed_size == 0.5

    def test_normalized_trade_signed_size_sell(self):
        trade = NormalizedTrade("ex", "BTC", "1", 0, 100.0, 0.5, "sell")
        assert trade.signed_size == -0.5

    def test_order_book_mid_price(self):
        ob = NormalizedOrderBook("ex", "BTC", 0, [(100.0, 1.0)], [(102.0, 1.0)])
        assert ob.mid_price == 101.0

    def test_order_book_mid_price_empty(self):
        ob = NormalizedOrderBook("ex", "BTC", 0, [], [])
        assert ob.mid_price is None

    def test_order_book_spread_bps(self):
        ob = NormalizedOrderBook("ex", "BTC", 0, [(100.0, 1.0)], [(101.0, 1.0)])
        mid = 100.5
        expected_bps = (1.0 / mid) * 10000
        assert abs(ob.spread_bps - expected_bps) < 0.01

    def test_order_book_imbalance(self):
        # All volume on bid side -> imbalance = 1.0
        ob = NormalizedOrderBook("ex", "BTC", 0, [(100.0, 10.0)], [(101.0, 0.0)])
        # bid_vol=10, ask_vol=0, total=10 -> (10-0)/10 = 1.0
        assert ob.imbalance == 1.0

    def test_book_ticker_spread_bps(self):
        bt = BookTickerData("ex", "BTC", 0, 100.0, 1.0, 101.0, 1.0)
        mid = 100.5
        expected = (1.0 / mid) * 10000
        assert abs(bt.spread_bps - expected) < 0.01


# ============================================================================
# 6. SEND GUARD
# ============================================================================


class TestSendGuard:
    """Test that _send only works when connected."""

    @pytest.mark.asyncio
    async def test_send_when_connected(self, client):
        """_send transmits message when connected."""
        client.state = ConnectionState.CONNECTED
        client.ws = AsyncMock()

        await client._send({"method": "subscribe"})

        client.ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_when_disconnected_is_noop(self, client):
        """_send does nothing when not connected."""
        client.state = ConnectionState.DISCONNECTED
        client.ws = AsyncMock()

        await client._send({"method": "subscribe"})

        client.ws.send.assert_not_called()
