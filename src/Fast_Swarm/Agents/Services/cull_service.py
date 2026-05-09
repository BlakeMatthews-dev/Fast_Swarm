"""
Agent Cull Service - Remove underperforming agents.

This service handles culling the bottom X% of agents based on fitness.

SPECIALIST PROTECTION:
Culling uses BEST regime fitness (not aggregate) so that specialists
who excel in one regime but struggle in others are not unfairly penalized.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.agent_models import Agent


def get_best_regime_fitness(agent: Agent) -> float:
    """
    Get the best regime fitness for an agent.

    Uses fitness_by_regime if available, otherwise falls back to fitness_score.
    This protects specialists who excel in specific regimes.

    Args:
        agent: The agent to evaluate

    Returns:
        Best regime fitness score (or aggregate if no regime data)
    """
    regime_fitness = agent.fitness_by_regime or {}

    if regime_fitness:
        # Filter out None values and get the max
        valid_scores = [v for v in regime_fitness.values() if v is not None and isinstance(v, (int, float))]
        if valid_scores:
            return max(valid_scores)

    # Fall back to aggregate fitness_score
    return float(agent.fitness_score or 0)


def get_cull_score(agent: Agent) -> float:
    """
    Combined cull score: in-sample fitness weighted by OOS performance.

    Agents with high in-sample but low OOS fitness get penalized — they're
    likely overfit. OOS fitness stored in agent.traits['oos_fitness_score']
    by the evolution cycle's Phase 1b.

    Formula: base_fitness * oos_multiplier
    - No OOS data: multiplier = 1.0 (neutral)
    - OOS > 30: multiplier = 1.0-1.5 (bonus for generalizing)
    - OOS < 15: multiplier = 0.3-0.7 (penalty for overfitting)
    """
    base = get_best_regime_fitness(agent)
    traits = agent.traits or {}
    oos = traits.get("oos_fitness_score")

    if oos is None:
        return base  # No OOS data yet, use base fitness

    # OOS multiplier: linear scale from 0.3 (oos=0) to 1.5 (oos=60+)
    oos_mult = min(1.5, max(0.3, 0.3 + (float(oos) / 60.0) * 1.2))
    return base * oos_mult


class AgentCullService:
    """Service for culling underperforming agents."""

    # Minimum backtests required before an agent can be culled
    MIN_BACKTESTS_FOR_CULL = 3  # Must have at least 3 backtests to be evaluated
    MIN_POPULATION = 150  # Never cull below this population

    async def cull_agents(
        self,
        session: AsyncSession,
        cull_percentile: float = 0.3,
        min_population: int = None,
        min_backtests: int = None,
    ) -> dict:
        """
        Cull the bottom X% of agents by fitness.

        PROTECTION: Agents with fewer than min_backtests are protected from culling.
        This ensures agents are properly evaluated before being removed.

        Args:
            session: Database session
            cull_percentile: Bottom X% to cull (0.3 = bottom 30%)
            min_population: Minimum population to maintain
            min_backtests: Minimum backtests required (default: MIN_BACKTESTS_FOR_CULL)

        Returns:
            Dict with culled agent IDs and stats
        """
        if min_backtests is None:
            min_backtests = self.MIN_BACKTESTS_FOR_CULL
        if min_population is None:
            min_population = self.MIN_POPULATION

        # Get all active agents sorted by fitness
        result = await session.execute(
            select(Agent).where(Agent.status == "active").order_by(desc(Agent.fitness_score))
        )
        agents = result.scalars().all()

        # Split into evaluated (can be culled) and protected (not enough backtests)
        evaluated_agents = []
        protected_agents = []
        for agent in agents:
            backtest_count = agent.backtest_count or 0
            if backtest_count >= min_backtests:
                evaluated_agents.append(agent)
            else:
                protected_agents.append(agent)

        if protected_agents:
            print(f"[Cull] Protected {len(protected_agents)} agents with <{min_backtests} backtests from culling")

        total_agents = len(agents)
        total_evaluated = len(evaluated_agents)

        if total_agents <= min_population:
            return {
                "culled_count": 0,
                "culled_ids": [],
                "remaining_count": total_agents,
                "protected_count": len(protected_agents),
                "message": f"Population ({total_agents}) at or below minimum ({min_population}), skipping cull",
            }

        if total_evaluated == 0:
            return {
                "culled_count": 0,
                "culled_ids": [],
                "remaining_count": total_agents,
                "protected_count": len(protected_agents),
                "message": f"No agents with {min_backtests}+ backtests to evaluate for culling",
            }

        # Calculate how many to cull (from EVALUATED agents only)
        cull_count = int(total_evaluated * cull_percentile)
        # Ensure we don't go below min_population (counting protected agents)
        max_cull = total_agents - min_population
        cull_count = min(cull_count, max_cull)

        if cull_count <= 0:
            return {
                "culled_count": 0,
                "culled_ids": [],
                "remaining_count": total_agents,
                "protected_count": len(protected_agents),
                "message": "No agents to cull",
            }

        # Get the bottom performers FROM EVALUATED AGENTS ONLY
        # Sort by CULL SCORE: regime fitness × OOS multiplier
        # Protects specialists AND penalizes overfit agents
        evaluated_agents.sort(key=lambda a: get_cull_score(a))
        agents_to_cull = evaluated_agents[:cull_count]

        # Log OOS-aware culling
        if agents_to_cull:
            sample = agents_to_cull[0]
            oos = (sample.traits or {}).get("oos_fitness_score", "N/A")
            print(
                f"[Cull] OOS-aware culling. Sample: {sample.name} "
                f"aggregate={float(sample.fitness_score or 0):.1f}, "
                f"best_regime={get_best_regime_fitness(sample):.1f}, "
                f"oos={oos}, cull_score={get_cull_score(sample):.1f}"
            )
        culled_ids = []

        for agent in agents_to_cull:
            agent.status = "culled"  # Event listener auto-syncs is_active=False
            session.add(agent)
            culled_ids.append(agent.agent_id)

        await session.commit()

        return {
            "culled_count": len(culled_ids),
            "culled_ids": culled_ids,
            "remaining_count": total_agents - len(culled_ids),
            "cull_threshold_fitness": agents_to_cull[0].fitness_score if agents_to_cull else None,
        }

    async def cull_specific_agents(
        self,
        session: AsyncSession,
        agent_ids: list[str],
    ) -> dict:
        """
        Cull specific agents by ID.

        Args:
            session: Database session
            agent_ids: List of agent IDs to cull

        Returns:
            Dict with culled agent IDs
        """
        result = await session.execute(select(Agent).where(Agent.agent_id.in_(agent_ids)))
        agents = result.scalars().all()

        culled_ids = []
        for agent in agents:
            agent.status = "culled"  # Event listener auto-syncs is_active=False
            session.add(agent)
            culled_ids.append(agent.agent_id)

        await session.commit()

        return {
            "culled_count": len(culled_ids),
            "culled_ids": culled_ids,
        }
