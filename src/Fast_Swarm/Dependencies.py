"""
Dependency Injection Module

Uses @lru_cache for lazy singleton initialization instead of module-level globals.
This enables:
- Lazy initialization (created on first use, not import)
- Easy testing via dependency_overrides
- Explicit dependencies in route signatures
- Proper lifecycle management

Usage in routers:
    from fastapi import Depends
    from Fast_Swarm.Dependencies import get_stream_manager, get_data_collector

    @router.get("/status")
    async def status(
        stream_manager: StreamManagerService = Depends(get_stream_manager),
    ):
        return {"connected": stream_manager.is_connected}

Usage in tests:
    app.dependency_overrides[get_stream_manager] = lambda: MockStreamManager()
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from .Database import async_session_maker

if TYPE_CHECKING:
    from .Infrastructure.Services.collector_service import DataCollectorService
    from .Infrastructure.Services.stream_manager_service import StreamManagerService
    from .System.Services.robustness_service import RobustnessService


@lru_cache
def get_stream_manager() -> "StreamManagerService":
    """
    Get the singleton StreamManagerService instance.

    Lazy initialization - created on first call, reused thereafter.
    """
    from .Infrastructure.Services.stream_manager_service import StreamManagerService

    return StreamManagerService()


@lru_cache
def get_data_collector() -> "DataCollectorService":
    """
    Get the singleton DataCollectorService instance.

    Lazy initialization - created on first call, reused thereafter.
    """
    from .Infrastructure.Services.collector_service import DataCollectorService

    return DataCollectorService(async_session_maker)


@lru_cache
def get_robustness_service() -> "RobustnessService":
    """
    Get the singleton RobustnessService instance.

    Lazy initialization - created on first call, reused thereafter.
    """
    from .System.Services.robustness_service import RobustnessService

    return RobustnessService()


# =============================================================================
# Backwards compatibility aliases (for existing code that imports globals)
# These will be removed in a future version - migrate to Depends() pattern
# =============================================================================


# Lazy properties that call the factory functions
class _LazyServiceProxy:
    """Proxy that lazily initializes services on first access."""

    @property
    def stream_manager(self) -> "StreamManagerService":
        return get_stream_manager()

    @property
    def data_collector(self) -> "DataCollectorService":
        return get_data_collector()

    @property
    def robustness_service(self) -> "RobustnessService":
        return get_robustness_service()


_proxy = _LazyServiceProxy()


# For direct attribute access (backwards compat with `Dependencies.stream_manager`)
# Module-level __getattr__ handles: from Fast_Swarm.Dependencies import stream_manager
def __getattr__(name: str):
    """Module-level __getattr__ for lazy service access."""
    if name == "stream_manager":
        return get_stream_manager()
    elif name == "data_collector":
        return get_data_collector()
    elif name == "robustness_service":
        return get_robustness_service()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
