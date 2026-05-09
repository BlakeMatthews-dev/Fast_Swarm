"""
Crypto.com Exchange REST API client for order execution.

API Documentation: https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html

Production Endpoint: https://api.crypto.com/exchange/v1/{method}
UAT Sandbox: https://uat-api.3ona.co/exchange/v1/{method}

Authentication: API Key + HMAC-SHA256 signature
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CryptoComRESTClient:
    """
    Crypto.com Exchange REST API client for trading operations.

    Implements the ExchangeClient interface from portfolio_agent_service.py
    for integration with the Portfolio Agent.

    Supports:
    - Account balance queries
    - Position management
    - Market and limit orders
    - Order cancellation and status
    """

    BASE_URL = "https://api.crypto.com/exchange/v1"
    UAT_BASE_URL = "https://uat-api.3ona.co/exchange/v1"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        use_sandbox: bool = False,
        timeout: float = 10.0,
    ):
        """
        Initialize crypto.com REST client.

        Args:
            api_key: Crypto.com API key
            api_secret: Crypto.com API secret
            use_sandbox: If True, use UAT sandbox environment
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.UAT_BASE_URL if use_sandbox else self.BASE_URL
        self.timeout = timeout
        self._request_id = 1

        # HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    # =========================================================================
    # Authentication
    # =========================================================================

    def _generate_signature(self, method: str, params: dict, nonce: int) -> str:
        """
        Generate HMAC-SHA256 signature for request.

        Signature format:
        method + id + api_key + sorted_params_string + nonce

        Args:
            method: API method name
            params: Request parameters
            nonce: Unix timestamp in milliseconds

        Returns:
            Hex-encoded signature string
        """
        # Sort params alphabetically and create param string
        param_string = ""
        if params:
            sorted_keys = sorted(params.keys())
            param_string = "".join(f"{k}{params[k]}" for k in sorted_keys)

        # Build signature payload
        sig_payload = f"{method}{self._request_id}{self.api_key}{param_string}{nonce}"

        # Create HMAC-SHA256 signature for API request authentication
        # Note: This is HMAC for message signing, NOT password hashing.
        # HMAC-SHA256 is the industry standard for API authentication (used by AWS, Stripe, all exchanges).
        # CodeQL py/weak-sensitive-data-hashing is a false positive here - api_secret is a
        # pre-shared signing key, not a password being stored.
        signature = hmac.new(  # noqa: S324
            self.api_secret.encode("utf-8"),
            sig_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    async def _signed_request(self, method: str, params: dict | None = None) -> dict:
        """
        Make an authenticated request.

        Args:
            method: API method name (e.g., 'private/get-account-summary')
            params: Request parameters

        Returns:
            API response dict
        """
        if params is None:
            params = {}

        nonce = int(time.time() * 1000)
        signature = self._generate_signature(method, params, nonce)

        request_body = {
            "id": self._request_id,
            "method": method,
            "params": params,
            "api_key": self.api_key,
            "sig": signature,
            "nonce": nonce,
        }
        self._request_id += 1

        try:
            response = await self._client.post(f"/{method}", json=request_body)
            response.raise_for_status()
            data = response.json()

            # Check for API-level errors
            if data.get("code") != 0:
                logger.error(
                    "Crypto.com API error: %s - %s",
                    data.get("code"),
                    data.get("message"),
                )
                return {
                    "error": str(data.get("code")),
                    "message": data.get("message", "Unknown error"),
                }

            return data.get("result", {})

        except httpx.HTTPStatusError as e:
            logger.error("Crypto.com HTTP error: %s", e)
            return {"error": "http_error", "message": str(e)}
        except Exception as e:
            logger.error("Crypto.com request error: %s", e)
            return {"error": "request_error", "message": str(e)}

    async def _public_request(self, method: str, params: dict | None = None) -> dict:
        """
        Make a public (unauthenticated) request.

        Args:
            method: API method name
            params: Request parameters

        Returns:
            API response dict
        """
        if params is None:
            params = {}

        request_body = {
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        self._request_id += 1

        try:
            response = await self._client.post(f"/{method}", json=request_body)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                return {
                    "error": str(data.get("code")),
                    "message": data.get("message", "Unknown error"),
                }

            return data.get("result", {})

        except Exception as e:
            logger.error("Crypto.com public request error: %s", e)
            return {"error": "request_error", "message": str(e)}

    # =========================================================================
    # Account Methods (ExchangeClient interface)
    # =========================================================================

    async def get_account_balance(self) -> dict[str, float]:
        """
        Get account balances by asset.

        Returns:
            Dict mapping asset symbol to available balance
        """
        result = await self._signed_request("private/user-balance")

        if "error" in result:
            logger.error("Failed to get balance: %s", result.get("message"))
            return {}

        balances = {}

        # Extract position balances (collateral assets)
        for pos in result.get("position_balances", []):
            asset = pos.get("instrument_name", "")
            quantity = float(pos.get("quantity", 0))
            if asset and quantity > 0:
                balances[asset] = quantity

        # Total available for trading (in USD)
        total_available = result.get("total_available_balance")
        if total_available:
            balances["USD"] = float(total_available)

        return balances

    async def get_positions(self) -> list[dict]:
        """
        Get all open positions.

        Returns:
            List of position dicts with symbol, side, size, entry_price
        """
        result = await self._signed_request("private/get-positions")

        if "error" in result:
            logger.error("Failed to get positions: %s", result.get("message"))
            return []

        positions = []
        for pos in result.get("data", []):
            quantity = float(pos.get("quantity", 0))
            if quantity == 0:
                continue

            positions.append({
                "symbol": pos.get("instrument_name"),
                "side": "long" if quantity > 0 else "short",
                "size": abs(quantity),
                "entry_price": float(pos.get("avg_price", 0)),
                "unrealized_pnl": float(pos.get("open_position_pnl", 0)),
                "cost": float(pos.get("cost", 0)),
            })

        return positions

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        size: float,
    ) -> dict:
        """
        Place a market order.

        Args:
            symbol: Instrument name (e.g., 'BTCUSD-PERP')
            side: 'buy' or 'sell'
            size: Order size in base currency

        Returns:
            Order result dict with order_id, status, etc.
        """
        params = {
            "instrument_name": symbol,
            "side": side.upper(),
            "type": "MARKET",
        }

        # Crypto.com uses 'quantity' for sells, 'notional' for buys
        # We'll use quantity for both since we specify base currency size
        params["quantity"] = str(size)

        result = await self._signed_request("private/create-order", params)

        if "error" in result:
            return result

        return {
            "order_id": result.get("order_id"),
            "client_oid": result.get("client_oid"),
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": float(result.get("avg_price", 0)) if result.get("avg_price") else 0,
            "status": result.get("status", "submitted"),
            "commission": 0,  # Calculated separately if needed
        }

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """
        Place a limit order.

        Args:
            symbol: Instrument name
            side: 'buy' or 'sell'
            size: Order size in base currency
            price: Limit price
            time_in_force: GTC, IOC, FOK

        Returns:
            Order result dict
        """
        # Map common TIF to crypto.com format
        tif_map = {
            "GTC": "GOOD_TILL_CANCEL",
            "IOC": "IMMEDIATE_OR_CANCEL",
            "FOK": "FILL_OR_KILL",
        }

        params = {
            "instrument_name": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "price": str(price),
            "quantity": str(size),
            "time_in_force": tif_map.get(time_in_force.upper(), "GOOD_TILL_CANCEL"),
        }

        result = await self._signed_request("private/create-order", params)

        if "error" in result:
            return result

        return {
            "order_id": result.get("order_id"),
            "client_oid": result.get("client_oid"),
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": price,
            "status": result.get("status", "submitted"),
            "commission": 0,
        }

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel
            symbol: Instrument name (required by some exchanges)

        Returns:
            True if cancelled successfully
        """
        params = {"order_id": order_id}
        result = await self._signed_request("private/cancel-order", params)

        if "error" in result:
            logger.error("Failed to cancel order %s: %s", order_id, result.get("message"))
            return False

        return True

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        """
        Get order status and details.

        Args:
            order_id: Order ID to query
            symbol: Instrument name

        Returns:
            Order status dict
        """
        params = {"order_id": order_id}
        result = await self._signed_request("private/get-order-detail", params)

        if "error" in result:
            return result

        order_info = result.get("order_info", {})

        # Map crypto.com status to common format
        status_map = {
            "NEW": "pending",
            "PENDING": "pending",
            "ACTIVE": "open",
            "FILLED": "filled",
            "CANCELED": "cancelled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }

        return {
            "order_id": order_info.get("order_id"),
            "symbol": order_info.get("instrument_name"),
            "side": order_info.get("side", "").lower(),
            "type": order_info.get("type", "").lower(),
            "size": float(order_info.get("quantity", 0)),
            "price": float(order_info.get("price", 0)) if order_info.get("price") else None,
            "filled_size": float(order_info.get("cumulative_quantity", 0)),
            "avg_price": float(order_info.get("avg_price", 0)) if order_info.get("avg_price") else 0,
            "status": status_map.get(order_info.get("status"), "unknown"),
            "commission": float(order_info.get("cumulative_fee", 0)),
            "created_at": order_info.get("create_time"),
            "updated_at": order_info.get("update_time"),
        }

    async def get_ticker(self, symbol: str) -> dict:
        """
        Get current ticker for a symbol.

        Args:
            symbol: Instrument name

        Returns:
            Ticker dict with price, bid, ask
        """
        params = {"instrument_name": symbol}
        result = await self._public_request("public/get-ticker", params)

        if "error" in result:
            return {"symbol": symbol, "price": 0, "bid": 0, "ask": 0}

        data = result.get("data", {})

        return {
            "symbol": symbol,
            "price": float(data.get("a", 0)),  # Last trade price
            "bid": float(data.get("b", 0)),  # Best bid
            "ask": float(data.get("k", 0)),  # Best ask
            "volume_24h": float(data.get("v", 0)),  # 24h volume
            "high_24h": float(data.get("h", 0)),  # 24h high
            "low_24h": float(data.get("l", 0)),  # 24h low
        }

    # =========================================================================
    # Additional Trading Methods
    # =========================================================================

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional instrument name filter

        Returns:
            List of open order dicts
        """
        params = {}
        if symbol:
            params["instrument_name"] = symbol

        result = await self._signed_request("private/get-open-orders", params)

        if "error" in result:
            return []

        orders = []
        for order in result.get("data", []):
            orders.append({
                "order_id": order.get("order_id"),
                "symbol": order.get("instrument_name"),
                "side": order.get("side", "").lower(),
                "type": order.get("type", "").lower(),
                "size": float(order.get("quantity", 0)),
                "price": float(order.get("price", 0)) if order.get("price") else None,
                "filled_size": float(order.get("cumulative_quantity", 0)),
                "status": order.get("status"),
            })

        return orders

    async def cancel_all_orders(self, symbol: str | None = None) -> int:
        """
        Cancel all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional instrument name filter

        Returns:
            Number of orders cancelled
        """
        params = {}
        if symbol:
            params["instrument_name"] = symbol

        result = await self._signed_request("private/cancel-all-orders", params)

        if "error" in result:
            return 0

        return result.get("count", 0)

    async def close_position(self, symbol: str) -> dict:
        """
        Close entire position for a symbol using market order.

        Args:
            symbol: Instrument name

        Returns:
            Order result dict
        """
        # Get current position
        positions = await self.get_positions()
        position = next((p for p in positions if p["symbol"] == symbol), None)

        if not position:
            return {"error": "no_position", "message": f"No open position for {symbol}"}

        # Place closing order
        close_side = "sell" if position["side"] == "long" else "buy"
        return await self.place_market_order(symbol, close_side, position["size"])

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_instruments(self) -> list[dict]:
        """
        Get list of tradeable instruments.

        Returns:
            List of instrument info dicts
        """
        result = await self._public_request("public/get-instruments")

        if "error" in result:
            return []

        return result.get("data", [])

    def get_status(self) -> dict[str, Any]:
        """Get client status."""
        return {
            "base_url": self.base_url,
            "request_id": self._request_id,
            "timeout": self.timeout,
        }


# =============================================================================
# Factory Function
# =============================================================================


def create_cryptocom_client(
    api_key: str | None = None,
    api_secret: str | None = None,
    use_sandbox: bool = False,
) -> CryptoComRESTClient:
    """
    Create an exchange REST client.

    Returns a ccxt-backed unified client when EXCHANGE_BACKEND=ccxt,
    otherwise returns the native CryptoComRESTClient.

    Credentials from environment:
    - CRYPTOCOM_API_KEY / EXCHANGE_API_KEY
    - CRYPTOCOM_API_SECRET / EXCHANGE_API_SECRET
    - EXCHANGE_ID (default: cryptocom, only used with ccxt backend)

    Args:
        api_key: Optional API key
        api_secret: Optional API secret
        use_sandbox: Use sandbox/testnet environment

    Returns:
        Exchange client (native or ccxt, same interface)
    """
    import os

    backend = os.environ.get("EXCHANGE_BACKEND", "native").lower()

    if backend == "ccxt":
        from Fast_Swarm.exchanges.ccxt_client import create_exchange_client

        return create_exchange_client(
            api_key=api_key,
            api_secret=api_secret,
            use_sandbox=use_sandbox,
        )

    key = api_key or os.environ.get("CRYPTOCOM_API_KEY", "")
    secret = api_secret or os.environ.get("CRYPTOCOM_API_SECRET", "")

    if not key or not secret:
        logger.warning(
            "Crypto.com API credentials not provided. "
            "Set CRYPTOCOM_API_KEY and CRYPTOCOM_API_SECRET environment variables."
        )

    return CryptoComRESTClient(
        api_key=key,
        api_secret=secret,
        use_sandbox=use_sandbox,
    )
