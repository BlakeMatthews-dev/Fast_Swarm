"""
Memory System Tests - V3 Parity + Enhancement.

Memory Types:
- observation: Neutral pattern noticed (weight 0.1-0.5)
- opinion: Belief + confidence (weight 0.3-0.8)
- lesson: Actionable takeaway (weight 0.5-0.9)
- counterfactual: What-if analysis (weight 0.2-0.6)
- regret: Decision to not repeat (weight 0.6-1.0)
- affirmation: Decision to repeat (weight 0.6-1.0)

Priority for Inheritance (higher = keep):
- affirmation: 5
- regret: 5
- lesson: 4
- opinion: 3
- counterfactual: 2
- observation: 1

Conflict Detection: 60% Jaccard word similarity

Memory Review: Weak memories (< 0.15 weight) surfaced for LLM review
- Actions: REINFORCE, COMBINE, FORGET, IMPROVE
"""

import pytest

# Memory type weight ranges (V3 spec)
WEIGHT_RANGES = {
    "observation": (0.1, 0.5),
    "opinion": (0.3, 0.8),
    "lesson": (0.5, 0.9),
    "counterfactual": (0.2, 0.6),
    "regret": (0.6, 1.0),
    "affirmation": (0.6, 1.0),
}

# Inheritance priority
PRIORITY = {
    "affirmation": 5,
    "regret": 5,
    "lesson": 4,
    "opinion": 3,
    "counterfactual": 2,
    "observation": 1,
}


class TestMemoryCRUD:
    """Basic memory operations."""

    def test_create_memory_with_all_fields(self):
        """Create memory with all fields populated."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        mem = create_memory(
            agent_id="agent-001",
            memory_type="lesson",
            content="RSI below 30 is buy signal",
            weight=0.7,
            confidence=0.8,
        )

        assert mem.memory_id is not None
        assert len(mem.memory_id) > 0
        assert mem.agent_id == "agent-001"
        assert mem.memory_type == "lesson"
        assert mem.content == "RSI below 30 is buy signal"
        assert mem.weight == 0.7
        assert mem.confidence == 0.8

    def test_create_memory_generates_id(self):
        """Memory ID is auto-generated."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        mem1 = create_memory(agent_id="agent-001", memory_type="lesson", content="Test 1")
        mem2 = create_memory(agent_id="agent-001", memory_type="lesson", content="Test 2")

        assert mem1.memory_id != mem2.memory_id

    def test_create_memory_default_values(self):
        """Defaults are set for optional fields."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        mem = create_memory(agent_id="agent-001", memory_type="observation", content="Noticed pattern")

        assert mem.weight > 0
        assert mem.confidence >= 0
        assert mem.reinforcement_count == 0
        assert mem.contradiction_count == 0
        assert mem.linked_trade_ids == []
        assert mem.linked_memory_ids == []

    def test_weight_bounds_by_type(self):
        """Weight clamped to type-specific range."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        # Observation max is 0.5
        mem = create_memory(
            agent_id="agent-001",
            memory_type="observation",
            content="Test",
            weight=0.9,  # Too high for observation
        )
        assert mem.weight <= 0.5, f"Observation weight {mem.weight} should be <= 0.5"

        # Regret min is 0.6
        mem = create_memory(
            agent_id="agent-001",
            memory_type="regret",
            content="Test",
            weight=0.3,  # Too low for regret
        )
        assert mem.weight >= 0.6, f"Regret weight {mem.weight} should be >= 0.6"

    def test_get_memory_by_id(self):
        """Retrieve memory by ID."""
        from Fast_Swarm.local_agents.core.memory import create_memory, get_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test lesson")

        retrieved = get_memory(mem.memory_id)

        assert retrieved is not None
        assert retrieved.memory_id == mem.memory_id
        assert retrieved.content == mem.content

    def test_get_memory_not_found(self):
        """Non-existent memory returns None."""
        from Fast_Swarm.local_agents.core.memory import get_memory

        result = get_memory("nonexistent-id")
        assert result is None

    def test_update_memory_weight(self):
        """Update memory weight."""
        from Fast_Swarm.local_agents.core.memory import create_memory, update_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test", weight=0.5)

        updated = update_memory(mem.memory_id, weight=0.8)

        assert updated.weight == 0.8
        assert updated.memory_id == mem.memory_id

    def test_delete_memory(self):
        """Delete memory by ID."""
        from Fast_Swarm.local_agents.core.memory import create_memory, delete_memory, get_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test")

        delete_memory(mem.memory_id)

        assert get_memory(mem.memory_id) is None


