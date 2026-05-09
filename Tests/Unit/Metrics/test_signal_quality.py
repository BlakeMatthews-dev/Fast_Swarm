"""
TDD: Signal Quality Tests.

Defines the API contract for src/Fast_Swarm/Metrics/signal_quality.py.
Components:
1. Statistical confidence: sqrt(n_trades) weighting
2. Mutual information: entry_confidence vs outcome
3. Skew evaluation: appropriate skew for specialist type
"""

import math

import pytest

from Fast_Swarm.Metrics.signal_quality import (
    calculate_confidence_factor,
    calculate_mutual_information,
    calculate_signal_quality,
    evaluate_skew_for_type,
)


# =============================================================================
# Confidence Factor
# =============================================================================


class TestConfidenceFactor:
    """sqrt(n_trades) / 10, capped at 1.0."""

    def test_zero_trades(self):
        """No trades -> 0 confidence."""
        assert calculate_confidence_factor(0) == 0.0

    def test_one_trade(self):
        """1 trade -> 0.1."""
        result = calculate_confidence_factor(1)
        assert abs(result - 0.1) < 0.01

    def test_30_trades(self):
        """30 trades -> sqrt(30)/10 ~ 0.55."""
        result = calculate_confidence_factor(30)
        assert abs(result - 0.5477) < 0.01

    def test_100_trades_cap(self):
        """100 trades -> sqrt(100)/10 = 1.0 (cap)."""
        assert calculate_confidence_factor(100) == 1.0

    def test_above_100_still_capped(self):
        """500 trades -> still 1.0."""
        assert calculate_confidence_factor(500) == 1.0

    def test_monotonically_increasing(self):
        """More trades -> higher confidence."""
        values = [1, 5, 10, 25, 50, 100]
        results = [calculate_confidence_factor(n) for n in values]
        for i in range(len(results) - 1):
            assert results[i + 1] >= results[i]


# =============================================================================
# Mutual Information
# =============================================================================


class TestMutualInformation:
    """MI between entry_confidence and trade outcome."""

    def test_perfect_correlation_high_mi(self):
        """High confidence = win, low confidence = loss -> high MI."""
        trades = (
            [{"entry_confidence": 0.9, "outcome": 0.05}] * 50 +
            [{"entry_confidence": 0.1, "outcome": -0.05}] * 50
        )
        result = calculate_mutual_information(trades)
        assert result > 0.3

    def test_random_correlation_low_mi(self):
        """Random confidence vs outcome -> near-zero MI."""
        import numpy as np
        rng = np.random.default_rng(90)
        trades = [
            {
                "entry_confidence": rng.uniform(0, 1),
                "outcome": rng.choice([-0.02, 0.02])
            }
            for _ in range(200)
        ]
        result = calculate_mutual_information(trades)
        assert result < 0.15

    def test_empty_trades_zero(self):
        """No trades -> 0 MI."""
        assert calculate_mutual_information([]) == 0.0

    def test_output_bounded_0_1(self):
        """MI in [0, 1]."""
        trades = [{"entry_confidence": 0.7, "outcome": 0.02}] * 100
        result = calculate_mutual_information(trades)
        assert 0.0 <= result <= 1.0


# =============================================================================
# Skew Evaluation
# =============================================================================


class TestSkewEvaluation:
    """Appropriate skew depends on specialist type."""

    def test_bull_positive_skew_rewarded(self):
        """Bull specialists: positive skew is good."""
        returns = [0.01, 0.02, 0.015, 0.05, 0.03, -0.005, -0.003]
        result = evaluate_skew_for_type(returns, "bull")
        assert result > 0

    def test_bear_negative_skew_acceptable(self):
        """Bear specialists: negative skew is OK (profits from declines)."""
        returns = [-0.01, -0.02, 0.005, -0.05, -0.03, 0.003]
        result = evaluate_skew_for_type(returns, "bear")
        assert result >= 0  # Not penalized

    def test_crash_specialist_negative_skew_ok(self):
        """Crash specialists: negative skew expected."""
        returns = [0.001, 0.001, -0.10, -0.15, 0.001]
        result = evaluate_skew_for_type(returns, "crash")
        assert result >= 0

    def test_recovery_positive_skew_rewarded(self):
        """Recovery specialists: positive skew expected (catching bounces)."""
        returns = [-0.005, 0.03, 0.05, 0.08, -0.002]
        result = evaluate_skew_for_type(returns, "recovery")
        assert result > 0

    def test_output_bounded_0_5(self):
        """Skew bonus capped at 5 pts."""
        returns = [0.01] * 50 + [0.50]  # Extreme positive skew
        result = evaluate_skew_for_type(returns, "bull")
        assert 0.0 <= result <= 5.0

    def test_empty_returns_zero(self):
        """No returns -> 0."""
        assert evaluate_skew_for_type([], "bull") == 0.0


# =============================================================================
# Full Signal Quality
# =============================================================================


class TestSignalQualityFull:
    """End-to-end signal quality scoring."""

    def test_output_bounded_0_20(self):
        """Total in [0, 20]."""
        trades = [{"entry_confidence": 0.7, "outcome": 0.02}] * 50
        result = calculate_signal_quality(trades, n_trades=50, specialist_type="bull")
        assert 0.0 <= result <= 20.0

    def test_high_quality_signal(self):
        """Good confidence, many trades, right skew -> high score."""
        trades = (
            [{"entry_confidence": 0.85, "outcome": 0.03}] * 80 +
            [{"entry_confidence": 0.3, "outcome": -0.01}] * 20
        )
        result = calculate_signal_quality(trades, n_trades=100, specialist_type="bull")
        assert result > 12.0

    def test_low_quality_signal(self):
        """Random confidence, few trades -> low score."""
        import numpy as np
        rng = np.random.default_rng(91)
        trades = [
            {"entry_confidence": rng.uniform(0, 1), "outcome": rng.choice([-0.02, 0.02])}
            for _ in range(10)
        ]
        result = calculate_signal_quality(trades, n_trades=10, specialist_type="bull")
        assert result < 12.0
