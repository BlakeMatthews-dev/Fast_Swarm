"""
Specialist Fitness Model V4.

100-point scoring system for specialist agents:
- Specialist Depth (40 pts): Performance in best regime
- Risk Discipline (35 pts): Safety outside best regime
- Signal Quality (20 pts): Is the edge real?
- Uniqueness (5 pts): Tiebreaker for diversity

Key changes from V3:
- Hard EV gate (0.0 for EV <= 0, not 0.35)
- Diminishing returns normalization (not linear)
- Specialist focus (agents excel in ONE regime)
- Interaction penalties (dangerous combinations)
"""

import math

from Fast_Swarm.Metrics.metrics_constants import (
    CLASSIFICATION_MIN_SCORE,
    EV_BREAKPOINTS,
    INTERACTION_PENALTIES,
    NON_SPECIALIST_REGIMES,
    RISK_DISCIPLINE_THRESHOLDS,
    SPECIALIST_DEPTH_SUBWEIGHTS,
    SPECIALIST_REGIMES,
    WEIGHTS_V4,
)
from Fast_Swarm.Metrics.normalization import diminishing_returns
from Fast_Swarm.Metrics.signal_quality import calculate_signal_quality


# =============================================================================
# EV Gate (Hard Gate - Fixed Bug)
# =============================================================================


def ev_multiplier(ev_pct: float) -> float:
    """
    EV gate multiplier.

    HARD GATE: EV <= 0 -> 0.0 (not 0.35 like the old bug).
    Smooth interpolation for positive EV.

    Args:
        ev_pct: Expectancy percentage.

    Returns:
        Multiplier [0.0, 1.5].
    """
    if not math.isfinite(ev_pct):
        return 0.0

    if ev_pct <= 0:
        return 0.0  # HARD GATE

    # Find interpolation segment
    for i in range(len(EV_BREAKPOINTS) - 1):
        ev_low, mult_low = EV_BREAKPOINTS[i]
        ev_high, mult_high = EV_BREAKPOINTS[i + 1]

        if ev_pct <= ev_high:
            if ev_high == ev_low:
                return mult_high
            ratio = (ev_pct - ev_low) / (ev_high - ev_low)
            return mult_low + ratio * (mult_high - mult_low)

    # Above all breakpoints
    return 1.5


# =============================================================================
# Specialist Depth (40 pts)
# =============================================================================


def calculate_specialist_depth(metrics) -> float:
    """
    Score agent's performance in their specialist regime.

    Components (sum to 40):
    - Sortino: 12 pts (diminishing returns)
    - Alpha: 10 pts (linear)
    - Expectancy: 8 pts (linear)
    - Exit efficiency: 5 pts (linear)
    - Payoff ratio: 5 pts (linear)

    Args:
        metrics: Object with sortino, alpha_pct, expectancy_pct,
                exit_efficiency, payoff_ratio attributes.

    Returns:
        Score 0.0-40.0.
    """
    score = 0.0
    weights = SPECIALIST_DEPTH_SUBWEIGHTS

    # Sortino: diminishing returns (12 pts)
    sortino_val = getattr(metrics, "sortino", 0.0)
    sortino_normalized = diminishing_returns(max(0, sortino_val), saturation=4.0)
    score += sortino_normalized * weights["sortino"]

    # Alpha: linear normalization (10 pts)
    alpha_val = getattr(metrics, "alpha_pct", 0.0)
    alpha_normalized = max(0.0, min(1.0, (alpha_val + 100) / 200.0))  # -100..+100 -> 0..1
    score += alpha_normalized * weights["alpha"]

    # Expectancy: linear (8 pts)
    exp_val = getattr(metrics, "expectancy_pct", 0.0)
    exp_normalized = max(0.0, min(1.0, exp_val / 10.0))  # 0..10% -> 0..1
    score += exp_normalized * weights["expectancy"]

    # Exit efficiency: linear (5 pts)
    exit_val = getattr(metrics, "exit_efficiency", 0.5)
    exit_normalized = max(0.0, min(1.0, (exit_val - 0.3) / 0.6))  # 0.3..0.9 -> 0..1
    score += exit_normalized * weights["exit_efficiency"]

    # Payoff ratio: linear (5 pts)
    payoff_val = getattr(metrics, "payoff_ratio", 1.0)
    payoff_normalized = max(0.0, min(1.0, (payoff_val - 0.5) / 2.5))  # 0.5..3.0 -> 0..1
    score += payoff_normalized * weights["payoff_ratio"]

    return max(0.0, min(40.0, score))


