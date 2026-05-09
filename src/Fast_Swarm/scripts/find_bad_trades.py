"""Find trades causing 100% drawdown."""
from Fast_Swarm.Database import get_sync_session
from sqlalchemy import text

with get_sync_session() as s:
    # Check distribution of pnl values
    print("=== PNL DISTRIBUTION ===")
    r = s.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(net_pnl_pct) as has_pnl,
            COUNT(*) - COUNT(net_pnl_pct) as null_pnl,
            MIN(net_pnl_pct)::float as min_pnl,
            MAX(net_pnl_pct)::float as max_pnl,
            AVG(net_pnl_pct)::float as avg_pnl
        FROM backtest_trades_unified
    """))
    row = r.fetchone()
    print(f"  Total trades: {row.total:,}")
    print(f"  Has PnL: {row.has_pnl:,}")
    print(f"  NULL PnL: {row.null_pnl:,}")
    print(f"  Min PnL: {row.min_pnl}%")
    print(f"  Max PnL: {row.max_pnl}%")
    print(f"  Avg PnL: {row.avg_pnl:.2f}%")

    # Check worst 10 trades
    print("\n=== WORST 10 TRADES ===")
    r = s.execute(text("""
        SELECT symbol, net_pnl_pct::float as pnl, entry_price::float, exit_price::float, exit_reason
        FROM backtest_trades_unified
        WHERE net_pnl_pct IS NOT NULL
        ORDER BY net_pnl_pct ASC
        LIMIT 10
    """))
    for row in r.fetchall():
        print(f"  {row.symbol}: {row.pnl:.1f}% | ${row.entry_price:.2f} -> ${row.exit_price:.2f} | {row.exit_reason}")

    # Check agents with 100% drawdown - what's their actual stored value?
    print("\n=== AGENTS WITH 100% DRAWDOWN ===")
    r = s.execute(text("""
        SELECT agent_id, name, max_drawdown_pct::float, total_trades, total_pnl::float
        FROM agents
        WHERE max_drawdown_pct >= 99.9
        ORDER BY max_drawdown_pct DESC
        LIMIT 5
    """))
    for row in r.fetchall():
        print(f"  {row.name}: DD={row.max_drawdown_pct:.4f}% | trades={row.total_trades} | pnl=${row.total_pnl:.2f}")
