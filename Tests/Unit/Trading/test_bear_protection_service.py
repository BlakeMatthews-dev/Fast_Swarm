"""
Bear Protection Service Unit Tests.

Tests for the supreme risk layer with VETO EXIT POWER.
Source: src/Fast_Swarm/Infrastructure/Services/bear_protection_service.py

No DB needed - this service is pure in-memory state machine
operating on MarketState dataclasses.
"""

from datetime import datetime, timezone

import pytest

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService,
    MarketState,
    Regime,
    RegimeConfig,
    RegimeState,
    get_bear_protection,
)


# ============================================================================
# HELPERS
# ============================================================================


def make_market_state(
    symbol="BTC/USDT",
    tf_1h=(None, None, None),
    tf_4h=(None, None, None),
    tf_1d=(None, None, None),
    time=None,
):
    """Create a MarketState with given timeframe derivatives.

    Each tf tuple is (velocity, acceleration, adx_jerk).
    """
    time = time or datetime.now(timezone.utc)
    return MarketState(
        time=time,
        symbol=symbol,
        tf_1h_vel=tf_1h[0],
        tf_1h_acc=tf_1h[1],
        tf_1h_adx_jerk=tf_1h[2],
        tf_4h_vel=tf_4h[0],
        tf_4h_acc=tf_4h[1],
        tf_4h_adx_jerk=tf_4h[2],
        tf_1d_vel=tf_1d[0],
        tf_1d_acc=tf_1d[1],
        tf_1d_adx_jerk=tf_1d[2],
    )


def danger_tf():
    """Return (vel, acc, jerk) that triggers DEFENSIVE exit signal.

    v3 AJ config: acc < -1.5 AND adx_jerk < -0.5
    """
    return (-2.0, -3.0, -1.0)


def opportunity_tf():
    """Return (vel, acc, jerk) that triggers AGGRESSIVE entry signal.

    vel < -0.5 AND acc > 1.5
    """
    return (-1.0, 2.0, 0.5)


def neutral_tf():
    """Return derivatives that trigger neither signal."""
    return (0.0, 0.0, 0.0)


# ============================================================================
# DEFAULT REGIME (NEUTRAL)
# ============================================================================


class TestDefaultRegime:
    """CONTRACT: Service starts in NEUTRAL regime."""

    @pytest.mark.critical
    def test_initial_regime_is_neutral(self):
        """Fresh service starts in NEUTRAL."""
        svc = BearProtectionService()
        assert svc.get_regime() == Regime.NEUTRAL

    @pytest.mark.critical
    def test_neutral_position_limit(self):
        """NEUTRAL regime allows 65% position."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=neutral_tf(), tf_4h=neutral_tf(), tf_1d=neutral_tf())
        result = svc.evaluate(state)

        assert result.regime == Regime.NEUTRAL
        assert result.max_position == pytest.approx(0.65)

    @pytest.mark.critical
    def test_neutral_no_signals_active(self):
        """NEUTRAL state has no exit or entry signals."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=neutral_tf(), tf_4h=neutral_tf(), tf_1d=neutral_tf())
        result = svc.evaluate(state)

        assert result.exit_signal_active is False
        assert result.entry_signal_active is False


# ============================================================================
# DEFENSIVE REGIME
# ============================================================================


