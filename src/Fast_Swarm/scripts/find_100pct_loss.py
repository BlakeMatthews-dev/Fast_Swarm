"""Find trades with -100% or worse PnL (calculation errors)."""

from Fast_Swarm.Database import get_sync_session
from sqlalchemy import text

# Find impossible trades
QUERY = """
SELECT
    agent_id,
    symbol,
    timeframe,
    entry_price::float,
    exit_price::float,
    pnl_pct::float,
    exit_reason,
    exit_timestamp
FROM backtest_trades_unified
WHERE pnl_pct <= -100
   OR pnl_pct IS NULL
   OR entry_price <= 0
   OR exit_price <= 0
ORDER BY pnl_pct ASC NULLS FIRST
LIMIT 50
"""

# Check overall distribution of extreme losses
DIST_QUERY = """
SELECT
    CASE
        WHEN pnl_pct <= -100 THEN 'pnl <= -100%'
        WHEN pnl_pct <= -90 THEN 'pnl -90 to -100%'
        WHEN pnl_pct <= -80 THEN 'pnl -80 to -90%'
        WHEN entry_price <= 0 THEN 'entry_price <= 0'
        WHEN exit_price <= 0 THEN 'exit_price <= 0'
        WHEN pnl_pct IS NULL THEN 'pnl_pct IS NULL'
        ELSE 'other'
    END AS issue,
    COUNT(*) as count
FROM backtest_trades_unified
WHERE pnl_pct <= -80
   OR pnl_pct IS NULL
   OR entry_price <= 0
   OR exit_price <= 0
GROUP BY issue
ORDER BY count DESC
"""

if __name__ == "__main__":
    with get_sync_session() as session:
        print("=" * 80)
        print("DISTRIBUTION OF PROBLEMATIC TRADES")
        print("=" * 80)

        result = session.execute(text(DIST_QUERY))
        rows = result.fetchall()
        for row in rows:
            print(f"  {row.issue:25s}: {row.count:,} trades")

        print("\n" + "=" * 80)
        print("SAMPLE OF WORST TRADES (pnl <= -100% or invalid)")
        print("=" * 80)

        result = session.execute(text(QUERY))
        rows = result.fetchall()

        for row in rows:
            pnl = row.pnl_pct if row.pnl_pct is not None else "NULL"
            print(f"  {row.symbol:10s} {row.timeframe:4s} | Entry: ${row.entry_price:,.2f} -> Exit: ${row.exit_price:,.2f} | PnL: {pnl}% | Reason: {row.exit_reason}")
