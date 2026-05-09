"""
Approval Queue Service Unit Tests - CONTRACT-BASED (TDD/EDD)

Tests for the three-mode trading system approval queue.
Source: src/Fast_Swarm/Trading/Services/approval_queue_service.py
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from Fast_Swarm.Trading.Models.trading_models import (
    ApprovalStatus,
    SignalType,
    TradingConfig,
    TradingMode,
)
from Fast_Swarm.Trading.Services.approval_queue_service import ApprovalQueueService


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def approval_service():
    """Create a fresh ApprovalQueueService instance."""
    return ApprovalQueueService()


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def paper_only_config():
    """Config for PAPER_ONLY mode."""
    return TradingConfig(
        agent_id="agent-paper",
        mode=TradingMode.PAPER_ONLY,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
    )


@pytest.fixture
def approval_config():
    """Config for APPROVAL mode."""
    return TradingConfig(
        agent_id="agent-approval",
        mode=TradingMode.APPROVAL,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
        limit_buffer_pct=0.1,
        approval_timeout_minutes=60,
    )


@pytest.fixture
def full_auto_config():
    """Config for FULL_AUTO mode."""
    return TradingConfig(
        agent_id="agent-auto",
        mode=TradingMode.FULL_AUTO,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
        limit_buffer_pct=0.1,
    )


# ============================================================================
# TRADING MODE CONFIGURATION
# ============================================================================


class TestTradingModeConfiguration:
    """CONTRACT: Trading modes are configured correctly."""

    def test_configure_paper_only_mode(self, approval_service, paper_only_config):
        """CONTRACT: PAPER_ONLY mode is stored correctly."""
        approval_service.configure_agent(paper_only_config)

        mode = approval_service.get_agent_mode(paper_only_config.agent_id)
        assert mode == TradingMode.PAPER_ONLY

    def test_configure_approval_mode(self, approval_service, approval_config):
        """CONTRACT: APPROVAL mode is stored correctly."""
        approval_service.configure_agent(approval_config)

        mode = approval_service.get_agent_mode(approval_config.agent_id)
        assert mode == TradingMode.APPROVAL

    def test_configure_full_auto_mode(self, approval_service, full_auto_config):
        """CONTRACT: FULL_AUTO mode is stored correctly."""
        approval_service.configure_agent(full_auto_config)

        mode = approval_service.get_agent_mode(full_auto_config.agent_id)
        assert mode == TradingMode.FULL_AUTO

    def test_unconfigured_agent_defaults_to_paper_only(self, approval_service):
        """CONTRACT: Unknown agents default to PAPER_ONLY mode."""
        mode = approval_service.get_agent_mode("unknown-agent")
        assert mode == TradingMode.PAPER_ONLY


# ============================================================================
# PAPER_ONLY MODE
# ============================================================================


class TestPaperOnlyMode:
    """CONTRACT: PAPER_ONLY mode records trades without queuing."""

    @pytest.mark.asyncio
    async def test_paper_only_returns_paper_recorded(
        self, approval_service, mock_session, paper_only_config
    ):
        """CONTRACT: PAPER_ONLY mode returns paper_recorded action."""
        approval_service.configure_agent(paper_only_config)

        result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=paper_only_config.agent_id,
            agent_name="Paper Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Test entry signal",
        )

        assert result["action"] == "paper_recorded"
        assert "trade_id" in result
        assert result["symbol"] == "BTC-USDT"

    @pytest.mark.asyncio
    async def test_paper_only_does_not_queue(
        self, approval_service, mock_session, paper_only_config
    ):
        """CONTRACT: PAPER_ONLY mode does not add to queue."""
        approval_service.configure_agent(paper_only_config)

        await approval_service.submit_trade(
            session=mock_session,
            agent_id=paper_only_config.agent_id,
            agent_name="Paper Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Test entry signal",
        )

        pending = await approval_service.get_pending_trades(paper_only_config.agent_id)
        assert len(pending) == 0


# ============================================================================
# APPROVAL MODE - NORMAL TRADES
# ============================================================================


class TestApprovalModeNormalTrades:
    """CONTRACT: APPROVAL mode queues normal trades for approval."""

    @pytest.mark.asyncio
    async def test_normal_trade_is_queued(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Normal trades are queued in APPROVAL mode."""
        approval_service.configure_agent(approval_config)

        result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry signal",
        )

        assert result["action"] == "queued"
        assert "trade_id" in result
        assert "expires_at" in result

    @pytest.mark.asyncio
    async def test_queued_trade_appears_in_pending(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Queued trades appear in pending list."""
        approval_service.configure_agent(approval_config)

        await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry signal",
        )

        pending = await approval_service.get_pending_trades(approval_config.agent_id)
        assert len(pending) == 1
        assert pending[0]["symbol"] == "BTC-USDT"
        assert pending[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_exit_normal_is_queued(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Normal exit signals are queued."""
        approval_service.configure_agent(approval_config)

        result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="short",
            signal_type=SignalType.EXIT_NORMAL,
            suggested_price=51000.0,
            size=0.1,
            size_usd=5100.0,
            reason="Take profit",
        )

        assert result["action"] == "queued"


