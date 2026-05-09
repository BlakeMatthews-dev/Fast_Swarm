"""
Evolution Cycle Service - Orchestrate one complete evolution cycle.

This service combines atomic operations (backtest, rank, reproduce, cull)
into a single evolution cycle.

BLUE-GREEN DEPLOYMENT:
Set USE_DEV_BACKTEST=1 to use non-blocking dev backtest service.
Default (unset or 0) uses production backtest service.
"""

import os
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ...Agents.Services.spawn_service import AgentSpawnService

# Blue-Green Switch: Use DEV backtest service if enabled
USE_DEV_BACKTEST = os.environ.get("USE_DEV_BACKTEST", "0") == "1"

if USE_DEV_BACKTEST:
    from ...Agents.Services.backtest_service_dev import AgentBacktestServiceDev as AgentBacktestService

    print("[EvolutionCycle] Using DEV backtest service (non-blocking)")
else:
    from ...Agents.Services.backtest_service import AgentBacktestService

    print("[EvolutionCycle] Using PROD backtest service")

from ...Agents.Services.cull_service import AgentCullService
from ...Agents.Services.ranking_service import AgentRankingService
from ...Patterns.Services.backtest_service import PatternBacktestService
from ...Patterns.Services.cull_service import PatternCullService
from ...Patterns.Services.discovery_service import PatternDiscoveryService
from ...Patterns.Services.pattern_service import get_tiers_by_quintile, is_spawn_eligible
from .state_cache_service import StateCacheService


