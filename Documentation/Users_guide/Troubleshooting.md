# Troubleshooting Guide

## Database Issues

### `FATAL: password authentication failed`
*   **Cause**: The PostgreSQL password in `.env` does not match the docker container.
*   **Fix**: Check `docker-compose.yml` for `POSTGRES_PASSWORD`. Default is often `coinswarm` or `coinswarm_dev_2024`. Update your `.env` file to match.

### `ConnectionRefusedError: [WinError 10061]`
*   **Cause**: PostgreSQL is not running.
*   **Fix**: Run `docker-compose up -d` in `local-utilities/`.

## LLM / AI Issues

### `vLLM not available`
*   **Cause**: The `vllm` python package is not installed (common on Windows as vLLM is Linux-optimized).
*   **Fix**: The system automatically falls back to `Ollama` or `Heuristic` mode. This is a warning, not a critical error.

### `OllamaConnectionError`
*   **Cause**: Ollama is not running locally on port 11434.
*   **Fix**: Start the Ollama desktop app.

## Data Issues

### Backtest returns 0 trades
*   **Cause**: Missing market data.
*   **Fix**: Ensure `enhanced_candles.db` exists in `local-utilities/` and has data for the requested timeframe. You may need to run `scripts/backfill-sentiment.ps1`.
