"""
Agent Trait System - V3 Parity.

22 Total Traits:
- 14 Independent (randomized at spawn)
- 3 Derived (from anchors with ±5% noise)
- 3 Threshold (from uncertainty_anchor)
- 2 Memory traits

Trading Parameter Formulas:
- position_size = 0.01 + risk_tolerance * 0.09 (1-10%)
- stop_loss_dist = 0.10 - stop_loss_tightness * 0.09 (1-10% inverted)
- take_profit_dist = 0.02 + profit_target_greed * 0.18 (2-20%)
- max_hold_ms = 3,600,000 + hold_duration_bias * 601,200,000 (1hr-7days)
"""

from dataclasses import dataclass

from Fast_Swarm.local_agents.shared.rng import seeded_random

# =============================================================================
# Trait Lists
# =============================================================================

INDEPENDENT_TRAITS = [
    # Core Risk (4)
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    # Pattern Selection (2)
    "win_rate_preference",
    "momentum_vs_reversion",
    # Execution (1)
    "entry_aggression",
    # Technical (1)
    "lookback_preference",
    # Sentiment (3)
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    # Macro (2)
    "funding_rate_sensitivity",
    "correlation_awareness",
    # Decision Anchor (1)
    "uncertainty_anchor",
]

DERIVED_TRAITS = [
    "drawdown_sensitivity",
    "stop_loss_tightness",
    "exit_aggression",
]

THRESHOLD_TRAITS = [
    "ai_assist_range",
    "min_threshold",
    "ai_threshold",
]

