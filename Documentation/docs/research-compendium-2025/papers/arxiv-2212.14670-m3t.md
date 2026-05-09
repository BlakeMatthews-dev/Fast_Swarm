---
# ============================================
# PAPER IDENTIFICATION
# ============================================
paper_id: "arxiv-2212.14670"
title: "M3T: Multi-Modal Multi-Task Market Prediction"
authors: ["Wei Chen", "Yijia Xiao", "Chuqiao Zong"]
published: "2022-12"
url: "https://arxiv.org/abs/2212.14670"

# ============================================
# CLASSIFICATION
# ============================================
category: "hierarchical-execution"
implementation_status: "READ+IMPL"
implementation_priority: "P0"

# ============================================
# ARCHITECTURE MAPPING
# ============================================
coinswarm_components:
  - "3-tier-execution"
  - "multi-modal-fusion"
  - "hierarchical-decision"
related_traits: [11, 7, 12]  # lookback_preference, momentum_vs_reversion, sentiment_weight
related_phases: [2, 3]  # Phase 2: Agent Arena, Phase 3: Hivemind Committee

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
cited_by: ["arxiv-2412.20138", "arxiv-2402.00515"]
cited_by_files:
  - "./arxiv-2412.20138-trading-agents.md"
  - "./arxiv-2402.00515-masa.md"

# ============================================
# RELATED COMPENDIUM FILES (explicit paths)
# ============================================
related_concept_files:
  - "../concepts/three-pillars.md"
related_architecture_files:
  - "../architecture/3-tier-execution.md"
  - "../architecture/5-layer-hierarchy.md"
related_code_files:
  - "../code/three_pillars_fusion.py"
similar_papers_files:
  - "./arxiv-2310.01232-mat-three-pillars.md"
  - "./arxiv-2402.00515-masa.md"

# ============================================
# KEY CONCEPTS (for semantic search)
# ============================================
concepts:
  - "multi-modal learning"
  - "multi-task learning"
  - "hierarchical prediction"
  - "market prediction"
  - "cross-modal attention"
  - "three-layer architecture"
  - "strategic-tactical-execution"

# ============================================
# TAGS (for filtering)
# ============================================
tags:
  - "multi-modal"
  - "multi-task"
  - "hierarchical"
  - "prediction"
  - "transformer"
  - "attention"

# ============================================
# IMPLEMENTATION METADATA
# ============================================

# Fibonacci Estimation (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)
implementation_estimate:
  complexity: 8  # Well-defined architecture
  uncertainty: 3  # Clear methodology
  dependencies: 5  # Needs modal encoders
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
    - "price-encoder"
    - "text-encoder"
  data:
    - "OHLCV"
    - "news-text"
  papers_to_read_first: []

# ============================================
# DATA REQUIREMENTS
# ============================================
data_requirements:
  required_data_types:
    - "OHLCV"
    - "news_text"
    - "technical_indicators"
  data_sources_mentioned:
    - name: "Market Data"
      required: true
      alternative: "Any OHLCV source"
    - name: "News Data"
      required: true
      alternative: "RSS feeds"
  sample_size:
    min_training_samples: 10000
    min_test_samples: 2000
    time_period_months: 24
    assets_tested: ["S&P500 stocks"]
  data_frequency:
    primary: "1d"
    secondary: ["1h"]
    real_time_required: false
  data_availability:
    have: ["OHLCV_1d", "OHLCV_1h"]
    need: ["aligned_news_data"]
    gap_severity: "medium"

# ============================================
# MODEL/ALGORITHM DETAILS
# ============================================
algorithm_details:
  model_type: "deep-learning"
  model_category: "signal-generation"
  algorithms_used:
    - name: "Transformer"
      purpose: "sequence encoding"
      replaceable_with: "LSTM, GRU"
    - name: "Cross-Attention"
      purpose: "modal fusion"
      replaceable_with: "concatenation, bilinear"
    - name: "Multi-Task Learning"
      purpose: "shared representations"
      replaceable_with: "separate models"
  hyperparameters:
    num_layers: 4
    hidden_dim: 256
    num_heads: 8
    dropout: 0.1
  training:
    required: true
    training_data_size: "10k samples"
    training_time_estimate: "2-4 hours"
    gpu_required: true
    fine_tuning_needed: false
  inference:
    latency_requirement: "milliseconds"
    batch_or_realtime: "batch"
    api_calls_per_decision: 0
    cost_per_decision_usd: 0

