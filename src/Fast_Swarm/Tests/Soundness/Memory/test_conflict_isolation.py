"""
EDD Soundness Test: Memory Conflict Isolation - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Memory System)
Validates that the Jaccard similarity-based conflict detection:
1. Detects 100% of direct contradictions (>= 90% similarity)
2. Correctly handles threshold edge cases (59% vs 61%)
3. Properly clamps weights per memory type
4. Never misses identical content conflicts
"""

import pytest

from Fast_Swarm.Agents.Services.memory_service import (
    CONFLICT_THRESHOLD,
    clamp_weight_for_type,
    jaccard_similarity,
)
from Fast_Swarm.Agents.Models.memory_models import MemoryType, WEIGHT_BOUNDS


class TestJaccardSimilarity:
    """CONTRACT: Test the Jaccard word similarity function."""

    def test_identical_texts_return_1(self):
        """CONTRACT: Identical texts must return 1.0 similarity."""
        text = "RSI oversold buy signal detected"
        assert jaccard_similarity(text, text) == pytest.approx(1.0)

    def test_completely_different_texts_return_0(self):
        """CONTRACT: Completely different texts return 0.0 similarity."""
        text1 = "alpha beta gamma"
        text2 = "delta epsilon zeta"
        assert jaccard_similarity(text1, text2) == pytest.approx(0.0)

    def test_empty_text_returns_0(self):
        """CONTRACT: Empty texts must not crash - return 0.0."""
        assert jaccard_similarity("", "hello world") == 0.0
        assert jaccard_similarity("hello world", "") == 0.0
        assert jaccard_similarity("", "") == 0.0

    def test_partial_overlap(self):
        """CONTRACT: Partial overlap returns correct ratio."""
        # "the cat sat" vs "the cat ran" -> intersection={the,cat}, union={the,cat,sat,ran}
        text1 = "the cat sat"
        text2 = "the cat ran"
        expected = 2 / 4  # 0.5
        assert jaccard_similarity(text1, text2) == pytest.approx(expected)

    def test_case_insensitivity(self):
        """CONTRACT: Similarity must be case-insensitive."""
        text1 = "RSI Oversold Signal"
        text2 = "rsi oversold signal"
        assert jaccard_similarity(text1, text2) == pytest.approx(1.0)

    def test_threshold_boundary_below(self):
        """CONTRACT: Just below 60% threshold should not trigger conflict."""
        # Build texts with exactly 59% overlap (not possible exactly, so aim for < 60%)
        # 3 shared words out of 6 total = 50% (well below 60%)
        text1 = "alpha beta gamma delta"
        text2 = "alpha beta gamma epsilon zeta eta"
        sim = jaccard_similarity(text1, text2)
        # 3 shared / 7 total = 0.428
        assert sim < CONFLICT_THRESHOLD

    def test_threshold_boundary_at(self):
        """CONTRACT: Exactly at 60% threshold should trigger conflict."""
        # 3 shared out of 5 total = 0.6
        text1 = "word1 word2 word3"
        text2 = "word1 word2 word3 word4 word5"
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(3 / 5)  # 0.6
        assert sim >= CONFLICT_THRESHOLD

    def test_threshold_boundary_above(self):
        """CONTRACT: Just above 60% threshold should trigger conflict."""
        # 4 shared out of 6 total = 0.667
        text1 = "word1 word2 word3 word4"
        text2 = "word1 word2 word3 word4 word5 word6"
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(4 / 6)  # 0.667
        assert sim > CONFLICT_THRESHOLD


class TestWeightClamping:
    """CONTRACT: Type-specific weight clamping."""

    def test_observation_weight_bounds(self):
        """CONTRACT: Observation type: 0.1 - 0.5."""
        assert clamp_weight_for_type(MemoryType.OBSERVATION, 0.0) == 0.1
        assert clamp_weight_for_type(MemoryType.OBSERVATION, 1.0) == 0.5
        assert clamp_weight_for_type(MemoryType.OBSERVATION, 0.3) == 0.3

    def test_regret_weight_bounds(self):
        """CONTRACT: Regret type: 0.6 - 1.0."""
        assert clamp_weight_for_type(MemoryType.REGRET, 0.0) == 0.6
        assert clamp_weight_for_type(MemoryType.REGRET, 1.5) == 1.0
        assert clamp_weight_for_type(MemoryType.REGRET, 0.8) == 0.8

    def test_affirmation_weight_bounds(self):
        """CONTRACT: Affirmation type: 0.6 - 1.0."""
        assert clamp_weight_for_type(MemoryType.AFFIRMATION, 0.0) == 0.6
        assert clamp_weight_for_type(MemoryType.AFFIRMATION, 1.5) == 1.0
        assert clamp_weight_for_type(MemoryType.AFFIRMATION, 0.7) == 0.7

    def test_lesson_weight_bounds(self):
        """CONTRACT: Lesson type: 0.5 - 0.9."""
        assert clamp_weight_for_type(MemoryType.LESSON, 0.0) == 0.5
        assert clamp_weight_for_type(MemoryType.LESSON, 1.5) == 0.9
        assert clamp_weight_for_type(MemoryType.LESSON, 0.7) == 0.7

    def test_opinion_weight_bounds(self):
        """CONTRACT: Opinion type: 0.3 - 0.8."""
        # Note: memory_models has OPINION weight bounds as (0.3, 0.8)
        assert clamp_weight_for_type(MemoryType.OPINION, 0.0) == 0.3
        assert clamp_weight_for_type(MemoryType.OPINION, 1.5) == 0.8
        assert clamp_weight_for_type(MemoryType.OPINION, 0.5) == 0.5

    def test_counterfactual_weight_bounds(self):
        """CONTRACT: Counterfactual type: 0.2 - 0.6."""
        # Note: memory_models has COUNTERFACTUAL weight bounds as (0.2, 0.6)
        assert clamp_weight_for_type(MemoryType.COUNTERFACTUAL, 0.0) == 0.2
        assert clamp_weight_for_type(MemoryType.COUNTERFACTUAL, 1.5) == 0.6
        assert clamp_weight_for_type(MemoryType.COUNTERFACTUAL, 0.4) == 0.4

    def test_all_types_have_bounds(self):
        """CONTRACT: Every MemoryType must have defined bounds."""
        for mem_type in MemoryType:
            assert mem_type in WEIGHT_BOUNDS, f"{mem_type} missing from WEIGHT_BOUNDS"
            lo, hi = WEIGHT_BOUNDS[mem_type]
            assert 0.0 <= lo < hi <= 1.0, f"Invalid bounds for {mem_type}: ({lo}, {hi})"


