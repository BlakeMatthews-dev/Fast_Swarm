# Coinswarm FastAPI Wrapper - API Reference

## Overview
This API provides a RESTful interface to the Coinswarm agent system, enabling read access to Agents, Patterns, and Trades, as well as triggering core system actions like backtesting and evolution.

**Base URL**: `http://localhost:8000`

## Endpoints

### 1. Agents Domain
Manage and inspect trading agents.

*   `GET /agents`
    *   **Description**: List all active agents.
    *   **Parameters**: `limit` (int, default 100), `skip` (int, default 0).
*   `GET /agents/{agent_id}`
    *   **Description**: Get detailed information for a specific agent (traits, assigned patterns, genealogy).
*   `GET /agents/stats/average`
    *   **Description**: Get population-level statistics, including average trait values and fitness scores.

### 2. Patterns Domain
Inspect trading patterns used by agents.

*   `GET /patterns`
    *   **Description**: List all active patterns.
    *   **Parameters**: `limit` (int, default 100), `skip` (int, default 0).
*   `GET /patterns/{pattern_id}`
    *   **Description**: Get details of a specific pattern (conditions, origin).
*   `GET /patterns/stats/average`
    *   **Description**: Get average performance metrics across all patterns (win rate, ROI, fitness).

### 3. Trades Domain
Inspect historical trading activity.

*   `GET /trades`
    *   **Description**: List recent trades.
    *   **Parameters**:
        *   `limit` (default 100)
        *   `agent_id` (optional filter)
        *   `asset` (optional filter, e.g., 'BTC/USDT')
*   `GET /trades/{trade_id}`
    *   **Description**: Get details of a specific trade (entry/exit price, PnL, reasoning).

### 4. System Actions & Events
Trigger core system processes.

*   `POST /evolution/start`
    *   **Description**: Start a full evolution run (generations, mutation, crossover).
    *   **Body**: `EvolutionRunRequest` (generations, population_size, etc.)
    *   **Result**: Runs in background.
*   `POST /actions/spawn`
    *   **Description**: Spawn a batch of new agents from scratch.
    *   **Parameters**: `count` (int).
*   `POST /actions/backtest`
    *   **Description**: Trigger a backtest for specific agents or the whole swarm.
    *   **Body**: `agent_ids` (list[str], optional).
    *   **Result**: Runs in background, generating new trades in DB.
*   `POST /actions/cull`
    *   **Description**: Remove underperforming agents.
    *   **Parameters**: `survival_rate` (float, default 0.6).

## Database Schema
The API interacts with the PostgreSQL `coinswarm` database.

*   **Agents Table**: `agents`
*   **Patterns Table**: `patterns`
*   **Trades Table**: `agent_trades`

## Key Differences from Legacy Scripts
*   **Asynchronous**: Uses `asyncpg` for non-blocking DB access.
*   **Service Layer**: Logic is encapsulated in `Services/` directories, separating concerns from Routers.
*   **Background Tasks**: Long-running operations (evolution, backtest) are offloaded to background threads to keep the API responsive.
