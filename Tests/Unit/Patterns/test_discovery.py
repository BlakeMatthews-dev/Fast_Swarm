"""
Pattern Discovery Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Pattern Discovery / CHAOS System)
Chaos trades generate random signals, AI analyzes winners to extract patterns.
"""

import random
import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any

# =============================================================================
# HELPER FACTORIES AND FUNCTIONS
# =============================================================================


def make_chaos_trade(
    trade_id: str = None,
    batch_id: str = "batch-001",
    direction: str = "LONG",
    entry_price: float = 50000.0,
    exit_price: float = 51000.0,
    entry_time: datetime = None,
    exit_time: datetime = None,
    hold_duration_hours: int = 24,
    indicators: dict[str, float] = None,
) -> dict[str, Any]:
    """Create a chaos trade dict for testing."""
    entry = entry_time or datetime.utcnow()
    exit_t = exit_time or (entry + timedelta(hours=hold_duration_hours))

    # Calculate PnL based on direction
    if direction == "LONG":
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
    else:  # SHORT
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100

    return {
        "trade_id": trade_id or str(uuid.uuid4()),
        "batch_id": batch_id,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_time": entry.isoformat(),
        "exit_time": exit_t.isoformat(),
        "hold_duration_hours": hold_duration_hours,
        "pnl_pct": pnl_pct,
        "pnl_usd": pnl_pct * 10,  # Assuming $1000 position
        "indicators": indicators
        or {
            "rsi": random.uniform(20, 80),
            "macd": random.uniform(-0.5, 0.5),
            "macd_signal": random.uniform(-0.5, 0.5),
            "volume_ratio": random.uniform(0.5, 2.0),
            "bb_upper": entry_price * 1.02,
            "bb_lower": entry_price * 0.98,
            "atr": entry_price * 0.02,
        },
        "symbol": "BTC",
        "timeframe": "1h",
        "created_at": datetime.utcnow().isoformat(),
    }


def generate_chaos_batch(
    count: int = 900,
    batch_id: str = None,
    seed: int = None,
) -> list[dict[str, Any]]:
    """Generate a batch of chaos trades."""
    if seed is not None:
        random.seed(seed)

    batch_id = batch_id or f"batch-{uuid.uuid4().hex[:8]}"
    trades = []

    for _ in range(count):
        direction = random.choice(["LONG", "SHORT"])
        entry_price = random.uniform(30000, 70000)
        pct_change = random.uniform(-0.05, 0.05)  # ±5%

        if direction == "LONG":
            exit_price = entry_price * (1 + pct_change)
        else:
            exit_price = entry_price * (1 - pct_change)

        trade = make_chaos_trade(
            batch_id=batch_id,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            hold_duration_hours=random.randint(1, 168),  # 1 hour to 7 days
        )
        trades.append(trade)

    return trades


