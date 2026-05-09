"""
Hivemind Data Feed Service.

Connects hiveminds to live market data streams for real-time trading.

Responsibilities:
- Subscribe to StreamManagerService for live data
- Compute indicators on incoming candles
- Route data to trios for voting decisions
- Track orderbook state for execution decisions
- Maintain candle history for indicator computation

Data Flow:
    StreamManager -> HivemindDataFeed -> TrioVotingService -> OrderExecutionService
"""

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Import data structures from WebSocket layer
from Fast_Swarm.exchanges.base_ws import (
    BookTickerData,
    KlineData,
    NormalizedOrderBook,
    NormalizedTrade,
)

# Import motion derivative service for Bear Protection
from Fast_Swarm.Infrastructure.Services.motion_derivative_service import (
    compute_motion_derivatives_from_history,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class LiveCandle:
    """A candle being built from live ticks."""

    symbol: str
    exchange: str
    timeframe: str
    timestamp: int  # Candle open time (unix seconds)

    open: float
    high: float
    low: float
    close: float
    volume: float

    trade_count: int = 0
    buy_volume: float = 0.0
    sell_volume: float = 0.0

    is_closed: bool = False

    def update(self, price: float, size: float, side: str):
        """Update candle with new tick."""
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size
        self.trade_count += 1
        if side == "buy":
            self.buy_volume += size
        else:
            self.sell_volume += size

    def to_dict(self) -> dict:
        """Convert to dict for indicator computation."""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
        }


@dataclass
class SymbolState:
    """Complete market state for a symbol."""

    symbol: str
    exchange: str

    # Current prices
    last_price: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread_bps: float = 0.0

    # Orderbook (top 10 levels)
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    orderbook_imbalance: float = 0.0

    # Candle history (for indicator computation)
    candle_history: deque = field(default_factory=lambda: deque(maxlen=500))
    current_candle: LiveCandle | None = None

    # Computed indicators (updated on each candle close)
    indicators: dict[str, float] = field(default_factory=dict)

    # Timestamps
    last_trade_time: int = 0
    last_orderbook_time: int = 0
    last_indicator_update: int = 0


@dataclass
class HivemindDataSnapshot:
    """
    Snapshot of all data needed for a hivemind voting decision.

    This is passed to the trio voting service when a candle closes.
    """

    symbol: str
    exchange: str
    timestamp: int

    # Price data
    candle: dict  # Current closed candle
    indicators: dict[str, float]  # All computed indicators

    # Orderbook data
    best_bid: float
    best_ask: float
    spread_bps: float
    orderbook_imbalance: float

    # Recent history context
    recent_closes: list[float]  # Last 20 closes for context


# =============================================================================
# Indicator Computation
# =============================================================================


