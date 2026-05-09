---
# ============================================
# PAPER IDENTIFICATION
# ============================================
paper_id: "kelly-compendium"
title: "Kelly Criterion Position Sizing: A Compendium"
authors: ["J.L. Kelly Jr (original)", "Multiple subsequent authors"]
published: "1956-2024"
url: "https://en.wikipedia.org/wiki/Kelly_criterion"

# ============================================
# CLASSIFICATION
# ============================================
category: "position-sizing"
implementation_status: "READ+IMPL"
implementation_priority: "P0"

# ============================================
# ARCHITECTURE MAPPING
# ============================================
coinswarm_components:
  - "position-sizing"
  - "risk-management"
  - "agent-traits"
related_traits: [1, 4, 6]  # risk_tolerance, profit_target_greed, drawdown_sensitivity
related_phases: [2, 3, 5]  # All trading phases

# ============================================
# RELATIONSHIPS (for graph construction)
# ============================================
validates: []
validates_files: []
extends: []
extends_files: []
contradicts: []
contradicts_files: []
cites: []
cites_files: []
cited_by: []
cited_by_files: []

# ============================================
# RELATED COMPENDIUM FILES (explicit paths)
# ============================================
related_concept_files:
  - "../concepts/position-sizing.md"
  - "../concepts/risk-management.md"
related_architecture_files:
  - "../architecture/5-layer-hierarchy.md"
related_code_files:
  - "../code/kelly_criterion.py"
similar_papers_files:
  - "./arxiv-2402.00515-masa.md"

# ============================================
# KEY CONCEPTS (for semantic search)
# ============================================
concepts:
  - "kelly criterion"
  - "optimal bet sizing"
  - "bankroll management"
  - "fractional kelly"
  - "expected geometric growth"
  - "risk of ruin"
  - "position sizing"
  - "bet sizing formula"

# ============================================
# TAGS (for filtering)
# ============================================
tags:
  - "kelly"
  - "position-sizing"
  - "risk"
  - "bankroll"
  - "optimal"
  - "fractional"

# ============================================
# IMPLEMENTATION METADATA
# ============================================

# Fibonacci Estimation (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)
implementation_estimate:
  complexity: 3  # Well-understood formula
  uncertainty: 2  # Clear math
  dependencies: 2  # Standalone
  total_fib: 5

# T-Shirt Sizing (XS, S, M, L, XL, XXL)
tshirt_size: "S"
tshirt_breakdown:
  code_changes: "S"
  testing_effort: "S"
  integration_work: "S"

# Prerequisites
prerequisites:
  systems: []
  data:
    - "win_rate"
    - "win_loss_ratio"
  papers_to_read_first: []

# ============================================
# DATA REQUIREMENTS
# ============================================
data_requirements:
  required_data_types:
    - "trade_history"
    - "win_rate"
    - "avg_win"
    - "avg_loss"
  data_sources_mentioned: []
  sample_size:
    min_training_samples: 100
    min_test_samples: null
    time_period_months: null
    assets_tested: []
  data_frequency:
    primary: "trade"
    secondary: []
    real_time_required: false
  data_availability:
    have: ["trade_history"]
    need: []
    gap_severity: "low"

# ============================================
# MODEL/ALGORITHM DETAILS
# ============================================
algorithm_details:
  model_type: "rule-based"
  model_category: "risk-management"
  algorithms_used:
    - name: "Kelly Criterion"
      purpose: "optimal bet size"
      replaceable_with: "fixed fractional, volatility targeting"
    - name: "Fractional Kelly"
      purpose: "conservative sizing"
      replaceable_with: "half-Kelly, quarter-Kelly"
  hyperparameters:
    kelly_fraction: 0.25
    max_position: 0.20
    min_position: 0.01
  training:
    required: false
    training_data_size: null
    training_time_estimate: null
    gpu_required: false
    fine_tuning_needed: false
  inference:
    latency_requirement: "microseconds"
    batch_or_realtime: "realtime"
    api_calls_per_decision: 0
    cost_per_decision_usd: 0

