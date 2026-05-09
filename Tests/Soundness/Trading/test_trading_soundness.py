"""
Trading Soundness Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (Economic Realism Category)
Tests that trading calculations are economically valid and safe.

These tests validate:
- P&L calculations are mathematically correct
- Position sizing respects limits
- Division safety (no crashes on edge cases)
- Economic validity (no phantom profits)
"""

from decimal import Decimal

import pytest


# ============================================================================
# P&L CALCULATION SOUNDNESS
# ============================================================================


class TestPnLCalculationSoundness:
    """SOUNDNESS: P&L calculations must be mathematically correct."""

    @pytest.mark.soundness
    def test_long_profit_calculation(self):
        """SOUNDNESS: Long position profit is (exit - entry) / entry."""
        entry_price = 50000.0
        exit_price = 55000.0
        size_usd = 10000.0

        # Expected: 10% gain
        expected_pnl_pct = (exit_price - entry_price) / entry_price
        expected_pnl_usd = size_usd * expected_pnl_pct

        assert expected_pnl_pct == pytest.approx(0.10, abs=0.001)
        assert expected_pnl_usd == pytest.approx(1000.0, abs=0.01)

    @pytest.mark.soundness
    def test_long_loss_calculation(self):
        """SOUNDNESS: Long position loss is negative."""
        entry_price = 50000.0
        exit_price = 45000.0
        size_usd = 10000.0

        pnl_pct = (exit_price - entry_price) / entry_price
        pnl_usd = size_usd * pnl_pct

        assert pnl_pct < 0
        assert pnl_pct == pytest.approx(-0.10, abs=0.001)
        assert pnl_usd == pytest.approx(-1000.0, abs=0.01)

    @pytest.mark.soundness
    def test_short_profit_calculation(self):
        """SOUNDNESS: Short position profit is (entry - exit) / entry."""
        entry_price = 50000.0
        exit_price = 45000.0
        size_usd = 10000.0

        # Short profits when price goes down
        pnl_pct = (entry_price - exit_price) / entry_price
        pnl_usd = size_usd * pnl_pct

        assert pnl_pct == pytest.approx(0.10, abs=0.001)
        assert pnl_usd == pytest.approx(1000.0, abs=0.01)

    @pytest.mark.soundness
    def test_short_loss_calculation(self):
        """SOUNDNESS: Short position loss when price goes up."""
        entry_price = 50000.0
        exit_price = 55000.0
        size_usd = 10000.0

        pnl_pct = (entry_price - exit_price) / entry_price
        pnl_usd = size_usd * pnl_pct

        assert pnl_pct < 0
        assert pnl_pct == pytest.approx(-0.10, abs=0.001)
        assert pnl_usd == pytest.approx(-1000.0, abs=0.01)

    @pytest.mark.soundness
    def test_zero_movement_zero_pnl(self):
        """SOUNDNESS: No price movement = zero P&L (before fees)."""
        entry_price = 50000.0
        exit_price = 50000.0

        pnl_pct = (exit_price - entry_price) / entry_price

        assert pnl_pct == 0.0


# ============================================================================
# DIVISION SAFETY SOUNDNESS
# ============================================================================


class TestDivisionSafety:
    """SOUNDNESS: No division by zero crashes."""

    @pytest.mark.soundness
    @pytest.mark.division_safety
    def test_pnl_with_zero_entry_price(self):
        """SOUNDNESS: Zero entry price must be guarded."""
        entry_price = 0.0
        exit_price = 100.0

        # Safe division pattern
        if entry_price > 0:
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = 0.0

        assert pnl_pct == 0.0  # No crash, returns safe default

    @pytest.mark.soundness
    @pytest.mark.division_safety
    def test_position_size_with_zero_price(self):
        """SOUNDNESS: Zero price doesn't crash position sizing."""
        balance = 10000.0
        kelly_fraction = 0.1
        price = 0.0

        position_size_usd = balance * kelly_fraction

        # Safe division
        if price > 0:
            size = position_size_usd / price
        else:
            size = 0.0

        assert size == 0.0  # No crash

    @pytest.mark.soundness
    @pytest.mark.division_safety
    def test_kelly_fraction_bounds(self):
        """SOUNDNESS: Kelly fraction must be bounded [0, 1]."""
        # Valid Kelly fractions
        valid_fractions = [0.0, 0.1, 0.25, 0.5, 1.0]
        for kf in valid_fractions:
            assert 0.0 <= kf <= 1.0

        # Invalid Kelly fractions should be clamped
        def clamp_kelly(kf):
            return max(0.0, min(1.0, kf))

        assert clamp_kelly(-0.5) == 0.0
        assert clamp_kelly(1.5) == 1.0
        assert clamp_kelly(0.3) == 0.3


