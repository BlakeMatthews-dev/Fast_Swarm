"""
Sanity Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (API Endpoints)
Basic API sanity tests.
"""

import pytest


class TestAPIRoot:
    """CONTRACT: API root endpoint."""

    def test_root_endpoint_active(self):
        """CONTRACT: GET / returns status=active."""
        pytest.fail("NOT IMPLEMENTED - Root endpoint active")

    def test_root_returns_200(self):
        """CONTRACT: GET / returns HTTP 200."""
        pytest.fail("NOT IMPLEMENTED - Root returns 200")


class TestHealthEndpoint:
    """CONTRACT: System health endpoint."""

    def test_health_endpoint_exists(self):
        """CONTRACT: GET /system/health returns 200."""
        pytest.fail("NOT IMPLEMENTED - Health endpoint exists")

    def test_health_contains_streams(self):
        """CONTRACT: Health response contains streams info."""
        pytest.fail("NOT IMPLEMENTED - Health contains streams")

    def test_health_contains_database(self):
        """CONTRACT: Health response contains database info."""
        pytest.fail("NOT IMPLEMENTED - Health contains database")
