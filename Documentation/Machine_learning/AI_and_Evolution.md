# Machine Learning & AI Integration

## Core Concepts

Coinswarm is not a "black box" ML model but an **Agentic Swarm** system. It combines deterministic algorithms, genetic evolution, and Large Language Models (LLMs) to make trading decisions.

### 1. Evolutionary Genetics
Agents evolve over generations using massive parallel backtesting.
*   **Traits System**: Each agent is defined by a 22-dimensional vector (`local_agents/core/traits.py`).
    *   *Independent Traits*: `risk_tolerance`, `volatility_seeking`, `profit_target_greed`.
    *   *Derived Traits*: Calculated from independent ones (e.g., `stop_loss_tightness`).
*   **Selection**: The fittest agents (High ROI, Low Drawdown) survive.
*   **Crossover & Mutation**: Survivors breed to create new agents with mixed traits and random mutations.

### 2. Decision Zones
The system uses a unique "Decision Zone" architecture to balance speed and intelligence (`local_agents/core/decision.py`).

| Zone | Condition | Action |
|------|-----------|--------|
| **EXECUTE** | High Confidence + Matches Traits | Immediate deterministic trade. |
| **WAIT** | Moderate Confidence | Hold for better signal. |
| **AI_REFLECT** | Uncertain / High Risk Context | **Consult User/LLM**. |

### 3. LLM Integration
In the `AI_REFLECT` zone, the agent effectively "asks for help".
*   **Prompt Engineering**: Context (market data, recent news, correlation) is compiled into a prompt.
*   **Model**: Currently supports local LLMs (via Ollama) or cloud models.
*   **Function**: The LLM acts as a high-level creative filter, spotting nuances (like news events) that the technical algorithms miss.

### 4. Pattern Recognition
*   **Algorithmic**: Uses hard-coded technical indicators (RSI, MACD, Bollinger Bands) defined in `patterns` table.
*   **Selection**: Agents "choose" patterns that align with their traits (e.g., a "Risk Averse" agent won't select a "Volatile Breakout" pattern).
