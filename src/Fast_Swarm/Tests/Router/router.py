"""
Test Runner Router - WIP
Provides API endpoints to run tests programmatically.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/tests", tags=["Tests"])


@router.get("/status")
async def test_status():
    """Check test runner status."""
    return {"status": "test_runner_wip", "message": "Test runner endpoints coming soon"}


@router.post("/run/all")
async def run_all_tests():
    """Run all tests - WIP."""
    return {"status": "not_implemented", "message": "Test runner under development"}
