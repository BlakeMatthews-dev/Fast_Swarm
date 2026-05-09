# Coinswarm Master Plan

> Living document: vision → current goals → questions → decisions → changelog

---

## 1. FINAL FUTURE STATE

Autonomous crypto trading via evolutionary pattern discovery:
- Three pillars: Technical (40%) + Sentiment (30%) + Fundamental (30%)
- **5-Layer Cognitive Hierarchy:** Planners → Coaches → Committee → Agents → Patterns
  - Extends M3T (3-layer) and MASA (2-agent) architectures in BOTH directions
  - Strategic layer above (Planners) + Reactive layer below (Patterns)
  - See `docs/BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md` Appendix A for paper-worthy analysis
- Live trading with circuit breakers
- Grand Challenge elite competition

---

## 2. CURRENT SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PATTERN ENTRY POINTS                                 │
│                                                                              │
│   ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐  ┌────────┐         │
│   │  CHAOS  │  │ ACADEMIC │  │ TECHNICAL │  │   AI   │  │ HYBRID │         │
│   │ Random  │  │  Papers  │  │ Classic   │  │  LLM   │  │ Merged │         │
│   │ trades  │  │  → JSON  │  │   TA      │  │ ideas  │  │ combos │         │
│   └────┬────┘  └────┬─────┘  └─────┬─────┘  └───┬────┘  └───┬────┘         │
│        │            │              │            │            │              │
│        └────────────┴──────────────┴────────────┴────────────┘              │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         BACKTESTING ENGINE                              ││
│  │  • Real OHLCV data (2019-2025)  • 100+ indicators  • Slippage model    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         FITNESS SCORE (0-100)                           ││
│  │  ROI + Sharpe + Sortino + Calmar + Drawdown + Win Rate + Profit Factor ││
│  │  < 40 = DIE    |    40-79 = SURVIVE    |    80+ = PROMOTE              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         TIER SYSTEM                                     ││
│  │  TIER 3 (Untested) ──promote──▶ TIER 2 (Proven) ──promote──▶ TIER 1    ││
│  │       ▲                              ▲                        (Elite)   ││
│  │       │                              │                           │      ││
│  │    new patterns                   survivors                      │      ││
│  │                                                                  ▼      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                  │           │
│                                                                  ▼           │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         AGENT ASSIGNMENT                                ││
│  │  Agents get 5-10 pattern SLOTS:                                        ││
│  │  • BASE (2-5): Permanent core strategies                               ││
│  │  • SITUATIONAL (0-5): Weekly swappable based on market regime          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      TRADING & FEEDBACK                                 ││
│  │  Agent executes trades → Results logged → Offline analysis             ││
│  │                                                                         ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │  HYBRID FEEDBACK LOOP (offline)                                  │  ││
│  │  │  Aggregate what works/doesn't → Optimize entry points            │  ││
│  │  │  • Chaos: Seed better random ranges                              │  ││
│  │  │  • Academic: Prioritize productive authors/papers                │  ││
│  │  │  • AI: Fine-tune prompts based on pattern success               │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flow Summary

1. **Entry Points**: 5 sources feed patterns into the system
   - **Chaos**: Random trades on real data → statistical discovery
   - **Academic**: Papers distilled by LLM → trading hypotheses
   - **Technical**: Classic TA (RSI oversold, golden cross, etc.)
   - **AI**: Direct LLM generation of novel strategies
   - **Hybrid**: Merge successful pattern elements

2. **Backtesting**: Every pattern tested against years of real OHLCV data

3. **Fitness Score**: 0-100 composite metric determines survival
   - Below 40: Pattern dies
   - 40-79: Pattern survives, continues testing
   - 80+: Pattern promoted to higher tier

4. **Tier System**: Patterns advance through proving grounds
   - Tier 3: Newcomers, low priority
   - Tier 2: Proven performers, more testing resources
   - Tier 1: Elite, eligible for agent assignment

5. **Agent Assignment**: Tier 1 patterns assigned to agent slots
   - Agents are executors that USE patterns
   - Each agent has 5-10 slots (base + situational)

6. **Hybrid Feedback**: Results feed back to optimize entry points
   - Which chaos ranges work? Seed more like them
   - Which authors produce winning patterns? Fetch more papers
   - Which AI prompts generate profitable ideas? Refine them

---

## 3. AGENT PERSONALITY TRAITS (16 Heritable)

