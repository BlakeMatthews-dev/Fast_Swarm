"""
Tests for CryptoComRESTClient - native Crypto.com exchange REST API client.

Covers signature generation, all API methods, error handling,
and factory routing.
"""

import hashlib
import hmac
import time
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
        api_key="test-api-key",
        api_secret="test-api-secret",
        use_sandbox=True,
        timeout=5.0,
    )


@pytest.fixture
def prod_client():
    """Create a production (non-sandbox) client."""
    return CryptoComRESTClient(
        api_key="prod-key",
        api_secret="prod-secret",
        use_sandbox=False,
    )


# =============================================================================
# Initialization Tests (~3 tests)
# =============================================================================


class TestInit:
    """Test client initialization."""

    def test_sandbox_url(self, client):
        """Sandbox client uses UAT base URL."""
        assert "uat-api" in client.base_url

    def test_production_url(self, prod_client):
        """Production client uses api.crypto.com."""
        assert "api.crypto.com" in prod_client.base_url

    def test_initial_request_id(self, client):
        """Request ID starts at 1."""
        assert client._request_id == 1


# =============================================================================
# Signature Generation Tests (~4 tests)
# =============================================================================


class TestSignature:
    """Test HMAC-SHA256 signature generation."""

    def test_signature_produces_hex_string(self, client):
        """Signature is a valid hex string."""
        sig = client._generate_signature("private/get-account-summary", {}, 1234567890)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest

    def test_signature_changes_with_params(self, client):
        """Different params produce different signatures."""
        sig1 = client._generate_signature("private/create-order", {"side": "BUY"}, 1000)
        sig2 = client._generate_signature("private/create-order", {"side": "SELL"}, 1000)
        assert sig1 != sig2

    def test_signature_changes_with_nonce(self, client):
        """Different nonces produce different signatures."""
        sig1 = client._generate_signature("private/create-order", {}, 1000)
        sig2 = client._generate_signature("private/create-order", {}, 2000)
        assert sig1 != sig2

    def test_signature_matches_manual_computation(self, client):
        """Signature matches manual HMAC-SHA256 computation."""
        method = "private/test"
        params = {"a": "1", "b": "2"}
        nonce = 9999

        # Manual computation matching the client's algorithm
        param_string = "a1b2"  # sorted keys
        sig_payload = f"{method}{client._request_id}{client.api_key}{param_string}{nonce}"
        expected = hmac.new(
            client.api_secret.encode("utf-8"),
            sig_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        result = client._generate_signature(method, params, nonce)
        assert result == expected


# =============================================================================
# Account Method Tests (~3 tests)
# =============================================================================


class TestAccountMethods:
    """Test account balance and position queries."""

    @pytest.mark.asyncio
    async def test_get_account_balance_success(self, client):
        """Successful balance query returns asset balances."""
        mock_response = {
            "position_balances": [
                {"instrument_name": "BTC", "quantity": "0.5"},
                {"instrument_name": "ETH", "quantity": "10.0"},
            ],
            "total_available_balance": "50000.0",
        }
        client._signed_request = AsyncMock(return_value=mock_response)

        balances = await client.get_account_balance()
        assert balances["BTC"] == 0.5
        assert balances["ETH"] == 10.0
        assert balances["USD"] == 50000.0

    @pytest.mark.asyncio
    async def test_get_account_balance_error(self, client):
        """Balance query error returns empty dict."""
        client._signed_request = AsyncMock(return_value={"error": "unauthorized"})
        balances = await client.get_account_balance()
        assert balances == {}

    @pytest.mark.asyncio
    async def test_get_positions_success(self, client):
        """Successful position query returns formatted positions."""
        mock_response = {
            "data": [
                {
                    "instrument_name": "BTCUSD-PERP",
                    "quantity": "0.5",
                    "avg_price": "50000",
                    "open_position_pnl": "500",
                    "cost": "25000",
                },
                {
                    "instrument_name": "ETHUSD-PERP",
                    "quantity": "-1.0",
                    "avg_price": "3000",
                    "open_position_pnl": "-50",
                    "cost": "3000",
                },
            ]
        }
        client._signed_request = AsyncMock(return_value=mock_response)

        positions = await client.get_positions()
        assert len(positions) == 2
        assert positions[0]["symbol"] == "BTCUSD-PERP"
        assert positions[0]["side"] == "long"
        assert positions[0]["size"] == 0.5
        assert positions[1]["side"] == "short"
        assert positions[1]["size"] == 1.0


# =============================================================================
# Order Method Tests (~5 tests)
# =============================================================================


class TestOrderMethods:
    """Test order placement, cancellation, and status."""

    @pytest.mark.asyncio
    async def test_place_market_order(self, client):
        """Market order sends correct params."""
        client._signed_request = AsyncMock(return_value={
            "order_id": "o1",
            "avg_price": "50010",
            "status": "FILLED",
        })

        result = await client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert result["order_id"] == "o1"
        assert result["status"] == "FILLED"

        call_args = client._signed_request.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("params", {})
        assert params["type"] == "MARKET"
        assert params["side"] == "BUY"

    @pytest.mark.asyncio
    async def test_place_limit_order(self, client):
        """Limit order sends correct params including TIF."""
        client._signed_request = AsyncMock(return_value={
            "order_id": "o2",
            "status": "ACTIVE",
        })

        result = await client.place_limit_order("BTCUSD-PERP", "sell", 0.1, 51000.0, "IOC")
        assert result["order_id"] == "o2"
        assert result["price"] == 51000.0

        call_args = client._signed_request.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("params", {})
        assert params["type"] == "LIMIT"
        assert params["time_in_force"] == "IMMEDIATE_OR_CANCEL"

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, client):
        """Cancel order returns True on success."""
        client._signed_request = AsyncMock(return_value={})
        result = await client.cancel_order("o1", "BTCUSD-PERP")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, client):
        """Cancel order returns False on error."""
        client._signed_request = AsyncMock(return_value={
            "error": "order_not_found",
            "message": "Order not found",
        })
        result = await client.cancel_order("bad-id", "BTCUSD-PERP")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_order_status(self, client):
        """Order status maps crypto.com status to common format."""
        client._signed_request = AsyncMock(return_value={
            "order_info": {
                "order_id": "o1",
                "instrument_name": "BTCUSD-PERP",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.1",
                "price": "50000",
                "cumulative_quantity": "0.05",
                "avg_price": "50010",
                "status": "ACTIVE",
                "cumulative_fee": "0.25",
            }
        })

        status = await client.get_order_status("o1", "BTCUSD-PERP")
        assert status["status"] == "open"
        assert status["filled_size"] == 0.05
        assert status["commission"] == 0.25


