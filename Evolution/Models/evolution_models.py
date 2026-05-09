from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class EvolutionCycle(SQLModel, table=True):
    __tablename__ = "evolution_cycles"

    cycle_id: str | None = Field(default=None, primary_key=True)
    cycle_number: int
    phase: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    agents_at_start: int | None = None
    agents_spawned: int = 0
    agents_culled: int = 0
    agents_reproduced: int = 0
    top_elo: float | None = None
    avg_elo: float | None = None
    status: str
    error_message: str | None = None
    config: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))


class EvolutionEvent(SQLModel, table=True):
    __tablename__ = "evolution_events"

    event_id: str | None = Field(default=None, primary_key=True)
    cycle_id: str = Field(foreign_key="evolution_cycles.cycle_id")
    event_type: str
    entity_type: str
    entity_id: str
    data: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    occurred_at: datetime