All traits: **float 0-1**, randomized at spawn, ±10% mutation/generation, stored in `agent_traits` table.

**Standardized Schema** - Every trait has:
1. Pattern Selection Formula (affects which patterns get chosen)
2. Trade Execution Formula (affects individual trade parameters)
3. AI Description (for uncertainty mode prompt injection)

### Core Risk & Position Traits (1-4)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 1 | `risk_tolerance` | `score *= (0.5 + t) × pattern.max_dd_norm` | `position = kelly × (0.1 + t × 0.9)` |
| 2 | `hold_duration_bias` | `score *= 1 - |t - pattern.hold_norm|` | `exit_patience = 0.5 + t × 1.5` (0.5x-2x) |
| 3 | `volatility_seeking` | `score *= (0.5 + t) × pattern.atr_pctl` | Skip trades if regime mismatch |
| 4 | `profit_target_greed` | `score *= pattern.avg_win^t` | `tp_ratio = 1.5 + t × 3.5` (1.5x-5x R:R) |

### Pattern Selection Traits (5-7)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 5 | `win_rate_preference` | `score = wr^(1+t) × roi^(2-t)` | `min_confidence = 0.4 + t × 0.4` |
| 6 | `drawdown_sensitivity` | `score *= 1 - t × pattern.max_dd/50` | `circuit_breaker = -0.05 - (1-t) × 0.15` |
| 7 | `momentum_vs_reversion` | `trend_wt = t; reversion_wt = 1-t` | Entry direction bias |

### Trade Execution Traits (8-10)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 8 | `stop_loss_tightness` | `score *= 1 - |t - pattern.stop_norm|` | `stop_pct = 0.01 + (1-t) × 0.09` (1-10%) |
| 9 | `entry_aggression` | `score *= (0.5 + t) × pattern.signal_freq` | `confirm_candles = ceil(3 × (1-t))` (0-3) |
| 10 | `exit_aggression` | Weight quick vs full-run patterns | `trail_activation = 1 + (1-t) × 2` (1x-3x) |

### Technical Configuration (11)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 11 | `lookback_preference` | Prefer patterns with matching periods | `period_mult = 0.5 + t` (0.5x-1.5x all indicators) |

**Lookback scaling (t=0.5 is baseline):**
- RSI: 7-21 (base 14), EMA: 6-18/13-39 (base 12/26), SMA: 10-30/100-300 (base 20/200)

### Sentiment & News Traits (12-14)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 12 | `sentiment_weight` | `score *= 1 + t × pattern.sent_corr` | `signal = tech × (1-t) + sent × t` |
| 13 | `news_reactivity` | `score *= t × pattern.news_alpha + (1-t) × baseline` | `post_news_delay = (1-t) × 4hrs` |
| 14 | `sentiment_contrarian` | Weight contrarian patterns | `sent_signal = raw × (1 - 2×t)` (follow↔fade) |

### Macro & Correlation Traits (15-16)

| # | Trait | Pattern Selection | Trade Execution |
|---|-------|-------------------|-----------------|
| 15 | `funding_rate_sensitivity` | `score *= 1 + t × pattern.funding_alpha` | `funding_thresh = 0.01 + (1-t) × 0.09` (1-10% APR) |
| 16 | `correlation_awareness` | `score *= (1-t) + t × (1 - pattern.btc_corr)` | `btc_regime_filter = btc_trend × t` |

### SQLModel Schema

