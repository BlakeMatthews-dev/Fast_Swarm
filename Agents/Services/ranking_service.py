"""
Agent Ranking Service - Calculate fitness and rank agents.

This service handles fitness calculation and ranking of agents.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, func, select

from ..Models.agent_models import Agent


class AgentRankingService:
    """Service for ranking agents by fitness."""

    async def rank_agents(
        self,
        session: AsyncSession,
        agent_ids: list[str] | None = None,
    ) -> list[dict]:
        """
        Rank agents by fitness score.

        Args:
            session: Database session
            agent_ids: Optional list of specific agent IDs to rank (default: all active)

        Returns:
            List of agents with rankings
        """
        # Build query
        query = select(Agent).where(Agent.status == "active")

        if agent_ids:
            query = query.where(Agent.agent_id.in_(agent_ids))

        query = query.order_by(desc(Agent.fitness_score).nulls_last())

        result = await session.exec(query)
        agents = result.all()

        # Build ranked list
        ranked = []
        for rank, agent in enumerate(agents, start=1):
            ranked.append(
                {
                    "rank": rank,
                    "agent_id": agent.agent_id,
                    "fitness_score": agent.fitness_score,
                    "sharpe_ratio": agent.sharpe_ratio,
                    "win_rate": agent.win_rate,
                    "total_trades": agent.total_trades,
                    "generation": agent.generation,
                }
            )

        return ranked

    async def get_all_agents_ranked(
        self,
        session: AsyncSession,
    ) -> list[Agent]:
        """
        Get all active agents ranked by fitness score (descending).

        Used by evolution cycle to select breeders, clones, and survivors.

        Args:
            session: Database session

        Returns:
            List of all active agents, sorted by fitness (best first)
        """
        query = select(Agent).where(Agent.status == "active").order_by(desc(Agent.fitness_score))
        result = await session.execute(query)
        return result.scalars().all()

    async def get_top_agents(
        self,
        session: AsyncSession,
        top_n: int = 10,
        top_percentile: float | None = None,
    ) -> list[Agent]:
        """
        Get top performing agents using SQL LIMIT.

        Args:
            session: Database session
            top_n: Number of top agents to return (if top_percentile not set)
            top_percentile: Top X% to return (overrides top_n)

        Returns:
            List of top agents
        """
        # Determine limit: either fixed count or percentile-based
        if top_percentile:
            # Get total count first (cheap aggregate query)
            count_result = await session.exec(select(func.count(Agent.id)).where(Agent.status == "active"))
            total = count_result.one()
            limit = max(1, int(total * top_percentile))
        else:
            limit = top_n

        # Fetch only what we need with SQL LIMIT
        result = await session.exec(
            select(Agent).where(Agent.status == "active").order_by(desc(Agent.fitness_score).nulls_last()).limit(limit)
        )
        return list(result.all())

    async def get_bottom_agents(
        self,
        session: AsyncSession,
        bottom_n: int = 10,
        bottom_percentile: float | None = None,
    ) -> list[Agent]:
        """
        Get bottom performing agents using SQL LIMIT.

        Args:
            session: Database session
            bottom_n: Number of bottom agents to return (if bottom_percentile not set)
            bottom_percentile: Bottom X% to return (overrides bottom_n)

        Returns:
            List of bottom agents
        """
        # Determine limit: either fixed count or percentile-based
        if bottom_percentile:
            count_result = await session.exec(select(func.count(Agent.id)).where(Agent.status == "active"))
            total = count_result.one()
            limit = max(1, int(total * bottom_percentile))
        else:
            limit = bottom_n

        # Fetch only what we need with SQL LIMIT (ascending for bottom)
        result = await session.exec(
            select(Agent).where(Agent.status == "active").order_by(Agent.fitness_score.nulls_last()).limit(limit)
        )
        return list(result.all())

    async def calculate_population_stats(
        self,
        session: AsyncSession,
    ) -> dict:
        """
        Calculate population-wide statistics using SQL aggregation.

        Returns:
            Dict with population stats
        """
        # Single SQL query for all aggregates
        result = await session.exec(
            select(
                func.count(Agent.id).label("total"),
                func.avg(Agent.fitness_score).label("avg_fitness"),
                func.max(Agent.fitness_score).label("max_fitness"),
                func.min(Agent.fitness_score).label("min_fitness"),
                func.avg(Agent.generation).label("avg_generation"),
                func.max(Agent.generation).label("max_generation"),
            ).where(Agent.status == "active")
        )
        row = result.one()

        if not row.total:
            return {
                "total_agents": 0,
                "avg_fitness": 0,
                "max_fitness": 0,
                "min_fitness": 0,
                "avg_generation": 0,
            }

        # Median requires a separate query (percentile_cont in PostgreSQL)
        from sqlmodel import text

        median_result = await session.execute(
            text("""
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY fitness_score)
                FROM agents WHERE status = 'active' AND fitness_score IS NOT NULL
            """)
        )
        median_fitness = median_result.scalar() or 0

        return {
            "total_agents": row.total,
            "avg_fitness": round(float(row.avg_fitness or 0), 4),
            "max_fitness": float(row.max_fitness or 0),
            "min_fitness": float(row.min_fitness or 0),
            "median_fitness": round(float(median_fitness), 4),
            "avg_generation": round(float(row.avg_generation or 0), 2),
            "max_generation": int(row.max_generation or 0),
        }
