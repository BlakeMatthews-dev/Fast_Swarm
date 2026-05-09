"""
Unit tests for local_agents.core.executor module.

Tests cover:
- AgentExecutor initialization and run execution
- Result collection and metrics computation
- Timeout and state handling
- Error handling and agent crash resilience

All DB and external service dependencies are mocked.
"""

import time
import uuid
from dataclasses import asdict, dataclass
from unittest.mock import MagicMock, patch

import pytest

from Fast_Swarm.local_agents.core.executor import (
    AgentExecutor,
    AgentMetrics,
    AgentState,
    CRUCIBLE_MIN_FITNESS,
    CRUCIBLE_MIN_TRADES,
    CRUCIBLE_MIN_WIN_RATE,
    FITNESS_SURVIVAL_THRESHOLD,
    Position,
    TradeOutcome,
    TradeResult,
    run_agent_backtest,
)
from Fast_Swarm.local_agents.core.decision import DecisionZone, TradeDecisionResult
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits


# =============================================================================
# Helpers
# =============================================================================


def _make_agent_record(
    agent_id=None,
    agent_name="TestAgent",
    pattern_ids=None,
    pattern_weights=None,
    traits=None,
):
    """Create a minimal AgentRecord for testing."""
    if agent_id is None:
        agent_id = str(uuid.uuid4())
    if pattern_ids is None:
        pattern_ids = ["pat-1"]
    if pattern_weights is None:
        pattern_weights = {pid: 1.0 for pid in pattern_ids}
    if traits is None:
        traits = asdict(AgentTraits())
    return AgentRecord(
        agent_id=agent_id,
        agent_name=agent_name,
        pattern_ids=pattern_ids,
        pattern_weights=pattern_weights,
        traits=traits,
    )


def _make_pattern(pattern_id="pat-1", direction="long"):
    """Create a minimal pattern dict."""
    return {
        "pattern_id": pattern_id,
        "name": f"TestPattern-{pattern_id}",
        "direction": direction,
        "entry_conditions": [
            {"indicator": "rsi", "operator": "<", "value": 30},
        ],
        "exit_conditions": {},
    }


def _make_candle(close=50000.0, timestamp=None, high=None, low=None, open_=None, volume=1000.0):
    """Create a minimal candle dict."""
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    if high is None:
        high = close * 1.001
    if low is None:
        low = close * 0.999
    if open_ is None:
        open_ = close
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "timestamp": timestamp,
    }


def _make_indicators(**overrides):
    """Create a minimal indicators dict."""
    base = {"rsi": 50.0, "volume_ratio": 1.0, "macd_line": 0.0}
    base.update(overrides)
    return base


# =============================================================================
# Run Execution Tests (~8 tests)
# =============================================================================


