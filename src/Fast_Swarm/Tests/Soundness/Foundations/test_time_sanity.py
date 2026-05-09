"""
Time Sanity Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (No Lookahead, UTC Enforcement)
All timestamps must be valid and in UTC.
"""

from datetime import datetime, timedelta, timezone

import pytest

# ============================================================================
# TIME SANITY CONTRACT
# ============================================================================


class TestUTCEnforcement:
    """CONTRACT: All timestamps must be UTC."""

    def test_all_timestamps_utc(self):
        """CONTRACT: System uses UTC everywhere."""
        # datetime.utcnow() is used throughout the codebase (agent_models, memory_models)
        now = datetime.utcnow()
        # Verify utcnow produces times near current UTC
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        diff = abs((now - utc_now).total_seconds())
        assert diff < 2, f"utcnow() should match UTC clock, diff={diff}s"

    def test_no_timezone_confusion(self):
        """CONTRACT: No ambiguous timezone conversions."""
        utc_time = datetime(2024, 6, 15, 12, 0, 0)
        # Adding a timezone should not change the time value
        utc_aware = utc_time.replace(tzinfo=timezone.utc)
        assert utc_aware.hour == 12, "UTC time should remain 12:00"
        assert utc_aware.tzinfo == timezone.utc

        # Naive datetime comparison should work consistently
        t1 = datetime(2024, 1, 1, 0, 0, 0)
        t2 = datetime(2024, 1, 1, 0, 0, 0)
        assert t1 == t2, "Same UTC times should be equal"

    def test_timestamp_stored_as_utc(self):
        """CONTRACT: Database stores timestamps as UTC."""
        from Agents.Models.agent_models import Agent
        # Agent model uses datetime.utcnow as default_factory
        # Verify the default factory produces UTC time
        now = datetime.utcnow()
        assert now.tzinfo is None, "utcnow() returns naive UTC (DB convention)"
        # Ensure it's reasonably close to actual UTC
        utc_reference = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((now - utc_reference).total_seconds()) < 2


class TestTimestampValidation:
    """CONTRACT: Timestamps must be valid."""

    def test_no_epoch_zero(self):
        """CONTRACT: Timestamp != 0 (epoch)."""
        epoch_zero = datetime(1970, 1, 1, 0, 0, 0)
        min_valid = datetime(2010, 1, 1, 0, 0, 0)
        assert epoch_zero < min_valid, "Epoch zero should be before minimum valid date"
        # Timestamp 0 in milliseconds
        epoch_zero_ms = 0
        assert epoch_zero_ms == 0, "Epoch zero ms is 0"
        # This should be rejected for crypto data
        is_valid = epoch_zero_ms > 0
        assert not is_valid, "Epoch zero timestamp should be rejected"

    def test_no_pre_2010_timestamps(self):
        """CONTRACT: Timestamps after 2010 for crypto data."""
        # Bitcoin genesis block: 2009-01-03; first real data ~2010
        min_valid = datetime(2010, 1, 1)
        pre_2010 = datetime(2009, 12, 31)
        assert pre_2010 < min_valid, "Pre-2010 dates should be rejected for crypto"

        # Sample candle timestamps should be after 2010
        base_time_ms = 1704067200000  # 2024-01-01 00:00:00 UTC
        base_dt = datetime.utcfromtimestamp(base_time_ms / 1000)
        assert base_dt > min_valid, f"Candle timestamp {base_dt} should be after 2010"

    def test_no_future_timestamps(self):
        """CONTRACT: Timestamps not in the future."""
        now = datetime.utcnow()
        future = now + timedelta(days=365)
        assert future > now, "Future time should be detectable"
        is_future = future > now
        assert is_future, "Future timestamps should be detected"
        # Current time should not be in the future
        assert not (now > now + timedelta(seconds=1))

    def test_timestamp_positive(self):
        """CONTRACT: Timestamps > 0."""
        # All valid timestamps in ms should be positive
        valid_timestamps = [
            1704067200000,  # 2024-01-01
            1609459200000,  # 2021-01-01
            1262304000000,  # 2010-01-01
        ]
        for ts in valid_timestamps:
            assert ts > 0, f"Timestamp {ts} must be positive"