class TestMemoryLinking:
    """Memory linking to trades and other memories."""

    def test_link_memory_to_trade(self):
        """Link memory to trade IDs."""
        from Fast_Swarm.local_agents.core.memory import create_memory, link_to_trade

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Learned from trade")

        linked = link_to_trade(mem.memory_id, "trade-001")

        assert "trade-001" in linked.linked_trade_ids

    def test_link_memory_to_memory(self):
        """Link memory to another memory."""
        from Fast_Swarm.local_agents.core.memory import create_memory, link_to_memory

        mem1 = create_memory(agent_id="agent-001", memory_type="observation", content="First observation")
        mem2 = create_memory(agent_id="agent-001", memory_type="lesson", content="Lesson from observation")

        linked = link_to_memory(mem2.memory_id, mem1.memory_id)

        assert mem1.memory_id in linked.linked_memory_ids

    def test_spawned_from_tracking(self):
        """Track parent memory for derived memories."""
        from Fast_Swarm.local_agents.core.memory import create_derived_memory, create_memory

        parent = create_memory(
            agent_id="agent-001", memory_type="observation", content="RSI often below 30 before rallies"
        )

        child = create_derived_memory(
            parent_id=parent.memory_id, agent_id="agent-001", memory_type="lesson", content="Buy when RSI < 30"
        )

        assert child.spawned_from == parent.memory_id


class TestMemoryConflictDetection:
    """Jaccard similarity conflict detection (60% threshold)."""

    def test_similar_memories_flagged(self):
        """60%+ word overlap -> conflict."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        mem_a = Memory(content="RSI below 30 means buy signal")
        mem_b = Memory(content="RSI below 30 means sell signal")

        # Words: RSI, below, 30, means, buy/sell, signal
        # Common: RSI, below, 30, means, signal = 5
        # Total unique: RSI, below, 30, means, buy, sell, signal = 7
        # Jaccard: 5/7 = 71% > 60%
        assert detect_conflict(mem_a, mem_b) is True

    def test_different_memories_not_flagged(self):
        """<60% overlap -> no conflict."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        mem_a = Memory(content="RSI signals oversold conditions")
        mem_b = Memory(content="MACD crossover indicates momentum shift")

        assert detect_conflict(mem_a, mem_b) is False

    def test_exact_duplicate_is_conflict(self):
        """Identical content -> conflict."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        mem_a = Memory(content="Always set stop loss")
        mem_b = Memory(content="Always set stop loss")

        assert detect_conflict(mem_a, mem_b) is True

    def test_empty_content_no_crash(self):
        """Empty strings -> no conflict, no crash."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        mem_a = Memory(content="")
        mem_b = Memory(content="RSI buy signal")

        assert detect_conflict(mem_a, mem_b) is False

    def test_both_empty_no_conflict(self):
        """Both empty -> no conflict (or handle gracefully)."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        mem_a = Memory(content="")
        mem_b = Memory(content="")

        # Either False or graceful handling
        result = detect_conflict(mem_a, mem_b)
        assert result is False or result is None

    def test_jaccard_calculation(self):
        """Verify Jaccard calculation is correct."""
        from Fast_Swarm.local_agents.core.memory import calculate_jaccard_similarity

        # 3 common words, 5 total unique
        sim = calculate_jaccard_similarity("the quick brown fox", "the slow brown dog")
        # Common: the, brown = 2
        # Total: the, quick, brown, fox, slow, dog = 6
        # Jaccard: 2/6 = 0.333
        assert 0.30 < sim < 0.40

    def test_conflict_threshold_exactly_60(self):
        """Exactly 60% Jaccard overlap -> is conflict."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        # For Jaccard = 0.6, we need |intersection|/|union| = 0.6
        # If intersection=3 and union=5, Jaccard = 3/5 = 0.6
        # To get union=5 with 3 shared: each set has 4 words, 3 shared, 1 unique each
        # Union = 3 + 1 + 1 = 5, Intersection = 3, Jaccard = 3/5 = 0.6
        mem_a = Memory(content="word1 word2 word3 unique_a")
        mem_b = Memory(content="word1 word2 word3 unique_b")
        # Intersection: {word1, word2, word3} = 3
        # Union: {word1, word2, word3, unique_a, unique_b} = 5
        # Jaccard = 3/5 = 0.6

        assert detect_conflict(mem_a, mem_b) is True

    def test_conflict_threshold_just_below_60(self):
        """Just below 60% -> not conflict."""
        from Fast_Swarm.local_agents.core.memory import Memory, detect_conflict

        # 2 of 5 words match = 40%
        mem_a = Memory(content="word1 word2 word3 word4 word5")
        mem_b = Memory(content="word1 word2 other1 other2 other3")

        assert detect_conflict(mem_a, mem_b) is False


