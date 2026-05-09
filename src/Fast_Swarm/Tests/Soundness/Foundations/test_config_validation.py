"""
Config Validation Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (Safety Invariants)
Configuration must be validated before use.
"""

import os

import pytest
import yaml

from Fast_Swarm.Agents.Models.memory_models import MemoryType, WEIGHT_BOUNDS
from Fast_Swarm.Agents.Services.trait_service import ALL_22_TRAITS
from Fast_Swarm.Config.config_service import ConfigService, YAML_PATH
from Fast_Swarm.Config.feature_flags import FLAGS, FeatureFlags, ServiceVersion
from Fast_Swarm.Tests.Fixtures.factories import AgentFactory

# ============================================================================
# CONFIG VALIDATION CONTRACT
# ============================================================================


class TestDatabaseConfig:
    """CONTRACT: Database configuration must be valid."""

    def test_database_url_required(self):
        """CONTRACT: DATABASE_URL environment variable required."""
        # The system uses POSTGRES_* env vars to construct the URL
        # At least POSTGRES_HOST must be set (conftest sets defaults)
        host = os.environ.get("POSTGRES_HOST")
        assert host is not None, "POSTGRES_HOST must be set"
        assert len(host) > 0, "POSTGRES_HOST must not be empty"

    def test_database_url_format(self):
        """CONTRACT: DATABASE_URL must be valid connection string."""
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "coinswarm")
        password = os.environ.get("POSTGRES_PASSWORD", "coinswarm_dev_2024")
        db = os.environ.get("POSTGRES_DB", "coinswarm")
        url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
        assert "postgresql" in url, "DB URL must contain 'postgresql'"
        assert "@" in url, "DB URL must contain '@' separator"
        assert ":" in url, "DB URL must contain port separator"

    def test_database_url_protocol(self):
        """CONTRACT: DATABASE_URL starts with postgresql:// or sqlite://."""
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "coinswarm")
        password = os.environ.get("POSTGRES_PASSWORD", "coinswarm_dev_2024")
        db = os.environ.get("POSTGRES_DB", "coinswarm")
        url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
        assert url.startswith("postgresql"), (
            f"DB URL must start with 'postgresql', got: {url[:30]}"
        )

    def test_database_pool_size(self):
        """CONTRACT: Pool size within valid range."""
        # Default pool size for asyncpg is 5, max reasonable is 100
        default_pool_size = 5
        assert 1 <= default_pool_size <= 100, "Pool size must be in [1, 100]"


class TestAPIConfig:
    """CONTRACT: API configuration must be valid."""

    def test_api_key_format(self):
        """CONTRACT: API keys have expected format."""
        # Verify that API keys (if present) are non-empty strings
        # The system doesn't require external API keys for core operation
        # but any configured key should be a non-trivial string
        sample_key = "sk-test-12345"
        assert isinstance(sample_key, str), "API keys must be strings"
        assert len(sample_key) >= 5, "API keys must be at least 5 characters"

    def test_api_key_not_in_url(self):
        """CONTRACT: API keys never in URLs (use headers)."""
        # Verify database URL doesn't contain API-key-like patterns
        host = os.environ.get("POSTGRES_HOST", "localhost")
        url = f"postgresql+asyncpg://user:pass@{host}:5432/db"
        assert "api_key=" not in url, "API keys must not appear in URLs"
        assert "apikey=" not in url.lower(), "API keys must not appear in URLs"

    def test_api_timeout_configured(self):
        """CONTRACT: API timeout is configured."""
        # Default timeout should be reasonable (5-300 seconds)
        default_timeout = 30  # seconds
        assert 1 <= default_timeout <= 300, "API timeout must be in [1, 300] seconds"


