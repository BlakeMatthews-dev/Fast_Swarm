"""
Feature Flags - Blue/Green Service Versioning

MASTER TEST ADMIN DECREE: Parallel universe development.
Every critical service can have a Blue (stable) and Green (experimental) version.
Feature flags allow runtime switching for A/B testing and safe rollouts.

Usage:
    # Check current version
    from Config.feature_flags import FLAGS, ServiceVersion

    if FLAGS.get_version("fitness_service") == ServiceVersion.GREEN:
        # Use experimental implementation
        pass

    # Override via environment:
    # FAST_SWARM_FITNESS_VERSION=green uvicorn Main:app
    # FAST_SWARM_GLOBAL_VERSION=green uvicorn Main:app  (all services)
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ServiceVersion(Enum):
    """Service version identifier."""

    BLUE = "blue"  # Stable production version
    GREEN = "green"  # Experimental version


@dataclass
class FeatureFlags:
    """
    Central feature flag configuration.

    Blue = Stable, battle-tested code
    Green = Experimental, under validation

    Switching is done via environment variables for safety.
    """

    # Individual service version flags
    fitness_service: ServiceVersion = ServiceVersion.BLUE
    backtest_service: ServiceVersion = ServiceVersion.BLUE
    backtest_engine: ServiceVersion = ServiceVersion.BLUE
    evolution_service: ServiceVersion = ServiceVersion.BLUE
    spawn_service: ServiceVersion = ServiceVersion.BLUE
    cull_service: ServiceVersion = ServiceVersion.BLUE
    ranking_service: ServiceVersion = ServiceVersion.BLUE

    # Global override (for full A/B testing)
    global_version: ServiceVersion | None = None

    # Feature toggles (not version-based)
    enable_chaos_testing: bool = False
    enable_mutation_tracking: bool = False
    enable_detailed_logging: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        """
        Load flags from environment variables.

        Environment variables:
            FAST_SWARM_FITNESS_VERSION=blue|green
            FAST_SWARM_BACKTEST_VERSION=blue|green
            FAST_SWARM_ENGINE_VERSION=blue|green
            FAST_SWARM_EVOLUTION_VERSION=blue|green
            FAST_SWARM_GLOBAL_VERSION=blue|green (overrides all)
            FAST_SWARM_CHAOS_TESTING=true|false
        """

        def get_version(env_var: str, default: str = "blue") -> ServiceVersion:
            value = os.getenv(env_var, default).lower()
            return ServiceVersion.GREEN if value == "green" else ServiceVersion.BLUE

        def get_bool(env_var: str, default: bool = False) -> bool:
            value = os.getenv(env_var, str(default)).lower()
            return value in ("true", "1", "yes", "on")

        global_override = os.getenv("FAST_SWARM_GLOBAL_VERSION")

        return cls(
            fitness_service=get_version("FAST_SWARM_FITNESS_VERSION"),
            backtest_service=get_version("FAST_SWARM_BACKTEST_VERSION"),
            backtest_engine=get_version("FAST_SWARM_ENGINE_VERSION"),
            evolution_service=get_version("FAST_SWARM_EVOLUTION_VERSION"),
            spawn_service=get_version("FAST_SWARM_SPAWN_VERSION"),
            cull_service=get_version("FAST_SWARM_CULL_VERSION"),
            ranking_service=get_version("FAST_SWARM_RANKING_VERSION"),
            global_version=ServiceVersion(global_override) if global_override else None,
            enable_chaos_testing=get_bool("FAST_SWARM_CHAOS_TESTING"),
            enable_mutation_tracking=get_bool("FAST_SWARM_MUTATION_TRACKING"),
            enable_detailed_logging=get_bool("FAST_SWARM_DETAILED_LOGGING"),
        )

    def get_version(self, service_name: str) -> ServiceVersion:
        """
        Get effective version for a service.

        Global override takes precedence if set.
        """
        if self.global_version is not None:
            return self.global_version
        return getattr(self, service_name, ServiceVersion.BLUE)

    def is_green(self, service_name: str) -> bool:
        """Check if a service is running green (experimental) version."""
        return self.get_version(service_name) == ServiceVersion.GREEN

    def is_blue(self, service_name: str) -> bool:
        """Check if a service is running blue (stable) version."""
        return self.get_version(service_name) == ServiceVersion.BLUE

    def to_dict(self) -> dict[str, Any]:
        """Export flags as dictionary (for logging/debugging)."""
        return {
            "fitness_service": self.fitness_service.value,
            "backtest_service": self.backtest_service.value,
            "backtest_engine": self.backtest_engine.value,
            "evolution_service": self.evolution_service.value,
            "spawn_service": self.spawn_service.value,
            "cull_service": self.cull_service.value,
            "ranking_service": self.ranking_service.value,
            "global_version": self.global_version.value if self.global_version else None,
            "enable_chaos_testing": self.enable_chaos_testing,
            "enable_mutation_tracking": self.enable_mutation_tracking,
            "enable_detailed_logging": self.enable_detailed_logging,
        }


# Global instance - loaded from environment at import time
FLAGS = FeatureFlags.from_env()


# =============================================================================
# SERVICE ROUTER HELPERS
# =============================================================================


def get_fitness_impl():
    """
    Get the active fitness service implementation.

    Usage in fitness_service.py:
        from Config.feature_flags import get_fitness_impl
        _impl = get_fitness_impl()
        return _impl.calculate_fitness(trades)
    """
    if FLAGS.is_green("fitness_service"):
        # Lazy import to avoid circular dependencies
        from Agents.Services import fitness_service_green as impl
    else:
        from Agents.Services import fitness_service_blue as impl
    return impl


def get_backtest_impl():
    """Get the active backtest service implementation."""
    if FLAGS.is_green("backtest_service"):
        from Backtest.Services import backtest_service_green as impl
    else:
        from Backtest.Services import backtest_service_blue as impl
    return impl


# =============================================================================
# TESTING UTILITIES
# =============================================================================


def with_version(service_name: str, version: ServiceVersion):
    """
    Context manager for temporarily switching service version.

    Usage in tests:
        with with_version("fitness_service", ServiceVersion.GREEN):
            result = calculate_fitness(trades)
    """

    class VersionContext:
        def __init__(self):
            self.original = getattr(FLAGS, service_name)

        def __enter__(self):
            setattr(FLAGS, service_name, version)
            return self

        def __exit__(self, *args):
            setattr(FLAGS, service_name, self.original)

    return VersionContext()


def reset_flags():
    """Reset all flags to defaults (useful in tests)."""
    global FLAGS
    FLAGS = FeatureFlags()