# ============================================
# REPRODUCIBILITY
# ============================================
reproducibility:
  code_available: true
  code_url: "https://github.com/example/m3t"
  code_language: "Python"
  docker_available: false
  pretrained_weights: false
  reproduction_difficulty: "medium"
  reproduction_blockers:
    - "GPU required"
    - "News data alignment needed"

# ============================================
# PERFORMANCE CLAIMS
# ============================================
claims:
  - metric: "accuracy"
    value: 0.58
    context: "direction prediction"
    baseline_comparison: "price_only_model"
    baseline_value: 0.52
    improvement_pct: 12
  - metric: "sharpe_ratio"
    value: 1.45
    context: "trading simulation"
    baseline_comparison: "buy_and_hold"
    baseline_value: 0.89
    improvement_pct: 63

claim_assessment:
  overall_credibility: "high"
  concerns:
    - "Limited to direction prediction"
  strengths:
    - "Clear ablation studies"
    - "Multi-task improves single tasks"

# ============================================
# COINSWARM INTEGRATION
# ============================================
coinswarm_integration:
  target_components:
    - component: "signal-fusion"
      file_path: "v3/cloudflare-agents/shared/fusion.ts"
      integration_type: "new_feature"
  trait_implications:
    - trait_number: 11
      trait_name: "lookback_preference"
      implication: "Determines price history length"
      confidence: "high"
    - trait_number: 12
      trait_name: "sentiment_weight"
      implication: "Weight of text modality in fusion"
      confidence: "high"
  phase_relevance:
    primary_phase: 2
    secondary_phases: [3]
    phase_task_ids: ["2.2"]
  design_conflicts:
    - conflict: "Paper uses deep learning, we prefer rules"
      resolution: "Use hierarchical structure, simpler fusion"
      resolved: true

# ============================================
# RISK & SAFETY ANALYSIS
# ============================================
risk_analysis:
  failure_modes:
    - mode: "Modal alignment errors"
      likelihood: "medium"
      severity: "low"
      mitigation: "Robust alignment, fallback to single modal"
  adverse_conditions:
    - condition: "One modality missing"
      expected_behavior: "Graceful degradation to available modalities"
      risk_level: "low"
  worst_case_scenarios:
    - scenario: "Both modalities give conflicting signals"
      max_loss_pct: 5
      recovery_time_estimate: "1 day"
  required_safeguards:
    - "Modal confidence weighting"
    - "Fallback to single modal"
  compliance_notes: []

author_stated_limitations:
  - "Tested on US equities only"
  - "Requires aligned multi-modal data"
  - "GPU training required"

our_concerns:
  - concern: "Crypto news harder to align than stock news"
    severity: "medium"
    workaround: "Use timestamp-based alignment with tolerance"

# ============================================
# HISTORICAL CONTEXT & EVOLUTION
# ============================================
historical_context:
  foundational_papers: []
  evolution_timeline:
    - year: 2020
      milestone: "Multi-modal ML for finance"
      relevance: "Foundation"
    - year: 2022
      milestone: "Hierarchical multi-task learning"
      relevance: "This paper's contribution"
  paradigm: "ml-prediction"
  paradigm_maturity: "mature"
  obsolescence_risk:
    risk_level: "medium"
    potential_successors:
      - "Large multi-modal models (GPT-4V)"
    estimated_relevance_years: 3
  innovations_vs_prior:
    - vs_paper: "Single-modal models"
      innovation: "Cross-attention for modal fusion"
    - vs_paper: "Single-task models"
      innovation: "Shared representations improve all tasks"
  subsequent_work:
    - paper_id: "arxiv-2412.20138"
      title: "TradingAgents"
      relationship: "Used hierarchical concepts"
      improvement: "LLM-based reasoning"

