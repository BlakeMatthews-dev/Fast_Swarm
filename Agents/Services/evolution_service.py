"""
Agent Evolution Service - Clone, reproduce, level up, and cull operations.

Based on V3's agent-evolution-controller.ts 4-phase cycle:
SPAWN → BACKTEST → SELECT → REPRODUCE
"""

import asyncio
import logging
import random

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

logger = logging.getLogger(__name__)

from ..Models.agent_models import Agent, EvolutionRunRequest
from .cull_service import AgentCullService
from .ranking_service import AgentRankingService
from .spawn_service import AgentSpawnService

# =============================================================================
# Module-level trigger function (called by evolution_router.py)
# =============================================================================

# Track active evolution runs to prevent concurrent cycles
_active_evolution_run = False
_last_evolution_result: dict | None = None
_evolution_lock = asyncio.Lock()  # Protects _active_evolution_run from race conditions


def reset_evolution_flag():
    """
    Reset the evolution flag on startup.

    This prevents the flag from being stuck forever after a crash
    where the finally block never executed.
    """
    global _active_evolution_run
    _active_evolution_run = False
    print("[Evolution] Global flag reset to False")


async def trigger_evolution(
    background_tasks: BackgroundTasks,
    request: EvolutionRunRequest,
) -> dict:
    """
    Trigger an evolution cycle in the background.

    Args:
        background_tasks: FastAPI BackgroundTasks for async execution
        request: Evolution parameters from API request

    Returns:
        Dict with status message and run ID

    Note:
        Uses asyncio.Lock to prevent TOCTOU race condition where two
        concurrent requests could both see _active_evolution_run=False
        and both start evolution cycles.
    """
    global _active_evolution_run

    # Acquire lock to prevent race condition (TOCTOU vulnerability)
    async with _evolution_lock:
        if _active_evolution_run:
            return {
                "status": "rejected",
                "message": "Evolution cycle already in progress",
                "hint": "Check /evolution/monitor/current for status",
            }

        # Mark as running while still holding the lock
        _active_evolution_run = True

    # Generate run ID (outside lock - no shared state access)
    run_id = f"evo_{int(asyncio.get_event_loop().time() * 1000)}"

    # Start background task
    background_tasks.add_task(
        _run_evolution_background,
        run_id=run_id,
        request=request,
    )

    return {
        "status": "started",
        "run_id": run_id,
        "message": f"Evolution cycle started with {request.generations} generations",
        "parameters": {
            "generations": request.generations,
            "population_size": request.population_size,
            "elite_percent": request.elite_percent,
            "survival_percent": request.survival_percent,
            "mutation_rate": request.mutation_rate,
            "assets": request.assets,
            "timeframe": request.timeframe,
        },
    }


