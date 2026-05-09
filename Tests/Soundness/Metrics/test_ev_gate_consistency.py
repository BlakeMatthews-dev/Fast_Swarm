"""
EDD: EV Gate Consistency Tests.

DOCUMENTS THE BUG: Two files have INCONSISTENT EV gate behavior.

1. local_agents/shared/fitness.py::expectancy_multiplier
   - EV <= 0 -> returns 0.0 (HARD GATE)
   - Agent gets 0 fitness if EV is non-positive

2. Agents/Services/fitness_service.py::calculate_ev_multiplier
   - EV <= 0 -> returns 0.35 (SOFT GATE)
   - Agent still gets 35% of raw fitness even with negative EV

The plan says: HARD GATE is correct. Soft gate is the bug.

These tests document current behavior, then assert the FIX once applied.
"""

import math
import pytest

from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier
from Fast_Swarm.Agents.Services.fitness_service import calculate_ev_multiplier


# =============================================================================
# Document the Bug: Inconsistency
# =============================================================================


class TestEVGateConsistency:
    """
    BUG FIXED: Both implementations now use V4 hard gate.
    Previous bug: fitness_service.py returned 0.35 for EV<=0 (soft gate).
    """

    def test_zero_ev_both_hard_gate(self):
        """FIXED: Same input (EV=0) produces same output: 0.0."""
        fitness_py = expectancy_multiplier(0.0)
        service_py = calculate_ev_multiplier(0.0)

        assert fitness_py == 0.0, f"fitness.py should return 0.0: {fitness_py}"
        assert service_py == 0.0, f"fitness_service.py should return 0.0: {service_py}"
        assert fitness_py == service_py  # Unified behavior

    def test_negative_ev_both_hard_gate(self):
        """FIXED: Negative EV -> 0.0 in both (losing agents get 0 fitness)."""
        fitness_py = expectancy_multiplier(-5.0)
        service_py = calculate_ev_multiplier(-5.0)

        assert fitness_py == 0.0
        assert service_py == 0.0  # Fixed: no more 35% for losers

    def test_slightly_positive_ev(self):
        """Just above zero: both use same V4 interpolation."""
        fitness_py = expectancy_multiplier(0.01)
        service_py = calculate_ev_multiplier(0.01)

        # Both use V4 breakpoints: (0.0001, 0.35) to (1.0, 0.8)
        assert fitness_py > 0.0
        assert fitness_py < 0.8
        assert fitness_py == service_py  # Unified


# =============================================================================
# Shared Behavior (both agree)
# =============================================================================


class TestEVGateAgreement:
    """Cases where both implementations agree."""

    def test_ev_1_percent(self):
        """EV=1%: both should give ~0.8."""
        fitness_py = expectancy_multiplier(1.0)
        service_py = calculate_ev_multiplier(1.0)

        assert abs(fitness_py - 0.8) < 0.01, f"fitness.py at 1%: {fitness_py}"
        assert abs(service_py - 0.8) < 0.01, f"service at 1%: {service_py}"

    def test_ev_3_percent(self):
        """EV=3%: both should give ~1.2."""
        fitness_py = expectancy_multiplier(3.0)
        service_py = calculate_ev_multiplier(3.0)

        assert abs(fitness_py - 1.2) < 0.01
        assert abs(service_py - 1.2) < 0.01

    def test_ev_9_percent(self):
        """EV=9%: both should cap at 1.5."""
        fitness_py = expectancy_multiplier(9.0)
        service_py = calculate_ev_multiplier(9.0)

        assert abs(fitness_py - 1.5) < 0.01
        assert abs(service_py - 1.5) < 0.01

    def test_ev_above_9(self):
        """EV>9%: both cap at 1.5."""
        fitness_py = expectancy_multiplier(20.0)
        service_py = calculate_ev_multiplier(20.0)

        assert fitness_py == 1.5
        assert service_py == 1.5

    def test_monotonically_increasing(self):
        """Both should be monotonically increasing for positive EV."""
        ev_values = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 9.0]

        prev_fitness = 0.0
        prev_service = 0.0

        for ev in ev_values:
            f = expectancy_multiplier(ev)
            s = calculate_ev_multiplier(ev)

            assert f >= prev_fitness, f"fitness.py not monotonic at EV={ev}"
            assert s >= prev_service, f"service not monotonic at EV={ev}"

            prev_fitness = f
            prev_service = s


# =============================================================================
# fitness.py Special Cases (NaN, Inf)
# =============================================================================


class TestEVGateSpecialValues:
    """fitness.py handles NaN/Inf; service.py may not."""

    def test_nan_returns_zero(self):
        """NaN EV -> 0.0 (gate closed)."""
        result = expectancy_multiplier(float('nan'))
        assert result == 0.0

    def test_negative_inf(self):
        """Negative infinity -> 0.0."""
        result = expectancy_multiplier(float('-inf'))
        assert result == 0.0

    def test_positive_inf(self):
        """Positive infinity -> 0.0 (non-finite data rejected)."""
        result = expectancy_multiplier(float('inf'))
        assert result == 0.0


# =============================================================================
# Interpolation Accuracy
# =============================================================================


class TestEVGateInterpolation:
    """Test interpolation between breakpoints."""

    def test_midpoint_0_to_1(self):
        """EV=0.5: should be between 0.35 and 0.8."""
        f = expectancy_multiplier(0.5)
        s = calculate_ev_multiplier(0.5)

        # Midpoint of (0.0001->0.35, 1.0->0.8) ~ 0.575
        assert 0.35 < f < 0.8, f"fitness.py at 0.5%: {f}"
        assert 0.35 < s < 0.8, f"service at 0.5%: {s}"

    def test_midpoint_1_to_3(self):
        """EV=2%: should be between 0.8 and 1.2."""
        f = expectancy_multiplier(2.0)
        s = calculate_ev_multiplier(2.0)

        assert 0.8 < f < 1.2, f"fitness.py at 2%: {f}"
        assert 0.8 < s < 1.2, f"service at 2%: {s}"

    def test_midpoint_3_to_9(self):
        """EV=6%: should be between 1.2 and 1.5."""
        f = expectancy_multiplier(6.0)
        s = calculate_ev_multiplier(6.0)

        assert 1.2 < f < 1.5, f"fitness.py at 6%: {f}"
        assert 1.2 < s < 1.5, f"service at 6%: {s}"
