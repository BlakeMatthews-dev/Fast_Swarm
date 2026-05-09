"""
Evolution Rules - Named Constants for Evolutionary Algorithm

MASTER TEST ADMIN DECREE: No magic numbers in production code.
All evolution parameters must be named, documented, and sourced from here.
"""

# =============================================================================
# POPULATION LIMITS
# =============================================================================

MIN_POPULATION = 150
"""Minimum population size. Cannot cull below this threshold."""

MAX_POPULATION = 1000
"""Maximum population size before forced culling."""

IDEAL_POPULATION = 500
"""Ideal population size for genetic diversity."""


# =============================================================================
# CULLING RULES
# =============================================================================

CULL_PERCENTILE = 20.0
"""Bottom percentile of agents to cull each cycle (20%)."""

CULL_MIN_BACKTESTS = 5
"""Minimum backtests before an agent can be culled."""

CULL_PROTECTION_GENERATIONS = 3
"""New agents protected from culling for this many generations."""


# =============================================================================
# PROMOTION/REPRODUCTION RULES
# =============================================================================

PROMOTE_PERCENTILE = 80.0
"""Top percentile of agents eligible for reproduction."""

REPRODUCTION_SLOTS = 50
"""Number of new agents created per evolution cycle."""

ELITE_PRESERVE_COUNT = 10
"""Number of top agents preserved unchanged (elitism)."""


# =============================================================================
# MUTATION RULES
# =============================================================================

MUTATION_RATE_BASE = 0.1
"""Base mutation rate (probability of mutating each trait)."""

MUTATION_RATE_MIN = 0.01
"""Minimum mutation rate."""

MUTATION_RATE_MAX = 0.5
"""Maximum mutation rate."""

MUTATION_STRENGTH = 0.2
"""Standard deviation for Gaussian mutation."""

MUTATION_STRENGTH_MIN = 0.05
"""Minimum mutation strength."""

MUTATION_STRENGTH_MAX = 0.5
"""Maximum mutation strength."""


# =============================================================================
# CROSSOVER RULES
# =============================================================================

CROSSOVER_RATE = 0.7
"""Probability of crossover vs cloning."""

CROSSOVER_POINTS = 2
"""Number of crossover points for multi-point crossover."""


# =============================================================================
# TRAIT DEFINITIONS
# =============================================================================

ALL_22_TRAITS = [
    # Core Risk Traits (7)
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    "win_rate_preference",
    "drawdown_sensitivity",
    "momentum_vs_reversion",
    # Position Management Traits (4)
    "stop_loss_tightness",
    "entry_aggression",
    "exit_aggression",
    "lookback_preference",
    # Market Sentiment Traits (4)
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    "funding_rate_sensitivity",
    # Correlation/Diversification (1)
    "correlation_awareness",
    # Behavioral Traits (6)
    "patience",
    "adaptability",
    "trend_following",
    "mean_reversion",
    "breakout_preference",
    "volume_sensitivity",
]
"""Complete list of 22 agent traits."""

TRAIT_COUNT = len(ALL_22_TRAITS)
"""Total number of traits (22)."""


# =============================================================================
# GENERATION RULES
# =============================================================================

GENERATION_INCREMENT = 1
"""Generation increment for offspring."""

MAX_GENERATION = 10000
"""Maximum generation number (sanity limit)."""


# =============================================================================
# ELO RATING RULES
# =============================================================================

ELO_DEFAULT = 1500.0
"""Default ELO rating for new agents."""

ELO_K_FACTOR = 32.0
"""K-factor for ELO rating updates."""

ELO_MIN = 100.0
"""Minimum ELO rating."""

ELO_MAX = 3000.0
"""Maximum ELO rating."""


# =============================================================================
# BACKTEST REQUIREMENTS
# =============================================================================

MIN_BACKTESTS_FOR_RANKING = 3
"""Minimum backtests before agent is ranked."""

MIN_BACKTESTS_FOR_EVOLUTION = 5
"""Minimum backtests before agent participates in evolution."""

BACKTEST_TIMEOUT_SECONDS = 300
"""Maximum time for a single backtest (5 minutes)."""


# =============================================================================
# PATTERN ASSIGNMENT
# =============================================================================

MIN_PATTERNS_PER_AGENT = 1
"""Minimum patterns assigned to an agent."""

MAX_PATTERNS_PER_AGENT = 10
"""Maximum patterns assigned to an agent."""

DEFAULT_PATTERNS_PER_AGENT = 3
"""Default number of patterns for new agents."""


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


def validate_population(count: int) -> bool:
    """Check if population count is valid."""
    return MIN_POPULATION <= count <= MAX_POPULATION


def can_cull(population: int, cull_count: int) -> bool:
    """Check if culling is allowed given current population."""
    return (population - cull_count) >= MIN_POPULATION


def get_cull_count(population: int) -> int:
    """Calculate how many agents to cull."""
    target_cull = int(population * CULL_PERCENTILE / 100)
    max_allowed = population - MIN_POPULATION
    return min(target_cull, max_allowed)
