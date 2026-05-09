"""
Progress Summary Script - Windows tested, fitness rates, max/avg.
"""

import asyncio
import sys

sys.path.insert(0, "C:/Users/Admin/Documents/Fast_Swarm")

from sqlalchemy import text

from Database import get_session


async def check_progress():
    """Get progress summary from database."""
    async for session in get_session():
        # Agent stats with windows tested
        agent_stats = await session.execute(
            text("""
            SELECT
                COUNT(*) as total_agents,
                COUNT(*) FILTER (WHERE backtest_count > 0) as agents_tested,
                COALESCE(SUM(backtest_count), 0) as total_backtests,
                COALESCE(AVG(backtest_count), 0) as avg_backtests_per_agent,
                COALESCE(MAX(backtest_count), 0) as max_backtests,
                COALESCE(AVG(fitness_score), 0) as avg_fitness,
                COALESCE(MAX(fitness_score), 0) as max_fitness,
                COALESCE(MIN(fitness_score), 0) as min_fitness,
                COALESCE(STDDEV(fitness_score), 0) as fitness_stddev,
                COUNT(*) FILTER (WHERE fitness_score >= 50) as fitness_50_plus,
                COUNT(*) FILTER (WHERE fitness_score >= 70) as fitness_70_plus,
                COUNT(*) FILTER (WHERE fitness_score >= 90) as fitness_90_plus
            FROM agents
            WHERE is_active = true
        """)
        )
        agent_row = agent_stats.fetchone()

        # Regime fitness breakdown (handles nested JSONB with 'fitness' key)
        regime_stats = await session.execute(
            text("""
            SELECT
                regime,
                COUNT(*) as count,
                AVG(fitness) as avg_fitness,
                MAX(fitness) as max_fitness,
                MIN(fitness) as min_fitness
            FROM (
                SELECT
                    key as regime,
                    COALESCE((value->>'fitness')::float, (value::text)::float) as fitness
                FROM agents, jsonb_each(fitness_by_regime)
                WHERE is_active = true
                  AND fitness_by_regime IS NOT NULL
                  AND fitness_by_regime != '{}'::jsonb
                  AND (value->>'fitness' IS NOT NULL OR jsonb_typeof(value) = 'number')
            ) sub
            WHERE fitness IS NOT NULL
            GROUP BY regime
            ORDER BY avg_fitness DESC
        """)
        )
        regime_rows = regime_stats.fetchall()

        # Pattern stats
        pattern_stats = await session.execute(
            text("""
            SELECT
                COUNT(*) as total_patterns,
                COUNT(*) FILTER (WHERE periods_tested > 0) as patterns_tested,
                COALESCE(SUM(periods_tested), 0) as total_tests,
                COALESCE(AVG(fitness_score), 0) as avg_fitness,
                COALESCE(MAX(fitness_score), 0) as max_fitness,
                COUNT(*) FILTER (WHERE fitness_score >= 50) as fitness_50_plus,
                COUNT(*) FILTER (WHERE fitness_score >= 70) as fitness_70_plus
            FROM patterns
            WHERE is_active = true
        """)
        )
        pattern_row = pattern_stats.fetchone()

        # Recent evolution cycles
        evo_stats = await session.execute(
            text("""
            SELECT
                COUNT(*) as total_cycles,
                MAX(generation) as latest_generation,
                AVG(EXTRACT(EPOCH FROM (ended_at - started_at))) as avg_duration_secs
            FROM evolution_cycles
            WHERE ended_at IS NOT NULL
        """)
        )
        evo_row = evo_stats.fetchone()

        # Windows calculation
        windows_per_agent = 552  # 152 canonical + 400 random
        agents_tested = agent_row[1] if agent_row else 0
        total_windows = agents_tested * windows_per_agent

        print("\n" + "=" * 70)
        print("FAST_SWARM PROGRESS SUMMARY")
        print("=" * 70)

        print("\n📊 AGENT WINDOWS TESTED")
        print("-" * 40)
        print(f"  Agents Active:        {agent_row[0]:,}")
        print(f"  Agents Tested:        {agents_tested:,}")
        print(f"  Windows per Agent:    {windows_per_agent:,}")
        print(f"  TOTAL WINDOWS:        {total_windows:,}")
        print(f"  Avg Backtests/Agent:  {float(agent_row[3]):.1f}")
        print(f"  Max Backtests:        {agent_row[4]:,}")

        print("\n📈 AGENT FITNESS DISTRIBUTION")
        print("-" * 40)
        print(f"  Avg Fitness:  {float(agent_row[5]):.2f}")
        print(f"  Max Fitness:  {float(agent_row[6]):.2f}")
        print(f"  Min Fitness:  {float(agent_row[7]):.2f}")
        print(f"  Std Dev:      {float(agent_row[8]):.2f}")
        print(f"  50+ Fitness:  {agent_row[9]:,} agents")
        print(f"  70+ Fitness:  {agent_row[10]:,} agents (elite)")
        print(f"  90+ Fitness:  {agent_row[11]:,} agents (top tier)")

        if regime_rows:
            print("\n🌍 REGIME FITNESS BREAKDOWN")
            print("-" * 40)
            for row in regime_rows:
                regime, count, avg_fit, max_fit, min_fit = row
                print(
                    f"  {regime:12s}  Avg:{float(avg_fit):6.2f}  Max:{float(max_fit):6.2f}  Min:{float(min_fit):6.2f}  ({count} agents)"
                )

        print("\n🔷 PATTERN TESTING")
        print("-" * 40)
        print(f"  Total Patterns:    {pattern_row[0]:,}")
        print(f"  Patterns Tested:   {pattern_row[1]:,}")
        print(f"  Total Tests:       {pattern_row[2]:,}")
        print(f"  Avg Fitness:       {float(pattern_row[3]):.2f}")
        print(f"  Max Fitness:       {float(pattern_row[4]):.2f}")
        print(f"  50+ Fitness:       {pattern_row[5]:,} patterns")
        print(f"  70+ Fitness:       {pattern_row[6]:,} patterns")

        print("\n⚡ EVOLUTION CYCLES")
        print("-" * 40)
        print(f"  Cycles Completed:   {evo_row[0] if evo_row else 0}")
        print(f"  Latest Generation:  {evo_row[1] if evo_row and evo_row[1] else 0}")
        if evo_row and evo_row[2]:
            print(f"  Avg Duration:       {float(evo_row[2]):.1f}s")

        print("\n" + "=" * 70)

        await session.close()
        break


if __name__ == "__main__":
    asyncio.run(check_progress())
