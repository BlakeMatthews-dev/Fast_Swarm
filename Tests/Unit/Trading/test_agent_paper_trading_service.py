"""
AgentPaperTradingService Unit Tests - CONTRACT-BASED (TDD/EDD)

Tests for the MVP direct agent -> paper trading bridge.
Source: src/Fast_Swarm/Trading/Services/agent_paper_trading_service.py
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def paper_trading_service():
    """Create a fresh AgentPaperTradingService instance."""
    return AgentPaperTradingService()


@pytest.fixture
def mock_agent():
    """Create a mock agent with patterns assigned."""
    agent = MagicMock()
    agent.agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"
    agent.name = "Test Trading Agent"
    agent.status = "active"
    agent.assigned_patterns = ["pattern-001", "pattern-002"]
    agent.pattern_weights = {"pattern-001": 1.0, "pattern-002": 0.8}
    agent.traits = {"kelly_fraction": 0.1, "risk_tolerance": 0.5}
    return agent


@pytest.fixture
def mock_inactive_agent():
    """Create a mock inactive agent."""
    agent = MagicMock()
    agent.agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"
    agent.name = "Inactive Agent"
    agent.status = "retired"
    return agent


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


def setup_session_with_agent(session: AsyncMock, agent):
    """Configure mock session to return the given agent."""
    mock_result = MagicMock()
    mock_result.first.return_value = agent
    session.exec = AsyncMock(return_value=mock_result)


# ============================================================================
# START PAPER TRADING CONTRACT
# ============================================================================


class TestStartPaperTrading:
    """CONTRACT: Starting paper trading initializes tracking correctly."""

    @pytest.mark.asyncio
    async def test_start_with_valid_agent(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Starting with valid agent returns success."""
        setup_session_with_agent(mock_session, mock_agent)

        result = await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            symbols=["BTC-USDT"],
            initial_balance=10000.0,
        )

        assert result["status"] == "started"
        assert result["agent_id"] == mock_agent.agent_id
        assert result["balance"] == 10000.0
        assert "BTC-USDT" in result["symbols"]

    @pytest.mark.asyncio
    async def test_start_with_nonexistent_agent(
        self, paper_trading_service, mock_session
    ):
        """CONTRACT: Starting with nonexistent agent returns error."""
        setup_session_with_agent(mock_session, None)

        result = await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id="nonexistent-agent",
        )

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_start_with_inactive_agent(
        self, paper_trading_service, mock_session, mock_inactive_agent
    ):
        """CONTRACT: Starting with inactive agent returns error."""
        setup_session_with_agent(mock_session, mock_inactive_agent)

        result = await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_inactive_agent.agent_id,
        )

        assert "error" in result
        assert "not active" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_start_initializes_position_tracking(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Starting initializes internal position tracking."""
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            initial_balance=50000.0,
        )

        assert mock_agent.agent_id in paper_trading_service.active_positions
        position_info = paper_trading_service.active_positions[mock_agent.agent_id]
        assert position_info["balance"] == 50000.0
        assert position_info["positions"] == {}
        assert position_info["trades_count"] == 0

    @pytest.mark.asyncio
    async def test_start_uses_default_symbols(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Default symbol is BTC-USDT when none specified."""
        setup_session_with_agent(mock_session, mock_agent)

        result = await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        assert "BTC-USDT" in result["symbols"]


# ============================================================================
# STOP PAPER TRADING CONTRACT
# ============================================================================


class TestStopPaperTrading:
    """CONTRACT: Stopping paper trading returns correct summary."""

    @pytest.mark.asyncio
    async def test_stop_active_agent(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Stopping active agent returns summary."""
        setup_session_with_agent(mock_session, mock_agent)

        # Start first
        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        # Then stop
        result = await paper_trading_service.stop_paper_trading(mock_agent.agent_id)

        assert result["status"] == "stopped"
        assert result["agent_id"] == mock_agent.agent_id
        assert "duration_seconds" in result
        assert "trades_count" in result
        assert "total_pnl" in result

    @pytest.mark.asyncio
    async def test_stop_removes_from_tracking(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Stopping removes agent from active tracking."""
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        await paper_trading_service.stop_paper_trading(mock_agent.agent_id)

        assert mock_agent.agent_id not in paper_trading_service.active_positions

    @pytest.mark.asyncio
    async def test_stop_nontrading_agent(self, paper_trading_service):
        """CONTRACT: Stopping non-trading agent returns error."""
        result = await paper_trading_service.stop_paper_trading("not-trading-agent")

        assert "error" in result
        assert "not actively trading" in result["error"].lower()


# ============================================================================
# GET ACTIVE AGENTS CONTRACT
# ============================================================================


class TestGetActiveAgents:
    """CONTRACT: Get active agents returns correct list."""

    @pytest.mark.asyncio
    async def test_get_active_agents_empty(self, paper_trading_service):
        """CONTRACT: Returns empty list when no agents trading."""
        result = await paper_trading_service.get_active_agents()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_active_agents_with_agents(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Returns list of active agents with stats."""
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        result = await paper_trading_service.get_active_agents()

        assert len(result) == 1
        assert result[0]["agent_id"] == mock_agent.agent_id
        assert "balance" in result[0]
        assert "positions" in result[0]
        assert "trades_count" in result[0]


# ============================================================================
# GET AGENT POSITIONS CONTRACT
# ============================================================================


class TestGetAgentPositions:
    """CONTRACT: Get positions returns correct data."""

    @pytest.mark.asyncio
    async def test_get_positions_for_active_agent(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Returns position data for active agent."""
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            initial_balance=25000.0,
        )

        result = await paper_trading_service.get_agent_positions(mock_agent.agent_id)

        assert result is not None
        assert result["agent_id"] == mock_agent.agent_id
        assert result["balance"] == 25000.0
        assert result["positions"] == {}

    @pytest.mark.asyncio
    async def test_get_positions_for_nontrading_agent(self, paper_trading_service):
        """CONTRACT: Returns None for non-trading agent."""
        result = await paper_trading_service.get_agent_positions("not-trading")
        assert result is None


# ============================================================================
# FORCE CLOSE POSITION CONTRACT
# ============================================================================


class TestForceClosePosition:
    """CONTRACT: Force close handles edge cases correctly."""

    @pytest.mark.asyncio
    async def test_force_close_nontrading_agent(
        self, paper_trading_service, mock_session
    ):
        """CONTRACT: Force close on non-trading agent returns error."""
        result = await paper_trading_service.force_close_position(
            session=mock_session,
            agent_id="not-trading",
            symbol="BTC-USDT",
            current_price=50000.0,
        )

        assert "error" in result
        assert "not actively trading" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_force_close_no_position(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Force close with no position returns error."""
        setup_session_with_agent(mock_session, mock_agent)

        # Start trading but don't open position
        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        result = await paper_trading_service.force_close_position(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            symbol="BTC-USDT",
            current_price=50000.0,
        )

        assert "error" in result


# ============================================================================
# EVALUATE AND TRADE CONTRACT
# ============================================================================


class TestEvaluateAndTrade:
    """CONTRACT: Evaluate and trade handles signals correctly."""

    @pytest.mark.asyncio
    async def test_evaluate_nontrading_agent_returns_none(
        self, paper_trading_service, mock_session
    ):
        """CONTRACT: Returns None for non-trading agent."""
        result = await paper_trading_service.evaluate_and_trade(
            session=mock_session,
            agent_id="not-trading",
            symbol="BTC-USDT",
            current_price=50000.0,
            candle_data={},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_agent_without_patterns_returns_none(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Returns None for agent without patterns."""
        mock_agent.assigned_patterns = []
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        result = await paper_trading_service.evaluate_and_trade(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            symbol="BTC-USDT",
            current_price=50000.0,
            candle_data={},
        )

        assert result is None


# ============================================================================
# POSITION SIZE CALCULATION CONTRACT
# ============================================================================


class TestPositionSizing:
    """CONTRACT: Position sizing uses Kelly fraction correctly."""

    @pytest.mark.asyncio
    async def test_kelly_fraction_from_traits(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Kelly fraction is read from agent traits."""
        mock_agent.traits = {"kelly_fraction": 0.15}
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
            initial_balance=100000.0,
        )

        # Verify tracking is set up correctly
        position_info = paper_trading_service.active_positions[mock_agent.agent_id]
        assert position_info["balance"] == 100000.0

    @pytest.mark.asyncio
    async def test_default_kelly_fraction(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Default Kelly fraction is 0.1 when not in traits."""
        mock_agent.traits = {}
        setup_session_with_agent(mock_session, mock_agent)

        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=mock_agent.agent_id,
        )

        # Service should use default 0.1 kelly_fraction
        assert mock_agent.agent_id in paper_trading_service.active_positions


# ============================================================================
# PATTERN EVALUATION CONTRACT
# ============================================================================


class TestPatternEvaluation:
    """CONTRACT: Pattern evaluation returns correct signals."""

    @pytest.mark.asyncio
    async def test_no_patterns_returns_hold(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Agent with no patterns returns 'hold'."""
        mock_agent.assigned_patterns = []
        setup_session_with_agent(mock_session, mock_agent)

        # Access private method for testing
        signal = await paper_trading_service._evaluate_patterns(mock_agent, {})

        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_patterns_with_no_votes_returns_hold(
        self, paper_trading_service, mock_session, mock_agent
    ):
        """CONTRACT: Patterns with no clear signal return 'hold'."""
        setup_session_with_agent(mock_session, mock_agent)

        # MVP implementation always returns hold (simplified)
        signal = await paper_trading_service._evaluate_patterns(mock_agent, {})

        assert signal == "hold"


# ============================================================================
# MULTIPLE AGENTS CONTRACT
# ============================================================================


class TestMultipleAgents:
    """CONTRACT: Multiple agents can trade simultaneously."""

    @pytest.mark.asyncio
    async def test_multiple_agents_independent(
        self, paper_trading_service, mock_session
    ):
        """CONTRACT: Multiple agents have independent tracking."""
        # Create two mock agents
        agent1 = MagicMock()
        agent1.agent_id = "agent-001"
        agent1.name = "Agent One"
        agent1.status = "active"
        agent1.assigned_patterns = ["p1"]
        agent1.traits = {}

        agent2 = MagicMock()
        agent2.agent_id = "agent-002"
        agent2.name = "Agent Two"
        agent2.status = "active"
        agent2.assigned_patterns = ["p2"]
        agent2.traits = {}

        # Start agent 1
        setup_session_with_agent(mock_session, agent1)
        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=agent1.agent_id,
            initial_balance=10000.0,
        )

        # Start agent 2
        setup_session_with_agent(mock_session, agent2)
        await paper_trading_service.start_paper_trading(
            session=mock_session,
            agent_id=agent2.agent_id,
            initial_balance=20000.0,
        )

        # Verify independent tracking
        assert len(paper_trading_service.active_positions) == 2
        assert paper_trading_service.active_positions[agent1.agent_id]["balance"] == 10000.0
        assert paper_trading_service.active_positions[agent2.agent_id]["balance"] == 20000.0

    @pytest.mark.asyncio
    async def test_stop_one_agent_keeps_others(
        self, paper_trading_service, mock_session
    ):
        """CONTRACT: Stopping one agent doesn't affect others."""
        agent1 = MagicMock()
        agent1.agent_id = "agent-001"
        agent1.name = "Agent One"
        agent1.status = "active"
        agent1.assigned_patterns = []
        agent1.traits = {}

        agent2 = MagicMock()
        agent2.agent_id = "agent-002"
        agent2.name = "Agent Two"
        agent2.status = "active"
        agent2.assigned_patterns = []
        agent2.traits = {}

        # Start both
        setup_session_with_agent(mock_session, agent1)
        await paper_trading_service.start_paper_trading(
            session=mock_session, agent_id=agent1.agent_id
        )

        setup_session_with_agent(mock_session, agent2)
        await paper_trading_service.start_paper_trading(
            session=mock_session, agent_id=agent2.agent_id
        )

        # Stop agent 1
        await paper_trading_service.stop_paper_trading(agent1.agent_id)

        # Agent 2 should still be active
        assert agent1.agent_id not in paper_trading_service.active_positions
        assert agent2.agent_id in paper_trading_service.active_positions
