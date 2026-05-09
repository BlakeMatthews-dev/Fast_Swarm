"""
Unit tests for AgentPaperTradingService.

Tests are organised into five classes matching the service's major
responsibilities:

    TestEvaluatePatterns   — pattern signal evaluation logic
    TestOpenPosition       — position opening, sizing, recording
    TestClosePosition      — P&L calculation, balance update, cleanup
    TestEvaluateAndTrade   — top-level orchestration (defensive trigger, routing)
    TestLifecycle          — start / stop / pause / resume / active-agents

All tests use mocked DB sessions so they run without PostgreSQL.
Tests that need a real DB are marked ``@pytest.mark.requires_db``.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)

# Re-use helpers from the local conftest
from .conftest import make_eval_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYMBOL = "BTC-USDT"
PRICE = 50_000.0
BALANCE = 10_000.0
KELLY = 0.1  # default kelly_fraction


def _setup_active_agent(service, agent, balance=BALANCE):
    """Register an agent as actively paper-trading inside the service."""
    service.active_positions[agent.agent_id] = {
        "agent_id": agent.agent_id,
        "agent_name": agent.name,
        "balance": balance,
        "symbols": [SYMBOL],
        "positions": {},
        "started_at": datetime.now(timezone.utc),
        "trades_count": 0,
        "total_pnl": 0.0,
    }


def _setup_open_position(service, agent, side="long", entry_price=PRICE, size=None):
    """Inject an open position into the service's tracking dict."""
    if agent.agent_id not in service.active_positions:
        _setup_active_agent(service, agent)

    pos_size = size or (BALANCE * KELLY / entry_price)
    trade_id = str(uuid.uuid4())
    service.active_positions[agent.agent_id]["positions"][SYMBOL] = {
        "trade_id": trade_id,
        "side": side,
        "entry_price": entry_price,
        "size": pos_size,
        "size_usd": BALANCE * KELLY,
        "entry_time": datetime.now(timezone.utc),
    }
    return trade_id


def _mock_session_with_agent(mock_session, agent):
    """Configure mock_session.exec to return the given agent on first()."""
    result_proxy = MagicMock()
    result_proxy.first.return_value = agent
    mock_session.exec = AsyncMock(return_value=result_proxy)


# ============================================================================
# 1. TestEvaluatePatterns (~10 tests)
# ============================================================================