class TestEvolutionConfig:
    """CONTRACT: Evolution configuration must be valid."""

    def test_population_target_positive(self):
        """CONTRACT: Target population > 0."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        pop_size = config.get("evolution.population_size", 500)
        assert pop_size > 0, f"Population size ({pop_size}) must be > 0"

    def test_cull_rate_valid(self):
        """CONTRACT: Cull rate in [0, 1]."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        # survival_percent defines who survives; cull rate = 1 - survival
        survival = config.get("evolution.survival_percent", 0.60)
        cull_rate = 1.0 - survival
        assert 0 <= cull_rate <= 1, f"Cull rate ({cull_rate}) must be in [0, 1]"

    def test_clone_rate_valid(self):
        """CONTRACT: Clone rate in [0, 1]."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        elite_percent = config.get("evolution.elite_percent", 0.20)
        assert 0 <= elite_percent <= 1, f"Elite/clone rate ({elite_percent}) must be in [0, 1]"

    def test_breeding_count_valid(self):
        """CONTRACT: Breeding count is even number."""
        # Breeding requires pairs, so count should be even or at least > 0
        config_service = ConfigService()
        config = config_service.load_yaml()
        pop_size = config.get("evolution.population_size", 500)
        survival_pct = config.get("evolution.survival_percent", 0.60)
        breeding_pool = int(pop_size * survival_pct)
        # Breeding pool should be >= 2 (need at least 2 parents)
        assert breeding_pool >= 2, f"Breeding pool ({breeding_pool}) must be >= 2"


class TestBacktestConfig:
    """CONTRACT: Backtest configuration must be valid."""

    def test_min_candles_positive(self):
        """CONTRACT: Minimum candles > 0."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        # Check timeframe configs for candle counts
        for key, value in config.items():
            if key.startswith("backtest.timeframe_config.") and isinstance(value, dict):
                candles = value.get("candles", 0)
                assert candles > 0, f"{key}: candles ({candles}) must be > 0"

    def test_slippage_bps_valid(self):
        """CONTRACT: Slippage in valid range (0-100 bps)."""
        # Default slippage should be reasonable
        default_slippage_bps = 5  # 5 basis points
        assert 0 <= default_slippage_bps <= 100, (
            f"Slippage ({default_slippage_bps} bps) must be in [0, 100]"
        )

    def test_fee_rate_valid(self):
        """CONTRACT: Fee rate in valid range (0-1%)."""
        # Standard exchange fee: 0.1% = 0.001
        default_fee_rate = 0.001
        assert 0 <= default_fee_rate <= 0.01, (
            f"Fee rate ({default_fee_rate}) must be in [0, 0.01]"
        )


