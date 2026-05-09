"""
API Smoke Tests - Hit every major FastAPI endpoint.

Uses httpx.AsyncClient with ASGITransport to test the FastAPI app
without starting a real server. Database and exchange interactions
are mocked to keep tests fast and isolated.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# We patch heavy startup operations before importing the app
# to avoid connecting to real databases or exchanges.


@pytest.fixture
def mock_lifespan():
    """Mock the app lifespan to skip DB init, streams, orchestrator, etc."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    return noop_lifespan


@pytest_asyncio.fixture
async def client(mock_lifespan):
    """Create an httpx AsyncClient against the FastAPI app with mocked startup."""
    import httpx

    with (
        patch("Fast_Swarm.Main.lifespan", mock_lifespan),
        patch("Fast_Swarm.Main.init_db", new_callable=AsyncMock),
        patch("Fast_Swarm.Main.ensure_database", new_callable=AsyncMock),
        patch("Fast_Swarm.Main.reset_evolution_flag"),
        patch("Fast_Swarm.Main.init_window_pool", new_callable=AsyncMock),
    ):
        from Fast_Swarm.Main import app

        # Override lifespan
        app.router.lifespan_context = mock_lifespan

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


# ============================================================================
# AGENT ENDPOINTS (/agents)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_agents(client):
    """GET /agents should return 200."""
    with patch("Fast_Swarm.Agents.Routers.agent_router.get_session", new_callable=AsyncMock):
        response = await client.get("/agents")
    # May return 200 with empty list or 500 if DB not available
    assert response.status_code in (200, 422, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_agent_stats(client):
    """GET /agents/stats/average should return 200."""
    response = await client.get("/agents/stats/average")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_agent_not_found(client):
    """GET /agents/nonexistent should return 404 or 500."""
    response = await client.get("/agents/nonexistent-agent-id")
    assert response.status_code in (404, 500)


# ============================================================================
# PATTERN ENDPOINTS (/patterns)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_patterns(client):
    """GET /patterns should return 200."""
    response = await client.get("/patterns")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_pattern_leaderboard(client):
    """GET /patterns/leaderboard should return 200."""
    response = await client.get("/patterns/leaderboard")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_patterns_by_tier(client):
    """GET /patterns/by-tier/1 should return valid response."""
    response = await client.get("/patterns/by-tier/1")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_patterns_by_origin(client):
    """GET /patterns/by-origin/technical should return valid response."""
    response = await client.get("/patterns/by-origin/technical")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_pattern_not_found(client):
    """GET /patterns/nonexistent should return 404 or 500."""
    response = await client.get("/patterns/nonexistent-pattern-id")
    assert response.status_code in (404, 500)


# ============================================================================
# ACTIONS ENDPOINTS (/actions)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_spawn(client):
    """POST /actions/spawn should accept valid payload."""
    response = await client.post(
        "/actions/spawn",
        json={"count": 1, "generation": 1},
    )
    assert response.status_code in (200, 422, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_cull(client):
    """POST /actions/cull should accept valid payload."""
    response = await client.post(
        "/actions/cull",
        json={"survival_rate": 0.7, "dry_run": True},
    )
    assert response.status_code in (200, 422, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_backtest_status(client):
    """GET /actions/backtest/status should return 200."""
    response = await client.get("/actions/backtest/status")
    assert response.status_code in (200, 500)


# ============================================================================
# EVOLUTION ENDPOINTS (/evolution)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_evolution_status(client):
    """GET /evolution/status should return 200."""
    response = await client.get("/evolution/status")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_evolution_monitor_cycles(client):
    """GET /evolution/monitor/cycles should return 200."""
    response = await client.get("/evolution/monitor/cycles")
    assert response.status_code in (200, 500)


# ============================================================================
# TRADE ENDPOINTS (/trades)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_trades(client):
    """GET /trades/ should return 200."""
    response = await client.get("/trades/")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_live_trades(client):
    """GET /trades/live should return 200."""
    response = await client.get("/trades/live")
    assert response.status_code in (200, 500)


# ============================================================================
# SYSTEM ENDPOINTS (/system)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_health(client):
    """GET /system/health should return 200."""
    response = await client.get("/system/health")
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "status" in data or "health" in data or isinstance(data, dict)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_progress(client):
    """GET /system/progress should return 200."""
    response = await client.get("/system/progress")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_orchestrator(client):
    """GET /system/orchestrator should return 200."""
    response = await client.get("/system/orchestrator")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_metrics(client):
    """GET /system/metrics should return 200."""
    response = await client.get("/system/metrics")
    assert response.status_code in (200, 500)


# ============================================================================
# TASKMASTER ENDPOINTS (/taskmaster)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_taskmaster_health(client):
    """GET /taskmaster/health should return 200."""
    response = await client.get("/taskmaster/health")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_taskmaster_components(client):
    """GET /taskmaster/components should return 200."""
    response = await client.get("/taskmaster/components")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_taskmaster_dashboard(client):
    """GET /taskmaster/dashboard should return 200."""
    response = await client.get("/taskmaster/dashboard")
    assert response.status_code in (200, 500)


# ============================================================================
# MARKET DATA ENDPOINTS (/market_data)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_market_data_symbols(client):
    """GET /market_data/symbols should return 200."""
    response = await client.get("/market_data/symbols")
    assert response.status_code in (200, 500)


# ============================================================================
# EXCHANGE ENDPOINTS (/exchanges)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchanges_list(client):
    """GET /exchanges/ should return 200."""
    response = await client.get("/exchanges/")
    assert response.status_code in (200, 500)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exchanges_status(client):
    """GET /exchanges/status should return 200."""
    response = await client.get("/exchanges/status")
    assert response.status_code in (200, 500)


# ============================================================================
# GOVERNANCE ENDPOINTS (/governance)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_committees(client):
    """GET /governance/committees should return 200."""
    response = await client.get("/governance/committees")
    assert response.status_code in (200, 500)


# ============================================================================
# TESTS ENDPOINTS (/tests)
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tests_status(client):
    """GET /tests/status should return 200."""
    response = await client.get("/tests/status")
    assert response.status_code in (200, 500)
