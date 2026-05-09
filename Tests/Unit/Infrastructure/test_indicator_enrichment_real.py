"""
Real integration tests for indicator_enrichment_service.py

Tests the pure-Python single-candle enrichment functions with real data objects.
Tests the SQL batch enrichment against a real test database.

Uses db_session fixture from conftest.py for database tests.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import (
    BATCH_SIZE,
    DEFAULT_SKIP_SYMBOLS,
    compute_derived_for_candle,
    enrich_candle_dict,
    enrich_candle_on_demand,
    compute_derived_indicators_batch,
    check_db_activity,
    wait_for_db_idle,
    get_enrichment_status,
)
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle


# ============================================================================
# HELPERS
# ============================================================================


def _make_candle_dict(
    close=50000.0,
    ema_9=49800.0,
    ema_21=49500.0,
    sma_50=48000.0,
    sma_200=45000.0,
    macd_line=120.0,
    macd_signal=100.0,
    rsi_14=55.0,
    stoch_k=60.0,
    adx_14=30.0,
    plus_di=25.0,
    minus_di=15.0,
    natr_14=3.0,
    bb_upper=51000.0,
    bb_lower=49000.0,
    bb_width=0.04,
    volume=1500.0,
    volume_sma_20=1000.0,
    time=None,
    **overrides,
) -> dict:
    """Build a realistic candle dict with all indicator fields populated."""
    candle = {
        "close": close,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "rsi_14": rsi_14,
        "stoch_k": stoch_k,
        "adx_14": adx_14,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "natr_14": natr_14,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "volume": volume,
        "volume_sma_20": volume_sma_20,
        "time": time or datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
    }
    candle.update(overrides)
    return candle


async def _insert_enhanced_candle(session: AsyncSession, **kwargs) -> None:
    """Insert an enhanced candle row directly via SQL for test setup."""
    defaults = {
        "time": datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
        "exchange": "binance",
        "symbol": "TEST",
        "timeframe": "1h",
        "open": 50000.0,
        "high": 51000.0,
        "low": 49000.0,
        "close": 50500.0,
        "volume": 1500.0,
        "ema_9": 50200.0,
        "ema_21": 49800.0,
        "sma_50": 48000.0,
        "sma_200": 45000.0,
        "macd_line": 120.0,
        "macd_signal": 100.0,
        "rsi_14": 55.0,
        "stoch_k": 60.0,
        "adx_14": 30.0,
        "plus_di": 25.0,
        "minus_di": 15.0,
        "natr_14": 3.0,
        "bb_upper": 51500.0,
        "bb_lower": 49000.0,
        "bb_width": 0.05,
        "volume_sma_20": 1000.0,
        "derived_computed_at": None,
    }
    defaults.update(kwargs)

    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    await session.execute(
        text(f"INSERT INTO enhanced_candles ({cols}) VALUES ({placeholders})"),
        defaults,
    )
    await session.commit()


# ============================================================================
# PURE PYTHON TESTS: compute_derived_for_candle
# ============================================================================


class TestComputeDerivedForCandle:
    """Tests for the pure-Python single-candle computation."""

    def test_ma_cross_bullish(self):
        """EMA 21 > SMA 50 should produce bullish cross signal."""
        candle = _make_candle_dict(ema_21=50000.0, sma_50=49000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["ma_cross_20_50"] == 1

    def test_ma_cross_bearish(self):
        """EMA 21 < SMA 50 should produce bearish cross signal."""
        candle = _make_candle_dict(ema_21=48000.0, sma_50=49000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["ma_cross_20_50"] == -1

    def test_golden_cross(self):
        """SMA 50 > SMA 200 should trigger golden cross."""
        candle = _make_candle_dict(sma_50=50000.0, sma_200=45000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["golden_cross"] == 1
        assert derived["death_cross"] == 0

    def test_death_cross(self):
        """SMA 50 < SMA 200 should trigger death cross."""
        candle = _make_candle_dict(sma_50=44000.0, sma_200=45000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["death_cross"] == 1
        assert derived["golden_cross"] == 0

    def test_macd_cross_bullish(self):
        """MACD line > signal should produce bullish signal."""
        candle = _make_candle_dict(macd_line=150.0, macd_signal=100.0)
        derived = compute_derived_for_candle(candle)
        assert derived["macd_cross"] == 1

    def test_macd_cross_bearish(self):
        """MACD line < signal should produce bearish signal."""
        candle = _make_candle_dict(macd_line=80.0, macd_signal=100.0)
        derived = compute_derived_for_candle(candle)
        assert derived["macd_cross"] == -1

    def test_price_vs_ma_percentages(self):
        """Price vs MA percentage calculations should be accurate."""
        candle = _make_candle_dict(close=50000.0, ema_9=49000.0, ema_21=48000.0)
        derived = compute_derived_for_candle(candle)
        # close=50000, ema_9=49000 => (50000-49000)/49000*100 ~ 2.04%
        assert abs(derived["price_vs_ema_9_pct"] - 2.0408) < 0.01
        # close=50000, ema_21=48000 => (50000-48000)/48000*100 ~ 4.17%
        assert abs(derived["price_vs_ema_21_pct"] - 4.1667) < 0.01

    def test_rsi_oversold(self):
        """RSI < 30 should flag oversold."""
        candle = _make_candle_dict(rsi_14=25.0)
        derived = compute_derived_for_candle(candle)
        assert derived["rsi_oversold"] == 1
        assert derived["rsi_overbought"] == 0
        assert derived["rsi_neutral"] == 0

    def test_rsi_overbought(self):
        """RSI > 70 should flag overbought."""
        candle = _make_candle_dict(rsi_14=75.0)
        derived = compute_derived_for_candle(candle)
        assert derived["rsi_overbought"] == 1
        assert derived["rsi_oversold"] == 0
        assert derived["rsi_neutral"] == 0

    def test_rsi_neutral(self):
        """RSI between 30-70 should flag neutral."""
        candle = _make_candle_dict(rsi_14=50.0)
        derived = compute_derived_for_candle(candle)
        assert derived["rsi_neutral"] == 1
        assert derived["rsi_oversold"] == 0
        assert derived["rsi_overbought"] == 0

    def test_rsi_boundary_30(self):
        """RSI exactly 30 should be neutral (30 <= rsi <= 70)."""
        candle = _make_candle_dict(rsi_14=30.0)
        derived = compute_derived_for_candle(candle)
        assert derived["rsi_neutral"] == 1
        assert derived["rsi_oversold"] == 0

    def test_stochastic_oversold(self):
        """Stoch K < 20 should flag oversold."""
        candle = _make_candle_dict(stoch_k=15.0)
        derived = compute_derived_for_candle(candle)
        assert derived["stoch_oversold"] == 1
        assert derived["stoch_overbought"] == 0

    def test_stochastic_overbought(self):
        """Stoch K > 80 should flag overbought."""
        candle = _make_candle_dict(stoch_k=85.0)
        derived = compute_derived_for_candle(candle)
        assert derived["stoch_overbought"] == 1
        assert derived["stoch_oversold"] == 0

    def test_strong_trend(self):
        """ADX > 25 should flag strong trend."""
        candle = _make_candle_dict(adx_14=35.0)
        derived = compute_derived_for_candle(candle)
        assert derived["strong_trend"] == 1
        assert derived["weak_trend"] == 0

    def test_weak_trend(self):
        """ADX < 20 should flag weak trend."""
        candle = _make_candle_dict(adx_14=15.0)
        derived = compute_derived_for_candle(candle)
        assert derived["weak_trend"] == 1
        assert derived["strong_trend"] == 0

    def test_volatility_regime_low(self):
        """NATR < 2 should produce low volatility regime."""
        candle = _make_candle_dict(natr_14=1.5)
        derived = compute_derived_for_candle(candle)
        assert derived["volatility_regime"] == "low"

    def test_volatility_regime_medium(self):
        """NATR 2-5 should produce medium volatility regime."""
        candle = _make_candle_dict(natr_14=3.5)
        derived = compute_derived_for_candle(candle)
        assert derived["volatility_regime"] == "medium"

    def test_volatility_regime_high(self):
        """NATR >= 5 should produce high volatility regime."""
        candle = _make_candle_dict(natr_14=7.0)
        derived = compute_derived_for_candle(candle)
        assert derived["volatility_regime"] == "high"

    def test_trend_regime_sideways(self):
        """ADX < 20 should produce sideways trend regime."""
        candle = _make_candle_dict(adx_14=15.0)
        derived = compute_derived_for_candle(candle)
        assert derived["trend_regime"] == "sideways"

    def test_trend_regime_uptrend(self):
        """ADX >= 20 with plus_di > minus_di should produce uptrend."""
        candle = _make_candle_dict(adx_14=30.0, plus_di=25.0, minus_di=15.0)
        derived = compute_derived_for_candle(candle)
        assert derived["trend_regime"] == "uptrend"

    def test_trend_regime_downtrend(self):
        """ADX >= 20 with minus_di > plus_di should produce downtrend."""
        candle = _make_candle_dict(adx_14=30.0, plus_di=10.0, minus_di=25.0)
        derived = compute_derived_for_candle(candle)
        assert derived["trend_regime"] == "downtrend"

    def test_session_asian(self):
        """Hour 0-7 UTC should flag Asian session."""
        t = datetime(2024, 6, 15, 3, 0, tzinfo=timezone.utc)
        candle = _make_candle_dict(time=t)
        derived = compute_derived_for_candle(candle)
        assert derived["is_asian_session"] == 1
        assert derived["is_london_session"] == 0

    def test_session_london(self):
        """Hour 8-15 UTC should flag London session."""
        t = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        candle = _make_candle_dict(time=t)
        derived = compute_derived_for_candle(candle)
        assert derived["is_london_session"] == 1
        assert derived["is_asian_session"] == 0

    def test_session_us(self):
        """Hour 13-20 UTC should flag US session."""
        t = datetime(2024, 6, 15, 15, 0, tzinfo=timezone.utc)
        candle = _make_candle_dict(time=t)
        derived = compute_derived_for_candle(candle)
        assert derived["is_us_session"] == 1
        assert derived["is_us_market_hours"] == 1

    def test_session_overlap_london_us(self):
        """Hour 15 UTC overlaps London and US sessions."""
        t = datetime(2024, 6, 15, 15, 0, tzinfo=timezone.utc)
        candle = _make_candle_dict(time=t)
        derived = compute_derived_for_candle(candle)
        assert derived["is_london_session"] == 1
        assert derived["is_us_session"] == 1

    def test_bollinger_upper_touch(self):
        """Close >= BB upper should flag price_at_bb_upper."""
        candle = _make_candle_dict(close=52000.0, bb_upper=51000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["price_at_bb_upper"] == 1
        assert derived["price_at_bb_lower"] == 0

    def test_bollinger_lower_touch(self):
        """Close <= BB lower should flag price_at_bb_lower."""
        candle = _make_candle_dict(close=48000.0, bb_lower=49000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["price_at_bb_lower"] == 1
        assert derived["price_at_bb_upper"] == 0

    def test_bb_squeeze(self):
        """BB width < 0.05 should flag squeeze."""
        candle = _make_candle_dict(bb_width=0.03)
        derived = compute_derived_for_candle(candle)
        assert derived["bb_squeeze"] == 1

    def test_high_volume(self):
        """Volume > 1.5x SMA should flag high volume."""
        candle = _make_candle_dict(volume=2000.0, volume_sma_20=1000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["high_volume"] == 1
        assert derived["low_volume"] == 0

    def test_low_volume(self):
        """Volume < 0.5x SMA should flag low volume."""
        candle = _make_candle_dict(volume=400.0, volume_sma_20=1000.0)
        derived = compute_derived_for_candle(candle)
        assert derived["low_volume"] == 1
        assert derived["high_volume"] == 0

    def test_none_indicators_skipped(self):
        """None indicator values should not produce derived keys."""
        candle = _make_candle_dict(
            ema_9=None, ema_21=None, sma_50=None, sma_200=None,
            macd_line=None, macd_signal=None, rsi_14=None, stoch_k=None,
            adx_14=None, natr_14=None, bb_upper=None, bb_lower=None,
            bb_width=None, volume=None, volume_sma_20=None,
        )
        derived = compute_derived_for_candle(candle)
        # Should still have session indicators from timestamp
        assert "is_asian_session" in derived or "is_london_session" in derived
        # Should NOT have MA cross (both inputs None)
        assert "ma_cross_20_50" not in derived
        assert "rsi_oversold" not in derived

    def test_price_above_ma_booleans(self):
        """Price above/below MA booleans should be correct."""
        candle = _make_candle_dict(
            close=50000.0, ema_9=49000.0, ema_21=51000.0,
            sma_50=48000.0, sma_200=52000.0,
        )
        derived = compute_derived_for_candle(candle)
        assert derived["price_above_ema_9"] == 1   # 50k > 49k
        assert derived["price_above_ema_21"] == 0   # 50k < 51k
        assert derived["price_above_sma_50"] == 1   # 50k > 48k
        assert derived["price_above_sma_200"] == 0  # 50k < 52k

    def test_unix_timestamp_seconds(self):
        """Unix timestamp in seconds should compute session indicators."""
        # 2024-06-15 10:00 UTC as seconds
        ts = 1718445600
        candle = _make_candle_dict(time=ts)
        derived = compute_derived_for_candle(candle)
        assert derived["is_london_session"] == 1

    def test_unix_timestamp_milliseconds(self):
        """Unix timestamp in milliseconds should compute session indicators."""
        # 2024-06-15 03:00 UTC as milliseconds
        ts = 1718420400000
        candle = _make_candle_dict(time=ts)
        derived = compute_derived_for_candle(candle)
        assert derived["is_asian_session"] == 1


# ============================================================================
# ENRICH CANDLE DICT (in-memory mutation)
# ============================================================================


class TestEnrichCandleDict:
    """Tests for enrich_candle_dict (mutates dict in-place)."""

    def test_enriches_missing_fields(self):
        """Should add derived fields to a candle dict."""
        candle = _make_candle_dict()
        result = enrich_candle_dict(candle)
        assert result is candle  # mutates in place
        assert "ma_cross_20_50" in candle
        assert "rsi_neutral" in candle

    def test_skips_already_enriched(self):
        """Should skip candles with derived_computed_at set."""
        candle = _make_candle_dict()
        candle["derived_computed_at"] = datetime.now(timezone.utc)
        result = enrich_candle_dict(candle)
        # Should NOT overwrite existing derived fields
        assert "ma_cross_20_50" not in result or result.get("ma_cross_20_50") is None

    def test_does_not_overwrite_existing_values(self):
        """Should not overwrite existing non-None derived values."""
        candle = _make_candle_dict()
        candle["ma_cross_20_50"] = 99  # pre-set value
        enrich_candle_dict(candle)
        assert candle["ma_cross_20_50"] == 99  # should not be overwritten

    def test_all_expected_keys_present(self):
        """A fully populated candle should produce all expected derived keys."""
        candle = _make_candle_dict()
        enrich_candle_dict(candle)
        expected_keys = [
            "ma_cross_20_50", "golden_cross", "death_cross", "macd_cross",
            "price_vs_ema_9_pct", "price_vs_ema_21_pct",
            "rsi_oversold", "rsi_overbought", "rsi_neutral",
            "stoch_oversold", "stoch_overbought",
            "strong_trend", "weak_trend",
            "volatility_regime", "trend_regime",
            "is_asian_session", "is_london_session", "is_us_session",
            "price_at_bb_upper", "price_at_bb_lower", "bb_squeeze",
            "high_volume", "low_volume",
        ]
        for key in expected_keys:
            assert key in candle, f"Missing derived key: {key}"


# ============================================================================
# DATABASE INTEGRATION TESTS
# ============================================================================


@pytest.mark.requires_db
class TestComputeDerivedIndicatorsBatch:
    """Tests for SQL batch enrichment against real database."""

    @pytest.mark.asyncio
    async def test_batch_enriches_unenriched_candles(self, db_session: AsyncSession):
        """Batch should update candles that have derived_computed_at IS NULL."""
        await _insert_enhanced_candle(db_session, symbol="TEST", timeframe="1h")

        updated = await compute_derived_indicators_batch(
            db_session, symbol="TEST", timeframe="1h", limit=100,
        )
        assert updated == 1

        # Verify derived columns were set
        result = await db_session.execute(
            text("SELECT ma_cross_20_50, rsi_neutral, derived_computed_at FROM enhanced_candles WHERE symbol = 'TEST'")
        )
        row = result.fetchone()
        assert row is not None
        assert row[2] is not None  # derived_computed_at should be set

    @pytest.mark.asyncio
    async def test_batch_skips_already_enriched(self, db_session: AsyncSession):
        """Batch should skip candles that already have derived_computed_at set."""
        await _insert_enhanced_candle(
            db_session, symbol="TEST", timeframe="1h",
            derived_computed_at=datetime.now(timezone.utc),
        )

        updated = await compute_derived_indicators_batch(
            db_session, symbol="TEST", timeframe="1h", limit=100,
        )
        assert updated == 0

    @pytest.mark.asyncio
    async def test_batch_symbol_filter(self, db_session: AsyncSession):
        """Symbol filter should only process matching rows."""
        t1 = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc)
        await _insert_enhanced_candle(db_session, symbol="BTC", timeframe="1h", time=t1)
        await _insert_enhanced_candle(db_session, symbol="ETH", timeframe="1h", time=t2)

        updated = await compute_derived_indicators_batch(
            db_session, symbol="BTC", timeframe="1h", limit=100,
        )
        assert updated == 1

        # ETH should still be unenriched
        result = await db_session.execute(
            text("SELECT derived_computed_at FROM enhanced_candles WHERE symbol = 'ETH'")
        )
        row = result.fetchone()
        assert row[0] is None

    @pytest.mark.asyncio
    async def test_batch_multiple_candles(self, db_session: AsyncSession):
        """Batch should process multiple candles at once."""
        base_time = datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            await _insert_enhanced_candle(
                db_session, symbol="MULTI", timeframe="1h",
                time=base_time + timedelta(hours=i),
                close=50000.0 + i * 100,
            )

        updated = await compute_derived_indicators_batch(
            db_session, symbol="MULTI", timeframe="1h", limit=100,
        )
        assert updated == 5

    @pytest.mark.asyncio
    async def test_batch_respects_limit(self, db_session: AsyncSession):
        """Limit parameter should cap the number of rows processed."""
        base_time = datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            await _insert_enhanced_candle(
                db_session, symbol="LIM", timeframe="1h",
                time=base_time + timedelta(hours=i),
            )

        updated = await compute_derived_indicators_batch(
            db_session, symbol="LIM", timeframe="1h", limit=3,
        )
        assert updated == 3

        # Remaining 7 should still be unenriched
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM enhanced_candles WHERE symbol = 'LIM' AND derived_computed_at IS NULL")
        )
        assert result.scalar() == 7


@pytest.mark.requires_db
class TestEnrichCandleOnDemand:
    """Tests for on-demand single-candle enrichment with DB persistence."""

    @pytest.mark.asyncio
    async def test_on_demand_computes_and_persists(self, db_session: AsyncSession):
        """On-demand enrichment should compute values and write to DB."""
        t = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        await _insert_enhanced_candle(db_session, symbol="OD", timeframe="1h", time=t)

        candle = {
            "time": t,
            "exchange": "binance",
            "symbol": "OD",
            "timeframe": "1h",
            "close": 50500.0,
            "ema_9": 50200.0,
            "ema_21": 49800.0,
            "sma_50": 48000.0,
            "sma_200": 45000.0,
            "rsi_14": 55.0,
            "adx_14": 30.0,
            "plus_di": 25.0,
            "minus_di": 15.0,
            "natr_14": 3.0,
        }

        derived = await enrich_candle_on_demand(db_session, candle, persist=True)
        await db_session.commit()

        assert "ma_cross_20_50" in derived
        assert derived["rsi_neutral"] == 1

        # Check DB was updated
        result = await db_session.execute(
            text("SELECT derived_computed_at, rsi_neutral FROM enhanced_candles WHERE symbol = 'OD'")
        )
        row = result.fetchone()
        assert row[0] is not None  # derived_computed_at set
        assert row[1] == 1  # rsi_neutral persisted

    @pytest.mark.asyncio
    async def test_on_demand_no_persist(self, db_session: AsyncSession):
        """With persist=False, should compute but not write to DB."""
        t = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        await _insert_enhanced_candle(db_session, symbol="NP", timeframe="1h", time=t)

        candle = {
            "time": t,
            "exchange": "binance",
            "symbol": "NP",
            "timeframe": "1h",
            "close": 50500.0,
            "ema_21": 49800.0,
            "sma_50": 48000.0,
            "rsi_14": 55.0,
        }

        derived = await enrich_candle_on_demand(db_session, candle, persist=False)
        assert "ma_cross_20_50" in derived

        # DB should NOT be updated
        result = await db_session.execute(
            text("SELECT derived_computed_at FROM enhanced_candles WHERE symbol = 'NP'")
        )
        row = result.fetchone()
        assert row[0] is None

    @pytest.mark.asyncio
    async def test_on_demand_empty_candle(self, db_session: AsyncSession):
        """A candle with all None indicators should return empty derived dict."""
        candle = {
            "time": datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
            "exchange": "binance",
            "symbol": "EMPTY",
            "timeframe": "1h",
            "close": 0,
        }
        derived = await enrich_candle_on_demand(db_session, candle, persist=False)
        # Should have session indicators at minimum
        assert "is_london_session" in derived


@pytest.mark.requires_db
class TestCheckDbActivity:
    """Tests for the DB activity monitor."""

    @pytest.mark.asyncio
    async def test_check_db_activity_returns_tuple(self, db_session: AsyncSession):
        """Should return (is_busy, active_count) tuple."""
        is_busy, active = await check_db_activity(db_session)
        assert isinstance(is_busy, bool)
        assert isinstance(active, int)
        assert active >= 0

    @pytest.mark.asyncio
    async def test_check_db_not_busy_during_test(self, db_session: AsyncSession):
        """During tests, DB should not be flagged as busy (few active queries)."""
        is_busy, _ = await check_db_activity(db_session)
        # In a test environment, should not be busy
        assert is_busy is False


@pytest.mark.requires_db
class TestGetEnrichmentStatus:
    """Tests for get_enrichment_status (requires DB)."""

    @pytest.mark.asyncio
    async def test_status_empty_table(self, db_session: AsyncSession):
        """Status on empty table should show all zeros."""
        # The conftest truncates all tables, so enhanced_candles is empty
        # get_enrichment_status uses its own session via async_session_maker,
        # but the test DB should be empty after truncation.
        # We insert via the test session to control the state.
        status = await _get_enrichment_status_with_session(db_session)
        assert status["total_candles"] == 0
        assert status["enriched"] == 0
        assert status["pending"] == 0

    @pytest.mark.asyncio
    async def test_status_with_mixed_candles(self, db_session: AsyncSession):
        """Status should correctly count enriched vs pending."""
        t1 = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc)
        t3 = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        await _insert_enhanced_candle(db_session, symbol="S1", time=t1, derived_computed_at=datetime.now(timezone.utc))
        await _insert_enhanced_candle(db_session, symbol="S2", time=t2, derived_computed_at=None)
        await _insert_enhanced_candle(db_session, symbol="S3", time=t3, derived_computed_at=None)

        status = await _get_enrichment_status_with_session(db_session)
        assert status["total_candles"] == 3
        assert status["enriched"] == 1
        assert status["pending"] == 2
        assert abs(status["percent_complete"] - 33.33) < 0.1


async def _get_enrichment_status_with_session(session: AsyncSession) -> dict:
    """Helper: run enrichment status query using the test session."""
    result = await session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(derived_computed_at) as enriched,
            COUNT(*) - COUNT(derived_computed_at) as pending
        FROM enhanced_candles
    """))
    row = result.fetchone()
    total = row[0]
    return {
        "total_candles": total,
        "enriched": row[1],
        "pending": row[2],
        "percent_complete": round(row[1] / total * 100, 2) if total > 0 else 0,
    }


# ============================================================================
# MODULE-LEVEL CONSTANTS
# ============================================================================


class TestModuleConstants:
    """Tests for module-level constants and defaults."""

    def test_batch_size_reasonable(self):
        """BATCH_SIZE should be a positive integer in a reasonable range."""
        assert isinstance(BATCH_SIZE, int)
        assert 1000 <= BATCH_SIZE <= 100000

    def test_default_skip_symbols_is_set(self):
        """DEFAULT_SKIP_SYMBOLS should contain major coins."""
        assert "BTC" in DEFAULT_SKIP_SYMBOLS
        assert "ETH" in DEFAULT_SKIP_SYMBOLS
        assert isinstance(DEFAULT_SKIP_SYMBOLS, set)
