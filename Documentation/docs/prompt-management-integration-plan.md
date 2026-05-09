# Coinswarm Prompt Management & Inference Integration Plan

> Comprehensive plan for hierarchical prompt caching, high-throughput agent inference, and evolutionary LLM optimization

---

## Executive Summary

This plan integrates:
1. **Hierarchical prompt composition** with vLLM prefix caching (94% cache ratio)
2. **High-throughput inference** for 200+ concurrent agents (500+ decisions/min)
3. **Uncertainty-gated LLM decisions** with evolutionary cost optimization
4. **Fast backtesting** with compiled patterns + selective LLM calls

**Hardware target:** 2x P40 (48GB VRAM) + 128GB RAM
**Primary model:** GPT-OSS 20B (3.6B active params, 16GB VRAM)
**Throughput goal:** 500+ trading decisions/minute live, 5 years backtest in <10 hours

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROMPT LAYER                                       │
│                                                                             │
│  prompts/                                                                   │
│  ├── _shared/                    ← Level 1-2: Cached across ALL prompts    │
│  │   ├── identity.md                                                       │
│  │   ├── indicators.md                                                     │
│  │   └── output-format.md                                                  │
│  ├── trading-decision/           ← Level 3: Cached per prompt type         │
│  │   ├── _type.md                                                          │
│  │   └── v1.template.md                                                    │
│  └── pattern-discovery/                                                    │
│      └── ...                                                               │
│                                                                             │
│  PromptManager → renders with {{variables}}, returns prefix_hash           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INFERENCE LAYER                                    │
│                                                                             │
│  vLLM Server (OpenAI-compatible API)                                       │
│  ├── Model: GPT-OSS 20B (tensor_parallel=2 for both P40s)                  │
│  ├── Prefix caching: ENABLED                                               │
│  ├── Max concurrent: 64 sequences                                          │
│  └── Continuous batching: auto                                             │
│                                                                             │
│  Throughput: 500-600 decisions/minute with full queue                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT LAYER                                        │
│                                                                             │
│  200+ Agents, each with:                                                   │
│  ├── Personality traits (16 floats, heritable)                             │
│  ├── Assigned patterns (5-10 pattern IDs)                                  │
│  ├── Confidence bounds (lower, upper) ← controls LLM usage                 │
│  └── Current positions & state                                             │
│                                                                             │
│  Decision flow:                                                            │
│  ├── Pattern match → confidence score                                      │
│  ├── If confidence > upper_bound → EXECUTE (no LLM)                        │
│  ├── If confidence < lower_bound → SKIP (no LLM)                           │
│  └── If between bounds → LLM DECIDES (costly)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVOLUTION LAYER                                    │
│                                                                             │
│  Selection Pressure:                                                       │
│  ├── Fitness = trading_performance - llm_cost + llm_edge                   │
│  ├── LLM usage is penalized (compute cost)                                 │
│  ├── LLM edge is rewarded (correct uncertain decisions)                    │
│  └── Evolution finds optimal confidence bounds                             │
│                                                                             │
│  Over generations:                                                         │
│  └── Agents converge to economically optimal LLM usage (~15-25%)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Prompt Infrastructure (DONE)

### Completed
- [x] `prompts/` directory structure with hierarchical components
- [x] `prompts/_shared/identity.md` - Agent identity (Level 1)
- [x] `prompts/_shared/indicators.md` - Indicator definitions (Level 2)
- [x] `prompts/_shared/output-format.md` - JSON requirements (Level 3)
- [x] `prompts/pattern-discovery/_type.md` - Task-specific (Level 4)
- [x] `prompts/pattern-discovery/v1.template.md` - Composition template
- [x] `local-utilities/prompt_manager.py` - Full implementation with:
  - Prefix chain loading
  - `{{variable}}` substitution
  - `batch_context` support
  - SQLite tracking (`prompts.sqlite`)
  - Fitness measurement
  - CLI tools

### Verified
```bash
$ python local-utilities/prompt_manager.py test
Prefix Hash: 90b74b36a91f5606
Cache Ratio: 94.3%
```

---

## Phase 2: Trading Decision Prompt

### Create trading-decision prompt type

```
prompts/trading-decision/
├── _type.md              # Trading decision task
└── v1.template.md        # Composition with market data
```

### Template structure

```markdown
---
type: trading_decision
version: 1
prefixes:
  - _shared/identity.md
  - _shared/indicators.md
  - trading-decision/_type.md
  - _shared/output-format.md
variables:
  - agent_traits
  - agent_patterns
  - pattern_confidence
  - market_summary
---

## Agent Configuration
Traits: {{agent_traits}}
Active Patterns: {{agent_patterns}}
Pattern Confidence: {{pattern_confidence}}

## Current Market
{{market_summary}}

## Decision Required
Should this agent enter a trade? Output JSON only.
```