# ============================================================================
# APPROVAL MODE - BEAR PROTECTION BYPASS
# ============================================================================


class TestBearProtectionBypass:
    """CONTRACT: Bear protection exits bypass approval queue."""

    @pytest.mark.asyncio
    async def test_bear_protection_auto_executes(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Bear protection exits auto-execute without queuing."""
        approval_service.configure_agent(approval_config)

        result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="short",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            suggested_price=48000.0,
            size=0.1,
            size_usd=4800.0,
            reason="Bear market detected - emergency exit",
        )

        assert result["action"] == "auto_executed"
        assert result["reason"] == "bear_protection_bypass"

    @pytest.mark.asyncio
    async def test_bear_protection_not_in_pending(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Bear protection exits do not appear in pending queue."""
        approval_service.configure_agent(approval_config)

        await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="short",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            suggested_price=48000.0,
            size=0.1,
            size_usd=4800.0,
            reason="Bear protection",
        )

        pending = await approval_service.get_pending_trades(approval_config.agent_id)
        assert len(pending) == 0


# ============================================================================
# FULL_AUTO MODE
# ============================================================================


class TestFullAutoMode:
    """CONTRACT: FULL_AUTO mode auto-executes all trades."""

    @pytest.mark.asyncio
    async def test_full_auto_executes_immediately(
        self, approval_service, mock_session, full_auto_config
    ):
        """CONTRACT: FULL_AUTO mode auto-executes trades."""
        approval_service.configure_agent(full_auto_config)

        result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=full_auto_config.agent_id,
            agent_name="Auto Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry signal",
        )

        assert result["action"] == "auto_executed"
        assert result["reason"] == "full_auto_mode"

    @pytest.mark.asyncio
    async def test_full_auto_does_not_queue(
        self, approval_service, mock_session, full_auto_config
    ):
        """CONTRACT: FULL_AUTO mode does not add to queue."""
        approval_service.configure_agent(full_auto_config)

        await approval_service.submit_trade(
            session=mock_session,
            agent_id=full_auto_config.agent_id,
            agent_name="Auto Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry signal",
        )

        pending = await approval_service.get_pending_trades(full_auto_config.agent_id)
        assert len(pending) == 0


# ============================================================================
# APPROVE/REJECT OPERATIONS
# ============================================================================


class TestApproveRejectOperations:
    """CONTRACT: Approve and reject work correctly."""

    @pytest.mark.asyncio
    async def test_approve_pending_trade(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Approving a trade executes it."""
        approval_service.configure_agent(approval_config)

        submit_result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry",
        )

        trade_id = submit_result["trade_id"]
        approve_result = await approval_service.approve_trade(mock_session, trade_id)

        assert approve_result["status"] == "approved"
        assert "execution" in approve_result

    @pytest.mark.asyncio
    async def test_reject_pending_trade(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Rejecting a trade removes it from queue."""
        approval_service.configure_agent(approval_config)

        submit_result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Approval Agent",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry",
        )

        trade_id = submit_result["trade_id"]
        reject_result = await approval_service.reject_trade(trade_id, "Changed my mind")

        assert reject_result["status"] == "rejected"
        assert reject_result["reason"] == "Changed my mind"

        # Should no longer be in pending
        pending = await approval_service.get_pending_trades(approval_config.agent_id)
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_approve_nonexistent_trade(self, approval_service, mock_session):
        """CONTRACT: Approving unknown trade returns error."""
        result = await approval_service.approve_trade(mock_session, "nonexistent-trade")
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_reject_nonexistent_trade(self, approval_service):
        """CONTRACT: Rejecting unknown trade returns error."""
        result = await approval_service.reject_trade("nonexistent-trade", "")
        assert "error" in result
        assert "not found" in result["error"]


# ============================================================================
# LIMIT ORDER CALCULATION
# ============================================================================


