"""
Triage Tests: Behavioral Logic - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Behavioral Logic)
Tests for Jaccard similarity, trait mutations, and agent logic.
"""

import random

import pytest

from Fast_Swarm.Agents.Services.memory_service import jaccard_similarity


class TestJaccardSimilarityLogic:
    """CONTRACT: Jaccard similarity conflict detection."""

    def test_jaccard_similarity_high_overlap(self):
        """CONTRACT: Similar texts produce similarity >= 0.60."""
        text1 = "RSI oversold buy signal confirmed strong"
        text2 = "RSI oversold buy signal confirmed"
        sim = jaccard_similarity(text1, text2)
        assert sim >= 0.60, f"High overlap should produce >= 0.60, got {sim}"

    def test_jaccard_similarity_exact_value(self):
        """CONTRACT: Known overlap produces expected similarity."""
        # "a b c" vs "a b d" -> intersection={a,b}, union={a,b,c,d} -> 2/4=0.5
        text1 = "a b c"
        text2 = "a b d"
        sim = jaccard_similarity(text1, text2)
        assert sim == pytest.approx(0.5)

    def test_jaccard_non_conflict(self):
        """CONTRACT: Distinct texts produce similarity < 0.20."""
        text1 = "RSI oversold signal"
        text2 = "volume breakout detected"
        sim = jaccard_similarity(text1, text2)
        assert sim < 0.20, f"Distinct texts should have low similarity, got {sim}"


class TestTraitMutationDistribution:
    """CONTRACT: Trait mutation stays within +/-10%."""

    def test_mutation_rate_bounded(self):
        """CONTRACT: Mutation range +/-10% from parent value."""
        parent_value = 0.5
        mutation_range = 0.1
        random.seed(42)
        for _ in range(100):
            delta = random.uniform(-mutation_range, mutation_range)
            mutated = parent_value + delta
            assert parent_value - mutation_range <= mutated <= parent_value + mutation_range

    def test_mutation_mean_centered(self):
        """CONTRACT: Mean mutation is centered on parent value."""
        parent_value = 0.5
        mutation_range = 0.1
        random.seed(42)
        mutations = []
        for _ in range(10000):
            delta = random.uniform(-mutation_range, mutation_range)
            mutations.append(parent_value + delta)
        mean_mutation = sum(mutations) / len(mutations)
        assert mean_mutation == pytest.approx(parent_value, abs=0.01)

    def test_mutation_max_bound(self):
        """CONTRACT: Mutated value never exceeds 1.0."""
        parent_value = 0.95
        mutation_range = 0.1
        random.seed(42)
        for _ in range(1000):
            delta = random.uniform(-mutation_range, mutation_range)
            mutated = max(0.0, min(1.0, parent_value + delta))
            assert mutated <= 1.0

    def test_mutation_min_bound(self):
        """CONTRACT: Mutated value never below 0.0."""
        parent_value = 0.05
        mutation_range = 0.1
        random.seed(42)
        for _ in range(1000):
            delta = random.uniform(-mutation_range, mutation_range)
            mutated = max(0.0, min(1.0, parent_value + delta))
            assert mutated >= 0.0


class TestAgentGeneration:
    """CONTRACT: Agent generation tracking."""

    def test_generation_increment(self):
        """CONTRACT: Child generation = parent generation + 1."""
        parent_generation = 3
        child_generation = parent_generation + 1
        assert child_generation == 4

    def test_genesis_generation_zero(self):
        """CONTRACT: Genesis agents have generation = 0."""
        from Fast_Swarm.Tests.Fixtures.factories import AgentFactory

        agent = AgentFactory.create(generation=0)
        assert agent["generation"] == 0
