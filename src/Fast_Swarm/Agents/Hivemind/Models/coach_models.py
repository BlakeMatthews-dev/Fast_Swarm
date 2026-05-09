"""
Coach and Hivemind Models for the Coopetition System.

Design Summary (from design session):
- 100 Coaches compete, each managing a Hivemind (roster of agent instances)
- Coaches are LLM-guided roster managers with evolvable traits
- Agent instances vote on trades (-2 to +2 scale) with confidence
- Hiveminds grouped into Trios for backtesting, ELO transfers on outcomes
- Sqrt-scaled ELO transfers, flat 5 ELO tax per backtest
- Clone at 1800 ELO, death at 1200 ELO, population maintained at 100
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

# =============================================================================
# Enums
# =============================================================================


class RosterStatus(str, Enum):
    """Agent instance status within a coach's roster."""
    ACTIVE = "active"    # Currently voting in trades
    BENCH = "bench"      # On roster but not voting


class CoachStatus(str, Enum):
    """Coach lifecycle status."""
    ACTIVE = "active"
    DEAD = "dead"        # Hit 1200 ELO threshold


class TrioStatus(str, Enum):
    """Trio lifecycle status."""
    ACTIVE = "active"
    REGROUPING = "regrouping"  # ELO gap too large, needs rebalancing
    COMPLETED = "completed"


class TradeLegType(str, Enum):
    """Type of trade leg for granular scoring."""
    ENTRY = "entry"      # Opening a new position
    ADD = "add"          # Adding to existing position
    TRIM = "trim"        # Reducing position
    EXIT = "exit"        # Closing position entirely
    FLIP = "flip"        # Reversing direction


class VoteDirection(int, Enum):
    """Vote scale from Strong Sell to Strong Buy."""
    STRONG_SELL = -2
    SELL = -1
    HOLD = 0
    BUY = 1
    STRONG_BUY = 2


# =============================================================================
# Trait Configuration (for spawning and mutation)
# =============================================================================

COACH_TRAIT_CONFIGS = {
    "kelly_fraction": {"min": 0.20, "max": 0.80, "mutation_std": 0.10},
    "action_threshold": {"min": 0.10, "max": 0.90, "mutation_std": 0.10},
    "regime_sensitivity": {"min": 0.0, "max": 1.0, "mutation_std": 0.10},
    "specialist_preference": {"min": 0.0, "max": 1.0, "mutation_std": 0.10},
    "patience": {"min": 0.0, "max": 1.0, "mutation_std": 0.10},
    "roster_size_preference": {"min": 3.0, "max": 7.0, "mutation_std": 0.5},
}


# =============================================================================
# Constants
# =============================================================================

COACH_STARTING_ELO = 1500.0
COACH_CLONE_THRESHOLD = 1800.0
COACH_DEATH_THRESHOLD = 1200.0
COACH_POPULATION_TARGET = 100

AGENT_STARTING_ELO = 1500.0
AGENT_CLONE_THRESHOLD = 1800.0
AGENT_DEATH_THRESHOLD = 1200.0

ELO_K_BASE = 32
BACKTEST_ELO_TAX = 5.0  # Flat tax per backtest, split across trio
HOLD_MISS_THRESHOLD = 0.01  # 1% - HOLD only wrong if missed > this

TRIO_ELO_GAP_THRESHOLD = 300.0  # Regroup if gap exceeds this


# =============================================================================
# Template Catalog (Crucible graduates + clones + releases)
# =============================================================================


