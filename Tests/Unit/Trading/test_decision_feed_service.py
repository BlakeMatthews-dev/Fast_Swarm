"""
Decision Feed Service Unit Tests.

Tests for the in-memory ring buffer with async pub/sub.
Source: src/Fast_Swarm/Trading/Services/decision_feed_service.py
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from Fast_Swarm.Trading.Services.decision_feed_service import (
    DecisionEvent,
    DecisionFeedService,
    get_decision_feed_service,
)


# ============================================================================
# HELPERS
# ============================================================================


def make_event(agent_id="agent-1", event_type="pattern_eval", **kwargs):
    """Create a test DecisionEvent with sensible defaults."""
    return DecisionEvent(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_id=agent_id,
        agent_name=f"Agent {agent_id}",
        symbol="BTC/USDT",
        timeframe="1h",
        event_type=event_type,
        **kwargs,
    )


# ============================================================================
# EMIT + GET_RECENT
# ============================================================================


class TestEmitAndGetRecent:
    """CONTRACT: emit stores events and get_recent retrieves them."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_emit_single_event_appears_in_recent(self):
        """Emit one event, get_recent returns it as a dict."""
        svc = DecisionFeedService(max_events=100)
        evt = make_event()
        await svc.emit(evt)

        recent = svc.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["event_id"] == evt.event_id
        assert recent[0]["agent_id"] == "agent-1"
        assert recent[0]["symbol"] == "BTC/USDT"

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_emit_multiple_events_returns_all(self):
        """Emit several events, all appear in get_recent."""
        svc = DecisionFeedService(max_events=100)
        events = [make_event(agent_id=f"a-{i}") for i in range(5)]
        for e in events:
            await svc.emit(e)

        recent = svc.get_recent(limit=50)
        assert len(recent) == 5
        returned_ids = {r["event_id"] for r in recent}
        assert returned_ids == {e.event_id for e in events}

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_recent_limit_caps_output(self):
        """get_recent(limit=N) returns at most N events."""
        svc = DecisionFeedService(max_events=100)
        for _ in range(20):
            await svc.emit(make_event())

        recent = svc.get_recent(limit=5)
        assert len(recent) == 5

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_recent_returns_dicts_not_dataclasses(self):
        """get_recent returns plain dicts (via asdict)."""
        svc = DecisionFeedService(max_events=100)
        await svc.emit(make_event())

        recent = svc.get_recent(limit=1)
        assert isinstance(recent[0], dict)
        assert "event_id" in recent[0]
        assert "patterns_evaluated" in recent[0]

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_recent_empty_buffer(self):
        """get_recent on empty buffer returns empty list."""
        svc = DecisionFeedService(max_events=100)
        assert svc.get_recent() == []


# ============================================================================
# RING BUFFER OVERFLOW
# ============================================================================


class TestRingBufferOverflow:
    """CONTRACT: Ring buffer discards oldest events when full."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_overflow_keeps_max_events(self):
        """Emit 600 events with max=500, only 500 remain."""
        svc = DecisionFeedService(max_events=500)
        all_events = []
        for i in range(600):
            evt = make_event(agent_id=f"a-{i}")
            all_events.append(evt)
            await svc.emit(evt)

        recent = svc.get_recent(limit=1000)
        assert len(recent) == 500

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_overflow_drops_oldest(self):
        """After overflow, oldest events are gone and newest remain."""
        svc = DecisionFeedService(max_events=500)
        all_events = []
        for i in range(600):
            evt = make_event(agent_id=f"a-{i}")
            all_events.append(evt)
            await svc.emit(evt)

        recent = svc.get_recent(limit=1000)
        recent_ids = {r["event_id"] for r in recent}

        # First 100 events should be gone
        for evt in all_events[:100]:
            assert evt.event_id not in recent_ids

        # Last 500 events should be present
        for evt in all_events[100:]:
            assert evt.event_id in recent_ids


# ============================================================================
# FIFO ORDER PRESERVATION
# ============================================================================


class TestFIFOOrder:
    """CONTRACT: Events maintain insertion order."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_recent_preserves_insertion_order(self):
        """Events come back in the order they were emitted."""
        svc = DecisionFeedService(max_events=100)
        ids = []
        for i in range(10):
            evt = make_event(agent_id=f"ordered-{i}")
            ids.append(evt.event_id)
            await svc.emit(evt)

        recent = svc.get_recent(limit=100)
        returned_ids = [r["event_id"] for r in recent]
        assert returned_ids == ids

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_get_recent_limit_returns_tail(self):
        """get_recent(limit=3) returns the last 3 events, in order."""
        svc = DecisionFeedService(max_events=100)
        ids = []
        for i in range(10):
            evt = make_event(agent_id=f"ordered-{i}")
            ids.append(evt.event_id)
            await svc.emit(evt)

        recent = svc.get_recent(limit=3)
        returned_ids = [r["event_id"] for r in recent]
        assert returned_ids == ids[-3:]


# ============================================================================
# AGENT FILTERING
# ============================================================================


