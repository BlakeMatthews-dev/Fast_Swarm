# Windows + psycopg3 fix: MUST be before any asyncio imports
import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import threading
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

load_dotenv()

# Default to local postgres if not set (matching docker-compose.yml)
POSTGRES_USER = os.getenv("POSTGRES_USER", "coinswarm")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
POSTGRES_DB = os.getenv("POSTGRES_DB", "coinswarm")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# psycopg3 connection URLs (unified driver for both async and sync)
# psycopg3 has native async support, replacing the need for asyncpg + psycopg2
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

# Sync URL uses the same psycopg driver (psycopg3 supports both modes)
SYNC_DATABASE_URL = os.getenv(
    "SYNC_DATABASE_URL",
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

# Lazy engine initialization - created on first use, not at import time
# This ensures the event loop policy is set before engine creation
_engine = None
_sync_engine = None
_async_session_maker = None
_sync_session_maker = None
_engine_lock = threading.Lock()  # FIX: Thread-safe engine initialization (RACE-002)


def get_async_engine():
    """Get async engine (created lazily to respect event loop policy)."""
    global _engine
    if _engine is None:
        with _engine_lock:  # FIX: Double-checked locking pattern
            if _engine is None:
                _engine = create_async_engine(
                    DATABASE_URL,
                    echo=False,
                    future=True,
                    pool_size=20,
                    max_overflow=30,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    pool_timeout=10,
                )
    return _engine


def get_sync_engine_instance():
    """Get sync engine (created lazily)."""
    global _sync_engine
    if _sync_engine is None:
        with _engine_lock:  # FIX: Double-checked locking pattern
            if _sync_engine is None:
                _sync_engine = create_engine(
                    SYNC_DATABASE_URL,
                    echo=False,
                    future=True,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )
    return _sync_engine


def async_session_maker():
    """Get async session maker (created lazily)."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = sessionmaker(get_async_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session_maker()


def sync_session_maker():
    """Get sync session maker (created lazily)."""
    global _sync_session_maker
    if _sync_session_maker is None:
        _sync_session_maker = sessionmaker(get_sync_engine_instance(), class_=Session, expire_on_commit=False)
    return _sync_session_maker()


@contextmanager
def get_sync_session():
    """Get a sync database session (for local_agents code)."""
    session = sync_session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_session() -> AsyncSession:
    """
    Async session dependency for FastAPI.

    Handles GeneratorExit gracefully to avoid IllegalStateChangeError
    when requests are cancelled mid-operation.
    """
    session = async_session_maker()
    try:
        yield session
    except GeneratorExit:
        # Request was cancelled - suppress cleanup errors
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            # Ignore cleanup errors (session may already be closed or in bad state)
            pass


def get_engine() -> AsyncEngine:
    return get_async_engine()


async def init_db():
    async with get_async_engine().begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

        # Run schema migrations for existing tables that may be missing columns
        await _run_migrations(conn)


async def _run_migrations(conn):
    """
    Add missing columns to existing tables.
    SQLModel.metadata.create_all doesn't alter existing tables.
    """
    from sqlalchemy import text

    # Migration: Add missing columns to candles table
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Add exchange column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'candles' AND column_name = 'exchange'
            ) THEN
                ALTER TABLE candles ADD COLUMN exchange VARCHAR DEFAULT 'binance';
                CREATE INDEX IF NOT EXISTS ix_candles_exchange ON candles(exchange);
            END IF;

            -- Add quote_volume column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'candles' AND column_name = 'quote_volume'
            ) THEN
                ALTER TABLE candles ADD COLUMN quote_volume FLOAT DEFAULT NULL;
            END IF;

            -- Add is_closed column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'candles' AND column_name = 'is_closed'
            ) THEN
                ALTER TABLE candles ADD COLUMN is_closed BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    """)
    )

    # Migration: Add 'exchange' column to tickers table if missing
    await conn.execute(
        text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tickers' AND column_name = 'exchange'
            ) THEN
                ALTER TABLE tickers ADD COLUMN exchange VARCHAR DEFAULT 'binance';
                CREATE INDEX IF NOT EXISTS ix_tickers_exchange ON tickers(exchange);
            END IF;
        END $$;
    """)
    )

    # Migration: Add performance metric columns to agents table if missing
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Add sharpe_ratio column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'sharpe_ratio'
            ) THEN
                ALTER TABLE agents ADD COLUMN sharpe_ratio FLOAT DEFAULT NULL;
            END IF;

            -- Add sortino_ratio column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'sortino_ratio'
            ) THEN
                ALTER TABLE agents ADD COLUMN sortino_ratio FLOAT DEFAULT NULL;
            END IF;

            -- Add calmar_ratio column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'calmar_ratio'
            ) THEN
                ALTER TABLE agents ADD COLUMN calmar_ratio FLOAT DEFAULT NULL;
            END IF;

            -- Add max_drawdown_pct column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'max_drawdown_pct'
            ) THEN
                ALTER TABLE agents ADD COLUMN max_drawdown_pct FLOAT DEFAULT 0.0;
            END IF;

            -- Add annualized_roi_pct column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'annualized_roi_pct'
            ) THEN
                ALTER TABLE agents ADD COLUMN annualized_roi_pct FLOAT DEFAULT 0.0;
            END IF;

            -- Add last_backtest_at column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'last_backtest_at'
            ) THEN
                ALTER TABLE agents ADD COLUMN last_backtest_at TIMESTAMP DEFAULT NULL;
            END IF;
        END $$;
    """)
    )

    # Migration: Add is_active column to patterns table if missing
    await conn.execute(
        text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'patterns' AND column_name = 'is_active'
            ) THEN
                ALTER TABLE patterns ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
                CREATE INDEX IF NOT EXISTS ix_patterns_is_active ON patterns(is_active);
            END IF;
        END $$;
    """)
    )

    # Migration: Add missing columns to agents table (model/DB mismatch)
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Add level column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'level'
            ) THEN
                ALTER TABLE agents ADD COLUMN level INTEGER DEFAULT 1;
            END IF;

            -- Add status column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'status'
            ) THEN
                ALTER TABLE agents ADD COLUMN status VARCHAR DEFAULT 'active';
            END IF;

            -- Add pattern_weights column (JSONB)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'pattern_weights'
            ) THEN
                ALTER TABLE agents ADD COLUMN pattern_weights JSONB DEFAULT '{}';
            END IF;

            -- Add parent_a_id column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'parent_a_id'
            ) THEN
                ALTER TABLE agents ADD COLUMN parent_a_id VARCHAR DEFAULT NULL;
            END IF;

            -- Add parent_b_id column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'parent_b_id'
            ) THEN
                ALTER TABLE agents ADD COLUMN parent_b_id VARCHAR DEFAULT NULL;
            END IF;

            -- Add trading_philosophy column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'trading_philosophy'
            ) THEN
                ALTER TABLE agents ADD COLUMN trading_philosophy TEXT DEFAULT NULL;
            END IF;

            -- Add backtest_count column (model uses this name)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'backtest_count'
            ) THEN
                ALTER TABLE agents ADD COLUMN backtest_count INTEGER DEFAULT 0;
            END IF;
        END $$;
    """)
    )

    # Migration: Add agent-specific columns to backtest_trades_unified if missing
    # The table itself is created by 001_unified_trades.sql migration
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Add agent_id column for agent backtest tracking
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'backtest_trades_unified' AND column_name = 'agent_id'
            ) THEN
                ALTER TABLE backtest_trades_unified ADD COLUMN agent_id TEXT;
                CREATE INDEX IF NOT EXISTS idx_backtest_trades_agent ON backtest_trades_unified(agent_id);
            END IF;

            -- Add decision zone columns for AI tracking
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'backtest_trades_unified' AND column_name = 'entry_confidence'
            ) THEN
                ALTER TABLE backtest_trades_unified ADD COLUMN entry_confidence FLOAT;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'backtest_trades_unified' AND column_name = 'decision_zone'
            ) THEN
                ALTER TABLE backtest_trades_unified ADD COLUMN decision_zone TEXT;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'backtest_trades_unified' AND column_name = 'ai_consulted'
            ) THEN
                ALTER TABLE backtest_trades_unified ADD COLUMN ai_consulted BOOLEAN DEFAULT FALSE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'backtest_trades_unified' AND column_name = 'ai_decision'
            ) THEN
                ALTER TABLE backtest_trades_unified ADD COLUMN ai_decision TEXT;
            END IF;
        END $$;
    """)
    )

    # Migration: Recreate evolution_cycles table with VARCHAR keys (was UUID)
    # First check if the table has wrong type and drop if needed
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Check if cycle_id column is UUID type (wrong) and drop table if so
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'evolution_cycles'
                AND column_name = 'cycle_id'
                AND data_type = 'uuid'
            ) THEN
                DROP TABLE IF EXISTS evolution_events CASCADE;
                DROP TABLE IF EXISTS evolution_cycles CASCADE;
            END IF;
        END $$
    """)
    )

    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS evolution_cycles (
            cycle_id VARCHAR PRIMARY KEY,
            cycle_number INTEGER NOT NULL,
            phase VARCHAR NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            duration_seconds INTEGER,
            agents_at_start INTEGER,
            agents_spawned INTEGER DEFAULT 0,
            agents_culled INTEGER DEFAULT 0,
            agents_reproduced INTEGER DEFAULT 0,
            top_elo FLOAT,
            avg_elo FLOAT,
            status VARCHAR NOT NULL,
            error_message TEXT,
            config JSONB DEFAULT '{}'
        )
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_evolution_cycles_status ON evolution_cycles(status)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_evolution_cycles_started ON evolution_cycles(started_at DESC)
    """)
    )

    # Migration: Create evolution_events table for detailed tracking
    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS evolution_events (
            event_id VARCHAR PRIMARY KEY,
            cycle_id VARCHAR REFERENCES evolution_cycles(cycle_id),
            event_type VARCHAR NOT NULL,
            entity_type VARCHAR NOT NULL,
            entity_id VARCHAR NOT NULL,
            data JSONB DEFAULT '{}',
            occurred_at TIMESTAMPTZ NOT NULL
        )
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_evolution_events_cycle ON evolution_events(cycle_id)
    """)
    )

    # Migration: Add missing columns to exchange_state table
    await conn.execute(
        text("""
        DO $$
        BEGIN
            -- Add latency_ms column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'exchange_state' AND column_name = 'latency_ms'
            ) THEN
                ALTER TABLE exchange_state ADD COLUMN latency_ms FLOAT DEFAULT NULL;
            END IF;
        END $$;
    """)
    )

    # Migration: Create system_config table for runtime configuration
    await conn.execute(
        text("""
        CREATE TABLE IF NOT EXISTS system_config (
            key VARCHAR(100) PRIMARY KEY,
            value JSONB NOT NULL,
            source VARCHAR(20) DEFAULT 'yaml',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    )

    # Migration: Genesis indexes for evolutionary index strategy
    # Agents table indexes
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_agents_fitness ON agents(fitness_score DESC)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_agents_status_fitness ON agents(status, fitness_score DESC)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_agents_generation ON agents(generation)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_agents_generation_status ON agents(generation, status)
    """)
    )

    # Patterns table indexes
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_patterns_status ON patterns(status)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_patterns_fitness ON patterns(fitness_score DESC)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_patterns_origin ON patterns(origin)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_patterns_symbol ON patterns(symbol)
    """)
    )

    # Backtest trades table indexes
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol ON backtest_trades_unified(symbol)
    """)
    )
    await conn.execute(
        text("""
        CREATE INDEX IF NOT EXISTS idx_backtest_trades_winner ON backtest_trades_unified(is_winner)
    """)
    )

    # Enhanced candles unique constraint (required for ON CONFLICT in backfill)
    # Try to create index - if duplicates exist, log warning and continue
    try:
        await conn.execute(
            text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_enhanced_candles_unique
            ON enhanced_candles(symbol, timeframe, time)
        """)
        )
        print("[DB] Enhanced candles unique index ready")
    except Exception as e:
        if "duplicate key" in str(e).lower():
            print("[DB] WARNING: Duplicates exist in enhanced_candles - run dedupe script manually")
            print("[DB] Backfill ON CONFLICT will fail until duplicates are removed")
        else:
            print(f"[DB] Index creation error: {e}")