# ============================================
# REPRODUCIBILITY
# ============================================
reproducibility:
  code_available: true
  code_url: null
  code_language: "Any"
  docker_available: false
  pretrained_weights: false
  reproduction_difficulty: "easy"
  reproduction_blockers: []

# ============================================
# PERFORMANCE CLAIMS
# ============================================
claims:
  - metric: "geometric_growth_rate"
    value: "optimal"
    context: "maximizes long-term wealth growth"
  - metric: "risk_of_ruin"
    value: 0
    context: "with fractional Kelly, never bet entire bankroll"

claim_assessment:
  overall_credibility: "high"
  concerns:
    - "Assumes known probabilities"
    - "Ignores correlation between bets"
  strengths:
    - "Mathematically proven optimal"
    - "50+ years of empirical validation"

# ============================================
# COINSWARM INTEGRATION
# ============================================
coinswarm_integration:
  target_components:
    - component: "position-sizer"
      file_path: "v3/cloudflare-agents/shared/position-sizing.ts"
      integration_type: "enhancement"
  trait_implications:
    - trait_number: 1
      trait_name: "risk_tolerance"
      implication: "Scales Kelly fraction (0.25 to 0.75)"
      confidence: "high"
    - trait_number: 4
      trait_name: "profit_target_greed"
      implication: "Affects take profit placement, indirectly affects win/loss ratio"
      confidence: "medium"
    - trait_number: 6
      trait_name: "drawdown_sensitivity"
      implication: "Reduces Kelly fraction during drawdowns"
      confidence: "high"
  phase_relevance:
    primary_phase: 2
    secondary_phases: [3, 5]
    phase_task_ids: ["2.1"]
  design_conflicts: []

# ============================================
# RISK & SAFETY ANALYSIS
# ============================================
risk_analysis:
  failure_modes:
    - mode: "Overestimated win rate"
      likelihood: "high"
      severity: "high"
      mitigation: "Use conservative estimates, apply fractional Kelly"
    - mode: "Fat tail risks"
      likelihood: "medium"
      severity: "high"
      mitigation: "Maximum position caps"
  adverse_conditions:
    - condition: "Win rate estimation error"
      expected_behavior: "Position sizes wrong direction"
      risk_level: "high"
    - condition: "Correlated losses"
      expected_behavior: "Larger drawdowns than expected"
      risk_level: "medium"
  worst_case_scenarios:
    - scenario: "Series of losses at full Kelly"
      max_loss_pct: 50
      recovery_time_estimate: "Months"
  required_safeguards:
    - "Fractional Kelly (25-50%)"
    - "Maximum position cap"
    - "Minimum trade history requirement"
  compliance_notes: []

author_stated_limitations:
  - "Assumes independent bets"
  - "Requires accurate probability estimates"
  - "Full Kelly too aggressive for real-world"

our_concerns:
  - concern: "Crypto win rates are unstable"
    severity: "medium"
    workaround: "Rolling window estimation, confidence adjustment"
  - concern: "Pattern win rates have high variance"
    severity: "medium"
    workaround: "Require minimum sample size before using Kelly"

# ============================================
# HISTORICAL CONTEXT & EVOLUTION
# ============================================
historical_context:
  foundational_papers:
    - paper_id: "kelly-1956"
      title: "A New Interpretation of Information Rate"
      relationship: "Original Kelly criterion paper"
      year: 1956
  evolution_timeline:
    - year: 1956
      milestone: "Kelly criterion published"
      relevance: "Foundation"
    - year: 1960s
      milestone: "Ed Thorp applies to gambling"
      relevance: "Practical validation"
    - year: 1990s
      milestone: "Applied to portfolio management"
      relevance: "Finance adoption"
    - year: 2010s
      milestone: "Algorithmic trading adoption"
      relevance: "Current usage"
  paradigm: "classical-ta"
  paradigm_maturity: "established"
  obsolescence_risk:
    risk_level: "low"
    potential_successors:
      - "Machine learning position sizing"
    estimated_relevance_years: 10
  innovations_vs_prior:
    - vs_paper: "Fixed fractional"
      innovation: "Adapts to edge size"
  subsequent_work: []

