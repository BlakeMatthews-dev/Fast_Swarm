"""
Signal Quality Metrics.

Determines if an agent's edge is real or noise:
1. Statistical confidence: sqrt(n_trades) weighting
2. Mutual information: entry_confidence vs outcome correlation
3. Skew evaluation: appropriate skew for specialist type
"""

import math

from Fast_Swarm.Metrics.metrics_constants import EXPECTED_SKEW
from Fast_Swarm.Metrics.metrics_engine import calculate_skew


def calculate_confidence_factor(n_trades: int) -> float:
    """
    Statistical confidence based on trade count.

    Factor = min(1.0, sqrt(n_trades) / 10)
    Need 100+ trades for full confidence.

    Args:
        n_trades: Number of trades.

    Returns:
        Confidence factor 0.0-1.0.
    """
    if n_trades <= 0:
        return 0.0
    return min(1.0, math.sqrt(n_trades) / 10.0)


def calculate_mutual_information(trades: list[dict]) -> float:
    """
    Mutual information between entry_confidence and trade outcome.

    Measures how well the agent's confidence predicts success.
    Uses binned MI approximation.

    Args:
        trades: List of dicts with 'entry_confidence' and 'outcome' keys.

    Returns:
        MI in [0, 1]. Higher = better predictive power.
    """
    if not trades or len(trades) < 10:
        return 0.0

    # Bin confidence into quartiles
    confidences = [t.get("entry_confidence", 0.5) for t in trades]
    outcomes = [1 if t.get("outcome", 0) > 0 else 0 for t in trades]

    # Sort by confidence and split into bins
    n_bins = 4
    sorted_pairs = sorted(zip(confidences, outcomes), key=lambda x: x[0])
    bin_size = max(1, len(sorted_pairs) // n_bins)

    # Calculate win rate per bin
    bin_win_rates = []
    for i in range(n_bins):
        start = i * bin_size
        end = start + bin_size if i < n_bins - 1 else len(sorted_pairs)
        bin_outcomes = [p[1] for p in sorted_pairs[start:end]]
        if bin_outcomes:
            bin_win_rates.append(sum(bin_outcomes) / len(bin_outcomes))

    if len(bin_win_rates) < 2:
        return 0.0

    # Calculate MI as monotonicity of win rates across bins
    # Perfect: Q1_wr < Q2_wr < Q3_wr < Q4_wr -> MI = 1.0
    overall_win_rate = sum(outcomes) / len(outcomes)

    if overall_win_rate == 0 or overall_win_rate == 1:
        return 0.0

    # Compute entropy reduction from binning
    total_entropy = _binary_entropy(overall_win_rate)
    if total_entropy == 0:
        return 0.0

    # Conditional entropy (average entropy within bins)
    cond_entropy = 0.0
    for wr in bin_win_rates:
        cond_entropy += _binary_entropy(wr) / len(bin_win_rates)

    # MI = H(outcome) - H(outcome | confidence_bin)
    mi = max(0.0, total_entropy - cond_entropy)

    # Normalize to [0, 1]
    return min(1.0, mi / total_entropy) if total_entropy > 0 else 0.0


def _binary_entropy(p: float) -> float:
    """Binary entropy H(p) = -p*log2(p) - (1-p)*log2(1-p)."""
    if p <= 0 or p >= 1:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def evaluate_skew_for_type(returns: list[float], specialist_type: str) -> float:
    """
    Evaluate if return skew is appropriate for specialist type.

    Bull/recovery: positive skew rewarded
    Bear/crash: negative skew acceptable (not penalized)
    Sideways/volatile: neutral (any skew OK)

    Args:
        returns: Trade returns.
        specialist_type: One of SPECIALIST_REGIMES.

    Returns:
        Bonus score 0.0-5.0.
    """
    if not returns or len(returns) < 5:
        return 0.0

    skew = calculate_skew(returns)
    expected = EXPECTED_SKEW.get(specialist_type, "neutral")

    if expected == "positive":
        # Reward positive skew (0 to 5 pts for skew 0 to 2.0)
        if skew > 0:
            return min(5.0, skew * 2.5)
        return 0.0

    elif expected == "negative":
        # Reward negative skew (or at least don't penalize)
        if skew < 0:
            return min(5.0, abs(skew) * 2.5)
        # Positive skew is OK for bear specialists too (just less bonus)
        return min(2.0, skew * 1.0) if skew > 0 else 0.0

    else:  # neutral
        # Any skew is fine, small bonus for having any pronounced skew
        return min(3.0, abs(skew) * 1.5)


def calculate_signal_quality(
    trades: list[dict],
    n_trades: int,
    specialist_type: str,
) -> float:
    """
    Full signal quality score (0-20 pts).

    Components:
    - Confidence factor: 0-8 pts (sqrt(n_trades) weighting)
    - Mutual information: 0-7 pts (entry_confidence vs outcome)
    - Skew bonus: 0-5 pts (appropriate for specialist type)

    Args:
        trades: List of trade dicts with 'entry_confidence' and 'outcome'.
        n_trades: Total number of trades.
        specialist_type: Agent's specialist regime.

    Returns:
        Signal quality score 0.0-20.0.
    """
    score = 0.0

    # 1. Confidence factor (0-8 pts)
    confidence = calculate_confidence_factor(n_trades)
    score += 8.0 * confidence

    # 2. Mutual information (0-7 pts)
    mi = calculate_mutual_information(trades)
    score += min(7.0, mi * 14.0)  # 0.5 MI = 7 pts

    # 3. Skew evaluation (0-5 pts)
    if trades:
        returns = [t.get("outcome", 0.0) for t in trades]
        skew_bonus = evaluate_skew_for_type(returns, specialist_type)
        score += skew_bonus

    return min(20.0, score)
