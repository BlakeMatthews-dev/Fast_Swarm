"""
Sanity Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (API Endpoints)
Basic API sanity tests.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from Router.main import app

    return TestClient(app)


class TestAPIRoot:
    """CONTRACT: API root endpoint."""

    def test_root_endpoint_active(self, client):
        """CONTRACT: GET / returns status=active."""
        response = client.get("/")
        data = response.json()
        assert data.get("status") == "active"

    def test_root_returns_200(self, client):
        """CONTRACT: GET / returns HTTP 200."""
        response = client.get("/")
        assert response.status_code == 200


class TestHealthEndpoint:
    """CONTRACT: System health endpoint."""

    def test_health_endpoint_exists(self, client):
        """CONTRACT: GET /system/health returns 200."""
        response = client.get("/system/health")
        assert response.status_code == 200

    def test_health_contains_streams(self, client):
        """CONTRACT: Health response contains streams info."""
        response = client.get("/system/health")
        data = response.json()
        assert "streams" in data or "websocket_streams" in data or "exchange_streams" in data

    def test_health_contains_database(self, client):
        """CONTRACT: Health response contains database info."""
        response = client.get("/system/health")
        data = response.json()
        assert "database" in data or "db" in data or "postgres" in data
