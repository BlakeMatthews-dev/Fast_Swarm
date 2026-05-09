"""
Tests for Memory Integration - weight bounds, episodic/semantic storage,
decay, capacity, and edge cases.

Tests span both memory_service.py and memory_integration_service.py.

All tests use AsyncMock for DB sessions (no real database required).
"""

import math
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Agents.Models.memory_models import (
    INHERITANCE_PRIORITY,
    WEIGHT_BOUNDS,
    AgentMemory,
    MemoryType,
)
from Fast_Swarm.Agents.Services.memory_service import (
    CONFLICT_THRESHOLD,
    MAX_MEMORIES_BEFORE_REVIEW,
    REVIEW_TRADE_COUNT,
    WEAK_MEMORY_THRESHOLD,
    WEIGHT_FLOOR,
    apply_inheritance_decay,
    clamp_weight_for_type,
    get_priority,
    get_weight_range,
    is_weak_memory,
    jaccard_similarity,
    validate_memory_type,
)


# =============================================================================
# Helpers
# =============================================================================

def _mock_memory(memory_id=None, agent_id="test-agent", memory_type="lesson",
                 content="test memory content", weight=0.5, confidence=0.5,
                 deleted=False, spawned_from=None, reinforcement_count=0,
                 contradiction_count=0, context_snapshot=None):
    """Create a mock AgentMemory object."""
    mem = MagicMock(spec=AgentMemory)
    mem.memory_id = memory_id or str(uuid.uuid4())
    mem.agent_id = agent_id
    mem.memory_type = memory_type
    mem.content = content
    mem.weight = weight
    mem.confidence = confidence
    mem.deleted = deleted
    mem.spawned_from = spawned_from
    mem.reinforcement_count = reinforcement_count
    mem.contradiction_count = contradiction_count
    mem.context_snapshot = context_snapshot or {}
    mem.linked_trade_ids = []
    mem.created_at = datetime.utcnow()
    mem.last_accessed_at = datetime.utcnow()
    return mem


# =============================================================================
# Memory Weight Bounds Tests (the fix we made)
# =============================================================================


class TestMemoryWeightBounds:
    """Tests for weight clamping per memory type."""

    def test_observation_weight_clamped_low(self):
        # OBSERVATION bounds: (0.1, 0.5)
        result = clamp_weight_for_type(MemoryType.OBSERVATION, 0.0)
        assert result == 0.1

    def test_observation_weight_clamped_high(self):
        result = clamp_weight_for_type(MemoryType.OBSERVATION, 1.0)
        assert result == 0.5

    def test_lesson_weight_clamped_low(self):
        # LESSON bounds: (0.5, 0.9)
        result = clamp_weight_for_type(MemoryType.LESSON, 0.1)
        assert result == 0.5

    def test_lesson_weight_clamped_high(self):
        result = clamp_weight_for_type(MemoryType.LESSON, 1.0)
        assert result == 0.9

    def test_regret_weight_bounds(self):
        # REGRET bounds: (0.6, 1.0)
        assert clamp_weight_for_type(MemoryType.REGRET, 0.0) == 0.6
        assert clamp_weight_for_type(MemoryType.REGRET, 1.0) == 1.0

    def test_affirmation_weight_bounds(self):
        # AFFIRMATION bounds: (0.6, 1.0)
        assert clamp_weight_for_type(MemoryType.AFFIRMATION, 0.3) == 0.6
        assert clamp_weight_for_type(MemoryType.AFFIRMATION, 0.9) == 0.9

    def test_opinion_weight_bounds(self):
        # OPINION bounds: (0.3, 0.8)
        assert clamp_weight_for_type(MemoryType.OPINION, 0.0) == 0.3
        assert clamp_weight_for_type(MemoryType.OPINION, 1.0) == 0.8

    def test_counterfactual_weight_bounds(self):
        # COUNTERFACTUAL bounds: (0.2, 0.6)
        assert clamp_weight_for_type(MemoryType.COUNTERFACTUAL, 0.0) == 0.2
        assert clamp_weight_for_type(MemoryType.COUNTERFACTUAL, 1.0) == 0.6

    def test_weight_within_bounds_unchanged(self):
        # Value within bounds should be returned as-is
        assert clamp_weight_for_type(MemoryType.LESSON, 0.7) == 0.7

    def test_all_types_have_bounds(self):
        for mem_type in MemoryType:
            assert mem_type in WEIGHT_BOUNDS, f"Missing bounds for {mem_type}"
            lo, hi = WEIGHT_BOUNDS[mem_type]
            assert 0.0 <= lo < hi <= 1.0


# =============================================================================
# Episodic Storage Tests (via create_memory mock)
# =============================================================================


class TestEpisodicStorage:
    """Tests for storing and retrieving episodic-like memories."""

    @pytest.mark.asyncio
    async def test_create_memory_calls_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.LESSON,
            content="RSI oversold works in ranging markets",
            weight=0.7,
            confidence=0.9,
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert mem.content == "RSI oversold works in ranging markets"

    @pytest.mark.asyncio
    async def test_create_memory_clamps_weight(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        # Try to create OBSERVATION with weight=1.0 (should clamp to 0.5)
        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.OBSERVATION,
            content="Market is trending up",
            weight=1.0,
        )
        assert mem.weight == 0.5

    @pytest.mark.asyncio
    async def test_create_memory_clamps_confidence(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.LESSON,
            content="test",
            confidence=1.5,
        )
        assert mem.confidence == 1.0


# =============================================================================
# Semantic Storage Tests
# =============================================================================


