"""
Hivemind Services Package.

Provides all services for the Coach/Hivemind coopetition trading system:

Core Services:
- coach_spawning_service: Population management, trait generation
- coach_llm_service: LLM-guided roster decisions, paper/live promotion
- trio_management_service: Trio formation and regrouping
- trio_voting_service: ELO-weighted voting aggregation
- elo_transfer_service: Sqrt-scaled P&L to ELO transfers

Data & Execution:
- hivemind_data_feed_service: Live market data routing
- portfolio_agent_service: Order execution with autonomous exits

Orchestration:
- hivemind_orchestrator: Wires everything together for live trading

Two-Tier Trading System:
- PAPER: Coaches start here, trading on live tick data but not real money
- LIVE: Coaches promoted here after proving themselves (ELO 1650+, 50+ trades, 55%+ win rate)
"""

from .coach_llm_service import (
    CoachLLMService,
    RosterContext,
    RosterDecision,
    TradingTier,
    acquire_agent_from_template,
    activate_agent,
    bench_agent,
    build_roster_context,
    check_demotion_needed,
    check_promotion_eligibility,
    demote_coach_to_paper,
    execute_roster_decision,
    promote_coach_to_live,
    release_agent,
    run_roster_review_cycle,
    swap_agents,
)
from .coach_spawning_service import (
    bootstrap_coach_population,
    check_and_process_clones,
    check_and_process_deaths,
    clone_coach,
    get_population_stats,
    maintain_population,
    process_coach_death,
    spawn_coach,
    spawn_coach_with_roster,
)
from .elo_transfer_service import (
    apply_backtest_tax,
    apply_clone_bonus,
    apply_death_elo,
    apply_spawn_elo,
    calculate_trio_transfers,
    process_trade_leg_results,
)
from .hivemind_data_feed_service import (
    HivemindDataFeedService,
    HivemindDataSnapshot,
    LiveCandle,
    SymbolState,
    compute_indicators,
)
from .hivemind_orchestrator import (
    HivemindConfig,
    HivemindOrchestrator,
    create_hivemind_orchestrator,
)
from .portfolio_agent_service import (
    ExchangeClient,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradingClient,
    PortfolioAgent,
    PortfolioState,
    Position,
    PositionSide,
    RiskLimits,
    TradeCommand,
)
from .trio_management_service import (
    disband_trio,
    ensure_all_coaches_in_trios,
    find_trios_needing_regroup,
    form_trios,
    get_all_active_trios,
    get_coach_trio,
    get_trio_stats,
    get_unassigned_coaches,
    regroup_all_trios,
)
from .trio_voting_service import (
    AgentVote,
    HivemindDecision,
    TrioDecision,
    aggregate_hivemind_votes,
    calculate_trio_decision,
    collect_agent_votes,
    execute_trio_voting_round,
)

__all__ = [
    # Coach LLM Service
    "CoachLLMService",
    "RosterContext",
    "RosterDecision",
    "TradingTier",
    "bench_agent",
    "activate_agent",
    "swap_agents",
    "acquire_agent_from_template",
    "release_agent",
    "execute_roster_decision",
    "build_roster_context",
    "run_roster_review_cycle",
    "check_promotion_eligibility",
    "check_demotion_needed",
    "promote_coach_to_live",
    "demote_coach_to_paper",
    # Coach Spawning
    "spawn_coach",
    "spawn_coach_with_roster",
    "clone_coach",
    "process_coach_death",
    "maintain_population",
    "bootstrap_coach_population",
    "get_population_stats",
    "check_and_process_clones",
    "check_and_process_deaths",
    # Trio Management
    "form_trios",
    "regroup_all_trios",
    "get_unassigned_coaches",
    "get_all_active_trios",
    "get_coach_trio",
    "get_trio_stats",
    "disband_trio",
    "find_trios_needing_regroup",
    "ensure_all_coaches_in_trios",
    # ELO Transfers
    "calculate_trio_transfers",
    "process_trade_leg_results",
    "apply_backtest_tax",
    "apply_spawn_elo",
    "apply_death_elo",
    "apply_clone_bonus",
    # Trio Voting
    "AgentVote",
    "HivemindDecision",
    "TrioDecision",
    "collect_agent_votes",
    "aggregate_hivemind_votes",
    "calculate_trio_decision",
    "execute_trio_voting_round",
    # Data Feed
    "HivemindDataFeedService",
    "HivemindDataSnapshot",
    "SymbolState",
    "LiveCandle",
    "compute_indicators",
    # Portfolio Agent
    "PortfolioAgent",
    "TradeCommand",
    "OrderResult",
    "Position",
    "PortfolioState",
    "RiskLimits",
    "ExchangeClient",
    "PaperTradingClient",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "PositionSide",
    # Orchestrator
    "HivemindOrchestrator",
    "HivemindConfig",
    "create_hivemind_orchestrator",
]
