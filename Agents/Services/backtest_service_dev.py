"""
Agent Backtest Service - DEV VERSION with Concurrency Optimizations.

KEY FIXES:
1. RUN BACKTEST IN THREAD POOL - engine.run() is sync, blocks event loop
2. SHARED DATA CACHE - Load OHLCV data ONCE, share across all agents
3. WORKER POOL - Process agents in parallel with thread pool
4. NON-BLOCKING - API remains responsive during backtests

Blue-Green Pattern:
- This file (backtest_service_dev.py) is the "blue" dev version
- Production (backtest_service.py) is "green"
- Switch by changing import in evolution_service.py
"""

import asyncio
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "local_agents"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.canonical_periods import get_canonical_periods_for_backtesting
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.shared.llm_client import AIZoneMode

from ...Trades.Services.trade_service import persist_trades
from ..Models.agent_models import Agent
from .fitness_service import TradeData, calculate_fitness


@dataclass
class CachedDataset:
    """Pre-loaded dataset range info."""

    asset: str
    timeframe: str
    start_ts: int
    end_ts: int
    candle_count: int


class DataCache:
    """Shared data cache - loads ranges ONCE."""

    def __init__(self):
        self._cache: dict[str, CachedDataset] = {}
        self._lock = asyncio.Lock()

    def _key(self, asset: str, tf: str) -> str:
        return f"{asset}:{tf}"

    async def preload(self, session: AsyncSession, assets: list[str], timeframes: list[str]) -> int:
        async with self._lock:
            loaded = 0
            for asset in assets:
                for tf in timeframes:
                    key = self._key(asset, tf)
                    if key in self._cache:
                        continue

                    result = await session.execute(
                        text("""
                            SELECT EXTRACT(EPOCH FROM MIN(time)) * 1000,
                                   EXTRACT(EPOCH FROM MAX(time)) * 1000,
                                   COUNT(*)
                            FROM enhanced_candles WHERE symbol = :a AND timeframe = :t
                        """),
                        {"a": asset, "t": tf},
                    )
                    row = result.fetchone()
                    if row and row[0] and row[1]:
                        self._cache[key] = CachedDataset(
                            asset=asset,
                            timeframe=tf,
                            start_ts=int(row[0]),
                            end_ts=int(row[1]),
                            candle_count=int(row[2] or 0),
                        )
                        loaded += 1
            return loaded

    def get(self, asset: str, tf: str) -> CachedDataset | None:
        return self._cache.get(self._key(asset, tf))

    def clear(self):
        self._cache.clear()


