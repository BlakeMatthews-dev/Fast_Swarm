# Prompt Engineering

Coinswarm uses Jinja2 templates to construct prompts for the LLM. These templates inject dynamic agent state (traits, recent trades, market context) into a structured prompt.

## Template Locations
All templates are located in `local_agents/prompts/`.

## Core Templates

### 1. Birth Selection (`birth_selection.j2`)
*   **Purpose**: Used when spawning a new agent to let it "choose" its own trading patterns based on its personality.
*   **Input Context**:
    *   `agent_name`: Name of the agent.
    *   `traits`: Using the 22-trait vector (e.g., Risk Tolerance: High).
    *   `patterns`: List of available patterns with stats.
*   **Output JSON**:
    *   `philosophy`: A short text description of *why* it trades this way.
    *   `selections`: List of pattern IDs and weights.

### 2. Philosophy Generation (`philosophy.j2`)
*   **Purpose**: Generates a human-readable "Bio" or "Manifesto" for the agent.
*   **Input Context**: Agent traits and selected patterns.
*   **Output**: A 1-2 paragraph description (stored in `trading_philosophy` column).

### 3. AI Zone Decision (`ai_zone_decision.j2`)
*   **Purpose**: The critical decision-making prompt when an agent enters the `AI_REFLECT` zone.
*   **Input Context**:
    *   `market_data`: Recent candles, indicators.
    *   `news_context`: (If available) summaries of recent crypto news.
    *   `agent_memory`: Recent wins/losses to simulate "confidence" or "fear".
*   **Output**: `TAKE_TRADE` or `WAIT`.

## Modifying Prompts
You can edit these `.j2` files directly. No restart is required; the system reads them on each call.
