"""
Pattern Service for Fast_Swarm.

Provides CRUD operations, tier management, and evolution functions for patterns.
"""

import random
import uuid
from datetime import datetime
from typing import Any

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..Models.pattern_models import Pattern

# =============================================================================
# Constants
# =============================================================================

VALID_ORIGINS = ["chaos", "academic", "technical", "ai", "hybrid"]
VALID_TIERS = [1, 2, 3]

# =============================================================================
# QUINTILE-BASED TIER SYSTEM (NOT Fixed Ranges)
# =============================================================================
# Tiers are determined by population percentile, not fixed fitness scores.
#
# | Quintile   | Tier | Status   | Spawn Eligible |
# |------------|------|----------|----------------|
# | Top 20%    | 1    | ELITE    | ✅ Yes         |
# | 20-40%     | 2    | PROVEN   | ✅ Yes         |
# | 40-60%     | 3    | UNTESTED | ❌ No          |
# | 60-80%     | 4    | WEAK     | ❌ No          |
# | Bottom 20% | 5    | CULL     | ❌ No (culled) |

# Spawn eligibility requirements
MIN_BACKTEST_WINDOWS = 100  # At least 100 backtest windows
MIN_ASSETS_TESTED = 3  # Tested on at least 3 different assets
REQUIRED_TIMEFRAMES = {"1m", "15m", "1h", "1d"}  # All 4 required

# Legacy thresholds (kept for backward compatibility, but NOT used for tier assignment)
FITNESS_TIER_1_THRESHOLD = 80  # Elite (DEPRECATED - use quintiles)
FITNESS_TIER_2_THRESHOLD = 60  # Proven (DEPRECATED - use quintiles)
FITNESS_TIER_3_MIN = 40  # Survive (DEPRECATED - use quintiles)
FITNESS_CULL_THRESHOLD = 40  # Below this = cull (DEPRECATED - use quintiles)

# Demotion thresholds (DEPRECATED - use quintiles instead)
DEMOTION_TIER_1_THRESHOLD = 70  # Below this, demote from tier 1
DEMOTION_TIER_2_THRESHOLD = 50  # Below this, demote from tier 2

# Evolution constants
MIN_TRADES_FOR_PROMOTION = 20
MUTATION_RATE = 0.10  # ±10%
TOP_PERCENT_CLONE = 0.20  # Top 20% get cloned
BOTTOM_PERCENT_CULL = 0.30  # Bottom 30% get culled


# =============================================================================
# Validation
# =============================================================================


def validate_origin(origin: str) -> tuple[bool, str]:
    """Validate pattern origin."""
    if origin not in VALID_ORIGINS:
        return False, f"Invalid origin '{origin}'. Must be one of: {VALID_ORIGINS}"
    return True, ""


def validate_tier(tier: int) -> tuple[bool, str]:
    """Validate pattern tier."""
    if tier not in VALID_TIERS:
        return False, f"Invalid tier {tier}. Must be one of: {VALID_TIERS}"
    return True, ""


def validate_conditions(conditions: list[dict]) -> tuple[bool, str]:
    """
    Validate condition structure.

    Each condition must have 'indicator' and optionally 'min'/'max'.
    """
    if not isinstance(conditions, list):
        return False, "Conditions must be a list"

    from .pattern_matching_service import INDICATORS

    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            return False, f"Condition {i} must be a dict"

        indicator = cond.get("indicator")
        if not indicator:
            return False, f"Condition {i} missing 'indicator'"

        if indicator not in INDICATORS:
            return False, f"Condition {i} has unknown indicator: {indicator}"

        min_val = cond.get("min")
        max_val = cond.get("max")

        if min_val is not None and max_val is not None:
            if min_val > max_val:
                return False, f"Condition {i}: min ({min_val}) > max ({max_val})"

    return True, ""


# =============================================================================
# CRUD Operations
# =============================================================================