async def _run_evolution_background(run_id: str, request: EvolutionRunRequest):
    """
    Background task that runs the evolution cycle.

    This runs asynchronously and updates global state for monitoring.
    Also persists EvolutionCycle records to the database.
    """
    global _active_evolution_run, _last_evolution_result
    import time
    from datetime import datetime

    _active_evolution_run = True
    start_time = time.time()

    try:
        from ...Database import async_session_maker
        from ...Evolution.Models.evolution_models import EvolutionCycle
        from ...System.Services.evolution_cycle_service import EvolutionCycleService

        cycle_service = EvolutionCycleService()

        results = []
        async with async_session_maker() as session:
            for gen in range(request.generations):
                cycle_start = time.time()
                print(f"[Evolution] Starting generation {gen + 1}/{request.generations}")

                # Create cycle record
                cycle = EvolutionCycle(
                    cycle_id=f"{run_id}_gen{gen + 1}",
                    cycle_number=gen + 1,
                    phase="running",
                    started_at=datetime.utcnow(),
                    status="running",
                    config={
                        "population_size": request.population_size,
                        "elite_percent": request.elite_percent,
                        "survival_percent": request.survival_percent,
                        "mutation_rate": request.mutation_rate,
                        "assets": request.assets,
                        "timeframe": request.timeframe,
                    },
                )
                session.add(cycle)
                await session.commit()

                try:
                    result = await cycle_service.run_evolution_cycle(
                        session=session,
                        target_agent_population=request.population_size,
                        survival_percentile=request.survival_percent,
                        clone_percentile=request.elite_percent,
                        mutation_rate=request.mutation_rate,
                        backtest_assets=request.assets,
                    )

                    result["generation"] = gen + 1
                    results.append(result)

                    # Update cycle record with results
                    cycle.phase = "completed"
                    cycle.status = "completed"
                    cycle.completed_at = datetime.utcnow()
                    cycle.duration_seconds = int(time.time() - cycle_start)
                    cycle.agents_spawned = result.get("spawned_count", 0)
                    cycle.agents_culled = result.get("culled_count", 0)
                    cycle.agents_reproduced = result.get("reproduced_count", 0)
                    final_pop = result.get("final_population", {})
                    cycle.avg_elo = final_pop.get("avg_fitness")
                    cycle.top_elo = final_pop.get("max_fitness")
                    session.add(cycle)
                    await session.commit()

                    print(
                        f"[Evolution] Generation {gen + 1} complete: fitness_avg={final_pop.get('avg_fitness', 'N/A')}"
                    )

                except Exception as gen_error:
                    # CRITICAL: Rollback the failed transaction before updating error status
                    # PostgreSQL requires ROLLBACK after any error before new commands can execute
                    await session.rollback()

                    # Update cycle with error (now in a fresh transaction)
                    cycle.phase = "failed"
                    cycle.status = "failed"
                    cycle.error_message = str(gen_error)
                    cycle.completed_at = datetime.utcnow()
                    session.add(cycle)
                    await session.commit()
                    raise gen_error

        _last_evolution_result = {
            "run_id": run_id,
            "status": "completed",
            "generations_completed": len(results),
            "duration_seconds": int(time.time() - start_time),
            "final_result": results[-1] if results else None,
            "all_results": results,
        }

        print(f"[Evolution] Run {run_id} completed successfully")

    except Exception as e:
        print(f"[Evolution] Run {run_id} failed: {e}")
        import traceback

        traceback.print_exc()
        _last_evolution_result = {
            "run_id": run_id,
            "status": "failed",
            "error": str(e),
        }
    finally:
        _active_evolution_run = False


def get_evolution_status() -> dict:
    """Get current evolution run status."""
    return {
        "is_running": _active_evolution_run,
        "last_result": _last_evolution_result,
    }


def _extract_patterns_from_agent(agent: Agent) -> list[dict]:
    """
    Extract patterns from agent's embedded JSONB, preserving modifications.

    Agents own their patterns and can modify them over time. This function
    extracts the agent's actual patterns rather than fetching canonical
    versions from the Pattern table (which would lose all evolution).

    Args:
        agent: Agent to extract patterns from

    Returns:
        List of pattern dicts with entry_conditions, exit_conditions, etc.
    """
    patterns = []
    assigned = agent.assigned_patterns

    if assigned is None:
        return patterns

    if isinstance(assigned, dict):
        # Modern format: {"base": [...patterns...], "weights": {...}}
        base_patterns = assigned.get("base", [])
        for p in base_patterns:
            if isinstance(p, dict) and p.get("entry_conditions") and p.get("exit_conditions"):
                patterns.append(
                    {
                        "pattern_id": p.get("pattern_id", f"embedded_{len(patterns)}"),
                        "entry_conditions": p["entry_conditions"],
                        "exit_conditions": p["exit_conditions"],
                        "fitness_score": p.get("fitness_score", 50.0),
                        # Preserve any agent-specific modifications
                        "confidence_threshold": p.get("confidence_threshold"),
                        "position_size_modifier": p.get("position_size_modifier"),
                    }
                )
    elif isinstance(assigned, list):
        # Legacy format: list of pattern IDs or pattern dicts
        for item in assigned:
            if isinstance(item, dict) and item.get("entry_conditions") and item.get("exit_conditions"):
                patterns.append(
                    {
                        "pattern_id": item.get("pattern_id", f"embedded_{len(patterns)}"),
                        "entry_conditions": item["entry_conditions"],
                        "exit_conditions": item["exit_conditions"],
                        "fitness_score": item.get("fitness_score", 50.0),
                    }
                )
            # If it's just an ID string, we can't recover the pattern - it was lost
            # This is the legacy case we're fixing

    return patterns


