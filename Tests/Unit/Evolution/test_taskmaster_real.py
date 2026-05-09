"""
Real integration tests for taskmaster_service.py

Tests the TaskmasterService:
- Component registration and unregistration
- Health check aggregation (healthy/degraded/critical)
- Stall detection and poke counting
- Activity log circular buffer
- Alert filtering

No DB needed — TaskmasterService is purely in-memory.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from Fast_Swarm.System.Services.taskmaster_service import (
    ComponentHealth,
    ComponentStatus,
    SystemHealthStatus,
    TaskmasterConfig,
    TaskmasterService,
)


# =============================================================================
# Component Registration Tests
# =============================================================================


class TestComponentRegistration:
    """Test registering and unregistering components."""

    def test_register_component(self):
        tm = TaskmasterService()
        tm.register_component("evo_loop", "Evolution Loop", lambda: {"status": ComponentStatus.HEALTHY})
        assert "evo_loop" in tm._components
        assert "evo_loop" in tm._component_health
        assert tm._component_health["evo_loop"].name == "Evolution Loop"

    def test_register_multiple_components(self):
        tm = TaskmasterService()
        for name in ["comp_a", "comp_b", "comp_c"]:
            tm.register_component(name, f"Component {name}", lambda: {"status": ComponentStatus.HEALTHY})
        assert len(tm._components) == 3

    def test_unregister_component(self):
        tm = TaskmasterService()
        tm.register_component("temp", "Temporary", lambda: {"status": ComponentStatus.HEALTHY})
        tm.unregister_component("temp")
        assert "temp" not in tm._components
        assert "temp" not in tm._component_health

    def test_unregister_nonexistent_is_noop(self):
        tm = TaskmasterService()
        tm.unregister_component("nonexistent")  # Should not raise

    def test_registration_logs_activity(self):
        tm = TaskmasterService()
        tm.register_component("test", "Test", lambda: {"status": ComponentStatus.HEALTHY})
        activities = tm.get_activity_summary()
        assert any(a["action"] == "registered" for a in activities)


# =============================================================================
# Health Check Tests
# =============================================================================


@pytest.mark.asyncio
class TestHealthChecks:
    """Test system health aggregation."""

    async def test_all_healthy(self):
        tm = TaskmasterService()
        tm.register_component("a", "A", lambda: {"status": ComponentStatus.HEALTHY})
        tm.register_component("b", "B", lambda: {"status": ComponentStatus.HEALTHY})

        await tm._check_all_components()
        report = await tm.check_system_health()

        assert report["status"] == "healthy"
        assert report["summary"]["healthy"] == 2
        assert report["summary"]["total_components"] == 2

    async def test_degraded_on_single_failure(self):
        tm = TaskmasterService()
        tm.register_component("ok", "OK", lambda: {"status": ComponentStatus.HEALTHY})
        tm.register_component("bad", "Bad", lambda: {"status": ComponentStatus.FAILED})

        await tm._check_all_components()
        report = await tm.check_system_health()

        assert report["status"] == "degraded"
        assert report["summary"]["failed"] == 1

    async def test_critical_on_stall(self):
        tm = TaskmasterService()
        tm.register_component("stalled", "Stalled", lambda: {"status": ComponentStatus.STALLED})

        await tm._check_all_components()
        report = await tm.check_system_health()

        assert report["status"] == "critical"
        assert report["summary"]["stalled"] == 1

    async def test_critical_on_multiple_failures(self):
        tm = TaskmasterService()
        tm.register_component("f1", "Fail1", lambda: {"status": ComponentStatus.FAILED})
        tm.register_component("f2", "Fail2", lambda: {"status": ComponentStatus.FAILED})

        await tm._check_all_components()
        report = await tm.check_system_health()

        assert report["status"] == "critical"
        assert report["summary"]["failed"] == 2

    async def test_health_check_exception_marks_failed(self):
        def broken_check():
            raise RuntimeError("check exploded")

        tm = TaskmasterService()
        tm.register_component("broken", "Broken", broken_check)

        await tm._check_all_components()
        report = await tm.check_system_health()

        assert tm._component_health["broken"].status == ComponentStatus.FAILED
        assert "check exploded" in tm._component_health["broken"].last_error

    async def test_async_health_check(self):
        async def async_check():
            return {"status": ComponentStatus.HEALTHY, "metadata": {"uptime": 3600}}

        tm = TaskmasterService()
        tm.register_component("async_comp", "Async", async_check)

        await tm._check_all_components()

        health = tm._component_health["async_comp"]
        assert health.status == ComponentStatus.HEALTHY
        assert health.metadata.get("uptime") == 3600

    async def test_last_active_at_tracked(self):
        now = datetime.utcnow()

        def check_with_active():
            return {"status": ComponentStatus.HEALTHY, "last_active_at": now}

        tm = TaskmasterService()
        tm.register_component("active", "Active", check_with_active)

        await tm._check_all_components()

        health = tm._component_health["active"]
        assert health.last_active_at == now


# =============================================================================
# Stall Detection & Poke Tests
# =============================================================================


@pytest.mark.asyncio
class TestStallDetection:
    """Test stall detection and poke escalation."""

    async def test_stalled_component_gets_poked(self):
        tm = TaskmasterService()
        tm.register_component("stalled", "Stalled", lambda: {"status": ComponentStatus.STALLED})

        await tm._check_all_components()

        health = tm._component_health["stalled"]
        assert health.poke_count == 1
        assert tm._poke_count == 1

    async def test_poke_count_increments(self):
        tm = TaskmasterService()
        tm.register_component("stalled", "Stalled", lambda: {"status": ComponentStatus.STALLED})

        # Check 3 times to trigger 3 pokes
        for _ in range(3):
            await tm._check_all_components()

        health = tm._component_health["stalled"]
        assert health.poke_count == 3

    async def test_poke_escalation_after_max_attempts(self):
        config = TaskmasterConfig(max_poke_attempts=2)
        tm = TaskmasterService(config=config)
        tm.register_component("stalled", "Stalled", lambda: {"status": ComponentStatus.STALLED})

        # First 2 checks: pokes sent
        await tm._check_all_components()
        await tm._check_all_components()
        assert tm._component_health["stalled"].poke_count == 2

        # 3rd check: escalation (no more pokes, logs critical)
        await tm._check_all_components()
        assert tm._component_health["stalled"].poke_count == 2  # No more pokes

        # Check that escalation was logged
        alerts = tm.get_alerts()
        assert any(a["level"] == "critical" and a["action"] == "escalated" for a in alerts)

    async def test_manual_poke_returns_true(self):
        tm = TaskmasterService()
        tm.register_component("comp", "Comp", lambda: {"status": ComponentStatus.STALLED})
        result = await tm.poke_stalled_component("comp")
        assert result is True

    async def test_manual_poke_nonexistent_returns_false(self):
        tm = TaskmasterService()
        result = await tm.poke_stalled_component("nonexistent")
        assert result is False


# =============================================================================
# Activity Log Tests
# =============================================================================


class TestActivityLog:
    """Test activity log circular buffer behavior."""

    def test_activity_log_records(self):
        tm = TaskmasterService()
        tm._log_activity("test", "action", "details")
        entries = tm.get_activity_summary(limit=10)
        assert len(entries) >= 1
        assert entries[0]["component_id"] == "test"
        assert entries[0]["action"] == "action"

    def test_activity_log_circular_buffer(self):
        config = TaskmasterConfig(activity_log_size=5)
        tm = TaskmasterService(config=config)

        for i in range(10):
            tm._log_activity("test", f"action_{i}", f"details_{i}")

        # Only last 5 should be kept
        assert len(tm._activity_log) == 5
        entries = tm.get_activity_summary(limit=10)
        assert len(entries) == 5

    def test_get_activity_summary_newest_first(self):
        tm = TaskmasterService()
        tm._log_activity("test", "first", "1")
        tm._log_activity("test", "second", "2")
        tm._log_activity("test", "third", "3")

        entries = tm.get_activity_summary(limit=3)
        assert entries[0]["action"] == "third"
        assert entries[2]["action"] == "first"

    def test_get_alerts_filters_by_level(self):
        tm = TaskmasterService()
        tm._log_activity("test", "info_action", "info details", level="info")
        tm._log_activity("test", "warn_action", "warning details", level="warning")
        tm._log_activity("test", "error_action", "error details", level="error")

        alerts = tm.get_alerts()
        # Should only contain warning and error
        assert all(a["level"] in ("warning", "error", "critical") for a in alerts)
        assert len(alerts) == 2


# =============================================================================
# Configuration Tests
# =============================================================================


class TestTaskmasterConfig:
    """Test configuration options."""

    def test_default_config(self):
        config = TaskmasterConfig()
        assert config.heartbeat_interval_sec == 30
        assert config.stall_threshold_sec == 300
        assert config.max_poke_attempts == 3
        assert config.activity_log_size == 100
        assert config.enabled is True

    def test_custom_config(self):
        config = TaskmasterConfig(
            heartbeat_interval_sec=10,
            stall_threshold_sec=60,
            max_poke_attempts=5,
        )
        assert config.heartbeat_interval_sec == 10
        assert config.max_poke_attempts == 5


# =============================================================================
# ComponentHealth Tests
# =============================================================================


class TestComponentHealth:
    """Test ComponentHealth dataclass."""

    def test_time_since_active_zero_when_none(self):
        health = ComponentHealth(component_id="test", name="Test")
        assert health.time_since_active == 0.0

    def test_time_since_active_positive(self):
        past = datetime.utcnow() - timedelta(seconds=60)
        health = ComponentHealth(component_id="test", name="Test", last_active_at=past)
        assert health.time_since_active >= 59.0  # Allow 1s margin

    def test_default_status_is_unknown(self):
        health = ComponentHealth(component_id="test", name="Test")
        assert health.status == ComponentStatus.UNKNOWN
