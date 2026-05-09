# Migration Guide: SQLite to PostgreSQL

## Background
The system currently interacts with both PostgreSQL (primary storage) and flat files/SQLite (legacy or specific data sources).

## Data Source Transition

1.  **Patterns**:
    *   File Source: `local_agents/patterns.json`
    *   Database: `patterns` table in Postgres.
    *   *Status*: The system auto-seeds patterns on startup if the table is empty.

2.  **Agents**:
    *   File Source: SQLite `agents` table (various locations).
    *   Database: `agents` table in Postgres.
    *   *Status*: New agents are spawned directly into Postgres.

3.  **Market Data**:
    *   Status: **External Source**.
    *   The system reads OHLCV data from `local-utilities/enhanced_candles.db` (SQLite). This serves as the data lake for backtesting.
