from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

# =============================================================================
# Response Models (Pydantic only, not DB tables)
# =============================================================================


class PatternSummary(SQLModel):
    """Lightweight pattern summary for leaderboard responses."""

    pattern_id: str
    name: str
    origin: str
    status: str
    fitness_score: float | None = None
    total_roi_pct: float | None = None
    sharpe_ratio: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    total_trades: int | None = None
    total_runs: int | None = None
    symbol: str | None = None
    timeframe: str | None = None
    last_backtest_at: str | None = None
    created_at: str | None = None


class PatternLeaderboardResponse(SQLModel):
    """Response model for /patterns/leaderboard endpoint."""

    count: int
    sort_by: str
    order: str
    patterns: list[PatternSummary]


class PatternsByTierResponse(SQLModel):
    """Response model for /patterns/by-tier/{tier} endpoint."""

    tier: int
    count: int
    patterns: list[Any]  # Full Pattern objects


class PatternsByOriginResponse(SQLModel):
    """Response model for /patterns/by-origin/{origin} endpoint."""

    origin: str
    count: int
    patterns: list[Any]  # Full Pattern objects


class RegimePatternSummary(SQLModel):
    """Pattern summary with regime-specific metrics."""

    pattern_id: str
    name: str
    origin: str
    status: str
    overall_fitness: float
    regime_fitness: float
    regime_trades: int
    regime_win_rate: float | None = None
    regime_sharpe: float | None = None


class TopPatternsByRegimeResponse(SQLModel):
    """Response model for /patterns/top-by-regime/{regime} endpoint."""

    regime: str
    count: int = 0
    patterns: list[RegimePatternSummary] = []
    message: str | None = None


class PatternFitnessByRegimeResponse(SQLModel):
    """Response model for /patterns/{id}/fitness-by-regime endpoint."""

    pattern_id: str
    name: str
    origin: str
    overall_fitness: float
    best_regime: str | None = None
    best_regime_fitness: float | None = None
    regimes_tested: int
    fitness_by_regime: dict[str, Any]


# =============================================================================
# Database Model
# =============================================================================


class Pattern(SQLModel, table=True):
    __tablename__ = "patterns"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    pattern_id: str = Field(unique=True, index=True)
    name: str
    description: str | None = None
    origin: str = Field(default="unknown")
    status: str = Field(default="untested")
    is_active: bool = Field(default=True)  # Active patterns can be assigned to agents

    # JSONB fields for logic (stored as list of condition objects)
    entry_conditions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSONB))
    exit_conditions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSONB))

    # Trading Context
    symbol: str | None = None
    timeframe: str | None = None
    asset_class: str | None = None

    # Metrics
    fitness_score: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    total_roi_pct: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 6)))
    sharpe_ratio: float | None = None
    win_rate: float | None = None  # Schema uses 'win_rate'
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    total_trades: int | None = None
    best_exit_pnl_improvement: float | None = None

    # Extended metrics (from DB schema)
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    expectancy_pct: float | None = None
    alpha_pct: float | None = None
    exit_efficiency: float | None = None

    # Per-regime fitness breakdown (like agents)
    # Keys: crash, bull, bear, blowoff, recovery, sideways, random_1m, random_1h, etc.
    fitness_by_regime: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    best_regime: str | None = None  # Regime where pattern performs best
    best_regime_fitness: float | None = None

    # Metadata
    priority: int | None = None
    periods_tested: int | None = None
    last_backtest_at: datetime | None = None
    last_selected_at: datetime | None = None
    total_runs: int = Field(default=0)
    assigned_agent_id: str | None = None

    # Provenance tracking
    source_db: str | None = None
    source_table: str | None = None
    source_id: str | None = None
    selection_reason: str | None = None
    exit_strategy: str = Field(default="scaled_out")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