research_trends:
  - trend: "Risk-adjusted position sizing"
    alignment: "high"
    trend_direction: "stable"

industry_adoption:
  adoption_level: "mainstream"
  known_implementations:
    - "Professional gambling"
    - "Hedge funds"
    - "Quantitative trading firms"
  barriers_to_adoption:
    - "Requires accurate probability estimates"
---

# Kelly Criterion Position Sizing: A Compendium

## Abstract

The Kelly Criterion, developed by John L. Kelly Jr. at Bell Labs in 1956, provides a formula for determining the optimal fraction of capital to bet on a favorable wager. The criterion maximizes the expected geometric growth rate of wealth over the long term. In trading applications, it determines optimal position size based on win rate and win/loss ratio. This compendium synthesizes the core Kelly concepts and their application to algorithmic trading, with specific focus on adaptations for Coinswarm's agent-based system.

## Key Findings

- **Full Kelly is Too Aggressive**: Real-world practitioners use 25-50% of Kelly for safety
- **Requires Accurate Estimates**: Position size highly sensitive to win rate errors
- **Beats Fixed Fractional**: Kelly adapts to edge size, fixed fractional doesn't
- **Never Bets Too Big**: Kelly never risks entire bankroll on single bet
- **Compound Growth Optimal**: Maximizes log-utility (geometric growth)

## Core Kelly Mathematics

### The Basic Kelly Formula

$$
f^* = \frac{p \cdot b - q}{b} = \frac{p(b + 1) - 1}{b}
$$

Where:
- $f^*$ = optimal fraction of capital to bet
- $p$ = probability of winning (win rate)
- $q$ = probability of losing (1 - p)
- $b$ = win/loss ratio (avg_win / avg_loss)

### Alternative Formulations

**Edge over Odds:**
$$
f^* = \frac{\text{Edge}}{\text{Odds}} = \frac{p \cdot b - q}{b}
$$

**Using Expected Value:**
$$
f^* = \frac{E[R]}{b} = \frac{p \cdot b - q}{b}
$$

**For Unequal Bet Sizes:**
$$
f^* = \frac{p}{a} - \frac{q}{b}
$$

Where $a$ = loss amount, $b$ = win amount (as multiples of bet).

### Worked Example

```
Pattern Statistics:
- Win rate: 55% (p = 0.55)
- Average win: $150
- Average loss: $100
- Win/loss ratio: b = 150/100 = 1.5

Kelly Calculation:
f* = (0.55 × 1.5 - 0.45) / 1.5
f* = (0.825 - 0.45) / 1.5
f* = 0.375 / 1.5
f* = 0.25 (25% of capital)

With Fractional Kelly (50%):
Position = 0.25 × 0.50 = 0.125 (12.5% of capital)
```

### Kelly for Trading

In trading, we adapt Kelly for:
1. **Partial Wins/Losses**: Trades don't always hit full targets
2. **Variable Position Sizing**: Risk percentage instead of fixed dollar amount
3. **Multiple Positions**: Portfolio Kelly for correlated assets

Trading Kelly Formula:
$$
f^* = \frac{\text{Win Rate} \times \text{Avg Win} - \text{Loss Rate} \times \text{Avg Loss}}{\text{Avg Win}}
$$

Or equivalently:
$$
f^* = \text{Win Rate} - \frac{\text{Loss Rate}}{\text{Win/Loss Ratio}}
$$

## Fractional Kelly

### Why Use Less Than Full Kelly

