# Coinswarm Research Compendium 2025

> **ML-First Academic Research Corpus for Autonomous Trading Systems**
>
> Created: 2025-12-28 | Last Updated: 2025-12-28
> Primary Use: Agent/ML training data for pattern discovery across papers

---

## Quick Stats

| Metric | Count |
|--------|-------|
| Total Papers | 180+ |
| P0 (Critical) | 8 |
| P1 (High Priority) | 24 |
| P2 (Medium) | 89 |
| P3 (Low) | 62 |
| Concept Files | 6 |
| Code Examples | 6 |

---

## Directory Structure

```
research-compendium-2025/
├── index.md                    # This file - master navigation
├── _tools/                     # Automation scripts
│   ├── add_paper.py           # Add new paper from arxiv
│   ├── update_crossrefs.py    # Rebuild cross-references
│   ├── validate_schema.py     # Validate all files
│   ├── generate_index.py      # Regenerate this index
│   ├── sync_bibliography.py   # Sync from ANNOTATED_BIBLIOGRAPHY.md
│   └── compendium_stats.py    # Generate statistics
├── _templates/                 # File templates
│   ├── paper_template.md      # Full paper template
│   └── concept_template.md    # Concept file template
├── _schema/                    # Validation schemas
│   └── paper_schema.json      # JSON Schema for papers
├── _data/                      # Pre-computed data
│   ├── citation_graph.json    # Citation relationships
│   ├── concept_index.json     # Concept → papers mapping
│   └── stats.json             # Compendium statistics
├── architecture/               # Core system design
│   ├── 3-tier-execution.md    # Strategic → Roster → Execution
│   ├── 5-layer-hierarchy.md   # Cognitive hierarchy
│   ├── data-schemas.md        # FullTradeRecord, etc.
│   └── implementation-roadmap.md
├── papers/                     # ONE FILE PER PAPER (180+)
│   └── arxiv-XXXX.XXXXX-name.md
├── concepts/                   # Cross-cutting concepts
│   ├── memory-systems.md      # Episodic/Semantic/Wisdom
│   ├── regime-detection.md    # HMM classification
│   ├── position-sizing.md     # Kelly criterion
│   ├── risk-management.md     # Stops, drawdown gates
│   ├── three-pillars.md       # Tech/Sentiment/Fundamental
│   └── evolutionary-systems.md # Genetic algorithms
├── code/                       # Python implementations
│   ├── kelly_criterion.py
│   ├── regime_classifier.py
│   ├── affinity_mutation.py
│   ├── memory_retrieval.py
│   ├── wisdom_extraction.py
│   └── three_pillars_fusion.py
└── meta/                       # Reference materials
    ├── glossary.md            # Term definitions
    ├── metrics.md             # Performance metrics
    └── traits.md              # 16 agent traits
```

---

## Navigation by Category

### Architecture Documents

| Document | Description | Path |
|----------|-------------|------|
| 3-Tier Execution | Strategic → Roster → Execution tiers | [architecture/3-tier-execution.md](architecture/3-tier-execution.md) |
| 5-Layer Hierarchy | Planners → Coaches → Committee → Agents → Patterns | [architecture/5-layer-hierarchy.md](architecture/5-layer-hierarchy.md) |
| Data Schemas | FullTradeRecord, memory schemas | [architecture/data-schemas.md](architecture/data-schemas.md) |
| Implementation Roadmap | P0-P3 task priorities | [architecture/implementation-roadmap.md](architecture/implementation-roadmap.md) |

### Concept Syntheses

| Concept | Related Papers | Path |
|---------|----------------|------|
| Memory Systems | MacroHFT, FinAgent, MASA | [concepts/memory-systems.md](concepts/memory-systems.md) |
| Regime Detection | HMM papers, classification | [concepts/regime-detection.md](concepts/regime-detection.md) |
| Position Sizing | Kelly papers (4 total) | [concepts/position-sizing.md](concepts/position-sizing.md) |
| Risk Management | Stop-loss papers (3 total) | [concepts/risk-management.md](concepts/risk-management.md) |
| Three Pillars | MAT, sentiment papers | [concepts/three-pillars.md](concepts/three-pillars.md) |
| Evolutionary Systems | CGA-Agent, GP papers | [concepts/evolutionary-systems.md](concepts/evolutionary-systems.md) |

### Code Implementations

| Module | Purpose | Path |
|--------|---------|------|
| kelly_criterion.py | Constrained Kelly position sizing | [code/kelly_criterion.py](code/kelly_criterion.py) |
| regime_classifier.py | HMM regime detection | [code/regime_classifier.py](code/regime_classifier.py) |
| affinity_mutation.py | Evolving roster slot affinities | [code/affinity_mutation.py](code/affinity_mutation.py) |
| memory_retrieval.py | Similarity-based episodic retrieval | [code/memory_retrieval.py](code/memory_retrieval.py) |
| wisdom_extraction.py | WHEN-DO-BECAUSE rule generation | [code/wisdom_extraction.py](code/wisdom_extraction.py) |
| three_pillars_fusion.py | Weighted pillar combination | [code/three_pillars_fusion.py](code/three_pillars_fusion.py) |

