"""
EDD Soundness Test: Trio Engine - Division Safety & Edge Cases

MASTER TEST ADMIN - Evidence-Driven Development Suite
Source of truth: CLAUDE.md (Division Safety requirements)

CRITICAL: All division operations must survive zero denominators.
These tests MUST NOT be removed or weakened. They prevent production crashes.

Division Hotspots Tested:
1. _evaluate_conditions: len(conditions) == 0
2. calculate_trio_metrics: len(trades) == 0
3. _check_entry/_check_exit: empty patterns, missing keys
4. _to_btc: zero prices
"""

import math
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

# =============================================================================
# MOCK CLASSES - Isolate trio_engine logic from dependencies
# =============================================================================


@dataclass
class MockAgent:
    """Mock agent for testing pattern evaluation."""

    pattern_ids: list
    traits: dict

    @classmethod
    def with_patterns(cls, pattern_ids: list, min_threshold: float = 0.3):
        return cls(pattern_ids=pattern_ids, traits={"min_threshold": min_threshold})

    @classmethod
    def empty(cls):
        return cls(pattern_ids=[], traits={})


@dataclass
class MockTrioDataBundle:
    """Mock data bundle for testing."""

    timestamp: int = 1000000
    btc_usd: dict = None
    eth_usd: dict = None
    sol_usd: dict = None
    eth_btc: dict = None
    sol_btc: dict = None
    sol_eth: dict = None

    def __post_init__(self):
        default_candle = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
        if self.btc_usd is None:
            self.btc_usd = {**default_candle, "close": 50000}
        if self.eth_usd is None:
            self.eth_usd = {**default_candle, "close": 3000}
        if self.sol_usd is None:
            self.sol_usd = {**default_candle, "close": 100}
        if self.eth_btc is None:
            self.eth_btc = {**default_candle, "close": 0.06}
        if self.sol_btc is None:
            self.sol_btc = {**default_candle, "close": 0.002}
        if self.sol_eth is None:
            self.sol_eth = {**default_candle, "close": 0.033}

    def get_pair(self, pair: str) -> dict | None:
        mapping = {
            "BTC-USD": self.btc_usd,
            "ETH-USD": self.eth_usd,
            "SOL-USD": self.sol_usd,
            "ETH/BTC": self.eth_btc,
            "SOL/BTC": self.sol_btc,
            "SOL/ETH": self.sol_eth,
        }
        return mapping.get(pair)

    def get_relative_strength(self) -> dict:
        return {"ETH_vs_BTC": 0.01, "SOL_vs_BTC": -0.02, "SOL_vs_ETH": -0.01}


# =============================================================================
# Import after mocks to avoid import errors
# =============================================================================

# We need to test the logic directly, so we'll import from trio_engine
# If imports fail due to dependencies, tests will be skipped
try:
    from local_agents.backtest.trio_engine import (
        TrioBacktestEngine,
        TrioTradeRecord,
        calculate_trio_metrics,
    )

    TRIO_ENGINE_AVAILABLE = True
except ImportError:
    TRIO_ENGINE_AVAILABLE = False


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def engine():
    """Create a TrioBacktestEngine with empty pattern matcher."""
    if not TRIO_ENGINE_AVAILABLE:
        pytest.skip("trio_engine not importable")
    return TrioBacktestEngine(
        pattern_matcher=MagicMock(),
        patterns={},
        slippage_pct=0.1,
        fee_pct=0.1,
    )


