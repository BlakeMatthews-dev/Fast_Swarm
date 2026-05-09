"""
Unit tests for local_agents.backtest.windows module.

Tests cover:
- Window slicing (generate_pool, generate_windows_for_pair)
- Coverage calculation (verify_coverage, _calculate_windows_needed)
- Log / math guards (domain errors, zero division)
- Edge cases (empty data, extreme parameters)

All DB access is mocked via _sync_initialize_for_testing.
"""

import math
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from Fast_Swarm.local_agents.backtest.windows import (
    COVERAGE_TARGETS,
    PRIORITY_SYMBOLS,
    TIMEFRAMES,
    WINDOW_DURATION_DAYS,
    Window,
    _calculate_windows_needed,
    _sync_initialize_for_testing,
    generate_pool,
    get_pool_stats,
    get_windows,
    get_windows_for_symbol,
    get_windows_for_timeframe,
    verify_coverage,
)
import Fast_Swarm.local_agents.backtest.windows as windows_mod


# =============================================================================
# Helpers
# =============================================================================


def _make_data_ranges(symbols=None, timeframes=None, days=365):
    """Create synthetic data ranges for testing."""
    if symbols is None:
        symbols = ["BTC", "ETH"]
    if timeframes is None:
        timeframes = ["1h", "4h"]
    end = datetime(2025, 1, 1)
    start = end - timedelta(days=days)
    return {(sym, tf): (start, end) for sym in symbols for tf in timeframes}


def _init_pool(symbols=None, timeframes=None, days=365, seed=42):
    """Initialize the pool for testing (no DB)."""
    ranges = _make_data_ranges(symbols, timeframes, days)
    _sync_initialize_for_testing(ranges, seed=seed)


def _teardown_pool():
    """Reset module state after each test."""
    windows_mod._POOL = []
    windows_mod._DATA_RANGES = {}
    windows_mod._LAST_REFRESH = None
    windows_mod._COVERAGE_STATS = {}


@pytest.fixture(autouse=True)
def clean_pool():
    """Reset pool state before and after each test."""
    _teardown_pool()
    yield
    _teardown_pool()


# =============================================================================
# Window Slicing Tests (~8 tests)
# =============================================================================


class TestWindowSlicing:
    """Tests for window generation and pool structure."""

    def test_window_dataclass_immutable(self):
        """Window is a frozen dataclass."""
        w = Window(symbol="BTC", timeframe="1h", start_ts=1000, end_ts=2000)
        with pytest.raises(AttributeError):
            w.symbol = "ETH"

    def test_window_to_dataset(self):
        """Window.to_dataset returns correct format for engine.run()."""
        w = Window(symbol="BTC", timeframe="1h", start_ts=1000, end_ts=86400000 + 1000)
        ds = w.to_dataset()
        assert ds["assets"] == ["BTC"]
        assert ds["timeframe"] == "1h"
        assert ds["start_ts"] == 1000
        assert ds["end_ts"] == 86400000 + 1000

    def test_window_duration_days(self):
        """Window.duration_days computes correct duration."""
        one_day_ms = 1000 * 60 * 60 * 24
        w = Window(symbol="BTC", timeframe="1h", start_ts=0, end_ts=7 * one_day_ms)
        assert w.duration_days == pytest.approx(7.0)

    def test_generate_pool_creates_windows(self):
        """generate_pool creates a non-empty pool of Window objects."""
        _init_pool(symbols=["BTC"], timeframes=["1h"], days=365)
        stats = get_pool_stats()
        assert stats["initialized"] is True
        assert stats["pool_size"] > 0
        assert "BTC" in stats["symbols"]

    def test_generate_pool_includes_anchor_windows(self):
        """Pool includes anchor windows at data boundaries."""
        ranges = _make_data_ranges(["BTC"], ["1h"], 365)
        _sync_initialize_for_testing(ranges, seed=42)
        pool = windows_mod._POOL
        start_ts = int(list(ranges.values())[0][0].timestamp() * 1000)
        end_ts = int(list(ranges.values())[0][1].timestamp() * 1000)
        # There should be a window starting near the data start
        has_start_anchor = any(abs(w.start_ts - start_ts) < 86400000 for w in pool)
        assert has_start_anchor, "No anchor window near data start"

    def test_generate_pool_deterministic(self):
        """Same seed produces identical pools."""
        _init_pool(symbols=["BTC"], timeframes=["1h"], days=365, seed=42)
        pool1 = list(windows_mod._POOL)
        _teardown_pool()
        _init_pool(symbols=["BTC"], timeframes=["1h"], days=365, seed=42)
        pool2 = list(windows_mod._POOL)
        assert len(pool1) == len(pool2)
        for w1, w2 in zip(pool1, pool2):
            assert w1 == w2

    def test_generate_pool_skips_insufficient_data(self):
        """Pairs with less data than minimum window duration are skipped."""
        # 1d timeframe needs at least 60 days, give it only 10
        ranges = _make_data_ranges(["BTC"], ["1d"], days=10)
        _sync_initialize_for_testing(ranges, seed=42)
        pool = windows_mod._POOL
        btc_1d_windows = [w for w in pool if w.symbol == "BTC" and w.timeframe == "1d"]
        assert len(btc_1d_windows) == 0

    def test_get_windows_returns_requested_count(self):
        """get_windows returns at most the requested count."""
        _init_pool(symbols=["BTC", "ETH"], timeframes=["1h", "4h"], days=365)
        windows = get_windows(count=5, seed=42)
        assert len(windows) == 5

    def test_get_windows_raises_without_init(self):
        """get_windows raises RuntimeError if pool not initialized."""
        with pytest.raises(RuntimeError, match="Pool not generated"):
            get_windows(count=5)


