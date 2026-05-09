"""
Agent Backtest Service - Run backtests for agents.

This service handles backtesting agents using the LocalBacktestEngine.
Updates agent stats (fitness, sharpe, etc.) in the database.
All data comes from PostgreSQL enhanced_candles table (5.2M+ rows).
"""

import random
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

# Add local_agents to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "local_agents"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader, preload_candles_for_windows
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.canonical_periods import (
    REGIMES,
    get_canonical_periods_for_backtesting,
)
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.shared.llm_client import AIZoneMode

from ...Trades.Services.trade_service import persist_trades
from ..Models.agent_models import Agent
from .fitness_service import TradeData, calculate_fitness


class AgentBacktestService:
    """Service for backtesting agents using PostgreSQL data."""

    # Random window generation settings - HUNDREDS of windows for robust testing
    WINDOWS_PER_ASSET_PER_TF = 20  # Windows per asset per timeframe

    # Regime importance weights for weighted fitness calculation
    # Higher weights = harder market conditions worth more in fitness
    REGIME_WEIGHTS = {
        # Random windows (baseline difficulty)
        "random_1m": 1.0,
        "random_5m": 1.0,
        "random_15m": 1.0,
        "random_1h": 1.0,
        "random_4h": 1.0,
        "random_1d": 1.0,
        # Canonical periods (varying difficulty)
        "bull": 0.5,  # Everyone can win in a bull market
        "bear": 2.0,  # Harder to profit when prices fall
        "crash": 3.0,  # Survival is critical - highest weight
        "sideways": 2.5,  # Market spends most time here, hard to profit
        "blowoff": 1.5,  # Volatility spike before reversal
        "recovery": 1.5,  # Catching the bounce
        "volatile": 2.0,  # High uncertainty
        "winter": 2.0,  # Extended bear
        "transition": 1.5,  # Regime change
    }

    # Timeframes to test with window sizes (candles per window)
    TIMEFRAME_CONFIG = {
        "1m": {"candles": 1440, "label": "1d"},  # 1440 1m = 1 day
        "5m": {"candles": 576, "label": "2d"},  # 576 5m = 2 days
        "15m": {"candles": 384, "label": "4d"},  # 384 15m = 4 days
        "1h": {"candles": 500, "label": "21d"},  # 500 1h = ~21 days
        "4h": {"candles": 180, "label": "30d"},  # 180 4h = 30 days
        "1d": {"candles": 90, "label": "90d"},  # 90 1d = 90 days
    }

    # Default timeframes to use if none specified
    # All timeframes for comprehensive coverage (random_1m, random_5m, etc.)
    DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

    def __init__(self):
        """
        Initialize backtest service.

        Data is loaded from PostgreSQL enhanced_candles table (5.2M+ rows)
        via the OHLCVLoader which queries the database directly.
        """
        # OHLCVLoader now uses PostgreSQL - no file path needed
        self.loader = OHLCVLoader()

    async def _generate_random_windows(
        self, session: AsyncSession, assets: list[str], timeframes: list[str] = None
    ) -> list[dict]:
        """
        Generate random backtest windows for each asset across multiple timeframes.

        Returns list of windows with start_ts/end_ts/timeframe for diverse testing.
        With 8 assets × 4 timeframes × 20 windows = 640 windows per backtest!

        OPTIMIZED: Uses single batched query instead of 48 separate queries.
        """
        from sqlalchemy import text

        windows = []
        timeframes = timeframes or self.DEFAULT_TIMEFRAMES

        # Timeframe to milliseconds
        tf_ms = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }

        # BATCHED QUERY: Get data ranges for ALL asset/timeframe combos in ONE query
        try:
            result = await session.execute(
                text("""
                    SELECT
                        symbol,
                        timeframe,
                        EXTRACT(EPOCH FROM MIN(time)) * 1000 as min_ts,
                        EXTRACT(EPOCH FROM MAX(time)) * 1000 as max_ts,
                        COUNT(*) as candle_count
                    FROM enhanced_candles
                    WHERE symbol = ANY(:assets) AND timeframe = ANY(:timeframes)
                    GROUP BY symbol, timeframe
                """),
                {"assets": assets, "timeframes": timeframes},
            )
            rows = result.fetchall()
        except Exception as e:
            print(f"[Backtest] Batched range query failed: {e}")
            return windows

        # Build lookup table: (asset, timeframe) -> (min_ts, max_ts, count)
        data_ranges = {}
        for row in rows:
            symbol, tf, min_ts, max_ts, count = row
            if min_ts is not None and max_ts is not None:
                data_ranges[(symbol, tf)] = (int(min_ts), int(max_ts), int(count or 0))

        # Generate random windows for each asset/timeframe with available data
        for timeframe in timeframes:
            if timeframe not in self.TIMEFRAME_CONFIG:
                continue

            config = self.TIMEFRAME_CONFIG[timeframe]
            window_candles = config["candles"]
            window_ms = window_candles * tf_ms.get(timeframe, 3_600_000)

            for asset in assets:
                key = (asset, timeframe)
                if key not in data_ranges:
                    continue

                min_ts, max_ts, candle_count = data_ranges[key]
                available_range = max_ts - min_ts - window_ms

                # Skip if not enough data
                if available_range <= 0 or candle_count < window_candles:
                    continue

                # Generate random windows for this asset/timeframe
                for _ in range(self.WINDOWS_PER_ASSET_PER_TF):
                    start_ts = min_ts + random.randint(0, int(available_range))
                    end_ts = start_ts + window_ms
                    windows.append(
                        {
                            "asset": asset,
                            "timeframe": timeframe,
                            "start_ts": start_ts,
                            "end_ts": end_ts,
                            "regime": f"random_{timeframe}",
                        }
                    )

        return windows

    async def _get_all_test_windows(
        self,
        session: AsyncSession,
        assets: list[str],
        timeframes: list[str] = None,
        include_canonical: bool = True,
    ) -> list[dict]:
        """
        Get ALL test windows: random windows + canonical periods.

        This ensures agents are tested on:
        1. Random windows across all timeframes (diverse market conditions)
        2. Canonical periods (FTX collapse, COVID crash, 2017 bull, etc.)

        Returns windows grouped by regime for per-regime fitness tracking.
        """
        all_windows = []

        # 1. Generate random windows across timeframes
        random_windows = await self._generate_random_windows(session, assets, timeframes)
        all_windows.extend(random_windows)

        # 2. Add canonical periods (historical events)
        if include_canonical:
            # Get canonical periods for these assets
            # Filter to available timeframes (default to 1h which has best coverage)
            canonical_timeframes = timeframes or ["1h"]
            # Use only 1h for canonical periods - they're defined by dates, not candle counts
            canonical_tf = "1h" if "1h" in canonical_timeframes else canonical_timeframes[0]

            canonical = get_canonical_periods_for_backtesting(
                assets=assets,
                timeframes=[canonical_tf],
                regimes=None,  # All regimes: crash, bull, bear, blowoff, recovery, sideways
            )

            # Convert to window format
            for period in canonical:
                all_windows.append(
                    {
                        "asset": period["asset"],
                        "timeframe": period["timeframe"],
                        "start_ts": period["start_ts"],
                        "end_ts": period["end_ts"],
                        "regime": period["regime"],  # crash, bull, bear, etc.
                        "period_name": period["name"],
                        "description": period.get("description", ""),
                    }
                )

            print(
                f"[Backtest] Added {len(canonical)} canonical periods across {len(REGIMES)} regimes: "
                f"{', '.join(REGIMES)}"
            )

        # Summary
        regime_counts = {}
        for w in all_windows:
            regime = w.get("regime", "unknown")
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        print(f"[Backtest] Total test windows: {len(all_windows)}")
        regime_summary = ", ".join(f"{r}:{c}" for r, c in sorted(regime_counts.items()))
        print(f"[Backtest] By regime: {regime_summary}")

        return all_windows

    async def backtest_agents(
        self,
        session: AsyncSession,
        agent_ids: list[str],
        assets: list[str] = None,
        timeframe: str = "1h",
        history_bars: int = 500,
        canonical_periods: list[dict] = None,
    ) -> dict[str, dict]:
        """
        Run backtests for multiple agents.

        Args:
            session: Database session
            agent_ids: List of agent IDs to backtest
            assets: List of assets to test (default: BTC/USDT, ETH/USDT, SOL/USDT)
            timeframe: Timeframe for backtesting
            history_bars: Number of historical bars to use
            canonical_periods: Optional list of canonical periods with regime labels.
                Each dict should have: {regime, asset, start_ts, end_ts}
                Example: [{"regime": "crash", "asset": "BTC", "start_ts": 1583625600000, "end_ts": 1584230400000}]

        Returns:
            Dict mapping agent_id to backtest results
        """
        if assets is None:
            assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        results = {}

        # Get agents from DB
        result = await session.exec(select(Agent).where(Agent.agent_id.in_(agent_ids)))
        agents = result.all()

        # Get patterns from DB
        from ...Patterns.Models.pattern_models import Pattern

        pattern_result = await session.exec(select(Pattern).where(Pattern.is_active == True))
        patterns = pattern_result.all()

        # Build pattern lookup
        pattern_lookup = {
            p.pattern_id: {
                "pattern_id": p.pattern_id,
                "entry_conditions": p.entry_conditions,
                "exit_conditions": p.exit_conditions,
            }
            for p in patterns
        }

        # OPTIMIZATION: Get windows and preload data ONCE for all agents
        clean_assets = [a.replace("/USDT", "").replace("-USD", "") for a in assets]
        all_windows = await self._get_all_test_windows(
            session,
            assets=clean_assets,
            timeframes=self.DEFAULT_TIMEFRAMES,
            include_canonical=True,
        )

        # Preload candle data for all windows (avoids repeated DB queries)
        preloaded_candles = {}
        if all_windows:
            # Convert windows to format expected by preload function
            from dataclasses import dataclass

            @dataclass
            class WindowAdapter:
                symbol: str
                timeframe: str
                start_ts: int
                end_ts: int

            window_adapters = [
                WindowAdapter(
                    symbol=w["asset"],
                    timeframe=w.get("timeframe", timeframe),
                    start_ts=w["start_ts"],
                    end_ts=w["end_ts"],
                )
                for w in all_windows
            ]

            print(f"[Backtest] Preloading data for {len(all_windows)} windows...")
            preloaded_candles = preload_candles_for_windows(window_adapters, self.loader)
            print(f"[Backtest] Preloaded {len(preloaded_candles)} asset/timeframe pairs")

        for agent in agents:
            try:
                # Get agent's patterns - handle both old (list) and new (dict) formats
                agent_patterns = []
                assigned = agent.assigned_patterns or {}

                # Extract pattern IDs from assigned_patterns
                if isinstance(assigned, dict):
                    # New format: {"base": [...], "situational": [...]}
                    base_patterns = assigned.get("base", [])
                    for p in base_patterns:
                        if isinstance(p, str):
                            # Old: just pattern ID
                            if p in pattern_lookup:
                                agent_patterns.append(pattern_lookup[p])
                        elif isinstance(p, dict):
                            # New: full pattern dict - use it directly if has conditions
                            pid = p.get("pattern_id", p.get("id", ""))
                            if p.get("entry_conditions") and p.get("exit_conditions"):
                                agent_patterns.append(p)
                            elif pid in pattern_lookup:
                                agent_patterns.append(pattern_lookup[pid])
                elif isinstance(assigned, list):
                    # Legacy format: just a list of pattern IDs
                    for pattern_id in assigned:
                        if pattern_id in pattern_lookup:
                            agent_patterns.append(pattern_lookup[pattern_id])

                if not agent_patterns:
                    print(f"Agent {agent.agent_id} has no valid patterns, skipping")
                    continue

                # Create backtest config from agent traits
                # Note: from_traits() computes stop_loss, take_profit, position_size from traits
                traits_dict = agent.traits if isinstance(agent.traits, dict) else agent.traits.__dict__

                # Filter to known AgentTraits fields (some old agents have deprecated fields)
                from dataclasses import fields as dataclass_fields

                known_fields = {f.name for f in dataclass_fields(AgentTraits)}
                filtered_traits = {k: v for k, v in traits_dict.items() if k in known_fields}

                agent_traits = AgentTraits(**filtered_traits)
                config = BacktestConfig.from_traits(agent_traits)

                # Build pattern dict for engine
                pattern_dict = {p["pattern_id"]: p for p in agent_patterns}

                # Create AgentRecord for the backtest engine
                agent_record = AgentRecord(
                    agent_id=agent.agent_id,
                    agent_name=agent.name,
                    generation=agent.generation,
                    traits=traits_dict,
                    pattern_ids=[p["pattern_id"] for p in agent_patterns],
                    pattern_weights=agent.pattern_weights or {},
                    trading_philosophy=agent.trading_philosophy or "",
                )

                # Create backtest engine with patterns, preloaded data, and LLM for uncertainty zone
                engine = LocalBacktestEngine(
                    loader=self.loader,
                    config=config,
                    patterns=pattern_dict,
                    ai_zone_mode=AIZoneMode.LLM,  # Use Ollama for AI decisions in uncertainty zone
                    preloaded_candles=preloaded_candles,  # OPTIMIZATION: Reuse preloaded data
                )

                # Run backtests using preloaded windows (generated once for all agents)
                # OPTIMIZED: Calculate metrics at window level, aggregate up (avoids O(n²) trade storage)
                all_trades = []  # Only for persistence, not metrics
                window_metrics = []  # Store per-window metrics for aggregation

                if all_windows:
                    # Summarize window distribution
                    regime_counts = {}
                    for w in all_windows:
                        regime = w.get("regime", "unknown")
                        regime_counts[regime] = regime_counts.get(regime, 0) + 1
                    regime_summary = ", ".join(f"{r}:{c}" for r, c in sorted(regime_counts.items()))
                    print(f"[Backtest] Agent {agent.agent_id}: Testing {len(all_windows)} windows [{regime_summary}]")

                    # Run backtest for each window - calculate metrics IMMEDIATELY per window
                    for window in all_windows:
                        window_tf = window.get("timeframe", timeframe)
                        dataset = {
                            "assets": [window["asset"]],
                            "timeframe": window_tf,
                            "start_ts": window["start_ts"],
                            "end_ts": window["end_ts"],
                        }
                        window_trades = engine.run(agent=agent_record, dataset=dataset)

                        # Keep trades only for persistence (not for re-calculating metrics)
                        all_trades.extend(window_trades)

                        # Normalize regime name (collapse random_1m, random_1h to "random")
                        raw_regime = window.get("regime", f"random_{window_tf}")
                        regime = "random" if raw_regime.startswith("random_") else raw_regime

                        # Calculate metrics for THIS WINDOW immediately (O(1) per window)
                        w_metrics = self._calculate_metrics(window_trades)
                        window_metrics.append(
                            {
                                "regime": regime,
                                "timeframe": window_tf,
                                "trades": len(window_trades),
                                "fitness": w_metrics.get("fitness_score", 0.0),
                                "sharpe": w_metrics.get("sharpe_ratio"),
                                "win_rate": w_metrics.get("win_rate"),
                                "roi": w_metrics.get("annualized_roi_pct", 0.0),
                                "pnl": w_metrics.get("total_pnl", 0.0),
                            }
                        )
                else:
                    # Fallback: full dataset (shouldn't happen)
                    print(f"[Backtest] Agent {agent.agent_id}: No windows generated, using full dataset")
                    all_trades = engine.run(
                        agent=agent_record, dataset={"assets": clean_assets, "timeframe": timeframe}
                    )
                    w_metrics = self._calculate_metrics(all_trades)
                    window_metrics.append(
                        {
                            "regime": "full",
                            "timeframe": timeframe,
                            "trades": len(all_trades),
                            "fitness": w_metrics.get("fitness_score", 0.0),
                            "sharpe": w_metrics.get("sharpe_ratio"),
                            "win_rate": w_metrics.get("win_rate"),
                            "roi": w_metrics.get("annualized_roi_pct", 0.0),
                            "pnl": w_metrics.get("total_pnl", 0.0),
                        }
                    )

                # Persist trades to backtest_trades_unified table
                if all_trades:
                    try:
                        trades_persisted = await persist_trades(
                            session,
                            all_trades,
                            source="evolution_backtest",
                            timeframe=timeframe,
                        )
                        if trades_persisted == 0 and len(all_trades) > 0:
                            print(
                                f"[Backtest] WARNING: Agent {agent.agent_id} generated {len(all_trades)} trades "
                                f"but 0 were persisted. Check [Trade Persist] logs above for details."
                            )
                        elif trades_persisted < len(all_trades):
                            print(
                                f"[Backtest] PARTIAL: Agent {agent.agent_id}: Only {trades_persisted}/{len(all_trades)} "
                                f"trades persisted. Check [Trade Persist] logs for failures."
                            )
                        else:
                            print(
                                f"[Backtest] Agent {agent.agent_id}: Persisted {trades_persisted} trades to backtest_trades_unified"
                            )
                    except Exception as persist_error:
                        print(
                            f"[Backtest] TRADE PERSIST FAILED for agent {agent.agent_id}: "
                            f"{type(persist_error).__name__}: {persist_error}"
                        )
                        print(f"[Backtest] Trade count that failed: {len(all_trades)}")
                        # Don't fail the whole backtest - agent metrics are still valid
                else:
                    print(
                        f"[Backtest] Agent {agent.agent_id}: No trades generated (patterns may not have matched any candles)"
                    )

                # AGGREGATE: Calculate overall metrics from window-level data
                # This is O(windows) not O(trades) - much faster
                total_trades = sum(w["trades"] for w in window_metrics)
                total_pnl = sum(w["pnl"] for w in window_metrics)

                # Weighted average for ratios (weight by trade count)
                valid_windows = [w for w in window_metrics if w["trades"] > 0]
                if valid_windows:
                    total_w = sum(w["trades"] for w in valid_windows)
                    avg_fitness = sum(w["fitness"] * w["trades"] for w in valid_windows) / total_w
                    avg_win_rate = sum((w["win_rate"] or 0) * w["trades"] for w in valid_windows) / total_w
                    # Sharpe: average across windows (each window is independent experiment)
                    sharpe_windows = [w for w in valid_windows if w["sharpe"] is not None]
                    avg_sharpe = (
                        sum(w["sharpe"] for w in sharpe_windows) / len(sharpe_windows) if sharpe_windows else None
                    )
                    avg_roi = sum(w["roi"] * w["trades"] for w in valid_windows) / total_w
                else:
                    avg_fitness = 0.0
                    avg_win_rate = None
                    avg_sharpe = None
                    avg_roi = 0.0

                metrics = {
                    "total_trades": total_trades,
                    "fitness_score": avg_fitness,
                    "sharpe_ratio": avg_sharpe,
                    "win_rate": avg_win_rate,
                    "annualized_roi_pct": avg_roi,
                    "total_pnl": total_pnl,
                    # Note: sortino/calmar/max_drawdown require trade-level data, computed below if needed
                    "sortino_ratio": None,
                    "calmar_ratio": None,
                    "max_drawdown_pct": 0.0,
                }

                # AGGREGATE by regime: group window metrics, average
                fitness_by_regime = {}
                unique_regimes = {w["regime"] for w in window_metrics}
                for regime in unique_regimes:
                    regime_windows = [w for w in window_metrics if w["regime"] == regime and w["trades"] > 0]
                    regime_trades = sum(w["trades"] for w in regime_windows)
                    if regime_trades >= 5:  # Minimum for statistical significance
                        regime_total = sum(w["trades"] for w in regime_windows)
                        fitness_by_regime[regime] = {
                            "fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
                            "trades": regime_trades,
                            "win_rate": sum((w["win_rate"] or 0) * w["trades"] for w in regime_windows) / regime_total,
                            "sharpe": sum(w["sharpe"] or 0 for w in regime_windows) / len(regime_windows),
                            "roi": sum(w["roi"] * w["trades"] for w in regime_windows) / regime_total,
                        }

                if fitness_by_regime:
                    regime_str = ", ".join(f"{r}={d['fitness']:.1f}" for r, d in fitness_by_regime.items())
                    print(f"[Backtest] Agent {agent.agent_id}: Per-regime fitness: {regime_str}")

                # Calculate weighted fitness if we have per-regime data
                # This prioritizes crash/sideways/bear performance over bull market gains
                base_fitness = metrics.get("fitness_score", 0.0)
                if fitness_by_regime:
                    weighted_fitness = self._calculate_weighted_fitness(fitness_by_regime, base_fitness)
                    weight_diff = weighted_fitness - base_fitness
                    if abs(weight_diff) > 1.0:  # Only log significant changes
                        print(
                            f"[Backtest] Agent {agent.agent_id}: Weighted fitness: {weighted_fitness:.1f} "
                            f"(base: {base_fitness:.1f}, delta: {weight_diff:+.1f})"
                        )
                    final_fitness = weighted_fitness
                else:
                    final_fitness = base_fitness

                # AGGREGATE 2D fitness matrix (regime × timeframe) for heatmap display
                fitness_matrix = {}
                for regime in unique_regimes:
                    regime_windows = [w for w in window_metrics if w["regime"] == regime]
                    unique_tfs = {w["timeframe"] for w in regime_windows}
                    fitness_matrix[regime] = {}
                    for tf in unique_tfs:
                        tf_windows = [w for w in regime_windows if w["timeframe"] == tf and w["trades"] > 0]
                        tf_trades = sum(w["trades"] for w in tf_windows)
                        if tf_trades >= 3:  # Lower threshold for matrix cells
                            tf_total = sum(w["trades"] for w in tf_windows)
                            fitness_matrix[regime][tf] = round(
                                sum(w["fitness"] * w["trades"] for w in tf_windows) / tf_total, 1
                            )

                # Update agent in DB
                agent.fitness_score = final_fitness
                agent.sharpe_ratio = metrics.get("sharpe_ratio")
                agent.sortino_ratio = metrics.get("sortino_ratio")
                agent.calmar_ratio = metrics.get("calmar_ratio")
                agent.max_drawdown_pct = metrics.get("max_drawdown_pct", 0.0)
                agent.annualized_roi_pct = metrics.get("annualized_roi_pct", 0.0)
                agent.win_rate = metrics.get("win_rate")
                agent.total_trades = metrics.get("total_trades", 0)
                agent.winning_trades = metrics.get("winning_trades", 0)
                agent.total_pnl = metrics.get("total_pnl", 0.0)
                agent.fitness_by_regime = fitness_by_regime  # Store per-regime breakdown
                agent.fitness_matrix = fitness_matrix  # Store 2D matrix for heatmap
                agent.backtest_count = (agent.backtest_count or 0) + 1
                agent.last_backtest_at = datetime.utcnow()

                session.add(agent)
                metrics["fitness_by_regime"] = fitness_by_regime  # Include in results
                results[agent.agent_id] = metrics

            except Exception as e:
                import traceback

                print(f"[Backtest] ERROR for agent {agent.agent_id}: {type(e).__name__}: {e}")
                print(
                    f"[Backtest] Agent details: generation={agent.generation}, "
                    f"patterns={len(agent_patterns) if 'agent_patterns' in dir() else 'N/A'}, "
                    f"traits_count={len(traits_dict) if 'traits_dict' in dir() else 'N/A'}"
                )
                traceback.print_exc()
                results[agent.agent_id] = {"error": str(e), "error_type": type(e).__name__}
                continue

        await session.commit()
        return results

    def _calculate_metrics(self, trades: list) -> dict:
        """Calculate performance metrics from trades."""
        if not trades:
            return {
                "total_trades": 0,
                "fitness_score": 0.0,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "calmar_ratio": None,
                "max_drawdown_pct": 0.0,
                "annualized_roi_pct": 0.0,
                "win_rate": None,
                "total_pnl": 0.0,
                "avg_trade_pct": 0.0,
            }

        # Calculate basic stats
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.pnl_pct is not None and t.pnl_pct > 0)
        win_rate = wins / total_trades if total_trades > 0 else 0

        # Calculate PnL - Filtering non-finite and Null values to ensure numerical stability
        import math

        finite_trades = [t for t in trades if t.pnl_pct is not None and math.isfinite(t.pnl_pct)]
        if len(finite_trades) < len(trades):
            print(f"[WARNING] Filtered {len(trades) - len(finite_trades)} invalid trades (Inf/NaN/Null) for stability")

        total_pnl = sum(t.pnl_pct for t in finite_trades)
        avg_pnl = total_pnl / len(finite_trades) if finite_trades else 0

        # Calculate returns for Sharpe/Sortino
        returns = [t.pnl_pct for t in finite_trades]

        # Sharpe ratio (simplified)
        import statistics

        if len(returns) > 1:
            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe_raw = (mean_return / std_return) if std_return > 0 else 0
            # Cap at ±6 to filter calculation anomalies while allowing exceptional strategies
            sharpe = max(-6.0, min(6.0, sharpe_raw))
        else:
            sharpe = None

        # Sortino ratio (downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) > 1:
            downside_std = statistics.stdev(downside_returns)
            sortino = (avg_pnl / downside_std) if downside_std > 0 else 0
        else:
            sortino = None

        # Max drawdown (simplified - running equity curve)
        equity = 100.0
        peak = equity
        max_dd = 0.0
        for trade in finite_trades:
            equity *= 1 + trade.pnl_pct / 100
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100
            if dd > max_dd:
                max_dd = dd

        # Calmar ratio
        annualized_roi = total_pnl  # Simplified
        calmar = (annualized_roi / max_dd) if max_dd > 0 else 0

        # Fitness score using the proper 100-point model from fitness_service.py
        # Includes: EV gate, EV multiplier, Sortino, Drawdown, Alpha, etc.
        try:
            trade_data_list = [
                TradeData(
                    pnl=t.pnl_pct,  # Use pnl_pct as pnl for now
                    pnl_pct=t.pnl_pct,
                    is_win=(t.pnl_pct > 0) if t.pnl_pct else False,
                    entry_price=getattr(t, "entry_price", 0.0) or 0.0,
                    exit_price=getattr(t, "exit_price", 0.0) or 0.0,
                    size=getattr(t, "size", 0.0) or 0.0,
                )
                for t in finite_trades
                if t.pnl_pct is not None
            ]

            if trade_data_list:
                fitness_result = calculate_fitness(trade_data_list)
                fitness = fitness_result.fitness_score
            else:
                fitness = 0.0
        except Exception as e:
            # Fallback to simple calculation if fitness_service fails
            print(f"[Backtest] fitness_service error: {e}, using fallback")
            fitness = (
                (sharpe * 10 if sharpe else 0) + (win_rate * 50) + (annualized_roi / 100 * 20) - (max_dd / 100 * 10)
            )
            fitness = max(0.0, min(100.0, fitness))

        return {
            "total_trades": total_trades,
            "fitness_score": fitness,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown_pct": max_dd,
            "annualized_roi_pct": annualized_roi,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_trade_pct": avg_pnl,
        }

    def _calculate_weighted_fitness(self, fitness_by_regime: dict[str, dict], fallback_fitness: float = 0.0) -> float:
        """
        Calculate weighted average fitness using regime importance coefficients.

        Harder market conditions (crash, sideways, bear) get higher weights because:
        - An agent that survives a crash is more valuable than one that profits in a bull
        - Sideways markets are where most trading happens - consistency matters
        - Bear markets require actual skill, not just momentum riding

        Args:
            fitness_by_regime: Dict mapping regime -> {fitness: float, trades: int, ...}
            fallback_fitness: Fitness to return if no regime data available

        Returns:
            Weighted average fitness score bounded to [0, 100]
        """
        if not fitness_by_regime:
            return fallback_fitness

        weighted_sum = 0.0
        total_weight = 0.0

        for regime, data in fitness_by_regime.items():
            if not isinstance(data, dict) or "fitness" not in data:
                continue

            regime_fitness = data["fitness"]
            weight = self.REGIME_WEIGHTS.get(regime, 1.0)

            weighted_sum += regime_fitness * weight
            total_weight += weight

        if total_weight == 0:
            return fallback_fitness

        weighted_fitness = weighted_sum / total_weight

        # Bound to [0, 100]
        return max(0.0, min(100.0, weighted_fitness))
