# Testing Strategy

## Overview
Coinswarm uses a mix of standard `pytest` unit tests and custom "verification scripts" to ensure system integrity.

## Running Tests

### 1. Unit Tests
Located in `local_agents/tests/`.
```powershell
cd local_agents
pytest
```

### 2. Verification Scripts (FastAPI)
Located in `Fast_Swarm/`. These check specific integrations.

*   `check_schema.py`: Verifies the `patterns` table schema matches the PostgreSQL DB.
    *   *Run*: `python Fast_Swarm/check_schema.py`
*   `check_trades.py`: Verifies DB connectivity and counts total trades.
    *   *Run*: `python Fast_Swarm/check_trades.py`
*   `demo_backtest.py`: End-to-end test. Spawns a backtest for 2 agents and verifies the trade count increases.
    *   *Run*: `python Fast_Swarm/demo_backtest.py`

## Continuous Integration
Future roadmap includes running these tests automatically on GitHub Actions.
