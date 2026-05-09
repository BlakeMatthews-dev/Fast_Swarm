"""
Portfolio Agent Service.

Dedicated agent per exchange that manages live positions and executes trades.

Architecture:
    Hivemind Voting -> Trade Commands -> Portfolio Agent -> Exchange API -> Orders

Responsibilities:
- Receive trade commands from hivemind system
- Execute orders via exchange REST API
- Track open positions and P&L
- Enforce risk controls (max position, daily loss limit)
- Report fills and position updates back to hiveminds
- Handle order failures gracefully

Each exchange has its own Portfolio Agent instance.
"""

import asyncio
import logging
import random
import uuid
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from decimal import Decimal
from typing import Any

from Fast_Swarm.Infrastructure.Models.market_data_models import PaperTrade

logger = logging.getLogger(__name__)

# Paper trading constants
DEFAULT_ORDER_EXPIRY_HOURS = 24
ALLOWED_CLOSE_FRACTIONS = [0.25, 0.50, 0.75, 1.00]


# =============================================================================
# Enums and Data Structures
# =============================================================================


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class TradeCommand:
    """
    Command from hivemind to execute a trade.

    This is the interface between decision-making and execution.
    The Portfolio Agent will autonomously manage the position once opened,
    including stop loss, take profit, and trailing stops.
    """

    command_id: str
    trio_id: str
    symbol: str

    # What to do
    side: OrderSide  # buy or sell
    size_pct: float  # % of available capital
    size_usd: float | None = None  # Absolute USD amount (alternative to pct)

    # Order parameters
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None  # For limit orders
    time_in_force: str = "GTC"  # GTC, IOC, FOK

    # Exit management (Portfolio Agent handles these autonomously)
    stop_loss_pct: float | None = None  # e.g. 0.05 = 5% stop loss
    take_profit_pct: float | None = None  # e.g. 0.15 = 15% take profit
    trailing_stop_pct: float | None = None  # e.g. 0.03 = 3% trailing stop
    timeout_minutes: int | None = None  # Auto-close after X minutes

    # Context
    confidence: float = 0.5
    reason: str = ""
    leg_id: str | None = None  # Trade leg this belongs to

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OrderResult:
    """
    Result of order execution.

    Returned to hivemind system after order completes or fails.
    """

    command_id: str
    order_id: str | None
    exchange: str
    symbol: str

    # Execution details
    status: OrderStatus
    side: OrderSide
    filled_size: float
    filled_price: float  # Average fill price
    commission: float
    commission_asset: str

    # Timing
    submitted_at: datetime | None
    filled_at: datetime | None

    # Error info
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class Position:
    """Current position state for a symbol."""

    symbol: str
    exchange: str

    side: PositionSide
    size: float  # Absolute size in base currency
    entry_price: float
    current_price: float

    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float

    # Risk tracking
    max_size_ever: float = 0.0
    max_drawdown_pct: float = 0.0

    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def notional_value(self) -> float:
        """Position value in quote currency."""
        return self.size * self.current_price


@dataclass
class PortfolioState:
    """Complete portfolio state for an exchange."""

    exchange: str

    # Capital
    total_equity: float
    available_balance: float
    margin_used: float

    # Positions
    positions: dict[str, Position] = field(default_factory=dict)

    # Daily P&L tracking
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_volume: float = 0.0

    # Risk metrics
    total_exposure: float = 0.0
    max_daily_loss_hit: bool = False

    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RiskLimits:
    """Risk control parameters for portfolio agent."""

    max_position_pct: float = 0.10  # Max 10% of equity in single position
    max_total_exposure_pct: float = 0.50  # Max 50% total exposure
    max_daily_loss_pct: float = 0.05  # Stop trading if down 5% today
    max_order_size_usd: float = 10000.0  # Max single order size
    min_order_size_usd: float = 10.0  # Min order size
    max_orders_per_minute: int = 10  # Rate limit


# =============================================================================
# Abstract Exchange Client
# =============================================================================


class ExchangeClient(ABC):
    """
    Abstract base class for exchange REST API clients.

    Implement this for each exchange (crypto.com, binance, etc.)
    """

    @abstractmethod
    async def get_account_balance(self) -> dict[str, float]:
        """Get account balances by asset."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict]:
        """Get open positions."""
        pass

    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        size: float,
    ) -> dict:
        """Place market order. Returns order info."""
        pass

    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """Place limit order. Returns order info."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order. Returns success."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        """Get order status."""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> dict:
        """Get current ticker (price, bid, ask)."""
        pass