class AgentTemplate(SQLModel, table=True):
    """
    Template for agent instances. Sources:
    1. Crucible graduates (proven agents)
    2. Agent clones (hit 1800 ELO)
    3. Coach releases (snapshot of evolved instance)

    Templates are never pruned - bad ones just don't get selected.
    """
    __tablename__ = "agent_templates"

    id: int | None = Field(default=None, primary_key=True)
    template_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Origin tracking
    origin_type: str  # "crucible", "clone", "release"
    source_agent_id: str | None = None  # Original agent that spawned this
    source_crucible_entry_id: int | None = Field(default=None, foreign_key="crucible_entries.id")
    parent_template_id: str | None = None  # If cloned from another template

    # Frozen agent state (copied when template created)
    name: str
    traits: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    assigned_patterns: list[str] = Field(default=[], sa_column=Column(JSONB))
    pattern_weights: dict[str, float] = Field(default={}, sa_column=Column(JSONB))

    # Fitness scores for catalog queries
    overall_fitness: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))
    regime_scores: dict[str, float] = Field(default={}, sa_column=Column(JSONB))

    # Metadata
    times_copied: int = Field(default=0)  # Popularity tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def salary(self) -> int:
        """Salary = fitness × 10 (cost to acquire)."""
        return int(float(self.overall_fitness) * 10)


# =============================================================================
# Coach Model
# =============================================================================


class Coach(SQLModel, table=True):
    """
    Coach: LLM-guided roster manager for a Hivemind.

    Coaches:
    - Have evolvable traits that influence their LLM decisions
    - Manage a roster of agent instances (active + bench)
    - Compete via their hivemind's performance in trios
    - Clone at 1800 ELO, die at 1200 ELO
    - Population maintained at 100 through auto-spawning
    """
    __tablename__ = "coaches"

    id: int | None = Field(default=None, primary_key=True)
    coach_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)
    name: str

    # Lineage
    generation: int = Field(default=0)
    parent_id: str | None = None

    # THE SINGLE METRIC THAT RULES EVERYTHING
    elo_rating: Decimal = Field(default=Decimal("1500.0"), sa_column=Column(Numeric(12, 4)))

    # Evolvable traits (passed to LLM as personality/bias)
    traits: dict[str, float] = Field(default={}, sa_column=Column(JSONB))
    # Expected traits:
    #   kelly_fraction: 0.20-0.80 (position sizing preference)
    #   action_threshold: 0.10-0.90 (when to act on signals)
    #   regime_sensitivity: 0.0-1.0 (how much to weight regime in decisions)
    #   specialist_preference: 0.0-1.0 (prefer specialists vs generalists)
    #   patience: 0.0-1.0 (how long to hold positions)
    #   roster_size_preference: 3.0-7.0 (target roster size)

    # Current beliefs (updated by Coach LLM)
    current_regime_belief: str = Field(default="unknown")
    predicted_regime: str = Field(default="unknown")
    regime_confidence: float = Field(default=0.5)

    # Timeframe focus (for future specialization)
    timeframe_focus: str = Field(default="swing")  # scalp, intraday, swing, position

    # Lifecycle
    status: str = Field(default="active")  # active, dead
    trading_tier: str = Field(default="paper")  # paper, live

    # Promotion/demotion tracking
    promoted_at: datetime | None = None  # When promoted to live trading
    demoted_at: datetime | None = None  # When demoted back to paper

    # Stats
    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    total_pnl: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))
    backtests_participated: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    died_at: datetime | None = None

    @property
    def max_roster_size(self) -> int:
        """Max roster size based on evolvable trait."""
        pref = self.traits.get("roster_size_preference", 5.0)
        return max(3, min(7, round(pref)))

    @property
    def kelly_fraction(self) -> float:
        """Kelly fraction for position sizing."""
        return self.traits.get("kelly_fraction", 0.5)

    @property
    def action_threshold(self) -> float:
        """Threshold for acting on signals."""
        return self.traits.get("action_threshold", 0.5)

    def can_add_agent(self, current_roster_size: int) -> bool:
        """Check if coach can add more agents (respects clone overflow)."""
        return current_roster_size < self.max_roster_size


# =============================================================================
# Agent Instance Model
# =============================================================================