def compute_indicators(candles: list[dict]) -> dict[str, float]:
    """
    Compute technical indicators from candle history.

    Uses simple implementations for speed. For production, consider
    using pandas-ta or similar library with pre-computed rolling windows.

    Args:
        candles: List of candle dicts with OHLCV data

    Returns:
        Dict of indicator_name -> value
    """
    if len(candles) < 2:
        return {}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    indicators = {}

    # Price
    indicators["close"] = closes[-1]
    indicators["open"] = candles[-1]["open"]
    indicators["high"] = candles[-1]["high"]
    indicators["low"] = candles[-1]["low"]
    indicators["volume"] = volumes[-1]

    # Simple Moving Averages
    if len(closes) >= 20:
        indicators["sma_20"] = sum(closes[-20:]) / 20
    if len(closes) >= 50:
        indicators["sma_50"] = sum(closes[-50:]) / 50
    if len(closes) >= 200:
        indicators["sma_200"] = sum(closes[-200:]) / 200

    # Exponential Moving Averages (simplified)
    if len(closes) >= 12:
        indicators["ema_12"] = _ema(closes, 12)
    if len(closes) >= 26:
        indicators["ema_26"] = _ema(closes, 26)

    # MACD
    if len(closes) >= 26:
        ema_12 = _ema(closes, 12)
        ema_26 = _ema(closes, 26)
        macd_line = ema_12 - ema_26
        indicators["macd"] = macd_line
        indicators["macd_line"] = macd_line
        # Signal line would need 9-period EMA of MACD history

    # RSI
    if len(closes) >= 15:
        indicators["rsi_14"] = _rsi(closes, 14)
        indicators["rsi"] = indicators["rsi_14"]

    # Bollinger Bands
    if len(closes) >= 20:
        sma = indicators["sma_20"]
        std = _std(closes[-20:])
        indicators["bb_upper"] = sma + 2 * std
        indicators["bb_lower"] = sma - 2 * std
        indicators["bb_middle"] = sma
        if std > 0:
            indicators["bb_width"] = (indicators["bb_upper"] - indicators["bb_lower"]) / sma * 100

    # ATR (Average True Range)
    if len(candles) >= 15:
        indicators["atr_14"] = _atr(candles, 14)
        indicators["atr"] = indicators["atr_14"]

    # Volume SMA
    if len(volumes) >= 20:
        indicators["volume_sma_20"] = sum(volumes[-20:]) / 20
        indicators["volume_ratio"] = volumes[-1] / indicators["volume_sma_20"] if indicators["volume_sma_20"] > 0 else 1.0

    # Price change
    if len(closes) >= 2:
        indicators["price_change_pct"] = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0

    # Higher timeframe context (approx)
    if len(closes) >= 60:
        indicators["close_1h_ago"] = closes[-60]
        indicators["change_1h_pct"] = (closes[-1] - closes[-60]) / closes[-60] * 100 if closes[-60] > 0 else 0

    if len(closes) >= 240:
        indicators["close_4h_ago"] = closes[-240]
        indicators["change_4h_pct"] = (closes[-1] - closes[-240]) / closes[-240] * 100 if closes[-240] > 0 else 0

    # ADX (Average Directional Index) - needed for Bear Protection motion derivatives
    if len(candles) >= 15:
        adx_result = _adx(candles, 14)
        if adx_result:
            indicators["adx_14"] = adx_result["adx"]
            indicators["plus_di"] = adx_result["plus_di"]
            indicators["minus_di"] = adx_result["minus_di"]

    return indicators


