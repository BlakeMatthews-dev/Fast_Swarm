import asyncio
from typing import Union

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Models.agent_models import (
    Agent,
    BacktestStatusResponse,
    CullAgentsResponse,
    CullDryRunResponse,
    SpawnAgentsResponse,
)
from ..Services import action_service

router = APIRouter(prefix="/actions", tags=["Agent Actions"])


@router.post("/spawn", response_model=SpawnAgentsResponse)
async def spawn_agents(count: int = 10) -> SpawnAgentsResponse:
    """
    Spawn new trading agents with AI-powered pattern selection.

    AI pattern selection is REQUIRED - agents receive personalized pattern
    portfolios based on their unique personality traits via Ollama LLM.

    Args:
        count: Number of agents to spawn (default: 10).

    Raises:
        HTTPException 503: If Ollama is not available (AI is required)
    """
    result = await action_service.spawn_agents(count)
    return SpawnAgentsResponse(**result)


@router.post("/spawn/exit-comparison")
async def spawn_exit_strategy_comparison():
    """
    Spawn 7 agents - one per exit strategy - with identical traits and patterns.

    Perfect for A/B testing exit strategies:
    - dynamic_trail: Logarithmic trailing (2%→12%)
    - atr_trail: ATR-based trailing (volatility adaptive)
    - scaled_out: 25% exit at each milestone
    - breakeven_trail: Move to breakeven after +5%
    - trailing_2pct/3pct/5pct: Fixed trailing stops

    All agents share the same traits, patterns, and entry conditions.
    Only exit strategy differs - run backtest to compare performance!
    """
    return await action_service.spawn_exit_strategy_comparison()


@router.post("/cull", response_model=Union[CullDryRunResponse, CullAgentsResponse])
async def cull_agents(
    survival_rate: float = 0.6, dry_run: bool = False, session: AsyncSession = Depends(get_session)
) -> CullDryRunResponse | CullAgentsResponse:
    """
    Cull the bottom percentage of agents based on fitness.

    Args:
        survival_rate: Fraction of agents to keep (default: 0.6 = keep top 60%)
        dry_run: If True, show what would be culled without actually culling
    """
    if dry_run:
        from sqlmodel import select

        statement = select(Agent).where(Agent.status == "active")
        result = await session.scalars(statement)
        agents = list(result.all())
        agents.sort(key=lambda a: a.fitness_score or -1.0, reverse=True)
        total = len(agents)
        survivors_count = int(total * survival_rate)
        to_cull = agents[survivors_count:]
        return CullDryRunResponse(
            would_cull=len(to_cull),
            would_survive=survivors_count,
            bottom_agents=[
                {"name": a.name, "fitness": float(a.fitness_score) if a.fitness_score else 0} for a in to_cull[:10]
            ],
        )
    result = await action_service.cull_agents(session, survival_rate)
    return CullAgentsResponse(**result)


@router.post("/backtest")
async def trigger_backtest(
    background_tasks: BackgroundTasks,
    agent_ids: list[str] | None = Body(default=None, description="List of agent IDs to backtest"),
    limit: int = None,
    sync: bool = False,
):
    """
    Run FULL backtest (random windows + canonical periods) on agents.

    This is the standard backtest that tests agents across:
    - Random windows: 640+ windows across 1m, 5m, 15m, 1h, 4h, 1d timeframes
    - Canonical periods: Historical events (FTX collapse, COVID crash, 2017 bull, etc.)

    For targeted testing, use:
    - POST /actions/backtest/canonical - Only canonical periods
    - POST /actions/backtest/random - Only random windows

    Args:
        agent_ids: Specific agent IDs to test (None = all active agents).
        limit: Max number of agents to backtest (None = all)
        sync: If True, run synchronously (blocking). If False, run in background.
    """
    # Filter out invalid agent IDs
    if agent_ids:
        agent_ids = [aid for aid in agent_ids if aid and aid != "string" and len(aid) > 5]
        if not agent_ids:
            agent_ids = None

    try:
        if sync:
            result = await asyncio.to_thread(action_service.perform_backtest_sync, agent_ids, limit)
            return result
        else:
            start_func = lambda: action_service.perform_backtest_sync(agent_ids, limit)
            background_tasks.add_task(start_func)
            return {"message": "Full backtest started in background", "check_status": "/actions/backtest/status"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e!s}")


