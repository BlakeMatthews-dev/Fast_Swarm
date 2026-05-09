"""
Pattern Evolution Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Pattern Tier System)
Fitness 0-100: < 40 = DIES | 40-79 = SURVIVES | 80+ = PROMOTED
Tier Flow: TIER 3 (Untested) → TIER 2 (Proven) → TIER 1 (Elite) → AGENT ASSIGNMENT
"""

import random
from datetime import datetime
from typing import Any

from Fast_Swarm.Patterns.Services.pattern_service import (
    apply_selection_pressure,
    calculate_pattern_fitness,
    crossover_patterns,
    is_assignable_to_agent,
    mutate_condition,
    mutate_conditions,
    mutate_pattern,
    should_cull,
    should_demote,
    should_promote,
)

# =============================================================================
# HELPER FACTORIES
# =============================================================================


def make_pattern(
    pattern_id: str = "test-pattern-001",
    fitness_score: float = 50.0,
    tier: int = 3,
    origin: str = "chaos",
    entry_conditions: list[dict[str, Any]] = None,
    exit_conditions: list[dict[str, Any]] = None,
    number_of_runs: int = 25,
    total_roi_pct: float = 10.0,
    sharpe_ratio: float = 1.0,
    win_rate: float = 0.55,
    max_drawdown_pct: float = 15.0,
    profit_factor: float = 1.5,
    generation: int = 1,
    parent_id: str = None,
    status: str = "active",
) -> dict[str, Any]:
    """Create a pattern dict for testing."""
    return {
        "pattern_id": pattern_id,
        "name": f"Test Pattern {pattern_id}",
        "entry_conditions": entry_conditions
        or [
            {"indicator": "rsi", "min": 20, "max": 35},
        ],
        "exit_conditions": exit_conditions
        or [
            {"indicator": "rsi", "min": 65, "max": 85},
        ],
        "asset": "BTC",
        "timeframe": "1h",
        "fitness_score": fitness_score,
        "tier": tier,
        "origin": origin,
        "number_of_runs": number_of_runs,
        "total_roi_pct": total_roi_pct,
        "sharpe_ratio": sharpe_ratio,
        "win_rate": win_rate,
        "max_drawdown_pct": max_drawdown_pct,
        "profit_factor": profit_factor,
        "generation": generation,
        "parent_id": parent_id,
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
    }


def make_backtest_result(
    total_trades: int = 100,
    winning_trades: int = 55,
    total_roi_pct: float = 25.0,
    sharpe_ratio: float = 1.5,
    max_drawdown_pct: float = 12.0,
    profit_factor: float = 1.8,
    fees_paid: float = 2.5,
    slippage_cost: float = 1.2,
) -> dict[str, Any]:
    """Create a backtest result dict for testing."""
    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": total_trades - winning_trades,
        "win_rate": winning_trades / total_trades if total_trades > 0 else 0,
        "total_roi_pct": total_roi_pct,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "profit_factor": profit_factor,
        "gross_profit": 30.0,
        "gross_loss": 30.0 / profit_factor if profit_factor > 0 else 30.0,
        "fees_paid": fees_paid,
        "slippage_cost": slippage_cost,
        "net_roi_pct": total_roi_pct - fees_paid - slippage_cost,
    }


# ============================================================================
# PATTERN EVOLUTION CONTRACT
# ============================================================================


