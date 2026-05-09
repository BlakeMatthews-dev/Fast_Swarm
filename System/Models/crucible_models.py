from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class CrucibleEntry(SQLModel, table=True):
    __tablename__ = "crucible_entries"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(index=True)
    snapshot_id: str = Field(unique=True, index=True)
    level_at_entry: int

    # Frozen agent state
    traits: dict[str, Any] = Field(sa_column=Column(JSONB))
    assigned_patterns: list[str] = Field(sa_column=Column(JSONB))
    pattern_weights: dict[str, float] = Field(sa_column=Column(JSONB))

    # Test Parameters
    starting_balance: Decimal = Field(default=Decimal("50000.0"), sa_column=Column(Numeric(18, 2)))
    current_balance: Decimal = Field(default=Decimal("50000.0"), sa_column=Column(Numeric(18, 2)))

    # Results
    overall_fitness: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 8)))

    # regime scores
    regime_scores: dict[str, float] = Field(default={}, sa_column=Column(JSONB))  # bull, bear, chop, lowvol

    status: str = Field(default="pending")  # pending, running, completed, failed

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Wisdom(SQLModel, table=True):
    __tablename__ = "wisdom"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(index=True)
    crucible_entry_id: int = Field(foreign_key="crucible_entries.id")

    title: str
    content: str  # The great piece of wisdom

    # LLM metadata
    model_used: str | None = None
    tokens_used: int | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
