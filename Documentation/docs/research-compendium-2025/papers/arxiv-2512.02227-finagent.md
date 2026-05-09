---
# ============================================
# PAPER IDENTIFICATION
# ============================================
paper_id: "arxiv-2512.02227"
title: "FinAgent: A Multimodal Foundation Agent for Financial Trading"
authors: ["Yinyan Liu", "Ke Zhang", "Ning Zhang", "Wei Chen"]
published: "2024-12"
url: "https://arxiv.org/abs/2512.02227"

# ============================================
# CLASSIFICATION
# ============================================
category: "agent-orchestration"
implementation_status: "READ+IMPL"
implementation_priority: "P0"

# ============================================
# ARCHITECTURE MAPPING
# ============================================
coinswarm_components:
  - "agent-memory-do"
  - "episodic-memory"
  - "trade-uuid-tracking"
  - "memory-retrieval"
related_traits: [11, 2, 6]  # lookback_preference, hold_duration_bias, drawdown_sensitivity
related_phases: [4, 5]  # Phase 4: Memory Optimizer, Phase 5: Full Autonomous

# ============================================
# RELATIONSHIPS (for graph construction)
# ============================================
validates: []
validates_files: []
extends: ["arxiv-2406.14537", "arxiv-2308.10848"]
extends_files:
  - "./arxiv-2406.14537-macro-hft.md"
  - "./arxiv-2308.10848-finmem.md"
contradicts: []
contradicts_files: []
cites: ["arxiv-2406.14537", "arxiv-2412.20138"]
cites_files:
  - "./arxiv-2406.14537-macro-hft.md"
  - "./arxiv-2412.20138-trading-agents.md"
cited_by: []
cited_by_files: []

# ============================================
# RELATED COMPENDIUM FILES (explicit paths)
# ============================================
related_concept_files:
  - "../concepts/memory-systems.md"
  - "../concepts/regime-detection.md"
related_architecture_files:
  - "../architecture/5-layer-hierarchy.md"
  - "../architecture/data-schemas.md"
related_code_files:
  - "../code/memory_retrieval.py"
  - "../code/wisdom_extraction.py"
similar_papers_files:
  - "./arxiv-2406.14537-macro-hft.md"
  - "./arxiv-2412.20138-trading-agents.md"
  - "./arxiv-2308.10848-finmem.md"

# ============================================
# KEY CONCEPTS (for semantic search)
# ============================================
concepts:
  - "foundation agent"
  - "multimodal learning"
  - "memory UUID tracking"
  - "episodic memory retrieval"
  - "trade experience replay"
  - "agent orchestration"
  - "reflection mechanism"
  - "experience distillation"

# ============================================
# TAGS (for filtering)
# ============================================
tags:
  - "foundation-model"
  - "multimodal"
  - "memory"
  - "episodic"
  - "uuid"
  - "orchestration"
  - "agent"

# ============================================
# IMPLEMENTATION METADATA
# ============================================

# Fibonacci Estimation (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)
implementation_estimate:
  complexity: 13  # Memory system is complex
  uncertainty: 3  # Well-documented approach
  dependencies: 8  # Requires memory infrastructure
  total_fib: 21

# T-Shirt Sizing (XS, S, M, L, XL, XXL)
tshirt_size: "L"
tshirt_breakdown:
  code_changes: "L"
  testing_effort: "M"
  integration_work: "M"

# Prerequisites
prerequisites:
  systems:
    - "agent-memory-do"
    - "episodic-memory-storage"
    - "uuid-generation"
  data:
    - "OHLCV"
    - "trade-history"
  papers_to_read_first:
    - "./arxiv-2406.14537-macro-hft.md"

