"""
Integration tests for the Live Execution Service.

Tests with REAL database session but MOCKED exchange client (CryptoComRESTClient).
Verifies:
- Limit order execution and DB recording
- Market order execution and DB recording
- Symbol conversion logic
- Slippage calculation
- Simulated (paper) execution fallback
- Error handling from exchange

Uses `db_session` fixture with transaction rollback for isolation.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Infrastructure.Models.exchange_models import LiveTradeUnified
from Fast_Swarm.Trading.Services.live_execution_service import LiveExecutionService


# ============================================================================
# HELPERS
# ============================================================================


def _make_trade_id() -> str:
    return f"trade-{uuid.uuid4().hex[:12]}"


def _make_agent_id() -> str:
    return f"agent-{uuid.uuid4().hex[:8]}"


def _build_service_with_mock_client() -> tuple[LiveExecutionService, AsyncMock]:
    """
    Build a LiveExecutionService with a mocked exchange client.

    Returns (service, mock_client) so tests can configure return values.
    """
    service = LiveExecutionService(
        api_key="test-key",
        api_secret="test-secret",
        use_sandbox=True,
    )
    mock_client = AsyncMock()
    service._client = mock_client
    service._initialized = True
    return service, mock_client


# ============================================================================
# 1. execute_limit_order — Verify LiveTradeUnified record in DB
# ============================================================================


class TestExecuteLimitOrder:
    """Test limit order execution with real DB."""

    @pytest.mark.critical
    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_limit_order_creates_db_record(self, db_session: AsyncSession):
        """Successful limit order should create a LiveTradeUnified record."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "ord-123",
            "status": "submitted",
            "price": 45100.0,
        }

        trade_id = _make_trade_id()
        agent_id = _make_agent_id()

        result = await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=agent_id,
            symbol="BTC-USDT",
            side="buy",
            size=0.5,
            limit_price=45000.0,
            order_type="limit",
            pattern_id="pat-001",
            pattern_name="RSI Oversold",
            regime="bull",
            reason="signal_entry",
        )

        assert result["success"] is True
        assert result["trade_id"] == trade_id
        assert result["order_id"] == "ord-123"
        assert result["source"] == "live"

        # Verify DB record
        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is not None
        assert trade.agent_id == agent_id
        assert trade.symbol == "BTC-USDT"
        assert trade.side == "buy"
        assert float(trade.size) == pytest.approx(0.5)
        assert trade.order_type == "limit"
        assert trade.order_id == "ord-123"
        assert trade.status == "open"
        assert trade.source == "live"
        assert trade.pattern_id == "pat-001"
        assert trade.pattern_name == "RSI Oversold"
        assert trade.regime == "bull"

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_limit_order_records_size_usd(self, db_session: AsyncSession):
        """size_usd should be calculated as size * fill_price."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "ord-456",
            "status": "submitted",
            "price": 45000.0,
        }

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is not None
        # size_usd = 0.1 * 45000.0 = 4500.0
        assert float(trade.size_usd) == pytest.approx(4500.0)

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_limit_order_calls_exchange_with_converted_symbol(self, db_session: AsyncSession):
        """Exchange should receive BTCUSD-PERP format."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "ord-789",
            "price": 45000.0,
        }

        await service.execute_limit_order(
            session=db_session,
            trade_id=_make_trade_id(),
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        mock_client.place_limit_order.assert_called_once_with(
            symbol="BTCUSD-PERP",
            side="buy",
            size=0.1,
            price=45000.0,
            time_in_force="GTC",
        )

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_limit_order_normalizes_long_to_buy(self, db_session: AsyncSession):
        """Side 'long' should be normalized to 'buy' for exchange."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "ord-norm",
            "price": 3000.0,
        }

        await service.execute_limit_order(
            session=db_session,
            trade_id=_make_trade_id(),
            agent_id=_make_agent_id(),
            symbol="ETH-USDT",
            side="long",
            size=1.0,
            limit_price=3000.0,
        )

        call_args = mock_client.place_limit_order.call_args
        assert call_args.kwargs["side"] == "buy"

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_limit_order_normalizes_short_to_sell(self, db_session: AsyncSession):
        """Side 'short' should be normalized to 'sell' for exchange."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "ord-short",
            "price": 3000.0,
        }

        await service.execute_limit_order(
            session=db_session,
            trade_id=_make_trade_id(),
            agent_id=_make_agent_id(),
            symbol="ETH-USDT",
            side="short",
            size=1.0,
            limit_price=3000.0,
        )

        call_args = mock_client.place_limit_order.call_args
        assert call_args.kwargs["side"] == "sell"


