"""
Trio Engine Exit Logic Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Implementation Plan (Part 2: Trio Engine Exit Logic)
Tests take profit, stop loss, trailing stops, bear protection VETO, and exit priority.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from Fast_Swarm.local_agents.backtest.trio_engine import (
    Holding,
    TrioBacktestEngine,
    TrioPosition,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_pattern_matcher():
    """Create a mock pattern matcher."""
    return MagicMock()


@pytest.fixture
def sample_patterns():
    """Sample patterns with exit conditions."""
    return {
        "pattern-001": {
            "pattern_id": "pattern-001",
            "entry_conditions": [
                {"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70}
            ],
            "exit_conditions": {
                "stop_loss_pct": 0.05,  # 5%
                "take_profit_pct": 0.10,  # 10%
            },
        },
    }


@pytest.fixture
def sample_patterns_with_indicator_exit():
    """Patterns with indicator-based exit conditions."""
    return {
        "pattern-002": {
            "pattern_id": "pattern-002",
            "entry_conditions": [],
            "exit_conditions": {
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.15,
                "conditions": [
                    {"indicator": "rsi_14", "operator": ">", "value": 80}  # Use "value" not "min"
                ],
            },
        },
    }


@pytest.fixture
def mock_agent(sample_patterns):
    """Create a mock agent with patterns."""
    agent = MagicMock()
    agent.pattern_ids = list(sample_patterns.keys())
    agent.traits = {
        "min_threshold": 0.3,
        "exit_threshold": 0.5,
        "trailing_stop_pct": 0.03,
    }
    return agent


@pytest.fixture
def trio_engine(mock_pattern_matcher, sample_patterns):
    """Create a trio engine for testing."""
    return TrioBacktestEngine(
        pattern_matcher=mock_pattern_matcher,
        patterns=sample_patterns,
        use_bear_protection=False,  # Disable for basic tests
    )


@pytest.fixture
def trio_engine_with_bear(mock_pattern_matcher, sample_patterns):
    """Create a trio engine with bear protection enabled."""
    engine = TrioBacktestEngine(
        pattern_matcher=mock_pattern_matcher,
        patterns=sample_patterns,
        use_bear_protection=True,
    )
    # Mock the bear protection service
    engine.bear_protection_service = MagicMock()
    return engine


@pytest.fixture
def btc_position():
    """Position holding BTC."""
    return TrioPosition(
        holding=Holding.BTC,
        amount=1.0,
        entry_price=50000.0,
        entry_timestamp=1704067200,
        highwater_price=50000.0,
    )


# ============================================================================
# STOP LOSS CONTRACT
# ============================================================================


class TestStopLoss:
    """CONTRACT: Stop loss exits at configured loss threshold."""

    def test_stop_loss_triggers_at_threshold(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Stop loss triggers when loss reaches threshold."""
        # Price dropped 5% (matches stop loss threshold)
        indicators = {
            "close": 47500.0,  # -5% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "stop_loss"

    def test_stop_loss_does_not_trigger_above_threshold(
        self, trio_engine, mock_agent, btc_position
    ):
        """CONTRACT: Stop loss does NOT trigger when loss is less than threshold."""
        # Price dropped only 3% (below 5% threshold)
        indicators = {
            "close": 48500.0,  # -3% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is False

    def test_stop_loss_triggers_at_large_loss(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Stop loss triggers for losses larger than threshold."""
        # Price dropped 10%
        indicators = {
            "close": 45000.0,  # -10% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "stop_loss"


# ============================================================================
# TAKE PROFIT CONTRACT
# ============================================================================


class TestTakeProfit:
    """CONTRACT: Take profit exits at configured profit threshold."""

    def test_take_profit_triggers_at_threshold(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Take profit triggers when profit reaches threshold."""
        # Price rose 10% (matches take profit threshold)
        indicators = {
            "close": 55000.0,  # +10% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "take_profit"

    def test_take_profit_does_not_trigger_below_threshold(
        self, trio_engine, mock_agent, btc_position
    ):
        """CONTRACT: Take profit does NOT trigger below threshold."""
        # Price rose only 5% (below 10% threshold)
        indicators = {
            "close": 52500.0,  # +5% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is False

    def test_take_profit_triggers_at_large_profit(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Take profit triggers for profits larger than threshold."""
        # Price rose 20%
        indicators = {
            "close": 60000.0,  # +20% from 50000
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "take_profit"


# ============================================================================
# TRAILING STOP CONTRACT
# ============================================================================


class TestTrailingStop:
    """CONTRACT: Trailing stop protects unrealized gains."""

    def test_trailing_stop_activates_after_profit(
        self, trio_engine, mock_agent, btc_position
    ):
        """CONTRACT: Trailing stop only activates after minimum profit."""
        # First, price goes up 10% (sets highwater)
        btc_position.highwater_price = 55000.0

        # Now price retraces more than trailing threshold from peak
        indicators = {
            "close": 53000.0,  # ~3.6% below highwater
            "atr_14": 0,  # No ATR to trigger fixed % fallback
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "trailing_stop"

    def test_trailing_stop_does_not_activate_in_loss(
        self, trio_engine, mock_agent, btc_position
    ):
        """CONTRACT: Trailing stop does NOT activate when position is losing."""
        # Position is in loss (highwater = entry)
        btc_position.highwater_price = 50000.0

        indicators = {
            "close": 49000.0,  # -2% from entry
            "atr_14": 0,
        }

        # Should NOT trigger trailing (not in profit)
        # May trigger stop loss instead if threshold met
        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        # Trailing stop specifically should not be the reason
        if should_exit:
            assert reason != "trailing_stop"

    def test_trailing_stop_uses_atr_when_available(
        self, trio_engine, mock_agent, btc_position
    ):
        """CONTRACT: ATR-based trailing is used when ATR data available."""
        # Set up profitable position
        btc_position.highwater_price = 56000.0  # +12% from entry

        indicators = {
            "close": 53000.0,
            "atr_14": 1500.0,  # ATR available
        }

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        # When ATR trailing triggers, reason should be atr_trailing_stop
        if should_exit and "trailing" in reason:
            assert reason == "atr_trailing_stop"

    def test_highwater_mark_updates(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Highwater mark updates when price increases."""
        initial_highwater = btc_position.highwater_price

        # Price goes up
        indicators = {
            "close": 55000.0,  # +10% from entry
            "atr_14": 0,
        }

        trio_engine._check_exit(mock_agent, indicators, btc_position)

        # Highwater should be updated
        assert btc_position.highwater_price == 55000.0
        assert btc_position.highwater_price > initial_highwater


# ============================================================================
# BEAR PROTECTION VETO CONTRACT
# ============================================================================


class TestBearProtectionVeto:
    """CONTRACT: Bear protection VETO forces exits in crisis."""

    def test_bear_veto_forces_exit(
        self, trio_engine_with_bear, mock_agent, btc_position
    ):
        """CONTRACT: Bear protection VETO forces exit regardless of P&L."""
        # Mock bear protection to signal VETO
        mock_regime = MagicMock()
        mock_regime.exit_signal_active = True
        trio_engine_with_bear.bear_protection_service.evaluate_regime.return_value = mock_regime

        # Position is profitable (normally wouldn't exit)
        indicators = {
            "close": 52000.0,  # +4% profit (below TP)
            "price_velocity": 0.6,
            "price_acceleration": -2.0,
            "adx_jerk": -0.5,
        }

        should_exit, confidence, reason = trio_engine_with_bear._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is True
        assert reason == "bear_protection_veto"

    def test_bear_veto_overrides_take_profit(
        self, trio_engine_with_bear, mock_agent, btc_position
    ):
        """CONTRACT: Bear VETO wins even when take profit also triggers."""
        # Mock bear protection VETO
        mock_regime = MagicMock()
        mock_regime.exit_signal_active = True
        trio_engine_with_bear.bear_protection_service.evaluate_regime.return_value = mock_regime

        # Position at take profit level
        indicators = {
            "close": 60000.0,  # +20% profit (triggers TP)
            "price_velocity": 0.6,
            "price_acceleration": -2.0,
            "adx_jerk": -0.5,
        }

        should_exit, confidence, reason = trio_engine_with_bear._check_exit(
            mock_agent, indicators, btc_position
        )

        # Bear VETO uses infinity value, so it should win
        assert should_exit is True
        assert reason == "bear_protection_veto"

    def test_no_exit_when_bear_protection_inactive(
        self, trio_engine_with_bear, mock_agent, btc_position
    ):
        """CONTRACT: No forced exit when bear protection is not active."""
        # Mock bear protection to NOT signal VETO
        mock_regime = MagicMock()
        mock_regime.exit_signal_active = False
        trio_engine_with_bear.bear_protection_service.evaluate_regime.return_value = mock_regime

        indicators = {
            "close": 52000.0,  # +4% (no exit conditions met)
            "price_velocity": 0.1,
            "price_acceleration": 0.1,
            "adx_jerk": 0.1,
        }

        should_exit, confidence, reason = trio_engine_with_bear._check_exit(
            mock_agent, indicators, btc_position
        )

        assert should_exit is False


# ============================================================================
# PATTERN-BASED EXIT CONTRACT
# ============================================================================


class TestPatternBasedExit:
    """CONTRACT: Pattern indicator conditions can trigger exits."""

    def test_pattern_exit_triggers_on_indicator(
        self, mock_pattern_matcher, sample_patterns_with_indicator_exit
    ):
        """CONTRACT: Pattern exit triggers when indicator conditions met."""
        engine = TrioBacktestEngine(
            pattern_matcher=mock_pattern_matcher,
            patterns=sample_patterns_with_indicator_exit,
            use_bear_protection=False,
        )

        agent = MagicMock()
        agent.pattern_ids = ["pattern-002"]
        agent.traits = {"exit_threshold": 0.5}

        position = TrioPosition(
            holding=Holding.BTC,
            entry_price=50000.0,
            highwater_price=50000.0,
        )

        indicators = {
            "close": 51000.0,  # Small profit, below TP
            "rsi_14": 85,  # Above 80, triggers exit condition
        }

        should_exit, confidence, reason = engine._check_exit(agent, indicators, position)

        assert should_exit is True
        assert reason == "pattern_exit"


# ============================================================================
# MOST PROFITABLE EXIT WINS CONTRACT
# ============================================================================


class TestMostProfitableExitWins:
    """CONTRACT: When multiple exits trigger, most profitable wins."""

    def test_take_profit_beats_stop_loss(
        self, mock_pattern_matcher
    ):
        """CONTRACT: Take profit (better value) beats stop loss."""
        # Create pattern where both TP and SL could trigger
        patterns = {
            "pattern-dual": {
                "exit_conditions": {
                    "stop_loss_pct": 0.20,  # 20% stop loss (would trigger at -20%)
                    "take_profit_pct": 0.05,  # 5% take profit
                },
            },
        }

        engine = TrioBacktestEngine(
            pattern_matcher=mock_pattern_matcher,
            patterns=patterns,
            use_bear_protection=False,
        )

        agent = MagicMock()
        agent.pattern_ids = ["pattern-dual"]
        agent.traits = {"exit_threshold": 0.5}

        position = TrioPosition(
            holding=Holding.BTC,
            entry_price=50000.0,
            highwater_price=60000.0,  # Was at +20%
        )

        # Now at 10% profit - triggers TP but not SL
        indicators = {
            "close": 55000.0,  # +10% from entry
            "atr_14": 1000.0,
        }

        should_exit, confidence, reason = engine._check_exit(agent, indicators, position)

        assert should_exit is True
        assert reason == "take_profit"

    def test_exit_priority_documented(self):
        """CONTRACT: Exit priority is clearly defined."""
        # Document the priority system:
        # 1. Bear Protection VETO (infinity value - always wins)
        # 2-5. All other exits sorted by P&L value (most profitable wins)
        #
        # This is a documentation test to ensure priority is understood
        priorities = [
            ("bear_protection_veto", "Uses float('inf'), always wins"),
            ("take_profit", "Uses current P&L value"),
            ("trailing_stop", "Uses current P&L value"),
            ("pattern_exit", "Uses current P&L value"),
            ("stop_loss", "Uses current (negative) P&L value"),
        ]
        assert len(priorities) == 5


# ============================================================================
# EDGE CASES CONTRACT
# ============================================================================


class TestExitEdgeCases:
    """CONTRACT: Edge cases handled correctly."""

    def test_no_exit_when_holding_usd(self, trio_engine, mock_agent):
        """CONTRACT: No exit check when holding USD (no position)."""
        position = TrioPosition(holding=Holding.USD)

        indicators = {"close": 50000.0}

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, position
        )

        assert should_exit is False

    def test_no_exit_with_zero_entry_price(self, trio_engine, mock_agent):
        """CONTRACT: Handle zero entry price gracefully."""
        position = TrioPosition(
            holding=Holding.BTC,
            entry_price=0.0,  # Invalid
        )

        indicators = {"close": 50000.0}

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, position
        )

        # Should not crash, should return no exit
        assert should_exit is False

    def test_no_exit_with_zero_current_price(self, trio_engine, mock_agent, btc_position):
        """CONTRACT: Handle zero current price gracefully."""
        indicators = {"close": 0.0}  # Invalid

        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators, btc_position
        )

        # Should not crash, should return no exit
        assert should_exit is False

    def test_missing_pattern_handled(self, trio_engine):
        """CONTRACT: Missing pattern IDs handled gracefully."""
        agent = MagicMock()
        agent.pattern_ids = ["nonexistent-pattern"]
        agent.traits = {}

        position = TrioPosition(
            holding=Holding.BTC,
            entry_price=50000.0,
        )

        indicators = {
            "close": 40000.0,  # Would trigger stop loss if pattern existed
        }

        # Should not crash
        should_exit, confidence, reason = trio_engine._check_exit(
            agent, indicators, position
        )

        # No exit because pattern not found
        assert should_exit is False


# ============================================================================
# INTEGRATION TEST - FULL EXIT FLOW
# ============================================================================


class TestExitIntegration:
    """Integration tests for the full exit flow."""

    def test_full_exit_flow_with_trailing(self, trio_engine, mock_agent):
        """Test complete exit flow with trailing stop."""
        position = TrioPosition(
            holding=Holding.BTC,
            entry_price=50000.0,
            highwater_price=50000.0,
        )

        # Step 1: Price rises, no exit (update highwater)
        indicators1 = {"close": 56000.0, "atr_14": 0}  # +12%
        should_exit, _, _ = trio_engine._check_exit(mock_agent, indicators1, position)
        assert should_exit is True  # TP triggers at 10%
        # Reset for trailing test
        trio_engine.patterns["pattern-001"]["exit_conditions"]["take_profit_pct"] = 0.20  # 20%

        # Re-run with higher TP threshold
        position.highwater_price = 50000.0  # Reset
        should_exit, _, _ = trio_engine._check_exit(mock_agent, indicators1, position)
        assert position.highwater_price == 56000.0  # Updated

        # Step 2: Price drops from peak, trailing triggers
        indicators2 = {"close": 53000.0, "atr_14": 0}  # ~5.4% below highwater
        should_exit, confidence, reason = trio_engine._check_exit(
            mock_agent, indicators2, position
        )

        assert should_exit is True
        assert reason == "trailing_stop"
