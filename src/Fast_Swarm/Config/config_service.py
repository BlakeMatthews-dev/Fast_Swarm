"""
Configuration Service with YAML + Database Sync

This service provides:
- YAML file as source of truth for deploys (version controlled)
- Database table for runtime queries (fast, cached)
- Bidirectional sync every 6 hours
- API for runtime config updates
"""

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Path to YAML config file
CONFIG_DIR = Path(__file__).parent
YAML_PATH = CONFIG_DIR / "system_config.yaml"


class ConfigService:
    """
    Configuration service with YAML + Database sync.

    Usage:
        config = get_config_service()
        population_size = await config.get("evolution.population_size", default=500)
        await config.set("evolution.population_size", 600, source="api")
    """

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._cache_loaded = False
        self._sync_task: asyncio.Task | None = None

    def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = ".") -> dict[str, Any]:
        """Flatten nested dict to dot-notation keys."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict) and not self._is_leaf_dict(v):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _is_leaf_dict(self, d: dict) -> bool:
        """Check if dict is a leaf node (e.g., timeframe_config entries)."""
        # Leaf dicts have simple values, not nested dicts
        if not d:
            return True
        first_value = next(iter(d.values()))
        return not isinstance(first_value, dict)

    def _unflatten_dict(self, d: dict[str, Any], sep: str = ".") -> dict:
        """Unflatten dot-notation keys to nested dict."""
        result = {}
        for key, value in d.items():
            parts = key.split(sep)
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    def load_yaml(self) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if not YAML_PATH.exists():
            logger.warning(f"Config file not found: {YAML_PATH}")
            return {}

        with open(YAML_PATH) as f:
            config = yaml.safe_load(f) or {}

        return self._flatten_dict(config)

    def save_yaml(self, flat_config: dict[str, Any]) -> None:
        """Save configuration to YAML file."""
        nested = self._unflatten_dict(flat_config)

        with open(YAML_PATH, "w") as f:
            yaml.dump(nested, f, default_flow_style=False, sort_keys=False, indent=2)

        logger.info(f"Config saved to {YAML_PATH}")

    async def load_yaml_to_db(self, session: AsyncSession) -> int:
        """
        Load YAML config into database (startup operation).
        YAML wins on conflict - it's the source of truth for deploys.

        Returns number of keys loaded.
        """
        flat_config = self.load_yaml()
        loaded = 0

        for key, value in flat_config.items():
            # Convert value to JSON string
            json_value = json.dumps(value)

            await session.execute(
                text("""
                    INSERT INTO system_config (key, value, source, updated_at)
                    VALUES (:key, :value, 'yaml', NOW())
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        source = 'yaml',
                        updated_at = NOW()
                """),
                {"key": key, "value": json_value},
            )
            loaded += 1

        await session.commit()

        # Refresh cache
        self._cache = flat_config
        self._cache_loaded = True

        logger.info(f"Loaded {loaded} config keys from YAML to database")
        return loaded

    async def sync_db_to_yaml(self, session: AsyncSession) -> int:
        """
        Sync database config back to YAML (periodic operation).
        Captures API changes for version control.

        Returns number of keys synced.
        """
        result = await session.execute(text("SELECT key, value, source FROM system_config ORDER BY key"))
        rows = result.fetchall()

        flat_config = {}
        api_changes = 0

        for row in rows:
            key, value_json, source = row
            value = json.loads(value_json)
            flat_config[key] = value
            if source == "api":
                api_changes += 1

        if api_changes > 0:
            self.save_yaml(flat_config)
            logger.info(f"Synced {api_changes} API changes back to YAML")

            # Mark all as yaml source now that they're saved
            await session.execute(text("UPDATE system_config SET source = 'yaml' WHERE source = 'api'"))
            await session.commit()

        # Refresh cache
        self._cache = flat_config
        self._cache_loaded = True

        return api_changes

    async def get(self, key: str, default: Any = None, session: AsyncSession | None = None) -> Any:
        """
        Get a configuration value.

        Uses cache if available, falls back to database query.
        Supports dot-notation keys: "evolution.population_size"
        """
        # Try cache first
        if self._cache_loaded and key in self._cache:
            return self._cache[key]

        # If no session, return from cache or default
        if session is None:
            return self._cache.get(key, default)

        # Query database
        result = await session.execute(text("SELECT value FROM system_config WHERE key = :key"), {"key": key})
        row = result.fetchone()

        if row is None:
            return default

        value = json.loads(row[0])
        self._cache[key] = value
        return value

    async def get_section(self, prefix: str, session: AsyncSession | None = None) -> dict[str, Any]:
        """
        Get all config values under a prefix.

        Example: get_section("evolution") returns all evolution.* keys
        """
        if self._cache_loaded:
            return {k: v for k, v in self._cache.items() if k.startswith(f"{prefix}.")}

        if session is None:
            return {}

        result = await session.execute(
            text("SELECT key, value FROM system_config WHERE key LIKE :prefix"), {"prefix": f"{prefix}.%"}
        )

        return {row[0]: json.loads(row[1]) for row in result.fetchall()}

    async def set(self, key: str, value: Any, source: str = "api", session: AsyncSession | None = None) -> bool:
        """
        Set a configuration value.

        Args:
            key: Dot-notation key (e.g., "evolution.population_size")
            value: New value (will be JSON serialized)
            source: 'api' for runtime changes, 'yaml' for deploy changes
            session: Database session (required for persistence)

        Returns:
            True if successful
        """
        if session is None:
            logger.warning(f"Cannot persist config change without session: {key}")
            self._cache[key] = value
            return False

        json_value = json.dumps(value)

        await session.execute(
            text("""
                INSERT INTO system_config (key, value, source, updated_at)
                VALUES (:key, :value, :source, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    source = EXCLUDED.source,
                    updated_at = NOW()
            """),
            {"key": key, "value": json_value, "source": source},
        )
        await session.commit()

        # Update cache
        self._cache[key] = value

        logger.info(f"Config updated: {key} = {value} (source: {source})")
        return True

    async def start_sync_loop(self, session_maker, interval_hours: float = 6.0):
        """Start periodic DB -> YAML sync loop."""

        async def sync_loop():
            while True:
                await asyncio.sleep(interval_hours * 3600)
                try:
                    async with session_maker() as session:
                        await self.sync_db_to_yaml(session)
                except Exception as e:
                    logger.error(f"Config sync failed: {e}", exc_info=True)

        self._sync_task = asyncio.create_task(sync_loop())
        logger.info(f"Config sync loop started (every {interval_hours} hours)")

    def stop_sync_loop(self):
        """Stop the sync loop."""
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
            logger.info("Config sync loop stopped")


# Singleton instance
_config_service: ConfigService | None = None


@lru_cache
def get_config_service() -> ConfigService:
    """Get the singleton ConfigService instance."""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service


# Convenience alias
config = get_config_service()
