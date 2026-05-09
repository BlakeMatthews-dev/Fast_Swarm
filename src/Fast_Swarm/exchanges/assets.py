"""
Asset Universe + Fee Modeling + Market Hours.

Defines the Bitcoin ecosystem assets tradeable across exchanges,
fee structures per exchange/asset class, and market hours.
"""

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import AssetClass


BITCOIN_ECOSYSTEM = {
    "crypto": ["BTC", "ETH", "SOL"],
    "btc_etf": ["IBIT", "FBTC", "GBTC", "ARKB", "BITB"],
    "btc_treasury": ["MSTR", "COIN", "MARA", "RIOT", "CLSK", "HUT", "BITF"],
    "crypto_etf": ["BITO", "ETHE"],
    "futures": ["BTC_FUT", "ETH_FUT"],
}

# Fee structure per exchange per asset class (in basis points)
EXCHANGE_FEES = {
    "crypto.com": {"crypto": {"fee_bps": 10, "slippage_bps": 2, "spread_bps": 3}},
    "alpaca": {
        "crypto": {"fee_bps": 15, "slippage_bps": 2, "spread_bps": 5},
        "equity": {"fee_bps": 0, "slippage_bps": 1, "spread_bps": 2},
        "etf": {"fee_bps": 0, "slippage_bps": 1, "spread_bps": 1},
    },
    "ibkr": {
        "equity": {"fee_bps": 0, "slippage_bps": 1, "spread_bps": 1},
        "etf": {"fee_bps": 0, "slippage_bps": 0.5, "spread_bps": 1},
        "future": {"fee_bps": 5, "slippage_bps": 1, "spread_bps": 2},
    },
}

# Market hours per asset class
MARKET_HOURS = {
    "crypto": {"open": "00:00", "close": "23:59", "timezone": "UTC", "days": [0, 1, 2, 3, 4, 5, 6]},
    "equity": {"open": "04:00", "close": "20:00", "timezone": "US/Eastern", "days": [0, 1, 2, 3, 4]},
    "future": {"open": "18:00", "close": "17:00", "timezone": "US/Eastern", "days": [0, 1, 2, 3, 4]},
}

# Which exchanges support which asset classes
EXCHANGE_CAPABILITIES = {
    "crypto.com": [AssetClass.CRYPTO],
    "alpaca": [AssetClass.CRYPTO, AssetClass.EQUITY, AssetClass.ETF],
    "ibkr": [AssetClass.EQUITY, AssetClass.ETF, AssetClass.FUTURE, AssetClass.CRYPTO],
}


def get_total_fee_bps(exchange: str, asset_class: str) -> float:
    """Get total transaction cost in basis points for an exchange + asset class."""
    fees = EXCHANGE_FEES.get(exchange, {}).get(asset_class, {})
    return fees.get("fee_bps", 0) + fees.get("slippage_bps", 0) + fees.get("spread_bps", 0)
