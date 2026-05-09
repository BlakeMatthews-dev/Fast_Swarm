---
paths:
  - local-utilities/**/*.py
  - pyswarm/**/*.py
  - "*.py"
---

# Python Utilities Rules

## Package Management
- Use `uv` for dependency management when available
- Virtual environment in `.venv/`
- Dependencies in `pyproject.toml`

## Data Import Scripts
- Always use real data from D1/R2, never mock data
- Batch operations to avoid rate limits
- Log progress for long-running imports
- Save checkpoint files for resumable operations

## Type Hints
```python
def process_candles(
    asset: str,
    candles: list[dict],
    *,
    timeframe: str = "1h"
) -> dict[str, float]:
    ...
```

## Error Handling
```python
import logging

logger = logging.getLogger(__name__)

try:
    result = process_data(data)
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise
except Exception as e:
    logger.exception(f"Unexpected error processing {asset}")
    raise
```

## Wrangler Integration
```python
import subprocess

# Query D1
result = subprocess.run(
    ["wrangler", "d1", "execute", "coinswarm-data-shard-1", "--command", sql],
    capture_output=True, text=True
)
```
