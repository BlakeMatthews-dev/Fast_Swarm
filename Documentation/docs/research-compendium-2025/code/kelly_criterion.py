#!/usr/bin/env python3
"""
Kelly Criterion Position Sizing Implementation.

This module provides position sizing calculations based on Kelly criterion,
adapted for trading applications with confidence adjustment and constraints.

Paper References:
- Kelly 1956: Original Kelly criterion
- arxiv-2402.15588: Focused portfolio sizing
- MASA (arxiv-2402.00515): Multi-agent risk parity

Related Concept: ../concepts/position-sizing.md
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class PositionConstraints:
    """Constraints for position sizing."""

    # Per-position limits
    max_single_position: float = 0.20  # 20% max per trade
    min_position_size: float = 0.01  # 1% minimum (avoid dust)

    # Portfolio limits
    max_total_exposure: float = 0.80  # 80% max invested
    max_correlated_exposure: float = 0.40  # 40% max in correlated assets

    # Risk limits
    max_portfolio_var: float = 0.02  # 2% daily VaR limit
    max_daily_loss: float = 0.05  # 5% max daily loss


@dataclass
class KellyResult:
    """Result of Kelly position sizing calculation."""

    raw_kelly: float  # Full Kelly fraction
    fractional_kelly: float  # After fractional multiplier
    confidence_adjusted: float  # After confidence adjustment
    trait_adjusted: float  # After trait adjustments
    final_position: float  # After all constraints
    reasoning: str  # Explanation of adjustments


def calculate_kelly_fraction(win_rate: float, avg_win: float, avg_loss: float, kelly_multiplier: float = 0.25) -> float:
    """
    Calculate Kelly criterion position size.

    The Kelly criterion determines optimal bet sizing for maximum
    long-term wealth growth. We use fractional Kelly for safety.

    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average winning trade return (positive, e.g., 0.05 for 5%)
        avg_loss: Average losing trade return (positive, absolute value)
        kelly_multiplier: Fraction of full Kelly to use (0.25-0.5 typical)

    Returns:
        Position size as fraction of capital (0-1)

    Formula:
        f* = (p * b - q) / b
        where:
        - p = probability of winning
        - q = 1 - p = probability of losing
        - b = win/loss ratio (avg_win / avg_loss)

    Example:
        >>> calculate_kelly_fraction(0.55, 0.10, 0.05, 0.25)
        0.1125  # 11.25% position size (quarter Kelly)
    """
    # Validate inputs
    if avg_loss <= 0:
        return 0.0
    if win_rate <= 0 or win_rate >= 1:
        return 0.0
    if avg_win <= 0:
        return 0.0

    p = win_rate
    q = 1 - win_rate
    b = avg_win / avg_loss  # Win/loss ratio

    # Full Kelly formula
    full_kelly = (p * b - q) / b

    # If negative, no edge - don't bet
    if full_kelly <= 0:
        return 0.0

    # Apply fractional multiplier for safety
    # Full Kelly is too aggressive for real trading
    fractional_kelly = kelly_multiplier * full_kelly

    # Safety cap - never more than 25% even with good edge
    return min(fractional_kelly, 0.25)


def confidence_adjusted_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    signal_confidence: float,
    kelly_multiplier: float = 0.25,
    min_confidence: float = 0.5,
) -> float:
    """
    Position size adjusted by signal confidence.

    Lower confidence signals get proportionally smaller positions.
    This accounts for uncertainty in our win rate estimates.

    Args:
        win_rate: Historical pattern win rate
        avg_win: Average winning trade return
        avg_loss: Average losing trade return
        signal_confidence: Confidence in current signal (0-1)
        kelly_multiplier: Kelly fraction to use
        min_confidence: Minimum confidence to trade

    Returns:
        Confidence-adjusted position size

    Paper Reference: MASA - confidence-weighted allocation
    """
    if signal_confidence < min_confidence:
        return 0.0

    base_kelly = calculate_kelly_fraction(win_rate, avg_win, avg_loss, kelly_multiplier)

    # Scale position by confidence
    # Low confidence = smaller position
    confidence_factor = signal_confidence

    return base_kelly * confidence_factor


def trait_adjusted_position_size(
    base_size: float, agent_traits: dict[str, float], recent_drawdown: float = 0.0
) -> float:
    """
    Adjust position size based on agent personality traits.

    Different agents have different risk appetites based on their
    evolved traits.

    Args:
        base_size: Kelly-calculated position size
        agent_traits: Dict of trait values (0-1)
        recent_drawdown: Current drawdown as decimal (0.05 = 5%)

    Returns:
        Trait-adjusted position size

    Relevant Traits:
        - risk_tolerance (1): Higher = larger positions
        - drawdown_sensitivity (6): Higher = reduce more in drawdown
        - win_rate_preference (5): Higher = prefer many small wins

    Paper Reference: TradingAgents - trait-driven behavior
    """
    # Risk tolerance scaling (trait #1)
    # 0.0 risk_tolerance -> 0.5x position
    # 0.5 risk_tolerance -> 0.875x position
    # 1.0 risk_tolerance -> 1.25x position
    risk_tolerance = agent_traits.get("risk_tolerance", 0.5)
    risk_factor = 0.5 + risk_tolerance * 0.75

    # Drawdown sensitivity adjustment (trait #6)
    # If in drawdown and sensitive, reduce size
    drawdown_sensitivity = agent_traits.get("drawdown_sensitivity", 0.5)
    if recent_drawdown > 0.03:  # 3% drawdown threshold
        # Max 50% reduction for very sensitive agent in bad drawdown
        dd_reduction = drawdown_sensitivity * min(recent_drawdown * 3, 0.5)
        dd_factor = 1.0 - dd_reduction
    else:
        dd_factor = 1.0

    # Apply adjustments
    adjusted = base_size * risk_factor * dd_factor

    # Safety cap - never exceed 25% regardless of traits
    return min(adjusted, 0.25)


def calculate_full_position_size(
    pattern_stats: dict,
    signal_confidence: float,
    agent_traits: dict[str, float],
    portfolio_state: dict,
    constraints: PositionConstraints | None = None,
) -> KellyResult:
    """
    Full position sizing calculation with all adjustments.

    This is the main entry point for position sizing, combining:
    1. Base Kelly calculation
    2. Confidence adjustment
    3. Trait adjustment
    4. Portfolio constraints

    Args:
        pattern_stats: Dict with win_rate, avg_win, avg_loss
        signal_confidence: Confidence in signal (0-1)
        agent_traits: Agent personality traits
        portfolio_state: Current portfolio state (drawdown, exposure, etc.)
        constraints: Position and portfolio constraints

    Returns:
        KellyResult with final position and reasoning
    """
    if constraints is None:
        constraints = PositionConstraints()

    reasoning_parts = []

    # Step 1: Raw Kelly
    raw_kelly = calculate_kelly_fraction(
        win_rate=pattern_stats.get("win_rate", 0.5),
        avg_win=pattern_stats.get("avg_win", 0.02),
        avg_loss=pattern_stats.get("avg_loss", 0.02),
        kelly_multiplier=1.0,  # Full Kelly first
    )
    reasoning_parts.append(f"Raw Kelly: {raw_kelly:.3f}")

    # Step 2: Fractional Kelly
    fractional = raw_kelly * 0.25  # Quarter Kelly
    reasoning_parts.append(f"Quarter Kelly: {fractional:.3f}")

    # Step 3: Confidence adjustment
    if signal_confidence < 0.5:
        conf_adjusted = 0.0
        reasoning_parts.append("Confidence too low (<0.5), no trade")
    else:
        conf_adjusted = fractional * signal_confidence
        reasoning_parts.append(f"Confidence adjusted ({signal_confidence:.2f}): {conf_adjusted:.3f}")

    # Step 4: Trait adjustment
    recent_dd = portfolio_state.get("recent_drawdown", 0.0)
    trait_adjusted = trait_adjusted_position_size(conf_adjusted, agent_traits, recent_dd)
    reasoning_parts.append(f"Trait adjusted: {trait_adjusted:.3f}")

    # Step 5: Apply constraints
    final = trait_adjusted

    # Single position limit
    if final > constraints.max_single_position:
        final = constraints.max_single_position
        reasoning_parts.append(f"Capped at max single: {final:.3f}")

    # Total exposure limit
    current_exposure = portfolio_state.get("current_exposure", 0.0)
    remaining_exposure = constraints.max_total_exposure - current_exposure
    if final > remaining_exposure:
        final = max(0, remaining_exposure)
        reasoning_parts.append(f"Limited by total exposure: {final:.3f}")

    # Minimum position
    if 0 < final < constraints.min_position_size:
        final = 0.0
        reasoning_parts.append("Below minimum, skipping trade")

    return KellyResult(
        raw_kelly=raw_kelly,
        fractional_kelly=fractional,
        confidence_adjusted=conf_adjusted,
        trait_adjusted=trait_adjusted,
        final_position=final,
        reasoning=" | ".join(reasoning_parts),
    )


# =============================================================================
# Utility Functions
# =============================================================================


def kelly_optimal_growth_rate(win_rate: float, avg_win: float, avg_loss: float, fraction: float) -> float:
    """
    Calculate expected log growth rate for a given position fraction.

    This is the metric Kelly criterion maximizes.

    Args:
        win_rate: Probability of winning
        avg_win: Average win return
        avg_loss: Average loss return
        fraction: Position fraction to evaluate

    Returns:
        Expected log growth rate

    Note: Maximum is achieved at Kelly-optimal fraction.
    """
    p = win_rate
    q = 1 - win_rate

    # Avoid log of negative numbers
    win_multiplier = 1 + fraction * avg_win
    loss_multiplier = 1 - fraction * avg_loss

    if win_multiplier <= 0 or loss_multiplier <= 0:
        return float("-inf")

    # Expected log return
    expected_log_return = p * np.log(win_multiplier) + q * np.log(loss_multiplier)

    return expected_log_return


def kelly_ruin_probability(fraction: float, win_rate: float, win_loss_ratio: float, num_trades: int = 100) -> float:
    """
    Estimate probability of ruin (losing X% of capital).

    Higher fractions = higher ruin probability.

    Args:
        fraction: Position fraction
        win_rate: Win rate
        win_loss_ratio: avg_win / avg_loss
        num_trades: Number of trades to simulate

    Returns:
        Estimated probability of 50% drawdown
    """
    # Monte Carlo simulation
    ruin_threshold = 0.5  # 50% loss = ruin
    simulations = 1000
    ruins = 0

    for _ in range(simulations):
        capital = 1.0
        max_capital = 1.0

        for _ in range(num_trades):
            if np.random.random() < win_rate:
                capital *= 1 + fraction * win_loss_ratio * 0.02
            else:
                capital *= 1 - fraction * 0.02

            max_capital = max(max_capital, capital)
            drawdown = (max_capital - capital) / max_capital

            if drawdown >= ruin_threshold:
                ruins += 1
                break

    return ruins / simulations


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example: Calculate position size for a pattern

    pattern_stats = {
        "win_rate": 0.55,
        "avg_win": 0.05,  # 5% average win
        "avg_loss": 0.03,  # 3% average loss
    }

    agent_traits = {
        "risk_tolerance": 0.6,
        "drawdown_sensitivity": 0.4,
        "win_rate_preference": 0.5,
    }

    portfolio_state = {
        "recent_drawdown": 0.02,
        "current_exposure": 0.30,
    }

    result = calculate_full_position_size(
        pattern_stats=pattern_stats,
        signal_confidence=0.75,
        agent_traits=agent_traits,
        portfolio_state=portfolio_state,
    )

    print("Position Sizing Result:")
    print(f"  Raw Kelly:         {result.raw_kelly:.4f}")
    print(f"  Fractional Kelly:  {result.fractional_kelly:.4f}")
    print(f"  Confidence Adj:    {result.confidence_adjusted:.4f}")
    print(f"  Trait Adjusted:    {result.trait_adjusted:.4f}")
    print(f"  Final Position:    {result.final_position:.4f}")
    print(f"  Reasoning:         {result.reasoning}")