class TestEvaluatePatterns:
    """Tests for AgentPaperTradingService._evaluate_patterns."""

    @pytest.mark.asyncio
    async def test_no_patterns_returns_hold(self, paper_trading_service, make_agent):
        """Agent with no assigned patterns produces 'hold'."""
        agent = make_agent(assigned_patterns={})
        signal = await paper_trading_service._evaluate_patterns(agent, {})
        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_buy_signal_above_threshold(self, paper_trading_service, make_agent):
        """Strong long-direction entry match produces 'buy'."""
        agent = make_agent(
            assigned_patterns={
                "p1": {
                    "entry_conditions": {"ind": "rsi", "op": "<", "val": 30},
                    "exit_conditions": {},
                    "direction": "long",
                },
            },
            pattern_weights={"p1": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=1.0)

        with patch(
            "Fast_Swarm.Trading.Services.agent_paper_trading_service.evaluate_conditions",
            return_value=mock_result,
            create=True,
        ) as mock_eval:
            # Patch the import inside _evaluate_patterns
            with patch.dict(
                "sys.modules",
                {
                    "Fast_Swarm.local_agents.backtest.pattern_matcher": MagicMock(
                        evaluate_conditions=MagicMock(return_value=mock_result)
                    )
                },
            ):
                signal = await paper_trading_service._evaluate_patterns(agent, {"rsi": 20})

        assert signal == "buy"

    @pytest.mark.asyncio
    async def test_sell_signal_above_threshold(self, paper_trading_service, make_agent):
        """Strong short-direction entry match produces 'sell'."""
        agent = make_agent(
            assigned_patterns={
                "p1": {
                    "entry_conditions": {"ind": "rsi", "op": ">", "val": 80},
                    "exit_conditions": {},
                    "direction": "short",
                },
            },
            pattern_weights={"p1": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=1.0)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {"rsi": 85})

        assert signal == "sell"

    @pytest.mark.asyncio
    async def test_close_wins_over_entry(self, paper_trading_service, make_agent):
        """Exit condition match (close_votes > 0.5) takes priority over entry signals."""
        agent = make_agent(
            assigned_patterns={
                "p1": {
                    "entry_conditions": {"ind": "rsi", "op": "<", "val": 30},
                    "exit_conditions": {"ind": "rsi", "op": ">", "val": 70},
                    "direction": "long",
                },
            },
            pattern_weights={"p1": 1.0},
        )

        # Both entry AND exit match
        entry_result = make_eval_result(matched=True, confidence=1.0)
        exit_result = make_eval_result(matched=True, confidence=1.0)

        call_count = 0

        def side_effect(conditions, data):
            nonlocal call_count
            call_count += 1
            # First call is entry, second is exit
            if call_count % 2 == 1:
                return entry_result
            return exit_result

        mock_module = MagicMock(evaluate_conditions=MagicMock(side_effect=side_effect))

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        assert signal == "close"

    @pytest.mark.asyncio
    async def test_weighted_voting(self, paper_trading_service, make_agent):
        """Patterns weighted by fitness — heavier weight wins the vote."""
        agent = make_agent(
            assigned_patterns={
                "p_long": {
                    "entry_conditions": {"ind": "x"},
                    "exit_conditions": {},
                    "direction": "long",
                },
                "p_short": {
                    "entry_conditions": {"ind": "y"},
                    "exit_conditions": {},
                    "direction": "short",
                },
            },
            # Long pattern has 3x weight
            pattern_weights={"p_long": 3.0, "p_short": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=1.0)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        # buy_votes=3.0, sell_votes=1.0 → 3 > 1.5*1 and 3 >= 0.5 → "buy"
        assert signal == "buy"

    @pytest.mark.asyncio
    async def test_import_error_fallback_hold(self, paper_trading_service, make_agent):
        """If pattern_matcher module cannot be imported, fall back to 'hold'."""
        agent = make_agent(
            assigned_patterns={
                "p1": {
                    "entry_conditions": {"ind": "rsi"},
                    "exit_conditions": {},
                    "direction": "long",
                },
            },
        )

        # Remove the module so the import inside _evaluate_patterns fails
        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": None}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_tie_returns_hold(self, paper_trading_service, make_agent):
        """Equal buy and sell scores (no 1.5x dominance) produce 'hold'."""
        agent = make_agent(
            assigned_patterns={
                "p_long": {
                    "entry_conditions": {"ind": "x"},
                    "exit_conditions": {},
                    "direction": "long",
                },
                "p_short": {
                    "entry_conditions": {"ind": "y"},
                    "exit_conditions": {},
                    "direction": "short",
                },
            },
            pattern_weights={"p_long": 1.0, "p_short": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=1.0)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        # buy_votes=1.0, sell_votes=1.0 → neither > 1.5*other → "hold"
        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_single_pattern_buy(self, paper_trading_service, make_agent):
        """Single long pattern that matches entry → 'buy'."""
        agent = make_agent(
            assigned_patterns={
                "only": {
                    "entry_conditions": {"ind": "rsi"},
                    "exit_conditions": {},
                    "direction": "long",
                },
            },
            pattern_weights={"only": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=0.8)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        # buy_votes=0.8, sell_votes=0 → 0.8 > 0*1.5 and 0.8 >= 0.5 → "buy"
        assert signal == "buy"

    @pytest.mark.asyncio
    async def test_single_pattern_sell(self, paper_trading_service, make_agent):
        """Single short pattern that matches entry → 'sell'."""
        agent = make_agent(
            assigned_patterns={
                "only": {
                    "entry_conditions": {"ind": "rsi"},
                    "exit_conditions": {},
                    "direction": "short",
                },
            },
            pattern_weights={"only": 1.0},
        )

        mock_result = make_eval_result(matched=True, confidence=0.9)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        # sell_votes=0.9 > 0*1.5 and 0.9 >= 0.5 → "sell"
        assert signal == "sell"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_hold(self, paper_trading_service, make_agent):
        """Entry match with confidence below 0.5 threshold → 'hold'."""
        agent = make_agent(
            assigned_patterns={
                "p1": {
                    "entry_conditions": {"ind": "rsi"},
                    "exit_conditions": {},
                    "direction": "long",
                },
            },
            pattern_weights={"p1": 1.0},
        )

        # confidence 0.3 → buy_votes = 0.3 < 0.5 threshold
        mock_result = make_eval_result(matched=True, confidence=0.3)
        mock_module = MagicMock(
            evaluate_conditions=MagicMock(return_value=mock_result)
        )

        with patch.dict("sys.modules", {"Fast_Swarm.local_agents.backtest.pattern_matcher": mock_module}):
            signal = await paper_trading_service._evaluate_patterns(agent, {})

        assert signal == "hold"


# ============================================================================
# 2. TestOpenPosition (~8 tests)
# ============================================================================


class TestOpenPosition:
    """Tests for AgentPaperTradingService._open_position."""

    @pytest.mark.asyncio
    async def test_kelly_sizing(self, paper_trading_service, mock_session, sample_agent_record):
        """Position size = kelly_fraction * balance / price."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        result = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )

        expected_usd = BALANCE * KELLY  # 1000
        expected_size = expected_usd / PRICE  # 0.02
        assert result["size_usd"] == pytest.approx(expected_usd)
        assert result["size"] == pytest.approx(expected_size)

    @pytest.mark.asyncio
    @pytest.mark.requires_db
    async def test_trade_recorded_to_db(self, paper_trading_service, mock_session, sample_agent_record):
        """A LiveTradeUnified record is added to the session with source='paper'."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )

        # session.add should have been called with the trade object
        mock_session.add.assert_called_once()
        trade_obj = mock_session.add.call_args[0][0]
        assert trade_obj.source == "paper"
        assert trade_obj.symbol == SYMBOL
        assert trade_obj.status == "open"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_position_tracked_in_memory(self, paper_trading_service, mock_session, sample_agent_record):
        """After opening, the position appears in active_positions dict."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        result = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )

        positions = paper_trading_service.active_positions[agent.agent_id]["positions"]
        assert SYMBOL in positions
        assert positions[SYMBOL]["trade_id"] == result["trade_id"]

    @pytest.mark.asyncio
    async def test_long_position_fields(self, paper_trading_service, mock_session, sample_agent_record):
        """Long position has correct side, entry_price, and action."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        result = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )

        assert result["action"] == "open"
        assert result["side"] == "long"
        assert result["price"] == PRICE
        assert result["symbol"] == SYMBOL

    @pytest.mark.asyncio
    async def test_short_position_fields(self, paper_trading_service, mock_session, sample_agent_record):
        """Short position recorded with side='short'."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        result = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "short", PRICE, {}, "bear"
        )

        assert result["side"] == "short"
        assert result["action"] == "open"

        pos = paper_trading_service.active_positions[agent.agent_id]["positions"][SYMBOL]
        assert pos["side"] == "short"

    @pytest.mark.asyncio
    async def test_insufficient_balance(self, paper_trading_service, mock_session, sample_agent_record):
        """Opening with zero balance still goes through (size → 0). Service does not guard."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent, balance=0.0)

        result = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )

        # Size should be 0 (0 * kelly / price)
        assert result["size"] == pytest.approx(0.0)
        assert result["size_usd"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_already_has_position(self, paper_trading_service, mock_session, sample_agent_record):
        """Opening a second position on the same symbol overwrites the first (no guard in service)."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        first = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )
        second = await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "short", PRICE + 1000, {}, "bear"
        )

        # Second call overwrites — the position now reflects the second trade
        pos = paper_trading_service.active_positions[agent.agent_id]["positions"][SYMBOL]
        assert pos["trade_id"] == second["trade_id"]
        assert pos["side"] == "short"

    @pytest.mark.asyncio
    async def test_trades_count_incremented(self, paper_trading_service, mock_session, sample_agent_record):
        """trades_count in active_positions increments on each open."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        assert paper_trading_service.active_positions[agent.agent_id]["trades_count"] == 0
        await paper_trading_service._open_position(
            mock_session, agent, SYMBOL, "long", PRICE, {}, "bull"
        )
        assert paper_trading_service.active_positions[agent.agent_id]["trades_count"] == 1


# ============================================================================
# 3. TestClosePosition (~8 tests)
# ============================================================================


class TestClosePosition:
    """Tests for AgentPaperTradingService._close_position."""

    @pytest.mark.asyncio
    async def test_long_pnl_calculation(self, paper_trading_service, mock_session, sample_agent_record):
        """Long P&L = (exit - entry) / entry * 100."""
        agent = sample_agent_record
        entry = 50_000.0
        exit_price = 51_000.0
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=entry)

        # Mock the trade lookup for updating the DB record
        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, exit_price, {}, "bull"
        )

        expected_pct = (exit_price - entry) / entry * 100
        assert result["pnl_pct"] == pytest.approx(expected_pct)

    @pytest.mark.asyncio
    async def test_short_pnl_calculation(self, paper_trading_service, mock_session, sample_agent_record):
        """Short P&L = (entry - exit) / entry * 100."""
        agent = sample_agent_record
        entry = 50_000.0
        exit_price = 49_000.0
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="short", entry_price=entry)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, exit_price, {}, "bear"
        )

        expected_pct = (entry - exit_price) / entry * 100
        assert result["pnl_pct"] == pytest.approx(expected_pct)

    @pytest.mark.asyncio
    async def test_no_position_error(self, paper_trading_service, mock_session, sample_agent_record):
        """Closing a symbol with no open position returns an error dict."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        # No position opened

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, PRICE, {}, "bull"
        )

        assert "error" in result
        assert "No position" in result["error"]

    @pytest.mark.asyncio
    async def test_balance_update(self, paper_trading_service, mock_session, sample_agent_record):
        """Balance increases by pnl_usd on profitable close."""
        agent = sample_agent_record
        entry = 50_000.0
        exit_price = 52_000.0
        _setup_active_agent(paper_trading_service, agent, balance=BALANCE)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=entry)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, exit_price, {}, "bull"
        )

        new_balance = paper_trading_service.active_positions[agent.agent_id]["balance"]
        assert new_balance == pytest.approx(BALANCE + result["pnl_usd"])

    @pytest.mark.asyncio
    @pytest.mark.requires_db
    async def test_trade_record_updated(self, paper_trading_service, mock_session, sample_agent_record):
        """The DB trade record gets exit_time, exit_price, pnl, status='closed'."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=PRICE)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, PRICE + 500, {}, "bull"
        )

        assert trade_record.status == "closed"
        assert trade_record.exit_price == Decimal(str(PRICE + 500))
        assert trade_record.exit_reason == "signal"
        assert trade_record.exit_time is not None

    @pytest.mark.asyncio
    async def test_position_removed(self, paper_trading_service, mock_session, sample_agent_record):
        """After closing, the symbol is removed from active_positions."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=PRICE)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, PRICE + 100, {}, "bull"
        )

        positions = paper_trading_service.active_positions[agent.agent_id]["positions"]
        assert SYMBOL not in positions

    @pytest.mark.asyncio
    async def test_duration_seconds(self, paper_trading_service, mock_session, sample_agent_record):
        """duration_seconds is a positive number (exit_time - entry_time)."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=PRICE)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, PRICE, {}, "bull"
        )

        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.requires_db
    async def test_realized_pnl_recorded(self, paper_trading_service, mock_session, sample_agent_record):
        """realized_pnl field is set on the trade record."""
        agent = sample_agent_record
        entry = 50_000.0
        exit_price = 51_000.0
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=entry)

        trade_record = MagicMock()
        result_proxy = MagicMock()
        result_proxy.first.return_value = trade_record
        mock_session.exec = AsyncMock(return_value=result_proxy)

        result = await paper_trading_service._close_position(
            mock_session, agent, SYMBOL, exit_price, {}, "bull"
        )

        # realized_pnl should be set to the Decimal pnl value
        assert trade_record.realized_pnl is not None
        assert float(trade_record.realized_pnl) == pytest.approx(result["pnl_usd"], abs=0.01)


