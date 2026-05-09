"""
Pattern Discovery Service - Priority queue-based pattern testing.

This service implements the complete pattern testing flow:
1. Priority Queue: HIGH (fast-track) → NORMAL (active) → LOW (deprioritized)
2. Batch Backtest: V3-style random windows with LocalBacktestEngine
3. Fitness Calculation: V2 Signed Risk formula (no EV gate)
4. Tier Promotion: TIER 3 (untested) → TIER 2 (proven) → TIER 1 (elite)

Utilities are now local to Fast_Swarm (no external path dependencies).
"""

# Import local utilities (ported from Coinswarm-1/local-utilities)
from Fast_Swarm.utilities import (
    PatternDiscoveryScheduler,
    backtest_pattern_on_windows,
    generate_random_windows,
    get_prioritized_patterns,
    update_priority_after_backtest,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.pattern_models import Pattern


class PatternDiscoveryService:
    """Service for pattern discovery and priority-based testing."""

    async def run_batch_backtest(
        self,
        session: AsyncSession,
        batch_size: int = 50,
        priority_filter: str | None = None,
    ) -> dict:
        """
        Run batch backtest using priority queue.

        This is the main entry point that:
        1. Gets patterns from priority queue
        2. Runs batch backtest (random windows)
        3. Updates fitness and priority
        4. Promotes patterns to higher tiers

        Args:
            session: Database session
            batch_size: Number of patterns to test
            priority_filter: "high", "normal", "low", or None (all)

        Returns:
            Dict with backtest results
        """
        # Get patterns from priority queue
        include_low = priority_filter == "low" or priority_filter is None
        patterns = await get_prioritized_patterns(
            session,
            limit=batch_size,
            include_low=include_low,
        )

        if not patterns:
            return {
                "patterns_tested": 0,
                "message": "No patterns in priority queue",
            }

        # Generate random windows for testing (shared across patterns)
        assets = ["BTC", "ETH", "SOL"]
        timeframe = "1h"

        windows = await generate_random_windows(
            session,
            asset=assets[0],  # Start with BTC
            timeframe=timeframe,
            num_windows=20,
        )

        if not windows:
            return {
                "patterns_tested": 0,
                "error": "Could not generate test windows (insufficient data)",
            }

        # Run batch backtest (V3-style random windows)
        results = {}
        tested = 0

        for pattern in patterns:
            pid = pattern.get("pattern_id")
            try:
                # Test on multiple assets
                all_results = []
                for asset in assets:
                    asset_windows = await generate_random_windows(
                        session, asset=asset, timeframe=timeframe, num_windows=10
                    )
                    if asset_windows:
                        pattern_results = await backtest_pattern_on_windows(
                            session, pattern, asset_windows, asset, timeframe
                        )
                        all_results.extend(pattern_results)

                if all_results:
                    # Aggregate results
                    avg_fitness = sum(r.get("fitness_score", 0) for r in all_results) / len(all_results)
                    total_trades = sum(r.get("total_trades", 0) for r in all_results)

                    results[pid] = {
                        "fitness": avg_fitness,
                        "total_trades": total_trades,
                        "windows_tested": len(all_results),
                    }

                    # Update priority
                    await update_priority_after_backtest(
                        session,
                        pid,
                        new_runs=(pattern.get("total_runs") or 0) + len(all_results),
                        new_periods_tested=(pattern.get("periods_tested") or 0) + len(all_results),
                        new_fitness=avg_fitness,
                    )
                    tested += 1
                else:
                    results[pid] = {"error": "No results from backtest"}

            except Exception as e:
                results[pid] = {"error": str(e)}

        # Check for tier promotions
        promotions = await self._check_tier_promotions(session)

        return {
            "patterns_tested": tested,
            "total_patterns": len(patterns),
            "tier_promotions": promotions,
            "results": results,
        }

    async def run_discovery_cycle(
        self,
        session: AsyncSession,
    ) -> dict:
        """
        Run pattern discovery cycle (creates new patterns).

        Uses PatternDiscoveryScheduler to:
        1. Load chaos trades from PostgreSQL
        2. RandomForest extracts top 20 features
        3. LLM generates patterns
        4. Inserts with status='untested', origin='automated_discovery'

        Returns:
            Dict with discovery results
        """
        scheduler = PatternDiscoveryScheduler(interval_hours=6)
        result = await scheduler.run_discovery_cycle(session)

        return result.to_dict()

    async def _check_tier_promotions(self, session: AsyncSession) -> dict:
        """
        Check for patterns that should be promoted to higher tiers.

        Tier System:
        - TIER 3 (Untested): fitness = 0
        - TIER 2 (Proven): fitness 40-79
        - TIER 1 (Elite): fitness 80+

        Returns:
            Dict with promotion counts
        """
        # Get patterns that need tier updates
        result = await session.exec(select(Pattern).where(Pattern.is_active == True))
        patterns = result.all()

        promotions = {"to_tier_1": 0, "to_tier_2": 0}

        for pattern in patterns:
            fitness = pattern.fitness_score or 0
            current_tier = pattern.tier or 3

            # Promote to TIER 1 (Elite)
            if fitness >= 80 and current_tier != 1:
                pattern.tier = 1
                session.add(pattern)
                promotions["to_tier_1"] += 1

            # Promote to TIER 2 (Proven)
            elif fitness >= 40 and current_tier == 3:
                pattern.tier = 2
                session.add(pattern)
                promotions["to_tier_2"] += 1

        await session.commit()
        return promotions

    async def _run_in_thread(self, func, *args, **kwargs):
        """Run blocking function in thread pool."""
        import asyncio

        return await asyncio.to_thread(func, *args, **kwargs)