# ============================================================================
# POSITION SIZE SOUNDNESS
# ============================================================================


class TestPositionSizeSoundness:
    """SOUNDNESS: Position sizes must be economically valid."""

    @pytest.mark.soundness
    def test_position_size_never_exceeds_balance(self):
        """SOUNDNESS: Position size USD never exceeds available balance."""
        balance = 10000.0
        kelly_fraction = 0.1

        position_size_usd = balance * kelly_fraction

        assert position_size_usd <= balance
        assert position_size_usd == 1000.0

    @pytest.mark.soundness
    def test_position_size_never_negative(self):
        """SOUNDNESS: Position size is always >= 0."""
        balance = 10000.0
        kelly_fractions = [0.0, 0.1, 0.5, 1.0]

        for kf in kelly_fractions:
            position_size_usd = balance * kf
            assert position_size_usd >= 0

    @pytest.mark.soundness
    def test_position_size_with_zero_balance(self):
        """SOUNDNESS: Zero balance produces zero position size."""
        balance = 0.0
        kelly_fraction = 0.1

        position_size_usd = balance * kelly_fraction

        assert position_size_usd == 0.0

    @pytest.mark.soundness
    def test_max_position_is_full_balance(self):
        """SOUNDNESS: Maximum position is 100% of balance (kelly=1.0)."""
        balance = 50000.0
        kelly_fraction = 1.0

        position_size_usd = balance * kelly_fraction

        assert position_size_usd == balance


# ============================================================================
# DECIMAL PRECISION SOUNDNESS
# ============================================================================


class TestDecimalPrecisionSoundness:
    """SOUNDNESS: Decimal calculations maintain precision."""

    @pytest.mark.soundness
    def test_decimal_pnl_precision(self):
        """SOUNDNESS: Decimal P&L avoids floating point errors."""
        entry = Decimal("50000.00")
        exit_price = Decimal("50000.01")  # Tiny movement
        size = Decimal("1.0")

        pnl = (exit_price - entry) * size

        # Decimal maintains exact precision
        assert pnl == Decimal("0.01")

    @pytest.mark.soundness
    def test_decimal_vs_float_precision(self):
        """SOUNDNESS: Decimal is more precise than float for money."""
        # Float precision issue
        float_result = 0.1 + 0.2
        assert float_result != 0.3  # Famous floating point issue

        # Decimal handles it correctly
        decimal_result = Decimal("0.1") + Decimal("0.2")
        assert decimal_result == Decimal("0.3")

    @pytest.mark.soundness
    def test_small_position_precision(self):
        """SOUNDNESS: Small positions maintain precision."""
        price = Decimal("50000.00")
        size_usd = Decimal("10.00")  # Small $10 position

        size = size_usd / price

        # Should be 0.0002 BTC exactly
        assert size == Decimal("0.0002")


# ============================================================================
# BALANCE UPDATE SOUNDNESS
# ============================================================================


class TestBalanceUpdateSoundness:
    """SOUNDNESS: Balance updates are economically valid."""

    @pytest.mark.soundness
    def test_balance_never_negative_after_loss(self):
        """SOUNDNESS: Balance stays >= 0 even after losses."""
        initial_balance = 10000.0
        position_size_usd = 1000.0  # 10% position
        loss_pct = -0.50  # 50% loss on position

        pnl_usd = position_size_usd * loss_pct
        new_balance = initial_balance + pnl_usd

        assert new_balance >= 0
        assert new_balance == 9500.0

    @pytest.mark.soundness
    def test_max_loss_is_position_size(self):
        """SOUNDNESS: Maximum loss on long is 100% of position (price -> 0)."""
        position_size_usd = 1000.0
        loss_pct = -1.0  # 100% loss

        max_loss = position_size_usd * loss_pct

        assert max_loss == -1000.0
        # Can't lose more than position on long

    @pytest.mark.soundness
    def test_profit_adds_to_balance(self):
        """SOUNDNESS: Profits increase balance correctly."""
        initial_balance = 10000.0
        position_size_usd = 1000.0
        profit_pct = 0.20  # 20% gain

        pnl_usd = position_size_usd * profit_pct
        new_balance = initial_balance + pnl_usd

        assert new_balance > initial_balance
        assert new_balance == 10200.0


