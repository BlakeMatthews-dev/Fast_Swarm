"""
ApprovalQueueService Integration Tests - Real Models, Real Queue State.

Tests the three-mode trading system approval queue using real model objects.
The service is mostly in-memory with DB persistence for execution callbacks.

Source: src/Fast_Swarm/Trading/Services/approval_queue_service.py
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Trading.Models.trading_models import (
    ApprovalStatus,
    PendingTrade,
    SignalType,
    TradingConfig,
    TradingMode,
)
from Fast_Swarm.Trading.Services.approval_queue_service import ApprovalQueueService


# ============================================================================
# HELPERS
# ============================================================================


def make_approval_service(
    *,
    agent_id: str = "agent-test",
    mode: TradingMode = TradingMode.PAPER_ONLY,
    timeout_minutes: int = 60,
    limit_buffer_pct: float = 0.1,
    execute_callback=None,
) -> ApprovalQueueService:
    """Create a configured ApprovalQueueService."""
    service = ApprovalQueueService()
    config = TradingConfig(
        agent_id=agent_id,
        mode=mode,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
        limit_buffer_pct=limit_buffer_pct,
        approval_timeout_minutes=timeout_minutes,
    )
    service.configure_agent(config)
    if execute_callback is not None:
        service.set_execute_callback(execute_callback)
    return service


async def submit_standard_trade(
    service: ApprovalQueueService,
    session: AsyncSession,
    *,
    agent_id: str = "agent-test",
    agent_name: str = "Test Agent",
    symbol: str = "BTC-USDT",
    side: str = "long",
    signal_type: SignalType = SignalType.ENTRY_LONG,
    price: float = 50000.0,
    size: float = 0.02,
    size_usd: float = 1000.0,
    reason: str = "RSI oversold entry",
    pattern_id: str | None = "pat-001",
    regime: str | None = "bull",
) -> dict:
    """Submit a standard trade through the service."""
    return await service.submit_trade(
        session=session,
        agent_id=agent_id,
        agent_name=agent_name,
        symbol=symbol,
        side=side,
        signal_type=signal_type,
        suggested_price=price,
        size=size,
        size_usd=size_usd,
        reason=reason,
        pattern_id=pattern_id,
        regime=regime,
    )


# ============================================================================
# TEST: PAPER_ONLY Mode
# ============================================================================


class TestPaperOnlyMode:
    """In PAPER_ONLY mode, trades are recorded but never queued or executed."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_paper_only_records_trade(self, db_session: AsyncSession):
        """Submit in PAPER_ONLY mode returns paper_recorded action."""
        service = make_approval_service(mode=TradingMode.PAPER_ONLY)

        result = await submit_standard_trade(service, db_session)

        assert result["action"] == "paper_recorded"
        assert result["symbol"] == "BTC-USDT"
        assert result["side"] == "long"
        assert result["signal_type"] == "entry_long"
        assert result["suggested_price"] == 50000.0
        assert result["size"] == 0.02
        assert result["size_usd"] == 1000.0
        assert result["reason"] == "RSI oversold entry"
        assert "trade_id" in result

    @pytest.mark.asyncio
    async def test_paper_only_does_not_queue(self, db_session: AsyncSession):
        """PAPER_ONLY trades do not appear in the pending queue."""
        service = make_approval_service(mode=TradingMode.PAPER_ONLY)

        await submit_standard_trade(service, db_session)

        pending = await service.get_pending_trades("agent-test")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_paper_only_does_not_call_callback(self, db_session: AsyncSession):
        """PAPER_ONLY mode never invokes the execution callback."""
        callback = AsyncMock()
        service = make_approval_service(
            mode=TradingMode.PAPER_ONLY, execute_callback=callback
        )

        await submit_standard_trade(service, db_session)

        callback.assert_not_called()


# ============================================================================
# TEST: APPROVAL Mode - Normal Trades Queued
# ============================================================================


