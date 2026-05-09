from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.evolution_models import EvolutionCycle, EvolutionEvent


async def get_recent_cycles(session: AsyncSession, limit: int = 10):
    statement = select(EvolutionCycle).order_by(desc(EvolutionCycle.cycle_number)).limit(limit)
    result = await session.exec(statement)
    return result.all()


async def get_cycle_events(session: AsyncSession, cycle_id: str):
    statement = (
        select(EvolutionEvent).where(EvolutionEvent.cycle_id == cycle_id).order_by(desc(EvolutionEvent.occurred_at))
    )
    result = await session.exec(statement)
    return result.all()


async def get_current_cycle(session: AsyncSession):
    statement = (
        select(EvolutionCycle).where(EvolutionCycle.status == "running").order_by(desc(EvolutionCycle.started_at))
    )
    result = await session.exec(statement)
    return result.first()