class TestSemanticStorage:
    """Tests for semantic-like memory operations."""

    @pytest.mark.asyncio
    async def test_create_memory_with_context_snapshot(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        context = {"pattern": "rsi_oversold", "win_rate": 0.65, "sample_size": 50}
        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.OPINION,
            content="RSI oversold is reliable",
            context_snapshot=context,
        )
        assert mem.context_snapshot == context

    @pytest.mark.asyncio
    async def test_create_memory_with_linked_trades(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.AFFIRMATION,
            content="Win streak confirmed approach",
            linked_trade_ids=["trade-1", "trade-2", "trade-3"],
        )
        assert mem.linked_trade_ids == ["trade-1", "trade-2", "trade-3"]


# =============================================================================
# Memory Decay Tests
# =============================================================================


class TestMemoryDecay:
    """Tests for inheritance decay mechanics."""

    def test_decay_reduces_weight(self):
        result = apply_inheritance_decay(0.8, decay_rate=0.2)
        assert result == pytest.approx(0.64)

    def test_decay_floors_at_minimum(self):
        result = apply_inheritance_decay(0.1, decay_rate=0.9)
        assert result == WEIGHT_FLOOR  # 0.1

    def test_zero_decay_preserves_weight(self):
        result = apply_inheritance_decay(0.8, decay_rate=0.0)
        assert result == 0.8

    def test_full_decay_floors_weight(self):
        result = apply_inheritance_decay(0.8, decay_rate=1.0)
        assert result == WEIGHT_FLOOR

    def test_decay_never_below_floor(self):
        for decay in [0.0, 0.1, 0.5, 0.9, 1.0]:
            result = apply_inheritance_decay(0.5, decay_rate=decay)
            assert result >= WEIGHT_FLOOR


# =============================================================================
# Jaccard Similarity Tests
# =============================================================================


class TestJaccardSimilarity:
    """Tests for Jaccard word similarity used in conflict detection."""

    def test_identical_texts(self):
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_disjoint_texts(self):
        assert jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        # "hello" in common, union = {"hello", "world", "there"} = 3 words
        result = jaccard_similarity("hello world", "hello there")
        assert result == pytest.approx(1 / 3)

    def test_empty_text_returns_zero(self):
        assert jaccard_similarity("", "hello") == 0.0
        assert jaccard_similarity("hello", "") == 0.0
        assert jaccard_similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert jaccard_similarity("Hello World", "hello world") == 1.0


# =============================================================================
# Memory Validation and Type Tests
# =============================================================================


class TestMemoryValidation:
    """Tests for memory type validation and helpers."""

    def test_valid_memory_types(self):
        for mem_type in MemoryType:
            assert validate_memory_type(mem_type.value)

    def test_invalid_memory_type(self):
        assert not validate_memory_type("nonexistent")
        assert not validate_memory_type("")

    def test_weak_memory_check(self):
        assert is_weak_memory(0.1)
        assert not is_weak_memory(0.5)
        assert is_weak_memory(0.14)
        assert not is_weak_memory(0.15)

    def test_priority_ordering(self):
        # Affirmation/Regret should be highest priority
        assert get_priority(MemoryType.AFFIRMATION) >= get_priority(MemoryType.LESSON)
        assert get_priority(MemoryType.REGRET) >= get_priority(MemoryType.LESSON)
        assert get_priority(MemoryType.LESSON) >= get_priority(MemoryType.OBSERVATION)

    def test_weight_range_returns_tuple(self):
        lo, hi = get_weight_range(MemoryType.LESSON)
        assert lo == 0.5
        assert hi == 0.9


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestMemoryEdgeCases:
    """Edge cases for memory operations."""

    def test_clamp_nan_weight(self):
        # NaN comparisons return False, so max/min should handle it
        # In practice, NaN breaks min/max, but the function should not crash
        result = clamp_weight_for_type(MemoryType.LESSON, float("nan"))
        # NaN > max returns False, NaN < min returns False
        # Result depends on implementation; we just verify no crash
        assert isinstance(result, float)

    def test_clamp_negative_weight(self):
        result = clamp_weight_for_type(MemoryType.OBSERVATION, -1.0)
        assert result == 0.1  # clamped to min

    def test_clamp_very_large_weight(self):
        result = clamp_weight_for_type(MemoryType.OBSERVATION, 999.0)
        assert result == 0.5  # clamped to max

    def test_inheritance_priority_all_types_present(self):
        for mem_type in MemoryType:
            assert mem_type in INHERITANCE_PRIORITY

    @pytest.mark.asyncio
    async def test_create_memory_with_spawned_from(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        mem = await create_memory(
            session=session,
            agent_id="child-agent",
            memory_type=MemoryType.LESSON,
            content="Inherited lesson",
            weight=0.7,
            spawned_from="parent-mem-123",
        )
        assert mem.spawned_from == "parent-mem-123"

    @pytest.mark.asyncio
    async def test_create_memory_default_linked_trades(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        from Agents.Services.memory_service import create_memory

        mem = await create_memory(
            session=session,
            agent_id="agent-1",
            memory_type=MemoryType.OBSERVATION,
            content="Market observation",
        )
        assert mem.linked_trade_ids == []

    def test_review_trade_count_constant(self):
        assert REVIEW_TRADE_COUNT == 50

    def test_max_memories_before_review_constant(self):
        assert MAX_MEMORIES_BEFORE_REVIEW == 100

    def test_conflict_threshold_constant(self):
        assert CONFLICT_THRESHOLD == 0.60
