"""
Agent Paper Trading Service - Direct agent -> paper trading bridge for MVP.

This service bypasses the coach/trio system and allows a single agent
to paper trade directly against live market data.

Flow:
1. Agent evaluates market conditions using its patterns
2. Agent generates a signal (buy/sell/hold)
3. Service executes paper trade at current market price
4. Trade is recorded to LiveTradeUnified table

This is the MVP path: Pattern -> Agent -> Paper Trade -> (later) Live Trade
The full path (Coach -> Trio -> Vote) is added post-MVP.

State Persistence:
- Sessions persisted to paper_trading_sessions table (survives restarts)
- Open positions restored from LiveTradeUnified on startup
- Balance/PnL recalculated from trade history
"""

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Numeric, Text, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

from ...Agents.Models.agent_models import Agent
from ...Infrastructure.Models.exchange_models import LiveTradeUnified

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Accumulation assets -- majors that historically recover from drawdowns.
# These skip hard stop losses; trailing stops protect profit instead.
# Ported from local_agents/backtest/engine.py
# ---------------------------------------------------------------------------
ACCUMULATION_ASSETS = {
    "BTC", "ETH", "SOL",
    "BTCUSDT", "ETHUSDT", "SOLUSDT",
    "BTC-USDT", "ETH-USDT", "SOL-USDT",
    "BTC-USD", "ETH-USD", "SOL-USD",
    "BTCUSD", "ETHUSD", "SOLUSD",
}


# Round-trip trading costs (fee + slippage, both sides)
_FEE_PCT = 0.075 / 100       # 0.075% per side (Crypto.com taker fee)
_SLIPPAGE_PCT = 0.02 / 100   # 0.02% estimated slippage per side
TOTAL_COST_PCT = (_FEE_PCT + _SLIPPAGE_PCT) * 2  # ~0.19% round trip


def _calculate_dynamic_trail(
    profit_pct: float,
    base_trail: float = 2.0,
    max_trail: float = 12.0,
    log_scale: float = 2.5,
) -> float:
    """Logarithmic trail that widens with profit (2% at 0% -> 12% cap)."""
    if profit_pct <= 0:
        return base_trail
    return min(max_trail, base_trail + log_scale * math.log1p(profit_pct / 10))


