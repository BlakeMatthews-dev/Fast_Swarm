---
# ============================================
# PAPER IDENTIFICATION
# ============================================
paper_id: "arxiv-2402.00515"
title: "MASA: Multi-Agent System for Automated Stock Analysis"
authors: ["Chen Gao", "Xiaochong Lan", "Feng Yu", "Zhengyu Lu"]
published: "2024-02"
url: "https://arxiv.org/abs/2402.00515"

# ============================================
# CLASSIFICATION
# ============================================
category: "multi-agent-risk"
implementation_status: "READ+IMPL"
implementation_priority: "P0"

# ============================================
# ARCHITECTURE MAPPING
# ============================================
coinswarm_components:
  - "multi-agent-coordination"
  - "risk-balancing"
  - "portfolio-allocation"
  - "agent-specialization"
related_traits: [1, 6, 16]  # risk_tolerance, drawdown_sensitivity, correlation_awareness
related_phases: [3, 5]  # Phase 3: Hivemind Committee, Phase 5: Full Autonomous

# ============================================
# RELATIONSHIPS (for graph construction)
# ============================================
validates: []
validates_files: []
extends: ["arxiv-2011.09607"]
extends_files:
  - "./arxiv-2011.09607-finrl.md"
contradicts: []
contradicts_files: []
cites: ["arxiv-2011.09607"]
cites_files:
  - "./arxiv-2011.09607-finrl.md"
cited_by: ["arxiv-2412.20138"]
cited_by_files:
  - "./arxiv-2412.20138-trading-agents.md"

# ============================================
# RELATED COMPENDIUM FILES (explicit paths)
# ============================================
related_concept_files:
  - "../concepts/risk-management.md"
  - "../concepts/position-sizing.md"
  - "../concepts/three-pillars.md"
related_architecture_files:
  - "../architecture/5-layer-hierarchy.md"
  - "../architecture/3-tier-execution.md"
related_code_files:
  - "../code/kelly_criterion.py"
  - "../code/affinity_mutation.py"
similar_papers_files:
  - "./arxiv-2412.20138-trading-agents.md"
  - "./arxiv-2212.14670-m3t.md"

# ============================================
# KEY CONCEPTS (for semantic search)
# ============================================
concepts:
  - "multi-agent risk balancing"
  - "portfolio allocation"
  - "agent specialization"
  - "risk parity"
  - "diversification"
  - "correlation-aware allocation"
  - "automated stock analysis"

# ============================================
# TAGS (for filtering)
# ============================================
tags:
  - "multi-agent"
  - "risk-management"
  - "portfolio"
  - "allocation"
  - "diversification"
  - "llm"

# ============================================
# IMPLEMENTATION METADATA
# ============================================

# Fibonacci Estimation (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)
implementation_estimate:
  complexity: 8  # Multi-agent coordination
  uncertainty: 3  # Well-documented
  dependencies: 5  # Portfolio infrastructure needed
  total_fib: 13

# T-Shirt Sizing (XS, S, M, L, XL, XXL)
tshirt_size: "M"
tshirt_breakdown:
  code_changes: "M"
  testing_effort: "M"
  integration_work: "S"

# Prerequisites
prerequisites:
  systems:
    - "portfolio-tracking"
    - "correlation-calculator"
  data:
    - "OHLCV"
    - "portfolio-positions"
  papers_to_read_first: []

# ============================================
# DATA REQUIREMENTS
# ============================================
data_requirements:
  required_data_types:
    - "OHLCV"
    - "asset_correlations"
    - "portfolio_holdings"
  data_sources_mentioned:
    - name: "Stock Price Data"
      required: true
      alternative: "Any market data provider"
  sample_size:
    min_training_samples: 5000
    min_test_samples: 1000
    time_period_months: 24
    assets_tested: ["Multiple US stocks"]
  data_frequency:
    primary: "1d"
    secondary: ["1h"]
    real_time_required: false
  data_availability:
    have: ["OHLCV_1d", "OHLCV_1h"]
    need: ["correlation_matrix"]
    gap_severity: "low"