# =============================================================================
# Risk Discipline (35 pts)
# =============================================================================


def calculate_risk_discipline(metrics) -> float:
    """
    Score agent's behavior OUTSIDE their specialist regime.

    Starts at 35 pts, subtract penalties for:
    - High exposure (trading too much when shouldn't)
    - High drawdown outside specialty
    - High risk of ruin
    - Long consecutive loss streaks

    Args:
        metrics: Object with exposure, max_drawdown_pct,
                risk_of_ruin, max_consecutive_losses attributes.

    Returns:
        Score 0.0-35.0.
    """
    score = 35.0
    thresholds = RISK_DISCIPLINE_THRESHOLDS

    # Exposure penalty: trading >30% outside specialty
    exposure = getattr(metrics, "exposure", 0.0)
    if exposure > thresholds["exposure_threshold"]:
        excess = exposure - thresholds["exposure_threshold"]
        penalty = min(thresholds["exposure_max_penalty"], excess * thresholds["exposure_penalty_rate"])
        score -= penalty

    # Drawdown penalty: >10% drawdown outside specialty
    max_dd = getattr(metrics, "max_drawdown_pct", 0.0)
    if max_dd > thresholds["drawdown_threshold"]:
        excess = max_dd - thresholds["drawdown_threshold"]
        penalty = min(thresholds["drawdown_max_penalty"], excess * thresholds["drawdown_penalty_rate"])
        score -= penalty

    # Risk of ruin penalty
    ruin = getattr(metrics, "risk_of_ruin", 0.0)
    if ruin > thresholds["ruin_threshold"]:
        penalty = min(thresholds["ruin_max_penalty"], ruin * thresholds["ruin_penalty_rate"])
        score -= penalty

    # Consecutive losses penalty
    consec = getattr(metrics, "max_consecutive_losses", 0)
    if consec > thresholds["consec_loss_threshold"]:
        excess = consec - thresholds["consec_loss_threshold"]
        penalty = min(thresholds["consec_loss_max_penalty"], excess * thresholds["consec_loss_penalty_rate"])
        score -= penalty

    return max(0.0, score)


# =============================================================================
# Uniqueness (5 pts - Tiebreaker)
# =============================================================================


def calculate_uniqueness(agent_returns: list[float], population_returns: list[float]) -> float:
    """
    Diversity bonus: low correlation with population.

    Uses R-squared: low R2 = independent signal = good.

    Args:
        agent_returns: Agent's return series.
        population_returns: Population average returns.

    Returns:
        Score 0.0-5.0.
    """
    if not agent_returns or not population_returns:
        return 2.5  # Neutral

    # Match lengths
    min_len = min(len(agent_returns), len(population_returns))
    if min_len < 5:
        return 2.5

    agent = agent_returns[:min_len]
    pop = population_returns[:min_len]

    # Calculate R-squared
    mean_a = sum(agent) / len(agent)
    mean_p = sum(pop) / len(pop)

    ss_res = sum((a - p) ** 2 for a, p in zip(agent, pop))
    ss_tot = sum((a - mean_a) ** 2 for a in agent)

    if ss_tot == 0:
        return 2.5  # No variance in agent returns

    r_squared = max(0.0, 1.0 - (ss_res / ss_tot))

    # Low R2 = independent = good
    return (1.0 - r_squared) * 5.0


# =============================================================================
# Interaction Penalties (Multiplicative)
# =============================================================================