class TestRunExecution:
    """Tests for single/batch agent run execution and state tracking."""

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_executor_initializes_idle(self):
        """AgentExecutor starts in IDLE state."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        assert executor.state == AgentState.IDLE
        assert executor.current_position is None
        assert executor.metrics.total_trades == 0

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_executor_traits_reconstructed_from_dict(self):
        """Traits dict on AgentRecord is converted to AgentTraits dataclass."""
        traits = AgentTraits(risk_tolerance=0.8, profit_target_greed=0.3)
        record = _make_agent_record(traits=asdict(traits))
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        assert isinstance(executor.traits, AgentTraits)
        assert executor.traits.risk_tolerance == 0.8
        assert executor.traits.profit_target_greed == 0.3

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_process_candle_idle_no_match_returns_none(self):
        """When idle and no pattern match, process_candle returns None."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # RSI at 50 should not match the < 30 entry condition
        result = executor.process_candle(_make_candle(), _make_indicators(rsi=50.0))
        assert result is None
        assert executor.state == AgentState.IDLE

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_process_candle_opens_position_on_match(self):
        """When idle and pattern matches, executor opens a position."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # RSI at 20 matches the < 30 condition
        result = executor.process_candle(
            _make_candle(close=50000.0),
            _make_indicators(rsi=20.0),
        )
        assert result is None  # No trade closed yet
        assert executor.state == AgentState.IN_POSITION
        assert executor.current_position is not None
        assert executor.current_position.pattern_id == "pat-1"

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_stop_loss_closes_position(self):
        """Position is closed when stop loss is hit."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # Open position
        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        assert executor.state == AgentState.IN_POSITION

        # Price drops below stop loss
        sl_price = executor.current_position.stop_loss_price
        result = executor.process_candle(
            _make_candle(close=sl_price * 0.99, timestamp=2000),
            _make_indicators(rsi=50.0),
        )
        assert result is not None
        assert result.exit_reason == "stop_loss"
        assert result.pnl_pct < 0
        assert executor.state == AgentState.IDLE

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_take_profit_closes_position(self):
        """Position is closed when take profit is hit."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        assert executor.state == AgentState.IN_POSITION

        tp_price = executor.current_position.take_profit_price
        result = executor.process_candle(
            _make_candle(close=tp_price * 1.01, timestamp=2000),
            _make_indicators(rsi=50.0),
        )
        assert result is not None
        assert result.exit_reason == "take_profit"
        assert result.pnl_pct > 0

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_dead_agent_skips_processing(self):
        """Dead agents return None from process_candle."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        executor.state = AgentState.DEAD
        result = executor.process_candle(_make_candle(), _make_indicators(rsi=20.0))
        assert result is None

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_run_agent_backtest_returns_executor(self):
        """run_agent_backtest processes candles and returns an executor."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        candles = [_make_candle(close=50000.0 + i * 10, timestamp=1000 + i * 3600000) for i in range(10)]
        indicators = [_make_indicators(rsi=50.0) for _ in range(10)]
        executor = run_agent_backtest(record, patterns, candles, indicators, db=None)
        assert isinstance(executor, AgentExecutor)


# =============================================================================
# Result Collection Tests (~6 tests)
# =============================================================================


class TestResultCollection:
    """Tests for result aggregation and metrics computation."""

    def test_agent_metrics_defaults(self):
        """AgentMetrics starts with sensible defaults."""
        m = AgentMetrics()
        assert m.total_trades == 0
        assert m.win_rate == 0.0
        assert m.avg_pnl == 0.0
        assert m.current_equity == 100.0

    def test_win_rate_computed_correctly(self):
        """Win rate = winning_trades / total_trades."""
        m = AgentMetrics(total_trades=10, winning_trades=6, losing_trades=4)
        assert m.win_rate == pytest.approx(0.6)

    def test_avg_pnl_computed_correctly(self):
        """Average PnL = total_pnl / total_trades."""
        m = AgentMetrics(total_trades=5, total_pnl_pct=25.0)
        assert m.avg_pnl == pytest.approx(5.0)

    def test_profit_factor_with_no_losses(self):
        """Profit factor is 10.0 when there are wins but no losses."""
        m = AgentMetrics(total_trades=5, winning_trades=5, losing_trades=0)
        assert m.profit_factor == 10.0

    def test_profit_factor_with_no_wins(self):
        """Profit factor is 0.0 when there are no wins."""
        m = AgentMetrics(total_trades=3, winning_trades=0, losing_trades=3)
        assert m.profit_factor == 0.0

    def test_fitness_neutral_with_few_trades(self):
        """Fitness returns 50.0 for agents with fewer than 5 trades."""
        m = AgentMetrics(total_trades=3)
        assert m.calculate_fitness() == 50.0

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_trade_history_accumulates(self):
        """Completed trades are appended to trade_history."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # Open
        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        # Close via stop loss
        sl_price = executor.current_position.stop_loss_price
        executor.process_candle(_make_candle(close=sl_price * 0.99, timestamp=2000), _make_indicators(rsi=50.0))
        assert len(executor.trade_history) == 1
        assert executor.metrics.total_trades == 1


# =============================================================================
# Timeout / State Handling Tests (~5 tests)
# =============================================================================


