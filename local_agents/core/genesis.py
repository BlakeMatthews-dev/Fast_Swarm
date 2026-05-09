"""
Agent Genesis - Spawning New Agents.

Handles:
1. Trait generation (22 traits)
2. Pattern self-selection via LLM
3. Philosophy generation
4. Agent naming (8 prefixes)
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict

from Fast_Swarm.local_agents.config import Config
from Fast_Swarm.local_agents.core.state import AgentDatabase, AgentRecord
from Fast_Swarm.local_agents.core.traits import (
    AgentTraits,
    derive_dependent_traits,
    derive_threshold_traits,
    generate_full_agent_name,
    generate_traits,
)
from Fast_Swarm.local_agents.shared.rng import seeded_random

# =============================================================================
# Exit Condition Generation (when patterns lack them)
# =============================================================================


def generate_exit_conditions(entry_conditions: list, traits: "AgentTraits" = None, seed: int = None) -> list:
    """
    Generate intelligent exit conditions based on entry conditions and agent traits.

    Combines:
    1. Exit STRATEGY selection (trailing, ATR, dynamic, scaled, breakeven)
    2. Indicator-based exit signals (opposite of entry conditions)

    Available exit strategies (from engine.py):
    - FIXED: Fixed TP/SL only
    - TRAILING_2PCT/3PCT/5PCT: Fixed trailing stop
    - DYNAMIC_TRAIL: Logarithmic widening trail (2% → 12%)
    - SCALED_OUT: 25% exit at each milestone
    - BREAKEVEN_TRAIL: Move to breakeven after +5%
    - ATR_TRAIL: 2x ATR trailing stop (adapts to volatility!)

    Args:
        entry_conditions: List of entry condition dicts
        traits: Agent traits (used to pick appropriate strategy)
        seed: Random seed for deterministic selection

    Returns:
        List of exit condition dicts with strategy AND indicator conditions
    """
    import random

    if seed:
        random.seed(seed)

    # === Step 1: Choose EXIT STRATEGY based on traits ===
    # Map trait profiles to appropriate exit strategies
    EXIT_STRATEGIES = [
        {
            "strategy": "dynamic_trail",
            "description": "Logarithmic trailing (2%→12%)",
            "traits_match": lambda t: t and t.profit_target_greed > 0.6,  # Greedy = let winners run
        },
        {
            "strategy": "atr_trail",
            "description": "ATR-based trailing (volatility adaptive)",
            "atr_multiplier": 2.0,
            "traits_match": lambda t: t and t.volatility_seeking > 0.5,  # Volatility seekers use ATR
        },
        {
            "strategy": "scaled_out",
            "description": "25% exit at each milestone",
            "scale_points": [5, 10, 20, 50],  # % profit milestones
            "traits_match": lambda t: t and t.risk_tolerance < 0.4,  # Risk averse = scale out
        },
        {
            "strategy": "breakeven_trail",
            "description": "Move to breakeven after +5%, then trail",
            "breakeven_trigger_pct": 5.0,
            "trail_after_breakeven": 3.0,
            "traits_match": lambda t: t and hasattr(t, "loss_aversion") and t.loss_aversion > 0.6,
        },
        {
            "strategy": "trailing_3pct",
            "description": "3% trailing stop",
            "trailing_pct": 3.0,
            "traits_match": lambda t: True,  # Default fallback
        },
    ]

    # Pick strategy based on traits or random
    chosen_strategy = None
    if traits:
        for strat in EXIT_STRATEGIES:
            if strat["traits_match"](traits):
                chosen_strategy = strat
                break
    if not chosen_strategy:
        # Random selection weighted toward better strategies
        weights = [0.25, 0.25, 0.15, 0.15, 0.20]  # dynamic, atr, scaled, breakeven, trailing
        chosen_strategy = random.choices(EXIT_STRATEGIES, weights=weights, k=1)[0]

    # === Step 2: Generate indicator-based exit conditions ===
    indicator_exits = []

    INDICATOR_INVERSIONS = {
        "rsi": {"type": "oscillator", "low": 30, "high": 70},
        "rsi_14": {"type": "oscillator", "low": 30, "high": 70},
        "rsi_7": {"type": "oscillator", "low": 30, "high": 70},
        "stoch_k": {"type": "oscillator", "low": 20, "high": 80},
        "stoch_d": {"type": "oscillator", "low": 20, "high": 80},
        "kdj_k": {"type": "oscillator", "low": 20, "high": 80},
        "mfi_14": {"type": "oscillator", "low": 20, "high": 80},
        "cci_20": {"type": "oscillator", "low": -100, "high": 100},
        "cmo_14": {"type": "oscillator", "low": -50, "high": 50},
        "macd_line": {"type": "signed"},
        "macd_histogram": {"type": "signed"},
        "adx_14": {"type": "trend_strength", "exit_below": 20},
        "pvo": {"type": "signed"},
        "trix_30": {"type": "signed"},
    }

    for cond in entry_conditions:
        indicator = cond.get("indicator", "")
        inv_rule = INDICATOR_INVERSIONS.get(indicator.lower())

        exit_cond = {"indicator": indicator}

        if inv_rule:
            if inv_rule["type"] == "oscillator":
                low, high = inv_rule["low"], inv_rule["high"]
                if "operator" in cond:
                    op = cond["operator"]
                    val = cond.get("value", 50)
                    if op == "<" and val <= low + 10:
                        exit_cond["operator"] = ">"
                        exit_cond["value"] = high
                    elif op == ">" and val >= high - 10:
                        exit_cond["operator"] = "<"
                        exit_cond["value"] = low
                    else:
                        exit_cond["operator"] = "<" if op == ">" else ">"
                        exit_cond["value"] = high if val < 50 else low
                elif "min" in cond:
                    exit_cond["min"] = high - 10
                    exit_cond["max"] = high + 10
            elif inv_rule["type"] == "signed":
                if "operator" in cond:
                    op = cond["operator"]
                    val = cond.get("value", 0)
                    exit_cond["operator"] = "<" if op == ">" else ">"
                    exit_cond["value"] = -val if val != 0 else 0.01
            elif inv_rule["type"] == "trend_strength":
                exit_cond["operator"] = "<"
                exit_cond["value"] = inv_rule["exit_below"]
        else:
            # Unknown: simple opposite
            if "operator" in cond:
                op = cond["operator"]
                val = cond.get("value", 0)
                # Convert to float if string, skip if not numeric
                try:
                    val = float(val) if isinstance(val, str) else val
                    exit_cond["operator"] = "<" if op == ">" else ">"
                    exit_cond["value"] = val * (0.5 if op == ">" else 1.5) if val > 0 else -val
                except (ValueError, TypeError):
                    continue  # Skip non-numeric conditions

        if "operator" in exit_cond or "min" in exit_cond:
            indicator_exits.append(exit_cond)

    # === Step 3: Combine strategy + indicator exits ===
    result = [
        {
            "exit_strategy": chosen_strategy["strategy"],
            "description": chosen_strategy["description"],
            **{k: v for k, v in chosen_strategy.items() if k not in ["strategy", "description", "traits_match"]},
        }
    ]

    # Add indicator conditions (exit when ANY is met)
    result.extend(indicator_exits)

    return result


# =============================================================================
# Affinity-Based Pattern Selection (NOT Random Shuffle)
# =============================================================================


def calculate_pattern_affinity(traits: AgentTraits, pattern: dict) -> float:
    """
    Calculate affinity score between agent traits and a pattern.

    IMPORTANT: This score is used ONLY for pre-filtering/sorting the candidate list.
    The AI receives raw trait/pattern data, NOT the affinity score.

    This ensures deterministic pattern selection (given same traits).

    Args:
        traits: Agent traits.
        pattern: Pattern dict with type, volatility, win_rate, etc.

    Returns:
        Affinity score (higher = better match).
    """
    score = 1.0

    # Get pattern metadata
    pattern_type = pattern.get("type", "").lower()
    pattern_volatility = (
        pattern.get("volatility", "medium").lower()
        if isinstance(pattern.get("volatility"), str)
        else pattern.get("volatility", 0.5)
    )
    pattern_win_rate = pattern.get("win_rate_pct", 50) or pattern.get("win_rate", 0.5)

    # Normalize win_rate to 0-1 if given as percentage
    if pattern_win_rate > 1:
        pattern_win_rate = pattern_win_rate / 100

    # === Momentum vs Reversion Alignment ===
    # High momentum_vs_reversion trait → prefers momentum patterns
    # Low momentum_vs_reversion trait → prefers mean reversion patterns
    if "momentum" in pattern_type or "trend" in pattern_type:
        score *= 0.5 + traits.momentum_vs_reversion  # 0.5-1.5x
    elif "reversion" in pattern_type or "mean" in pattern_type:
        score *= 1.5 - traits.momentum_vs_reversion  # 0.5-1.5x

    # === Volatility Alignment ===
    # High volatility_seeking trait → prefers high volatility patterns
    if isinstance(pattern_volatility, str):
        if pattern_volatility == "high":
            score *= 0.5 + traits.volatility_seeking
        elif pattern_volatility == "low":
            score *= 1.5 - traits.volatility_seeking
    else:
        # Numeric volatility - closer to trait is better
        vol_diff = abs(traits.volatility_seeking - pattern_volatility)
        score *= 1.0 - vol_diff * 0.5  # 0.5-1.0x

    # === Win Rate Preference ===
    # High win_rate_preference trait → prefers high win rate patterns
    if traits.win_rate_preference > 0.6 and pattern_win_rate > 0.55:
        score *= 1.2
    elif traits.win_rate_preference < 0.4 and pattern_win_rate < 0.50:
        # Lower WR patterns might have higher payoff
        score *= 1.1

    # === Risk Tolerance Alignment ===
    # Just a small bonus for risk-aligned patterns
    if hasattr(traits, "risk_tolerance"):
        if (traits.risk_tolerance > 0.7 and pattern.get("aggressive", False)) or (
            traits.risk_tolerance < 0.3 and pattern.get("conservative", False)
        ):
            score *= 1.1

    return max(0.1, score)  # Minimum score to avoid zeros


def sort_patterns_by_affinity(
    traits: AgentTraits,
    patterns: list[dict],
) -> list[dict]:
    """
    Sort patterns by affinity score (deterministic, not random).

    Used to pre-filter patterns before showing to AI for selection.
    The AI receives raw pattern data, NOT the affinity scores.

    Args:
        traits: Agent traits.
        patterns: List of pattern dicts.

    Returns:
        Patterns sorted by affinity (highest first).
    """
    # Calculate affinity for each pattern
    scored = [(calculate_pattern_affinity(traits, p), p) for p in patterns]

    # Sort by affinity descending (deterministic)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return patterns without scores (AI sees raw data)
    return [p for _, p in scored]


def get_top_patterns_for_spawn(
    traits: AgentTraits,
    patterns: list[dict],
    count: int = 15,
) -> list[dict]:
    """
    Get top N patterns for spawn by affinity.

    Pipeline:
    1. Sort all patterns by affinity
    2. Take top N
    3. Return raw pattern data (no affinity scores)

    Args:
        traits: Agent traits.
        patterns: Available patterns.
        count: Number of patterns to return.

    Returns:
        Top N patterns by trait affinity.
    """
    sorted_patterns = sort_patterns_by_affinity(traits, patterns)
    return sorted_patterns[:count]


def compute_regime_fitness_from_patterns(patterns: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Compute current regime fitness status from pattern metadata.

    Aggregates fitness by regime from patterns that have regime data,
    then sorts to find which regimes are weakest.

    Args:
        patterns: Patterns with optional best_category and category_fitness fields.

    Returns:
        Tuple of (regime_fitness_list, weak_regimes_list)
        - regime_fitness_list: [{'name': 'crash', 'avg_fitness': 5.2}, ...]
        - weak_regimes_list: ['crash', 'bear', 'random_1m'] (bottom 5)
    """
    from collections import defaultdict

    regime_scores = defaultdict(list)

    for p in patterns:
        # Get regime data from pattern metadata
        best_cat = p.get("best_category")
        cat_fitness = p.get("category_fitness", 0)

        if best_cat and cat_fitness is not None:
            regime_scores[best_cat].append(float(cat_fitness))

        # Also check fitness_by_regime if available
        fitness_by_regime = p.get("fitness_by_regime", {})
        if isinstance(fitness_by_regime, dict):
            for regime, data in fitness_by_regime.items():
                if isinstance(data, dict):
                    fitness = data.get("fitness", 0)
                elif isinstance(data, (int, float)):
                    fitness = data
                else:
                    continue
                regime_scores[regime].append(float(fitness))

    if not regime_scores:
        return [], []

    # Calculate averages
    regime_fitness = []
    for regime, scores in regime_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        regime_fitness.append(
            {
                "name": regime,
                "avg_fitness": avg,
                "sample_count": len(scores),
            }
        )

    # Sort by fitness ascending (weakest first)
    regime_fitness.sort(key=lambda x: x["avg_fitness"])

    # Get weak regimes (bottom 5 or those under 40 fitness)
    weak_regimes = [r["name"] for r in regime_fitness if r["avg_fitness"] < 40][:5]

    return regime_fitness, weak_regimes


