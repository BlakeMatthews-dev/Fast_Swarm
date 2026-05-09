"""
Pattern Discovery Service - Priority queue-based pattern testing.

This service implements the complete pattern testing flow:
1. Priority Queue: HIGH (fast-track) → NORMAL (active) → LOW (deprioritized)
2. Batch Backtest: Uses pre-generated window pool (15K+ windows at startup)
3. Fitness Calculation: V2 Signed Risk formula (no EV gate)
4. Tier Promotion: TIER 3 (untested) → TIER 2 (proven) → TIER 1 (elite)

Utilities are now local to Fast_Swarm (no external path dependencies).
"""

# Import local utilities (ported from Coinswarm-1/local-utilities)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.local_agents.backtest.windows import get_windows_for_symbol, is_initialized
from Fast_Swarm.utilities import (
    PatternDiscoveryScheduler,
    backtest_pattern_on_windows,
    get_prioritized_patterns,
    update_priority_after_backtest,
)

from ..Models.pattern_models import Pattern


class PatternTestContext:
    """
    Shared context for pattern testing — created once, reused across all patterns.

    Holds the loader, config, traits, and pre-computed benchmarks.
    No database interaction after construction.
    """

    def __init__(self, preloaded_candles=None, benchmarks: dict = None):
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
        from Fast_Swarm.local_agents.backtest.engine import BacktestConfig
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        self.loader = OHLCVLoader()
        self.traits = AgentTraits()
        self.traits.min_threshold = 0.0  # No decision zone for pattern tests
        self.traits.ai_threshold = 0.0
        self.config = BacktestConfig.from_traits(self.traits)
        self.traits_dict = self.traits.__dict__
        self.preloaded_candles = preloaded_candles
        self.benchmarks = benchmarks or {}  # {(asset, timeframe, start_ts): float}


def _compute_pattern_on_windows(
    pattern_dict: dict,
    windows: list[dict],
    ctx: PatternTestContext,
) -> dict:
    """
    Pure computation: run one pattern against all windows.

    No database interaction. Uses shared context (loader, config, candles).
    Returns dict with aggregated metrics + collected trade records.
    """
    import json
    from datetime import datetime

    from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine
    from Fast_Swarm.local_agents.core.state import AgentRecord
    from Fast_Swarm.utilities.pattern_backtest import calculate_metrics_for_trades

    pattern_id = pattern_dict.get("pattern_id", "unknown")
    entry_str = pattern_dict.get("entry_conditions", "[]")
    exit_str = pattern_dict.get("exit_conditions", "{}")

    entry_conditions = json.loads(entry_str) if isinstance(entry_str, str) else entry_str
    exit_config = json.loads(exit_str) if isinstance(exit_str, str) else exit_str

    if not entry_conditions:
        return {"pattern_id": pattern_id, "total_trades": 0, "windows_tested": 0, "runs": len(windows), "trades": []}

    # Create engine once for this pattern (reused across windows)
    engine_patterns = {
        pattern_id: {
            "pattern_id": pattern_id,
            "entry_conditions": entry_conditions,
            "exit_conditions": exit_config,
        }
    }

    test_agent = AgentRecord(
        agent_id=f"pattern_test_{pattern_id}",
        agent_name=f"Test_{pattern_id[:20]}",
        traits=ctx.traits_dict,
        pattern_ids=[pattern_id],
        pattern_weights={pattern_id: 1.0},
    )

    engine = LocalBacktestEngine(
        loader=ctx.loader, config=ctx.config, patterns=engine_patterns,
        preloaded_candles=ctx.preloaded_candles,
    )

    all_metrics = []
    all_trades = []

    for window in windows:
        try:
            asset = window.get("asset", "BTC")
            timeframe = window.get("timeframe", "1h")

            trades = engine.run(
                agent=test_agent,
                dataset={
                    "assets": [asset],
                    "timeframe": timeframe,
                    "start_ts": window["start_ts"],
                    "end_ts": window["end_ts"],
                },
            )

            # Get benchmark for this window (buy-and-hold return)
            benchmark_key = (asset, timeframe, window["start_ts"])
            benchmark = ctx.benchmarks.get(benchmark_key, None)

            if not trades:
                # Pattern didn't trade = held cash = 0% return
                # Alpha = 0% - benchmark (credit for avoiding crashes, penalty for missing rallies)
                if benchmark is not None:
                    sit_out_alpha = -benchmark  # Positive when market dropped, negative when it rallied
                    # Fitness for sitting out: based on alpha only (no trades to evaluate risk metrics)
                    # Capped alpha contribution: 40% weight in fitness formula
                    sit_out_fitness = max(0, min(100, (min(100, max(-100, sit_out_alpha)) / 100) * 40))
                    all_metrics.append({
                        "pattern_id": pattern_id,
                        "asset": asset,
                        "timeframe": timeframe,
                        "regime": window.get("regime", "random"),
                        "total_trades": 0,
                        "fitness_score": sit_out_fitness,
                        "alpha_pct": sit_out_alpha,
                        "total_pnl_pct": 0,
                        "win_rate": 0,
                        "sortino_ratio": 0,
                        "sharpe_ratio": 0,
                        "max_drawdown_pct": 0,
                        "calmar_ratio": 0,
                        "expectancy_pct": 0,
                    })
                continue

            all_trades.extend(trades)
            trade_dicts = [{"pnl_pct": t.pnl_pct} for t in trades if hasattr(t, "pnl_pct")]
            if not trade_dicts:
                continue

            metrics = calculate_metrics_for_trades(
                trade_dicts,
                benchmark_return_pct=benchmark or 0.0,
                window_name=window.get("name", "unknown"),
                window_days=window.get("days", 0),
            )
            metrics["pattern_id"] = pattern_id
            metrics["asset"] = asset
            metrics["timeframe"] = timeframe
            metrics["regime"] = window.get("regime", "random")
            all_metrics.append(metrics)

        except Exception as e:
            print(f"[PatternTest] Window error for {pattern_id[:8]}: {e}")

    if not all_metrics:
        return {"pattern_id": pattern_id, "total_trades": 0, "windows_tested": 0, "runs": len(windows), "trades": all_trades}

    # Aggregate across windows
    n = len(all_metrics)
    return {
        "pattern_id": pattern_id,
        "fitness": sum(r.get("fitness_score", 0) for r in all_metrics) / n,
        "total_trades": sum(r.get("total_trades", 0) for r in all_metrics),
        "windows_tested": n,
        "runs": n,
        "win_rate": sum(r.get("win_rate", 0) for r in all_metrics) / n,
        "alpha_pct": sum(r.get("alpha_pct", 0) for r in all_metrics) / n,
        "sortino_ratio": sum(r.get("sortino_ratio", 0) for r in all_metrics) / n,
        "max_drawdown_pct": sum(r.get("max_drawdown_pct", 0) for r in all_metrics) / n,
        "total_roi_pct": sum(r.get("total_pnl_pct", 0) for r in all_metrics),
        "sharpe_ratio": sum(r.get("sharpe_ratio", 0) for r in all_metrics) / n,
        "calmar_ratio": sum(r.get("calmar_ratio", 0) for r in all_metrics) / n,
        "expectancy_pct": sum(r.get("expectancy_pct", 0) for r in all_metrics) / n,
        "trades": all_trades,  # Raw trade records for batch persistence
    }


