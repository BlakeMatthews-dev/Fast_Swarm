"""
Pattern Cull Service - Remove underperforming patterns.

This service handles culling the bottom X% of patterns based on fitness.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.pattern_models import Pattern


class PatternCullService:
    """Service for culling underperforming patterns."""

    async def cull_patterns(
        self,
        session: AsyncSession,
        cull_percentile: float = 0.3,
        min_population: int = 20,
    ) -> dict:
        """
        Cull the bottom X% of patterns by fitness.

        Args:
            session: Database session
            cull_percentile: Bottom X% to cull (0.3 = bottom 30%)
            min_population: Minimum population to maintain

        Returns:
            Dict with culled pattern IDs and stats
        """
        # Get all active patterns sorted by fitness
        result = await session.exec(
            select(Pattern).where(Pattern.is_active == True).order_by(desc(Pattern.fitness_score))
        )
        patterns = result.all()

        total_patterns = len(patterns)

        if total_patterns <= min_population:
            return {
                "culled_count": 0,
                "culled_ids": [],
                "remaining_count": total_patterns,
                "message": f"Population ({total_patterns}) at or below minimum ({min_population}), skipping cull",
            }

        # Calculate how many to cull
        cull_count = int(total_patterns * cull_percentile)
        cull_count = min(cull_count, total_patterns - min_population)

        if cull_count <= 0:
            return {
                "culled_count": 0,
                "culled_ids": [],
                "remaining_count": total_patterns,
                "message": "No patterns to cull",
            }

        # Get the bottom performers
        patterns_to_cull = patterns[-cull_count:]
        culled_ids = []

        for pattern in patterns_to_cull:
            pattern.is_active = False
            session.add(pattern)
            culled_ids.append(pattern.pattern_id)

        await session.commit()

        return {
            "culled_count": len(culled_ids),
            "culled_ids": culled_ids,
            "remaining_count": total_patterns - len(culled_ids),
            "cull_threshold_fitness": patterns_to_cull[0].fitness_score if patterns_to_cull else None,
        }