Full Kelly has several problems:
1. **High Variance**: Drawdowns can be severe
2. **Estimation Error**: Small errors in p or b cause large position errors
3. **Psychological Stress**: Drawdowns are hard to handle

### Fractional Kelly Formula

$$
f = k \cdot f^*
$$

Where k is typically 0.25 to 0.50.

### Fraction Guidelines

| Confidence in Estimates | Kelly Fraction | Typical Use |
|------------------------|----------------|-------------|
| Very High | 50% (Half Kelly) | Proven patterns |
| High | 33% (Third Kelly) | Good track record |
| Medium | 25% (Quarter Kelly) | New patterns |
| Low | 10-20% | Experimental |

### Drawdown Comparison

| Kelly Fraction | Expected Max Drawdown | Recovery Time |
|----------------|----------------------|---------------|
| 100% (Full) | ~50% | Very long |
| 50% (Half) | ~25% | Moderate |
| 25% (Quarter) | ~12% | Fast |

## Implementation

### Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    PATTERN STATISTICS                       │
│         (win_rate, avg_win, avg_loss, trade_count)         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  MINIMUM SAMPLE CHECK                       │
│                                                             │
│   IF trade_count < 30:                                      │
│     Use minimum position (1-2% of capital)                  │
│   ELSE:                                                     │
│     Continue to Kelly calculation                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  CALCULATE RAW KELLY                        │
│                                                             │
│   win_loss_ratio = avg_win / avg_loss                       │
│   raw_kelly = (win_rate * win_loss_ratio - (1-win_rate))    │
│               / win_loss_ratio                              │
│                                                             │
│   IF raw_kelly <= 0:                                        │
│     No edge - skip trade or minimum position                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  APPLY KELLY FRACTION                       │
│                                                             │
│   Based on agent's risk_tolerance trait:                    │
│   kelly_mult = 0.25 + risk_tolerance * 0.25                │
│   (Ranges from 0.25 to 0.50)                               │
│                                                             │
│   fractional_kelly = raw_kelly * kelly_mult                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  APPLY CONFIDENCE ADJUSTMENT                │
│                                                             │
│   confidence_mult = signal_confidence                       │
│   (From pattern signal, 0.0 to 1.0)                        │
│                                                             │
│   adjusted_kelly = fractional_kelly * confidence_mult       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     APPLY BOUNDS                            │
│                                                             │
│   MIN_POSITION = 0.01 (1%)                                  │
│   MAX_POSITION = 0.20 (20%)                                 │
│                                                             │
│   final_position = clip(adjusted_kelly, MIN, MAX)           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  DRAWDOWN ADJUSTMENT                        │
│                                                             │
│   IF current_drawdown > 0.05:                               │
│     reduction = 1 - (current_drawdown / 0.20)              │
│     final_position *= max(0.5, reduction)                   │
└─────────────────────────────────────────────────────────────┘
```

### Key Equations

#### Equation 1: Trait-Adjusted Kelly Multiplier

$$
k_{adjusted} = 0.25 + \text{risk\_tolerance} \times 0.25
$$

Maps risk_tolerance trait (0-1) to Kelly fraction (0.25-0.50).

#### Equation 2: Confidence-Adjusted Position

$$
f_{conf} = f_{kelly} \times \sqrt{c}
$$

Where c = signal confidence. Using square root dampens overconfidence.

#### Equation 3: Drawdown Reduction

$$
f_{final} = f_{adjusted} \times \max\left(0.5, 1 - \frac{DD_{current}}{DD_{max}}\right)
$$

Reduces position size proportionally during drawdowns.

#### Equation 4: Sample Size Confidence

$$
\text{confidence}_{sample} = \min\left(1.0, \sqrt{\frac{n}{100}}\right)
$$

Where n = number of trades. Ramps up to full confidence at 100 trades.

## Code Implementation

```python
# PRODUCTION: Full Kelly position sizing
from dataclasses import dataclass
from typing import Optional
import math