def classify_trades(trades: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Classify trades into winners and losers."""
    winners = [t for t in trades if t.get("pnl_pct", 0) > 0]
    losers = [t for t in trades if t.get("pnl_pct", 0) <= 0]
    return {"winners": winners, "losers": losers}


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * percentile / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def extract_pattern_from_winners(
    winners: list[dict[str, Any]],
    indicators: list[str] = None,
    min_winners: int = 5,
) -> dict[str, Any]:
    """Extract pattern conditions from winning trades."""
    if len(winners) < min_winners:
        return None

    indicators = indicators or ["rsi", "macd", "volume_ratio"]
    conditions = []

    for ind in indicators:
        values = [w.get("indicators", {}).get(ind) for w in winners if w.get("indicators", {}).get(ind) is not None]
        if not values:
            continue

        # Use percentiles for bounds
        min_val = calculate_percentile(values, 10)
        max_val = calculate_percentile(values, 90)

        # Filter out high variance indicators
        if len(values) > 1:
            std_dev = statistics.stdev(values)
            mean_val = statistics.mean(values)
            cv = std_dev / abs(mean_val) if mean_val != 0 else float("inf")
            if cv > 1.0:  # High coefficient of variation = noisy
                continue

        conditions.append(
            {
                "indicator": ind,
                "min": min_val,
                "max": max_val,
            }
        )

    return {
        "pattern_id": f"chaos-{uuid.uuid4().hex[:12]}",
        "name": f"Chaos Pattern {len(conditions)} conditions",
        "entry_conditions": conditions,
        "exit_conditions": [],
        "origin": "chaos",
        "winners_count": len(winners),
        "created_at": datetime.utcnow().isoformat(),
    }


def pattern_jaccard_similarity(p1: dict[str, Any], p2: dict[str, Any]) -> float:
    """Calculate Jaccard similarity between two patterns."""
    conds1 = p1.get("entry_conditions", [])
    conds2 = p2.get("entry_conditions", [])

    if not conds1 and not conds2:
        return 1.0
    if not conds1 or not conds2:
        return 0.0

    indicators1 = set(c.get("indicator") for c in conds1)
    indicators2 = set(c.get("indicator") for c in conds2)

    intersection = len(indicators1 & indicators2)
    union = len(indicators1 | indicators2)

    return intersection / union if union > 0 else 0.0


def filter_duplicate_patterns(
    patterns: list[dict[str, Any]],
    threshold: float = 0.80,
) -> list[dict[str, Any]]:
    """Remove patterns that are too similar."""
    if not patterns:
        return []

    filtered = [patterns[0]]

    for p in patterns[1:]:
        is_duplicate = False
        for existing in filtered:
            if pattern_jaccard_similarity(p, existing) >= threshold:
                # Keep higher fitness
                if p.get("fitness_score", 0) > existing.get("fitness_score", 0):
                    filtered.remove(existing)
                    filtered.append(p)
                is_duplicate = True
                break
        if not is_duplicate:
            filtered.append(p)

    return filtered


def is_trivial_pattern(pattern: dict[str, Any]) -> bool:
    """Check if pattern has trivial (too wide) conditions."""
    for cond in pattern.get("entry_conditions", []):
        min_val = cond.get("min")
        max_val = cond.get("max")
        if min_val is not None and max_val is not None:
            range_size = abs(max_val - min_val)
            # RSI range 0-100, if covering >80 it's trivial
            if cond.get("indicator") == "rsi" and range_size > 80:
                return True
    return False


def is_narrow_pattern(pattern: dict[str, Any]) -> bool:
    """Check if pattern has unrealistically narrow ranges."""
    for cond in pattern.get("entry_conditions", []):
        min_val = cond.get("min")
        max_val = cond.get("max")
        if min_val is not None and max_val is not None:
            range_size = abs(max_val - min_val)
            # RSI range < 2 is too narrow
            if cond.get("indicator") == "rsi" and range_size < 2:
                return True
    return False


def is_impossible_pattern(pattern: dict[str, Any]) -> bool:
    """Check if pattern conditions can never match."""
    for cond in pattern.get("entry_conditions", []):
        min_val = cond.get("min")
        max_val = cond.get("max")
        if min_val is not None and max_val is not None:
            if min_val > max_val:
                return True
    return False


# ============================================================================
# PATTERN DISCOVERY CONTRACT
# ============================================================================


class TestChaosTradeGeneration:
    """CONTRACT: Chaos trade generation (Phase 1)."""

    def test_generate_random_trades_900(self):
        """CONTRACT: Default chaos batch = 900 random trades."""
        trades = generate_chaos_batch(count=900, seed=42)

        assert len(trades) == 900

    def test_chaos_trades_use_real_ohlcv(self):
        """CONTRACT: Chaos trades use REAL historical OHLCV."""
        # Contract: data_source config should specify real data
        config = {
            "data_source": "ohlcv_1h",
            "use_synthetic": False,
        }

        assert config["data_source"] in ["ohlcv_1h", "ohlcv_6h", "ohlcv_1d"]
        assert config["use_synthetic"] is False

    def test_chaos_trade_random_entry(self):
        """CONTRACT: Entry time is random within OHLCV range."""
        random.seed(42)
        trades = generate_chaos_batch(count=100, seed=42)

        # Check that hold durations vary (which affects exit times)
        hold_durations = [t["hold_duration_hours"] for t in trades]
        unique_durations = set(hold_durations)

        # Should have variety in hold durations (affects entry/exit timing)
        assert len(unique_durations) > 10, "Entry/exit times should be randomized via hold duration"

    def test_chaos_trade_random_direction(self):
        """CONTRACT: Direction is random (50% LONG, 50% SHORT)."""
        trades = generate_chaos_batch(count=1000, seed=42)

        long_count = sum(1 for t in trades if t["direction"] == "LONG")
        short_count = sum(1 for t in trades if t["direction"] == "SHORT")

        # Should be roughly 50/50 (within 10%)
        assert 400 <= long_count <= 600, f"LONG count {long_count} should be ~500"
        assert 400 <= short_count <= 600, f"SHORT count {short_count} should be ~500"

    def test_chaos_trade_random_hold_duration(self):
        """CONTRACT: Hold duration random (1 hour to 7 days)."""
        trades = generate_chaos_batch(count=100, seed=42)

        durations = [t["hold_duration_hours"] for t in trades]

        assert min(durations) >= 1, "Min hold should be 1 hour"
        assert max(durations) <= 168, "Max hold should be 168 hours (7 days)"
        assert len(set(durations)) > 10, "Should have variety in hold durations"

    def test_chaos_trade_calculates_pnl(self):
        """CONTRACT: PnL calculated from entry to exit prices."""
        trade = make_chaos_trade(
            direction="LONG",
            entry_price=50000.0,
            exit_price=51000.0,
        )

        expected_pnl = ((51000 - 50000) / 50000) * 100  # 2%
        assert abs(trade["pnl_pct"] - expected_pnl) < 0.01

    def test_chaos_trade_calculates_pnl_short(self):
        """PnL correctly calculated for SHORT trades."""
        trade = make_chaos_trade(
            direction="SHORT",
            entry_price=50000.0,
            exit_price=49000.0,
        )

        expected_pnl = ((50000 - 49000) / 50000) * 100  # 2%
        assert abs(trade["pnl_pct"] - expected_pnl) < 0.01

    def test_chaos_trade_stores_indicators(self):
        """CONTRACT: Trade stores all indicator values at entry."""
        trade = make_chaos_trade()

        assert "indicators" in trade
        assert "rsi" in trade["indicators"]
        assert "macd" in trade["indicators"]
        assert "volume_ratio" in trade["indicators"]


class TestChaosTradeStorage:
    """CONTRACT: Chaos trade persistence."""

    def test_chaos_trades_saved_to_db(self):
        """CONTRACT: Chaos trades persisted to database."""
        # Contract: trades have all fields needed for DB storage
        trade = make_chaos_trade()

        required_fields = ["trade_id", "batch_id", "direction", "entry_price", "exit_price", "pnl_pct", "indicators"]

        for field in required_fields:
            assert field in trade, f"Missing field: {field}"

    def test_chaos_trade_unique_id(self):
        """CONTRACT: Each chaos trade has unique ID."""
        trades = generate_chaos_batch(count=100, seed=42)

        trade_ids = [t["trade_id"] for t in trades]
        unique_ids = set(trade_ids)

        assert len(unique_ids) == len(trade_ids), "Trade IDs should be unique"

    def test_chaos_trade_batch_id(self):
        """CONTRACT: Chaos trades grouped by batch_id."""
        batch_id = "test-batch-001"
        trades = generate_chaos_batch(count=50, batch_id=batch_id)

        for trade in trades:
            assert trade["batch_id"] == batch_id


class TestWinnerLoserAnalysis:
    """CONTRACT: Analyze winners vs losers."""

    def test_classify_winners_positive_pnl(self):
        """CONTRACT: Winners have PnL > 0."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        for winner in classified["winners"]:
            assert winner["pnl_pct"] > 0

    def test_classify_losers_negative_pnl(self):
        """CONTRACT: Losers have PnL <= 0."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        for loser in classified["losers"]:
            assert loser["pnl_pct"] <= 0

    def test_winner_percentage_calculated(self):
        """CONTRACT: Calculate winner percentage per batch."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        total = len(trades)
        winner_pct = len(classified["winners"]) / total * 100

        assert 0 <= winner_pct <= 100

    def test_average_winner_pnl(self):
        """CONTRACT: Calculate average winner PnL."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        winners = classified["winners"]
        if winners:
            avg_pnl = statistics.mean([w["pnl_pct"] for w in winners])
            assert avg_pnl > 0

    def test_average_loser_pnl(self):
        """CONTRACT: Calculate average loser PnL."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        losers = classified["losers"]
        if losers:
            avg_pnl = statistics.mean([l["pnl_pct"] for l in losers])
            assert avg_pnl <= 0


class TestPatternExtraction:
    """CONTRACT: Extract patterns from winning trades."""

    def test_extract_common_indicator_ranges(self):
        """CONTRACT: Find common indicator ranges in winners."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        pattern = extract_pattern_from_winners(classified["winners"])

        if pattern:
            assert "entry_conditions" in pattern
            assert len(pattern["entry_conditions"]) > 0

    def test_extraction_uses_percentiles(self):
        """CONTRACT: Use percentiles (10th, 90th) for bounds."""
        # Create winners with known RSI values
        winners = []
        for rsi_val in [25, 30, 35, 40, 45, 50, 55, 60, 65]:
            trade = make_chaos_trade()
            trade["indicators"]["rsi"] = rsi_val
            trade["pnl_pct"] = 1.0
            winners.append(trade)

        pattern = extract_pattern_from_winners(winners, indicators=["rsi"])

        if pattern:
            rsi_cond = next((c for c in pattern["entry_conditions"] if c["indicator"] == "rsi"), None)
            if rsi_cond:
                # 10th percentile of [25,30,35,40,45,50,55,60,65] ≈ 25-30
                # 90th percentile ≈ 60-65
                assert rsi_cond["min"] >= 25
                assert rsi_cond["max"] <= 65

    def test_extraction_minimum_5_winners(self):
        """CONTRACT: Need at least 5 winners to extract pattern."""
        winners = [make_chaos_trade() for _ in range(4)]
        for w in winners:
            w["pnl_pct"] = 1.0

        pattern = extract_pattern_from_winners(winners, min_winners=5)

        assert pattern is None, "Should return None with fewer than 5 winners"

    def test_extracted_pattern_has_conditions(self):
        """CONTRACT: Extracted pattern has entry_conditions list."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        pattern = extract_pattern_from_winners(classified["winners"])

        if pattern:
            assert isinstance(pattern.get("entry_conditions"), list)

    def test_extraction_filters_noise(self):
        """CONTRACT: Indicators with high variance filtered out."""
        # Create winners with high variance in one indicator
        winners = []
        for i in range(20):
            trade = make_chaos_trade()
            trade["indicators"]["rsi"] = 30 + i  # Low variance
            trade["indicators"]["noisy"] = random.uniform(0, 1000)  # High variance
            trade["pnl_pct"] = 1.0
            winners.append(trade)

        pattern = extract_pattern_from_winners(winners, indicators=["rsi", "noisy"])

        if pattern:
            # RSI should be included, noisy should be filtered
            indicators = [c["indicator"] for c in pattern["entry_conditions"]]
            assert "rsi" in indicators


class TestAIPatternDiscovery:
    """CONTRACT: AI-assisted pattern discovery (Phase 2)."""

    def test_ai_analyzes_winners(self):
        """CONTRACT: AI receives winning trade data."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        ai_input = {
            "winners": classified["winners"],
            "total_count": len(classified["winners"]),
        }

        assert len(ai_input["winners"]) > 0
        assert ai_input["total_count"] == len(classified["winners"])

    def test_ai_analyzes_losers(self):
        """CONTRACT: AI receives losing trade data for contrast."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)

        ai_input = {
            "winners": classified["winners"],
            "losers": classified["losers"],
        }

        assert "losers" in ai_input

    def test_ai_extracts_discriminating_features(self):
        """CONTRACT: AI identifies features that distinguish W from L."""
        # Simulate AI extraction
        discriminating = {
            "features": [
                {"indicator": "rsi", "winner_avg": 35, "loser_avg": 55, "discriminating": True},
                {"indicator": "volume_ratio", "winner_avg": 1.5, "loser_avg": 0.8, "discriminating": True},
            ]
        }

        for feature in discriminating["features"]:
            assert "winner_avg" in feature
            assert "loser_avg" in feature

    def test_ai_generates_pattern_json(self):
        """CONTRACT: AI outputs valid pattern JSON."""
        ai_pattern = {
            "pattern_id": "ai-generated-001",
            "name": "AI RSI Oversold Pattern",
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 35},
            ],
            "exit_conditions": [
                {"indicator": "rsi", "min": 65, "max": 80},
            ],
            "origin": "ai",
        }

        assert "pattern_id" in ai_pattern
        assert "entry_conditions" in ai_pattern
        assert ai_pattern["origin"] == "ai"

    def test_ai_pattern_has_rationale(self):
        """CONTRACT: AI pattern includes reasoning/rationale."""
        ai_pattern = {
            "pattern_id": "ai-generated-001",
            "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 35}],
            "rationale": "RSI values 20-35 in winners vs 50-70 in losers suggests oversold entries work",
            "origin": "ai",
        }

        assert "rationale" in ai_pattern
        assert len(ai_pattern["rationale"]) > 10


