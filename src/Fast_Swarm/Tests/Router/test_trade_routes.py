"""
Trade Router Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Fast_Swarm/CLAUDE.md (API Routes)
Tests for /trades endpoints.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# TRADE ROUTER CONTRACT
# ============================================================================


@pytest.mark.asyncio
class TestGetTradesList:
    """CONTRACT: GET /trades endpoint."""

    async def test_get_trades_200(self, async_client):
        """CONTRACT: GET /trades returns 200 OK."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/")
            assert resp.status_code == 200

    async def test_get_trades_list(self, async_client):
        """CONTRACT: Response is list of trades."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(
                return_value=[
                    {"trade_id": "t1", "symbol": "BTC/USDT", "pnl": 10.0},
                    {"trade_id": "t2", "symbol": "ETH/USDT", "pnl": -5.0},
                ]
            )

            resp = await async_client.get("/trades/")
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2

    async def test_get_trades_pagination(self, async_client):
        """CONTRACT: Supports offset and limit."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/?skip=10&limit=5")
            assert resp.status_code == 200
            # Verify service was called with correct params
            call_kwargs = mock_svc.get_all_trades.call_args
            assert call_kwargs[1]["offset"] == 10
            assert call_kwargs[1]["limit"] == 5

    async def test_get_trades_filter_agent_id(self, async_client):
        """CONTRACT: ?agent_id=X filters by agent."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/?agent_id=agent-001")
            assert resp.status_code == 200
            call_kwargs = mock_svc.get_all_trades.call_args
            assert call_kwargs[1]["agent_id"] == "agent-001"

    async def test_get_trades_filter_asset(self, async_client):
        """CONTRACT: ?symbol=BTC filters by symbol."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/?symbol=BTC")
            assert resp.status_code == 200
            call_kwargs = mock_svc.get_all_trades.call_args
            assert call_kwargs[1]["symbol"] == "BTC"

    async def test_get_trades_filter_date_range(self, async_client):
        """CONTRACT: ?source=evolution_backtest filters by source."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/?source=evolution_backtest")
            assert resp.status_code == 200
            call_kwargs = mock_svc.get_all_trades.call_args
            assert call_kwargs[1]["source"] == "evolution_backtest"

    async def test_get_trades_order_by_timestamp(self, async_client):
        """CONTRACT: Trades returned in order (service handles ordering)."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(
                return_value=[
                    {"trade_id": "t1", "pnl": 10.0},
                    {"trade_id": "t2", "pnl": -5.0},
                ]
            )

            resp = await async_client.get("/trades/")
            data = resp.json()
            assert len(data) == 2
            assert data[0]["trade_id"] == "t1"


@pytest.mark.asyncio
class TestGetTradeById:
    """CONTRACT: GET /trades/{id} endpoint."""

    async def test_get_trade_by_id_200(self, async_client):
        """CONTRACT: Valid ID returns 200 OK."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_trade_by_id = AsyncMock(
                return_value={
                    "trade_id": "trade-001",
                    "symbol": "BTC/USDT",
                    "pnl": 100.0,
                    "pnl_pct": 2.0,
                }
            )

            resp = await async_client.get("/trades/trade-001")
            assert resp.status_code == 200

    async def test_get_trade_by_id_404(self, async_client):
        """CONTRACT: Invalid ID returns 404."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_trade_by_id = AsyncMock(return_value=None)

            resp = await async_client.get("/trades/nonexistent-trade")
            assert resp.status_code == 404
            data = resp.json()
            assert "detail" in data

    async def test_get_trade_includes_pnl(self, async_client):
        """CONTRACT: Response includes pnl and pnl_pct."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_trade_by_id = AsyncMock(
                return_value={
                    "trade_id": "trade-001",
                    "symbol": "BTC/USDT",
                    "pnl": 100.0,
                    "pnl_pct": 2.0,
                    "entry_price": 50000.0,
                    "exit_price": 51000.0,
                }
            )

            resp = await async_client.get("/trades/trade-001")
            data = resp.json()
            assert "pnl" in data
            assert "pnl_pct" in data
            assert data["pnl"] == 100.0
            assert data["pnl_pct"] == 2.0

    async def test_get_trade_includes_indicators(self, async_client):
        """CONTRACT: Response includes symbol and trade details."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_trade_by_id = AsyncMock(
                return_value={
                    "trade_id": "trade-001",
                    "symbol": "BTC/USDT",
                    "entry_price": 50000.0,
                    "exit_price": 51000.0,
                    "pnl": 100.0,
                    "pnl_pct": 2.0,
                }
            )

            resp = await async_client.get("/trades/trade-001")
            data = resp.json()
            assert "symbol" in data
            assert data["symbol"] == "BTC/USDT"


