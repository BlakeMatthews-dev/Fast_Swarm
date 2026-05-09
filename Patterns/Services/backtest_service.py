"""
Pattern Backtest Service - Run backtests for patterns.

This service handles backtesting patterns and updating their fitness scores.
All data comes from PostgreSQL enhanced_candles table (5.2M+ rows).

REGIME TESTING:
Patterns are tested across canonical periods (crash, bull, bear, etc.)
to identify specialized patterns for different market conditions.
"""

import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

# Add local_agents to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "local_agents"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.canonical_periods import (
    get_canonical_periods_for_backtesting,
)
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits

from ..Models.pattern_models import Pattern


class PatternBacktestService:
    """Service for backtesting patterns using PostgreSQL data."""

    # Regime importance weights (same as AgentBacktestService)
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

    # Random window generation settings
    WINDOWS_PER_ASSET_PER_TF = 10  # Fewer than agents since patterns are faster to test
    TIMEFRAME_CONFIG = {
        "1m": {"candles": 1440},  # 1 day
        "15m": {"candles": 384},  # 4 days
        "1h": {"candles": 500},  # ~21 days
        "1d": {"candles": 90},  # 90 days
    }

    def __init__(self):
        """
        Initialize backtest service.

        Data is loaded from PostgreSQL enhanced_candles table (5.2M+ rows)
        via the OHLCVLoader which queries the database directly.
        """
        # OHLCVLoader now uses PostgreSQL - no file path needed
        self.loader = OHLCVLoader()

    async def backtest_patterns(
        self,
        session: AsyncSession,
        pattern_ids: list[str],
        assets: list[str] = None,
        timeframe: str = "1h",
        history_bars: int = 500,
    ) -> dict[str, dict]:
        """
        Run backtests for multiple patterns.

        Args:
            session: Database session
            pattern_ids: List of pattern IDs to backtest
            assets: List of assets to test
            timeframe: Timeframe for backtesting
            history_bars: Number of historical bars

        Returns:
            Dict mapping pattern_id to backtest results
        """
        if assets is None:
            assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        results = {}

        # Get patterns from DB
        result = await session.exec(select(Pattern).where(Pattern.pattern_id.in_(pattern_ids)))
        patterns = result.all()

        # Use default traits for pattern testing
        default_traits = AgentTraits()
        config = BacktestConfig.from_traits(default_traits)

        for pattern in patterns:
            try:
                # Create pattern dict for engine
                pattern_dict = {
                    pattern.pattern_id: {
                        "pattern_id": pattern.pattern_id,
                        "entry_conditions": pattern.entry_conditions,
                        "exit_conditions": pattern.exit_conditions,
                    }
                }

                # Create a test AgentRecord for pattern backtesting
                test_agent = AgentRecord(
                    agent_id=f"pattern_test_{pattern.pattern_id}",
                    agent_name=f"PatternTest_{pattern.name}",
                    traits=default_traits.__dict__,
                    pattern_ids=[pattern.pattern_id],
                    pattern_weights={pattern.pattern_id: 1.0},
                )

                # Create backtest engine with pattern
                engine = LocalBacktestEngine(
                    loader=self.loader,
                    config=config,
                    patterns=pattern_dict,
                )

                # Run backtest using proper interface
                all_trades = engine.run(
                    agent=test_agent,
                    dataset={
                        "assets": [a.replace("/USDT", "").replace("-USD", "") for a in assets],
                        "timeframe": timeframe,
                    },
                )

                # Calculate metrics
                metrics = self._calculate_metrics(all_trades)

                # Update pattern in DB
                pattern.fitness_score = metrics.get("fitness_score", 0.0)
                pattern.sharpe_ratio = metrics.get("sharpe_ratio")
                pattern.sortino_ratio = metrics.get("sortino_ratio")
                pattern.calmar_ratio = metrics.get("calmar_ratio")
                pattern.max_drawdown_pct = metrics.get("max_drawdown_pct", 0.0)
                pattern.annualized_roi_pct = metrics.get("annualized_roi_pct", 0.0)
                pattern.win_rate = metrics.get("win_rate")
                pattern.total_trades = metrics.get("total_trades", 0)
                pattern.avg_trade_pct = metrics.get("avg_trade_pct", 0.0)
                pattern.last_backtest_at = datetime.utcnow()
                pattern.periods_tested = (pattern.periods_tested or 0) + 1

                session.add(pattern)
                results[pattern.pattern_id] = metrics

            except Exception as e:
                print(f"Error backtesting pattern {pattern.pattern_id}: {e}")
                results[pattern.pattern_id] = {"error": str(e)}
                continue

        await session.commit()
        return results

    async def backtest_patterns_by_regime(
        self,
        session: AsyncSession,
        pattern_ids: list[str],
        assets: list[str] = None,
        timeframes: list[str] = None,
        include_random: bool = True,
    ) -> dict[str, dict]:
        """
        Run backtests for patterns across ALL canonical periods AND random windows.

        This tests each pattern against:
        - Canonical periods: crash, bull, bear, recovery, blowoff, sideways
        - Random windows: diverse market conditions across timeframes

        Returns per-regime fitness with weighted overall fitness.
        """
        if assets is None:
            assets = ["BTC", "ETH", "SOL"]
        if timeframes is None:
            timeframes = ["1h", "1d", "15m", "1m"]

        # Get canonical periods
        canonical_periods = get_canonical_periods_for_backtesting(
            assets=assets,
            timeframes=timeframes,
            regimes=None,
        )

        # Get random windows
        all_windows = []
        if include_random:
            random_windows = await self._generate_random_windows(session, assets, timeframes)
            all_windows.extend(random_windows)
            print(f"[PatternBacktest] Generated {len(random_windows)} random windows")

        # Add canonical periods as windows
        for period in canonical_periods:
            all_windows.append(
                {
                    "asset": period["asset"],
                    "timeframe": period["timeframe"],
                    "start_ts": period["start_ts"],
                    "end_ts": period["end_ts"],
                    "regime": period["regime"],
                }
            )

        print(
            f"[PatternBacktest] Testing {len(pattern_ids)} patterns across {len(all_windows)} total windows "
            f"({len(canonical_periods)} canonical + {len(all_windows) - len(canonical_periods)} random)"
        )

        results = {}
        result = await session.exec(select(Pattern).where(Pattern.pattern_id.in_(pattern_ids)))
        patterns = result.all()

        default_traits = AgentTraits()
        config = BacktestConfig.from_traits(default_traits)

        for pattern in patterns:
            try:
                pattern_dict = {
                    pattern.pattern_id: {
                        "pattern_id": pattern.pattern_id,
                        "entry_conditions": pattern.entry_conditions,
                        "exit_conditions": pattern.exit_conditions,
                    }
                }

                test_agent = AgentRecord(
                    agent_id=f"pattern_test_{pattern.pattern_id}",
                    agent_name=f"PatternTest_{pattern.name}",
                    traits=default_traits.__dict__,
                    pattern_ids=[pattern.pattern_id],
                    pattern_weights={pattern.pattern_id: 1.0},
                )

                # Track results by regime (canonical + random_*)
                regime_results: dict[str, list] = {}

                for window in all_windows:
                    regime = window["regime"]
                    if regime not in regime_results:
                        regime_results[regime] = []
                    try:
                        engine = LocalBacktestEngine(
                            loader=self.loader,
                            config=config,
                            patterns=pattern_dict,
                        )
                        trades = engine.run(
                            agent=test_agent,
                            dataset={
                                "assets": [window["asset"]],
                                "timeframe": window["timeframe"],
                                "start_ts": window["start_ts"],
                                "end_ts": window["end_ts"],
                            },
                        )
                        metrics = self._calculate_metrics(trades)
                        regime_results[regime].append(metrics)
                    except Exception:
                        continue

                fitness_by_regime = {}
                best_regime = None
                best_regime_fitness = 0.0

                for regime, metrics_list in regime_results.items():
                    if metrics_list:
                        avg_fitness = sum(m.get("fitness_score", 0) for m in metrics_list) / len(metrics_list)
                        total_trades = sum(m.get("total_trades", 0) for m in metrics_list)
                        avg_win_rate = sum(m.get("win_rate", 0) or 0 for m in metrics_list) / len(metrics_list)
                        avg_sharpe_vals = [
                            m.get("sharpe_ratio") for m in metrics_list if m.get("sharpe_ratio") is not None
                        ]
                        avg_sharpe = sum(avg_sharpe_vals) / len(avg_sharpe_vals) if avg_sharpe_vals else None

                        fitness_by_regime[regime] = {
                            "fitness": round(avg_fitness, 2),
                            "trades": total_trades,
                            "win_rate": round(avg_win_rate, 4),
                            "sharpe": round(avg_sharpe, 3) if avg_sharpe else None,
                            "windows_tested": len(metrics_list),
                        }

                        if avg_fitness > best_regime_fitness:
                            best_regime_fitness = avg_fitness
                            best_regime = regime

                # Use weighted fitness (crash/sideways/bear weighted higher than bull)
                overall_fitness = self._calculate_weighted_fitness(fitness_by_regime, fallback_fitness=0.0)

                pattern.fitness_by_regime = fitness_by_regime
                pattern.best_regime = best_regime
                pattern.best_regime_fitness = best_regime_fitness
                pattern.fitness_score = overall_fitness
                pattern.last_backtest_at = datetime.utcnow()
                pattern.periods_tested = (pattern.periods_tested or 0) + len(all_windows)

                session.add(pattern)
                results[pattern.pattern_id] = {
                    "fitness_by_regime": fitness_by_regime,
                    "best_regime": best_regime,
                    "best_regime_fitness": best_regime_fitness,
                    "overall_fitness": overall_fitness,
                    "weighted": True,
                }
                print(
                    f"[PatternBacktest] {pattern.pattern_id}: weighted_fitness={overall_fitness:.1f}, "
                    f"best={best_regime} ({best_regime_fitness:.1f})"
                )

            except Exception as e:
                print(f"[PatternBacktest] Error testing {pattern.pattern_id}: {e}")
                results[pattern.pattern_id] = {"error": str(e)}

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
                "avg_trade_pct": 0.0,
            }

        # Calculate basic stats (guard against None pnl_pct)
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.pnl_pct is not None and t.pnl_pct > 0)
        win_rate = wins / total_trades if total_trades > 0 else 0

        # Calculate PnL (filter None values)
        total_pnl = sum(t.pnl_pct for t in trades if t.pnl_pct is not None)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

        # Calculate returns for Sharpe/Sortino (exclude None)
        returns = [t.pnl_pct for t in trades if t.pnl_pct is not None]

        # Sharpe ratio
        import statistics

        if len(returns) > 1:
            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe_raw = (mean_return / std_return) if std_return > 0 else 0
            # Cap at ±6 to filter calculation anomalies while allowing exceptional strategies
            sharpe = max(-6.0, min(6.0, sharpe_raw))
        else:
            sharpe = None

        # Sortino ratio
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) > 1:
            downside_std = statistics.stdev(downside_returns)
            sortino = (avg_pnl / downside_std) if downside_std > 0 else 0
        else:
            sortino = None

        # Max drawdown (skip trades with None pnl)
        equity = 100.0
        peak = equity
        max_dd = 0.0
        for trade in trades:
            if trade.pnl_pct is None:
                continue
            equity *= 1 + trade.pnl_pct / 100
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Calmar ratio
        annualized_roi = total_pnl
        calmar = (annualized_roi / max_dd) if max_dd > 0 else 0

        # Fitness score
        fitness = (sharpe * 10 if sharpe else 0) + (win_rate * 50) + (annualized_roi / 100) * 20 - (max_dd / 100) * 10

        return {
            "total_trades": total_trades,
            "fitness_score": max(0, fitness),
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown_pct": max_dd,
            "annualized_roi_pct": annualized_roi,
            "win_rate": win_rate,
            "avg_trade_pct": avg_pnl,
        }

    async def _generate_random_windows(
        self, session: AsyncSession, assets: list[str], timeframes: list[str] = None
    ) -> list[dict]:
        """
        Generate random backtest windows for pattern testing.
        Similar to AgentBacktestService but with fewer windows per asset.
        """
        import random

        from sqlalchemy import text

        windows = []
        timeframes = timeframes or list(self.TIMEFRAME_CONFIG.keys())

        tf_ms = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }

        for timeframe in timeframes:
            if timeframe not in self.TIMEFRAME_CONFIG:
                continue

            config = self.TIMEFRAME_CONFIG[timeframe]
            window_candles = config["candles"]
            window_ms = window_candles * tf_ms.get(timeframe, 3_600_000)

            for asset in assets:
                try:
                    result = await session.execute(
                        text("""
                            SELECT
                                EXTRACT(EPOCH FROM MIN(time)) * 1000 as min_ts,
                                EXTRACT(EPOCH FROM MAX(time)) * 1000 as max_ts,
                                COUNT(*) as candle_count
                            FROM enhanced_candles
                            WHERE symbol = :asset AND timeframe = :tf
                        """),
                        {"asset": asset, "tf": timeframe},
                    )
                    row = result.fetchone()
                    if not row or row[0] is None or row[1] is None:
                        continue

                    min_ts, max_ts, candle_count = int(row[0]), int(row[1]), int(row[2] or 0)
                    available_range = max_ts - min_ts - window_ms

                    if available_range <= 0 or candle_count < window_candles:
                        continue

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
                except Exception as e:
                    print(f"[PatternBacktest] Could not get range for {asset}/{timeframe}: {e}")
                    continue

        return windows

    def _calculate_weighted_fitness(self, fitness_by_regime: dict[str, dict], fallback_fitness: float = 0.0) -> float:
        """
        Calculate weighted average fitness using regime importance coefficients.
        Same logic as AgentBacktestService for consistency.
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