class AgentEvolutionService:
    """Service for agent evolution operations."""

    def __init__(self):
        self.spawn_service = AgentSpawnService()
        self.cull_service = AgentCullService()
        self.ranking_service = AgentRankingService()

    async def clone_agent(
        self,
        session: AsyncSession,
        parent_id: str,
        mutation_rate: float = 0.1,
    ) -> str:
        """
        Clone an agent with trait mutations.

        Based on V3's cloneAgent():
        - Mutates traits by ±mutation_rate (default 0.1 = ±10%)
        - Increments generation
        - Sets parent_id

        Args:
            session: Database session
            parent_id: Parent agent ID
            mutation_rate: Mutation rate for traits (0.1 = ±10%)

        Returns:
            New agent ID
        """
        # Get parent
        result = await session.exec(select(Agent).where(Agent.agent_id == parent_id))
        parent = result.first()

        if not parent:
            raise ValueError(f"Parent agent {parent_id} not found")

        # Mutate traits
        parent_traits = parent.traits if isinstance(parent.traits, dict) else parent.traits.__dict__
        mutated_traits = {}

        for key, value in parent_traits.items():
            if isinstance(value, (int, float)):
                # Add mutation: (random - 0.5) * 2 * mutation_rate
                mutation = (random.random() - 0.5) * 2 * mutation_rate
                mutated_traits[key] = max(0, min(1, value + mutation))
            else:
                mutated_traits[key] = value

        # Create clone via spawn service
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        agent_db = AgentDatabase()

        # Get patterns from parent's JSONB (NOT the Pattern table!)
        # This preserves any modifications the parent made to their patterns
        available_patterns = _extract_patterns_from_agent(parent)

        # Spawn with mutated traits
        agent_record = spawn_agent(
            seed=random.randint(0, 1000000),
            available_patterns=available_patterns,
            generation=parent.generation + 1,
            use_llm=False,
            db=agent_db,
        )

        # Override traits with mutated ones
        agent_record.traits = mutated_traits

        # Convert to SQLModel Agent
        clone = Agent(
            agent_id=agent_record.agent_id,
            name=f"agent_{agent_record.agent_id[:8]}",
            traits=mutated_traits,
            assigned_patterns=parent.assigned_patterns,
            pattern_weights=parent.pattern_weights,
            generation=parent.generation + 1,
            parent_a_id=parent_id,
            trading_philosophy=parent.trading_philosophy,
            is_active=True,
            status="active",
            level=1,  # Child starts at level 1
        )

        # LEVEL UP: Parent levels up when spawning a child
        parent.level = (parent.level or 0) + 1
        session.add(parent)

        session.add(clone)
        await session.commit()

        return clone.agent_id

    async def crossover_agents(
        self,
        session: AsyncSession,
        parent_a_id: str,
        parent_b_id: str,
        noise_rate: float = 0.05,
    ) -> str:
        """
        Create crossbred offspring from two parents.

        Based on V3's crossoverAgents():
        - 50% chance to inherit each trait from either parent
        - Adds noise of ±noise_rate (default 0.05 = ±5%)
        - Generation = max(parent generations) + 1

        Args:
            session: Database session
            parent_a_id: First parent ID
            parent_b_id: Second parent ID
            noise_rate: Noise rate for crossover (0.05 = ±5%)

        Returns:
            New agent ID
        """
        # Get parents
        result = await session.exec(select(Agent).where(Agent.agent_id.in_([parent_a_id, parent_b_id])))
        parents = result.all()

        if len(parents) != 2:
            raise ValueError("Could not find both parents")

        parent_a = parents[0]
        parent_b = parents[1]

        # Check for same lineage (V3's areSameLineage)
        if self._are_same_lineage(parent_a, parent_b):
            raise ValueError("Cannot crossbreed agents from same lineage")

        # Mix traits
        traits_a = parent_a.traits if isinstance(parent_a.traits, dict) else parent_a.traits.__dict__
        traits_b = parent_b.traits if isinstance(parent_b.traits, dict) else parent_b.traits.__dict__

        mixed_traits = {}
        for key in traits_a.keys():
            val_a = traits_a.get(key, 0)
            val_b = traits_b.get(key, 0)

            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                # 50% chance from each parent + noise
                base = val_a if random.random() < 0.5 else val_b
                noise = (random.random() - 0.5) * 2 * noise_rate
                mixed_traits[key] = max(0, min(1, base + noise))
            else:
                mixed_traits[key] = val_a  # Default to parent A

        # Create child
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        agent_db = AgentDatabase()

        # Get patterns from both parents' JSONB (NOT the Pattern table!)
        # This preserves any modifications each parent made to their patterns
        patterns_a = _extract_patterns_from_agent(parent_a)
        patterns_b = _extract_patterns_from_agent(parent_b)

        # Merge patterns, deduplicate by pattern_id (prefer higher fitness)
        pattern_map = {}
        for p in patterns_a + patterns_b:
            pid = p.get("pattern_id")
            if pid not in pattern_map or p.get("fitness_score", 0) > pattern_map[pid].get("fitness_score", 0):
                pattern_map[pid] = p
        available_patterns = list(pattern_map.values())

        # Spawn child
        new_generation = max(parent_a.generation, parent_b.generation) + 1
        agent_record = spawn_agent(
            seed=random.randint(0, 1000000),
            available_patterns=available_patterns,
            generation=new_generation,
            use_llm=False,
            db=agent_db,
        )

        # Override traits
        agent_record.traits = mixed_traits

        # Convert to SQLModel Agent
        child = Agent(
            agent_id=agent_record.agent_id,
            name=f"agent_{agent_record.agent_id[:8]}",
            traits=mixed_traits,
            assigned_patterns=agent_record.pattern_ids,
            pattern_weights=agent_record.pattern_weights,
            generation=new_generation,
            parent_a_id=parent_a_id,
            parent_b_id=parent_b_id,
            trading_philosophy=agent_record.trading_philosophy,
            is_active=True,
            status="active",
            level=1,  # Child starts at level 1
        )

        # LEVEL UP: Both parents level up when spawning a child
        parent_a.level = (parent_a.level or 0) + 1
        parent_b.level = (parent_b.level or 0) + 1
        session.add(parent_a)
        session.add(parent_b)

        session.add(child)
        await session.commit()

        return child.agent_id

    def _are_same_lineage(self, agent_a: Agent, agent_b: Agent) -> bool:
        """Check if two agents share the same lineage."""
        return (
            agent_a.agent_id == agent_b.parent_a_id
            or agent_b.agent_id == agent_a.parent_a_id
            or (agent_a.parent_a_id is not None and agent_a.parent_a_id == agent_b.parent_a_id)
        )

    async def evolve_generation(
        self,
        session: AsyncSession,
        promotion_percentile: float = 0.2,
        retirement_percentile: float = 0.3,
        clone_mutation_rate: float = 0.1,
        crossover_noise_rate: float = 0.05,
    ) -> dict:
        """
        Execute one complete evolution cycle (V3's 4-phase cycle).

        Phases:
        1. SELECT - Identify top 20% and bottom 30%
        2. CLONE - Clone top performers with mutations
        3. CROSSBREED - Create offspring from compatible pairs
        4. CULL - Remove bottom performers

        Args:
            session: Database session
            promotion_percentile: Top X% to clone/breed (0.2 = 20%)
            retirement_percentile: Bottom X% to cull (0.3 = 30%)
            clone_mutation_rate: Mutation rate for clones
            crossover_noise_rate: Noise rate for crossbreeding

        Returns:
            Dict with evolution results
        """
        # Phase 1: SELECT
        top_agents = await self.ranking_service.get_top_agents(
            session=session,
            top_percentile=promotion_percentile,
        )

        bottom_agents = await self.ranking_service.get_bottom_agents(
            session=session,
            bottom_percentile=retirement_percentile,
        )

        # Phase 2: CLONE top performers (with error aggregation)
        cloned_ids = []
        clone_failures = []
        for agent in top_agents:
            try:
                clone_id = await self.clone_agent(
                    session=session,
                    parent_id=agent.agent_id,
                    mutation_rate=clone_mutation_rate,
                )
                cloned_ids.append(clone_id)
            except Exception as e:
                logger.error(f"Clone failed for {agent.agent_id}: {e}", exc_info=True)
                clone_failures.append(
                    {
                        "parent_id": agent.agent_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Phase 3: CROSSBREED compatible pairs (with error aggregation)
        crossbred_ids = []
        crossover_failures = []
        lineage_skips = 0
        pairs_to_create = len(top_agents) // 2

        for i in range(pairs_to_create):
            if i * 2 + 1 >= len(top_agents):
                break

            parent_a = top_agents[i * 2]
            parent_b = top_agents[i * 2 + 1]

            try:
                child_id = await self.crossover_agents(
                    session=session,
                    parent_a_id=parent_a.agent_id,
                    parent_b_id=parent_b.agent_id,
                    noise_rate=crossover_noise_rate,
                )
                crossbred_ids.append(child_id)
            except ValueError:
                # Same lineage, skip (expected behavior, not a failure)
                lineage_skips += 1
                continue
            except Exception as e:
                logger.error(f"Crossover failed for {parent_a.agent_id} x {parent_b.agent_id}: {e}", exc_info=True)
                crossover_failures.append(
                    {
                        "parent_a_id": parent_a.agent_id,
                        "parent_b_id": parent_b.agent_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Log critical warning if failure rate is too high (>50%)

        if top_agents:
            clone_failure_rate = len(clone_failures) / len(top_agents)
            if clone_failure_rate > 0.5:
                logger.critical(
                    f"Evolution cycle had {clone_failure_rate:.0%} clone failure rate! "
                    f"({len(clone_failures)}/{len(top_agents)} failed)"
                )

        if pairs_to_create > 0:
            crossover_failure_rate = len(crossover_failures) / pairs_to_create
            if crossover_failure_rate > 0.5:
                logger.critical(
                    f"Evolution cycle had {crossover_failure_rate:.0%} crossover failure rate! "
                    f"({len(crossover_failures)}/{pairs_to_create} failed)"
                )

        # Phase 4: CULL bottom performers
        cull_result = await self.cull_service.cull_agents(
            session=session,
            cull_percentile=retirement_percentile,
        )

        return {
            "promoted_count": len(top_agents),
            "cloned_count": len(cloned_ids),
            "clone_failures": len(clone_failures),
            "crossbred_count": len(crossbred_ids),
            "crossover_failures": len(crossover_failures),
            "lineage_skips": lineage_skips,
            "culled_count": cull_result["culled_count"],
            "cloned_ids": cloned_ids,
            "crossbred_ids": crossbred_ids,
            "culled_ids": cull_result["culled_ids"],
            # Include sample failures for debugging (first 3 of each)
            "failure_details": {
                "clone_failures": clone_failures[:3],
                "crossover_failures": crossover_failures[:3],
            },
        }
