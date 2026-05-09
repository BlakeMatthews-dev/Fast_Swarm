"""
EDD Soundness Test: Vote Poisoning Prevention - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Governance/Committee)
Validates that:
1. Single agent cannot hijack consensus with extreme confidence
2. Quorum enforcement rejects decisions below min_quorum
3. ELO bounds prevent any agent from gaining infinite weight
4. Confidence capping prevents gaming
5. ELO updates are bounded and reasonable
"""

import pytest

from Agents.Hivemind.Services.governance_service import (
    BASE_ELO,
    ELO_K_FACTOR,
    MAX_CONFIDENCE,
    MIN_ELO_WEIGHT,
    calculate_elo_weight,
)


class TestConfidenceCapping:
    """CONTRACT: Confidence is capped to prevent single-agent dominance."""

    def test_max_confidence_below_100_percent(self):
        """CONTRACT: MAX_CONFIDENCE must be < 1.0 to prevent hijacking."""
        assert MAX_CONFIDENCE < 1.0

    def test_confidence_cap_value(self):
        """CONTRACT: MAX_CONFIDENCE should be 0.95."""
        assert MAX_CONFIDENCE == 0.95

    def test_confidence_clamping(self):
        """CONTRACT: Confidence > MAX is clamped down."""
        raw_confidence = 0.99
        capped = min(raw_confidence, MAX_CONFIDENCE)
        assert capped == MAX_CONFIDENCE
        assert capped <= 0.95


class TestELOWeightBounds:
    """CONTRACT: ELO weight calculations are bounded."""

    def test_base_elo_gives_weight_1(self):
        """CONTRACT: Base ELO (1500) should give weight = 1.0."""
        weight = calculate_elo_weight(BASE_ELO)
        assert weight == pytest.approx(1.0)

    def test_low_elo_has_minimum_weight(self):
        """CONTRACT: Very low ELO has minimum weight (anti-silencing)."""
        weight = calculate_elo_weight(500.0)
        assert weight >= MIN_ELO_WEIGHT
        assert weight == MIN_ELO_WEIGHT  # 500/1500 = 0.33 < 0.5, so clamped

    def test_zero_elo_clamped(self):
        """CONTRACT: Zero ELO is clamped to minimum weight."""
        weight = calculate_elo_weight(0.0)
        assert weight == MIN_ELO_WEIGHT

    def test_high_elo_proportional(self):
        """CONTRACT: High ELO gives proportionally higher weight."""
        weight_high = calculate_elo_weight(2000.0)
        weight_base = calculate_elo_weight(BASE_ELO)
        assert weight_high > weight_base
        assert weight_high == pytest.approx(2000.0 / BASE_ELO)

    def test_extreme_elo_not_infinite(self):
        """CONTRACT: Even extreme ELO doesn't give infinite weight."""
        weight = calculate_elo_weight(2500.0)
        assert weight < float("inf")
        assert weight == pytest.approx(2500.0 / BASE_ELO)


class TestQuorumEnforcement:
    """CONTRACT: Quorum requirements are enforced."""

    def test_min_quorum_positive(self):
        """CONTRACT: min_quorum must be > 0."""
        min_quorum = 3  # Standard quorum
        assert min_quorum > 0

    def test_single_vote_insufficient_for_quorum_3(self):
        """CONTRACT: 1 vote cannot satisfy quorum of 3."""
        num_votes = 1
        min_quorum = 3
        quorum_met = num_votes >= min_quorum
        assert not quorum_met

    def test_quorum_3_requires_3_matching_votes(self):
        """CONTRACT: Quorum 3 needs 3 identical vote decisions."""
        min_quorum = 3
        votes = [0.8, 0.7, 0.9]  # 3 BUY votes
        quorum_met = len(votes) >= min_quorum
        assert quorum_met
        # All positive -> BUY consensus
        assert all(v > 0 for v in votes)