def _apply_result_to_pattern(pattern, result: dict):
    """Apply computed metrics to a pattern model object (no DB write)."""
    from datetime import datetime

    if result.get("total_trades", 0) > 0:
        pattern.fitness_score = result.get("fitness")
        pattern.total_trades = (pattern.total_trades or 0) + result.get("total_trades", 0)
        pattern.win_rate = result.get("win_rate")
        pattern.alpha_pct = result.get("alpha_pct")
        pattern.sortino_ratio = result.get("sortino_ratio")
        pattern.max_drawdown_pct = result.get("max_drawdown_pct")
        pattern.total_roi_pct = result.get("total_roi_pct")
        if result.get("sharpe_ratio"):
            pattern.sharpe_ratio = result["sharpe_ratio"]
        if result.get("calmar_ratio"):
            pattern.calmar_ratio = result["calmar_ratio"]
        if result.get("expectancy_pct"):
            pattern.expectancy_pct = result["expectancy_pct"]

    pattern.total_runs = (pattern.total_runs or 0) + result.get("runs", 1)
    pattern.periods_tested = (pattern.periods_tested or 0) + result.get("runs", 1)
    pattern.last_backtest_at = datetime.utcnow()


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

        import time
        batch_start = time.time()
        print(f"[PatternBacktest] Testing {len(patterns)} patterns across 3 assets...")

        # Use pre-generated window pool (loaded at server startup)
        assets = ["BTC", "ETH", "SOL"]
        windows_per_asset = 10

        if not is_initialized():
            print("[PatternBacktest] ERROR: Window pool not initialized!")
            return {
                "patterns_tested": 0,
                "error": "Window pool not initialized - restart server",
            }

        # Grab windows from the pre-generated pool (instant, no DB queries)
        print(f"[PatternBacktest] Sampling {windows_per_asset} windows per asset from pool...")
        windows_by_asset = {}
        for asset in assets:
            # Convert Window objects to dicts for backtest_pattern_on_windows
            pool_windows = get_windows_for_symbol(asset, count=windows_per_asset)
            if pool_windows:
                windows_by_asset[asset] = [
                    {"start_ts": w.start_ts, "end_ts": w.end_ts, "symbol": w.symbol, "timeframe": w.timeframe}
                    for w in pool_windows
                ]
                print(f"[PatternBacktest]   {asset}: {len(pool_windows)} windows")
            else:
                print(f"[PatternBacktest]   {asset}: NO WINDOWS IN POOL")

        if not windows_by_asset:
            print("[PatternBacktest] ERROR: No windows in pool for any asset")
            return {
                "patterns_tested": 0,
                "error": "No windows in pool for target assets",
            }

        total_windows = sum(len(w) for w in windows_by_asset.values())
        print(f"[PatternBacktest] Ready: {total_windows} windows from pool")

        # Run batch backtest (V3-style random windows)
        results = {}
        tested = 0

        for idx, pattern in enumerate(patterns):
            pid = pattern.get("pattern_id")
            pattern_start = time.time()
            print(f"[PatternBacktest] [{idx + 1}/{len(patterns)}] Testing {pid[:16]}...", end=" ", flush=True)
            try:
                # Test on multiple assets using PRE-GENERATED windows
                # Each window already has its own timeframe from the pool
                all_results = []
                for asset, asset_windows in windows_by_asset.items():
                    for window in asset_windows:
                        try:
                            window_results = await backtest_pattern_on_windows(
                                session, pattern, [window], asset, window["timeframe"]
                            )
                            all_results.extend(window_results)
                        except Exception as win_err:
                            # Rollback so session stays usable for next window
                            try:
                                await session.rollback()
                            except Exception:
                                pass

                pattern_elapsed = time.time() - pattern_start
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
                    print(f"fitness={avg_fitness:.1f}, trades={total_trades}, windows={len(all_results)} ({pattern_elapsed:.1f}s)")
                else:
                    print(f"0 trades, 0 windows ({pattern_elapsed:.1f}s)")
                    results[pid] = {"total_trades": 0, "windows_tested": 0}

            except Exception as e:
                print(f"ERROR: {e}")
                try:
                    await session.rollback()
                except Exception:
                    pass
                results[pid] = {"error": str(e)}

        # Check for tier promotions
        batch_elapsed = time.time() - batch_start
        print("[PatternBacktest] Checking tier promotions...")
        promotions = await self._check_tier_promotions(session)

        print(f"[PatternBacktest] DONE: {tested}/{len(patterns)} patterns tested in {batch_elapsed:.1f}s")
        if promotions:
            print(f"[PatternBacktest] Tier promotions: {promotions}")

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
        result = await session.exec(select(Pattern).where(Pattern.is_active.is_(True)))
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

    def compute_pattern_results(
        self,
        pattern,
        windows: list[dict],
        ctx: "PatternTestContext",
    ) -> dict:
        """
        Pure computation: test a pattern on windows, return results.

        No database interaction. Uses shared PatternTestContext.

        Args:
            pattern: Pattern model object (read-only)
            windows: List of window dicts
            ctx: Shared context with loader, config, benchmarks, candle cache

        Returns:
            Dict with computed metrics + raw trades (caller persists)
        """
        import time

        pattern_start = time.time()
        pid = pattern.pattern_id

        if windows:
            w = windows[0]
            window_summary = f"{w.get('asset', '?')}/{w.get('timeframe', '?')}"
            if len(windows) > 1:
                window_summary += f" (+{len(windows)-1} more)"
            print(f"[PatternTest] {pid[:8]}: testing on {window_summary}...")

        pattern_dict = {
            "pattern_id": pattern.pattern_id,
            "entry_conditions": pattern.entry_conditions,
            "exit_conditions": pattern.exit_conditions,
        }

        result = _compute_pattern_on_windows(pattern_dict, windows, ctx)
        pattern_elapsed = time.time() - pattern_start

        trades = result.get("total_trades", 0)
        if trades > 0:
            window_info = ""
            if windows:
                w = windows[0]
                window_info = f"{w.get('asset', '?')}/{w.get('timeframe', '?')} ({w.get('regime', '?')})"
            print(
                f"[PatternTest] {pid[:8]}: "
                f"fitness={result.get('fitness', 0):.1f}, trades={trades}, "
                f"α={result.get('alpha_pct', 0):+.1f}%, sortino={result.get('sortino_ratio', 0):.2f}, "
                f"DD={result.get('max_drawdown_pct', 0):.1f}%, WR={result.get('win_rate', 0):.0f}%, "
                f"PnL={result.get('total_roi_pct', 0):+.1f}% | {window_info} ({pattern_elapsed:.1f}s)"
            )
        else:
            window_info = ""
            if windows:
                w = windows[0]
                window_info = f" | {w.get('asset', '?')}/{w.get('timeframe', '?')}"
            print(f"[PatternTest] {pid[:8]}: 0 trades, 0 windows{window_info} ({pattern_elapsed:.1f}s)")

        return result

    # Backward-compatible wrapper for non-orchestrator callers
    async def test_pattern_on_windows(self, session, pattern, windows, preloaded_candles=None):
        """Legacy wrapper that computes + persists in one call."""
        ctx = PatternTestContext(preloaded_candles=preloaded_candles)
        result = self.compute_pattern_results(pattern, windows, ctx)
        _apply_result_to_pattern(pattern, result)
        session.add(pattern)
        return result

    async def _run_in_thread(self, func, *args, **kwargs):
        """Run blocking function in thread pool."""
        import asyncio

        return await asyncio.to_thread(func, *args, **kwargs)
