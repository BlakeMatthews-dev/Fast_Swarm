from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.pattern_models import Pattern


async def get_pattern_average_stats(session: AsyncSession):
    """
    Calculate average stats for all patterns.
    Returns a dictionary of average performance metrics.
    """
    # Fetch patterns that are active and have fitness scores
    # Note: is_active=True, not status (status can be elite/surviving/retired/etc)
    statement = select(Pattern).where(Pattern.is_active == True, Pattern.fitness_score.isnot(None))
    result = await session.exec(statement)
    patterns = result.all()

    if not patterns:
        return {"message": "No patterns with fitness scores found", "count": 0}

    metrics = ["fitness_score", "win_rate", "total_trades", "total_roi_pct"]

    # Initialize sums
    totals = dict.fromkeys(metrics, 0.0)
    counts = dict.fromkeys(metrics, 0)

    for p in patterns:
        if p.fitness_score is not None:
            totals["fitness_score"] += float(p.fitness_score)
            counts["fitness_score"] += 1

        if p.win_rate is not None:
            totals["win_rate"] += float(p.win_rate)
            counts["win_rate"] += 1

        if p.total_trades is not None:
            totals["total_trades"] += float(p.total_trades)
            counts["total_trades"] += 1

        if p.total_roi_pct is not None:
            totals["total_roi_pct"] += float(p.total_roi_pct)
            counts["total_roi_pct"] += 1

    # Calculate Averages
    averages = {}
    for key in metrics:
        if counts[key] > 0:
            averages[key] = round(totals[key] / counts[key], 4)
        else:
            averages[key] = None

    # Count by status
    status_counts = {}
    for p in patterns:
        status = p.status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    # Top performers
    sorted_patterns = sorted([p for p in patterns if p.fitness_score], key=lambda x: x.fitness_score, reverse=True)
    top_5 = [{"name": p.name, "fitness": round(p.fitness_score, 2), "status": p.status} for p in sorted_patterns[:5]]

    return {
        "count": len(patterns),
        "averages": averages,
        "by_status": status_counts,
        "top_performers": top_5,
    }
