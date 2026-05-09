"""
Agent Backtest Service - Run backtests for agents.

This service handles backtesting agents using the LocalBacktestEngine.
Updates agent stats (fitness, sharpe, etc.) in the database.
All data comes from PostgreSQL enhanced_candles table (5.2M+ rows).
"""

import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

# Add local_agents to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "local_agents"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader, preload_candles_for_windows
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.canonical_periods import (
    get_canonical_periods_for_backtesting,
)
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.shared.llm_client import AIZoneMode

from ...Trades.Services.trade_service import persist_trades
from ..Models.agent_models import Agent
from .fitness_service import TradeData, calculate_fitness


def _extract_pattern_refs(agent) -> tuple[list[dict], list[str]]:
    """
    Extract pattern references from an agent's assigned_patterns field.

    Handles 3 forms of pattern assignment:
    1. Embedded patterns (dict with entry_conditions) -> returned in embedded_patterns list
    2. Reference IDs (strings) -> returned in reference_ids list
    3. Partial dicts (pattern_id but no conditions) -> ID extracted to reference_ids

    Args:
        agent: Agent object with assigned_patterns attribute

    Returns:
        Tuple of (embedded_patterns, reference_ids):
        - embedded_patterns: List of fully hydrated pattern dicts (have entry_conditions)
        - reference_ids: List of pattern ID strings that need DB lookup
    """
    embedded_patterns = []
    reference_ids = []

    assigned = agent.assigned_patterns or {}

    # Handle dict format ({"base": [...]})
    if isinstance(assigned, dict):
        base_patterns = assigned.get("base", [])
        for p in base_patterns:
            if p is None:
                continue
            if isinstance(p, str):
                # Form 2: String reference ID
                if p:  # Skip empty strings
                    reference_ids.append(p)
            elif isinstance(p, dict):
                # Check if it's a fully embedded pattern (has entry_conditions with content)
                if p.get("entry_conditions") and p.get("exit_conditions"):
                    # Form 1: Embedded pattern with conditions
                    embedded_patterns.append(p)
                else:
                    # Form 3: Partial dict - extract ID
                    pid = p.get("pattern_id", p.get("id", ""))
                    if pid:
                        reference_ids.append(pid)

    # Handle list format ([...patterns...])
    elif isinstance(assigned, list):
        for item in assigned:
            if item is None:
                continue
            if isinstance(item, str):
                # Form 2: String reference ID
                if item:  # Skip empty strings
                    reference_ids.append(item)
            elif isinstance(item, dict):
                # Check if it's a fully embedded pattern
                if item.get("entry_conditions") and item.get("exit_conditions"):
                    # Form 1: Embedded pattern with conditions
                    embedded_patterns.append(item)
                else:
                    # Form 3: Partial dict - extract ID
                    pid = item.get("pattern_id", item.get("id", ""))
                    if pid:
                        reference_ids.append(pid)

    return embedded_patterns, reference_ids


