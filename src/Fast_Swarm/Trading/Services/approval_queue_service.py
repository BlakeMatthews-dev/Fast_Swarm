"""
Approval Queue Service - Manages pending trades for APPROVAL mode.

Handles:
- Queuing trades that need user approval
- Auto-executing bear protection exits (bypass approval)
- Processing approved trades as limit orders
- Expiring stale pending trades
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Trading.Models.trading_models import (
    ApprovalStatus,
    ExecutionResult,
    PendingTrade,
    SignalType,
    TradingConfig,
    TradingMode,
)


class ApprovalQueueService:
    """
    Service for managing the approval queue in APPROVAL trading mode.

    Architecture:
    - Pending trades are stored in memory (with DB persistence for recovery)
    - Bear protection exits bypass the queue entirely
    - Approved trades are executed as limit orders with a price buffer
    - Expired trades are automatically rejected
    """

    def __init__(self):
        # In-memory queue: agent_id -> list of PendingTrade
        self.pending_queues: dict[str, list[PendingTrade]] = {}

        # Agent configurations: agent_id -> TradingConfig
        self.agent_configs: dict[str, TradingConfig] = {}

        # Execution callback (set by the trading service)
        self._execute_callback = None

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    def set_execute_callback(self, callback):
        """Set the callback for executing approved trades."""
        self._execute_callback = callback

    def configure_agent(self, config: TradingConfig) -> None:
        """Configure trading mode for an agent."""
        self.agent_configs[config.agent_id] = config
        if config.agent_id not in self.pending_queues:
            self.pending_queues[config.agent_id] = []

    def get_agent_mode(self, agent_id: str) -> TradingMode:
        """Get the trading mode for an agent."""
        config = self.agent_configs.get(agent_id)
        if config is None:
            return TradingMode.PAPER_ONLY  # Default
        return config.mode

    async def submit_trade(
        self,
        session: AsyncSession,
        agent_id: str,
        agent_name: str,
        symbol: str,
        side: str,
        signal_type: SignalType,
        suggested_price: float,
        size: float,
        size_usd: float,
        reason: str,
        pattern_id: str | None = None,
        pattern_name: str | None = None,
        regime: str | None = None,
        entry_signals: dict[str, Any] | None = None,
    ) -> dict:
        """
        Submit a trade signal for processing based on trading mode.

        Returns:
            dict with status and details:
            - PAPER_ONLY: {"action": "paper_recorded", ...}
            - APPROVAL + bear protection: {"action": "auto_executed", ...}
            - APPROVAL + normal: {"action": "queued", "trade_id": ..., ...}
            - FULL_AUTO: {"action": "executing", ...}
        """
        config = self.agent_configs.get(agent_id)
        mode = config.mode if config else TradingMode.PAPER_ONLY

        # Generate unique trade ID
        trade_id = f"trade-{uuid.uuid4().hex[:12]}"

        # Calculate expiration time
        timeout_minutes = config.approval_timeout_minutes if config else 60
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

        # Create pending trade object
        pending_trade = PendingTrade(
            trade_id=trade_id,
            agent_id=agent_id,
            agent_name=agent_name,
            symbol=symbol,
            side=side,
            signal_type=signal_type,
            suggested_price=suggested_price,
            size=size,
            size_usd=size_usd,
            reason=reason,
            pattern_id=pattern_id,
            pattern_name=pattern_name,
            regime=regime,
            expires_at=expires_at,
            entry_signals=entry_signals,
        )

        # Route based on mode
        if mode == TradingMode.PAPER_ONLY:
            return await self._handle_paper_only(pending_trade)

        elif mode == TradingMode.APPROVAL:
            return await self._handle_approval_mode(session, pending_trade)

        elif mode == TradingMode.FULL_AUTO:
            return await self._handle_full_auto(session, pending_trade)

        return {"error": f"Unknown trading mode: {mode}"}

    async def _handle_paper_only(self, trade: PendingTrade) -> dict:
        """Handle trade in PAPER_ONLY mode - just record, no queue."""
        return {
            "action": "paper_recorded",
            "trade_id": trade.trade_id,
            "agent_id": trade.agent_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "signal_type": trade.signal_type.value,
            "suggested_price": trade.suggested_price,
            "size": trade.size,
            "size_usd": trade.size_usd,
            "reason": trade.reason,
            "message": "Trade recorded as paper trade only",
        }

    async def _handle_approval_mode(
        self, session: AsyncSession, trade: PendingTrade
    ) -> dict:
        """
        Handle trade in APPROVAL mode.

        Bear protection exits auto-execute immediately.
        All other trades go to the approval queue.
        """
        # Bear protection bypasses approval
        if trade.is_bear_protection():
            trade.status = ApprovalStatus.AUTO_EXECUTED
            result = await self._execute_as_limit_order(session, trade)
            return {
                "action": "auto_executed",
                "trade_id": trade.trade_id,
                "reason": "bear_protection_bypass",
                "execution": result,
                "message": "Bear protection exit auto-executed (bypassed approval)",
            }

        # Add to approval queue
        async with self._lock:
            if trade.agent_id not in self.pending_queues:
                self.pending_queues[trade.agent_id] = []
            self.pending_queues[trade.agent_id].append(trade)

        return {
            "action": "queued",
            "trade_id": trade.trade_id,
            "agent_id": trade.agent_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "signal_type": trade.signal_type.value,
            "suggested_price": trade.suggested_price,
            "size": trade.size,
            "size_usd": trade.size_usd,
            "reason": trade.reason,
            "expires_at": trade.expires_at.isoformat() if trade.expires_at else None,
            "message": "Trade queued for approval",
        }

    async def _handle_full_auto(
        self, session: AsyncSession, trade: PendingTrade
    ) -> dict:
        """Handle trade in FULL_AUTO mode - execute immediately as limit order."""
        trade.status = ApprovalStatus.AUTO_EXECUTED
        result = await self._execute_as_limit_order(session, trade)
        return {
            "action": "auto_executed",
            "trade_id": trade.trade_id,
            "reason": "full_auto_mode",
            "execution": result,
            "message": "Trade auto-executed in FULL_AUTO mode",
        }

    async def _execute_as_limit_order(
        self, session: AsyncSession, trade: PendingTrade
    ) -> dict:
        """
        Execute a trade as a limit order with buffer.

        Buy orders: limit price = suggested_price * (1 + buffer_pct)
        Sell orders: limit price = suggested_price * (1 - buffer_pct)
        """
        config = self.agent_configs.get(trade.agent_id)
        buffer_pct = config.limit_buffer_pct if config else 0.001  # Default 0.1%

        # Calculate limit price based on side
        if trade.side.lower() in ["buy", "long"]:
            # Buy: willing to pay slightly more
            limit_price = trade.suggested_price * (1 + buffer_pct / 100)
        else:
            # Sell: willing to accept slightly less
            limit_price = trade.suggested_price * (1 - buffer_pct / 100)

        trade.limit_price = limit_price
        trade.approval_time = datetime.now(timezone.utc)

        # Call execution callback if set
        if self._execute_callback:
            try:
                result = await self._execute_callback(
                    session=session,
                    trade_id=trade.trade_id,
                    agent_id=trade.agent_id,
                    symbol=trade.symbol,
                    side=trade.side,
                    size=trade.size,
                    limit_price=limit_price,
                    order_type="limit",
                )
                return {
                    "success": True,
                    "limit_price": limit_price,
                    "buffer_pct": buffer_pct,
                    "order_result": result,
                }
            except Exception as e:
                return {
                    "success": False,
                    "limit_price": limit_price,
                    "error": str(e),
                }

        # No callback - return simulated result
        return {
            "success": True,
            "limit_price": limit_price,
            "buffer_pct": buffer_pct,
            "simulated": True,
            "message": "No execution callback configured",
        }

    # =========================================================================
    # APPROVAL QUEUE MANAGEMENT
    # =========================================================================

    async def get_pending_trades(
        self, agent_id: str | None = None
    ) -> list[dict]:
        """Get all pending trades, optionally filtered by agent."""
        await self._cleanup_expired()

        result = []
        async with self._lock:
            if agent_id:
                trades = self.pending_queues.get(agent_id, [])
                for trade in trades:
                    if trade.status == ApprovalStatus.PENDING:
                        result.append(self._trade_to_dict(trade))
            else:
                for trades in self.pending_queues.values():
                    for trade in trades:
                        if trade.status == ApprovalStatus.PENDING:
                            result.append(self._trade_to_dict(trade))

        return result

    async def approve_trade(
        self, session: AsyncSession, trade_id: str
    ) -> dict:
        """
        Approve a pending trade and execute it as a limit order.

        Returns execution result or error if trade not found/expired.
        """
        await self._cleanup_expired()

        async with self._lock:
            trade = self._find_trade(trade_id)
            if trade is None:
                return {"error": f"Trade {trade_id} not found"}

            if trade.status != ApprovalStatus.PENDING:
                return {"error": f"Trade {trade_id} is not pending (status: {trade.status.value})"}

            if trade.is_expired():
                trade.status = ApprovalStatus.EXPIRED
                return {"error": f"Trade {trade_id} has expired"}

            # Mark as approved
            trade.status = ApprovalStatus.APPROVED

        # Execute the trade
        result = await self._execute_as_limit_order(session, trade)

        # Remove from queue after execution
        async with self._lock:
            self._remove_trade(trade_id)

        return {
            "status": "approved",
            "trade_id": trade_id,
            "agent_id": trade.agent_id,
            "symbol": trade.symbol,
            "execution": result,
        }

    async def reject_trade(self, trade_id: str, reason: str = "") -> dict:
        """Reject a pending trade."""
        async with self._lock:
            trade = self._find_trade(trade_id)
            if trade is None:
                return {"error": f"Trade {trade_id} not found"}

            if trade.status != ApprovalStatus.PENDING:
                return {"error": f"Trade {trade_id} is not pending (status: {trade.status.value})"}

            trade.status = ApprovalStatus.REJECTED
            self._remove_trade(trade_id)

        return {
            "status": "rejected",
            "trade_id": trade_id,
            "agent_id": trade.agent_id,
            "symbol": trade.symbol,
            "reason": reason,
        }

    async def approve_all(
        self, session: AsyncSession, agent_id: str
    ) -> dict:
        """Approve all pending trades for an agent."""
        await self._cleanup_expired()

        results = []
        errors = []

        async with self._lock:
            trades = self.pending_queues.get(agent_id, [])
            pending = [t for t in trades if t.status == ApprovalStatus.PENDING]

        for trade in pending:
            result = await self.approve_trade(session, trade.trade_id)
            if "error" in result:
                errors.append(result)
            else:
                results.append(result)

        return {
            "agent_id": agent_id,
            "approved_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
        }

    async def reject_all(self, agent_id: str, reason: str = "") -> dict:
        """Reject all pending trades for an agent."""
        async with self._lock:
            trades = self.pending_queues.get(agent_id, [])
            pending = [t for t in trades if t.status == ApprovalStatus.PENDING]

        results = []
        for trade in pending:
            result = await self.reject_trade(trade.trade_id, reason)
            results.append(result)

        return {
            "agent_id": agent_id,
            "rejected_count": len(results),
            "reason": reason,
            "results": results,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _find_trade(self, trade_id: str) -> PendingTrade | None:
        """Find a trade by ID across all queues. Must hold lock."""
        for trades in self.pending_queues.values():
            for trade in trades:
                if trade.trade_id == trade_id:
                    return trade
        return None

    def _remove_trade(self, trade_id: str) -> bool:
        """Remove a trade from all queues. Must hold lock."""
        for agent_id, trades in self.pending_queues.items():
            for i, trade in enumerate(trades):
                if trade.trade_id == trade_id:
                    trades.pop(i)
                    return True
        return False

    async def _cleanup_expired(self) -> int:
        """Mark expired trades and remove them. Returns count of expired."""
        count = 0
        async with self._lock:
            for trades in self.pending_queues.values():
                for trade in trades:
                    if trade.status == ApprovalStatus.PENDING and trade.is_expired():
                        trade.status = ApprovalStatus.EXPIRED
                        count += 1

            # Remove all non-pending trades
            for agent_id in list(self.pending_queues.keys()):
                self.pending_queues[agent_id] = [
                    t for t in self.pending_queues[agent_id]
                    if t.status == ApprovalStatus.PENDING
                ]

        return count

    def _trade_to_dict(self, trade: PendingTrade) -> dict:
        """Convert a PendingTrade to a dictionary for API responses."""
        return {
            "trade_id": trade.trade_id,
            "agent_id": trade.agent_id,
            "agent_name": trade.agent_name,
            "symbol": trade.symbol,
            "side": trade.side,
            "signal_type": trade.signal_type.value,
            "suggested_price": trade.suggested_price,
            "size": trade.size,
            "size_usd": trade.size_usd,
            "reason": trade.reason,
            "pattern_id": trade.pattern_id,
            "pattern_name": trade.pattern_name,
            "regime": trade.regime,
            "created_at": trade.created_at.isoformat(),
            "expires_at": trade.expires_at.isoformat() if trade.expires_at else None,
            "status": trade.status.value,
            "is_bear_protection": trade.is_bear_protection(),
        }

    def get_queue_stats(self) -> dict:
        """Get statistics about the approval queue."""
        total_pending = 0
        by_agent = {}

        for agent_id, trades in self.pending_queues.items():
            pending_count = len([t for t in trades if t.status == ApprovalStatus.PENDING])
            if pending_count > 0:
                by_agent[agent_id] = pending_count
                total_pending += pending_count

        return {
            "total_pending": total_pending,
            "agents_with_pending": len(by_agent),
            "by_agent": by_agent,
        }


# Singleton instance
_approval_queue_service: ApprovalQueueService | None = None


def get_approval_queue_service() -> ApprovalQueueService:
    """Get the singleton ApprovalQueueService instance."""
    global _approval_queue_service
    if _approval_queue_service is None:
        _approval_queue_service = ApprovalQueueService()
    return _approval_queue_service
