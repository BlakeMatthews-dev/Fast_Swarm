"""
Alpaca Exchange Client.

Implements ExchangeClient ABC for Alpaca Markets.
Supports both crypto (24/7) and equities (market hours).
"""

import os

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    ExchangeClient,
    AssetClass,
    AccountType,
)


class AlpacaExchangeClient(ExchangeClient):
    """Alpaca exchange client supporting crypto + equities."""

    exchange_name = "alpaca"

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        account_type: AccountType = AccountType.TAXABLE,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.paper = paper
        self.account_type = account_type
        self._trading_client = None

    def _get_client(self):
        """Lazy-initialize the trading client."""
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(
                self.api_key, self.secret_key, paper=self.paper
            )
        return self._trading_client

    async def get_account_balance(self) -> dict[str, float]:
        client = self._get_client()
        acct = client.get_account()
        return {
            "USD": float(acct.cash),
            "equity": float(acct.equity),
            "buying_power": float(acct.buying_power),
        }

    async def get_positions(self) -> list[dict]:
        client = self._get_client()
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "side": "long" if float(p.qty) > 0 else "short",
                "size": abs(float(p.qty)),
                "entry_price": float(p.avg_entry_price),
                "asset_class": self.classify_asset(p.symbol).value,
            }
            for p in positions
        ]

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = self._get_client()
        req = MarketOrderRequest(
            symbol=self._normalize_symbol(symbol),
            qty=size,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        return {
            "order_id": str(order.id),
            "symbol": symbol,
            "side": side,
            "size": float(order.filled_qty or size),
            "price": float(order.filled_avg_price or 0),
            "status": order.status.value,
            "commission": 0,
            "filled_at": str(order.filled_at or ""),
        }

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float, time_in_force: str = "GTC"
    ) -> dict:
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = self._get_client()
        req = LimitOrderRequest(
            symbol=self._normalize_symbol(symbol),
            qty=size,
            limit_price=price,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        order = client.submit_order(req)
        return {
            "order_id": str(order.id),
            "symbol": symbol,
            "side": side,
            "size": size,
            "limit_price": price,
            "status": order.status.value,
        }

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        client = self._get_client()
        try:
            client.cancel_order_by_id(order_id)
            return True
        except Exception:
            return False

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        client = self._get_client()
        order = client.get_order_by_id(order_id)
        return {
            "order_id": order_id,
            "status": order.status.value,
            "filled_qty": float(order.filled_qty or 0),
            "filled_price": float(order.filled_avg_price or 0),
        }

    async def get_ticker(self, symbol: str) -> dict:
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoLatestQuoteRequest

            asset_class = self.classify_asset(symbol)
            normalized = self._normalize_symbol(symbol)

            if asset_class == AssetClass.CRYPTO:
                data_client = CryptoHistoricalDataClient(self.api_key, self.secret_key)
                req = CryptoLatestQuoteRequest(symbol_or_symbols=normalized)
                quotes = data_client.get_crypto_latest_quote(req)
                quote = quotes.get(normalized)
                if quote:
                    return {"symbol": symbol, "price": float(quote.ask_price),
                            "bid": float(quote.bid_price), "ask": float(quote.ask_price)}
        except Exception as e:
            print(f"[Alpaca] Ticker error for {symbol}: {e}")
        return {"symbol": symbol, "price": 0, "bid": 0, "ask": 0}

    def is_market_open(self, asset_class: AssetClass = AssetClass.CRYPTO) -> bool:
        if asset_class == AssetClass.CRYPTO:
            return True
        try:
            client = self._get_client()
            clock = client.get_clock()
            return clock.is_open
        except Exception:
            return False

    def classify_asset(self, symbol: str) -> AssetClass:
        from Fast_Swarm.exchanges.assets import BITCOIN_ECOSYSTEM
        if symbol in BITCOIN_ECOSYSTEM.get("crypto", []):
            return AssetClass.CRYPTO
        if symbol in BITCOIN_ECOSYSTEM.get("btc_etf", []) + BITCOIN_ECOSYSTEM.get("crypto_etf", []):
            return AssetClass.ETF
        if symbol in BITCOIN_ECOSYSTEM.get("futures", []):
            return AssetClass.FUTURE
        return AssetClass.EQUITY

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for Alpaca. BTC -> BTC/USD for crypto."""
        from Fast_Swarm.exchanges.assets import BITCOIN_ECOSYSTEM
        if "/" in symbol or "-" in symbol:
            base = symbol.replace("-", "/").split("/")[0]
            return f"{base}/USD"
        if symbol in BITCOIN_ECOSYSTEM.get("crypto", []):
            return f"{symbol}/USD"
        return symbol
