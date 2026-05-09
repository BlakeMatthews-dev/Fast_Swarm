# Monitoring Domains Reference

The FastAPI wrapper now includes specialized domains for monitoring the active Swarm system.

## 1. Evolution Domain
**Prefix**: `/evolution/monitor`
*   `GET /cycles`: List recent evolutionary generations/cycles.
*   `GET /cycles/current`: Get the currently active cycle (if running).
*   `GET /events/{cycle_id}`: View detailed logs (spawns, deaths, mutations) for a cycle.

**Usage**: Use this to build a "Live Feed" of what the Evolution Daemon is doing.

## 2. Governance Domain
**Prefix**: `/governance`
*   `GET /committees`: List active agent committees.
*   `GET /committees/{id}`: View committee details (assets, quorum, performance).
*   `GET /committees/{id}/decisions`: View consensus decisions (Buy/Sell/Hold).
*   `GET /committees/{id}/votes`: Detailed stream of individual agent votes.

**Usage**: Use this to visualize *why* the swarm is trading. Show the "Vote Distribution" (e.g., 70% Bullish) on your dashboard.

## 3. Market Data Domain
**Prefix**: `/market_data`
*   `GET /candles`: Fetch raw OHLCV data from Postgres.
*   `GET /range`: Fetch a specific historical range for charting.

**Usage**: Lightweight chart data access directly from the DB.