### Tasks
- [ ] Create `prompts/trading-decision/_type.md`
- [ ] Create `prompts/trading-decision/v1.template.md`
- [ ] Test with PromptManager
- [ ] Verify cache ratio >90%

---

## Phase 3: vLLM Server Setup

### Installation

```bash
pip install vllm

# Download GPT-OSS 20B
ollama pull gpt-oss:20b
# Or from HuggingFace for vLLM
```

### Server configuration

```python
# vllm_server.py
from vllm import LLM, SamplingParams
from vllm.entrypoints.openai.api_server import run_server

llm = LLM(
    model="openai/gpt-oss-20b",
    tensor_parallel_size=2,           # Use both P40s
    enable_prefix_caching=True,       # CRITICAL
    max_num_seqs=64,                  # Concurrent sequences
    max_num_batched_tokens=16384,
    gpu_memory_utilization=0.92,
    trust_remote_code=True,
)

# Serves OpenAI-compatible API on port 8000
```

### Startup script

```bash
#!/bin/bash
# start_vllm.sh

python -m vllm.entrypoints.openai.api_server \
    --model openai/gpt-oss-20b \
    --tensor-parallel-size 2 \
    --enable-prefix-caching \
    --max-num-seqs 64 \
    --gpu-memory-utilization 0.92 \
    --port 8000
```

### Tasks
- [ ] Install vLLM
- [ ] Download GPT-OSS 20B model
- [ ] Create `start_vllm.sh` script
- [ ] Test prefix caching is working
- [ ] Benchmark throughput

---

## Phase 4: Agent Decision System

### Core decision logic

```python
# local-utilities/agent_decision.py

from dataclasses import dataclass
from enum import Enum
from prompt_manager import PromptManager

class DecisionType(Enum):
    SKIP = "skip"           # Confidence too low
    EXECUTE = "execute"     # Confidence high enough
    LLM_DECIDE = "llm"      # In uncertainty zone

@dataclass
class AgentTraits:
    # Core 16 traits
    risk_tolerance: float
    hold_duration_bias: float
    # ... other traits ...

    # Uncertainty bounds (evolvable)
    confidence_lower_bound: float = 0.4
    confidence_upper_bound: float = 0.75

@dataclass
class Decision:
    action: str              # "long", "short", "skip"
    confidence: float
    used_llm: bool
    llm_cost: float = 0.0
    reasoning: str = ""

class AgentDecisionEngine:
    def __init__(self, vllm_url: str = "http://localhost:8000"):
        self.pm = PromptManager()
        self.client = AsyncOpenAI(base_url=f"{vllm_url}/v1")
        self.llm_cost_per_call = 0.01  # Fitness penalty

    def evaluate_patterns(self, agent: Agent, indicators: dict) -> float:
        """Fast pattern matching, returns confidence 0-1."""
        confidences = []
        for pattern in agent.patterns:
            if pattern.matches(indicators):
                confidences.append(pattern.confidence)

        if not confidences:
            return 0.0
        return max(confidences)

    async def decide(
        self,
        agent: Agent,
        indicators: dict,
        market_context: str  # Batch context (cached)
    ) -> Decision:
        """Make trading decision with uncertainty-gated LLM."""

        pattern_confidence = self.evaluate_patterns(agent, indicators)

        # Below lower bound → skip (no trade)
        if pattern_confidence < agent.traits.confidence_lower_bound:
            return Decision(
                action="skip",
                confidence=pattern_confidence,
                used_llm=False
            )

        # Above upper bound → execute (high confidence)
        if pattern_confidence > agent.traits.confidence_upper_bound:
            return Decision(
                action=self._pattern_direction(agent, indicators),
                confidence=pattern_confidence,
                used_llm=False
            )

        # In uncertainty zone → ask LLM
        return await self._llm_decision(
            agent, indicators, pattern_confidence, market_context
        )

    async def _llm_decision(
        self,
        agent: Agent,
        indicators: dict,
        pattern_confidence: float,
        market_context: str
    ) -> Decision:
        """Call LLM for uncertain decisions."""

        prompt_result = self.pm.render(
            "trading_decision",
            variables={
                "agent_traits": agent.traits.to_json(),
                "agent_patterns": [p.name for p in agent.patterns],
                "pattern_confidence": pattern_confidence,
                "market_summary": self._summarize_indicators(indicators),
            },
            batch_context=market_context
        )

        response = await self.client.completions.create(
            model="gpt-oss-20b",
            prompt=prompt_result["prompt"],
            max_tokens=100,
        )

        decision = self._parse_response(response.choices[0].text)
        decision.used_llm = True
        decision.llm_cost = self.llm_cost_per_call

        return decision
```

