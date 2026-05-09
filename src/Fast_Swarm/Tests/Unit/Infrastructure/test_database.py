"""
Tests for Fast_Swarm.Database module.

Validates connection-string construction, engine/session factory behavior,
pool settings, and error handling.  All tests use mocks -- no real DB needed.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# We must reset the module-level globals between tests so each test gets
# a fresh engine/session factory.  Import the module for patching.
# ---------------------------------------------------------------------------

MODULE = "Fast_Swarm.Database"


def _reset_db_globals():
    """Reset the lazy-init globals in the Database module."""
    import Fast_Swarm.Database as db_mod

    db_mod._engine = None
    db_mod._sync_engine = None
    db_mod._async_session_maker = None
    db_mod._sync_session_maker = None


@pytest.fixture(autouse=True)
def _clean_db_globals():
    """Ensure each test starts with fresh DB globals."""
    _reset_db_globals()
    yield
    _reset_db_globals()


# =========================================================================
# Connection String Construction
# =========================================================================


class TestConnectionString:
    """Verify that DATABASE_URL is built correctly from env vars."""

    def test_default_url_format(self):
        """Default URL uses psycopg driver with default creds."""
        import Fast_Swarm.Database as db_mod

        url = db_mod.DATABASE_URL
        assert "postgresql+psycopg://" in url
        assert "coinswarm" in url  # default user or password

    def test_url_contains_host_and_port(self):
        """URL includes POSTGRES_HOST and POSTGRES_PORT."""
        import Fast_Swarm.Database as db_mod

        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        assert f"@{host}:{port}/" in db_mod.DATABASE_URL

    def test_sync_url_matches_format(self):
        """Sync URL should also use postgresql+psycopg driver."""
        import Fast_Swarm.Database as db_mod

        assert "postgresql+psycopg://" in db_mod.SYNC_DATABASE_URL


# =========================================================================
# Engine Factory
# =========================================================================


class TestEngineFactory:
    """Verify async and sync engine creation and caching."""

    @patch(f"{MODULE}.create_async_engine")
    def test_get_async_engine_creates_once(self, mock_create):
        """get_async_engine should only call create_async_engine once (lazy singleton)."""
        import Fast_Swarm.Database as db_mod

        mock_engine = MagicMock()
        mock_create.return_value = mock_engine

        e1 = db_mod.get_async_engine()
        e2 = db_mod.get_async_engine()

        assert e1 is e2
        mock_create.assert_called_once()

    @patch(f"{MODULE}.create_async_engine")
    def test_async_engine_pool_settings(self, mock_create):
        """Async engine should be created with expected pool settings."""
        import Fast_Swarm.Database as db_mod

        db_mod.get_async_engine()

        _, kwargs = mock_create.call_args
        assert kwargs["pool_size"] == 20
        assert kwargs["max_overflow"] == 30
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_recycle"] == 3600
        assert kwargs["pool_timeout"] == 10

    @patch(f"{MODULE}.create_engine")
    def test_get_sync_engine_creates_once(self, mock_create):
        """get_sync_engine_instance should only call create_engine once."""
        import Fast_Swarm.Database as db_mod

        mock_engine = MagicMock()
        mock_create.return_value = mock_engine

        e1 = db_mod.get_sync_engine_instance()
        e2 = db_mod.get_sync_engine_instance()

        assert e1 is e2
        mock_create.assert_called_once()

    @patch(f"{MODULE}.create_engine")
    def test_sync_engine_pool_settings(self, mock_create):
        """Sync engine should be created with expected pool settings."""
        import Fast_Swarm.Database as db_mod

        db_mod.get_sync_engine_instance()

        _, kwargs = mock_create.call_args
        assert kwargs["pool_size"] == 10
        assert kwargs["max_overflow"] == 20
        assert kwargs["pool_pre_ping"] is True


# =========================================================================
# Session Factory
# =========================================================================


class TestSessionFactory:
    """Verify session makers return usable session objects."""

    @patch(f"{MODULE}.create_async_engine")
    @patch(f"{MODULE}.sessionmaker")
    def test_async_session_maker_returns_session(self, mock_sm, mock_engine):
        """async_session_maker should return a session instance."""
        import Fast_Swarm.Database as db_mod

        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_sm.return_value = mock_factory

        session = db_mod.async_session_maker()
        assert session is mock_session

    @patch(f"{MODULE}.create_engine")
    @patch(f"{MODULE}.sessionmaker")
    def test_sync_session_maker_returns_session(self, mock_sm, mock_engine):
        """sync_session_maker should return a session instance."""
        import Fast_Swarm.Database as db_mod

        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_sm.return_value = mock_factory

        session = db_mod.sync_session_maker()
        assert session is mock_session


# =========================================================================
# get_sync_session Context Manager
# =========================================================================


class TestSyncSessionContextManager:
    """Verify the get_sync_session context manager behavior."""

    @patch(f"{MODULE}.sync_session_maker")
    def test_commits_on_success(self, mock_maker):
        """Session should be committed on clean exit."""
        import Fast_Swarm.Database as db_mod

        mock_session = MagicMock()
        mock_maker.return_value = mock_session

        with db_mod.get_sync_session() as session:
            pass  # No error

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch(f"{MODULE}.sync_session_maker")
    def test_rollback_on_error(self, mock_maker):
        """Session should be rolled back on exception."""
        import Fast_Swarm.Database as db_mod

        mock_session = MagicMock()
        mock_maker.return_value = mock_session

        with pytest.raises(ValueError):
            with db_mod.get_sync_session() as session:
                raise ValueError("boom")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
