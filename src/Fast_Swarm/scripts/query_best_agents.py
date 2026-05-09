"""Query best agents by favorable regime fitness (excluding bear/crash)."""

from Fast_Swarm.Database import get_sync_session
from sqlalchemy import text

QUERY = """
SELECT
    agent_id,
    name,
    status,
    fitness_score::float AS overall_fitness,
    (
        SELECT COALESCE(SUM((value->>'fitness')::float), 0)
        FROM jsonb_each(fitness_by_regime) AS kv(key, value)
        WHERE key NOT IN ('bear', 'crash', 'BEAR', 'CRASH')
          AND value->>'fitness' IS NOT NULL
    ) AS favorable_fitness_sum,
    fitness_by_regime,
    -- Performance metrics
    sortino_ratio::float,
    sharpe_ratio::float,
    calmar_ratio::float,
    max_drawdown_pct::float,
    annualized_roi_pct::float,
    -- Trade stats
    total_trades,
    winning_trades,
    total_pnl::float,
    win_rate::float,
    elo_rating::float,
    -- Agent info
    generation,
    traits,
    assigned_patterns
FROM agents
WHERE status = 'active'
  AND fitness_by_regime IS NOT NULL
  AND fitness_by_regime != '{}'::jsonb
ORDER BY favorable_fitness_sum DESC NULLS LAST
LIMIT 10
"""

TRADES_QUERY = """
SELECT
    symbol,
    timeframe,
    side,
    entry_price::float,
    exit_price::float,
    CASE WHEN entry_price > 0 THEN ((exit_price - entry_price) / entry_price * 100) ELSE 0 END AS roi_pct,
    pnl_usd::float,
    is_winner,
    entry_timestamp,
    exit_timestamp
FROM backtest_trades_unified
WHERE agent_id = :agent_id
ORDER BY exit_timestamp DESC
LIMIT 5
"""

if __name__ == "__main__":
    with get_sync_session() as session:
        result = session.execute(text(QUERY))
        rows = result.fetchall()

        print("=" * 100)
        print("TOP 10 AGENTS BY FAVORABLE REGIME FITNESS (excluding bear/crash)")
        print("=" * 100)

        for i, row in enumerate(rows, 1):
            aid = row.agent_id
            name = (row.name or "unnamed")[:30]
            fsum = row.favorable_fitness_sum or 0

            print(f"\n{'='*100}")
            print(f"#{i} {name}")
            print(f"    ID: {aid}")
            print(f"    Generation: {row.generation or 'N/A'}")
            print(f"{'='*100}")

            # Fitness
            print(f"\n  FAVORABLE FITNESS SUM: {fsum:.4f}")
            print(f"  Overall Fitness:       {row.overall_fitness or 0:.4f}")

            # Performance Metrics
            print(f"\n  PERFORMANCE METRICS:")
            print(f"    Sortino Ratio:    {row.sortino_ratio or 0:.4f}")
            print(f"    Sharpe Ratio:     {row.sharpe_ratio or 0:.4f}")
            print(f"    Calmar Ratio:     {row.calmar_ratio or 0:.4f}")
            print(f"    Max Drawdown:     {row.max_drawdown_pct or 0:.2f}%")
            print(f"    Annualized ROI:   {row.annualized_roi_pct or 0:.2f}%")

            # Trade Stats
            total = row.total_trades or 0
            wins = row.winning_trades or 0
            pnl = row.total_pnl or 0
            avg_roi = (pnl / total) if total > 0 else 0
            print(f"\n  TRADE STATS:")
            print(f"    Total Trades:     {total}")
            print(f"    Winning Trades:   {wins}")
            print(f"    Win Rate:         {(row.win_rate or 0) * 100:.1f}%")
            print(f"    Total P&L:        ${pnl:,.2f}")
            print(f"    Avg P&L/Trade:    ${avg_roi:,.2f}")
            print(f"    ELO Rating:       {row.elo_rating or 1500:.0f}")

            # Regime breakdown (favorable only)
            if row.fitness_by_regime:
                print(f"\n  REGIME FITNESS (favorable):")
                for regime, data in row.fitness_by_regime.items():
                    if regime.lower() not in ('bear', 'crash'):
                        fitness = data.get('fitness', 0) if isinstance(data, dict) else 0
                        trades = data.get('trades', 0) if isinstance(data, dict) else 0
                        wr = data.get('win_rate', 0) if isinstance(data, dict) else 0
                        print(f"    {regime:12s}: fit={fitness:.2f}, trades={trades}, wr={wr*100:.0f}%")

            # Recent trades
            trades_result = session.execute(
                text(TRADES_QUERY),
                {"agent_id": aid}
            )
            trades = trades_result.fetchall()
            if trades:
                print(f"\n  RECENT TRADES (last 5):")
                for t in trades:
                    winner = "W" if t.is_winner else "L"
                    print(f"    [{winner}] {t.symbol:10s} {t.timeframe:4s} | ROI: {t.roi_pct or 0:+.2f}% | PnL: ${t.pnl_usd or 0:+.2f}")

            # Patterns
            if row.assigned_patterns:
                patterns = row.assigned_patterns if isinstance(row.assigned_patterns, list) else []
                if patterns:
                    print(f"\n  PATTERNS ({len(patterns)}):")
                    for p in patterns[:3]:
                        print(f"    - {p}")

        print(f"\n{'='*100}")
        print(f"Total agents found: {len(rows)}")
        print("=" * 100)
