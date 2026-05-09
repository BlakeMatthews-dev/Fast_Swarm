"""
State Cache Service - Pattern and agent caching for performance.

This service provides caching for frequently accessed data:
- Pattern cache: Full pattern definitions with entry/exit conditions
- Agent index: Lightweight agent metadata for quick lookups
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


class StateCacheService:
    """Service for caching patterns and agent metadata."""

    def __init__(self):
        self.pattern_cache: dict[str, dict] = {}
        self.agent_index: dict[str, dict] = {}
        self._pattern_cache_loaded = False
        self._agent_index_loaded = False

    async def load_pattern_cache(
        self,
        session: AsyncSession,
        force_reload: bool = False,
    ) -> dict[str, dict]:
        """
        Load all active patterns into cache.

        Args:
            session: Database session
            force_reload: If True, reload even if already cached

        Returns:
            Pattern cache dict
        """
        if self._pattern_cache_loaded and not force_reload:
            return self.pattern_cache

        from ...Patterns.Models.pattern_models import Pattern

        # Get all active patterns
        result = await session.exec(select(Pattern).where(Pattern.is_active == True))
        patterns = result.all()

        # Build cache
        self.pattern_cache = {}
        for pattern in patterns:
            self.pattern_cache[pattern.pattern_id] = {
                "pattern_id": pattern.pattern_id,
                "entry_conditions": pattern.entry_conditions,
                "exit_conditions": pattern.exit_conditions,
                "fitness_score": pattern.fitness_score,
                "win_rate": pattern.win_rate,
                "sharpe_ratio": pattern.sharpe_ratio,
                "total_trades": pattern.total_trades,
            }

        self._pattern_cache_loaded = True
        return self.pattern_cache

    async def load_agent_index(
        self,
        session: AsyncSession,
        force_reload: bool = False,
    ) -> dict[str, dict]:
        """
        Load agent metadata into index (lightweight, no full agent data).

        Args:
            session: Database session
            force_reload: If True, reload even if already cached

        Returns:
            Agent index dict
        """
        if self._agent_index_loaded and not force_reload:
            return self.agent_index

        from ...Agents.Models.agent_models import Agent

        # Get all active agents (metadata only)
        result = await session.execute(select(Agent).where(Agent.status == "active"))
        result = result.scalars()
        agents = result.all()

        # Build index
        self.agent_index = {}
        for agent in agents:
            self.agent_index[agent.agent_id] = {
                "agent_id": agent.agent_id,
                "fitness_score": agent.fitness_score or 0.0,
                "backtest_count": agent.backtest_count or 0,
                "generation": agent.generation,
                "is_active": agent.is_active,
                "assigned_patterns": agent.assigned_patterns or [],
            }

        self._agent_index_loaded = True
        return self.agent_index

    def get_pattern(self, pattern_id: str) -> dict | None:
        """Get pattern from cache."""
        return self.pattern_cache.get(pattern_id)

    def get_patterns_by_ids(self, pattern_ids: list[str]) -> list[dict]:
        """Get multiple patterns from cache."""
        return [self.pattern_cache[pid] for pid in pattern_ids if pid in self.pattern_cache]

    def get_agent_metadata(self, agent_id: str) -> dict | None:
        """Get agent metadata from index."""
        return self.agent_index.get(agent_id)

    def get_top_patterns(self, limit: int = 100) -> list[dict]:
        """Get top N patterns by fitness from cache."""
        sorted_patterns = sorted(self.pattern_cache.values(), key=lambda p: p.get("fitness_score", 0), reverse=True)
        return sorted_patterns[:limit]

    def get_top_agents(self, limit: int = 50) -> list[dict]:
        """Get top N agents by fitness from index."""
        sorted_agents = sorted(self.agent_index.values(), key=lambda a: a.get("fitness_score", 0), reverse=True)
        return sorted_agents[:limit]

    def invalidate_pattern_cache(self):
        """Invalidate pattern cache (force reload on next access)."""
        self._pattern_cache_loaded = False
        self.pattern_cache = {}

    def invalidate_agent_index(self):
        """Invalidate agent index (force reload on next access)."""
        self._agent_index_loaded = False
        self.agent_index = {}

    def invalidate_all(self):
        """Invalidate all caches."""
        self.invalidate_pattern_cache()
        self.invalidate_agent_index()

    async def refresh_caches(self, session: AsyncSession):
        """Refresh all caches from database."""
        await self.load_pattern_cache(session, force_reload=True)
        await self.load_agent_index(session, force_reload=True)

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "pattern_cache_loaded": self._pattern_cache_loaded,
            "pattern_cache_size": len(self.pattern_cache),
            "agent_index_loaded": self._agent_index_loaded,
            "agent_index_size": len(self.agent_index),
        }
