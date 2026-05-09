"""
Unified Exchange Client using ccxt.

Drop-in replacement for CryptoComRESTClient that supports 100+ exchanges
via the ccxt library. Same interface, same return types.

Activated via: EXCHANGE_BACKEND=ccxt (default: native)

Supported exchanges (tested):
    - cryptocom (Crypto.com)
    - binance, binanceusdm (Binance spot/futures)
    - bybit (Bybit)
    - okx (OKX)
    - hyperliquid (Hyperliquid)
    - coinbasepro / coinbaseadvanced (Coinbase)

Usage:
    from Fast_Swarm.exchanges.ccxt_client import CCXTClient

    client = CCXTClient(
        exchange_id="cryptocom",
        api_key="...",
        api_secret="...",
    )
    balance = await client.get_account_balance()
"""

import logging
import os
from typing import Any

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

# Symbol mapping: Fast_Swarm format → ccxt format
# CryptoComRESTClient uses "BTCUSD-PERP"; ccxt uses "BTC/USD:USD"
# We normalize both directions.
_PERP_SUFFIX = "-PERP"


def _to_ccxt_symbol(symbol: str) -> str:
    """Convert Fast_Swarm instrument name to ccxt unified symbol."""
    if symbol.endswith(_PERP_SUFFIX):
        base_quote = symbol[: -len(_PERP_SUFFIX)]
        # BTCUSD-PERP → BTC/USD:USD
        # Try common splits: 3-char base (BTC, ETH, SOL, etc.)
        for split_pos in (3, 4):
            if len(base_quote) > split_pos:
                base = base_quote[:split_pos]
                quote = base_quote[split_pos:]
                return f"{base}/{quote}:{quote}"
        return symbol  # Fallback — pass through
    # Spot: BTC_USDT → BTC/USDT
    if "_" in symbol:
        return symbol.replace("_", "/")
    return symbol


def _from_ccxt_symbol(symbol: str) -> str:
    """Convert ccxt unified symbol back to Fast_Swarm format."""
    # BTC/USD:USD → BTCUSD-PERP
    if ":" in symbol:
        market_part = symbol.split(":")[0]
        return market_part.replace("/", "") + _PERP_SUFFIX
    # BTC/USDT → BTC_USDT
    if "/" in symbol:
        return symbol.replace("/", "_")
    return symbol