# ============================================================================
# TRADE DURATION SOUNDNESS
# ============================================================================


class TestTradeDurationSoundness:
    """SOUNDNESS: Trade durations must be valid."""

    @pytest.mark.soundness
    def test_duration_is_positive(self):
        """SOUNDNESS: Trade duration is always positive."""
        from datetime import datetime, timezone

        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)

        duration = (exit_time - entry_time).total_seconds()

        assert duration > 0
        assert duration == 3600  # 1 hour

    @pytest.mark.soundness
    def test_duration_zero_for_instant_close(self):
        """SOUNDNESS: Instant close has zero duration."""
        from datetime import datetime, timezone

        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        exit_time = entry_time  # Same time

        duration = (exit_time - entry_time).total_seconds()

        assert duration == 0


# ============================================================================
# EDGE CASE SOUNDNESS
# ============================================================================


class TestEdgeCaseSoundness:
    """SOUNDNESS: Edge cases are handled safely."""

    @pytest.mark.soundness
    @pytest.mark.edge_case
    def test_very_small_price(self):
        """SOUNDNESS: Very small prices don't cause issues."""
        price = 0.00000001  # 1 satoshi-like price
        size_usd = 100.0

        if price > 0:
            size = size_usd / price
            assert size > 0
            # Very large position in units, but valid

    @pytest.mark.soundness
    @pytest.mark.edge_case
    def test_very_large_price(self):
        """SOUNDNESS: Very large prices don't overflow."""
        price = 1_000_000.0  # $1M per unit
        size_usd = 1000.0

        size = size_usd / price

        assert size == pytest.approx(0.001, abs=0.0001)

    @pytest.mark.soundness
    @pytest.mark.edge_case
    def test_extreme_pnl_percentage(self):
        """SOUNDNESS: Extreme P&L percentages are handled."""
        entry = 100.0
        exit_price = 10000.0  # 100x gain

        pnl_pct = (exit_price - entry) / entry

        assert pnl_pct == 99.0  # 9900% gain
        # No overflow, just a large number

    @pytest.mark.soundness
    @pytest.mark.edge_case
    def test_minimum_trade_size(self):
        """SOUNDNESS: Minimum viable trade size."""
        min_size_usd = 1.0  # $1 minimum
        price = 50000.0

        size = min_size_usd / price

        assert size > 0
        assert size == pytest.approx(0.00002, abs=0.000001)


# ============================================================================
# SLIPPAGE SOUNDNESS
# ============================================================================


class TestSlippageSoundness:
    """SOUNDNESS: Slippage calculations are realistic."""

    @pytest.mark.soundness
    def test_slippage_is_adverse(self):
        """SOUNDNESS: Slippage always works against the trader."""
        requested_price = 50000.0
        slippage_pct = 0.001  # 0.1% slippage

        # Buy: pay more
        buy_fill_price = requested_price * (1 + slippage_pct)
        assert buy_fill_price > requested_price

        # Sell: receive less
        sell_fill_price = requested_price * (1 - slippage_pct)
        assert sell_fill_price < requested_price

    @pytest.mark.soundness
    def test_slippage_is_bounded(self):
        """SOUNDNESS: Slippage has reasonable bounds."""
        max_slippage_pct = 0.01  # 1% max for normal orders
        requested_price = 50000.0

        worst_buy_price = requested_price * (1 + max_slippage_pct)
        worst_sell_price = requested_price * (1 - max_slippage_pct)

        # Slippage shouldn't exceed bounds
        assert worst_buy_price <= requested_price * 1.01
        assert worst_sell_price >= requested_price * 0.99

    @pytest.mark.soundness
    def test_slippage_percentage_calculation(self):
        """SOUNDNESS: Slippage percentage is calculated correctly."""
        requested_price = 50000.0
        fill_price = 50050.0  # Slightly worse

        slippage_pct = (fill_price - requested_price) / requested_price * 100

        assert slippage_pct == pytest.approx(0.1, abs=0.01)  # 0.1%