# ============================================================================
# 2. execute_market_order — Verify trade recorded with "filled" status
# ============================================================================


class TestExecuteMarketOrder:
    """Test market order execution with real DB."""

    @pytest.mark.critical
    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_market_order_creates_filled_record(self, db_session: AsyncSession):
        """Market order should record trade with 'filled' status."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_market_order.return_value = {
            "order_id": "mkt-001",
            "price": 44950.0,
            "status": "filled",
        }

        result = await service.execute_market_order(
            session=db_session,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="sell",
            size=0.2,
            reason="emergency_exit",
        )

        assert result["success"] is True
        assert result["status"] == "filled"
        assert result["fill_price"] == 44950.0

        # Verify DB record
        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == result["trade_id"])
        )
        trade = db_result.first()
        assert trade is not None
        assert trade.status == "filled"
        assert trade.order_type == "market"
        assert trade.source == "live"
        assert trade.exit_reason == "emergency_exit"

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_market_order_not_ready_returns_error(self, db_session: AsyncSession):
        """Market order when service not initialized should fail."""
        service = LiveExecutionService()  # Not initialized

        result = await service.execute_market_order(
            session=db_session,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="sell",
            size=0.1,
        )

        assert result["success"] is False
        assert "not connected" in result["error"].lower()

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_market_order_generates_trade_id(self, db_session: AsyncSession):
        """Market orders auto-generate trade IDs."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_market_order.return_value = {
            "order_id": "mkt-auto",
            "price": 3100.0,
        }

        result = await service.execute_market_order(
            session=db_session,
            agent_id=_make_agent_id(),
            symbol="ETH-USDT",
            side="buy",
            size=1.0,
        )

        assert result["success"] is True
        assert result["trade_id"].startswith("trade-")


# ============================================================================
# 3. _convert_symbol — BTC-USDT → BTCUSD-PERP
# ============================================================================


class TestConvertSymbol:
    """Test symbol format conversion for Crypto.com exchange."""

    def test_btc_usdt_to_perp(self):
        service = LiveExecutionService()
        assert service._convert_symbol("BTC-USDT") == "BTCUSD-PERP"

    def test_eth_usdt_to_perp(self):
        service = LiveExecutionService()
        assert service._convert_symbol("ETH-USDT") == "ETHUSD-PERP"

    def test_btc_usd_to_perp(self):
        service = LiveExecutionService()
        assert service._convert_symbol("BTC-USD") == "BTCUSD-PERP"

    def test_sol_usdt_to_perp(self):
        service = LiveExecutionService()
        assert service._convert_symbol("SOL-USDT") == "SOLUSD-PERP"

    def test_already_no_suffix(self):
        """Symbol with no known suffix should still get USD-PERP appended."""
        service = LiveExecutionService()
        result = service._convert_symbol("DOGE")
        assert result == "DOGEUSD-PERP"


# ============================================================================
# 4. Slippage calculation (fill_price vs requested_price)
# ============================================================================


class TestSlippageCalculation:
    """Test slippage is correctly calculated and stored."""

    @pytest.mark.critical
    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_positive_slippage_recorded(self, db_session: AsyncSession):
        """Fill above requested price = positive slippage (bad for buys)."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "slip-001",
            "price": 45100.0,  # Filled above requested
        }

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is not None
        # slippage = (45100 - 45000) / 45000 * 100 = 0.222%
        assert trade.slippage_pct is not None
        assert trade.slippage_pct == pytest.approx(0.2222, abs=0.01)

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_negative_slippage_recorded(self, db_session: AsyncSession):
        """Fill below requested price = negative slippage (good for buys)."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "slip-002",
            "price": 44900.0,  # Filled below requested
        }

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade.slippage_pct is not None
        assert trade.slippage_pct < 0  # Favorable slippage

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_zero_slippage(self, db_session: AsyncSession):
        """Fill at exactly requested price = zero slippage."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "slip-003",
            "price": 45000.0,
        }

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade.slippage_pct == pytest.approx(0.0)

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_no_slippage_when_no_fill_price(self, db_session: AsyncSession):
        """When exchange returns no fill price, slippage should be None."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "order_id": "slip-004",
            "price": None,  # No fill yet
        }

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        # No fill_price => no slippage calc
        assert trade.slippage_pct is None