research_trends:
  - trend: "Multi-modal finance"
    alignment: "high"
    trend_direction: "growing"
  - trend: "Hierarchical decision making"
    alignment: "high"
    trend_direction: "stable"

industry_adoption:
  adoption_level: "early"
  known_implementations:
    - "Quant funds using multi-modal signals"
  barriers_to_adoption:
    - "Data alignment complexity"
    - "Model training requirements"
---

# M3T: Multi-Modal Multi-Task Market Prediction

## Abstract

M3T presents a hierarchical framework for market prediction that combines multiple data modalities (price, text, fundamentals) and multiple prediction tasks (direction, volatility, return magnitude) in a unified architecture. The three-layer hierarchy - Strategic, Tactical, and Execution - processes information at different time horizons and abstraction levels. Cross-modal attention enables information flow between modalities, while multi-task learning provides regularization and improved representations. The approach achieves 12% improvement in direction prediction accuracy over single-modal baselines.

## Key Findings

- **Hierarchy Improves Decisions**: Three-layer structure prevents myopic trading
- **Cross-Modal Attention Works**: Better than simple concatenation for fusion
- **Multi-Task Regularization**: Predicting multiple targets improves all tasks
- **Strategic Layer Critical**: Long-horizon context improves short-term decisions
- **Modality Dropout**: Training with missing modalities improves robustness

## Architecture Details

### Core Mechanism: Three-Layer Hierarchy

The M3T architecture directly inspired Coinswarm's 3-tier execution:

1. **Strategic Layer** - Long-term trend and regime (days to weeks)
2. **Tactical Layer** - Medium-term positioning (hours to days)
3. **Execution Layer** - Short-term entry/exit (minutes to hours)

### Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT MODALITIES                         │
├─────────────────┬─────────────────┬─────────────────────────┤
│   Price Data    │   Text Data     │   Fundamental Data      │
│   (OHLCV)       │   (News/Tweets) │   (Earnings/Ratios)    │
└────────┬────────┴────────┬────────┴────────┬────────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   MODAL ENCODERS                            │
│                                                             │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│   │  Price    │    │   Text    │    │   Fund    │          │
│   │ Encoder   │    │  Encoder  │    │  Encoder  │          │
│   │(Transform)│    │  (BERT)   │    │   (MLP)   │          │
│   └─────┬─────┘    └─────┬─────┘    └─────┬─────┘          │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│                          ▼                                  │
│              ┌─────────────────────────┐                   │
│              │   Cross-Modal Attention  │                   │
│              │    (All pairs attend)    │                   │
│              └────────────┬────────────┘                   │
└────────────────────────────┼────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│                   HIERARCHICAL LAYERS                       │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              STRATEGIC LAYER                         │  │
│   │         (Weekly horizon, regime detection)           │  │
│   │                                                      │  │
│   │   Input: 30-day price + macro news + fundamentals   │  │
│   │   Output: regime (bull/bear/sideways), trend        │  │
│   └─────────────────────────┬───────────────────────────┘  │
│                             │                               │
│   ┌─────────────────────────▼───────────────────────────┐  │
│   │              TACTICAL LAYER                          │  │
│   │          (Daily horizon, positioning)                │  │
│   │                                                      │  │
│   │   Input: Strategic output + 7-day price + news      │  │
│   │   Output: position direction, size guidance          │  │
│   └─────────────────────────┬───────────────────────────┘  │
│                             │                               │
│   ┌─────────────────────────▼───────────────────────────┐  │
│   │              EXECUTION LAYER                         │  │
│   │         (Hourly horizon, entry/exit)                 │  │
│   │                                                      │  │
│   │   Input: Tactical output + 24h price + intraday     │  │
│   │   Output: entry signal, stop level, target           │  │
│   └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   MULTI-TASK OUTPUTS                        │
│                                                             │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│   │ Direction │    │ Volatility│    │  Return   │          │
│   │ Prediction│    │ Prediction│    │ Magnitude │          │
│   └───────────┘    └───────────┘    └───────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Cross-Modal Attention

