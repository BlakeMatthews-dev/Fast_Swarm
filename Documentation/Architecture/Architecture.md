# System Architecture: FastAPI Wrapper & Local Agents

## Overview
The Coinswarm FastAPI Wrapper serves as a modern control plane and data access layer sitting on top of the existing `local_agents` Python core. It bridges the gap between the legacy script-based execution model and a modern, web-accessible service architecture.

## Architecture Diagram

```mermaid
graph TD
    Client[Web Client / User] -->|HTTP JSON| FastAPI[FastAPI Server]
    
    subgraph "Fast_Swarm (New Layer)"
        FastAPI --> Routers[Routers (Agents, Patterns, Trades)]
        Routers --> Services[Service Layer]
        Services --> Models[SQLModel / Pydantic Models]
    end
    
    subgraph "Data Layer"
        Services -->|SQLAlchemy/AsyncPG| PG[(PostgreSQL Database)]
        PG -->|Tables| T_Agents[agents]
        PG -->|Tables| T_Patterns[patterns]
        PG -->|Tables| T_Trades[agent_trades]
        PG -->|Tables| T_Gov[committees/votes]
        PG -->|Tables| T_Evo[evolution_cycles]
        PG -->|Tables| T_Mkt[candles]
    end
    
    subgraph "Legacy Core (local_agents)"
        Services -->|Direct Import| Evolution[run_evolution.py]
        Services -->|Direct Import| Backtest[backtest/engine.py]
        Services -->|Direct Import| Genesis[core/genesis.py]
        
        Evolution -->|Writes| PG
        Backtest -->|Writes| PG
        Genesis -->|Writes| PG
    end
```

## Key Components

### 1. Fast_Swarm Application
*   **Entry Point**: `Main.Py` - Configures the app, database lifecycles, and router inclusion.
*   **Database**: `Database.py` - Manages the `asyncpg` connection pool and `SQLModel` engines.
*   **Domain Structure**: Code is organized by domain (`Agents`, `Patterns`, `Trades`, `Evolution`, `Governance`), each containing:
    *   `Models/`: Database schema definitions.
    *   `Routers/`: API endpoint definitions.
    *   `Services/`: Business logic and wrappers.

### 2. Integration Strategy
*   **Read Operations**: The API reads directly from PostgreSQL using its own efficient `SQLModel` definitions.
*   **Action Operations**: The API currently focuses on **Monitoring**. Direct control of the Evolution Daemon or Backtest Engine is planned but the underlying `local_agents` core is currently being refactored by another team.
    *   *Note*: The API is designed to eventually wrap these core functions.
*   **Pure Postgres**: All data, including Market Data (`candles`) and Logs (`evolution_events`), resides in PostgreSQL. There is no SQLite dependency for reading data.

### 3. File Map
*   **FastAPI Root**: `Fast_Swarm/`
*   **Legacy Core**: `local_agents/`
*   **Shared Utilities**: `local-utilities/`
```
