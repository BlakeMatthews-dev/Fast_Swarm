import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Models.crucible_models import CrucibleEntry, Wisdom
from ..Services.crucible_entry_service import CrucibleEntryService
from ..Services.crucible_test_service import CrucibleTestService
from ..Services.orchestrator import get_orchestrator
from ..Services.wisdom_service import WisdomTransferService

router = APIRouter(prefix="/system", tags=["System"])

# Services are initialized here or passed via dependency injection if preferred
# For simplicity with the existing structure, we can use the global instances where applicable
# or create new ones for stateless logic.
crucible_service = CrucibleEntryService()
crucible_test_service = CrucibleTestService()
wisdom_service = WisdomTransferService()


@router.post("/crucible/check/{agent_id}", response_model=Optional[CrucibleEntry])
async def check_agent_for_crucible(agent_id: str, session: AsyncSession = Depends(get_session)):
    """Check if an agent is eligible for the Crucible and create an entry if so."""
    return await crucible_service.check_and_create_entry(session, agent_id)


@router.post("/crucible/run/{entry_id}", tags=["Crucible"])
async def run_crucible_test(entry_id: int, session: AsyncSession = Depends(get_session)):
    """
    Run the Crucible walk-forward validation test for a pending entry.

    Tests the agent snapshot on all assets with $50k paper money,
    scoring overall fitness and per-regime performance.
    """
    return await crucible_test_service.run_crucible_test(session, entry_id)


@router.post("/crucible/run-pending", tags=["Crucible"])
async def run_all_pending_crucible_tests(session: AsyncSession = Depends(get_session)):
    """
    Run Crucible tests for all pending entries.

    Called automatically after evolution creates new entries,
    or manually to process any backlog.
    """
    from sqlmodel import select as sel

    result = await session.exec(
        sel(CrucibleEntry).where(CrucibleEntry.status == "pending")
    )
    pending = result.all()

    if not pending:
        return {"message": "No pending crucible entries", "tested": 0}

    results = []
    for entry in pending:
        test_result = await crucible_test_service.run_crucible_test(session, entry.id)
        results.append(test_result)

    return {
        "tested": len(results),
        "results": results,
    }


@router.get("/wisdom/latest", response_model=list[Wisdom])
async def get_latest_wisdom(limit: int = 5, session: AsyncSession = Depends(get_session)):
    """Get the latest distilled wisdom from the swarm."""
    return await wisdom_service.get_latest_wisdom(session, limit)


# =============================================================================
# Memory Endpoints
# =============================================================================