# =============================================================================
# Paper Trading Client (for testing)
# =============================================================================


class PaperTradingClient(ExchangeClient):
    """
    Simulated exchange client for paper trading.

    Executes trades instantly at current price with simulated slippage.
    """

    def __init__(
        self,
        initial_balance: float = 100000.0,
        slippage_bps: float = 5.0,
        fee_bps: float = 10.0,
    ):
        self.balance = {"USD": initial_balance}
        self.positions: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps

        # Mock prices (should be updated from live feed)
        self._prices: dict[str, float] = {}

        # Trade history and events (NEW)
        self.trade_history: deque = deque(maxlen=10000)  # In-memory buffer
        self.trade_legs: list = []  # Partial close tracking
        self.pending_orders: dict[str, dict] = {}  # Resting limit orders
        self._event_callbacks: list = []
        self._db_flush_queue: asyncio.Queue = asyncio.Queue()
        self._flush_task = None

        # P&L tracking
        self.realized_pnl: float = 0.0

    def set_price(self, symbol: str, price: float):
        """Update mock price (call from data feed)."""
        self._prices[symbol] = price

    async def get_account_balance(self) -> dict[str, float]:
        return self.balance.copy()

    async def get_positions(self) -> list[dict]:
        return list(self.positions.values())

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        size: float,
    ) -> dict:
        price = self._prices.get(symbol, 0)
        if price == 0:
            return {"error": "no_price", "message": "No price for " + symbol}

        # Apply slippage with variance (realistic simulation)
        fill_price = self._apply_slippage(price, side, size)

        # Calculate commission
        notional = size * fill_price
        commission = notional * self.fee_bps / 10000

        # Update balance based on side
        if side == "buy":
            cost = notional + commission
            if self.balance.get("USD", 0) < cost:
                return {"error": "insufficient_funds", "message": "Not enough USD"}
            self.balance["USD"] -= cost
        else:
            # SELL: Validate position exists and has sufficient size
            pos = self.positions.get(symbol)
            if not pos:
                return {"error": "no_position", "message": f"No position in {symbol}"}

            if pos["side"] == "long":
                if pos["size"] < size:
                    return {
                        "error": "insufficient_size",
                        "message": f"Position {pos['size']:.6f} < sell size {size:.6f}",
                    }

                # Calculate realized P&L for the closing portion
                pnl = (fill_price - pos["entry_price"]) * size
                proceeds = notional - commission
                self.balance["USD"] += proceeds
                self.realized_pnl += pnl

                logger.info(
                    "[Paper] SELL %s: size=%.6f, entry=$%.2f, exit=$%.2f, P&L=$%.2f",
                    symbol, size, pos["entry_price"], fill_price, pnl
                )
            else:
                # Covering a short position (not implemented for long-only)
                return {"error": "short_not_supported", "message": "Long-only mode"}

        # Create order record
        order_id = str(uuid.uuid4())[:8]
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": fill_price,
            "status": "filled",
            "commission": commission,
            "filled_at": datetime.now(UTC).isoformat(),
        }

        self.orders[order_id] = order

        # Update position tracking
        self._update_position(symbol, side, size, fill_price)

        # Record trade to history and emit event
        self._record_trade(order)

        return order

    def _apply_slippage(self, price: float, side: str, size: float) -> float:
        """Apply realistic slippage with variance."""
        # Base slippage + random component (Gaussian)
        base_bps = self.slippage_bps
        variance_bps = random.gauss(0, base_bps * 0.5)  # 50% std dev

        # Size-dependent slippage (larger orders = more slippage)
        notional = size * price
        size_factor = 1.0 + (notional / 10000) * 0.1  # +10% per $10k

        total_bps = (base_bps + variance_bps) * size_factor
        total_bps = max(0, total_bps)  # No negative slippage

        if side == "buy":
            return price * (1 + total_bps / 10000)
        else:
            return price * (1 - total_bps / 10000)

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        time_in_force: str = "GTC",
        expiry_hours: float | None = None,
    ) -> dict:
        """
        Place limit order with 24h default expiry.

        If price is immediately favorable, fills as market order.
        Otherwise, order rests on book until filled, cancelled, or expired.
        """
        current_price = self._prices.get(symbol, 0)
        expiry = expiry_hours or DEFAULT_ORDER_EXPIRY_HOURS

        # Check if immediately fillable
        if (side == "buy" and current_price <= price) or (side == "sell" and current_price >= price):
            return await self.place_market_order(symbol, side, size)

        # Rest order on book with expiry
        order_id = str(uuid.uuid4())[:8]
        created = datetime.now(UTC)
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "size": size,
            "limit_price": price,
            "time_in_force": time_in_force,
            "status": "pending",
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(hours=expiry)).isoformat(),
        }

        self.pending_orders[order_id] = order
        self.orders[order_id] = order

        logger.info(
            "[Paper] Limit order placed: %s %s %.6f @ $%.2f (expires in %dh)",
            side.upper(), symbol, size, price, int(expiry)
        )

        return order

    def check_pending_orders(self, symbol: str, price: float):
        """
        Called on each price update to check fills and expiries.

        Should be wired to the price feed callback in hivemind_orchestrator.
        """
        now = datetime.now(UTC)
        orders_to_remove = []

        for order_id, order in list(self.pending_orders.items()):
            # Check expiry
            expires_at = datetime.fromisoformat(order["expires_at"])
            if now >= expires_at:
                order["status"] = "expired"
                self._emit_event("order_expired", order)
                orders_to_remove.append(order_id)
                logger.info("[Paper] Order expired: %s", order_id)
                continue

            if order["symbol"] != symbol or order["status"] != "pending":
                continue

            # Check if price crossed limit
            limit_price = order["limit_price"]
            if (order["side"] == "buy" and price <= limit_price) or \
               (order["side"] == "sell" and price >= limit_price):
                # Fill the order
                asyncio.create_task(self._fill_pending_order(order_id, price))

        # Clean up expired orders
        for order_id in orders_to_remove:
            self.pending_orders.pop(order_id, None)

    async def _fill_pending_order(self, order_id: str, fill_price: float):
        """Fill a pending limit order."""
        order = self.pending_orders.get(order_id)
        if not order or order["status"] != "pending":
            return

        # Mark as filling to prevent double-fill
        order["status"] = "filling"

        result = await self.place_market_order(
            symbol=order["symbol"],
            side=order["side"],
            size=order["size"],
        )

        if "error" not in result:
            order["status"] = "filled"
            order["filled_at"] = datetime.now(UTC).isoformat()
            order["fill_price"] = result.get("price", fill_price)
            self._emit_event("order_filled", order)
            logger.info("[Paper] Limit order filled: %s @ $%.2f", order_id, order["fill_price"])
        else:
            order["status"] = "failed"
            order["error"] = result.get("error")
            self._emit_event("order_failed", order)

        # Remove from pending
        self.pending_orders.pop(order_id, None)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id]["status"] = "cancelled"
            return True
        return False

    async def get_order_status(self, order_id: str, symbol: str) -> dict:
        return self.orders.get(order_id, {"error": "not_found"})

    async def get_ticker(self, symbol: str) -> dict:
        price = self._prices.get(symbol, 0)
        return {
            "symbol": symbol,
            "price": price,
            "bid": price * 0.9999,
            "ask": price * 1.0001,
        }

    # =========================================================================
    # Event Callbacks and Trade History
    # =========================================================================

    def on_trade_event(self, callback):
        """Register callback for trade events (fills, cancels, expiries, etc)."""
        self._event_callbacks.append(callback)

    def _emit_event(self, event_type: str, data: dict):
        """Emit event to all registered callbacks."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for cb in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(event))
                else:
                    cb(event)
            except Exception as e:
                logger.error("Event callback error: %s", e)

    def _record_trade(self, trade: dict):
        """Record trade to history and queue for DB flush."""
        self.trade_history.append(trade)
        self._db_flush_queue.put_nowait(trade)
        self._emit_event("trade_executed", trade)

    async def _flush_to_db(self, session_factory):
        """
        Background task to flush trades to PostgreSQL.

        Call this in a background task to persist trade history.
        """
        while True:
            trades_to_flush = []
            # Batch up to 100 trades
            for _ in range(100):
                try:
                    trade = self._db_flush_queue.get_nowait()
                    trades_to_flush.append(trade)
                except asyncio.QueueEmpty:
                    break

            if trades_to_flush:
                try:
                    async with session_factory() as session:
                        await self._insert_trades(session, trades_to_flush)
                        await session.commit()
                except Exception as e:
                    logger.error("DB flush error: %s", e)
                    # Re-queue failed trades
                    for trade in trades_to_flush:
                        self._db_flush_queue.put_nowait(trade)

            await asyncio.sleep(5)  # Flush every 5 seconds

    async def _insert_trades(self, session, trades: list[dict]):
        """Insert trades to paper_trades table."""
        for trade in trades:
            paper_trade = PaperTrade(
                order_id=trade.get("order_id", ""),
                agent_id=trade.get("agent_id"),
                symbol=trade.get("symbol", ""),
                side=trade.get("side", ""),
                size=Decimal(str(trade.get("size", 0))),
                price=Decimal(str(trade.get("price", 0))),
                commission=Decimal(str(trade.get("commission", 0))),
                filled_at=datetime.fromisoformat(trade["filled_at"])
                if isinstance(trade.get("filled_at"), str)
                else trade.get("filled_at", datetime.now(UTC)),
                entry_price=Decimal(str(trade["entry_price"]))
                if trade.get("entry_price")
                else None,
                realized_pnl=Decimal(str(trade["realized_pnl"]))
                if trade.get("realized_pnl")
                else None,
                is_partial=trade.get("is_partial", False),
                close_fraction=trade.get("close_fraction"),
                parent_order_id=trade.get("parent_order_id"),
            )
            session.add(paper_trade)
        logger.debug("Inserted %d trades to paper_trades table", len(trades))

    # =========================================================================
    # Partial Position Closes
    # =========================================================================

    async def close_position_partial(self, symbol: str, fraction: float) -> dict:
        """
        Close a fraction of position as a separate trade leg.

        Args:
            symbol: The symbol to close
            fraction: One of ALLOWED_CLOSE_FRACTIONS (0.25, 0.50, 0.75, 1.00)

        Returns:
            Order result dict or error dict
        """
        if fraction not in ALLOWED_CLOSE_FRACTIONS:
            return {
                "error": "invalid_fraction",
                "message": f"Fraction must be one of {ALLOWED_CLOSE_FRACTIONS}",
                "allowed": ALLOWED_CLOSE_FRACTIONS,
            }

        pos = self.positions.get(symbol)
        if not pos:
            return {"error": "no_position", "message": f"No position in {symbol}"}

        close_size = pos["size"] * fraction
        entry_price = pos["entry_price"]

        # Execute the sell
        close_result = await self.place_market_order(symbol, "sell", close_size)

        if "error" not in close_result:
            exit_price = close_result.get("price", 0)

            # Create separate trade leg record
            leg = {
                "leg_id": str(uuid.uuid4())[:8],
                "parent_position_id": pos.get("position_id", symbol),
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": close_size,
                "pnl": (exit_price - entry_price) * close_size,
                "fraction": fraction,
                "closed_at": datetime.now(UTC).isoformat(),
            }
            self.trade_legs.append(leg)
            self._emit_event("trade_leg_closed", leg)

            logger.info(
                "[Paper] Partial close %s: %.0f%% (%.6f units), P&L=$%.2f",
                symbol, fraction * 100, close_size, leg["pnl"]
            )

        return close_result

    def get_trade_history(self, limit: int = 100) -> list[dict]:
        """Get recent trade history."""
        return list(self.trade_history)[-limit:]

    def get_trade_legs(self, symbol: str | None = None) -> list[dict]:
        """Get trade legs, optionally filtered by symbol."""
        if symbol:
            return [leg for leg in self.trade_legs if leg["symbol"] == symbol]
        return self.trade_legs.copy()

    def get_portfolio_summary(self) -> dict:
        """Get summary of paper trading portfolio."""
        return {
            "balance_usd": self.balance.get("USD", 0),
            "realized_pnl": self.realized_pnl,
            "positions": len(self.positions),
            "pending_orders": len(self.pending_orders),
            "total_trades": len(self.trade_history),
            "trade_legs": len(self.trade_legs),
        }

    # =========================================================================
    # Position Tracking
    # =========================================================================

    def _update_position(self, symbol: str, side: str, size: float, price: float):
        """Update position tracking after fill."""
        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "side": "long" if side == "buy" else "short",
                "size": size,
                "entry_price": price,
            }
        else:
            pos = self.positions[symbol]
            if side == "buy":
                # Adding to long or closing short
                if pos["side"] == "long":
                    # Average in
                    total_size = pos["size"] + size
                    pos["entry_price"] = (pos["entry_price"] * pos["size"] + price * size) / total_size
                    pos["size"] = total_size
                else:
                    # Closing short
                    pos["size"] -= size
                    if pos["size"] <= 0:
                        del self.positions[symbol]
            else:
                # Adding to short or closing long
                if pos["side"] == "short":
                    total_size = pos["size"] + size
                    pos["entry_price"] = (pos["entry_price"] * pos["size"] + price * size) / total_size
                    pos["size"] = total_size
                else:
                    pos["size"] -= size
                    if pos["size"] <= 0:
                        del self.positions[symbol]


# =============================================================================
# Portfolio Agent
# =============================================================================


class PortfolioAgent:
    """
    Dedicated agent managing portfolio at a single exchange.

    Receives trade commands, executes them, and reports results.
    """

    def __init__(
        self,
        exchange_name: str,
        client: ExchangeClient,
        risk_limits: RiskLimits | None = None,
    ):
        self.exchange = exchange_name
        self.client = client
        self.risk_limits = risk_limits or RiskLimits()

        # State
        self.portfolio = PortfolioState(
            exchange=exchange_name,
            total_equity=0.0,
            available_balance=0.0,
            margin_used=0.0,
        )
        self._pending_commands: asyncio.Queue = asyncio.Queue()
        self._running = False

        # Callbacks
        self._fill_callbacks: list[Callable[[OrderResult], None]] = []
        self._position_callbacks: list[Callable[[Position], None]] = []

        # Rate limiting
        self._orders_this_minute: list[datetime] = []

        # Command history
        self._command_history: dict[str, TradeCommand] = {}
        self._order_history: dict[str, OrderResult] = {}

        # Active exit management tracking
        # Maps position symbol -> TradeCommand with exit params
        self._active_exit_rules: dict[str, TradeCommand] = {}
        # Tracks highest price seen for trailing stops (per symbol)
        self._trailing_high_water: dict[str, float] = {}
        # Tracks lowest price seen for short trailing stops
        self._trailing_low_water: dict[str, float] = {}

    def on_fill(self, callback: Callable[[OrderResult], None]):
        """Register callback for order fills."""
        self._fill_callbacks.append(callback)

    def on_position_update(self, callback: Callable[[Position], None]):
        """Register callback for position updates."""
        self._position_callbacks.append(callback)

    async def start(self):
        """Start the portfolio agent."""
        self._running = True

        # Initial sync
        await self._sync_portfolio()

        # Start command processor
        asyncio.create_task(self._process_commands())

        # Start position monitor
        asyncio.create_task(self._monitor_positions())

        logger.info("PortfolioAgent started for %s", self.exchange)

    async def stop(self):
        """Stop the portfolio agent."""
        self._running = False
        logger.info("PortfolioAgent stopped for %s", self.exchange)

    async def submit_command(self, command: TradeCommand) -> str:
        """
        Submit a trade command for execution.

        Returns command_id for tracking.
        """
        self._command_history[command.command_id] = command
        await self._pending_commands.put(command)
        logger.info(
            "[%s] Command queued: %s %s %.4f",
            self.exchange, command.side.value, command.symbol, command.size_pct
        )
        return command.command_id

    async def _process_commands(self):
        """Process queued trade commands."""
        while self._running:
            try:
                # Wait for command with timeout
                try:
                    command = await asyncio.wait_for(
                        self._pending_commands.get(),
                        timeout=1.0
                    )
                except TimeoutError:
                    continue

                # Execute command
                result = await self._execute_command(command)

                # Store result
                self._order_history[command.command_id] = result

                # Notify callbacks
                for cb in self._fill_callbacks:
                    try:
                        cb(result)
                    except Exception as e:
                        logger.error("Fill callback error: %s", e)

            except Exception as e:
                logger.error("[%s] Command processor error: %s", self.exchange, e)

    async def _execute_command(self, command: TradeCommand) -> OrderResult:
        """Execute a single trade command."""
        # Check risk limits
        risk_check = self._check_risk_limits(command)
        if risk_check:
            return OrderResult(
                command_id=command.command_id,
                order_id=None,
                exchange=self.exchange,
                symbol=command.symbol,
                status=OrderStatus.REJECTED,
                side=command.side,
                filled_size=0,
                filled_price=0,
                commission=0,
                commission_asset="USD",
                submitted_at=None,
                filled_at=None,
                error_code="risk_limit",
                error_message=risk_check,
            )

        # Check rate limit
        if not self._check_rate_limit():
            return OrderResult(
                command_id=command.command_id,
                order_id=None,
                exchange=self.exchange,
                symbol=command.symbol,
                status=OrderStatus.REJECTED,
                side=command.side,
                filled_size=0,
                filled_price=0,
                commission=0,
                commission_asset="USD",
                submitted_at=None,
                filled_at=None,
                error_code="rate_limit",
                error_message="Order rate limit exceeded",
            )

        # Calculate order size
        size = await self._calculate_order_size(command)
        if size <= 0:
            return OrderResult(
                command_id=command.command_id,
                order_id=None,
                exchange=self.exchange,
                symbol=command.symbol,
                status=OrderStatus.REJECTED,
                side=command.side,
                filled_size=0,
                filled_price=0,
                commission=0,
                commission_asset="USD",
                submitted_at=None,
                filled_at=None,
                error_code="invalid_size",
                error_message="Calculated size is zero or negative",
            )

        # Place order
        submitted_at = datetime.now(UTC)
        self._orders_this_minute.append(submitted_at)

        try:
            if command.order_type == OrderType.MARKET:
                order_response = await self.client.place_market_order(
                    symbol=command.symbol,
                    side=command.side.value,
                    size=size,
                )
            else:
                if not command.limit_price:
                    return OrderResult(
                        command_id=command.command_id,
                        order_id=None,
                        exchange=self.exchange,
                        symbol=command.symbol,
                        status=OrderStatus.REJECTED,
                        side=command.side,
                        filled_size=0,
                        filled_price=0,
                        commission=0,
                        commission_asset="USD",
                        submitted_at=submitted_at,
                        filled_at=None,
                        error_code="no_limit_price",
                        error_message="Limit order requires price",
                    )

                order_response = await self.client.place_limit_order(
                    symbol=command.symbol,
                    side=command.side.value,
                    size=size,
                    price=command.limit_price,
                    time_in_force=command.time_in_force,
                )

            # Check for error
            if "error" in order_response:
                return OrderResult(
                    command_id=command.command_id,
                    order_id=None,
                    exchange=self.exchange,
                    symbol=command.symbol,
                    status=OrderStatus.FAILED,
                    side=command.side,
                    filled_size=0,
                    filled_price=0,
                    commission=0,
                    commission_asset="USD",
                    submitted_at=submitted_at,
                    filled_at=None,
                    error_code=order_response.get("error"),
                    error_message=order_response.get("message"),
                )

            # Success - register exit rules if any are specified
            filled_price = order_response.get("price", 0)
            if self._has_exit_rules(command):
                self._register_exit_rules(command, filled_price)

            return OrderResult(
                command_id=command.command_id,
                order_id=order_response.get("order_id"),
                exchange=self.exchange,
                symbol=command.symbol,
                status=OrderStatus.FILLED,
                side=command.side,
                filled_size=order_response.get("size", size),
                filled_price=filled_price,
                commission=order_response.get("commission", 0),
                commission_asset="USD",
                submitted_at=submitted_at,
                filled_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("[%s] Order execution error: %s", self.exchange, e)
            return OrderResult(
                command_id=command.command_id,
                order_id=None,
                exchange=self.exchange,
                symbol=command.symbol,
                status=OrderStatus.FAILED,
                side=command.side,
                filled_size=0,
                filled_price=0,
                commission=0,
                commission_asset="USD",
                submitted_at=submitted_at,
                filled_at=None,
                error_code="exception",
                error_message=str(e),
            )

    def _check_risk_limits(self, command: TradeCommand) -> str | None:
        """
        Check if command violates risk limits.

        Returns error message if violated, None if OK.
        """
        # Check daily loss limit
        if self.portfolio.max_daily_loss_hit:
            return "Daily loss limit reached - trading halted"

        # Check position limit would be exceeded
        # (simplified - would need more complex logic for real impl)

        return None

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now(UTC)

        # Clean old entries
        cutoff = now.timestamp() - 60
        self._orders_this_minute = [
            t for t in self._orders_this_minute
            if t.timestamp() > cutoff
        ]

        return len(self._orders_this_minute) < self.risk_limits.max_orders_per_minute

    async def _calculate_order_size(self, command: TradeCommand) -> float:
        """Calculate actual order size from command parameters."""
        if command.size_usd:
            # Absolute size specified
            ticker = await self.client.get_ticker(command.symbol)
            price = ticker.get("price", 0)
            if price > 0:
                return command.size_usd / price
            return 0

        # Percentage of equity
        size_usd = self.portfolio.total_equity * command.size_pct
        size_usd = min(size_usd, self.risk_limits.max_order_size_usd)
        size_usd = max(size_usd, self.risk_limits.min_order_size_usd)

        ticker = await self.client.get_ticker(command.symbol)
        price = ticker.get("price", 0)
        if price > 0:
            return size_usd / price

        return 0

    async def _sync_portfolio(self):
        """Sync portfolio state from exchange."""
        try:
            # Get balances
            balances = await self.client.get_account_balance()
            self.portfolio.total_equity = balances.get("USD", 0)
            self.portfolio.available_balance = balances.get("USD", 0)

            # Get positions
            positions = await self.client.get_positions()
            for pos_data in positions:
                symbol = pos_data.get("symbol")
                if symbol:
                    self.portfolio.positions[symbol] = Position(
                        symbol=symbol,
                        exchange=self.exchange,
                        side=PositionSide(pos_data.get("side", "flat")),
                        size=pos_data.get("size", 0),
                        entry_price=pos_data.get("entry_price", 0),
                        current_price=pos_data.get("entry_price", 0),
                        unrealized_pnl=0,
                        unrealized_pnl_pct=0,
                        realized_pnl=0,
                    )

            self.portfolio.updated_at = datetime.now(UTC)

        except Exception as e:
            logger.error("[%s] Portfolio sync error: %s", self.exchange, e)

    async def _monitor_positions(self):
        """
        Periodically update position P&L and check autonomous exit conditions.

        This is the core loop that makes the Portfolio Agent truly autonomous -
        it monitors positions and executes exits even without receiving new signals.
        """
        while self._running:
            try:
                await asyncio.sleep(5)  # Update every 5 seconds

                # Copy keys to avoid modification during iteration
                symbols = list(self.portfolio.positions.keys())

                for symbol in symbols:
                    position = self.portfolio.positions.get(symbol)
                    if not position:
                        continue

                    ticker = await self.client.get_ticker(symbol)
                    price = ticker.get("price", 0)
                    if price > 0:
                        position.current_price = price

                        if position.side == PositionSide.LONG:
                            position.unrealized_pnl = (price - position.entry_price) * position.size
                            position.unrealized_pnl_pct = (price - position.entry_price) / position.entry_price * 100 if position.entry_price > 0 else 0
                        elif position.side == PositionSide.SHORT:
                            position.unrealized_pnl = (position.entry_price - price) * position.size
                            position.unrealized_pnl_pct = (position.entry_price - price) / position.entry_price * 100 if position.entry_price > 0 else 0

                        # Track max drawdown
                        if position.unrealized_pnl_pct < 0:
                            position.max_drawdown_pct = min(
                                position.max_drawdown_pct,
                                position.unrealized_pnl_pct
                            )

                        position.updated_at = datetime.now(UTC)

                        # === AUTONOMOUS EXIT CHECK ===
                        # This is what makes the agent manage positions independently
                        exit_reason = await self._check_exit_conditions(position)
                        if exit_reason:
                            await self._execute_exit(position, exit_reason)
                            continue  # Position closed, skip callback

                        # Notify callbacks
                        for cb in self._position_callbacks:
                            try:
                                cb(position)
                            except Exception as e:
                                logger.error("Position callback error: %s", e)

            except Exception as e:
                logger.error("[%s] Position monitor error: %s", self.exchange, e)

    def get_status(self) -> dict[str, Any]:
        """Get agent status."""
        return {
            "exchange": self.exchange,
            "running": self._running,
            "equity": self.portfolio.total_equity,
            "positions": len(self.portfolio.positions),
            "pending_commands": self._pending_commands.qsize(),
            "orders_this_minute": len(self._orders_this_minute),
            "daily_pnl": self.portfolio.daily_pnl,
            "daily_trades": self.portfolio.daily_trades,
            "active_exit_rules": len(self._active_exit_rules),
        }

    # =========================================================================
    # Autonomous Exit Management
    # =========================================================================

    def _has_exit_rules(self, command: TradeCommand) -> bool:
        """Check if command has any exit rules defined."""
        return any([
            command.stop_loss_pct is not None,
            command.take_profit_pct is not None,
            command.trailing_stop_pct is not None,
            command.timeout_minutes is not None,
        ])

    def _register_exit_rules(self, command: TradeCommand, entry_price: float):
        """
        Register exit rules for a filled position.

        Called after successful order execution to track autonomous exits.
        """
        symbol = command.symbol
        self._active_exit_rules[symbol] = command

        # Initialize trailing stop tracking
        if command.trailing_stop_pct is not None:
            if command.side == OrderSide.BUY:
                # For long positions, track high water mark
                self._trailing_high_water[symbol] = entry_price
            else:
                # For short positions, track low water mark
                self._trailing_low_water[symbol] = entry_price

        logger.info(
            "[%s] Exit rules registered for %s: SL=%.2f%%, TP=%.2f%%, Trail=%.2f%%, Timeout=%s min",
            self.exchange,
            symbol,
            (command.stop_loss_pct or 0) * 100,
            (command.take_profit_pct or 0) * 100,
            (command.trailing_stop_pct or 0) * 100,
            command.timeout_minutes,
        )

    def _clear_exit_rules(self, symbol: str):
        """Clear exit rules when position is closed."""
        self._active_exit_rules.pop(symbol, None)
        self._trailing_high_water.pop(symbol, None)
        self._trailing_low_water.pop(symbol, None)

    async def _check_exit_conditions(self, position: Position) -> str | None:
        """
        Check if any exit condition is triggered for a position.

        Returns exit reason if triggered, None otherwise.
        """
        symbol = position.symbol
        command = self._active_exit_rules.get(symbol)

        if not command:
            return None

        current_price = position.current_price
        entry_price = position.entry_price

        if entry_price <= 0 or current_price <= 0:
            return None

        # Calculate P&L percentage based on position side
        if position.side == PositionSide.LONG:
            pnl_pct = (current_price - entry_price) / entry_price
        elif position.side == PositionSide.SHORT:
            pnl_pct = (entry_price - current_price) / entry_price
        else:
            return None

        # Check stop loss
        if command.stop_loss_pct is not None:
            if pnl_pct <= -command.stop_loss_pct:
                return f"stop_loss_triggered (loss: {pnl_pct*100:.2f}%)"

        # Check take profit
        if command.take_profit_pct is not None:
            if pnl_pct >= command.take_profit_pct:
                return f"take_profit_triggered (profit: {pnl_pct*100:.2f}%)"

        # Check trailing stop
        if command.trailing_stop_pct is not None:
            if position.side == PositionSide.LONG:
                # Update high water mark
                high_water = self._trailing_high_water.get(symbol, entry_price)
                if current_price > high_water:
                    self._trailing_high_water[symbol] = current_price
                    high_water = current_price

                # Check if dropped from high water by trailing %
                if high_water > 0:
                    drop_from_high = (high_water - current_price) / high_water
                    if drop_from_high >= command.trailing_stop_pct:
                        return f"trailing_stop_triggered (drop: {drop_from_high*100:.2f}% from ${high_water:.2f})"

            elif position.side == PositionSide.SHORT:
                # Update low water mark
                low_water = self._trailing_low_water.get(symbol, entry_price)
                if current_price < low_water:
                    self._trailing_low_water[symbol] = current_price
                    low_water = current_price

                # Check if rose from low water by trailing %
                if low_water > 0:
                    rise_from_low = (current_price - low_water) / low_water
                    if rise_from_low >= command.trailing_stop_pct:
                        return f"trailing_stop_triggered (rise: {rise_from_low*100:.2f}% from ${low_water:.2f})"

        # Check timeout
        if command.timeout_minutes is not None:
            age_minutes = (datetime.now(UTC) - command.created_at).total_seconds() / 60
            if age_minutes >= command.timeout_minutes:
                return f"timeout_triggered (age: {age_minutes:.1f} min)"

        return None

    async def _execute_exit(self, position: Position, reason: str):
        """
        Execute an automatic exit for a position.

        Creates and submits a closing order.
        """
        symbol = position.symbol
        original_command = self._active_exit_rules.get(symbol)

        # Determine close side (opposite of position)
        if position.side == PositionSide.LONG:
            close_side = OrderSide.SELL
        elif position.side == PositionSide.SHORT:
            close_side = OrderSide.BUY
        else:
            logger.warning("[%s] Cannot close flat position %s", self.exchange, symbol)
            return

        logger.info(
            "[%s] Auto-exit triggered for %s: %s",
            self.exchange, symbol, reason
        )

        # Create close command
        close_command = TradeCommand(
            command_id=str(uuid.uuid4()),
            trio_id=original_command.trio_id if original_command else "auto_exit",
            symbol=symbol,
            side=close_side,
            size_pct=0,  # Not used - we specify USD
            size_usd=position.size * position.current_price,  # Close full position
            order_type=OrderType.MARKET,
            confidence=1.0,
            reason=f"auto_exit: {reason}",
            leg_id=original_command.leg_id if original_command else None,
        )

        # Clear exit rules BEFORE executing to prevent re-triggering
        self._clear_exit_rules(symbol)

        # Execute the close
        result = await self._execute_command(close_command)

        if result.status == OrderStatus.FILLED:
            logger.info(
                "[%s] Auto-exit completed for %s at $%.2f",
                self.exchange, symbol, result.filled_price
            )
        else:
            logger.error(
                "[%s] Auto-exit failed for %s: %s",
                self.exchange, symbol, result.error_message
            )
            # Re-register exit rules if close failed
            if original_command:
                self._active_exit_rules[symbol] = original_command
