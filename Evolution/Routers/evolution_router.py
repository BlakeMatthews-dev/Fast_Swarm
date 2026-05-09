from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Models.evolution_models import EvolutionCycle, EvolutionEvent
from ..Services import evolution_monitor

router = APIRouter(prefix="/evolution/monitor", tags=["Evolution"])


@router.get("/cycles", response_model=list[EvolutionCycle])
async def list_cycles(limit: int = 10, session: AsyncSession = Depends(get_session)):
    """List recent evolution cycles."""
    return await evolution_monitor.get_recent_cycles(session, limit)


@router.get("/current", response_model=EvolutionCycle)
async def get_active_cycle(session: AsyncSession = Depends(get_session)):
    """Get the currently running cycle (if any)."""
    cycle = await evolution_monitor.get_current_cycle(session)
    if not cycle:
        raise HTTPException(status_code=404, detail="No active cycle found")
    return cycle


@router.get("/events/{cycle_id}", response_model=list[EvolutionEvent])
async def list_cycle_events(cycle_id: str, session: AsyncSession = Depends(get_session)):
    """List details events for a specific cycle."""
    return await evolution_monitor.get_cycle_events(session, cycle_id)