### Tasks
- [ ] Create `local-utilities/agent_decision.py`
- [ ] Implement pattern matching (fast path)
- [ ] Implement LLM decision (slow path)
- [ ] Add async batch processing
- [ ] Test with mock agents

---

## Phase 5: Agent Swarm Orchestration

### Concurrent decision making

```python
# local-utilities/agent_swarm.py

import asyncio
from typing import List
from agent_decision import AgentDecisionEngine, Decision

class AgentSwarm:
    def __init__(self, agents: List[Agent], vllm_url: str):
        self.agents = agents
        self.engine = AgentDecisionEngine(vllm_url)

    async def decision_cycle(self, market_data: dict) -> List[Decision]:
        """All agents decide concurrently."""

        # Prepare batch context (cached for all agents)
        market_context = self._format_market_context(market_data)
        indicators = self._compute_indicators(market_data)

        # Launch all decisions concurrently
        tasks = [
            self.engine.decide(agent, indicators, market_context)
            for agent in self.agents
        ]

        # vLLM batches automatically
        decisions = await asyncio.gather(*tasks)

        return list(zip(self.agents, decisions))

    def _format_market_context(self, market_data: dict) -> str:
        """Format market data as batch context (shared prefix)."""
        return f"""
## Current Market State
Timestamp: {market_data['timestamp']}

### Candles
1D: {self._format_candles(market_data['candles_1d'][-30:])}
1H: {self._format_candles(market_data['candles_1h'][-168:])}
15m: {self._format_candles(market_data['candles_15m'][-96:])}

### Order Book
Bids: {market_data['orderbook']['bids'][:10]}
Asks: {market_data['orderbook']['asks'][:10]}
"""

# Usage
async def main():
    agents = load_agents()  # 200+ agents
    swarm = AgentSwarm(agents, "http://localhost:8000")

    while True:
        market_data = fetch_market_data()
        decisions = await swarm.decision_cycle(market_data)

        for agent, decision in decisions:
            if decision.action != "skip":
                execute_trade(agent, decision)

        await asyncio.sleep(60)  # Next cycle
```

### Tasks
- [ ] Create `local-utilities/agent_swarm.py`
- [ ] Implement batch context formatting
- [ ] Add decision logging
- [ ] Create execution dispatcher
- [ ] Test with 200+ concurrent agents

---

## Phase 6: Fast Backtesting

### Hybrid backtest engine

```python
# local-utilities/fast_backtest.py

import numpy as np
from typing import List, Dict
from agent_decision import AgentDecisionEngine

class HybridBacktester:
    """Fast backtesting with selective LLM calls."""

    def __init__(self, agents: List[Agent], candles: np.ndarray):
        self.agents = agents
        self.candles = candles
        self.indicators = self._precompute_indicators(candles)
        self.engine = AgentDecisionEngine()

        # Results tracking
        self.results = {agent.id: BacktestResult() for agent in agents}

    def _precompute_indicators(self, candles: np.ndarray) -> Dict[str, np.ndarray]:
        """Vectorized indicator computation for ALL candles."""
        return {
            "rsi14": compute_rsi(candles, 14),
            "macd": compute_macd(candles),
            "sma20": compute_sma(candles, 20),
            # ... all indicators
        }

    def run(self) -> Dict[str, BacktestResult]:
        """Run full backtest."""

        n_candles = len(self.candles)
        llm_queue = []  # Batch LLM calls

        for i in range(n_candles):
            indicators_at_i = {k: v[i] for k, v in self.indicators.items()}

            for agent in self.agents:
                decision_type, confidence = self._fast_evaluate(
                    agent, indicators_at_i
                )

                if decision_type == "execute":
                    self._record_trade(agent, i, confidence, used_llm=False)

                elif decision_type == "llm":
                    # Queue for batch LLM processing
                    llm_queue.append((agent, i, indicators_at_i, confidence))

                    # Process LLM queue in batches
                    if len(llm_queue) >= 64:
                        self._process_llm_batch(llm_queue)
                        llm_queue = []

            # Progress
            if i % 10000 == 0:
                print(f"Processed {i}/{n_candles} candles")

        # Final LLM batch
        if llm_queue:
            self._process_llm_batch(llm_queue)

        return self.results

    def _fast_evaluate(self, agent: Agent, indicators: dict) -> tuple:
        """Fast pattern matching (no LLM)."""
        confidence = 0.0

        for pattern in agent.patterns:
            if self._pattern_matches(pattern, indicators):
                confidence = max(confidence, pattern.confidence)

        if confidence < agent.traits.confidence_lower_bound:
            return "skip", confidence
        elif confidence > agent.traits.confidence_upper_bound:
            return "execute", confidence
        else:
            return "llm", confidence

    def _pattern_matches(self, pattern: Pattern, indicators: dict) -> bool:
        """Evaluate pattern conditions (vectorizable)."""
        for condition in pattern.entry_conditions:
            indicator_value = indicators.get(condition.indicator, 0)

            if condition.operator == "<" and not (indicator_value < condition.value):
                return False
            elif condition.operator == ">" and not (indicator_value > condition.value):
                return False
            # ... other operators

        return True

    async def _process_llm_batch(self, queue: list):
        """Process queued LLM decisions in batch."""

        # Format batch context (same candle data for batch)
        batch_context = self._format_batch_context(queue[0][1])  # Use first candle idx

        tasks = [
            self.engine._llm_decision(agent, indicators, confidence, batch_context)
            for agent, candle_idx, indicators, confidence in queue
        ]

        decisions = await asyncio.gather(*tasks)

        for (agent, candle_idx, _, _), decision in zip(queue, decisions):
            if decision.action != "skip":
                self._record_trade(agent, candle_idx, decision.confidence, used_llm=True)

            # Track LLM usage for fitness
            self.results[agent.id].llm_calls += 1
            self.results[agent.id].llm_cost += decision.llm_cost
```

### Backtest speed estimates

| LLM Usage | 5 Years × 200 Agents | Time |
|-----------|---------------------|------|
| 0% (patterns only) | 2.6M candles × 200 | 20 min |
| 10% LLM | + 52M LLM calls | 3 hours |
| 20% LLM | + 104M LLM calls | 6 hours |
| 25% LLM | + 130M LLM calls | 8 hours |

### Tasks
- [ ] Create `local-utilities/fast_backtest.py`
- [ ] Implement vectorized indicator computation
- [ ] Implement fast pattern matching
- [ ] Add LLM batch queue processing
- [ ] Benchmark with real data

---

## Phase 7: Evolutionary Fitness with LLM Cost

### Fitness calculation

```python
# local-utilities/evolution/fitness.py

@dataclass
class BacktestResult:
    # Trading performance
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    # LLM usage
    llm_calls: int = 0
    llm_cost: float = 0.0
    llm_profitable: int = 0  # LLM decisions that were profitable

def calculate_fitness(result: BacktestResult) -> float:
    """Calculate agent fitness with LLM cost penalty."""

    # Base trading performance (0-80 points)
    win_rate = result.winning_trades / max(result.total_trades, 1)

    performance_score = (
        min(result.sharpe_ratio * 10, 25) +      # 0-25 points
        min(win_rate * 30, 25) +                  # 0-25 points
        min(result.total_pnl / 100, 20) +         # 0-20 points
        max(0, 10 - result.max_drawdown / 5)      # 0-10 points
    )

    # LLM cost penalty (0-15 points)
    llm_penalty = result.llm_cost  # Direct cost

    # LLM edge bonus (0-10 points)
    if result.llm_calls > 0:
        llm_accuracy = result.llm_profitable / result.llm_calls
        llm_edge = (llm_accuracy - 0.5) * 20  # +10 if 100% accurate, -10 if 0%
    else:
        llm_edge = 0

    # Final fitness
    fitness = performance_score - llm_penalty + llm_edge

    return max(0, min(100, fitness))
```

### Trait mutation with bounds

```python
# local-utilities/evolution/mutation.py

def mutate_agent(agent: Agent, mutation_rate: float = 0.1) -> Agent:
    """Mutate agent traits including confidence bounds."""

    new_traits = {}

    for trait_name, value in agent.traits.items():
        if random.random() < mutation_rate:
            # Gaussian mutation
            new_value = value + random.gauss(0, 0.05)
            new_value = max(0.0, min(1.0, new_value))
            new_traits[trait_name] = new_value
        else:
            new_traits[trait_name] = value

    # Ensure lower_bound < upper_bound
    if new_traits["confidence_lower_bound"] > new_traits["confidence_upper_bound"]:
        new_traits["confidence_lower_bound"], new_traits["confidence_upper_bound"] = \
            new_traits["confidence_upper_bound"], new_traits["confidence_lower_bound"]

    # Minimum uncertainty gap (prevent trivial solutions)
    min_gap = 0.1
    if new_traits["confidence_upper_bound"] - new_traits["confidence_lower_bound"] < min_gap:
        midpoint = (new_traits["confidence_upper_bound"] + new_traits["confidence_lower_bound"]) / 2
        new_traits["confidence_lower_bound"] = midpoint - min_gap / 2
        new_traits["confidence_upper_bound"] = midpoint + min_gap / 2

    return Agent(traits=new_traits, patterns=agent.patterns)
```