# ============================================
# MODEL/ALGORITHM DETAILS
# ============================================
algorithm_details:
  model_type: "multi-agent-llm"
  model_category: "portfolio-optimization"
  algorithms_used:
    - name: "Risk Parity"
      purpose: "equal risk contribution allocation"
      replaceable_with: "mean-variance optimization"
    - name: "Correlation Analysis"
      purpose: "diversification scoring"
      replaceable_with: "PCA-based clustering"
    - name: "Multi-Agent Voting"
      purpose: "signal aggregation"
      replaceable_with: "weighted ensemble"
  hyperparameters:
    max_correlation: 0.7
    max_single_position: 0.25
    min_diversification: 5
    rebalance_threshold: 0.1
  training:
    required: false
    training_data_size: null
    training_time_estimate: null
    gpu_required: false
    fine_tuning_needed: false
  inference:
    latency_requirement: "seconds"
    batch_or_realtime: "batch"
    api_calls_per_decision: 3
    cost_per_decision_usd: 0.05

# ============================================
# REPRODUCIBILITY
# ============================================
reproducibility:
  code_available: false
  code_url: null
  code_language: "Python"
  docker_available: false
  pretrained_weights: false
  reproduction_difficulty: "medium"
  reproduction_blockers:
    - "No public code"
    - "Specific prompt templates not shared"

# ============================================
# PERFORMANCE CLAIMS
# ============================================
claims:
  - metric: "sharpe_ratio"
    value: 1.67
    context: "US stocks portfolio 2020-2023"
    baseline_comparison: "equal_weight"
    baseline_value: 1.12
    improvement_pct: 49
  - metric: "max_drawdown"
    value: 0.15
    context: "including COVID crash"
    baseline_comparison: "equal_weight"
    baseline_value: 0.28
    improvement_pct: 46
  - metric: "diversification_ratio"
    value: 1.8
    context: "average across period"

claim_assessment:
  overall_credibility: "medium"
  concerns:
    - "No code available"
    - "Limited dataset details"
  strengths:
    - "Multiple risk metrics reported"
    - "Drawdown analysis included"

# ============================================
# COINSWARM INTEGRATION
# ============================================
coinswarm_integration:
  target_components:
    - component: "portfolio-manager"
      file_path: "v3/cloudflare-agents/agents/portfolio-do.ts"
      integration_type: "new_feature"
    - component: "correlation-tracker"
      file_path: "v3/cloudflare-agents/shared/correlation.ts"
      integration_type: "new_feature"
  trait_implications:
    - trait_number: 1
      trait_name: "risk_tolerance"
      implication: "Determines maximum position sizes"
      confidence: "high"
    - trait_number: 6
      trait_name: "drawdown_sensitivity"
      implication: "Triggers rebalancing on drawdown"
      confidence: "high"
    - trait_number: 16
      trait_name: "correlation_awareness"
      implication: "Controls diversification requirements"
      confidence: "high"
  phase_relevance:
    primary_phase: 3
    secondary_phases: [5]
    phase_task_ids: ["3.3"]
  design_conflicts:
    - conflict: "Paper focuses on stocks, we trade crypto"
      resolution: "Same principles apply, adjust correlation thresholds"
      resolved: true

# ============================================
# RISK & SAFETY ANALYSIS
# ============================================
risk_analysis:
  failure_modes:
    - mode: "Correlation breakdown during crisis"
      likelihood: "medium"
      severity: "high"
      mitigation: "Use rolling correlations, increase in volatility"
    - mode: "Over-diversification reduces returns"
      likelihood: "low"
      severity: "low"
      mitigation: "Balance diversification with concentration"
  adverse_conditions:
    - condition: "All assets correlated (market crash)"
      expected_behavior: "Diversification provides less protection"
      risk_level: "high"
    - condition: "Low volatility regime"
      expected_behavior: "Risk parity underperforms momentum"
      risk_level: "low"
  worst_case_scenarios:
    - scenario: "Correlation spike during position"
      max_loss_pct: 20
      recovery_time_estimate: "4-8 weeks"
  required_safeguards:
    - "Maximum position size limits"
    - "Correlation monitoring alerts"
    - "Drawdown-triggered rebalancing"
  compliance_notes: []

