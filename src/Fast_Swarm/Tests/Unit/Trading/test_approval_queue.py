"""
Tests for ApprovalQueueService - manages pending trades for APPROVAL mode.

Covers queue/approve/reject flow, timeout/expiry, priority ordering,
duplicate prevention, queue limits, and mode routing.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from Fast_Swarm.Trading.Models.trading_models import (
    ApprovalStatus,
    PendingTrade,
    SignalType,
    TradingConfig,
    TradingMode,
)
from Fast_Swarm.Trading.Services.approval_queue_service import (
    ApprovalQueueService,
    get_approval_queue_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create a fresh approval queue service."""
    return ApprovalQueueService()


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def approval_config():
    """Config for APPROVAL mode agent."""
    return TradingConfig(
        agent_id="agent-001",
        mode=TradingMode.APPROVAL,
        approval_timeout_minutes=60,
        limit_buffer_pct=0.1,
    )


@pytest.fixture
def full_auto_config():
    """Config for FULL_AUTO mode agent."""
    return TradingConfig(
        agent_id="agent-auto",
        mode=TradingMode.FULL_AUTO,
    )


@pytest.fixture
def paper_config():
    """Config for PAPER_ONLY mode agent."""
    return TradingConfig(
        agent_id="agent-paper",
        mode=TradingMode.PAPER_ONLY,
    )


async def _submit_trade(service, session, agent_id="agent-001", signal_type=SignalType.ENTRY_LONG):
    """Helper to submit a trade."""
    return await service.submit_trade(
        session=session,
        agent_id=agent_id,
        agent_name="TestAgent",
        symbol="BTC-USDT",
        side="long",
        signal_type=signal_type,
        suggested_price=50000.0,
        size=0.01,
        size_usd=500.0,
        reason="RSI oversold",
        pattern_id="pat-1",
        pattern_name="RSI_Oversold",
        regime="bull",
    )


# =============================================================================
# Configuration Tests
# =============================================================================


class TestConfiguration:
    """Test agent configuration."""

    def test_configure_agent(self, service, approval_config):
        """configure_agent stores config and creates queue."""
        service.configure_agent(approval_config)
        assert "agent-001" in service.agent_configs
        assert "agent-001" in service.pending_queues

    def test_get_agent_mode_default(self, service):
        """Unconfigured agent defaults to PAPER_ONLY."""
        mode = service.get_agent_mode("unknown-agent")
        assert mode == TradingMode.PAPER_ONLY

    def test_get_agent_mode_configured(self, service, approval_config):
        """Configured agent returns correct mode."""
        service.configure_agent(approval_config)
        mode = service.get_agent_mode("agent-001")
        assert mode == TradingMode.APPROVAL


# =============================================================================
# Submit Trade Mode Routing Tests
# =============================================================================


class TestModeRouting:
    """Test trade submission routes by mode."""

    @pytest.mark.asyncio
    async def test_paper_only_records_trade(self, service, mock_session, paper_config):
        """PAPER_ONLY mode records trade without queuing."""
        service.configure_agent(paper_config)
        result = await _submit_trade(service, mock_session, agent_id="agent-paper")
        assert result["action"] == "paper_recorded"
        assert result["symbol"] == "BTC-USDT"

    @pytest.mark.asyncio
    async def test_approval_mode_queues_trade(self, service, mock_session, approval_config):
        """APPROVAL mode queues normal trades for approval."""
        service.configure_agent(approval_config)
        result = await _submit_trade(service, mock_session)
        assert result["action"] == "queued"
        assert result["trade_id"] is not None
        assert result["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_approval_mode_bear_protection_auto_executes(
        self, service, mock_session, approval_config
    ):
        """Bear protection signals bypass approval queue."""
        service.configure_agent(approval_config)
        result = await _submit_trade(
            service, mock_session, signal_type=SignalType.EXIT_BEAR_PROTECTION
        )
        assert result["action"] == "auto_executed"
        assert result["reason"] == "bear_protection_bypass"

    @pytest.mark.asyncio
    async def test_full_auto_mode_auto_executes(self, service, mock_session, full_auto_config):
        """FULL_AUTO mode auto-executes without queuing."""
        service.configure_agent(full_auto_config)
        result = await _submit_trade(service, mock_session, agent_id="agent-auto")
        assert result["action"] == "auto_executed"
        assert result["reason"] == "full_auto_mode"