---

## Papers by Priority

### P0 - Critical (Implement First)

| Paper ID | Title | Category | Path |
|----------|-------|----------|------|
| arxiv-2412.20138 | TradingAgents | multi-agent-llm | [papers/arxiv-2412.20138-trading-agents.md](papers/arxiv-2412.20138-trading-agents.md) |
| arxiv-2512.02227 | FinAgent | agent-orchestration | [papers/arxiv-2512.02227-finagent.md](papers/arxiv-2512.02227-finagent.md) |
| arxiv-2406.14537 | MacroHFT | memory-augmented | [papers/arxiv-2406.14537-macro-hft.md](papers/arxiv-2406.14537-macro-hft.md) |
| arxiv-2402.00515 | MASA | multi-agent-risk | [papers/arxiv-2402.00515-masa.md](papers/arxiv-2402.00515-masa.md) |
| arxiv-2212.14670 | M3T | hierarchical-execution | [papers/arxiv-2212.14670-m3t.md](papers/arxiv-2212.14670-m3t.md) |
| various | Kelly Papers (4) | position-sizing | [concepts/position-sizing.md](concepts/position-sizing.md) |

### P1 - High Priority

| Paper ID | Title | Category | Path |
|----------|-------|----------|------|
| arxiv-2510.07943 | CGA-Agent | genetic-trading | [papers/arxiv-2510.07943-cga-agent.md](papers/arxiv-2510.07943-cga-agent.md) |
| arxiv-2510.26353 | XAI Meta-labeling | reliability | [papers/arxiv-2510.26353-xai-meta-labeling.md](papers/arxiv-2510.26353-xai-meta-labeling.md) |
| arxiv-2310.01232 | MAT Three Pillars | modal-fusion | [papers/arxiv-2310.01232-mat-three-pillars.md](papers/arxiv-2310.01232-mat-three-pillars.md) |
| arxiv-2510.08068 | Reflect Agent | verbal-feedback | [papers/arxiv-2510.08068-reflect-agent.md](papers/arxiv-2510.08068-reflect-agent.md) |
| various | Stop-loss Papers (3) | risk-management | [concepts/risk-management.md](concepts/risk-management.md) |
| various | Regime Detection (3) | hmm-classification | [concepts/regime-detection.md](concepts/regime-detection.md) |

---

## Papers by Category

### Multi-Agent LLM Systems
- [TradingAgents](papers/arxiv-2412.20138-trading-agents.md) - Bull/bear debate, committee voting
- [FinAgent](papers/arxiv-2512.02227-finagent.md) - Memory UUID, orchestration
- [MASA](papers/arxiv-2402.00515-masa.md) - Multi-agent risk parity

### Memory & Learning
- [MacroHFT](papers/arxiv-2406.14537-macro-hft.md) - M=(K,E,V) memory architecture
- [Reflect Agent](papers/arxiv-2510.08068-reflect-agent.md) - Verbal feedback wisdom

### Risk Management
- [Kelly Papers](concepts/position-sizing.md) - Position sizing fundamentals
- [Stop-Loss Papers](concepts/risk-management.md) - Optimal stop placement

### Evolutionary Trading
- [CGA-Agent](papers/arxiv-2510.07943-cga-agent.md) - Genetic trading strategies

### Signal Reliability
- [XAI Meta-labeling](papers/arxiv-2510.26353-xai-meta-labeling.md) - M1/M2 reliability framework

---

## ML Query Examples

The structured YAML frontmatter enables queries like:

```python
# Find all papers that extend MASA
papers_extending_masa = [p for p in papers if "arxiv-2402.00515" in p.extends]

# Find papers relevant to trait #8 (stop_loss_tightness)
stop_loss_papers = [p for p in papers if 8 in p.related_traits]

# Find contradicting claims about Sharpe ratios
sharpe_claims = [(p.paper_id, c) for p in papers
                 for c in p.claims if c.metric == "sharpe_ratio"]

# Build citation graph
for p in papers:
    for cited in p.cites:
        graph.add_edge(p.paper_id, cited)

# Find papers with high implementation complexity
complex_papers = [p for p in papers if p.implementation_estimate.complexity >= 13]

# Find papers with blocking data gaps
blocked = [p for p in papers if p.data_requirements.gap_severity == "blocking"]
```

---

## Maintenance

### Adding New Papers

```bash
# From arxiv URL
python _tools/add_paper.py --url https://arxiv.org/abs/2501.12345

# Interactive mode
python _tools/add_paper.py --interactive

# Batch import from bibliography
python _tools/sync_bibliography.py --source ../../ANNOTATED_BIBLIOGRAPHY.md
```

### Updating Cross-References

```bash
python _tools/update_crossrefs.py
```

### Validating Schema

```bash
python _tools/validate_schema.py
```

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial compendium creation |

---

## Related Documentation

- [ANNOTATED_BIBLIOGRAPHY.md](../ANNOTATED_BIBLIOGRAPHY.md) - Source bibliography
- [BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md](../BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md) - Architecture mapping
- [Master_plan.md](../../.claude/Master_plan.md) - System architecture