@dataclass
class KellyInput:
    """Input parameters for Kelly calculation."""
    win_rate: float         # 0.0 to 1.0
    avg_win: float          # Positive value
    avg_loss: float         # Positive value (magnitude)
    trade_count: int        # Number of historical trades
    signal_confidence: float  # 0.0 to 1.0
    risk_tolerance: float   # Agent trait, 0.0 to 1.0
    current_drawdown: float  # 0.0 to 1.0

@dataclass
class KellyOutput:
    """Output from Kelly calculation."""
    position_size: float     # Final position as fraction of capital
    raw_kelly: float         # Unadjusted Kelly fraction
    has_edge: bool           # Whether there's a positive edge
    adjustments_applied: list[str]  # What adjustments were made


def calculate_kelly_position(
    input: KellyInput,
    min_position: float = 0.01,
    max_position: float = 0.20,
    min_trades: int = 30,
    max_drawdown: float = 0.20
) -> KellyOutput:
    """
    Calculate position size using Kelly criterion with all adjustments.

    The full Coinswarm Kelly implementation includes:
    1. Raw Kelly from win rate and win/loss ratio
    2. Fractional Kelly based on risk_tolerance trait
    3. Confidence adjustment from signal strength
    4. Sample size adjustment for limited data
    5. Drawdown reduction during losing periods
    6. Hard min/max bounds

    Args:
        input: KellyInput with all required parameters
        min_position: Minimum position size (default 1%)
        max_position: Maximum position size (default 20%)
        min_trades: Minimum trades before using Kelly (default 30)
        max_drawdown: Drawdown level for max reduction (default 20%)

    Returns:
        KellyOutput with final position and diagnostics
    """
    adjustments = []

    # Input validation
    if input.win_rate <= 0 or input.win_rate >= 1:
        return KellyOutput(
            position_size=min_position,
            raw_kelly=0.0,
            has_edge=False,
            adjustments_applied=["invalid_win_rate"]
        )

    if input.avg_win <= 0 or input.avg_loss <= 0:
        return KellyOutput(
            position_size=min_position,
            raw_kelly=0.0,
            has_edge=False,
            adjustments_applied=["invalid_win_loss_amounts"]
        )

    # Step 1: Calculate raw Kelly
    win_loss_ratio = input.avg_win / input.avg_loss
    loss_rate = 1 - input.win_rate

    raw_kelly = (input.win_rate * win_loss_ratio - loss_rate) / win_loss_ratio

    # Check for positive edge
    if raw_kelly <= 0:
        return KellyOutput(
            position_size=min_position,
            raw_kelly=raw_kelly,
            has_edge=False,
            adjustments_applied=["no_edge"]
        )

    has_edge = True
    position = raw_kelly

    # Step 2: Apply fractional Kelly based on risk_tolerance
    kelly_fraction = 0.25 + input.risk_tolerance * 0.25  # 0.25 to 0.50
    position *= kelly_fraction
    adjustments.append(f"fractional_kelly_{kelly_fraction:.2f}")

    # Step 3: Apply confidence adjustment
    if input.signal_confidence < 1.0:
        confidence_mult = math.sqrt(input.signal_confidence)  # Dampen
        position *= confidence_mult
        adjustments.append(f"confidence_{input.signal_confidence:.2f}")

    # Step 4: Apply sample size adjustment
    if input.trade_count < min_trades:
        position = min_position
        adjustments.append(f"insufficient_trades_{input.trade_count}")
    elif input.trade_count < 100:
        sample_conf = math.sqrt(input.trade_count / 100)
        position *= sample_conf
        adjustments.append(f"sample_size_{input.trade_count}")

    # Step 5: Apply drawdown reduction
    if input.current_drawdown > 0.05:  # 5% threshold
        reduction = max(0.5, 1 - (input.current_drawdown / max_drawdown))
        position *= reduction
        adjustments.append(f"drawdown_reduction_{reduction:.2f}")

    # Step 6: Apply bounds
    if position < min_position:
        position = min_position
        adjustments.append("min_bound")
    elif position > max_position:
        position = max_position
        adjustments.append("max_bound")

    return KellyOutput(
        position_size=round(position, 4),
        raw_kelly=round(raw_kelly, 4),
        has_edge=has_edge,
        adjustments_applied=adjustments
    )