class TestApprovalModeQueued:
    """In APPROVAL mode, normal trades are queued as pending."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_normal_trade_queued_as_pending(self, db_session: AsyncSession):
        """Normal entry signal in APPROVAL mode is queued."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )

        assert result["action"] == "queued"
        assert result["message"] == "Trade queued for approval"
        assert result["symbol"] == "BTC-USDT"
        assert result["side"] == "long"
        assert result["signal_type"] == "entry_long"
        assert "trade_id" in result
        assert result["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_queued_trade_appears_in_pending_list(self, db_session: AsyncSession):
        """Queued trade is visible via get_pending_trades."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 1
        assert pending[0]["trade_id"] == submit_result["trade_id"]
        assert pending[0]["status"] == "pending"
        assert pending[0]["symbol"] == "BTC-USDT"
        assert pending[0]["is_bear_protection"] is False

    @pytest.mark.asyncio
    async def test_multiple_trades_queue_independently(self, db_session: AsyncSession):
        """Multiple submissions create independent pending entries."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        r1 = await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="BTC-USDT"
        )
        r2 = await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="ETH-USDT"
        )

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 2
        trade_ids = {p["trade_id"] for p in pending}
        assert r1["trade_id"] in trade_ids
        assert r2["trade_id"] in trade_ids


# ============================================================================
# TEST: APPROVAL Mode - Bear Protection Bypass
# ============================================================================


class TestBearProtectionBypass:
    """Bear protection exits auto-execute, bypassing the approval queue."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_bear_protection_auto_executes(self, db_session: AsyncSession):
        """EXIT_BEAR_PROTECTION signal auto-executes in APPROVAL mode."""
        callback = AsyncMock(return_value={"order_id": "order-123", "filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        result = await submit_standard_trade(
            service,
            db_session,
            agent_id="agent-approval",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            side="sell",
            reason="Bear protection defensive exit",
        )

        assert result["action"] == "auto_executed"
        assert result["reason"] == "bear_protection_bypass"
        assert "execution" in result
        assert result["execution"]["success"] is True

    @pytest.mark.asyncio
    async def test_bear_protection_calls_callback(self, db_session: AsyncSession):
        """Bear protection trades invoke the execution callback."""
        callback = AsyncMock(return_value={"filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        await submit_standard_trade(
            service,
            db_session,
            agent_id="agent-approval",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            side="sell",
        )

        callback.assert_called_once()
        call_kwargs = callback.call_args.kwargs
        assert call_kwargs["symbol"] == "BTC-USDT"
        assert call_kwargs["side"] == "sell"
        assert call_kwargs["order_type"] == "limit"

    @pytest.mark.asyncio
    async def test_bear_protection_not_queued(self, db_session: AsyncSession):
        """Bear protection trades do not appear in the pending queue."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        await submit_standard_trade(
            service,
            db_session,
            agent_id="agent-approval",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            side="sell",
        )

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0


# ============================================================================
# TEST: FULL_AUTO Mode
# ============================================================================