async def create_pattern(
    session: AsyncSession,
    name: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]] | None = None,
    origin: str = "unknown",
    description: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    direction: str = "LONG",
) -> Pattern:
    """
    Create a new pattern.

    Args:
        session: Database session
        name: Pattern name
        entry_conditions: Entry condition list
        exit_conditions: Exit condition list
        origin: Pattern origin (chaos/academic/technical/ai/hybrid)
        description: Pattern description
        symbol: Trading symbol (e.g., BTC)
        timeframe: Timeframe (e.g., 1h)
        direction: Trade direction (LONG/SHORT)

    Returns:
        Created Pattern instance
    """
    # Validate origin
    if origin not in VALID_ORIGINS and origin != "unknown":
        raise ValueError(f"Invalid origin: {origin}")

    # Validate conditions
    is_valid, error = validate_conditions(entry_conditions)
    if not is_valid:
        raise ValueError(f"Invalid entry conditions: {error}")

    if exit_conditions:
        is_valid, error = validate_conditions(exit_conditions)
        if not is_valid:
            raise ValueError(f"Invalid exit conditions: {error}")

    pattern = Pattern(
        pattern_id=str(uuid.uuid4()),
        name=name,
        description=description,
        origin=origin,
        status="untested",
        is_active=True,
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions or [],
        symbol=symbol,
        timeframe=timeframe,
        fitness_score=50.0,  # Default neutral fitness
        total_trades=0,
        total_runs=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Store direction in entry_conditions metadata
    if entry_conditions:
        pattern.entry_conditions = [
            {**cond, "direction": direction} if i == 0 else cond for i, cond in enumerate(entry_conditions)
        ]

    session.add(pattern)
    await session.flush()

    return pattern


async def get_pattern_by_id(
    session: AsyncSession,
    pattern_id: str,
    include_archived: bool = False,
) -> Pattern | None:
    """Get a pattern by ID."""
    statement = select(Pattern).where(Pattern.pattern_id == pattern_id)
    if not include_archived:
        statement = statement.where(Pattern.status != "archived")

    result = await session.execute(statement)
    return result.scalars().first()


async def get_all_patterns(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    include_archived: bool = False,
) -> list[Pattern]:
    """Get all patterns with pagination."""
    statement = select(Pattern).order_by(desc(Pattern.fitness_score).nulls_last())

    if not include_archived:
        statement = statement.where(Pattern.status != "archived")

    statement = statement.offset(offset).limit(limit)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_patterns_by_tier(
    session: AsyncSession,
    tier: int,
    limit: int = 100,
) -> list[Pattern]:
    """Get patterns filtered by tier."""
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}")

    # Map tier to fitness ranges
    if tier == 1:
        statement = select(Pattern).where(
            Pattern.fitness_score >= FITNESS_TIER_1_THRESHOLD, Pattern.status != "archived"
        )
    elif tier == 2:
        statement = select(Pattern).where(
            Pattern.fitness_score >= FITNESS_TIER_2_THRESHOLD,
            Pattern.fitness_score < FITNESS_TIER_1_THRESHOLD,
            Pattern.status != "archived",
        )
    else:  # tier 3
        # Tier 3 includes patterns with fitness < 60 OR fitness is None (untested)
        from sqlalchemy import or_

        statement = select(Pattern).where(
            or_(Pattern.fitness_score < FITNESS_TIER_2_THRESHOLD, Pattern.fitness_score.is_(None)),
            Pattern.status != "archived",
        )

    # NULLS LAST ensures patterns with actual fitness scores come first
    statement = statement.order_by(desc(Pattern.fitness_score).nulls_last()).limit(limit)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_patterns_by_origin(
    session: AsyncSession,
    origin: str,
    limit: int = 100,
) -> list[Pattern]:
    """Get patterns filtered by origin."""
    if origin not in VALID_ORIGINS:
        raise ValueError(f"Invalid origin: {origin}")

    statement = (
        select(Pattern)
        .where(Pattern.origin == origin, Pattern.status != "archived")
        .order_by(desc(Pattern.fitness_score).nulls_last())
        .limit(limit)
    )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_patterns_by_asset(
    session: AsyncSession,
    asset: str,
    limit: int = 100,
) -> list[Pattern]:
    """Get patterns filtered by asset/symbol."""
    statement = (
        select(Pattern)
        .where(Pattern.symbol == asset, Pattern.status != "archived")
        .order_by(desc(Pattern.fitness_score).nulls_last())
        .limit(limit)
    )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def update_pattern(
    session: AsyncSession,
    pattern_id: str,
    **updates,
) -> Pattern | None:
    """
    Update pattern fields.

    Args:
        session: Database session
        pattern_id: Pattern to update
        **updates: Fields to update

    Returns:
        Updated pattern or None if not found
    """
    pattern = await get_pattern_by_id(session, pattern_id)
    if not pattern:
        raise ValueError(f"Pattern not found: {pattern_id}")

    # Validate specific fields
    if "origin" in updates:
        is_valid, error = validate_origin(updates["origin"])
        if not is_valid:
            raise ValueError(error)

    if "entry_conditions" in updates:
        is_valid, error = validate_conditions(updates["entry_conditions"])
        if not is_valid:
            raise ValueError(error)

    if "exit_conditions" in updates:
        is_valid, error = validate_conditions(updates["exit_conditions"])
        if not is_valid:
            raise ValueError(error)

    # Bound fitness score
    if "fitness_score" in updates:
        updates["fitness_score"] = max(0.0, min(100.0, updates["fitness_score"]))

    # Apply updates
    for key, value in updates.items():
        if hasattr(pattern, key):
            setattr(pattern, key, value)

    pattern.updated_at = datetime.utcnow()
    await session.flush()

    return pattern


async def soft_delete_pattern(
    session: AsyncSession,
    pattern_id: str,
) -> bool:
    """
    Soft delete a pattern (set status to 'archived').

    Returns:
        True if deleted, raises ValueError if not found
    """
    pattern = await get_pattern_by_id(session, pattern_id, include_archived=True)
    if not pattern:
        raise ValueError(f"Pattern not found: {pattern_id}")

    pattern.status = "archived"
    pattern.is_active = False
    pattern.assigned_agent_id = None  # Unassign from agent
    pattern.updated_at = datetime.utcnow()

    await session.flush()
    return True


async def batch_create_patterns(
    session: AsyncSession,
    patterns_data: list[dict[str, Any]],
) -> list[str]:
    """
    Create multiple patterns in a batch.

    Args:
        session: Database session
        patterns_data: List of pattern data dicts

    Returns:
        List of created pattern_ids
    """
    pattern_ids = []

    for data in patterns_data:
        pattern = await create_pattern(
            session=session,
            name=data.get("name", f"Pattern_{uuid.uuid4().hex[:8]}"),
            entry_conditions=data.get("entry_conditions", []),
            exit_conditions=data.get("exit_conditions"),
            origin=data.get("origin", "unknown"),
            description=data.get("description"),
            symbol=data.get("symbol"),
            timeframe=data.get("timeframe"),
        )
        pattern_ids.append(pattern.pattern_id)

    return pattern_ids