class TestDefensiveRegime:
    """CONTRACT: DEFENSIVE triggers on multi-TF danger signals with 0% position."""

    @pytest.mark.critical
    def test_two_tf_danger_triggers_defensive(self):
        """2 timeframes with danger signals -> DEFENSIVE."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=danger_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE
        assert result.exit_signal_active is True

    @pytest.mark.critical
    def test_three_tf_danger_triggers_defensive(self):
        """3 timeframes with danger signals -> DEFENSIVE."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=danger_tf(),
            tf_1d=danger_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE
        assert result.exit_signal_active is True

    @pytest.mark.critical
    def test_defensive_position_is_zero(self):
        """DEFENSIVE regime sets max position to 0% (full exit)."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        result = svc.evaluate(state)

        assert result.max_position == pytest.approx(0.0)

    @pytest.mark.critical
    def test_single_tf_danger_does_not_trigger_defensive(self):
        """Only 1 TF with danger signal is NOT enough (need 2+)."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.NEUTRAL
        assert result.exit_signal_active is False

    @pytest.mark.critical
    def test_defensive_triggered_by_string(self):
        """Trigger string contains 'exit:' and the timeframe names."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        result = svc.evaluate(state)

        assert "exit:" in result.triggered_by
        assert "1h" in result.triggered_by
        assert "4h" in result.triggered_by


# ============================================================================
# AGGRESSIVE REGIME
# ============================================================================


class TestAggressiveRegime:
    """CONTRACT: AGGRESSIVE triggers on single TF opportunity signal."""

    @pytest.mark.critical
    def test_one_tf_opportunity_triggers_aggressive(self):
        """1 timeframe with opportunity signal -> AGGRESSIVE."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=opportunity_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.AGGRESSIVE
        assert result.entry_signal_active is True

    @pytest.mark.critical
    def test_aggressive_position_limit(self):
        """AGGRESSIVE regime allows 90% position."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=opportunity_tf())
        result = svc.evaluate(state)

        assert result.max_position == pytest.approx(0.90)

    @pytest.mark.critical
    def test_aggressive_trigger_string(self):
        """Trigger string contains 'entry:' and the timeframe name."""
        svc = BearProtectionService()
        state = make_market_state(tf_4h=opportunity_tf())
        result = svc.evaluate(state)

        assert "entry:" in result.triggered_by
        assert "4h" in result.triggered_by


# ============================================================================
# REGIME PRIORITY: DEFENSIVE OVERRIDES AGGRESSIVE
# ============================================================================


class TestRegimePriority:
    """CONTRACT: DEFENSIVE takes priority when both signals fire."""

    @pytest.mark.critical
    def test_defensive_wins_over_aggressive(self):
        """When exit and entry signals both fire, DEFENSIVE wins."""
        svc = BearProtectionService()
        # 2 TFs danger (DEFENSIVE) + 1 TF opportunity (AGGRESSIVE)
        state = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=danger_tf(),
            tf_1d=opportunity_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE
        assert result.exit_signal_active is True


# ============================================================================
# REGIME STICKINESS
# ============================================================================


class TestRegimeStickiness:
    """CONTRACT: Regimes are sticky until opposite signal or all-clear."""

    @pytest.mark.critical
    def test_defensive_stays_with_one_tf_remaining(self):
        """DEFENSIVE persists if danger drops to 1 TF (no opposite signal)."""
        svc = BearProtectionService()

        # Enter DEFENSIVE
        state1 = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        svc.evaluate(state1)
        assert svc.get_regime() == Regime.DEFENSIVE

        # Only 1 TF still dangerous - not enough to re-trigger, but no
        # all-clear either (1 exit signal still present)
        state2 = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state2)

        # Regime stays DEFENSIVE because it's sticky
        assert result.regime == Regime.DEFENSIVE

    @pytest.mark.critical
    def test_all_clear_returns_to_neutral(self):
        """DEFENSIVE -> NEUTRAL when all signals clear."""
        svc = BearProtectionService()

        # Enter DEFENSIVE
        state1 = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        svc.evaluate(state1)
        assert svc.get_regime() == Regime.DEFENSIVE

        # All clear
        state2 = make_market_state(
            tf_1h=neutral_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state2)

        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_aggressive_to_neutral_on_all_clear(self):
        """AGGRESSIVE -> NEUTRAL when all signals clear."""
        svc = BearProtectionService()

        # Enter AGGRESSIVE
        state1 = make_market_state(tf_1h=opportunity_tf())
        svc.evaluate(state1)
        assert svc.get_regime() == Regime.AGGRESSIVE

        # All clear
        state2 = make_market_state(
            tf_1h=neutral_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )
        result = svc.evaluate(state2)

        assert result.regime == Regime.NEUTRAL


# ============================================================================
# VETO EXIT POWER (should_force_exit)
# ============================================================================


class TestVetoExitPower:
    """CONTRACT: should_force_exit returns True only in DEFENSIVE with active exit."""

    @pytest.mark.critical
    def test_force_exit_in_defensive(self):
        """should_force_exit is True when DEFENSIVE + exit signals active."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())

        assert svc.should_force_exit(state) is True

    @pytest.mark.critical
    def test_no_force_exit_in_neutral(self):
        """should_force_exit is False in NEUTRAL."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=neutral_tf(),
            tf_4h=neutral_tf(),
            tf_1d=neutral_tf(),
        )

        assert svc.should_force_exit(state) is False

    @pytest.mark.critical
    def test_no_force_exit_in_aggressive(self):
        """should_force_exit is False in AGGRESSIVE."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=opportunity_tf())

        assert svc.should_force_exit(state) is False