class CCXTClient:
    """
    Unified exchange client using ccxt.

    Implements the same interface as CryptoComRESTClient so callers
    can swap with zero code changes. Also satisfies the ExchangeClient
    ABC from portfolio_agent_service.py.
    """

    def __init__(
        self,
        exchange_id: str = "cryptocom",
        api_key: str = "",
        api_secret: str = "",
        password: str = "",
        use_sandbox: bool = False,
        timeout: float = 10.0,
    ):
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {exchange_id}. Check ccxt.exchanges.")

        config: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "timeout": int(timeout * 1000),
            "enableRateLimit": True,
        }
        if password:
            config["password"] = password

        self._exchange: ccxt.Exchange = exchange_class(config)
        self._exchange_id = exchange_id

        if use_sandbox:
            self._exchange.set_sandbox_mode(True)

    async def close(self):
        """Close the exchange connection."""
        await self._exchange.close()

    # =========================================================================
    # Account Methods (matches CryptoComRESTClient interface)
    # =========================================================================

    async def get_account_balance(self) -> dict[str, float]:
        """Get account balances by asset."""
        try:
            balance = await self._exchange.fetch_balance()
        except Exception as e:
            logger.error("Failed to get balance from %s: %s", self._exchange_id, e)
            return {}

        result: dict[str, float] = {}
        free = balance.get("free", {})
        for asset, amount in free.items():
            if amount and float(amount) > 0:
                result[asset] = float(amount)
        return result

    async def get_positions(self) -> list[dict]:
        """Get all open positions."""
        try:
            positions = await self._exchange.fetch_positions()
        except Exception as e:
            logger.error("Failed to get positions from %s: %s", self._exchange_id, e)
            return []

        result = []
        for pos in positions:
            contracts = float(pos.get("contracts", 0) or 0)
            if contracts == 0:
                continue
            result.append({
                "symbol": _from_ccxt_symbol(pos.get("symbol", "")),
                "side": pos.get("side", "long"),
                "size": abs(contracts),
                "entry_price": float(pos.get("entryPrice", 0) or 0),
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0) or 0),
                "cost": float(pos.get("initialMargin", 0) or 0),
            })
        return result

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        size: float,
    ) -> dict:
        """Place a market order."""
        ccxt_symbol = _to_ccxt_symbol(symbol)
        try:
            order = await self._exchange.create_order(
                symbol=ccxt_symbol,
                type="market",
                side=side.lower(),
                amount=size,
            )
        except Exception as e:
            logger.error("Market order failed on %s: %s", self._exchange_id, e)
            return {"error": "order_failed", "message": str(e)}

        return {
            "order_id": order.get("id"),
            "client_oid": order.get("clientOrderId"),
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": float(order.get("average", 0) or 0),
            "status": _map_status(order.get("status", "")),
            "commission": float(order.get("fee", {}).get("cost", 0) or 0) if order.get("fee") else 0,
        }

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """Place a limit order."""
        ccxt_symbol = _to_ccxt_symbol(symbol)
        params: dict[str, Any] = {}
        if time_in_force.upper() != "GTC":
            params["timeInForce"] = time_in_force.upper()

        try:
            order = await self._exchange.create_order(
                symbol=ccxt_symbol,
                type="limit",
                side=side.lower(),
                amount=size,
                price=price,
                params=params,
            )
        except Exception as e:
            logger.error("Limit order failed on %s: %s", self._exchange_id, e)
            return {"error": "order_failed", "message": str(e)}

        return {
            "order_id": order.get("id"),
            "client_oid": order.get("clientOrderId"),
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": price,
            "status": _map_status(order.get("status", "")),
            "commission": float(order.get("fee", {}).get("cost", 0) or 0) if order.get("fee") else 0,
        }

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        ccxt_symbol = _to_ccxt_symbol(symbol)
        try:
            await self._exchange.cancel_order(order_id, ccxt_symbol)
            return True
        except Exception as e:
            logger.error("Failed to cancel order %s on %s: %s", order_id, self._exchange_id, e)
            return False

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        """Get order status and details."""
        ccxt_symbol = _to_ccxt_symbol(symbol)
        try:
            order = await self._exchange.fetch_order(order_id, ccxt_symbol)
        except Exception as e:
            logger.error("Failed to get order %s from %s: %s", order_id, self._exchange_id, e)
            return {"error": "fetch_failed", "message": str(e)}

        return {
            "order_id": order.get("id"),
            "symbol": symbol,
            "side": (order.get("side") or "").lower(),
            "type": (order.get("type") or "").lower(),
            "size": float(order.get("amount", 0) or 0),
            "price": float(order.get("price", 0) or 0) if order.get("price") else None,
            "filled_size": float(order.get("filled", 0) or 0),
            "avg_price": float(order.get("average", 0) or 0) if order.get("average") else 0,
            "status": _map_status(order.get("status", "")),
            "commission": float(order.get("fee", {}).get("cost", 0) or 0) if order.get("fee") else 0,
            "created_at": order.get("timestamp"),
            "updated_at": order.get("lastTradeTimestamp"),
        }

    async def get_ticker(self, symbol: str) -> dict:
        """Get current ticker for a symbol."""
        ccxt_symbol = _to_ccxt_symbol(symbol)
        try:
            ticker = await self._exchange.fetch_ticker(ccxt_symbol)
        except Exception as e:
            logger.error("Failed to get ticker for %s from %s: %s", symbol, self._exchange_id, e)
            return {"symbol": symbol, "price": 0, "bid": 0, "ask": 0}

        return {
            "symbol": symbol,
            "price": float(ticker.get("last", 0) or 0),
            "bid": float(ticker.get("bid", 0) or 0),
            "ask": float(ticker.get("ask", 0) or 0),
            "volume_24h": float(ticker.get("baseVolume", 0) or 0),
            "high_24h": float(ticker.get("high", 0) or 0),
            "low_24h": float(ticker.get("low", 0) or 0),
        }

    # =========================================================================
    # Additional Trading Methods (matches CryptoComRESTClient)
    # =========================================================================

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """Get all open orders, optionally filtered by symbol."""
        ccxt_symbol = _to_ccxt_symbol(symbol) if symbol else None
        try:
            orders = await self._exchange.fetch_open_orders(ccxt_symbol)
        except Exception as e:
            logger.error("Failed to get open orders from %s: %s", self._exchange_id, e)
            return []

        return [
            {
                "order_id": o.get("id"),
                "symbol": _from_ccxt_symbol(o.get("symbol", "")),
                "side": (o.get("side") or "").lower(),
                "type": (o.get("type") or "").lower(),
                "size": float(o.get("amount", 0) or 0),
                "price": float(o.get("price", 0) or 0) if o.get("price") else None,
                "filled_size": float(o.get("filled", 0) or 0),
                "status": o.get("status"),
            }
            for o in orders
        ]

    async def cancel_all_orders(self, symbol: str | None = None) -> int:
        """Cancel all open orders, optionally filtered by symbol."""
        ccxt_symbol = _to_ccxt_symbol(symbol) if symbol else None
        try:
            result = await self._exchange.cancel_all_orders(ccxt_symbol)
            if isinstance(result, list):
                return len(result)
            return 1
        except Exception as e:
            logger.error("Failed to cancel all orders on %s: %s", self._exchange_id, e)
            return 0

    async def close_position(self, symbol: str) -> dict:
        """Close entire position for a symbol using market order."""
        positions = await self.get_positions()
        position = next((p for p in positions if p["symbol"] == symbol), None)

        if not position:
            return {"error": "no_position", "message": f"No open position for {symbol}"}

        close_side = "sell" if position["side"] == "long" else "buy"
        return await self.place_market_order(symbol, close_side, position["size"])

    async def get_instruments(self) -> list[dict]:
        """Get list of tradeable instruments."""
        try:
            await self._exchange.load_markets()
            return [
                {
                    "instrument_name": _from_ccxt_symbol(sym),
                    "base_currency": market.get("base"),
                    "quote_currency": market.get("quote"),
                    "type": market.get("type"),
                    "active": market.get("active"),
                }
                for sym, market in self._exchange.markets.items()
                if market.get("active")
            ]
        except Exception as e:
            logger.error("Failed to get instruments from %s: %s", self._exchange_id, e)
            return []

    def get_status(self) -> dict[str, Any]:
        """Get client status."""
        return {
            "exchange": self._exchange_id,
            "base_url": getattr(self._exchange, "urls", {}).get("api", ""),
            "rate_limit": self._exchange.rateLimit,
            "timeout": self._exchange.timeout,
        }