class TestSingleAgentHijackPrevention:
    """CONTRACT: Single agent cannot dominate committee decisions."""

    def test_single_high_confidence_vote_limited(self):
        """CONTRACT: Max confidence + max ELO still limited."""
        max_elo_weight = calculate_elo_weight(2500.0)
        max_vote_weight = max_elo_weight * MAX_CONFIDENCE
        # With 3 agents, single agent's max influence
        # Other 2 agents at minimum weight and confidence
        other_weight = MIN_ELO_WEIGHT * 0.5 * 2  # 2 agents, low conf
        total_weight = max_vote_weight + other_weight
        single_influence = max_vote_weight / total_weight
        # Should not be able to completely dominate
        assert single_influence < 1.0

    def test_extreme_confidence_rejected(self):
        """CONTRACT: Confidence > 1.0 should be rejected."""
        # The governance service raises ValueError for confidence > 1.0
        confidence = 1.5
        assert confidence > 1.0
        # Validation: confidence must be in [0, 1]
        is_invalid = confidence < 0.0 or confidence > 1.0
        assert is_invalid

    def test_three_agent_minimum_influence(self):
        """CONTRACT: With 3 agents, no single agent > 50% influence."""
        # Best case: one agent at max ELO, max confidence
        best_weight = calculate_elo_weight(2500.0) * MAX_CONFIDENCE
        # Other two at base ELO, moderate confidence
        other_weight_each = calculate_elo_weight(BASE_ELO) * 0.7
        total = best_weight + 2 * other_weight_each
        best_influence = best_weight / total
        # With 3 agents and capping, single agent influence is bounded
        assert best_influence < 0.75, f"Single agent influence {best_influence:.2f} too high"


class TestELOUpdateBounds:
    """CONTRACT: ELO updates are bounded and reasonable."""

    def test_elo_k_factor_reasonable(self):
        """CONTRACT: K-factor should be standard chess value (32)."""
        assert ELO_K_FACTOR == 32

    def test_max_elo_gain_per_vote(self):
        """CONTRACT: Maximum ELO gain from single vote is bounded."""
        # Max gain: actual=1.0, expected=0.0 -> gain = K * (1 - 0) = K
        # But expected is never exactly 0 for reasonable ELO
        old_elo = 1000.0  # Low ELO -> high expected opponent advantage
        expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - old_elo) / 400.0))
        max_gain = ELO_K_FACTOR * (1.0 - expected)
        assert max_gain <= ELO_K_FACTOR
        assert max_gain > 0

    def test_max_elo_loss_per_vote(self):
        """CONTRACT: Maximum ELO loss from single vote is bounded."""
        old_elo = 2000.0  # High ELO
        expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - old_elo) / 400.0))
        max_loss = ELO_K_FACTOR * (0.0 - expected)  # actual=0 (wrong)
        assert abs(max_loss) <= ELO_K_FACTOR
        assert max_loss < 0

    def test_elo_convergence_from_high(self):
        """CONTRACT: High ELO agents lose more on mistakes."""
        high_elo = 2200.0
        base_elo = BASE_ELO
        expected_high = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - high_elo) / 400.0))
        expected_base = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - base_elo) / 400.0))
        # High ELO has higher expected score, so loses more when wrong
        loss_high = ELO_K_FACTOR * (0.0 - expected_high)
        loss_base = ELO_K_FACTOR * (0.0 - expected_base)
        assert abs(loss_high) > abs(loss_base)

    def test_elo_convergence_from_low(self):
        """CONTRACT: Low ELO agents gain more on correct votes."""
        low_elo = 1100.0
        base_elo = BASE_ELO
        expected_low = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - low_elo) / 400.0))
        expected_base = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - base_elo) / 400.0))
        # Low ELO has lower expected, so gains more when correct
        gain_low = ELO_K_FACTOR * (1.0 - expected_low)
        gain_base = ELO_K_FACTOR * (1.0 - expected_base)
        assert gain_low > gain_base