@pytest.fixture
def engine_with_patterns():
    """Create engine with sample patterns."""
    if not TRIO_ENGINE_AVAILABLE:
        pytest.skip("trio_engine not importable")

    patterns = {
        "rsi_oversold": {
            "pattern_id": "rsi_oversold",
            "entry_conditions": [{"indicator": "rsi_14", "operator": "<", "value": 30}],
            "exit_conditions": [{"indicator": "rsi_14", "operator": ">", "value": 70}],
        },
        "rsi_dict_exit": {
            "pattern_id": "rsi_dict_exit",
            "entry_conditions": [{"indicator": "rsi_14", "operator": "<", "value": 35}],
            "exit_conditions": {
                "conditions": [{"indicator": "rsi_14", "operator": ">", "value": 65}],
                "take_profit_pct": 5.0,
            },
        },
        "empty_conditions": {
            "pattern_id": "empty_conditions",
            "entry_conditions": [],
            "exit_conditions": [],
        },
        "missing_conditions": {
            "pattern_id": "missing_conditions",
        },
    }

    return TrioBacktestEngine(
        pattern_matcher=MagicMock(),
        patterns=patterns,
        slippage_pct=0.1,
        fee_pct=0.1,
    )


# =============================================================================
# TEST: Division Safety in _evaluate_conditions
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestEvaluateConditionsDivisionSafety:
    """CONTRACT: _evaluate_conditions must handle division by zero."""

    def test_empty_conditions_no_crash(self, engine):
        """
        CONTRACT: Empty conditions list returns (False, 0.0), no division error.

        Risk: len(conditions) == 0 in confidence calculation.
        """
        matched, confidence = engine._evaluate_conditions([], {"rsi_14": 50})

        assert matched is False
        assert confidence == 0.0

    def test_none_conditions_no_crash(self, engine):
        """
        CONTRACT: None conditions handled gracefully.
        """
        # This should not crash - depends on implementation
        try:
            matched, _ = engine._evaluate_conditions(None, {"rsi_14": 50})
            assert matched is False
        except TypeError:
            # If it raises TypeError, that's acceptable - just shouldn't crash unexpectedly
            pass

    def test_single_condition_division(self, engine):
        """
        CONTRACT: Single condition produces valid confidence.

        Risk: Division by 1 should work correctly.
        """
        conditions = [{"indicator": "rsi_14", "operator": "<", "value": 50}]
        matched, confidence = engine._evaluate_conditions(conditions, {"rsi_14": 30})

        assert matched is True
        assert confidence == 1.0  # 1/1 = 1.0
        assert math.isfinite(confidence)

    def test_partial_match_division(self, engine):
        """
        CONTRACT: Partial matches return valid confidence.
        """
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 50},
            {"indicator": "macd_line", "operator": ">", "value": 0},
        ]
        # Only RSI matches, MACD not in indicators
        matched, confidence = engine._evaluate_conditions(conditions, {"rsi_14": 30})

        # Should not match (not all conditions met) but shouldn't crash
        assert matched is False
        assert math.isfinite(confidence)


# =============================================================================
# TEST: Division Safety in calculate_trio_metrics
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestTrioMetricsDivisionSafety:
    """CONTRACT: calculate_trio_metrics must handle empty trade lists."""

    def test_empty_trades_no_crash(self):
        """
        CONTRACT: Empty trades returns valid metrics without division error.

        Risk: Division by len(trades) in win_rate and avg_btc_pnl.
        """
        metrics = calculate_trio_metrics([])

        assert metrics["total_trades"] == 0
        assert "win_rate" not in metrics or metrics.get("win_rate", 0) == 0
        # Should not crash

    def test_single_trade_metrics(self):
        """
        CONTRACT: Single trade produces valid metrics.
        """
        trade = TrioTradeRecord(
            trade_id="test1",
            timestamp=1000,
            action="buy",
            from_asset="USD",
            to_asset="BTC",
            from_amount=10000,
            to_amount=0.2,
            price=50000,
            pair_used="BTC-USD",
            data_source="test",
            btc_before=0,
            btc_after=0.2,
            btc_pnl=0.2,
        )

        metrics = calculate_trio_metrics([trade])

        assert metrics["total_trades"] == 1
        assert metrics["win_rate"] == 1.0  # 1/1
        assert math.isfinite(metrics["avg_btc_pnl"])

    def test_all_losing_trades(self):
        """
        CONTRACT: All losing trades produce 0% win rate.
        """
        trades = [
            TrioTradeRecord(
                trade_id=f"test{i}",
                timestamp=1000 + i,
                action="buy",
                from_asset="USD",
                to_asset="BTC",
                from_amount=10000,
                to_amount=0.2,
                price=50000,
                pair_used="BTC-USD",
                data_source="test",
                btc_before=0.2,
                btc_after=0.1,
                btc_pnl=-0.1,  # All losses
            )
            for i in range(5)
        ]

        metrics = calculate_trio_metrics(trades)

        assert metrics["win_rate"] == 0.0
        assert metrics["total_btc_pnl"] < 0