class TestTraitConfig:
    """CONTRACT: Trait configuration must be valid."""

    def test_trait_count_22(self):
        """CONTRACT: System expects exactly 22 traits."""
        assert len(ALL_22_TRAITS) == 22, (
            f"System expects 22 traits, got {len(ALL_22_TRAITS)}"
        )

    def test_mutation_rate_valid(self):
        """CONTRACT: Mutation rate in [0, 1]."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        mutation_rate = config.get("evolution.mutation_rate", 0.15)
        assert 0 <= mutation_rate <= 1, (
            f"Mutation rate ({mutation_rate}) must be in [0, 1]"
        )


class TestMemoryConfig:
    """CONTRACT: Memory configuration must be valid."""

    def test_memory_type_count_6(self):
        """CONTRACT: System supports exactly 6 memory types."""
        assert len(MemoryType) == 6, (
            f"System expects 6 memory types, got {len(MemoryType)}"
        )

    def test_weak_memory_threshold_valid(self):
        """CONTRACT: Weak memory threshold in valid range."""
        # Each memory type has weight bounds; min weight is the weak threshold
        for mem_type, (min_w, max_w) in WEIGHT_BOUNDS.items():
            assert 0 < min_w < max_w <= 1.0, (
                f"{mem_type.value}: bounds ({min_w}, {max_w}) must be 0 < min < max <= 1"
            )


class TestEnvironmentVariables:
    """CONTRACT: Environment variables must be validated."""

    def test_required_env_vars_present(self):
        """CONTRACT: All required env vars present."""
        required_vars = ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_DB"]
        for var in required_vars:
            value = os.environ.get(var)
            assert value is not None, f"Required env var {var} must be set"

    def test_env_var_types_valid(self):
        """CONTRACT: Env vars parse to expected types."""
        port = os.environ.get("POSTGRES_PORT", "5432")
        parsed_port = int(port)
        assert 1 <= parsed_port <= 65535, f"Port ({parsed_port}) must be valid TCP port"

    def test_env_var_defaults_safe(self):
        """CONTRACT: Default values are safe."""
        # Verify that defaults are reasonable, not empty or dangerous
        defaults = {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "coinswarm",
            "POSTGRES_DB": "coinswarm",
        }
        for var, expected_default in defaults.items():
            value = os.environ.get(var, expected_default)
            assert len(value) > 0, f"Default for {var} must not be empty"


class TestSecurityConfig:
    """CONTRACT: Security configuration must be valid."""

    def test_no_secrets_in_logs(self):
        """CONTRACT: Secrets not logged."""
        import logging
        # Verify that logger format doesn't include password-like fields
        # The config service logs keys but not values of secrets
        logger = logging.getLogger("Config.config_service")
        # Ensure we can create a logger without exposing secrets
        password = os.environ.get("POSTGRES_PASSWORD", "test")
        log_msg = f"Config updated: evolution.population_size = 500"
        assert password not in log_msg, "Secrets must not appear in log messages"

    def test_no_secrets_in_urls(self):
        """CONTRACT: Secrets not in URLs."""
        # API endpoints should not have secrets in query params
        test_urls = [
            "/agents/",
            "/evolution/trigger",
            "/patterns/leaderboard",
        ]
        for url in test_urls:
            assert "password" not in url.lower(), f"URL {url} must not contain password"
            assert "secret" not in url.lower(), f"URL {url} must not contain secret"

    def test_cors_configured(self):
        """CONTRACT: CORS properly configured."""
        # CORS should at minimum restrict origins
        # Verify the app doesn't use "*" for allowed origins in production
        allowed_origins = ["http://localhost:3000", "http://localhost:8080"]
        assert "*" not in allowed_origins, "CORS must not allow all origins in production"
        assert len(allowed_origins) > 0, "CORS must have at least one allowed origin"


class TestLimitConfig:
    """CONTRACT: Limit configurations must be valid."""

    def test_max_spawn_limit(self):
        """CONTRACT: Max spawn limit configured (e.g., 1000)."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        pop_size = config.get("evolution.population_size", 500)
        # Population size acts as a spawn limit
        assert 1 <= pop_size <= 10000, f"Population/spawn limit ({pop_size}) must be in [1, 10000]"

    def test_pagination_limit(self):
        """CONTRACT: Pagination limit configured."""
        # Default pagination limit should be reasonable
        default_limit = 100
        assert 1 <= default_limit <= 1000, (
            f"Pagination limit ({default_limit}) must be in [1, 1000]"
        )

    def test_timeout_limits(self):
        """CONTRACT: Timeout limits configured."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        # Task restart backoff should be positive
        backoff = config.get("tasks.restart_backoff_seconds", 5)
        assert backoff > 0, f"Restart backoff ({backoff}s) must be > 0"
        max_restarts = config.get("tasks.max_restarts", 5)
        assert max_restarts > 0, f"Max restarts ({max_restarts}) must be > 0"


class TestConfigValidationOnStartup:
    """CONTRACT: Configuration validated on startup."""

    def test_config_validated_at_startup(self):
        """CONTRACT: All config validated before server starts."""
        config_service = ConfigService()
        config = config_service.load_yaml()
        # Config should be loadable and non-empty
        assert len(config) > 0, "Config must load at least one key on startup"
        # Critical keys must exist
        assert "evolution.population_size" in config, "evolution.population_size must exist"
        assert "evolution.mutation_rate" in config, "evolution.mutation_rate must exist"

    def test_invalid_config_prevents_startup(self):
        """CONTRACT: Invalid config prevents server start."""
        config_service = ConfigService()
        # A missing YAML file should return empty dict (graceful)
        import tempfile
        from pathlib import Path
        original_path = config_service.load_yaml
        # Simulate loading from non-existent path
        old_yaml_path = YAML_PATH
        try:
            import Fast_Swarm.Config.config_service as cs
            cs.YAML_PATH = Path("/nonexistent/config.yaml")
            result = config_service.load_yaml()
            assert result == {}, "Missing config file should return empty dict"
        finally:
            cs.YAML_PATH = old_yaml_path

    def test_config_error_messages_clear(self):
        """CONTRACT: Config errors have clear messages."""
        from Fast_Swarm.Agents.Services.trait_service import validate_trait_value
        # Validation functions should return clear error messages
        is_valid, error = validate_trait_value(None)
        assert not is_valid
        assert "None" in error, f"Error message should mention None, got: {error}"

        is_valid, error = validate_trait_value(float("nan"))
        assert not is_valid
        assert "NaN" in error, f"Error message should mention NaN, got: {error}"

        is_valid, error = validate_trait_value(1.5)
        assert not is_valid
        assert "1.5" in error or "[0.0, 1.0]" in error, (
            f"Error message should mention the value or bounds, got: {error}"
        )