### Tasks
- [ ] Create `local-utilities/evolution/fitness.py`
- [ ] Create `local-utilities/evolution/mutation.py`
- [ ] Add confidence bounds to agent traits schema
- [ ] Integrate with existing evolution system
- [ ] Test evolutionary pressure on LLM usage

---

## Phase 8: Monitoring & Dashboards

### Metrics to track

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Inference metrics
llm_requests_total = Counter('llm_requests_total', 'Total LLM requests', ['agent_id'])
llm_latency = Histogram('llm_latency_seconds', 'LLM request latency')
prefix_cache_hits = Counter('prefix_cache_hits', 'Prefix cache hits')

# Agent metrics
agent_llm_usage = Gauge('agent_llm_usage_ratio', 'LLM usage ratio', ['agent_id'])
agent_fitness = Gauge('agent_fitness', 'Agent fitness score', ['agent_id'])
agent_confidence_bounds = Gauge('agent_confidence_bounds', 'Confidence bounds', ['agent_id', 'bound'])

# Backtest metrics
backtest_progress = Gauge('backtest_progress', 'Backtest progress %')
backtest_llm_queue = Gauge('backtest_llm_queue', 'LLM queue size')
```

### Tasks
- [ ] Add Prometheus metrics
- [ ] Create Grafana dashboard
- [ ] Add LLM usage tracking per agent
- [ ] Add confidence bounds evolution visualization

---

## Implementation Timeline

| Phase | Description | Effort | Dependencies |
|-------|-------------|--------|--------------|
| 1 | Prompt Infrastructure | DONE | - |
| 2 | Trading Decision Prompt | 2 hours | Phase 1 |
| 3 | vLLM Server Setup | 4 hours | GPT-OSS model download |
| 4 | Agent Decision System | 4 hours | Phase 2, 3 |
| 5 | Agent Swarm Orchestration | 3 hours | Phase 4 |
| 6 | Fast Backtesting | 6 hours | Phase 4 |
| 7 | Evolutionary Fitness | 3 hours | Phase 6 |
| 8 | Monitoring | 2 hours | Phase 5 |

**Total: ~24 hours of implementation**

---

## Key Files Created/Modified

### New Files
```
prompts/
├── _shared/
│   ├── identity.md          ✓ Created
│   ├── indicators.md        ✓ Created
│   └── output-format.md     ✓ Created
├── pattern-discovery/
│   ├── _type.md             ✓ Created
│   └── v1.template.md       ✓ Created
└── trading-decision/
    ├── _type.md             □ Phase 2
    └── v1.template.md       □ Phase 2

local-utilities/
├── prompt_manager.py        ✓ Created
├── prompts.sqlite           ✓ Auto-created
├── agent_decision.py        □ Phase 4
├── agent_swarm.py           □ Phase 5
├── fast_backtest.py         □ Phase 6
└── evolution/
    ├── fitness.py           □ Phase 7
    └── mutation.py          □ Phase 7

docs/
├── prompt-evolution-architecture.md     ✓ Created
└── trading-agent-inference-performance.md  ✓ Created
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Prefix cache ratio | >90% |
| Live decisions/minute | >500 |
| 5-year backtest time (200 agents) | <10 hours |
| Optimal LLM usage (evolved) | 15-25% |
| LLM edge (accuracy improvement) | >5% |

---

## Next Immediate Steps

1. **Create trading-decision prompt** (Phase 2)
2. **Install vLLM and test with GPT-OSS 20B** (Phase 3)
3. **Benchmark prefix caching** - verify 94%+ cache ratio
4. **Implement agent decision engine** (Phase 4)
5. **Run first 200-agent concurrent test**

---

## References

- [docs/prompt-evolution-architecture.md](prompt-evolution-architecture.md)
- [docs/trading-agent-inference-performance.md](trading-agent-inference-performance.md)
- [local-utilities/prompt_manager.py](../local-utilities/prompt_manager.py)
- [OpenAI GPT-OSS](https://openai.com/index/introducing-gpt-oss/)
- [vLLM Documentation](https://docs.vllm.ai/)
