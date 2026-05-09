"""
Custom Hypothesis Strategies for Fast_Swarm - MASTER TEST ADMIN

Reusable strategies for property-based testing.
These generate valid, edge-case-rich test data for invariant verification.

JUST KEEP TESTING, JUST KEEP TESTING!
"""

from hypothesis import strategies as st
from hypothesis.strategies import composite

from Agents.Services.fitness_service import TradeData

# =============================================================================
# NAMED CONSTANTS (from factories.py - NO DUPLICATION)
# =============================================================================

ALL_22_TRAITS = [
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    "win_rate_preference",
    "drawdown_sensitivity",
    "momentum_vs_reversion",
    "stop_loss_tightness",
    "entry_aggression",
    "exit_aggression",
    "lookback_preference",
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    "funding_rate_sensitivity",
    "correlation_awareness",
    "patience",
    "adaptability",
    "trend_following",
    "mean_reversion",
    "breakout_preference",
    "volume_sensitivity",
]

# Trait bounds
TRAIT_MIN = 0.0
TRAIT_MAX = 1.0

# PnL bounds for realistic scenarios
REALISTIC_PNL_MIN = -50.0
REALISTIC_PNL_MAX = 100.0

# Extreme PnL for stress testing
EXTREME_PNL_MIN = -100.0
EXTREME_PNL_MAX = 1000.0

# Trade list size bounds
MIN_TRADES = 0
MAX_TRADES_NORMAL = 100
MAX_TRADES_STRESS = 10000

# Price bounds
MIN_PRICE = 0.01  # Avoid zero prices
MAX_PRICE = 1000000.0


# =============================================================================
# TRADE STRATEGIES
# =============================================================================


