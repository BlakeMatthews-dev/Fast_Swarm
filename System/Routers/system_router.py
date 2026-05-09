from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Models.crucible_models import CrucibleEntry, Wisdom
from ..Services.crucible_entry_service import CrucibleEntryService
from ..Services.wisdom_service import WisdomTransferService

router = APIRouter(prefix="/system", tags=["System"])

# Services are initialized here or passed via dependency injection if preferred
# For simplicity with the existing structure, we can use the global instances where applicable
# or create new ones for stateless logic.
crucible_service = CrucibleEntryService()
wisdom_service = WisdomTransferService()


@router.post("/crucible/check/{agent_id}", response_model=Optional[CrucibleEntry])
async def check_agent_for_crucible(agent_id: str, session: AsyncSession = Depends(get_session)):
    """Check if an agent is eligible for the Crucible and create an entry if so."""
    return await crucible_service.check_and_create_entry(session, agent_id)


@router.get("/wisdom/latest", response_model=list[Wisdom])
async def get_latest_wisdom(limit: int = 5, session: AsyncSession = Depends(get_session)):
    """Get the latest distilled wisdom from the swarm."""
    return await wisdom_service.get_latest_wisdom(session, limit)


@router.get("/health", tags=["Infrastructure"])
async def get_system_health():
    """Get status of background collectors and streams."""
    # Get stream status - convert any non-serializable objects
    import math

    from ...Dependencies import robustness_service, stream_manager

    try:
        streams_status = {}
        for name, client in stream_manager.clients.items():
            status = client.get_status()
            # Handle infinity (not JSON-serializable)
            secs = status.get("seconds_since_last_message", -1)
            if not math.isfinite(secs):
                secs = -1  # Use -1 to indicate "never received"
            # Ensure all values are JSON serializable
            streams_status[name] = {
                "exchange": status.get("exchange", name),
                "state": str(status.get("state", "unknown")),
                "reconnect_count": status.get("reconnect_count", 0),
                "seconds_since_last_message": secs,
            }
    except Exception as e:
        streams_status = {"error": str(e)}

    return {
        "streams": streams_status,
        "robustness": {
            "is_running": robustness_service._running,
            "nightly_hours": list(robustness_service._nightly_hours),  # Convert range to list
        },
    }


@router.post("/robustness/trigger_chaos")
async def trigger_chaos_test():
    """Manually trigger a random chaos validation test."""
    from ...Dependencies import robustness_service

    if not robustness_service._test_registry:
        raise HTTPException(status_code=400, detail="No tests registered")

    import random

    test_func = random.choice(robustness_service._test_registry)
    await test_func()
    return {"message": f"Triggered {test_func.__name__}"}


