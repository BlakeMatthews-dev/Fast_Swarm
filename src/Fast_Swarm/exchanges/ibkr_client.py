"""
Interactive Brokers Exchange Client.

Implements ExchangeClient ABC using ib_insync library.
Supports equities, ETFs, futures, and crypto via TWS/Gateway.
Port 7497 = TWS paper, 7496 = TWS live, 4002 = Gateway paper.
"""

import asyncio
import os

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    ExchangeClient,
    AssetClass,
    AccountType,
)


class IBKRExchangeClient(ExchangeClient):
    """Interactive Brokers exchange client via ib_insync."""

    exchange_name = "ibkr"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int = 1,
        account_type: AccountType = AccountType.TAXABLE,
        account_id: str = "",
    ):
        self.host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("IBKR_PORT", "7497"))
        self.client_id = client_id
        self.account_type = account_type
        self.account_id = account_id or os.getenv("IBKR_ACCOUNT_ID", "")
        self._ib = None
        self._ready = False

    def _get_ib(self):
        """Lazy-initialize IB connection object."""
        if self._ib is None:
            try:
                from ib_insync import IB
                self._ib = IB()
            except ImportError:
                raise ImportError("ib_insync not installed. Run: pip install ib_insync")
        return self._ib

    async def initialize(self) -> bool:
        """Connect to TWS/Gateway."""
        try:
            ib = self._get_ib()
            await ib.connectAsync(self.host, self.port, self.client_id)
            if ib.isConnected() and not self.account_id:
                accounts = ib.managedAccounts()
                self.account_id = accounts[0] if accounts else ""
            self._ready = ib.isConnected()
            return self._ready
        except Exception as e:
            print(f"[IBKR] Connection failed: {e}")
            return False

    async def get_account_balance(self) -> dict[str, float]:
        """Get account balance from IBKR."""
        ib = self._get_ib()
        values = ib.accountValues(self.account_id)
        result = {"USD": 0.0, "equity": 0.0, "buying_power": 0.0}
        for v in values:
            if v.tag == "NetLiquidation" and v.currency == "USD":
                result["equity"] = float(v.value)
            elif v.tag == "AvailableFunds" and v.currency == "USD":
                result["USD"] = float(v.value)
                result["buying_power"] = float(v.value)
        return result

    async def get_positions(self) -> list[dict]:
        """Get all open positions."""
        ib = self._get_ib()
        positions = ib.positions(self.account_id)
        return [
            {
                "symbol": p.contract.symbol,
                "side": "long" if p.position > 0 else "short",
                "size": abs(float(p.position)),
                "entry_price": float(p.avgCost),
                "asset_class": self._contract_to_asset_class(p.contract).value,
            }
            for p in positions
        ]

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        """Place a market order via IBKR."""
        from ib_insync import MarketOrder

        ib = self._get_ib()
        contract = self._resolve_contract(symbol)
        await ib.qualifyContractsAsync(contract)

        action = "BUY" if side == "buy" else "SELL"
        order = MarketOrder(action, size)
        trade = ib.placeOrder(contract, order)

        # Wait for fill with timeout
        timeout = 30
        while not trade.isDone() and timeout > 0:
            await asyncio.sleep(1)
            ib.sleep(0)  # Process IB events
            timeout -= 1

        fill_price = trade.orderStatus.avgFillPrice if trade.fills else 0
        return {
            "order_id": str(trade.order.orderId),
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": float(fill_price),
            "status": trade.orderStatus.status,
            "commission": sum(f.commissionReport.commission for f in trade.fills if f.commissionReport) if trade.fills else 0,
            "filled_at": str(trade.fills[-1].time) if trade.fills else "",
        }

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float, time_in_force: str = "GTC"
    ) -> dict:
        """Place a limit order via IBKR."""
        from ib_insync import LimitOrder

        ib = self._get_ib()
        contract = self._resolve_contract(symbol)
        await ib.qualifyContractsAsync(contract)

        action = "BUY" if side == "buy" else "SELL"
        order = LimitOrder(action, size, price)
        trade = ib.placeOrder(contract, order)

        return {
            "order_id": str(trade.order.orderId),
            "symbol": symbol,
            "side": side,
            "size": size,
            "limit_price": price,
            "status": trade.orderStatus.status,
        }

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        ib = self._get_ib()
        for trade in ib.openTrades():
            if str(trade.order.orderId) == order_id:
                ib.cancelOrder(trade.order)
                return True
        return False

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        """Get status of an order."""
        ib = self._get_ib()
        for trade in ib.trades():
            if str(trade.order.orderId) == order_id:
                return {
                    "order_id": order_id,
                    "status": trade.orderStatus.status,
                    "filled_qty": float(trade.orderStatus.filled),
                    "filled_price": float(trade.orderStatus.avgFillPrice),
                }
        return {"order_id": order_id, "status": "unknown", "filled_qty": 0, "filled_price": 0}

    async def get_ticker(self, symbol: str) -> dict:
        """Get latest price for a symbol."""
        ib = self._get_ib()
        contract = self._resolve_contract(symbol)
        try:
            await ib.qualifyContractsAsync(contract)
            ticker = ib.reqMktData(contract, snapshot=True)
            await asyncio.sleep(2)  # Wait for snapshot data
            price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
            return {
                "symbol": symbol,
                "price": float(price or 0),
                "bid": float(ticker.bid or 0),
                "ask": float(ticker.ask or 0),
            }
        except Exception as e:
            print(f"[IBKR] Ticker error for {symbol}: {e}")
            return {"symbol": symbol, "price": 0, "bid": 0, "ask": 0}

    def is_market_open(self, asset_class: AssetClass = AssetClass.CRYPTO) -> bool:
        """Check if market is open for this asset class."""
        if asset_class == AssetClass.CRYPTO:
            return True
        from Fast_Swarm.exchanges.assets import MARKET_HOURS
        from datetime import datetime
        try:
            import pytz
        except ImportError:
            return True  # Assume open if pytz not available
        hours = MARKET_HOURS.get(asset_class.value, MARKET_HOURS["equity"])
        tz = pytz.timezone(hours["timezone"])
        now = datetime.now(tz)
        if now.weekday() not in hours["days"]:
            return False
        open_time = datetime.strptime(hours["open"], "%H:%M").time()
        close_time = datetime.strptime(hours["close"], "%H:%M").time()
        return open_time <= now.time() <= close_time

    def classify_asset(self, symbol: str) -> AssetClass:
        """Classify a symbol into its asset class."""
        from Fast_Swarm.exchanges.assets import BITCOIN_ECOSYSTEM
        if symbol in BITCOIN_ECOSYSTEM.get("crypto", []):
            return AssetClass.CRYPTO
        if symbol in BITCOIN_ECOSYSTEM.get("futures", []):
            return AssetClass.FUTURE
        if symbol in BITCOIN_ECOSYSTEM.get("btc_etf", []) + BITCOIN_ECOSYSTEM.get("crypto_etf", []):
            return AssetClass.ETF
        return AssetClass.EQUITY

    def _resolve_contract(self, symbol: str):
        """Map symbol to IB contract type."""
        from ib_insync import Stock, Crypto, Future
        from Fast_Swarm.exchanges.assets import BITCOIN_ECOSYSTEM
        if symbol in BITCOIN_ECOSYSTEM.get("crypto", []):
            return Crypto(symbol, "PAXOS", "USD")
        elif symbol in BITCOIN_ECOSYSTEM.get("futures", []):
            return Future(symbol.replace("_FUT", ""), exchange="CME", currency="USD")
        else:
            return Stock(symbol, "SMART", "USD")

    def _contract_to_asset_class(self, contract) -> AssetClass:
        """Determine asset class from IB contract object."""
        sec_type = getattr(contract, "secType", "")
        if sec_type == "CRYPTO":
            return AssetClass.CRYPTO
        elif sec_type == "FUT":
            return AssetClass.FUTURE
        elif sec_type == "STK":
            from Fast_Swarm.exchanges.assets import BITCOIN_ECOSYSTEM
            if contract.symbol in BITCOIN_ECOSYSTEM.get("btc_etf", []) + BITCOIN_ECOSYSTEM.get("crypto_etf", []):
                return AssetClass.ETF
            return AssetClass.EQUITY
        return AssetClass.EQUITY