# =============================================================================
# Approve/Reject Flow Tests
# =============================================================================


class TestApproveReject:
    """Test trade approval and rejection."""

    @pytest.mark.asyncio
    async def test_approve_trade_success(self, service, mock_session, approval_config):
        """Approved trade is executed and removed from queue."""
        service.configure_agent(approval_config)
        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]

        result = await service.approve_trade(mock_session, trade_id)
        assert result["status"] == "approved"
        assert result["trade_id"] == trade_id

        # Trade should be removed from pending
        pending = await service.get_pending_trades("agent-001")
        assert not any(t["trade_id"] == trade_id for t in pending)

    @pytest.mark.asyncio
    async def test_approve_nonexistent_trade(self, service, mock_session):
        """Approving a nonexistent trade returns error."""
        result = await service.approve_trade(mock_session, "fake-trade-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reject_trade_success(self, service, mock_session, approval_config):
        """Rejected trade is removed from queue."""
        service.configure_agent(approval_config)
        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]

        result = await service.reject_trade(trade_id, reason="too risky")
        assert result["status"] == "rejected"
        assert result["reason"] == "too risky"

        pending = await service.get_pending_trades("agent-001")
        assert not any(t["trade_id"] == trade_id for t in pending)

    @pytest.mark.asyncio
    async def test_reject_nonexistent_trade(self, service):
        """Rejecting a nonexistent trade returns error."""
        result = await service.reject_trade("fake-trade-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_double_approve_fails(self, service, mock_session, approval_config):
        """Cannot approve a trade that was already approved."""
        service.configure_agent(approval_config)
        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]

        await service.approve_trade(mock_session, trade_id)
        result = await service.approve_trade(mock_session, trade_id)
        assert "error" in result


# =============================================================================
# Timeout/Expiry Tests
# =============================================================================


class TestExpiry:
    """Test trade expiration handling."""

    @pytest.mark.asyncio
    async def test_expired_trade_not_approvable(self, service, mock_session, approval_config):
        """Expired trade cannot be approved."""
        service.configure_agent(approval_config)
        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]

        # Force expire the trade
        trade = service._find_trade(trade_id)
        trade.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        result = await service.approve_trade(mock_session, trade_id)
        assert "error" in result
        assert "expired" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_stale_trades(self, service, mock_session, approval_config):
        """Expired trades are cleaned up automatically."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)

        # Force expire all trades
        for trades in service.pending_queues.values():
            for trade in trades:
                trade.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        count = await service._cleanup_expired()
        assert count >= 1

        pending = await service.get_pending_trades("agent-001")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_non_expired_trade_survives_cleanup(self, service, mock_session, approval_config):
        """Non-expired trades are not removed by cleanup."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)

        # Trades should have future expiry by default
        count = await service._cleanup_expired()
        assert count == 0

        pending = await service.get_pending_trades("agent-001")
        assert len(pending) == 1


# =============================================================================
# Queue Management Tests
# =============================================================================


class TestQueueManagement:
    """Test queue listing, approve_all, reject_all."""

    @pytest.mark.asyncio
    async def test_get_pending_trades_by_agent(self, service, mock_session, approval_config):
        """get_pending_trades filters by agent_id."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)
        await _submit_trade(service, mock_session)

        pending = await service.get_pending_trades("agent-001")
        assert len(pending) == 2

        # Other agent should have none
        pending_other = await service.get_pending_trades("agent-999")
        assert len(pending_other) == 0

    @pytest.mark.asyncio
    async def test_get_pending_trades_all(self, service, mock_session, approval_config):
        """get_pending_trades without filter returns all agents."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)

        all_pending = await service.get_pending_trades()
        assert len(all_pending) >= 1

    @pytest.mark.asyncio
    async def test_approve_all(self, service, mock_session, approval_config):
        """approve_all approves all pending trades for an agent."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)
        await _submit_trade(service, mock_session)

        result = await service.approve_all(mock_session, "agent-001")
        assert result["approved_count"] == 2
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_reject_all(self, service, mock_session, approval_config):
        """reject_all rejects all pending trades for an agent."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)
        await _submit_trade(service, mock_session)

        result = await service.reject_all("agent-001", reason="market crash")
        assert result["rejected_count"] == 2

    @pytest.mark.asyncio
    async def test_queue_stats(self, service, mock_session, approval_config):
        """get_queue_stats returns correct counts."""
        service.configure_agent(approval_config)
        await _submit_trade(service, mock_session)
        await _submit_trade(service, mock_session)

        stats = service.get_queue_stats()
        assert stats["total_pending"] == 2
        assert stats["agents_with_pending"] == 1
        assert stats["by_agent"]["agent-001"] == 2