MEMORY_TRAITS = [
    "memory_condensation",
    "inheritance_decay",
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AgentTraits:
    """Agent personality traits (22 total)."""

    # Core Risk (4)
    risk_tolerance: float = 0.5
    hold_duration_bias: float = 0.5
    volatility_seeking: float = 0.5
    profit_target_greed: float = 0.5

    # Pattern Selection (2)
    win_rate_preference: float = 0.5
    momentum_vs_reversion: float = 0.5

    # Execution (1)
    entry_aggression: float = 0.5

    # Technical (1)
    lookback_preference: float = 0.5

    # Sentiment (3)
    sentiment_weight: float = 0.5
    news_reactivity: float = 0.5
    sentiment_contrarian: float = 0.5

    # Macro (2)
    funding_rate_sensitivity: float = 0.5
    correlation_awareness: float = 0.5

    # Decision Anchor (1) - Independent
    uncertainty_anchor: float = 0.5

    # Derived (3) - From anchors with ±5% noise
    drawdown_sensitivity: float = 0.5
    stop_loss_tightness: float = 0.5
    exit_aggression: float = 0.5

    # Threshold (3) - From uncertainty_anchor
    ai_assist_range: float = 0.2
    min_threshold: float = 0.3
    ai_threshold: float = 0.7

    # Memory (2)
    memory_condensation: float = 0.5
    inheritance_decay: float = 0.3


# =============================================================================
# Trait Generation
# =============================================================================


def generate_traits(
    seed: int,
    overrides: dict | None = None,
    trait_bias: dict | None = None,
) -> AgentTraits:
    """
    Generate agent traits from seed.

    Args:
        seed: Random seed for reproducibility.
        overrides: Optional dict of trait -> value to override (exact values).
        trait_bias: Optional dict of trait -> (min, max) tuples to constrain ranges.
                   Used to bias trait generation based on learnings from previous runs.

    Returns:
        AgentTraits with all 22 traits populated.
    """
    traits = AgentTraits()
    rng = seeded_random(seed)

    # Generate 14 independent traits
    for trait_name in INDEPENDENT_TRAITS:
        value = rng()

        # Apply trait bias (constrain to learned range)
        if trait_bias and trait_name in trait_bias:
            min_val, max_val = trait_bias[trait_name]
            value = min_val + value * (max_val - min_val)

        setattr(traits, trait_name, value)

    # Generate memory traits
    for trait_name in MEMORY_TRAITS:
        value = rng()
        setattr(traits, trait_name, value)

    # Apply overrides (exact values take precedence)
    if overrides:
        for trait_name, value in overrides.items():
            if hasattr(traits, trait_name):
                setattr(traits, trait_name, value)

    return traits


def derive_dependent_traits(traits: AgentTraits, seed: int) -> AgentTraits:
    """
    Derive dependent traits from anchor traits.

    Formulas (with ±5% noise):
    - drawdown_sensitivity = 1 - risk_tolerance + noise
    - stop_loss_tightness = 1 - risk_tolerance + noise
    - exit_aggression = 1 - hold_duration_bias + noise

    Args:
        traits: Traits with independent values set.
        seed: Seed for noise generation.

    Returns:
        Traits with derived values populated.
    """
    rng = seeded_random(seed)

    # Drawdown sensitivity (inverse of risk tolerance)
    noise1 = (rng() - 0.5) * 0.10  # ±5%
    traits.drawdown_sensitivity = _clamp(1 - traits.risk_tolerance + noise1)

    # Stop loss tightness (inverse of risk tolerance)
    noise2 = (rng() - 0.5) * 0.10
    traits.stop_loss_tightness = _clamp(1 - traits.risk_tolerance + noise2)

    # Exit aggression (inverse of hold duration)
    noise3 = (rng() - 0.5) * 0.10
    traits.exit_aggression = _clamp(1 - traits.hold_duration_bias + noise3)

    return traits


def derive_threshold_traits(uncertainty_anchor: float, seed: int) -> dict:
    """
    Derive threshold traits from uncertainty anchor.

    Args:
        uncertainty_anchor: Center point for thresholds (0-1).
        seed: Seed for range randomization.

    Returns:
        Dict with ai_assist_range, min_threshold, ai_threshold.
    """
    rng = seeded_random(seed)

    # AI assist range: 0.1 to 0.3
    ai_assist_range = 0.1 + rng() * 0.2

    # Calculate thresholds symmetric around anchor
    min_threshold = _clamp(uncertainty_anchor - ai_assist_range)
    ai_threshold = _clamp(uncertainty_anchor + ai_assist_range)

    return {
        "ai_assist_range": ai_assist_range,
        "min_threshold": min_threshold,
        "ai_threshold": ai_threshold,
    }


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to range."""
    return max(min_val, min(max_val, value))


# =============================================================================
# Trait Mutation
# =============================================================================


def mutate_traits(traits: AgentTraits, rate: float, seed: int) -> AgentTraits:
    """
    Mutate traits by ±10% with given probability.

    Args:
        traits: Original traits.
        rate: Mutation probability per trait (0-1).
        seed: Random seed.

    Returns:
        New AgentTraits with mutations applied.
    """
    from dataclasses import asdict

    # Create copy
    mutated = AgentTraits(**asdict(traits))
    rng = seeded_random(seed)

    # Only mutate independent and memory traits
    mutable_traits = INDEPENDENT_TRAITS + MEMORY_TRAITS

    for trait_name in mutable_traits:
        # Check if this trait should mutate
        if rng() < rate:
            current = getattr(mutated, trait_name)
            # ±10% mutation
            delta = (rng() - 0.5) * 0.2
            new_value = _clamp(current + delta)
            setattr(mutated, trait_name, new_value)

    return mutated


# =============================================================================
# Trait Crossover
# =============================================================================


def crossover_traits(parent_a: AgentTraits, parent_b: AgentTraits, seed: int) -> AgentTraits:
    """
    Create child traits from two parents.

    Uses uniform crossover: each trait randomly from either parent.

    Args:
        parent_a: First parent.
        parent_b: Second parent.
        seed: Random seed.

    Returns:
        New AgentTraits combining both parents.
    """
    child = AgentTraits()
    rng = seeded_random(seed)

    # Crossover independent and memory traits
    crossover_traits_list = INDEPENDENT_TRAITS + MEMORY_TRAITS

    for trait_name in crossover_traits_list:
        if rng() < 0.5:
            value = getattr(parent_a, trait_name)
        else:
            value = getattr(parent_b, trait_name)
        setattr(child, trait_name, value)

    return child


# =============================================================================
# Trading Parameter Formulas
# =============================================================================


def calculate_position_size(risk_tolerance: float) -> float:
    """
    Calculate position size from risk tolerance.

    Formula: 0.01 + risk_tolerance * 0.09 (1-10%)

    Args:
        risk_tolerance: Trait value 0-1.

    Returns:
        Position size as decimal (0.01 to 0.10).
    """
    return 0.01 + risk_tolerance * 0.09


def calculate_stop_loss_distance(stop_loss_tightness: float) -> float:
    """
    Calculate stop loss distance from tightness.

    Formula: 0.10 - stop_loss_tightness * 0.09 (1-10%, inverted)

    Args:
        stop_loss_tightness: Trait value 0-1.

    Returns:
        Stop loss distance as decimal (0.01 to 0.10).
    """
    return 0.10 - stop_loss_tightness * 0.09


def calculate_take_profit_distance(profit_target_greed: float) -> float:
    """
    Calculate take profit distance from greed.

    Formula: 0.02 + profit_target_greed * 0.18 (2-20%)

    Args:
        profit_target_greed: Trait value 0-1.

    Returns:
        Take profit distance as decimal (0.02 to 0.20).
    """
    return 0.02 + profit_target_greed * 0.18


def calculate_max_hold_duration_ms(hold_duration_bias: float) -> int:
    """
    Calculate max hold duration from hold bias.

    Formula: 3,600,000 + hold_duration_bias * 601,200,000 (1hr-7days)

    Args:
        hold_duration_bias: Trait value 0-1.

    Returns:
        Max hold duration in milliseconds.
    """
    one_hour = 3_600_000
    additional = 601_200_000  # ~7 days minus 1 hour
    return int(one_hour + hold_duration_bias * additional)


# =============================================================================
# Agent Naming - Multi-Dimensional Identity System
# =============================================================================

# Trait dimension analysis functions
# Each returns (dimension_name, score, descriptor) where score is 0-1
TRAIT_DIMENSIONS = {
    # Risk profile (how much risk they take)
    "risk": {
        "calc": lambda t: (t.risk_tolerance + t.profit_target_greed) / 2,
        "high": "Bold",  # high risk, high reward seeking
        "low": "Cautious",  # conservative, capital preservation
    },
    # Speed profile (how fast they trade)
    "speed": {
        "calc": lambda t: ((1 - t.hold_duration_bias) + t.exit_aggression + t.entry_aggression) / 3,
        "high": "Swift",  # quick trades, aggressive entry/exit
        "low": "Patient",  # holds positions, waits for setups
    },
    # Strategy style (momentum vs mean reversion)
    "style": {
        "calc": lambda t: t.momentum_vs_reversion,
        "high": "Trend",  # follows momentum
        "low": "Fade",  # mean reversion, contrarian
    },
    # Market awareness (sentiment/news sensitivity)
    "awareness": {
        "calc": lambda t: (t.sentiment_weight + t.news_reactivity) / 2,
        "high": "Social",  # follows crowd/news
        "low": "Technical",  # ignores noise, pure technicals
    },
    # Volatility preference
    "volatility": {
        "calc": lambda t: t.volatility_seeking,
        "high": "Volatile",  # seeks high volatility
        "low": "Stable",  # prefers calm markets
    },
}

# Threshold for what counts as "notable" in a dimension
NOTABLE_THRESHOLD_HIGH = 0.65
NOTABLE_THRESHOLD_LOW = 0.35

# Character names organized by personality archetype
# Each list has names that "feel" like that personality
ARCHETYPE_NAMES = {
    # Bold/Risk-taking names
    "Bold": ["Maverick", "Blaze", "Rex", "Ace", "Duke", "Titan", "Maximus", "Brutus", "Thor", "Spike"],
    "Cautious": [
        "Walter",
        "Eugene",
        "Milton",
        "Bernard",
        "Harold",
        "Norman",
        "Edgar",
        "Clarence",
        "Chester",
        "Herbert",
    ],
    # Speed-based names
    "Swift": ["Flash", "Dash", "Zippy", "Rocket", "Bolt", "Turbo", "Blitz", "Sonic", "Jet", "Speedy"],
    "Patient": ["Sage", "Willow", "Buddha", "Zen", "Sequoia", "Oak", "Stone", "River", "Moss", "Cliff"],
    # Style-based names
    "Trend": ["Rider", "Surfer", "Wave", "Flow", "Current", "Drift", "Glide", "Coast", "Stream", "Tide"],
    "Fade": ["Contra", "Rebel", "Flip", "Counter", "Reverse", "Switch", "Pivot", "Twist", "Bounce", "Snap"],
    # Awareness-based names
    "Social": ["Echo", "Pulse", "Buzz", "Vibe", "Hype", "Scout", "Radar", "Signal", "Beacon", "Herald"],
    "Technical": ["Quant", "Logic", "Binary", "Sigma", "Delta", "Vector", "Matrix", "Cipher", "Axiom", "Vertex"],
    # Volatility-based names
    "Volatile": ["Storm", "Chaos", "Tempest", "Thunder", "Cyclone", "Tornado", "Havoc", "Fury", "Rage", "Inferno"],
    "Stable": ["Anchor", "Harbor", "Haven", "Bastion", "Fortress", "Granite", "Steel", "Diamond", "Bedrock", "Pillar"],
    # Balanced/neutral names
    "Balanced": ["Atlas", "Phoenix", "Orion", "Nova", "Cosmo", "Zenith", "Apex", "Prime", "Core", "Nexus"],
}


def analyze_agent_identity(traits: AgentTraits) -> dict:
    """
    Analyze agent traits to determine multi-dimensional identity.

    Returns dict with:
        - dimensions: {name: (score, descriptor, is_notable)}
        - primary: Most extreme dimension
        - secondary: Second most extreme dimension
        - personality_summary: Human-readable summary
    """
    dimensions = {}
    extremes = []  # (distance_from_center, dimension_name, descriptor, score)

    for dim_name, dim_config in TRAIT_DIMENSIONS.items():
        try:
            score = dim_config["calc"](traits)
            score = _clamp(score)

            # Determine descriptor and notability
            if score >= NOTABLE_THRESHOLD_HIGH:
                descriptor = dim_config["high"]
                is_notable = True
                distance = score - 0.5  # How far from neutral
            elif score <= NOTABLE_THRESHOLD_LOW:
                descriptor = dim_config["low"]
                is_notable = True
                distance = 0.5 - score
            else:
                # Neutral - use neither descriptor
                descriptor = "Balanced"
                is_notable = False
                distance = 0

            dimensions[dim_name] = {
                "score": score,
                "descriptor": descriptor,
                "is_notable": is_notable,
            }

            if is_notable:
                extremes.append((distance, dim_name, descriptor, score))

        except AttributeError:
            dimensions[dim_name] = {
                "score": 0.5,
                "descriptor": "Unknown",
                "is_notable": False,
            }

    # Sort by extremity (most extreme first)
    extremes.sort(reverse=True)

    # Get primary and secondary notable dimensions
    primary = extremes[0] if len(extremes) > 0 else (0, "risk", "Balanced", 0.5)
    secondary = extremes[1] if len(extremes) > 1 else None

    # Build personality summary
    if len(extremes) == 0:
        summary = "A balanced generalist trader"
    elif len(extremes) == 1:
        summary = f"A {primary[2].lower()} trader"
    else:
        summary = f"A {primary[2].lower()}, {secondary[2].lower()} trader"

    return {
        "dimensions": dimensions,
        "primary": primary,
        "secondary": secondary,
        "notable_count": len(extremes),
        "personality_summary": summary,
    }


def get_agent_name_prefix(**trait_values) -> str:
    """
    Get agent name prefix based on trait values.

    Uses multi-dimensional analysis to create a more descriptive name.
    Format: {PRIMARY}{SECONDARY} if both notable, else {PRIMARY}

    Examples:
        - BoldSwift (high risk + fast trading)
        - FadeTechnical (mean reversion + ignores sentiment)
        - PatientTrend (slow + momentum following)
        - Cautious (only one notable dimension)

    Args:
        **trait_values: Trait name -> value pairs.

    Returns:
        Prefix string combining notable traits.
    """
    # Create traits object
    traits = AgentTraits()
    for name, value in trait_values.items():
        if hasattr(traits, name):
            setattr(traits, name, value)

    # Analyze identity
    identity = analyze_agent_identity(traits)

    # Build name from notable dimensions
    if identity["notable_count"] == 0:
        return "Balanced"
    elif identity["notable_count"] == 1:
        return identity["primary"][2]
    else:
        # Combine primary and secondary
        primary_desc = identity["primary"][2]
        secondary_desc = identity["secondary"][2]
        return f"{primary_desc}{secondary_desc}"


def generate_character_name(traits: AgentTraits, seed: int) -> str:
    """
    Generate a character-style name based on agent traits.

    Format: {Descriptor}_{Descriptor}_{CharacterName}

    Examples:
        - Cautious_Trending_Walter
        - Bold_Swift_Maverick
        - Patient_Fade_Sage
        - Stable_Technical_Anchor

    Args:
        traits: Agent traits object.
        seed: Random seed for name selection.

    Returns:
        Character-style name string.
    """
    from Fast_Swarm.local_agents.shared.rng import seeded_random

    identity = analyze_agent_identity(traits)
    rng = seeded_random(seed)

    # Get descriptors from notable dimensions (up to 2)
    descriptors = []
    if identity["notable_count"] >= 1:
        descriptors.append(identity["primary"][2])
    if identity["notable_count"] >= 2:
        descriptors.append(identity["secondary"][2])

    # If no notable dimensions, use "Balanced"
    if not descriptors:
        descriptors = ["Balanced"]

    # Pick a character name from the primary archetype
    primary_archetype = descriptors[0]
    name_pool = ARCHETYPE_NAMES.get(primary_archetype, ARCHETYPE_NAMES["Balanced"])

    # Use seed to pick deterministically from the pool
    name_index = int(rng() * len(name_pool))
    character_name = name_pool[name_index]

    # Build the full name: Descriptor_Descriptor_Name or Descriptor_Name
    if len(descriptors) == 2:
        return f"{descriptors[0]}_{descriptors[1]}_{character_name}"
    else:
        return f"{descriptors[0]}_{character_name}"


def generate_agent_name(prefix: str, generation: int, seed: int) -> str:
    """
    Generate full agent name (legacy format).

    Format: {PREFIX}-G{generation}-{hex_hash}

    Args:
        prefix: Name prefix (e.g., "BoldSwift").
        generation: Agent generation number.
        seed: Seed for hash generation.

    Returns:
        Full agent name (e.g., "BoldSwift-G3-7F3").
    """
    # Generate 3-char hex hash from seed
    hex_hash = format(seed & 0xFFF, "03X")
    return f"{prefix}-G{generation}-{hex_hash}"


def generate_full_agent_name(traits: AgentTraits, generation: int, seed: int) -> str:
    """
    Generate a full character-style agent name with generation tag.

    Format: {Descriptor}_{Descriptor}_{CharacterName}_G{gen}

    Examples:
        - Cautious_Trend_Walter_G3
        - Bold_Swift_Maverick_G1
        - Patient_Fade_Sage_G7

    Args:
        traits: Agent traits object.
        generation: Agent generation number.
        seed: Random seed for name selection.

    Returns:
        Full character-style name with generation.
    """
    base_name = generate_character_name(traits, seed)
    return f"{base_name}_G{generation}"


# Legacy single-prefix system (kept for reference/compatibility)
NAME_PREFIX_SCORES_LEGACY = {
    "ALPHA": lambda t: t.risk_tolerance + t.profit_target_greed,
    "STEADY": lambda t: (1 - t.risk_tolerance) + t.drawdown_sensitivity,
    "SWIFT": lambda t: (1 - t.hold_duration_bias) + t.exit_aggression,
    "PATIENT": lambda t: t.hold_duration_bias + (1 - t.exit_aggression),
    "MOMENTUM": lambda t: t.momentum_vs_reversion + t.volatility_seeking,
    "REVERT": lambda t: (1 - t.momentum_vs_reversion) + (1 - t.volatility_seeking),
    "SOCIAL": lambda t: t.sentiment_weight + t.news_reactivity,
    "STOIC": lambda t: (1 - t.sentiment_weight) + (1 - t.news_reactivity),
}
