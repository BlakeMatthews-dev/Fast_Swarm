---
description: Search memories for specific topics
argument-hint: <search query>
---

# Memory Search

Quick query of memories for specific topics.

## Usage

Provide search terms after the command:
- `/memory-search trailing stops`
- `/memory-search "PostgreSQL decision"`
- `/memory-search committee quorum`

## Process

1. Take search query from $ARGUMENTS
2. Call `mcp__memory__search_nodes` with query
3. Display matching entities and observations
4. Show relevance ranking
5. Offer to drill deeper or update

## Output Format

```
=== MEMORY SEARCH: "[query]" ===

MATCHES (N found):

1. [Entity Name] [Type]
   Relevance: ★★★★☆

   Matching observations:
   → "[observation 1]"
   → "[observation 2]"

2. [Another Entity] [Type]
   Relevance: ★★☆☆☆
   ...

Actions: [D]rill into | [U]pdate | [A]dd new
```
