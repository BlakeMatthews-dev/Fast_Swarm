"""
Pattern Cull Service - Remove underperforming patterns.

This service handles:
- Culling the bottom X% of patterns based on fitness
- Detecting pattern decay (alpha erosion over time)
"""

from datetime import datetime, timedelta

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
            select(Pattern).where(Pattern.is_active.is_(True)).order_by(desc(Pattern.fitness_score))
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

    async def detect_decay(
        self,
        session: AsyncSession,
        fitness_drop_threshold: float = 20.0,
    ) -> dict:
        """
        Detect patterns with declining fitness (alpha erosion).

        Compares current fitness to peak fitness. Patterns that dropped
        more than threshold get flagged and demoted to Tier 3.

        Args:
            session: Database session
            fitness_drop_threshold: Minimum fitness drop to flag (default: 20 points)

        Returns:
            Dict with decaying pattern IDs and stats
        """
        result = await session.exec(
            select(Pattern).where(Pattern.is_active.is_(True))
        )
        patterns = result.all()

        decaying = []
        for pattern in patterns:
            current = float(pattern.fitness_score or 0)
            # Check fitness_by_regime for historical peak
            regime_scores = pattern.fitness_by_regime or {}
            if regime_scores:
                peak = max(
                    (float(v) for v in regime_scores.values() if v is not None and isinstance(v, (int, float))),
                    default=current,
                )
            else:
                peak = current

            # Also check if total_runs is high but fitness is low (used to be good)
            runs = pattern.total_runs or 0
            if runs > 20 and current < 15:
                # Pattern has been tested extensively but scores poorly now
                pattern.tier = 3  # Demote
                session.add(pattern)
                decaying.append({
                    "pattern_id": pattern.pattern_id,
                    "name": pattern.name,
                    "fitness": current,
                    "runs": runs,
                    "reason": "low_fitness_after_many_runs",
                })
            elif peak - current >= fitness_drop_threshold and runs > 10:
                pattern.tier = 3  # Demote
                session.add(pattern)
                decaying.append({
                    "pattern_id": pattern.pattern_id,
                    "name": pattern.name,
                    "fitness": current,
                    "peak": peak,
                    "drop": peak - current,
                    "reason": "fitness_decay",
                })

        if decaying:
            await session.commit()
            print(f"[PatternDecay] Flagged {len(decaying)} decaying patterns")

        return {
            "decaying_count": len(decaying),
            "patterns": decaying[:10],  # Sample
        }
