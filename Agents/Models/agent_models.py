from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(unique=True, index=True)
    name: str
    level: int = Field(default=1)
    generation: int = Field(default=1)
    # DEPRECATED: Use status instead. is_active is auto-synced from status.
    is_active: bool = Field(default=True)
    # Source of truth: "active", "retired", "culled", "dead"
    status: str = Field(default="active")

    # JSONB fields
    traits: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    assigned_patterns: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    pattern_weights: dict[str, float] = Field(default={}, sa_column=Column(JSONB))

    parent_a_id: str | None = None
    parent_b_id: str | None = None
    trading_philosophy: str | None = None

    fitness_score: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))
    fitness_by_regime: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))  # {"crash": 45.2, "bull": 72.1, ...}
    # 2D fitness matrix: regime × timeframe for heatmap display
    # {"crash": {"1m": 45.2, "1h": 52.1}, "bull": {"1m": 84.0, "15m": 70.0}, ...}
    fitness_matrix: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    elo_rating: Decimal = Field(default=Decimal("1500"), sa_column=Column(Numeric(12, 4)))
    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    total_pnl: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))
    win_rate: float | None = None
    backtest_count: int = Field(default=0)

    # Performance metrics (set by backtest_service)
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    max_drawdown_pct: float = Field(default=0.0)
    annualized_roi_pct: float = Field(default=0.0)
    last_backtest_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True


# Auto-sync is_active when status changes
@event.listens_for(Agent.status, "set")
def sync_is_active_from_status(target, value, oldvalue, initiator):
    """Keep is_active in sync with status (deprecated field)."""
    target.is_active = value == "active"


# =============================================================================
# Response Models (Pydantic only, not DB tables)
# =============================================================================


class SpawnAgentsResponse(SQLModel):
    """Response model for /actions/spawn endpoint."""

    message: str
    agents: list[str]
    ai_selection: bool
    patterns_available: int


class CullAgentsResponse(SQLModel):
    """Response model for /actions/cull endpoint."""

    culled: int
    survived: int
    culled_agents: list[str] = []


class CullDryRunResponse(SQLModel):
    """Response model for /actions/cull?dry_run=true endpoint."""

    dry_run: bool = True
    would_cull: int
    would_survive: int
    bottom_agents: list[dict]


class BacktestStatusResponse(SQLModel):
    """Response model for /actions/backtest/status endpoint."""

    running: bool
    progress: int = 0
    total: int = 0
    current_agent: str | None = None
    completed: list[dict] = []
    errors: list[str] = []


# =============================================================================
# Request Models
# =============================================================================


class EvolutionRunRequest(SQLModel):
    generations: int = 10
    population_size: int = 15
    elite_percent: float = 0.20
    survival_percent: float = 0.60
    mutation_rate: float = 0.15
    assets: list[str] = ["BTC/USDT", "ETH/USDT"]
    timeframe: str = "1h"
    ai_zone_mode: str = "heuristic"  # skip, heuristic, llm
