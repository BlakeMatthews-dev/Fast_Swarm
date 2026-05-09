from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from ...Database import get_session
from ..Models.agent_models import Agent
from ..Services import agent_service

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[Agent])
async def read_agents(skip: int = 0, limit: int = 100, session: AsyncSession = Depends(get_session)):
    """
    Get all active agents.
    """
    return await agent_service.get_all_agents(session, limit=limit, offset=skip)


@router.get("/stats/average")
async def get_average_agent_stats(session: AsyncSession = Depends(get_session)):
    """
    Get average statistics and trait values for all active agents.
    """
    from ..Services import agent_stats_service

    return await agent_stats_service.get_agent_average_stats(session)


@router.get("/top-by-regime/{regime}")
async def get_top_agents_by_regime(regime: str, limit: int = 20, session: AsyncSession = Depends(get_session)):
    """
    Get top performing agents for a specific regime.

    Supported regimes:
    - Canonical: crash, bull, bear, sideways, blowoff, recovery, volatile, winter, transition
    - Random windows: random_1m, random_5m, random_15m, random_1h, random_4h, random_1d

    Returns agents sorted by fitness in that regime.
    """
    from sqlalchemy import text

    # Query agents with fitness data for this regime
    # Using raw SQL for JSONB query
    result = await session.execute(
        text("""
            SELECT agent_id, name, generation, fitness_score,
                   fitness_by_regime->:regime->>'fitness' as regime_fitness,
                   fitness_by_regime->:regime->>'trades' as regime_trades,
                   fitness_by_regime->:regime->>'win_rate' as regime_win_rate,
                   fitness_by_regime->:regime->>'sharpe' as regime_sharpe
            FROM agents
            WHERE is_active = true
              AND fitness_by_regime ? :regime
              AND (fitness_by_regime->:regime->>'fitness')::float > 0
            ORDER BY (fitness_by_regime->:regime->>'fitness')::float DESC
            LIMIT :limit
        """),
        {"regime": regime, "limit": limit},
    )
    rows = result.fetchall()

    if not rows:
        return {"regime": regime, "agents": [], "message": f"No agents with fitness data for regime '{regime}'"}

    return {
        "regime": regime,
        "count": len(rows),
        "agents": [
            {
                "agent_id": row[0],
                "name": row[1],
                "generation": row[2],
                "overall_fitness": row[3],
                "regime_fitness": float(row[4]) if row[4] else 0.0,
                "regime_trades": int(row[5]) if row[5] else 0,
                "regime_win_rate": float(row[6]) if row[6] else None,
                "regime_sharpe": float(row[7]) if row[7] else None,
            }
            for row in rows
        ],
    }


@router.get("/{agent_id}/fitness-by-regime")
async def get_agent_fitness_by_regime(agent_id: str, session: AsyncSession = Depends(get_session)):
    """
    Get per-regime fitness breakdown for a specific agent.

    Returns fitness scores across all tested regimes:
    - crash, bull, bear, sideways, blowoff, recovery (canonical periods)
    - random_1m, random_15m, random_1h, random_1d (random windows)
    """
    agent = await agent_service.get_agent_by_id(session, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    fitness_by_regime = agent.fitness_by_regime or {}

    # Sort by fitness descending
    sorted_regimes = sorted(
        fitness_by_regime.items(), key=lambda x: x[1].get("fitness", 0) if isinstance(x[1], dict) else 0, reverse=True
    )

    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "overall_fitness": agent.fitness_score,
        "regimes_tested": len(fitness_by_regime),
        "fitness_by_regime": dict(sorted_regimes),
        "best_regime": sorted_regimes[0][0] if sorted_regimes else None,
        "worst_regime": sorted_regimes[-1][0] if sorted_regimes else None,
    }


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, session: AsyncSession = Depends(get_session)):
    """
    Get a specific agent by ID.
    """
    agent = await agent_service.get_agent_by_id(session, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