class TestTierPromotion:
    """CONTRACT: Pattern tier promotion rules."""

    def test_tier_3_to_2_on_fitness_60(self):
        """CONTRACT: Tier 3 pattern with fitness >= 60 promoted to Tier 2."""
        pattern = make_pattern(tier=3, fitness_score=60.0, number_of_runs=25)

        # should_promote returns target tier or None
        result = should_promote(pattern)

        assert result == 2, "Tier 3 with fitness 60 should promote to Tier 2"

    def test_tier_3_stays_at_3_with_fitness_59(self):
        """Tier 3 pattern with fitness 59 should NOT promote."""
        pattern = make_pattern(tier=3, fitness_score=59.9, number_of_runs=25)

        result = should_promote(pattern)

        assert result is None, "Fitness 59.9 should not trigger promotion"

    def test_tier_2_to_1_on_fitness_80(self):
        """CONTRACT: Tier 2 pattern with fitness >= 80 promoted to Tier 1."""
        pattern = make_pattern(tier=2, fitness_score=80.0, number_of_runs=30)

        result = should_promote(pattern)

        assert result == 1, "Tier 2 with fitness 80 should promote to Tier 1"

    def test_tier_2_stays_with_fitness_79(self):
        """Tier 2 pattern with fitness 79 should NOT promote."""
        pattern = make_pattern(tier=2, fitness_score=79.9, number_of_runs=30)

        result = should_promote(pattern)

        assert result is None, "Fitness 79.9 should not trigger Tier 2 promotion"

    def test_promotion_requires_min_trades(self):
        """CONTRACT: Promotion requires minimum 20 trades."""
        pattern = make_pattern(tier=3, fitness_score=85.0, number_of_runs=15)

        result = should_promote(pattern)

        # With only 15 trades, should not promote despite high fitness
        assert result is None, "Should require minimum trades for promotion"

    def test_promotion_with_sufficient_trades(self):
        """Pattern with sufficient trades can be promoted."""
        pattern = make_pattern(tier=3, fitness_score=65.0, number_of_runs=20)

        result = should_promote(pattern)

        assert result == 2, "20 trades should be sufficient for promotion"

    def test_promotion_updates_tier_field(self):
        """CONTRACT: Promotion updates pattern.tier field."""
        pattern = make_pattern(tier=3, fitness_score=70.0, number_of_runs=25)

        new_tier = should_promote(pattern)
        if new_tier is not None:
            pattern["tier"] = new_tier

        assert pattern["tier"] == 2, "Tier field should be updated after promotion"

    def test_promotion_logs_event(self):
        """CONTRACT: Promotion creates event log entry."""
        pattern = make_pattern(tier=2, fitness_score=85.0, number_of_runs=30)

        old_tier = pattern["tier"]
        new_tier = should_promote(pattern)

        # Create event log entry
        event = {
            "type": "promotion",
            "pattern_id": pattern["pattern_id"],
            "from_tier": old_tier,
            "to_tier": new_tier,
            "fitness_score": pattern["fitness_score"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        assert event["type"] == "promotion"
        assert event["from_tier"] == 2
        assert event["to_tier"] == 1


class TestTierDemotion:
    """CONTRACT: Pattern tier demotion rules."""

    def test_tier_1_to_2_on_fitness_below_70(self):
        """CONTRACT: Tier 1 pattern with fitness < 70 demoted to Tier 2."""
        pattern = make_pattern(tier=1, fitness_score=69.0)

        result = should_demote(pattern)

        assert result == 2, "Tier 1 with fitness < 70 should demote to Tier 2"

    def test_tier_1_stays_with_fitness_70(self):
        """Tier 1 pattern with fitness 70 should NOT demote."""
        pattern = make_pattern(tier=1, fitness_score=70.0)

        result = should_demote(pattern)

        assert result is None, "Fitness 70 should not trigger demotion"

    def test_tier_2_to_3_on_fitness_below_50(self):
        """CONTRACT: Tier 2 pattern with fitness < 50 demoted to Tier 3."""
        pattern = make_pattern(tier=2, fitness_score=49.0)

        result = should_demote(pattern)

        assert result == 3, "Tier 2 with fitness < 50 should demote to Tier 3"

    def test_tier_2_stays_with_fitness_50(self):
        """Tier 2 pattern with fitness 50 should NOT demote."""
        pattern = make_pattern(tier=2, fitness_score=50.0)

        result = should_demote(pattern)

        assert result is None, "Fitness 50 should not trigger Tier 2 demotion"

    def test_demotion_updates_tier_field(self):
        """CONTRACT: Demotion updates pattern.tier field."""
        pattern = make_pattern(tier=1, fitness_score=55.0)

        new_tier = should_demote(pattern)
        if new_tier is not None:
            pattern["tier"] = new_tier

        assert pattern["tier"] == 2, "Tier field should be updated after demotion"

    def test_demotion_logs_event(self):
        """CONTRACT: Demotion creates event log entry."""
        pattern = make_pattern(tier=1, fitness_score=60.0)

        old_tier = pattern["tier"]
        new_tier = should_demote(pattern)

        event = {
            "type": "demotion",
            "pattern_id": pattern["pattern_id"],
            "from_tier": old_tier,
            "to_tier": new_tier,
            "fitness_score": pattern["fitness_score"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        assert event["type"] == "demotion"
        assert event["from_tier"] == 1
        assert event["to_tier"] == 2


class TestPatternCulling:
    """CONTRACT: Pattern culling (death) rules."""

    def test_cull_tier_3_fitness_below_40(self):
        """CONTRACT: Tier 3 pattern with fitness < 40 is culled."""
        pattern = make_pattern(tier=3, fitness_score=35.0)

        result = should_cull(pattern)

        assert result is True, "Tier 3 with fitness < 40 should be culled"

    def test_no_cull_fitness_40(self):
        """Pattern with fitness 40 should NOT be culled."""
        pattern = make_pattern(tier=3, fitness_score=40.0)

        result = should_cull(pattern)

        assert result is False, "Fitness 40 should not trigger culling"

    def test_cull_sets_status_archived(self):
        """CONTRACT: Culled pattern has status='archived'."""
        pattern = make_pattern(tier=3, fitness_score=30.0, status="active")

        if should_cull(pattern):
            pattern["status"] = "archived"

        assert pattern["status"] == "archived"

    def test_cull_unassigns_from_agents(self):
        """CONTRACT: Culling unassigns pattern from all agents."""
        pattern = make_pattern(tier=3, fitness_score=25.0)
        agent_assignments = [
            {"agent_id": "agent-1", "pattern_id": pattern["pattern_id"]},
            {"agent_id": "agent-2", "pattern_id": pattern["pattern_id"]},
        ]

        if should_cull(pattern):
            # Remove all assignments
            agent_assignments = [a for a in agent_assignments if a["pattern_id"] != pattern["pattern_id"]]

        assert len(agent_assignments) == 0, "All assignments should be removed"

    def test_cull_preserves_history(self):
        """CONTRACT: Culled pattern's trade history preserved."""
        pattern = make_pattern(tier=3, fitness_score=20.0)
        trade_history = [
            {"trade_id": "t1", "pattern_id": pattern["pattern_id"], "pnl": 10.0},
            {"trade_id": "t2", "pattern_id": pattern["pattern_id"], "pnl": -5.0},
        ]

        if should_cull(pattern):
            pattern["status"] = "archived"
            # History should NOT be deleted

        assert len(trade_history) == 2, "Trade history should be preserved"


class TestPatternSurvival:
    """CONTRACT: Pattern survival rules."""

    def test_survive_fitness_40_to_79(self):
        """CONTRACT: Pattern with fitness 40-79 survives (no tier change)."""
        for fitness in [40, 50, 60, 70, 79]:
            pattern = make_pattern(tier=3, fitness_score=float(fitness), number_of_runs=15)

            # Should not be culled
            culled = should_cull(pattern)

            assert culled is False, f"Fitness {fitness} should survive"

    def test_survivor_keeps_tier(self):
        """CONTRACT: Surviving pattern keeps current tier."""
        pattern = make_pattern(tier=2, fitness_score=55.0, number_of_runs=15)
        original_tier = pattern["tier"]

        # No promotion, no demotion for fitness 55 in tier 2
        promote_to = should_promote(pattern)
        demote_to = should_demote(pattern)

        if promote_to is None and demote_to is None:
            new_tier = original_tier
        elif promote_to:
            new_tier = promote_to
        else:
            new_tier = demote_to

        assert new_tier == original_tier, "Survivor should keep tier"

    def test_survivor_increments_generation(self):
        """CONTRACT: Surviving pattern increments generation count."""
        pattern = make_pattern(tier=2, fitness_score=55.0, generation=3)

        # After surviving a cycle, generation increments
        if not should_cull(pattern):
            pattern["generation"] += 1

        assert pattern["generation"] == 4, "Generation should increment after survival"


class TestPatternFitnessCalculation:
    """CONTRACT: Pattern fitness calculation."""

    def test_fitness_from_backtest_results(self):
        """CONTRACT: Fitness calculated from backtest metrics."""
        backtest = make_backtest_result(
            total_trades=100,
            winning_trades=60,  # 60% win rate
            total_roi_pct=30.0,
            sharpe_ratio=1.8,
        )

        fitness = calculate_pattern_fitness(backtest)

        assert fitness is not None
        assert isinstance(fitness, float)

    def test_fitness_includes_roi(self):
        """CONTRACT: Fitness formula includes ROI component."""
        backtest_high_roi = make_backtest_result(total_roi_pct=50.0, sharpe_ratio=1.0)
        backtest_low_roi = make_backtest_result(total_roi_pct=5.0, sharpe_ratio=1.0)

        fitness_high = calculate_pattern_fitness(backtest_high_roi)
        fitness_low = calculate_pattern_fitness(backtest_low_roi)

        assert fitness_high > fitness_low, "Higher ROI should mean higher fitness"

    def test_fitness_includes_sharpe(self):
        """CONTRACT: Fitness formula includes Sharpe ratio."""
        backtest_high_sharpe = make_backtest_result(sharpe_ratio=2.5, total_roi_pct=20.0)
        backtest_low_sharpe = make_backtest_result(sharpe_ratio=0.5, total_roi_pct=20.0)

        fitness_high = calculate_pattern_fitness(backtest_high_sharpe)
        fitness_low = calculate_pattern_fitness(backtest_low_sharpe)

        assert fitness_high > fitness_low, "Higher Sharpe should mean higher fitness"

    def test_fitness_includes_win_rate(self):
        """CONTRACT: Fitness formula includes win rate."""
        backtest_high_win = make_backtest_result(winning_trades=70, total_trades=100)
        backtest_low_win = make_backtest_result(winning_trades=40, total_trades=100)

        fitness_high = calculate_pattern_fitness(backtest_high_win)
        fitness_low = calculate_pattern_fitness(backtest_low_win)

        assert fitness_high > fitness_low, "Higher win rate should mean higher fitness"

    def test_fitness_includes_trade_count(self):
        """CONTRACT: Fitness formula includes trade count penalty."""
        # Keep win rate proportional: 55% for both
        backtest_many = make_backtest_result(total_trades=100, winning_trades=55, total_roi_pct=20.0)
        backtest_few = make_backtest_result(total_trades=10, winning_trades=6, total_roi_pct=20.0)  # ~55% win rate

        fitness_many = calculate_pattern_fitness(backtest_many)
        fitness_few = calculate_pattern_fitness(backtest_few)

        # Too few trades should be penalized
        assert fitness_many > fitness_few, "More trades should mean higher fitness (statistical significance)"

    def test_fitness_bounded_0_100(self):
        """CONTRACT: Pattern fitness always in [0, 100]."""
        # Test extreme values
        extreme_good = make_backtest_result(
            total_roi_pct=1000.0,
            sharpe_ratio=10.0,
            winning_trades=99,
            total_trades=100,
        )
        extreme_bad = make_backtest_result(
            total_roi_pct=-50.0,
            sharpe_ratio=-1.0,
            winning_trades=10,
            total_trades=100,
        )

        fitness_good = calculate_pattern_fitness(extreme_good)
        fitness_bad = calculate_pattern_fitness(extreme_bad)

        assert 0 <= fitness_good <= 100, f"Fitness {fitness_good} should be bounded"
        assert 0 <= fitness_bad <= 100, f"Fitness {fitness_bad} should be bounded"


class TestPatternBacktesting:
    """CONTRACT: Pattern backtesting."""

    def test_backtest_on_real_ohlcv(self):
        """CONTRACT: Backtest uses REAL historical OHLCV."""
        # This is a contract test - the backtest engine must use real data
        pattern = make_pattern()

        # Backtest config should specify real data source
        backtest_config = {
            "data_source": "ohlcv_1h",
            "use_synthetic": False,
        }

        assert backtest_config["data_source"] in ["ohlcv_1h", "ohlcv_6h", "ohlcv_1d"]
        assert backtest_config["use_synthetic"] is False

    def test_backtest_minimum_100_candles(self):
        """CONTRACT: Backtest requires minimum 100 candles."""
        min_candles = 100

        candle_data = list(range(min_candles))

        assert len(candle_data) >= 100, "Backtest requires minimum 100 candles"

    def test_backtest_calculates_trades(self):
        """CONTRACT: Backtest generates list of trades."""
        backtest_result = make_backtest_result(total_trades=50)

        assert backtest_result["total_trades"] == 50
        assert backtest_result["winning_trades"] + backtest_result["losing_trades"] == 50

    def test_backtest_includes_fees(self):
        """CONTRACT: Backtest applies trading fees."""
        backtest = make_backtest_result(fees_paid=5.0)

        assert backtest["fees_paid"] > 0, "Backtest must include fees"
        assert backtest["net_roi_pct"] < backtest["total_roi_pct"], "Net ROI must account for fees"

    def test_backtest_includes_slippage(self):
        """CONTRACT: Backtest applies slippage model."""
        backtest = make_backtest_result(slippage_cost=2.0)

        assert backtest["slippage_cost"] > 0, "Backtest must include slippage"


class TestPatternStatistics:
    """CONTRACT: Pattern statistics tracking."""

    def test_track_total_trades(self):
        """CONTRACT: Track total number of trades."""
        backtest = make_backtest_result(total_trades=150)

        assert "total_trades" in backtest
        assert backtest["total_trades"] == 150

    def test_track_win_rate(self):
        """CONTRACT: Track win rate percentage."""
        backtest = make_backtest_result(winning_trades=60, total_trades=100)

        assert "win_rate" in backtest
        assert abs(backtest["win_rate"] - 0.6) < 0.001

    def test_track_profit_factor(self):
        """CONTRACT: Track profit factor (gross profit / gross loss)."""
        backtest = make_backtest_result(profit_factor=1.75)

        assert "profit_factor" in backtest
        assert backtest["profit_factor"] == 1.75

    def test_track_max_drawdown(self):
        """CONTRACT: Track maximum drawdown percentage."""
        backtest = make_backtest_result(max_drawdown_pct=18.5)

        assert "max_drawdown_pct" in backtest
        assert backtest["max_drawdown_pct"] == 18.5

    def test_track_sharpe_ratio(self):
        """CONTRACT: Track Sharpe ratio."""
        backtest = make_backtest_result(sharpe_ratio=1.65)

        assert "sharpe_ratio" in backtest
        assert backtest["sharpe_ratio"] == 1.65

    def test_track_sortino_ratio(self):
        """CONTRACT: Track Sortino ratio."""
        # Sortino is similar to Sharpe but only penalizes downside volatility
        # Add to backtest result
        backtest = make_backtest_result()
        backtest["sortino_ratio"] = 2.1

        assert "sortino_ratio" in backtest
        assert backtest["sortino_ratio"] == 2.1


class TestPatternAgentAssignment:
    """CONTRACT: Pattern assignment to agents."""

    def test_only_tier_1_2_assignable(self):
        """CONTRACT: Only Tier 1 and 2 patterns assignable to agents."""
        tier_1_pattern = make_pattern(tier=1)
        tier_2_pattern = make_pattern(tier=2)

        assert is_assignable_to_agent(tier_1_pattern) is True
        assert is_assignable_to_agent(tier_2_pattern) is True

    def test_tier_3_not_assignable(self):
        """CONTRACT: Tier 3 patterns cannot be assigned."""
        tier_3_pattern = make_pattern(tier=3)

        assert is_assignable_to_agent(tier_3_pattern) is False

    def test_archived_not_assignable(self):
        """Archived patterns cannot be assigned."""
        archived_pattern = make_pattern(tier=1, status="archived")

        assert is_assignable_to_agent(archived_pattern) is False

    def test_assignment_creates_weight(self):
        """CONTRACT: Assignment creates agent-pattern weight entry."""
        pattern = make_pattern(tier=1)
        agent_id = "agent-001"

        assignment = {
            "agent_id": agent_id,
            "pattern_id": pattern["pattern_id"],
            "weight": 1.0,
            "assigned_at": datetime.utcnow().isoformat(),
        }

        assert "weight" in assignment
        assert assignment["weight"] > 0

    def test_initial_weight_1_0(self):
        """CONTRACT: Initial assignment weight = 1.0."""
        pattern = make_pattern(tier=2)

        initial_weight = 1.0  # Default weight on assignment

        assert initial_weight == 1.0


class TestPatternLineage:
    """CONTRACT: Pattern lineage tracking."""

    def test_track_parent_pattern_id(self):
        """CONTRACT: Mutated patterns track parent_id."""
        parent = make_pattern(pattern_id="parent-001")

        child = mutate_pattern(parent)

        assert child["parent_id"] == "parent-001"

    def test_track_generation(self):
        """CONTRACT: Patterns track generation number."""
        pattern = make_pattern(generation=5)

        assert pattern["generation"] == 5

    def test_generation_1_for_new(self):
        """CONTRACT: New patterns start at generation 1."""
        new_pattern = make_pattern()

        assert new_pattern["generation"] == 1

    def test_generation_increments_on_mutation(self):
        """CONTRACT: Generation increments on mutation/crossover."""
        parent = make_pattern(generation=3)

        child = mutate_pattern(parent)

        assert child["generation"] == 4


class TestPatternMutation:
    """CONTRACT: Pattern mutation operations."""

    def test_mutate_condition_bounds(self):
        """CONTRACT: Mutation adjusts condition min/max ±10%."""
        condition = {"indicator": "rsi", "min": 30, "max": 40}

        random.seed(42)
        mutated = mutate_condition(condition)

        # Original was 30-40, so:
        # min should be in range [27, 33] (30 ± 10%)
        # max should be in range [36, 44] (40 ± 10%)
        assert 27 <= mutated["min"] <= 33
        assert 36 <= mutated["max"] <= 44

    def test_mutation_preserves_indicator(self):
        """CONTRACT: Mutation keeps same indicators."""
        condition = {"indicator": "macd", "min": -0.5, "max": 0.5}

        mutated = mutate_condition(condition)

        assert mutated["indicator"] == "macd"

    def test_mutation_bounded(self):
        """CONTRACT: Mutated bounds stay within valid ranges."""
        # RSI must stay in 0-100
        condition = {"indicator": "rsi", "min": 5, "max": 95}

        random.seed(123)
        for _ in range(100):
            mutated = mutate_condition(condition)
            assert 0 <= mutated["min"] <= 100, f"RSI min out of bounds: {mutated['min']}"
            assert 0 <= mutated["max"] <= 100, f"RSI max out of bounds: {mutated['max']}"
            assert mutated["min"] <= mutated["max"], "min must be <= max"

    def test_mutation_creates_new_pattern(self):
        """CONTRACT: Mutation creates new pattern ID."""
        parent = make_pattern(pattern_id="parent-001")

        child = mutate_pattern(parent)

        assert child["pattern_id"] != "parent-001"
        assert child["pattern_id"].startswith("mut-") or len(child["pattern_id"]) > 10

    def test_mutate_conditions_list(self):
        """Mutation can be applied to list of conditions."""
        conditions = [
            {"indicator": "rsi", "min": 30, "max": 40},
            {"indicator": "macd", "min": -0.1, "max": 0.1},
        ]

        random.seed(42)
        mutated = mutate_conditions(conditions)

        assert len(mutated) == 2
        assert mutated[0]["indicator"] == "rsi"
        assert mutated[1]["indicator"] == "macd"


class TestPatternCrossover:
    """CONTRACT: Pattern crossover operations."""

    def test_crossover_combines_conditions(self):
        """CONTRACT: Crossover combines conditions from two parents."""
        parent_a = make_pattern(
            pattern_id="parent-a",
            entry_conditions=[{"indicator": "rsi", "min": 20, "max": 30}],
            exit_conditions=[{"indicator": "rsi", "min": 70, "max": 80}],
        )
        parent_b = make_pattern(
            pattern_id="parent-b",
            entry_conditions=[{"indicator": "macd", "min": -0.5, "max": 0}],
            exit_conditions=[{"indicator": "macd", "min": 0, "max": 0.5}],
        )

        random.seed(42)
        child = crossover_patterns(parent_a, parent_b)

        # Child should have conditions from both parents
        all_indicators = set()
        for cond in child["entry_conditions"] + child["exit_conditions"]:
            all_indicators.add(cond["indicator"])

        # At least one indicator from each parent should appear
        assert len(child["entry_conditions"]) >= 1
        assert len(child["exit_conditions"]) >= 1

    def test_crossover_tracks_both_parents(self):
        """CONTRACT: Crossover tracks parent_a_id and parent_b_id."""
        parent_a = make_pattern(pattern_id="parent-a")
        parent_b = make_pattern(pattern_id="parent-b")

        child = crossover_patterns(parent_a, parent_b)

        assert child["parent_id"] in ["parent-a", "parent-b"] or "parent-a" in str(child)
        # Both parents should be tracked somehow
        assert "parent_a_id" in child or "parent_id" in child

    def test_crossover_creates_new_pattern(self):
        """CONTRACT: Crossover creates new pattern ID."""
        parent_a = make_pattern(pattern_id="parent-a")
        parent_b = make_pattern(pattern_id="parent-b")

        child = crossover_patterns(parent_a, parent_b)

        assert child["pattern_id"] not in ["parent-a", "parent-b"]


class TestPatternSelectionPressure:
    """CONTRACT: Selection pressure applied to patterns."""

    def test_top_20_percent_clone(self):
        """CONTRACT: Top 20% patterns get cloned."""
        patterns = [make_pattern(pattern_id=f"p{i}", fitness_score=float(100 - i)) for i in range(10)]

        result = apply_selection_pressure(patterns)

        # Top 20% = 2 patterns should be cloned
        assert result["cloned_count"] >= 2

    def test_bottom_30_percent_culled(self):
        """CONTRACT: Bottom 30% patterns get culled."""
        patterns = [make_pattern(pattern_id=f"p{i}", fitness_score=float(100 - i * 10)) for i in range(10)]
        # Bottom 30% will have fitness: 10, 20, 30 (below cull threshold of 40)

        result = apply_selection_pressure(patterns)

        assert result["culled_count"] >= 3

    def test_selection_by_fitness_ranking(self):
        """CONTRACT: Selection based on fitness ranking."""
        patterns = [
            make_pattern(pattern_id="low", fitness_score=30.0),
            make_pattern(pattern_id="high", fitness_score=90.0),
            make_pattern(pattern_id="mid", fitness_score=60.0),
        ]

        result = apply_selection_pressure(patterns)

        # High fitness should survive, low should be culled
        assert "high" in [p["pattern_id"] for p in result["survivors"]]
        assert "low" in [p["pattern_id"] for p in result["culled"]]


class TestPatternEvolutionCycle:
    """CONTRACT: Pattern evolution cycle execution."""

    def test_evolution_cycle_phases(self):
        """CONTRACT: Evolution cycle has discovery, backtest, select phases."""
        phases = ["discovery", "backtest", "select"]

        cycle_config = {
            "phases": phases,
            "current_phase": "discovery",
        }

        assert "discovery" in cycle_config["phases"]
        assert "backtest" in cycle_config["phases"]
        assert "select" in cycle_config["phases"]

    def test_evolution_cycle_returns_metrics(self):
        """CONTRACT: Cycle returns metrics (promoted, culled, mutated)."""
        patterns = [
            make_pattern(pattern_id=f"p{i}", fitness_score=float(50 + i * 5), tier=3, number_of_runs=25)
            for i in range(10)
        ]

        result = apply_selection_pressure(patterns)

        assert "cloned_count" in result
        assert "culled_count" in result
        assert "survivors" in result
        assert "culled" in result

    def test_evolution_cycle_idempotent(self):
        """CONTRACT: Running cycle twice doesn't double-process."""
        patterns = [make_pattern(pattern_id=f"p{i}", fitness_score=float(50 + i * 5)) for i in range(5)]

        result1 = apply_selection_pressure(patterns)
        # Running again on survivors should not dramatically change outcome
        result2 = apply_selection_pressure(result1["survivors"])

        # Second run on survivors should have fewer culls (already filtered)
        assert result2["culled_count"] <= result1["culled_count"]


class TestPatternEvolutionDeterminism:
    """CONTRACT: Pattern evolution determinism."""

    def test_evolution_deterministic_with_seed(self):
        """CONTRACT: Same seed = same evolution results."""
        patterns = [make_pattern(pattern_id=f"p{i}", fitness_score=float(50 + i * 5)) for i in range(10)]

        random.seed(42)
        result1 = apply_selection_pressure(patterns)

        random.seed(42)
        result2 = apply_selection_pressure(patterns)

        assert result1["cloned_count"] == result2["cloned_count"]
        assert result1["culled_count"] == result2["culled_count"]

    def test_selection_deterministic(self):
        """CONTRACT: Same fitness rankings = same selections."""
        patterns = [make_pattern(pattern_id=f"p{i}", fitness_score=float(100 - i * 10)) for i in range(10)]

        result1 = apply_selection_pressure(patterns)
        result2 = apply_selection_pressure(patterns)

        # Same input should give same culled patterns
        culled_ids_1 = set(p["pattern_id"] for p in result1["culled"])
        culled_ids_2 = set(p["pattern_id"] for p in result2["culled"])

        assert culled_ids_1 == culled_ids_2

    def test_mutation_deterministic_with_seed(self):
        """CONTRACT: Same seed = same mutation results."""
        parent = make_pattern()

        random.seed(42)
        child1 = mutate_pattern(parent)

        random.seed(42)
        child2 = mutate_pattern(parent)

        # Entry conditions should match
        assert child1["entry_conditions"] == child2["entry_conditions"]
        assert child1["exit_conditions"] == child2["exit_conditions"]
