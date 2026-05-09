"""
TDD: Normalization Function Tests.

Defines the API contract for src/Fast_Swarm/Metrics/normalization.py.
Three normalization curves:
1. Sigmoid: smooth S-curve for bounded values (win rate)
2. Logarithmic: penalizes bad values heavily (drawdown)
3. Diminishing returns: rewards improvement less at high end (Sortino)
"""

import math

import pytest

from Fast_Swarm.Metrics.normalization import (
    diminishing_returns,
    logarithmic_penalty,
    sigmoid_normalize,
)


# =============================================================================
# Sigmoid Normalization
# =============================================================================


class TestSigmoidNormalize:
    """Smooth S-curve mapping to [0, 1]."""

    def test_output_bounded_0_1(self):
        """Always in [0, 1]."""
        for val in [-100, -1, 0, 0.5, 1, 100]:
            result = sigmoid_normalize(val, center=0.5, steepness=10.0)
            assert 0.0 <= result <= 1.0, f"val={val}, result={result}"

    def test_center_gives_half(self):
        """Value at center -> 0.5."""
        result = sigmoid_normalize(0.5, center=0.5, steepness=10.0)
        assert abs(result - 0.5) < 0.01

    def test_above_center_above_half(self):
        """Values above center -> above 0.5."""
        result = sigmoid_normalize(0.7, center=0.5, steepness=10.0)
        assert result > 0.5

    def test_below_center_below_half(self):
        """Values below center -> below 0.5."""
        result = sigmoid_normalize(0.3, center=0.5, steepness=10.0)
        assert result < 0.5

    def test_steepness_controls_transition(self):
        """Higher steepness -> sharper transition."""
        soft = sigmoid_normalize(0.6, center=0.5, steepness=5.0)
        sharp = sigmoid_normalize(0.6, center=0.5, steepness=20.0)
        assert sharp > soft  # Same value, sharper -> further from 0.5

    def test_monotonically_increasing(self):
        """Higher values -> higher output."""
        values = [0.1, 0.3, 0.5, 0.7, 0.9]
        results = [sigmoid_normalize(v, center=0.5, steepness=10.0) for v in values]
        for i in range(len(results) - 1):
            assert results[i + 1] > results[i]

    def test_extreme_low_near_zero(self):
        """Very low value -> near 0."""
        result = sigmoid_normalize(-10.0, center=0.5, steepness=10.0)
        assert result < 0.01

    def test_extreme_high_near_one(self):
        """Very high value -> near 1."""
        result = sigmoid_normalize(10.0, center=0.5, steepness=10.0)
        assert result > 0.99


# =============================================================================
# Logarithmic Penalty
# =============================================================================


class TestLogarithmicPenalty:
    """Penalizes bad values heavily (e.g., drawdown)."""

    def test_zero_input_max_score(self):
        """Zero drawdown -> maximum score (1.0)."""
        result = logarithmic_penalty(0.0, max_val=50.0)
        assert abs(result - 1.0) < 0.01

    def test_max_input_zero_score(self):
        """Maximum drawdown -> zero score."""
        result = logarithmic_penalty(50.0, max_val=50.0)
        assert result < 0.05

    def test_output_bounded_0_1(self):
        """Always in [0, 1]."""
        for val in [0, 5, 10, 25, 50, 100]:
            result = logarithmic_penalty(val, max_val=50.0)
            assert 0.0 <= result <= 1.0

    def test_convex_curve(self):
        """First few percent of DD costs more than later ones."""
        # Going from 0->5% drawdown loses more score than 45->50%
        s0 = logarithmic_penalty(0.0, max_val=50.0)
        s5 = logarithmic_penalty(5.0, max_val=50.0)
        s45 = logarithmic_penalty(45.0, max_val=50.0)
        s50 = logarithmic_penalty(50.0, max_val=50.0)

        drop_first_5 = s0 - s5
        drop_last_5 = s45 - s50

        assert drop_first_5 > drop_last_5  # First 5% hurts more

    def test_monotonically_decreasing(self):
        """Higher drawdown -> lower score."""
        values = [0, 10, 20, 30, 40, 50]
        results = [logarithmic_penalty(v, max_val=50.0) for v in values]
        for i in range(len(results) - 1):
            assert results[i + 1] < results[i]


# =============================================================================
# Diminishing Returns
# =============================================================================


class TestDiminishingReturns:
    """Rewards improvement less at high end (e.g., Sortino)."""

    def test_zero_input_zero(self):
        """Zero Sortino -> zero score."""
        result = diminishing_returns(0.0, saturation=4.0)
        assert result < 0.05

    def test_output_bounded_0_1(self):
        """Always in [0, 1)."""
        for val in [0, 0.5, 1, 2, 3, 4, 10, 100]:
            result = diminishing_returns(val, saturation=4.0)
            assert 0.0 <= result < 1.0

    def test_saturation_point_high(self):
        """At saturation value, should be ~0.63 (1-1/e) or similar."""
        result = diminishing_returns(4.0, saturation=4.0)
        assert 0.5 < result < 0.8

    def test_diminishing_marginal_gain(self):
        """Going from 1->2 gives more than 3->4."""
        s1 = diminishing_returns(1.0, saturation=4.0)
        s2 = diminishing_returns(2.0, saturation=4.0)
        s3 = diminishing_returns(3.0, saturation=4.0)
        s4 = diminishing_returns(4.0, saturation=4.0)

        gain_1_to_2 = s2 - s1
        gain_3_to_4 = s4 - s3

        assert gain_1_to_2 > gain_3_to_4

    def test_negative_input_zero(self):
        """Negative input -> 0 (no credit for negative Sortino)."""
        result = diminishing_returns(-1.0, saturation=4.0)
        assert result == 0.0

    def test_monotonically_increasing(self):
        """Higher value -> higher score (but slower)."""
        values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
        results = [diminishing_returns(v, saturation=4.0) for v in values]
        for i in range(len(results) - 1):
            assert results[i + 1] > results[i]

    def test_far_above_saturation_near_one(self):
        """Way above saturation -> asymptotically approaching 1.0."""
        result = diminishing_returns(100.0, saturation=4.0)
        assert result > 0.95