class AgentInstance(SQLModel, table=True):
    """
    Agent Instance: A copy of a template on a coach's roster.

    Instances:
    - Are copied from templates (can mutate independently)
    - Vote on trades with direction (-2 to +2) and confidence
    - Gain/lose ELO based on vote correctness
    - Clone at 1800 ELO (added to roster AND template catalog)
    - Die at 1200 ELO (removed from roster)
    """
    __tablename__ = "agent_instances"

    id: int | None = Field(default=None, primary_key=True)
    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Source template
    template_id: str = Field(index=True, foreign_key="agent_templates.template_id")

    # Owning coach
    coach_id: str = Field(index=True, foreign_key="coaches.coach_id")

    # Roster status
    roster_status: str = Field(default="bench")  # active, bench
    slot_number: int | None = None  # Position in active roster (1-7)

    # Instance-specific state (can mutate from template)
    name: str
    traits: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    assigned_patterns: list[str] = Field(default=[], sa_column=Column(JSONB))
    pattern_weights: dict[str, float] = Field(default={}, sa_column=Column(JSONB))

    # Instance ELO (separate from template fitness)
    elo_rating: Decimal = Field(default=Decimal("1500.0"), sa_column=Column(Numeric(12, 4)))

    # Lineage (for clones)
    parent_instance_id: str | None = None
    generation: int = Field(default=0)

    # Stats
    total_votes: int = Field(default=0)
    correct_votes: int = Field(default=0)
    total_pnl: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))

    # Lifecycle
    is_active: bool = Field(default=True)
    acquired_at: datetime = Field(default_factory=datetime.utcnow)
    released_at: datetime | None = None

    @property
    def salary(self) -> int:
        """Salary based on template fitness (fixed at acquisition)."""
        # This would be set at acquisition time from template.salary
        # For now, return a default
        return 1500

    @property
    def win_rate(self) -> float:
        """Calculate win rate from vote history."""
        if self.total_votes == 0:
            return 0.0
        return self.correct_votes / self.total_votes


# =============================================================================
# Trio Model (Grouping for competition)
# =============================================================================


class Trio(SQLModel, table=True):
    """
    Trio: Group of 3 hiveminds that compete together.

    Trios:
    - Grouped by similar ELO ratings
    - Run backtests together, vote per trade
    - Winners steal ELO from losers (coopetition)
    - Regrouped when ELO gap exceeds threshold (300)
    """
    __tablename__ = "trios"

    id: int | None = Field(default=None, primary_key=True)
    trio_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Member coaches (their hiveminds compete)
    coach_id_1: str = Field(foreign_key="coaches.coach_id")
    coach_id_2: str = Field(foreign_key="coaches.coach_id")
    coach_id_3: str = Field(foreign_key="coaches.coach_id")

    # Current ELO spread (for regrouping check)
    elo_spread: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(12, 4)))

    # Status
    status: str = Field(default="active")  # active, regrouping, completed

    # Stats
    trades_evaluated: int = Field(default=0)
    backtests_completed: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    disbanded_at: datetime | None = None

    def needs_regrouping(self, coaches: list[Coach]) -> bool:
        """Check if ELO gap exceeds threshold."""
        elos = [float(c.elo_rating) for c in coaches]
        spread = max(elos) - min(elos)
        return spread > TRIO_ELO_GAP_THRESHOLD


# =============================================================================
# Trade Leg Model (Granular position tracking)
# =============================================================================


class TradeLeg(SQLModel, table=True):
    """
    Trade Leg: Individual position change for granular scoring.

    Each leg is scored independently:
    - Entry/Exit legs get 2x ELO weight
    - Add/Trim legs get 1x ELO weight
    - P&L uses sqrt scaling for diminishing returns
    """
    __tablename__ = "trade_legs"

    id: int | None = Field(default=None, primary_key=True)
    leg_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Parent trio
    trio_id: str = Field(index=True, foreign_key="trios.trio_id")

    # Leg details
    leg_type: str  # entry, add, trim, exit, flip
    direction: int  # +1 long, -1 short
    size_pct: Decimal = Field(sa_column=Column(Numeric(8, 4)))  # % of position

    # Price tracking
    asset: str
    open_price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    open_candle_idx: int
    close_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    close_candle_idx: int | None = None

    # Result
    pnl_pct: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 6)))
    is_closed: bool = Field(default=False)

    # ELO weight multiplier (2.0 for entry/exit, 1.0 for mid-trade)
    elo_weight: Decimal = Field(default=Decimal("1.0"), sa_column=Column(Numeric(4, 2)))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None