def prepare_spawn_prompt_data(
    traits: AgentTraits,
    patterns: list[dict],
) -> dict:
    """
    Prepare data for spawn prompt.

    AI receives RAW trait/pattern data, NOT pre-computed affinity scores.
    This preserves information so AI can reason about alignment dimensions.
    Also includes dynamic regime fitness data computed from pattern metadata.

    Args:
        traits: Agent traits.
        patterns: Candidate patterns.

    Returns:
        Dict with traits, patterns, and regime fitness for prompt rendering.
    """
    # Compute regime fitness from pattern metadata
    regime_fitness, weak_regimes = compute_regime_fitness_from_patterns(patterns)

    return {
        "traits": asdict(traits),
        "patterns": patterns,  # Raw pattern data, no affinity scores
        "regime_fitness": regime_fitness,  # Dynamic regime status
        "weak_regimes": weak_regimes,  # Priority targets
    }


# =============================================================================
# Pattern Selection
# =============================================================================


def select_patterns_heuristic(
    traits: AgentTraits, available_patterns: list[dict], seed: int, count: int = 4
) -> list[dict]:
    """
    Heuristically select patterns matching agent traits (no LLM).

    Used for fast spawning during backtesting.

    Args:
        traits: Agent traits.
        available_patterns: List of pattern dicts with metadata.
        seed: Random seed.
        count: Number of patterns to select.

    Returns:
        List of {pattern_id, weight, reasoning}.
    """
    if not available_patterns:
        return []

    rng = seeded_random(seed)

    # Score patterns by trait alignment
    scored = []
    for pattern in available_patterns:
        score = 0.0

        # Win rate preference
        wr = pattern.get("win_rate_pct", 50)
        if traits.win_rate_preference > 0.6 and wr > 55:
            score += 0.3
        elif traits.win_rate_preference < 0.4 and wr < 50:
            score += 0.1  # Lower WR patterns might have higher payoff

        # Volatility seeking
        if pattern.get("volatility", "medium") == "high":
            score += traits.volatility_seeking * 0.3
        elif pattern.get("volatility", "medium") == "low":
            score += (1 - traits.volatility_seeking) * 0.3

        # Momentum vs reversion
        pattern_type = pattern.get("type", "").lower()
        if "momentum" in pattern_type or "trend" in pattern_type:
            score += traits.momentum_vs_reversion * 0.3
        elif "reversion" in pattern_type or "mean" in pattern_type:
            score += (1 - traits.momentum_vs_reversion) * 0.3

        # Add randomness for diversity
        score += rng() * 0.2

        scored.append((score, pattern))

    # Sort by score and take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [p for _, p in scored[:count]]

    # Calculate weights
    total_score = sum(s for s, _ in scored[:count])
    if total_score == 0:
        total_score = 1.0

    results = []
    for score, pattern in scored[:count]:
        weight = score / total_score
        results.append(
            {
                "pattern_id": pattern.get("pattern_id", pattern.get("id", str(uuid.uuid4()))),
                "weight": round(weight, 2),
                "reasoning": f"Aligned with traits (score: {score:.2f})",
            }
        )

    return results


