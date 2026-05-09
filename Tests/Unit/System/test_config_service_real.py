"""
Real integration tests for ConfigService (config_service.py)

Tests YAML loading/saving, database sync, cache behavior, get/set operations,
and section queries against a real PostgreSQL test database.

Uses db_session fixture from conftest.py for database tests.

Key behavior of _flatten_dict / _is_leaf_dict:
  - A dict whose values are ALL non-dict (scalars, lists, etc.) is a "leaf dict"
    and is NOT flattened further. It is kept as a single value.
  - Only dicts containing nested dicts are recursed into.
  - Example: {"a": {"b": 1}} flattens to {"a": {"b": 1}} (leaf dict kept as value)
  - Example: {"a": {"sub": {"x": 1}}} flattens to {"a.sub": {"x": 1}}

The value column in system_config must be TEXT (not JSONB) because the service
does json.dumps() on write and json.loads() on read. JSONB + asyncpg would
auto-deserialize, breaking json.loads().
"""

import json
import os
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from Fast_Swarm.Config.config_service import ConfigService, get_config_service


# ============================================================================
# HELPERS
# ============================================================================


def _make_config_service(yaml_path: Path | None = None) -> ConfigService:
    """Create a fresh ConfigService instance (not the singleton)."""
    svc = ConfigService()
    return svc