author_stated_limitations:
  - "Tested on US stocks only"
  - "Does not account for transaction costs in rebalancing"
  - "Static correlation windows"

our_concerns:
  - concern: "Crypto correlations are unstable"
    severity: "medium"
    workaround: "Use shorter correlation windows, regime-based adjustment"
  - concern: "Rebalancing costs in crypto can be high"
    severity: "medium"
    workaround: "Use threshold-based rebalancing"

# ============================================
# HISTORICAL CONTEXT & EVOLUTION
# ============================================
historical_context:
  foundational_papers:
    - paper_id: "arxiv-2011.09607"
      title: "FinRL"
      relationship: "RL for portfolio optimization"
      year: 2020
  evolution_timeline:
    - year: 2010
      milestone: "Risk parity popularized"
      relevance: "Foundation concept"
    - year: 2024
      milestone: "LLM-enhanced portfolio management"
      relevance: "This paper's contribution"
  paradigm: "multi-agent-llm"
  paradigm_maturity: "emerging"
  obsolescence_risk:
    risk_level: "low"
    potential_successors:
      - "Real-time correlation models"
    estimated_relevance_years: 4
  innovations_vs_prior:
    - vs_paper: "Traditional Risk Parity"
      innovation: "LLM agents for qualitative analysis"
    - vs_paper: "Single-agent portfolio"
      innovation: "Specialized agents for different risk factors"
  subsequent_work:
    - paper_id: "arxiv-2412.20138"
      title: "TradingAgents"
      relationship: "Extended multi-agent framework"
      improvement: "Added debate mechanism"

research_trends:
  - trend: "Multi-agent portfolio management"
    alignment: "high"
    trend_direction: "growing"
  - trend: "Risk-aware AI systems"
    alignment: "high"
    trend_direction: "growing"

industry_adoption:
  adoption_level: "experimental"
  known_implementations:
    - "Academic research"
  barriers_to_adoption:
    - "Complexity of multi-agent coordination"
    - "Regulatory concerns"
---

# MASA: Multi-Agent System for Automated Stock Analysis

## Abstract

MASA presents a multi-agent system for automated stock analysis and portfolio management. The system employs specialized agents for different aspects of analysis - fundamental, technical, sentiment, and risk - coordinated through a risk-balancing framework. Each agent contributes analysis weighted by confidence and historical accuracy, with the risk agent having override capability to enforce diversification and position limits. The system demonstrates improved Sharpe ratio and reduced drawdown compared to equal-weight baselines.

## Key Findings

- **Risk Agent Critical**: Dedicated risk agent prevents concentration and enforces diversification
- **Correlation Awareness**: Portfolio-level correlation limits prevent hidden concentration
- **Specialization Works**: Agents focused on single domains outperform generalists
- **Override Mechanism**: Risk veto prevents individual agent errors from causing portfolio damage
- **Rebalancing Thresholds**: 10% drift threshold balances costs vs risk

## Architecture Details

### Core Mechanism

MASA uses a hierarchical multi-agent structure:

1. **Analysis Agents** - Generate signals for individual assets
   - Fundamental Agent
   - Technical Agent
   - Sentiment Agent

2. **Risk Agent** - Portfolio-level oversight
   - Correlation monitoring
   - Position limit enforcement
   - Drawdown tracking

3. **Portfolio Manager** - Final allocation decisions

### Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    ASSET UNIVERSE                           │
│                (All tradeable assets)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Fundamental │  │  Technical  │  │  Sentiment  │
│    Agent    │  │    Agent    │  │    Agent    │
│             │  │             │  │             │
│ P/E, EPS,   │  │ RSI, MACD,  │  │ News, F&G,  │
│ Revenue     │  │ Patterns    │  │ Social      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       │     ┌──────────┴──────────┐     │
       └────►│   SIGNAL AGGREGATOR │◄────┘
             │                     │
             │  Weighted by:       │
             │  - Confidence       │
             │  - Historical Acc   │
             └──────────┬──────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      RISK AGENT                             │
│                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │ Correlation │  │  Position   │  │  Drawdown   │        │
│   │   Check     │  │   Limits    │  │  Monitor    │        │
│   └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│   Can VETO or REDUCE any proposed allocation               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  PORTFOLIO MANAGER                          │
│                                                             │
│   Final allocation considering:                             │
│   - Agent signals                                           │
│   - Risk constraints                                        │
│   - Transaction costs                                       │
│   - Current holdings                                        │
└─────────────────────────────────────────────────────────────┘
```

### Risk Agent Rules

```
RULE 1: Max Position Size
  IF proposed_weight[asset] > max_single_position:
    proposed_weight[asset] = max_single_position

RULE 2: Correlation Limit
  IF correlation(asset_new, existing_portfolio) > max_correlation:
    EITHER reduce weight OR skip asset

RULE 3: Diversification Minimum
  IF count(positions > 1%) < min_positions:
    BLOCK concentrated allocations

RULE 4: Drawdown Protection
  IF current_drawdown > threshold:
    REDUCE all positions by drawdown_reduction_factor
```

### Key Equations

#### Equation 1: Signal Aggregation

$$
S_{asset} = \sum_{i \in agents} w_i \cdot c_i \cdot s_i
$$

Where:
- $w_i$ = agent weight (based on historical accuracy)
- $c_i$ = agent confidence (0-1)
- $s_i$ = agent signal (-1 to 1)

#### Equation 2: Risk Parity Allocation

$$
w_i = \frac{1/\sigma_i}{\sum_{j} 1/\sigma_j}
$$

Where:
- $w_i$ = weight of asset i
- $\sigma_i$ = volatility of asset i

#### Equation 3: Correlation Penalty

$$
w_{adjusted} = w_{proposed} \cdot (1 - \rho_{portfolio})
$$

Where:
- $\rho_{portfolio}$ = correlation with existing portfolio

#### Equation 4: Rebalancing Threshold

$$
\text{Rebalance if } \sum_{i} |w_i^{current} - w_i^{target}| > \theta
$$

Where $\theta$ is typically 0.10 (10%).

## Coinswarm Mapping

### Direct Implementation Points

| Paper Component | Coinswarm Equivalent | Implementation Status |
|-----------------|---------------------|----------------------|
| Risk Agent | Agents with high drawdown_sensitivity | Trait exists |
| Correlation Check | correlation_awareness trait | Trait exists |
| Position Limits | risk_tolerance trait | Trait exists |
| Signal Aggregation | Committee voting | Partial |
| Rebalancing | Not yet implemented | Needed |

### Implementation Code

```python
# CONCEPTUAL: MASA risk agent logic
class RiskAgent:
    """
    Risk agent from MASA paper.

    Paper Reference: Section 4.2 "Risk Management Agent"

    Provides portfolio-level oversight with veto power.
    """
    def __init__(
        self,
        max_position: float = 0.25,
        max_correlation: float = 0.70,
        min_positions: int = 5,
        drawdown_threshold: float = 0.10
    ):
        self.max_position = max_position
        self.max_correlation = max_correlation
        self.min_positions = min_positions
        self.drawdown_threshold = drawdown_threshold

    def evaluate_allocation(
        self,
        proposed: dict[str, float],
        current_portfolio: dict,
        correlations: np.ndarray
    ) -> tuple[dict[str, float], list[str]]:
        """
        Evaluate and potentially modify proposed allocation.

        Returns:
            (adjusted_allocation, list_of_overrides)
        """
        adjusted = proposed.copy()
        overrides = []

        # Rule 1: Position limits
        for asset, weight in adjusted.items():
            if weight > self.max_position:
                adjusted[asset] = self.max_position
                overrides.append(f"Capped {asset} at {self.max_position}")

        # Rule 2: Correlation check
        # ... implementation

        return adjusted, overrides
