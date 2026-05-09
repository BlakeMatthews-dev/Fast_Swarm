from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import asc, desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ...Database import get_session
from ..Models.pattern_models import (
    Pattern,
    PatternFitnessByRegimeResponse,
    PatternLeaderboardResponse,
    PatternsByOriginResponse,
    PatternsByTierResponse,
    PatternSummary,
    RegimePatternSummary,
    TopPatternsByRegimeResponse,
)
from ..Services import pattern_service

router = APIRouter(prefix="/patterns", tags=["Patterns"])

# Valid sort columns for leaderboard
SORT_COLUMNS = {
    "fitness_score": Pattern.fitness_score,
    "total_roi_pct": Pattern.total_roi_pct,
    "sharpe_ratio": Pattern.sharpe_ratio,
    "win_rate": Pattern.win_rate,
    "profit_factor": Pattern.profit_factor,
    "max_drawdown_pct": Pattern.max_drawdown_pct,
    "total_trades": Pattern.total_trades,
    "total_runs": Pattern.total_runs,
    "created_at": Pattern.created_at,
    "last_backtest_at": Pattern.last_backtest_at,
}


@router.get("/leaderboard", response_model=PatternLeaderboardResponse)
async def get_pattern_leaderboard(
    sort_by: str = Query("fitness_score", description="Column to sort by"),
    order: Literal["asc", "desc"] = Query("desc", description="Sort order"),
    origin: str | None = Query(None, description="Filter by origin (chaos/academic/technical/ai/hybrid)"),
    min_trades: int = Query(0, description="Minimum number of trades"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> PatternLeaderboardResponse:
    """
    Pattern leaderboard with sortable stats.

    Sortable columns: fitness_score, total_roi_pct, sharpe_ratio, win_rate,
    profit_factor, max_drawdown_pct, total_trades, total_runs, created_at, last_backtest_at
    """
    if sort_by not in SORT_COLUMNS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by. Must be one of: {list(SORT_COLUMNS.keys())}")

    column = SORT_COLUMNS[sort_by]
    order_func = desc if order == "desc" else asc

    statement = select(Pattern).where(Pattern.status != "archived")

    if origin:
        statement = statement.where(Pattern.origin == origin)

    if min_trades > 0:
        statement = statement.where(Pattern.total_trades >= min_trades)

    statement = statement.order_by(order_func(column).nulls_last())
    statement = statement.offset(offset).limit(limit)

    result = await session.execute(statement)
    patterns = result.scalars().all()

    return PatternLeaderboardResponse(
        count=len(patterns),
        sort_by=sort_by,
        order=order,
        patterns=[
            PatternSummary(
                pattern_id=p.pattern_id,
                name=p.name,
                origin=p.origin,
                status=p.status,
                fitness_score=float(p.fitness_score) if p.fitness_score else None,
                total_roi_pct=float(p.total_roi_pct) if p.total_roi_pct else None,
                sharpe_ratio=p.sharpe_ratio,
                win_rate=p.win_rate,
                profit_factor=p.profit_factor,
                max_drawdown_pct=p.max_drawdown_pct,
                total_trades=p.total_trades,
                total_runs=p.total_runs,
                symbol=p.symbol,
                timeframe=p.timeframe,
                last_backtest_at=p.last_backtest_at.isoformat() if p.last_backtest_at else None,
                created_at=p.created_at.isoformat() if p.created_at else None,
            )
            for p in patterns
        ],
    )


@router.get("/", response_model=list[Pattern])
async def read_patterns(skip: int = 0, limit: int = 100, session: AsyncSession = Depends(get_session)):
    """
    Get all patterns, ordered by fitness score.
    """
    return await pattern_service.get_all_patterns(session, limit=limit, offset=skip)


@router.get("/stats/average")
async def get_average_pattern_stats(session: AsyncSession = Depends(get_session)):
    """
    Get average statistics for all active patterns.
    """
    from ..Services import pattern_stats_service

    return await pattern_stats_service.get_pattern_average_stats(session)


@router.get("/by-tier/{tier}", response_model=PatternsByTierResponse)
async def get_patterns_by_tier(
    tier: int, limit: int = Query(100, ge=1, le=500), session: AsyncSession = Depends(get_session)
) -> PatternsByTierResponse:
    """
    Get patterns by tier (1=Elite 80+, 2=Proven 60-79, 3=Untested <60).
    """
    if tier not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Tier must be 1, 2, or 3")
    patterns = await pattern_service.get_patterns_by_tier(session, tier, limit)
    return PatternsByTierResponse(tier=tier, count=len(patterns), patterns=patterns)


@router.get("/by-origin/{origin}", response_model=PatternsByOriginResponse)
async def get_patterns_by_origin(
    origin: str, limit: int = Query(100, ge=1, le=500), session: AsyncSession = Depends(get_session)
) -> PatternsByOriginResponse:
    """
    Get patterns by origin (chaos/academic/technical/ai/hybrid).
    """
    patterns = await pattern_service.get_patterns_by_origin(session, origin, limit)
    return PatternsByOriginResponse(origin=origin, count=len(patterns), patterns=patterns)


@router.get("/top-by-regime/{regime}", response_model=TopPatternsByRegimeResponse)
async def get_top_patterns_by_regime(
    regime: str, limit: int = Query(20, ge=1, le=100), session: AsyncSession = Depends(get_session)
) -> TopPatternsByRegimeResponse:
    """
    Get top performing patterns for a specific regime.

    Supported regimes:
    - Canonical: crash, bull, bear, sideways, blowoff, recovery, volatile, winter, transition
    - Random windows: random_1m, random_5m, random_15m, random_1h, random_4h, random_1d

    Returns patterns sorted by fitness in that regime.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT pattern_id, name, origin, status, fitness_score,
                   fitness_by_regime->:regime->>'fitness' as regime_fitness,
                   fitness_by_regime->:regime->>'trades' as regime_trades,
                   fitness_by_regime->:regime->>'win_rate' as regime_win_rate,
                   fitness_by_regime->:regime->>'sharpe' as regime_sharpe
            FROM patterns
            WHERE status != 'archived'
              AND fitness_by_regime ? :regime
              AND (fitness_by_regime->:regime->>'fitness')::float > 0
            ORDER BY (fitness_by_regime->:regime->>'fitness')::float DESC
            LIMIT :limit
        """),
        {"regime": regime, "limit": limit},
    )
    rows = result.fetchall()

    if not rows:
        return TopPatternsByRegimeResponse(
            regime=regime, patterns=[], message=f"No patterns with fitness data for regime '{regime}'"
        )

    return TopPatternsByRegimeResponse(
        regime=regime,
        count=len(rows),
        patterns=[
            RegimePatternSummary(
                pattern_id=row[0],
                name=row[1],
                origin=row[2],
                status=row[3],
                overall_fitness=float(row[4]) if row[4] else 0.0,
                regime_fitness=float(row[5]) if row[5] else 0.0,
                regime_trades=int(row[6]) if row[6] else 0,
                regime_win_rate=float(row[7]) if row[7] else None,
                regime_sharpe=float(row[8]) if row[8] else None,
            )
            for row in rows
        ],
    )