class TestFullAutoMode:
    """In FULL_AUTO mode, all trades auto-execute immediately."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_full_auto_auto_executes(self, db_session: AsyncSession):
        """Normal trade in FULL_AUTO mode auto-executes."""
        callback = AsyncMock(return_value={"order_id": "order-456", "filled": True})
        service = make_approval_service(
            agent_id="agent-auto",
            mode=TradingMode.FULL_AUTO,
            execute_callback=callback,
        )

        result = await submit_standard_trade(
            service, db_session, agent_id="agent-auto"
        )

        assert result["action"] == "auto_executed"
        assert result["reason"] == "full_auto_mode"
        assert result["execution"]["success"] is True
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_auto_not_queued(self, db_session: AsyncSession):
        """FULL_AUTO trades are not added to the pending queue."""
        service = make_approval_service(
            agent_id="agent-auto", mode=TradingMode.FULL_AUTO
        )

        await submit_standard_trade(service, db_session, agent_id="agent-auto")

        pending = await service.get_pending_trades("agent-auto")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_full_auto_without_callback_simulates(self, db_session: AsyncSession):
        """FULL_AUTO without a callback returns a simulated result."""
        service = make_approval_service(
            agent_id="agent-auto", mode=TradingMode.FULL_AUTO
        )

        result = await submit_standard_trade(service, db_session, agent_id="agent-auto")

        assert result["execution"]["success"] is True
        assert result["execution"]["simulated"] is True


# ============================================================================
# TEST: Approve Pending Trade
# ============================================================================


class TestApproveTrade:
    """Approving a pending trade executes it as a limit order."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_approve_executes_with_callback(self, db_session: AsyncSession):
        """Approving a pending trade triggers the execution callback."""
        callback = AsyncMock(return_value={"order_id": "order-789", "filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )
        trade_id = submit_result["trade_id"]

        approve_result = await service.approve_trade(db_session, trade_id)

        assert approve_result["status"] == "approved"
        assert approve_result["trade_id"] == trade_id
        assert approve_result["execution"]["success"] is True
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_removes_from_queue(self, db_session: AsyncSession):
        """Approved trade is removed from the pending queue."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )
        trade_id = submit_result["trade_id"]

        await service.approve_trade(db_session, trade_id)

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_error(self, db_session: AsyncSession):
        """Approving a non-existent trade ID returns an error."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        result = await service.approve_trade(db_session, "trade-nonexistent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_approve_calculates_limit_price_buy(self, db_session: AsyncSession):
        """Approved buy trade has limit_price = suggested * (1 + buffer)."""
        callback = AsyncMock(return_value={"filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            limit_buffer_pct=0.1,
            execute_callback=callback,
        )

        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", side="buy", price=50000.0
        )

        pending = await service.get_pending_trades("agent-approval")
        trade_id = pending[0]["trade_id"]

        await service.approve_trade(db_session, trade_id)

        call_kwargs = callback.call_args.kwargs
        # 50000 * (1 + 0.1/100) = 50050.0
        expected_limit = 50000.0 * (1 + 0.1 / 100)
        assert abs(call_kwargs["limit_price"] - expected_limit) < 0.01

    @pytest.mark.asyncio
    async def test_approve_calculates_limit_price_sell(self, db_session: AsyncSession):
        """Approved sell trade has limit_price = suggested * (1 - buffer)."""
        callback = AsyncMock(return_value={"filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            limit_buffer_pct=0.1,
            execute_callback=callback,
        )

        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", side="sell", price=50000.0
        )

        pending = await service.get_pending_trades("agent-approval")
        trade_id = pending[0]["trade_id"]

        await service.approve_trade(db_session, trade_id)

        call_kwargs = callback.call_args.kwargs
        expected_limit = 50000.0 * (1 - 0.1 / 100)
        assert abs(call_kwargs["limit_price"] - expected_limit) < 0.01


# ============================================================================
# TEST: Reject Pending Trade
# ============================================================================


class TestRejectTrade:
    """Rejecting a pending trade removes it from the queue without execution."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_reject_removes_from_queue(self, db_session: AsyncSession):
        """Rejected trade is removed from the pending queue."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )
        trade_id = submit_result["trade_id"]

        reject_result = await service.reject_trade(trade_id, reason="Too risky")

        assert reject_result["status"] == "rejected"
        assert reject_result["trade_id"] == trade_id
        assert reject_result["reason"] == "Too risky"

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_reject_does_not_call_callback(self, db_session: AsyncSession):
        """Rejecting a trade never invokes the execution callback."""
        callback = AsyncMock()
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )

        await service.reject_trade(submit_result["trade_id"])

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_error(self, db_session: AsyncSession):
        """Rejecting a non-existent trade ID returns an error."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        result = await service.reject_trade("trade-nonexistent")

        assert "error" in result


# ============================================================================
# TEST: Expired Trade Cleanup
# ============================================================================


class TestExpiredTradeCleanup:
    """Expired trades are automatically cleaned up."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_expired_trades_removed_from_pending(self, db_session: AsyncSession):
        """Trades past their expiration are cleaned up on next query."""
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            timeout_minutes=1,  # 1 minute timeout
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )

        # Manually expire the trade by backdating expires_at
        trade = service._find_trade(submit_result["trade_id"])
        trade.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_approve_expired_trade_returns_error(self, db_session: AsyncSession):
        """Attempting to approve an expired trade returns an error."""
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            timeout_minutes=1,
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )
        trade_id = submit_result["trade_id"]

        # Expire the trade
        trade = service._find_trade(trade_id)
        trade.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        result = await service.approve_trade(db_session, trade_id)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_cleanup_returns_expired_count(self, db_session: AsyncSession):
        """_cleanup_expired returns the count of expired trades."""
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            timeout_minutes=1,
        )

        # Submit 3 trades
        for _ in range(3):
            await submit_standard_trade(service, db_session, agent_id="agent-approval")

        # Expire 2 of them
        trades = service.pending_queues["agent-approval"]
        trades[0].expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        trades[1].expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        count = await service._cleanup_expired()
        assert count == 2

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 1


