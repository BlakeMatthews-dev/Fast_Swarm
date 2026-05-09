"""
Agent Live Trading Service - Direct agent -> Crypto.com execution bridge.

Mirrors the AgentPaperTradingService pattern but places real orders on
the Crypto.com exchange. Uses limit orders with buffer for entries and
market orders for emergency exits (bear protection).

Flow:
1. Agent evaluates market conditions using its patterns (same as paper)
2. Agent generates a signal (buy/sell/hold)
3. Service places limit order on Crypto.com (with 0.1% buffer)
4. Order fill is confirmed via status polling
5. Trade is recorded to LiveTradeUnified (source="live")

Key differences from paper trading:
- Real exchange API calls (not simulated fills)
- Order confirmation required before recording position
- Market orders for urgent exits (bear protection DEFENSIVE)
- Exchange position sync for reconciliation
- Rate limit and error handling for exchange API

This is the MVP live path: Pattern -> Agent -> Exchange Order -> Fill -> Record
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ...Agents.Models.agent_models import Agent
from ...Infrastructure.Models.exchange_models import LiveTradeUnified
from ...exchanges.cryptocom_rest import CryptoComRESTClient, create_cryptocom_client

logger = logging.getLogger(__name__)


class AgentLiveTradingService:
    """
    Direct agent -> Crypto.com execution bridge for MVP live trading.

    Mirrors AgentPaperTradingService structure but executes real orders.
    Uses limit orders with a buffer for entries and market orders for
    bear protection emergency exits.
    """

    LIMIT_BUFFER_PCT = 0.001  # 0.1% buffer from signal price
    ORDER_POLL_INTERVAL = 5  # seconds between order status checks
    ORDER_TIMEOUT = 300  # 5 minutes before cancelling unfilled limit orders

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        use_sandbox: bool = False,
    ):
        self.api_key = api_key or os.getenv("CRYPTOCOM_API_KEY", "")
        self.api_secret = api_secret or os.getenv("CRYPTOCOM_API_SECRET", "")
        self.use_sandbox = use_sandbox

        self.active_agents: dict[str, dict] = {}  # agent_id -> session info
        self._client: CryptoComRESTClient | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize(self) -> bool:
        """
        Initialize the Crypto.com REST client.

        Must be called before any trading operations. Checks for valid
        API credentials and creates the HTTP client connection.

        Returns:
            True if initialized successfully, False if credentials missing
        """
        if not self.api_key or not self.api_secret:
            logger.warning(
                "Crypto.com API credentials not configured. "
                "Set CRYPTOCOM_API_KEY and CRYPTOCOM_API_SECRET env vars."
            )
            return False

        try:
            self._client = create_cryptocom_client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                use_sandbox=self.use_sandbox,
            )
            self._initialized = True
            env = "SANDBOX" if self.use_sandbox else "PRODUCTION"
            logger.info("Live trading service initialized (%s)", env)
            return True
        except Exception as e:
            logger.error("Failed to initialize exchange client: %s", e)
            return False

    async def close(self):
        """Close the exchange client and clean up."""
        if self._client:
            await self._client.close()
            self._client = None
            self._initialized = False

    def is_ready(self) -> bool:
        """Check if service has valid exchange connection."""
        return self._initialized and self._client is not None

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    async def start_live_trading(
        self,
        session: AsyncSession,
        agent_id: str,
        symbols: list[str] | None = None,
        risk_limits: dict | None = None,
    ) -> dict:
        """
        Start live trading for an agent.

        Validates the agent exists, checks exchange connection, and begins
        tracking the agent for live market evaluation.

        Args:
            session: Database session
            agent_id: Agent to start trading
            symbols: Symbols to trade (default: BTC-USDT)
            risk_limits: Optional risk config (max_position_pct, max_daily_trades)

        Returns:
            Status dict with agent info and exchange state
        """
        if not self.is_ready():
            return {"error": "Exchange not initialized. Call initialize() first."}

        # Validate agent
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()

        if not agent:
            return {"error": "Agent not found", "agent_id": agent_id}

        if agent.status != "active":
            return {"error": "Agent not active", "status": agent.status}

        symbols = symbols or ["BTC-USDT"]
        risk = risk_limits or {}

        # Initialize agent session
        self.active_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "symbols": symbols,
            "positions": {},  # symbol -> position info
            "open_orders": {},  # order_id -> order info
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": risk.get("max_position_pct", 0.25),
            "max_daily_trades": risk.get("max_daily_trades", 10),
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }

        logger.info(
            "Started LIVE trading for agent %s (%s) on %s [%s]",
            agent_id[:8],
            agent.name,
            symbols,
            "SANDBOX" if self.use_sandbox else "PRODUCTION",
        )

        return {
            "status": "started",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "symbols": symbols,
            "exchange": "crypto.com",
            "environment": "sandbox" if self.use_sandbox else "production",
        }

    async def stop_live_trading(self, agent_id: str) -> dict:
        """
        Stop live trading for an agent.

        Cancels any open orders but does NOT close positions.
        User must explicitly close positions before stopping.

        Args:
            agent_id: Agent to stop

        Returns:
            Session summary with trade statistics
        """
        if agent_id not in self.active_agents:
            return {"error": "Agent not actively live trading", "agent_id": agent_id}

        agent_info = self.active_agents.pop(agent_id)
        duration = datetime.now(timezone.utc) - agent_info["started_at"]

        # Cancel any open orders for this agent
        cancelled = await self._cancel_open_orders(agent_id, agent_info)

        open_positions = len(agent_info["positions"])
        if open_positions > 0:
            logger.warning(
                "Agent %s stopped with %d open positions! Close them manually.",
                agent_id[:8],
                open_positions,
            )

        return {
            "status": "stopped",
            "agent_id": agent_id,
            "duration_seconds": duration.total_seconds(),
            "trades_count": agent_info["trades_count"],
            "total_pnl": agent_info["total_pnl"],
            "open_positions": open_positions,
            "orders_cancelled": cancelled,
            "warning": (
                f"{open_positions} positions still open on exchange!"
                if open_positions > 0
                else None
            ),
        }

    # =========================================================================
    # EVALUATION AND EXECUTION
    # =========================================================================

    async def evaluate_and_execute(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        current_price: float,
        candle_data: dict,
        regime: str = "unknown",
    ) -> dict | None:
        """
        Evaluate market conditions and potentially execute a live trade.

        Same evaluation logic as paper trading, but executes real orders.

        Args:
            session: Database session
            agent_id: Agent making the decision
            symbol: Trading symbol
            current_price: Current market price
            candle_data: OHLCV + indicators
            regime: Current market regime

        Returns:
            Execution result if action was taken, None otherwise
        """
        if agent_id not in self.active_agents:
            return None

        agent_info = self.active_agents[agent_id]

        # Check if paused
        if agent_info.get("paused", False):
            return None

        # Reset daily trade counter if new day
        today = datetime.now(timezone.utc).date()
        if agent_info["daily_reset"] != today:
            agent_info["daily_trades"] = 0
            agent_info["daily_reset"] = today

        # Check daily trade limit
        if agent_info["daily_trades"] >= agent_info["max_daily_trades"]:
            return None

        # Get agent
        result = await session.exec(select(Agent).where(Agent.agent_id == agent_id))
        agent = result.first()
        if not agent or not agent.assigned_patterns:
            return None

        # =====================================================================
        # Bear Protection: Force close on DEFENSIVE trigger
        # =====================================================================
        defensive_trigger = candle_data.get("defensive_trigger")
        if defensive_trigger == 1:
            current_position = agent_info["positions"].get(symbol)
            if current_position is not None:
                logger.warning(
                    "BEAR PROTECTION: DEFENSIVE - force closing LIVE %s position via MARKET order",
                    symbol,
                )
                return await self._emergency_close(
                    session, agent_id, symbol, current_price, "defensive_regime"
                )
            # Block new entries during DEFENSIVE
            return None

        # =====================================================================
        # Evaluate patterns (same logic as paper trading)
        # =====================================================================
        signal = await self._evaluate_patterns(agent, candle_data)

        if signal == "hold":
            return None

        current_position = agent_info["positions"].get(symbol)

        # Entry signals
        if current_position is None and signal in ("buy", "long"):
            return await self._place_entry_order(
                session, agent, symbol, "long", current_price, candle_data, regime
            )
        elif current_position is None and signal in ("sell", "short"):
            return await self._place_entry_order(
                session, agent, symbol, "short", current_price, candle_data, regime
            )
        # Exit signal
        elif current_position is not None and signal == "close":
            return await self._place_exit_order(
                session, agent_id, symbol, current_price, "signal"
            )

        return None

    async def _evaluate_patterns(self, agent: Agent, candle_data: dict) -> str:
        """
        Evaluate agent's patterns against current market data.

        Identical logic to AgentPaperTradingService._evaluate_patterns().
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

        for pattern_id, pattern_data in agent.assigned_patterns.items():
            weight = (agent.pattern_weights or {}).get(pattern_id, 1.0)

            entry_conditions = pattern_data.get("entry_conditions", {})
            exit_conditions = pattern_data.get("exit_conditions", {})
            direction = pattern_data.get("direction", "long")

            if entry_conditions:
                try:
                    entry_result = evaluate_conditions(entry_conditions, candle_data)
                    if entry_result.matched:
                        if direction == "long":
                            buy_votes += weight * entry_result.confidence
                        else:
                            sell_votes += weight * entry_result.confidence
                except Exception as e:
                    logger.debug("Entry eval error for pattern %s: %s", pattern_id, e)

            if exit_conditions:
                try:
                    exit_result = evaluate_conditions(exit_conditions, candle_data)
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

    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================

    async def _place_entry_order(
        self,
        session: AsyncSession,
        agent: Agent,
        symbol: str,
        side: str,
        price: float,
        candle_data: dict,
        regime: str,
    ) -> dict:
        """
        Place a limit entry order on the exchange.

        Calculates position size from Kelly fraction, applies buffer to price,
        places order via Crypto.com API, and records to database on fill.

        Args:
            session: Database session
            agent: Agent placing the order
            symbol: Trading symbol
            side: "long" or "short"
            price: Signal price
            candle_data: Market data
            regime: Market regime

        Returns:
            Order result dict
        """
        agent_info = self.active_agents[agent.agent_id]

        # Get account balance for position sizing
        balance = await self._get_available_balance()
        if balance <= 0:
            return {"error": "No available balance", "agent_id": agent.agent_id}

        # Position sizing: Kelly fraction capped by max_position_pct
        kelly_fraction = (agent.traits or {}).get("kelly_fraction", 0.1)
        max_pct = agent_info["max_position_pct"]
        position_pct = min(kelly_fraction, max_pct)
        position_size_usd = balance * position_pct
        size = position_size_usd / price if price > 0 else 0

        if size <= 0:
            return {"error": "Position size too small", "agent_id": agent.agent_id}

        # Calculate limit price with buffer
        if side == "long":
            limit_price = price * (1 + self.LIMIT_BUFFER_PCT)
            exchange_side = "buy"
        else:
            limit_price = price * (1 - self.LIMIT_BUFFER_PCT)
            exchange_side = "sell"

        # Convert symbol to exchange format
        exchange_symbol = self._convert_symbol(symbol)

        # Place limit order on exchange
        logger.info(
            "Agent %s placing LIVE %s %s: signal=%.2f, limit=%.2f, size=%.6f",
            agent.agent_id[:8],
            side,
            symbol,
            price,
            limit_price,
            size,
        )

        order_result = await self._client.place_limit_order(
            symbol=exchange_symbol,
            side=exchange_side,
            size=size,
            price=limit_price,
            time_in_force="GTC",
        )

        if "error" in order_result:
            logger.error(
                "Order placement failed for agent %s: %s",
                agent.agent_id[:8],
                order_result.get("message"),
            )
            return {
                "action": "order_failed",
                "error": order_result.get("message", "Unknown exchange error"),
                "symbol": symbol,
                "side": side,
            }

        order_id = order_result.get("order_id")
        trade_id = str(uuid.uuid4())

        # Track the open order
        agent_info["open_orders"][order_id] = {
            "order_id": order_id,
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "signal_price": price,
            "limit_price": limit_price,
            "size": size,
            "size_usd": position_size_usd,
            "regime": regime,
            "placed_at": datetime.now(timezone.utc),
        }

        # Record trade as "pending" in database
        trade = LiveTradeUnified(
            trade_id=trade_id,
            source="live",
            agent_id=agent.agent_id,
            exchange="crypto.com",
            venue_type="perp",
            symbol=symbol,
            side=side,
            entry_time=datetime.now(timezone.utc),
            requested_price=Decimal(str(price)),
            size=Decimal(str(size)),
            size_usd=Decimal(str(position_size_usd)),
            status="pending",
            order_type="limit_buffer",
            order_id=order_id,
            regime=regime,
            trading_mode="mvp_live",
            created_at=datetime.now(timezone.utc),
        )
        session.add(trade)
        await session.commit()

        agent_info["daily_trades"] += 1

        return {
            "action": "order_placed",
            "trade_id": trade_id,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "signal_price": price,
            "limit_price": limit_price,
            "size": size,
            "size_usd": position_size_usd,
            "exchange": "crypto.com",
        }

    async def _place_exit_order(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        price: float,
        reason: str,
    ) -> dict:
        """
        Place a limit exit order to close a position.

        Uses limit order with buffer for normal exits.
        For urgent exits (bear protection), use _emergency_close() instead.
        """
        agent_info = self.active_agents[agent_id]
        position = agent_info["positions"].get(symbol)

        if not position:
            return {"error": "No position to close", "symbol": symbol}

        side = position["side"]
        size = position["size"]

        # Exit side is opposite of position
        if side == "long":
            limit_price = price * (1 - self.LIMIT_BUFFER_PCT)
            exchange_side = "sell"
        else:
            limit_price = price * (1 + self.LIMIT_BUFFER_PCT)
            exchange_side = "buy"

        exchange_symbol = self._convert_symbol(symbol)

        order_result = await self._client.place_limit_order(
            symbol=exchange_symbol,
            side=exchange_side,
            size=size,
            price=limit_price,
            time_in_force="GTC",
        )

        if "error" in order_result:
            # If limit fails, try market order for safety
            logger.warning(
                "Limit exit failed, attempting market order for %s: %s",
                symbol,
                order_result.get("message"),
            )
            return await self._emergency_close(session, agent_id, symbol, price, reason)

        order_id = order_result.get("order_id")

        # Track exit order
        agent_info["open_orders"][order_id] = {
            "order_id": order_id,
            "trade_id": position["trade_id"],
            "symbol": symbol,
            "side": exchange_side,
            "is_exit": True,
            "limit_price": limit_price,
            "size": size,
            "placed_at": datetime.now(timezone.utc),
        }

        logger.info(
            "Agent %s exit order placed for %s: limit=%.2f, reason=%s",
            agent_id[:8],
            symbol,
            limit_price,
            reason,
        )

        return {
            "action": "exit_order_placed",
            "trade_id": position["trade_id"],
            "order_id": order_id,
            "symbol": symbol,
            "exit_price": limit_price,
            "reason": reason,
        }

    async def _emergency_close(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        price: float,
        reason: str,
    ) -> dict:
        """
        Emergency close via market order (for bear protection / urgent exits).

        This bypasses limit orders and executes immediately at market price.
        Used when DEFENSIVE regime is detected or limit exit fails.
        """
        agent_info = self.active_agents[agent_id]
        position = agent_info["positions"].get(symbol)

        if not position:
            return {"error": "No position to close", "symbol": symbol}

        side = position["side"]
        size = position["size"]
        exchange_side = "sell" if side == "long" else "buy"
        exchange_symbol = self._convert_symbol(symbol)

        logger.warning(
            "EMERGENCY CLOSE: Agent %s %s %s via MARKET order (reason: %s)",
            agent_id[:8],
            side,
            symbol,
            reason,
        )

        order_result = await self._client.place_market_order(
            symbol=exchange_symbol,
            side=exchange_side,
            size=size,
        )

        if "error" in order_result:
            logger.error(
                "CRITICAL: Emergency market order FAILED for %s: %s",
                symbol,
                order_result.get("message"),
            )
            return {
                "action": "emergency_close_failed",
                "error": order_result.get("message"),
                "symbol": symbol,
            }

        # Calculate P&L
        fill_price = order_result.get("price", price)
        entry_price = position["entry_price"]
        if entry_price > 0:
            if side == "long":
                pnl_pct = (fill_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - fill_price) / entry_price
        else:
            pnl_pct = 0.0

        pnl_usd = position["size_usd"] * pnl_pct

        # Update trade record in database
        result = await session.exec(
            select(LiveTradeUnified).where(
                LiveTradeUnified.trade_id == position["trade_id"]
            )
        )
        trade = result.first()
        if trade:
            trade.exit_time = datetime.now(timezone.utc)
            trade.exit_price = Decimal(str(fill_price))
            trade.pnl_pct = pnl_pct * 100
            trade.pnl_usd = Decimal(str(pnl_usd))
            trade.realized_pnl = Decimal(str(pnl_usd))
            trade.duration_seconds = int(
                (datetime.now(timezone.utc) - position["entry_time"]).total_seconds()
            )
            trade.status = "closed"
            trade.exit_reason = reason
            trade.updated_at = datetime.now(timezone.utc)
            session.add(trade)
            await session.commit()

        # Update local tracking
        agent_info["total_pnl"] += pnl_usd
        del agent_info["positions"][symbol]

        logger.info(
            "EMERGENCY CLOSED: Agent %s %s %s @ %.2f (P&L: %.2f%%, $%.2f)",
            agent_id[:8],
            side,
            symbol,
            fill_price,
            pnl_pct * 100,
            pnl_usd,
        )

        return {
            "action": "emergency_closed",
            "trade_id": position["trade_id"],
            "order_id": order_result.get("order_id"),
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": fill_price,
            "pnl_pct": pnl_pct * 100,
            "pnl_usd": pnl_usd,
            "reason": reason,
        }

    # =========================================================================
    # ORDER STATUS MANAGEMENT
    # =========================================================================

    async def check_order_fills(self, session: AsyncSession) -> list[dict]:
        """
        Poll exchange for order fill status.

        Called periodically to check if pending limit orders have been filled.
        On fill: records entry price, creates position tracking.
        On timeout: cancels stale orders.

        Args:
            session: Database session for updating records

        Returns:
            List of fill/cancel events
        """
        events = []

        for agent_id, agent_info in list(self.active_agents.items()):
            orders_to_remove = []

            for order_id, order_info in list(agent_info["open_orders"].items()):
                symbol = order_info["symbol"]
                exchange_symbol = self._convert_symbol(symbol)

                # Check order status on exchange
                status = await self._client.get_order_status(order_id, exchange_symbol)
                if not status or "error" in status:
                    continue

                order_status = status.get("status", "unknown")

                if order_status == "filled":
                    fill_price = status.get("avg_price", order_info["limit_price"])
                    event = await self._handle_order_fill(
                        session, agent_id, order_info, fill_price
                    )
                    if event:
                        events.append(event)
                    orders_to_remove.append(order_id)

                elif order_status in ("cancelled", "rejected", "expired"):
                    logger.info(
                        "Order %s %s for agent %s: %s",
                        order_status,
                        symbol,
                        agent_id[:8],
                        order_id,
                    )
                    orders_to_remove.append(order_id)
                    events.append({
                        "action": f"order_{order_status}",
                        "order_id": order_id,
                        "symbol": symbol,
                        "agent_id": agent_id,
                    })

                else:
                    # Check for timeout (5 min unfilled -> cancel)
                    placed_at = order_info.get("placed_at", datetime.now(timezone.utc))
                    elapsed = (datetime.now(timezone.utc) - placed_at).total_seconds()

                    if elapsed > self.ORDER_TIMEOUT:
                        logger.info(
                            "Order timed out (%.0fs), cancelling: %s %s",
                            elapsed,
                            symbol,
                            order_id,
                        )
                        cancelled = await self._client.cancel_order(
                            order_id, exchange_symbol
                        )
                        if cancelled:
                            orders_to_remove.append(order_id)
                            events.append({
                                "action": "order_timeout_cancelled",
                                "order_id": order_id,
                                "symbol": symbol,
                                "agent_id": agent_id,
                                "elapsed_seconds": elapsed,
                            })

            # Clean up processed orders
            for oid in orders_to_remove:
                agent_info["open_orders"].pop(oid, None)

        return events

    async def _handle_order_fill(
        self,
        session: AsyncSession,
        agent_id: str,
        order_info: dict,
        fill_price: float,
    ) -> dict | None:
        """
        Handle a confirmed order fill from the exchange.

        If it's an entry order: create position tracking + update DB.
        If it's an exit order: calculate P&L + close position.
        """
        agent_info = self.active_agents.get(agent_id)
        if not agent_info:
            return None

        symbol = order_info["symbol"]
        trade_id = order_info["trade_id"]
        is_exit = order_info.get("is_exit", False)

        if is_exit:
            # Handle exit fill
            position = agent_info["positions"].get(symbol)
            if not position:
                return None

            entry_price = position["entry_price"]
            side = position["side"]

            if entry_price > 0:
                if side == "long":
                    pnl_pct = (fill_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - fill_price) / entry_price
            else:
                pnl_pct = 0.0

            pnl_usd = position["size_usd"] * pnl_pct

            # Update DB record
            result = await session.exec(
                select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
            )
            trade = result.first()
            if trade:
                trade.exit_time = datetime.now(timezone.utc)
                trade.exit_price = Decimal(str(fill_price))
                trade.pnl_pct = pnl_pct * 100
                trade.pnl_usd = Decimal(str(pnl_usd))
                trade.realized_pnl = Decimal(str(pnl_usd))
                trade.duration_seconds = int(
                    (datetime.now(timezone.utc) - position["entry_time"]).total_seconds()
                )
                trade.status = "closed"
                trade.exit_reason = "signal"
                trade.updated_at = datetime.now(timezone.utc)
                session.add(trade)
                await session.commit()

            agent_info["total_pnl"] += pnl_usd
            del agent_info["positions"][symbol]

            logger.info(
                "LIVE EXIT FILLED: Agent %s %s %s @ %.2f (P&L: %.2f%%)",
                agent_id[:8],
                side,
                symbol,
                fill_price,
                pnl_pct * 100,
            )

            return {
                "action": "exit_filled",
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "exit_price": fill_price,
                "pnl_pct": pnl_pct * 100,
                "pnl_usd": pnl_usd,
            }

        else:
            # Handle entry fill
            slippage_pct = (
                abs(fill_price - order_info["signal_price"])
                / order_info["signal_price"]
                * 100
                if order_info["signal_price"] > 0
                else 0.0
            )

            # Create position tracking
            agent_info["positions"][symbol] = {
                "trade_id": trade_id,
                "side": order_info["side"],
                "entry_price": fill_price,
                "size": order_info["size"],
                "size_usd": order_info["size_usd"],
                "entry_time": datetime.now(timezone.utc),
            }
            agent_info["trades_count"] += 1

            # Update DB record with fill price
            result = await session.exec(
                select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
            )
            trade = result.first()
            if trade:
                trade.entry_price = Decimal(str(fill_price))
                trade.slippage_pct = slippage_pct
                trade.status = "open"
                trade.updated_at = datetime.now(timezone.utc)
                session.add(trade)
                await session.commit()

            logger.info(
                "LIVE ENTRY FILLED: Agent %s %s %s @ %.2f (signal=%.2f, slippage=%.3f%%)",
                agent_id[:8],
                order_info["side"],
                symbol,
                fill_price,
                order_info["signal_price"],
                slippage_pct,
            )

            return {
                "action": "entry_filled",
                "trade_id": trade_id,
                "order_id": order_info["order_id"],
                "symbol": symbol,
                "side": order_info["side"],
                "fill_price": fill_price,
                "signal_price": order_info["signal_price"],
                "slippage_pct": slippage_pct,
            }

    # =========================================================================
    # POSITION MANAGEMENT (USER OVERRIDES)
    # =========================================================================

    async def close_position(
        self,
        session: AsyncSession,
        agent_id: str,
        symbol: str,
        urgency: str = "normal",
    ) -> dict:
        """
        Close a position for an agent.

        Args:
            session: Database session
            agent_id: Agent whose position to close
            symbol: Symbol to close
            urgency: "normal" (limit order) or "urgent" (market order)

        Returns:
            Close result dict
        """
        if agent_id not in self.active_agents:
            return {"error": "Agent not actively trading"}

        agent_info = self.active_agents[agent_id]
        position = agent_info["positions"].get(symbol)

        if not position:
            return {"error": "No position for symbol", "symbol": symbol}

        # Get current price for the close
        exchange_symbol = self._convert_symbol(symbol)
        ticker = await self._client.get_ticker(exchange_symbol)
        current_price = ticker.get("price", 0)

        if current_price <= 0:
            return {"error": "Could not get current price", "symbol": symbol}

        if urgency == "urgent":
            return await self._emergency_close(
                session, agent_id, symbol, current_price, "manual_urgent"
            )
        else:
            return await self._place_exit_order(
                session, agent_id, symbol, current_price, "manual_override"
            )

    async def close_all_positions(
        self,
        session: AsyncSession,
        agent_id: str,
    ) -> dict:
        """
        Close all positions for an agent via market orders.

        Emergency exit mechanism. All positions closed immediately.
        """
        if agent_id not in self.active_agents:
            return {"error": "Agent not actively trading"}

        agent_info = self.active_agents[agent_id]
        positions_to_close = list(agent_info["positions"].keys())

        if not positions_to_close:
            return {"status": "no_positions", "agent_id": agent_id}

        # Cancel all open orders first
        await self._cancel_open_orders(agent_id)

        closed = []
        errors = []

        for symbol in positions_to_close:
            exchange_symbol = self._convert_symbol(symbol)
            ticker = await self._client.get_ticker(exchange_symbol)
            current_price = ticker.get("price", 0)

            if current_price <= 0:
                errors.append({"symbol": symbol, "error": "No price available"})
                continue

            result = await self._emergency_close(
                session, agent_id, symbol, current_price, "close_all_override"
            )

            if "error" in result:
                errors.append({"symbol": symbol, "error": result["error"]})
            else:
                closed.append(result)

        total_pnl = sum(c.get("pnl_usd", 0) for c in closed)

        return {
            "status": "closed_all",
            "agent_id": agent_id,
            "positions_closed": len(closed),
            "total_pnl_usd": total_pnl,
            "closed": closed,
            "errors": errors if errors else None,
        }

    async def pause_trading(self, agent_id: str) -> dict:
        """Pause trading for an agent (keeps positions, stops new trades)."""
        if agent_id not in self.active_agents:
            return {"error": "Agent not actively trading"}

        agent_info = self.active_agents[agent_id]
        if agent_info.get("paused", False):
            return {"error": "Agent already paused"}

        agent_info["paused"] = True
        agent_info["paused_at"] = datetime.now(timezone.utc)

        logger.info("Paused LIVE trading for agent %s", agent_id[:8])
        return {
            "status": "paused",
            "agent_id": agent_id,
            "open_positions": len(agent_info["positions"]),
        }

    async def resume_trading(self, agent_id: str) -> dict:
        """Resume trading for a paused agent."""
        if agent_id not in self.active_agents:
            return {"error": "Agent not actively trading"}

        agent_info = self.active_agents[agent_id]
        if not agent_info.get("paused", False):
            return {"error": "Agent not paused"}

        agent_info["paused"] = False
        paused_at = agent_info.pop("paused_at", None)
        pause_duration = 0
        if paused_at:
            pause_duration = (datetime.now(timezone.utc) - paused_at).total_seconds()

        logger.info("Resumed LIVE trading for agent %s (paused %.0fs)", agent_id[:8], pause_duration)
        return {
            "status": "resumed",
            "agent_id": agent_id,
            "pause_duration_seconds": pause_duration,
        }

    # =========================================================================
    # ACCOUNT AND POSITION QUERIES
    # =========================================================================

    async def get_account_state(self) -> dict:
        """
        Get current exchange account state.

        Returns balances and positions directly from the exchange.
        """
        if not self.is_ready():
            return {"error": "Exchange not initialized"}

        balance = await self._client.get_account_balance()
        positions = await self._client.get_positions()

        return {
            "balances": balance,
            "positions": positions,
            "exchange": "crypto.com",
            "environment": "sandbox" if self.use_sandbox else "production",
        }

    async def get_active_agents(self) -> list[dict]:
        """Get all actively live trading agents."""
        result = []
        for agent_id, info in self.active_agents.items():
            result.append({
                "agent_id": agent_id,
                "agent_name": info["agent_name"],
                "symbols": info["symbols"],
                "positions": len(info["positions"]),
                "open_orders": len(info["open_orders"]),
                "trades_count": info["trades_count"],
                "total_pnl": info["total_pnl"],
                "daily_trades": info["daily_trades"],
                "max_daily_trades": info["max_daily_trades"],
                "status": "paused" if info.get("paused") else "trading",
                "started_at": info["started_at"].isoformat(),
            })
        return result

    async def sync_positions(self, session: AsyncSession) -> dict:
        """
        Reconcile local position tracking with exchange positions.

        Checks exchange for actual positions and compares with local state.
        Reports discrepancies for manual resolution.

        Returns:
            Sync report with any discrepancies found
        """
        if not self.is_ready():
            return {"error": "Exchange not initialized"}

        exchange_positions = await self._client.get_positions()
        discrepancies = []

        # Check each exchange position against local tracking
        for ex_pos in exchange_positions:
            symbol = ex_pos["symbol"]
            local_symbol = self._reverse_convert_symbol(symbol)

            found_locally = False
            for agent_id, info in self.active_agents.items():
                local_pos = info["positions"].get(local_symbol)
                if local_pos:
                    found_locally = True
                    size_diff = abs(ex_pos["size"] - local_pos["size"])
                    if size_diff > 0.0001:
                        discrepancies.append({
                            "type": "size_mismatch",
                            "symbol": local_symbol,
                            "agent_id": agent_id,
                            "local_size": local_pos["size"],
                            "exchange_size": ex_pos["size"],
                        })
                    break

            if not found_locally:
                discrepancies.append({
                    "type": "untracked_position",
                    "symbol": local_symbol,
                    "exchange_side": ex_pos["side"],
                    "exchange_size": ex_pos["size"],
                })

        return {
            "exchange_positions": len(exchange_positions),
            "local_positions": sum(
                len(info["positions"]) for info in self.active_agents.values()
            ),
            "discrepancies": discrepancies,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # UTILITIES
    # =========================================================================

    async def _get_available_balance(self) -> float:
        """Get available USD balance from exchange."""
        if not self._client:
            return 0.0

        balances = await self._client.get_account_balance()
        return balances.get("USD", 0.0)

    async def _cancel_open_orders(
        self, agent_id: str, agent_info: dict | None = None
    ) -> int:
        """Cancel all open orders for an agent on the exchange."""
        if agent_info is None:
            agent_info = self.active_agents.get(agent_id)
        if not agent_info:
            return 0

        cancelled = 0
        for order_id, order_info in list(agent_info["open_orders"].items()):
            exchange_symbol = self._convert_symbol(order_info["symbol"])
            success = await self._client.cancel_order(order_id, exchange_symbol)
            if success:
                cancelled += 1

        agent_info["open_orders"].clear()
        return cancelled

    def _convert_symbol(self, symbol: str) -> str:
        """Convert internal symbol format to Crypto.com format."""
        # BTC-USDT -> BTCUSD-PERP
        base = symbol.replace("-USDT", "").replace("-USD", "").replace("USDT", "")
        return f"{base}USD-PERP"

    def _reverse_convert_symbol(self, exchange_symbol: str) -> str:
        """Convert Crypto.com symbol back to internal format."""
        # BTCUSD-PERP -> BTC-USDT
        base = exchange_symbol.replace("USD-PERP", "").replace("USD", "")
        return f"{base}-USDT"

    def get_all_active_agents(self) -> dict[str, dict]:
        """Return all active agents for background loop iteration."""
        return dict(self.active_agents)


# Singleton instance
_live_trading_service: AgentLiveTradingService | None = None


def get_live_trading_service() -> AgentLiveTradingService:
    """Get or create the singleton AgentLiveTradingService."""
    global _live_trading_service
    if _live_trading_service is None:
        _live_trading_service = AgentLiveTradingService()
    return _live_trading_service
