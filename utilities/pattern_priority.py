"""
Pattern Priority Module - Async PostgreSQL-based priority management.

Ported from Coinswarm-1/local-utilities with improvements:
- Async-first using SQLAlchemy async sessions
- Integrated with Fast_Swarm Database module
- No external dependencies (psycopg2 directly) - uses existing session factory
- Cleaner type hints and error handling

Priority Selection Logic:
  HIGH (0): Fast-tracked for validation
    - Academic patterns: until 100 runs
    - AI-generated patterns: until 50 runs
    - User-specified HIGH: until 300 runs

  NORMAL (1): Active backtesting
    - 30% lowest runs (need more data)
    - 20% lowest fitness (might improve)
    - 50% highest fitness (proven winners)

  LOW (2): Deprioritized (still tested, just later)
    - Patterns with 300+ periods tested (unless top fitness)
"""

from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class Priority(IntEnum):
    """Pattern priority levels for backtesting queue."""

    HIGH = 0  # Fast-tracked (academic, AI, user-specified)
    NORMAL = 1  # Active backtesting
    LOW = 2  # Deprioritized (enough data)


# Thresholds
PERIODS_THRESHOLD = 300  # Patterns with 300+ periods go to low priority

HIGH_PRIORITY_RUNS = {
    "academic": 100,
    "ai": 50,
    "user_high": 300,
}

AI_ORIGINS = {"ai", "ai_generated", "chaos_discovery", "ml_generated", "automated_discovery"}


@dataclass
class PriorityResult:
    """Result of priority calculation."""

    pattern_id: str
    priority: int
    selection_reason: str


def calculate_single_priority(
    origin: str,
    total_runs: int,
    periods_tested: int,
    fitness_score: float,
    is_in_top_fitness: bool = False,
) -> tuple[int, str]:
    """
    Calculate priority for a single pattern.

    Returns:
        (priority_level, selection_reason)
    """
    origin_lower = (origin or "").lower()
    total_runs = total_runs or 0
    periods_tested = periods_tested or 0

    # Check HIGH priority by origin
    if origin_lower == "academic" and total_runs < HIGH_PRIORITY_RUNS["academic"]:
        return Priority.HIGH, "high_priority_academic"

    if origin_lower in AI_ORIGINS and total_runs < HIGH_PRIORITY_RUNS["ai"]:
        return Priority.HIGH, "high_priority_ai"

    if origin_lower == "user_high" and total_runs < HIGH_PRIORITY_RUNS["user_high"]:
        return Priority.HIGH, "high_priority_user"

    # Check LOW priority (enough data)
    if periods_tested >= PERIODS_THRESHOLD and not is_in_top_fitness:
        return Priority.LOW, "low_priority_enough_data"

    return Priority.NORMAL, "normal_priority"


def calculate_priority_buckets(patterns: list[dict]) -> dict[str, list[dict]]:
    """
    Assign patterns to priority buckets.

    Returns:
        Dict with 'high', 'normal', 'low' lists
    """
    if not patterns:
        return {"high": [], "normal": [], "low": []}

    high = []
    remaining = []

    # FIRST PASS: Check HIGH priority by origin
    for p in patterns:
        origin = (p.get("origin") or "").lower()
        runs = p.get("total_runs") or 0

        if origin == "academic" and runs < HIGH_PRIORITY_RUNS["academic"]:
            p["selection_reason"] = "high_priority_academic"
            p["priority"] = Priority.HIGH
            high.append(p)
        elif origin in AI_ORIGINS and runs < HIGH_PRIORITY_RUNS["ai"]:
            p["selection_reason"] = "high_priority_ai"
            p["priority"] = Priority.HIGH
            high.append(p)
        elif origin == "user_high" and runs < HIGH_PRIORITY_RUNS["user_high"]:
            p["selection_reason"] = "high_priority_user"
            p["priority"] = Priority.HIGH
            high.append(p)
        else:
            remaining.append(p)

    # SECOND PASS: NORMAL/LOW logic
    n = len(remaining)
    if n == 0:
        return {"high": high, "normal": [], "low": []}

    # Sort by metrics
    by_runs = sorted(remaining, key=lambda p: p.get("total_runs") or 0)
    by_fitness_desc = sorted(remaining, key=lambda p: p.get("fitness_score") or 0, reverse=True)

    # Bucket sizes
    lowest_runs_count = max(1, int(n * 0.30))
    highest_fitness_count = max(1, int(n * 0.50))

    lowest_runs_ids = {p["pattern_id"] for p in by_runs[:lowest_runs_count]}
    highest_fitness_ids = {p["pattern_id"] for p in by_fitness_desc[:highest_fitness_count]}

    normal = []
    low = []

    for p in remaining:
        pid = p["pattern_id"]
        periods = p.get("periods_tested") or 0
        in_highest_fitness = pid in highest_fitness_ids
        in_lowest_runs = pid in lowest_runs_ids

        if periods >= PERIODS_THRESHOLD and not in_highest_fitness:
            p["selection_reason"] = "low_priority_enough_data"
            p["priority"] = Priority.LOW
            low.append(p)
        elif in_highest_fitness:
            p["selection_reason"] = "highest_fitness"
            p["priority"] = Priority.NORMAL
            normal.append(p)
        elif in_lowest_runs:
            p["selection_reason"] = "lowest_runs"
            p["priority"] = Priority.NORMAL
            normal.append(p)
        else:
            p["selection_reason"] = "low_priority_not_selected"
            p["priority"] = Priority.LOW
            low.append(p)

    return {"high": high, "normal": normal, "low": low}