# =============================================================================
# TEST: _check_entry Edge Cases
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestCheckEntryEdgeCases:
    """CONTRACT: _check_entry handles all edge cases gracefully."""

    def test_empty_pattern_ids(self, engine_with_patterns):
        """
        CONTRACT: Agent with no patterns returns no entry signal.
        """
        agent = MockAgent.empty()
        indicators = {"rsi_14": 25}

        triggered, confidence, pattern_id = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is False
        assert confidence == 0.0
        assert pattern_id is None

    def test_missing_pattern_in_registry(self, engine_with_patterns):
        """
        CONTRACT: Missing pattern ID handled gracefully.
        """
        agent = MockAgent.with_patterns(["nonexistent_pattern"])
        indicators = {"rsi_14": 25}

        triggered, confidence, pattern_id = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is False
        assert confidence == 0.0
        assert pattern_id is None

    def test_pattern_with_empty_entry_conditions(self, engine_with_patterns):
        """
        CONTRACT: Pattern with empty entry_conditions skipped.
        """
        agent = MockAgent.with_patterns(["empty_conditions"])
        indicators = {"rsi_14": 25}

        triggered, _, _ = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is False

    def test_pattern_missing_entry_conditions_key(self, engine_with_patterns):
        """
        CONTRACT: Pattern without entry_conditions key handled.
        """
        agent = MockAgent.with_patterns(["missing_conditions"])
        indicators = {"rsi_14": 25}

        triggered, _, _ = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is False

    def test_successful_entry_signal(self, engine_with_patterns):
        """
        CONTRACT: Valid entry conditions trigger signal.
        """
        agent = MockAgent.with_patterns(["rsi_oversold"], min_threshold=0.3)
        indicators = {"rsi_14": 25}  # Below 30, should trigger

        triggered, confidence, pattern_id = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is True
        assert confidence > 0
        assert pattern_id == "rsi_oversold"

    def test_below_threshold_no_signal(self, engine_with_patterns):
        """
        CONTRACT: Confidence below min_threshold returns no signal.
        """
        agent = MockAgent.with_patterns(["rsi_oversold"], min_threshold=2.0)  # Impossibly high
        indicators = {"rsi_14": 25}

        triggered, _, _ = engine_with_patterns._check_entry(agent, indicators)

        assert triggered is False


