import asyncio
import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


class TestRunnerService:
    """Service to execute pytest suites programmatically."""

    def __init__(self, test_dir: str = "Fast_Swarm/Tests"):
        self.test_dir = Path(test_dir)

    async def run_all_tests(self) -> dict:
        """Run all tests in the test directory."""
        logger.info(f"Running all tests in {self.test_dir}...")

        # Run pytest in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: pytest.main([str(self.test_dir), "-v"]))

        result = {
            "status": "success" if exit_code == 0 else "failure",
            "exit_code": int(exit_code),
            "timestamp": datetime.utcnow().isoformat(),
        }

        if exit_code != 0:
            logger.error(f"Test suite failed with exit code {exit_code}")
        else:
            logger.info("Test suite passed successfully.")

        return result

    async def run_specific_test(self, test_file: str) -> dict:
        """Run a specific test file."""
        full_path = self.test_dir / test_file
        if not full_path.exists():
            return {"status": "error", "message": f"Test file {test_file} not found"}

        logger.info(f"Running specific test: {full_path}...")
        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: pytest.main([str(full_path), "-v"]))

        return {
            "status": "success" if exit_code == 0 else "failure",
            "exit_code": int(exit_code),
            "test_file": str(test_file),
        }


from datetime import datetime
