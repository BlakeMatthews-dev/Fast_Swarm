from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.pattern_models import Pattern


async def get_pattern_average_stats(session: AsyncSession):
    """
    Calculate average stats for all patterns using SQL aggregation.
    Returns a dictionary of average performance metrics.

    Optimized: Uses database-side aggregation instead of loading all patterns into memory.
    """
    # Use SQL aggregation for averages (much faster than loading all patterns)
    result = await session.execute(
        select(
            func.count().label('count'),
            func.avg(Pattern.fitness_score).label('avg_fitness'),
            func.avg(Pattern.win_rate).label('avg_win_rate'),
            func.avg(Pattern.total_trades).label('avg_trades'),
            func.avg(Pattern.total_roi_pct).label('avg_roi'),
            func.avg(Pattern.sortino_ratio).label('avg_sortino'),
        ).where(Pattern.is_active.is_(True), Pattern.fitness_score.isnot(None))
    )
    row = result.one()

    if not row.count or row.count == 0:
        return {"message": "No patterns with fitness scores found", "count": 0}

    averages = {
        "fitness_score": round(float(row.avg_fitness), 4) if row.avg_fitness else None,
        "win_rate": round(float(row.avg_win_rate), 4) if row.avg_win_rate else None,
        "total_trades": round(float(row.avg_trades), 4) if row.avg_trades else None,
        "total_roi_pct": round(float(row.avg_roi), 4) if row.avg_roi else None,
        "sortino_ratio": round(float(row.avg_sortino), 4) if row.avg_sortino else None,
    }

    # Count by status using SQL aggregation
    status_result = await session.execute(
        select(
            Pattern.status,
            func.count().label('count')
        ).where(
            Pattern.is_active.is_(True),
            Pattern.fitness_score.isnot(None)
        ).group_by(Pattern.status)
    )
    status_counts = {row.status or "unknown": row.count for row in status_result.all()}

    # Top 5 performers (only fetches 5 rows, not all patterns)
    top_result = await session.execute(
        select(Pattern.name, Pattern.fitness_score, Pattern.status)
        .where(Pattern.is_active.is_(True), Pattern.fitness_score.isnot(None))
        .order_by(Pattern.fitness_score.desc())
        .limit(5)
    )
    top_5 = [
        {"name": r.name, "fitness": round(float(r.fitness_score), 2), "status": r.status}
        for r in top_result.all()
    ]

    return {
        "count": row.count,
        "averages": averages,
        "by_status": status_counts,
        "top_performers": top_5,
    }
