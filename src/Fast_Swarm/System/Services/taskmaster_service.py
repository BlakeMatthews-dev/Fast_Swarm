"""
TaskmasterService - Monitoring and motivational service for Fast_Swarm.

Monitors system components (background loops, orchestrator phases) and provides
health checks, manual interventions, and activity logging.

Based on WatchdogSupervisor patterns from audit_supervisor/watchdog.py.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ComponentStatus(Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALLED = "stalled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class SystemHealthStatus(Enum):
    """Overall system health."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass
class ComponentHealth:
    """Health status of a monitored component."""
    component_id: str
    name: str
    status: ComponentStatus = ComponentStatus.UNKNOWN
    last_check_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    last_error: Optional[str] = None
    poke_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def time_since_active(self) -> float:
        """Seconds since last activity."""
        if not self.last_active_at:
            return 0.0
        return (datetime.utcnow() - self.last_active_at).total_seconds()


@dataclass
class ActivityEntry:
    """Single activity log entry."""
    timestamp: datetime
    component_id: str
    action: str
    details: str
    level: str = "info"  # info, warning, error, critical


@dataclass
class TaskmasterConfig:
    """Configuration for Taskmaster monitoring."""
    heartbeat_interval_sec: int = 30
    stall_threshold_sec: int = 300  # 5 minutes
    max_poke_attempts: int = 3
    activity_log_size: int = 100
    enabled: bool = True