def apply_interaction_penalties(
    specialist_sortino: float,
    specialist_max_dd: float,
    risk_of_ruin: float,
    specialist_trades: int,
) -> float:
    """
    Multiplicative penalties for dangerous metric combinations.

    Args:
        specialist_sortino: Sortino in specialist regime.
        specialist_max_dd: Max drawdown % in specialist regime.
        risk_of_ruin: Overall ruin probability.
        specialist_trades: Number of trades in specialist regime.

    Returns:
        Penalty factor 0.0-1.0 (multiply with raw fitness).
    """
    penalty = 1.0
    config = INTERACTION_PENALTIES

    # Fragile: high Sortino but huge drawdown
    if (specialist_sortino > config["fragile"]["sortino_threshold"] and
            specialist_max_dd > config["fragile"]["drawdown_threshold"]):
        penalty *= config["fragile"]["penalty_factor"]

    # High ruin probability
    if risk_of_ruin > config["high_ruin"]["ruin_threshold"]:
        penalty *= config["high_ruin"]["penalty_factor"]

    # Low trade count (unreliable metrics)
    if specialist_trades < config["low_trades"]["trades_threshold"]:
        penalty *= config["low_trades"]["penalty_factor"]

    return penalty


# =============================================================================
# Regime Classification
# =============================================================================


def classify_specialist_regime(fitness_by_regime: dict[str, float]) -> str:
    """
    Determine agent's specialist regime from fitness scores.

    Returns the specialist regime with highest fitness,
    ignoring non-specialist regimes (transition, random).

    Args:
        fitness_by_regime: Dict of {regime: fitness_score}.

    Returns:
        Regime name or 'unclassified' if insufficient data.
    """
    if not fitness_by_regime:
        return "unclassified"

    # Filter to specialist regimes only
    specialist_scores = {
        regime: score
        for regime, score in fitness_by_regime.items()
        if regime in SPECIALIST_REGIMES and score > 0
    }

    if not specialist_scores:
        return "unclassified"

    # Find best regime
    best_regime = max(specialist_scores, key=lambda r: specialist_scores[r])
    best_score = specialist_scores[best_regime]

    # Must exceed minimum threshold
    if best_score < CLASSIFICATION_MIN_SCORE:
        return "unclassified"

    return best_regime


# =============================================================================
# Full Pipeline
# =============================================================================


def calculate_specialist_fitness(
    specialist_metrics,
    out_of_regime_metrics,
    trades: list[dict],
    agent_returns: list[float],
    population_returns: list[float],
    specialist_type: str,
) -> float:
    """
    Calculate full V4 specialist fitness.

    Args:
        specialist_metrics: Metrics for agent's specialist regime.
        out_of_regime_metrics: Metrics for trades outside specialist regime.
        trades: All trades with 'entry_confidence' and 'outcome'.
        agent_returns: Agent's full return series.
        population_returns: Population average returns.
        specialist_type: Agent's specialist regime name.

    Returns:
        Fitness score 0.0-100.0.
    """
    # EV Gate
    ev_pct = getattr(specialist_metrics, "expectancy_pct", 0.0)
    multiplier = ev_multiplier(ev_pct)

    if multiplier == 0.0:
        return 0.0

    # Components
    depth = calculate_specialist_depth(specialist_metrics)
    discipline = calculate_risk_discipline(out_of_regime_metrics)

    n_trades = getattr(specialist_metrics, "n_trades", len(trades))
    signal = calculate_signal_quality(trades, n_trades=n_trades, specialist_type=specialist_type)

    uniqueness = calculate_uniqueness(agent_returns, population_returns)

    # Raw score
    raw = depth + discipline + signal + uniqueness

    # Apply EV multiplier
    scaled = raw * multiplier

    # Apply interaction penalties
    penalty_factor = apply_interaction_penalties(
        specialist_sortino=getattr(specialist_metrics, "sortino", 0.0),
        specialist_max_dd=getattr(specialist_metrics, "max_drawdown_pct", 0.0),
        risk_of_ruin=getattr(out_of_regime_metrics, "risk_of_ruin", 0.0),
        specialist_trades=n_trades,
    )
    final = scaled * penalty_factor

    # Clamp to [0, 100]
    return max(0.0, min(100.0, final))