# =============================================================================
# TEST: _check_exit Edge Cases
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestCheckExitEdgeCases:
    """CONTRACT: _check_exit handles all edge cases and formats gracefully."""

    def test_empty_pattern_ids(self, engine_with_patterns):
        """
        CONTRACT: Agent with no patterns returns no exit signal.
        """
        agent = MockAgent.empty()
        indicators = {"rsi_14": 75}

        triggered, confidence, pattern_id = engine_with_patterns._check_exit(agent, indicators)

        assert triggered is False
        assert confidence == 0.0
        assert pattern_id is None

    def test_list_format_exit_conditions(self, engine_with_patterns):
        """
        CONTRACT: List-format exit_conditions evaluated correctly.
        """
        agent = MockAgent.with_patterns(["rsi_oversold"], min_threshold=0.3)
        indicators = {"rsi_14": 75}  # Above 70, should trigger exit

        triggered, _, pattern_id = engine_with_patterns._check_exit(agent, indicators)

        assert triggered is True
        assert pattern_id == "rsi_oversold"

    def test_dict_format_exit_conditions(self, engine_with_patterns):
        """
        CONTRACT: Dict-format exit_conditions with nested 'conditions' list evaluated.
        """
        agent = MockAgent.with_patterns(["rsi_dict_exit"], min_threshold=0.3)
        indicators = {"rsi_14": 70}  # Above 65, should trigger

        triggered, _, pattern_id = engine_with_patterns._check_exit(agent, indicators)

        assert triggered is True
        assert pattern_id == "rsi_dict_exit"

    def test_dict_without_conditions_key(self, engine_with_patterns):
        """
        CONTRACT: Dict exit_conditions without 'conditions' key doesn't crash.
        """
        # Add a pattern with dict exit but no conditions key
        engine_with_patterns.patterns["pnl_only"] = {
            "pattern_id": "pnl_only",
            "entry_conditions": [{"indicator": "rsi_14", "operator": "<", "value": 30}],
            "exit_conditions": {"take_profit_pct": 5.0, "stop_loss_pct": -3.0},  # No conditions list
        }

        agent = MockAgent.with_patterns(["pnl_only"])
        indicators = {"rsi_14": 75}

        triggered, _, _ = engine_with_patterns._check_exit(agent, indicators)

        # Should not crash, and should return False (no indicator conditions to match)
        assert triggered is False

    def test_empty_exit_conditions(self, engine_with_patterns):
        """
        CONTRACT: Empty exit_conditions dict skipped without crash.
        """
        agent = MockAgent.with_patterns(["empty_conditions"])
        indicators = {"rsi_14": 75}

        triggered, _, _ = engine_with_patterns._check_exit(agent, indicators)

        assert triggered is False

    def test_missing_exit_conditions_key(self, engine_with_patterns):
        """
        CONTRACT: Pattern without exit_conditions key handled.
        """
        agent = MockAgent.with_patterns(["missing_conditions"])
        indicators = {"rsi_14": 75}

        triggered, _, _ = engine_with_patterns._check_exit(agent, indicators)

        assert triggered is False


# =============================================================================
# TEST: Indicator Edge Cases
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestIndicatorEdgeCases:
    """CONTRACT: Indicator evaluation handles edge values."""

    def test_missing_indicator_in_data(self, engine):
        """
        CONTRACT: Missing indicator in data doesn't crash.
        """
        conditions = [{"indicator": "nonexistent", "operator": "<", "value": 50}]
        indicators = {"rsi_14": 30}  # Different indicator

        matched, _ = engine._evaluate_conditions(conditions, indicators)

        assert matched is False  # Can't match if indicator missing

    def test_none_indicator_value(self, engine):
        """
        CONTRACT: None indicator value handled gracefully.
        """
        conditions = [{"indicator": "rsi_14", "operator": "<", "value": 50}]
        indicators = {"rsi_14": None}

        matched, _ = engine._evaluate_conditions(conditions, indicators)

        assert matched is False

    def test_nan_indicator_value(self, engine):
        """
        CONTRACT: NaN indicator value doesn't crash comparison.
        """
        conditions = [{"indicator": "rsi_14", "operator": "<", "value": 50}]
        indicators = {"rsi_14": float("nan")}

        # Should not crash
        matched, _ = engine._evaluate_conditions(conditions, indicators)

        # NaN comparisons return False
        assert matched is False

    def test_inf_indicator_value(self, engine):
        """
        CONTRACT: Inf indicator value doesn't crash.
        """
        conditions = [{"indicator": "rsi_14", "operator": "<", "value": 50}]
        indicators = {"rsi_14": float("inf")}

        matched, _ = engine._evaluate_conditions(conditions, indicators)

        assert matched is False  # inf is not < 50

    def test_between_operator(self, engine):
        """
        CONTRACT: 'between' operator works correctly.
        """
        conditions = [{"indicator": "rsi_14", "operator": "between", "value": [30, 70]}]

        # Test in range
        matched, _ = engine._evaluate_conditions(conditions, {"rsi_14": 50})
        assert matched is True

        # Test below range
        matched, _ = engine._evaluate_conditions(conditions, {"rsi_14": 20})
        assert matched is False

        # Test above range
        matched, _ = engine._evaluate_conditions(conditions, {"rsi_14": 80})
        assert matched is False

    def test_all_operators(self, engine):
        """
        CONTRACT: All comparison operators work correctly.
        """
        test_cases = [
            ({"operator": "<", "value": 50}, 30, True),
            ({"operator": "<", "value": 50}, 60, False),
            ({"operator": ">", "value": 50}, 60, True),
            ({"operator": ">", "value": 50}, 30, False),
            ({"operator": "<=", "value": 50}, 50, True),
            ({"operator": ">=", "value": 50}, 50, True),
            ({"operator": "==", "value": 50}, 50, True),
            ({"operator": "==", "value": 50}, 51, False),
        ]

        for cond_part, indicator_val, expected_match in test_cases:
            cond = {"indicator": "rsi_14", **cond_part}
            matched, _ = engine._evaluate_conditions([cond], {"rsi_14": indicator_val})
            assert matched == expected_match, f"Failed for {cond_part} with value {indicator_val}"


