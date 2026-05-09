"""
Crucible Test Service - Run mass walk-forward validation on frozen agents.

Tests agents on every asset/candle with $50k paper money.
Scores overall fitness and per-regime (bull, bear, chop, lowvol) fitness.

NOTE: Uses the SAME fitness formula as the main backtest service.
The Crucible is just a more rigorous backtest, not a different scoring system.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Backtest.Services.backtest_service import (
    calculate_backtest_metrics,
    calculate_metrics_by_regime,
)
from Fast_Swarm.local_agents.backtest.engine import create_backtest_engine
from Fast_Swarm.local_agents.core.state import AgentRecord

from ..Models.crucible_models import CrucibleEntry


class CrucibleTestService:
    """Service for running Crucible tests."""

    def __init__(self):
        self.starting_balance = 50000.0

    async def run_crucible_test(
        self,
        session: AsyncSession,
        entry_id: int,
        assets: list[str] | None = None,
    ) -> dict:
        """
        Run a full Crucible test for a snapshot.
        """
        # Get entry
        result = await session.exec(select(CrucibleEntry).where(CrucibleEntry.id == entry_id))
        entry = result.first()

        if not entry:
            raise ValueError(f"Crucible entry {entry_id} not found")

        if entry.status != "pending":
            return {"status": entry.status, "message": "Test already started or completed"}

        # Update status
        entry.status = "running"
        entry.started_at = datetime.utcnow()
        session.add(entry)
        await session.commit()

        try:
            # 1. Prepare assets (every asset in the DB)
            if not assets:
                # In a real scenario, we'd query the OHLCV loader for available assets
                # For now, let's use a broad list
                assets = ["BTC", "ETH", "SOL", "BNB", "ADA", "XRP", "DOT", "LINK", "MATIC", "AVAX"]

            # 2. Setup Backtest Engine
            # We need to map patterns to the format the engine expects
            from ...Patterns.Models.pattern_models import Pattern

            pattern_result = await session.exec(select(Pattern).where(Pattern.pattern_id.in_(entry.assigned_patterns)))
            patterns_list = pattern_result.all()
            pattern_defs = {
                p.pattern_id: {
                    "entry_conditions": p.entry_conditions,
                    "exit_conditions": p.exit_conditions,
                    "fitness_score": p.fitness_score,
                }
                for p in patterns_list
            }

            engine = create_backtest_engine(patterns=pattern_defs)

            # 3. Create AgentRecord for the snapshot
            agent_record = AgentRecord(
                agent_id=entry.agent_id,
                traits=entry.traits,
                pattern_ids=entry.assigned_patterns,
                pattern_weights=entry.pattern_weights,
                generation=0,  # Snapshot is generation 0 / frozen
            )

            # 4. Run Backtest on ALL assets, ALL timeframes, RECENT data only (OOS gauntlet)
            # Crucible tests generalization: multi-timeframe on recent 6-month data
            from datetime import timedelta

            oos_cutoff = datetime.utcnow() - timedelta(days=180)
            crucible_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

            all_trades = []
            for tf in crucible_timeframes:
                tf_trades = engine.run(
                    agent=agent_record,
                    dataset={
                        "assets": assets,
                        "timeframe": tf,
                        "start_ts": int(oos_cutoff.timestamp() * 1000),
                    },
                )
                all_trades.extend(tf_trades)

            # 5. Calculate Metrics and Regime Scores
            # Scored on overall fitness + every regime type (bull, bear, chop, lowvol)
            metrics = self._calculate_crucible_metrics(all_trades)

            # 6. Update Entry
            entry.overall_fitness = metrics["overall_fitness"]
            entry.regime_scores = metrics["regime_scores"]
            entry.status = "completed"
            entry.completed_at = datetime.utcnow()

            # Calculate final balance (relative to metrics)
            entry.current_balance = self.starting_balance * (1 + (metrics["total_pnl_pct"] / 100))

            session.add(entry)
            await session.commit()

            # 7. WISDOM GENERATION: Extract wisdom from successful Crucible completion
            wisdom_id = None
            try:
                from .wisdom_service import WisdomTransferService

                wisdom_service = WisdomTransferService()
                wisdom = await wisdom_service.generate_wisdom_from_entry(
                    session=session,
                    entry_id=entry_id,
                    use_llm=True,  # Use LLM if available, fall back to heuristic
                )
                if wisdom:
                    wisdom_id = wisdom.id
                    print(f"[Crucible] Generated wisdom {wisdom_id} from entry {entry_id}")
            except Exception as e:
                print(f"[Crucible] Wisdom generation failed for entry {entry_id}: {e}")

            # 8. AUTO-GRADUATE: Start paper trading if fitness exceeds threshold
            GRADUATION_THRESHOLD = 40.0  # Minimum Crucible fitness to paper trade
            paper_trading_started = False
            if entry.overall_fitness and entry.overall_fitness >= GRADUATION_THRESHOLD:
                try:
                    from ...Trading.Services.agent_paper_trading_service import AgentPaperTradingService

                    paper_service = AgentPaperTradingService()
                    paper_result = await paper_service.start_paper_trading(
                        session=session,
                        agent_id=entry.agent_id,
                        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
                        initial_balance=50000.0,
                    )
                    paper_trading_started = "error" not in paper_result
                    if paper_trading_started:
                        print(f"[Crucible] GRADUATED: Agent {entry.agent_id} → paper trading (fitness={entry.overall_fitness:.1f})")
                    else:
                        print(f"[Crucible] Paper trading start failed: {paper_result}")
                except Exception as pt_err:
                    print(f"[Crucible] Paper trading graduation failed: {pt_err}")

            return {
                "entry_id": entry_id,
                "status": "completed",
                "overall_fitness": entry.overall_fitness,
                "regime_scores": entry.regime_scores,
                "total_trades": len(all_trades),
                "wisdom_id": wisdom_id,
                "graduated_to_paper": paper_trading_started,
            }

        except Exception as e:
            entry.status = "failed"
            session.add(entry)
            await session.commit()
            print(f"[Crucible] Test failed for entry {entry_id}: {e}")
            return {"status": "failed", "error": str(e)}

    def _calculate_crucible_metrics(self, trades: list[Any]) -> dict:
        """
        Calculate metrics for Crucible snapshots.

        Uses the SAME fitness formula as the main backtest service.
        The Crucible is just a more rigorous backtest across all assets/regimes.
        """
        if not trades:
            return {
                "overall_fitness": 0.0,
                "total_pnl_pct": 0.0,
                "regime_scores": {"bull": 0.0, "bear": 0.0, "chop": 0.0, "lowvol": 0.0},
                "metrics": {},
            }

        # Use the standard backtest metrics (same as everywhere else)
        metrics = calculate_backtest_metrics(trades)

        # Calculate overall fitness using the standard formula
        # fitness = (sharpe * 10) + (win_rate * 50) + (roi / 100 * 20) - (max_dd / 100 * 10)
        sharpe = metrics.get("sharpe_ratio", 0) or 0
        win_rate = metrics.get("win_rate", 0) or 0
        roi = metrics.get("total_roi_pct", 0) or 0
        max_dd = metrics.get("max_drawdown_pct", 0) or 0

        overall_fitness = (sharpe * 10) + (win_rate * 50) + (roi / 100 * 20) - (max_dd / 100 * 10)
        overall_fitness = max(0.0, min(100.0, overall_fitness))

        # Build regime map from trade data
        regime_map = {}
        for trade in trades:
            trade_id = getattr(trade, "trade_id", None)
            regime = getattr(trade, "regime", "unknown")
            if trade_id:
                regime_map[trade_id] = regime.lower() if regime else "unknown"

        # Calculate per-regime fitness using standard formula
        regime_metrics = calculate_metrics_by_regime(trades, regime_map)

        # Extract just the fitness scores for each regime
        regime_scores = {
            "bull": regime_metrics.get("bull", {}).get("fitness", 0.0),
            "bear": regime_metrics.get("bear", {}).get("fitness", 0.0),
            "chop": regime_metrics.get("chop", {}).get("fitness", 0.0),
            "lowvol": regime_metrics.get("lowvol", {}).get("fitness", 0.0),
        }

        return {
            "overall_fitness": overall_fitness,
            "total_pnl_pct": metrics.get("total_roi_pct", 0.0),
            "regime_scores": regime_scores,
            "metrics": metrics,  # Include full metrics for transparency
        }
