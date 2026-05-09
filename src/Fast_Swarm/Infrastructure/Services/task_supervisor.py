"""
Task Supervisor - Managed background task execution with auto-restart.

Replaces raw asyncio.create_task() calls with supervised tasks that:
- Auto-restart on failure with exponential backoff
- Track restart counts and failure reasons
- Clean shutdown on app termination
- Expose status for monitoring endpoints
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class TaskSupervisor:
    """
    Supervisor for background tasks with auto-restart capability.

    Usage:
        supervisor = TaskSupervisor()

        # In lifespan startup:
        await supervisor.spawn("evolution", evolution_loop)
        await supervisor.spawn("pattern_discovery", pattern_discovery_loop)

        yield  # Server runs...

        # In lifespan shutdown:
        await supervisor.shutdown()
    """

    def __init__(self, max_restarts: int = 5, base_backoff_seconds: float = 5.0):
        """
        Initialize the task supervisor.

        Args:
            max_restarts: Maximum restart attempts before giving up (per task)
            base_backoff_seconds: Base delay between restarts (multiplied by attempt number)
        """
        self.max_restarts = max_restarts
        self.base_backoff_seconds = base_backoff_seconds
        self.tasks: dict[str, asyncio.Task] = {}
        self.restart_counts: dict[str, int] = {}
        self.last_errors: dict[str, str] = {}
        self.started_at: dict[str, datetime] = {}
        self._shutdown = False

    async def spawn(
        self,
        name: str,
        coro_factory: Callable[[], Coroutine],
        max_restarts: int | None = None,
    ) -> None:
        """
        Spawn a supervised task that auto-restarts on failure.

        Args:
            name: Unique identifier for the task
            coro_factory: Zero-arg async function that returns a coroutine
            max_restarts: Override default max_restarts for this task
        """
        if name in self.tasks and not self.tasks[name].done():
            logger.warning(f"Task {name} already running, skipping spawn")
            return

        max_attempts = max_restarts if max_restarts is not None else self.max_restarts
        self.restart_counts[name] = 0
        self.started_at[name] = datetime.utcnow()

        async def supervised():
            while not self._shutdown and self.restart_counts[name] < max_attempts:
                attempt = self.restart_counts[name] + 1
                try:
                    logger.info(f"Task '{name}' starting (attempt {attempt}/{max_attempts})")
                    await coro_factory()
                    # If coro_factory returns normally (no exception), the task is done
                    logger.info(f"Task '{name}' completed normally")
                    break
                except asyncio.CancelledError:
                    logger.info(f"Task '{name}' cancelled")
                    break
                except Exception as e:
                    self.restart_counts[name] += 1
                    self.last_errors[name] = str(e)
                    logger.error(f"Task '{name}' crashed (attempt {attempt}): {e}", exc_info=True)

                    if self.restart_counts[name] < max_attempts and not self._shutdown:
                        backoff = self.base_backoff_seconds * self.restart_counts[name]
                        logger.info(f"Task '{name}' will restart in {backoff:.1f}s")
                        await asyncio.sleep(backoff)

            if self.restart_counts[name] >= max_attempts:
                logger.critical(
                    f"Task '{name}' exceeded {max_attempts} restart attempts, giving up. "
                    f"Last error: {self.last_errors.get(name)}"
                )

        self.tasks[name] = asyncio.create_task(supervised())
        logger.info(f"Spawned supervised task: {name}")

    async def shutdown(self, timeout: float = 10.0) -> dict[str, str]:
        """
        Cancel all tasks and wait for cleanup.

        Args:
            timeout: Maximum seconds to wait for task cancellation

        Returns:
            Dict of task names to their final status
        """
        self._shutdown = True
        results = {}

        for name, task in self.tasks.items():
            if not task.done():
                task.cancel()

        if self.tasks:
            done, pending = await asyncio.wait(self.tasks.values(), timeout=timeout, return_when=asyncio.ALL_COMPLETED)

            for name, task in self.tasks.items():
                if task in done:
                    results[name] = "stopped"
                else:
                    results[name] = "timeout"
                    logger.warning(f"Task '{name}' did not stop within {timeout}s")

        logger.info(f"Task supervisor shutdown complete: {results}")
        return results

    def get_status(self) -> dict[str, Any]:
        """
        Get status of all supervised tasks.

        Returns:
            Dict with task statuses for monitoring endpoints
        """
        status = {}
        for name, task in self.tasks.items():
            status[name] = {
                "running": not task.done(),
                "restart_count": self.restart_counts.get(name, 0),
                "last_error": self.last_errors.get(name),
                "started_at": self.started_at.get(name, datetime.utcnow()).isoformat(),
                "max_restarts": self.max_restarts,
            }
            if task.done():
                try:
                    exc = task.exception()
                    status[name]["exit_reason"] = str(exc) if exc else "normal"
                except asyncio.CancelledError:
                    status[name]["exit_reason"] = "cancelled"
        return status

    def is_healthy(self) -> bool:
        """
        Check if all tasks are running (no permanent failures).

        Returns:
            True if all tasks are running or haven't exceeded max_restarts
        """
        for name, task in self.tasks.items():
            if task.done() and self.restart_counts.get(name, 0) >= self.max_restarts:
                return False
        return True


# Singleton instance (optional - can also instantiate directly)
_supervisor: TaskSupervisor | None = None


def get_task_supervisor() -> TaskSupervisor:
    """Get the singleton TaskSupervisor instance."""
    global _supervisor
    if _supervisor is None:
        _supervisor = TaskSupervisor()
    return _supervisor