async def _create_system_config_table(session: AsyncSession) -> None:
    """Ensure system_config table exists in the test database.

    Uses TEXT for the value column (not JSONB) because the service code
    does json.dumps() before INSERT and json.loads() on SELECT.
    With JSONB + asyncpg, values are auto-deserialized, which breaks json.loads().

    Drops and recreates to ensure correct column types across test runs.
    """
    await session.execute(text("DROP TABLE IF EXISTS system_config"))
    await session.execute(text("""
        CREATE TABLE system_config (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL,
            source VARCHAR(20) DEFAULT 'yaml',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await session.commit()


async def _insert_config_row(session: AsyncSession, key: str, value, source: str = "yaml") -> None:
    """Insert a config row directly."""
    json_value = json.dumps(value)
    await session.execute(
        text("""
            INSERT INTO system_config (key, value, source, updated_at)
            VALUES (:key, :value, :source, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source
        """),
        {"key": key, "value": json_value, "source": source},
    )
    await session.commit()


def _patch_yaml_path(yaml_path: Path):
    """Context manager to temporarily patch the module-level YAML_PATH."""
    import Fast_Swarm.Config.config_service as cs_module
    original_path = cs_module.YAML_PATH
    cs_module.YAML_PATH = yaml_path

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            cs_module.YAML_PATH = original_path

    return _Ctx()


# ============================================================================
# YAML OPERATIONS (no DB needed)
# ============================================================================


class TestYamlOperations:
    """Tests for YAML file load/save (pure file I/O).

    Note: _flatten_dict treats dicts with only simple values as "leaf dicts"
    and keeps them as single values rather than flattening further.
    So {"evolution": {"population_size": 500}} stays as key="evolution",
    value={"population_size": 500}.
    """

    def test_load_yaml_returns_flat_dict(self):
        """Loading a YAML file should return a flattened dict.

        Because _is_leaf_dict returns True for dicts with only scalar values,
        top-level sections with simple values become leaf dicts.
        """
        yaml_content = """
evolution:
  population_size: 500
  mutation_rate: 0.15
backtest:
  min_trades_for_regime: 5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                flat = svc.load_yaml()

            # These are leaf dicts (all values are scalars), so they stay as dict values
            assert flat["evolution"] == {"population_size": 500, "mutation_rate": 0.15}
            assert flat["backtest"] == {"min_trades_for_regime": 5}
        finally:
            os.unlink(yaml_path)

    def test_load_yaml_missing_file(self):
        """Loading a missing YAML file should return empty dict."""
        svc = _make_config_service()
        with _patch_yaml_path(Path("/tmp/nonexistent_config_test.yaml")):
            result = svc.load_yaml()
            assert result == {}

    def test_save_and_reload_yaml(self):
        """Saving a flat dict and reloading should produce the same values."""
        svc = _make_config_service()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_path = Path(f.name)

        try:
            with _patch_yaml_path(yaml_path):
                # Use keys that match the actual flatten behavior:
                # save_yaml unflattens, then load_yaml re-flattens.
                # "evolution.population_size" unflattens to {"evolution": {"population_size": 600}}
                # which re-flattens to {"evolution": {"population_size": 600}} (leaf dict).
                flat_config = {
                    "evolution.population_size": 600,
                    "evolution.elite_percent": 0.25,
                    "backtest.windows_per_asset_per_tf": 30,
                }
                svc.save_yaml(flat_config)

                reloaded = svc.load_yaml()
                # After unflatten -> YAML -> flatten, leaf dicts are grouped
                assert reloaded["evolution"] == {"population_size": 600, "elite_percent": 0.25}
                assert reloaded["backtest"] == {"windows_per_asset_per_tf": 30}
        finally:
            os.unlink(yaml_path)

    def test_load_yaml_with_lists(self):
        """YAML lists should be preserved as leaf values."""
        yaml_content = """
evolution:
  assets:
    - BTC
    - ETH
    - SOL
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                flat = svc.load_yaml()

            # {"evolution": {"assets": [...]}} is a leaf dict (list is not a dict)
            assert flat["evolution"] == {"assets": ["BTC", "ETH", "SOL"]}
        finally:
            os.unlink(yaml_path)

    def test_load_yaml_with_nested_leaf_dicts(self):
        """Leaf dicts (timeframe_config entries) should be preserved as values."""
        yaml_content = """
backtest:
  timeframe_config:
    1m:
      candles: 1440
    1h:
      candles: 720
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                flat = svc.load_yaml()

            # timeframe_config contains nested dicts (1m, 1h), so it's NOT a leaf.
            # But 1m and 1h contain only scalars, so they ARE leaves.
            assert flat["backtest.timeframe_config.1m"] == {"candles": 1440}
            assert flat["backtest.timeframe_config.1h"] == {"candles": 720}
        finally:
            os.unlink(yaml_path)

    def test_load_yaml_deeply_nested(self):
        """Deeply nested structure should flatten only non-leaf levels."""
        yaml_content = """
level1:
  level2:
    level3:
      key: value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                flat = svc.load_yaml()

            # level1.level2 contains a dict (level3), so it recurses.
            # level3 is {"key": "value"} — leaf dict.
            assert flat["level1.level2.level3"] == {"key": "value"}
        finally:
            os.unlink(yaml_path)


# ============================================================================
# FLATTEN / UNFLATTEN
# ============================================================================


class TestFlattenUnflatten:
    """Tests for dict flatten/unflatten logic."""

    def test_flatten_leaf_dict(self):
        """A dict whose values are all scalars is a leaf and is NOT flattened."""
        svc = _make_config_service()
        nested = {"a": {"b": 1, "c": 2}, "d": 3}
        flat = svc._flatten_dict(nested)
        # {"b": 1, "c": 2} is a leaf dict — kept as a value under key "a"
        assert flat == {"a": {"b": 1, "c": 2}, "d": 3}

    def test_flatten_nested_dicts(self):
        """A dict containing nested dicts IS flattened."""
        svc = _make_config_service()
        nested = {"a": {"sub": {"x": 1}, "other": {"y": 2}}}
        flat = svc._flatten_dict(nested)
        # "sub" and "other" are leaf dicts
        assert flat == {"a.sub": {"x": 1}, "a.other": {"y": 2}}

    def test_unflatten_simple(self):
        svc = _make_config_service()
        flat = {"a.b": 1, "a.c": 2, "d": 3}
        nested = svc._unflatten_dict(flat)
        assert nested == {"a": {"b": 1, "c": 2}, "d": 3}

    def test_roundtrip_flatten_unflatten(self):
        """Flatten then unflatten should produce the original structure."""
        svc = _make_config_service()
        original = {
            "evolution": {"population_size": 500, "mutation_rate": 0.15},
            "backtest": {"min_trades": 5},
        }
        flat = svc._flatten_dict(original)
        restored = svc._unflatten_dict(flat)
        assert restored == original

    def test_is_leaf_dict_empty(self):
        """Empty dict should be considered a leaf."""
        svc = _make_config_service()
        assert svc._is_leaf_dict({}) is True

    def test_is_leaf_dict_simple_values(self):
        """Dict with simple (non-dict) values should be a leaf."""
        svc = _make_config_service()
        assert svc._is_leaf_dict({"candles": 720}) is True

    def test_is_leaf_dict_nested(self):
        """Dict with nested dict values should NOT be a leaf."""
        svc = _make_config_service()
        assert svc._is_leaf_dict({"sub": {"val": 1}}) is False


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================


@pytest.mark.requires_db
class TestLoadYamlToDb:
    """Tests for YAML -> DB loading."""

    @pytest.mark.asyncio
    async def test_load_yaml_to_db(self, db_session: AsyncSession):
        """Should insert all YAML keys into system_config table."""
        await _create_system_config_table(db_session)

        # Use a structure with nested dicts so flatten produces dot-notation keys
        yaml_content = """
outer:
  section_a:
    key_a: 100
  section_b:
    key_b: hello
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                loaded = await svc.load_yaml_to_db(db_session)

            assert loaded == 2

            # Verify rows in DB
            result = await db_session.execute(text("SELECT key, value, source FROM system_config ORDER BY key"))
            rows = result.fetchall()
            assert len(rows) == 2
            assert rows[0][0] == "outer.section_a"
            assert json.loads(rows[0][1]) == {"key_a": 100}
            assert rows[0][2] == "yaml"
            assert rows[1][0] == "outer.section_b"
            assert json.loads(rows[1][1]) == {"key_b": "hello"}
        finally:
            os.unlink(yaml_path)

    @pytest.mark.asyncio
    async def test_load_yaml_to_db_simple_section(self, db_session: AsyncSession):
        """A simple section (leaf dict) should be stored as a single key with dict value."""
        await _create_system_config_table(db_session)

        yaml_content = """
test_section:
  key_a: 100
  key_b: hello
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                loaded = await svc.load_yaml_to_db(db_session)

            # Leaf dict: one key "test_section" with value {"key_a": 100, "key_b": "hello"}
            assert loaded == 1

            result = await db_session.execute(text("SELECT key, value FROM system_config"))
            row = result.fetchone()
            assert row[0] == "test_section"
            assert json.loads(row[1]) == {"key_a": 100, "key_b": "hello"}
        finally:
            os.unlink(yaml_path)

    @pytest.mark.asyncio
    async def test_load_yaml_to_db_upserts(self, db_session: AsyncSession):
        """Loading YAML should overwrite existing DB values (YAML is source of truth)."""
        await _create_system_config_table(db_session)

        # Insert a pre-existing value
        await _insert_config_row(db_session, "test_section", {"key_a": 999}, "api")

        yaml_content = """
test_section:
  key_a: 100
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                await svc.load_yaml_to_db(db_session)

            result = await db_session.execute(
                text("SELECT value, source FROM system_config WHERE key = 'test_section'")
            )
            row = result.fetchone()
            assert json.loads(row[0]) == {"key_a": 100}  # YAML value wins
            assert row[1] == "yaml"
        finally:
            os.unlink(yaml_path)

    @pytest.mark.asyncio
    async def test_load_yaml_refreshes_cache(self, db_session: AsyncSession):
        """Loading YAML to DB should refresh the in-memory cache."""
        await _create_system_config_table(db_session)

        yaml_content = """
cache_test:
  value: 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = Path(f.name)

        try:
            svc = _make_config_service()
            with _patch_yaml_path(yaml_path):
                await svc.load_yaml_to_db(db_session)

            assert svc._cache_loaded is True
            # Leaf dict: {"cache_test": {"value": 42}}
            assert svc._cache["cache_test"] == {"value": 42}
        finally:
            os.unlink(yaml_path)


@pytest.mark.requires_db
class TestGetSet:
    """Tests for get/set config operations."""

    @pytest.mark.asyncio
    async def test_get_from_cache(self, db_session: AsyncSession):
        """Get should return cached value without DB query when cache is loaded."""
        svc = _make_config_service()
        svc._cache = {"test.key": "cached_value"}
        svc._cache_loaded = True

        value = await svc.get("test.key", session=db_session)
        assert value == "cached_value"

    @pytest.mark.asyncio
    async def test_get_from_db(self, db_session: AsyncSession):
        """Get should query DB when key not in cache."""
        await _create_system_config_table(db_session)
        await _insert_config_row(db_session, "db.key", "db_value")

        svc = _make_config_service()
        # Cache not loaded, so should fall through to DB
        value = await svc.get("db.key", session=db_session)
        assert value == "db_value"

    @pytest.mark.asyncio
    async def test_get_default(self, db_session: AsyncSession):
        """Get should return default when key not found."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        value = await svc.get("nonexistent.key", default=42, session=db_session)
        assert value == 42

    @pytest.mark.asyncio
    async def test_get_no_session_returns_cache_or_default(self):
        """Get without session should return cache value or default."""
        svc = _make_config_service()
        svc._cache = {"cached.key": 99}

        value = await svc.get("cached.key")
        assert value == 99

        value = await svc.get("missing.key", default=0)
        assert value == 0

    @pytest.mark.asyncio
    async def test_set_persists_to_db(self, db_session: AsyncSession):
        """Set should write value to database."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        result = await svc.set("new.key", 123, source="api", session=db_session)
        assert result is True

        # Verify in DB
        row = await db_session.execute(
            text("SELECT value, source FROM system_config WHERE key = 'new.key'")
        )
        db_row = row.fetchone()
        assert json.loads(db_row[0]) == 123
        assert db_row[1] == "api"

    @pytest.mark.asyncio
    async def test_set_updates_cache(self, db_session: AsyncSession):
        """Set should update the in-memory cache."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        await svc.set("cache.update", "new_val", session=db_session)
        assert svc._cache["cache.update"] == "new_val"

    @pytest.mark.asyncio
    async def test_set_without_session_only_caches(self):
        """Set without session should update cache but return False."""
        svc = _make_config_service()
        result = await svc.set("no_session.key", 42)
        assert result is False
        assert svc._cache["no_session.key"] == 42

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self, db_session: AsyncSession):
        """Set should overwrite an existing key."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        await svc.set("overwrite.key", "first", session=db_session)
        await svc.set("overwrite.key", "second", session=db_session)

        value = await svc.get("overwrite.key", session=db_session)
        assert value == "second"

    @pytest.mark.asyncio
    async def test_set_complex_value(self, db_session: AsyncSession):
        """Set should handle complex JSON-serializable values."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        complex_val = {"nested": {"list": [1, 2, 3], "flag": True}}
        await svc.set("complex.key", complex_val, session=db_session)

        retrieved = await svc.get("complex.key", session=db_session)
        assert retrieved == complex_val


@pytest.mark.requires_db
class TestGetSection:
    """Tests for section-based config queries."""

    @pytest.mark.asyncio
    async def test_get_section_from_cache(self):
        """get_section should filter cached keys by prefix."""
        svc = _make_config_service()
        svc._cache = {
            "evolution.population_size": 500,
            "evolution.mutation_rate": 0.15,
            "backtest.min_trades": 5,
        }
        svc._cache_loaded = True

        section = await svc.get_section("evolution")
        assert len(section) == 2
        assert section["evolution.population_size"] == 500
        assert section["evolution.mutation_rate"] == 0.15
        assert "backtest.min_trades" not in section

    @pytest.mark.asyncio
    async def test_get_section_from_db(self, db_session: AsyncSession):
        """get_section should query DB when cache not loaded."""
        await _create_system_config_table(db_session)
        await _insert_config_row(db_session, "section.a", 1)
        await _insert_config_row(db_session, "section.b", 2)
        await _insert_config_row(db_session, "other.c", 3)

        svc = _make_config_service()  # fresh, cache not loaded
        section = await svc.get_section("section", session=db_session)
        assert len(section) == 2
        assert section["section.a"] == 1
        assert section["section.b"] == 2

    @pytest.mark.asyncio
    async def test_get_section_empty(self, db_session: AsyncSession):
        """get_section for a non-existent prefix should return empty dict."""
        await _create_system_config_table(db_session)

        svc = _make_config_service()
        section = await svc.get_section("nonexistent", session=db_session)
        assert section == {}

    @pytest.mark.asyncio
    async def test_get_section_no_session_no_cache(self):
        """get_section without session and no cache should return empty dict."""
        svc = _make_config_service()
        section = await svc.get_section("anything")
        assert section == {}


@pytest.mark.requires_db
class TestSyncDbToYaml:
    """Tests for DB -> YAML sync."""

    @pytest.mark.asyncio
    async def test_sync_captures_api_changes(self, db_session: AsyncSession):
        """Sync should write API-sourced changes back to YAML."""
        await _create_system_config_table(db_session)
        await _insert_config_row(db_session, "sync.yaml_key", 10, "yaml")
        await _insert_config_row(db_session, "sync.api_key", 20, "api")

        svc = _make_config_service()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_path = Path(f.name)

        try:
            with _patch_yaml_path(yaml_path):
                api_changes = await svc.sync_db_to_yaml(db_session)

            assert api_changes == 1

            # After sync, api sources should be marked as yaml
            result = await db_session.execute(
                text("SELECT source FROM system_config WHERE key = 'sync.api_key'")
            )
            row = result.fetchone()
            assert row[0] == "yaml"
        finally:
            if yaml_path.exists():
                os.unlink(yaml_path)

    @pytest.mark.asyncio
    async def test_sync_no_api_changes_skips_write(self, db_session: AsyncSession):
        """Sync with no API changes should not write YAML file."""
        await _create_system_config_table(db_session)
        await _insert_config_row(db_session, "sync.only_yaml", 10, "yaml")

        svc = _make_config_service()

        # Use a path that doesn't exist - if sync tries to write, it will create it
        yaml_path = Path(tempfile.mktemp(suffix=".yaml"))
        try:
            with _patch_yaml_path(yaml_path):
                api_changes = await svc.sync_db_to_yaml(db_session)

            assert api_changes == 0
            # File should NOT have been created
            assert not yaml_path.exists()
        finally:
            if yaml_path.exists():
                os.unlink(yaml_path)

    @pytest.mark.asyncio
    async def test_sync_refreshes_cache(self, db_session: AsyncSession):
        """Sync should refresh the in-memory cache from DB."""
        await _create_system_config_table(db_session)
        await _insert_config_row(db_session, "cache.refresh", 77, "yaml")

        svc = _make_config_service()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_path = Path(f.name)

        try:
            with _patch_yaml_path(yaml_path):
                await svc.sync_db_to_yaml(db_session)

            assert svc._cache_loaded is True
            assert svc._cache["cache.refresh"] == 77
        finally:
            if yaml_path.exists():
                os.unlink(yaml_path)


# ============================================================================
# SINGLETON / get_config_service
# ============================================================================


class TestSingleton:
    """Tests for the singleton pattern."""

    def test_get_config_service_returns_same_instance(self):
        """get_config_service should return the same instance every time."""
        # Note: lru_cache means this is always the same object
        svc1 = get_config_service()
        svc2 = get_config_service()
        assert svc1 is svc2

    def test_config_service_has_empty_cache_initially(self):
        """A fresh ConfigService should have empty cache."""
        svc = ConfigService()
        assert svc._cache == {}
        assert svc._cache_loaded is False
        assert svc._sync_task is None


# ============================================================================
# SYNC LOOP LIFECYCLE
# ============================================================================


class TestSyncLoopLifecycle:
    """Tests for start/stop sync loop."""

    def test_stop_sync_loop_when_not_running(self):
        """Stopping sync loop when not started should be a no-op."""
        svc = _make_config_service()
        svc.stop_sync_loop()  # should not raise
        assert svc._sync_task is None

    @pytest.mark.asyncio
    async def test_start_and_stop_sync_loop(self):
        """Starting and stopping the sync loop should manage the task."""
        from unittest.mock import AsyncMock, MagicMock

        svc = _make_config_service()
        mock_session_maker = MagicMock()

        await svc.start_sync_loop(mock_session_maker, interval_hours=0.001)
        assert svc._sync_task is not None
        assert not svc._sync_task.done()

        svc.stop_sync_loop()
        assert svc._sync_task is None
