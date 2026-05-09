"""
FastAPI router for MVP trading system.

Endpoints:
- Paper Trading: Start/stop agents, view active sessions
- Positions: View/manage open positions
- Live Trading: Stub endpoints for future implementation
- Monitoring: Orders, trade history

Uses AgentPaperTradingService for paper trading operations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ...Database import get_session
from ...Infrastructure.Models.exchange_models import LiveTradeUnified
from ..Models.trading_models import TradingConfig, TradingMode
from ..Services.agent_paper_trading_service import AgentPaperTradingService
from ..Services.approval_queue_service import (
    ApprovalQueueService,
    get_approval_queue_service,
)
from ..Services.live_execution_service import (
    LiveExecutionService,
    get_live_execution_service,
)

router = APIRouter(prefix="/trading", tags=["Trading"])

# Singleton service instance
_paper_trading_service: AgentPaperTradingService | None = None


def get_paper_trading_service() -> AgentPaperTradingService:
    """Get singleton AgentPaperTradingService instance."""
    global _paper_trading_service
    if _paper_trading_service is None:
        _paper_trading_service = AgentPaperTradingService()
    return _paper_trading_service


# =============================================================================
# Request/Response Models
# =============================================================================


class StartPaperTradingRequest(BaseModel):
    """Request body for starting paper trading."""

    symbols: list[str] | None = Field(
        default=None, description="Trading symbols (default: BTC-USDT)"
    )
    initial_balance: float = Field(
        default=10000.0, ge=100.0, le=1000000.0, description="Starting paper balance"
    )


class PaperTradingStatusResponse(BaseModel):
    """Response for paper trading start/stop operations."""

    status: str
    agent_id: str
    agent_name: str | None = None
    balance: float | None = None
    symbols: list[str] | None = None
    duration_seconds: float | None = None
    trades_count: int | None = None
    total_pnl: float | None = None
    final_balance: float | None = None
    error: str | None = None


class ActiveAgentResponse(BaseModel):
    """Response for active paper trading agent."""

    agent_id: str
    agent_name: str
    balance: float
    positions: int
    trades_count: int
    total_pnl: float


class PositionResponse(BaseModel):
    """Response for position data."""

    trade_id: str
    agent_id: str
    symbol: str
    side: str
    entry_price: float
    size: float
    size_usd: float
    entry_time: datetime
    unrealized_pnl: float | None = None


class AgentPositionsResponse(BaseModel):
    """Response for agent's positions and balance."""

    agent_id: str
    balance: float
    positions: dict[str, Any]
    trades_count: int
    total_pnl: float


class ClosePositionRequest(BaseModel):
    """Request body for force closing a position."""

    agent_id: str = Field(description="Agent ID owning the position")
    current_price: float = Field(gt=0, description="Current market price for closing")


class ClosePositionResponse(BaseModel):
    """Response for closing a position."""

    action: str
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl_usd: float
    duration_seconds: float
    error: str | None = None


class OrderResponse(BaseModel):
    """Response for active order data."""

    trade_id: str
    agent_id: str
    symbol: str
    side: str
    order_type: str
    requested_price: float | None = None
    size: float
    status: str
    created_at: datetime


class TradeHistoryResponse(BaseModel):
    """Response for recent trade history."""

    trade_id: str
    agent_id: str
    agent_name: str | None = None
    symbol: str
    side: str
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    pnl_pct: float | None = None
    pnl_usd: float | None = None
    status: str
    exit_reason: str | None = None
    duration_seconds: int | None = None


# =============================================================================
# Paper Trading Endpoints
# =============================================================================


