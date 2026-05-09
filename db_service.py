"""
Centralized Database Service for Fast_Swarm.

All database access should go through this service to ensure:
- Consistent async patterns (no sync psycopg2)
- Type-safe SQLModel queries
- Single source of truth for DB operations
- Easy mocking for tests
"""

from typing import Any

from sqlmodel import desc, select

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Patterns.Models.pattern_models import Pattern


def _fitness_to_tier(fitness: float) -> int:
    """
    Compute tier from fitness score.
    Evolution discovers thresholds - we just classify.

    Tier 1 (Elite): fitness >= 80
    Tier 2 (Proven): fitness >= 40
    Tier 3 (Untested/Dying): fitness < 40
    """
    if fitness >= 80:
        return 1
    if fitness >= 40:
        return 2
    return 3


class DatabaseService:
    """Centralized database access for Fast_Swarm."""

    @staticmethod
    async def get_active_patterns(
        limit: int = 10000,
        min_fitness: float = 0.0,
        min_trades: int = 5,  # Require at least 5 trades (will increase as backtests run)
        require_exit_conditions: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Load active patterns for agent spawning.

        Returns lightweight dicts (not full ORM objects) for compatibility
        with local_agents genesis code.

        Args:
            limit: Max patterns to return.
            min_fitness: Minimum fitness score.
            min_trades: Minimum number of trades (default 100 for proven patterns).
            require_exit_conditions: Only return patterns with valid exit conditions.
        """
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        async with async_session_maker() as session:
            statement = (
                select(Pattern)
                .where(Pattern.is_active == True)
                .where(Pattern.entry_conditions.isnot(None))
                .where(Pattern.total_runs >= min_trades)  # Only proven patterns!
                .where(Pattern.fitness_score >= min_fitness)
            )

            # Filter for patterns with VALID exit conditions (not empty {} or [])
            if require_exit_conditions:
                # exit_conditions must exist and not be empty
                statement = (
                    statement.where(Pattern.exit_conditions.isnot(None))
                    .where(cast(Pattern.exit_conditions, JSONB) != cast("[]", JSONB))
                    .where(cast(Pattern.exit_conditions, JSONB) != cast("{}", JSONB))
                )

            statement = statement.order_by(desc(Pattern.fitness_score)).limit(limit)
            result = (
                await session.run_sync(lambda s: s.scalars(statement).all())
                if hasattr(session, "run_sync")
                else await session.exec(statement)
            )
            patterns = result if isinstance(result, list) else result.all()

            print(f"[DatabaseService] Loaded {len(patterns)} active patterns")

            return [
                {
                    "pattern_id": p.pattern_id,
                    "name": p.name,
                    "fitness_score": p.fitness_score or 0,
                    "tier": _fitness_to_tier(p.fitness_score or 0),
                    "entry_conditions": p.entry_conditions or [],
                    "exit_conditions": p.exit_conditions or {},
                    # Full stats for LLM pattern selection
                    "win_rate_pct": (p.win_rate or 0.5) * 100,  # Convert 0-1 to %
                    "sharpe_ratio": p.sharpe_ratio or 0,
                    "total_roi_pct": p.total_roi_pct or 0,
                    "max_drawdown_pct": p.max_drawdown_pct or 0,
                    "profit_factor": p.profit_factor or 1.0,
                    "number_of_runs": p.total_runs or 0,
                    "description": p.description or "",
                    "timeframe": p.timeframe or "1h",
                    "symbol": p.symbol or "BTC",
                }
                for p in patterns
            ]

    @staticmethod
    async def get_pattern_by_id(pattern_id: str) -> Pattern | None:
        """Get single pattern by ID."""
        async with async_session_maker() as session:
            statement = select(Pattern).where(Pattern.pattern_id == pattern_id)
            result = await session.scalars(statement)
            return result.first()

    @staticmethod
    async def get_patterns_by_ids(pattern_ids: list[str]) -> list[Pattern]:
        """Get multiple patterns by IDs."""
        async with async_session_maker() as session:
            statement = select(Pattern).where(Pattern.pattern_id.in_(pattern_ids))
            result = await session.scalars(statement)
            return list(result.all())

    @staticmethod
    async def get_top_patterns(limit: int = 100) -> list[Pattern]:
        """Get top patterns by fitness score."""
        async with async_session_maker() as session:
            statement = (
                select(Pattern).where(Pattern.is_active == True).order_by(desc(Pattern.fitness_score)).limit(limit)
            )
            result = await session.scalars(statement)
            return list(result.all())


# Singleton instance for convenience
db = DatabaseService()