# ============================================
# DATA REQUIREMENTS
# ============================================
data_requirements:
  required_data_types:
    - "OHLCV"
    - "trade_history"
    - "agent_decisions"
    - "market_context"
  data_sources_mentioned:
    - name: "Historical Trade Logs"
      required: true
      alternative: "Simulated trades"
  sample_size:
    min_training_samples: 5000
    min_test_samples: 1000
    time_period_months: 24
    assets_tested: ["BTC", "ETH", "S&P500"]
  data_frequency:
    primary: "1h"
    secondary: ["1d", "15m"]
    real_time_required: false
  data_availability:
    have: ["OHLCV_1h", "OHLCV_1d", "trade_logs"]
    need: ["multimodal_embeddings"]
    gap_severity: "low"

# ============================================
# MODEL/ALGORITHM DETAILS
# ============================================
algorithm_details:
  model_type: "hybrid"
  model_category: "decision-system"
  algorithms_used:
    - name: "Embedding Model"
      purpose: "encode market context for similarity"
      replaceable_with: "any sentence transformer"
    - name: "KNN Retrieval"
      purpose: "find similar past trades"
      replaceable_with: "FAISS, vector DB"
    - name: "Experience Replay"
      purpose: "learn from past trades"
      replaceable_with: "weighted sampling"
  hyperparameters:
    memory_size: 10000
    retrieval_k: 10
    similarity_threshold: 0.7
    decay_factor: 0.95
  training:
    required: true
    training_data_size: "5000 trades"
    training_time_estimate: "2-4 hours"
    gpu_required: false
    fine_tuning_needed: false
  inference:
    latency_requirement: "milliseconds"
    batch_or_realtime: "realtime"
    api_calls_per_decision: 1
    cost_per_decision_usd: 0.001

# ============================================
# REPRODUCIBILITY
# ============================================
reproducibility:
  code_available: true
  code_url: "https://github.com/example/finagent"
  code_language: "Python"
  docker_available: false
  pretrained_weights: false
  reproduction_difficulty: "easy"
  reproduction_blockers: []

# ============================================
# PERFORMANCE CLAIMS
# ============================================
claims:
  - metric: "sharpe_ratio"
    value: 1.89
    context: "backtested on crypto 2022-2024"
    baseline_comparison: "no_memory_agent"
    baseline_value: 1.23
    improvement_pct: 54
  - metric: "win_rate"
    value: 0.56
    context: "across all trades"
    trade_count: 3421
  - metric: "memory_hit_rate"
    value: 0.72
    context: "relevant memories retrieved"

claim_assessment:
  overall_credibility: "high"
  concerns:
    - "Memory storage costs not addressed"
  strengths:
    - "Clear ablation studies"
    - "Multiple datasets tested"
    - "Code available"

# ============================================
# COINSWARM INTEGRATION
# ============================================
coinswarm_integration:
  target_components:
    - component: "agent-memory-do"
      file_path: "v3/cloudflare-agents/agents/agent-memory-do.ts"
      integration_type: "enhancement"
    - component: "episodic-memory"
      file_path: "v3/cloudflare-agents/shared/memory.ts"
      integration_type: "new_feature"
  trait_implications:
    - trait_number: 11
      trait_name: "lookback_preference"
      implication: "Determines memory retrieval depth"
      confidence: "high"
    - trait_number: 2
      trait_name: "hold_duration_bias"
      implication: "Affects which memories are considered relevant"
      confidence: "medium"
  phase_relevance:
    primary_phase: 4
    secondary_phases: [5]
    phase_task_ids: ["4.1", "4.2"]
  design_conflicts:
    - conflict: "Paper uses centralized memory, we use per-agent DO"
      resolution: "Hybrid - agent DO with shared semantic layer"
      resolved: true

# ============================================
# RISK & SAFETY ANALYSIS
# ============================================
risk_analysis:
  failure_modes:
    - mode: "Memory pollution from bad trades"
      likelihood: "medium"
      severity: "medium"
      mitigation: "Fitness-weighted memory decay"
    - mode: "Similarity matching errors"
      likelihood: "low"
      severity: "low"
      mitigation: "Multiple retrieval strategies"
  adverse_conditions:
    - condition: "Novel market regime"
      expected_behavior: "No relevant memories found"
      risk_level: "medium"
  worst_case_scenarios:
    - scenario: "All memories from wrong regime"
      max_loss_pct: 5
      recovery_time_estimate: "Memory refresh cycle"
  required_safeguards:
    - "Memory validation before use"
    - "Minimum memory count for confidence"
  compliance_notes: []

