"""
Live Execution Service - Bridges approved trades to Crypto.com exchange.

Handles:
- Executing approved trades as limit orders
- Recording trades in LiveTradeUnified
- Order status tracking
- Emergency market order exits
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.exchanges.cryptocom_rest import CryptoComRESTClient, create_cryptocom_client
from Fast_Swarm.Infrastructure.Models.exchange_models import LiveTradeUnified

logger = logging.getLogger(__name__)


class LiveExecutionService:
    """
    Service for executing trades on Crypto.com exchange.

    Integrates with ApprovalQueueService via callback to execute
    approved trades as limit orders.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        use_sandbox: bool = True,
    ):
        """
        Initialize live execution service.

        Args:
            api_key: Crypto.com API key (or from env CRYPTOCOM_API_KEY)
            api_secret: Crypto.com API secret (or from env CRYPTOCOM_API_SECRET)
            use_sandbox: If True, use UAT sandbox for testing
        """
        self.api_key = api_key or os.getenv("CRYPTOCOM_API_KEY", "")
        self.api_secret = api_secret or os.getenv("CRYPTOCOM_API_SECRET", "")
        self.use_sandbox = use_sandbox
        self._client: CryptoComRESTClient | None = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the crypto.com client.

        Returns:
            True if initialized successfully
        """
        if not self.api_key or not self.api_secret:
            logger.warning(
                "Crypto.com API credentials not configured. "
                "Set CRYPTOCOM_API_KEY and CRYPTOCOM_API_SECRET env vars."
            )
            return False

        try:
            self._client = create_cryptocom_client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                use_sandbox=self.use_sandbox,
            )
            self._initialized = True
            logger.info(
                "Live execution service initialized (sandbox=%s)", self.use_sandbox
            )
            return True
        except Exception as e:
            logger.error("Failed to initialize crypto.com client: %s", e)
            return False

    async def close(self):
        """Close the exchange client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._initialized = False

    def is_ready(self) -> bool:
        """Check if service is ready for trading."""
        return self._initialized and self._client is not None

    # =========================================================================
    # EXECUTION CALLBACK (for ApprovalQueueService)
    # =========================================================================

    async def execute_limit_order(
        self,
        session: AsyncSession,
        trade_id: str,
        agent_id: str,
        symbol: str,
        side: str,
        size: float,
        limit_price: float,
        order_type: str = "limit",
        pattern_id: str | None = None,
        pattern_name: str | None = None,
        regime: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """
        Execute a limit order on the exchange.

        This is the callback used by ApprovalQueueService when trades
        are approved (or auto-executed for bear protection/full_auto).

        Args:
            session: Database session for recording trade
            trade_id: Unique trade ID
            agent_id: Agent requesting the trade
            symbol: Trading symbol (e.g., "BTC-USDT")
            side: "buy"/"long" or "sell"/"short"
            size: Order size in base currency
            limit_price: Limit order price
            order_type: "limit" or "market"
            pattern_id: Optional pattern ID
            pattern_name: Optional pattern name
            regime: Current market regime
            reason: Trade reason

        Returns:
            Execution result dict
        """
        if not self.is_ready():
            # Simulated execution when not connected to exchange
            return await self._simulated_execution(
                session=session,
                trade_id=trade_id,
                agent_id=agent_id,
                symbol=symbol,
                side=side,
                size=size,
                limit_price=limit_price,
                order_type=order_type,
                pattern_id=pattern_id,
                pattern_name=pattern_name,
                regime=regime,
                reason=reason,
            )

        try:
            # Convert symbol format (BTC-USDT -> BTCUSD-PERP)
            exchange_symbol = self._convert_symbol(symbol)

            # Normalize side
            normalized_side = "buy" if side.lower() in ["buy", "long"] else "sell"

            # Place limit order on exchange
            order_result = await self._client.place_limit_order(
                symbol=exchange_symbol,
                side=normalized_side,
                size=size,
                price=limit_price,
                time_in_force="GTC",
            )

            if "error" in order_result:
                logger.error(
                    "Order placement failed for %s: %s",
                    trade_id,
                    order_result.get("message"),
                )
                return {
                    "success": False,
                    "error": order_result.get("message", "Order failed"),
                    "trade_id": trade_id,
                }

            # Record trade in database
            await self._record_trade(
                session=session,
                trade_id=trade_id,
                agent_id=agent_id,
                symbol=symbol,
                side=side,
                size=size,
                requested_price=limit_price,
                fill_price=order_result.get("price"),
                order_id=order_result.get("order_id"),
                order_type=order_type,
                status="open",
                source="live",
                pattern_id=pattern_id,
                pattern_name=pattern_name,
                regime=regime,
                reason=reason,
            )

            return {
                "success": True,
                "trade_id": trade_id,
                "order_id": order_result.get("order_id"),
                "symbol": symbol,
                "side": side,
                "size": size,
                "limit_price": limit_price,
                "status": order_result.get("status", "submitted"),
                "source": "live",
            }

        except Exception as e:
            logger.error("Execution error for %s: %s", trade_id, e)
            return {
                "success": False,
                "error": str(e),
                "trade_id": trade_id,
            }

    async def execute_market_order(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        side: str,
        size: float,
        reason: str = "emergency_exit",
    ) -> dict:
        """
        Execute a market order (for urgent exits like bear protection).

        Args:
            session: Database session
            agent_id: Agent ID
            symbol: Trading symbol
            side: "buy" or "sell"
            size: Order size
            reason: Reason for market order

        Returns:
            Execution result
        """
        trade_id = f"trade-{uuid.uuid4().hex[:12]}"

        if not self.is_ready():
            return {
                "success": False,
                "error": "Exchange not connected",
                "trade_id": trade_id,
            }

        try:
            exchange_symbol = self._convert_symbol(symbol)
            normalized_side = "buy" if side.lower() in ["buy", "long"] else "sell"

            order_result = await self._client.place_market_order(
                symbol=exchange_symbol,
                side=normalized_side,
                size=size,
            )

            if "error" in order_result:
                return {
                    "success": False,
                    "error": order_result.get("message"),
                    "trade_id": trade_id,
                }

            await self._record_trade(
                session=session,
                trade_id=trade_id,
                agent_id=agent_id,
                symbol=symbol,
                side=side,
                size=size,
                requested_price=None,
                fill_price=order_result.get("price"),
                order_id=order_result.get("order_id"),
                order_type="market",
                status="filled",
                source="live",
                reason=reason,
            )

            return {
                "success": True,
                "trade_id": trade_id,
                "order_id": order_result.get("order_id"),
                "fill_price": order_result.get("price"),
                "status": "filled",
            }

        except Exception as e:
            logger.error("Market order error: %s", e)
            return {"success": False, "error": str(e), "trade_id": trade_id}

    # =========================================================================
    # SIMULATED EXECUTION (when exchange not connected)
    # =========================================================================

    async def _simulated_execution(
        self,
        session: AsyncSession,
        trade_id: str,
        agent_id: str,
        symbol: str,
        side: str,
        size: float,
        limit_price: float,
        order_type: str,
        pattern_id: str | None = None,
        pattern_name: str | None = None,
        regime: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """
        Simulate order execution when exchange is not connected.

        Records trade as "paper" source for tracking without real execution.
        """
        logger.info(
            "Simulated execution: %s %s %s @ %s (no exchange connection)",
            side,
            size,
            symbol,
            limit_price,
        )

        await self._record_trade(
            session=session,
            trade_id=trade_id,
            agent_id=agent_id,
            symbol=symbol,
            side=side,
            size=size,
            requested_price=limit_price,
            fill_price=limit_price,  # Assume fill at limit in simulation
            order_id=None,
            order_type=order_type,
            status="open",
            source="paper",  # Mark as paper since not real execution
            pattern_id=pattern_id,
            pattern_name=pattern_name,
            regime=regime,
            reason=reason,
        )

        return {
            "success": True,
            "trade_id": trade_id,
            "order_id": None,
            "symbol": symbol,
            "side": side,
            "size": size,
            "limit_price": limit_price,
            "status": "simulated",
            "source": "paper",
            "message": "Simulated - exchange not connected",
        }

    # =========================================================================
    # DATABASE RECORDING
    # =========================================================================

    async def _record_trade(
        self,
        session: AsyncSession,
        trade_id: str,
        agent_id: str,
        symbol: str,
        side: str,
        size: float,
        requested_price: float | None,
        fill_price: float | None,
        order_id: str | None,
        order_type: str,
        status: str,
        source: str,
        pattern_id: str | None = None,
        pattern_name: str | None = None,
        regime: str | None = None,
        reason: str | None = None,
    ) -> LiveTradeUnified:
        """Record a trade in the database."""
        # Calculate size_usd
        price = fill_price or requested_price or 0
        size_usd = size * price

        # Calculate slippage if we have both prices
        slippage_pct = None
        if requested_price and fill_price and requested_price > 0:
            slippage_pct = ((fill_price - requested_price) / requested_price) * 100

        trade = LiveTradeUnified(
            trade_id=trade_id,
            agent_id=agent_id,
            exchange="crypto.com",
            symbol=symbol,
            side=side,
            size=Decimal(str(size)),
            size_usd=Decimal(str(size_usd)),
            entry_price=Decimal(str(fill_price)) if fill_price else None,
            entry_time=datetime.now(timezone.utc),
            requested_price=Decimal(str(requested_price)) if requested_price else None,
            slippage_pct=slippage_pct,
            order_type=order_type,
            order_id=order_id,
            status=status,
            source=source,
            pattern_id=pattern_id,
            pattern_name=pattern_name,
            regime=regime,
            exit_reason=reason,
        )

        session.add(trade)
        await session.commit()

        logger.info(
            "Trade recorded: %s %s %s @ %s (%s)",
            trade_id,
            side,
            symbol,
            fill_price or requested_price,
            source,
        )

        return trade

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _convert_symbol(self, symbol: str) -> str:
        """
        Convert symbol format to crypto.com format.

        BTC-USDT -> BTCUSD-PERP (for perpetuals)
        ETH-USDT -> ETHUSD-PERP
        """
        # Simple conversion for common pairs
        base = symbol.replace("-USDT", "").replace("-USD", "")
        return f"{base}USD-PERP"

    async def get_order_status(self, order_id: str, symbol: str) -> dict | None:
        """Get the status of an existing order."""
        if not self.is_ready():
            return None

        exchange_symbol = self._convert_symbol(symbol)
        return await self._client.get_order_status(order_id, exchange_symbol)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order."""
        if not self.is_ready():
            return False

        exchange_symbol = self._convert_symbol(symbol)
        return await self._client.cancel_order(order_id, exchange_symbol)


# Singleton instance
_live_execution_service: LiveExecutionService | None = None


def get_live_execution_service() -> LiveExecutionService:
    """Get the singleton LiveExecutionService instance."""
    global _live_execution_service
    if _live_execution_service is None:
        _live_execution_service = LiveExecutionService()
    return _live_execution_service