# =============================================================================
# Ticker & Public Methods (~2 tests)
# =============================================================================


class TestPublicMethods:
    """Test public API methods."""

    @pytest.mark.asyncio
    async def test_get_ticker(self, client):
        """Ticker returns price data."""
        client._public_request = AsyncMock(return_value={
            "data": {
                "a": "50000",
                "b": "49999",
                "k": "50001",
                "v": "1000",
                "h": "51000",
                "l": "49000",
            }
        })

        ticker = await client.get_ticker("BTCUSD-PERP")
        assert ticker["price"] == 50000.0
        assert ticker["bid"] == 49999.0
        assert ticker["ask"] == 50001.0
        assert ticker["volume_24h"] == 1000.0

    @pytest.mark.asyncio
    async def test_get_ticker_error(self, client):
        """Ticker error returns zero values."""
        client._public_request = AsyncMock(return_value={"error": "timeout"})
        ticker = await client.get_ticker("BTCUSD-PERP")
        assert ticker["price"] == 0
        assert ticker["bid"] == 0


# =============================================================================
# Error Handling Tests (~4 tests)
# =============================================================================


class TestErrorHandling:
    """Test error handling for various HTTP and API errors."""

    @pytest.mark.asyncio
    async def test_api_level_error(self, client):
        """Non-zero API code returns error dict."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 10006,
            "message": "INSUFFICIENT_BALANCE",
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client._signed_request("private/create-order", {"side": "BUY"})
        assert "error" in result
        assert result["message"] == "INSUFFICIENT_BALANCE"

    @pytest.mark.asyncio
    async def test_http_error(self, client):
        """HTTP status error returns error dict."""
        import httpx

        client._client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_response
        )
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client._signed_request("private/create-order")
        assert "error" in result
        assert result["error"] == "http_error"

    @pytest.mark.asyncio
    async def test_connection_error(self, client):
        """Connection error returns error dict."""
        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=ConnectionError("DNS failed"))

        result = await client._signed_request("private/get-account-summary")
        assert "error" in result
        assert result["error"] == "request_error"

    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """close() calls aclose on underlying httpx client."""
        client._client = AsyncMock()
        await client.close()
        client._client.aclose.assert_awaited_once()


# =============================================================================
# Additional Trading Methods (~2 tests)
# =============================================================================


class TestAdditionalMethods:
    """Test open orders, cancel all, close position."""

    @pytest.mark.asyncio
    async def test_get_open_orders(self, client):
        """Open orders returns list of order dicts."""
        client._signed_request = AsyncMock(return_value={
            "data": [
                {
                    "order_id": "o1",
                    "instrument_name": "BTCUSD-PERP",
                    "side": "BUY",
                    "type": "LIMIT",
                    "quantity": "0.1",
                    "price": "49000",
                    "cumulative_quantity": "0",
                    "status": "ACTIVE",
                }
            ]
        })
        orders = await client.get_open_orders("BTCUSD-PERP")
        assert len(orders) == 1
        assert orders[0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, client):
        """cancel_all_orders returns count."""
        client._signed_request = AsyncMock(return_value={"count": 3})
        count = await client.cancel_all_orders("BTCUSD-PERP")
        assert count == 3


# =============================================================================
# Factory Tests (~2 tests)
# =============================================================================


class TestFactory:
    """Test create_cryptocom_client factory."""

    def test_native_client_created_by_default(self):
        """Default backend creates native CryptoComRESTClient."""
        with patch.dict("os.environ", {"EXCHANGE_BACKEND": "native"}, clear=False):
            client = create_cryptocom_client(api_key="k", api_secret="s")
            assert isinstance(client, CryptoComRESTClient)

    def test_ccxt_backend_creates_ccxt_client(self):
        """EXCHANGE_BACKEND=ccxt creates CCXTClient."""
        with patch.dict("os.environ", {"EXCHANGE_BACKEND": "ccxt"}, clear=False):
            with patch(
                "Fast_Swarm.exchanges.ccxt_client.create_exchange_client"
            ) as mock_ccxt:
                mock_ccxt.return_value = MagicMock()
                client = create_cryptocom_client(api_key="k", api_secret="s")
                mock_ccxt.assert_called_once()

    def test_status(self, client):
        """get_status returns client info."""
        status = client.get_status()
        assert "base_url" in status
        assert "request_id" in status
        assert "timeout" in status
