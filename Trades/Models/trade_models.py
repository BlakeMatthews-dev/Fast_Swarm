from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class BacktestTrade(SQLModel, table=True):
    """
    Unified backtest trade model.

    Maps to backtest_trades_unified table from 001_unified_trades.sql migration.
    Used for: pattern backtests, chaos discovery, evolution backtests, regime tests.
    """

    __tablename__ = "backtest_trades_unified"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)

    # Identity
    trade_id: str | None = Field(default=None, unique=True, index=True)
    source: str = Field(default="evolution_backtest")  # 'chaos', 'pattern_backtest', 'evolution_backtest'

    # Pattern/Agent info
    pattern_id: str | None = Field(default=None, index=True)
    pattern_name: str | None = None
    agent_id: str | None = Field(default=None, index=True)  # Extension for agent tracking

    # Trade basics
    symbol: str = Field(index=True)
    timeframe: str | None = None
    side: str  # 'long' or 'short'

    # Timestamps (BIGINT epoch ms)
    entry_timestamp: int = Field(sa_column=Column(BigInteger, index=True))
    exit_timestamp: int | None = Field(default=None, sa_column=Column(BigInteger))
    hold_bars: int | None = None

    # Prices
    entry_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    exit_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))

    # Position sizing
    position_size_usd: Decimal = Field(default=Decimal("10000.0"), sa_column=Column(Numeric(18, 2)))

    # PnL metrics
    gross_pnl_pct: float | None = None
    net_pnl_pct: float | None = None  # After costs
    pnl_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    is_winner: bool | None = None

    # Exit info
    exit_reason: str | None = None  # 'stop_loss', 'take_profit', 'signal', 'timeout'

    # MFE/MAE analysis
    mfe_pct: float | None = None
    mfe_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    mfe_timestamp: int | None = Field(default=None, sa_column=Column(BigInteger))
    mfe_bars_from_entry: int | None = None
    mae_pct: float | None = None
    mae_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    mae_timestamp: int | None = Field(default=None, sa_column=Column(BigInteger))
    mae_bars_from_entry: int | None = None

    # Post-trade analysis
    peak_after_exit_pct: float | None = None
    ideal_exit_pct: float | None = None

    # Context (JSONB)
    entry_indicators: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    exit_indicators: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))

    # Regime context
    regime: str | None = None  # 'bull', 'bear', 'sideways', 'volatile'
    period_id: str | None = None

    # Costs
    slippage_pct: float | None = None
    fees_pct: float | None = None

    # Metadata
    source_db: str | None = None
    source_table: str | None = None

    # Decision zone tracking (agent-specific extension)
    entry_confidence: float | None = None
    decision_zone: str | None = None
    ai_consulted: bool | None = Field(default=False)
    ai_decision: str | None = None

    class Config:
        arbitrary_types_allowed = True


# Alias for backward compatibility
Trade = BacktestTrade