class TestAgentFiltering:
    """CONTRACT: get_recent filters by agent_id when provided."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_filter_by_agent_id(self):
        """Only events from specified agent are returned."""
        svc = DecisionFeedService(max_events=100)
        for i in range(5):
            await svc.emit(make_event(agent_id="alice"))
        for i in range(3):
            await svc.emit(make_event(agent_id="bob"))

        alice_events = svc.get_recent(limit=100, agent_id="alice")
        assert len(alice_events) == 5
        assert all(e["agent_id"] == "alice" for e in alice_events)

        bob_events = svc.get_recent(limit=100, agent_id="bob")
        assert len(bob_events) == 3
        assert all(e["agent_id"] == "bob" for e in bob_events)

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_filter_nonexistent_agent_returns_empty(self):
        """Filtering by unknown agent returns empty list."""
        svc = DecisionFeedService(max_events=100)
        await svc.emit(make_event(agent_id="alice"))

        result = svc.get_recent(limit=100, agent_id="unknown")
        assert result == []

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_filter_with_limit(self):
        """Agent filter + limit work together."""
        svc = DecisionFeedService(max_events=100)
        for i in range(10):
            await svc.emit(make_event(agent_id="alice"))

        result = svc.get_recent(limit=3, agent_id="alice")
        assert len(result) == 3

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_no_filter_returns_all_agents(self):
        """Without agent_id filter, all agents' events appear."""
        svc = DecisionFeedService(max_events=100)
        await svc.emit(make_event(agent_id="alice"))
        await svc.emit(make_event(agent_id="bob"))
        await svc.emit(make_event(agent_id="charlie"))

        result = svc.get_recent(limit=100)
        agents = {e["agent_id"] for e in result}
        assert agents == {"alice", "bob", "charlie"}


# ============================================================================
# SUBSCRIBER RECEIVES EVENTS
# ============================================================================


class TestSubscriberReceivesEvents:
    """CONTRACT: Subscribers get emitted events via async queue."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_subscriber_receives_event(self):
        """A subscriber queue receives emitted events."""
        svc = DecisionFeedService(max_events=100)
        q = await svc.subscribe()

        evt = make_event()
        await svc.emit(evt)

        received = q.get_nowait()
        assert received.event_id == evt.event_id

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self):
        """All subscribers receive the same event."""
        svc = DecisionFeedService(max_events=100)
        q1 = await svc.subscribe()
        q2 = await svc.subscribe()

        evt = make_event()
        await svc.emit(evt)

        r1 = q1.get_nowait()
        r2 = q2.get_nowait()
        assert r1.event_id == evt.event_id
        assert r2.event_id == evt.event_id

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_subscriber_receives_multiple_events_in_order(self):
        """Subscriber receives events in emission order."""
        svc = DecisionFeedService(max_events=100)
        q = await svc.subscribe()

        ids = []
        for _ in range(5):
            evt = make_event()
            ids.append(evt.event_id)
            await svc.emit(evt)

        received_ids = [q.get_nowait().event_id for _ in range(5)]
        assert received_ids == ids

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_late_subscriber_misses_prior_events(self):
        """A subscriber added after emit doesn't get old events."""
        svc = DecisionFeedService(max_events=100)
        await svc.emit(make_event())

        q = await svc.subscribe()
        assert q.empty()


# ============================================================================
# DEAD SUBSCRIBER (QUEUE FULL) REMOVAL
# ============================================================================


class TestDeadSubscriberRemoval:
    """CONTRACT: Subscribers whose queues are full get auto-removed."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_dead_subscriber_removed_on_queue_full(self):
        """When a subscriber queue is full, it's removed from the list."""
        svc = DecisionFeedService(max_events=500)
        q = await svc.subscribe()

        # Queue maxsize is 100; fill it up, then one more should trigger removal
        for i in range(100):
            await svc.emit(make_event(agent_id=f"fill-{i}"))

        # Queue should be full now
        assert q.full()

        # This emit should cause QueueFull -> dead subscriber removal
        await svc.emit(make_event(agent_id="overflow"))

        assert q not in svc._subscribers

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_healthy_subscriber_survives_dead_removal(self):
        """A healthy subscriber is kept when a dead one is removed."""
        svc = DecisionFeedService(max_events=500)

        # dead_q will fill up and get removed
        dead_q = await svc.subscribe()

        # Fill the dead subscriber's queue (maxsize=100)
        for i in range(100):
            await svc.emit(make_event(agent_id=f"fill-{i}"))

        # Now add a healthy subscriber that hasn't received the old events
        healthy_q = await svc.subscribe()

        # This emit triggers dead removal but healthy_q should survive
        await svc.emit(make_event(agent_id="trigger"))

        assert dead_q not in svc._subscribers
        assert healthy_q in svc._subscribers

        # Healthy subscriber got the trigger event
        received = healthy_q.get_nowait()
        assert received.agent_id == "trigger"


# ============================================================================
# UNSUBSCRIBE
# ============================================================================


class TestUnsubscribe:
    """CONTRACT: unsubscribe removes subscriber from the list."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self):
        """After unsubscribe, the queue no longer receives events."""
        svc = DecisionFeedService(max_events=100)
        q = await svc.subscribe()

        await svc.unsubscribe(q)

        await svc.emit(make_event())
        assert q.empty()

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_unsubscribe_idempotent(self):
        """Unsubscribing a queue that isn't subscribed is a no-op."""
        svc = DecisionFeedService(max_events=100)
        q = await svc.subscribe()
        await svc.unsubscribe(q)
        # Second unsubscribe should not raise
        await svc.unsubscribe(q)

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_unsubscribe_does_not_affect_other_subscribers(self):
        """Unsubscribing one queue doesn't affect others."""
        svc = DecisionFeedService(max_events=100)
        q1 = await svc.subscribe()
        q2 = await svc.subscribe()

        await svc.unsubscribe(q1)

        evt = make_event()
        await svc.emit(evt)

        assert q1.empty()
        received = q2.get_nowait()
        assert received.event_id == evt.event_id


# ============================================================================
# SINGLETON
# ============================================================================


class TestSingleton:
    """CONTRACT: get_decision_feed_service returns a singleton."""

    @pytest.mark.critical
    def test_singleton_returns_same_instance(self):
        """Multiple calls return the same object."""
        svc1 = get_decision_feed_service()
        svc2 = get_decision_feed_service()
        assert svc1 is svc2