# =============================================================================
# Tier Management
# =============================================================================


def get_tier_from_fitness(fitness: float) -> int:
    """
    Get tier based on fitness score (LEGACY - uses fixed thresholds).

    DEPRECATED: Use get_tiers_by_quintile() for the correct quintile-based system.

    This function is kept for backward compatibility but should not be used
    for spawn eligibility or cull decisions.
    """
    if fitness >= FITNESS_TIER_1_THRESHOLD:
        return 1
    elif fitness >= FITNESS_TIER_2_THRESHOLD:
        return 2
    return 3


def get_tiers_by_quintile(patterns: list[dict[str, Any]]) -> dict[str, int]:
    """
    Calculate quintile-based tiers for a list of patterns.

    CORRECT IMPLEMENTATION: Tiers are based on population percentile, not fixed ranges.

    | Quintile   | Tier | Status   |
    |------------|------|----------|
    | Top 20%    | 1    | ELITE    |
    | 20-40%     | 2    | PROVEN   |
    | 40-60%     | 3    | UNTESTED |
    | 60-80%     | 4    | WEAK     |
    | Bottom 20% | 5    | CULL     |

    Args:
        patterns: List of pattern dicts with 'pattern_id' and 'fitness_score'.

    Returns:
        Dict mapping pattern_id to tier (1-5).
    """
    if not patterns:
        return {}

    # Sort by fitness descending
    sorted_patterns = sorted(patterns, key=lambda p: p.get("fitness_score", 0) or 0, reverse=True)

    total = len(sorted_patterns)
    result = {}

    for i, pattern in enumerate(sorted_patterns):
        # Calculate percentile (0 = top, 1 = bottom)
        percentile = i / total if total > 0 else 0

        # Assign tier based on quintile
        if percentile < 0.20:
            tier = 1  # Top 20% = ELITE
        elif percentile < 0.40:
            tier = 2  # 20-40% = PROVEN
        elif percentile < 0.60:
            tier = 3  # 40-60% = UNTESTED
        elif percentile < 0.80:
            tier = 4  # 60-80% = WEAK
        else:
            tier = 5  # Bottom 20% = CULL

        pattern_id = pattern.get("pattern_id", "")
        if pattern_id:
            result[pattern_id] = tier

    return result


def is_spawn_eligible(
    pattern_or_tier: Any = None,
    tier: int | None = None,
) -> bool:
    """
    Check if a pattern is eligible for spawn (can be shown to agents).

    Requirements:
    1. Tier 1 or 2 (top 40% of population by fitness)
    2. 100+ backtest windows
    3. Tested on 3+ assets
    4. Tested on all 4 required timeframes (1m, 15m, 1h, 1d)

    Args:
        pattern_or_tier: Pattern dict or tier number.
        tier: Explicit tier value (if pattern_or_tier is not a dict).

    Returns:
        True if pattern can be assigned to agents.
    """
    # Handle simple tier check
    if isinstance(pattern_or_tier, int):
        return pattern_or_tier in [1, 2]
    if tier is not None and pattern_or_tier is None:
        return tier in [1, 2]

    # Handle pattern dict
    if isinstance(pattern_or_tier, dict):
        pattern = pattern_or_tier

        # Get tier (required to be 1 or 2)
        pattern_tier = pattern.get("tier", 3)
        if pattern_tier not in [1, 2]:
            return False

        # Check backtest count
        backtest_count = pattern.get("backtest_count", 0) or pattern.get("total_runs", 0) or 0
        if backtest_count < MIN_BACKTEST_WINDOWS:
            return False

        # Check assets tested
        assets_tested = pattern.get("assets_tested", [])
        if isinstance(assets_tested, list) and len(assets_tested) < MIN_ASSETS_TESTED:
            return False

        # Check timeframes tested
        timeframes_tested = set(pattern.get("timeframes_tested", []))
        if not REQUIRED_TIMEFRAMES.issubset(timeframes_tested):
            return False

        return True

    # Fallback for simple tier check
    if tier is not None:
        return tier in [1, 2]

    return False


def is_cull_eligible(pattern: dict[str, Any]) -> bool:
    """
    Check if a pattern is eligible for culling.

    Patterns can only be culled AFTER meeting the same testing requirements as spawn.
    This prevents culling undertested patterns that might actually be good.

    Requirements (same as spawn):
    1. 100+ backtest windows
    2. Tested on 3+ assets
    3. Tested on all 4 required timeframes

    Note: Tier 5 patterns that don't meet these requirements are in "evaluation limbo"
    and will continue to be tested rather than culled prematurely.

    Args:
        pattern: Pattern dict with backtest stats.

    Returns:
        True if pattern can be culled (meets testing requirements AND tier 5).
    """
    # Must be tier 5 (bottom quintile)
    pattern_tier = pattern.get("tier", 3)
    if pattern_tier != 5:
        return False

    # Check backtest count
    backtest_count = pattern.get("backtest_count", 0) or pattern.get("total_runs", 0) or 0
    if backtest_count < MIN_BACKTEST_WINDOWS:
        return False

    # Check assets tested
    assets_tested = pattern.get("assets_tested", [])
    if isinstance(assets_tested, list) and len(assets_tested) < MIN_ASSETS_TESTED:
        return False

    # Check timeframes tested
    timeframes_tested = set(pattern.get("timeframes_tested", []))
    if not REQUIRED_TIMEFRAMES.issubset(timeframes_tested):
        return False

    return True


