"""
TDD: Regime Classification Tests.

Defines the API contract for specialist regime detection.
Agent's specialist regime = whichever regime has their highest fitness_by_regime score.
"""

import pytest

from Fast_Swarm.Metrics.metrics_constants import SPECIALIST_REGIMES, NON_SPECIALIST_REGIMES
from Fast_Swarm.Metrics.fitness_model import classify_specialist_regime


# =============================================================================
# Regime Constants
# =============================================================================


class TestRegimeConstants:
    """Regime taxonomy is correctly defined."""

    def test_seven_specialist_regimes(self):
        """Exactly 7 specialist regimes."""
        assert len(SPECIALIST_REGIMES) == 7

    def test_specialist_regimes_content(self):
        """All expected regimes present."""
        expected = {"bull", "blowoff", "sideways", "crash", "bear", "recovery", "volatile"}
        assert set(SPECIALIST_REGIMES) == expected

    def test_non_specialist_regimes(self):
        """Non-specialist regimes defined."""
        assert "transition" in NON_SPECIALIST_REGIMES
        # random_* is a pattern, check at least one
        assert any(r.startswith("random") for r in NON_SPECIALIST_REGIMES) or "random" in NON_SPECIALIST_REGIMES

    def test_no_overlap(self):
        """Specialist and non-specialist don't overlap."""
        specialist_set = set(SPECIALIST_REGIMES)
        non_specialist_set = set(NON_SPECIALIST_REGIMES)
        assert specialist_set.isdisjoint(non_specialist_set)


# =============================================================================
# Specialist Classification
# =============================================================================


class TestClassifySpecialistRegime:
    """Determine agent's best regime from fitness_by_regime scores."""

    def test_clear_specialist(self):
        """One regime clearly dominant."""
        fitness_by_regime = {
            "bull": 75.0,
            "bear": 30.0,
            "crash": 20.0,
            "sideways": 25.0,
            "blowoff": 15.0,
            "recovery": 35.0,
            "volatile": 28.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        assert result == "bull"

    def test_bear_specialist(self):
        """Bear regime dominant."""
        fitness_by_regime = {
            "bull": 20.0,
            "bear": 80.0,
            "crash": 60.0,
            "sideways": 30.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        assert result == "bear"

    def test_unclassified_too_few_trades(self):
        """Empty or insufficient data -> 'unclassified'."""
        result = classify_specialist_regime({})
        assert result == "unclassified"

    def test_unclassified_all_zeros(self):
        """All zero scores -> 'unclassified'."""
        fitness_by_regime = {
            "bull": 0.0,
            "bear": 0.0,
            "crash": 0.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        assert result == "unclassified"

    def test_ignores_non_specialist_regimes(self):
        """Non-specialist regimes (transition, random) don't count."""
        fitness_by_regime = {
            "transition": 90.0,  # High but non-specialist
            "random_1": 85.0,   # High but non-specialist
            "bull": 50.0,       # Actual specialist regime
            "bear": 30.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        assert result == "bull"  # Highest SPECIALIST regime

    def test_minimum_threshold(self):
        """Need minimum score to be classified (not just highest-of-garbage)."""
        fitness_by_regime = {
            "bull": 5.0,  # Too low to be meaningful
            "bear": 3.0,
            "crash": 2.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        # If all scores are below threshold, return unclassified
        assert result == "unclassified"

    def test_close_competition_picks_highest(self):
        """When regimes are close, still picks highest."""
        fitness_by_regime = {
            "bull": 55.0,
            "recovery": 54.0,
            "volatile": 53.0,
        }
        result = classify_specialist_regime(fitness_by_regime)
        assert result == "bull"