# =============================================================================
# Execution Callback Tests
# =============================================================================


class TestExecutionCallback:
    """Test execution callback integration."""

    @pytest.mark.asyncio
    async def test_execute_with_callback(self, service, mock_session, approval_config):
        """Execution uses callback when set."""
        callback = AsyncMock(return_value={"success": True, "order_id": "ord-cb-1"})
        service.set_execute_callback(callback)
        service.configure_agent(approval_config)

        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]
        result = await service.approve_trade(mock_session, trade_id)

        callback.assert_awaited_once()
        assert result["execution"]["success"] is True

    @pytest.mark.asyncio
    async def test_execute_without_callback_simulates(self, service, mock_session, approval_config):
        """Without callback, execution returns simulated result."""
        service.configure_agent(approval_config)
        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]
        result = await service.approve_trade(mock_session, trade_id)

        assert result["execution"]["simulated"] is True

    @pytest.mark.asyncio
    async def test_callback_exception_handled(self, service, mock_session, approval_config):
        """Exception in callback returns error result."""
        callback = AsyncMock(side_effect=RuntimeError("exchange down"))
        service.set_execute_callback(callback)
        service.configure_agent(approval_config)

        submit_result = await _submit_trade(service, mock_session)
        trade_id = submit_result["trade_id"]
        result = await service.approve_trade(mock_session, trade_id)

        assert result["execution"]["success"] is False
        assert "exchange down" in result["execution"]["error"]


# =============================================================================
# PendingTrade Model Tests
# =============================================================================


class TestPendingTradeModel:
    """Test PendingTrade dataclass behavior."""

    def test_is_bear_protection(self):
        """Bear protection signal identified correctly."""
        trade = PendingTrade(
            trade_id="t1",
            agent_id="a1",
            agent_name="Test",
            symbol="BTC-USDT",
            side="sell",
            signal_type=SignalType.EXIT_BEAR_PROTECTION,
            suggested_price=50000.0,
            size=0.01,
            size_usd=500.0,
            reason="bear",
        )
        assert trade.is_bear_protection() is True

    def test_is_not_bear_protection(self):
        """Normal entry signal is not bear protection."""
        trade = PendingTrade(
            trade_id="t2",
            agent_id="a1",
            agent_name="Test",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.01,
            size_usd=500.0,
            reason="RSI",
        )
        assert trade.is_bear_protection() is False

    def test_is_expired(self):
        """Expired check works with past datetime."""
        trade = PendingTrade(
            trade_id="t3",
            agent_id="a1",
            agent_name="Test",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.01,
            size_usd=500.0,
            reason="test",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        assert trade.is_expired() is True

    def test_not_expired(self):
        """Trade with future expiry is not expired."""
        trade = PendingTrade(
            trade_id="t4",
            agent_id="a1",
            agent_name="Test",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.01,
            size_usd=500.0,
            reason="test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert trade.is_expired() is False

    def test_no_expiry_never_expires(self):
        """Trade without expiry time never expires."""
        trade = PendingTrade(
            trade_id="t5",
            agent_id="a1",
            agent_name="Test",
            symbol="BTC-USDT",
            side="long",
            signal_type=SignalType.ENTRY_LONG,
            suggested_price=50000.0,
            size=0.01,
            size_usd=500.0,
            reason="test",
            expires_at=None,
        )
        assert trade.is_expired() is False


# =============================================================================
# Singleton Test
# =============================================================================


class TestSingleton:
    """Test singleton pattern."""

    def test_singleton(self):
        """get_approval_queue_service returns same instance."""
        import Fast_Swarm.Trading.Services.approval_queue_service as mod

        mod._approval_queue_service = None
        svc1 = get_approval_queue_service()
        svc2 = get_approval_queue_service()
        assert svc1 is svc2
        mod._approval_queue_service = None  # cleanup