def should_promote(fitness: float, current_tier: int, trade_count: int) -> bool:
    """Check if pattern should be promoted."""
    if trade_count < MIN_TRADES_FOR_PROMOTION:
        return False

    if current_tier == 3 and fitness >= FITNESS_TIER_2_THRESHOLD:
        return True
    if current_tier == 2 and fitness >= FITNESS_TIER_1_THRESHOLD:
        return True
    return False


def should_demote(fitness: float, current_tier: int) -> bool:
    """Check if pattern should be demoted."""
    if current_tier == 1 and fitness < DEMOTION_TIER_1_THRESHOLD:
        return True
    if current_tier == 2 and fitness < DEMOTION_TIER_2_THRESHOLD:
        return True
    return False


def should_cull(fitness: float, tier: int) -> bool:
    """Check if pattern should be culled."""
    return tier == 3 and fitness < FITNESS_CULL_THRESHOLD


async def promote_pattern(
    session: AsyncSession,
    pattern_id: str,
) -> Pattern | None:
    """Promote pattern to higher tier."""
    pattern = await get_pattern_by_id(session, pattern_id)
    if not pattern:
        return None

    current_tier = get_tier_from_fitness(pattern.fitness_score or 50)
    new_tier = get_tier_from_fitness(pattern.fitness_score or 50)

    if new_tier < current_tier:
        pattern.status = f"tier_{new_tier}"
        pattern.updated_at = datetime.utcnow()
        await session.flush()

    return pattern


async def demote_pattern(
    session: AsyncSession,
    pattern_id: str,
) -> Pattern | None:
    """Demote pattern to lower tier."""
    pattern = await get_pattern_by_id(session, pattern_id)
    if not pattern:
        return None

    current_tier = get_tier_from_fitness(pattern.fitness_score or 50)
    new_tier = min(3, current_tier + 1)

    pattern.status = f"tier_{new_tier}"
    pattern.updated_at = datetime.utcnow()
    await session.flush()

    return pattern


async def cull_pattern(
    session: AsyncSession,
    pattern_id: str,
) -> bool:
    """Cull (archive) a pattern."""
    return await soft_delete_pattern(session, pattern_id)


# =============================================================================
# Evolution Operations
# =============================================================================