def _ema(values: list[float], period: int) -> float:
    """Calculate EMA."""
    if len(values) < period:
        return values[-1] if values else 0

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period  # Start with SMA

    for price in values[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    """Calculate RSI."""
    if len(closes) < period + 1:
        return 50.0  # Neutral

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    # Use recent period
    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def _std(values: list[float]) -> float:
    """Calculate standard deviation."""
    if len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5


def _atr(candles: list[dict], period: int = 14) -> float:
    """Calculate Average True Range."""
    if len(candles) < period + 1:
        return 0.0

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i-1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    # Use recent period
    recent_tr = true_ranges[-period:]
    return sum(recent_tr) / len(recent_tr) if recent_tr else 0.0


def _adx(candles: list[dict], period: int = 14) -> dict | None:
    """
    Calculate ADX (Average Directional Index) with +DI and -DI.

    ADX measures trend strength (not direction). Values:
    - 0-20: Weak/no trend
    - 20-40: Strong trend
    - 40-60: Very strong trend
    - 60+: Extremely strong trend

    Returns dict with 'adx', 'plus_di', 'minus_di' or None if insufficient data.
    """
    if len(candles) < period + 1:
        return None

    # Calculate True Range, +DM, -DM
    true_ranges = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_high = candles[i - 1]["high"]
        prev_low = candles[i - 1]["low"]
        prev_close = candles[i - 1]["close"]

        # True Range
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

        # Directional Movement
        up_move = high - prev_high
        down_move = prev_low - low

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)

    if len(true_ranges) < period:
        return None

    # Smooth using Wilder's smoothing (similar to EMA but different multiplier)
    def wilder_smooth(values: list[float], period: int) -> list[float]:
        smoothed = [sum(values[:period])]  # First value is SMA
        for i in range(period, len(values)):
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + values[i])
        return smoothed

    atr_smoothed = wilder_smooth(true_ranges, period)
    plus_dm_smoothed = wilder_smooth(plus_dm, period)
    minus_dm_smoothed = wilder_smooth(minus_dm, period)

    if not atr_smoothed or atr_smoothed[-1] == 0:
        return None

    # Calculate +DI and -DI
    plus_di_val = (plus_dm_smoothed[-1] / atr_smoothed[-1]) * 100
    minus_di_val = (minus_dm_smoothed[-1] / atr_smoothed[-1]) * 100

    # Calculate DX
    di_sum = plus_di_val + minus_di_val
    if di_sum == 0:
        dx_values = [0]
    else:
        # Calculate DX for each period
        dx_values = []
        for i in range(len(atr_smoothed)):
            if atr_smoothed[i] > 0:
                pdi = (plus_dm_smoothed[i] / atr_smoothed[i]) * 100
                mdi = (minus_dm_smoothed[i] / atr_smoothed[i]) * 100
                di_sum_i = pdi + mdi
                if di_sum_i > 0:
                    dx_values.append(abs(pdi - mdi) / di_sum_i * 100)
                else:
                    dx_values.append(0)

    # ADX is smoothed DX
    if len(dx_values) >= period:
        adx_smoothed = wilder_smooth(dx_values, period)
        adx_val = adx_smoothed[-1] if adx_smoothed else 0
    else:
        adx_val = sum(dx_values) / len(dx_values) if dx_values else 0

    return {
        "adx": adx_val,
        "plus_di": plus_di_val,
        "minus_di": minus_di_val,
    }


# =============================================================================
# Hivemind Data Feed Service
# =============================================================================


