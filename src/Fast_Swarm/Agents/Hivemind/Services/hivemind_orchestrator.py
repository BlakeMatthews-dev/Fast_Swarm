"""
Hivemind Orchestrator Service.

Wires together all hivemind components for live trading:
- Data feeds (WebSocket streams)
- Trio voting (decision making)
- Portfolio agents (order execution)
- ELO tracking (performance scoring)

This is the main entry point for running the hivemind system live.

Data Flow:
    Exchange WebSockets
           ↓
    HivemindDataFeedService (aggregates candles, computes indicators)
           ↓
    TrioVotingService (hiveminds vote, trio aggregates)
           ↓
    PortfolioAgent (executes orders, manages positions)
           ↓
    ELO Transfer Service (scores results, updates ratings)
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.exchanges import (
    BinanceWebSocket,
    CoinbaseWebSocket,
    CryptoComWebSocket,
    DydxWebSocket,
    HyperliquidWebSocket,
)
from Fast_Swarm.exchanges.cryptocom_rest import CryptoComRESTClient

from .elo_transfer_service import process_trade_leg_results
from .hivemind_data_feed_service import HivemindDataFeedService, HivemindDataSnapshot
from .portfolio_agent_service import (
    OrderResult,
    OrderSide,
    PortfolioAgent,
    Position,
    TradeCommand,
)
from .trio_management_service import get_all_active_trios
from .trio_voting_service import (
    TrioDecision,
    execute_trio_voting_round,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class HivemindConfig:
    """Configuration for hivemind system."""

    # Trading symbols (exchange, symbol pairs)
    symbols: list[tuple[str, str]]

    # Timeframe for candle aggregation
    candle_timeframe: str = "1m"

    # Minimum confidence to execute trade
    min_confidence: float = 0.6

    # Default exit parameters
    default_stop_loss_pct: float = 0.05  # 5% stop loss
    default_take_profit_pct: float = 0.15  # 15% take profit
    default_trailing_stop_pct: float | None = None  # Optional trailing stop
    default_timeout_minutes: int | None = 60  # 1 hour timeout

    # Position sizing
    default_position_size_pct: float = 0.02  # 2% of equity per trade

    # Exchanges to use (will connect to all by default)
    use_binance: bool = True
    use_coinbase: bool = True
    use_cryptocom: bool = True
    use_hyperliquid: bool = False  # Perps only
    use_dydx: bool = False  # Perps only


# =============================================================================
# Orchestrator
# =============================================================================


class HivemindOrchestrator:
    """
    Orchestrates the entire hivemind trading system.

    Responsibilities:
    - Initialize and connect all exchange WebSocket clients
    - Wire data feeds to voting service
    - Wire voting decisions to portfolio agents
    - Track trade legs for ELO scoring
    - Manage system lifecycle
    """

    def __init__(
        self,
        config: HivemindConfig,
        session_factory,  # Async session factory for DB access
        cryptocom_client: CryptoComRESTClient | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Hivemind configuration
            session_factory: Callable that returns AsyncSession
            cryptocom_client: Optional pre-configured REST client
        """
        self.config = config
        self.session_factory = session_factory

        # WebSocket clients
        self._ws_clients: dict[str, Any] = {}

        # Data feed service
        self._data_feed = HivemindDataFeedService(
            candle_timeframe=config.candle_timeframe,
        )

        # Portfolio agents (one per exchange)
        self._portfolio_agents: dict[str, PortfolioAgent] = {}
        self._cryptocom_client = cryptocom_client

        # Active trade tracking
        self._active_trades: dict[str, dict] = {}  # command_id -> trade info
        self._pending_legs: dict[str, str] = {}  # command_id -> leg_id

        # State
        self._running = False
        self._started_at: datetime | None = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start the entire hivemind system."""
        logger.info("Starting Hivemind Orchestrator...")
        self._running = True
        self._started_at = datetime.now(UTC)

        # Initialize WebSocket clients
        await self._init_websocket_clients()

        # Initialize portfolio agents
        await self._init_portfolio_agents()

        # Register callbacks
        self._data_feed.on_candle_close(self._on_candle_close)

        # Start data feed
        await self._data_feed.start(self.config.symbols)

        # Connect all WebSockets
        await self._connect_all_websockets()

        logger.info(
            "Hivemind Orchestrator started with %d symbols, %d exchanges",
            len(self.config.symbols),
            len(self._ws_clients),
        )

    async def stop(self):
        """Stop the entire system gracefully."""
        logger.info("Stopping Hivemind Orchestrator...")
        self._running = False

        # Stop data feed
        await self._data_feed.stop()

        # Disconnect WebSockets
        for name, client in self._ws_clients.items():
            try:
                await client.disconnect()
                logger.info("Disconnected %s WebSocket", name)
            except Exception as e:
                logger.error("Error disconnecting %s: %s", name, e)

        # Stop portfolio agents
        for name, agent in self._portfolio_agents.items():
            try:
                await agent.stop()
                logger.info("Stopped %s portfolio agent", name)
            except Exception as e:
                logger.error("Error stopping %s agent: %s", name, e)

        logger.info("Hivemind Orchestrator stopped")

    # =========================================================================
    # Initialization
    # =========================================================================

    async def _init_websocket_clients(self):
        """Initialize WebSocket clients for configured exchanges."""
        # Group symbols by exchange
        exchange_symbols: dict[str, list[str]] = {}
        for exchange, symbol in self.config.symbols:
            exchange_symbols.setdefault(exchange.lower(), []).append(symbol)

        # Create clients
        if self.config.use_binance and "binance" in exchange_symbols:
            self._ws_clients["binance"] = BinanceWebSocket(use_global=True)

        if self.config.use_coinbase and "coinbase" in exchange_symbols:
            self._ws_clients["coinbase"] = CoinbaseWebSocket()

        if self.config.use_cryptocom and "crypto.com" in exchange_symbols:
            self._ws_clients["crypto.com"] = CryptoComWebSocket()

        if self.config.use_hyperliquid and "hyperliquid" in exchange_symbols:
            self._ws_clients["hyperliquid"] = HyperliquidWebSocket()

        if self.config.use_dydx and "dydx" in exchange_symbols:
            self._ws_clients["dydx"] = DydxWebSocket()

        logger.info("Initialized %d WebSocket clients", len(self._ws_clients))

    async def _init_portfolio_agents(self):
        """Initialize portfolio agents for order execution."""
        # For now, only crypto.com has REST client implemented
        if self._cryptocom_client:
            from .portfolio_agent_service import RiskLimits

            agent = PortfolioAgent(
                exchange_name="crypto.com",
                client=self._cryptocom_client,
                risk_limits=RiskLimits(
                    max_position_pct=0.10,
                    max_total_exposure_pct=0.50,
                    max_daily_loss_pct=0.05,
                ),
            )

            # Register callbacks
            agent.on_fill(self._on_order_fill)
            agent.on_position_update(self._on_position_update)

            await agent.start()
            self._portfolio_agents["crypto.com"] = agent

        logger.info("Initialized %d portfolio agents", len(self._portfolio_agents))

    async def _connect_all_websockets(self):
        """Connect all WebSocket clients and subscribe to data."""
        # Group symbols by exchange
        exchange_symbols: dict[str, list[str]] = {}
        for exchange, symbol in self.config.symbols:
            exchange_symbols.setdefault(exchange.lower(), []).append(symbol)

        # Connect and subscribe each client
        tasks = []
        for name, client in self._ws_clients.items():
            symbols = exchange_symbols.get(name, [])
            if symbols:
                # Register data handlers
                client.on_trade(self._data_feed._handle_trade)
                client.on_order_book(self._data_feed._handle_orderbook)
                if hasattr(client, "on_kline"):
                    client.on_kline(self._data_feed._handle_kline)
                if hasattr(client, "on_book_ticker"):
                    client.on_book_ticker(self._data_feed._handle_ticker)
                    # Also register paper trading price update callback
                    client.on_book_ticker(self._create_ticker_callback(name))

                # Create connection task
                tasks.append(self._connect_and_subscribe(client, symbols))

        # Connect all in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _connect_and_subscribe(self, client, symbols: list[str]):
        """Connect a single WebSocket and subscribe to data."""
        try:
            # Start connection in background
            asyncio.create_task(client.connect())

            # Wait for connection
            for _ in range(30):  # 30 second timeout
                if client.is_connected:
                    break
                await asyncio.sleep(1)

            if not client.is_connected:
                logger.error("Failed to connect %s WebSocket", client.EXCHANGE_NAME)
                return

            # Subscribe to data
            await client.subscribe_trades(symbols)
            await client.subscribe_order_book(symbols)

            if hasattr(client, "subscribe_klines"):
                await client.subscribe_klines(symbols, [self.config.candle_timeframe])

            if hasattr(client, "subscribe_book_ticker"):
                await client.subscribe_book_ticker(symbols)

            logger.info("Connected and subscribed %s to %d symbols", client.EXCHANGE_NAME, len(symbols))

        except Exception as e:
            logger.error("Error connecting %s: %s", client.EXCHANGE_NAME, e)

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def _on_candle_close(self, snapshot: HivemindDataSnapshot):
        """
        Handle candle close event - triggers trio voting.

        This is the main decision point where hiveminds analyze data
        and potentially generate trade commands.
        """
        if not self._running:
            return

        # Run voting asynchronously
        asyncio.create_task(self._process_voting_round(snapshot))

    async def _process_voting_round(self, snapshot: HivemindDataSnapshot):
        """
        Process a voting round for all active trios.

        Args:
            snapshot: Current market data snapshot
        """
        try:
            async with self.session_factory() as session:
                # Get all active trios
                trios = await get_all_active_trios(session)

                if not trios:
                    logger.debug("No active trios for voting")
                    return

                # Process each trio
                for trio in trios:
                    await self._process_trio_vote(session, trio, snapshot)

        except Exception as e:
            logger.error("Error in voting round: %s", e)

    async def _process_trio_vote(
        self,
        session: AsyncSession,
        trio,
        snapshot: HivemindDataSnapshot,
    ):
        """
        Process voting for a single trio.

        Args:
            session: Database session
            trio: Trio object
            snapshot: Market data snapshot
        """
        try:
            # =================================================================
            # Bear Protection Check - VETO POWER before voting
            # If defensive_trigger is active, block new positions entirely
            # =================================================================
            defensive_trigger = snapshot.indicators.get("defensive_trigger")
            if defensive_trigger == 1:
                logger.warning(
                    "BEAR PROTECTION: Blocking trio %s vote for %s - defensive_trigger active "
                    "(acc=%.2f, adx_jerk=%.2f)",
                    trio.trio_id[:8],
                    snapshot.symbol,
                    snapshot.indicators.get("close_acceleration_zscore", 0),
                    snapshot.indicators.get("adx_14_jerk_zscore", 0),
                )
                # TODO: Could also force-close existing positions here
                return

            # Execute voting round
            decision, leg = await execute_trio_voting_round(
                session=session,
                trio=trio,
                symbol=snapshot.symbol,
                current_price=snapshot.candle["close"],
                data_snapshot=snapshot,
            )

            if not decision:
                return

            # Check if decision meets minimum confidence
            if decision.avg_confidence < self.config.min_confidence:
                logger.debug(
                    "Trio %s decision confidence %.2f below threshold %.2f",
                    trio.trio_id[:8],
                    decision.avg_confidence,
                    self.config.min_confidence,
                )
                return

            # Skip HOLD decisions
            if decision.direction == "hold":
                return

            # Convert to trade command
            command = self._decision_to_command(decision, leg, snapshot)
            if not command:
                return

            # Find appropriate portfolio agent
            agent = self._portfolio_agents.get(snapshot.exchange)
            if not agent:
                logger.warning("No portfolio agent for exchange %s", snapshot.exchange)
                return

            # Track the trade
            self._active_trades[command.command_id] = {
                "trio_id": trio.trio_id,
                "leg_id": leg.leg_id if leg else None,
                "decision": decision,
                "snapshot": snapshot,
                "submitted_at": datetime.now(UTC),
            }

            if leg:
                self._pending_legs[command.command_id] = leg.leg_id

            # Submit command
            await agent.submit_command(command)
            logger.info(
                "Trio %s submitted %s %s at %.2f (conf: %.2f)",
                trio.trio_id[:8],
                decision.direction,
                snapshot.symbol,
                snapshot.candle["close"],
                decision.avg_confidence,
            )

        except Exception as e:
            logger.error("Error processing trio %s vote: %s", trio.trio_id[:8], e)

    def _decision_to_command(
        self,
        decision: TrioDecision,
        leg,
        snapshot: HivemindDataSnapshot,
    ) -> TradeCommand | None:
        """Convert a trio decision to a trade command."""
        import uuid

        if decision.direction == "hold":
            return None

        side = OrderSide.BUY if decision.direction == "long" else OrderSide.SELL

        return TradeCommand(
            command_id=str(uuid.uuid4()),
            trio_id=decision.trio_id,
            symbol=snapshot.symbol,
            side=side,
            size_pct=self.config.default_position_size_pct * decision.position_size,
            stop_loss_pct=self.config.default_stop_loss_pct,
            take_profit_pct=self.config.default_take_profit_pct,
            trailing_stop_pct=self.config.default_trailing_stop_pct,
            timeout_minutes=self.config.default_timeout_minutes,
            confidence=decision.avg_confidence,
            reason=f"trio_vote:{decision.direction}:{decision.vote_breakdown}",
            leg_id=leg.leg_id if leg else None,
        )

    def _on_order_fill(self, result: OrderResult):
        """Handle order fill - update trade tracking."""
        command_id = result.command_id
        trade_info = self._active_trades.get(command_id)

        if trade_info and result.status.value == "filled":
            logger.info(
                "Order filled: %s %s at $%.2f (size: %.4f)",
                result.side.value,
                result.symbol,
                result.filled_price,
                result.filled_size,
            )

            # Store fill info for ELO scoring
            trade_info["fill_result"] = result
            trade_info["filled_at"] = datetime.now(UTC)

    def _on_position_update(self, position: Position):
        """Handle position P&L update."""
        # Log significant P&L changes
        if abs(position.unrealized_pnl_pct) > 5:  # >5% move
            logger.info(
                "Position %s P&L: %.2f%% ($%.2f)",
                position.symbol,
                position.unrealized_pnl_pct,
                position.unrealized_pnl,
            )

    def _create_ticker_callback(self, exchange_name: str):
        """
        Create a ticker callback for a specific exchange.

        Returns a closure that extracts price from BookTickerData and
        updates paper trading clients.
        """
        def callback(ticker_data):
            # Extract symbol and price from BookTickerData
            symbol = getattr(ticker_data, "symbol", None)
            # Try different price attributes (exchanges use different names)
            price = (
                getattr(ticker_data, "price", None) or
                getattr(ticker_data, "last_price", None) or
                getattr(ticker_data, "bid_price", None) or
                0
            )
            if symbol and price > 0:
                self._on_ticker_update(symbol, price, exchange_name)

        return callback

    def _on_ticker_update(self, symbol: str, price: float, exchange: str = ""):
        """
        Handle ticker/price update - updates paper trading clients.

        This wires live price data to paper trading clients so they can:
        1. Update position mark-to-market pricing
        2. Check and fill pending limit orders
        3. Evaluate stop loss / take profit conditions

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            price: Current price
            exchange: Exchange name (optional)
        """
        if price <= 0:
            return

        # Update paper trading clients with new price
        for agent_name, agent in self._portfolio_agents.items():
            client = agent.client
            # Check if this is a paper trading client with set_price method
            if hasattr(client, "set_price"):
                client.set_price(symbol, price)

            # Check pending limit orders
            if hasattr(client, "check_pending_orders"):
                client.check_pending_orders(symbol, price)

    # =========================================================================
    # ELO Scoring
    # =========================================================================

    async def process_closed_trades(self):
        """
        Process closed trades and update ELO ratings.

        Called periodically to score completed trade legs.
        """
        try:
            async with self.session_factory() as session:
                # Find closed trades that need scoring
                closed_commands = []
                for cmd_id, info in list(self._active_trades.items()):
                    if "closed_at" in info and "scored" not in info:
                        closed_commands.append((cmd_id, info))

                if not closed_commands:
                    return

                # Process each closed trade
                for cmd_id, info in closed_commands:
                    leg_id = self._pending_legs.get(cmd_id)
                    if leg_id:
                        await process_trade_leg_results(
                            session=session,
                            leg_id=leg_id,
                        )
                        info["scored"] = True
                        logger.info("Scored trade leg %s", leg_id[:8])

        except Exception as e:
            logger.error("Error processing closed trades: %s", e)

    # =========================================================================
    # Status & Monitoring
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "uptime_seconds": (datetime.now(UTC) - self._started_at).total_seconds() if self._started_at else 0,
            "websockets": {
                name: {
                    "connected": client.is_connected,
                    "state": client.state.value,
                    "seconds_since_message": client.seconds_since_last_message,
                }
                for name, client in self._ws_clients.items()
            },
            "portfolio_agents": {
                name: agent.get_status()
                for name, agent in self._portfolio_agents.items()
            },
            "data_feed": self._data_feed.get_status(),
            "active_trades": len(self._active_trades),
            "pending_legs": len(self._pending_legs),
        }


# =============================================================================
# Factory Functions
# =============================================================================


async def create_hivemind_orchestrator(
    session_factory,
    symbols: list[tuple[str, str]],
    cryptocom_api_key: str | None = None,
    cryptocom_api_secret: str | None = None,
) -> HivemindOrchestrator:
    """
    Create and configure a hivemind orchestrator.

    Args:
        session_factory: Async session factory for DB
        symbols: List of (exchange, symbol) tuples to trade
        cryptocom_api_key: Optional crypto.com API key
        cryptocom_api_secret: Optional crypto.com API secret

    Returns:
        Configured HivemindOrchestrator instance
    """
    from Fast_Swarm.exchanges.cryptocom_rest import create_cryptocom_client

    # Create REST client if credentials provided
    rest_client = None
    if cryptocom_api_key and cryptocom_api_secret:
        rest_client = create_cryptocom_client(
            api_key=cryptocom_api_key,
            api_secret=cryptocom_api_secret,
        )

    config = HivemindConfig(symbols=symbols)

    return HivemindOrchestrator(
        config=config,
        session_factory=session_factory,
        cryptocom_client=rest_client,
    )