@router.get("/progress", tags=["Monitoring"])
async def get_evolution_progress(session: AsyncSession = Depends(get_session)):
    """
    Get comprehensive evolution progress summary.

    Returns:
    - Windows tested (per agent and total)
    - Fitness distribution (avg, max, min, stddev)
    - Regime fitness breakdown
    - Pattern testing stats
    - Rate of change metrics
    """
    from sqlalchemy import text

    WINDOWS_PER_AGENT = 552  # 152 canonical + 400 random

    # Agent stats
    agent_stats = await session.execute(
        text("""
        SELECT
            COUNT(*) as total_agents,
            COUNT(*) FILTER (WHERE backtest_count > 0) as agents_tested,
            COALESCE(SUM(backtest_count), 0) as total_backtests,
            COALESCE(AVG(backtest_count), 0) as avg_backtests_per_agent,
            COALESCE(MAX(backtest_count), 0) as max_backtests,
            COALESCE(AVG(fitness_score), 0) as avg_fitness,
            COALESCE(MAX(fitness_score), 0) as max_fitness,
            COALESCE(MIN(fitness_score), 0) as min_fitness,
            COALESCE(STDDEV(fitness_score), 0) as fitness_stddev,
            COUNT(*) FILTER (WHERE fitness_score >= 50) as fitness_50_plus,
            COUNT(*) FILTER (WHERE fitness_score >= 70) as fitness_70_plus,
            COUNT(*) FILTER (WHERE fitness_score >= 90) as fitness_90_plus
        FROM agents
        WHERE is_active = true
    """)
    )
    agent_row = agent_stats.fetchone()

    # Regime fitness breakdown
    regime_stats = await session.execute(
        text("""
        SELECT
            regime,
            COUNT(*) as count,
            AVG(fitness) as avg_fitness,
            MAX(fitness) as max_fitness,
            MIN(fitness) as min_fitness
        FROM (
            SELECT
                key as regime,
                COALESCE((value->>'fitness')::float, (value::text)::float) as fitness
            FROM agents, jsonb_each(fitness_by_regime)
            WHERE is_active = true
              AND fitness_by_regime IS NOT NULL
              AND fitness_by_regime != '{}'::jsonb
              AND (value->>'fitness' IS NOT NULL OR jsonb_typeof(value) = 'number')
        ) sub
        WHERE fitness IS NOT NULL
        GROUP BY regime
        ORDER BY avg_fitness DESC
    """)
    )
    regime_rows = regime_stats.fetchall()

    # Pattern stats
    pattern_stats = await session.execute(
        text("""
        SELECT
            COUNT(*) as total_patterns,
            COUNT(*) FILTER (WHERE periods_tested > 0) as patterns_tested,
            COALESCE(SUM(periods_tested), 0) as total_tests,
            COALESCE(AVG(fitness_score), 0) as avg_fitness,
            COALESCE(MAX(fitness_score), 0) as max_fitness,
            COUNT(*) FILTER (WHERE fitness_score >= 50) as fitness_50_plus,
            COUNT(*) FILTER (WHERE fitness_score >= 70) as fitness_70_plus
        FROM patterns
        WHERE is_active = true
    """)
    )
    pattern_row = pattern_stats.fetchone()

    # Evolution cycles
    evo_stats = await session.execute(
        text("""
        SELECT
            COUNT(*) as total_cycles,
            MAX(cycle_number) as latest_generation,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_secs
        FROM evolution_cycles
        WHERE completed_at IS NOT NULL
    """)
    )
    evo_row = evo_stats.fetchone()

    agents_tested = agent_row[1] if agent_row else 0
    total_windows = agents_tested * WINDOWS_PER_AGENT

    return {
        "windows": {
            "windows_per_agent": WINDOWS_PER_AGENT,
            "agents_tested": agents_tested,
            "total_windows_tested": total_windows,
            "canonical_periods": 152,
            "random_windows": 400,
        },
        "agents": {
            "total_active": agent_row[0] if agent_row else 0,
            "tested": agents_tested,
            "total_backtests": int(agent_row[2]) if agent_row else 0,
            "avg_backtests_per_agent": round(float(agent_row[3]), 1) if agent_row else 0,
            "max_backtests": int(agent_row[4]) if agent_row else 0,
        },
        "fitness": {
            "avg": round(float(agent_row[5]), 2) if agent_row else 0,
            "max": round(float(agent_row[6]), 2) if agent_row else 0,
            "min": round(float(agent_row[7]), 2) if agent_row else 0,
            "stddev": round(float(agent_row[8]), 2) if agent_row else 0,
            "agents_50_plus": agent_row[9] if agent_row else 0,
            "agents_70_plus": agent_row[10] if agent_row else 0,
            "agents_90_plus": agent_row[11] if agent_row else 0,
        },
        "regime_fitness": {
            row[0]: {
                "count": row[1],
                "avg": round(float(row[2]), 2),
                "max": round(float(row[3]), 2),
                "min": round(float(row[4]), 2),
            }
            for row in regime_rows
        }
        if regime_rows
        else {},
        "patterns": {
            "total": pattern_row[0] if pattern_row else 0,
            "tested": pattern_row[1] if pattern_row else 0,
            "total_tests": int(pattern_row[2]) if pattern_row else 0,
            "avg_fitness": round(float(pattern_row[3]), 2) if pattern_row else 0,
            "max_fitness": round(float(pattern_row[4]), 2) if pattern_row else 0,
            "patterns_50_plus": pattern_row[5] if pattern_row else 0,
            "patterns_70_plus": pattern_row[6] if pattern_row else 0,
        },
        "evolution": {
            "cycles_completed": evo_row[0] if evo_row else 0,
            "latest_generation": evo_row[1] if evo_row and evo_row[1] else 0,
            "avg_cycle_duration_secs": round(float(evo_row[2]), 1) if evo_row and evo_row[2] else 0,
        },
    }