# ============================================================================
# TEST: Queue Stats
# ============================================================================


class TestQueueStats:
    """Tests for queue statistics accuracy."""

    @pytest.mark.asyncio
    async def test_empty_queue_stats(self, db_session: AsyncSession):
        """Empty queue has zero stats."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        stats = service.get_queue_stats()

        assert stats["total_pending"] == 0
        assert stats["agents_with_pending"] == 0
        assert stats["by_agent"] == {}

    @pytest.mark.asyncio
    async def test_stats_count_pending_only(self, db_session: AsyncSession):
        """Stats only count PENDING trades, not approved/rejected/expired."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        # Submit 3 trades
        r1 = await submit_standard_trade(service, db_session, agent_id="agent-approval")
        r2 = await submit_standard_trade(service, db_session, agent_id="agent-approval")
        r3 = await submit_standard_trade(service, db_session, agent_id="agent-approval")

        # Reject one
        await service.reject_trade(r1["trade_id"])

        stats = service.get_queue_stats()
        assert stats["total_pending"] == 2
        assert stats["agents_with_pending"] == 1
        assert stats["by_agent"]["agent-approval"] == 2

    @pytest.mark.asyncio
    async def test_stats_multi_agent(self, db_session: AsyncSession):
        """Stats correctly separate pending counts by agent."""
        service = ApprovalQueueService()
        for aid in ["agent-a", "agent-b"]:
            config = TradingConfig(agent_id=aid, mode=TradingMode.APPROVAL)
            service.configure_agent(config)

        await submit_standard_trade(service, db_session, agent_id="agent-a")
        await submit_standard_trade(service, db_session, agent_id="agent-a")
        await submit_standard_trade(service, db_session, agent_id="agent-b")

        stats = service.get_queue_stats()
        assert stats["total_pending"] == 3
        assert stats["agents_with_pending"] == 2
        assert stats["by_agent"]["agent-a"] == 2
        assert stats["by_agent"]["agent-b"] == 1


# ============================================================================
# TEST: Approve All / Reject All Batch Operations
# ============================================================================