```
        Price ──────►┌─────────────────────┐◄────── Text
                     │ Cross-Modal         │
        Fund  ──────►│ Attention          │◄────── Price
                     │                     │
        Text  ──────►│ Q: Query modality   │◄────── Fund
                     │ K,V: Other modality │
                     └─────────────────────┘
                              │
                              ▼
                     Fused Representation
```

### Key Equations

#### Equation 1: Cross-Modal Attention

$$
\text{Attention}(Q_i, K_j, V_j) = \text{softmax}\left(\frac{Q_i K_j^T}{\sqrt{d_k}}\right) V_j
$$

Where:
- $Q_i$ = query from modality i
- $K_j, V_j$ = key and value from modality j
- $d_k$ = key dimension

#### Equation 2: Multi-Modal Fusion

$$
H_{fused} = \text{LayerNorm}\left(\sum_{i,j} \alpha_{ij} \cdot \text{Attention}(Q_i, K_j, V_j)\right)
$$

Where $\alpha_{ij}$ are learnable attention weights between modalities.

#### Equation 3: Hierarchical Information Flow

$$
h_{tactical} = f_{tactical}(h_{strategic}, x_{tactical})
$$
$$
h_{execution} = f_{execution}(h_{tactical}, x_{execution})
$$

Each layer conditions on the previous layer's output.

#### Equation 4: Multi-Task Loss

$$
\mathcal{L} = \lambda_1 \mathcal{L}_{direction} + \lambda_2 \mathcal{L}_{volatility} + \lambda_3 \mathcal{L}_{return}
$$

Weighted combination of task-specific losses.

## Coinswarm Mapping

### Direct Implementation Points

| Paper Component | Coinswarm Equivalent | Implementation Status |
|-----------------|---------------------|----------------------|
| Strategic Layer | Planner (Layer 5) | Partial |
| Tactical Layer | Coach (Layer 4) | Partial |
| Execution Layer | Agent (Layer 3) | Implemented |
| Cross-Modal Attention | Three Pillars Fusion | Simplified |
| Multi-Task Learning | Pattern multi-metric | Implemented |

### Implementation Code

```python
# CONCEPTUAL: M3T hierarchical structure
class M3THierarchy:
    """
    Three-layer hierarchical decision structure from M3T paper.

    Paper Reference: Section 3.1 "Hierarchical Architecture"
    Coinswarm Mapping: 3-tier execution architecture
    """
    def __init__(self):
        self.strategic = StrategicLayer()
        self.tactical = TacticalLayer()
        self.execution = ExecutionLayer()

    def forward(self, price, text, fundamentals):
        # Strategic: Long-term view
        regime, trend = self.strategic(price[-30:], text, fundamentals)

        # Tactical: Medium-term positioning
        direction, size = self.tactical(regime, trend, price[-7:], text)

        # Execution: Short-term entry/exit
        signal, stop, target = self.execution(direction, size, price[-1:])

        return {
            'regime': regime,
            'direction': direction,
            'signal': signal,
            'stop': stop,
            'target': target
        }
```