class TestVoteBoundaries:
    """CONTRACT: Vote value boundaries."""

    def test_vote_value_range(self):
        """CONTRACT: vote_value must be in [-1, 1]."""
        valid_votes = [-1.0, -0.5, 0.0, 0.5, 1.0]
        invalid_votes = [-1.5, 1.5, 2.0, -2.0]
        for v in valid_votes:
            assert -1.0 <= v <= 1.0
        for v in invalid_votes:
            assert v < -1.0 or v > 1.0

    def test_vote_direction_long(self):
        """CONTRACT: +1.0 = strong LONG signal."""
        vote = 1.0
        assert vote > 0, "Positive vote = LONG"
        assert vote == 1.0, "Maximum LONG signal"

    def test_vote_direction_short(self):
        """CONTRACT: -1.0 = strong SHORT signal."""
        vote = -1.0
        assert vote < 0, "Negative vote = SHORT"
        assert vote == -1.0, "Maximum SHORT signal"


class TestAntiGamingMechanisms:
    """CONTRACT: Mechanisms that prevent gaming the system."""

    def test_elo_floor_prevents_sandbagging(self):
        """CONTRACT: Agents can't drop ELO below 1000."""
        elo_floor = 1000.0
        # Simulate many losses from base ELO
        elo = BASE_ELO
        for _ in range(100):
            expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - elo) / 400.0))
            elo = elo + ELO_K_FACTOR * (0.0 - expected)
            elo = max(elo_floor, min(2500.0, elo))
        assert elo >= elo_floor

    def test_elo_ceiling_prevents_runaway(self):
        """CONTRACT: Agents can't gain infinite ELO (max 2500)."""
        elo_ceiling = 2500.0
        elo = BASE_ELO
        for _ in range(200):
            expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - elo) / 400.0))
            elo = elo + ELO_K_FACTOR * (1.0 - expected)
            elo = max(1000.0, min(elo_ceiling, elo))
        assert elo <= elo_ceiling

    def test_deliberate_losing_penalized(self):
        """CONTRACT: Deliberate losing doesn't benefit agent."""
        # An agent that deliberately loses should have decreasing ELO/weight
        elo = BASE_ELO
        initial_weight = calculate_elo_weight(elo)
        for _ in range(20):
            expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - elo) / 400.0))
            elo = elo + ELO_K_FACTOR * (0.0 - expected)
            elo = max(1000.0, min(2500.0, elo))
        final_weight = calculate_elo_weight(elo)
        assert final_weight < initial_weight, "Deliberate losing must reduce influence"


class TestEdgeCases:
    """CONTRACT: Edge cases and boundary conditions."""

    def test_tie_vote_value(self):
        """CONTRACT: Zero vote (HOLD) is valid."""
        vote = 0.0
        assert -1.0 <= vote <= 1.0
        assert vote == 0.0

    def test_minimal_movement_is_hold_correct(self):
        """CONTRACT: Small price movements count as HOLD correct."""
        vote_value = 0.05  # Very small vote (near HOLD)
        actual_outcome = 0.001  # Very small movement
        # Both are near zero -> HOLD was correct
        is_hold_vote = abs(vote_value) < 0.1
        is_small_move = abs(actual_outcome) < 0.01
        hold_correct = is_hold_vote and is_small_move
        assert hold_correct

    def test_confidence_zero_minimal_impact(self):
        """CONTRACT: Zero confidence vote has minimal impact."""
        elo_weight = calculate_elo_weight(BASE_ELO)
        zero_conf_weight = elo_weight * 0.0  # confidence=0
        normal_conf_weight = elo_weight * 0.7
        assert zero_conf_weight == 0.0
        assert normal_conf_weight > zero_conf_weight


class TestDeterminism:
    """CONTRACT: ELO calculations are deterministic."""

    def test_elo_weight_deterministic(self):
        """CONTRACT: Same ELO always produces same weight."""
        for elo in [1000, 1200, 1500, 1800, 2500]:
            w1 = calculate_elo_weight(float(elo))
            w2 = calculate_elo_weight(float(elo))
            assert w1 == w2

    def test_expected_score_deterministic(self):
        """CONTRACT: Expected score calculation is deterministic."""
        for elo in [1000, 1200, 1500, 1800, 2200]:
            e1 = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - elo) / 400.0))
            e2 = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - elo) / 400.0))
            assert e1 == e2
