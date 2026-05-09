"""
Canonical Agents - FROZEN TEST AGENTS

MASTER TEST ADMIN DECREE: These agents are IMMUTABLE.
They are created with fixed seeds for deterministic trait generation.
Changing these invalidates all golden files.

Usage:
    from Tests.Fixtures.canonical_agents import CANONICAL_AGENTS
    agent = CANONICAL_AGENTS["balanced_trader"]
"""

from typing import Any

from Constants.evolution_rules import ALL_22_TRAITS
from Tests.Fixtures.factories import AgentFactory

# =============================================================================
# CANONICAL AGENT SEEDS - DO NOT MODIFY
# =============================================================================

CANONICAL_SEEDS = {
    "balanced_trader": 42,
    "aggressive_momentum": 123,
    "conservative_reversal": 999,
    "trend_follower": 777,
    "mean_reverter": 333,
    "high_frequency": 555,
    "patient_accumulator": 888,
    "volatile_hunter": 666,
}


# =============================================================================
# TRAIT OVERRIDES FOR ARCHETYPE AGENTS
# =============================================================================

ARCHETYPE_TRAITS = {
    "balanced_trader": {
        # No overrides - pure seed-generated traits
    },
    "aggressive_momentum": {
        "risk_tolerance": 0.9,
        "momentum_vs_reversion": 0.95,  # Strong momentum bias
        "entry_aggression": 0.85,
        "exit_aggression": 0.7,
        "volatility_seeking": 0.8,
        "trend_following": 0.9,
    },
    "conservative_reversal": {
        "risk_tolerance": 0.2,
        "momentum_vs_reversion": 0.1,  # Strong reversion bias
        "entry_aggression": 0.3,
        "exit_aggression": 0.8,  # Quick to exit
        "mean_reversion": 0.9,
        "patience": 0.85,
        "drawdown_sensitivity": 0.9,
    },
    "trend_follower": {
        "trend_following": 0.95,
        "momentum_vs_reversion": 0.9,
        "breakout_preference": 0.8,
        "patience": 0.7,
        "hold_duration_bias": 0.8,  # Holds longer
    },
    "mean_reverter": {
        "mean_reversion": 0.95,
        "momentum_vs_reversion": 0.05,
        "entry_aggression": 0.6,
        "patience": 0.9,
        "sentiment_contrarian": 0.85,
    },
    "high_frequency": {
        "hold_duration_bias": 0.1,  # Very short holds
        "entry_aggression": 0.95,
        "exit_aggression": 0.95,
        "patience": 0.1,
        "profit_target_greed": 0.2,  # Takes small profits
        "stop_loss_tightness": 0.9,  # Tight stops
    },
    "patient_accumulator": {
        "patience": 0.95,
        "hold_duration_bias": 0.9,
        "entry_aggression": 0.2,
        "profit_target_greed": 0.8,  # Lets winners run
        "drawdown_sensitivity": 0.3,  # Tolerates drawdowns
    },
    "volatile_hunter": {
        "volatility_seeking": 0.95,
        "risk_tolerance": 0.85,
        "breakout_preference": 0.9,
        "volume_sensitivity": 0.8,
        "adaptability": 0.7,
    },
}


# =============================================================================
# BUILD CANONICAL AGENTS
# =============================================================================


def _build_canonical_agents() -> dict[str, dict[str, Any]]:
    """
    Build all canonical agents with their fixed seeds and trait overrides.

    This function is called once at module load to create the frozen agents.
    """
    agents = {}

    for name, seed in CANONICAL_SEEDS.items():
        trait_overrides = ARCHETYPE_TRAITS.get(name, {})

        agent = AgentFactory.create(
            agent_id=f"canonical-{name}-{seed}",
            name=name.replace("_", " ").title(),
            seed=seed,
            traits_override=trait_overrides,
            generation=1,
            fitness_score=50.0,  # Default starting fitness
            backtest_count=0,
        )

        agents[name] = agent

    return agents


# The canonical agents - created once, used everywhere
CANONICAL_AGENTS: dict[str, dict[str, Any]] = _build_canonical_agents()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_agent(name: str) -> dict[str, Any]:
    """Get a canonical agent by name."""
    if name not in CANONICAL_AGENTS:
        available = ", ".join(CANONICAL_AGENTS.keys())
        raise ValueError(f"Unknown agent '{name}'. Available: {available}")
    # Return a copy to prevent modification
    return dict(CANONICAL_AGENTS[name])


def get_aggressive_agents() -> dict[str, dict[str, Any]]:
    """Get agents with aggressive trading styles."""
    aggressive_names = ["aggressive_momentum", "high_frequency", "volatile_hunter"]
    return {name: dict(CANONICAL_AGENTS[name]) for name in aggressive_names}


def get_conservative_agents() -> dict[str, dict[str, Any]]:
    """Get agents with conservative trading styles."""
    conservative_names = ["conservative_reversal", "patient_accumulator"]
    return {name: dict(CANONICAL_AGENTS[name]) for name in conservative_names}


def get_all_agent_names() -> list:
    """Get list of all canonical agent names."""
    return list(CANONICAL_AGENTS.keys())


# =============================================================================
# VALIDATION
# =============================================================================


def validate_canonical_agents():
    """
    Validate that all canonical agents have correct structure.

    Run this in tests to catch any factory changes that break agents.
    """
    required_fields = ["agent_id", "name", "traits", "generation", "fitness_score"]

    for name, agent in CANONICAL_AGENTS.items():
        for field in required_fields:
            assert field in agent, f"Agent '{name}' missing field '{field}'"

        # Validate trait count
        assert len(agent["traits"]) == len(ALL_22_TRAITS), (
            f"Agent '{name}' has {len(agent['traits'])} traits, expected {len(ALL_22_TRAITS)}"
        )

        # Validate trait bounds
        for trait_name, value in agent["traits"].items():
            assert 0.0 <= value <= 1.0, f"Agent '{name}' trait '{trait_name}' = {value} out of bounds"

    return True