# ============================================================================
# 4. TestEvaluateAndTrade (~5 tests)
# ============================================================================


class TestEvaluateAndTrade:
    """Tests for AgentPaperTradingService.evaluate_and_trade."""

    @pytest.mark.asyncio
    async def test_defensive_trigger_force_closes(
        self, paper_trading_service, mock_session, sample_agent_record
    ):
        """defensive_trigger=1 with an open position forces a close."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=PRICE)

        _mock_session_with_agent(mock_session, agent)

        # Need a second exec call for the _close_position trade lookup
        trade_record = MagicMock()

        call_count = 0
        original_exec = mock_session.exec

        async def exec_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: Agent lookup in evaluate_and_trade
                proxy = MagicMock()
                proxy.first.return_value = agent
                return proxy
            else:
                # Second call: Trade lookup in _close_position
                proxy = MagicMock()
                proxy.first.return_value = trade_record
                return proxy

        mock_session.exec = AsyncMock(side_effect=exec_side_effect)

        candle = {"defensive_trigger": 1}
        result = await paper_trading_service.evaluate_and_trade(
            mock_session, agent.agent_id, SYMBOL, PRICE + 100, candle
        )

        assert result is not None
        assert result["action"] == "close"

    @pytest.mark.asyncio
    async def test_defensive_trigger_blocks_opening(
        self, paper_trading_service, mock_session, sample_agent_record
    ):
        """defensive_trigger=1 without open position blocks new trades (returns None)."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        # No position open

        _mock_session_with_agent(mock_session, agent)

        candle = {"defensive_trigger": 1}
        result = await paper_trading_service.evaluate_and_trade(
            mock_session, agent.agent_id, SYMBOL, PRICE, candle
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_buy_path(self, paper_trading_service, mock_session, sample_agent_record):
        """evaluate → buy signal → opens long position."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        _mock_session_with_agent(mock_session, agent)

        with patch.object(
            paper_trading_service, "_evaluate_patterns", new_callable=AsyncMock, return_value="buy"
        ):
            result = await paper_trading_service.evaluate_and_trade(
                mock_session, agent.agent_id, SYMBOL, PRICE, {}
            )

        assert result is not None
        assert result["action"] == "open"
        assert result["side"] == "long"

    @pytest.mark.asyncio
    async def test_sell_path(self, paper_trading_service, mock_session, sample_agent_record):
        """evaluate → sell signal → opens short position."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        _mock_session_with_agent(mock_session, agent)

        with patch.object(
            paper_trading_service, "_evaluate_patterns", new_callable=AsyncMock, return_value="sell"
        ):
            result = await paper_trading_service.evaluate_and_trade(
                mock_session, agent.agent_id, SYMBOL, PRICE, {}
            )

        assert result is not None
        assert result["action"] == "open"
        assert result["side"] == "short"

    @pytest.mark.asyncio
    async def test_close_path(self, paper_trading_service, mock_session, sample_agent_record):
        """evaluate → close signal with open position → closes position."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)
        _setup_open_position(paper_trading_service, agent, side="long", entry_price=PRICE)

        # exec called twice: once for agent lookup, once for trade lookup in _close_position
        trade_record = MagicMock()
        call_count = 0

        async def exec_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proxy = MagicMock()
            if call_count == 1:
                proxy.first.return_value = agent
            else:
                proxy.first.return_value = trade_record
            return proxy

        mock_session.exec = AsyncMock(side_effect=exec_side_effect)

        with patch.object(
            paper_trading_service, "_evaluate_patterns", new_callable=AsyncMock, return_value="close"
        ):
            result = await paper_trading_service.evaluate_and_trade(
                mock_session, agent.agent_id, SYMBOL, PRICE + 200, {}
            )

        assert result is not None
        assert result["action"] == "close"

    @pytest.mark.asyncio
    async def test_hold_path(self, paper_trading_service, mock_session, sample_agent_record):
        """evaluate → hold signal → no action (returns None)."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        _mock_session_with_agent(mock_session, agent)

        with patch.object(
            paper_trading_service, "_evaluate_patterns", new_callable=AsyncMock, return_value="hold"
        ):
            result = await paper_trading_service.evaluate_and_trade(
                mock_session, agent.agent_id, SYMBOL, PRICE, {}
            )

        assert result is None


# ============================================================================
# 5. TestLifecycle (~4 tests)
# ============================================================================


class TestLifecycle:
    """Tests for start/stop/pause/resume/get_active_agents."""

    @pytest.mark.asyncio
    async def test_start_paper_trading(self, paper_trading_service, mock_session, sample_agent_record):
        """start_paper_trading registers the agent in active_positions."""
        agent = sample_agent_record
        _mock_session_with_agent(mock_session, agent)

        result = await paper_trading_service.start_paper_trading(
            mock_session, agent.agent_id, symbols=["BTC-USDT"], initial_balance=5000.0
        )

        assert result["status"] == "started"
        assert agent.agent_id in paper_trading_service.active_positions
        info = paper_trading_service.active_positions[agent.agent_id]
        assert info["balance"] == 5000.0
        assert info["symbols"] == ["BTC-USDT"]

    @pytest.mark.asyncio
    async def test_stop_paper_trading(self, paper_trading_service, mock_session, sample_agent_record):
        """stop_paper_trading removes the agent from active_positions."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        result = await paper_trading_service.stop_paper_trading(agent.agent_id)

        assert result["status"] == "stopped"
        assert agent.agent_id not in paper_trading_service.active_positions
        assert "duration_seconds" in result

    @pytest.mark.asyncio
    async def test_get_active_agents(self, paper_trading_service, make_agent):
        """get_active_agents returns info for all registered agents."""
        a1 = make_agent(agent_id="a1", name="Agent1")
        a2 = make_agent(agent_id="a2", name="Agent2")
        _setup_active_agent(paper_trading_service, a1)
        _setup_active_agent(paper_trading_service, a2)

        agents = await paper_trading_service.get_active_agents()

        assert len(agents) == 2
        agent_ids = {a["agent_id"] for a in agents}
        assert agent_ids == {"a1", "a2"}

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, paper_trading_service, sample_agent_record):
        """Pause sets paused=True, resume sets paused=False."""
        agent = sample_agent_record
        _setup_active_agent(paper_trading_service, agent)

        # Pause
        pause_result = await paper_trading_service.pause_trading(agent.agent_id)
        assert pause_result["status"] == "paused"
        assert paper_trading_service.is_paused(agent.agent_id) is True

        # Resume
        resume_result = await paper_trading_service.resume_trading(agent.agent_id)
        assert resume_result["status"] == "resumed"
        assert paper_trading_service.is_paused(agent.agent_id) is False

    @pytest.mark.asyncio
    async def test_stop_nonexistent_agent(self, paper_trading_service):
        """Stopping an agent that isn't trading returns an error."""
        result = await paper_trading_service.stop_paper_trading("nonexistent-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_pause_nonexistent_agent(self, paper_trading_service):
        """Pausing an agent that isn't trading returns an error."""
        result = await paper_trading_service.pause_trading("nonexistent-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_start_inactive_agent(self, paper_trading_service, mock_session, make_agent):
        """Starting paper trading for a non-active agent returns an error."""
        agent = make_agent(status="retired")
        _mock_session_with_agent(mock_session, agent)

        result = await paper_trading_service.start_paper_trading(
            mock_session, agent.agent_id
        )

        assert "error" in result
        assert "not active" in result["error"]