# ============================================================================
# POSITION LIMIT CALCULATION
# ============================================================================


class TestPositionLimit:
    """CONTRACT: get_position_limit returns correct dollar amounts."""

    @pytest.mark.critical
    def test_neutral_position_limit_dollars(self):
        """NEUTRAL: 65% of capital."""
        svc = BearProtectionService()
        assert svc.get_position_limit(10000.0) == pytest.approx(6500.0)

    @pytest.mark.critical
    def test_defensive_position_limit_dollars(self):
        """DEFENSIVE: 0% of capital."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        svc.evaluate(state)

        assert svc.get_position_limit(10000.0) == pytest.approx(0.0)

    @pytest.mark.critical
    def test_aggressive_position_limit_dollars(self):
        """AGGRESSIVE: 90% of capital."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=opportunity_tf())
        svc.evaluate(state)

        assert svc.get_position_limit(10000.0) == pytest.approx(9000.0)


# ============================================================================
# EXIT SIGNAL THRESHOLD LOGIC (v3 AJ CONFIG)
# ============================================================================


class TestExitSignalThresholds:
    """CONTRACT: v3 AJ config uses acc + jerk only (velocity ignored)."""

    @pytest.mark.critical
    def test_exit_ignores_velocity(self):
        """Even with positive velocity, exit fires if acc+jerk thresholds met."""
        svc = BearProtectionService()
        # vel=+5 (strong upward velocity), but acc and jerk are dangerous
        state = make_market_state(
            tf_1h=(5.0, -3.0, -1.0),
            tf_4h=(5.0, -3.0, -1.0),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE

    @pytest.mark.critical
    def test_exit_needs_both_acc_and_jerk(self):
        """Exit requires BOTH acc < -1.5 AND jerk < -0.5."""
        svc = BearProtectionService()

        # Only acc bad, jerk OK
        state1 = make_market_state(
            tf_1h=(0.0, -3.0, 0.0),
            tf_4h=(0.0, -3.0, 0.0),
        )
        r1 = svc.evaluate(state1)
        assert r1.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_exit_needs_jerk_too(self):
        """Jerk alone (without bad acc) does not trigger exit."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=(0.0, 0.0, -2.0),
            tf_4h=(0.0, 0.0, -2.0),
        )
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_exit_at_exact_thresholds_does_not_fire(self):
        """At exact threshold values (-1.5 acc, -0.5 jerk) exit does NOT fire (strict <)."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=(0.0, -1.5, -0.5),
            tf_4h=(0.0, -1.5, -0.5),
        )
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_exit_just_beyond_thresholds_fires(self):
        """Just beyond thresholds (-1.51, -0.51) exit fires."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=(0.0, -1.51, -0.51),
            tf_4h=(0.0, -1.51, -0.51),
        )
        result = svc.evaluate(state)
        assert result.regime == Regime.DEFENSIVE


# ============================================================================
# ENTRY SIGNAL THRESHOLD LOGIC
# ============================================================================


class TestEntrySignalThresholds:
    """CONTRACT: Entry (AGGRESSIVE) needs vel < -0.5 AND acc > 1.5."""

    @pytest.mark.critical
    def test_entry_needs_both_vel_and_acc(self):
        """Entry needs BOTH vel < -0.5 AND acc > 1.5."""
        svc = BearProtectionService()
        # vel OK but acc not enough
        state = make_market_state(tf_1h=(-1.0, 1.0, 0.0))
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_entry_vel_alone_insufficient(self):
        """Vel < -0.5 alone doesn't trigger AGGRESSIVE."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=(-2.0, 0.0, 0.0))
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_entry_at_exact_thresholds_does_not_fire(self):
        """At exact threshold values (-0.5 vel, 1.5 acc) entry does NOT fire."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=(0.0, -0.5, 1.5))
        result = svc.evaluate(state)
        # vel=-0.5 is NOT < -0.5, acc=1.5 is NOT > 1.5
        assert result.regime == Regime.NEUTRAL


# ============================================================================
# NONE VALUES (MISSING DATA)
# ============================================================================


class TestMissingData:
    """CONTRACT: None values don't trigger any signals."""

    @pytest.mark.critical
    def test_all_none_stays_neutral(self):
        """All None derivatives -> no signals -> NEUTRAL."""
        svc = BearProtectionService()
        state = make_market_state()  # All None by default
        result = svc.evaluate(state)

        assert result.regime == Regime.NEUTRAL
        assert result.exit_signal_active is False
        assert result.entry_signal_active is False

    @pytest.mark.critical
    def test_partial_none_exit_does_not_fire(self):
        """Exit signal with None jerk doesn't fire."""
        svc = BearProtectionService()
        state = make_market_state(
            tf_1h=(0.0, -3.0, None),
            tf_4h=(0.0, -3.0, None),
        )
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_partial_none_entry_does_not_fire(self):
        """Entry signal with None vel doesn't fire."""
        svc = BearProtectionService()
        state = make_market_state(tf_1h=(None, 3.0, 0.0))
        result = svc.evaluate(state)
        assert result.regime == Regime.NEUTRAL