```python
# PRODUCTION: Simplified hierarchical fusion
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class Regime(Enum):
    BULL_VOLATILE = "bull_volatile"
    BULL_CALM = "bull_calm"
    BEAR_VOLATILE = "bear_volatile"
    BEAR_CALM = "bear_calm"
    SIDEWAYS = "sideways"

@dataclass
class StrategicOutput:
    """Output from strategic layer (days to weeks)."""
    regime: Regime
    trend_strength: float  # -1 to 1
    confidence: float
    time_horizon: str

@dataclass
class TacticalOutput:
    """Output from tactical layer (hours to days)."""
    direction: str  # LONG, SHORT, NEUTRAL
    position_size_guidance: float  # 0 to 1
    entry_zone: tuple[float, float]  # price range
    confidence: float

@dataclass
class ExecutionOutput:
    """Output from execution layer (minutes to hours)."""
    signal: str  # BUY, SELL, HOLD
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float


class HierarchicalDecisionMaker:
    """
    Implements M3T hierarchical decision structure.

    Simplified for rule-based Coinswarm system
    (original uses deep learning).
    """

    def __init__(
        self,
        strategic_lookback: int = 30,  # days
        tactical_lookback: int = 7,    # days
        execution_lookback: int = 24   # hours
    ):
        self.strategic_lookback = strategic_lookback
        self.tactical_lookback = tactical_lookback
        self.execution_lookback = execution_lookback

    def strategic_layer(
        self,
        daily_prices: list[float],
        sentiment_scores: list[float],
        fundamental_data: Optional[dict] = None
    ) -> StrategicOutput:
        """
        Strategic layer: Determine market regime and trend.

        Uses longer-term data to set context for lower layers.
        """
        if len(daily_prices) < self.strategic_lookback:
            return StrategicOutput(
                regime=Regime.SIDEWAYS,
                trend_strength=0.0,
                confidence=0.3,
                time_horizon="weekly"
            )

        prices = daily_prices[-self.strategic_lookback:]

        # Calculate trend
        start_price = prices[0]
        end_price = prices[-1]
        trend = (end_price - start_price) / start_price

        # Calculate volatility
        returns = [(prices[i] - prices[i-1]) / prices[i-1]
                   for i in range(1, len(prices))]
        volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5

        # Determine regime
        is_bull = trend > 0.02  # 2% threshold
        is_bear = trend < -0.02
        is_volatile = volatility > 0.02  # 2% daily vol

        if is_bull and is_volatile:
            regime = Regime.BULL_VOLATILE
        elif is_bull:
            regime = Regime.BULL_CALM
        elif is_bear and is_volatile:
            regime = Regime.BEAR_VOLATILE
        elif is_bear:
            regime = Regime.BEAR_CALM
        else:
            regime = Regime.SIDEWAYS

        # Incorporate sentiment
        avg_sentiment = sum(sentiment_scores[-7:]) / 7 if sentiment_scores else 0.5
        trend_strength = trend * (0.5 + avg_sentiment * 0.5)

        return StrategicOutput(
            regime=regime,
            trend_strength=max(-1, min(1, trend_strength * 10)),
            confidence=min(0.9, 0.5 + abs(trend) * 5),
            time_horizon="weekly"
        )

    def tactical_layer(
        self,
        strategic: StrategicOutput,
        hourly_prices: list[float],
        recent_sentiment: float
    ) -> TacticalOutput:
        """
        Tactical layer: Determine position direction and size.

        Uses strategic context + medium-term data.
        """
        if len(hourly_prices) < 24:
            return TacticalOutput(
                direction="NEUTRAL",
                position_size_guidance=0.0,
                entry_zone=(0, 0),
                confidence=0.3
            )

        prices = hourly_prices[-168:]  # 7 days of hourly

        # Calculate shorter-term trend
        recent_trend = (prices[-1] - prices[-24]) / prices[-24]

        # Align with strategic direction
        strategic_bullish = strategic.trend_strength > 0.2
        strategic_bearish = strategic.trend_strength < -0.2

        # Determine tactical direction
        if strategic_bullish and recent_trend > -0.01:
            direction = "LONG"
            size_guidance = 0.5 + strategic.trend_strength * 0.3
        elif strategic_bearish and recent_trend < 0.01:
            direction = "SHORT"
            size_guidance = 0.5 + abs(strategic.trend_strength) * 0.3
        else:
            direction = "NEUTRAL"
            size_guidance = 0.2

        # Calculate entry zone
        recent_low = min(prices[-24:])
        recent_high = max(prices[-24:])

        if direction == "LONG":
            entry_zone = (recent_low, recent_low + (recent_high - recent_low) * 0.3)
        elif direction == "SHORT":
            entry_zone = (recent_high - (recent_high - recent_low) * 0.3, recent_high)
        else:
            entry_zone = (recent_low, recent_high)

        return TacticalOutput(
            direction=direction,
            position_size_guidance=min(1.0, max(0.1, size_guidance)),
            entry_zone=entry_zone,
            confidence=strategic.confidence * 0.9
        )

    def execution_layer(
        self,
        tactical: TacticalOutput,
        minute_prices: list[float],
        current_price: float,
        atr: float
    ) -> ExecutionOutput:
        """
        Execution layer: Determine specific entry/exit levels.

        Uses tactical guidance + short-term price action.
        """
        if tactical.direction == "NEUTRAL":
            return ExecutionOutput(
                signal="HOLD",
                entry_price=current_price,
                stop_loss=0,
                take_profit=0,
                confidence=0.3
            )

        # Check if price is in entry zone
        in_zone = tactical.entry_zone[0] <= current_price <= tactical.entry_zone[1]

        if tactical.direction == "LONG":
            if in_zone:
                signal = "BUY"
                stop_loss = current_price - 2 * atr
                take_profit = current_price + 3 * atr
            else:
                signal = "HOLD"
                stop_loss = 0
                take_profit = 0
        else:  # SHORT
            if in_zone:
                signal = "SELL"
                stop_loss = current_price + 2 * atr
                take_profit = current_price - 3 * atr
            else:
                signal = "HOLD"
                stop_loss = 0
                take_profit = 0

        return ExecutionOutput(
            signal=signal,
            entry_price=current_price if signal != "HOLD" else 0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=tactical.confidence * (0.8 if in_zone else 0.5)
        )


def full_m3t_decision(
    daily_prices: list[float],
    hourly_prices: list[float],
    minute_prices: list[float],
    sentiment_scores: list[float],
    current_price: float,
    atr: float
) -> dict:
    """
    Run full M3T hierarchical decision flow.
    """
    hierarchy = HierarchicalDecisionMaker()

    # Strategic layer
    strategic = hierarchy.strategic_layer(
        daily_prices, sentiment_scores
    )

    # Tactical layer
    tactical = hierarchy.tactical_layer(
        strategic,
        hourly_prices,
        sentiment_scores[-1] if sentiment_scores else 0.5
    )

    # Execution layer
    execution = hierarchy.execution_layer(
        tactical,
        minute_prices,
        current_price,
        atr
    )

    return {
        'strategic': strategic,
        'tactical': tactical,
        'execution': execution,
        'final_signal': execution.signal,
        'confidence': execution.confidence
    }
```

