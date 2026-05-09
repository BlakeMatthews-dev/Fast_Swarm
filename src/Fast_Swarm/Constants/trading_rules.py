"""
Trading Rules - Named Constants for Trading Operations

MASTER TEST ADMIN DECREE: No magic numbers in production code.
All trading parameters must be named, documented, and sourced from here.
"""

# =============================================================================
# POSITION SIZING
# =============================================================================

DEFAULT_POSITION_SIZE = 0.1
"""Default position size as fraction of capital (10%)."""

MIN_POSITION_SIZE = 0.01
"""Minimum position size (1%)."""

MAX_POSITION_SIZE = 1.0
"""Maximum position size (100% - full capital)."""


# =============================================================================
# TRADING COSTS (by Tier)
# =============================================================================

# Costs are in basis points (bps) per side
# Total round-trip cost = 2 * (maker_fee + taker_fee + slippage)

TRADING_COSTS = {
    "tier_1": {  # BTC, ETH - most liquid
        "maker_fee_bps": 1.0,
        "taker_fee_bps": 2.0,
        "slippage_bps": 10.0,
        "description": "Major pairs (BTC, ETH) - highest liquidity",
    },
    "tier_2": {  # Top 20 alts
        "maker_fee_bps": 2.0,
        "taker_fee_bps": 4.0,
        "slippage_bps": 20.0,
        "description": "Major alts (SOL, AVAX, etc.) - good liquidity",
    },
    "tier_3": {  # Mid-cap alts
        "maker_fee_bps": 3.0,
        "taker_fee_bps": 6.0,
        "slippage_bps": 50.0,
        "description": "Mid-cap alts - moderate liquidity",
    },
    "tier_4": {  # Small caps, memes
        "maker_fee_bps": 5.0,
        "taker_fee_bps": 10.0,
        "slippage_bps": 100.0,
        "description": "Small caps, memes - low liquidity",
    },
}

DEFAULT_COST_TIER = "tier_2"
"""Default cost tier when asset tier is unknown."""


def get_round_trip_cost_bps(tier: str = DEFAULT_COST_TIER) -> float:
    """Calculate total round-trip trading cost in basis points."""
    costs = TRADING_COSTS.get(tier, TRADING_COSTS[DEFAULT_COST_TIER])
    one_side = costs["maker_fee_bps"] + costs["slippage_bps"]
    return 2 * one_side  # Round trip


# =============================================================================
# FUNDING RATES
# =============================================================================

FUNDING_RATE_INTERVAL_HOURS = 8
"""Funding rate payment interval (every 8 hours on most exchanges)."""

FUNDING_RATE_DEFAULT_BPS = 1.0
"""Default funding rate in basis points (0.01% per interval)."""

FUNDING_RATE_EXTREME_BPS = 30.0
"""Extreme funding rate threshold (0.3% - market stress)."""


# =============================================================================
# LIQUIDATION
# =============================================================================

LIQUIDATION_THRESHOLD_LEVERAGE = 20.0
"""Leverage threshold where liquidation risk becomes significant."""

MAINTENANCE_MARGIN_PCT = 0.5
"""Maintenance margin requirement as percentage."""


# =============================================================================
# PRICE BOUNDS
# =============================================================================

MIN_PRICE = 0.00000001
"""Minimum valid price (prevents division by zero)."""

MAX_PRICE = 1_000_000_000.0
"""Maximum valid price (sanity check)."""


# =============================================================================
# PNL BOUNDS
# =============================================================================

PNL_PCT_REALISTIC_MIN = -50.0
"""Realistic minimum PnL percentage for a single trade."""

PNL_PCT_REALISTIC_MAX = 100.0
"""Realistic maximum PnL percentage for a single trade."""

PNL_PCT_EXTREME_MIN = -100.0
"""Extreme minimum PnL (complete loss - liquidation)."""

PNL_PCT_EXTREME_MAX = 1000.0
"""Extreme maximum PnL (10x - rare but possible)."""


# =============================================================================
# TIMEFRAMES
# =============================================================================

TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "6h": 21600,
    "1d": 86400,
}
"""Timeframe to seconds mapping."""

DEFAULT_TIMEFRAME = "1h"
"""Default backtesting timeframe."""


# =============================================================================
# MARKET CONDITIONS
# =============================================================================

SPREAD_NORMAL_BPS = 5.0
"""Normal bid-ask spread in basis points."""

SPREAD_STRESSED_BPS = 50.0
"""Stressed market bid-ask spread (10x normal)."""

SPREAD_CRISIS_BPS = 500.0
"""Crisis market bid-ask spread (100x normal)."""


# =============================================================================
# ASSET TIERS
# =============================================================================

TIER_1_ASSETS = ["BTC", "ETH"]
"""Tier 1 assets - highest liquidity."""

TIER_2_ASSETS = ["SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "MATIC", "LINK"]
"""Tier 2 assets - major alts."""


def get_asset_tier(symbol: str) -> str:
    """Get trading cost tier for an asset."""
    base = symbol.replace("/USDT", "").replace("/USD", "").upper()
    if base in TIER_1_ASSETS:
        return "tier_1"
    elif base in TIER_2_ASSETS:
        return "tier_2"
    else:
        return "tier_3"