class TestLimitOrderCalculation:
    """CONTRACT: Limit orders calculated with correct buffer."""

    @pytest.mark.asyncio
    async def test_buy_limit_price_above_suggested(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Buy limit price is above suggested price."""
        approval_service.configure_agent(approval_config)

        # Submit and approve
        submit_result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Agent",
            symbol="BTC-USDT",
            side="buy",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Entry",
        )

        approve_result = await approval_service.approve_trade(
            mock_session, submit_result["trade_id"]
        )

        # Buffer is 0.1%, so limit = 50000 * 1.001 = 50050
        limit_price = approve_result["execution"]["limit_price"]
        assert limit_price > 50000.0
        assert limit_price == pytest.approx(50050.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_sell_limit_price_below_suggested(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Sell limit price is below suggested price."""
        approval_service.configure_agent(approval_config)

        submit_result = await approval_service.submit_trade(
            session=mock_session,
            agent_id=approval_config.agent_id,
            agent_name="Agent",
            symbol="BTC-USDT",
            side="sell",
            signal_type=SignalType.EXIT_NORMAL,
            suggested_price=50000.0,
            size=0.1,
            size_usd=5000.0,
            reason="Exit",
        )

        approve_result = await approval_service.approve_trade(
            mock_session, submit_result["trade_id"]
        )

        # Buffer is 0.1%, so limit = 50000 * 0.999 = 49950
        limit_price = approve_result["execution"]["limit_price"]
        assert limit_price < 50000.0
        assert limit_price == pytest.approx(49950.0, rel=0.001)


# ============================================================================
# BULK OPERATIONS
# ============================================================================


class TestBulkOperations:
    """CONTRACT: Bulk approve/reject work correctly."""

    @pytest.mark.asyncio
    async def test_approve_all_for_agent(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Approve all approves multiple trades."""
        approval_service.configure_agent(approval_config)

        # Submit 3 trades
        for i in range(3):
            await approval_service.submit_trade(
                session=mock_session,
                agent_id=approval_config.agent_id,
                agent_name="Agent",
                symbol=f"SYMBOL-{i}",
                side="long",
                signal_type=SignalType.ENTRY_LONG,
                suggested_price=50000.0,
                size=0.1,
                size_usd=5000.0,
                reason=f"Trade {i}",
            )

        result = await approval_service.approve_all(mock_session, approval_config.agent_id)

        assert result["approved_count"] == 3
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_reject_all_for_agent(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Reject all rejects multiple trades."""
        approval_service.configure_agent(approval_config)

        # Submit 3 trades
        for i in range(3):
            await approval_service.submit_trade(
                session=mock_session,
                agent_id=approval_config.agent_id,
                agent_name="Agent",
                symbol=f"SYMBOL-{i}",
                side="long",
                signal_type=SignalType.ENTRY_LONG,
                suggested_price=50000.0,
                size=0.1,
                size_usd=5000.0,
                reason=f"Trade {i}",
            )

        result = await approval_service.reject_all(
            approval_config.agent_id, "Market changed"
        )

        assert result["rejected_count"] == 3

        # Queue should be empty
        pending = await approval_service.get_pending_trades(approval_config.agent_id)
        assert len(pending) == 0


# ============================================================================
# QUEUE STATISTICS
# ============================================================================


class TestQueueStatistics:
    """CONTRACT: Queue statistics are accurate."""

    @pytest.mark.asyncio
    async def test_empty_queue_stats(self, approval_service):
        """CONTRACT: Empty queue returns zero stats."""
        stats = approval_service.get_queue_stats()

        assert stats["total_pending"] == 0
        assert stats["agents_with_pending"] == 0
        assert stats["by_agent"] == {}

    @pytest.mark.asyncio
    async def test_stats_count_pending_trades(
        self, approval_service, mock_session, approval_config
    ):
        """CONTRACT: Stats count pending trades correctly."""
        approval_service.configure_agent(approval_config)

        # Submit 2 trades
        for i in range(2):
            await approval_service.submit_trade(
                session=mock_session,
                agent_id=approval_config.agent_id,
                agent_name="Agent",
                symbol=f"SYMBOL-{i}",
                side="long",
                signal_type=SignalType.ENTRY_LONG,
                suggested_price=50000.0,
                size=0.1,
                size_usd=5000.0,
                reason=f"Trade {i}",
            )

        stats = approval_service.get_queue_stats()

        assert stats["total_pending"] == 2
        assert stats["agents_with_pending"] == 1
        assert stats["by_agent"][approval_config.agent_id] == 2