class TestTimeoutAndState:
    """Tests for state transitions and timeout-related behaviour."""

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_backtest_closes_open_position_at_end(self):
        """run_agent_backtest force-closes any open position at backtest end."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        # First candle triggers entry, then neutral candles
        candles = [_make_candle(close=50000.0, timestamp=1000)]
        candles += [_make_candle(close=50100.0, timestamp=1000 + (i + 1) * 3600000) for i in range(5)]
        indicators = [_make_indicators(rsi=20.0)]  # first triggers entry
        indicators += [_make_indicators(rsi=50.0) for _ in range(5)]
        executor = run_agent_backtest(record, patterns, candles, indicators, db=None)
        # Position should be closed by backtest_end
        assert executor.current_position is None
        assert executor.state == AgentState.IDLE

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_state_transitions_idle_to_position_and_back(self):
        """State transitions: IDLE -> IN_POSITION -> IDLE after close."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        assert executor.state == AgentState.IDLE

        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        assert executor.state == AgentState.IN_POSITION

        sl_price = executor.current_position.stop_loss_price
        executor.process_candle(_make_candle(close=sl_price * 0.99, timestamp=2000), _make_indicators(rsi=50.0))
        assert executor.state == AgentState.IDLE

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_agent_dies_when_fitness_below_threshold(self):
        """Agent transitions to DEAD when fitness drops below survival threshold."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # Simulate many losing trades to kill fitness
        executor.metrics.total_trades = 25
        executor.metrics.losing_trades = 25
        executor.metrics.winning_trades = 0
        executor.metrics.total_pnl_pct = -80.0
        executor.metrics.max_drawdown_pct = 60.0
        executor.metrics.max_consecutive_losses = 25
        # Compute fitness to check it is below threshold
        fitness = executor.metrics.calculate_fitness()
        assert fitness < FITNESS_SURVIVAL_THRESHOLD

    def test_crucible_qualification_requires_min_trades(self):
        """Agent does not qualify for crucible with too few trades."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        with patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False):
            executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        executor.metrics.total_trades = CRUCIBLE_MIN_TRADES - 1
        executor.metrics.winning_trades = CRUCIBLE_MIN_TRADES - 1
        assert not executor.qualifies_for_crucible()

    def test_crucible_qualification_success(self):
        """Agent qualifies for crucible with enough trades, fitness, and win rate."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        with patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False):
            executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        executor.metrics.total_trades = 100
        executor.metrics.winning_trades = 60
        executor.metrics.losing_trades = 40
        executor.metrics.total_pnl_pct = 50.0
        executor.metrics.max_drawdown_pct = 10.0
        executor.metrics.max_consecutive_losses = 3
        assert executor.qualifies_for_crucible()


# =============================================================================
# Error Handling Tests (~6 tests)
# =============================================================================


class TestErrorHandling:
    """Tests for error resilience: agent crash, missing data, bad patterns."""

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_missing_pattern_id_skipped_gracefully(self):
        """Pattern IDs that don't exist in patterns dict are skipped."""
        record = _make_agent_record(pattern_ids=["nonexistent"])
        patterns = {}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        result = executor.process_candle(_make_candle(), _make_indicators(rsi=20.0))
        assert result is None
        assert executor.state == AgentState.IDLE

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_pattern_without_entry_conditions_skipped(self):
        """Patterns without entry_conditions do not crash the executor."""
        record = _make_agent_record()
        patterns = {"pat-1": {"pattern_id": "pat-1", "name": "Empty"}}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        result = executor.process_candle(_make_candle(), _make_indicators(rsi=20.0))
        assert result is None

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_close_position_without_position_raises(self):
        """Calling _close_position with no current position raises ValueError."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        with pytest.raises(ValueError, match="No position to close"):
            executor._close_position(50000.0, 1000, "manual")

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_db_failure_on_trade_record_does_not_crash(self):
        """Database write failure during trade recording is caught."""
        mock_db = MagicMock()
        mock_db.create_trade.side_effect = RuntimeError("DB connection lost")
        mock_db.create_memory.side_effect = RuntimeError("DB connection lost")
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=mock_db, use_bear_protection=False)
        # Open position
        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        # Close via stop loss -- should not raise despite DB failure
        sl_price = executor.current_position.stop_loss_price
        result = executor.process_candle(
            _make_candle(close=sl_price * 0.99, timestamp=2000),
            _make_indicators(rsi=50.0),
        )
        assert result is not None
        assert executor.metrics.total_trades == 1

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_sync_to_database_without_db_is_noop(self):
        """sync_to_database with no db set does nothing."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        executor.sync_to_database()  # Should not raise

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_backtest_with_empty_candles(self):
        """run_agent_backtest with empty candle list does not crash."""
        record = _make_agent_record()
        patterns = {"pat-1": _make_pattern()}
        executor = run_agent_backtest(record, patterns, [], [], db=None)
        assert executor.metrics.total_trades == 0

    @patch("Fast_Swarm.local_agents.core.executor.BEAR_PROTECTION_AVAILABLE", False)
    def test_multiple_patterns_best_signal_selected(self):
        """When multiple patterns match, the best weighted signal is selected."""
        record = _make_agent_record(
            pattern_ids=["pat-1", "pat-2"],
            pattern_weights={"pat-1": 0.5, "pat-2": 2.0},
        )
        patterns = {
            "pat-1": _make_pattern("pat-1"),
            "pat-2": _make_pattern("pat-2"),
        }
        executor = AgentExecutor(record, patterns, db=None, use_bear_protection=False)
        # Both should match with rsi=20
        executor.process_candle(_make_candle(close=50000.0, timestamp=1000), _make_indicators(rsi=20.0))
        if executor.current_position:
            # pat-2 has higher weight, so it should be selected
            assert executor.current_position.pattern_id == "pat-2"