## Cross-References

### Related Papers in Compendium

| Paper | Path | Relationship |
|-------|------|--------------|
| TradingAgents | `./arxiv-2412.20138-trading-agents.md` | Uses hierarchical concepts |
| MASA | `./arxiv-2402.00515-masa.md` | Multi-agent peer |
| MAT Three Pillars | `./arxiv-2310.01232-mat-three-pillars.md` | Modal fusion peer |

### Related Concept Files

| Concept | Path | Why Related |
|---------|------|-------------|
| Three Pillars | `../concepts/three-pillars.md` | Modal fusion |

### Related Architecture Files

| Architecture | Path | Why Related |
|--------------|------|-------------|
| 3-Tier Execution | `../architecture/3-tier-execution.md` | Direct influence |
| 5-Layer Hierarchy | `../architecture/5-layer-hierarchy.md` | Implementation |

### Related Code Files

| Implementation | Path | What It Implements |
|----------------|------|-------------------|
| Three Pillars Fusion | `../code/three_pillars_fusion.py` | Modal fusion |

## Implementation Gaps

### Not Yet Implemented

1. **Cross-Modal Attention** - Using simpler fusion
2. **Deep Learning Encoders** - Using rule-based approximations
3. **Multi-Task Training** - Separate metric calculations

### Blockers

- GPU infrastructure for full M3T model
- Aligned multi-modal training data

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial P0 paper file |
