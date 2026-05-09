import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure we can import from project root
sys.path.append(os.getcwd())

from Fast_Swarm.Database import DATABASE_URL


async def count_trades():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        # Use backtest_trades_unified (canonical table, not legacy agent_trades)
        result = await conn.execute(text("SELECT COUNT(*) FROM backtest_trades_unified"))
        count = result.scalar()
    await engine.dispose()
    return count


def run_test():
    # Helper to run async count
    initial = asyncio.run(count_trades())
    print(f"Initial Trade Count: {initial}")

    print("\nRunning Backtest (via Action Service)...")
    try:
        # Import services
        from Fast_Swarm.Agents.Services.action_service import perform_backtest_sync
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        db = AgentDatabase()
        agents = db.get_all_active_agents()
        if not agents:
            print("No active agents found!")
            return

        # Pick top 2 agents
        test_agents = [a.agent_id for a in agents[:2]]
        names = [a.agent_name for a in agents[:2]]
        print(f"Backtesting 2 agents: {names}")

        # Run specific backtest
        perform_backtest_sync(test_agents)

    except Exception as e:
        print(f"Error during backtest: {e}")
        import traceback

        traceback.print_exc()

    final = asyncio.run(count_trades())
    print(f"\nFinal Trade Count: {final}")
    print(f"Trades Generated: {final - initial}")


if __name__ == "__main__":
    run_test()