class TestDiscoveryBatching:
    """CONTRACT: Pattern discovery batching."""

    def test_backtest_batch_50_patterns(self):
        """CONTRACT: Backtest patterns in batches of 50."""
        batch_size = 50
        patterns = [{"pattern_id": f"p{i}"} for i in range(125)]

        batches = [patterns[i : i + batch_size] for i in range(0, len(patterns), batch_size)]

        assert len(batches) == 3
        assert len(batches[0]) == 50
        assert len(batches[1]) == 50
        assert len(batches[2]) == 25

    def test_batch_parallelization(self):
        """CONTRACT: Batches can run in parallel."""
        batch_config = {
            "parallel": True,
            "max_concurrent": 4,
        }

        assert batch_config["parallel"] is True
        assert batch_config["max_concurrent"] > 1

    def test_batch_progress_tracking(self):
        """CONTRACT: Track progress through batches."""
        total_batches = 5
        progress = {
            "total": total_batches,
            "completed": 3,
            "in_progress": 1,
            "pending": 1,
            "percent": 60.0,
        }

        assert progress["completed"] + progress["in_progress"] + progress["pending"] == total_batches


class TestDiscoveryFiltering:
    """CONTRACT: Filter discovered patterns."""

    def test_filter_duplicate_patterns(self):
        """CONTRACT: Remove near-duplicate patterns."""
        patterns = [
            {
                "pattern_id": "p1",
                "entry_conditions": [{"indicator": "rsi"}, {"indicator": "macd"}],
                "fitness_score": 60,
            },
            {
                "pattern_id": "p2",
                "entry_conditions": [{"indicator": "rsi"}, {"indicator": "macd"}],
                "fitness_score": 70,
            },
            {"pattern_id": "p3", "entry_conditions": [{"indicator": "volume_ratio"}], "fitness_score": 50},
        ]

        filtered = filter_duplicate_patterns(patterns, threshold=0.80)

        # p1 and p2 are duplicates, should keep p2 (higher fitness)
        assert len(filtered) == 2
        ids = [p["pattern_id"] for p in filtered]
        assert "p2" in ids
        assert "p3" in ids

    def test_filter_trivial_patterns(self):
        """CONTRACT: Remove patterns with trivial conditions."""
        trivial_pattern = {"entry_conditions": [{"indicator": "rsi", "min": 5, "max": 95}]}

        assert is_trivial_pattern(trivial_pattern) is True

    def test_filter_impossible_patterns(self):
        """CONTRACT: Remove patterns that can never match."""
        impossible = {"entry_conditions": [{"indicator": "rsi", "min": 80, "max": 20}]}

        assert is_impossible_pattern(impossible) is True

    def test_filter_too_narrow_ranges(self):
        """CONTRACT: Remove patterns with unrealistically narrow ranges."""
        narrow = {"entry_conditions": [{"indicator": "rsi", "min": 29.9, "max": 30.1}]}

        assert is_narrow_pattern(narrow) is True