def mutate_condition(
    condition: dict[str, Any],
    mutation_rate: float = MUTATION_RATE,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Mutate a single condition's bounds by ±mutation_rate.

    Args:
        condition: Condition dict
        mutation_rate: Max change rate (default 0.10 = ±10%)
        seed: Random seed for determinism

    Returns:
        Mutated condition
    """
    if seed is not None:
        random.seed(seed)

    mutated = condition.copy()

    if "min" in mutated and mutated["min"] is not None:
        change = random.uniform(-mutation_rate, mutation_rate)
        mutated["min"] = mutated["min"] * (1 + change)

    if "max" in mutated and mutated["max"] is not None:
        change = random.uniform(-mutation_rate, mutation_rate)
        mutated["max"] = mutated["max"] * (1 + change)

    # Ensure min <= max
    if mutated.get("min") is not None and mutated.get("max") is not None:
        if mutated["min"] > mutated["max"]:
            mutated["min"], mutated["max"] = mutated["max"], mutated["min"]

    return mutated


def mutate_conditions(
    conditions: list[dict[str, Any]],
    mutation_rate: float = MUTATION_RATE,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Mutate all conditions."""
    if seed is not None:
        random.seed(seed)

    return [mutate_condition(c, mutation_rate) for c in conditions]


async def mutate_pattern(
    session: AsyncSession,
    pattern_id: str,
    mutation_rate: float = MUTATION_RATE,
    seed: int | None = None,
) -> Pattern:
    """
    Create a mutated copy of a pattern.

    Args:
        session: Database session
        pattern_id: Pattern to mutate
        mutation_rate: Mutation rate
        seed: Random seed

    Returns:
        New mutated pattern
    """
    parent = await get_pattern_by_id(session, pattern_id)
    if not parent:
        raise ValueError(f"Pattern not found: {pattern_id}")

    # Mutate conditions
    entry_conditions = mutate_conditions(parent.entry_conditions or [], mutation_rate, seed)
    exit_conditions = mutate_conditions(parent.exit_conditions or [], mutation_rate, seed)

    # Create child pattern
    child = await create_pattern(
        session=session,
        name=f"{parent.name}_mutated",
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        origin=parent.origin,
        description=f"Mutated from {pattern_id}",
        symbol=parent.symbol,
        timeframe=parent.timeframe,
    )

    return child


async def crossover_patterns(
    session: AsyncSession,
    pattern_a_id: str,
    pattern_b_id: str,
    seed: int | None = None,
) -> Pattern:
    """
    Create a crossover child from two parent patterns.

    Args:
        session: Database session
        pattern_a_id: First parent
        pattern_b_id: Second parent
        seed: Random seed

    Returns:
        New crossover pattern
    """
    parent_a = await get_pattern_by_id(session, pattern_a_id)
    parent_b = await get_pattern_by_id(session, pattern_b_id)

    if not parent_a:
        raise ValueError(f"Pattern A not found: {pattern_a_id}")
    if not parent_b:
        raise ValueError(f"Pattern B not found: {pattern_b_id}")

    if seed is not None:
        random.seed(seed)

    # Combine conditions from both parents
    entry_a = parent_a.entry_conditions or []
    entry_b = parent_b.entry_conditions or []

    # Take half from each (random selection)
    half_a = entry_a[: len(entry_a) // 2 + 1]
    half_b = entry_b[len(entry_b) // 2 :]

    combined_entry = half_a + half_b

    # Similar for exit conditions
    exit_a = parent_a.exit_conditions or []
    exit_b = parent_b.exit_conditions or []
    combined_exit = exit_a[: len(exit_a) // 2 + 1] + exit_b[len(exit_b) // 2 :]

    child = await create_pattern(
        session=session,
        name=f"{parent_a.name}_x_{parent_b.name}",
        entry_conditions=combined_entry,
        exit_conditions=combined_exit,
        origin="hybrid",
        description=f"Crossover of {pattern_a_id} and {pattern_b_id}",
        symbol=parent_a.symbol or parent_b.symbol,
        timeframe=parent_a.timeframe or parent_b.timeframe,
    )

    return child


# =============================================================================
# Selection Pressure
# =============================================================================


async def apply_selection_pressure(
    session: AsyncSession,
    seed: int | None = None,
) -> dict[str, int]:
    """
    Apply selection pressure: clone top 20%, cull bottom 30%.

    Args:
        session: Database session
        seed: Random seed for determinism

    Returns:
        Dict with counts of cloned, culled patterns
    """
    if seed is not None:
        random.seed(seed)

    # Get all active patterns ordered by fitness
    patterns = await get_all_patterns(session, limit=1000)

    if not patterns:
        return {"cloned": 0, "culled": 0, "survived": 0}

    # Sort by fitness descending
    sorted_patterns = sorted(patterns, key=lambda p: p.fitness_score or 0, reverse=True)

    total = len(sorted_patterns)
    top_count = max(1, int(total * TOP_PERCENT_CLONE))
    bottom_count = max(1, int(total * BOTTOM_PERCENT_CULL))

    cloned = 0
    culled = 0

    # Clone top performers
    for pattern in sorted_patterns[:top_count]:
        try:
            await mutate_pattern(session, pattern.pattern_id, seed=seed)
            cloned += 1
        except Exception:
            pass

    # Cull bottom performers
    for pattern in sorted_patterns[-bottom_count:]:
        try:
            await cull_pattern(session, pattern.pattern_id)
            culled += 1
        except Exception:
            pass

    survived = total - culled

    return {"cloned": cloned, "culled": culled, "survived": survived}


# =============================================================================
# Fitness Calculation
# =============================================================================


def calculate_pattern_fitness(
    roi_pct: float,
    sharpe_ratio: float,
    win_rate: float,
    trade_count: int,
    max_drawdown_pct: float = 0,
) -> float:
    """
    Calculate pattern fitness from backtest metrics.

    Formula:
    - ROI component: 30%
    - Sharpe component: 30%
    - Win rate component: 20%
    - Trade count penalty/bonus: 20%

    Args:
        roi_pct: Total ROI percentage
        sharpe_ratio: Sharpe ratio
        win_rate: Win rate (0-1)
        trade_count: Number of trades
        max_drawdown_pct: Max drawdown percentage

    Returns:
        Fitness score in [0, 100]
    """
    # ROI component (cap at ±50%)
    roi_capped = max(-50, min(50, roi_pct))
    roi_score = (roi_capped + 50) / 100 * 100  # Scale to 0-100

    # Sharpe component (cap at ±3)
    sharpe_capped = max(-3, min(3, sharpe_ratio))
    sharpe_score = (sharpe_capped + 3) / 6 * 100  # Scale to 0-100

    # Win rate component (already 0-1, scale to 0-100)
    win_rate_score = max(0, min(1, win_rate)) * 100

    # Trade count component (penalty for too few, bonus for many)
    if trade_count < 10:
        trade_score = trade_count * 5  # 0-50 for 0-10 trades
    elif trade_count < 100:
        trade_score = 50 + (trade_count - 10) * 0.5  # 50-95 for 10-100 trades
    else:
        trade_score = 95 + min(5, (trade_count - 100) * 0.01)  # 95-100 for 100+ trades

    # Drawdown penalty
    drawdown_penalty = min(20, max_drawdown_pct * 0.5)

    # Weighted average
    fitness = roi_score * 0.30 + sharpe_score * 0.30 + win_rate_score * 0.20 + trade_score * 0.20 - drawdown_penalty

    return max(0.0, min(100.0, fitness))


async def update_pattern_fitness(
    session: AsyncSession,
    pattern_id: str,
    roi_pct: float,
    sharpe_ratio: float,
    win_rate: float,
    trade_count: int,
    max_drawdown_pct: float = 0,
) -> Pattern | None:
    """Update pattern with calculated fitness."""
    fitness = calculate_pattern_fitness(roi_pct, sharpe_ratio, win_rate, trade_count, max_drawdown_pct)

    return await update_pattern(
        session,
        pattern_id,
        fitness_score=fitness,
        total_roi_pct=roi_pct,
        sharpe_ratio=sharpe_ratio,
        win_rate=win_rate,
        total_trades=trade_count,
        max_drawdown_pct=max_drawdown_pct,
        last_backtest_at=datetime.utcnow(),
    )


# =============================================================================
# Agent Assignment
# =============================================================================


def is_assignable_to_agent(tier: int) -> bool:
    """Check if pattern tier can be assigned to agents."""
    return tier in [1, 2]  # Only tier 1 and 2 are assignable


async def assign_pattern_to_agent(
    session: AsyncSession,
    pattern_id: str,
    agent_id: str,
) -> Pattern | None:
    """
    Assign pattern to an agent.

    Only tier 1 and 2 patterns can be assigned.
    """
    pattern = await get_pattern_by_id(session, pattern_id)
    if not pattern:
        raise ValueError(f"Pattern not found: {pattern_id}")

    tier = get_tier_from_fitness(pattern.fitness_score or 50)
    if not is_assignable_to_agent(tier):
        raise ValueError(f"Tier {tier} patterns cannot be assigned to agents")

    pattern.assigned_agent_id = agent_id
    pattern.last_selected_at = datetime.utcnow()
    pattern.updated_at = datetime.utcnow()

    await session.flush()
    return pattern


async def unassign_pattern_from_agent(
    session: AsyncSession,
    pattern_id: str,
) -> Pattern | None:
    """Unassign pattern from its agent."""
    pattern = await get_pattern_by_id(session, pattern_id)
    if not pattern:
        return None

    pattern.assigned_agent_id = None
    pattern.updated_at = datetime.utcnow()

    await session.flush()
    return pattern


# =============================================================================
# Pure Functions for Dict-Based Patterns (Used in Tests)
# =============================================================================


def should_promote_dict(pattern: dict[str, Any]) -> int | None:
    """
    Check if pattern dict should be promoted.

    Returns target tier or None if no promotion.
    """
    fitness = pattern.get("fitness_score", 0)
    tier = pattern.get("tier", 3)
    trades = pattern.get("number_of_runs", 0)

    if trades < MIN_TRADES_FOR_PROMOTION:
        return None

    if tier == 3 and fitness >= FITNESS_TIER_2_THRESHOLD:
        return 2
    if tier == 2 and fitness >= FITNESS_TIER_1_THRESHOLD:
        return 1

    return None


def should_demote_dict(pattern: dict[str, Any]) -> int | None:
    """
    Check if pattern dict should be demoted.

    Returns target tier or None if no demotion.
    """
    fitness = pattern.get("fitness_score", 0)
    tier = pattern.get("tier", 3)

    if tier == 1 and fitness < DEMOTION_TIER_1_THRESHOLD:
        return 2
    if tier == 2 and fitness < DEMOTION_TIER_2_THRESHOLD:
        return 3

    return None


def should_cull_dict(pattern: dict[str, Any]) -> bool:
    """Check if pattern dict should be culled."""
    fitness = pattern.get("fitness_score", 0)
    tier = pattern.get("tier", 3)
    return tier == 3 and fitness < FITNESS_CULL_THRESHOLD


def is_assignable_to_agent_dict(pattern: dict[str, Any]) -> bool:
    """Check if pattern dict can be assigned to agents."""
    tier = pattern.get("tier", 3)
    status = pattern.get("status", "active")
    return tier in [1, 2] and status != "archived"


def mutate_condition_dict(
    condition: dict[str, Any],
    mutation_rate: float = MUTATION_RATE,
) -> dict[str, Any]:
    """
    Mutate a single condition's bounds by ±mutation_rate.
    Bounds indicator values to valid ranges.
    """
    from .pattern_matching_service import INDICATOR_BOUNDS

    mutated = condition.copy()
    indicator = mutated.get("indicator", "")
    bounds = INDICATOR_BOUNDS.get(indicator, (float("-inf"), float("inf")))

    if "min" in mutated and mutated["min"] is not None:
        change = random.uniform(-mutation_rate, mutation_rate)
        new_val = mutated["min"] * (1 + change)
        mutated["min"] = max(bounds[0], min(bounds[1], new_val))

    if "max" in mutated and mutated["max"] is not None:
        change = random.uniform(-mutation_rate, mutation_rate)
        new_val = mutated["max"] * (1 + change)
        mutated["max"] = max(bounds[0], min(bounds[1], new_val))

    # Ensure min <= max
    if mutated.get("min") is not None and mutated.get("max") is not None:
        if mutated["min"] > mutated["max"]:
            mutated["min"], mutated["max"] = mutated["max"], mutated["min"]

    return mutated


def mutate_conditions_dict(
    conditions: list[dict[str, Any]],
    mutation_rate: float = MUTATION_RATE,
) -> list[dict[str, Any]]:
    """Mutate all conditions in list."""
    return [mutate_condition_dict(c, mutation_rate) for c in conditions]


def mutate_pattern_dict(
    pattern: dict[str, Any],
    mutation_rate: float = MUTATION_RATE,
) -> dict[str, Any]:
    """
    Create a mutated copy of a pattern dict.

    Returns new pattern dict with mutated conditions.
    """
    child = pattern.copy()

    # New ID
    child["pattern_id"] = f"mut-{uuid.uuid4().hex[:12]}"

    # Track lineage
    child["parent_id"] = pattern.get("pattern_id")
    child["generation"] = pattern.get("generation", 1) + 1

    # Mutate conditions
    if child.get("entry_conditions"):
        child["entry_conditions"] = mutate_conditions_dict(child["entry_conditions"], mutation_rate)

    if child.get("exit_conditions"):
        child["exit_conditions"] = mutate_conditions_dict(child["exit_conditions"], mutation_rate)

    # Reset fitness for new pattern
    child["fitness_score"] = 50.0
    child["number_of_runs"] = 0
    child["status"] = "untested"
    child["created_at"] = datetime.utcnow().isoformat()

    return child


def crossover_patterns_dict(
    parent_a: dict[str, Any],
    parent_b: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a crossover child from two parent pattern dicts.
    """
    # Combine entry conditions from both parents
    entry_a = parent_a.get("entry_conditions", [])
    entry_b = parent_b.get("entry_conditions", [])

    # Take roughly half from each
    split_a = len(entry_a) // 2 + 1 if entry_a else 0
    split_b = len(entry_b) // 2 if entry_b else 0

    combined_entry = entry_a[:split_a] + entry_b[split_b:]
    if not combined_entry:
        combined_entry = entry_a or entry_b or []

    # Same for exit conditions
    exit_a = parent_a.get("exit_conditions", [])
    exit_b = parent_b.get("exit_conditions", [])

    split_exit_a = len(exit_a) // 2 + 1 if exit_a else 0
    split_exit_b = len(exit_b) // 2 if exit_b else 0

    combined_exit = exit_a[:split_exit_a] + exit_b[split_exit_b:]
    if not combined_exit:
        combined_exit = exit_a or exit_b or []

    child = {
        "pattern_id": f"cross-{uuid.uuid4().hex[:12]}",
        "name": f"Crossover_{parent_a.get('pattern_id', 'a')}_{parent_b.get('pattern_id', 'b')}",
        "entry_conditions": combined_entry,
        "exit_conditions": combined_exit,
        "parent_id": parent_a.get("pattern_id"),
        "parent_a_id": parent_a.get("pattern_id"),
        "parent_b_id": parent_b.get("pattern_id"),
        "generation": max(parent_a.get("generation", 1), parent_b.get("generation", 1)) + 1,
        "origin": "hybrid",
        "tier": 3,
        "fitness_score": 50.0,
        "number_of_runs": 0,
        "status": "untested",
        "asset": parent_a.get("asset") or parent_b.get("asset"),
        "timeframe": parent_a.get("timeframe") or parent_b.get("timeframe"),
        "created_at": datetime.utcnow().isoformat(),
    }

    return child


def apply_selection_pressure_dict(
    patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Apply selection pressure to list of pattern dicts.

    Returns dict with cloned_count, culled_count, survivors, culled lists.
    """
    if not patterns:
        return {
            "cloned_count": 0,
            "culled_count": 0,
            "survivors": [],
            "culled": [],
            "clones": [],
        }

    # Sort by fitness descending
    sorted_patterns = sorted(patterns, key=lambda p: p.get("fitness_score", 0), reverse=True)

    total = len(sorted_patterns)
    top_count = max(1, int(total * TOP_PERCENT_CLONE))

    # Determine which to cull (bottom 30% OR fitness < 40)
    culled = []
    survivors = []

    for i, p in enumerate(sorted_patterns):
        fitness = p.get("fitness_score", 0)
        # Cull if in bottom 30% AND fitness < cull threshold
        if fitness < FITNESS_CULL_THRESHOLD:
            culled.append(p)
        else:
            survivors.append(p)

    # Clone top performers
    clones = []
    for pattern in sorted_patterns[:top_count]:
        clone = mutate_pattern_dict(pattern)
        clones.append(clone)

    return {
        "cloned_count": len(clones),
        "culled_count": len(culled),
        "survivors": survivors,
        "culled": culled,
        "clones": clones,
    }


def calculate_pattern_fitness_from_backtest(
    backtest: dict[str, Any],
) -> float:
    """
    Calculate pattern fitness from backtest result dict.

    Args:
        backtest: Dict with total_trades, winning_trades, total_roi_pct,
                  sharpe_ratio, max_drawdown_pct, etc.

    Returns:
        Fitness score in [0, 100]
    """
    total_trades = backtest.get("total_trades", 0)
    winning_trades = backtest.get("winning_trades", 0)
    total_roi_pct = backtest.get("total_roi_pct", 0)
    sharpe_ratio = backtest.get("sharpe_ratio", 0)
    max_drawdown_pct = backtest.get("max_drawdown_pct", 0)

    # Win rate
    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    return calculate_pattern_fitness(
        roi_pct=total_roi_pct,
        sharpe_ratio=sharpe_ratio,
        win_rate=win_rate,
        trade_count=total_trades,
        max_drawdown_pct=max_drawdown_pct,
    )


# Aliases for test compatibility
def should_promote(pattern: dict[str, Any]) -> int | None:
    """Alias for should_promote_dict."""
    return should_promote_dict(pattern)


def should_demote(pattern: dict[str, Any]) -> int | None:
    """Alias for should_demote_dict."""
    return should_demote_dict(pattern)


def should_cull(pattern: dict[str, Any]) -> bool:
    """Alias for should_cull_dict."""
    return should_cull_dict(pattern)


def is_assignable_to_agent(pattern: dict[str, Any]) -> bool:
    """Alias for is_assignable_to_agent_dict."""
    return is_assignable_to_agent_dict(pattern)


def mutate_condition(condition: dict[str, Any], mutation_rate: float = MUTATION_RATE) -> dict[str, Any]:
    """Alias for mutate_condition_dict."""
    return mutate_condition_dict(condition, mutation_rate)


def mutate_conditions(conditions: list[dict[str, Any]], mutation_rate: float = MUTATION_RATE) -> list[dict[str, Any]]:
    """Alias for mutate_conditions_dict."""
    return mutate_conditions_dict(conditions, mutation_rate)


def mutate_pattern(pattern: dict[str, Any], mutation_rate: float = MUTATION_RATE) -> dict[str, Any]:
    """Alias for mutate_pattern_dict."""
    return mutate_pattern_dict(pattern, mutation_rate)


def crossover_patterns(parent_a: dict[str, Any], parent_b: dict[str, Any]) -> dict[str, Any]:
    """Alias for crossover_patterns_dict."""
    return crossover_patterns_dict(parent_a, parent_b)


def apply_selection_pressure(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    """Alias for apply_selection_pressure_dict."""
    return apply_selection_pressure_dict(patterns)


# =============================================================================
# Regime-Priority Functions
# =============================================================================


async def get_weakest_regime_categories(
    session: AsyncSession,
    top_n_worst: int = 5,
) -> list[str]:
    """
    Find the N weakest (regime, timeframe) categories by average fitness.

    This is used for regime-priority spawning: we want to spawn agents with
    patterns that excel in the weakest categories to improve overall robustness.

    Args:
        session: Database session
        top_n_worst: Number of worst categories to return

    Returns:
        List of category names sorted by lowest avg fitness first.
        Example: ['crash', 'bear', 'random_1m', 'sideways', 'blowoff']
    """
    from sqlalchemy import text

    # Query fitness_by_regime from all active patterns
    # This handles both agents and patterns with regime fitness data
    result = await session.execute(
        text("""
        SELECT
            key as category,
            AVG(COALESCE(
                (value->>'fitness')::float,
                CASE WHEN jsonb_typeof(value) = 'number' THEN value::text::float ELSE NULL END
            )) as avg_fitness,
            COUNT(*) as sample_count
        FROM patterns, jsonb_each(fitness_by_regime)
        WHERE is_active = true
          AND fitness_by_regime IS NOT NULL
          AND fitness_by_regime != '{}'::jsonb
          AND (
              value->>'fitness' IS NOT NULL
              OR jsonb_typeof(value) = 'number'
          )
        GROUP BY key
        HAVING COUNT(*) >= 5
        ORDER BY avg_fitness ASC
        LIMIT :limit
    """),
        {"limit": top_n_worst},
    )

    rows = result.fetchall()

    if not rows:
        # Fallback: try agent fitness_by_regime
        result = await session.execute(
            text("""
            SELECT
                key as category,
                AVG(COALESCE(
                    (value->>'fitness')::float,
                    CASE WHEN jsonb_typeof(value) = 'number' THEN value::text::float ELSE NULL END
                )) as avg_fitness,
                COUNT(*) as sample_count
            FROM agents, jsonb_each(fitness_by_regime)
            WHERE is_active = true
              AND fitness_by_regime IS NOT NULL
              AND fitness_by_regime != '{}'::jsonb
              AND (
                  value->>'fitness' IS NOT NULL
                  OR jsonb_typeof(value) = 'number'
              )
            GROUP BY key
            HAVING COUNT(*) >= 5
            ORDER BY avg_fitness ASC
            LIMIT :limit
        """),
            {"limit": top_n_worst},
        )
        rows = result.fetchall()

    categories = [row[0] for row in rows]
    print(f"[PatternService] Weakest {len(categories)} regime categories: {categories}")
    return categories


def calculate_pattern_fitness(
    backtest_or_roi=None,
    sharpe_ratio=None,
    win_rate=None,
    trade_count=None,
    max_drawdown_pct=0,
    *,
    roi_pct=None,
):
    """
    Calculate pattern fitness - overloaded to accept dict or individual args.

    Can be called as:
    - calculate_pattern_fitness(backtest_dict)
    - calculate_pattern_fitness(roi_pct=10, sharpe_ratio=1, ...)
    - calculate_pattern_fitness(10, 1, 0.5, 100)  # positional
    """
    # Handle dict input
    if isinstance(backtest_or_roi, dict):
        return calculate_pattern_fitness_from_backtest(backtest_or_roi)

    # Determine ROI value - prefer keyword arg, fall back to positional
    actual_roi = roi_pct if roi_pct is not None else (backtest_or_roi if backtest_or_roi is not None else 0)

    # ROI component (cap at ±50%)
    roi_capped = max(-50, min(50, actual_roi))
    roi_score = (roi_capped + 50) / 100 * 100

    # Sharpe component (cap at ±3)
    sharpe_capped = max(-3, min(3, sharpe_ratio or 0))
    sharpe_score = (sharpe_capped + 3) / 6 * 100

    # Win rate component
    win_rate_score = max(0, min(1, win_rate or 0)) * 100

    # Trade count component
    tc = trade_count or 0
    if tc < 10:
        trade_score = tc * 5
    elif tc < 100:
        trade_score = 50 + (tc - 10) * 0.5
    else:
        trade_score = 95 + min(5, (tc - 100) * 0.01)

    # Drawdown penalty
    drawdown_penalty = min(20, (max_drawdown_pct or 0) * 0.5)

    fitness = roi_score * 0.30 + sharpe_score * 0.30 + win_rate_score * 0.20 + trade_score * 0.20 - drawdown_penalty

    return max(0.0, min(100.0, fitness))