# ============================================================================
# CUSTOM CONFIG
# ============================================================================


class TestCustomConfig:
    """CONTRACT: Custom RegimeConfig overrides defaults."""

    @pytest.mark.critical
    def test_custom_defensive_max(self):
        """Custom defensive_max is respected."""
        config = RegimeConfig(defensive_max=0.10)
        svc = BearProtectionService(config=config)
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        result = svc.evaluate(state)

        assert result.max_position == pytest.approx(0.10)

    @pytest.mark.critical
    def test_custom_tf_confirm_count(self):
        """Custom defensive_tf_confirm=3 requires all 3 TFs."""
        config = RegimeConfig(defensive_tf_confirm=3)
        svc = BearProtectionService(config=config)

        # Only 2 TFs dangerous - not enough with confirm=3
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        result = svc.evaluate(state)

        assert result.regime == Regime.NEUTRAL

    @pytest.mark.critical
    def test_custom_tf_confirm_3_all_danger(self):
        """With confirm=3, all 3 TFs dangerous triggers DEFENSIVE."""
        config = RegimeConfig(defensive_tf_confirm=3)
        svc = BearProtectionService(config=config)

        state = make_market_state(
            tf_1h=danger_tf(),
            tf_4h=danger_tf(),
            tf_1d=danger_tf(),
        )
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE


# ============================================================================
# REGIME DURATION
# ============================================================================


class TestRegimeDuration:
    """CONTRACT: get_regime_duration_hours tracks time in regime."""

    @pytest.mark.critical
    def test_duration_is_non_negative(self):
        """Duration is always >= 0."""
        svc = BearProtectionService()
        assert svc.get_regime_duration_hours() >= 0.0

    @pytest.mark.critical
    def test_regime_change_resets_duration(self):
        """Transitioning to a new regime resets the since timestamp."""
        svc = BearProtectionService()

        # Trigger DEFENSIVE
        state = make_market_state(tf_1h=danger_tf(), tf_4h=danger_tf())
        result = svc.evaluate(state)

        assert result.regime == Regime.DEFENSIVE
        # Duration should be very small (just changed)
        assert svc.get_regime_duration_hours() < 0.01


# ============================================================================
# SINGLETON
# ============================================================================


class TestBearProtectionSingleton:
    """CONTRACT: get_bear_protection returns a singleton."""

    @pytest.mark.critical
    def test_singleton_returns_same_instance(self):
        """Multiple calls return the same object."""
        svc1 = get_bear_protection()
        svc2 = get_bear_protection()
        assert svc1 is svc2