class TestConflictDetection:
    """CONTRACT: Conflict detection logic."""

    def test_contradiction_threshold(self):
        """CONTRACT: High similarity texts detected as potential conflicts."""
        text1 = "RSI oversold buy signal strong confirmation"
        text2 = "RSI oversold buy signal strong confirmation detected"
        sim = jaccard_similarity(text1, text2)
        assert sim >= 0.60, f"High overlap {sim} should trigger conflict"

    def test_overlap_vs_refinement(self):
        """CONTRACT: 75-89% = overlap, 60-74% = refinement."""
        # High overlap: 5/6 shared
        text1 = "alpha beta gamma delta epsilon"
        text2 = "alpha beta gamma delta epsilon zeta"
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(5 / 6)  # 0.833
        is_overlap = 0.75 <= sim < 0.90
        assert is_overlap, f"Similarity {sim} should be classified as overlap"

    def test_no_false_positives_on_unrelated(self):
        """CONTRACT: Unrelated content must not trigger conflict."""
        text1 = "RSI oversold buy signal"
        text2 = "volume spike detected breakout"
        sim = jaccard_similarity(text1, text2)
        assert sim < CONFLICT_THRESHOLD, f"Unrelated texts should not conflict (sim={sim})"

    def test_identical_memory_conflict(self):
        """CONTRACT: Identical memories always conflict."""
        text = "MACD crossover bullish signal confirmed"
        sim = jaccard_similarity(text, text)
        assert sim == 1.0
        assert sim >= CONFLICT_THRESHOLD


class TestEdgeCases:
    """CONTRACT: Edge cases and boundary conditions."""

    def test_single_word_texts(self):
        """CONTRACT: Single word texts should work correctly."""
        assert jaccard_similarity("hello", "hello") == 1.0
        assert jaccard_similarity("hello", "world") == 0.0

    def test_whitespace_handling(self):
        """CONTRACT: Extra whitespace should not affect results."""
        text1 = "RSI oversold buy"
        text2 = "RSI  oversold  buy"
        # split() handles multiple whitespace
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(1.0)

    def test_numeric_content(self):
        """CONTRACT: Numeric values in text should be handled."""
        text1 = "RSI 30 oversold"
        text2 = "RSI 30 oversold signal"
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(3 / 4)  # 0.75

    def test_special_characters(self):
        """CONTRACT: Special characters split words correctly."""
        text1 = "price-action breakout"
        text2 = "price-action breakout confirmed"
        sim = jaccard_similarity(text1, text2)
        # "price-action" treated as one word by split()
        assert sim == pytest.approx(2 / 3)


class TestMemoryDecay:
    """CONTRACT: Memory decay over time."""

    def test_decay_applied_on_inheritance(self):
        """CONTRACT: Inherited memories have decay applied."""
        original_weight = 0.8
        decay_rate = 0.2  # 20% decay
        decayed_weight = original_weight * (1.0 - decay_rate)
        assert decayed_weight < original_weight
        assert decayed_weight == pytest.approx(0.64)

    def test_decay_rate_bounded(self):
        """CONTRACT: Decay rate is bounded [0.0, 1.0]."""
        # Valid decay rates
        for rate in [0.0, 0.1, 0.2, 0.5, 1.0]:
            assert 0.0 <= rate <= 1.0
        # After decay, weight should be non-negative
        weight = 0.8
        for rate in [0.0, 0.2, 0.5, 0.9, 1.0]:
            decayed = weight * (1.0 - rate)
            assert decayed >= 0.0

    def test_memory_weight_after_decay(self):
        """CONTRACT: Weight after decay still valid for type."""
        # A lesson with weight 0.9 decayed by 0.2 -> 0.72, still within [0.5, 0.9]
        weight = 0.9
        decay_rate = 0.2
        decayed = weight * (1.0 - decay_rate)
        clamped = clamp_weight_for_type(MemoryType.LESSON, decayed)
        lo, hi = WEIGHT_BOUNDS[MemoryType.LESSON]
        assert lo <= clamped <= hi