class TestBatchOperations:
    """Tests for approve_all and reject_all batch operations."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_approve_all_executes_all_pending(self, db_session: AsyncSession):
        """approve_all executes all pending trades for an agent."""
        callback = AsyncMock(return_value={"filled": True})
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="BTC-USDT"
        )
        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="ETH-USDT"
        )
        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="SOL-USDT"
        )

        result = await service.approve_all(db_session, "agent-approval")

        assert result["approved_count"] == 3
        assert result["error_count"] == 0
        assert len(result["results"]) == 3
        assert callback.call_count == 3

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_reject_all_removes_all_pending(self, db_session: AsyncSession):
        """reject_all removes all pending trades for an agent."""
        service = make_approval_service(
            agent_id="agent-approval", mode=TradingMode.APPROVAL
        )

        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="BTC-USDT"
        )
        await submit_standard_trade(
            service, db_session, agent_id="agent-approval", symbol="ETH-USDT"
        )

        result = await service.reject_all("agent-approval", reason="Market too volatile")

        assert result["rejected_count"] == 2
        assert result["reason"] == "Market too volatile"

        pending = await service.get_pending_trades("agent-approval")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_approve_all_does_not_affect_other_agents(self, db_session: AsyncSession):
        """approve_all only affects the specified agent's trades."""
        service = ApprovalQueueService()
        for aid in ["agent-a", "agent-b"]:
            config = TradingConfig(agent_id=aid, mode=TradingMode.APPROVAL)
            service.configure_agent(config)

        await submit_standard_trade(service, db_session, agent_id="agent-a")
        await submit_standard_trade(service, db_session, agent_id="agent-b")

        await service.approve_all(db_session, "agent-a")

        pending_a = await service.get_pending_trades("agent-a")
        pending_b = await service.get_pending_trades("agent-b")
        assert len(pending_a) == 0
        assert len(pending_b) == 1

    @pytest.mark.asyncio
    async def test_reject_all_does_not_affect_other_agents(self, db_session: AsyncSession):
        """reject_all only affects the specified agent's trades."""
        service = ApprovalQueueService()
        for aid in ["agent-a", "agent-b"]:
            config = TradingConfig(agent_id=aid, mode=TradingMode.APPROVAL)
            service.configure_agent(config)

        await submit_standard_trade(service, db_session, agent_id="agent-a")
        await submit_standard_trade(service, db_session, agent_id="agent-b")

        await service.reject_all("agent-a")

        pending_b = await service.get_pending_trades("agent-b")
        assert len(pending_b) == 1


# ============================================================================
# TEST: Default Mode / Unconfigured Agent
# ============================================================================


class TestDefaultBehavior:
    """Tests for unconfigured agents and default mode."""

    @pytest.mark.asyncio
    async def test_unconfigured_agent_defaults_to_paper_only(self, db_session: AsyncSession):
        """An agent with no config defaults to PAPER_ONLY mode."""
        service = ApprovalQueueService()

        mode = service.get_agent_mode("unconfigured-agent")
        assert mode == TradingMode.PAPER_ONLY

    @pytest.mark.asyncio
    async def test_unconfigured_agent_submit_uses_paper_only(self, db_session: AsyncSession):
        """Submitting for unconfigured agent uses PAPER_ONLY path."""
        service = ApprovalQueueService()

        result = await submit_standard_trade(
            service, db_session, agent_id="unconfigured-agent"
        )

        assert result["action"] == "paper_recorded"


# ============================================================================
# TEST: Execution Callback Error Handling
# ============================================================================


class TestCallbackErrorHandling:
    """Tests for error handling when the execution callback fails."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_callback_exception_returns_error(self, db_session: AsyncSession):
        """If the execution callback raises, the result reports failure."""
        callback = AsyncMock(side_effect=ConnectionError("Exchange unreachable"))
        service = make_approval_service(
            agent_id="agent-approval",
            mode=TradingMode.APPROVAL,
            execute_callback=callback,
        )

        submit_result = await submit_standard_trade(
            service, db_session, agent_id="agent-approval"
        )

        approve_result = await service.approve_trade(db_session, submit_result["trade_id"])

        assert approve_result["execution"]["success"] is False
        assert "Exchange unreachable" in approve_result["execution"]["error"]

    @pytest.mark.asyncio
    async def test_full_auto_callback_exception(self, db_session: AsyncSession):
        """FULL_AUTO callback failure is reported in the result."""
        callback = AsyncMock(side_effect=TimeoutError("Request timed out"))
        service = make_approval_service(
            agent_id="agent-auto",
            mode=TradingMode.FULL_AUTO,
            execute_callback=callback,
        )

        result = await submit_standard_trade(
            service, db_session, agent_id="agent-auto"
        )

        assert result["execution"]["success"] is False
        assert "timed out" in result["execution"]["error"]
