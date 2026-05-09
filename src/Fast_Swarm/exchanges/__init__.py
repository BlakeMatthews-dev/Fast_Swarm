"""Exchange WebSocket clients for Fast_Swarm.

Provides normalized WebSocket clients for multiple trading exchanges:
- Binance (spot & futures)
- Coinbase
- Crypto.com (spot & perpetuals)
- Hyperliquid (perpetuals)
- dYdX (perpetuals)

All clients normalize data into common types (NormalizedTrade, NormalizedOrderBook, etc.)
for consistent handling across the platform.
"""

from .base_ws import (
    BaseWebSocketClient,
    BookTickerData,
    ConnectionState,
    KlineData,
    MarkPriceData,
    NormalizedOrderBook,
    NormalizedTrade,
)
from .binance_ws import BinanceWebSocket
from .coinbase_ws import CoinbaseWebSocket
from .cryptocom_ws import CryptoComWebSocket
from .dydx_ws import DydxWebSocket
from .dydx_ws import FundingData as DydxFundingData
from .dydx_ws import OpenInterestData as DydxOpenInterestData
from .hyperliquid_ws import FundingData as HLFundingData
from .hyperliquid_ws import HyperliquidWebSocket
from .hyperliquid_ws import OpenInterestData as HLOpenInterestData

__all__ = [
    # Base classes and types
    "BaseWebSocketClient",
    "NormalizedTrade",
    "NormalizedOrderBook",
    "MarkPriceData",
    "BookTickerData",
    "KlineData",
    "ConnectionState",
    # Exchange implementations
    "BinanceWebSocket",
    "CoinbaseWebSocket",
    "CryptoComWebSocket",
    "HyperliquidWebSocket",
    "DydxWebSocket",
    # Funding/OI data types
    "HLFundingData",
    "HLOpenInterestData",
    "DydxFundingData",
    "DydxOpenInterestData",
]