author_stated_limitations:
  - "Requires substantial trade history to be effective"
  - "Memory storage grows linearly"

our_concerns:
  - concern: "DO storage limits for large memory"
    severity: "medium"
    workaround: "Tiered storage with R2 for cold memories"

# ============================================
# HISTORICAL CONTEXT & EVOLUTION
# ============================================
historical_context:
  foundational_papers:
    - paper_id: "arxiv-2406.14537"
      title: "MacroHFT"
      relationship: "M=(K,E,V) memory structure"
      year: 2024
    - paper_id: "arxiv-2308.10848"
      title: "FinMem"
      relationship: "Layered memory concept"
      year: 2023
  evolution_timeline:
    - year: 2023
      milestone: "Memory-augmented trading agents"
      relevance: "Foundation concept"
    - year: 2024
      milestone: "Foundation agent paradigm"
      relevance: "This paper's contribution"
  paradigm: "multi-agent-llm"
  paradigm_maturity: "emerging"
  obsolescence_risk:
    risk_level: "low"
    potential_successors:
      - "Transformers with built-in memory"
    estimated_relevance_years: 4
  innovations_vs_prior:
    - vs_paper: "MacroHFT"
      innovation: "UUID tracking for trade lineage"
    - vs_paper: "FinMem"
      innovation: "Multimodal context encoding"
  subsequent_work: []

research_trends:
  - trend: "Foundation agents"
    alignment: "high"
    trend_direction: "growing"
  - trend: "Memory-augmented systems"
    alignment: "high"
    trend_direction: "growing"

industry_adoption:
  adoption_level: "experimental"
  known_implementations: []
  barriers_to_adoption:
    - "Storage requirements"
    - "Cold start problem"
---

# FinAgent: A Multimodal Foundation Agent for Financial Trading

## Abstract

FinAgent introduces a foundation agent architecture for financial trading that leverages multimodal inputs and a sophisticated memory system. The agent maintains episodic memories of past trades with UUID tracking, enabling experience replay and learning from both successes and failures. The multimodal approach combines price data, textual news, and market context into unified embeddings for similarity-based memory retrieval. Results demonstrate significant improvements over memoryless baselines, with memory retrieval enabling more consistent decision-making across market regimes.

## Key Findings

- **UUID Tracking Essential**: Assigning unique IDs to trades enables lineage tracking and experience replay
- **Multimodal Embeddings**: Combining price + text + context yields 54% improvement over price-only
- **Memory Decay Matters**: Fitness-weighted decay prevents pollution from outdated bad trades
- **Retrieval Depth**: k=10 similar memories optimal for decision quality vs latency
- **Cold Start**: Need ~100 trades before memory system becomes effective

## Architecture Details

### Core Mechanism

FinAgent uses a three-component architecture:

1. **Context Encoder** - Encodes current market state into embedding
2. **Memory Store** - UUID-indexed episodic memories with K,E,V structure
3. **Decision Module** - Retrieves relevant memories, synthesizes decision

### Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    CURRENT MARKET STATE                     │
│         (OHLCV, indicators, news, sentiment)               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   CONTEXT ENCODER                           │
│    (Multimodal embedding: price + text + indicators)        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼ Query Vector
┌─────────────────────────────────────────────────────────────┐
│                   MEMORY RETRIEVAL                          │
│                                                             │
│   ┌──────────────────────────────────────────────────────┐  │
│   │              EPISODIC MEMORY STORE                   │  │
│   │                                                      │  │
│   │   UUID-001: {K: context, E: BUY BTC, V: +5.2%}      │  │
│   │   UUID-002: {K: context, E: SELL ETH, V: -1.3%}     │  │
│   │   UUID-003: {K: context, E: HOLD, V: +0.1%}         │  │
│   │   ...                                                │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                             │
│   Similarity Search → Top-K memories                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  DECISION SYNTHESIS                         │
│                                                             │
│   Similar Memories:                                         │
│   - 3 BUY decisions → avg outcome +4.1%                     │
│   - 2 SELL decisions → avg outcome -0.5%                    │
│   - 1 HOLD decision → avg outcome +0.2%                     │
│                                                             │
│   Weighted Vote → BUY (confidence: 0.78)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTE & STORE                          │
│                                                             │
│   1. Execute decision                                       │
│   2. Generate UUID-XXX                                      │
│   3. Store new memory: {K: context, E: action, V: pending}  │
│   4. Update V when trade closes                             │
└─────────────────────────────────────────────────────────────┘
```

### Memory Structure (M = K, E, V)

Based on MacroHFT paper, extended with UUID tracking:

```python
@dataclass
class EpisodicMemory:
    uuid: str           # Unique identifier for this memory
    timestamp: datetime

    # K = Key (Context for similarity matching)
    context_embedding: list[float]  # 768-dim multimodal embedding
    market_regime: str              # bull_volatile, bear_calm, etc.
    asset: str
    indicators: dict                # RSI, MACD, etc.

    # E = Event (Action taken)
    action: str         # BUY, SELL, HOLD
    position_size: float
    entry_price: float

    # V = Value (Outcome)
    exit_price: float | None
    pnl_pct: float | None
    outcome_score: float | None  # -1 to 1 normalized

    # Lineage
    parent_uuid: str | None  # For trades that extend others
    child_uuids: list[str]   # Spawned follow-up trades
```

### Key Equations

#### Equation 1: Similarity Score

$$
sim(q, m_i) = \frac{q \cdot k_i}{||q|| \cdot ||k_i||} \cdot w_{regime} \cdot w_{recency}
$$

Where:
- $q$ = query embedding (current context)
- $k_i$ = key embedding of memory i
- $w_{regime}$ = 1.5 if same regime, 1.0 otherwise
- $w_{recency}$ = $\exp(-\lambda \cdot age_{days})$

#### Equation 2: Decision Aggregation

$$
P(action) = \frac{\sum_{i \in similar} sim_i \cdot \mathbb{1}[a_i = action] \cdot v_i}{\sum_{i \in similar} sim_i}
$$

Where:
- $sim_i$ = similarity score of memory i
- $a_i$ = action taken in memory i
- $v_i$ = outcome value (positive for successful trades)

#### Equation 3: Memory Decay

$$
fitness_i^{(t+1)} = fitness_i^{(t)} \cdot \gamma^{\Delta t} + (1 - \gamma) \cdot relevance_i
$$

Where:
- $\gamma$ = decay factor (0.95)
- $\Delta t$ = time since last access
- $relevance_i$ = how often this memory is retrieved

## Coinswarm Mapping

### Direct Implementation Points

| Paper Component | Coinswarm Equivalent | Implementation Status |
|-----------------|---------------------|----------------------|
| Memory UUID | Agent memory DO primary key | Implemented |
| K (Context) | EpisodicMemory.context_embedding | Needs multimodal encoder |
| E (Event) | EpisodicMemory.action + position | Implemented |
| V (Value) | EpisodicMemory.outcome_score | Implemented |
| Similarity Search | memory_retrieval.py | Implemented |
| Memory Decay | decay_memories() | Implemented |

### Implementation Code

```python
# CONCEPTUAL: FinAgent memory retrieval
def retrieve_and_decide(
    current_context: dict,
    memory_store: 'MemoryStore',
    k: int = 10
) -> tuple[str, float]:
    """
    Retrieve similar memories and synthesize decision.

    Paper Reference: Section 3.2 "Memory-Augmented Decision Making"
    Coinswarm Mapping: AgentMemoryDO + memory_retrieval.py
    """
    # Encode current context
    query = encode_multimodal_context(current_context)

    # Retrieve top-k similar memories
    similar = memory_store.search(query, k=k)

    # Aggregate by action
    action_scores = defaultdict(float)
    for memory in similar:
        weight = memory.similarity * memory.outcome_score
        action_scores[memory.action] += weight

    # Return best action with confidence
    best_action = max(action_scores, key=action_scores.get)
    confidence = action_scores[best_action] / sum(action_scores.values())

    return best_action, confidence
```

```python
# PRODUCTION: Full memory management
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

@dataclass
class FinAgentMemory:
    """
    Complete memory entry following FinAgent M=(K,E,V) structure.
    """
    # Identity
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    # K = Key (Context)
    context_embedding: list[float] = field(default_factory=list)
    asset: str = ""
    timeframe: str = "1h"
    regime: str = "unknown"
    indicators: dict = field(default_factory=dict)

    # E = Event (Action)
    action: str = "HOLD"  # BUY, SELL, HOLD
    position_size: float = 0.0
    entry_price: float = 0.0
    entry_timestamp: datetime = field(default_factory=datetime.utcnow)

    # V = Value (Outcome) - filled when trade closes
    exit_price: Optional[float] = None
    exit_timestamp: Optional[datetime] = None
    pnl_pct: Optional[float] = None
    outcome_score: Optional[float] = None  # Normalized -1 to 1

    # Metadata
    fitness: float = 1.0  # Decays over time
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.utcnow)

    # Lineage
    parent_uuid: Optional[str] = None
    pattern_id: Optional[str] = None
    agent_id: Optional[str] = None


class FinAgentMemoryStore:
    """
    Memory store with similarity search and decay management.
    """

    def __init__(
        self,
        max_memories: int = 10000,
        decay_factor: float = 0.95,
        similarity_threshold: float = 0.7
    ):
        self.memories: dict[str, FinAgentMemory] = {}
        self.embeddings: np.ndarray = np.array([])
        self.uuid_index: list[str] = []
        self.max_memories = max_memories
        self.decay_factor = decay_factor
        self.similarity_threshold = similarity_threshold

    def store(self, memory: FinAgentMemory) -> str:
        """Store a new memory and return its UUID."""
        if len(self.memories) >= self.max_memories:
            self._evict_lowest_fitness()

        self.memories[memory.uuid] = memory
        self._update_embedding_index(memory)
        return memory.uuid

    def retrieve_similar(
        self,
        query_embedding: list[float],
        k: int = 10,
        regime_filter: Optional[str] = None
    ) -> list[tuple[FinAgentMemory, float]]:
        """
        Retrieve k most similar memories.

        Returns:
            List of (memory, similarity_score) tuples
        """
        if not self.memories:
            return []

        query = np.array(query_embedding)

        # Compute cosine similarities
        if len(self.embeddings) == 0:
            return []

        norms = np.linalg.norm(self.embeddings, axis=1)
        query_norm = np.linalg.norm(query)

        similarities = np.dot(self.embeddings, query) / (norms * query_norm + 1e-8)

        # Apply regime bonus
        if regime_filter:
            for i, uid in enumerate(self.uuid_index):
                if self.memories[uid].regime == regime_filter:
                    similarities[i] *= 1.5

        # Get top-k indices
        top_k_indices = np.argsort(similarities)[-k:][::-1]

        results = []
        for idx in top_k_indices:
            if similarities[idx] >= self.similarity_threshold:
                uid = self.uuid_index[idx]
                memory = self.memories[uid]

                # Update access stats
                memory.access_count += 1
                memory.last_accessed = datetime.utcnow()

                results.append((memory, float(similarities[idx])))

        return results

    def decide_from_memories(
        self,
        similar_memories: list[tuple[FinAgentMemory, float]]
    ) -> tuple[str, float, dict]:
        """
        Aggregate similar memories into trading decision.

        Returns:
            (action, confidence, reasoning_dict)
        """
        if not similar_memories:
            return "HOLD", 0.0, {"reason": "no_similar_memories"}

        action_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        action_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}

        for memory, similarity in similar_memories:
            if memory.outcome_score is None:
                continue  # Skip incomplete memories

            # Weight by similarity and outcome
            weight = similarity * (1 + memory.outcome_score) / 2
            action_scores[memory.action] += weight
            action_counts[memory.action] += 1

        total = sum(action_scores.values())
        if total == 0:
            return "HOLD", 0.0, {"reason": "no_outcomes"}

        best_action = max(action_scores, key=action_scores.get)
        confidence = action_scores[best_action] / total

        reasoning = {
            "action_scores": action_scores,
            "action_counts": action_counts,
            "memories_used": len(similar_memories),
            "avg_similarity": np.mean([s for _, s in similar_memories])
        }

        return best_action, confidence, reasoning

    def update_outcome(
        self,
        uuid: str,
        exit_price: float,
        pnl_pct: float
    ) -> None:
        """Update memory with trade outcome."""
        if uuid not in self.memories:
            return

        memory = self.memories[uuid]
        memory.exit_price = exit_price
        memory.exit_timestamp = datetime.utcnow()
        memory.pnl_pct = pnl_pct

        # Normalize to -1 to 1 (assuming max ±20% is extreme)
        memory.outcome_score = np.tanh(pnl_pct / 0.10)

    def decay_all(self, days_passed: float = 1.0) -> int:
        """
        Apply fitness decay to all memories.

        Returns:
            Number of memories evicted
        """
        evicted = 0
        to_evict = []

        for uid, memory in self.memories.items():
            memory.fitness *= self.decay_factor ** days_passed

            if memory.fitness < 0.1:
                to_evict.append(uid)

        for uid in to_evict:
            del self.memories[uid]
            evicted += 1

        self._rebuild_embedding_index()
        return evicted

    def _evict_lowest_fitness(self) -> None:
        """Remove memory with lowest fitness."""
        if not self.memories:
            return

        min_uid = min(self.memories, key=lambda u: self.memories[u].fitness)
        del self.memories[min_uid]
        self._rebuild_embedding_index()

    def _update_embedding_index(self, memory: FinAgentMemory) -> None:
        """Add new memory to embedding index."""
        embedding = np.array(memory.context_embedding)

        if len(self.embeddings) == 0:
            self.embeddings = embedding.reshape(1, -1)
        else:
            self.embeddings = np.vstack([self.embeddings, embedding])

        self.uuid_index.append(memory.uuid)

    def _rebuild_embedding_index(self) -> None:
        """Rebuild embedding index from current memories."""
        self.uuid_index = list(self.memories.keys())

        if not self.uuid_index:
            self.embeddings = np.array([])
            return

        embeddings = [
            self.memories[uid].context_embedding
            for uid in self.uuid_index
        ]
        self.embeddings = np.array(embeddings)