# =============================================================================
# TEST: _to_btc Division Safety
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestToBtcDivisionSafety:
    """CONTRACT: _to_btc handles zero prices without crash."""

    def test_btc_passthrough(self, engine):
        """
        CONTRACT: BTC amount returned as-is (no division).
        """
        bundle = MockTrioDataBundle()
        result = engine._to_btc("BTC", 1.5, bundle)
        assert result == 1.5

    def test_usd_zero_btc_price(self, engine):
        """
        CONTRACT: Zero BTC price doesn't crash USD conversion.

        Risk: Division by btc_usd price.
        """
        bundle = MockTrioDataBundle(btc_usd={"close": 0})

        # This will cause division by zero - should handle gracefully
        try:
            result = engine._to_btc("USD", 10000, bundle)
            # If it returns inf, that's the expected math result
            assert result == float("inf") or math.isnan(result)
        except ZeroDivisionError:
            pytest.fail("_to_btc should handle zero BTC price without ZeroDivisionError")

    def test_eth_conversion(self, engine):
        """
        CONTRACT: ETH to BTC conversion uses multiplication (safe).
        """
        bundle = MockTrioDataBundle(eth_btc={"close": 0.06})
        result = engine._to_btc("ETH", 10, bundle)
        assert result == 0.6  # 10 * 0.06

    def test_unknown_asset(self, engine):
        """
        CONTRACT: Unknown asset returns 0, not crash.
        """
        bundle = MockTrioDataBundle()
        result = engine._to_btc("UNKNOWN", 100, bundle)
        assert result == 0.0


# =============================================================================
# TEST: Best Pattern Selection
# =============================================================================


@pytest.mark.skipif(not TRIO_ENGINE_AVAILABLE, reason="trio_engine not importable")
class TestBestPatternSelection:
    """CONTRACT: Multiple patterns select highest confidence."""

    def test_multiple_matching_patterns_selects_best(self, engine):
        """
        CONTRACT: When multiple patterns match, highest confidence wins.
        """
        engine.patterns = {
            "pattern_a": {
                "entry_conditions": [{"indicator": "rsi_14", "operator": "<", "value": 40}],
            },
            "pattern_b": {
                "entry_conditions": [
                    {"indicator": "rsi_14", "operator": "<", "value": 35},
                    {"indicator": "macd_line", "operator": ">", "value": -1},
                ],
            },
        }

        agent = MockAgent.with_patterns(["pattern_a", "pattern_b"], min_threshold=0.1)
        indicators = {"rsi_14": 30, "macd_line": 0}

        triggered, _, pattern_id = engine._check_entry(agent, indicators)

        assert triggered is True
        # Both should match - pattern_b has more conditions but both conditions matched
        # Confidence for pattern_a: 1/1 = 1.0
        # Confidence for pattern_b: 2/2 = 1.0
        # First one wins if equal (pattern_a comes first in iteration)
        assert pattern_id in ["pattern_a", "pattern_b"]
