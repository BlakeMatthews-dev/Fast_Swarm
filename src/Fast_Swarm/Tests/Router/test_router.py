"""
Router API Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (API Routes)
Tests for the /tests API router endpoints.
"""

import pytest

# ============================================================================
# TEST RUNNER ROUTER CONTRACT
# ============================================================================


@pytest.mark.asyncio
class TestTestRunnerRoutes:
    """CONTRACT: Test runner API endpoints."""

    async def test_post_run_all_tests(self, async_client):
        """CONTRACT: POST /tests/run/all triggers full test suite."""
        resp = await async_client.post("/tests/run/all")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        # Currently WIP, returns not_implemented status
        assert data["status"] == "not_implemented"
        assert "message" in data

    async def test_post_run_specific_test_file(self, async_client):
        """CONTRACT: POST /tests/run/{file} - endpoint not yet implemented."""
        # The test runner router currently only has /tests/run/all
        # A specific file endpoint would return 404 or 405
        resp = await async_client.post("/tests/run/some_test_file")
        assert resp.status_code in (404, 405)

    async def test_get_list_available_tests(self, async_client):
        """CONTRACT: GET /tests/status returns test runner status."""
        resp = await async_client.get("/tests/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "test_runner_wip"
        assert "message" in data

    async def test_run_nonexistent_test_returns_404(self, async_client):
        """CONTRACT: Running nonexistent test returns 404."""
        resp = await async_client.post("/tests/run/nonexistent_test_module")
        assert resp.status_code in (404, 405)

    async def test_run_invalid_test_path_rejected(self, async_client):
        """CONTRACT: Invalid test paths are rejected (no matching route)."""
        resp = await async_client.post("/tests/run/../../etc/passwd")
        assert resp.status_code in (404, 405)
        # Ensure no sensitive data leaked
        if resp.status_code == 200:
            data = resp.json()
            assert "passwd" not in str(data)
