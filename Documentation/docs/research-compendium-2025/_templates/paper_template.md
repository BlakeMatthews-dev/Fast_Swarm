---
# ============================================
# PAPER IDENTIFICATION
# ============================================
paper_id: "arxiv-XXXX.XXXXX"
title: "Full Paper Title"
authors: ["Author1", "Author2"]
published: "2024-XX"
url: "https://arxiv.org/abs/XXXX.XXXXX"

# ============================================
# CLASSIFICATION
# ============================================
category: "category-name"  # See categories list below
implementation_status: "NEW"  # VALIDATES | READ+IMPL | READ+PARTIAL | READ+SKIP | NEW
implementation_priority: "P2"  # P0 | P1 | P2 | P3

# ============================================
# ARCHITECTURE MAPPING
# ============================================
coinswarm_components:
  - "component-name"
related_traits: []  # List of trait numbers (1-16)
related_phases: []  # Phase numbers from implementation roadmap

# ============================================
# RELATIONSHIPS (for graph construction)
# ============================================
validates: []  # Paper IDs this validates
validates_files: []  # e.g., ["./arxiv-2402.00515-masa.md"]
extends: []  # Paper IDs this extends
extends_files: []
contradicts: []  # Paper IDs with conflicting findings
contradicts_files: []
cites: []  # Key citations (paper IDs)
cites_files: []
cited_by: []  # Papers that cite this (auto-populated)
cited_by_files: []

# ============================================
# RELATED COMPENDIUM FILES (explicit paths)
# ============================================
related_concept_files: []
  # e.g., - "../concepts/memory-systems.md"
related_architecture_files: []
  # e.g., - "../architecture/5-layer-hierarchy.md"
related_code_files: []
  # e.g., - "../code/kelly_criterion.py"
similar_papers_files: []  # Auto-generated from shared concepts

# ============================================
# KEY CONCEPTS (for semantic search)
# ============================================
concepts:
  - "concept1"
  - "concept2"

# ============================================
# TAGS (for filtering)
# ============================================
tags:
  - "tag1"
  - "tag2"

# ============================================
# IMPLEMENTATION METADATA
# ============================================

# Fibonacci Estimation (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)
implementation_estimate:
  complexity: 5  # 1=trivial, 89=massive refactor
  uncertainty: 3  # 1=well-understood, 89=research needed
  dependencies: 2  # 1=standalone, 89=requires many systems
  total_fib: 8  # Sum or max of above

# T-Shirt Sizing (XS, S, M, L, XL, XXL)
tshirt_size: "M"
tshirt_breakdown:
  code_changes: "S"
  testing_effort: "M"
  integration_work: "S"

# Prerequisites
prerequisites:
  systems: []  # Required infrastructure
  data: []  # Required data feeds
  papers_to_read_first: []  # Prerequisite paper files

# ============================================
# DATA REQUIREMENTS
# ============================================
data_requirements:
  required_data_types:
    - "OHLCV"
  data_sources_mentioned: []
    # - name: "Source Name"
    #   required: false
    #   alternative: "Alternative source"
  sample_size:
    min_training_samples: null
    min_test_samples: null
    time_period_months: null
    assets_tested: []
  data_frequency:
    primary: "1h"
    secondary: []
    real_time_required: false
  data_availability:
    have: []
    need: []
    gap_severity: "low"  # low/medium/high/blocking

# ============================================
# MODEL/ALGORITHM DETAILS
# ============================================
algorithm_details:
  model_type: "rule-based"  # rule-based, ml-classification, ml-regression, rl, llm, hybrid, ensemble
  model_category: "signal-generation"  # signal-generation, risk-management, execution, portfolio-optimization, decision-system
  algorithms_used: []
    # - name: "Algorithm Name"
    #   purpose: "what it does"
    #   replaceable_with: "alternatives"
  hyperparameters: {}
  training:
    required: false
    training_data_size: null
    training_time_estimate: null
    gpu_required: false
    fine_tuning_needed: false
  inference:
    latency_requirement: "seconds"  # milliseconds, seconds, minutes, hours
    batch_or_realtime: "batch"
    api_calls_per_decision: 0
    cost_per_decision_usd: 0

# ============================================
# REPRODUCIBILITY
# ============================================
reproducibility:
  code_available: false
  code_url: null
  code_language: null
  docker_available: false
  pretrained_weights: false
  reproduction_difficulty: "medium"  # easy, medium, hard, impossible
  reproduction_blockers: []

# ============================================
# PERFORMANCE CLAIMS
# ============================================
claims: []
  # - metric: "sharpe_ratio"
  #   value: 1.5
  #   context: "backtested on X"
  #   baseline_comparison: "buy_and_hold"
  #   baseline_value: 0.5
  #   improvement_pct: 200
  #   statistically_significant: true
  #   p_value: 0.05

claim_assessment:
  overall_credibility: "medium"  # low, medium, high
  concerns: []
  strengths: []