class HivemindDataFeedService:
    """
    Manages live data feeds for all active hiveminds.

    Connects to StreamManagerService and routes data to trios.
    """

    def __init__(
        self,
        stream_manager=None,
        candle_timeframe: str = "1m",
    ):
        """
        Initialize the data feed service.

        Args:
            stream_manager: StreamManagerService instance
            candle_timeframe: Timeframe for candle aggregation
        """
        self.stream_manager = stream_manager
        self.candle_timeframe = candle_timeframe
        self.timeframe_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[candle_timeframe]

        # Symbol state tracking
        self._symbol_states: dict[str, SymbolState] = {}

        # Callbacks for candle close events
        self._candle_close_callbacks: list[Callable[[HivemindDataSnapshot], None]] = []

        # Running state
        self._running = False

    def on_candle_close(self, callback: Callable[[HivemindDataSnapshot], None]):
        """Register callback for when a candle closes (triggers voting)."""
        self._candle_close_callbacks.append(callback)

    async def start(self, symbols: list[tuple[str, str]]):
        """
        Start the data feed for specified symbols.

        Args:
            symbols: List of (exchange, symbol) tuples
        """
        self._running = True

        # Initialize symbol states
        for exchange, symbol in symbols:
            key = self._make_key(exchange, symbol)
            self._symbol_states[key] = SymbolState(
                symbol=symbol,
                exchange=exchange,
            )

        # Register callbacks with stream manager
        if self.stream_manager:
            self.stream_manager.on_trade(self._handle_trade)
            self.stream_manager.on_kline(self._handle_kline)
            self.stream_manager.on_order_book(self._handle_orderbook)
            self.stream_manager.on_ticker(self._handle_ticker)

        logger.info("HivemindDataFeedService started for %d symbols", len(symbols))

    async def stop(self):
        """Stop the data feed."""
        self._running = False
        logger.info("HivemindDataFeedService stopped")

    def _make_key(self, exchange: str, symbol: str) -> str:
        """Create lookup key for symbol state."""
        return exchange + ":" + symbol

    def _get_state(self, exchange: str, symbol: str) -> SymbolState | None:
        """Get symbol state, creating if needed."""
        key = self._make_key(exchange, symbol)
        return self._symbol_states.get(key)

    # =========================================================================
    # Data Handlers
    # =========================================================================

    def _handle_trade(self, trade: NormalizedTrade):
        """Handle incoming trade tick."""
        state = self._get_state(trade.exchange, trade.symbol)
        if not state:
            return

        # Update price
        state.last_price = trade.price
        state.last_trade_time = trade.timestamp

        # Get candle timestamp (floor to timeframe)
        candle_ts = (trade.timestamp // 1000 // self.timeframe_seconds) * self.timeframe_seconds

        # Check if we need to close current candle and start new one
        if state.current_candle is None:
            # Start first candle
            state.current_candle = LiveCandle(
                symbol=trade.symbol,
                exchange=trade.exchange,
                timeframe=self.candle_timeframe,
                timestamp=candle_ts,
                open=trade.price,
                high=trade.price,
                low=trade.price,
                close=trade.price,
                volume=trade.size,
            )
        elif candle_ts > state.current_candle.timestamp:
            # Close current candle
            self._close_candle(state)

            # Start new candle
            state.current_candle = LiveCandle(
                symbol=trade.symbol,
                exchange=trade.exchange,
                timeframe=self.candle_timeframe,
                timestamp=candle_ts,
                open=trade.price,
                high=trade.price,
                low=trade.price,
                close=trade.price,
                volume=trade.size,
            )
        else:
            # Update current candle
            state.current_candle.update(trade.price, trade.size, trade.side)

    def _handle_kline(self, kline: KlineData):
        """Handle incoming kline (from exchanges that provide them directly)."""
        state = self._get_state(kline.exchange, kline.symbol)
        if not state:
            return

        # If this is a closed candle, process it
        if kline.is_closed and kline.timeframe == self.candle_timeframe:
            candle_dict = {
                "timestamp": kline.timestamp,
                "open": kline.open,
                "high": kline.high,
                "low": kline.low,
                "close": kline.close,
                "volume": kline.volume,
            }

            state.candle_history.append(candle_dict)
            state.last_price = kline.close

            # Recompute indicators
            self._update_indicators(state)

            # Notify callbacks
            self._notify_candle_close(state, candle_dict)

    def _handle_orderbook(self, orderbook: NormalizedOrderBook):
        """Handle orderbook update."""
        state = self._get_state(orderbook.exchange, orderbook.symbol)
        if not state:
            return

        state.bids = orderbook.bids[:10]  # Top 10 levels
        state.asks = orderbook.asks[:10]
        state.last_orderbook_time = orderbook.timestamp

        if orderbook.bids and orderbook.asks:
            state.best_bid = orderbook.bids[0][0]
            state.best_ask = orderbook.asks[0][0]
            state.spread_bps = orderbook.spread_bps or 0
            state.orderbook_imbalance = orderbook.imbalance

    def _handle_ticker(self, ticker: BookTickerData):
        """Handle book ticker (best bid/ask) update."""
        state = self._get_state(ticker.exchange, ticker.symbol)
        if not state:
            return

        state.best_bid = ticker.best_bid
        state.best_ask = ticker.best_ask
        state.spread_bps = ticker.spread_bps

    # =========================================================================
    # Candle Processing
    # =========================================================================

    def _close_candle(self, state: SymbolState):
        """Close current candle and trigger voting."""
        if not state.current_candle:
            return

        candle = state.current_candle
        candle.is_closed = True

        # Add to history
        candle_dict = candle.to_dict()
        state.candle_history.append(candle_dict)

        # Recompute indicators
        self._update_indicators(state)

        # Notify callbacks (triggers trio voting)
        self._notify_candle_close(state, candle_dict)

    def _update_indicators(self, state: SymbolState):
        """Recompute indicators from candle history, including motion derivatives."""
        candles = list(state.candle_history)
        if not candles:
            return

        # Compute base indicators (now includes ADX)
        state.indicators = compute_indicators(candles)
        state.last_indicator_update = int(datetime.utcnow().timestamp())

        # For motion derivatives, we need ADX values in the candle history
        # Enrich each candle with its ADX value for derivative computation
        # We compute ADX incrementally for each candle in the history
        enriched_candles = []
        for i, candle in enumerate(candles):
            enriched = candle.copy()
            # Compute ADX for candles up to this point
            if i >= 14:
                history_slice = candles[: i + 1]
                adx_result = _adx(history_slice, 14)
                if adx_result:
                    enriched["adx_14"] = adx_result["adx"]
            enriched_candles.append(enriched)

        # Compute motion derivatives if we have enough history (24+ candles)
        # Motion derivatives need: 21 for z-score window + 3 for jerk derivative
        if len(enriched_candles) >= 24 and enriched_candles[-1].get("adx_14") is not None:
            try:
                current_candle = enriched_candles[-1]
                history = enriched_candles[:-1]

                motion_data = compute_motion_derivatives_from_history(history, current_candle)

                # Merge motion derivatives into indicators
                for key, value in motion_data.items():
                    if value is not None:
                        state.indicators[key] = value

                # Log if defensive trigger fires
                if motion_data.get("defensive_trigger") == 1:
                    logger.warning(
                        "DEFENSIVE TRIGGER (live): %s - acc=%.2f, adx_jerk=%.2f",
                        state.symbol,
                        motion_data.get("close_acceleration_zscore", 0),
                        motion_data.get("adx_14_jerk_zscore", 0),
                    )
            except Exception as e:
                logger.debug("Motion derivative computation failed: %s", e)

    def _notify_candle_close(self, state: SymbolState, candle: dict):
        """Notify all callbacks of candle close."""
        # Build snapshot
        recent_closes = [c["close"] for c in list(state.candle_history)[-20:]]

        snapshot = HivemindDataSnapshot(
            symbol=state.symbol,
            exchange=state.exchange,
            timestamp=candle["timestamp"],
            candle=candle,
            indicators=state.indicators.copy(),
            best_bid=state.best_bid,
            best_ask=state.best_ask,
            spread_bps=state.spread_bps,
            orderbook_imbalance=state.orderbook_imbalance,
            recent_closes=recent_closes,
        )

        # Call all registered callbacks
        for callback in self._candle_close_callbacks:
            try:
                callback(snapshot)
            except Exception as e:
                logger.error("Candle close callback error: %s", e)

    # =========================================================================
    # Public API
    # =========================================================================

    def get_snapshot(self, exchange: str, symbol: str) -> HivemindDataSnapshot | None:
        """Get current data snapshot for a symbol (for on-demand queries)."""
        state = self._get_state(exchange, symbol)
        if not state or not state.candle_history:
            return None

        recent_closes = [c["close"] for c in list(state.candle_history)[-20:]]
        last_candle = list(state.candle_history)[-1]

        return HivemindDataSnapshot(
            symbol=state.symbol,
            exchange=state.exchange,
            timestamp=last_candle["timestamp"],
            candle=last_candle,
            indicators=state.indicators.copy(),
            best_bid=state.best_bid,
            best_ask=state.best_ask,
            spread_bps=state.spread_bps,
            orderbook_imbalance=state.orderbook_imbalance,
            recent_closes=recent_closes,
        )

    def get_status(self) -> dict[str, Any]:
        """Get service status."""
        return {
            "running": self._running,
            "symbols_tracked": len(self._symbol_states),
            "symbols": [
                {
                    "key": key,
                    "last_price": state.last_price,
                    "candles_in_history": len(state.candle_history),
                    "indicators_count": len(state.indicators),
                    "spread_bps": state.spread_bps,
                }
                for key, state in self._symbol_states.items()
            ],
            "callbacks_registered": len(self._candle_close_callbacks),
        }
