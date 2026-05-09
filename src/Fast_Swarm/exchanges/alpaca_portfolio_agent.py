"""
Alpaca Portfolio Agent.

Subclass of PortfolioAgent with Alpaca-specific features:
- Fractional shares for crypto, integer for equities
- Notional (dollar-amount) orders
- Market clock awareness
"""

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    PortfolioAgent,
    AssetClass,
)
from Fast_Swarm.exchanges.alpaca_client import AlpacaExchangeClient


class AlpacaPortfolioAgent(PortfolioAgent):
    """Alpaca-specific portfolio agent with equity + crypto support."""

    def __init__(self, client: AlpacaExchangeClient, risk_limits=None):
        super().__init__(exchange_name="alpaca", client=client, risk_limits=risk_limits)

    async def place_notional_order(self, symbol: str, side: str, usd_amount: float) -> dict:
        """Place order by dollar amount (Alpaca supports notional for crypto)."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = self.client._get_client()
        req = MarketOrderRequest(
            symbol=symbol,
            notional=usd_amount,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        return {
            "order_id": str(order.id),
            "symbol": symbol,
            "side": side,
            "notional": usd_amount,
            "status": order.status.value,
        }

    async def get_market_clock(self) -> dict:
        """Get market open/close times for equities."""
        client = self.client._get_client()
        clock = client.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": str(clock.next_open),
            "next_close": str(clock.next_close),
        }

    async def _calculate_order_size(self, command) -> float:
        """Override: Integer shares for equities, fractional for crypto."""
        size = await super()._calculate_order_size(command)
        asset_class = self.client.classify_asset(command.symbol)
        if asset_class != AssetClass.CRYPTO:
            size = round(size)
        return size