# =============================================================================
# Status Mapping
# =============================================================================


def _map_status(ccxt_status: str) -> str:
    """Map ccxt order status to Fast_Swarm common format."""
    return {
        "open": "pending",
        "closed": "filled",
        "canceled": "cancelled",
        "expired": "expired",
        "rejected": "rejected",
    }.get(ccxt_status, ccxt_status)


# =============================================================================
# Factory Function (matches create_cryptocom_client API)
# =============================================================================


def create_exchange_client(
    exchange_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    password: str | None = None,
    use_sandbox: bool = False,
) -> CCXTClient:
    """
    Create a unified exchange client.

    Reads from environment if credentials not provided:
        EXCHANGE_ID (default: cryptocom)
        EXCHANGE_API_KEY / CRYPTOCOM_API_KEY
        EXCHANGE_API_SECRET / CRYPTOCOM_API_SECRET
        EXCHANGE_PASSWORD (for exchanges like OKX that need passphrase)

    Args:
        exchange_id: ccxt exchange identifier
        api_key: API key
        api_secret: API secret
        password: Exchange passphrase (OKX, etc.)
        use_sandbox: Use sandbox/testnet

    Returns:
        Configured CCXTClient instance
    """
    eid = exchange_id or os.environ.get("EXCHANGE_ID", "cryptocom")
    key = api_key or os.environ.get("EXCHANGE_API_KEY") or os.environ.get("CRYPTOCOM_API_KEY", "")
    secret = api_secret or os.environ.get("EXCHANGE_API_SECRET") or os.environ.get("CRYPTOCOM_API_SECRET", "")
    pwd = password or os.environ.get("EXCHANGE_PASSWORD", "")

    if not key or not secret:
        logger.warning(
            "Exchange API credentials not provided for %s. "
            "Set EXCHANGE_API_KEY/EXCHANGE_API_SECRET or exchange-specific env vars.",
            eid,
        )

    return CCXTClient(
        exchange_id=eid,
        api_key=key,
        api_secret=secret,
        password=pwd,
        use_sandbox=use_sandbox,
    )