async def get_prioritized_patterns(
    session: AsyncSession,
    limit: int | None = None,
    include_low: bool = False,
) -> list[dict]:
    """
    Get patterns ordered by priority (HIGH first, then NORMAL).

    Args:
        session: Async database session
        limit: Max patterns to return
        include_low: Whether to include LOW priority

    Returns:
        List of pattern dicts ordered by priority
    """
    conditions = ["is_active = TRUE"]

    if not include_low:
        conditions.append("COALESCE(priority, 2) < 3")  # priority 3 = untested/low priority

    where_clause = " AND ".join(conditions)
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT
            pattern_id, name, entry_conditions, exit_conditions,
            origin, fitness_score, total_runs,
            periods_tested, priority
        FROM patterns
        WHERE {where_clause}
        ORDER BY
            COALESCE(priority, 2) ASC,
            COALESCE(total_runs, 0) ASC,
            created_at DESC
        {limit_clause}
    """

    result = await session.execute(text(query))
    rows = result.fetchall()

    patterns = []
    for row in rows:
        patterns.append(
            {
                "pattern_id": row[0],
                "name": row[1],
                "entry_conditions": row[2],
                "exit_conditions": row[3],
                "origin": row[4],
                "fitness_score": row[5],
                "total_runs": row[6],
                "periods_tested": row[7],
                "priority": row[8],
            }
        )

    return patterns


async def update_priority_after_backtest(
    session: AsyncSession,
    pattern_id: str,
    new_runs: int,
    new_periods_tested: int,
    new_fitness: float,
) -> None:
    """
    Update pattern's priority after a backtest run.

    Args:
        session: Async database session
        pattern_id: Pattern to update
        new_runs: Updated total_runs count
        new_periods_tested: Updated periods_tested count
        new_fitness: Updated fitness score
    """
    # Get pattern origin
    result = await session.execute(text("SELECT origin FROM patterns WHERE pattern_id = :pid"), {"pid": pattern_id})
    row = result.fetchone()
    if not row:
        return

    origin = row[0] or ""

    # Check if in top 50% by fitness
    result = await session.execute(
        text("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN fitness_score <= :fitness THEN 1 ELSE 0 END) as rank
            FROM patterns
            WHERE is_active = TRUE AND fitness_score IS NOT NULL
        """),
        {"fitness": new_fitness},
    )
    stats = result.fetchone()
    total = stats[0] or 1
    rank = stats[1] or 0
    is_in_top_fitness = (rank / total) >= 0.5

    # Calculate new priority
    priority, reason = calculate_single_priority(
        origin=origin,
        total_runs=new_runs,
        periods_tested=new_periods_tested,
        fitness_score=new_fitness,
        is_in_top_fitness=is_in_top_fitness,
    )

    # Map priority level to DB priority value (Fast_Swarm uses priority 1-4)
    # Priority HIGH (0) -> 1 (elite)
    # Priority NORMAL (1) -> 2 (proven)
    # Priority LOW (2) -> 3 (untested)
    priority_map = {Priority.HIGH: 1, Priority.NORMAL: 2, Priority.LOW: 3}
    db_priority = priority_map.get(priority, 2)

    await session.execute(
        text("""
            UPDATE patterns
            SET priority = :priority,
                periods_tested = :periods,
                total_runs = :runs
            WHERE pattern_id = :pid
        """),
        {"priority": db_priority, "periods": new_periods_tested, "runs": new_runs, "pid": pattern_id},
    )
    await session.commit()


async def recalculate_all_priorities(session: AsyncSession) -> dict[str, int]:
    """
    Recalculate priorities for ALL patterns.

    Returns:
        Dict with counts: {'high': N, 'normal': N, 'low': N}
    """
    # Fetch all active patterns
    result = await session.execute(
        text("""
            SELECT pattern_id, origin, total_runs, periods_tested, fitness_score
            FROM patterns
            WHERE is_active = TRUE
        """)
    )
    rows = result.fetchall()

    patterns = []
    for row in rows:
        patterns.append(
            {
                "pattern_id": row[0],
                "origin": row[1],
                "total_runs": row[2],
                "periods_tested": row[3],
                "fitness_score": row[4],
            }
        )

    if not patterns:
        return {"high": 0, "normal": 0, "low": 0}

    # Calculate buckets
    buckets = calculate_priority_buckets(patterns)

    # Batch update
    priority_map = {Priority.HIGH: 1, Priority.NORMAL: 2, Priority.LOW: 3}

    for bucket_name, bucket_patterns in buckets.items():
        for p in bucket_patterns:
            db_priority = priority_map.get(p["priority"], 2)
            await session.execute(
                text("UPDATE patterns SET priority = :priority WHERE pattern_id = :pid"),
                {"priority": db_priority, "pid": p["pattern_id"]},
            )

    await session.commit()

    counts = {
        "high": len(buckets["high"]),
        "normal": len(buckets["normal"]),
        "low": len(buckets["low"]),
    }

    print(
        f"[Priority] Recalculated {len(patterns)} patterns: "
        f"HIGH={counts['high']}, NORMAL={counts['normal']}, LOW={counts['low']}"
    )

    return counts