# ============================================================================
# 5. Simulated execution — Paper source when not initialized
# ============================================================================


class TestSimulatedExecution:
    """Test paper/simulated execution fallback."""

    @pytest.mark.critical
    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_simulated_when_not_initialized(self, db_session: AsyncSession):
        """Service without exchange connection should simulate trades."""
        service = LiveExecutionService()  # Not initialized, no client

        trade_id = _make_trade_id()

        result = await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        assert result["success"] is True
        assert result["source"] == "paper"
        assert result["status"] == "simulated"
        assert "Simulated" in result["message"]

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_simulated_records_paper_source(self, db_session: AsyncSession):
        """Simulated trade should have source='paper' in DB."""
        service = LiveExecutionService()

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="ETH-USDT",
            side="sell",
            size=1.0,
            limit_price=3000.0,
            pattern_name="Bearish Divergence",
            regime="bear",
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is not None
        assert trade.source == "paper"
        assert trade.pattern_name == "Bearish Divergence"
        assert trade.regime == "bear"

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_simulated_fills_at_limit_price(self, db_session: AsyncSession):
        """Simulated execution assumes fill at limit price."""
        service = LiveExecutionService()

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.5,
            limit_price=42000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is not None
        assert float(trade.entry_price) == pytest.approx(42000.0)
        # Slippage should be 0 since fill == requested
        assert trade.slippage_pct == pytest.approx(0.0)

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_simulated_has_no_order_id(self, db_session: AsyncSession):
        """Simulated trades should not have an exchange order_id."""
        service = LiveExecutionService()

        trade_id = _make_trade_id()

        await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade.order_id is None


# ============================================================================
# 6. Error handling — Exchange returns error
# ============================================================================


class TestErrorHandling:
    """Test error handling when exchange returns errors."""

    @pytest.mark.critical
    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_exchange_error_returns_failure(self, db_session: AsyncSession):
        """Exchange error should return success=False without DB record."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.return_value = {
            "error": True,
            "message": "Insufficient margin",
        }

        trade_id = _make_trade_id()

        result = await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=100.0,
            limit_price=45000.0,
        )

        assert result["success"] is False
        assert "Insufficient margin" in result["error"]
        assert result["trade_id"] == trade_id

        # Verify NO DB record created for failed order
        db_result = await db_session.exec(
            select(LiveTradeUnified).where(LiveTradeUnified.trade_id == trade_id)
        )
        trade = db_result.first()
        assert trade is None

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_exchange_exception_returns_failure(self, db_session: AsyncSession):
        """Exception during execution should be caught and returned."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_limit_order.side_effect = ConnectionError("Exchange unreachable")

        trade_id = _make_trade_id()

        result = await service.execute_limit_order(
            session=db_session,
            trade_id=trade_id,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            limit_price=45000.0,
        )

        assert result["success"] is False
        assert "Exchange unreachable" in result["error"]

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_market_order_exchange_error(self, db_session: AsyncSession):
        """Market order exchange error should return failure."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_market_order.return_value = {
            "error": True,
            "message": "Rate limit exceeded",
        }

        result = await service.execute_market_order(
            session=db_session,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="sell",
            size=0.5,
        )

        assert result["success"] is False

    @pytest.mark.requires_db
    @pytest.mark.asyncio
    async def test_market_order_exception(self, db_session: AsyncSession):
        """Market order exception should be caught gracefully."""
        service, mock_client = _build_service_with_mock_client()
        mock_client.place_market_order.side_effect = TimeoutError("Request timed out")

        result = await service.execute_market_order(
            session=db_session,
            agent_id=_make_agent_id(),
            symbol="BTC-USDT",
            side="sell",
            size=0.5,
        )

        assert result["success"] is False
        assert "timed out" in result["error"].lower()


# ============================================================================
# SERVICE STATE TESTS
# ============================================================================


class TestServiceState:
    """Test service initialization and readiness checks."""

    def test_not_ready_by_default(self):
        service = LiveExecutionService()
        assert service.is_ready() is False

    def test_ready_after_mock_init(self):
        service, _ = _build_service_with_mock_client()
        assert service.is_ready() is True

    @pytest.mark.asyncio
    async def test_close_resets_state(self):
        service, mock_client = _build_service_with_mock_client()
        assert service.is_ready() is True

        await service.close()

        assert service.is_ready() is False
        assert service._client is None
        mock_client.close.assert_called_once()