```python
class AgentTraits(SQLModel, table=True):
    __tablename__ = "agent_traits"

    agent_id: str = Field(primary_key=True, foreign_key="agents.agent_id")

    # Core Risk & Position (1-4)
    risk_tolerance: float = Field(default=0.5, ge=0.0, le=1.0)
    hold_duration_bias: float = Field(default=0.5, ge=0.0, le=1.0)
    volatility_seeking: float = Field(default=0.5, ge=0.0, le=1.0)
    profit_target_greed: float = Field(default=0.5, ge=0.0, le=1.0)

    # Pattern Selection (5-7)
    win_rate_preference: float = Field(default=0.5, ge=0.0, le=1.0)
    drawdown_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    momentum_vs_reversion: float = Field(default=0.5, ge=0.0, le=1.0)

    # Trade Execution (8-10)
    stop_loss_tightness: float = Field(default=0.5, ge=0.0, le=1.0)
    entry_aggression: float = Field(default=0.5, ge=0.0, le=1.0)
    exit_aggression: float = Field(default=0.5, ge=0.0, le=1.0)

    # Technical Configuration (11)
    lookback_preference: float = Field(default=0.5, ge=0.0, le=1.0)

    # Sentiment & News (12-14)
    sentiment_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    news_reactivity: float = Field(default=0.5, ge=0.0, le=1.0)
    sentiment_contrarian: float = Field(default=0.5, ge=0.0, le=1.0)

    # Macro & Correlation (15-16)
    funding_rate_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    correlation_awareness: float = Field(default=0.5, ge=0.0, le=1.0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### Usage Modes

1. **Automated Mode**: Traits → formulas → concrete trade parameters
2. **Uncertainty Mode**: Traits + context → AI prompt → decision

### AI Prompt Template (Uncertainty Mode)

When pattern conditions have overlapping signals or confidence is below threshold, the agent generates an AI prompt using its personality traits:

```
You are {agent_name}, a crypto trading agent with the following personality profile:

RISK PROFILE:
- Risk Tolerance: {risk_tolerance:.0%} ({self._risk_label(risk_tolerance)})
- Drawdown Sensitivity: {drawdown_sensitivity:.0%} ({self._dd_label(drawdown_sensitivity)})
- Profit Target Greed: {profit_target_greed:.0%} ({self._greed_label(profit_target_greed)})

TRADING STYLE:
- Hold Duration: {hold_duration_bias:.0%} ({self._hold_label(hold_duration_bias)})
- Entry Aggression: {entry_aggression:.0%} ({self._entry_label(entry_aggression)})
- Exit Aggression: {exit_aggression:.0%} ({self._exit_label(exit_aggression)})
- Momentum vs Reversion: {momentum_vs_reversion:.0%} ({self._mvr_label(momentum_vs_reversion)})

MARKET SENSITIVITY:
- Volatility Seeking: {volatility_seeking:.0%} ({self._vol_label(volatility_seeking)})
- Sentiment Weight: {sentiment_weight:.0%} ({self._sent_label(sentiment_weight)})
- News Reactivity: {news_reactivity:.0%} ({self._news_label(news_reactivity)})
- Funding Rate Sensitivity: {funding_rate_sensitivity:.0%}

CURRENT MARKET STATE:
- Asset: {asset}
- Price: ${price:,.2f}
- 24h Change: {change_24h:+.2f}%
- Volatility Regime: {volatility_regime}
- Trend Regime: {trend_regime}

ACTIVE SIGNALS:
{signal_list}

CONFLICTING INDICATORS:
{conflict_description}

Given your personality and these market conditions, should you:
A) Enter LONG position
B) Enter SHORT position
C) WAIT for clearer signal
D) EXIT current position (if any)

Explain your reasoning in 2-3 sentences, then give your choice.
```

**Trait Label Functions:**
```python
def _risk_label(t: float) -> str:
    if t > 0.7: return "aggressive risk-taker"
    if t > 0.4: return "moderate risk tolerance"
    return "conservative, capital preservation"

def _hold_label(t: float) -> str:
    if t > 0.7: return "swing trader, holds for days"
    if t > 0.4: return "day trader"
    return "scalper, quick exits"

def _mvr_label(t: float) -> str:
    if t > 0.7: return "momentum chaser, follows trends"
    if t > 0.4: return "balanced approach"
    return "contrarian, fades moves"

def _vol_label(t: float) -> str:
    if t > 0.7: return "seeks volatile markets"
    if t > 0.4: return "neutral on volatility"
    return "prefers calm markets"

def _entry_label(t: float) -> str:
    if t > 0.7: return "aggressive, enters on first signal"
    if t > 0.4: return "waits for confirmation"
    return "very patient, needs multiple signals"
```

**Confidence Threshold Calculation:**
```python
def calculate_confidence_threshold(traits: AgentTraits) -> float:
    """
    Higher win_rate_preference = needs more confidence
    Higher entry_aggression = lower threshold (more willing to enter)
    """
    base = 0.5
    wr_adjustment = traits.win_rate_preference * 0.3  # +0 to +0.3
    ea_adjustment = -traits.entry_aggression * 0.2   # -0.2 to 0
    return max(0.3, min(0.8, base + wr_adjustment + ea_adjustment))
