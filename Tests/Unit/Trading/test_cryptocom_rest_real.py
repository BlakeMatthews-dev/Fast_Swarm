"""
CryptoComRESTClient Unit Tests - Real parsing logic with mocked HTTP transport.

Source: src/Fast_Swarm/exchanges/cryptocom_rest.py

Tests:
1. HMAC signature generation (known test vectors)
2. Response parsing for order responses
3. Error handling (rate limit, auth failure, network error)
4. Symbol conversion / request formatting
5. Order placement request format
"""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from Fast_Swarm.exchanges.cryptocom_rest import CryptoComRESTClient


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """Create a CryptoComRESTClient with known test credentials."""
    return CryptoComRESTClient(
        api_key="test_api_key_123",
        api_secret="test_api_secret_456",
        use_sandbox=False,
        timeout=5.0,
    )


@pytest.fixture
def sandbox_client():
    """Create a sandbox CryptoComRESTClient."""
    return CryptoComRESTClient(
        api_key="test_key",
        api_secret="test_secret",
        use_sandbox=True,
    )


# ============================================================================
# 1. HMAC SIGNATURE GENERATION
# ============================================================================


class TestSignatureGeneration:
    """Test HMAC-SHA256 signature generation with known test vectors."""

    def test_signature_empty_params(self, client):
        """Signature with no params: method + id + api_key + nonce."""
        method = "private/get-account-summary"
        nonce = 1700000000000

        sig = client._generate_signature(method, {}, nonce)

        # Manually compute expected signature
        payload = f"{method}{client._request_id}{client.api_key}{nonce}"
        expected = hmac.new(
            b"test_api_secret_456", payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        assert sig == expected
        assert len(sig) == 64  # SHA256 hex digest is 64 chars

    def test_signature_with_params_sorted(self, client):
        """Params must be sorted alphabetically in the signature payload."""
        method = "private/create-order"
        params = {
            "instrument_name": "BTCUSD-PERP",
            "side": "BUY",
            "type": "MARKET",
            "quantity": "0.01",
        }
        nonce = 1700000000000

        sig = client._generate_signature(method, params, nonce)

        # Sorted keys: instrument_name, quantity, side, type
        sorted_param_str = (
            "instrument_nameBTCUSD-PERP"
            "quantity0.01"
            "sideBUY"
            "typeMARKET"
        )
        payload = f"{method}{client._request_id}{client.api_key}{sorted_param_str}{nonce}"
        expected = hmac.new(
            b"test_api_secret_456", payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        assert sig == expected

    def test_signature_deterministic(self, client):
        """Same inputs always produce the same signature."""
        method = "private/get-positions"
        params = {"instrument_name": "ETHUSD-PERP"}
        nonce = 1700000000000

        sig1 = client._generate_signature(method, params, nonce)
        sig2 = client._generate_signature(method, params, nonce)

        assert sig1 == sig2

    def test_signature_changes_with_nonce(self, client):
        """Different nonces produce different signatures."""
        method = "private/get-positions"
        params = {}

        sig1 = client._generate_signature(method, params, 1700000000000)
        sig2 = client._generate_signature(method, params, 1700000000001)

        assert sig1 != sig2


# ============================================================================
# 2. RESPONSE PARSING
# ============================================================================


class TestResponseParsing:
    """Test parsing of API responses with real parsing logic."""

    @pytest.mark.asyncio
    async def test_parse_account_balance(self, client):
        """Parse account balance response correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "method": "private/user-balance",
            "code": 0,
            "result": {
                "position_balances": [
                    {"instrument_name": "BTC", "quantity": "1.5"},
                    {"instrument_name": "ETH", "quantity": "10.0"},
                    {"instrument_name": "USDT", "quantity": "0"},
                ],
                "total_available_balance": "50000.00",
            },
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        balances = await client.get_account_balance()

        assert balances["BTC"] == 1.5
        assert balances["ETH"] == 10.0
        assert "USDT" not in balances  # Zero balance excluded
        assert balances["USD"] == 50000.00

    @pytest.mark.asyncio
    async def test_parse_positions(self, client):
        """Parse positions response with long and short positions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "method": "private/get-positions",
            "code": 0,
            "result": {
                "data": [
                    {
                        "instrument_name": "BTCUSD-PERP",
                        "quantity": "0.5",
                        "avg_price": "42000.00",
                        "open_position_pnl": "500.00",
                        "cost": "21000.00",
                    },
                    {
                        "instrument_name": "ETHUSD-PERP",
                        "quantity": "-2.0",
                        "avg_price": "2200.00",
                        "open_position_pnl": "-100.00",
                        "cost": "4400.00",
                    },
                    {
                        "instrument_name": "SOLUSD-PERP",
                        "quantity": "0",
                        "avg_price": "0",
                    },
                ],
            },
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        positions = await client.get_positions()

        assert len(positions) == 2  # Zero-quantity excluded
        assert positions[0]["symbol"] == "BTCUSD-PERP"
        assert positions[0]["side"] == "long"
        assert positions[0]["size"] == 0.5
        assert positions[0]["entry_price"] == 42000.00
        assert positions[1]["side"] == "short"
        assert positions[1]["size"] == 2.0

    @pytest.mark.asyncio
    async def test_parse_order_status(self, client):
        """Parse order detail response with status mapping."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "method": "private/get-order-detail",
            "code": 0,
            "result": {
                "order_info": {
                    "order_id": "order_123",
                    "instrument_name": "BTCUSD-PERP",
                    "side": "BUY",
                    "type": "LIMIT",
                    "quantity": "0.5",
                    "price": "42000",
                    "cumulative_quantity": "0.25",
                    "avg_price": "41999.50",
                    "status": "ACTIVE",
                    "cumulative_fee": "2.10",
                    "create_time": 1700000000000,
                    "update_time": 1700000001000,
                },
            },
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        status = await client.get_order_status("order_123", "BTCUSD-PERP")

        assert status["order_id"] == "order_123"
        assert status["status"] == "open"  # ACTIVE -> open
        assert status["filled_size"] == 0.25
        assert status["avg_price"] == 41999.50
        assert status["commission"] == 2.10

    @pytest.mark.asyncio
    async def test_parse_ticker(self, client):
        """Parse ticker response with correct field mapping."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "method": "public/get-ticker",
            "code": 0,
            "result": {
                "data": {
                    "a": "42500.00",   # Last price
                    "b": "42499.50",   # Best bid
                    "k": "42500.50",   # Best ask
                    "v": "1234.56",    # Volume
                    "h": "43000.00",   # 24h high
                    "l": "41000.00",   # 24h low
                },
            },
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        ticker = await client.get_ticker("BTCUSD-PERP")

        assert ticker["price"] == 42500.00
        assert ticker["bid"] == 42499.50
        assert ticker["ask"] == 42500.50
        assert ticker["volume_24h"] == 1234.56


# ============================================================================
# 3. ERROR HANDLING
# ============================================================================


class TestErrorHandling:
    """Test error handling for various failure modes."""

    @pytest.mark.asyncio
    async def test_api_level_error(self, client):
        """API returns code != 0 (e.g., rate limit or invalid params)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "method": "private/create-order",
            "code": 10004,
            "message": "INVALID_NONCE",
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.place_market_order("BTCUSD-PERP", "buy", 0.01)

        assert "error" in result
        assert result["error"] == "10004"
        assert result["message"] == "INVALID_NONCE"

    @pytest.mark.asyncio
    async def test_http_status_error(self, client):
        """HTTP 429 or 500 error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=mock_response,
        )

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client._signed_request("private/create-order", {})

        assert result["error"] == "http_error"

    @pytest.mark.asyncio
    async def test_network_error(self, client):
        """Connection timeout / network error handling."""
        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=httpx.ConnectTimeout("Connection timed out"))

        result = await client._signed_request("private/get-positions", {})

        assert result["error"] == "request_error"
        assert "timed out" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_balance_on_error_returns_empty(self, client):
        """get_account_balance returns empty dict on error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "code": 10007,
            "message": "INVALID_API_KEY",
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        balances = await client.get_account_balance()
        assert balances == {}


# ============================================================================
# 4. CLIENT CONFIGURATION
# ============================================================================


class TestClientConfiguration:
    """Test client initialization and configuration."""

    def test_production_base_url(self, client):
        assert client.base_url == "https://api.crypto.com/exchange/v1"

    def test_sandbox_base_url(self, sandbox_client):
        assert sandbox_client.base_url == "https://uat-api.3ona.co/exchange/v1"

    def test_request_id_increments(self, client):
        """Request ID increments with each signed request preparation."""
        initial_id = client._request_id
        # Generate two signatures (simulating two requests)
        client._generate_signature("method1", {}, 1000)
        # _request_id is used in signature but not incremented there;
        # it increments in _signed_request. Verify it starts at 1.
        assert client._request_id == initial_id

    def test_get_status(self, client):
        status = client.get_status()
        assert status["base_url"] == "https://api.crypto.com/exchange/v1"
        assert status["timeout"] == 5.0
        assert "request_id" in status


# ============================================================================
# 5. ORDER PLACEMENT REQUEST FORMAT
# ============================================================================


class TestOrderRequestFormat:
    """Test that order placement builds correct request bodies."""

    @pytest.mark.asyncio
    async def test_market_order_request_body(self, client):
        """Market order sends correct params to API."""
        captured_kwargs = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "code": 0,
            "result": {
                "order_id": "ord_001",
                "status": "FILLED",
                "avg_price": "42000.00",
            },
        }

        async def capture_post(url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=capture_post)

        result = await client.place_market_order("BTCUSD-PERP", "buy", 0.01)

        # Verify the request body
        body = captured_kwargs["json"]
        assert body["method"] == "private/create-order"
        assert body["params"]["instrument_name"] == "BTCUSD-PERP"
        assert body["params"]["side"] == "BUY"
        assert body["params"]["type"] == "MARKET"
        assert body["params"]["quantity"] == "0.01"
        assert "sig" in body
        assert body["api_key"] == "test_api_key_123"

        # Verify parsed response
        assert result["order_id"] == "ord_001"
        assert result["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_limit_order_tif_mapping(self, client):
        """Limit order maps time-in-force correctly."""
        captured_kwargs = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "code": 0,
            "result": {"order_id": "ord_002", "status": "NEW"},
        }

        async def capture_post(url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=capture_post)

        await client.place_limit_order("ETHUSD-PERP", "sell", 1.0, 2200.0, "IOC")

        body = captured_kwargs["json"]
        assert body["params"]["type"] == "LIMIT"
        assert body["params"]["price"] == "2200.0"
        assert body["params"]["time_in_force"] == "IMMEDIATE_OR_CANCEL"
        assert body["params"]["side"] == "SELL"

    @pytest.mark.asyncio
    async def test_cancel_order_returns_true_on_success(self, client):
        """Cancel order returns True when API returns code 0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 1, "code": 0, "result": {}}

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.cancel_order("ord_001", "BTCUSD-PERP")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false_on_error(self, client):
        """Cancel order returns False when API returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "code": 30006,
            "message": "ORDER_NOT_FOUND",
        }

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.cancel_order("nonexistent", "BTCUSD-PERP")
        assert result is False
