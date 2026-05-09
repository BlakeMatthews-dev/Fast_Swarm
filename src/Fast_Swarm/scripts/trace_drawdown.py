"""Trace how agents reach 100% drawdown."""

from Fast_Swarm.Database import get_sync_session
from sqlalchemy import text

# Find an agent with ~100% drawdown
AGENT_QUERY = """
SELECT agent_id, name, max_drawdown_pct, total_trades, total_pnl
FROM agents
WHERE max_drawdown_pct > 99
  AND status = 'active'
LIMIT 3
"""

# Get all trades for an agent, chronologically
TRADES_QUERY = """
SELECT
    symbol,
    timeframe,
    entry_price::float,
    exit_price::float,
    CASE WHEN entry_price > 0 THEN ((exit_price - entry_price) / entry_price * 100) ELSE 0 END AS pnl_pct,
    pnl_usd::float,
    exit_timestamp,
    exit_reason
FROM backtest_trades_unified
WHERE agent_id = :agent_id
ORDER BY exit_timestamp ASC
"""

if __name__ == "__main__":
    with get_sync_session() as session:
        # Find agents with 100% drawdown
        result = session.execute(text(AGENT_QUERY))
        agents = result.fetchall()

        if not agents:
            print("No agents found with 100% drawdown")
            exit()

        for agent in agents:
            print("=" * 80)
            print(f"AGENT: {agent.agent_id}")
            print(f"  Name: {agent.name}")
            print(f"  Max Drawdown: {agent.max_drawdown_pct:.2f}%")
            print(f"  Total Trades: {agent.total_trades}")
            print(f"  Total PnL: ${agent.total_pnl:,.2f}")
            print("=" * 80)

            # Get trades
            trades_result = session.execute(
                text(TRADES_QUERY),
                {"agent_id": agent.agent_id}
            )
            trades = trades_result.fetchall()

            # Simulate equity curve
            equity = 100.0
            peak = 100.0
            max_dd = 0.0

            print("\n  EQUITY CURVE (first 30 trades):")
            print("  " + "-" * 70)

            for i, t in enumerate(trades[:30]):
                pnl = float(t.pnl_pct or 0)
                old_equity = equity
                equity *= (1 + pnl / 100)

                if equity > peak:
                    peak = equity

                if peak > 0:
                    dd = (peak - equity) / peak * 100
                    if dd > max_dd:
                        max_dd = dd

                # Show big moves
                if abs(pnl) > 10 or i < 5 or i >= len(trades[:30]) - 3:
                    reason = t.exit_reason or "None"
                    print(f"  [{i+1:3d}] {t.symbol:8s} | PnL: {pnl:+7.2f}% | Equity: {old_equity:8.2f} -> {equity:8.2f} | DD: {max_dd:5.1f}% | Exit: {reason}")

            if len(trades) > 30:
                # Continue simulation for all trades
                for t in trades[30:]:
                    pnl = t.pnl_pct or 0
                    equity *= (1 + pnl / 100)
                    if equity > peak:
                        peak = equity
                    if peak > 0:
                        dd = (peak - equity) / peak * 100
                        if dd > max_dd:
                            max_dd = dd

                print(f"  ... ({len(trades) - 30} more trades)")

            print("  " + "-" * 70)
            print(f"  FINAL: Equity = {equity:.4f}, Peak = {peak:.2f}, Max DD = {max_dd:.2f}%")
            print()

            # Show SOL trades specifically
            sol_trades = [t for t in trades if 'SOL' in (t.symbol or '')]
            if sol_trades:
                print(f"  SOL TRADES ({len(sol_trades)} total):")
                sol_losses = [t.pnl_pct for t in sol_trades if (t.pnl_pct or 0) < -50]
                if sol_losses:
                    print(f"    Trades with >50% loss: {len(sol_losses)}")
                    print(f"    Average loss: {sum(sol_losses)/len(sol_losses):.1f}%")
                    print(f"    Worst loss: {min(sol_losses):.1f}%")