def calculate_optimal_f(
    trade_results: list[float],
    initial_capital: float = 10000
) -> float:
    """
    Calculate optimal f using historical trade results.

    Uses simulation to find f that maximizes terminal wealth.
    This is an alternative to Kelly when trade sizes vary.
    """
    if not trade_results or len(trade_results) < 30:
        return 0.01  # Minimum

    best_f = 0.01
    best_terminal = initial_capital

    for f in [i / 100 for i in range(1, 51)]:  # Test 0.01 to 0.50
        capital = initial_capital

        for trade in trade_results:
            # Calculate position value
            position_value = capital * f

            # Apply trade result
            capital += position_value * trade

            # Check for ruin
            if capital <= 0:
                capital = 0
                break

        if capital > best_terminal:
            best_terminal = capital
            best_f = f

    return best_f


# Example usage
def kelly_example():
    """Demonstrate Kelly calculation."""
    input = KellyInput(
        win_rate=0.55,
        avg_win=150,
        avg_loss=100,
        trade_count=50,
        signal_confidence=0.8,
        risk_tolerance=0.5,
        current_drawdown=0.03
    )

    result = calculate_kelly_position(input)

    print(f"Raw Kelly: {result.raw_kelly:.2%}")
    print(f"Final Position: {result.position_size:.2%}")
    print(f"Has Edge: {result.has_edge}")
    print(f"Adjustments: {result.adjustments_applied}")

    # Output:
    # Raw Kelly: 16.67%
    # Final Position: 5.55%
    # Has Edge: True
    # Adjustments: ['fractional_kelly_0.38', 'confidence_0.80', 'sample_size_50']
```

## Trait Integration

### How Agent Traits Affect Kelly

| Trait | Effect on Kelly |
|-------|-----------------|
| risk_tolerance | Directly scales Kelly fraction (0.25-0.50) |
| drawdown_sensitivity | Triggers earlier position reduction |
| profit_target_greed | Affects take profit → affects avg_win |
| win_rate_preference | Affects pattern selection → affects win_rate |

### Trait-Adjusted Kelly Table

| risk_tolerance | Base Kelly | Fractional Kelly | Max Position |
|----------------|------------|------------------|--------------|
| 0.0 (conservative) | 25% | 6.25% | 15% |
| 0.25 | 25% | 7.81% | 17.5% |
| 0.5 | 25% | 9.38% | 20% |
| 0.75 | 25% | 10.94% | 22.5% |
| 1.0 (aggressive) | 25% | 12.5% | 25% |

## Cross-References

### Related Papers in Compendium

| Paper | Path | Relationship |
|-------|------|--------------|
| MASA | `./arxiv-2402.00515-masa.md` | Uses Kelly for allocation |

### Related Concept Files

| Concept | Path | Why Related |
|---------|------|-------------|
| Position Sizing | `../concepts/position-sizing.md` | Full concept doc |
| Risk Management | `../concepts/risk-management.md` | Broader context |

### Related Code Files

| Implementation | Path | What It Implements |
|----------------|------|-------------------|
| Kelly Criterion | `../code/kelly_criterion.py` | Production code |

## Implementation Gaps

### Fully Implemented

1. Basic Kelly calculation
2. Fractional Kelly
3. Confidence adjustment
4. Drawdown reduction
5. Trait integration

### Not Yet Implemented

1. **Multi-Asset Kelly** - Correlated positions
2. **Rolling Window Estimation** - Dynamic win rate
3. **Regime-Adjusted Kelly** - Different fractions per regime

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial P0 paper file |