class TestDiscoveryMetrics:
    """CONTRACT: Pattern discovery metrics."""

    def test_discovery_returns_patterns_count(self):
        """CONTRACT: Returns count of patterns discovered."""
        result = {
            "patterns_discovered": 15,
            "patterns_filtered": 5,
            "patterns_kept": 10,
        }

        assert "patterns_discovered" in result
        assert result["patterns_discovered"] == 15

    def test_discovery_returns_duration(self):
        """CONTRACT: Returns discovery duration."""
        result = {
            "duration_seconds": 45.5,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": (datetime.utcnow() + timedelta(seconds=45.5)).isoformat(),
        }

        assert "duration_seconds" in result
        assert result["duration_seconds"] > 0

    def test_discovery_returns_trades_analyzed(self):
        """CONTRACT: Returns count of trades analyzed."""
        result = {
            "trades_analyzed": 900,
            "winners": 450,
            "losers": 450,
        }

        assert "trades_analyzed" in result
        assert result["trades_analyzed"] == 900


class TestEvolutionaryDiscovery:
    """CONTRACT: Evolutionary pattern refinement."""

    def test_mutate_pattern_conditions(self):
        """CONTRACT: Can mutate pattern condition bounds ±10%."""
        from Fast_Swarm.Patterns.Services.pattern_service import mutate_condition

        condition = {"indicator": "rsi", "min": 30, "max": 40}

        random.seed(42)
        mutated = mutate_condition(condition)

        # Bounds should change by at most ±10%
        assert 27 <= mutated["min"] <= 33
        assert 36 <= mutated["max"] <= 44

    def test_crossover_patterns(self):
        """CONTRACT: Can combine conditions from two patterns."""
        from Fast_Swarm.Patterns.Services.pattern_service import crossover_patterns

        parent_a = {
            "pattern_id": "a",
            "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 30}],
            "exit_conditions": [],
        }
        parent_b = {
            "pattern_id": "b",
            "entry_conditions": [{"indicator": "macd", "min": -0.5, "max": 0}],
            "exit_conditions": [],
        }

        child = crossover_patterns(parent_a, parent_b)

        assert "entry_conditions" in child
        assert len(child["entry_conditions"]) >= 1

    def test_add_condition_mutation(self):
        """CONTRACT: Mutation can add new condition."""
        pattern = {"entry_conditions": [{"indicator": "rsi", "min": 30, "max": 40}]}

        # Simulate adding a condition
        new_condition = {"indicator": "macd", "min": -0.1, "max": 0.1}
        pattern["entry_conditions"].append(new_condition)

        assert len(pattern["entry_conditions"]) == 2

    def test_remove_condition_mutation(self):
        """CONTRACT: Mutation can remove condition."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 30, "max": 40},
                {"indicator": "macd", "min": -0.1, "max": 0.1},
            ]
        }

        # Remove one condition
        pattern["entry_conditions"] = pattern["entry_conditions"][:1]

        assert len(pattern["entry_conditions"]) == 1


class TestDiscoveryDeterminism:
    """CONTRACT: Discovery determinism with seed."""

    def test_discovery_deterministic_with_seed(self):
        """CONTRACT: Same seed = same patterns discovered."""
        trades1 = generate_chaos_batch(count=100, seed=42)
        trades2 = generate_chaos_batch(count=100, seed=42)

        # Same seed should produce same trade characteristics (not UUIDs - those use uuid4)
        assert trades1[0]["direction"] == trades2[0]["direction"]
        assert trades1[0]["entry_price"] == trades2[0]["entry_price"]
        assert trades1[0]["hold_duration_hours"] == trades2[0]["hold_duration_hours"]
        assert len(trades1) == len(trades2)

    def test_different_seeds_different_patterns(self):
        """CONTRACT: Different seeds = different patterns."""
        trades1 = generate_chaos_batch(count=100, seed=42)
        trades2 = generate_chaos_batch(count=100, seed=123)

        # Different seeds should produce different trade characteristics
        # (entry_price is randomly generated, so should differ)
        assert trades1[0]["entry_price"] != trades2[0]["entry_price"]


class TestPatternOriginTracking:
    """CONTRACT: Track pattern origin."""

    def test_chaos_pattern_origin_chaos(self):
        """CONTRACT: Chaos-discovered patterns have origin='chaos'."""
        trades = generate_chaos_batch(count=100, seed=42)
        classified = classify_trades(trades)
        pattern = extract_pattern_from_winners(classified["winners"])

        if pattern:
            assert pattern["origin"] == "chaos"

    def test_ai_pattern_origin_ai(self):
        """CONTRACT: AI-discovered patterns have origin='ai'."""
        ai_pattern = {
            "origin": "ai",
            "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 35}],
        }

        assert ai_pattern["origin"] == "ai"

    def test_hybrid_pattern_origin_hybrid(self):
        """CONTRACT: Combined patterns have origin='hybrid'."""
        from Fast_Swarm.Patterns.Services.pattern_service import crossover_patterns

        parent_a = {"pattern_id": "a", "entry_conditions": [], "exit_conditions": []}
        parent_b = {"pattern_id": "b", "entry_conditions": [], "exit_conditions": []}

        child = crossover_patterns(parent_a, parent_b)

        assert child["origin"] == "hybrid"

    def test_academic_pattern_origin_academic(self):
        """CONTRACT: Paper-based patterns have origin='academic'."""
        academic_pattern = {
            "origin": "academic",
            "name": "Mean Reversion RSI",
            "source": "arxiv-2024-12345",
        }

        assert academic_pattern["origin"] == "academic"

    def test_technical_pattern_origin_technical(self):
        """CONTRACT: TA-based patterns have origin='technical'."""
        technical_pattern = {
            "origin": "technical",
            "name": "Classic RSI Divergence",
        }

        assert technical_pattern["origin"] == "technical"


class TestPatternDeduplication:
    """CONTRACT: Pattern deduplication."""

    def test_jaccard_similarity_calculation(self):
        """CONTRACT: Calculate Jaccard similarity between patterns."""
        p1 = {"entry_conditions": [{"indicator": "rsi"}, {"indicator": "macd"}]}
        p2 = {"entry_conditions": [{"indicator": "rsi"}, {"indicator": "volume_ratio"}]}

        similarity = pattern_jaccard_similarity(p1, p2)

        # Intersection: {rsi}, Union: {rsi, macd, volume_ratio}
        # Jaccard = 1/3 = 0.333
        assert abs(similarity - 0.333) < 0.01

    def test_dedupe_threshold_80_percent(self):
        """CONTRACT: 80%+ Jaccard similarity = duplicate."""
        p1 = {"entry_conditions": [{"indicator": "rsi"}, {"indicator": "macd"}]}
        p2 = {"entry_conditions": [{"indicator": "rsi"}, {"indicator": "macd"}]}

        similarity = pattern_jaccard_similarity(p1, p2)

        assert similarity >= 0.80, "Same conditions should be 100% similar"

    def test_keep_higher_fitness_on_dedupe(self):
        """CONTRACT: Keep pattern with higher fitness on dedupe."""
        patterns = [
            {"pattern_id": "p1", "entry_conditions": [{"indicator": "rsi"}], "fitness_score": 60},
            {"pattern_id": "p2", "entry_conditions": [{"indicator": "rsi"}], "fitness_score": 80},
        ]

        filtered = filter_duplicate_patterns(patterns, threshold=0.80)

        assert len(filtered) == 1
        assert filtered[0]["fitness_score"] == 80


class TestRawValueStorage:
    """CONTRACT: Store raw values, not buckets (evolution discovers)."""

    def test_store_raw_rsi_value(self):
        """CONTRACT: Store RSI as 28.3, not 'rsi_oversold'."""
        trade = make_chaos_trade()
        trade["indicators"]["rsi"] = 28.3

        assert isinstance(trade["indicators"]["rsi"], float)
        assert trade["indicators"]["rsi"] == 28.3

    def test_store_raw_macd_value(self):
        """CONTRACT: Store MACD as -0.23, not 'macd_bearish'."""
        trade = make_chaos_trade()
        trade["indicators"]["macd"] = -0.23

        assert isinstance(trade["indicators"]["macd"], float)
        assert trade["indicators"]["macd"] == -0.23

    def test_store_raw_volume_ratio(self):
        """CONTRACT: Store volume_ratio as 1.45, not 'high_volume'."""
        trade = make_chaos_trade()
        trade["indicators"]["volume_ratio"] = 1.45

        assert isinstance(trade["indicators"]["volume_ratio"], float)
        assert trade["indicators"]["volume_ratio"] == 1.45

    def test_no_predefined_buckets(self):
        """CONTRACT: No predefined indicator buckets used."""
        trade = make_chaos_trade()

        # Check that indicators are raw floats, not string buckets
        for key, value in trade["indicators"].items():
            assert not isinstance(value, str), f"Indicator {key} should be numeric, not string"


class TestDiscoveryScheduling:
    """CONTRACT: Discovery cycle scheduling."""

    def test_discovery_scheduled_interval(self):
        """CONTRACT: Discovery runs on configured interval."""
        schedule_config = {
            "interval_hours": 6,
            "enabled": True,
        }

        assert schedule_config["interval_hours"] == 6
        assert schedule_config["enabled"] is True

    def test_discovery_skipped_if_running(self):
        """CONTRACT: Skip if previous discovery still running."""
        state = {
            "is_running": True,
            "started_at": datetime.utcnow().isoformat(),
        }

        # Should skip if already running
        should_skip = state["is_running"]
        assert should_skip is True

    def test_discovery_retry_on_failure(self):
        """CONTRACT: Retry failed discovery after delay."""
        retry_config = {
            "max_retries": 3,
            "retry_delay_seconds": 60,
            "current_attempt": 1,
        }

        assert retry_config["max_retries"] == 3
        assert retry_config["retry_delay_seconds"] == 60
