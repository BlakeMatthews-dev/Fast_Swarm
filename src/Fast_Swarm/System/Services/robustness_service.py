import asyncio
import logging
import random
from collections.abc import Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class RobustnessService:
    """
    Service for automated stability and chaos testing.
    Randomly validates features and scales up during nightly hours.
    """

    def __init__(self):
        self._running = False
        self._test_registry: list[Callable] = []
        self._nightly_hours = range(0, 6)  # 12 AM to 6 AM

    def register_test(self, func: Callable):
        """Register a feature validation function."""
        self._test_registry.append(func)

    async def start_chaos_loop(self):
        """Main loop for random feature validation."""
        self._running = True
        logger.info("Chaos Robustness Loop Started.")

        while self._running:
            # Determine sleep interval based on time of day
            is_night = datetime.utcnow().hour in self._nightly_hours

            if is_night:
                # Test heavily: every 5-15 minutes
                interval = random.randint(300, 900)
                logger.info("Nightly mode active: Scaling up validation frequency.")
            else:
                # Standard testing: every 30-60 minutes
                interval = random.randint(1800, 3600)

            await asyncio.sleep(interval)

            if self._test_registry:
                test_func = random.choice(self._test_registry)
                try:
                    logger.info(f"Chaos Test: Validating {test_func.__name__}...")
                    await test_func()
                except Exception as e:
                    logger.error(f"Chaos Test Failed for {test_func.__name__}: {e}")

    async def stop(self):
        self._running = False
        logger.info("Robustness Service Stopped.")

    # --- Built-in Chaos Tests ---

    async def validate_api_root(self):
        """Example test: Check if API root is responsive."""
        # This would use an internal httpx client or similar
        pass

    async def validate_economic_assumptions(self):
        """EDD: Run pytest on economic assumptions file."""
        from .test_runner_service import TestRunnerService

        runner = TestRunnerService()
        result = await runner.run_specific_test("test_economic_assumptions.py")
        if result["status"] != "success":
            logger.error(f"Economic assumptions validation FAILED: {result}")
        else:
            logger.info("Economic assumptions validation PASSED.")
        return result