# =============================================================================
# Coverage Calculation Tests (~5 tests)
# =============================================================================


class TestCoverageCalculation:
    """Tests for coverage and depth computation."""

    def test_calculate_windows_needed_full_coverage_single_window(self):
        """When window covers entire range, returns small number."""
        n = _calculate_windows_needed(
            data_days=30,
            avg_window_days=60,  # bigger than data
            target_coverage=0.95,
            target_depth=1.5,
        )
        assert n >= 2  # Minimum

    def test_calculate_windows_needed_zero_data_returns_zero(self):
        """Zero data days returns 0 windows needed."""
        n = _calculate_windows_needed(
            data_days=0,
            avg_window_days=30,
            target_coverage=0.95,
            target_depth=1.5,
        )
        assert n == 0

    def test_calculate_windows_needed_zero_window_returns_zero(self):
        """Zero window days returns 0 windows needed."""
        n = _calculate_windows_needed(
            data_days=365,
            avg_window_days=0,
            target_coverage=0.95,
            target_depth=1.5,
        )
        assert n == 0

    def test_verify_coverage_returns_dict(self):
        """verify_coverage returns a dict with expected keys after init."""
        _init_pool(symbols=["BTC"], timeframes=["1h"], days=365)
        result = verify_coverage(sample_points=100)
        assert "pairs_checked" in result
        assert "pairs_meeting_coverage" in result
        assert "pairs_meeting_depth" in result
        assert "priority_ok" in result

    def test_verify_coverage_empty_pool(self):
        """verify_coverage on empty pool returns error."""
        result = verify_coverage()
        assert "error" in result


# =============================================================================
# Log Guard Tests (~3 tests)
# =============================================================================


class TestLogGuards:
    """Tests for math domain safety in coverage calculations."""

    def test_log_guard_ratio_zero(self):
        """_calculate_windows_needed handles ratio <= 0 without domain error."""
        # avg_window_days negative (pathological) should not crash
        n = _calculate_windows_needed(
            data_days=365,
            avg_window_days=-1,
            target_coverage=0.95,
            target_depth=1.5,
        )
        assert n == 0  # Returns 0 for invalid input

    def test_log_guard_near_full_coverage(self):
        """Coverage target near 1.0 does not cause log(0) error."""
        # Should not raise
        n = _calculate_windows_needed(
            data_days=365,
            avg_window_days=30,
            target_coverage=0.999,
            target_depth=1.5,
        )
        assert n > 0

    def test_log_of_valid_ratio(self):
        """Normal ratio produces correct math without error."""
        n = _calculate_windows_needed(
            data_days=365,
            avg_window_days=30,
            target_coverage=0.95,
            target_depth=1.3,
        )
        assert n > 0
        # Should be reasonable for 365 days with 30-day windows
        assert n < 500


# =============================================================================
# Edge Case Tests (~4 tests)
# =============================================================================


class TestEdgeCases:
    """Tests for boundary conditions and extreme inputs."""

    def test_single_day_data(self):
        """Single day of data with 1m timeframe (min window = 7 days) produces no windows."""
        ranges = _make_data_ranges(["BTC"], ["1m"], days=1)
        _sync_initialize_for_testing(ranges, seed=42)
        pool = windows_mod._POOL
        assert len(pool) == 0

    def test_very_large_pool(self):
        """Large data range with many symbols generates a big pool without crash."""
        symbols = [f"SYM{i}" for i in range(10)]
        ranges = _make_data_ranges(symbols, ["1h"], days=500)
        _sync_initialize_for_testing(ranges, seed=42)
        stats = get_pool_stats()
        assert stats["pool_size"] > 50

    def test_get_windows_for_symbol_filters(self):
        """get_windows_for_symbol returns only windows for the requested symbol."""
        _init_pool(symbols=["BTC", "ETH", "SOL"], timeframes=["1h"], days=365)
        btc_windows = get_windows_for_symbol("BTC", count=100)
        for w in btc_windows:
            assert w.symbol == "BTC"

    def test_get_windows_for_timeframe_filters(self):
        """get_windows_for_timeframe returns only windows for the requested timeframe."""
        _init_pool(symbols=["BTC"], timeframes=["1h", "4h"], days=365)
        h1_windows = get_windows_for_timeframe("1h", count=100)
        for w in h1_windows:
            assert w.timeframe == "1h"

    def test_get_windows_for_missing_symbol_returns_empty(self):
        """get_windows_for_symbol with non-existent symbol returns empty list."""
        _init_pool(symbols=["BTC"], timeframes=["1h"], days=365)
        result = get_windows_for_symbol("DOGE", count=5)
        assert result == []

    def test_pool_stats_when_not_initialized(self):
        """get_pool_stats returns initialized=False when pool is empty."""
        stats = get_pool_stats()
        assert stats["initialized"] is False
        assert stats["pool_size"] == 0

    def test_priority_symbols_constant(self):
        """PRIORITY_SYMBOLS contains expected symbols."""
        assert "BTC" in PRIORITY_SYMBOLS
        assert "ETH" in PRIORITY_SYMBOLS
        assert "SOL" in PRIORITY_SYMBOLS

    def test_window_duration_days_mapping_complete(self):
        """All standard timeframes have duration mappings."""
        for tf in TIMEFRAMES:
            assert tf in WINDOW_DURATION_DAYS, f"Missing duration for {tf}"
            min_d, max_d = WINDOW_DURATION_DAYS[tf]
            assert min_d > 0
            assert max_d > min_d