class TaskmasterService:
    """
    Monitors Fast_Swarm system components and provides interventions.

    Components monitored:
    - evolution_loop (via orchestrator)
    - pattern_discovery_loop (via orchestrator)
    - pattern_backtest_loop (via orchestrator)
    - window_pool_refresh_loop
    - paper_trading (if active)
    - live_trading (if active)
    """

    def __init__(self, config: Optional[TaskmasterConfig] = None):
        self.config = config or TaskmasterConfig()

        # Component registry: component_id -> (name, health_check_func)
        self._components: Dict[str, tuple[str, Callable]] = {}
        self._component_health: Dict[str, ComponentHealth] = {}

        # Activity log (circular buffer)
        self._activity_log: List[ActivityEntry] = []

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._started_at: Optional[datetime] = None
        self._check_count = 0
        self._poke_count = 0

    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================

    async def start_monitoring(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            print("[Taskmaster] Already running")
            return

        if not self.config.enabled:
            print("[Taskmaster] Disabled by config")
            return

        print("[Taskmaster] Starting monitoring...")
        self._running = True
        self._started_at = datetime.utcnow()
        self._task = asyncio.create_task(self._monitoring_loop())

        self._log_activity(
            component_id="taskmaster",
            action="started",
            details="Taskmaster monitoring started"
        )

    async def stop_monitoring(self) -> None:
        """Stop the monitoring loop gracefully."""
        if not self._running:
            return

        print("[Taskmaster] Stopping...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._log_activity(
            component_id="taskmaster",
            action="stopped",
            details=f"Taskmaster stopped after {self._check_count} checks, {self._poke_count} pokes"
        )

        print("[Taskmaster] Stopped")

    # ==========================================================================
    # COMPONENT REGISTRATION
    # ==========================================================================

    def register_component(
        self,
        component_id: str,
        name: str,
        health_check: Callable[[], Dict[str, Any]]
    ) -> None:
        """
        Register a component for monitoring.

        Args:
            component_id: Unique identifier (e.g., "evolution_loop")
            name: Human-readable name
            health_check: Async callable that returns health status dict with:
                - status: ComponentStatus
                - last_active_at: datetime (optional)
                - metadata: Dict (optional)
        """
        self._components[component_id] = (name, health_check)
        self._component_health[component_id] = ComponentHealth(
            component_id=component_id,
            name=name
        )

        print(f"[Taskmaster] Registered component: {name} ({component_id})")

        self._log_activity(
            component_id=component_id,
            action="registered",
            details=f"Component '{name}' registered for monitoring"
        )

    def unregister_component(self, component_id: str) -> None:
        """Remove a component from monitoring."""
        if component_id in self._components:
            name = self._components[component_id][0]
            del self._components[component_id]
            del self._component_health[component_id]

            self._log_activity(
                component_id=component_id,
                action="unregistered",
                details=f"Component '{name}' unregistered"
            )

    # ==========================================================================
    # MONITORING LOOP
    # ==========================================================================

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop - checks all components periodically."""
        while self._running:
            try:
                await self._check_all_components()
                self._check_count += 1

                # Wait for next interval
                try:
                    await asyncio.sleep(self.config.heartbeat_interval_sec)
                except asyncio.CancelledError:
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Taskmaster] Monitoring loop error: {e}")
                self._log_activity(
                    component_id="taskmaster",
                    action="error",
                    details=f"Monitoring loop error: {e}",
                    level="error"
                )
                await asyncio.sleep(10)

    async def _check_all_components(self) -> None:
        """Check health of all registered components."""
        for component_id, (name, health_check) in self._components.items():
            try:
                # Call health check function
                result = await health_check() if asyncio.iscoroutinefunction(health_check) else health_check()

                # Update component health
                health = self._component_health[component_id]
                health.status = result.get("status", ComponentStatus.UNKNOWN)
                health.last_check_at = datetime.utcnow()

                if "last_active_at" in result:
                    health.last_active_at = result["last_active_at"]

                if "metadata" in result:
                    health.metadata = result["metadata"]

                if "error" in result:
                    health.last_error = result["error"]

                # Check for stall
                if health.status == ComponentStatus.STALLED:
                    await self._handle_stalled_component(component_id)

            except Exception as e:
                # Health check failed
                health = self._component_health[component_id]
                health.status = ComponentStatus.FAILED
                health.last_check_at = datetime.utcnow()
                health.last_error = str(e)

                self._log_activity(
                    component_id=component_id,
                    action="health_check_failed",
                    details=f"Health check error: {e}",
                    level="error"
                )

    async def _handle_stalled_component(self, component_id: str) -> None:
        """Handle a stalled component with escalating pokes."""
        health = self._component_health[component_id]

        if health.poke_count < self.config.max_poke_attempts:
            # Poke the component
            success = await self.poke_stalled_component(component_id)
            if success:
                health.poke_count += 1
                self._poke_count += 1
        else:
            # Escalate
            self._log_activity(
                component_id=component_id,
                action="escalated",
                details=f"Component stalled after {health.poke_count} pokes",
                level="critical"
            )

    # ==========================================================================
    # HEALTH CHECKS
    # ==========================================================================

    async def check_system_health(self) -> Dict[str, Any]:
        """
        Get aggregated system health report.

        Returns:
            {
                "status": "healthy" | "degraded" | "critical",
                "components": {...},
                "summary": {...}
            }
        """
        components = {}

        # Gather component statuses
        healthy_count = 0
        degraded_count = 0
        stalled_count = 0
        failed_count = 0

        for component_id, health in self._component_health.items():
            components[component_id] = {
                "name": health.name,
                "status": health.status.value,
                "last_check_at": health.last_check_at.isoformat() if health.last_check_at else None,
                "last_active_at": health.last_active_at.isoformat() if health.last_active_at else None,
                "time_since_active": health.time_since_active,
                "poke_count": health.poke_count,
                "last_error": health.last_error,
                "metadata": health.metadata
            }

            if health.status == ComponentStatus.HEALTHY:
                healthy_count += 1
            elif health.status == ComponentStatus.DEGRADED:
                degraded_count += 1
            elif health.status == ComponentStatus.STALLED:
                stalled_count += 1
            elif health.status == ComponentStatus.FAILED:
                failed_count += 1

        # Determine overall status
        if stalled_count > 0 or failed_count > 1:
            overall_status = SystemHealthStatus.CRITICAL
        elif degraded_count > 0 or failed_count > 0:
            overall_status = SystemHealthStatus.DEGRADED
        else:
            overall_status = SystemHealthStatus.HEALTHY

        return {
            "status": overall_status.value,
            "components": components,
            "summary": {
                "total_components": len(self._components),
                "healthy": healthy_count,
                "degraded": degraded_count,
                "stalled": stalled_count,
                "failed": failed_count,
                "checks_performed": self._check_count,
                "pokes_sent": self._poke_count,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "uptime_seconds": (datetime.utcnow() - self._started_at).total_seconds() if self._started_at else 0
            }
        }

    # ==========================================================================
    # MANUAL INTERVENTIONS
    # ==========================================================================

    async def poke_stalled_component(self, component_id: str) -> bool:
        """
        Send a poke to a stalled component.

        Returns:
            True if poke was sent, False otherwise
        """
        if component_id not in self._components:
            return False

        health = self._component_health[component_id]

        self._log_activity(
            component_id=component_id,
            action="poked",
            details=f"Manual poke sent (poke #{health.poke_count + 1})",
            level="warning"
        )

        # For orchestrator components, we don't actually "poke" - just log
        # The monitoring itself will detect when they resume

        return True

    async def force_evolution_cycle(self) -> Dict[str, Any]:
        """Manually trigger an evolution cycle."""
        try:
            from Fast_Swarm.Database import async_session_maker
            from Fast_Swarm.System.Services.evolution_cycle_service import EvolutionCycleService

            async with async_session_maker() as session:
                service = EvolutionCycleService()
                result = await service.run_evolution_cycle(session)

            self._log_activity(
                component_id="evolution",
                action="manual_trigger",
                details="Evolution cycle manually triggered",
                level="info"
            )

            return {"status": "success", "result": result}

        except Exception as e:
            self._log_activity(
                component_id="evolution",
                action="manual_trigger_failed",
                details=f"Manual evolution trigger failed: {e}",
                level="error"
            )
            return {"status": "error", "error": str(e)}

    async def force_crucible_check(self) -> Dict[str, Any]:
        """Manually trigger Crucible eligibility check."""
        try:
            from Fast_Swarm.Database import async_session_maker
            from Fast_Swarm.System.Services.crucible_entry_service import CrucibleEntryService

            async with async_session_maker() as session:
                service = CrucibleEntryService()
                result = await service.check_all_eligible(session)

            self._log_activity(
                component_id="crucible",
                action="manual_check",
                details=f"Crucible check manually triggered: {result.get('agents_retired', 0)} retired",
                level="info"
            )

            return {"status": "success", "result": result}

        except Exception as e:
            self._log_activity(
                component_id="crucible",
                action="manual_check_failed",
                details=f"Manual Crucible check failed: {e}",
                level="error"
            )
            return {"status": "error", "error": str(e)}

    # ==========================================================================
    # ACTIVITY LOG
    # ==========================================================================

    def _log_activity(
        self,
        component_id: str,
        action: str,
        details: str,
        level: str = "info"
    ) -> None:
        """Add entry to activity log (circular buffer)."""
        entry = ActivityEntry(
            timestamp=datetime.utcnow(),
            component_id=component_id,
            action=action,
            details=details,
            level=level
        )

        self._activity_log.append(entry)

        # Keep only last N entries
        if len(self._activity_log) > self.config.activity_log_size:
            self._activity_log = self._activity_log[-self.config.activity_log_size:]

    def get_activity_summary(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent activity log entries."""
        recent = self._activity_log[-limit:] if limit > 0 else self._activity_log

        return [
            {
                "timestamp": entry.timestamp.isoformat(),
                "component_id": entry.component_id,
                "action": entry.action,
                "details": entry.details,
                "level": entry.level
            }
            for entry in reversed(recent)  # Newest first
        ]

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts (warnings and errors)."""
        # Return recent warnings/errors/critical entries
        alerts = [
            {
                "timestamp": entry.timestamp.isoformat(),
                "component_id": entry.component_id,
                "action": entry.action,
                "details": entry.details,
                "level": entry.level
            }
            for entry in reversed(self._activity_log)
            if entry.level in ("warning", "error", "critical")
        ]

        return alerts[:10]  # Last 10 alerts


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_taskmaster_instance: Optional[TaskmasterService] = None


def get_taskmaster() -> TaskmasterService:
    """Get or create the global Taskmaster instance."""
    global _taskmaster_instance
    if _taskmaster_instance is None:
        _taskmaster_instance = TaskmasterService()
    return _taskmaster_instance
