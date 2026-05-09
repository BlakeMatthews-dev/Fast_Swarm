"""
Taskmaster Router - API endpoints for system monitoring and interventions.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from Fast_Swarm.System.Services.taskmaster_service import get_taskmaster
from Fast_Swarm.Infrastructure.Services.bear_protection_service import get_bear_protection

router = APIRouter(prefix="/taskmaster", tags=["Taskmaster"])


@router.get("/health")
async def get_health():
    """
    Get overall system health status.

    Returns aggregated health across all monitored components.
    """
    taskmaster = get_taskmaster()
    health_report = await taskmaster.check_system_health()
    return health_report


@router.get("/components")
async def get_components():
    """
    Get status of all monitored components.

    Returns detailed status for each component including:
    - Current status (healthy/degraded/stalled/failed)
    - Last activity time
    - Metadata (phase, cycles, etc.)
    """
    taskmaster = get_taskmaster()
    health_report = await taskmaster.check_system_health()
    return health_report["components"]


@router.post("/poke/{component_id}")
async def poke_component(component_id: str):
    """
    Manually poke a stalled component.

    Used to send a wake-up signal to a component that appears stuck.
    """
    taskmaster = get_taskmaster()
    success = await taskmaster.poke_stalled_component(component_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found")

    return {
        "status": "success",
        "component_id": component_id,
        "message": "Poke sent"
    }


@router.post("/force/evolution")
async def force_evolution():
    """
    Manually trigger an evolution cycle.

    Bypasses the normal orchestrator schedule to immediately run evolution.
    """
    taskmaster = get_taskmaster()
    result = await taskmaster.force_evolution_cycle()

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.post("/force/crucible")
async def force_crucible():
    """
    Manually trigger Crucible eligibility check.

    Checks for agents ready to retire and clone-and-retire if eligible.
    """
    taskmaster = get_taskmaster()
    result = await taskmaster.force_crucible_check()

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/activity")
async def get_activity(limit: int = 20):
    """
    Get recent activity log.

    Args:
        limit: Number of entries to return (default 20)

    Returns recent Taskmaster activity including pokes, checks, and interventions.
    """
    taskmaster = get_taskmaster()
    activity = taskmaster.get_activity_summary(limit=limit)
    return {
        "activity": activity,
        "total": len(activity)
    }


@router.get("/alerts")
async def get_alerts():
    """
    Get active alerts (warnings and errors).

    Returns only warning/error/critical activity entries.
    """
    taskmaster = get_taskmaster()
    alerts = taskmaster.get_alerts()
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.get("/dashboard")
async def serve_dashboard():
    """
    Serve the Taskmaster dashboard HTML page.

    Simple vanilla JS dashboard with auto-refresh showing:
    - Overall system health
    - Component statuses
    - Recent activity log
    - Manual intervention buttons
    """
    dashboard_path = Path(__file__).parent.parent / "static" / "taskmaster_dashboard.html"

    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")

    return FileResponse(dashboard_path)