class PaperTradingSession(SQLModel, table=True):
    """Persists paper trading session state across restarts."""

    __tablename__ = "paper_trading_sessions"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(unique=True, index=True)
    agent_name: str = ""
    initial_balance: float = 10000.0
    current_balance: float = 10000.0
    symbols: str = "[]"  # JSON list
    trades_count: int = 0
    total_pnl: float = 0.0
    paused: bool = False
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AgentPaperTradingService:
    """
    Direct agent -> paper trading bridge.

    For MVP: One agent trades directly without coach/trio overhead.

    Circuit breaker: Auto-stops agent if drawdown exceeds MAX_DRAWDOWN_PCT.
    State persistence: Sessions survive container restarts via DB.
    """

    MAX_DRAWDOWN_PCT = 25.0  # Kill switch: stop trading if drawdown > 25%
    # NOTE: This is absolute drawdown. In a bear market, agents that outperform
    # buy-and-hold may still hit this. TODO: Track benchmark drawdown and compare
    # agent drawdown relative to benchmark (alpha drawdown) instead of absolute.

    def __init__(self):
        self.active_positions: dict[str, dict] = {}  # agent_id -> position info
        self._peak_balances: dict[str, float] = {}  # agent_id -> highest balance seen
        self._restored = False  # Track if we've restored from DB

    def _check_circuit_breaker(self, agent_id: str, current_balance: float, initial_balance: float) -> bool:
        """
        Check if agent has exceeded max drawdown. Returns True if trading should stop.

        Tracks peak balance and calculates drawdown from peak.
        """
        peak = self._peak_balances.get(agent_id, initial_balance)
        if current_balance > peak:
            self._peak_balances[agent_id] = current_balance
            peak = current_balance

        if peak > 0:
            drawdown_pct = ((peak - current_balance) / peak) * 100
            if drawdown_pct >= self.MAX_DRAWDOWN_PCT:
                print(
                    f"[CIRCUIT BREAKER] Agent {agent_id}: drawdown {drawdown_pct:.1f}% >= {self.MAX_DRAWDOWN_PCT}% "
                    f"(balance: ${current_balance:.2f}, peak: ${peak:.2f}). STOPPING."
                )
                return True
        return False

    async def restore_sessions(self, session: AsyncSession) -> int:
        """
        Restore paper trading sessions from DB after restart.

        Rebuilds active_positions from PaperTradingSession rows and
        reloads open positions from LiveTradeUnified.
        Returns number of sessions restored.
        """
        if self._restored:
            return 0

        try:
            # Ensure table exists
            from ...Database import get_async_engine
            async with get_async_engine().begin() as conn:
                await conn.run_sync(PaperTradingSession.metadata.create_all)

            # Load all active sessions
            result = await session.exec(select(PaperTradingSession))
            sessions = result.all()

            restored = 0
            for s in sessions:
                symbols = json.loads(s.symbols) if s.symbols else ["BTC-USDT"]

                self.active_positions[s.agent_id] = {
                    "agent_id": s.agent_id,
                    "agent_name": s.agent_name,
                    "balance": s.current_balance,
                    "symbols": symbols,
                    "positions": {},
                    "started_at": s.started_at or datetime.now(timezone.utc),
                    "trades_count": s.trades_count,
                    "total_pnl": s.total_pnl,
                    "paused": s.paused,
                }

                # Restore open positions from LiveTradeUnified
                open_trades = await session.exec(
                    select(LiveTradeUnified).where(
                        LiveTradeUnified.agent_id == s.agent_id,
                        LiveTradeUnified.source == "paper",
                        LiveTradeUnified.status == "open",
                    )
                )
                for trade in open_trades.all():
                    entry_px = float(trade.entry_price or 0)
                    self.active_positions[s.agent_id]["positions"][trade.symbol] = {
                        "trade_id": trade.trade_id,
                        "side": trade.side,
                        "entry_price": entry_px,
                        "size": float(trade.size or 0),
                        "size_usd": float(trade.size_usd or 0),
                        "entry_time": trade.entry_time or datetime.now(timezone.utc),
                        # Trailing stop state -- on restore we reset peak to entry
                        # so the trail starts fresh (conservative; no MFE data saved)
                        "peak_price": entry_px,
                        "trailing_stop_price": 0.0,
                    }

                # Restore peak balance for circuit breaker
                self._peak_balances[s.agent_id] = max(s.initial_balance, s.current_balance)

                restored += 1
                open_count = len(self.active_positions[s.agent_id]["positions"])
                logger.info(
                    "Restored paper trading: %s (%s) bal=$%.2f pnl=$%.2f open=%d",
                    s.agent_id[:8], s.agent_name, s.current_balance, s.total_pnl, open_count,
                )

            self._restored = True
            if restored:
                logger.info("Restored %d paper trading sessions from DB", restored)
            return restored

        except Exception as e:
            logger.error("Failed to restore paper trading sessions: %s", e)
            self._restored = True
            return 0

    async def _persist_session(self, session: AsyncSession, agent_id: str) -> None:
        """Persist current session state to DB."""
        if agent_id not in self.active_positions:
            return

        info = self.active_positions[agent_id]
        now = datetime.now(timezone.utc)

        try:
            result = await session.exec(
                select(PaperTradingSession).where(PaperTradingSession.agent_id == agent_id)
            )
            existing = result.first()

            if existing:
                existing.current_balance = info["balance"]
                existing.trades_count = info["trades_count"]
                existing.total_pnl = info["total_pnl"]
                existing.paused = info.get("paused", False)
                existing.symbols = json.dumps(info["symbols"])
                existing.updated_at = now
                session.add(existing)
            else:
                new_session = PaperTradingSession(
                    agent_id=agent_id,
                    agent_name=info["agent_name"],
                    initial_balance=info["balance"],
                    current_balance=info["balance"],
                    symbols=json.dumps(info["symbols"]),
                    trades_count=info["trades_count"],
                    total_pnl=info["total_pnl"],
                    paused=info.get("paused", False),
                    started_at=info["started_at"],
                    updated_at=now,
                )
                session.add(new_session)

            await session.commit()
        except Exception as e:
            logger.warning("Failed to persist session for %s: %s", agent_id[:8], e)

    async def _remove_session(self, session: AsyncSession, agent_id: str) -> None:
        """Remove a session from DB (on stop)."""
        try:
            result = await session.exec(
                select(PaperTradingSession).where(PaperTradingSession.agent_id == agent_id)
            )
            existing = result.first()
            if existing:
                await session.delete(existing)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to remove session for %s: %s", agent_id[:8], e)

    async def start_paper_trading(
        self,
        session: AsyncSession,
        agent_id: str,
        symbols: list[str] | None = None,
        initial_balance: float = 10000.0,
    ) -> dict:
        """
        Start paper trading for an agent.

        Args:
            session: Database session
            agent_id: Agent to start trading
            symbols: Symbols to trade (default: BTC-USDT)
            initial_balance: Starting paper balance

        Returns:
            Status dict with agent info
        """
        # Get agent
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return {"error": "Agent not found", "agent_id": agent_id}

        if agent.status != "active":
            return {"error": "Agent not active", "status": agent.status}

        symbols = symbols or ["BTC-USDT"]

        # Initialize position tracking
        self.active_positions[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "balance": initial_balance,
            "symbols": symbols,
            "positions": {},  # symbol -> position
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
        }

        logger.info(
            "Started paper trading for agent %s (%s) with $%.2f on %s",
            agent_id[:8],
            agent.name,
            initial_balance,
            symbols,
        )

        # Persist to DB so session survives restarts
        await self._persist_session(session, agent_id)

        return {
            "status": "started",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "balance": initial_balance,
            "symbols": symbols,
        }

    async def stop_paper_trading(self, session: AsyncSession, agent_id: str) -> dict:
        """Stop paper trading for an agent."""
        if agent_id not in self.active_positions:
            return {"error": "Agent not actively trading", "agent_id": agent_id}

        # Remove from DB
        await self._remove_session(session, agent_id)

        position_info = self.active_positions.pop(agent_id)
        duration = datetime.now(timezone.utc) - position_info["started_at"]

        return {
            "status": "stopped",
            "agent_id": agent_id,
            "duration_seconds": duration.total_seconds(),
            "trades_count": position_info["trades_count"],
            "total_pnl": position_info["total_pnl"],
            "final_balance": position_info["balance"],
        }

    async def evaluate_and_trade(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        current_price: float,
        candle_data: dict,
        regime: str = "unknown",
    ) -> dict | None:
        """
        Evaluate market conditions and potentially execute a paper trade.

        Args:
            session: Database session
            agent_id: Agent making the decision
            symbol: Trading symbol
            current_price: Current market price
            candle_data: OHLCV + indicators for pattern matching
            regime: Current market regime

        Returns:
            Trade info if a trade was executed, None otherwise
        """
        if agent_id not in self.active_positions:
            return None

        # Get agent
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent or not agent.assigned_patterns:
            return None

        position_info = self.active_positions[agent_id]

        # =================================================================
        # Circuit Breaker Check - drawdown kill switch
        # If drawdown exceeds MAX_DRAWDOWN_PCT, stop the agent entirely
        # and persist the removal to the DB so it doesn't restart.
        # =================================================================
        initial_balance = 10000.0  # Default; try to get from DB session record
        try:
            cb_result = await session.exec(
                select(PaperTradingSession).where(PaperTradingSession.agent_id == agent_id)
            )
            cb_record = cb_result.first()
            if cb_record:
                initial_balance = cb_record.initial_balance
        except Exception:
            pass

        if self._check_circuit_breaker(agent_id, position_info["balance"], initial_balance):
            logger.warning(
                "Circuit breaker tripped for agent %s — removing from DB and active positions",
                agent_id[:8],
            )
            # Persist removal to DB so session doesn't resurrect on restart
            await self._remove_session(session, agent_id)
            # Remove from in-memory state
            self.active_positions.pop(agent_id, None)
            self._peak_balances.pop(agent_id, None)
            return {"action": "circuit_breaker", "agent_id": agent_id, "balance": position_info["balance"]}

        current_position = position_info["positions"].get(symbol)

        # =================================================================
        # Bear Protection — BearProtectionService with motion derivatives
        # Evaluates acceleration + jerk z-scores across 1h/4h/1d timeframes.
        # DEFENSIVE regime → force-close open positions, block new entries.
        # =================================================================
        bear_regime = None
        bear_regime_result = None  # Full RegimeState for conviction sizing
        try:
            from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
                BearProtectionService,
                MarketState,
                Regime,
            )
            bear_svc = BearProtectionService()
            bear_state = MarketState(
                time=datetime.now(timezone.utc),
                symbol=symbol,
                tf_1h_vel=candle_data.get("close_velocity_zscore"),
                tf_1h_acc=candle_data.get("close_acceleration_zscore"),
                tf_1h_adx_jerk=candle_data.get("adx_14_jerk_zscore"),
                # Higher TFs come from the multi-TF candle merge in Main.py
                tf_4h_vel=candle_data.get("close_velocity_zscore_4h"),
                tf_4h_acc=candle_data.get("close_acceleration_zscore_4h"),
                tf_4h_adx_jerk=candle_data.get("adx_14_jerk_zscore_4h"),
                tf_1d_vel=candle_data.get("close_velocity_zscore_1d"),
                tf_1d_acc=candle_data.get("close_acceleration_zscore_1d"),
                tf_1d_adx_jerk=candle_data.get("adx_14_jerk_zscore_1d"),
            )
            regime_result = bear_svc.evaluate(bear_state)
            bear_regime = regime_result.regime
            bear_regime_result = regime_result

            if bear_regime == Regime.DEFENSIVE:
                logger.warning(
                    "BEAR PROTECTION [%s]: DEFENSIVE regime (%s) — "
                    "acc=%.2f, adx_jerk=%.2f",
                    symbol,
                    regime_result.triggered_by,
                    candle_data.get("close_acceleration_zscore", 0),
                    candle_data.get("adx_14_jerk_zscore", 0),
                )
                if current_position is not None:
                    logger.warning(
                        "BEAR PROTECTION: Force closing %s position for %s",
                        current_position.get("side", "?"), symbol,
                    )
                    return await self._close_position(
                        session, agent, symbol, current_price, candle_data, "defensive"
                    )
                # Block new entries during DEFENSIVE
                return None
        except ImportError:
            # Fallback: use the raw defensive_trigger flag from candle
            defensive_trigger = candle_data.get("defensive_trigger")
            if defensive_trigger == 1:
                if current_position is not None:
                    return await self._close_position(
                        session, agent, symbol, current_price, candle_data, "defensive"
                    )
                return None
        except Exception as e:
            logger.debug("Bear protection eval error: %s", e)

        # =================================================================
        # EXIT CHECK — runs FIRST, regardless of pattern signal.
        # Risk management always takes priority over entry signals.
        # Ported from backtest engine _check_exit():
        #   1. Hard SL (skip for accumulation assets like BTC/ETH/SOL)
        #   2. Dynamic trailing stop (widens with profit)
        #   3. Pattern exit conditions
        # =================================================================
        if current_position is not None:
            should_exit, exit_reason = self._check_exit(
                current_position, symbol, current_price, candle_data, agent
            )
            if should_exit:
                return await self._close_position(
                    session, agent, symbol, current_price, candle_data, exit_reason
                )

        # =================================================================
        # Pattern evaluation — produces entry/exit signal
        # =================================================================

        # Inject sentiment + regime data into candle_data for pattern evaluation
        try:
            from Fast_Swarm.Infrastructure.Services.sentiment_service import SentimentService
            sentiment = SentimentService()
            fg = await sentiment.get_fear_greed_current(session)
            if fg:
                candle_data["fear_greed"] = fg.value
                candle_data["fear_greed_class"] = fg.classification
        except Exception:
            pass  # Sentiment is optional

        # Auto-detect market regime from current indicators
        try:
            from Fast_Swarm.local_agents.trading_utilities.pattern_matching import classify_regime

            if "return_10" not in candle_data:
                pve9 = candle_data.get("price_vs_ema_9_pct")
                if pve9 is not None:
                    candle_data["return_10"] = pve9
            if "return_20" not in candle_data:
                pve21 = candle_data.get("price_vs_ema_21_pct")
                if pve21 is not None:
                    candle_data["return_20"] = pve21
            if "volatility_percentile" not in candle_data:
                natr = candle_data.get("natr_14")
                if natr is not None:
                    candle_data["volatility_percentile"] = min(100, max(0, natr * 15))

            detected_regime = classify_regime(candle_data)
            candle_data["regime"] = detected_regime
            if regime == "unknown":
                regime = detected_regime
        except Exception:
            pass

        signal = await self._evaluate_patterns(agent, candle_data)

        if signal == "hold":
            return None

        # =================================================================
        # Action dispatch
        # =================================================================
        if current_position is None and signal in ("buy", "long"):
            return await self._open_position(
                session, agent, symbol, "long", current_price, candle_data, regime,
                bear_regime_result=bear_regime_result,
            )
        elif current_position is None and signal in ("sell", "short"):
            return await self._open_position(
                session, agent, symbol, "short", current_price, candle_data, regime,
                bear_regime_result=bear_regime_result,
            )
        elif current_position is not None and signal == "close":
            return await self._close_position(
                session, agent, symbol, current_price, candle_data, regime
            )
        # buy/sell while holding = acknowledged but no scale-in yet (future)

        return None

    # =================================================================
    # Exit check — ported from backtest engine _check_exit().
    #
    # Priority:
    #   1. Hard SL (10% default, skipped for BTC/ETH/SOL)
    #   2. Dynamic trailing stop (2% base, widens logarithmically to 12%)
    #   3. Pattern exit conditions via evaluate_conditions()
    #
    # Does NOT include time-based exits (fees for no signal = waste).
    # =================================================================
    def _check_exit(
        self,
        position: dict,
        symbol: str,
        current_price: float,
        candle_data: dict,
        agent: Agent,
    ) -> tuple[bool, str]:
        """
        Check if an open position should be closed.

        Mutates position['peak_price'] and position['trailing_stop_price']
        to ratchet the trailing stop. Returns (should_exit, reason).
        """
        entry_price = position.get("entry_price", 0)
        if entry_price <= 0:
            return True, "invalid_entry_price"

        side = position.get("side", "long")
        if side == "long":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        # --- 1. Hard stop loss (skip for accumulation assets) ---
        symbol_upper = symbol.upper()
        base_sym = symbol_upper.replace("-USDT", "").replace("-USD", "").replace("USDT", "").replace("USD", "")
        is_accumulation = symbol_upper in ACCUMULATION_ASSETS or base_sym in {"BTC", "ETH", "SOL"}

        # SL from agent traits or 10% default
        sl_tightness = (agent.traits or {}).get("stop_loss_tightness", 0.5)
        sl_pct = -(3 + sl_tightness * 17)  # 3% (tight) to 20% (loose), matches traits.py
        if not is_accumulation and pnl_pct <= sl_pct:
            logger.info(
                "HARD SL for %s %s: %.1f%% <= %.1f%%",
                agent.agent_id[:8], symbol, pnl_pct, sl_pct,
            )
            return True, "stop_loss"

        # --- 2. Hybrid trailing stop (ATR floor + profit scaling + breakeven lock) ---
        # Update peak price (ratchet only)
        peak = position.get("peak_price", entry_price)
        if side == "long":
            if current_price > peak:
                position["peak_price"] = current_price
                peak = current_price
        else:
            if peak == 0 or current_price < peak:
                position["peak_price"] = current_price
                peak = current_price

        # ATR-based floor: adapts to current market volatility
        atr = candle_data.get("atr_14") or candle_data.get("atr_7") or 0
        if atr > 0 and current_price > 0:
            atr_trail_pct = (atr * 2.0 / current_price) * 100  # 2x ATR
        else:
            atr_trail_pct = 2.0  # Fallback when ATR unavailable

        # Profit-scaled bonus: widens trail as profit grows
        profit_bonus = _calculate_dynamic_trail(pnl_pct) - 2.0  # 0% at breakeven, up to 10%

        # Hybrid: ATR floor + profit bonus
        trail_pct = atr_trail_pct + max(0, profit_bonus)

        # Breakeven lock: once profit exceeds round-trip fees, never let
        # the stop drop below entry. No reason to give back cleared fees.
        if side == "long":
            breakeven_price = entry_price * (1 + TOTAL_COST_PCT)
        else:
            breakeven_price = entry_price * (1 - TOTAL_COST_PCT)
        above_fees = pnl_pct > (TOTAL_COST_PCT * 100)

        # Calculate trailing stop level and ratchet
        if side == "long":
            new_stop = peak * (1 - trail_pct / 100)
            # Breakeven lock: if we've cleared fees, stop floor = entry + fees
            if above_fees and new_stop < breakeven_price:
                new_stop = breakeven_price
            if new_stop > position.get("trailing_stop_price", 0):
                position["trailing_stop_price"] = new_stop
            if position["trailing_stop_price"] > 0 and current_price <= position["trailing_stop_price"]:
                reason = "breakeven_lock" if position["trailing_stop_price"] <= breakeven_price * 1.001 else "trailing_stop"
                logger.info(
                    "EXIT [%s] %s %s: price %.2f <= stop %.2f "
                    "(atr_trail=%.1f%%, profit_bonus=%.1f%%, pnl=%.1f%%)",
                    reason, agent.agent_id[:8], symbol, current_price,
                    position["trailing_stop_price"], atr_trail_pct, profit_bonus, pnl_pct,
                )
                return True, reason
        else:
            new_stop = peak * (1 + trail_pct / 100)
            if above_fees and new_stop > breakeven_price:
                new_stop = breakeven_price
            cur_stop = position.get("trailing_stop_price", 0)
            if cur_stop == 0 or new_stop < cur_stop:
                position["trailing_stop_price"] = new_stop
            if position["trailing_stop_price"] > 0 and current_price >= position["trailing_stop_price"]:
                reason = "breakeven_lock" if position["trailing_stop_price"] >= breakeven_price * 0.999 else "trailing_stop"
                logger.info(
                    "EXIT [%s] %s %s: price %.2f >= stop %.2f "
                    "(atr_trail=%.1f%%, profit_bonus=%.1f%%, pnl=%.1f%%)",
                    reason, agent.agent_id[:8], symbol, current_price,
                    position["trailing_stop_price"], atr_trail_pct, profit_bonus, pnl_pct,
                )
                return True, reason

        # --- 3. Pattern exit conditions ---
        try:
            from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

            patterns_flat = self._flatten_patterns(agent)
            for pdata in patterns_flat:
                exit_conds = pdata.get("exit_conditions", {})
                if not exit_conds:
                    continue
                # Skip if exit_conditions is just SL/TP params, not indicator conditions
                param_keys = {"stop_loss_pct", "take_profit_pct", "max_hold_periods",
                              "stop_loss", "take_profit", "timeout_bars"}
                if isinstance(exit_conds, dict) and any(k in exit_conds for k in param_keys):
                    continue
                result = evaluate_conditions(exit_conds, candle_data, match_threshold=0.6)
                if result.matched:
                    logger.info(
                        "PATTERN EXIT for %s %s: confidence %.2f",
                        agent.agent_id[:8], symbol, result.confidence,
                    )
                    return True, "pattern_exit"
        except Exception as e:
            logger.debug("Pattern exit eval error: %s", e)

        return False, ""

    @staticmethod
    def _flatten_patterns(agent: Agent) -> list[dict]:
        """Flatten assigned_patterns from any format into a list of dicts."""
        ap = agent.assigned_patterns
        if not ap:
            return []
        if isinstance(ap, list):
            return [p for p in ap if isinstance(p, dict)]
        if isinstance(ap, dict):
            flat = []
            for key, value in ap.items():
                if isinstance(value, list):
                    flat.extend(p for p in value if isinstance(p, dict))
                elif isinstance(value, dict):
                    value["_pattern_id"] = key
                    flat.append(value)
            return flat
        return []

    @staticmethod
    def _get_first_pattern_id(agent: Agent) -> str | None:
        """Extract the first pattern_id string from assigned_patterns (any format)."""
        ap = agent.assigned_patterns
        if not ap:
            return None
        if isinstance(ap, list):
            for p in ap:
                if isinstance(p, dict) and "pattern_id" in p:
                    return p["pattern_id"]
        elif isinstance(ap, dict):
            for key, value in ap.items():
                if isinstance(value, list):
                    for p in value:
                        if isinstance(p, dict) and "pattern_id" in p:
                            return p["pattern_id"]
                elif isinstance(value, dict) and "pattern_id" in value:
                    return value["pattern_id"]
                elif isinstance(key, str) and len(key) > 8:
                    return key  # Legacy format: key IS the pattern_id
        return None

    async def _evaluate_patterns(self, agent: Agent, candle_data: dict) -> str:
        """
        Evaluate agent's patterns against current market data.

        Uses PatternMatcher.evaluate_conditions() to check each pattern's
        entry/exit conditions against candle indicator values. Weighted
        majority vote determines the signal.

        Returns: "buy", "sell", "close", or "hold"
        """
        if not agent.assigned_patterns:
            return "hold"

        try:
            from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions
        except ImportError:
            logger.warning("PatternMatcher not available - returning hold")
            return "hold"

        buy_votes = 0.0
        sell_votes = 0.0
        close_votes = 0.0

        # Multi-timeframe confidence: for each base indicator, check ALL timeframe
        # versions. If rsi_14 < 30 matches on 1m AND rsi_14_1h also < 30, that's
        # higher confidence than matching on 1m alone.
        # The base indicator value stays as-is (fastest TF), but we count how many
        # TFs agree and boost confidence accordingly.
        TF_SUFFIXES = ["_1m", "_5m", "_15m", "_1h", "_4h", "_1d"]
        tf_agreement = {}
        for key, val in candle_data.items():
            # Skip TF-suffixed keys and non-indicator keys
            if any(key.endswith(s) for s in TF_SUFFIXES):
                continue
            if key in ("time", "exchange", "symbol", "timeframe", "open", "high", "low", "close", "volume"):
                continue
            if val is None:
                continue
            # Count how many TFs have this indicator with same sign/direction
            agree = 0
            total_tf = 0
            for suffix in TF_SUFFIXES:
                tf_val = candle_data.get(f"{key}{suffix}")
                if tf_val is not None:
                    total_tf += 1
                    # "Agreement" = same sign (both positive or both negative)
                    try:
                        if (float(val) > 0 and float(tf_val) > 0) or (float(val) < 0 and float(tf_val) < 0) or (float(val) == 0 and float(tf_val) == 0):
                            agree += 1
                    except (ValueError, TypeError):
                        pass
            if total_tf > 0:
                tf_agreement[key] = agree / total_tf  # 0.0 = no agreement, 1.0 = all TFs agree

        # Overall multi-TF confidence multiplier
        if tf_agreement:
            avg_agreement = sum(tf_agreement.values()) / len(tf_agreement)
            htf_bias = 0.5 + avg_agreement  # 0.5 (no agreement) to 1.5 (full agreement)
        else:
            htf_bias = 1.0

        # Flatten assigned_patterns: supports all formats
        # Format A (legacy dict): {pattern_id: {entry_conditions, ...}}
        # Format B (nested dict): {"base": [{pattern_id, ...}, ...]}
        # Format C (flat list): [{pattern_id, entry_conditions, ...}, ...]
        patterns_flat = []
        ap = agent.assigned_patterns
        if isinstance(ap, list):
            # Format C: direct list of pattern dicts
            for p in ap:
                if isinstance(p, dict):
                    patterns_flat.append(p)
        elif isinstance(ap, dict):
            for key, value in ap.items():
                if isinstance(value, list):
                    # Format B: "base" or "situational" → list of pattern dicts
                    for p in value:
                        if isinstance(p, dict):
                            patterns_flat.append(p)
                elif isinstance(value, dict):
                    # Format A: pattern_id → pattern data
                    value["_pattern_id"] = key
                    patterns_flat.append(value)

        for pattern_data in patterns_flat:
            pattern_id = pattern_data.get("pattern_id", pattern_data.get("_pattern_id", "unknown"))
            weight = pattern_data.get("weight", (agent.pattern_weights or {}).get(pattern_id, 1.0))

            entry_conditions = pattern_data.get("entry_conditions", {})
            exit_conditions = pattern_data.get("exit_conditions", {})
            direction = pattern_data.get("direction", "long")

            # Weighted confidence sum: each condition contributes 1/N scaled by
            # logarithmic depth past threshold. Total must exceed 0.3 to trigger.
            _PAPER_MATCH_THRESHOLD = 0.6

            if entry_conditions:
                try:
                    entry_result = evaluate_conditions(
                        entry_conditions, candle_data,
                        match_threshold=_PAPER_MATCH_THRESHOLD,
                    )
                    if entry_result.matched:
                        if direction == "long":
                            buy_votes += weight * entry_result.confidence * htf_bias
                        else:
                            sell_votes += weight * entry_result.confidence * (2.0 - htf_bias)
                except Exception as e:
                    logger.debug("Entry eval error for pattern %s: %s", pattern_id, e)

            if exit_conditions:
                try:
                    exit_result = evaluate_conditions(
                        exit_conditions, candle_data,
                        match_threshold=_PAPER_MATCH_THRESHOLD,
                    )
                    if exit_result.matched:
                        close_votes += weight * exit_result.confidence
                except Exception as e:
                    logger.debug("Exit eval error for pattern %s: %s", pattern_id, e)

        if close_votes > 0.5:
            return "close"

        total_entry_votes = buy_votes + sell_votes
        if total_entry_votes == 0:
            return "hold"

        if buy_votes > sell_votes * 1.5 and buy_votes >= 0.5:
            return "buy"
        elif sell_votes > buy_votes * 1.5 and sell_votes >= 0.5:
            return "sell"

        return "hold"

    async def _open_position(
        self,
        session: AsyncSession,
        agent: Agent,
        symbol: str,
        side: str,
        price: float,
        candle_data: dict,
        regime: str,
        bear_regime_result=None,
    ) -> dict:
        """Open a new paper position."""
        position_info = self.active_positions[agent.agent_id]

        # --- Conviction-scaled Kelly sizing ---
        # Base Kelly from agent traits
        kelly_fraction = (agent.traits or {}).get("kelly_fraction", 0.1)

        # Volatility scaling: High vol → smaller, low vol → larger
        vol_scale = 1.0
        atr_pct = candle_data.get("atr_14_pct") or candle_data.get("atr_pct")
        if atr_pct and atr_pct > 0:
            vol_scale = min(1.5, max(0.3, 2.5 / atr_pct))

        # Conviction multiplier from bear protection regime
        # Graduated by TF confirmation count + signal depth
        # Research basis: mtf_divergence_matcher.py (0.5x / 2.5x / 5.0x tiers)
        conviction_mult = 1.0  # NEUTRAL default
        if bear_regime_result is not None:
            from Fast_Swarm.Infrastructure.Services.bear_protection_service import Regime
            if bear_regime_result.regime == Regime.AGGRESSIVE:
                n_confirm = bear_regime_result.entry_confirmation_count
                avg_depth = bear_regime_result.entry_avg_depth

                if n_confirm >= 3:
                    # All timeframes agree — maximum conviction
                    # Base 5x, bonus for depth past threshold
                    conviction_mult = 5.0 + min(3.0, avg_depth * 0.5)  # Up to 8x
                elif n_confirm == 2:
                    conviction_mult = 2.5 + min(1.5, avg_depth * 0.3)  # Up to 4x
                elif n_confirm == 1:
                    conviction_mult = 0.5

                logger.info(
                    "CONVICTION SIZING %s %s: %dTF confirm, depth=%.1f -> %.1fx Kelly",
                    agent.agent_id[:8], symbol, n_confirm, avg_depth, conviction_mult,
                )
            elif bear_regime_result.regime == Regime.DEFENSIVE:
                conviction_mult = 0.0  # Should not reach here (blocked earlier)

        adjusted_kelly = kelly_fraction * vol_scale * conviction_mult
        # Cap at 50% of balance per position (allows up to 5x base 10% Kelly)
        adjusted_kelly = min(0.50, adjusted_kelly)
        position_size_usd = position_info["balance"] * adjusted_kelly
        size = position_size_usd / price

        trade_id = str(uuid.uuid4())

        # Snapshot the full market state at entry for future pattern mining
        from Fast_Swarm.Infrastructure.Services.market_snapshot_service import snapshot_to_jsonb
        entry_snapshot = snapshot_to_jsonb(candle_data)

        # Create trade record
        trade = LiveTradeUnified(
            trade_id=trade_id,
            source="paper",
            agent_id=agent.agent_id,
            agent_name=agent.name,
            pattern_id=self._get_first_pattern_id(agent),
            exchange="paper",
            venue_type="paper",
            symbol=symbol,
            side=side,
            entry_time=datetime.now(timezone.utc),
            entry_price=Decimal(str(price)),
            requested_price=Decimal(str(price)),
            size=Decimal(str(size)),
            size_usd=Decimal(str(position_size_usd)),
            status="open",
            order_type="market",
            regime=regime,
            trading_mode="mvp_direct",
            entry_signals=entry_snapshot,
            created_at=datetime.now(timezone.utc),
        )

        session.add(trade)
        await session.commit()
        await session.refresh(trade)

        # Track position locally (includes trailing-stop state)
        position_info["positions"][symbol] = {
            "trade_id": trade_id,
            "side": side,
            "entry_price": price,
            "size": size,
            "size_usd": position_size_usd,
            "entry_time": datetime.now(timezone.utc),
            # Trailing stop state (ported from backtest engine OpenTrade)
            "peak_price": price,  # Best price in our favor
            "trailing_stop_price": 0.0,  # Ratchets only
        }

        position_info["trades_count"] += 1

        # Persist updated state
        await self._persist_session(session, agent.agent_id)

        logger.info(
            "Agent %s opened %s %s @ %.2f (size: %.4f, $%.2f)",
            agent.agent_id[:8],
            side,
            symbol,
            price,
            size,
            position_size_usd,
        )

        return {
            "action": "open",
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "price": price,
            "size": size,
            "size_usd": position_size_usd,
        }

    async def _close_position(
        self,
        session: AsyncSession,
        agent: Agent,
        symbol: str,
        price: float,
        candle_data: dict,
        regime: str,
    ) -> dict:
        """Close an existing paper position."""
        position_info = self.active_positions[agent.agent_id]
        position = position_info["positions"].get(symbol)

        if not position:
            return {"error": "No position to close", "symbol": symbol}

        # Calculate P&L
        entry_price = position["entry_price"]
        size = position["size"]
        side = position["side"]

        # Costs deducted from PnL (module-level TOTAL_COST_PCT ~0.19%)
        if side == "long":
            pnl_pct = (price - entry_price) / entry_price - TOTAL_COST_PCT
        else:  # short
            pnl_pct = (entry_price - price) / entry_price - TOTAL_COST_PCT

        pnl_usd = position["size_usd"] * pnl_pct
        duration = (datetime.now(timezone.utc) - position["entry_time"]).total_seconds()

        # Update trade record
        result = await session.exec(
            select(LiveTradeUnified).where(
                LiveTradeUnified.trade_id == position["trade_id"]
            )
        )
        trade = result.first()

        if trade:
            # Snapshot full market state at exit
            from Fast_Swarm.Infrastructure.Services.market_snapshot_service import snapshot_to_jsonb
            trade.exit_signals = snapshot_to_jsonb(candle_data)

            trade.exit_time = datetime.now(timezone.utc)
            trade.exit_price = Decimal(str(price))
            trade.pnl_pct = pnl_pct * 100  # Store as percentage
            trade.pnl_usd = Decimal(str(pnl_usd))
            trade.realized_pnl = Decimal(str(pnl_usd))
            trade.duration_seconds = int(duration)
            trade.status = "closed"
            trade.exit_reason = regime  # Actual reason (trailing_stop, defensive, pattern_exit, etc.)
            trade.updated_at = datetime.now(timezone.utc)

            session.add(trade)
            await session.commit()

        # Update local tracking
        position_info["balance"] += pnl_usd
        position_info["total_pnl"] += pnl_usd
        del position_info["positions"][symbol]

        # Persist updated state
        await self._persist_session(session, agent.agent_id)

        logger.info(
            "Agent %s closed %s %s @ %.2f (P&L: %.2f%%, $%.2f)",
            agent.agent_id[:8],
            side,
            symbol,
            price,
            pnl_pct * 100,
            pnl_usd,
        )

        return {
            "action": "close",
            "trade_id": position["trade_id"],
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": price,
            "pnl_pct": pnl_pct * 100,
            "pnl_usd": pnl_usd,
            "duration_seconds": duration,
        }

    async def get_active_agents(self) -> list[dict]:
        """Get all agents currently paper trading."""
        return [
            {
                "agent_id": info["agent_id"],
                "agent_name": info["agent_name"],
                "balance": info["balance"],
                "positions": len(info["positions"]),
                "trades_count": info["trades_count"],
                "total_pnl": info["total_pnl"],
            }
            for info in self.active_positions.values()
        ]

    async def get_agent_positions(self, agent_id: str) -> dict | None:
        """Get current positions for an agent."""
        if agent_id not in self.active_positions:
            return None

        info = self.active_positions[agent_id]
        return {
            "agent_id": agent_id,
            "balance": info["balance"],
            "positions": info["positions"],
            "trades_count": info["trades_count"],
            "total_pnl": info["total_pnl"],
        }

    async def force_close_position(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        current_price: float,
    ) -> dict:
        """
        Force close a position (user override).

        Args:
            session: Database session
            agent_id: Agent ID
            symbol: Symbol to close
            current_price: Current market price

        Returns:
            Close result
        """
        if agent_id not in self.active_positions:
            return {"error": "Agent not actively trading"}

        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return {"error": "Agent not found"}

        return await self._close_position(
            session, agent, symbol, current_price, {}, "manual_override"
        )

    async def pause_trading(self, agent_id: str) -> dict:
        """
        Pause trading for an agent (keeps positions, stops new trades).

        Args:
            agent_id: Agent to pause

        Returns:
            Status dict
        """
        if agent_id not in self.active_positions:
            return {"error": "Agent not actively trading"}

        position_info = self.active_positions[agent_id]

        if position_info.get("paused", False):
            return {"error": "Agent already paused", "agent_id": agent_id}

        position_info["paused"] = True
        position_info["paused_at"] = datetime.now(timezone.utc)

        logger.info("Paused trading for agent %s", agent_id[:8])

        return {
            "status": "paused",
            "agent_id": agent_id,
            "open_positions": len(position_info["positions"]),
            "balance": position_info["balance"],
        }

    async def resume_trading(self, agent_id: str) -> dict:
        """
        Resume trading for a paused agent.

        Args:
            agent_id: Agent to resume

        Returns:
            Status dict
        """
        if agent_id not in self.active_positions:
            return {"error": "Agent not actively trading"}

        position_info = self.active_positions[agent_id]

        if not position_info.get("paused", False):
            return {"error": "Agent not paused", "agent_id": agent_id}

        position_info["paused"] = False
        paused_at = position_info.pop("paused_at", None)
        pause_duration = 0
        if paused_at:
            pause_duration = (datetime.now(timezone.utc) - paused_at).total_seconds()

        logger.info("Resumed trading for agent %s (paused %.0fs)", agent_id[:8], pause_duration)

        return {
            "status": "resumed",
            "agent_id": agent_id,
            "pause_duration_seconds": pause_duration,
        }

    async def close_all_positions(
        self,
        session: AsyncSession,
        agent_id: str,
        current_prices: dict[str, float],
    ) -> dict:
        """
        Close all positions for an agent (emergency exit).

        Args:
            session: Database session
            agent_id: Agent ID
            current_prices: Dict of symbol -> current price

        Returns:
            Summary of closed positions
        """
        if agent_id not in self.active_positions:
            return {"error": "Agent not actively trading"}

        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return {"error": "Agent not found"}

        position_info = self.active_positions[agent_id]
        positions_to_close = list(position_info["positions"].keys())

        if not positions_to_close:
            return {
                "status": "no_positions",
                "agent_id": agent_id,
                "message": "No open positions to close",
            }

        closed = []
        errors = []

        for symbol in positions_to_close:
            price = current_prices.get(symbol)
            if price is None:
                errors.append({"symbol": symbol, "error": "No price provided"})
                continue

            close_result = await self._close_position(
                session, agent, symbol, price, {}, "close_all_override"
            )

            if "error" in close_result:
                errors.append({"symbol": symbol, "error": close_result["error"]})
            else:
                closed.append(close_result)

        total_pnl = sum(c.get("pnl_usd", 0) for c in closed)

        logger.info(
            "Closed all positions for agent %s: %d closed, %d errors, P&L: $%.2f",
            agent_id[:8],
            len(closed),
            len(errors),
            total_pnl,
        )

        return {
            "status": "closed_all",
            "agent_id": agent_id,
            "positions_closed": len(closed),
            "total_pnl_usd": total_pnl,
            "closed": closed,
            "errors": errors if errors else None,
        }

    def get_all_active_agents(self) -> dict[str, dict]:
        """Get all active paper trading agents (sync, for background loop)."""
        return self.active_positions

    def is_paused(self, agent_id: str) -> bool:
        """Check if an agent is paused."""
        if agent_id not in self.active_positions:
            return False
        return self.active_positions[agent_id].get("paused", False)


# Module-level singleton for use in Main.py background loop
paper_trading_service = AgentPaperTradingService()
