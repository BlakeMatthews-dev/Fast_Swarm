"""
Canonical Backtesting Windows - FROZEN TEST DATA

MASTER TEST ADMIN DECREE: These windows are IMMUTABLE.
They define the exact time periods used for regression/snapshot testing.
Changing these invalidates all golden files.

Usage:
    from Tests.Fixtures.canonical_windows import CANONICAL_WINDOWS
    window = CANONICAL_WINDOWS["btc_2023_h1"]
    start, end = window.start, window.end
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TestWindow:
    """
    Immutable backtesting window definition.

    frozen=True ensures these cannot be accidentally modified.
    """

    name: str
    start: datetime
    end: datetime
    asset: str
    timeframe: str
    description: str
    expected_candles: int  # For validation


# =============================================================================
# CANONICAL WINDOWS - DO NOT MODIFY WITHOUT UPDATING GOLDEN FILES
# =============================================================================

CANONICAL_WINDOWS: dict[str, TestWindow] = {
    # -------------------------------------------------------------------------
    # BTC Windows
    # -------------------------------------------------------------------------
    "btc_2023_h1": TestWindow(
        name="BTC 2023 H1",
        start=datetime(2023, 1, 1, 0, 0, 0),
        end=datetime(2023, 6, 30, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="Bitcoin first half 2023 - sideways accumulation then rally to 31K",
        expected_candles=4344,  # ~181 days * 24 hours
    ),
    "btc_2022_bear": TestWindow(
        name="BTC 2022 Bear",
        start=datetime(2022, 5, 1, 0, 0, 0),
        end=datetime(2022, 12, 31, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="Bitcoin bear market - Luna crash, 3AC collapse, FTX implosion",
        expected_candles=5880,  # ~245 days * 24 hours
    ),
    "btc_2021_bull": TestWindow(
        name="BTC 2021 Bull",
        start=datetime(2021, 1, 1, 0, 0, 0),
        end=datetime(2021, 4, 14, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="Bitcoin bull run - 29K to 64K ATH",
        expected_candles=2496,  # ~104 days * 24 hours
    ),
    # -------------------------------------------------------------------------
    # ETH Windows
    # -------------------------------------------------------------------------
    "eth_2022_bear": TestWindow(
        name="ETH 2022 Bear",
        start=datetime(2022, 5, 1, 0, 0, 0),
        end=datetime(2022, 12, 31, 23, 59, 59),
        asset="ETH/USDT",
        timeframe="1h",
        description="Ethereum bear market - tests drawdown handling and recovery",
        expected_candles=5880,
    ),
    "eth_merge_period": TestWindow(
        name="ETH Merge Period",
        start=datetime(2022, 8, 1, 0, 0, 0),
        end=datetime(2022, 10, 31, 23, 59, 59),
        asset="ETH/USDT",
        timeframe="1h",
        description="Ethereum merge event - high volatility regime change",
        expected_candles=2208,  # ~92 days * 24 hours
    ),
    # -------------------------------------------------------------------------
    # Multi-Asset Windows
    # -------------------------------------------------------------------------
    "multi_2024_volatile": TestWindow(
        name="Multi-Asset 2024 Volatile",
        start=datetime(2024, 1, 1, 0, 0, 0),
        end=datetime(2024, 6, 30, 23, 59, 59),
        asset="*",  # All assets
        timeframe="1h",
        description="Recent volatile period - ETF approvals, halving anticipation",
        expected_candles=4344,
    ),
    # -------------------------------------------------------------------------
    # Stress Test Windows (Short, High Volatility)
    # -------------------------------------------------------------------------
    "flash_crash_may2021": TestWindow(
        name="Flash Crash May 2021",
        start=datetime(2021, 5, 19, 0, 0, 0),
        end=datetime(2021, 5, 21, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="50% crash in 48 hours - extreme stress test",
        expected_candles=72,  # 3 days * 24 hours
    ),
    "luna_collapse": TestWindow(
        name="Luna Collapse",
        start=datetime(2022, 5, 7, 0, 0, 0),
        end=datetime(2022, 5, 13, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="UST/Luna death spiral contagion - market-wide panic",
        expected_candles=168,  # 7 days * 24 hours
    ),
    "ftx_collapse": TestWindow(
        name="FTX Collapse",
        start=datetime(2022, 11, 6, 0, 0, 0),
        end=datetime(2022, 11, 14, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1h",
        description="FTX implosion - trust crisis, exchange runs",
        expected_candles=216,  # 9 days * 24 hours
    ),
    # -------------------------------------------------------------------------
    # Daily Timeframe Windows (Long-term)
    # -------------------------------------------------------------------------
    "btc_full_cycle_daily": TestWindow(
        name="BTC Full Cycle Daily",
        start=datetime(2020, 1, 1, 0, 0, 0),
        end=datetime(2023, 12, 31, 23, 59, 59),
        asset="BTC/USDT",
        timeframe="1d",
        description="Full market cycle - COVID crash, bull run, bear market, recovery",
        expected_candles=1461,  # 4 years
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_window(name: str) -> TestWindow:
    """Get a canonical window by name."""
    if name not in CANONICAL_WINDOWS:
        available = ", ".join(CANONICAL_WINDOWS.keys())
        raise ValueError(f"Unknown window '{name}'. Available: {available}")
    return CANONICAL_WINDOWS[name]


def get_stress_windows() -> dict[str, TestWindow]:
    """Get all stress test windows (short, high volatility)."""
    stress_names = ["flash_crash_may2021", "luna_collapse", "ftx_collapse"]
    return {name: CANONICAL_WINDOWS[name] for name in stress_names}


def get_btc_windows() -> dict[str, TestWindow]:
    """Get all BTC windows."""
    return {k: v for k, v in CANONICAL_WINDOWS.items() if "btc" in k.lower()}


def get_eth_windows() -> dict[str, TestWindow]:
    """Get all ETH windows."""
    return {k: v for k, v in CANONICAL_WINDOWS.items() if "eth" in k.lower()}
