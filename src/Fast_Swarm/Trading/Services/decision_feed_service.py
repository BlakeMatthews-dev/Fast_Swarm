"""
Decision Feed Service.

In-memory ring buffer storing recent AI trading decision events.
Events are emitted during paper trading candle evaluation and streamed
to the dashboard via SSE (Server-Sent Events).
"""

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import asyncio


@dataclass
class DecisionEvent:
    """A single decision event for the live feed."""

    event_id: str  # UUID
    timestamp: str  # ISO format
    agent_id: str
    agent_name: str
    symbol: str
    timeframe: str
    event_type: str  # "pattern_eval" | "zone_decision" | "llm_result" | "trade_proposal"
    # Pattern evaluation fields
    patterns_evaluated: int = 0
    buy_confidence: float = 0.0
    sell_confidence: float = 0.0
    # Zone decision fields
    zone: str = ""  # SKIP | AI_REFLECT | EXECUTE
    zone_thresholds: dict = field(default_factory=dict)
    # LLM result fields
    llm_decision: str = ""  # "hold" | "enter" | "exit" | ""
    llm_reason: str = ""
    llm_parsed: bool = True
    # Trade proposal fields (links to approval queue)
    trade_id: str = ""
    side: str = ""
    suggested_price: float = 0.0
    size_usd: float = 0.0
    status: str = "info"  # "info" | "pending" | "approved" | "rejected" | "expired"
    # Pattern details
    pattern_names: list = field(default_factory=list)
    regime: str = ""


class DecisionFeedService:
    """Manages the real-time decision event feed."""

    def __init__(self, max_events: int = 500):
        self._events: deque[DecisionEvent] = deque(maxlen=max_events)
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def emit(self, event: DecisionEvent):
        """Add event to buffer and notify all subscribers."""
        async with self._lock:
            self._events.append(event)
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def get_recent(self, limit: int = 50, agent_id: str | None = None) -> list[dict]:
        """Get recent events, optionally filtered by agent."""
        events = list(self._events)
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        return [asdict(e) for e in events[-limit:]]

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to new events (for SSE streaming)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        """Remove subscriber."""
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


# Singleton
_decision_feed: DecisionFeedService | None = None


def get_decision_feed_service() -> DecisionFeedService:
    """Get or create the global DecisionFeedService singleton."""
    global _decision_feed
    if _decision_feed is None:
        _decision_feed = DecisionFeedService()
    return _decision_feed
