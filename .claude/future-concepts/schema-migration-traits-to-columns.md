# Future: Migrate Traits from JSONB to Columns

> **Status:** FUTURE - Implement when trait schema is finalized
> **Priority:** Medium
> **Prerequisite:** Traits schema stable for 3+ months

---

## Current State

Traits are stored as JSONB in both `Agent` and (future) `Coach` models:

```python
class Agent(SQLModel, table=True):
    traits: Dict[str, Any] = Field(sa_column=Column(JSONB))
```

This allows flexibility during development but has drawbacks once the schema is stable.

---

## Why Migrate?

### Problems with JSONB (Post-Stabilization)

| Issue | Impact |
|-------|--------|
| No DB-level validation | Can store `{"risk_tolerance": "banana"}` |
| Schema drift | Old agents might have different trait sets |
| Query inefficiency | Can't index individual traits efficiently |
| No referential integrity | Can't enforce FK relationships |
| Cross-generation comparison | Hard to compare agents if schemas differ |

### Benefits of Columns

| Benefit | Description |
|---------|-------------|
| Type enforcement | DB rejects invalid data |
| Indexable | `CREATE INDEX ON agent_traits(risk_tolerance)` |
| Queryable | `WHERE risk_tolerance > 0.8` is fast |
| Schema consistency | All agents have identical structure |
| IDE support | Full autocomplete on trait fields |

---

## Migration Plan

### Phase 1: Add Pydantic Validation (Intermediate Step)

Before full migration, add strict validation to catch drift:

```python
from pydantic import BaseModel, Field as PydanticField, Extra

class AgentTraits(BaseModel):
    """Strict schema - rejects unknown fields"""
    risk_tolerance: float = PydanticField(ge=0.0, le=1.0)
    conviction: float = PydanticField(ge=0.0, le=1.0)
    # ... all 22 traits

    class Config:
        extra = Extra.forbid  # Reject unknown fields
        frozen = True         # Immutable

class Agent(SQLModel, table=True):
    _traits: Dict[str, Any] = Field(sa_column=Column("traits", JSONB))

    @property
    def traits(self) -> AgentTraits:
        return AgentTraits(**self._traits)
```

### Phase 2: Full Column Migration

Once schema is stable (3+ months unchanged):

```sql
-- 1. Add columns
ALTER TABLE agents
    ADD COLUMN risk_tolerance FLOAT,
    ADD COLUMN conviction FLOAT,
    -- ... all traits

-- 2. Migrate data
UPDATE agents SET
    risk_tolerance = (traits->>'risk_tolerance')::float,
    conviction = (traits->>'conviction')::float,
    -- ... all traits

-- 3. Add constraints
ALTER TABLE agents
    ADD CONSTRAINT chk_risk_tolerance CHECK (risk_tolerance BETWEEN 0.0 AND 1.0),
    ADD CONSTRAINT chk_conviction CHECK (conviction BETWEEN 0.0 AND 1.0);

-- 4. Drop JSONB column (after validation)
ALTER TABLE agents DROP COLUMN traits;
```

### Phase 3: Update Python Models

```python
class Agent(SQLModel, table=True):
    # Individual columns instead of JSONB
    risk_tolerance: float = Field(ge=0.0, le=1.0)
    conviction: float = Field(ge=0.0, le=1.0)
    patience: float = Field(ge=0.0, le=1.0)
    # ... all 22 traits as columns
```

---

## Trigger Conditions

Migrate when ALL of these are true:

- [ ] No trait additions/removals for 3+ months
- [ ] At least 1000 agents in database (sufficient data to validate)
- [ ] Evolution loop running stably
- [ ] Coach system implemented and stable
- [ ] Performance issues with JSONB queries (optional trigger)

---

## Applies To

- `agents` table → `agent_traits` (or inline columns)
- `coaches` table → `coach_traits` (or inline columns)
- `crucible_entries.traits` snapshot (keep as JSONB for historical)

---

## Notes

- Crucible snapshots should KEEP JSONB since they're historical records
- Migration should be ONE-TIME, not gradual
- Run in maintenance window due to table locks

---

*Created: 2026-01-17*
*Context: Discussion about @dataclass vs SQLModel for traits*