def select_patterns_llm(
    traits: AgentTraits,
    available_patterns: list[dict],
    agent_name: str,
    llm_call: Callable[[str], str],
) -> tuple[list[dict], str | None]:
    """
    Select patterns using LLM (Ollama).

    NO HEURISTIC FALLBACK - LLM is always used for AI decisions.
    If LLM fails, raises an exception rather than silently falling back.

    Args:
        traits: Agent traits.
        available_patterns: Available patterns.
        agent_name: Agent name for prompt.
        llm_call: Function to call LLM with prompt.

    Returns:
        Tuple of (selections, philosophy).
        selections: List of {pattern_id, weight, reasoning}.
        philosophy: AI-generated trading philosophy or None.

    Raises:
        FileNotFoundError: If template not found.
        ImportError: If jinja2 not installed.
        RuntimeError: If LLM call fails or returns invalid response.
    """
    # Load template - REQUIRED, no fallback
    template_path = Config.PROMPTS_DIR / "birth_selection.j2"
    print(f"[Genesis:LLM] Template path: {template_path}")
    if not template_path.exists():
        raise FileNotFoundError(
            f"LLM template not found at {template_path}. LLM is required for pattern selection (no heuristic fallback)."
        )

    from jinja2 import Template

    template = Template(template_path.read_text())
    print("[Genesis:LLM] Template loaded successfully")

    # CRITICAL: Use affinity sort, NOT random shuffle
    # This ensures deterministic pattern selection based on trait alignment
    #
    # Pipeline:
    # 1. Filter: top 20% by fitness (spawn-eligible)
    # 2. Sort: by affinity score (trait alignment) - DETERMINISTIC
    # 3. Take: top 15 most aligned
    # 4. Pass: raw trait + pattern data (NO affinity score) to AI

    # Step 1: Sort by affinity, take top 50%
    sorted_by_affinity = sort_patterns_by_affinity(traits, available_patterns)
    top_50_pct_affinity = sorted_by_affinity[: max(1, len(sorted_by_affinity) // 2)]
    print(f"[Genesis:LLM] Step 1: Top 50% by affinity = {len(top_50_pct_affinity)} patterns")

    # Step 2: Sort those by fitness, take top 40%
    sorted_by_fitness = sorted(top_50_pct_affinity, key=lambda p: p.get("fitness_score", 0), reverse=True)
    top_40_pct_fitness = sorted_by_fitness[: max(1, len(sorted_by_fitness) * 2 // 5)]
    print(f"[Genesis:LLM] Step 2: Top 40% by fitness = {len(top_40_pct_fitness)} patterns")

    # Step 3: Shuffle for diversity
    import random

    shuffled = top_40_pct_fitness.copy()
    random.shuffle(shuffled)

    # Step 4: Take 20 for LLM
    top_patterns = shuffled[:20]
    print(f"[Genesis:LLM] Step 3-4: Shuffled, showing {len(top_patterns)} to LLM")

    # Step 4: Render prompt with RAW data (no affinity scores) + regime fitness
    prompt_data = prepare_spawn_prompt_data(traits, top_patterns)
    prompt = template.render(
        agent_name=agent_name,
        traits=prompt_data["traits"],
        patterns=prompt_data["patterns"],
        regime_fitness=prompt_data.get("regime_fitness", []),
        weak_regimes=prompt_data.get("weak_regimes", []),
    )
    print(f"[Genesis:LLM] Rendered prompt ({len(prompt)} chars)")
    if prompt_data.get("weak_regimes"):
        print(f"[Genesis:LLM] Weak regimes highlighted: {prompt_data['weak_regimes']}")

    # Call LLM - REQUIRED, no fallback
    print("[Genesis:LLM] Calling LLM...")
    response = llm_call(prompt)
    print(f"[Genesis:LLM] Got response ({len(response)} chars): {response[:200]}...")

    # Try to find JSON in response
    import re

    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        json_str = json_match.group()
        result = json.loads(json_str)
        raw_selections = result.get("selections", [])
        philosophy = result.get("philosophy", None)

        # Convert pattern_number to pattern_id (NUMBERED SELECTION)
        # This prevents LLM from hallucinating invalid pattern IDs
        selections = []
        for sel in raw_selections:
            # Support both old format (pattern_id) and new format (pattern_number)
            if "pattern_number" in sel:
                num = sel["pattern_number"]
                # Validate number is in range (1-indexed)
                if 1 <= num <= len(top_patterns):
                    pattern = top_patterns[num - 1]  # Convert to 0-indexed
                    selections.append(
                        {
                            "pattern_id": pattern["pattern_id"],
                            "weight": sel.get("weight", 1.0 / len(raw_selections)),
                            "reasoning": sel.get("reasoning", ""),
                        }
                    )
                    print(f"[Genesis:LLM] Selection #{num} -> {pattern['pattern_id']}")
                else:
                    print(f"[Genesis:LLM] WARNING: Invalid pattern_number {num}, skipping")
            elif "pattern_id" in sel:
                # Legacy format - validate pattern_id exists
                pid = sel["pattern_id"]
                valid_ids = {p["pattern_id"] for p in top_patterns}
                if pid in valid_ids:
                    selections.append(sel)
                    print(f"[Genesis:LLM] Legacy selection: {pid}")
                else:
                    print(f"[Genesis:LLM] WARNING: Invalid pattern_id {pid}, skipping")

        print(f"[Genesis:LLM] Validated {len(selections)} selections from LLM")
        if philosophy:
            print(f"[Genesis:LLM] Got AI philosophy: {philosophy[:100]}...")
        if selections:
            return selections, philosophy

    # No fallback - raise error if LLM response is invalid
    raise RuntimeError(
        f"LLM returned invalid response (no valid JSON with selections). "
        f"Response: {response[:500]}... "
        "LLM is required for pattern selection (no heuristic fallback)."
    )


# =============================================================================
# Philosophy Generation
# =============================================================================


def generate_philosophy_heuristic(traits: AgentTraits) -> str:
    """Generate trading philosophy from traits (no LLM)."""
    parts = []

    # Risk style
    if traits.risk_tolerance > 0.7:
        parts.append("I embrace volatility and size positions aggressively when conviction is high")
    elif traits.risk_tolerance < 0.3:
        parts.append("I prioritize capital preservation with conservative position sizing")
    else:
        parts.append("I balance risk and reward with measured position sizes")

    # Trading style
    if traits.momentum_vs_reversion > 0.7:
        parts.append("riding trends until momentum fades")
    elif traits.momentum_vs_reversion < 0.3:
        parts.append("fading extremes when mean reversion signals appear")
    else:
        parts.append("adapting between momentum and reversion as conditions warrant")

    # Time horizon
    if traits.hold_duration_bias > 0.7:
        parts.append("I hold positions patiently, letting winners run")
    elif traits.hold_duration_bias < 0.3:
        parts.append("I take quick profits and cut losses fast")

    return ". ".join(parts) + "."


def generate_philosophy_llm(
    traits: AgentTraits,
    patterns: list[dict],
    agent_name: str,
    llm_call: Callable[[str], str],
) -> str:
    """
    Generate trading philosophy using LLM.

    NO HEURISTIC FALLBACK - LLM is always used for AI decisions.
    If LLM fails, raises an exception rather than silently falling back.

    Raises:
        FileNotFoundError: If template not found.
        RuntimeError: If LLM call fails.
    """
    template_path = Config.PROMPTS_DIR / "philosophy.j2"
    if not template_path.exists():
        raise FileNotFoundError(
            f"Philosophy template not found at {template_path}. "
            "LLM is required for philosophy generation (no heuristic fallback)."
        )

    from jinja2 import Template

    template = Template(template_path.read_text())

    prompt = template.render(
        agent_name=agent_name,
        traits=asdict(traits),
        patterns=patterns,
    )

    response = llm_call(prompt)
    try:
        result = json.loads(response)
        philosophy = result.get("philosophy")
        if philosophy:
            return philosophy
        raise RuntimeError("LLM response missing 'philosophy' field")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned invalid JSON: {e}. Response: {response[:500]}...")


# =============================================================================
# Agent Spawning
# =============================================================================


def spawn_agent(
    seed: int,
    available_patterns: list[dict],
    generation: int = 1,
    parent_a_id: str | None = None,
    parent_b_id: str | None = None,
    trait_overrides: dict | None = None,
    trait_bias: dict | None = None,
    use_llm: bool = True,  # DEFAULT TO TRUE - Always use LLM
    llm_call: Callable[[str], str] | None = None,
    db: AgentDatabase | None = None,
) -> AgentRecord:
    """
    Spawn a new agent.

    NOTE: LLM is REQUIRED for pattern selection and philosophy generation.
    Set use_llm=True (default) and provide llm_call function.
    No heuristic fallback is available.

    Args:
        seed: Random seed for reproducibility.
        available_patterns: Patterns agent can choose from.
        generation: Generation number.
        parent_a_id: First parent ID (for bred agents).
        parent_b_id: Second parent ID.
        trait_overrides: Override specific traits.
        trait_bias: Dict of trait -> (min, max) to constrain ranges (from learnings).
        use_llm: Use LLM for pattern selection and philosophy (default: True).
        llm_call: LLM call function (REQUIRED when use_llm=True).
        db: Database instance.

    Returns:
        Created AgentRecord.

    Raises:
        ValueError: If use_llm=True but llm_call is not provided.
    """
    # Step 1: Generate traits (with optional bias from learnings)
    traits = generate_traits(seed, trait_overrides, trait_bias=trait_bias)

    # Step 2: Derive dependent traits
    traits = derive_dependent_traits(traits, seed + 1)

    # Step 3: Derive threshold traits
    threshold_traits = derive_threshold_traits(traits.uncertainty_anchor, seed + 2)
    traits.ai_assist_range = threshold_traits["ai_assist_range"]
    traits.min_threshold = threshold_traits["min_threshold"]
    traits.ai_threshold = threshold_traits["ai_threshold"]

    # Step 4: Generate character-style name
    agent_name = generate_full_agent_name(traits, generation, seed)

    # Step 5: Select patterns (LLM REQUIRED - no heuristic fallback)
    print(f"[Genesis] Pattern selection: use_llm={use_llm}, llm_call={'provided' if llm_call else 'None'}")

    if use_llm:
        if llm_call is None:
            raise ValueError(
                "LLM is required for pattern selection but llm_call was not provided. "
                "Pass a valid llm_call function or set use_llm=False (not recommended)."
            )
        print(f"[Genesis] Calling LLM for pattern selection with {len(available_patterns)} patterns...")
        selections, llm_philosophy = select_patterns_llm(traits, available_patterns, agent_name, llm_call)
        print(f"[Genesis] LLM returned {len(selections)} selections")
    else:
        print("[Genesis] WARNING: Using deprecated heuristic selection (use_llm=False)")
        print("[Genesis] LLM is strongly recommended for all AI decisions")
        selections = select_patterns_heuristic(traits, available_patterns, seed + 3)
        llm_philosophy = None

    pattern_ids = [s["pattern_id"] for s in selections]
    pattern_weights = {s["pattern_id"]: s["weight"] for s in selections}

    # Step 5b: Create COPIES of selected patterns (agents own their patterns!)
    # This is critical - agents store full pattern data, not just references
    patterns_by_id = {p["pattern_id"]: p for p in available_patterns}
    pattern_copies = []
    for sel in selections:
        pid = sel["pattern_id"]
        if pid in patterns_by_id:
            # Deep copy the pattern data
            original = patterns_by_id[pid]
            entry_conds = original.get("entry_conditions", [])
            exit_conds = original.get("exit_conditions", {})

            # Generate exit conditions if pattern lacks them!
            # This is CRITICAL - patterns without exits can never close trades
            if not exit_conds or exit_conds == {} or exit_conds == []:
                exit_conds = generate_exit_conditions(
                    entry_conditions=entry_conds,
                    traits=traits,
                    seed=hash(pid) % 10000,  # Deterministic per pattern
                )
                print(
                    f"[Genesis] Generated exit conditions for {pid}: {exit_conds[0].get('exit_strategy', 'indicator')}"
                )

            pattern_copy = {
                "pattern_id": pid,
                "name": original.get("name", pid),
                "entry_conditions": entry_conds,
                "exit_conditions": exit_conds,
                "weight": sel.get("weight", 1.0),
                "reasoning": sel.get("reasoning", ""),
                # Copy fitness metadata for reference
                "fitness_score": original.get("fitness_score", 0),
                "win_rate": original.get("win_rate", original.get("win_rate_pct", 50)),
                "type": original.get("type", original.get("origin", "unknown")),
            }
            pattern_copies.append(pattern_copy)
        else:
            print(f"[Genesis] WARNING: Pattern {pid} not found in available_patterns")

    # Step 6: Generate philosophy (LLM REQUIRED when use_llm=True)
    if llm_philosophy:
        philosophy = llm_philosophy
        print("[Genesis] Using AI-generated philosophy from birth selection")
    elif use_llm and llm_call:
        philosophy = generate_philosophy_llm(traits, selections, agent_name, llm_call)
    else:
        print("[Genesis] WARNING: Using deprecated heuristic philosophy")
        philosophy = generate_philosophy_heuristic(traits)

    # Step 7: Create database record
    if db is None:
        db = AgentDatabase()

    record = db.create_agent(
        agent_name=agent_name,
        traits=traits,
        pattern_ids=pattern_ids,
        pattern_copies=pattern_copies,  # Full pattern data!
        generation=generation,
        parent_a_id=parent_a_id,
        parent_b_id=parent_b_id,
        pattern_weights=pattern_weights,
        trading_philosophy=philosophy,
    )

    return record


def spawn_child(
    parent_a: AgentRecord,
    parent_b: AgentRecord,
    seed: int,
    available_patterns: list[dict],
    mutation_rate: float = 0.10,
    use_llm: bool = True,  # DEFAULT TO TRUE - Always use LLM
    llm_call: Callable[[str], str] | None = None,
    db: AgentDatabase | None = None,
) -> AgentRecord:
    """
    Spawn a child agent from two parents.

    Uses crossover + mutation for traits.
    LLM is REQUIRED for pattern selection (no heuristic fallback).

    Args:
        parent_a: First parent.
        parent_b: Second parent.
        seed: Random seed.
        available_patterns: Available patterns.
        mutation_rate: Mutation probability per trait.
        use_llm: Use LLM for pattern selection (default: True).
        llm_call: LLM call function (REQUIRED when use_llm=True).
        db: Database instance.

    Returns:
        Child AgentRecord.

    Raises:
        ValueError: If use_llm=True but llm_call is not provided.
    """
    from Fast_Swarm.local_agents.core.traits import crossover_traits, mutate_traits

    # Reconstruct parent traits
    traits_a = AgentTraits(**parent_a.traits)
    traits_b = AgentTraits(**parent_b.traits)

    # Crossover
    child_traits = crossover_traits(traits_a, traits_b, seed)

    # Mutation
    child_traits = mutate_traits(child_traits, mutation_rate, seed + 1)

    # Derive dependent traits fresh
    child_traits = derive_dependent_traits(child_traits, seed + 2)

    # Calculate generation
    child_generation = max(parent_a.generation, parent_b.generation) + 1

    # Spawn with inherited traits
    return spawn_agent(
        seed=seed + 3,
        available_patterns=available_patterns,
        generation=child_generation,
        parent_a_id=parent_a.agent_id,
        parent_b_id=parent_b.agent_id,
        trait_overrides=asdict(child_traits),
        use_llm=use_llm,
        llm_call=llm_call,
        db=db,
    )


# =============================================================================
# Population Initialization
# =============================================================================


def initialize_population(
    population_size: int,
    available_patterns: list[dict],
    base_seed: int = 42,
    use_llm: bool = True,  # DEFAULT TO TRUE - Always use LLM
    llm_call: Callable[[str], str] | None = None,
    db: AgentDatabase | None = None,
    trait_bias: dict | None = None,
) -> list[AgentRecord]:
    """
    Initialize a population of agents.

    LLM is REQUIRED for pattern selection (no heuristic fallback).

    Args:
        population_size: Number of agents to spawn.
        available_patterns: Available patterns.
        base_seed: Base seed for reproducibility.
        use_llm: Use LLM for pattern selection (default: True).
        llm_call: LLM call function (REQUIRED when use_llm=True).
        db: Database instance.
        trait_bias: Dict of trait -> (min, max) to constrain ranges (from learnings).

    Returns:
        List of AgentRecords.

    Raises:
        ValueError: If use_llm=True but llm_call is not provided.
    """
    population = []

    for i in range(population_size):
        agent = spawn_agent(
            seed=base_seed + i * 1000,
            available_patterns=available_patterns,
            generation=1,
            use_llm=use_llm,
            llm_call=llm_call,
            db=db,
            trait_bias=trait_bias,
        )
        population.append(agent)

    return population