```

```python
# PRODUCTION: Full risk-balancing allocation
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class AllocationProposal:
    """Proposed portfolio allocation from analysis agents."""
    asset: str
    weight: float
    signal_strength: float  # -1 to 1
    confidence: float  # 0 to 1
    source_agents: list[str]

@dataclass
class RiskCheckResult:
    """Result of risk agent evaluation."""
    approved: bool
    original_weight: float
    adjusted_weight: float
    override_reason: Optional[str]
    risk_score: float  # 0 to 1, higher = more risky

class MASARiskBalancer:
    """
    Implements MASA risk balancing logic.

    Provides portfolio-level risk constraints with override capability.
    """

    def __init__(
        self,
        max_single_position: float = 0.25,
        max_correlation: float = 0.70,
        min_positions: int = 5,
        max_portfolio_volatility: float = 0.20,
        drawdown_threshold: float = 0.10,
        drawdown_reduction: float = 0.50
    ):
        self.max_single_position = max_single_position
        self.max_correlation = max_correlation
        self.min_positions = min_positions
        self.max_portfolio_volatility = max_portfolio_volatility
        self.drawdown_threshold = drawdown_threshold
        self.drawdown_reduction = drawdown_reduction

    def check_proposal(
        self,
        proposal: AllocationProposal,
        current_holdings: dict[str, float],
        correlation_matrix: np.ndarray,
        asset_volatilities: dict[str, float],
        current_drawdown: float
    ) -> RiskCheckResult:
        """
        Check single allocation proposal against risk rules.
        """
        adjusted_weight = proposal.weight
        override_reason = None
        risk_score = 0.0

        # Rule 1: Position size limit
        if adjusted_weight > self.max_single_position:
            adjusted_weight = self.max_single_position
            override_reason = f"Position capped at {self.max_single_position:.0%}"
            risk_score += 0.3

        # Rule 2: Correlation with existing portfolio
        if current_holdings:
            portfolio_correlation = self._calculate_portfolio_correlation(
                proposal.asset, current_holdings, correlation_matrix
            )
            if portfolio_correlation > self.max_correlation:
                reduction = 1 - (portfolio_correlation - self.max_correlation)
                adjusted_weight *= max(0.5, reduction)
                override_reason = f"High correlation ({portfolio_correlation:.2f})"
                risk_score += 0.2

        # Rule 3: Drawdown protection
        if current_drawdown > self.drawdown_threshold:
            adjusted_weight *= self.drawdown_reduction
            override_reason = f"Drawdown protection ({current_drawdown:.1%} DD)"
            risk_score += 0.4

        # Rule 4: Volatility contribution
        if proposal.asset in asset_volatilities:
            asset_vol = asset_volatilities[proposal.asset]
            if asset_vol > self.max_portfolio_volatility:
                vol_scale = self.max_portfolio_volatility / asset_vol
                adjusted_weight *= vol_scale
                risk_score += 0.1

        return RiskCheckResult(
            approved=adjusted_weight > 0.01,
            original_weight=proposal.weight,
            adjusted_weight=adjusted_weight,
            override_reason=override_reason,
            risk_score=min(1.0, risk_score)
        )

    def balance_portfolio(
        self,
        proposals: list[AllocationProposal],
        current_holdings: dict[str, float],
        correlation_matrix: np.ndarray,
        asset_volatilities: dict[str, float],
        current_drawdown: float
    ) -> dict[str, float]:
        """
        Balance full portfolio considering all proposals.
        """
        # Check each proposal
        checked = []
        for proposal in proposals:
            result = self.check_proposal(
                proposal,
                current_holdings,
                correlation_matrix,
                asset_volatilities,
                current_drawdown
            )
            if result.approved:
                checked.append((proposal.asset, result.adjusted_weight))

        # Ensure minimum diversification
        if len(checked) < self.min_positions:
            # Scale up weights to meet minimum
            scale = self.min_positions / max(len(checked), 1)
            checked = [(a, w * scale) for a, w in checked]

        # Normalize to sum to 1 (or less if in drawdown)
        total = sum(w for _, w in checked)
        max_allocation = 1.0 - current_drawdown if current_drawdown > 0 else 1.0

        if total > max_allocation:
            scale = max_allocation / total
            checked = [(a, w * scale) for a, w in checked]

        return dict(checked)

    def _calculate_portfolio_correlation(
        self,
        asset: str,
        holdings: dict[str, float],
        corr_matrix: np.ndarray
    ) -> float:
        """Calculate weighted correlation with existing portfolio."""
        # Simplified: return max correlation with any existing holding
        # Full implementation would use correlation matrix indices
        return 0.5  # Placeholder


