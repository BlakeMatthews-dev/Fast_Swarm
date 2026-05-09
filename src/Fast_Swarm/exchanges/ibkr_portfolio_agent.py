"""
IBKR Portfolio Agent.

Subclass of PortfolioAgent with IBKR-specific features:
- IRA account type enforcement (no shorting, no margin)
- Integer share quantities (no fractional)
- Contract qualification before orders
- TWS connection lifecycle management
"""

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    PortfolioAgent,
    AssetClass,
    AccountType,
)
from Fast_Swarm.exchanges.ibkr_client import IBKRExchangeClient


class IBKRPortfolioAgent(PortfolioAgent):
    """IBKR-specific portfolio agent with IRA + futures support."""

    def __init__(self, client: IBKRExchangeClient, risk_limits=None):
        super().__init__(exchange_name="ibkr", client=client, risk_limits=risk_limits)
        self.account_type = client.account_type

    async def get_ira_restrictions(self) -> dict:
        """Get IRA-specific restrictions."""
        is_ira = self.account_type in (AccountType.IRA_TRADITIONAL, AccountType.IRA_ROTH)
        return {
            "shorting_allowed": not is_ira,
            "margin_allowed": not is_ira,
            "options_level": 0 if is_ira else 4,
            "account_type": self.account_type.value,
        }

    async def _execute_command(self, command):
        """Override: Enforce IRA constraints before execution."""
        if self.account_type in (AccountType.IRA_TRADITIONAL, AccountType.IRA_ROTH):
            # IRA cannot short sell
            if command.side == "sell":
                # Check if we actually hold this position
                positions = await self.client.get_positions()
                held_symbols = [p["symbol"] for p in positions if p["side"] == "long"]
                if command.symbol not in held_symbols:
                    return {
                        "order_id": None,
                        "symbol": command.symbol,
                        "status": "rejected",
                        "error_code": "ira_no_short",
                        "error_message": "IRA accounts cannot short sell",
                    }
        return await super()._execute_command(command)

    async def get_contract_details(self, symbol: str) -> dict:
        """Get full IB contract details (min tick, lot size, etc.)."""
        ib = self.client._get_ib()
        contract = self.client._resolve_contract(symbol)
        try:
            await ib.qualifyContractsAsync(contract)
            details = await ib.reqContractDetailsAsync(contract)
            if details:
                d = details[0]
                return {
                    "min_tick": d.minTick,
                    "trading_hours": d.tradingHours,
                    "long_name": d.longName,
                    "category": d.category,
                }
        except Exception as e:
            print(f"[IBKR] Contract details error for {symbol}: {e}")
        return {}

    async def _calculate_order_size(self, command) -> float:
        """Override: Integer shares only for equities (no fractional at IBKR)."""
        size = await super()._calculate_order_size(command)
        asset_class = self.client.classify_asset(command.symbol)
        if asset_class != AssetClass.CRYPTO:
            size = int(size)  # IBKR requires integer quantities
        return max(size, 1) if size > 0 else 0
