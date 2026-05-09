"""
Real integration tests for HivemindDataFeedService.

Tests the data feed pipeline: trade handling, candle construction,
indicator computation, orderbook tracking, and snapshot generation.
No DB required — this service is purely in-memory.
Only external calls (motion derivatives) are mocked where needed.
"""

import time
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service import (
    HivemindDataFeedService,
    HivemindDataSnapshot,
    LiveCandle,
    SymbolState,
    _adx,
    _atr,
    _ema,
    _rsi,
    _std,
    compute_indicators,
)
from Fast_Swarm.exchanges.base_ws import (
    BookTickerData,
    KlineData,
    NormalizedOrderBook,
    NormalizedTrade,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(
    exchange: str = "binance",
    symbol: str = "BTCUSDT",
    price: float = 50000.0,
    size: float = 0.1,
    side: str = "buy",
    timestamp: int = 1700000000000,
    trade_id: str = "t1",
) -> NormalizedTrade:
    return NormalizedTrade(
        exchange=exchange,
        symbol=symbol,
        trade_id=trade_id,
        timestamp=timestamp,
        price=price,
        size=size,
        side=side,
    )


def _make_kline(
    exchange: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    timestamp: int = 1700000000,
    open_: float = 50000.0,
    high: float = 50100.0,
    low: float = 49900.0,
    close: float = 50050.0,
    volume: float = 10.0,
    is_closed: bool = True,
) -> KlineData:
    return KlineData(
        exchange=exchange,
        symbol=symbol,
        timestamp=timestamp,
        timeframe=timeframe,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


def _make_orderbook(
    exchange: str = "binance",
    symbol: str = "BTCUSDT",
    best_bid: float = 49990.0,
    best_ask: float = 50010.0,
    timestamp: int = 1700000000,
) -> NormalizedOrderBook:
    bids = [(best_bid - i * 10, 1.0 + i * 0.1) for i in range(15)]
    asks = [(best_ask + i * 10, 1.0 + i * 0.1) for i in range(15)]
    return NormalizedOrderBook(
        exchange=exchange,
        symbol=symbol,
        timestamp=timestamp,
        bids=bids,
        asks=asks,
    )


def _make_ticker(
    exchange: str = "binance",
    symbol: str = "BTCUSDT",
    best_bid: float = 49990.0,
    best_ask: float = 50010.0,
    timestamp: int = 1700000000,
) -> BookTickerData:
    return BookTickerData(
        exchange=exchange,
        symbol=symbol,
        timestamp=timestamp,
        best_bid=best_bid,
        best_bid_qty=5.0,
        best_ask=best_ask,
        best_ask_qty=5.0,
    )


def _generate_candle_history(count: int, base_price: float = 50000.0) -> list[dict]:
    """Generate a list of candle dicts for indicator tests."""
    candles = []
    price = base_price
    for i in range(count):
        change = ((i % 7) - 3) * 50
        o = price
        c = price + change
        h = max(o, c) + abs(change) * 0.2
        lo = min(o, c) - abs(change) * 0.2
        candles.append({
            "timestamp": 1700000000 + i * 60,
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 100.0 + i,
            "trade_count": 10 + i,
            "buy_volume": 50.0 + i * 0.5,
            "sell_volume": 50.0 + i * 0.5,
        })
        price = c
    return candles


# ===========================================================================
# LiveCandle Tests
# ===========================================================================


class TestLiveCandle:
    """Tests for the LiveCandle dataclass."""

    def test_update_buy(self):
        candle = LiveCandle(
            symbol="BTCUSDT", exchange="binance", timeframe="1m",
            timestamp=1700000000, open=50000.0, high=50000.0,
            low=50000.0, close=50000.0, volume=0.0,
        )
        candle.update(50100.0, 0.5, "buy")
        assert candle.high == 50100.0
        assert candle.close == 50100.0
        assert candle.buy_volume == 0.5
        assert candle.sell_volume == 0.0
        assert candle.trade_count == 1

    def test_update_sell(self):
        candle = LiveCandle(
            symbol="BTCUSDT", exchange="binance", timeframe="1m",
            timestamp=1700000000, open=50000.0, high=50000.0,
            low=50000.0, close=50000.0, volume=0.0,
        )
        candle.update(49900.0, 0.3, "sell")
        assert candle.low == 49900.0
        assert candle.close == 49900.0
        assert candle.sell_volume == 0.3
        assert candle.buy_volume == 0.0

    def test_update_preserves_high_low(self):
        candle = LiveCandle(
            symbol="BTCUSDT", exchange="binance", timeframe="1m",
            timestamp=1700000000, open=50000.0, high=50200.0,
            low=49800.0, close=50000.0, volume=1.0,
        )
        candle.update(50050.0, 0.1, "buy")
        assert candle.high == 50200.0
        assert candle.low == 49800.0

    def test_to_dict(self):
        candle = LiveCandle(
            symbol="BTCUSDT", exchange="binance", timeframe="1m",
            timestamp=1700000000, open=50000.0, high=50100.0,
            low=49900.0, close=50050.0, volume=1.5,
            trade_count=5, buy_volume=0.8, sell_volume=0.7,
        )
        d = candle.to_dict()
        assert d["timestamp"] == 1700000000
        assert d["open"] == 50000.0
        assert d["close"] == 50050.0
        assert d["volume"] == 1.5
        assert d["trade_count"] == 5
        assert d["buy_volume"] == 0.8


# ===========================================================================
# Indicator Computation Tests
# ===========================================================================


class TestIndicatorComputation:
    """Tests for the compute_indicators function and helpers."""

    def test_empty_candles_returns_empty(self):
        assert compute_indicators([]) == {}

    def test_single_candle_returns_empty(self):
        candles = _generate_candle_history(1)
        assert compute_indicators(candles) == {}

    def test_two_candles_has_price_change(self):
        candles = _generate_candle_history(2)
        ind = compute_indicators(candles)
        assert "price_change_pct" in ind
        assert "close" in ind

    def test_sma_20_computed_at_20_candles(self):
        candles = _generate_candle_history(20)
        ind = compute_indicators(candles)
        assert "sma_20" in ind
        expected = sum(c["close"] for c in candles[-20:]) / 20
        assert abs(ind["sma_20"] - expected) < 1e-6

    def test_sma_50_not_present_under_50_candles(self):
        candles = _generate_candle_history(30)
        ind = compute_indicators(candles)
        assert "sma_50" not in ind

    def test_sma_50_computed_at_50_candles(self):
        candles = _generate_candle_history(50)
        ind = compute_indicators(candles)
        assert "sma_50" in ind

    def test_rsi_range(self):
        candles = _generate_candle_history(30)
        ind = compute_indicators(candles)
        assert "rsi_14" in ind
        assert 0.0 <= ind["rsi_14"] <= 100.0

    def test_bollinger_bands_at_20_candles(self):
        candles = _generate_candle_history(25)
        ind = compute_indicators(candles)
        assert "bb_upper" in ind
        assert "bb_lower" in ind
        assert ind["bb_upper"] > ind["bb_lower"]

    def test_macd_at_26_candles(self):
        candles = _generate_candle_history(30)
        ind = compute_indicators(candles)
        assert "macd" in ind
        assert "macd_line" in ind

    def test_atr_computed(self):
        candles = _generate_candle_history(20)
        ind = compute_indicators(candles)
        assert "atr_14" in ind
        assert ind["atr_14"] > 0

    def test_volume_ratio_at_20_candles(self):
        candles = _generate_candle_history(25)
        ind = compute_indicators(candles)
        assert "volume_sma_20" in ind
        assert "volume_ratio" in ind
        assert ind["volume_ratio"] > 0

    def test_adx_at_15_candles(self):
        candles = _generate_candle_history(20)
        ind = compute_indicators(candles)
        assert "adx_14" in ind
        assert "plus_di" in ind
        assert "minus_di" in ind

    def test_hourly_change(self):
        candles = _generate_candle_history(65)
        ind = compute_indicators(candles)
        assert "close_1h_ago" in ind
        assert "change_1h_pct" in ind

    def test_four_hour_change(self):
        candles = _generate_candle_history(250)
        ind = compute_indicators(candles)
        assert "close_4h_ago" in ind
        assert "change_4h_pct" in ind


class TestHelperFunctions:
    """Tests for _ema, _rsi, _std, _atr, _adx."""

    def test_ema_short_list_returns_last(self):
        result = _ema([100.0, 200.0], 10)
        assert result == 200.0

    def test_ema_empty_returns_zero(self):
        assert _ema([], 10) == 0

    def test_rsi_insufficient_data_returns_neutral(self):
        assert _rsi([100.0, 101.0], 14) == 50.0

    def test_rsi_all_gains_returns_100(self):
        closes = [float(i) for i in range(20)]  # monotonically increasing
        assert _rsi(closes, 14) == 100.0

    def test_std_single_value_returns_zero(self):
        assert _std([42.0]) == 0.0

    def test_std_identical_values_returns_zero(self):
        assert _std([5.0, 5.0, 5.0]) == 0.0

    def test_atr_insufficient_returns_zero(self):
        candles = _generate_candle_history(5)
        assert _atr(candles, 14) == 0.0

    def test_adx_insufficient_returns_none(self):
        candles = _generate_candle_history(5)
        assert _adx(candles, 14) is None

    def test_adx_returns_dict(self):
        candles = _generate_candle_history(30)
        result = _adx(candles, 14)
        assert result is not None
        assert "adx" in result
        assert "plus_di" in result
        assert "minus_di" in result


# ===========================================================================
# HivemindDataFeedService Tests
# ===========================================================================


class TestHivemindDataFeedServiceInit:
    """Tests for service initialization."""

    def test_default_init(self):
        svc = HivemindDataFeedService()
        assert svc.stream_manager is None
        assert svc.candle_timeframe == "1m"
        assert svc.timeframe_seconds == 60
        assert svc._running is False

    def test_custom_timeframe(self):
        svc = HivemindDataFeedService(candle_timeframe="5m")
        assert svc.timeframe_seconds == 300

    def test_invalid_timeframe_raises(self):
        with pytest.raises(KeyError):
            HivemindDataFeedService(candle_timeframe="2m")


class TestServiceLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        assert svc._running is True
        assert len(svc._symbol_states) == 1

    @pytest.mark.asyncio
    async def test_start_multiple_symbols(self):
        svc = HivemindDataFeedService()
        symbols = [("binance", "BTCUSDT"), ("binance", "ETHUSDT"), ("bybit", "BTCUSDT")]
        await svc.start(symbols)
        assert len(svc._symbol_states) == 3

    @pytest.mark.asyncio
    async def test_stop_clears_running(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        await svc.stop()
        assert svc._running is False

    @pytest.mark.asyncio
    async def test_start_registers_stream_callbacks(self):
        mock_stream = MagicMock()
        svc = HivemindDataFeedService(stream_manager=mock_stream)
        await svc.start([("binance", "BTCUSDT")])
        mock_stream.on_trade.assert_called_once()
        mock_stream.on_kline.assert_called_once()
        mock_stream.on_order_book.assert_called_once()
        mock_stream.on_ticker.assert_called_once()


class TestTradeHandling:
    """Tests for _handle_trade — candle construction from ticks."""

    @pytest.mark.asyncio
    async def test_first_trade_creates_candle(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        trade = _make_trade(timestamp=1700000060000)
        svc._handle_trade(trade)

        state = svc._get_state("binance", "BTCUSDT")
        assert state.current_candle is not None
        assert state.current_candle.open == 50000.0
        assert state.last_price == 50000.0

    @pytest.mark.asyncio
    async def test_trade_updates_current_candle(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        ts = 1700000060000  # same minute

        svc._handle_trade(_make_trade(timestamp=ts, price=50000.0, size=0.1, side="buy"))
        svc._handle_trade(_make_trade(timestamp=ts + 1000, price=50100.0, size=0.2, side="buy"))
        svc._handle_trade(_make_trade(timestamp=ts + 2000, price=49900.0, size=0.3, side="sell"))

        state = svc._get_state("binance", "BTCUSDT")
        assert state.current_candle.high == 50100.0
        assert state.current_candle.low == 49900.0
        assert state.current_candle.close == 49900.0

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_new_minute_closes_candle(self, _mock_motion):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        # Trade in minute 0
        svc._handle_trade(_make_trade(timestamp=1700000060000, price=50000.0))
        # Trade in minute 1 should close the first candle
        svc._handle_trade(_make_trade(timestamp=1700000120000, price=50100.0))

        state = svc._get_state("binance", "BTCUSDT")
        assert len(state.candle_history) == 1
        assert state.current_candle.open == 50100.0

    @pytest.mark.asyncio
    async def test_unknown_symbol_ignored(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        trade = _make_trade(symbol="ETHUSDT")
        svc._handle_trade(trade)
        # Should not crash, no state for ETHUSDT
        assert svc._get_state("binance", "ETHUSDT") is None


class TestKlineHandling:
    """Tests for _handle_kline — direct candle ingestion."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_closed_kline_appended(self, _mock_motion):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        kline = _make_kline(is_closed=True)
        svc._handle_kline(kline)

        state = svc._get_state("binance", "BTCUSDT")
        assert len(state.candle_history) == 1
        assert state.last_price == 50050.0

    @pytest.mark.asyncio
    async def test_unclosed_kline_not_appended(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        kline = _make_kline(is_closed=False)
        svc._handle_kline(kline)

        state = svc._get_state("binance", "BTCUSDT")
        assert len(state.candle_history) == 0

    @pytest.mark.asyncio
    async def test_wrong_timeframe_kline_ignored(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        kline = _make_kline(timeframe="5m", is_closed=True)
        svc._handle_kline(kline)

        state = svc._get_state("binance", "BTCUSDT")
        assert len(state.candle_history) == 0


class TestOrderbookHandling:
    """Tests for _handle_orderbook and _handle_ticker."""

    @pytest.mark.asyncio
    async def test_orderbook_updates_state(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        ob = _make_orderbook(best_bid=49990.0, best_ask=50010.0)
        svc._handle_orderbook(ob)

        state = svc._get_state("binance", "BTCUSDT")
        assert state.best_bid == 49990.0
        assert state.best_ask == 50010.0
        assert len(state.bids) == 10  # top 10 only
        assert len(state.asks) == 10

    @pytest.mark.asyncio
    async def test_ticker_updates_bid_ask(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        ticker = _make_ticker(best_bid=49995.0, best_ask=50005.0)
        svc._handle_ticker(ticker)

        state = svc._get_state("binance", "BTCUSDT")
        assert state.best_bid == 49995.0
        assert state.best_ask == 50005.0


class TestCandleCloseCallback:
    """Tests for candle close notification pipeline."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_callback_fired_on_candle_close(self, _mock_motion):
        svc = HivemindDataFeedService()
        snapshots = []
        svc.on_candle_close(lambda snap: snapshots.append(snap))
        await svc.start([("binance", "BTCUSDT")])

        # Minute 0 trade
        svc._handle_trade(_make_trade(timestamp=1700000060000, price=50000.0))
        # Minute 1 trade triggers close
        svc._handle_trade(_make_trade(timestamp=1700000120000, price=50100.0))

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert isinstance(snap, HivemindDataSnapshot)
        assert snap.symbol == "BTCUSDT"
        assert snap.exchange == "binance"
        assert snap.candle["close"] == 50000.0

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_callback_error_does_not_crash(self, _mock_motion):
        svc = HivemindDataFeedService()

        def bad_callback(snap):
            raise ValueError("boom")

        svc.on_candle_close(bad_callback)
        await svc.start([("binance", "BTCUSDT")])

        # Should not raise
        svc._handle_trade(_make_trade(timestamp=1700000060000, price=50000.0))
        svc._handle_trade(_make_trade(timestamp=1700000120000, price=50100.0))

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_multiple_callbacks_all_called(self, _mock_motion):
        svc = HivemindDataFeedService()
        calls = {"a": 0, "b": 0}
        svc.on_candle_close(lambda snap: calls.__setitem__("a", calls["a"] + 1))
        svc.on_candle_close(lambda snap: calls.__setitem__("b", calls["b"] + 1))
        await svc.start([("binance", "BTCUSDT")])

        svc._handle_trade(_make_trade(timestamp=1700000060000))
        svc._handle_trade(_make_trade(timestamp=1700000120000))

        assert calls["a"] == 1
        assert calls["b"] == 1


class TestGetSnapshot:
    """Tests for the public get_snapshot API."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_get_snapshot_returns_data(self, _mock_motion):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        kline = _make_kline(is_closed=True, close=50050.0)
        svc._handle_kline(kline)

        snap = svc.get_snapshot("binance", "BTCUSDT")
        assert snap is not None
        assert snap.candle["close"] == 50050.0
        assert 50050.0 in snap.recent_closes

    @pytest.mark.asyncio
    async def test_get_snapshot_no_history_returns_none(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        assert svc.get_snapshot("binance", "BTCUSDT") is None

    @pytest.mark.asyncio
    async def test_get_snapshot_unknown_symbol_returns_none(self):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])
        assert svc.get_snapshot("binance", "ETHUSDT") is None


class TestGetStatus:
    """Tests for the get_status API."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_status_structure(self, _mock_motion):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT"), ("binance", "ETHUSDT")])

        svc.on_candle_close(lambda snap: None)
        svc._handle_kline(_make_kline(is_closed=True))

        status = svc.get_status()
        assert status["running"] is True
        assert status["symbols_tracked"] == 2
        assert status["callbacks_registered"] == 1
        assert len(status["symbols"]) == 2

    @pytest.mark.asyncio
    async def test_status_not_running(self):
        svc = HivemindDataFeedService()
        status = svc.get_status()
        assert status["running"] is False
        assert status["symbols_tracked"] == 0


class TestIndicatorUpdateIntegration:
    """Tests for indicator recomputation on candle close."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={},
    )
    async def test_indicators_computed_after_enough_candles(self, _mock_motion):
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        # Feed 30 closed klines
        for i in range(30):
            price = 50000.0 + i * 10
            kline = _make_kline(
                timestamp=1700000000 + i * 60,
                open_=price,
                high=price + 20,
                low=price - 20,
                close=price + 5,
                volume=100.0 + i,
                is_closed=True,
            )
            svc._handle_kline(kline)

        state = svc._get_state("binance", "BTCUSDT")
        assert len(state.candle_history) == 30
        assert "sma_20" in state.indicators
        assert "rsi_14" in state.indicators
        assert "macd" in state.indicators
        assert "atr_14" in state.indicators

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.Agents.Hivemind.Services.hivemind_data_feed_service"
        ".compute_motion_derivatives_from_history",
        return_value={"defensive_trigger": 1, "close_acceleration_zscore": -3.5, "adx_14_jerk_zscore": 2.1},
    )
    async def test_motion_derivatives_merged(self, _mock_motion):
        """When motion derivative computation returns data, it should be merged into indicators."""
        svc = HivemindDataFeedService()
        await svc.start([("binance", "BTCUSDT")])

        # Need 24+ candles with adx_14 for motion derivatives to fire
        for i in range(30):
            price = 50000.0 + i * 10
            kline = _make_kline(
                timestamp=1700000000 + i * 60,
                open_=price,
                high=price + 50,
                low=price - 50,
                close=price + 5,
                volume=100.0 + i,
                is_closed=True,
            )
            svc._handle_kline(kline)

        state = svc._get_state("binance", "BTCUSDT")
        assert state.indicators.get("defensive_trigger") == 1


class TestSymbolKeyMake:
    """Tests for the _make_key helper."""

    def test_key_format(self):
        svc = HivemindDataFeedService()
        assert svc._make_key("binance", "BTCUSDT") == "binance:BTCUSDT"

    def test_different_exchanges_different_keys(self):
        svc = HivemindDataFeedService()
        k1 = svc._make_key("binance", "BTCUSDT")
        k2 = svc._make_key("bybit", "BTCUSDT")
        assert k1 != k2
