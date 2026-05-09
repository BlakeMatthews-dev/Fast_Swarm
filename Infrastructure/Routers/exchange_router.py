from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...Database import get_session
from ..Models.exchange_models import ExchangeState
from ..Services.exchange_service import ExchangeService

router = APIRouter(prefix="/exchanges", tags=["Exchanges"])
exch_service = ExchangeService()


@router.get("/", response_model=list[str])
async def list_exchanges(session: AsyncSession = Depends(get_session)):
    """List available exchanges."""
    return await exch_service.get_all_exchanges(session)


@router.get("/status", response_model=list[ExchangeState])
async def get_all_status(session: AsyncSession = Depends(get_session)):
    """Get current status of all trading pairs."""
    return await exch_service.get_active_market_states(session)


@router.get("/{exchange}/{symbol}", response_model=ExchangeState)
async def get_pair_status(exchange: str, symbol: str, session: AsyncSession = Depends(get_session)):
    """Get detailed status for a specific pair."""
    state = await exch_service.get_exchange_state(session, exchange, symbol)
    if not state:
        raise HTTPException(status_code=404, detail="Exchange state not found")
    return state
