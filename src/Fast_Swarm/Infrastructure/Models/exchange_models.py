from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ExchangeState(SQLModel, table=True):
    """Exchange connection state - currently empty, for future use."""

    __tablename__ = "exchange_state"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    symbol: str = Field(index=True)
    last_update: datetime = Field(default_factory=datetime.utcnow)
    is_trading: bool = Field(default=True)
    last_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    bid_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    ask_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    mid_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    spread_bps: float
    bid_depth_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 2)))
    ask_depth_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 2)))
    order_imbalance: float | None = None
    maker_fee_bps: float | None = None
    taker_fee_bps: float | None = None
    latency_ms: float | None = None


class Trade(SQLModel, table=True):
    """Legacy trade model - empty table. Use LiveTradeUnified or AgentTrade."""

    __tablename__ = "trades_live"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    symbol: str = Field(index=True)
    trade_id: str
    timestamp: datetime = Field(index=True)
    price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    size: Decimal = Field(sa_column=Column(Numeric(24, 8)))
    side: str  # buy/sell
    is_liquidation: bool = Field(default=False)


class LiveTradeUnified(SQLModel, table=True):
    """
    Unified live trades from all sources (paper, live, backtest).

    Contains 13K+ rows of actual trade data.
    """

    __tablename__ = "live_trades_unified"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    trade_id: str = Field(index=True)
    source: str  # paper, live, backtest
    committee_id: str | None = None
    decision_id: str | None = None
    agent_id: str | None = Field(default=None, index=True)
    agent_name: str | None = None
    pattern_id: str | None = Field(default=None, index=True)
    pattern_name: str | None = None
    pattern_timeframe: str | None = None
    pattern_tier: str | None = None
    pattern_origin: str | None = None
    exchange: str = Field(index=True)
    venue_type: str | None = None  # paper, live
    symbol: str = Field(index=True)
    side: str  # long/short
    entry_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    exit_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    duration_seconds: int | None = None
    entry_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    exit_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    size: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
    size_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 2)))
    pnl_pct: float | None = None
    pnl_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    fees_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    realized_pnl: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    status: str = Field(default="open")  # open, closed
    exit_reason: str | None = None
    trading_mode: str | None = None
    mfe_pct: float | None = None  # Max favorable excursion
    mae_pct: float | None = None  # Max adverse excursion
    entry_signals: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    exit_signals: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    vote_count: int | None = None
    confidence: float | None = None
    created_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    source_db: str | None = None
    source_table: str | None = None

    # MVP additions for execution tracking
    order_type: str | None = None  # "market", "limit_buffer"
    requested_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))  # Price requested (vs fill)
    slippage_pct: float | None = None  # Actual slippage: (fill - requested) / requested
    regime: str | None = None  # Market regime at trade time: bull, bear, chop, flat
    order_id: str | None = None  # Exchange order ID for live trades


class AgentTrade(SQLModel, table=True):
    """
    Backtest trades from agents - TimescaleDB hypertable.

    Contains 2.1M+ rows of backtest trade data.
    """

    __tablename__ = "agent_trades"
    __table_args__ = ({"extend_existing": True},)

    time: datetime = Field(sa_column=Column(DateTime(timezone=True), primary_key=True))
    agent_id: str = Field(primary_key=True, index=True)
    pattern_id: str | None = Field(default=None, index=True)
    symbol: str = Field(index=True)
    side: str  # long/short
    entry_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    exit_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    size: Decimal = Field(sa_column=Column(Numeric(24, 8)))
    pnl: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    pnl_pct: float | None = None
    fees: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    duration_seconds: int | None = None
    exit_reason: str | None = None
    trade_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column("metadata", JSONB))
