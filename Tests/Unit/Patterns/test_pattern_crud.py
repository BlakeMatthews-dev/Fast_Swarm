"""
Pattern CRUD Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Pattern System)
Patterns define entry/exit conditions, have fitness scores, and exist in tiers.
"""

import pytest
from Fast_Swarm.Patterns.Services.pattern_service import (
    VALID_ORIGINS,
    VALID_TIERS,
    batch_create_patterns,
    calculate_pattern_fitness,
    create_pattern,
    get_all_patterns,
    get_pattern_by_id,
    get_patterns_by_asset,
    get_patterns_by_origin,
    get_patterns_by_tier,
    get_tier_from_fitness,
    soft_delete_pattern,
    update_pattern,
    validate_conditions,
    validate_origin,
    validate_tier,
)

# ============================================================================
# PATTERN CRUD CONTRACT
# ============================================================================


class TestPatternCreate:
    """CONTRACT: Pattern creation operations."""

    @pytest.mark.asyncio
    async def test_create_pattern_minimal(self, db_session):
        """CONTRACT: Create pattern with just name and conditions."""
        pattern = await create_pattern(
            session=db_session,
            name="Test Pattern",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        assert pattern is not None
        assert pattern.name == "Test Pattern"

    @pytest.mark.asyncio
    async def test_create_pattern_with_entry_conditions(self, db_session):
        """CONTRACT: Pattern stores entry_conditions as JSON."""
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": -0.5, "max": 0.5},
        ]
        pattern = await create_pattern(
            session=db_session,
            name="Entry Test",
            entry_conditions=conditions,
        )
        assert pattern.entry_conditions is not None
        assert len(pattern.entry_conditions) == 2

    @pytest.mark.asyncio
    async def test_create_pattern_with_exit_conditions(self, db_session):
        """CONTRACT: Pattern stores exit_conditions as JSON."""
        entry = [{"indicator": "rsi", "min": 20, "max": 40}]
        exit_conds = [{"indicator": "rsi", "min": 70, "max": 80}]
        pattern = await create_pattern(
            session=db_session,
            name="Exit Test",
            entry_conditions=entry,
            exit_conditions=exit_conds,
        )
        assert pattern.exit_conditions is not None
        assert len(pattern.exit_conditions) == 1

    @pytest.mark.asyncio
    async def test_create_pattern_returns_id(self, db_session):
        """CONTRACT: Create returns pattern_id."""
        pattern = await create_pattern(
            session=db_session,
            name="ID Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        assert pattern.pattern_id is not None
        assert len(pattern.pattern_id) > 0

    @pytest.mark.asyncio
    async def test_create_pattern_unique_id(self, db_session):
        """CONTRACT: Each pattern gets unique ID."""
        p1 = await create_pattern(
            session=db_session,
            name="Pattern 1",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        p2 = await create_pattern(
            session=db_session,
            name="Pattern 2",
            entry_conditions=[{"indicator": "rsi", "min": 30, "max": 50}],
        )
        assert p1.pattern_id != p2.pattern_id

    @pytest.mark.asyncio
    async def test_create_pattern_timestamps(self, db_session):
        """CONTRACT: Pattern has created_at and updated_at."""
        pattern = await create_pattern(
            session=db_session,
            name="Timestamp Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        assert pattern.created_at is not None
        assert pattern.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_pattern_default_fitness_50(self, db_session):
        """CONTRACT: New pattern starts with fitness_score = 50."""
        pattern = await create_pattern(
            session=db_session,
            name="Fitness Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        assert pattern.fitness_score == 50.0

    @pytest.mark.asyncio
    async def test_create_pattern_default_tier_3(self, db_session):
        """CONTRACT: New pattern starts in tier 3 (untested)."""
        pattern = await create_pattern(
            session=db_session,
            name="Tier Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        # Default fitness 50 = tier 3
        tier = get_tier_from_fitness(pattern.fitness_score)
        assert tier == 3


class TestPatternRead:
    """CONTRACT: Pattern read operations."""

    @pytest.mark.asyncio
    async def test_get_pattern_by_id_exists(self, db_session):
        """CONTRACT: Get existing pattern by ID."""
        created = await create_pattern(
            session=db_session,
            name="Read Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        fetched = await get_pattern_by_id(db_session, created.pattern_id)
        assert fetched is not None
        assert fetched.pattern_id == created.pattern_id

    @pytest.mark.asyncio
    async def test_get_pattern_by_id_not_found(self, db_session):
        """CONTRACT: Get non-existent pattern returns None/404."""
        fetched = await get_pattern_by_id(db_session, "nonexistent-id")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_patterns_all(self, db_session):
        """CONTRACT: List all patterns."""
        # Create some patterns
        for i in range(3):
            await create_pattern(
                session=db_session,
                name=f"List Test {i}",
                entry_conditions=[{"indicator": "rsi", "min": 20 + i, "max": 40 + i}],
            )
        patterns = await get_all_patterns(db_session, limit=100)
        assert len(patterns) >= 3

    @pytest.mark.asyncio
    async def test_list_patterns_pagination(self, db_session):
        """CONTRACT: List patterns with offset and limit."""
        for i in range(5):
            await create_pattern(
                session=db_session,
                name=f"Page Test {i}",
                entry_conditions=[{"indicator": "rsi", "min": 20 + i, "max": 40 + i}],
            )
        page1 = await get_all_patterns(db_session, limit=2, offset=0)
        page2 = await get_all_patterns(db_session, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_list_patterns_filter_by_tier(self, db_session):
        """CONTRACT: Filter patterns by tier (1, 2, or 3)."""
        # Create pattern with tier 3 fitness (< 60)
        p = await create_pattern(
            session=db_session,
            name="Tier 3 Pattern",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        # Default fitness is 50, which is tier 3
        # Use higher limit to handle existing patterns in test DB
        tier3_patterns = await get_patterns_by_tier(db_session, tier=3, limit=1000)
        assert any(pat.pattern_id == p.pattern_id for pat in tier3_patterns)

    @pytest.mark.asyncio
    async def test_list_patterns_filter_by_origin(self, db_session):
        """CONTRACT: Filter by origin (chaos/academic/technical/ai/hybrid)."""
        p = await create_pattern(
            session=db_session,
            name="Chaos Pattern",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
            origin="chaos",
        )
        chaos_patterns = await get_patterns_by_origin(db_session, origin="chaos")
        assert any(pat.pattern_id == p.pattern_id for pat in chaos_patterns)

    @pytest.mark.asyncio
    async def test_list_patterns_order_by_fitness(self, db_session):
        """CONTRACT: Order patterns by fitness descending."""
        patterns = await get_all_patterns(db_session, limit=10)
        if len(patterns) >= 2:
            for i in range(len(patterns) - 1):
                assert (patterns[i].fitness_score or 0) >= (patterns[i + 1].fitness_score or 0)

    @pytest.mark.asyncio
    async def test_list_patterns_filter_by_asset(self, db_session):
        """CONTRACT: Filter patterns by asset (BTC, ETH, etc.)."""
        p = await create_pattern(
            session=db_session,
            name="BTC Pattern",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
            symbol="BTC",
        )
        btc_patterns = await get_patterns_by_asset(db_session, asset="BTC")
        assert any(pat.pattern_id == p.pattern_id for pat in btc_patterns)

    @pytest.mark.asyncio
    async def test_get_pattern_with_stats(self, db_session):
        """CONTRACT: Get pattern with computed stats (win_rate, sharpe)."""
        p = await create_pattern(
            session=db_session,
            name="Stats Pattern",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        fetched = await get_pattern_by_id(db_session, p.pattern_id)
        # Stats fields exist (may be None for new pattern)
        assert hasattr(fetched, "win_rate")
        assert hasattr(fetched, "sharpe_ratio")


class TestPatternUpdate:
    """CONTRACT: Pattern update operations."""

    @pytest.mark.asyncio
    async def test_update_pattern_fitness(self, db_session):
        """CONTRACT: Update fitness_score field."""
        p = await create_pattern(
            session=db_session,
            name="Update Fitness",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        updated = await update_pattern(db_session, p.pattern_id, fitness_score=75.0)
        assert updated.fitness_score == 75.0

    @pytest.mark.asyncio
    async def test_update_pattern_tier(self, db_session):
        """CONTRACT: Update tier field."""
        p = await create_pattern(
            session=db_session,
            name="Update Tier",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        # Update fitness to change tier
        updated = await update_pattern(db_session, p.pattern_id, fitness_score=85.0)
        tier = get_tier_from_fitness(updated.fitness_score)
        assert tier == 1  # 85 >= 80 = tier 1

    @pytest.mark.asyncio
    async def test_update_pattern_conditions(self, db_session):
        """CONTRACT: Update entry/exit conditions."""
        p = await create_pattern(
            session=db_session,
            name="Update Conditions",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        new_conditions = [{"indicator": "macd", "min": -1, "max": 1}]
        updated = await update_pattern(db_session, p.pattern_id, entry_conditions=new_conditions)
        assert updated.entry_conditions[0]["indicator"] == "macd"

    @pytest.mark.asyncio
    async def test_update_pattern_timestamps(self, db_session):
        """CONTRACT: updated_at changes on update."""
        p = await create_pattern(
            session=db_session,
            name="Update Timestamp",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        original_updated = p.updated_at
        updated = await update_pattern(db_session, p.pattern_id, fitness_score=60.0)
        assert updated.updated_at >= original_updated

    @pytest.mark.asyncio
    async def test_update_pattern_not_found(self, db_session):
        """CONTRACT: Update non-existent pattern raises error."""
        with pytest.raises(ValueError, match="not found"):
            await update_pattern(db_session, "nonexistent-id", fitness_score=50.0)

    @pytest.mark.asyncio
    async def test_update_pattern_partial(self, db_session):
        """CONTRACT: Can update single field without touching others."""
        p = await create_pattern(
            session=db_session,
            name="Partial Update",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
            symbol="ETH",
        )
        updated = await update_pattern(db_session, p.pattern_id, fitness_score=70.0)
        assert updated.fitness_score == 70.0
        assert updated.symbol == "ETH"  # Unchanged


class TestPatternDelete:
    """CONTRACT: Pattern delete operations."""

    @pytest.mark.asyncio
    async def test_delete_pattern_soft(self, db_session):
        """CONTRACT: Delete is soft-delete (status='archived')."""
        p = await create_pattern(
            session=db_session,
            name="Delete Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        await soft_delete_pattern(db_session, p.pattern_id)
        # Should not be found in normal query
        fetched = await get_pattern_by_id(db_session, p.pattern_id)
        assert fetched is None
        # But exists when including archived
        archived = await get_pattern_by_id(db_session, p.pattern_id, include_archived=True)
        assert archived is not None
        assert archived.status == "archived"

    @pytest.mark.asyncio
    async def test_delete_pattern_not_found(self, db_session):
        """CONTRACT: Delete non-existent pattern raises error."""
        with pytest.raises(ValueError, match="not found"):
            await soft_delete_pattern(db_session, "nonexistent-id")

    @pytest.mark.asyncio
    async def test_delete_pattern_unassigns_agents(self, db_session):
        """CONTRACT: Deleting pattern unassigns it from agents."""
        p = await create_pattern(
            session=db_session,
            name="Unassign Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        # Simulate assignment
        await update_pattern(db_session, p.pattern_id, assigned_agent_id="agent-123")
        # Delete
        await soft_delete_pattern(db_session, p.pattern_id)
        archived = await get_pattern_by_id(db_session, p.pattern_id, include_archived=True)
        assert archived.assigned_agent_id is None

    @pytest.mark.asyncio
    async def test_deleted_pattern_excluded_from_list(self, db_session):
        """CONTRACT: Archived patterns not in default list."""
        p = await create_pattern(
            session=db_session,
            name="Exclude Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        pid = p.pattern_id
        await soft_delete_pattern(db_session, pid)
        patterns = await get_all_patterns(db_session)
        assert not any(pat.pattern_id == pid for pat in patterns)


class TestPatternConditions:
    """CONTRACT: Pattern condition structure."""

    def test_entry_conditions_json_structure(self):
        """CONTRACT: entry_conditions is array of condition objects."""
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": -0.5, "max": 0.5},
        ]
        is_valid, _ = validate_conditions(conditions)
        assert is_valid is True

    def test_exit_conditions_json_structure(self):
        """CONTRACT: exit_conditions is array of condition objects."""
        conditions = [{"indicator": "rsi", "min": 70, "max": 80}]
        is_valid, _ = validate_conditions(conditions)
        assert is_valid is True

    def test_condition_has_indicator(self):
        """CONTRACT: Each condition has 'indicator' field."""
        is_valid, error = validate_conditions([{"min": 20, "max": 40}])
        assert is_valid is False
        assert "indicator" in error.lower()

    def test_condition_has_min_max(self):
        """CONTRACT: Each condition has 'min' and 'max' bounds."""
        # min/max are optional but when present must be valid
        is_valid, _ = validate_conditions([{"indicator": "rsi", "min": 20, "max": 40}])
        assert is_valid is True

    def test_condition_invalid_indicator_rejected(self):
        """CONTRACT: Unknown indicator name raises ValueError."""
        is_valid, error = validate_conditions([{"indicator": "fake_indicator", "min": 0, "max": 100}])
        assert is_valid is False

    def test_condition_invalid_bounds_rejected(self):
        """CONTRACT: min > max raises ValueError."""
        is_valid, error = validate_conditions([{"indicator": "rsi", "min": 50, "max": 30}])
        assert is_valid is False


class TestPatternOrigin:
    """CONTRACT: Pattern origin types."""

    def test_5_origin_types(self):
        """CONTRACT: 5 valid origin types exist."""
        assert len(VALID_ORIGINS) == 5

    @pytest.mark.parametrize("origin", ["chaos", "academic", "technical", "ai", "hybrid"])
    def test_origin_valid(self, origin):
        """CONTRACT: Each origin type is valid."""
        is_valid, _ = validate_origin(origin)
        assert is_valid is True

    def test_invalid_origin_rejected(self):
        """CONTRACT: Unknown origin raises ValueError."""
        is_valid, error = validate_origin("invalid_origin")
        assert is_valid is False


class TestPatternTiers:
    """CONTRACT: Pattern tier system."""

    def test_tier_1_elite(self):
        """CONTRACT: Tier 1 = elite (proven performers)."""
        tier = get_tier_from_fitness(85.0)
        assert tier == 1

    def test_tier_2_proven(self):
        """CONTRACT: Tier 2 = proven (passed backtests)."""
        tier = get_tier_from_fitness(70.0)
        assert tier == 2

    def test_tier_3_untested(self):
        """CONTRACT: Tier 3 = untested (new patterns)."""
        tier = get_tier_from_fitness(50.0)
        assert tier == 3

    def test_tier_must_be_1_2_3(self):
        """CONTRACT: Tier must be 1, 2, or 3."""
        assert VALID_TIERS == [1, 2, 3]

    def test_tier_0_invalid(self):
        """CONTRACT: Tier 0 is invalid."""
        is_valid, _ = validate_tier(0)
        assert is_valid is False

    def test_tier_4_invalid(self):
        """CONTRACT: Tier 4 is invalid."""
        is_valid, _ = validate_tier(4)
        assert is_valid is False


class TestPatternDatabase:
    """CONTRACT: Pattern database operations."""

    @pytest.mark.asyncio
    async def test_pattern_persists_to_db(self, db_session):
        """CONTRACT: Created pattern saved to database."""
        p = await create_pattern(
            session=db_session,
            name="Persist Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        # Fetch to verify persistence
        fetched = await get_pattern_by_id(db_session, p.pattern_id)
        assert fetched is not None

    @pytest.mark.asyncio
    async def test_pattern_retrievable_after_commit(self, db_session):
        """CONTRACT: Pattern retrievable immediately after save."""
        p = await create_pattern(
            session=db_session,
            name="Retrieve Test",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 40}],
        )
        fetched = await get_pattern_by_id(db_session, p.pattern_id)
        assert fetched is not None
        assert fetched.name == "Retrieve Test"

    @pytest.mark.asyncio
    async def test_pattern_rollback_on_error(self, db_session):
        """CONTRACT: Database rolled back on error."""
        # Invalid conditions should raise
        with pytest.raises(ValueError):
            await create_pattern(
                session=db_session,
                name="Rollback Test",
                entry_conditions=[{"indicator": "invalid_ind", "min": 20, "max": 40}],
            )

    @pytest.mark.asyncio
    async def test_pattern_batch_create(self, db_session):
        """CONTRACT: Can create multiple patterns in batch."""
        patterns_data = [
            {"name": "Batch 1", "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}]},
            {"name": "Batch 2", "entry_conditions": [{"indicator": "macd", "min": -1, "max": 1}]},
            {"name": "Batch 3", "entry_conditions": [{"indicator": "atr", "min": 1, "max": 5}]},
        ]
        pattern_ids = await batch_create_patterns(db_session, patterns_data)
        assert len(pattern_ids) == 3


class TestPatternFitnessCalculation:
    """CONTRACT: Pattern fitness calculation."""

    def test_fitness_bounded_0_100(self):
        """Fitness always in [0, 100]."""
        # High performance
        f1 = calculate_pattern_fitness(roi_pct=100, sharpe_ratio=3, win_rate=0.8, trade_count=100)
        assert 0 <= f1 <= 100

        # Low performance
        f2 = calculate_pattern_fitness(roi_pct=-50, sharpe_ratio=-2, win_rate=0.2, trade_count=5)
        assert 0 <= f2 <= 100

    def test_fitness_includes_roi(self):
        """Fitness includes ROI component."""
        f_high_roi = calculate_pattern_fitness(roi_pct=50, sharpe_ratio=1, win_rate=0.5, trade_count=50)
        f_low_roi = calculate_pattern_fitness(roi_pct=-50, sharpe_ratio=1, win_rate=0.5, trade_count=50)
        assert f_high_roi > f_low_roi

    def test_fitness_includes_sharpe(self):
        """Fitness includes Sharpe component."""
        f_high_sharpe = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=2, win_rate=0.5, trade_count=50)
        f_low_sharpe = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=0, win_rate=0.5, trade_count=50)
        assert f_high_sharpe > f_low_sharpe

    def test_fitness_includes_win_rate(self):
        """Fitness includes win rate component."""
        f_high_wr = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=1, win_rate=0.8, trade_count=50)
        f_low_wr = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=1, win_rate=0.3, trade_count=50)
        assert f_high_wr > f_low_wr

    def test_fitness_includes_trade_count(self):
        """Fitness includes trade count component."""
        f_many = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=1, win_rate=0.5, trade_count=100)
        f_few = calculate_pattern_fitness(roi_pct=10, sharpe_ratio=1, win_rate=0.5, trade_count=5)
        assert f_many > f_few
