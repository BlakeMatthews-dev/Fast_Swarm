from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import text

# Traits to aggregate (from INDEPENDENT_TRAITS in traits.py)
TRAIT_KEYS = [
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    "win_rate_preference",
    "momentum_vs_reversion",
    "entry_aggression",
    "lookback_preference",
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    "funding_rate_sensitivity",
    "correlation_awareness",
    "uncertainty_anchor",
]


async def get_agent_average_stats(session: AsyncSession):
    """
    Calculate average stats for all active agents using SQL aggregation.

    Optimized to push all computation to the database instead of loading
    all agents into memory and iterating in Python.
    """
    # Query 1: Basic aggregates (single row result)
    basic_stats_sql = text("""
        SELECT
            COUNT(*) as active_count,
            COALESCE(AVG(fitness_score), 0) as avg_fitness,
            COUNT(*) FILTER (WHERE fitness_score >= 50) as fitness_50_plus,
            COALESCE(AVG(win_rate), 0) as avg_win_rate,
            COALESCE(AVG(COALESCE(backtest_count, 0)), 0) as avg_backtest_count
        FROM agents
        WHERE status = 'active'
    """)
    result = await session.execute(basic_stats_sql)
    row = result.fetchone()

    if not row or row.active_count == 0:
        return {"message": "No active agents found", "count": 0}

    active_count = row.active_count
    avg_fitness = round(float(row.avg_fitness), 2)
    fitness_50_plus = row.fitness_50_plus
    avg_win_rate = round(float(row.avg_win_rate), 4)
    avg_backtest_count = round(float(row.avg_backtest_count), 2)

    # Query 2: Trait averages via JSONB extraction
    # Use parameterized query with ANY() instead of f-string IN clause
    trait_stats_sql = text("""
        SELECT key, AVG(value::float) as avg_value
        FROM agents, jsonb_each_text(traits) as t(key, value)
        WHERE status = 'active'
          AND traits IS NOT NULL
          AND key = ANY(:trait_keys)
          AND value ~ '^-?[0-9]+(\\.[0-9]+)?$'
        GROUP BY key
    """)
    result = await session.execute(trait_stats_sql, {"trait_keys": TRAIT_KEYS})
    trait_rows = result.fetchall()

    averages = dict.fromkeys(TRAIT_KEYS)
    for row in trait_rows:
        if row.key in averages:
            averages[row.key] = round(float(row.avg_value), 4)

    # Query 3: Regime fitness aggregation
    regime_stats_sql = text("""
        SELECT
            regime_key,
            AVG(COALESCE((data->>'fitness')::float, 0)) as avg_fitness,
            COUNT(*) as agent_count,
            AVG(COALESCE((data->>'trades')::float, 0)) as avg_trades,
            AVG(COALESCE((data->>'win_rate')::float, 0)) as avg_win_rate
        FROM agents, jsonb_each(fitness_by_regime) as t(regime_key, data)
        WHERE status = 'active' AND fitness_by_regime IS NOT NULL
        GROUP BY regime_key
    """)
    result = await session.execute(regime_stats_sql)
    regime_rows = result.fetchall()

    regime_fitness = {}
    for row in regime_rows:
        regime_fitness[row.regime_key] = {
            "fitness": round(float(row.avg_fitness), 2),
            "agents": row.agent_count,
            "trades": int(row.avg_trades),
            "win_rate": round(float(row.avg_win_rate), 4),
        }

    # Query 4: Count specialists (agents with 50+ fitness in at least one regime)
    specialists_sql = text("""
        SELECT COUNT(DISTINCT id) as specialists
        FROM agents, jsonb_each(fitness_by_regime) as t(regime_key, data)
        WHERE status = 'active'
          AND fitness_by_regime IS NOT NULL
          AND (data->>'fitness')::float >= 50
    """)
    result = await session.execute(specialists_sql)
    specialists = result.scalar() or 0

    return {
        "active_count": active_count,
        "avg_fitness": avg_fitness,
        "fitness_50_plus": fitness_50_plus,
        "specialists": specialists,
        "avg_win_rate": avg_win_rate,
        "avg_backtest_count": avg_backtest_count,
        "regime_fitness": regime_fitness,
        "average_traits": averages,
    }