@router.get("/memory/{agent_id}", tags=["Memory"])
async def get_agent_memories(
    agent_id: str,
    limit: int = 50,
    memory_type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Get memories for a specific agent.

    Args:
        agent_id: Agent ID to get memories for
        limit: Maximum number of memories to return
        memory_type: Optional filter by type (observation, opinion, lesson, counterfactual, regret, affirmation)

    Returns:
        List of memory objects with content, type, weight, and metadata
    """
    from ...Agents.Services.memory_service import get_agent_memories as fetch_memories

    memories = await fetch_memories(session, agent_id, limit=limit)

    # Filter by type if specified
    if memory_type:
        memories = [m for m in memories if m.memory_type == memory_type]

    return [
        {
            "memory_id": m.memory_id,
            "agent_id": m.agent_id,
            "memory_type": m.memory_type,
            "content": m.content,
            "weight": m.weight,
            "confidence": m.confidence,
            "reinforcement_count": m.reinforcement_count,
            "contradiction_count": m.contradiction_count,
            "spawned_from": m.spawned_from,
            "created_at": m.created_at.isoformat(),
        }
        for m in memories
    ]


@router.get("/memory/{agent_id}/stats", tags=["Memory"])
async def get_agent_memory_stats(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Get memory statistics for an agent.

    Returns:
        - total: Total memory count
        - by_type: Breakdown by memory type
        - avg_weight: Average memory weight
        - weak_count: Memories with weight < 0.15 (need review)
        - inherited_count: Memories inherited from parents
    """
    from ...Agents.Services.memory_integration_service import get_agent_memory_stats as fetch_stats

    return await fetch_stats(session, agent_id)


@router.get("/memory/{agent_id}/weak", tags=["Memory"])
async def get_weak_memories(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Get weak memories for an agent that may need review or deletion.

    Weak memories have weight < 0.15 and may be:
    - Outdated observations
    - Contradicted lessons
    - Low-confidence opinions

    Returns:
        List of weak memories sorted by weight (lowest first)
    """
    from ...Agents.Services.memory_service import get_weak_memories as fetch_weak

    memories = await fetch_weak(session, agent_id)
    return [
        {
            "memory_id": m.memory_id,
            "memory_type": m.memory_type,
            "content": m.content,
            "weight": m.weight,
            "reinforcement_count": m.reinforcement_count,
            "contradiction_count": m.contradiction_count,
            "created_at": m.created_at.isoformat(),
        }
        for m in memories
    ]


@router.get("/crucible/leaderboard", tags=["Crucible"])
async def get_crucible_leaderboard(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """
    Get the Crucible leaderboard - top performing agents who completed Crucible.

    Returns agents ranked by overall fitness from Crucible tests, including
    their wisdom contributions and regime performance breakdown.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT
                ce.agent_id,
                ce.level_at_entry,
                ce.overall_fitness,
                ce.regime_scores,
                ce.completed_at,
                a.name as agent_name,
                a.generation,
                w.title as wisdom_title,
                w.id as wisdom_id
            FROM crucible_entries ce
            LEFT JOIN agents a ON ce.agent_id = a.agent_id
            LEFT JOIN wisdom w ON w.crucible_entry_id = ce.id
            WHERE ce.status = 'completed'
            ORDER BY ce.overall_fitness DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    rows = result.fetchall()

    return [
        {
            "rank": idx + 1,
            "agent_id": row[0],
            "agent_name": row[5],
            "level": row[1],
            "generation": row[6],
            "fitness": float(row[2]) if row[2] else 0,
            "regime_scores": row[3] or {},
            "completed_at": row[4].isoformat() if row[4] else None,
            "wisdom_title": row[7],
            "wisdom_id": row[8],
        }
        for idx, row in enumerate(rows)
    ]


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


@router.get("/orchestrator", tags=["Monitoring"])
async def get_orchestrator_status():
    """
    Get the current status of the backtest orchestrator.

    The orchestrator runs P2 operations (backtesting, evolution, pattern discovery)
    sequentially to prevent resource contention.

    Returns:
    - running: Whether the orchestrator is active
    - phase: Current phase (idle, loading_windows, testing_patterns, etc.)
    - windows_loaded: Number of windows in current batch
    - patterns_tested: Progress through pattern batch
    - agents_tested: Progress through agent batch
    - cycles_completed: Total pipeline cycles completed
    """
    orchestrator = get_orchestrator()
    return orchestrator.get_status()


@router.post("/orchestrator/start", tags=["Control"])
async def start_orchestrator():
    """Start the backtest orchestrator if not already running."""
    orchestrator = get_orchestrator()
    if orchestrator.is_running:
        return {"message": "Orchestrator already running", "status": orchestrator.get_status()}
    await orchestrator.start()
    return {"message": "Orchestrator started", "status": orchestrator.get_status()}


@router.post("/orchestrator/stop", tags=["Control"])
async def stop_orchestrator():
    """Stop the backtest orchestrator gracefully."""
    orchestrator = get_orchestrator()
    if not orchestrator.is_running:
        return {"message": "Orchestrator not running", "status": orchestrator.get_status()}
    await orchestrator.stop()
    return {"message": "Orchestrator stopped", "status": orchestrator.get_status()}


@router.get("/events", tags=["Monitoring"])
async def event_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time dashboard updates.

    Streams orchestrator status, system health, and key metrics every 2 seconds.
    Use this instead of polling for real-time updates.

    Example usage in JavaScript:
        const eventSource = new EventSource('/system/events');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log(data.type, data.data);
        };
    """
    async def generate():
        import math

        from ...Dependencies import stream_manager

        while True:
            try:
                # Orchestrator status
                orchestrator = get_orchestrator()
                orchestrator_status = orchestrator.get_status()

                yield f"data: {json.dumps({'type': 'orchestrator', 'data': orchestrator_status})}\n\n"

                # Stream health (every other iteration to reduce load)
                try:
                    streams_status = {}
                    for name, client in stream_manager.clients.items():
                        status = client.get_status()
                        secs = status.get("seconds_since_last_message", -1)
                        if not math.isfinite(secs):
                            secs = -1
                        streams_status[name] = {
                            "state": str(status.get("state", "unknown")),
                            "seconds_since_last_message": secs,
                        }
                    yield f"data: {json.dumps({'type': 'streams', 'data': streams_status})}\n\n"
                except Exception:
                    pass  # Stream status is optional

                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/metrics", tags=["Monitoring"])
async def prometheus_metrics(session: AsyncSession = Depends(get_session)):
    """
    Prometheus-compatible metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    Includes: agent counts, pattern counts, orchestrator state, backtest metrics.
    """
    from sqlalchemy import text

    metrics_lines = []

    # Orchestrator metrics
    orchestrator = get_orchestrator()
    status = orchestrator.get_status()

    metrics_lines.append("# HELP orchestrator_running Whether the orchestrator is running (1=yes, 0=no)")
    metrics_lines.append("# TYPE orchestrator_running gauge")
    metrics_lines.append(f"orchestrator_running {1 if status['running'] else 0}")

    metrics_lines.append("# HELP orchestrator_cycles_completed Total orchestrator cycles completed")
    metrics_lines.append("# TYPE orchestrator_cycles_completed counter")
    metrics_lines.append(f"orchestrator_cycles_completed {status['cycles_completed']}")

    metrics_lines.append("# HELP orchestrator_patterns_tested Patterns tested in current batch")
    metrics_lines.append("# TYPE orchestrator_patterns_tested gauge")
    metrics_lines.append(f"orchestrator_patterns_tested {status['patterns_tested']}")

    metrics_lines.append("# HELP orchestrator_agents_tested Agents tested in current batch")
    metrics_lines.append("# TYPE orchestrator_agents_tested gauge")
    metrics_lines.append(f"orchestrator_agents_tested {status['agents_tested']}")

    # Agent metrics
    agent_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE is_active = true) as active,
                COUNT(*) as total,
                COALESCE(AVG(fitness_score) FILTER (WHERE is_active = true), 0) as avg_fitness,
                COALESCE(MAX(fitness_score) FILTER (WHERE is_active = true), 0) as max_fitness
            FROM agents
        """)
    )
    agent_row = agent_result.fetchone()

    metrics_lines.append("# HELP agents_active_total Number of active agents")
    metrics_lines.append("# TYPE agents_active_total gauge")
    metrics_lines.append(f"agents_active_total {agent_row[0] if agent_row else 0}")

    metrics_lines.append("# HELP agents_total Total number of agents")
    metrics_lines.append("# TYPE agents_total gauge")
    metrics_lines.append(f"agents_total {agent_row[1] if agent_row else 0}")

    metrics_lines.append("# HELP agents_fitness_avg Average fitness score of active agents")
    metrics_lines.append("# TYPE agents_fitness_avg gauge")
    metrics_lines.append(f"agents_fitness_avg {float(agent_row[2]) if agent_row else 0:.4f}")

    metrics_lines.append("# HELP agents_fitness_max Maximum fitness score")
    metrics_lines.append("# TYPE agents_fitness_max gauge")
    metrics_lines.append(f"agents_fitness_max {float(agent_row[3]) if agent_row else 0:.4f}")

    # Pattern metrics
    pattern_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE is_active = true) as active,
                COUNT(*) as total,
                COALESCE(AVG(fitness_score) FILTER (WHERE is_active = true AND fitness_score IS NOT NULL), 0) as avg_fitness
            FROM patterns
        """)
    )
    pattern_row = pattern_result.fetchone()

    metrics_lines.append("# HELP patterns_active_total Number of active patterns")
    metrics_lines.append("# TYPE patterns_active_total gauge")
    metrics_lines.append(f"patterns_active_total {pattern_row[0] if pattern_row else 0}")

    metrics_lines.append("# HELP patterns_total Total number of patterns")
    metrics_lines.append("# TYPE patterns_total gauge")
    metrics_lines.append(f"patterns_total {pattern_row[1] if pattern_row else 0}")

    metrics_lines.append("# HELP patterns_fitness_avg Average fitness score of active patterns")
    metrics_lines.append("# TYPE patterns_fitness_avg gauge")
    metrics_lines.append(f"patterns_fitness_avg {float(pattern_row[2]) if pattern_row else 0:.4f}")

    # Trade metrics
    trade_result = await session.execute(
        text("""
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE is_winner = true) as winning_trades
            FROM backtest_trades_unified
        """)
    )
    trade_row = trade_result.fetchone()

    metrics_lines.append("# HELP backtest_trades_total Total backtest trades")
    metrics_lines.append("# TYPE backtest_trades_total counter")
    metrics_lines.append(f"backtest_trades_total {trade_row[0] if trade_row else 0}")

    metrics_lines.append("# HELP backtest_trades_winning Total winning trades")
    metrics_lines.append("# TYPE backtest_trades_winning counter")
    metrics_lines.append(f"backtest_trades_winning {trade_row[1] if trade_row else 0}")

    return Response(
        content="\n".join(metrics_lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )
