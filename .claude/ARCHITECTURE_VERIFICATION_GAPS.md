# Architecture Verification Gaps (January 2025)

> **Purpose**: Documents gaps between INTENDED architecture (user-verified) and ACTUAL implementation (code-traced).
> **Source**: Q&A session with system owner, 30+ verification questions.

---

## 🚨 CRITICAL BUGS

### 1. Committee Voting Bug
- **ACTUAL**: `committee.py` VoteManager aggregates ALL active agents' votes
- **INTENDED**: Only 5-10 roster agents selected by Coach should vote
- **Impact**: Wrong agents influencing trade decisions
- **Fix Location**: `committee/committee.py`, `agents/coach.py`

### 2. MFE/MAE Order Not Tracked
- **ACTUAL**: `chaos_trade_generator.py` tracks MFE/MAE values only
- **INTENDED**: Must track ORDER (which came first)
  - MFE first → should've exited at the top
  - MAE first → held through dip successfully
- **Impact**: Missing critical context for exit condition discovery
- **Fix Location**: `chaos_trade_generator.py`

---

## ⚠️ DESIGN GAPS

### 3. Exit Conditions Allow Fixed TP/SL
- **ACTUAL**: Code allows fixed take-profit and stop-loss
- **INTENDED**: NEVER use fixed TP/SL - only:
  - Trailing stops
  - Indicator-based exits
  - Combination of above
- **User Quote**: "stop loss at MAE seems like a TERRIBLE plan"
- **Fix Location**: `discover_exit_conditions.py`, pattern validation

### 4. Pattern Discovery Not Automated
- **ACTUAL**: All discovery pipelines require manual trigger
- **INTENDED**: RandomForest → LLM pipeline should run on scheduled timer
  - Automated: RF/XGBoost → LLM pattern extraction (daily/weekly)
  - Manual: 5+ ML-focused analysis tools
- **Fix Location**: Need new scheduler/daemon

### 5. Train/Test Split Confusion
- **ACTUAL**: Some code references "train/test" validation
- **INTENDED**: "There is no training. All backtests are TESTING."
  - Paper trading is the only "validation" phase
- **User Quote**: "THIS IS SOMETHING THAT I KEEP EXPLAINING IS VERY WRONG"
- **Fix Location**: Remove train/test language from codebase

---

## 📋 DOCUMENTATION GAPS

### 6. Master_plan.md Shows 16 Traits
- **ACTUAL**: `traits.py` has 22 traits
- **INTENDED**: Keep all 22, update documentation
- **Fix Location**: `.claude/Master_plan.md`

---

## ✅ INTENDED ARCHITECTURE (User-Verified)

### Chaos Trades
| Aspect | Intended Behavior |
|--------|-------------------|
| Data captured | 200+ indicators + MFE/MAE + ORDER + market context |
| Minimum trades | 500-1000 before pattern discovery |
| Winner threshold | PnL > +2% |
| Loser threshold | PnL < -2% |

### Pattern Discovery
| Aspect | Intended Behavior |
|--------|-------------------|
| Automated pipeline | RF/XGBoost → LLM on schedule (daily/weekly) |
| Manual pipelines | 5+ ML-focused tools triggered as needed |
| Format | JSON with entry_conditions[] + exit_conditions[] |
| All patterns | Queue for backtest - backtesting is the filter |

### Backtesting
| Aspect | Intended Behavior |
|--------|-------------------|
| Random windows | 60-360 candles, random timeframes (1m to 1d) |
| Canonical periods | 20-30 fixed historical extremes (bear, bull, crash, etc.) |
| Minimum backtests | 100+ per pattern for reliability |
| No training | ALL backtests are testing, no train/test split |