@router.post(
    "/paper/start/{agent_id}",
    response_model=PaperTradingStatusResponse,
    summary="Start paper trading for an agent",
)
async def start_paper_trading(
    agent_id: str,
    request: StartPaperTradingRequest = StartPaperTradingRequest(),
    session: AsyncSession = Depends(get_session),
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Start paper trading for an agent.

    This begins a live paper trading session where the agent evaluates
    market conditions and executes simulated trades at current market prices.

    Args:
        agent_id: Agent to start trading
        request: Trading parameters (symbols, initial balance)

    Returns:
        Status with agent info and initial configuration

    Raises:
        HTTPException 404: Agent not found
        HTTPException 400: Agent not active
    """
    result = await service.start_paper_trading(
        session=session,
        agent_id=agent_id,
        symbols=request.symbols,
        initial_balance=request.initial_balance,
    )

    if "error" in result:
        status_code = 404 if "not found" in result["error"] else 400
        raise HTTPException(status_code=status_code, detail=result["error"])

    return PaperTradingStatusResponse(**result)


@router.post(
    "/paper/stop/{agent_id}",
    response_model=PaperTradingStatusResponse,
    summary="Stop paper trading for an agent",
)
async def stop_paper_trading(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Stop paper trading for an agent.

    This closes the paper trading session and returns final statistics.
    Any open positions remain in the database but are no longer actively managed.

    Args:
        agent_id: Agent to stop trading

    Returns:
        Final session statistics (duration, trades count, P&L)

    Raises:
        HTTPException 404: Agent not actively trading
    """
    result = await service.stop_paper_trading(session, agent_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return PaperTradingStatusResponse(**result)


@router.get(
    "/paper/status",
    response_model=list[ActiveAgentResponse],
    summary="List all actively paper trading agents",
)
async def get_paper_trading_status(
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Get list of all agents currently paper trading.

    Returns active session info including current balance, position count,
    and P&L for each agent.

    Returns:
        List of active agent sessions with current statistics
    """
    agents = await service.get_active_agents()
    return [ActiveAgentResponse(**agent) for agent in agents]


# =============================================================================
# Position Management Endpoints
# =============================================================================


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="Get all open positions across all agents",
)
async def get_all_positions(
    limit: int = Query(100, ge=1, le=1000, description="Maximum positions to return"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get all open positions across all agents.

    Queries the LiveTradeUnified table for positions with status='open'.
    Useful for monitoring overall system exposure.

    Args:
        limit: Maximum number of positions to return (default: 100)

    Returns:
        List of open positions with entry details
    """
    stmt = (
        select(LiveTradeUnified)
        .where(LiveTradeUnified.status == "open")
        .order_by(desc(LiveTradeUnified.entry_time))
        .limit(limit)
    )

    result = await session.exec(stmt)
    positions = result.all()

    return [
        PositionResponse(
            trade_id=p.trade_id,
            agent_id=p.agent_id or "unknown",
            symbol=p.symbol,
            side=p.side,
            entry_price=float(p.entry_price) if p.entry_price else 0.0,
            size=float(p.size) if p.size else 0.0,
            size_usd=float(p.size_usd) if p.size_usd else 0.0,
            entry_time=p.entry_time or datetime.utcnow(),
        )
        for p in positions
    ]


@router.get(
    "/positions/{agent_id}",
    response_model=AgentPositionsResponse,
    summary="Get specific agent's positions and balance",
)
async def get_agent_positions(
    agent_id: str,
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Get current positions and balance for a specific agent.

    Only returns data if the agent is actively paper trading.
    Use /trading/positions with agent_id filter for database-persisted positions.

    Args:
        agent_id: Agent to query

    Returns:
        Agent's current balance, positions, and statistics

    Raises:
        HTTPException 404: Agent not actively trading
    """
    result = await service.get_agent_positions(agent_id)

    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Agent {agent_id} not actively trading"
        )

    return AgentPositionsResponse(**result)


@router.post(
    "/positions/{symbol}/close",
    response_model=ClosePositionResponse,
    summary="Force close a position",
)
async def force_close_position(
    symbol: str,
    request: ClosePositionRequest,
    session: AsyncSession = Depends(get_session),
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Force close a position at current market price.

    This is a manual override for closing positions outside of normal
    agent trading logic. Useful for risk management or testing.

    Args:
        symbol: Trading symbol to close
        request: Agent ID and current price

    Returns:
        Close result with P&L details

    Raises:
        HTTPException 404: Position not found or agent not trading
        HTTPException 400: Invalid price
    """
    if request.current_price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")

    result = await service.force_close_position(
        session=session,
        agent_id=request.agent_id,
        symbol=symbol,
        current_price=request.current_price,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return ClosePositionResponse(**result)


# =============================================================================
# Live Trading Endpoints (Stub for MVP)
# =============================================================================


@router.post(
    "/live/start/{agent_id}",
    summary="Start live trading (NOT IMPLEMENTED - CHECKPOINT)",
    status_code=501,
)
async def start_live_trading(agent_id: str):
    """
    Start live trading for an agent.

    CHECKPOINT: This endpoint is a stub for future implementation.
    Live trading requires exchange API integration, order execution,
    and real-time risk management.

    Args:
        agent_id: Agent to start live trading

    Raises:
        HTTPException 501: Not implemented
    """
    raise HTTPException(
        status_code=501,
        detail="Live trading not implemented. This is a checkpoint for MVP. Use /trading/paper/start for paper trading.",
    )


@router.post(
    "/live/stop/{agent_id}",
    summary="Stop live trading (NOT IMPLEMENTED - CHECKPOINT)",
    status_code=501,
)
async def stop_live_trading(agent_id: str):
    """
    Stop live trading for an agent.

    CHECKPOINT: This endpoint is a stub for future implementation.

    Args:
        agent_id: Agent to stop live trading

    Raises:
        HTTPException 501: Not implemented
    """
    raise HTTPException(
        status_code=501,
        detail="Live trading not implemented. This is a checkpoint for MVP.",
    )


# =============================================================================
# Override Endpoints (User Interventions)
# =============================================================================


class PauseResumeResponse(BaseModel):
    """Response for pause/resume operations."""

    status: str
    agent_id: str
    open_positions: int | None = None
    balance: float | None = None
    pause_duration_seconds: float | None = None
    error: str | None = None


class CloseAllRequest(BaseModel):
    """Request body for closing all positions."""

    current_prices: dict[str, float] = Field(
        description="Dict of symbol -> current price for each open position"
    )


class CloseAllResponse(BaseModel):
    """Response for close all positions."""

    status: str
    agent_id: str
    positions_closed: int | None = None
    total_pnl_usd: float | None = None
    closed: list[dict] | None = None
    errors: list[dict] | None = None
    message: str | None = None
    error: str | None = None


@router.post(
    "/override/pause/{agent_id}",
    response_model=PauseResumeResponse,
    summary="Pause trading for an agent",
)
async def pause_agent_trading(
    agent_id: str,
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Pause trading for an agent.

    The agent keeps its open positions but won't open new trades
    until resumed. Use this for temporary risk management.

    Args:
        agent_id: Agent to pause

    Returns:
        Pause status with current position info

    Raises:
        HTTPException 404: Agent not actively trading
        HTTPException 400: Agent already paused
    """
    result = await service.pause_trading(agent_id)

    if "error" in result:
        if "not actively trading" in result["error"]:
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return PauseResumeResponse(**result)


@router.post(
    "/override/resume/{agent_id}",
    response_model=PauseResumeResponse,
    summary="Resume trading for a paused agent",
)
async def resume_agent_trading(
    agent_id: str,
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Resume trading for a paused agent.

    Args:
        agent_id: Agent to resume

    Returns:
        Resume status with pause duration

    Raises:
        HTTPException 404: Agent not actively trading
        HTTPException 400: Agent not paused
    """
    result = await service.resume_trading(agent_id)

    if "error" in result:
        if "not actively trading" in result["error"]:
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return PauseResumeResponse(**result)


@router.post(
    "/override/close-all/{agent_id}",
    response_model=CloseAllResponse,
    summary="Close all positions for an agent (emergency exit)",
)
async def close_all_agent_positions(
    agent_id: str,
    request: CloseAllRequest,
    session: AsyncSession = Depends(get_session),
    service: AgentPaperTradingService = Depends(get_paper_trading_service),
):
    """
    Close all open positions for an agent.

    This is an emergency exit mechanism. All positions are closed
    at the provided current prices, regardless of profit/loss.

    Args:
        agent_id: Agent whose positions to close
        request: Current prices for each symbol

    Returns:
        Summary of closed positions with total P&L

    Raises:
        HTTPException 404: Agent not found or not trading
    """
    result = await service.close_all_positions(
        session=session,
        agent_id=agent_id,
        current_prices=request.current_prices,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return CloseAllResponse(**result)


# =============================================================================
# Monitoring Endpoints
# =============================================================================


@router.get(
    "/orders/active",
    response_model=list[OrderResponse],
    summary="Get active limit orders",
)
async def get_active_orders(
    limit: int = Query(100, ge=1, le=1000, description="Maximum orders to return"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get all active limit orders.

    Queries for trades with order_type='limit_buffer' and status='open'.
    These are orders waiting to be filled at specific price levels.

    Args:
        limit: Maximum number of orders to return (default: 100)

    Returns:
        List of active orders with details
    """
    stmt = (
        select(LiveTradeUnified)
        .where(
            LiveTradeUnified.order_type == "limit_buffer",
            LiveTradeUnified.status == "open",
        )
        .order_by(desc(LiveTradeUnified.created_at))
        .limit(limit)
    )

    result = await session.exec(stmt)
    orders = result.all()

    return [
        OrderResponse(
            trade_id=o.trade_id,
            agent_id=o.agent_id or "unknown",
            symbol=o.symbol,
            side=o.side,
            order_type=o.order_type or "market",
            requested_price=(
                float(o.requested_price) if o.requested_price else None
            ),
            size=float(o.size) if o.size else 0.0,
            status=o.status,
            created_at=o.created_at or datetime.utcnow(),
        )
        for o in orders
    ]


@router.get(
    "/trades/recent",
    response_model=list[TradeHistoryResponse],
    summary="Get recent trade history",
)
async def get_recent_trades(
    limit: int = Query(100, ge=1, le=1000, description="Maximum trades to return"),
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    source: str | None = Query(
        None, description="Filter by source (paper, live, backtest)"
    ),
    status: str | None = Query(None, description="Filter by status (open, closed)"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get recent trade history with optional filters.

    Queries LiveTradeUnified table with various filters for monitoring
    and analysis of trading activity.

    Args:
        limit: Maximum number of trades to return (default: 100)
        agent_id: Filter by specific agent
        symbol: Filter by trading symbol
        source: Filter by source (paper, live, backtest)
        status: Filter by status (open, closed)

    Returns:
        List of trades with entry/exit details and P&L
    """
    stmt = select(LiveTradeUnified).order_by(desc(LiveTradeUnified.entry_time))

    if agent_id:
        stmt = stmt.where(LiveTradeUnified.agent_id == agent_id)
    if symbol:
        stmt = stmt.where(LiveTradeUnified.symbol == symbol)
    if source:
        stmt = stmt.where(LiveTradeUnified.source == source)
    if status:
        stmt = stmt.where(LiveTradeUnified.status == status)

    stmt = stmt.limit(limit)

    result = await session.exec(stmt)
    trades = result.all()

    return [
        TradeHistoryResponse(
            trade_id=t.trade_id,
            agent_id=t.agent_id or "unknown",
            agent_name=t.agent_name,
            symbol=t.symbol,
            side=t.side,
            entry_time=t.entry_time,
            exit_time=t.exit_time,
            entry_price=float(t.entry_price) if t.entry_price else None,
            exit_price=float(t.exit_price) if t.exit_price else None,
            pnl_pct=t.pnl_pct,
            pnl_usd=float(t.pnl_usd) if t.pnl_usd else None,
            status=t.status,
            exit_reason=t.exit_reason,
            duration_seconds=t.duration_seconds,
        )
        for t in trades
    ]


# =============================================================================
# Approval Queue Endpoints (APPROVAL Mode)
# =============================================================================


class SetModeRequest(BaseModel):
    """Request body for setting trading mode."""

    mode: str = Field(
        description="Trading mode: paper_only, approval, or full_auto"
    )
    initial_balance: float = Field(
        default=10000.0, ge=100.0, le=1000000.0, description="Initial balance"
    )
    symbols: list[str] = Field(
        default=["BTC-USDT"], description="Trading symbols"
    )
    limit_buffer_pct: float = Field(
        default=0.1, ge=0.01, le=1.0, description="Limit order buffer percentage"
    )
    approval_timeout_minutes: int = Field(
        default=60, ge=5, le=1440, description="Approval timeout in minutes"
    )


class SetModeResponse(BaseModel):
    """Response for setting trading mode."""

    status: str
    agent_id: str
    mode: str
    balance: float | None = None
    symbols: list[str] | None = None
    message: str | None = None
    error: str | None = None


class PendingTradeResponse(BaseModel):
    """Response for a pending trade."""

    trade_id: str
    agent_id: str
    agent_name: str
    symbol: str
    side: str
    signal_type: str
    suggested_price: float
    size: float
    size_usd: float
    reason: str
    pattern_id: str | None = None
    pattern_name: str | None = None
    regime: str | None = None
    created_at: str
    expires_at: str | None = None
    status: str
    is_bear_protection: bool


class ApproveRejectRequest(BaseModel):
    """Request body for rejecting a trade (optional reason)."""

    reason: str = Field(default="", description="Optional rejection reason")


class ApproveRejectResponse(BaseModel):
    """Response for approve/reject operations."""

    status: str
    trade_id: str
    agent_id: str | None = None
    symbol: str | None = None
    execution: dict | None = None
    reason: str | None = None
    error: str | None = None


class ApprovalStatsResponse(BaseModel):
    """Response for approval queue statistics."""

    total_pending: int
    agents_with_pending: int
    by_agent: dict[str, int]


class BulkApprovalResponse(BaseModel):
    """Response for bulk approve/reject operations."""

    agent_id: str
    approved_count: int | None = None
    rejected_count: int | None = None
    error_count: int | None = None
    reason: str | None = None
    results: list[dict] | None = None
    errors: list[dict] | None = None


@router.post(
    "/mode/{agent_id}",
    response_model=SetModeResponse,
    summary="Set trading mode for an agent",
)
async def set_trading_mode(
    agent_id: str,
    request: SetModeRequest,
    session: AsyncSession = Depends(get_session),
    paper_service: AgentPaperTradingService = Depends(get_paper_trading_service),
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
    execution_service: LiveExecutionService = Depends(get_live_execution_service),
):
    """
    Set the trading mode for an agent.

    Three modes available:
    - PAPER_ONLY: Simulated trades only, no real execution
    - APPROVAL: Paper trades queue for approval, bear protection auto-executes
    - FULL_AUTO: Auto-execute all trades as limit orders

    This also starts paper trading tracking for the agent.

    Args:
        agent_id: Agent to configure
        request: Trading mode and configuration

    Returns:
        Configured mode and settings

    Raises:
        HTTPException 400: Invalid mode or configuration
        HTTPException 404: Agent not found
    """
    # Validate mode
    try:
        mode = TradingMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be: paper_only, approval, or full_auto",
        )

    # Start paper trading to initialize tracking
    result = await paper_service.start_paper_trading(
        session=session,
        agent_id=agent_id,
        symbols=request.symbols,
        initial_balance=request.initial_balance,
    )

    if "error" in result:
        status_code = 404 if "not found" in result["error"] else 400
        raise HTTPException(status_code=status_code, detail=result["error"])

    # Configure the approval queue service
    config = TradingConfig(
        agent_id=agent_id,
        mode=mode,
        symbols=request.symbols,
        initial_balance=request.initial_balance,
        limit_buffer_pct=request.limit_buffer_pct,
        approval_timeout_minutes=request.approval_timeout_minutes,
    )
    approval_service.configure_agent(config)

    # Wire execution callback for APPROVAL and FULL_AUTO modes
    if mode in (TradingMode.APPROVAL, TradingMode.FULL_AUTO):
        approval_service.set_execute_callback(execution_service.execute_limit_order)

    # Determine exchange status
    exchange_status = "connected" if execution_service.is_ready() else "simulated"

    return SetModeResponse(
        status="configured",
        agent_id=agent_id,
        mode=mode.value,
        balance=request.initial_balance,
        symbols=request.symbols,
        message=f"Trading mode set to {mode.value}. "
        + ("Bear protection exits will auto-execute. " if mode == TradingMode.APPROVAL else "")
        + f"Exchange: {exchange_status}.",
    )


@router.get(
    "/approval/pending",
    response_model=list[PendingTradeResponse],
    summary="Get all pending trades awaiting approval",
)
async def get_all_pending_trades(
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Get all pending trades across all agents.

    These are trades in APPROVAL mode that need user approval before execution.
    Bear protection exits are auto-executed and won't appear here.

    Returns:
        List of pending trades with details
    """
    trades = await approval_service.get_pending_trades()
    return [PendingTradeResponse(**t) for t in trades]


@router.get(
    "/approval/pending/{agent_id}",
    response_model=list[PendingTradeResponse],
    summary="Get pending trades for a specific agent",
)
async def get_agent_pending_trades(
    agent_id: str,
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Get pending trades for a specific agent.

    Args:
        agent_id: Agent to query

    Returns:
        List of pending trades for the agent
    """
    trades = await approval_service.get_pending_trades(agent_id=agent_id)
    return [PendingTradeResponse(**t) for t in trades]


@router.post(
    "/approval/approve/{trade_id}",
    response_model=ApproveRejectResponse,
    summary="Approve a pending trade (executes as limit order)",
)
async def approve_trade(
    trade_id: str,
    session: AsyncSession = Depends(get_session),
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Approve a pending trade for execution.

    The trade will be executed as a limit order with a buffer:
    - Buy: limit price = suggested_price * (1 + buffer_pct)
    - Sell: limit price = suggested_price * (1 - buffer_pct)

    Args:
        trade_id: ID of the trade to approve

    Returns:
        Execution result with limit order details

    Raises:
        HTTPException 404: Trade not found
        HTTPException 400: Trade already processed or expired
    """
    result = await approval_service.approve_trade(session, trade_id)

    if "error" in result:
        if "not found" in result["error"]:
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return ApproveRejectResponse(**result)


@router.post(
    "/approval/reject/{trade_id}",
    response_model=ApproveRejectResponse,
    summary="Reject a pending trade",
)
async def reject_trade(
    trade_id: str,
    request: ApproveRejectRequest = ApproveRejectRequest(),
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Reject a pending trade.

    The trade will be removed from the queue without execution.

    Args:
        trade_id: ID of the trade to reject
        request: Optional rejection reason

    Returns:
        Rejection confirmation

    Raises:
        HTTPException 404: Trade not found
        HTTPException 400: Trade already processed
    """
    result = await approval_service.reject_trade(trade_id, request.reason)

    if "error" in result:
        if "not found" in result["error"]:
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return ApproveRejectResponse(**result)


@router.post(
    "/approval/approve-all/{agent_id}",
    response_model=BulkApprovalResponse,
    summary="Approve all pending trades for an agent",
)
async def approve_all_trades(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Approve all pending trades for an agent.

    All trades will be executed as limit orders.

    Args:
        agent_id: Agent whose trades to approve

    Returns:
        Summary of approvals with execution results
    """
    result = await approval_service.approve_all(session, agent_id)
    return BulkApprovalResponse(**result)


@router.post(
    "/approval/reject-all/{agent_id}",
    response_model=BulkApprovalResponse,
    summary="Reject all pending trades for an agent",
)
async def reject_all_trades(
    agent_id: str,
    request: ApproveRejectRequest = ApproveRejectRequest(),
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Reject all pending trades for an agent.

    Args:
        agent_id: Agent whose trades to reject
        request: Optional rejection reason

    Returns:
        Summary of rejections
    """
    result = await approval_service.reject_all(agent_id, request.reason)
    return BulkApprovalResponse(**result)


@router.get(
    "/approval/stats",
    response_model=ApprovalStatsResponse,
    summary="Get approval queue statistics",
)
async def get_approval_stats(
    approval_service: ApprovalQueueService = Depends(get_approval_queue_service),
):
    """
    Get statistics about the approval queue.

    Returns total pending trades and breakdown by agent.

    Returns:
        Queue statistics
    """
    stats = approval_service.get_queue_stats()
    return ApprovalStatsResponse(**stats)
