# Coinswarm Operator Guide

## Getting Started

1.  **Start the Server**
    ```powershell
    cd Coinswarm-1
    uvicorn Fast_Swarm.Main:app --reload
    ```
    Access the interactive docs at: `http://localhost:8000/docs`

## Common Workflows

### 1. Monitoring the Swarm
*   **Check Swarm Health**: Call `GET /agents/stats/average` to see the average fitness and trait distribution of your active agents.
*   **Inspect Top Agents**: Call `GET /agents?limit=10` combined with client-side sorting (or future server-side sort) to find your best performers.
*   **Review Performance**: Call `GET /trades` to see the latest trading activity across the entire swarm.

### 2. Managing Population
*   **Spawn New Agents**: If your population is low, use `POST /actions/spawn?count=10` to inject fresh DNA into the pool.
*   **Cull Weak Agents**: If the database is cluttered with poor performers, use `POST /actions/cull?survival_rate=0.5` to remove the bottom 50%.

### 3. Running Simulations
*   **Trigger Backtest**: To verify how current agents perform on recent data, call `POST /actions/backtest`. This runs in the background. You can monitor progress by watching the trade count increase via `GET /trades`.
*   **Run Evolution**: for a full evolutionary cycle (generations, crossover, mutation), use `POST /evolution/start`.

## Troubleshooting
*   **Database Connection**: Ensure your `.env` or environment variables match the `docker-compose.yml` settings (`coinswarm` / `coinswarm_dev_2024`).
*   **Missing Data**: If backtests produce 0 trades, check `local-utilities/enhanced_candles.db` to ensure you have market data for the assets/timeframes you are testing.