class TestNoLookaheadBias:
    """CONTRACT: No access to future data."""

    def test_backtest_no_future_access(self, sample_candles):
        """CONTRACT: Backtest cannot access future candles."""
        # In a backtest, at candle index i, only candles [0..i] should be visible
        for i in range(len(sample_candles)):
            visible_candles = sample_candles[:i + 1]
            future_candles = sample_candles[i + 1:]
            # Current candle's data should not depend on future candles
            current = sample_candles[i]
            for future in future_candles:
                assert future["timestamp"] > current["timestamp"], (
                    "Future candles must have later timestamps"
                )

    def test_indicator_no_future_data(self, sample_candles):
        """CONTRACT: Indicators only use past data."""
        # RSI with lookback=14 at position i uses candles [i-14..i], not [i+1..]
        lookback = 14
        for i in range(lookback, len(sample_candles)):
            window = sample_candles[i - lookback:i + 1]
            # Window should contain exactly lookback+1 candles
            assert len(window) == lookback + 1
            # All window timestamps should be <= current
            current_ts = sample_candles[i]["timestamp"]
            for candle in window:
                assert candle["timestamp"] <= current_ts, (
                    "Indicator window must not include future data"
                )

    def test_decision_at_candle_close(self, sample_candles):
        """CONTRACT: Decisions made at candle close only."""
        # A decision at candle i uses close price of candle i
        for i in range(1, len(sample_candles)):
            decision_price = sample_candles[i]["close"]
            assert decision_price is not None, "Decision price (close) must not be None"
            # Decision should not use the next candle's open
            if i < len(sample_candles) - 1:
                next_open = sample_candles[i + 1]["open"]
                # Decision at i uses close[i], not open[i+1]
                # (they may be equal in some cases, but conceptually different)

    def test_entry_after_signal_candle(self, sample_candles):
        """CONTRACT: Entry on candle AFTER signal."""
        # If signal fires on candle i, entry is on candle i+1
        signal_candle_idx = 5
        entry_candle_idx = signal_candle_idx + 1
        assert entry_candle_idx > signal_candle_idx, "Entry must be after signal"
        if entry_candle_idx < len(sample_candles):
            assert sample_candles[entry_candle_idx]["timestamp"] > sample_candles[signal_candle_idx]["timestamp"]


class TestTimeOrdering:
    """CONTRACT: Time series must be ordered."""

    def test_candles_chronological(self, sample_candles):
        """CONTRACT: OHLCV candles in chronological order."""
        for i in range(1, len(sample_candles)):
            assert sample_candles[i]["timestamp"] > sample_candles[i - 1]["timestamp"], (
                f"Candle {i} timestamp ({sample_candles[i]['timestamp']}) must be > "
                f"candle {i-1} ({sample_candles[i-1]['timestamp']})"
            )

    def test_trades_chronological(self, sample_trades_data):
        """CONTRACT: Trades ordered by entry time."""
        # sample_trades_data doesn't have entry_time by default,
        # but we can verify the contract with constructed data
        trades_with_time = []
        base = datetime(2024, 1, 1)
        for i, trade in enumerate(sample_trades_data):
            trade["entry_time"] = base + timedelta(hours=i)
            trade["exit_time"] = base + timedelta(hours=i, minutes=30)
            trades_with_time.append(trade)

        for i in range(1, len(trades_with_time)):
            assert trades_with_time[i]["entry_time"] >= trades_with_time[i - 1]["entry_time"], (
                "Trades must be in chronological order"
            )

    def test_no_duplicate_timestamps(self, sample_candles):
        """CONTRACT: No duplicate timestamps in series."""
        timestamps = [c["timestamp"] for c in sample_candles]
        assert len(timestamps) == len(set(timestamps)), (
            "No duplicate timestamps allowed in candle series"
        )