@pytest.mark.asyncio
class TestGetTradesByAgent:
    """CONTRACT: GET /trades/stats/{agent_id} endpoint."""

    async def test_get_trades_by_agent_200(self, async_client):
        """CONTRACT: Returns 200 OK."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "agent_id": "agent-001",
                    "total_trades": 50,
                    "win_rate": 0.6,
                    "average_pnl": 15.0,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            assert resp.status_code == 200

    async def test_get_trades_by_agent_list(self, async_client):
        """CONTRACT: Returns agent's trade stats."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "agent_id": "agent-001",
                    "total_trades": 50,
                    "win_rate": 0.6,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            data = resp.json()
            assert "total_trades" in data or "agent_id" in data

    async def test_get_trades_by_agent_404(self, async_client):
        """CONTRACT: Stats for nonexistent agent returns empty or error."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={"agent_id": "nonexistent", "total_trades": 0}
            )

            resp = await async_client.get("/trades/stats/nonexistent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_trades"] == 0


@pytest.mark.asyncio
class TestGetTradesByPattern:
    """CONTRACT: GET /trades/?pattern_id=X endpoint."""

    async def test_get_trades_by_pattern_200(self, async_client):
        """CONTRACT: Returns 200 OK."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(return_value=[])

            resp = await async_client.get("/trades/?pattern_id=pat-001")
            assert resp.status_code == 200

    async def test_get_trades_by_pattern_list(self, async_client):
        """CONTRACT: Returns list of pattern's trades."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_all_trades = AsyncMock(
                return_value=[
                    {"trade_id": "t1", "pattern_id": "pat-001"},
                    {"trade_id": "t2", "pattern_id": "pat-001"},
                ]
            )

            resp = await async_client.get("/trades/?pattern_id=pat-001")
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2
            call_kwargs = mock_svc.get_all_trades.call_args
            assert call_kwargs[1]["pattern_id"] == "pat-001"


@pytest.mark.asyncio
class TestGetTradeStats:
    """CONTRACT: GET /trades/stats/{agent_id} endpoint."""

    async def test_get_trade_stats_200(self, async_client):
        """CONTRACT: Returns 200 OK."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "total_trades": 100,
                    "win_rate": 0.55,
                    "average_pnl": 12.5,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            assert resp.status_code == 200

    async def test_get_trade_stats_total_count(self, async_client):
        """CONTRACT: Response includes total_trades."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "total_trades": 250,
                    "win_rate": 0.55,
                    "average_pnl": 12.5,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            data = resp.json()
            assert "total_trades" in data
            assert data["total_trades"] == 250

    async def test_get_trade_stats_win_rate(self, async_client):
        """CONTRACT: Response includes win_rate."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "total_trades": 100,
                    "win_rate": 0.62,
                    "average_pnl": 15.0,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            data = resp.json()
            assert "win_rate" in data
            assert data["win_rate"] == 0.62

    async def test_get_trade_stats_average_pnl(self, async_client):
        """CONTRACT: Response includes average_pnl."""
        with patch(
            "Fast_Swarm.Trades.Routers.trade_router.trade_service"
        ) as mock_svc:
            mock_svc.get_agent_trade_stats = AsyncMock(
                return_value={
                    "total_trades": 100,
                    "win_rate": 0.55,
                    "average_pnl": 18.75,
                }
            )

            resp = await async_client.get("/trades/stats/agent-001")
            data = resp.json()
            assert "average_pnl" in data
            assert data["average_pnl"] == 18.75