```

**When to Use Uncertainty Mode:**
- Pattern signals conflict (RSI says buy, MACD says sell)
- Signal confidence < agent's threshold
- Unusual market conditions (high VIX, news event)
- Position sizing decision when near limits

---

## 4. TRAIT COUPLING (Prevent Contradictions)

Some trait combinations are logically contradictory. Solution: 13 independent + 3 derived traits.

### Contradictory Pairs

| Anchor Trait | Contradicts | Why |
|--------------|-------------|-----|
| `risk_tolerance` (high) | `drawdown_sensitivity` (high) | Can't love risk AND fear drawdowns |
| `risk_tolerance` (high) | `stop_loss_tightness` (high) | Can't love risk AND use tight stops |
| `hold_duration_bias` (high) | `exit_aggression` (high) | Can't be patient holder AND aggressive exiter |

### Coupled Generation

**13 Independent** (random): risk_tolerance, hold_duration_bias, volatility_seeking, profit_target_greed, win_rate_preference, momentum_vs_reversion, entry_aggression, lookback_preference, sentiment_weight, news_reactivity, sentiment_contrarian, funding_rate_sensitivity, correlation_awareness

**3 Derived** (coupled with ±10% noise):
```python
drawdown_sensitivity = clamp((1 - risk_tolerance) + noise())
stop_loss_tightness = clamp((1 - risk_tolerance) + noise())
exit_aggression = clamp((1 - hold_duration_bias) + noise())
```

---

## 5. THREE-TIER AGENT MEMORY

```
Episodic  → "what happened"   → 7 days, ~100 trades
Semantic  → "what I learned"  → lifetime, aggregated stats
Wisdom    → "what I believe"  → philosophy + WHEN-DO-BECAUSE rules
```

### Memory Flow

```
TRADE → EPISODIC (hot) → SEMANTIC (warm) → WISDOM (cold)
        every trade      every 50 trades   on triggers
```

### Wisdom Rewrite Triggers

| Trigger | Condition |
|---------|-----------|
| Scheduled | Every 100 completed trades |
| Performance Cliff | 5 consecutive losses OR -15% drawdown |
| Regime Shift | Market regime changed AND underperforming |
| Promotion | Agent enters top 20% |

### SQLModel Schema

```python
class AgentMemory(SQLModel, table=True):
    agent_id: str = Field(primary_key=True)

    # Episodic
    episodic_trades: str | None = None      # JSON array
    episodic_updated_at: datetime | None = None

    # Semantic
    pattern_affinities: str | None = None   # JSON: {pattern_id: {stats}}
    regime_preferences: str | None = None   # JSON: {regime: win_rate}
    indicator_biases: str | None = None     # JSON: {indicator: bias}

    # Wisdom
    philosophy: str | None = None           # 2-4 sentences
    one_liner: str | None = None            # Motto
    wisdom_rules: str | None = None         # JSON: [{when, do, because}]
```

---

## 6. TWO-PHASE SPAWNING PROMPTS

### Prompt 1: Pattern Selection

```
You are an agent in the CoinSwarm Agentic Trading System. You have just
spawned on {{timestamp}}.

