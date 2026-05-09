from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric
from sqlmodel import Column, Field, SQLModel


class Committee(SQLModel, table=True):
    __tablename__ = "committees"

    committee_id: str | None = Field(default=None, primary_key=True)
    name: str
    asset: str
    timeframe: str
    voting_threshold: float
    min_quorum: int
    total_votes: int
    correct_votes: int
    total_pnl: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CommitteeVote(SQLModel, table=True):
    __tablename__ = "committee_votes"

    vote_id: str | None = Field(default=None, primary_key=True)
    committee_id: str = Field(foreign_key="committees.committee_id")
    agent_id: str
    vote_value: float
    confidence: float
    reasoning: str | None = None
    asset: str
    candle_timestamp: datetime
    triggered_pattern_id: str | None = None
    voted_at: datetime


class CommitteeDecision(SQLModel, table=True):
    __tablename__ = "committee_decisions"

    decision_id: str | None = Field(default=None, primary_key=True)
    committee_id: str = Field(foreign_key="committees.committee_id")
    weighted_vote: float
    raw_vote: float
    num_voters: int
    decision: str
    threshold_used: float
    asset: str
    decided_at: datetime