### Pattern Tiers
| Tier | Criteria |
|------|----------|
| Tier 3 → 2 | fitness ≥ 40 (doesn't die) |
| Tier 2 → 1 | Top 10% of Tier 2 |
| Death/Archive | fitness < 40, preserved for deduplication |

### Agent Patterns
| Type | Count | When Changed |
|------|-------|--------------|
| BASE | 2-5 | Only during evolution (inheritance/mutation) |
| SITUATIONAL | 0-5 | Every 5 backtest periods; coaches advise in live sessions |

### Agent Levels & Progression
| Level | Meaning | Unlocks |
|-------|---------|---------|
| Level = | Number of children spawned | - |
| Level 5+ | Mature agent | Can change patterns, gain situational slots |
| Every level after 5 | +1 pattern slot | |
| Every 5 levels | Can swap a BASE pattern | |

### Pattern Forking
| Element | Modifiable? |
|---------|-------------|
| Exit conditions | Full freedom (trailing, indicator-based) |
| Entry thresholds | Yes, values can be tweaked |
| Entry logic | NO - intrinsic to pattern definition |

### Committee & Roster
| Aspect | Intended Behavior |
|--------|-------------------|
| Roster size | 5-10 variable, Coach decides |
| Composition | Mix of specialist (fundamental, sentiment) + technical agents |
| Vote aggregation | Role-based weighting (specialist vs technical) |
| Tie handling | Majority to OPEN, tie allowed to CLOSE profitable |
| Position sizing | Kelly criterion on aggregated win probability |

### Three Pillars
| Pillar | Guideline % | Reality |
|--------|-------------|---------|
| Technical | 40% | Coach decides actual split |
| Sentiment | 30% | Based on roster size constraints |
| Fundamental | 30% | e.g., 5-agent roster = 20% increments |

### Specialist Agents (NOT FULLY DESIGNED)
- **Intended Role**: Predict direction/volatility (rising, falling, increased volatility)
- **Mechanism**: Semantic search over historical data with similar patterns
- **Output**: Confidence + timeframe (e.g., "60% confidence price rises over 6 hours")
- **Status**: Design incomplete, not implemented

### Decoupled Cycles
- Backtesting: Own cycle
- Evolution: Separate cycle
- Pattern discovery: Independent
- Memory consolidation: Different timing
- **Key**: NOT everything linked to same cycle time

### Evolution
| Aspect | Intended Behavior |
|--------|-------------------|
| Trigger | Time-based initially (hourly), slow down as system matures |
| Clone | Single elite parent |
| Reproduction | Two parents crossover |
| Memory inheritance | Based on parent's memory_condensation trait |
| Coach evolution | YES - coaches compete and can die |

### Crucible
- **Purpose**: Qualification gate before paper trading
- Tests agents across multiple regimes
- Maintains separate leaderboard

### Data Sources (Intended)
| Type | Sources |
|------|---------|
| Sentiment | Nostr (not Twitter/X), internet searches, regulatory/legal news |
| Fundamental | Research, news articles, tokenomics (not implemented) |
| Technical | 200+ indicators from enhanced_candles |

---

## 🔴 DO NOT TOUCH

### Fitness Equations
> "We spent so long tweaking those fitness equations that if you mess with them I am switching AI providers."

---

## 📊 DEVELOPMENT STATUS

| Component | Status |
|-----------|--------|
| Python local-utilities/ | ACTIVE DEVELOPMENT |
| V3 Cloudflare | PAUSED (cloud costs) |
| Resume V3 when | Live profitable trades fund cloud costs |

---

## 🔍 NEEDS INVESTIGATION

1. **Regime Detection Conflict**: Crucible vs Daemon use different regime logic - which is correct?
2. **Specialist Agent Design**: How exactly should fundamental/sentiment agents work?

---

## 📝 NEXT STEPS

1. [ ] Fix Committee voting to only count roster agents
2. [ ] Add MFE/MAE order tracking to chaos_trade_generator.py
3. [ ] Remove fixed TP/SL from exit condition options
4. [ ] Update Master_plan.md with 22 traits
5. [ ] Implement scheduled RF→LLM pattern discovery
6. [ ] Remove train/test language from codebase
7. [ ] Investigate regime detection discrepancy