class TestMemoryInheritance:
    """Memory selection during reproduction."""

    def test_priority_ordering(self):
        """Affirmations/regrets kept over observations."""
        from Fast_Swarm.local_agents.core.memory import Memory, select_for_inheritance

        memories = [
            Memory(memory_type="observation", weight=0.5, content="Obs"),
            Memory(memory_type="affirmation", weight=0.3, content="Affirm"),  # Lower weight but higher priority
        ]

        # With 50% condensation, should keep affirmation
        selected = select_for_inheritance(memories, condensation=0.5)

        types = [m.memory_type for m in selected]
        assert "affirmation" in types, "Should keep affirmation despite lower weight"

    def test_decay_applied(self):
        """Inherited memories have decayed weight."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_inheritance_decay

        original = Memory(weight=0.8, content="Test")
        inherited = apply_inheritance_decay(original, decay_rate=0.5)

        assert inherited.weight == 0.4, f"Expected 0.4, got {inherited.weight}"

    def test_min_weight_floor(self):
        """Decayed weight floors at 0.1."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_inheritance_decay

        original = Memory(weight=0.15, content="Test")
        inherited = apply_inheritance_decay(original, decay_rate=0.9)

        assert inherited.weight >= 0.1, f"Weight {inherited.weight} should floor at 0.1"

    def test_condensation_0_keeps_none(self):
        """0% condensation -> no memories inherited."""
        from Fast_Swarm.local_agents.core.memory import Memory, select_for_inheritance

        memories = [
            Memory(memory_type="affirmation", weight=1.0, content="Best memory"),
        ]

        selected = select_for_inheritance(memories, condensation=0.0)

        assert len(selected) == 0

    def test_condensation_1_keeps_all(self):
        """100% condensation -> all memories inherited."""
        from Fast_Swarm.local_agents.core.memory import Memory, select_for_inheritance

        memories = [
            Memory(memory_type="observation", weight=0.1, content="Obs"),
            Memory(memory_type="lesson", weight=0.5, content="Lesson"),
            Memory(memory_type="affirmation", weight=0.8, content="Affirm"),
        ]

        selected = select_for_inheritance(memories, condensation=1.0)

        assert len(selected) == len(memories)

    def test_inheritance_preserves_links(self):
        """Inherited memories keep their linked IDs."""
        from Fast_Swarm.local_agents.core.memory import Memory, select_for_inheritance

        memories = [
            Memory(
                memory_type="lesson",
                weight=0.7,
                content="Lesson",
                linked_trade_ids=["trade-001", "trade-002"],
                linked_memory_ids=["mem-001"],
            ),
        ]

        selected = select_for_inheritance(memories, condensation=1.0)

        assert len(selected) == 1
        assert selected[0].linked_trade_ids == ["trade-001", "trade-002"]