# ============================================
# COINSWARM INTEGRATION
# ============================================
coinswarm_integration:
  target_components: []
    # - component: "component-name"
    #   file_path: "v3/cloudflare-agents/..."
    #   integration_type: "new_feature"  # new_feature, enhancement, replacement
  trait_implications: []
    # - trait_number: 7
    #   trait_name: "momentum_vs_reversion"
    #   implication: "how this paper affects this trait"
    #   confidence: "high"  # low, medium, high
  phase_relevance:
    primary_phase: null
    secondary_phases: []
    phase_task_ids: []
  design_conflicts: []
    # - conflict: "description"
    #   resolution: "how resolved"
    #   resolved: true

# ============================================
# RISK & SAFETY ANALYSIS
# ============================================
risk_analysis:
  failure_modes: []
    # - mode: "failure description"
    #   likelihood: "medium"  # low, medium, high
    #   severity: "high"
    #   mitigation: "how to prevent"
  adverse_conditions: []
    # - condition: "market condition"
    #   expected_behavior: "what happens"
    #   risk_level: "high"
  worst_case_scenarios: []
    # - scenario: "description"
    #   max_loss_pct: 10
    #   recovery_time_estimate: "1-2 weeks"
  required_safeguards: []
  compliance_notes: []

author_stated_limitations: []
our_concerns: []
  # - concern: "description"
  #   severity: "medium"
  #   workaround: "solution"

# ============================================
# HISTORICAL CONTEXT & EVOLUTION
# ============================================
historical_context:
  foundational_papers: []
    # - paper_id: "arxiv-XXXX.XXXXX"
    #   title: "Paper Title"
    #   relationship: "how related"
    #   year: 2020
  evolution_timeline: []
    # - year: 2020
    #   milestone: "event"
    #   relevance: "why important"
  paradigm: "classical-ta"  # classical-ta, ml-prediction, rl-optimization, llm-reasoning, multi-agent-llm
  paradigm_maturity: "mature"  # established, mature, emerging, experimental
  obsolescence_risk:
    risk_level: "low"  # low, medium, high
    potential_successors: []
    estimated_relevance_years: 5
  innovations_vs_prior: []
    # - vs_paper: "paper name"
    #   innovation: "what's new"
  subsequent_work: []
    # - paper_id: "arxiv-XXXX.XXXXX"
    #   title: "Paper Title"
    #   relationship: "how it extends this"
    #   improvement: "what's better"

research_trends: []
  # - trend: "trend name"
  #   alignment: "high"  # low, medium, high
  #   trend_direction: "growing"  # growing, stable, declining

industry_adoption:
  adoption_level: "none"  # none, experimental, early, mainstream
  known_implementations: []
  barriers_to_adoption: []
---

# [Paper Title]

## Abstract

[Full abstract from paper]

## Key Findings

- Finding 1
- Finding 2
- Finding 3

## Architecture Details

### Core Mechanism

[Detailed breakdown of the main contribution]

### Decision Flow

```
┌─────────────┐
│   Input     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Process    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Output    │
└─────────────┘
```

### Key Equations

#### Equation 1: [Name]

$$
formula = here
$$

Where:
- $var$ = description

## Coinswarm Mapping

### Direct Implementation Points

| Paper Component | Coinswarm Equivalent | Implementation Status |
|-----------------|---------------------|----------------------|
| Component 1 | Mapping 1 | Status |

### Implementation Code

```python
# CONCEPTUAL: High-level algorithm explanation
def paper_algorithm(inputs):
    """
    Brief description.

    Paper Reference: Section X.X "Name"
    Coinswarm Mapping: How this maps to our system
    """
    pass
```

```python
# PRODUCTION: Copy-pasteable implementation
def production_implementation(
    param1: type1,
    param2: type2,
    *,
    optional: type3 = default
) -> ReturnType:
    """
    Full implementation with error handling.

    Args:
        param1: Description
        param2: Description
        optional: Description

    Returns:
        Description
    """
    pass
```

## Cross-References

### Related Papers in Compendium

| Paper | Path | Relationship |
|-------|------|--------------|
| Paper Name | `./path.md` | How related |

### Related Concept Files

| Concept | Path | Why Related |
|---------|------|-------------|
| Concept Name | `../concepts/file.md` | Reason |

### Related Code Files

| Implementation | Path | What It Implements |
|----------------|------|-------------------|
| Module | `../code/file.py` | Section reference |

## Implementation Gaps

### Not Yet Implemented

1. Gap 1
2. Gap 2

### Blockers

- Blocker 1

## Raw Distillation

[Link to or embed the original distillation if available]

---

## Categories Reference

Valid categories:
- multi-agent-llm
- agent-orchestration
- memory-augmented
- multi-agent-risk
- hierarchical-execution
- genetic-trading
- reliability
- modal-fusion
- verbal-feedback
- position-sizing
- risk-management
- regime-detection
- sentiment-analysis
- technical-analysis
- fundamental-analysis
- portfolio-optimization
- execution-algorithms
- market-microstructure
- reinforcement-learning
- deep-learning
- transformer
- attention-mechanism
- explainable-ai
- (add more as needed)

## Traits Reference

1. risk_tolerance
2. hold_duration_bias
3. volatility_seeking
4. profit_target_greed
5. win_rate_preference
6. drawdown_sensitivity
7. momentum_vs_reversion
8. stop_loss_tightness
9. entry_aggression
10. exit_aggression
11. lookback_preference
12. sentiment_weight
13. news_reactivity
14. sentiment_contrarian
15. funding_rate_sensitivity
16. correlation_awareness