@composite
def trade_data(draw, min_pnl: float = REALISTIC_PNL_MIN, max_pnl: float = REALISTIC_PNL_MAX):
    """
    Generate a single valid TradeData.

    Excludes NaN and Inf by default - use trade_data_with_edge_cases for those.
    """
    pnl_pct = draw(
        st.floats(
            min_value=min_pnl,
            max_value=max_pnl,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    entry_price = draw(
        st.floats(
            min_value=MIN_PRICE,
            max_value=MAX_PRICE,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    exit_price = entry_price * (1 + pnl_pct / 100)
    size = draw(st.floats(min_value=0.001, max_value=100.0, allow_nan=False, allow_infinity=False))
    pnl = (exit_price - entry_price) * size
    is_win = pnl_pct > 0

    return TradeData(
        pnl=pnl,
        pnl_pct=pnl_pct,
        is_win=is_win,
        entry_price=entry_price,
        exit_price=exit_price,
        size=size,
    )


@composite
def trade_data_with_edge_cases(draw):
    """
    Generate TradeData that may include edge cases (NaN, Inf, extreme values).

    Use this for resilience testing.
    """
    # 90% normal, 10% edge cases
    is_edge_case = draw(st.booleans()) and draw(st.booleans())  # ~25% chance

    if is_edge_case:
        edge_type = draw(st.sampled_from(["nan", "inf", "neg_inf", "extreme", "zero"]))

        if edge_type == "nan":
            return TradeData(pnl=float("nan"), pnl_pct=float("nan"), is_win=True)
        elif edge_type == "inf":
            return TradeData(pnl=float("inf"), pnl_pct=float("inf"), is_win=True)
        elif edge_type == "neg_inf":
            return TradeData(pnl=float("-inf"), pnl_pct=float("-inf"), is_win=False)
        elif edge_type == "extreme":
            pnl_pct = draw(st.floats(min_value=EXTREME_PNL_MIN, max_value=EXTREME_PNL_MAX))
            return TradeData(pnl=pnl_pct * 100, pnl_pct=pnl_pct, is_win=pnl_pct > 0)
        else:  # zero
            return TradeData(pnl=0.0, pnl_pct=0.0, is_win=False)

    return draw(trade_data())


@composite
def trade_list(draw, min_size: int = MIN_TRADES, max_size: int = MAX_TRADES_NORMAL):
    """Generate a list of valid trades."""
    return draw(st.lists(trade_data(), min_size=min_size, max_size=max_size))


@composite
def trade_list_with_edge_cases(draw, min_size: int = MIN_TRADES, max_size: int = MAX_TRADES_NORMAL):
    """Generate a list of trades that may include edge cases."""
    return draw(st.lists(trade_data_with_edge_cases(), min_size=min_size, max_size=max_size))


@composite
def winning_trade_list(draw, min_size: int = 1, max_size: int = 50):
    """Generate a list of all-winning trades (for testing zero downside deviation)."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    return [draw(trade_data(min_pnl=0.01, max_pnl=REALISTIC_PNL_MAX)) for _ in range(count)]


@composite
def losing_trade_list(draw, min_size: int = 1, max_size: int = 50):
    """Generate a list of all-losing trades (for testing zero profit scenarios)."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    return [draw(trade_data(min_pnl=REALISTIC_PNL_MIN, max_pnl=-0.01)) for _ in range(count)]


@composite
def identical_pnl_trade_list(draw, min_size: int = 2, max_size: int = 50):
    """Generate trades with identical PnL (for testing zero variance)."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    pnl_pct = draw(st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False))

    return [TradeData(pnl=pnl_pct * 100, pnl_pct=pnl_pct, is_win=pnl_pct > 0) for _ in range(count)]


# =============================================================================
# TRAIT STRATEGIES
# =============================================================================


@composite
def valid_traits(draw) -> dict[str, float]:
    """Generate a valid 22-trait dictionary with all values in [0, 1]."""
    return {
        trait: draw(st.floats(min_value=TRAIT_MIN, max_value=TRAIT_MAX, allow_nan=False, allow_infinity=False))
        for trait in ALL_22_TRAITS
    }


@composite
def extreme_traits(draw) -> dict[str, float]:
    """Generate traits at boundaries (0.0 or 1.0)."""
    return {trait: draw(st.sampled_from([0.0, 1.0])) for trait in ALL_22_TRAITS}


@composite
def mutation_rate(draw) -> float:
    """Generate a valid mutation rate."""
    return draw(st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False))


# =============================================================================
# AGENT STRATEGIES
# =============================================================================


@composite
def agent_like(draw) -> dict:
    """Generate an agent-like dictionary for testing."""
    return {
        "agent_id": draw(st.text(min_size=8, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-")),
        "traits": draw(valid_traits()),
        "generation": draw(st.integers(min_value=1, max_value=100)),
        "assigned_patterns": [],
        "fitness_score": draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
    }


# =============================================================================
# CANDLE STRATEGIES
# =============================================================================


@composite
def ohlcv_candle(draw, base_price: float = 50000.0):
    """Generate a single OHLCV candle."""
    change_pct = draw(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))

    open_price = base_price
    close_price = base_price * (1 + change_pct / 100)
    high_price = max(open_price, close_price) * (1 + abs(change_pct) * 0.002)
    low_price = min(open_price, close_price) * (1 - abs(change_pct) * 0.002)
    volume = draw(st.floats(min_value=100, max_value=100000, allow_nan=False, allow_infinity=False))

    return {
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


@composite
def candle_sequence(draw, length: int = 100):
    """Generate a realistic OHLCV candle sequence."""
    base_price = draw(st.floats(min_value=100, max_value=100000, allow_nan=False, allow_infinity=False))
    base_timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC

    candles = []
    price = base_price

    for i in range(length):
        change_pct = draw(st.floats(min_value=-5, max_value=5, allow_nan=False, allow_infinity=False))
        open_price = price
        close_price = price * (1 + change_pct / 100)
        high = max(open_price, close_price) * 1.01
        low = min(open_price, close_price) * 0.99
        volume = draw(st.floats(min_value=100, max_value=10000, allow_nan=False, allow_infinity=False))

        candles.append(
            {
                "timestamp": base_timestamp + i * 3600000,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": volume,
            }
        )
        price = close_price

    return candles


# =============================================================================
# EV AND MULTIPLIER STRATEGIES
# =============================================================================


@composite
def ev_value(draw) -> float:
    """Generate an EV value for testing multiplier."""
    return draw(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))


@composite
def fitness_score(draw) -> float:
    """Generate a fitness score for tier testing."""
    return draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))


# =============================================================================
# STRESS TEST STRATEGIES
# =============================================================================


@composite
def large_trade_list(draw, size: int = MAX_TRADES_STRESS):
    """Generate a large trade list for stress testing."""
    return draw(st.lists(trade_data(), min_size=size, max_size=size))


@composite
def mixed_edge_case_trades(draw, size: int = 100):
    """
    Generate a mix of normal and edge case trades.

    Good for fuzzing the fitness calculation.
    """
    trades = []
    for _ in range(size):
        trade = draw(trade_data_with_edge_cases())
        trades.append(trade)
    return trades