class TestMemoryReview:
    """Enhanced memory review system."""

    def test_weak_memories_flagged_for_review(self):
        """Memories below threshold flagged."""
        from Fast_Swarm.local_agents.core.memory import Memory, get_memories_for_review

        memories = [
            Memory(weight=0.5, content="Strong memory"),
            Memory(weight=0.12, content="Weak memory 1"),
            Memory(weight=0.08, content="Weak memory 2"),
        ]

        flagged = get_memories_for_review(memories, threshold=0.15)

        assert len(flagged) == 2
        assert all(m.weight < 0.15 for m in flagged)

    def test_no_weak_memories_empty_list(self):
        """No weak memories -> empty list."""
        from Fast_Swarm.local_agents.core.memory import Memory, get_memories_for_review

        memories = [
            Memory(weight=0.5, content="Strong 1"),
            Memory(weight=0.6, content="Strong 2"),
        ]

        flagged = get_memories_for_review(memories, threshold=0.15)

        assert len(flagged) == 0

    def test_all_weak_memories_all_flagged(self):
        """All weak -> all flagged."""
        from Fast_Swarm.local_agents.core.memory import Memory, get_memories_for_review

        memories = [
            Memory(weight=0.10, content="Weak 1"),
            Memory(weight=0.05, content="Weak 2"),
        ]

        flagged = get_memories_for_review(memories, threshold=0.15)

        assert len(flagged) == 2


class TestReviewTriggers:
    """Memory review trigger conditions."""

    def test_trigger_on_session_end(self):
        """Session end triggers review."""
        from Fast_Swarm.local_agents.core.memory import should_trigger_review

        assert should_trigger_review(trigger="session_end") is True

    def test_trigger_on_backtest_interval(self):
        """Every N backtests triggers review."""
        from Fast_Swarm.local_agents.core.memory import should_trigger_review

        # At interval
        assert should_trigger_review(trigger="backtest_interval", backtest_count=50) is True
        assert should_trigger_review(trigger="backtest_interval", backtest_count=100) is True

        # Not at interval
        assert should_trigger_review(trigger="backtest_interval", backtest_count=25) is False

    def test_trigger_on_birth(self):
        """Agent birth triggers review."""
        from Fast_Swarm.local_agents.core.memory import should_trigger_review

        assert should_trigger_review(trigger="on_birth") is True

    def test_trigger_on_memory_count_threshold(self):
        """High memory count triggers review."""
        from Fast_Swarm.local_agents.core.memory import should_trigger_review

        assert should_trigger_review(trigger="memory_count", memory_count=100) is True
        assert should_trigger_review(trigger="memory_count", memory_count=50) is False

    def test_trigger_on_weak_memory_count(self):
        """Many weak memories triggers review."""
        from Fast_Swarm.local_agents.core.memory import should_trigger_review

        assert should_trigger_review(trigger="weak_memory_count", weak_count=10) is True
        assert should_trigger_review(trigger="weak_memory_count", weak_count=3) is False


