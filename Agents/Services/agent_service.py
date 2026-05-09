"""
Agent Service for Fast_Swarm.

Provides agent CRUD operations and trait-driven calculation methods
for position sizing, stop loss, and take profit parameters.
"""

from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..Models.agent_models import Agent

# =============================================================================
# Trait-Driven Calculation Functions
# =============================================================================


def calculate_position_size(risk_tolerance: float) -> float:
    """
    Calculate position size as percentage of portfolio.

    Args:
        risk_tolerance: Agent trait 0-1 (higher = more aggressive)

    Returns:
        Position size 0.01 to 0.10 (1% to 10%)

    Formula: 0.01 + risk_tolerance * 0.09
    - risk_tolerance=0.0 -> 1% position
    - risk_tolerance=0.5 -> 5.5% position
    - risk_tolerance=1.0 -> 10% position
    """
    clamped = max(0.0, min(1.0, risk_tolerance))
    return 0.01 + clamped * 0.09


def calculate_stop_loss(stop_loss_tightness: float) -> float:
    """
    Calculate stop loss percentage (inverted: high tightness = tight stop).

    Args:
        stop_loss_tightness: Agent trait 0-1 (higher = tighter stop)

    Returns:
        Stop loss 0.01 to 0.10 (1% to 10%)

    Formula: 0.10 - stop_loss_tightness * 0.09
    - tightness=0.0 -> 10% stop loss (loose)
    - tightness=0.5 -> 5.5% stop loss
    - tightness=1.0 -> 1% stop loss (tight)
    """
    clamped = max(0.0, min(1.0, stop_loss_tightness))
    return 0.10 - clamped * 0.09


def calculate_take_profit(profit_target_greed: float) -> float:
    """
    Calculate take profit percentage.

    Args:
        profit_target_greed: Agent trait 0-1 (higher = greedier targets)

    Returns:
        Take profit 0.02 to 0.20 (2% to 20%)

    Formula: 0.02 + profit_target_greed * 0.18
    - greed=0.0 -> 2% take profit (conservative)
    - greed=0.5 -> 11% take profit
    - greed=1.0 -> 20% take profit (greedy)
    """
    clamped = max(0.0, min(1.0, profit_target_greed))
    return 0.02 + clamped * 0.18


def calculate_max_hold_duration_ms(hold_duration_bias: float) -> int:
    """
    Calculate maximum hold duration in milliseconds.

    Args:
        hold_duration_bias: Agent trait 0-1 (higher = longer holds)

    Returns:
        Duration from 1 hour to 7 days in milliseconds

    Formula: 3.6M ms (1h) + hold_duration_bias * 601.2M ms
    - bias=0.0 -> 1 hour (3,600,000 ms)
    - bias=0.5 -> ~3.5 days
    - bias=1.0 -> 7 days (604,800,000 ms)
    """
    ONE_HOUR_MS = 3_600_000
    SIX_DAYS_MS = 601_200_000  # 7 days - 1 hour in ms
    clamped = max(0.0, min(1.0, hold_duration_bias))
    return int(ONE_HOUR_MS + clamped * SIX_DAYS_MS)


def calculate_derived_traits(base_traits: dict[str, float]) -> dict[str, float]:
    """
    Calculate derived traits from base traits.

    Derived traits prevent contradictions in agent behavior:
    - drawdown_sensitivity = 1 - risk_tolerance (inverted)
    - stop_loss_tightness = 1 - risk_tolerance (inverted)
    - exit_aggression = 1 - hold_duration_bias (inverted)

    Args:
        base_traits: Dictionary of base trait values

    Returns:
        Dictionary with derived traits added
    """
    import random

    traits = base_traits.copy()

    # Get base traits with defaults
    risk_tolerance = traits.get("risk_tolerance", 0.5)
    hold_duration_bias = traits.get("hold_duration_bias", 0.5)

    # Derive with small noise (+-5%)
    def noise():
        return random.uniform(-0.05, 0.05)

    traits["drawdown_sensitivity"] = max(0.0, min(1.0, 1.0 - risk_tolerance + noise()))
    traits["stop_loss_tightness"] = max(0.0, min(1.0, 1.0 - risk_tolerance + noise()))
    traits["exit_aggression"] = max(0.0, min(1.0, 1.0 - hold_duration_bias + noise()))

    return traits


def get_trading_parameters(traits: dict[str, Any]) -> dict[str, float]:
    """
    Get all trading parameters from agent traits.

    Args:
        traits: Agent traits dictionary

    Returns:
        Dictionary with calculated trading parameters:
        - position_size_pct
        - stop_loss_pct
        - take_profit_pct
        - max_hold_ms
    """

    # Handle None values by defaulting to 0.5
    def safe_get(key: str, default: float = 0.5) -> float:
        value = traits.get(key, default)
        return default if value is None else value

    return {
        "position_size_pct": calculate_position_size(safe_get("risk_tolerance", 0.5)),
        "stop_loss_pct": calculate_stop_loss(safe_get("stop_loss_tightness", 0.5)),
        "take_profit_pct": calculate_take_profit(safe_get("profit_target_greed", 0.5)),
        "max_hold_ms": calculate_max_hold_duration_ms(safe_get("hold_duration_bias", 0.5)),
    }


# =============================================================================
# Database Operations
# =============================================================================


async def get_all_agents(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    include_inactive: bool = False,
) -> list[Agent]:
    """
    Fetch all agents with optional filtering.

    Args:
        session: Database session
        limit: Maximum results
        offset: Pagination offset
        include_inactive: Whether to include inactive/culled agents

    Returns:
        List of Agent instances
    """
    statement = select(Agent)
    if not include_inactive:
        statement = statement.where(Agent.status == "active")
    statement = statement.offset(offset).limit(limit)

    result = await session.exec(statement)
    return list(result.all())


async def get_agent_by_id(
    session: AsyncSession,
    agent_id: str,
) -> Agent | None:
    """Fetch a specific agent by agent_id."""
    statement = select(Agent).where(Agent.agent_id == agent_id)
    result = await session.exec(statement)
    return result.first()


async def get_agents_by_fitness(
    session: AsyncSession,
    min_fitness: float = 0.0,
    limit: int = 100,
) -> list[Agent]:
    """
    Fetch agents above a fitness threshold, ordered by fitness descending.

    Args:
        session: Database session
        min_fitness: Minimum fitness score
        limit: Maximum results

    Returns:
        List of Agent instances ordered by fitness
    """
    statement = (
        select(Agent)
        .where(Agent.status == "active")
        .where(Agent.fitness_score >= min_fitness)
        .order_by(Agent.fitness_score.desc())
        .limit(limit)
    )

    result = await session.exec(statement)
    return list(result.all())


async def update_agent_fitness(
    session: AsyncSession,
    agent_id: str,
    fitness_score: float,
    win_rate: float | None = None,
    total_trades: int | None = None,
    total_pnl: float | None = None,
) -> Agent | None:
    """
    Update agent fitness metrics after backtest.

    Args:
        session: Database session
        agent_id: Agent to update
        fitness_score: New fitness score
        win_rate: Optional win rate update
        total_trades: Optional trade count update
        total_pnl: Optional PnL update

    Returns:
        Updated Agent or None if not found
    """
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return None

    agent.fitness_score = max(0.0, min(100.0, fitness_score))

    if win_rate is not None:
        agent.win_rate = max(0.0, min(1.0, win_rate))
    if total_trades is not None:
        agent.total_trades = max(0, total_trades)
    if total_pnl is not None:
        agent.total_pnl = total_pnl

    agent.backtest_count += 1

    await session.commit()
    await session.refresh(agent)
    return agent
