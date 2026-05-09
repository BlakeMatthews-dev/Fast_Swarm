from fastapi import APIRouter, BackgroundTasks

from ..Models.agent_models import EvolutionRunRequest
from ..Services import evolution_service

router = APIRouter(prefix="/evolution", tags=["Evolution"])


@router.post("/start")
async def start_evolution(request: EvolutionRunRequest, background_tasks: BackgroundTasks):
    """
    Trigger a new evolution run in the background.
    """
    return await evolution_service.trigger_evolution(background_tasks, request)


@router.get("/status")
async def get_evolution_status():
    """
    Get current evolution run status.

    Returns whether an evolution is running and the last result.
    """
    return evolution_service.get_evolution_status()
