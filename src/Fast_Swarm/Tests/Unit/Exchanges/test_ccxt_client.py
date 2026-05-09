"""
Tests for CryptoComRESTClient - native exchange client via Crypto.com REST API.

Covers account methods, order placement, cancellation, status queries,
ticker, open orders, position close, factory function, and error handling.

Replaces the original ccxt_client tests since the ccxt backend module
does not yet exist. Tests the actual exchange abstraction in use.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.exchanges.cryptocom_rest import (
    CryptoComRESTClient,
    create_cryptocom_client,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def client():
    """Create a CryptoComRESTClient with test credentials."""
    return CryptoComRESTClient(
        api_key="test-key",
        api_secret="test-secret",
        use_sandbox=True,
    )


# =============================================================================
# Constructor & Config Tests
# =============================================================================


class TestClientConfig:
    """Test client initialization and configuration."""

    def test_sandbox_url(self):
        """Sandbox mode uses UAT URL."""
        c = CryptoComRESTClient(api_key="k", api_secret="s", use_sandbox=True)
        assert "uat" in c.base_url

    def test_production_url(self):
        """Production mode uses real URL."""
        c = CryptoComRESTClient(api_key="k", api_secret="s", use_sandbox=False)
        assert c.base_url == CryptoComRESTClient.BASE_URL

    def test_get_status(self, client):
        """get_status returns client info."""
        status = client.get_status()
        assert "base_url" in status
        assert "request_id" in status
        assert "timeout" in status


# =============================================================================
# Signature Tests
# =============================================================================


class TestSignature:
    """Test HMAC signature generation."""

    def test_signature_deterministic(self, client):
        """Same inputs produce same signature."""
        sig1 = client._generate_signature("test-method", {"key": "val"}, 1000)
        sig2 = client._generate_signature("test-method", {"key": "val"}, 1000)
        assert sig1 == sig2

    def test_signature_changes_with_nonce(self, client):
        """Different nonces produce different signatures."""
        sig1 = client._generate_signature("method", {}, 1000)
        sig2 = client._generate_signature("method", {}, 2000)
        assert sig1 != sig2

    def test_signature_changes_with_params(self, client):
        """Different params produce different signatures."""
        sig1 = client._generate_signature("method", {"a": "1"}, 1000)
        sig2 = client._generate_signature("method", {"a": "2"}, 1000)
        assert sig1 != sig2

    def test_signature_is_hex(self, client):
        """Signature is a hex string."""
        sig = client._generate_signature("method", {}, 1000)
        assert all(c in "0123456789abcdef" for c in sig)


# =============================================================================
# Account Methods Tests
# =============================================================================


class TestAccountMethods:
    """Test account balance and position queries."""

    @pytest.mark.asyncio
    async def test_get_account_balance(self, client):
        """Balance returns non-zero balances."""
        mock_result = {
            "position_balances": [
                {"instrument_name": "BTC", "quantity": "0.5"},
                {"instrument_name": "ETH", "quantity": "0.0"},
            ],
            "total_available_balance": "10000.0",
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            balance = await client.get_account_balance()
        assert balance["BTC"] == 0.5
        assert balance["USD"] == 10000.0
        # Zero balances should be excluded
        assert "ETH" not in balance

    @pytest.mark.asyncio
    async def test_get_account_balance_error(self, client):
        """Balance error returns empty dict."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={"error": "api_down", "message": "API down"}):
            balance = await client.get_account_balance()
        assert balance == {}

    @pytest.mark.asyncio
    async def test_get_positions(self, client):
        """Positions returned with correct fields."""
        mock_result = {
            "data": [
                {
                    "instrument_name": "BTCUSD-PERP",
                    "quantity": "0.5",
                    "avg_price": "50000.0",
                    "open_position_pnl": "500.0",
                    "cost": "25000.0",
                }
            ]
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            positions = await client.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSD-PERP"
        assert positions[0]["side"] == "long"
        assert positions[0]["size"] == 0.5

    @pytest.mark.asyncio
    async def test_get_positions_excludes_zero(self, client):
        """Zero-quantity positions are excluded."""
        mock_result = {
            "data": [
                {"instrument_name": "BTCUSD-PERP", "quantity": "0", "avg_price": "0", "open_position_pnl": "0", "cost": "0"},
            ]
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            positions = await client.get_positions()
        assert len(positions) == 0


# =============================================================================
# Order Methods Tests
# =============================================================================


class TestOrderMethods:
    """Test order placement and management."""

    @pytest.mark.asyncio
    async def test_place_market_order(self, client):
        """Market order returns order result."""
        mock_result = {
            "order_id": "ord-1",
            "client_oid": "client-1",
            "avg_price": "50010.0",
            "status": "FILLED",
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            result = await client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert result["order_id"] == "ord-1"
        assert result["symbol"] == "BTCUSD-PERP"
        assert result["side"] == "buy"
        assert result["size"] == 0.1

    @pytest.mark.asyncio
    async def test_place_limit_order(self, client):
        """Limit order passes price and TIF."""
        mock_result = {
            "order_id": "ord-2",
            "status": "NEW",
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result) as mock_req:
            result = await client.place_limit_order("BTCUSD-PERP", "sell", 0.1, 51000.0, "IOC")
        # Verify the signed request was called with correct params
        call_args = mock_req.call_args
        params = call_args[0][1]
        assert params["price"] == "51000.0"
        assert params["time_in_force"] == "IMMEDIATE_OR_CANCEL"
        assert result["order_id"] == "ord-2"

    @pytest.mark.asyncio
    async def test_place_order_error(self, client):
        """Order placement error returns error dict."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={"error": "insufficient_margin", "message": "Insufficient margin"}):
            result = await client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, client):
        """Cancel order returns True on success."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={}):
            result = await client.cancel_order("ord-1", "BTCUSD-PERP")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, client):
        """Cancel order returns False on error."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={"error": "not_found", "message": "Order not found"}):
            result = await client.cancel_order("bad-id", "BTCUSD-PERP")
        assert result is False


# =============================================================================
# Order Status Tests
# =============================================================================


class TestOrderStatus:
    """Test order status queries."""

    @pytest.mark.asyncio
    async def test_get_order_status(self, client):
        """Order status maps crypto.com fields to common format."""
        mock_result = {
            "order_info": {
                "order_id": "ord-1",
                "instrument_name": "BTCUSD-PERP",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.1",
                "price": "50000.0",
                "cumulative_quantity": "0.1",
                "avg_price": "50005.0",
                "status": "FILLED",
                "cumulative_fee": "0.5",
                "create_time": 1700000000000,
                "update_time": 1700000001000,
            }
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            status = await client.get_order_status("ord-1", "BTCUSD-PERP")
        assert status["order_id"] == "ord-1"
        assert status["status"] == "filled"
        assert status["filled_size"] == 0.1
        assert status["avg_price"] == 50005.0
        assert status["commission"] == 0.5

    @pytest.mark.asyncio
    async def test_get_order_status_error(self, client):
        """Order status error returns error dict."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={"error": "not_found", "message": "Not found"}):
            status = await client.get_order_status("bad-id", "BTCUSD-PERP")
        assert "error" in status


# =============================================================================
# Ticker Tests
# =============================================================================


class TestTicker:
    """Test ticker queries."""

    @pytest.mark.asyncio
    async def test_get_ticker(self, client):
        """Ticker returns formatted price data."""
        mock_result = {
            "data": {
                "a": "50000.0",
                "b": "49999.0",
                "k": "50001.0",
                "v": "1000.0",
                "h": "51000.0",
                "l": "49000.0",
            }
        }
        with patch.object(client, "_public_request", new_callable=AsyncMock, return_value=mock_result):
            ticker = await client.get_ticker("BTCUSD-PERP")
        assert ticker["price"] == 50000.0
        assert ticker["bid"] == 49999.0
        assert ticker["ask"] == 50001.0
        assert ticker["volume_24h"] == 1000.0

    @pytest.mark.asyncio
    async def test_get_ticker_error(self, client):
        """Ticker error returns zero values."""
        with patch.object(client, "_public_request", new_callable=AsyncMock, return_value={"error": "timeout", "message": "Timeout"}):
            ticker = await client.get_ticker("BTCUSD-PERP")
        assert ticker["price"] == 0


# =============================================================================
# Additional Methods Tests
# =============================================================================


class TestAdditionalMethods:
    """Test open orders, cancel all, close position."""

    @pytest.mark.asyncio
    async def test_get_open_orders(self, client):
        """Open orders returns list."""
        mock_result = {
            "data": [
                {
                    "order_id": "ord-open-1",
                    "instrument_name": "BTCUSD-PERP",
                    "side": "BUY",
                    "type": "LIMIT",
                    "quantity": "0.1",
                    "price": "49500.0",
                    "cumulative_quantity": "0.0",
                    "status": "ACTIVE",
                }
            ]
        }
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value=mock_result):
            orders = await client.get_open_orders("BTCUSD-PERP")
        assert len(orders) == 1
        assert orders[0]["symbol"] == "BTCUSD-PERP"
        assert orders[0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, client):
        """cancel_all_orders returns count."""
        with patch.object(client, "_signed_request", new_callable=AsyncMock, return_value={"count": 2}):
            count = await client.cancel_all_orders("BTCUSD-PERP")
        assert count == 2

    @pytest.mark.asyncio
    async def test_close_position_no_position(self, client):
        """Closing nonexistent position returns error."""
        with patch.object(client, "get_positions", new_callable=AsyncMock, return_value=[]):
            result = await client.close_position("SOLUSD-PERP")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_close_position_long(self, client):
        """Closing long position places sell market order."""
        positions = [{"symbol": "BTCUSD-PERP", "side": "long", "size": 0.5}]
        mock_order = {"order_id": "close-1", "status": "FILLED"}
        with patch.object(client, "get_positions", new_callable=AsyncMock, return_value=positions):
            with patch.object(client, "place_market_order", new_callable=AsyncMock, return_value=mock_order) as mock_place:
                result = await client.close_position("BTCUSD-PERP")
        mock_place.assert_awaited_once_with("BTCUSD-PERP", "sell", 0.5)
        assert result["order_id"] == "close-1"


# =============================================================================
# Client Lifecycle Tests
# =============================================================================


class TestLifecycle:
    """Test client lifecycle."""

    @pytest.mark.asyncio
    async def test_close(self, client):
        """close() calls HTTP client aclose."""
        with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_close:
            await client.close()
        mock_close.assert_awaited_once()

    def test_get_status(self, client):
        """get_status returns client info."""
        status = client.get_status()
        assert "base_url" in status
        assert "timeout" in status


# =============================================================================
# Factory Tests
# =============================================================================


class TestFactory:
    """Test create_cryptocom_client factory."""

    def test_factory_returns_native_client(self):
        """Default factory returns CryptoComRESTClient."""
        with patch.dict("os.environ", {"EXCHANGE_BACKEND": "native"}, clear=False):
            client = create_cryptocom_client(api_key="k", api_secret="s")
            assert isinstance(client, CryptoComRESTClient)

    def test_factory_sandbox_mode(self):
        """Factory respects sandbox flag."""
        client = create_cryptocom_client(api_key="k", api_secret="s", use_sandbox=True)
        assert "uat" in client.base_url

    def test_factory_from_env(self):
        """Factory reads credentials from environment."""
        with patch.dict("os.environ", {
            "EXCHANGE_BACKEND": "native",
            "CRYPTOCOM_API_KEY": "env-key",
            "CRYPTOCOM_API_SECRET": "env-secret",
        }, clear=False):
            client = create_cryptocom_client()
            assert client.api_key == "env-key"
            assert client.api_secret == "env-secret"