@router.post("/backtest/canonical")
async def trigger_backtest_canonical(
    background_tasks: BackgroundTasks,
    agent_ids: list[str] | None = Body(default=None),
    regimes: list[str] | None = Body(
        default=None, description="Specific regimes to test: crash, bull, bear, sideways, etc."
    ),
    limit: int = None,
    sync: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """
    Run backtest on CANONICAL PERIODS ONLY (historical market events).

    Tests agents against known historical periods:
    - crash: COVID crash (Mar 2020), FTX collapse (Nov 2022), Luna crash (May 2022)
    - bull: 2017 bull run, 2020-2021 bull
    - bear: 2018 bear, 2022 bear
    - blowoff: Parabolic tops
    - recovery: Post-crash bounces
    - sideways: Consolidation periods

    Use this for regime-specific fitness analysis without random window noise.

    Args:
        agent_ids: Specific agent IDs to test (None = all active)
        regimes: Specific regimes to test (None = all canonical regimes)
        limit: Max agents to backtest
        sync: If True, run synchronously
    """
    if agent_ids:
        agent_ids = [aid for aid in agent_ids if aid and aid != "string" and len(aid) > 5]
        if not agent_ids:
            agent_ids = None

    try:
        if sync:
            result = await asyncio.to_thread(action_service.perform_backtest_canonical_sync, agent_ids, regimes, limit)
            return result
        else:
            start_func = lambda: action_service.perform_backtest_canonical_sync(agent_ids, regimes, limit)
            background_tasks.add_task(start_func)
            return {
                "message": "Canonical backtest started in background",
                "regimes": regimes or "all",
                "check_status": "/actions/backtest/status",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canonical backtest failed: {e!s}")


@router.post("/backtest/random")
async def trigger_backtest_random(
    background_tasks: BackgroundTasks,
    agent_ids: list[str] | None = Body(default=None),
    timeframes: list[str] | None = Body(default=None, description="Timeframes: 1m, 5m, 15m, 1h, 4h, 1d"),
    windows_per_asset: int = Body(default=20, description="Random windows per asset per timeframe"),
    limit: int = None,
    sync: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """
    Run backtest on RANDOM WINDOWS ONLY (diverse market conditions).

    Generates random time windows across multiple timeframes for comprehensive testing:
    - 1m: 1440 candles (~1 day)
    - 5m: 576 candles (~2 days)
    - 15m: 384 candles (~4 days)
    - 1h: 500 candles (~21 days)
    - 4h: 180 candles (~30 days)
    - 1d: 90 candles (~90 days)

    With 8 assets × 4 timeframes × 20 windows = 640+ windows per agent.

    Args:
        agent_ids: Specific agent IDs to test (None = all active)
        timeframes: Specific timeframes (None = all: 1m, 5m, 15m, 1h, 1d)
        windows_per_asset: Number of random windows per asset per timeframe
        limit: Max agents to backtest
        sync: If True, run synchronously
    """
    if agent_ids:
        agent_ids = [aid for aid in agent_ids if aid and aid != "string" and len(aid) > 5]
        if not agent_ids:
            agent_ids = None

    try:
        if sync:
            result = await asyncio.to_thread(
                action_service.perform_backtest_random_sync, agent_ids, timeframes, windows_per_asset, limit
            )
            return result
        else:
            start_func = lambda: action_service.perform_backtest_random_sync(
                agent_ids, timeframes, windows_per_asset, limit
            )
            background_tasks.add_task(start_func)
            return {
                "message": "Random window backtest started in background",
                "timeframes": timeframes or "all",
                "windows_per_asset": windows_per_asset,
                "check_status": "/actions/backtest/status",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Random backtest failed: {e!s}")


@router.get("/backtest/status", response_model=BacktestStatusResponse)
async def get_backtest_status() -> BacktestStatusResponse:
    """
    Get current backtest progress.
    """
    result = action_service.get_backtest_status()
    return BacktestStatusResponse(**result)