class AgentBacktestServiceDev:
    """
    DEV VERSION - Non-blocking backtest service.

    CRITICAL FIX: engine.run() is SYNCHRONOUS and blocks the event loop.
    Solution: Run in ThreadPoolExecutor so API stays responsive.
    """

    WINDOWS_PER_ASSET_PER_TF = 20
    MAX_WORKERS = 4  # Thread pool size
    DEFAULT_TIMEFRAMES = ["1m", "15m", "1h", "1d"]

    TIMEFRAME_CONFIG = {
        "1m": {"candles": 1440},
        "5m": {"candles": 576},
        "15m": {"candles": 384},
        "1h": {"candles": 500},
        "4h": {"candles": 180},
        "1d": {"candles": 90},
    }

    # Regime importance weights - harder conditions worth more in fitness
    # MUST match backtest_service.py for consistency
    REGIME_WEIGHTS = {
        "random_1m": 1.0,
        "random_5m": 1.0,
        "random_15m": 1.0,
        "random_1h": 1.0,
        "random_4h": 1.0,
        "random_1d": 1.0,
        "bull": 0.5,  # Everyone can win in a bull market
        "bear": 2.0,  # Harder to profit when prices fall
        "crash": 3.0,  # Survival is critical - highest weight
        "sideways": 2.5,  # Market spends most time here
        "blowoff": 1.5,  # Volatility spike before reversal
        "recovery": 1.5,  # Catching the bounce
        "volatile": 2.0,  # High uncertainty
    }

    def __init__(self):
        self.loader = OHLCVLoader()
        self.data_cache = DataCache()
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)

    def _generate_windows_sync(self, assets: list[str], timeframes: list[str]) -> list[dict]:
        """Generate windows (sync, runs in thread)."""
        windows = []
        tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

        for tf in timeframes:
            if tf not in self.TIMEFRAME_CONFIG:
                continue
            window_ms = self.TIMEFRAME_CONFIG[tf]["candles"] * tf_ms.get(tf, 3_600_000)

            for asset in assets:
                cached = self.data_cache.get(asset, tf)
                if not cached or cached.candle_count < self.TIMEFRAME_CONFIG[tf]["candles"]:
                    continue

                available = cached.end_ts - cached.start_ts - window_ms
                if available <= 0:
                    continue

                for _ in range(self.WINDOWS_PER_ASSET_PER_TF):
                    start = cached.start_ts + random.randint(0, int(available))
                    windows.append(
                        {
                            "asset": asset,
                            "timeframe": tf,
                            "start_ts": start,
                            "end_ts": start + window_ms,
                            "regime": f"random_{tf}",
                        }
                    )

        # Add canonical periods
        canonical = get_canonical_periods_for_backtesting(assets, ["1h"], None)
        for p in canonical:
            windows.append(
                {
                    "asset": p["asset"],
                    "timeframe": p["timeframe"],
                    "start_ts": p["start_ts"],
                    "end_ts": p["end_ts"],
                    "regime": p["regime"],
                }
            )

        return windows

    def _run_backtest_sync(
        self,
        agent_data: dict,
        pattern_lookup: dict,
        windows: list[dict],
    ) -> dict:
        """
        Run backtest for ONE agent - SYNC, runs in thread pool.

        This is the CPU-intensive work that would block the event loop.
        """
        try:
            agent_id = agent_data["agent_id"]
            traits_dict = agent_data["traits"]
            assigned = agent_data["assigned_patterns"]

            # Get patterns
            agent_patterns = []
            if isinstance(assigned, dict):
                for p in assigned.get("base", []):
                    if isinstance(p, str) and p in pattern_lookup:
                        agent_patterns.append(pattern_lookup[p])
                    elif isinstance(p, dict):
                        pid = p.get("pattern_id", p.get("id", ""))
                        if p.get("entry_conditions"):
                            agent_patterns.append(p)
                        elif pid in pattern_lookup:
                            agent_patterns.append(pattern_lookup[pid])
            elif isinstance(assigned, list):
                for pid in assigned:
                    if pid in pattern_lookup:
                        agent_patterns.append(pattern_lookup[pid])

            if not agent_patterns:
                return {"agent_id": agent_id, "error": "no_patterns"}

            # Build config
            from dataclasses import fields as df

            known = {f.name for f in df(AgentTraits)}
            filtered = {k: v for k, v in traits_dict.items() if k in known}
            config = BacktestConfig.from_traits(AgentTraits(**filtered))

            # Create engine
            pattern_dict = {p["pattern_id"]: p for p in agent_patterns}
            agent_record = AgentRecord(
                agent_id=agent_id,
                agent_name=agent_data.get("name", ""),
                generation=agent_data.get("generation", 0),
                traits=traits_dict,
                pattern_ids=list(pattern_dict.keys()),
                pattern_weights=agent_data.get("pattern_weights", {}),
                trading_philosophy=agent_data.get("philosophy", ""),
            )

            engine = LocalBacktestEngine(
                loader=self.loader,
                config=config,
                patterns=pattern_dict,
                ai_zone_mode=AIZoneMode.SKIP,  # Skip LLM in threads
            )

            # Run on windows
            all_trades = []
            trades_by_regime = {}

            for w in windows:
                dataset = {
                    "assets": [w["asset"]],
                    "timeframe": w["timeframe"],
                    "start_ts": w["start_ts"],
                    "end_ts": w["end_ts"],
                }
                trades = engine.run(agent=agent_record, dataset=dataset)
                all_trades.extend(trades)

                regime = w.get("regime", "unknown")
                if regime not in trades_by_regime:
                    trades_by_regime[regime] = []
                trades_by_regime[regime].extend(trades)

            # Calculate metrics
            metrics = self._calc_metrics(all_trades)

            # Per-regime
            regime_fitness = {}
            for regime, rtrades in trades_by_regime.items():
                if len(rtrades) >= 5:
                    rm = self._calc_metrics(rtrades)
                    regime_fitness[regime] = {
                        "fitness": rm.get("fitness_score", 0),
                        "trades": rm.get("total_trades", 0),
                        "win_rate": rm.get("win_rate"),
                    }

            return {
                "agent_id": agent_id,
                "metrics": metrics,
                "fitness_by_regime": regime_fitness,
                "trades": all_trades,
            }

        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"agent_id": agent_data.get("agent_id", "?"), "error": str(e)}

    async def backtest_agents(
        self,
        session: AsyncSession,
        agent_ids: list[str],
        assets: list[str] = None,
        timeframe: str = "1h",
    ) -> dict[str, dict]:
        """
        Run backtests - NON-BLOCKING via thread pool.
        """
        if assets is None:
            assets = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE"]

        clean_assets = [a.replace("/USDT", "").replace("-USD", "") for a in assets]

        # 1. Preload cache
        print("[BacktestDev] Preloading data cache...")
        await self.data_cache.preload(session, clean_assets, self.DEFAULT_TIMEFRAMES)

        # 2. Generate windows (in thread to not block)
        loop = asyncio.get_event_loop()
        windows = await loop.run_in_executor(
            self._executor, self._generate_windows_sync, clean_assets, self.DEFAULT_TIMEFRAMES
        )
        print(f"[BacktestDev] Generated {len(windows)} windows")

        # 3. Load patterns
        from ...Patterns.Models.pattern_models import Pattern

        pattern_result = await session.exec(select(Pattern).where(Pattern.is_active == True))
        patterns = pattern_result.all()
        pattern_lookup = {
            p.pattern_id: {
                "pattern_id": p.pattern_id,
                "entry_conditions": p.entry_conditions,
                "exit_conditions": p.exit_conditions,
            }
            for p in patterns
        }

        # 4. Get agents and serialize for thread pool
        result = await session.exec(select(Agent).where(Agent.agent_id.in_(agent_ids)))
        agents = result.all()

        agent_data_list = [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "generation": a.generation,
                "traits": a.traits if isinstance(a.traits, dict) else {},
                "assigned_patterns": a.assigned_patterns or {},
                "pattern_weights": a.pattern_weights or {},
                "philosophy": a.trading_philosophy or "",
            }
            for a in agents
        ]

        print(f"[BacktestDev] Running {len(agents)} agents in thread pool...")

        # 5. Run backtests in thread pool - NON-BLOCKING
        tasks = []
        for agent_data in agent_data_list:
            task = loop.run_in_executor(
                self._executor,
                self._run_backtest_sync,
                agent_data,
                pattern_lookup,
                windows,
            )
            tasks.append(task)

        # Gather results (event loop stays responsive!)
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 6. Process results
        results = {}
        agent_lookup = {a.agent_id: a for a in agents}

        for res in batch_results:
            if isinstance(res, Exception):
                continue

            agent_id = res.get("agent_id")
            if res.get("error") or agent_id not in agent_lookup:
                results[agent_id] = res
                continue

            agent = agent_lookup[agent_id]
            metrics = res["metrics"]

            # Persist trades
            if res.get("trades"):
                try:
                    await persist_trades(session, res["trades"], "evolution_backtest_dev", timeframe)
                except Exception as e:
                    print(f"[BacktestDev] Trade persist error: {e}")

            # Update agent
            # Calculate weighted fitness from regime scores (crash/bear/sideways weighted higher)
            fitness_by_regime = res.get("fitness_by_regime", {})
            base_fitness = metrics.get("fitness_score", 0)
            if fitness_by_regime:
                weighted_fitness = self._calculate_weighted_fitness(fitness_by_regime, base_fitness)
                agent.fitness_score = weighted_fitness
            else:
                agent.fitness_score = base_fitness
            agent.sharpe_ratio = metrics.get("sharpe_ratio")
            agent.sortino_ratio = metrics.get("sortino_ratio")
            agent.calmar_ratio = metrics.get("calmar_ratio")
            agent.max_drawdown_pct = metrics.get("max_drawdown_pct", 0)
            agent.annualized_roi_pct = metrics.get("annualized_roi_pct", 0)
            agent.win_rate = metrics.get("win_rate")
            agent.total_trades = metrics.get("total_trades", 0)
            agent.fitness_by_regime = fitness_by_regime
            agent.backtest_count = (agent.backtest_count or 0) + 1
            agent.last_backtest_at = datetime.utcnow()
            session.add(agent)

            results[agent_id] = metrics

        await session.commit()
        print(f"[BacktestDev] Complete: {len(results)} agents processed")
        return results

    def _calc_metrics(self, trades: list) -> dict:
        """Calculate metrics from trades."""
        if not trades:
            return {"total_trades": 0, "fitness_score": 0, "win_rate": None}

        import math
        import statistics

        total = len(trades)
        wins = sum(1 for t in trades if t.pnl_pct and t.pnl_pct > 0)
        win_rate = wins / total if total > 0 else 0

        finite = [t for t in trades if t.pnl_pct and math.isfinite(t.pnl_pct)]
        pnl = sum(t.pnl_pct for t in finite)
        avg = pnl / len(finite) if finite else 0

        returns = [t.pnl_pct for t in finite]
        sharpe = None
        if len(returns) > 1:
            std = statistics.stdev(returns)
            sharpe = (statistics.mean(returns) / std) if std > 0 else 0
            sharpe = max(-6, min(6, sharpe))

        # Drawdown
        eq, peak, max_dd = 100.0, 100.0, 0.0
        for t in finite:
            eq *= 1 + t.pnl_pct / 100
            peak = max(peak, eq)
            dd = ((peak - eq) / peak) * 100
            max_dd = max(max_dd, dd)

        # Fitness score using the proper 100-point model from fitness_service.py
        # Includes: EV gate, EV multiplier, Sortino, Drawdown, Alpha, etc.
        try:
            trade_data_list = [
                TradeData(
                    pnl=t.pnl_pct,
                    pnl_pct=t.pnl_pct,
                    is_win=(t.pnl_pct > 0) if t.pnl_pct else False,
                    entry_price=getattr(t, "entry_price", 0.0) or 0.0,
                    exit_price=getattr(t, "exit_price", 0.0) or 0.0,
                    size=getattr(t, "size", 0.0) or 0.0,
                )
                for t in finite
                if t.pnl_pct is not None
            ]

            if trade_data_list:
                fitness_result = calculate_fitness(trade_data_list)
                fitness = fitness_result.fitness_score
            else:
                fitness = 0.0
        except Exception as e:
            # Fallback to simple calculation if fitness_service fails
            print(f"[BacktestDev] fitness_service error: {e}, using fallback")
            fitness = (sharpe * 10 if sharpe else 0) + (win_rate * 50) + (pnl / 100 * 20) - (max_dd / 100 * 10)
            fitness = max(0, min(100, fitness))

        return {
            "total_trades": total,
            "fitness_score": fitness,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_dd,
            "annualized_roi_pct": pnl,
            "win_rate": win_rate,
            "total_pnl": pnl,
        }

    def _calculate_weighted_fitness(self, fitness_by_regime: dict[str, dict], fallback_fitness: float = 0.0) -> float:
        """
        Calculate weighted average fitness using regime importance coefficients.

        Harder market conditions (crash, sideways, bear) get higher weights.
        MUST match backtest_service.py logic for consistency.
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
        return max(0.0, min(100.0, weighted_fitness))


# Export same interface
BacktestService = AgentBacktestServiceDev