YOUR PERSONALITY TRAITS:
| Trait | Value | Interpretation |
|-------|-------|----------------|
{{#each traits}}
| {{name}} | {{value}} | {{interpretation}} |
{{/each}}

Your first decision is to choose your patterns. You will be evaluated
against other agents using these patterns.

TOP PERFORMING PATTERNS (choose up to 5, weights MUST sum to 1.0):

{{#each patterns}}
---
**{{name}}** (ID: {{pattern_id}})
Entry: {{entry_conditions}}
Exit: {{exit_conditions}}
Metrics: Fitness={{fitness_score}}, WinRate={{win_rate}}%, ROI={{total_roi_pct}}%
Tags: {{tags}}
---
{{/each}}

EXAMPLES OF SUCCESSFUL SELECTIONS:
{{#each examples}}
**{{agent_name}}** (Fitness: {{fitness_score}})
{{#each selections}}
  - {{pattern_name}} ({{weight}}) - "{{reasoning}}"
{{/each}}
{{/each}}

OUTPUT FORMAT:
{
  "selections": [
    {"pattern_id": "<id>", "weight": <0.0-1.0>, "reasoning": "<why>"}
  ],
  "strategy_summary": "<2-3 sentences>"
}
```

### Prompt 2: Philosophy Statement

```
You have selected your trading patterns. Now synthesize your personality
and pattern choices into a trading philosophy.

YOUR PERSONALITY TRAITS:
{{traits_table}}

YOUR SELECTED PATTERNS:
{{#each selections}}
**{{pattern_name}}** (weight: {{weight}})
- Entry: {{entry_conditions}}
- Exit: {{exit_conditions}}
- Reasoning: "{{reasoning}}"
{{/each}}

Write a trading philosophy statement that captures:
1. Your core approach to markets
2. When you expect to excel

OUTPUT FORMAT:
{
  "philosophy": "<2-4 sentence trading philosophy>",
  "one_liner": "<single memorable motto>",
  "expected_strengths": ["<market condition 1>", "<market condition 2>"]
}
```

---

## 7. DEVELOPMENT ROADMAP

### Phase 1: Pattern Discovery & Backtesting (CURRENT)
```
Capital: $0 (paper trading)
Strategy: Evolutionary pattern discovery + backtesting
Goal: Build library of proven patterns with fitness > 80
Target: 100+ Tier 1 patterns, Sortino > 1.5, Calmar > 1.0, MaxDD < 15%
Exit Criteria: Proven patterns beating buy-and-hold consistently
```

**Immediate Tasks:**
- Unified local SQLite database (SQLModel)
- Merge academic pipeline + 24K chaos patterns
- Enable provenance queries
- Generate V3 upload SQL

**V3 Status**: Chaos evolution works, cognitive hierarchy NOT built

---

### Phase 2: Agent Trading
```
Capital: $500 - $5,000
Strategy: Individual agents with 16 heritable traits execute patterns
Goal: Agents compete, best traits survive via evolution
Target: 50-100% APR with consistent performance
Exit Criteria: Stable agent population, clear trait winners
```

**Key Components:**
- Agents spawn with random traits (16 floats 0-1)
- Each agent gets 5-10 pattern slots (base + situational)
- Agents compete on same market data
- Winners reproduce with ±10% trait mutation
- Losers die, patterns returned to pool

---

### Phase 3: Hivemind Committee + Coaches
```
Capital: $5K - $50K
Strategy: Committee voting on trades, coaches manage agent rosters
Goal: Collective intelligence beats individual agents
Target: 100-150% APR with lower drawdown than Phase 2
Exit Criteria: Committee consistently outperforms best individual agent
```

**Key Components:**
- **Committee**: Multiple agents vote on each trade decision
- **Coaches/Planners**: Meta-agents that select which agents play
- **Roster Management**: Coaches under selection pressure too
- **Cultural Knowledge**: Shared wisdom across agent generations
- **Memory Tiers**: Episodic → Semantic → Wisdom propagation

**Cognitive Hierarchy (5 Layers):**

> **Paper-Worthy Insight:** Our 5-layer hierarchy extends academic baselines (M3T, MASA) in both directions.
> See `docs/BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md` Appendix A for full analysis.

```
LAYER 5: Planners (strategic direction, months/quarters)
    ↓     - Set pillar weights, risk budgets, sector allocations
    ↓     - NO M3T/MASA equivalent (we are more complete)
    ↓
LAYER 4: Coaches (roster selection, weekly/daily)
    ↓     - Select which agents are active vs benched
    ↓     - Under evolution pressure (bad coaches replaced)
    ↓     - Maps to M3T "Macro" but slower time scale
    ↓
LAYER 3: Committee (vote aggregation, per signal)
    ↓     - Quorum rules, confidence weighting
    ↓     - Maps to M3T "Meta" + MASA agent coordination
    ↓
LAYER 2: Agents (pattern execution, per trade)
    ↓     - 16 heritable traits, memory inheritance
    ↓     - Maps to M3T "Micro"
    ↓
LAYER 1: Patterns (entry/exit rules, sub-second)
          - Reactive firing, stop-loss triggers
          - NO M3T/MASA equivalent (we are more granular)
```

**Key Differentiators vs Academic Baselines:**
| Aspect | M3T | MASA | Coinswarm |
|--------|-----|------|-----------|
| Strategic layer | ❌ | ❌ | ✅ Planners |
| Execution layers | ✅ 3 | ✅ 2 | ✅ 3 |
| Reactive layer | ❌ | ❌ | ✅ Patterns |
| Evolution pressure | ❌ | ❌ | ✅ All layers |
| Memory inheritance | ❌ | ❌ | ✅ Semantic/Wisdom |

---

### Phase 4: Cross-Exchange Market Making (PARALLEL TRACK)
```
Capital Required: $10K minimum, $50K comfortable
Strategy: Cross-exchange MM with maker rebates
Goal: Near-riskless spread capture
Target: 180-270% APR
```

**Key Research (2025-12-27):**
- Live data collected across 5 exchanges (Coinbase, Binance, Hyperliquid, dYdX, Crypto.com)
- Cross-exchange spreads average ~10 bps
- Maker fees enable profit: Coinbase 0%, Hyperliquid -0.02% REBATE
- Backtest simulation: $752/day on $100K (274% APR)

**Minimum Capital by Strategy:**
| Level | Capital | Trade Size | Daily P&L | APR |
|-------|---------|------------|-----------|-----|
| Bare Minimum | $1-2K | 0.001 BTC | $5-15 | ~150% |
| Practical | $10K | 0.01 BTC | $50-75 | ~200% |
| Comfortable | $50K | 0.05 BTC | $250-400 | ~250% |

**Prerequisites:**
- [ ] Proven pattern trading profits (Phase 2+)
- [ ] Exchange API credentials + permissions
- [ ] Real-time execution infrastructure
- [ ] Inventory management system
- [ ] Position/risk monitoring dashboard

**Reference Files:**
- `docs/market-making-poc-plan.md` - 5-day PoC research plan
- `local-utilities/mm_simulator.py` - Backtest engine
- `local-utilities/min_capital_analysis.py` - Capital requirements

**Note:** MM is ADDITIVE to pattern trading, not replacement. Can run in parallel once infrastructure exists.

---

### Phase 5: Full Autonomous System + Grand Challenge
```
Capital: $100K+
Strategy: All pillars (Technical 40% + Sentiment 30% + Fundamental 30%)
Goal: Fully autonomous with circuit breakers, self-reflection
Features: Grand Challenge elite competition
```

**Key Components:**
- **Three Pillars**: Technical analysis + sentiment + fundamentals weighted
- **Self-Reflection**: System analyzes own performance, adjusts weights
- **Circuit Breakers**: Auto-halt on drawdown, correlation breakdown
- **Grand Challenge**: Elite pattern tournament with high stakes
- **Memory Optimizer**: Cross-generation wisdom distillation

---

## 8. QUESTIONS TO ANSWER

**Q1**: Unified vs separate pattern tables?

**Q2**: Import all 24K patterns or filter?

**Q3**: What to implement after unified DB?

---

## 9. ANSWERED QUESTIONS

### [2025-12-15] Memory infrastructure?
**A**: Cloudflare (DO/D1/KV), NOT Redis

### [2025-12-15] ORM choice?
**A**: SQLModel

### [2025-12-15] Pattern origins?
**A**: chaos, academic, technical, ai, hybrid

---

## 10. CHANGELOG

### 2025-12-27
- Created full implementation roadmap: docs/implementation-roadmap.md
- Added 5-phase roadmap (Pattern → Agent → Committee → MM → Autonomous)
- Updated fitness targets: Sortino > 1.5, Calmar > 1.0, MaxDD < 15%
- V3 audit: Layer 1-4 done, Layer 5-7 partial/missing
- Added Phase 4: Cross-Exchange Market Making (parallel track)
- Live data collection validated across 5 exchanges
- MM backtest: $752/day on $100K (274% APR) with maker fees
- Created mm_simulator.py, min_capital_analysis.py, market-making-poc-plan.md

### 2025-12-16
- 07:00 - Added TRAIT COUPLING, THREE-TIER MEMORY, TWO-PHASE SPAWNING PROMPTS
- 04:30 - Added AI PROMPT TEMPLATE for Uncertainty Mode with trait labels
- 04:00 - Unified DB working: 29,350 chaos + 24 academic patterns

### 2025-12-15
- 21:30 - Added 16 AGENT PERSONALITY TRAITS with SQLModel schema
- 20:15 - Added CURRENT SYSTEM ARCHITECTURE section with flow diagram
- 19:30 - Created Master_Plan.md
- 19:15 - Documented V3 actual vs docs (8 DOs, $0/month, gaps)
- 19:00 - Added architecture details (circuit breakers, traits, regimes)
- 18:30 - Added Pattern Slots, Grand Challenge, Wisdom System
- 17:45 - Full codebase exploration, table inventory, data shards

---

*Last updated: 2025-12-15*