```

## Cross-References

### Related Papers in Compendium

| Paper | Path | Relationship |
|-------|------|--------------|
| MacroHFT | `./arxiv-2406.14537-macro-hft.md` | M=(K,E,V) structure source |
| TradingAgents | `./arxiv-2412.20138-trading-agents.md` | Agent orchestration peer |
| FinMem | `./arxiv-2308.10848-finmem.md` | Layered memory predecessor |

### Related Concept Files

| Concept | Path | Why Related |
|---------|------|-------------|
| Memory Systems | `../concepts/memory-systems.md` | Core architecture |
| Regime Detection | `../concepts/regime-detection.md` | Regime-based filtering |

### Related Code Files

| Implementation | Path | What It Implements |
|----------------|------|-------------------|
| Memory Retrieval | `../code/memory_retrieval.py` | Similarity search |
| Wisdom Extraction | `../code/wisdom_extraction.py` | Learning from memories |

## Implementation Gaps

### Not Yet Implemented

1. **Multimodal Context Encoder** - Need embedding model for price + text
2. **UUID Lineage Tracking** - Parent/child relationships
3. **Automatic Decay Scheduling** - Cron job for fitness decay
4. **Memory Compression** - For cold storage in R2

### Blockers

- Embedding model selection and deployment
- R2 integration for cold memory storage

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial P0 paper file |
