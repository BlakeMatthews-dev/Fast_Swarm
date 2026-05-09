from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ...Database import get_session
from ...Infrastructure.Models.exchange_models import AgentTrade, LiveTradeUnified
from ..Services import trade_service

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("/")
async def read_trades(
    limit: int = Query(100, le=1000),
    skip: int = 0,
    agent_id: str | None = None,
    pattern_id: str | None = None,
    symbol: str | None = None,
    source: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    List backtest trades with optional filters.

    Filters:
    - agent_id: Filter by agent
    - pattern_id: Filter by pattern
    - symbol: Filter by trading symbol (e.g., BTC, ETH)
    - source: Filter by source (evolution_backtest, pattern_backtest, chaos)
    """
    return await trade_service.get_all_trades(
        session,
        limit=limit,
        offset=skip,
        agent_id=agent_id,
        pattern_id=pattern_id,
        symbol=symbol,
        source=source,
    )


@router.get("/stats/{agent_id}")
async def get_agent_stats(agent_id: str, session: AsyncSession = Depends(get_session)):
    """
    Get aggregate trade statistics for an agent.
    """
    return await trade_service.get_agent_trade_stats(session, agent_id)


@router.get("/agent")
async def get_agent_trades(
    agent_id: str | None = Query(None),
    pattern_id: str | None = Query(None),
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """
    Agent backtest trades (2.1M+ rows).
    """
    stmt = select(AgentTrade).order_by(desc(AgentTrade.time))
    if agent_id:
        stmt = stmt.where(AgentTrade.agent_id == agent_id)
    if pattern_id:
        stmt = stmt.where(AgentTrade.pattern_id == pattern_id)
    if symbol:
        stmt = stmt.where(AgentTrade.symbol == symbol)
    stmt = stmt.limit(limit)
    result = await session.exec(stmt)
    return [
        {
            "time": t.time.isoformat(),
            "agent_id": t.agent_id,
            "pattern_id": t.pattern_id,
            "symbol": t.symbol,
            "side": t.side,
            "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
        }
        for t in result.all()
    ]


@router.get("/live")
async def get_live_trades(
    agent_id: str | None = Query(None),
    symbol: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """
    Live/paper trades (13K+ rows).
    """
    stmt = select(LiveTradeUnified).order_by(desc(LiveTradeUnified.entry_time))
    if agent_id:
        stmt = stmt.where(LiveTradeUnified.agent_id == agent_id)
    if symbol:
        stmt = stmt.where(LiveTradeUnified.symbol == symbol)
    if status:
        stmt = stmt.where(LiveTradeUnified.status == status)
    stmt = stmt.limit(limit)
    result = await session.exec(stmt)
    return [
        {
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "side": t.side,
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "pnl_pct": t.pnl_pct,
            "status": t.status,
            "exit_reason": t.exit_reason,
        }
        for t in result.all()
    ]


@router.get("/{trade_id}")
async def read_trade(trade_id: str, session: AsyncSession = Depends(get_session)):
    """
    Get a specific trade by ID.
    """
    trade = await trade_service.get_trade_by_id(session, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade
