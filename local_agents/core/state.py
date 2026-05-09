"""
Agent State Persistence - PostgreSQL ONLY.

Stores:
- Agents (traits, patterns, status)
- Memories (typed, weighted, linked)
- Trades (with confidence, zone, outcome)

Schema is defined in local-utilities/db/init/02_schema.sql and 03_agent_system.sql.
This module provides the Python interface to PostgreSQL.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC
from decimal import Decimal
from typing import Any

from .memory import Memory
from .traits import AgentTraits


def _convert_decimals(obj: Any) -> Any:
    """Recursively convert Decimal objects to floats for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    return obj


# PostgreSQL support (REQUIRED)
# Use the centralized Fast_Swarm.Database module
try:
    from sqlalchemy import text

    from Fast_Swarm.Database import get_sync_session

    HAS_POSTGRES = True
except ImportError as e:
    HAS_POSTGRES = False
    _POSTGRES_IMPORT_ERROR = str(e)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AgentRecord:
    """Agent database record."""

    agent_id: str
    agent_name: str
    generation: int = 1
    parent_a_id: str | None = None
    parent_b_id: str | None = None
    traits: dict = None
    pattern_ids: list = None
    pattern_copies: list = None  # FULL pattern data (entry_conditions, exit_conditions, etc.)
    pattern_weights: dict = None
    trading_philosophy: str = ""
    status: str = "active"
    fitness_score: float = 0.0
    backtest_count: int = 0
    created_at: int = 0
    updated_at: int = 0


@dataclass
class TradeRecord:
    """Trade database record."""

    trade_id: str
    agent_id: str
    pattern_id: str
    asset: str
    direction: str
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_timestamp: int = 0
    exit_timestamp: int = 0
    pnl_pct: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    position_size_pct: float = 1.0
    entry_confidence: float = 0.5
    decision_zone: str = "execute"
    ai_consulted: bool = False
    ai_decision: str | None = None
    created_at: int = 0


# =============================================================================
# Database Connection
# =============================================================================


class AgentDatabase:
    """
    PostgreSQL-only agent persistence.

    Schema is defined in local-utilities/db/init/02_schema.sql.
    This class provides the Python interface to the agents, memories, and trades tables.
    """

    def __init__(self):
        """
        Initialize PostgreSQL database connection.

        Raises:
            RuntimeError: If PostgreSQL dependencies are not installed.
        """
        if not HAS_POSTGRES:
            raise RuntimeError(
                f"PostgreSQL is required but not available. "
                f"Install dependencies: pip install sqlalchemy psycopg\n"
                f"Import error: {_POSTGRES_IMPORT_ERROR}"
            )

    # =========================================================================
    # Agent CRUD
    # =========================================================================

    def create_agent(
        self,
        agent_name: str,
        traits: AgentTraits,
        pattern_ids: list[str],
        pattern_copies: list[dict] = None,  # Full pattern data (agents own their patterns!)
        generation: int = 1,
        parent_a_id: str | None = None,
        parent_b_id: str | None = None,
        pattern_weights: dict | None = None,
        trading_philosophy: str = "",
    ) -> AgentRecord:
        """Create a new agent in PostgreSQL."""
        agent_id = str(uuid.uuid4())
        now = int(time.time() * 1000)

        record = AgentRecord(
            agent_id=agent_id,
            agent_name=agent_name,
            generation=generation,
            parent_a_id=parent_a_id,
            parent_b_id=parent_b_id,
            traits=asdict(traits),
            pattern_ids=pattern_ids,
            pattern_weights=pattern_weights or {},
            trading_philosophy=trading_philosophy,
            status="active",
            fitness_score=0.0,
            backtest_count=0,
            created_at=now,
            updated_at=now,
        )

        # Build assigned_patterns with FULL pattern copies (not just IDs!)
        # Structure: {"base": [full_pattern_dict, ...], "situational": [...]}
        if pattern_copies:
            base_patterns = pattern_copies[:5]  # Max 5 base patterns
            situational_patterns = pattern_copies[5:10] if len(pattern_copies) > 5 else []
        else:
            # Fallback for legacy code that doesn't provide copies
            base_patterns = [{"pattern_id": pid} for pid in (pattern_ids[:5] if pattern_ids else [])]
            situational_patterns = [
                {"pattern_id": pid} for pid in (pattern_ids[5:10] if pattern_ids and len(pattern_ids) > 5 else [])
            ]

        with get_sync_session() as session:
            session.execute(
                text("""
                INSERT INTO agents (
                    agent_id, name, generation, traits, assigned_patterns,
                    is_active, fitness_score, pattern_weights, trading_philosophy,
                    parent_a_id, parent_b_id, status, created_at, updated_at
                ) VALUES (
                    :agent_id, :name, :generation, CAST(:traits AS jsonb), CAST(:assigned_patterns AS jsonb),
                    :is_active, :fitness_score, CAST(:pattern_weights AS jsonb), :trading_philosophy,
                    :parent_a_id, :parent_b_id, :status, NOW(), NOW()
                )
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    traits = EXCLUDED.traits,
                    assigned_patterns = EXCLUDED.assigned_patterns,
                    pattern_weights = EXCLUDED.pattern_weights,
                    trading_philosophy = EXCLUDED.trading_philosophy,
                    updated_at = NOW()
            """),
                {
                    "agent_id": record.agent_id,
                    "name": record.agent_name,
                    "generation": record.generation,
                    "traits": json.dumps(_convert_decimals(record.traits)),
                    "assigned_patterns": json.dumps(
                        _convert_decimals(
                            {
                                "base": base_patterns,  # FULL pattern copies!
                                "situational": situational_patterns,
                            }
                        )
                    ),
                    "is_active": record.status == "active",
                    "fitness_score": record.fitness_score,
                    "pattern_weights": json.dumps(_convert_decimals(record.pattern_weights or {})),
                    "trading_philosophy": record.trading_philosophy or "",
                    "parent_a_id": record.parent_a_id,
                    "parent_b_id": record.parent_b_id,
                    "status": record.status,
                },
            )

        return record

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        """Get agent by ID from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT agent_id, name, generation, traits, is_active,
                       fitness_score, created_at, updated_at,
                       assigned_patterns, pattern_weights, trading_philosophy
                FROM agents WHERE agent_id = :agent_id
            """),
                {"agent_id": agent_id},
            )
            row = result.fetchone()

        if not row:
            return None

        traits_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}

        # Extract pattern copies from assigned_patterns column
        # New format: {"base": [full_pattern_dict, ...], "situational": [...]}
        # Legacy format: {"base": [pattern_id, ...], "situational": [...]}
        assigned = row[8] if isinstance(row[8], dict) else json.loads(row[8]) if row[8] else {}
        base_patterns = assigned.get("base", [])
        situational_patterns = assigned.get("situational", [])

        # Combine all patterns
        all_patterns = base_patterns + situational_patterns

        # Detect if we have full copies or just IDs
        if all_patterns and isinstance(all_patterns[0], dict) and "entry_conditions" in all_patterns[0]:
            # Full pattern copies (new format)
            pattern_copies = all_patterns
            pattern_ids = [p.get("pattern_id", "") for p in all_patterns]
        else:
            # Legacy format (just IDs) - no copies available
            pattern_copies = []
            pattern_ids = [p if isinstance(p, str) else p.get("pattern_id", "") for p in all_patterns]

        # Pattern weights from dedicated column
        pattern_weights = row[9] if isinstance(row[9], dict) else json.loads(row[9]) if row[9] else {}

        return AgentRecord(
            agent_id=row[0],
            agent_name=row[1],
            generation=row[2] or 1,
            parent_a_id=traits_data.get("parent_a_id"),
            parent_b_id=traits_data.get("parent_b_id"),
            traits={k: v for k, v in traits_data.items() if k not in ["parent_a_id", "parent_b_id"]},
            pattern_ids=pattern_ids,
            pattern_copies=pattern_copies,  # Full pattern data!
            pattern_weights=pattern_weights,
            trading_philosophy=row[10] or "",
            status="active" if row[4] else "inactive",
            fitness_score=row[5] or 0.0,
            backtest_count=0,
            created_at=int(row[6].timestamp() * 1000) if row[6] else 0,
            updated_at=int(row[7].timestamp() * 1000) if row[7] else 0,
        )

    def get_agents_by_status(self, status: str) -> list[AgentRecord]:
        """Get agents by status from PostgreSQL."""
        is_active = status == "active"
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT agent_id, name, generation, traits, is_active,
                       fitness_score, created_at, updated_at,
                       assigned_patterns, pattern_weights, trading_philosophy
                FROM agents WHERE is_active = :is_active
                ORDER BY fitness_score DESC NULLS LAST
            """),
                {"is_active": is_active},
            )
            rows = result.fetchall()

        agents = []
        for row in rows:
            traits_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}

            # Extract pattern copies from assigned_patterns column
            assigned = row[8] if isinstance(row[8], dict) else json.loads(row[8]) if row[8] else {}
            base_patterns = assigned.get("base", [])
            situational_patterns = assigned.get("situational", [])
            all_patterns = base_patterns + situational_patterns

            # Detect if we have full copies or just IDs
            if all_patterns and isinstance(all_patterns[0], dict) and "entry_conditions" in all_patterns[0]:
                pattern_copies = all_patterns
                pattern_ids = [p.get("pattern_id", "") for p in all_patterns]
            else:
                pattern_copies = []
                pattern_ids = [p if isinstance(p, str) else p.get("pattern_id", "") for p in all_patterns]

            # Pattern weights from dedicated column
            pattern_weights = row[9] if isinstance(row[9], dict) else json.loads(row[9]) if row[9] else {}

            agents.append(
                AgentRecord(
                    agent_id=row[0],
                    agent_name=row[1],
                    generation=row[2] or 1,
                    parent_a_id=traits_data.get("parent_a_id"),
                    parent_b_id=traits_data.get("parent_b_id"),
                    traits={k: v for k, v in traits_data.items() if k not in ["parent_a_id", "parent_b_id"]},
                    pattern_ids=pattern_ids,
                    pattern_copies=pattern_copies,
                    pattern_weights=pattern_weights,
                    trading_philosophy=row[10] or "",
                    status="active" if row[4] else "inactive",
                    fitness_score=row[5] or 0.0,
                    backtest_count=0,
                    created_at=int(row[6].timestamp() * 1000) if row[6] else 0,
                    updated_at=int(row[7].timestamp() * 1000) if row[7] else 0,
                )
            )
        return agents

    def get_all_active_agents(self) -> list[AgentRecord]:
        """Get all active agents."""
        return self.get_agents_by_status("active")

    def update_agent_fitness(self, agent_id: str, fitness: float, backtest_count: int = None):
        """Update agent fitness score."""
        with get_sync_session() as session:
            session.execute(
                text("""
                UPDATE agents SET fitness_score = :fitness, updated_at = NOW()
                WHERE agent_id = :agent_id
            """),
                {"fitness": fitness, "agent_id": agent_id},
            )

    def update_agent_status(self, agent_id: str, status: str):
        """Update agent status (active, retired, dead)."""
        is_active = status == "active"
        with get_sync_session() as session:
            session.execute(
                text("""
                UPDATE agents SET is_active = :is_active, updated_at = NOW()
                WHERE agent_id = :agent_id
            """),
                {"is_active": is_active, "agent_id": agent_id},
            )

    # =========================================================================
    # Memory CRUD
    # =========================================================================

    def create_memory(self, memory: Memory) -> str:
        """Create a new memory in PostgreSQL."""
        memory_id = memory.memory_id or str(uuid.uuid4())

        with get_sync_session() as session:
            session.execute(
                text("""
                INSERT INTO agent_memories (
                    memory_id, agent_id, memory_type, content, weight, confidence,
                    linked_trade_ids, linked_memory_ids, spawned_from, context_snapshot,
                    reinforcement_count, contradiction_count, is_deleted
                ) VALUES (
                    :memory_id, :agent_id, :memory_type, :content, :weight, :confidence,
                    CAST(:linked_trade_ids AS jsonb), CAST(:linked_memory_ids AS jsonb),
                    :spawned_from, CAST(:context_snapshot AS jsonb),
                    :reinforcement_count, :contradiction_count, :is_deleted
                )
            """),
                {
                    "memory_id": memory_id,
                    "agent_id": memory.agent_id,
                    "memory_type": memory.memory_type,
                    "content": memory.content,
                    "weight": memory.weight,
                    "confidence": memory.confidence,
                    "linked_trade_ids": json.dumps(memory.linked_trade_ids or []),
                    "linked_memory_ids": json.dumps(memory.linked_memory_ids or []),
                    "spawned_from": memory.spawned_from,
                    "context_snapshot": json.dumps(_convert_decimals(memory.context_snapshot or {})),
                    "reinforcement_count": memory.reinforcement_count or 0,
                    "contradiction_count": memory.contradiction_count or 0,
                    "is_deleted": memory.deleted,
                },
            )

        return memory_id

    def get_memory(self, memory_id: str) -> Memory | None:
        """Get memory by ID from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT memory_id, agent_id, memory_type, content, weight, confidence,
                       linked_trade_ids, linked_memory_ids, spawned_from, context_snapshot,
                       created_at, updated_at, reinforcement_count, contradiction_count, is_deleted
                FROM agent_memories
                WHERE memory_id = :memory_id AND is_deleted = false
            """),
                {"memory_id": memory_id},
            )
            row = result.fetchone()

        if not row:
            return None

        return self._row_to_memory_pg(row)

    def get_agent_memories(self, agent_id: str, memory_type: str | None = None) -> list[Memory]:
        """Get all memories for an agent from PostgreSQL."""
        with get_sync_session() as session:
            if memory_type:
                result = session.execute(
                    text("""
                    SELECT memory_id, agent_id, memory_type, content, weight, confidence,
                           linked_trade_ids, linked_memory_ids, spawned_from, context_snapshot,
                           created_at, updated_at, reinforcement_count, contradiction_count, is_deleted
                    FROM agent_memories
                    WHERE agent_id = :agent_id AND memory_type = :memory_type AND is_deleted = false
                """),
                    {"agent_id": agent_id, "memory_type": memory_type},
                )
            else:
                result = session.execute(
                    text("""
                    SELECT memory_id, agent_id, memory_type, content, weight, confidence,
                           linked_trade_ids, linked_memory_ids, spawned_from, context_snapshot,
                           created_at, updated_at, reinforcement_count, contradiction_count, is_deleted
                    FROM agent_memories
                    WHERE agent_id = :agent_id AND is_deleted = false
                """),
                    {"agent_id": agent_id},
                )
            rows = result.fetchall()

        return [self._row_to_memory_pg(row) for row in rows]

    def update_memory(self, memory_id: str, **updates):
        """Update memory fields in PostgreSQL."""
        valid_fields = ["weight", "content", "reinforcement_count", "contradiction_count"]
        set_parts = []
        params = {"memory_id": memory_id}

        for field, value in updates.items():
            if field in valid_fields:
                set_parts.append(f"{field} = :{field}")
                params[field] = value

        if not set_parts:
            return

        set_parts.append("updated_at = NOW()")
        set_clause = ", ".join(set_parts)

        with get_sync_session() as session:
            session.execute(
                text(f"""
                UPDATE agent_memories SET {set_clause}
                WHERE memory_id = :memory_id
            """),
                params,
            )

    def delete_memory(self, memory_id: str):
        """Soft delete a memory in PostgreSQL."""
        with get_sync_session() as session:
            session.execute(
                text("""
                UPDATE agent_memories SET is_deleted = true, updated_at = NOW()
                WHERE memory_id = :memory_id
            """),
                {"memory_id": memory_id},
            )

    def _row_to_memory_pg(self, row: Any) -> Memory:
        """Convert PostgreSQL row to Memory."""
        linked_trades = row[6] if isinstance(row[6], list) else json.loads(row[6]) if row[6] else []
        linked_mems = row[7] if isinstance(row[7], list) else json.loads(row[7]) if row[7] else []
        ctx = row[9] if isinstance(row[9], dict) else json.loads(row[9]) if row[9] else {}

        return Memory(
            memory_id=row[0],
            agent_id=row[1],
            memory_type=row[2],
            content=row[3],
            weight=row[4] or 1.0,
            confidence=row[5] or 1.0,
            linked_trade_ids=linked_trades,
            linked_memory_ids=linked_mems,
            spawned_from=row[8],
            context_snapshot=ctx,
            created_at=int(row[10].timestamp() * 1000) if row[10] else 0,
            last_accessed_at=int(row[11].timestamp() * 1000) if row[11] else 0,
            reinforcement_count=row[12] or 0,
            contradiction_count=row[13] or 0,
            deleted=bool(row[14]),
        )

    # =========================================================================
    # Trade CRUD
    # =========================================================================

    def create_trade(self, trade: TradeRecord) -> str:
        """Create a new trade record in PostgreSQL agent_trades hypertable."""
        from datetime import datetime

        trade_id = trade.trade_id or str(uuid.uuid4())

        # Convert entry_timestamp (ms) to datetime for hypertable
        trade_time = datetime.fromtimestamp(trade.entry_timestamp / 1000, tz=UTC)

        # Calculate duration in seconds
        duration_seconds = (trade.exit_timestamp - trade.entry_timestamp) / 1000 if trade.exit_timestamp else 0

        # Build metadata JSON with extra fields
        metadata = {
            "mfe_pct": trade.mfe_pct,
            "mae_pct": trade.mae_pct,
            "position_size_pct": trade.position_size_pct,
            "entry_confidence": trade.entry_confidence,
            "decision_zone": trade.decision_zone,
            "ai_consulted": trade.ai_consulted,
            "ai_decision": trade.ai_decision,
            "trade_id": trade_id,
        }

        with get_sync_session() as session:
            session.execute(
                text("""
                INSERT INTO agent_trades (
                    time, agent_id, pattern_id, symbol, side,
                    entry_price, exit_price, size, pnl, pnl_pct,
                    fees, duration_seconds, exit_reason, metadata
                ) VALUES (
                    :time, :agent_id, :pattern_id, :symbol, :side,
                    :entry_price, :exit_price, :size, :pnl, :pnl_pct,
                    :fees, :duration_seconds, :exit_reason, :metadata
                )
                ON CONFLICT (time, agent_id, symbol) DO NOTHING
            """),
                {
                    "time": trade_time,
                    "agent_id": trade.agent_id,
                    "pattern_id": trade.pattern_id,
                    "symbol": trade.asset,
                    "side": trade.direction,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "size": getattr(trade, "position_size_pct", 1.0),
                    "pnl": trade.pnl_pct * getattr(trade, "position_size_pct", 1.0) / 100,
                    "pnl_pct": trade.pnl_pct,
                    "fees": getattr(trade, "fees_pct", 0.0),
                    "duration_seconds": duration_seconds,
                    "exit_reason": getattr(trade, "exit_reason", "unknown"),
                    "metadata": json.dumps(_convert_decimals(metadata)),
                },
            )

        return trade_id

    def get_agent_trades(self, agent_id: str, limit: int = 100) -> list[TradeRecord]:
        """Get trades for an agent from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT trade_id, agent_id, pattern_id, asset, direction,
                       entry_price, exit_price, entry_timestamp, exit_timestamp,
                       pnl_pct, mfe_pct, mae_pct, position_size_pct,
                       entry_confidence, decision_zone, ai_consulted, ai_decision, created_at
                FROM agent_trades
                WHERE agent_id = :agent_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
                {"agent_id": agent_id, "limit": limit},
            )
            rows = result.fetchall()

        return [self._row_to_trade_pg(row) for row in rows]

    def get_trades_by_pattern(self, pattern_id: str, limit: int = 100) -> list[TradeRecord]:
        """Get trades for a pattern from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT trade_id, agent_id, pattern_id, asset, direction,
                       entry_price, exit_price, entry_timestamp, exit_timestamp,
                       pnl_pct, mfe_pct, mae_pct, position_size_pct,
                       entry_confidence, decision_zone, ai_consulted, ai_decision, created_at
                FROM agent_trades
                WHERE pattern_id = :pattern_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
                {"pattern_id": pattern_id, "limit": limit},
            )
            rows = result.fetchall()

        return [self._row_to_trade_pg(row) for row in rows]

    def _row_to_trade_pg(self, row: Any) -> TradeRecord:
        """Convert PostgreSQL row to TradeRecord."""
        return TradeRecord(
            trade_id=row[0],
            agent_id=row[1],
            pattern_id=row[2],
            asset=row[3],
            direction=row[4],
            entry_price=row[5],
            exit_price=row[6],
            entry_timestamp=row[7],
            exit_timestamp=row[8],
            pnl_pct=row[9],
            mfe_pct=row[10],
            mae_pct=row[11],
            position_size_pct=row[12],
            entry_confidence=row[13],
            decision_zone=row[14],
            ai_consulted=bool(row[15]),
            ai_decision=row[16],
            created_at=int(row[17].timestamp() * 1000) if row[17] else 0,
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_population_stats(self) -> dict:
        """Get population statistics from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = true) as active,
                    COUNT(*) FILTER (WHERE is_active = false) as inactive,
                    AVG(fitness_score) FILTER (WHERE is_active = true) as avg_fitness,
                    MAX(generation) as max_gen
                FROM agents
            """)
            )
            row = result.fetchone()

        return {
            "total_agents": row[0] or 0,
            "active": row[1] or 0,
            "retired": row[2] or 0,
            "dead": 0,
            "avg_fitness": float(row[3]) if row[3] else 0.0,
            "max_generation": row[4] or 0,
        }

    def get_top_agents(self, limit: int = 10) -> list[AgentRecord]:
        """Get top agents by fitness from PostgreSQL."""
        with get_sync_session() as session:
            result = session.execute(
                text("""
                SELECT agent_id, name, generation, traits, is_active,
                       fitness_score, created_at, updated_at,
                       assigned_patterns, pattern_weights, trading_philosophy
                FROM agents
                WHERE is_active = true
                ORDER BY fitness_score DESC NULLS LAST
                LIMIT :limit
            """),
                {"limit": limit},
            )
            rows = result.fetchall()

        agents = []
        for row in rows:
            traits_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}

            # Extract pattern copies from assigned_patterns column
            assigned = row[8] if isinstance(row[8], dict) else json.loads(row[8]) if row[8] else {}
            base_patterns = assigned.get("base", [])
            situational_patterns = assigned.get("situational", [])
            all_patterns = base_patterns + situational_patterns

            # Detect if we have full copies or just IDs
            if all_patterns and isinstance(all_patterns[0], dict) and "entry_conditions" in all_patterns[0]:
                pattern_copies = all_patterns
                pattern_ids = [p.get("pattern_id", "") for p in all_patterns]
            else:
                pattern_copies = []
                pattern_ids = [p if isinstance(p, str) else p.get("pattern_id", "") for p in all_patterns]

            # Pattern weights from dedicated column
            pattern_weights = row[9] if isinstance(row[9], dict) else json.loads(row[9]) if row[9] else {}

            agents.append(
                AgentRecord(
                    agent_id=row[0],
                    agent_name=row[1],
                    generation=row[2] or 1,
                    parent_a_id=traits_data.get("parent_a_id"),
                    parent_b_id=traits_data.get("parent_b_id"),
                    traits={k: v for k, v in traits_data.items() if k not in ["parent_a_id", "parent_b_id"]},
                    pattern_ids=pattern_ids,
                    pattern_copies=pattern_copies,
                    pattern_weights=pattern_weights,
                    trading_philosophy=row[10] or "",
                    status="active" if row[4] else "inactive",
                    fitness_score=row[5] or 0.0,
                    backtest_count=0,
                    created_at=int(row[6].timestamp() * 1000) if row[6] else 0,
                    updated_at=int(row[7].timestamp() * 1000) if row[7] else 0,
                )
            )
        return agents

    def clear_all(self):
        """Clear all data (for testing) in PostgreSQL."""
        with get_sync_session() as session:
            # Use backtest_trades_unified (canonical table, not legacy agent_trades)
            session.execute(text("DELETE FROM backtest_trades_unified"))
            session.execute(text("DELETE FROM agent_memories"))
            session.execute(text("DELETE FROM agents"))


# =============================================================================
# Module-level convenience functions
# =============================================================================

_db: AgentDatabase | None = None


def get_db() -> AgentDatabase:
    """Get or create the database instance."""
    global _db
    if _db is None:
        _db = AgentDatabase()
    return _db


def reset_db():
    """Reset the database instance (for testing)."""
    global _db
    _db = None