class AgentBacktestService:
    """Service for backtesting agents using PostgreSQL data."""

    # Window selection settings - use pre-generated pool
    WINDOWS_PER_BACKTEST = 10  # Select ~10 windows per run (increased as enrichment catches up)
    CANONICAL_WINDOWS_PER_REGIME = 4  # Max canonical windows per regime type

    # Regime importance weights for weighted fitness calculation
    # Higher weights = harder market conditions worth more in fitness
    REGIME_WEIGHTS = {
        # Benchmark-classified regimes (from window buy-and-hold return)
        "bull": 0.5,       # >+15% — everyone profits, low signal
        "mild_bull": 0.8,  # +3% to +15% — moderate, some signal
        "sideways": 2.0,   # -3% to +3% — hard to profit, high signal
        "mild_bear": 2.5,  # -15% to -3% — alpha matters most here
        "bear": 3.0,       # <-15% — survival is critical, highest weight
        # Legacy canonical names (for pre-classified windows if any)
        "crash": 3.0,
        "blowoff": 1.5,
        "recovery": 1.5,
        "volatile": 2.0,
        "winter": 2.0,
        "transition": 1.5,
        # Random fallback
        "random": 1.0,
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

    async def _get_windows_from_pool(
        self,
        session: AsyncSession,
        agent_id: str = None,
        count: int = None,
    ) -> list[dict]:
        """
        Get random windows from the pre-generated pool.

        Uses the window pool (~15K windows) and selects a subset for this backtest.
        If agent_id provided, skips windows the agent has already tested.

        Args:
            session: Database session
            agent_id: Optional agent ID to check for already-tested windows
            count: Number of windows to select (default: WINDOWS_PER_BACKTEST)

        Returns:
            List of window dicts with asset/timeframe/start_ts/end_ts/regime
        """
        from Fast_Swarm.local_agents.backtest.windows import get_pool_stats, get_windows, is_initialized

        count = count or self.WINDOWS_PER_BACKTEST

        # Ensure pool is initialized
        if not is_initialized():
            print("[Backtest] WARNING: Window pool not initialized, using fallback")
            return []

        # Get windows from pool
        pool_windows = get_windows(count=count * 2)  # Get extra to filter tested ones

        # If we have an agent, filter out already-tested windows
        # Uses aggregation instead of LIMIT to get complete tested window set
        tested_window_keys = set()
        if agent_id:
            try:
                from sqlalchemy import text

                result = await session.execute(
                    text("""
                        SELECT symbol || '_' || timeframe || '_' ||
                               EXTRACT(EPOCH FROM entry_timestamp)::bigint as window_key
                        FROM backtest_trades_unified
                        WHERE agent_id = :agent_id
                        GROUP BY symbol, timeframe, entry_timestamp
                    """),
                    {"agent_id": agent_id},
                )
                tested_window_keys = {row[0] for row in result.fetchall()}
            except Exception as e:
                print(f"[Backtest] Could not fetch tested windows: {e}")

        # Convert pool windows to dict format, filtering already-tested
        windows = []
        for w in pool_windows:
            # Create a key to check if this window was tested
            window_key = f"{w.symbol}_{w.timeframe}_{w.start_ts // 1000}"

            # Skip if agent already tested this window
            if window_key in tested_window_keys:
                continue

            windows.append(
                {
                    "asset": w.symbol,
                    "timeframe": w.timeframe,
                    "start_ts": w.start_ts,
                    "end_ts": w.end_ts,
                    "regime": f"random_{w.timeframe}",
                }
            )

            if len(windows) >= count:
                break

        stats = get_pool_stats()
        skipped = len(tested_window_keys) if tested_window_keys else 0
        print(
            f"[Backtest] Selected {len(windows)} windows from pool of {stats['pool_size']} (skipped {skipped} already tested)"
        )

        return windows

    async def _get_all_test_windows(
        self,
        session: AsyncSession,
        assets: list[str],
        timeframes: list[str] = None,
        include_canonical: bool = True,
        agent_id: str = None,
    ) -> list[dict]:
        """
        Get test windows from pool + canonical periods.

        This ensures agents are tested on:
        1. Random windows from pool (~50 per run, skipping already-tested)
        2. Canonical periods (FTX collapse, COVID crash, 2017 bull, etc.)

        Returns windows grouped by regime for per-regime fitness tracking.
        """
        all_windows = []

        # 1. Get random windows from pre-generated pool (skips already-tested)
        random_windows = await self._get_windows_from_pool(
            session,
            agent_id=agent_id,
            count=self.WINDOWS_PER_BACKTEST,
        )
        all_windows.extend(random_windows)

        # 2. Add canonical periods (historical events) - limited per regime
        if include_canonical:
            # Get canonical periods for these assets
            canonical_timeframes = timeframes or ["1h"]
            canonical_tf = "1h" if "1h" in canonical_timeframes else canonical_timeframes[0]

            canonical = get_canonical_periods_for_backtesting(
                assets=assets,
                timeframes=[canonical_tf],
                regimes=None,  # All regimes: crash, bull, bear, blowoff, recovery, sideways
            )

            # Limit canonical windows per regime to avoid overwhelming random windows
            regime_counts = {}
            for period in canonical:
                regime = period["regime"]
                if regime_counts.get(regime, 0) >= self.CANONICAL_WINDOWS_PER_REGIME:
                    continue
                regime_counts[regime] = regime_counts.get(regime, 0) + 1

                all_windows.append(
                    {
                        "asset": period["asset"],
                        "timeframe": period["timeframe"],
                        "start_ts": period["start_ts"],
                        "end_ts": period["end_ts"],
                        "regime": regime,
                        "period_name": period["name"],
                        "description": period.get("description", ""),
                    }
                )

            canonical_added = sum(regime_counts.values())
            print(
                f"[Backtest] Added {canonical_added} canonical periods (max {self.CANONICAL_WINDOWS_PER_REGIME}/regime)"
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
        min_start_ts: int = None,
        timeframes_override: list[str] = None,
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

        from ...Patterns.Models.pattern_models import Pattern

        # Clean asset names (remove /USDT suffix)
        clean_assets = [a.replace("/USDT", "").replace("-USD", "") for a in assets]

        for agent in agents:
            # Use savepoint so one agent's failure doesn't poison the session
            try:
                await session.execute(text("SAVEPOINT agent_backtest"))
            except Exception:
                pass

            # Get FRESH random windows each cycle — don't skip tested windows
            # This ensures evolution sees different market conditions each generation
            test_timeframes = timeframes_override or self.DEFAULT_TIMEFRAMES
            all_windows = await self._get_all_test_windows(
                session,
                assets=clean_assets,
                timeframes=test_timeframes,
                include_canonical=True if not min_start_ts else False,
                agent_id=None,  # Don't skip — fresh random windows each run
            )

            # Apply temporal filter for OOS validation
            if min_start_ts and all_windows:
                all_windows = [w for w in all_windows if w.get("start_ts", 0) >= min_start_ts]

            # Preload candle data for this agent's windows
            preloaded_candles = {}
            if all_windows:
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

                preloaded_candles = preload_candles_for_windows(window_adapters, self.loader)

            try:
                # Extract agent's patterns using hydrate-once pattern:
                # - Embedded patterns (have entry_conditions) → use directly
                # - Reference IDs (strings) → query only those IDs, persist back
                agent_patterns = []
                reference_ids = []
                assigned = agent.assigned_patterns or {}

                if isinstance(assigned, dict):
                    base_patterns = assigned.get("base", [])
                    for p in base_patterns:
                        if isinstance(p, str):
                            reference_ids.append(p)
                        elif isinstance(p, dict):
                            if p.get("entry_conditions") and p.get("exit_conditions"):
                                agent_patterns.append(p)
                            else:
                                pid = p.get("pattern_id", p.get("id", ""))
                                if pid:
                                    reference_ids.append(pid)
                elif isinstance(assigned, list):
                    for item in assigned:
                        if isinstance(item, str):
                            reference_ids.append(item)

                # Hydrate reference IDs (only query what we need)
                if reference_ids:
                    pattern_result = await session.exec(select(Pattern).where(Pattern.pattern_id.in_(reference_ids)))
                    fetched_patterns = pattern_result.all()

                    for p in fetched_patterns:
                        hydrated = {
                            "pattern_id": p.pattern_id,
                            "name": p.name,
                            "entry_conditions": p.entry_conditions,
                            "exit_conditions": p.exit_conditions,
                        }
                        agent_patterns.append(hydrated)

                    # Persist hydrated patterns back to agent
                    if fetched_patterns:
                        agent.assigned_patterns = {"base": agent_patterns}
                        session.add(agent)
                        print(f"[Backtest] {agent.agent_id[:8]}: Hydrated {len(fetched_patterns)} pattern refs")

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
                                "sortino": w_metrics.get("sortino_ratio"),
                                "calmar": w_metrics.get("calmar_ratio"),
                                "max_drawdown": w_metrics.get("max_drawdown_pct", 0.0),
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
                            "sortino": w_metrics.get("sortino_ratio"),
                            "calmar": w_metrics.get("calmar_ratio"),
                            "max_drawdown": w_metrics.get("max_drawdown_pct", 0.0),
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
                            fetch_indicators=True,  # Enable for pattern discovery
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
                    sharpe_windows = [w for w in valid_windows if w.get("sharpe") is not None]
                    avg_sharpe = (
                        sum(w["sharpe"] for w in sharpe_windows) / len(sharpe_windows) if sharpe_windows else None
                    )
                    # Sortino: average across windows
                    sortino_windows = [w for w in valid_windows if w.get("sortino") is not None]
                    avg_sortino = (
                        sum(w["sortino"] for w in sortino_windows) / len(sortino_windows) if sortino_windows else None
                    )
                    # Calmar: average across windows
                    calmar_windows = [w for w in valid_windows if w.get("calmar") is not None]
                    avg_calmar = (
                        sum(w["calmar"] for w in calmar_windows) / len(calmar_windows) if calmar_windows else None
                    )
                    # Max drawdown: take worst (highest) across all windows
                    max_dd = max((w.get("max_drawdown") or 0) for w in valid_windows)
                    avg_roi = sum(w["roi"] * w["trades"] for w in valid_windows) / total_w
                else:
                    avg_fitness = 0.0
                    avg_win_rate = None
                    avg_sharpe = None
                    avg_sortino = None
                    avg_calmar = None
                    max_dd = 0.0
                    avg_roi = 0.0

                metrics = {
                    "total_trades": total_trades,
                    "fitness_score": avg_fitness,
                    "sharpe_ratio": avg_sharpe,
                    "sortino_ratio": avg_sortino,
                    "calmar_ratio": avg_calmar,
                    "max_drawdown_pct": max_dd,
                    "win_rate": avg_win_rate,
                    "annualized_roi_pct": avg_roi,
                    "total_pnl": total_pnl,
                }

                # AGGREGATE by regime: group window metrics, average
                # NOW INCLUDES: sortino, calmar, max_drawdown per regime
                fitness_by_regime = {}
                unique_regimes = {w["regime"] for w in window_metrics}
                for regime in unique_regimes:
                    regime_windows = [w for w in window_metrics if w["regime"] == regime and w["trades"] > 0]
                    regime_trades = sum(w["trades"] for w in regime_windows)
                    if regime_trades >= 5:  # Minimum for statistical significance
                        regime_total = sum(w["trades"] for w in regime_windows)
                        # Compute averages for ratio metrics
                        sharpe_wins = [w for w in regime_windows if w.get("sharpe") is not None]
                        sortino_wins = [w for w in regime_windows if w.get("sortino") is not None]
                        calmar_wins = [w for w in regime_windows if w.get("calmar") is not None]
                        fitness_by_regime[regime] = {
                            "fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
                            "trades": regime_trades,
                            "win_rate": sum((w["win_rate"] or 0) * w["trades"] for w in regime_windows) / regime_total,
                            "sharpe": sum(w["sharpe"] for w in sharpe_wins) / len(sharpe_wins) if sharpe_wins else None,
                            "sortino": sum(w["sortino"] for w in sortino_wins) / len(sortino_wins) if sortino_wins else None,
                            "calmar": sum(w["calmar"] for w in calmar_wins) / len(calmar_wins) if calmar_wins else None,
                            "max_drawdown": max((w.get("max_drawdown") or 0) for w in regime_windows),
                            "roi": sum(w["roi"] * w["trades"] for w in regime_windows) / regime_total,
                        }

                if fitness_by_regime:
                    regime_str = ", ".join(f"{r}={d['fitness']:.1f}" for r, d in fitness_by_regime.items())
                    print(f"[Backtest] Agent {agent.agent_id}: Per-regime fitness: {regime_str}")

                # Calculate weighted fitness using top-5 regime scores
                # Rewards specialists over generalists
                base_fitness = metrics.get("fitness_score", 0.0)
                if fitness_by_regime:
                    weighted_fitness = self._calculate_weighted_fitness(fitness_by_regime, base_fitness)
                    weight_diff = weighted_fitness - base_fitness
                    if abs(weight_diff) > 1.0:
                        # Show which regimes were selected
                        valid = [(r, d["fitness"]) for r, d in fitness_by_regime.items()
                                 if isinstance(d, dict) and isinstance(d.get("fitness"), (int, float))]
                        top5 = sorted(valid, key=lambda x: x[1], reverse=True)[:5]
                        top5_str = ", ".join(f"{r}={f:.0f}" for r, f in top5)
                        print(
                            f"[Backtest] Agent {agent.agent_id}: [TOP-5] Weighted: {weighted_fitness:.1f} "
                            f"(base: {base_fitness:.1f}, delta: {weight_diff:+.1f}) regimes: {top5_str}"
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
                # Rollback to savepoint so session stays usable for next agent
                try:
                    await session.execute(text("ROLLBACK TO SAVEPOINT agent_backtest"))
                except Exception:
                    pass

                print(f"[Backtest] ERROR for agent {agent.agent_id}: {type(e).__name__}: {e}")
                results[agent.agent_id] = {"error": str(e), "error_type": type(e).__name__}
                continue

        await session.commit()
        return results

    def _calculate_metrics(self, trades: list, benchmark_pct: float = 0.0) -> dict:
        """Calculate performance metrics from trades, relative to benchmark."""
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

        # Calculate returns for Sharpe/Sortino using Metrics engine (QuantStats-backed)
        from Fast_Swarm.Metrics.metrics_engine import (
            calculate_calmar,
            calculate_max_drawdown,
            calculate_sharpe,
            calculate_sortino,
        )

        returns = [t.pnl_pct for t in finite_trades]
        # Metrics engine expects decimal returns (0.025 = 2.5%), not percentages
        returns_decimal = [r / 100.0 for r in returns]

        sharpe = calculate_sharpe(returns_decimal) if len(returns) > 1 else None
        sortino = calculate_sortino(returns_decimal) if len(returns) > 1 else None
        max_dd = calculate_max_drawdown(returns_decimal) * 100  # Back to percentage for storage
        calmar = calculate_calmar(returns_decimal)
        annualized_roi = total_pnl  # Used in fallback fitness and stats output

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
                fitness_result = calculate_fitness(trade_data_list, benchmark_pct=benchmark_pct)
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
        Calculate weighted fitness using the agent's BEST 5 regime scores.

        Takes top 5 regimes by fitness, weights them by regime importance
        (bear=3x, sideways=2x, bull=0.5x), returns weighted average.

        This prevents generalist dilution: an agent excelling in 2-3 regimes
        isn't dragged down by 10+ untested or irrelevant regimes. Evolution
        rewards specialists.

        Args:
            fitness_by_regime: Dict mapping regime -> {fitness: float, trades: int, ...}
            fallback_fitness: Fitness to return if no regime data available

        Returns:
            Weighted average fitness score bounded to [0, 100]
        """
        if not fitness_by_regime:
            return fallback_fitness

        # Extract valid regime scores
        regime_scores = []
        for regime, data in fitness_by_regime.items():
            if not isinstance(data, dict) or "fitness" not in data:
                continue
            fitness_val = data["fitness"]
            if not isinstance(fitness_val, (int, float)):
                continue
            regime_scores.append((regime, float(fitness_val)))

        if not regime_scores:
            return fallback_fitness

        # Select top 5 by fitness score
        top_regimes = sorted(regime_scores, key=lambda x: x[1], reverse=True)[:5]

        # Weight the top 5
        weighted_sum = 0.0
        total_weight = 0.0
        for regime, fitness in top_regimes:
            weight = self.REGIME_WEIGHTS.get(regime, 1.0)
            weighted_sum += fitness * weight
            total_weight += weight

        if total_weight == 0:
            return fallback_fitness

        return max(0.0, min(100.0, weighted_sum / total_weight))

    async def backtest_agent_on_windows(
        self,
        session: AsyncSession,
        agent,
        windows: list[dict],
        preloaded_candles: dict = None,
    ) -> dict:
        """
        Test a single agent on pre-loaded windows (used by orchestrator).

        This is called by the orchestrator to test agents one at a time
        on windows that have already been loaded. This avoids loading
        candle data multiple times.

        Args:
            session: Database session
            agent: Agent model object
            windows: List of window dicts with asset/timeframe/start_ts/end_ts
            preloaded_candles: Dict of (symbol, timeframe, start_ts) -> DataFrame

        Returns:
            Dict with test results
        """
        import time

        from ...Patterns.Models.pattern_models import Pattern

        agent_start = time.time()
        aid = agent.agent_id
        aname = agent.name or aid[:8]  # Use name if available, else short ID

        # Extract agent's patterns using hydrate-once pattern:
        # - Embedded patterns (have entry_conditions) → use directly, no DB query
        # - Reference IDs (strings) → query only those IDs, then persist back to agent
        agent_patterns = []
        reference_ids = []  # Pattern IDs that need DB lookup
        assigned = agent.assigned_patterns or {}

        # First pass: collect embedded patterns and reference IDs
        if isinstance(assigned, dict):
            base_patterns = assigned.get("base", [])
            for p in base_patterns:
                if isinstance(p, str):
                    reference_ids.append(p)
                elif isinstance(p, dict):
                    if p.get("entry_conditions") and p.get("exit_conditions"):
                        agent_patterns.append(p)
                    else:
                        # Dict but missing conditions - treat as reference
                        pid = p.get("pattern_id", p.get("id", ""))
                        if pid:
                            reference_ids.append(pid)
        elif isinstance(assigned, list):
            for item in assigned:
                if isinstance(item, str):
                    reference_ids.append(item)

        # Second pass: hydrate reference IDs (only query what we need)
        if reference_ids:
            pattern_result = await session.exec(select(Pattern).where(Pattern.pattern_id.in_(reference_ids)))
            fetched_patterns = pattern_result.all()

            for p in fetched_patterns:
                hydrated = {
                    "pattern_id": p.pattern_id,
                    "name": p.name,
                    "entry_conditions": p.entry_conditions,
                    "exit_conditions": p.exit_conditions,
                }
                agent_patterns.append(hydrated)

            # Mark that we need to persist hydrated patterns (defer session.add to avoid flush conflicts)
            patterns_were_hydrated = len(fetched_patterns) > 0
            if patterns_were_hydrated:
                agent.assigned_patterns = {"base": agent_patterns}
                print(f"[AgentTest] {aname}: Hydrated {len(fetched_patterns)} pattern refs → embedded")

        if not agent_patterns:
            print(f"[AgentTest] {aid[:8]}: No valid patterns, skipping")
            return {"agent_id": aid, "error": "No valid patterns"}

        # Create backtest config from agent traits
        traits_dict = agent.traits if isinstance(agent.traits, dict) else agent.traits.__dict__

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

        # Create backtest engine with preloaded candles
        engine = LocalBacktestEngine(
            loader=self.loader,
            config=config,
            patterns=pattern_dict,
            ai_zone_mode=AIZoneMode.LLM,
            preloaded_candles=preloaded_candles,
        )

        # Run backtest for each window
        all_trades = []
        window_metrics = []

        for window in windows:
            window_tf = window.get("timeframe", "1h")
            dataset = {
                "assets": [window["asset"]],
                "timeframe": window_tf,
                "start_ts": window["start_ts"],
                "end_ts": window["end_ts"],
            }
            window_trades = engine.run(agent=agent_record, dataset=dataset)
            all_trades.extend(window_trades)

            # Calculate benchmark (buy-and-hold return) for this window
            benchmark_pct = 0.0
            try:
                cache_key = f"{window['asset']}_{window_tf}"
                if preloaded_candles and cache_key in preloaded_candles:
                    wdf = preloaded_candles[cache_key]
                    wdf_window = wdf[(wdf["timestamp"] >= window["start_ts"]) & (wdf["timestamp"] <= window["end_ts"])]
                    if len(wdf_window) >= 2:
                        first_close = float(wdf_window.iloc[0]["close"])
                        last_close = float(wdf_window.iloc[-1]["close"])
                        if first_close > 0:
                            benchmark_pct = ((last_close - first_close) / first_close) * 100
            except Exception:
                pass

            # Classify window regime from benchmark return
            # This gives evolution real regime signal instead of "random" everywhere
            if benchmark_pct > 15:
                regime = "bull"
            elif benchmark_pct > 3:
                regime = "mild_bull"
            elif benchmark_pct > -3:
                regime = "sideways"
            elif benchmark_pct > -15:
                regime = "mild_bear"
            else:
                regime = "bear"

            w_metrics = self._calculate_metrics(window_trades, benchmark_pct=benchmark_pct)
            window_metrics.append(
                {
                    "regime": regime,
                    "timeframe": window_tf,
                    "trades": len(window_trades),
                    "fitness": w_metrics.get("fitness_score", 0.0),
                    "sortino": w_metrics.get("sortino_ratio"),
                    "win_rate": w_metrics.get("win_rate"),
                    "roi": w_metrics.get("annualized_roi_pct", 0.0),
                    "pnl": w_metrics.get("total_pnl", 0.0),
                }
            )

        agent_elapsed = time.time() - agent_start

        # Aggregate metrics
        total_trades = sum(w["trades"] for w in window_metrics)
        total_pnl = sum(w["pnl"] for w in window_metrics)
        total_winning_trades = sum(1 for t in all_trades if t.pnl_pct > 0)

        valid_windows = [w for w in window_metrics if w["trades"] > 0]
        if valid_windows:
            total_w = sum(w["trades"] for w in valid_windows)
            avg_fitness = sum(w["fitness"] * w["trades"] for w in valid_windows) / total_w
            avg_win_rate = sum((w["win_rate"] or 0) * w["trades"] for w in valid_windows) / total_w
            sortino_windows = [w for w in valid_windows if w["sortino"] is not None]
            avg_sortino = sum(w["sortino"] for w in sortino_windows) / len(sortino_windows) if sortino_windows else None
        else:
            avg_fitness = 0.0
            avg_win_rate = None
            avg_sortino = None

        # Update agent in DB (agent is already tracked, no need to add)
        # Convert to proper types to avoid Decimal + float errors
        from decimal import Decimal

        agent.fitness_score = float(avg_fitness) if avg_fitness else 0.0
        agent.sortino_ratio = float(avg_sortino) if avg_sortino else None
        agent.win_rate = float(avg_win_rate) if avg_win_rate else None
        agent.total_trades = int(agent.total_trades or 0) + int(total_trades)
        agent.winning_trades = int(agent.winning_trades or 0) + int(total_winning_trades)
        agent.total_pnl = Decimal(str(float(agent.total_pnl or 0) + float(total_pnl)))
        agent.backtest_count = int(agent.backtest_count or 0) + 1
        agent.last_backtest_at = datetime.utcnow()
        # Note: agent is already tracked by session from the initial query
        # Calling session.add() during autoflush causes warnings

        # MEMORY CREATION: Create memories from significant trade outcomes
        # Use no_autoflush to prevent SQLAlchemy warnings about session.add() during flush
        if all_trades and total_trades >= 5:
            try:
                from .memory_integration_service import (
                    create_memories_from_trades,
                    maybe_trigger_memory_review,
                )

                # Create memories from aggregate results (not per-window to avoid spam)
                aggregate_trades = [
                    {
                        "pnl_pct": getattr(t, "pnl_pct", 0),
                        "pattern_id": getattr(t, "pattern_id", "unknown"),
                        "trade_id": getattr(t, "trade_id", ""),
                    }
                    for t in all_trades
                ]
                # Use dominant regime from window metrics
                dominant_regime = (
                    max(window_metrics, key=lambda w: w["trades"])["regime"] if window_metrics else "random"
                )
                dominant_tf = max(window_metrics, key=lambda w: w["trades"])["timeframe"] if window_metrics else "1h"

                # Use no_autoflush context to prevent session.add() during flush warnings
                async with session.no_autoflush:
                    await create_memories_from_trades(
                        session=session,
                        agent_id=aid,
                        trades=aggregate_trades,
                        regime=dominant_regime,
                        timeframe=dominant_tf,
                    )

                    # Check if memory review should be triggered (every 50 backtests)
                    await maybe_trigger_memory_review(
                        session=session,
                        agent_id=aid,
                        backtest_count=agent.backtest_count,
                    )
            except Exception as e:
                print(f"[AgentTest] Memory creation failed for {aid[:8]}: {e}")

        print(
            f"[AgentTest] {aid[:8]}: fitness={avg_fitness:.1f}, trades={total_trades}, windows={len(windows)} ({agent_elapsed:.1f}s)"
        )

        return {
            "agent_id": aid,
            "fitness": avg_fitness,
            "total_trades": total_trades,
            "windows_tested": len(windows),
        }

    async def backtest_agent_on_windows_compute(
        self,
        agent,
        windows: list[dict],
        preloaded_candles: dict = None,
        pattern_cache: dict = None,
    ) -> dict:
        """
        Pure compute variant — no DB session, no writes.

        Called by orchestrator's compute-then-write architecture.
        Returns a result dict that the orchestrator applies to the agent in a batch write.

        Args:
            agent: Agent model object (read-only during compute)
            windows: Pre-loaded window dicts
            preloaded_candles: Dict of cache_key -> DataFrame
            pattern_cache: Dict of pattern_id -> {pattern_id, name, entry_conditions, exit_conditions}
        """
        import time

        agent_start = time.time()
        aid = agent.agent_id
        aname = agent.name or aid[:8]

        # Resolve patterns from cache (no DB)
        agent_patterns = []
        assigned = agent.assigned_patterns or {}
        patterns_were_hydrated = False

        if isinstance(assigned, dict):
            for p in assigned.get("base", []):
                if isinstance(p, str):
                    if pattern_cache and p in pattern_cache:
                        agent_patterns.append(pattern_cache[p])
                        patterns_were_hydrated = True
                elif isinstance(p, dict):
                    if p.get("entry_conditions") and p.get("exit_conditions"):
                        agent_patterns.append(p)
                    else:
                        pid = p.get("pattern_id", p.get("id", ""))
                        if pid and pattern_cache and pid in pattern_cache:
                            agent_patterns.append(pattern_cache[pid])
                            patterns_were_hydrated = True
        elif isinstance(assigned, list):
            for item in assigned:
                if isinstance(item, str) and pattern_cache and item in pattern_cache:
                    agent_patterns.append(pattern_cache[item])
                    patterns_were_hydrated = True

        if not agent_patterns:
            return {"agent_id": aid, "error": "No valid patterns"}

        # Build config from traits
        traits_dict = agent.traits if isinstance(agent.traits, dict) else agent.traits.__dict__
        from dataclasses import fields as dataclass_fields
        known_fields = {f.name for f in dataclass_fields(AgentTraits)}
        filtered_traits = {k: v for k, v in traits_dict.items() if k in known_fields}
        agent_traits = AgentTraits(**filtered_traits)
        config = BacktestConfig.from_traits(agent_traits)

        pattern_dict = {p["pattern_id"]: p for p in agent_patterns}

        agent_record = AgentRecord(
            agent_id=agent.agent_id,
            agent_name=agent.name,
            generation=agent.generation,
            traits=traits_dict,
            pattern_ids=[p["pattern_id"] for p in agent_patterns],
            pattern_weights=agent.pattern_weights or {},
            trading_philosophy=agent.trading_philosophy or "",
        )

        engine = LocalBacktestEngine(
            loader=self.loader,
            config=config,
            patterns=pattern_dict,
            ai_zone_mode=AIZoneMode.LLM,
            preloaded_candles=preloaded_candles,
        )

        # Run backtest — pure compute
        all_trades = []
        window_metrics = []

        for window in windows:
            window_tf = window.get("timeframe", "1h")
            dataset = {
                "assets": [window["asset"]],
                "timeframe": window_tf,
                "start_ts": window["start_ts"],
                "end_ts": window["end_ts"],
            }
            window_trades = engine.run(agent=agent_record, dataset=dataset)
            all_trades.extend(window_trades)

            # Benchmark
            benchmark_pct = 0.0
            try:
                cache_key = f"{window['asset']}_{window_tf}"
                if preloaded_candles and cache_key in preloaded_candles:
                    wdf = preloaded_candles[cache_key]
                    wdf_window = wdf[(wdf["timestamp"] >= window["start_ts"]) & (wdf["timestamp"] <= window["end_ts"])]
                    if len(wdf_window) >= 2:
                        first_close = float(wdf_window.iloc[0]["close"])
                        last_close = float(wdf_window.iloc[-1]["close"])
                        if first_close > 0:
                            benchmark_pct = ((last_close - first_close) / first_close) * 100
            except Exception:
                pass

            # Regime from benchmark
            if benchmark_pct > 15:
                regime = "bull"
            elif benchmark_pct > 3:
                regime = "mild_bull"
            elif benchmark_pct > -3:
                regime = "sideways"
            elif benchmark_pct > -15:
                regime = "mild_bear"
            else:
                regime = "bear"

            w_metrics = self._calculate_metrics(window_trades, benchmark_pct=benchmark_pct)
            window_metrics.append({
                "regime": regime,
                "timeframe": window_tf,
                "trades": len(window_trades),
                "fitness": w_metrics.get("fitness_score", 0.0),
                "sortino": w_metrics.get("sortino_ratio"),
                "calmar": w_metrics.get("calmar_ratio"),
                "max_drawdown": w_metrics.get("max_drawdown_pct"),
                "win_rate": w_metrics.get("win_rate"),
                "roi": w_metrics.get("annualized_roi_pct", 0.0),
                "pnl": w_metrics.get("total_pnl", 0.0),
            })

        # Aggregate
        total_trades = sum(w["trades"] for w in window_metrics)
        total_pnl = sum(w["pnl"] for w in window_metrics)
        total_winning = sum(1 for t in all_trades if t.pnl_pct > 0)

        valid_windows = [w for w in window_metrics if w["trades"] > 0]
        if valid_windows:
            total_w = sum(w["trades"] for w in valid_windows)
            avg_fitness = sum(w["fitness"] * w["trades"] for w in valid_windows) / total_w
            avg_win_rate = sum((w["win_rate"] or 0) * w["trades"] for w in valid_windows) / total_w
            sortino_wins = [w for w in valid_windows if w["sortino"] is not None]
            avg_sortino = sum(w["sortino"] for w in sortino_wins) / len(sortino_wins) if sortino_wins else None
        else:
            avg_fitness = 0.0
            avg_win_rate = None
            avg_sortino = None

        # Per-regime fitness aggregation
        fitness_by_regime = {}
        unique_regimes = {w["regime"] for w in window_metrics}
        for regime in unique_regimes:
            regime_windows = [w for w in window_metrics if w["regime"] == regime]
            regime_total = sum(w["trades"] for w in regime_windows)
            if regime_total >= 5:
                fitness_by_regime[regime] = {
                    "fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
                    "trades": regime_total,
                    "sortino": sum(w["sortino"] for w in regime_windows if w["sortino"] is not None) / max(1, len([w for w in regime_windows if w["sortino"] is not None])),
                }

        # Top-5 weighted fitness
        if fitness_by_regime:
            final_fitness = self._calculate_weighted_fitness(fitness_by_regime, avg_fitness)
        else:
            final_fitness = avg_fitness

        elapsed = time.time() - agent_start
        print(f"[AgentCompute] {aname}: fitness={final_fitness:.1f}, trades={total_trades}, windows={len(windows)} ({elapsed:.1f}s)")

        return {
            "agent_id": aid,
            "fitness": final_fitness,
            "total_trades": total_trades,
            "winning_trades": total_winning,
            "total_pnl": total_pnl,
            "sortino": avg_sortino,
            "win_rate": avg_win_rate,
            "fitness_by_regime": fitness_by_regime,
            "hydrated_patterns": agent_patterns if patterns_were_hydrated else None,
        }