@router.get("/{pattern_id}/fitness-by-regime", response_model=PatternFitnessByRegimeResponse)
async def get_pattern_fitness_by_regime(
    pattern_id: str, session: AsyncSession = Depends(get_session)
) -> PatternFitnessByRegimeResponse:
    """
    Get per-regime fitness breakdown for a specific pattern.

    Returns fitness scores across all tested regimes:
    - crash, bull, bear, sideways, blowoff, recovery (canonical periods)
    - random_1m, random_15m, random_1h, random_1d (random windows)
    """
    pattern = await pattern_service.get_pattern_by_id(session, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    fitness_by_regime = pattern.fitness_by_regime or {}

    # Sort by fitness descending
    sorted_regimes = sorted(
        fitness_by_regime.items(), key=lambda x: x[1].get("fitness", 0) if isinstance(x[1], dict) else 0, reverse=True
    )

    return PatternFitnessByRegimeResponse(
        pattern_id=pattern.pattern_id,
        name=pattern.name,
        origin=pattern.origin,
        overall_fitness=float(pattern.fitness_score) if pattern.fitness_score else 0.0,
        best_regime=pattern.best_regime,
        best_regime_fitness=pattern.best_regime_fitness,
        regimes_tested=len(fitness_by_regime),
        fitness_by_regime=dict(sorted_regimes),
    )


@router.get("/{pattern_id}", response_model=Pattern)
async def get_pattern(pattern_id: str, session: AsyncSession = Depends(get_session)):
    """
    Get a specific pattern by ID.
    """
    pattern = await pattern_service.get_pattern_by_id(session, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern
