"""
Shared fixtures for Router API tests.

Provides an async HTTPX test client wired to a minimal FastAPI app
that includes all the production routers. Service-layer dependencies
are overridden with mocks so tests never hit a real database.
"""

import math
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Lightweight FastAPI app containing only the routers under test
# ---------------------------------------------------------------------------

def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app with all routers, no lifespan side-effects."""
    app = FastAPI(title="CoinSwarm Test", redirect_slashes=False)

    from Fast_Swarm.System.Routers.system_router import router as system_router
    from Fast_Swarm.Trades.Routers.trade_router import router as trade_router
    from Fast_Swarm.Agents.Routers.evolution_router import router as evolution_router
    from Fast_Swarm.Agents.Routers.agent_router import router as agent_router
    from Fast_Swarm.Patterns.Routers.pattern_router import router as pattern_router
    from Fast_Swarm.Tests.Router.router import router as test_runner_router

    app.include_router(system_router)
    app.include_router(trade_router)
    app.include_router(evolution_router)
    app.include_router(agent_router)
    app.include_router(pattern_router)
    app.include_router(test_runner_router)

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client():
    """
    Provide an httpx.AsyncClient bound to the test FastAPI app.

    The ``get_session`` dependency is overridden so that no real database
    connection is required. Individual tests can further patch service
    functions as needed.
    """
    app = _build_test_app()

    # Override the DB session dependency globally
    from Fast_Swarm.Database import get_session

    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