# =============================================================================
# Hivemind Vote Model (Per-trade voting record)
# =============================================================================


class HivemindVote(SQLModel, table=True):
    """
    Hivemind Vote: Record of how a hivemind voted on a trade leg.

    Vote scale: -2 (Strong Sell) to +2 (Strong Buy)
    Weighted by: ELO × Confidence × Coach Kelly%
    """
    __tablename__ = "hivemind_votes"

    id: int | None = Field(default=None, primary_key=True)
    vote_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # What we're voting on
    leg_id: str = Field(index=True, foreign_key="trade_legs.leg_id")
    trio_id: str = Field(index=True, foreign_key="trios.trio_id")

    # Who voted
    coach_id: str = Field(index=True, foreign_key="coaches.coach_id")

    # The vote
    vote_direction: int  # -2, -1, 0, +1, +2
    confidence: Decimal = Field(sa_column=Column(Numeric(5, 4)))  # 0.0 to 1.0

    # Weighted vote (direction × confidence × coach_elo × kelly)
    weighted_vote: Decimal = Field(sa_column=Column(Numeric(12, 4)))

    # Individual agent votes that composed this (for debugging/analysis)
    agent_votes: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    # Format: {"instance_id": {"direction": 1, "confidence": 0.8, "elo": 1520}, ...}

    # Outcome (filled after leg closes)
    was_correct: bool | None = None
    elo_change: Decimal | None = Field(default=None, sa_column=Column(Numeric(10, 4)))

    voted_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# ELO Transfer Record (Audit trail)
# =============================================================================


class ELOTransfer(SQLModel, table=True):
    """
    ELO Transfer: Record of ELO movement between coaches/agents.

    Tracks:
    - Trade-based transfers (winners from losers)
    - Backtest tax (flat 5 ELO per backtest)
    - Clone bonuses
    - Death penalties
    """
    __tablename__ = "elo_transfers"

    id: int | None = Field(default=None, primary_key=True)
    transfer_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Transfer type
    transfer_type: str  # "trade", "tax", "clone_bonus", "death_penalty", "spawn"

    # Parties (can be coach or agent instance)
    from_entity_type: str  # "coach", "agent_instance", "system"
    from_entity_id: str | None = None
    to_entity_type: str  # "coach", "agent_instance", "system"
    to_entity_id: str | None = None

    # Amount
    amount: Decimal = Field(sa_column=Column(Numeric(10, 4)))

    # Context
    leg_id: str | None = Field(default=None, foreign_key="trade_legs.leg_id")
    trio_id: str | None = Field(default=None, foreign_key="trios.trio_id")
    reason: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Response Models (Pydantic only, not DB tables)
# =============================================================================


class CoachSummary(SQLModel):
    """Summary view of a coach for API responses."""
    coach_id: str
    name: str
    elo_rating: float
    generation: int
    roster_size: int
    active_agents: int
    status: str
    traits: dict[str, float]


class TrioSummary(SQLModel):
    """Summary view of a trio for API responses."""
    trio_id: str
    coach_ids: list[str]
    elo_spread: float
    trades_evaluated: int
    status: str


class HivemindStatus(SQLModel):
    """Full status of a coach's hivemind."""
    coach: CoachSummary
    active_roster: list[dict]
    bench: list[dict]
    recent_votes: list[dict]
    current_trio_id: str | None
