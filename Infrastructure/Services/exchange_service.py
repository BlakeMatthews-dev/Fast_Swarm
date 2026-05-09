from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.exchange_models import ExchangeState


class ExchangeService:
    """Service for managing and querying exchange states."""

    async def get_all_exchanges(self, session: AsyncSession) -> list[str]:
        """List all unique exchange names in the system."""
        statement = select(ExchangeState.exchange).distinct()
        result = await session.exec(statement)
        return result.all()

    async def get_exchange_state(self, session: AsyncSession, exchange: str, symbol: str) -> ExchangeState | None:
        """Get the latest state (price, depth, fees) for a specific symbol on an exchange."""
        statement = (
            select(ExchangeState)
            .where(ExchangeState.exchange == exchange)
            .where(ExchangeState.symbol == symbol)
            .order_by(desc(ExchangeState.last_update))
        )
        result = await session.exec(statement)
        return result.first()

    async def get_active_market_states(self, session: AsyncSession) -> list[ExchangeState]:
        """Get all currently active market states."""
        statement = select(ExchangeState).where(ExchangeState.is_trading == True)
        result = await session.exec(statement)
        return result.all()