def aggregate_agent_signals(
    agent_signals: dict[str, dict],
    agent_weights: dict[str, float],
    min_confidence: float = 0.5
) -> list[AllocationProposal]:
    """
    Aggregate signals from multiple agents into allocation proposals.

    Implements Equation 1 from MASA paper.
    """
    asset_scores: dict[str, dict] = {}

    for agent_name, signals in agent_signals.items():
        agent_weight = agent_weights.get(agent_name, 1.0)

        for asset, signal_data in signals.items():
            if signal_data['confidence'] < min_confidence:
                continue

            weighted_signal = (
                agent_weight *
                signal_data['confidence'] *
                signal_data['signal']
            )

            if asset not in asset_scores:
                asset_scores[asset] = {
                    'total_signal': 0.0,
                    'total_weight': 0.0,
                    'agents': []
                }

            asset_scores[asset]['total_signal'] += weighted_signal
            asset_scores[asset]['total_weight'] += agent_weight * signal_data['confidence']
            asset_scores[asset]['agents'].append(agent_name)

    # Convert to proposals
    proposals = []
    for asset, data in asset_scores.items():
        if data['total_weight'] > 0:
            avg_signal = data['total_signal'] / data['total_weight']

            # Convert signal to weight (positive signal = long position)
            weight = max(0, avg_signal) * 0.25  # Cap at 25%

            if weight > 0.01:  # Minimum 1% position
                proposals.append(AllocationProposal(
                    asset=asset,
                    weight=weight,
                    signal_strength=avg_signal,
                    confidence=data['total_weight'] / len(data['agents']),
                    source_agents=data['agents']
                ))

    return proposals
```

## Cross-References

### Related Papers in Compendium

| Paper | Path | Relationship |
|-------|------|--------------|
| TradingAgents | `./arxiv-2412.20138-trading-agents.md` | Extends this framework |
| M3T | `./arxiv-2212.14670-m3t.md` | Hierarchical approach peer |
| FinRL | `./arxiv-2011.09607-finrl.md` | Foundation |

### Related Concept Files

| Concept | Path | Why Related |
|---------|------|-------------|
| Risk Management | `../concepts/risk-management.md` | Core concept |
| Position Sizing | `../concepts/position-sizing.md` | Allocation methods |
| Three Pillars | `../concepts/three-pillars.md` | Agent specialization |

### Related Code Files

| Implementation | Path | What It Implements |
|----------------|------|-------------------|
| Kelly Criterion | `../code/kelly_criterion.py` | Position sizing |
| Affinity Mutation | `../code/affinity_mutation.py` | Agent evolution |

## Implementation Gaps

### Not Yet Implemented

1. **Correlation Matrix Calculator** - Need real-time correlation tracking
2. **Rebalancing Engine** - Automated rebalancing on threshold
3. **Risk Agent Override** - Veto mechanism in committee

### Blockers

- Correlation data infrastructure
- Portfolio tracking system

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial P0 paper file |
