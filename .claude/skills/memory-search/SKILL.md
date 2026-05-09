# Memory Search

Quick query of memories for specific topics.

## What This Skill Does

1. Takes a search query as argument
2. Calls `mcp__memory__search_nodes` with the query
3. Displays matching entities and observations
4. Shows relevance/match quality
5. Offers to drill deeper or update

## Usage

```
/memory-search trailing stops
/memory-search "PostgreSQL decision"
/memory-search committee quorum
/memory-search position management
```

## Output Format

```
=== MEMORY SEARCH: "trailing stops" ===

MATCHES (2 found):

1. Position Management System [Trading Infrastructure]
   Relevance: ★★★★☆ (direct match)

   Matching observations:
   → "Trailing stops with dynamic percentages based on volatility"
   → "Scale-out functionality for profitable positions"

   Related entities:
   - Committee Tick Trading (uses positions)
   - Exchange Integration (executes stops)

2. 16 Agent Personality Traits [Feature]
   Relevance: ★★☆☆☆ (indirect)

   Matching observations:
   → "stop_loss_tightness: 0-1 scale for how tight stops are"

NO EXACT MATCH? Try:
- "stop loss" (related concept)
- "risk management" (broader category)
- "position" (parent concept)

Actions:
[D]rill into entity | [U]pdate observation | [A]dd new | [Q]uit
```

## Search Tips

| Query Type | Example | Best For |
|------------|---------|----------|
| Single word | `committee` | Broad search |
| Phrase | `"voting weights"` | Exact match |
| Multiple words | `position risk` | AND search |
| Question | `how does committee vote` | Conceptual |

## Process

1. Parse query (handle quotes, multiple words)
2. Call `mcp__memory__search_nodes(query)`
3. Rank results by relevance:
   - Entity name match: 100 points
   - Entity type match: 50 points
   - Observation match: 30 points per match
4. Display with relevance stars
5. Show related entities via relations
6. Offer actions (drill, update, add)

## When to Use

- Quick lookup of specific topics
- Before asking a question (check if known)
- Finding related concepts
- Verifying memory contains expected info