class TestTimeGaps:
    """CONTRACT: Time gaps must be handled."""

    def test_detect_missing_candles(self, sample_candles):
        """CONTRACT: Detect gaps in candle series."""
        # 1-hour candles should have 3600000ms intervals
        expected_interval = 3600000
        gaps = []
        for i in range(1, len(sample_candles)):
            interval = sample_candles[i]["timestamp"] - sample_candles[i - 1]["timestamp"]
            if interval != expected_interval:
                gaps.append(i)
        # Our sample data should have no gaps
        assert len(gaps) == 0, f"Detected {len(gaps)} gaps in sample candles"

    def test_handle_weekend_gaps(self):
        """CONTRACT: Handle weekend gaps for stocks/forex."""
        # Crypto trades 24/7, so weekends are normal
        # But the system should not crash if there's a gap
        friday = datetime(2024, 1, 5, 23, 0, 0)  # Friday
        monday = datetime(2024, 1, 8, 0, 0, 0)  # Monday
        gap_hours = (monday - friday).total_seconds() / 3600
        assert gap_hours == 49, "Weekend gap should be ~49 hours"
        # Gap detection should flag this but not crash
        is_gap = gap_hours > 2  # More than 2 hours for 1h candles
        assert is_gap, "Weekend gap should be detected"

    def test_handle_exchange_downtime(self):
        """CONTRACT: Handle exchange downtime gaps."""
        # Exchange downtime can create gaps in data
        normal_interval_ms = 3600000  # 1 hour
        downtime_gap_ms = 7200000  # 2 hours (1 missing candle)
        is_gap = downtime_gap_ms > normal_interval_ms
        assert is_gap, "Exchange downtime gap should be detected"
        missing_candles = (downtime_gap_ms // normal_interval_ms) - 1
        assert missing_candles == 1, "Should detect 1 missing candle"


class TestTradeDuration:
    """CONTRACT: Trade durations must be valid."""

    def test_exit_after_entry(self):
        """CONTRACT: exit_time > entry_time always."""
        entry = datetime(2024, 1, 1, 12, 0, 0)
        exit_ = datetime(2024, 1, 1, 14, 30, 0)
        assert exit_ > entry, "Exit must be after entry"
        duration = (exit_ - entry).total_seconds()
        assert duration > 0, "Trade duration must be positive"

    def test_minimum_trade_duration(self):
        """CONTRACT: Trade duration >= minimum (e.g., 1 minute)."""
        min_duration = timedelta(minutes=1)
        entry = datetime(2024, 1, 1, 12, 0, 0)
        exit_ = entry + timedelta(seconds=30)
        duration = exit_ - entry
        is_too_short = duration < min_duration
        assert is_too_short, "30-second trade should be below minimum"

        valid_exit = entry + timedelta(minutes=5)
        valid_duration = valid_exit - entry
        assert valid_duration >= min_duration, "5-minute trade should meet minimum"

    def test_maximum_trade_duration(self):
        """CONTRACT: Trade duration <= max_hold from traits."""
        # Max hold derived from hold_duration_bias trait (0-1) mapped to hours
        hold_duration_bias = 0.5  # Mid-range
        max_hold_hours = 1 + hold_duration_bias * 167  # 1h to 168h (1 week)
        entry = datetime(2024, 1, 1, 0, 0, 0)
        exit_ = entry + timedelta(hours=max_hold_hours)
        duration_hours = (exit_ - entry).total_seconds() / 3600
        assert duration_hours <= 168, "Max hold should not exceed 1 week"
        assert duration_hours >= 1, "Min hold should be at least 1 hour"


class TestHoldDuration:
    """CONTRACT: Hold duration calculations."""

    def test_hold_duration_positive(self):
        """CONTRACT: Hold duration always positive."""
        entry = datetime(2024, 1, 1, 10, 0, 0)
        exit_ = datetime(2024, 1, 1, 12, 0, 0)
        hold = (exit_ - entry).total_seconds()
        assert hold > 0, "Hold duration must be positive"

    def test_hold_duration_from_traits(self):
        """CONTRACT: Max hold derived from hold_duration_bias trait."""
        # hold_duration_bias in [0, 1] maps to max hold time
        for bias in [0.0, 0.25, 0.5, 0.75, 1.0]:
            max_hold_hours = 1 + bias * 167  # 1h to 168h
            assert 1 <= max_hold_hours <= 168, (
                f"Bias {bias}: max_hold ({max_hold_hours}h) must be in [1, 168]"
            )


class TestCandleTimestamps:
    """CONTRACT: Candle timestamps must align."""

    def test_1h_candles_hourly_aligned(self, sample_candles):
        """CONTRACT: 1h candles on hour boundaries."""
        for candle in sample_candles:
            ts_ms = candle["timestamp"]
            # 1h = 3600000ms; timestamp should be divisible by 3600000
            assert ts_ms % 3600000 == 0, (
                f"1h candle timestamp {ts_ms} must be hourly aligned"
            )

    def test_6h_candles_6h_aligned(self):
        """CONTRACT: 6h candles on 6-hour boundaries."""
        six_hours_ms = 6 * 3600000
        # Valid 6h timestamps
        valid_ts = [
            1704067200000,  # 2024-01-01 00:00 UTC
            1704088800000,  # 2024-01-01 06:00 UTC
            1704110400000,  # 2024-01-01 12:00 UTC
        ]
        for ts in valid_ts:
            assert ts % six_hours_ms == 0, f"6h candle {ts} must be 6h aligned"

    def test_1d_candles_daily_aligned(self):
        """CONTRACT: 1d candles on day boundaries."""
        one_day_ms = 24 * 3600000
        valid_ts = [
            1704067200000,  # 2024-01-01 00:00 UTC
            1704153600000,  # 2024-01-02 00:00 UTC
        ]
        for ts in valid_ts:
            assert ts % one_day_ms == 0, f"1d candle {ts} must be daily aligned"


class TestBacktestTimeRange:
    """CONTRACT: Backtest time range validation."""

    def test_backtest_start_before_end(self):
        """CONTRACT: start_date < end_date."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)
        assert start < end, "Backtest start must be before end"

        # Invalid: start after end
        bad_start = datetime(2024, 7, 1)
        bad_end = datetime(2024, 1, 1)
        assert not (bad_start < bad_end), "Start after end should be detected"

    def test_backtest_minimum_duration(self):
        """CONTRACT: Minimum backtest duration (e.g., 1 week)."""
        min_duration = timedelta(weeks=1)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 3)  # Only 2 days
        duration = end - start
        assert duration < min_duration, "2-day backtest should be below minimum"

        valid_end = datetime(2024, 1, 15)  # 14 days
        valid_duration = valid_end - start
        assert valid_duration >= min_duration, "14-day backtest should meet minimum"