class TestReviewActions:
    """Memory review action outcomes."""

    def test_reinforce_increases_weight(self):
        """REINFORCE action increases memory weight."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_review_action

        mem = Memory(weight=0.12, content="Test")
        original_weight = mem.weight
        original_reinforce_count = mem.reinforcement_count
        result = apply_review_action(mem, action="reinforce")

        assert result.weight > original_weight
        assert result.reinforcement_count > original_reinforce_count

    def test_forget_deletes_memory(self):
        """FORGET action marks memory for deletion."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_review_action

        mem = Memory(weight=0.08, content="Test")
        result = apply_review_action(mem, action="forget")

        # Either returns None or marks as deleted
        assert result is None or getattr(result, "deleted", False) is True

    def test_improve_updates_content(self):
        """IMPROVE action updates memory content."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_review_action

        mem = Memory(weight=0.10, content="Original content")
        result = apply_review_action(mem, action="improve", new_content="Improved content with more detail")

        assert result.content == "Improved content with more detail"

    def test_combine_merges_memories(self):
        """COMBINE action merges with another memory."""
        from Fast_Swarm.local_agents.core.memory import Memory, apply_review_action

        mem1 = Memory(memory_id="mem-001", weight=0.10, content="Part 1")
        mem2 = Memory(memory_id="mem-002", weight=0.12, content="Part 2")

        result = apply_review_action(mem1, action="combine", combine_with=mem2)

        # Result should have combined content or reference both
        assert result is not None
        # Weight should be at least the max of the two
        assert result.weight >= max(mem1.weight, mem2.weight)


class TestMemoryReinforcement:
    """Memory reinforcement and contradiction tracking."""

    def test_reinforce_memory(self):
        """Reinforcing memory increases count and weight."""
        from Fast_Swarm.local_agents.core.memory import create_memory, reinforce_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test", weight=0.5)
        original_weight = mem.weight

        reinforced = reinforce_memory(mem.memory_id)

        assert reinforced.reinforcement_count == 1
        assert reinforced.weight > original_weight

    def test_contradict_memory(self):
        """Contradicting memory increases count and decreases weight."""
        from Fast_Swarm.local_agents.core.memory import contradict_memory, create_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test", weight=0.7)
        original_weight = mem.weight

        contradicted = contradict_memory(mem.memory_id)

        assert contradicted.contradiction_count == 1
        assert contradicted.weight < original_weight

    def test_weight_floor_on_contradiction(self):
        """Weight doesn't go below 0.1 on contradiction."""
        from Fast_Swarm.local_agents.core.memory import contradict_memory, create_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test", weight=0.5)

        # Contradict many times
        for _ in range(10):
            mem = contradict_memory(mem.memory_id)

        assert mem.weight >= 0.1

    def test_weight_ceiling_on_reinforcement(self):
        """Weight doesn't exceed type max on reinforcement."""
        from Fast_Swarm.local_agents.core.memory import create_memory, reinforce_memory

        # Observation max is 0.5
        mem = create_memory(agent_id="agent-001", memory_type="observation", content="Test", weight=0.4)

        # Reinforce many times
        for _ in range(10):
            mem = reinforce_memory(mem.memory_id)

        assert mem.weight <= 0.5  # Observation max


class TestMemoryAccessTracking:
    """Track last access time for decay calculations."""

    def test_access_updates_timestamp(self):
        """Accessing memory updates last_accessed_at."""
        import time

        from Fast_Swarm.local_agents.core.memory import access_memory, create_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test")
        original_time = mem.last_accessed_at

        time.sleep(0.01)  # Small delay

        accessed = access_memory(mem.memory_id)

        assert accessed.last_accessed_at > original_time

    def test_created_at_immutable(self):
        """created_at doesn't change on access."""
        from Fast_Swarm.local_agents.core.memory import access_memory, create_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test")
        original_created = mem.created_at

        access_memory(mem.memory_id)
        accessed = access_memory(mem.memory_id)

        assert accessed.created_at == original_created


class TestMemoryContextSnapshot:
    """Context snapshot at memory creation."""

    def test_snapshot_stored(self):
        """Context snapshot is stored."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        mem = create_memory(
            agent_id="agent-001",
            memory_type="lesson",
            content="Test",
            context_snapshot={"fitness": 65, "recent_win_rate": 0.55, "market_regime": "trending"},
        )

        assert mem.context_snapshot["fitness"] == 65
        assert mem.context_snapshot["recent_win_rate"] == 0.55

    def test_snapshot_empty_by_default(self):
        """Snapshot is empty dict by default."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        mem = create_memory(agent_id="agent-001", memory_type="lesson", content="Test")

        assert mem.context_snapshot == {}


class TestMemoryTypeValidation:
    """Validate memory types."""

    def test_valid_memory_types(self):
        """All valid memory types accepted."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        valid_types = ["observation", "opinion", "lesson", "counterfactual", "regret", "affirmation"]

        for mtype in valid_types:
            mem = create_memory(agent_id="agent-001", memory_type=mtype, content="Test")
            assert mem.memory_type == mtype

    def test_invalid_memory_type_raises(self):
        """Invalid memory type raises error."""
        from Fast_Swarm.local_agents.core.memory import create_memory

        with pytest.raises((ValueError, KeyError)):
            create_memory(agent_id="agent-001", memory_type="invalid_type", content="Test")