class EvolutionCycleService:
    """Service for running complete evolution cycles."""

    def __init__(self):
        self.agent_spawn = AgentSpawnService()
        self.agent_backtest = AgentBacktestService()
        self.agent_cull = AgentCullService()
        self.agent_ranking = AgentRankingService()
        self.pattern_backtest = PatternBacktestService()
        self.pattern_cull = PatternCullService()
        self.pattern_discovery = PatternDiscoveryService()
        self.state_cache = StateCacheService()

    async def run_evolution_cycle(
        self,
        session: AsyncSession,
        target_agent_population: int = 500,
        breeding_count: int = 10,
        clone_percentile: float = 0.20,
        survival_percentile: float = 0.70,
        mutation_rate: float = 0.15,
        backtest_assets: list[str] | None = None,
        rapid_evolution: bool = False,
    ) -> dict:
        """
        Run one complete evolution cycle.

        Evolution Model:
        - Top 10 agents → 5 crossover children (breeding pairs)
        - Top X% → clone themselves (elite preservation with mutation)
        - Top Y% → survive unchanged
        - Bottom (100-Y)% → culled
        - Spawn fresh = culled - children - clones (diversity injection)

        Args:
            session: Database session
            target_agent_population: Minimum target population
            breeding_count: Number of top agents to breed (default 10 → 5 children)
            clone_percentile: Top X% to clone (default 0.20)
            survival_percentile: Top Y% to survive (default 0.70)
            mutation_rate: Mutation rate for clones/children
            backtest_assets: Assets to backtest on
            rapid_evolution: If True, use aggressive settings (X=15%, Y=55%)

        Returns:
            Dict with cycle results
        """
        # Apply rapid evolution settings if requested
        if rapid_evolution:
            clone_percentile = 0.15
            survival_percentile = 0.55
        cycle_start = datetime.utcnow()
        results = {
            "cycle_start": cycle_start.isoformat(),
            "phases": {},
        }

        # Phase 0: Load caches for performance
        print("[EvolutionCycle] Phase 0: Loading state caches...")
        await self.state_cache.refresh_caches(session)
        cache_stats = self.state_cache.get_cache_stats()
        results["cache_stats"] = cache_stats

        # Phase 0.5: Quick pattern batch test (small batch — full testing done by separate loop)
        print("[EvolutionCycle] Phase 0.5: Quick pattern batch test (10 patterns)...")
        try:
            discovery_result = await self.pattern_discovery.run_batch_backtest(
                session=session,
                batch_size=10,
            )
        except Exception as e:
            print(f"[EvolutionCycle] Pattern backtest skipped: {e}")
            # TODO: Remove rollback once pattern discovery uses compute-then-write
            await session.rollback()
            discovery_result = {"skipped": True, "reason": str(e)}
        results["phases"]["pattern_discovery"] = discovery_result

        # Invalidate pattern cache after discovery (patterns updated)
        self.state_cache.invalidate_pattern_cache()
        await self.state_cache.load_pattern_cache(session, force_reload=True)

        # Phase 1: Backtest all active agents
        print("[EvolutionCycle] Phase 1: Backtesting agents...")
        from sqlmodel import select

        from ...Agents.Models.agent_models import Agent

        agent_result = await session.execute(select(Agent).where(Agent.status == "active"))
        agent_result = agent_result.scalars()
        active_agents = agent_result.all()
        agent_ids = [a.agent_id for a in active_agents]

        # CRITICAL: Population Extinction Detection
        if len(agent_ids) == 0:
            print("[EvolutionCycle] CRITICAL: Population extinct! No active agents found.")
            print("[EvolutionCycle] Triggering emergency spawn...")
            # Emergency spawn to recover from extinction
            try:
                emergency_spawned = await self.agent_spawn.spawn_new_agents(
                    session=session,
                    count=target_agent_population,
                    generation=1,
                )
                print(f"[EvolutionCycle] Emergency spawned {len(emergency_spawned)} agents")
                agent_ids = emergency_spawned
                results["emergency_spawn"] = {
                    "triggered": True,
                    "agents_spawned": len(emergency_spawned),
                    "reason": "population_extinct",
                }
            except Exception as spawn_err:
                print(f"[EvolutionCycle] FATAL: Emergency spawn failed: {spawn_err}")
                results["error"] = f"Population extinct and emergency spawn failed: {spawn_err}"
                results["phases"]["backtest"] = {"error": "population_extinct", "agents_tested": 0}
                return results

        try:
            backtest_results = await self.agent_backtest.backtest_agents(
                session=session,
                agent_ids=agent_ids,
                assets=backtest_assets,
            )
            results["phases"]["backtest"] = {
                "agents_tested": len(agent_ids),
                "successful": sum(1 for r in backtest_results.values() if "error" not in r),
                "failed": sum(1 for r in backtest_results.values() if "error" in r),
            }
        except Exception as bt_err:
            print(f"[EvolutionCycle] Backtest phase failed: {bt_err}")
            await session.rollback()
            backtest_results = {}
            results["phases"]["backtest"] = {"error": str(bt_err), "agents_tested": 0}

        # Phase 1b: Out-of-Sample validation (last 6 months, all timeframes)
        # This is the key overfitting filter — agents must generalize to recent unseen data
        print("[EvolutionCycle] Phase 1b: Out-of-sample validation (recent 6 months, all TFs)...")
        try:
            from datetime import timedelta

            oos_days = 180
            oos_cutoff_ts = int((datetime.utcnow() - timedelta(days=oos_days)).timestamp() * 1000)
            all_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

            oos_results = await self.agent_backtest.backtest_agents(
                session=session,
                agent_ids=agent_ids,
                assets=backtest_assets,
                min_start_ts=oos_cutoff_ts,
                timeframes_override=all_timeframes,
            )

            # Store OOS fitness — batch load all agents in one query
            valid_oos = {aid: r for aid, r in oos_results.items() if "error" not in r}
            oos_scored = 0
            if valid_oos:
                agent_result = await session.execute(
                    select(Agent).where(Agent.agent_id.in_(list(valid_oos.keys())))
                )
                agents_by_id = {a.agent_id: a for a in agent_result.scalars().all()}
                for aid, oos_result in valid_oos.items():
                    agent_obj = agents_by_id.get(aid)
                    if agent_obj:
                        traits = agent_obj.traits or {}
                        traits["oos_fitness_score"] = float(oos_result.get("fitness_score", 0))
                        agent_obj.traits = traits
                        oos_scored += 1

            await session.commit()
            results["phases"]["oos_validation"] = {
                "oos_days": oos_days,
                "agents_scored": oos_scored,
                "timeframes": all_timeframes,
            }
            print(f"[EvolutionCycle] OOS: {oos_scored} agents scored on recent {oos_days}-day data across {len(all_timeframes)} timeframes")
        except Exception as oos_err:
            print(f"[EvolutionCycle] OOS validation failed (non-fatal): {oos_err}")
            await session.rollback()
            results["phases"]["oos_validation"] = {"error": str(oos_err)}

        # Phase 2: Rank agents
        print("[EvolutionCycle] Phase 2: Ranking agents...")
        rankings = await self.agent_ranking.rank_agents(session=session)

        results["phases"]["rank"] = {
            "total_agents": len(rankings),
            "top_fitness": float(rankings[0]["fitness_score"]) if rankings else 0,
            "avg_fitness": sum(float(r["fitness_score"] or 0) for r in rankings) / len(rankings) if rankings else 0,
        }

        # Phase 2.5: Level increment for top 10 agents (+2 levels each)
        # This rewards consistently high performers regardless of reproduction
        print("[EvolutionCycle] Phase 2.5: Incrementing levels for top 10 agents...")
        all_agents_for_leveling = await self.agent_ranking.get_all_agents_ranked(session=session)
        top_10_agents = all_agents_for_leveling[:10]
        leveled_agents = []

        for agent in top_10_agents:
            old_level = agent.level or 1
            agent.level = old_level + 2
            leveled_agents.append({"agent_id": agent.agent_id, "old_level": old_level, "new_level": agent.level})
        # Agents are already tracked by session from the query — no add() needed

        await session.commit()
        print(f"[EvolutionCycle] Leveled up {len(leveled_agents)} agents (+2 each)")

        results["phases"]["level_increment"] = {
            "agents_leveled": len(leveled_agents),
            "level_increase": 2,
            "agents": leveled_agents[:5],  # Sample
        }

        # Phase 3: Breeding - Top 10 agents produce 5 crossover children
        print("[EvolutionCycle] Phase 3: Breeding top 10 agents...")
        all_agents_ranked = await self.agent_ranking.get_all_agents_ranked(session=session)
        total_population = len(all_agents_ranked)

        # Get top 10 for breeding (paired → 5 children)
        breeding_agents = all_agents_ranked[: min(breeding_count, total_population)]
        children_spawned = []

        for i in range(0, len(breeding_agents) - 1, 2):
            parent_a = breeding_agents[i]
            parent_b = breeding_agents[i + 1]

            try:
                child_ids = await self.agent_spawn.spawn_children(
                    session=session,
                    parent_ids=[parent_a.agent_id, parent_b.agent_id],
                    mutation_rate=mutation_rate,
                )
                children_spawned.extend(child_ids)
            except Exception as e:
                print(f"[EvolutionCycle] Error breeding {parent_a.agent_id} + {parent_b.agent_id}: {e}")
                continue

        results["phases"]["breed"] = {
            "breeding_parents": len(breeding_agents),
            "children_spawned": len(children_spawned),
        }

        # Phase 3b: Cloning - Top X% (excluding breeders) clone themselves
        print(f"[EvolutionCycle] Phase 3b: Cloning top {clone_percentile * 100:.0f}%...")
        clone_count = int(total_population * clone_percentile)
        # Exclude top 10 breeders from clone pool
        clone_candidates = all_agents_ranked[breeding_count : clone_count + breeding_count]

        clones_created = []
        for agent in clone_candidates:
            try:
                clone_ids = await self.agent_spawn.spawn_children(
                    session=session,
                    parent_ids=[agent.agent_id],  # Single parent = clone
                    mutation_rate=mutation_rate,
                )
                clones_created.extend(clone_ids)
            except Exception as e:
                print(f"[EvolutionCycle] Error cloning {agent.agent_id}: {e}")
                continue

        results["phases"]["clone"] = {
            "clone_candidates": len(clone_candidates),
            "clones_created": len(clones_created),
        }

        # Phase 4: Cull bottom (100-Y)% performers
        cull_percentile = 1.0 - survival_percentile
        print(f"[EvolutionCycle] Phase 4: Culling bottom {cull_percentile * 100:.0f}%...")
        cull_result = await self.agent_cull.cull_agents(
            session=session,
            cull_percentile=cull_percentile,
            min_population=10,
        )

        results["phases"]["cull"] = cull_result

        # Phase 5: Spawn fresh agents for diversity
        # Formula: spawn = culled - children - clones
        # NEW: Use regime-priority patterns (targeting weak categories like crash/bear/1m)
        print("[EvolutionCycle] Phase 5: Spawning fresh agents for diversity...")
        culled_count = cull_result.get("culled_count", 0)
        children_count = len(children_spawned)
        clones_count = len(clones_created)
        current_population = cull_result["remaining_count"] + children_count + clones_count

        # Calculate spawn needed
        spawn_for_replacement = max(0, culled_count - children_count - clones_count)
        spawn_for_target = max(0, target_agent_population - current_population)
        spawn_count = max(spawn_for_replacement, spawn_for_target)

        # CAP: Never spawn more than 10 agents per evolution cycle
        MAX_SPAWN_PER_CYCLE = 10
        if spawn_count > MAX_SPAWN_PER_CYCLE:
            print(f"[EvolutionCycle] Capping spawn from {spawn_count} to {MAX_SPAWN_PER_CYCLE}")
            spawn_count = MAX_SPAWN_PER_CYCLE

        if spawn_count > 0:
            # NEW: Try regime-priority patterns first (targets weak categories)
            from ...Agents.Services.spawn_service import get_regime_priority_patterns

            spawn_patterns = []
            try:
                regime_patterns = await get_regime_priority_patterns(
                    session,
                    top_pct_per_category=0.20,
                    final_pool_size=50,
                )
                if regime_patterns:
                    spawn_patterns = regime_patterns
                    print(
                        f"[EvolutionCycle] Using {len(spawn_patterns)} regime-priority patterns (targeting weak categories)"
                    )
            except Exception as e:
                print(f"[EvolutionCycle] Regime-priority patterns failed: {e}")

            # FALLBACK: Use standard quintile-based patterns if regime-priority is empty
            if not spawn_patterns:
                print("[EvolutionCycle] Fallback: Using quintile-based patterns")
                from ...Patterns.Models.pattern_models import Pattern

                pattern_result = await session.exec(select(Pattern).where(Pattern.is_active.is_(True)))
                all_patterns = pattern_result.all()

                # Convert to dicts and calculate quintile tiers
                pattern_dicts = [
                    {
                        "pattern_id": p.pattern_id,
                        "fitness_score": p.fitness_score or 0,
                        "backtest_count": getattr(p, "backtest_count", 0) or 0,
                        "assets_tested": getattr(p, "assets_tested", []) or [],
                        "timeframes_tested": getattr(p, "timeframes_tested", []) or [],
                    }
                    for p in all_patterns
                ]

                tiers = get_tiers_by_quintile(pattern_dicts)

                # Filter by spawn eligibility (Tier 1-2)
                for p in all_patterns:
                    tier = tiers.get(p.pattern_id, 5)
                    if is_spawn_eligible(tier=tier):
                        spawn_patterns.append(
                            {
                                "pattern_id": p.pattern_id,
                                "entry_conditions": p.entry_conditions,
                                "exit_conditions": p.exit_conditions,
                                "type": getattr(p, "origin", "unknown"),
                                "fitness_score": p.fitness_score or 0,
                                "win_rate": getattr(p, "win_rate", 0.5) or 0.5,
                                "volatility": 0.5,
                            }
                        )

                # Fallback if no spawn-eligible patterns
                if not spawn_patterns and all_patterns:
                    print("[EvolutionCycle] No spawn-eligible patterns. Using top 40% fallback.")
                    sorted_patterns = sorted(all_patterns, key=lambda p: p.fitness_score or 0, reverse=True)
                    spawn_patterns = [
                        {
                            "pattern_id": p.pattern_id,
                            "entry_conditions": p.entry_conditions,
                            "exit_conditions": p.exit_conditions,
                            "type": getattr(p, "origin", "unknown"),
                            "fitness_score": p.fitness_score or 0,
                            "win_rate": getattr(p, "win_rate", 0.5) or 0.5,
                            "volatility": 0.5,
                        }
                        for p in sorted_patterns[: max(1, int(len(sorted_patterns) * 0.4))]
                    ]

            print(f"[EvolutionCycle] Spawning {spawn_count} agents with {len(spawn_patterns)} patterns")

            try:
                new_agent_ids = await self.agent_spawn.spawn_new_agents(
                    session=session,
                    count=spawn_count,
                    generation=1,
                    available_patterns=spawn_patterns,
                )
                results["phases"]["spawn"] = {
                    "agents_spawned": len(new_agent_ids),
                    "pattern_source": "regime_priority" if regime_patterns else "quintile_fallback",
                    "pattern_count": len(spawn_patterns),
                    "formula": f"max({culled_count} - {children_count} - {clones_count}, {target_agent_population} - {current_population})",
                    "new_agent_ids": new_agent_ids[:5],  # Sample
                }
            except Exception as spawn_err:
                print(f"[EvolutionCycle] Spawn phase failed: {spawn_err}")
                await session.rollback()
                results["phases"]["spawn"] = {"error": str(spawn_err), "agents_spawned": 0}
        else:
            results["phases"]["spawn"] = {
                "agents_spawned": 0,
                "message": "Children and clones sufficient",
            }

        # Final stats
        cycle_end = datetime.utcnow()
        final_stats = await self.agent_ranking.calculate_population_stats(session=session)

        results["cycle_end"] = cycle_end.isoformat()
        results["duration_seconds"] = (cycle_end - cycle_start).total_seconds()
        results["final_population"] = final_stats

        # Phase 6: Crucible Eligibility Check
        # Check all agents that leveled up or were created this cycle for Crucible eligibility
        print("[EvolutionCycle] Phase 6: Checking Crucible eligibility...")
        from .crucible_entry_service import CrucibleEntryService

        crucible_service = CrucibleEntryService()

        # Check the agents that just leveled up (most likely to be eligible)
        leveled_agent_ids = [a["agent_id"] for a in leveled_agents]
        crucible_entries = await crucible_service.check_agents_batch(session, leveled_agent_ids)

        results["phases"]["crucible"] = {
            "agents_checked": len(leveled_agent_ids),
            "entries_created": len(crucible_entries),
            "new_entries": [
                {"agent_id": e.agent_id, "level": e.level_at_entry}
                for e in crucible_entries
            ],
        }

        if crucible_entries:
            print(f"[EvolutionCycle] {len(crucible_entries)} agents entered the Crucible!")

            # Phase 6b: Run Crucible tests for new entries
            print("[EvolutionCycle] Phase 6b: Running Crucible tests...")
            from .crucible_test_service import CrucibleTestService

            test_service = CrucibleTestService()
            crucible_results = []
            for entry in crucible_entries:
                try:
                    test_result = await test_service.run_crucible_test(session, entry.id)
                    crucible_results.append(test_result)
                except Exception as e:
                    print(f"[EvolutionCycle] Crucible test failed for entry {entry.id}: {e}")

            results["phases"]["crucible"]["tests_run"] = len(crucible_results)
            results["phases"]["crucible"]["tests_completed"] = sum(
                1 for r in crucible_results if r.get("status") == "completed"
            )

        return results

    async def run_pattern_cycle(
        self,
        session: AsyncSession,
        cull_percentile: float = 0.3,
        backtest_assets: list[str] | None = None,
    ) -> dict:
        """
        Run one pattern evolution cycle.

        Phases:
        1. Backtest all active patterns
        2. Cull bottom performers

        Args:
            session: Database session
            cull_percentile: Bottom X% to cull
            backtest_assets: Assets to backtest on

        Returns:
            Dict with cycle results
        """
        cycle_start = datetime.utcnow()
        results = {
            "cycle_start": cycle_start.isoformat(),
            "phases": {},
        }

        # Phase 1: Backtest patterns
        print("[PatternCycle] Phase 1: Backtesting patterns...")
        from sqlmodel import select

        from ...Patterns.Models.pattern_models import Pattern

        pattern_result = await session.exec(select(Pattern).where(Pattern.is_active.is_(True)))
        active_patterns = pattern_result.all()
        pattern_ids = [p.pattern_id for p in active_patterns]

        backtest_results = await self.pattern_backtest.backtest_patterns(
            session=session,
            pattern_ids=pattern_ids,
            assets=backtest_assets,
        )

        results["phases"]["backtest"] = {
            "patterns_tested": len(pattern_ids),
            "successful": sum(1 for r in backtest_results.values() if "error" not in r),
            "failed": sum(1 for r in backtest_results.values() if "error" in r),
        }

        # Phase 2: Cull patterns
        print("[PatternCycle] Phase 2: Culling patterns...")
        cull_result = await self.pattern_cull.cull_patterns(
            session=session,
            cull_percentile=cull_percentile,
            min_population=20,
        )

        results["phases"]["cull"] = cull_result

        cycle_end = datetime.utcnow()
        results["cycle_end"] = cycle_end.isoformat()
        results["duration_seconds"] = (cycle_end - cycle_start).total_seconds()

        return results
