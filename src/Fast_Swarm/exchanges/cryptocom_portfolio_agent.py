"""
Crypto.com Portfolio Agent.

Adapter wrapping the existing CryptoComRESTClient to match the ExchangeClient ABC.
Crypto-only, 24/7 trading.
"""

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    AssetClass,
    ExchangeClient,
    PortfolioAgent,
)


class CryptoComExchangeClient(ExchangeClient):
    """Adapter wrapping existing Crypto.com REST client to match ExchangeClient ABC."""

    exchange_name = "crypto.com"

    def __init__(self, rest_client=None):
        """
        Initialize with existing REST client instance.

        Args:
            rest_client: Existing CryptoComRESTClient instance (or None for lazy init).
        """
        self._client = rest_client

    def _get_client(self):
        """Get or create the REST client."""
        if self._client is None:
            try:
                from Fast_Swarm.exchanges.cryptocom_rest import create_cryptocom_client
                self._client = create_cryptocom_client()
            except ImportError:
                raise ImportError("Exchange client not found in exchanges/cryptocom_rest.py")
        return self._client

    async def initialize(self) -> bool:
        """Initialize connection."""
        try:
            client = self._get_client()
            # Test connection by getting balance
            await client.get_account_balance()
            return True
        except Exception as e:
            print(f"[Crypto.com] Init failed: {e}")
            return False

    async def get_account_balance(self) -> dict[str, float]:
        """Get account balance."""
        client = self._get_client()
        return await client.get_account_balance()

    async def get_positions(self) -> list[dict]:
        """Get open positions."""
        client = self._get_client()
        return await client.get_positions()

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        """Place a market order."""
        client = self._get_client()
        return await client.place_market_order(symbol, side, size)

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float, time_in_force: str = "GTC"
    ) -> dict:
        """Place a limit order."""
        client = self._get_client()
        return await client.place_limit_order(symbol, side, size, price, time_in_force)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        client = self._get_client()
        return await client.cancel_order(order_id, symbol)

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        """Get order status."""
        client = self._get_client()
        return await client.get_order_status(order_id, symbol)

    async def get_ticker(self, symbol: str) -> dict:
        """Get latest ticker."""
        client = self._get_client()
        return await client.get_ticker(symbol)

    def classify_asset(self, symbol: str) -> AssetClass:
        """All Crypto.com assets are crypto."""
        return AssetClass.CRYPTO


class CryptoComPortfolioAgent(PortfolioAgent):
    """Crypto.com portfolio agent - crypto-only, 24/7."""

    def __init__(self, client: CryptoComExchangeClient, risk_limits=None):
        super().__init__(exchange_name="crypto.com", client=client, risk_limits=risk_limits)
