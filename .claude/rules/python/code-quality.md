---
paths:
  - src/Fast_Swarm/**/*.py
  - Tests/**/*.py
  - "**/*.py"
---

# Python Code Quality Rules

> Extracted from comprehensive code review and real-world trading system failures

---

## Math & Division Safety

**Always guard against division by zero, NaN, and Infinity:**

```python
# BAD
avg_price = total_price / count
roi = (current - entry) / entry

# GOOD
avg_price = total_price / count if count > 0 else 0.0
roi = (current - entry) / entry if entry != 0 else 0.0

# For fitness calculations, bound all results
import math

def safe_fitness(raw_score: float) -> float:
    if not math.isfinite(raw_score):
        return 50.0  # Neutral default
    return max(0.0, min(100.0, raw_score))
```

**Math edge cases to watch:**

```python
import math
import numpy as np

# These all produce problematic values:
math.sqrt(-1)      # ValueError (use cmath for complex)
math.log(0)        # ValueError
math.log(-1)       # ValueError
np.log(0)          # -inf (no error!)
np.sqrt(-1)        # nan (no error!)
1.0 / 0.0          # ZeroDivisionError
np.float64(1) / 0  # inf (no error!)

# ALWAYS check before math operations:
def safe_log(x: float) -> float:
    if x <= 0:
        return float('-inf')  # Or raise, or return 0
    return math.log(x)

def safe_sqrt(x: float) -> float:
    if x < 0:
        return 0.0  # Or raise
    return math.sqrt(x)

# Percentages should be capped
pct = max(-100.0, min(100.0, raw_pct))
```

**NumPy/Pandas silent failures:**

```python
import numpy as np
import pandas as pd

# BAD - These silently produce NaN/inf
arr = np.array([1, 2, 0])
result = 10 / arr  # array([10., 5., inf]) - no error!

df['ratio'] = df['a'] / df['b']  # NaN where b=0, no error

# GOOD - Explicit handling
with np.errstate(divide='raise', invalid='raise'):
    try:
        result = 10 / arr
    except FloatingPointError:
        result = np.where(arr != 0, 10 / np.where(arr != 0, arr, 1), 0)

# Or use numpy's safe division
result = np.divide(10, arr, out=np.zeros_like(arr, dtype=float), where=arr != 0)

# Pandas - fill NaN explicitly
df['ratio'] = df['a'] / df['b'].replace(0, np.nan)
df['ratio'] = df['ratio'].fillna(0)
```

---

## List & Dict Access

**Always check before accessing:**

```python
# BAD
first = prices[0]
last = prices[-1]
value = data['key']

# GOOD
first = prices[0] if prices else None
last = prices[-1] if prices else None
value = data.get('key')  # Returns None if missing
value = data.get('key', default_value)  # With explicit default

# For nested access
value = data.get('level1', {}).get('level2', {}).get('level3', default)

# Or use a helper
def deep_get(d: dict, *keys, default=None):
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d

value = deep_get(data, 'level1', 'level2', 'level3', default=0)
```

---

## JSON Parsing

**Always wrap json.loads in try/except:**

```python
import json
from typing import Any, TypeVar, Optional

T = TypeVar('T')

# BAD
data = json.loads(json_string)

# GOOD
def safe_parse(json_string: str, default: T = None) -> T | None:
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"[Component] JSON parse failed: {str(e)}, input: {json_string[:100]}")
        return default

data = safe_parse(json_string, default={'status': 'error'})
```

---

## Async & Database Patterns

**Use executemany for bulk inserts:**

```python
# BAD - N+1 queries
for item in items:
    cursor.execute("INSERT INTO table VALUES (?)", (item,))

# GOOD - Single batch
cursor.executemany("INSERT INTO table VALUES (?)", [(item,) for item in items])

# For asyncpg (PostgreSQL)
await conn.executemany("INSERT INTO table VALUES ($1)", [(item,) for item in items])
```

**Always use timeouts for HTTP requests:**

```python
import httpx

# GOOD - httpx (preferred for async)
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(url)
```

**Use asyncio.gather with return_exceptions:**

```python
# GOOD - Resilient to individual failures
results = await asyncio.gather(*[fetch(url) for url in urls], return_exceptions=True)
successes = [r for r in results if not isinstance(r, Exception)]
failures = [r for r in results if isinstance(r, Exception)]
```

---

## Error Handling

**Never swallow errors silently:**

```python
# BAD
try:
    operation()
except:  # Bare except catches EVERYTHING
    pass  # Error swallowed

# GOOD
try:
    operation()
except Exception as e:
    logger.error(f"[Component] Operation failed: {e}", exc_info=True)
    raise
```

**Use context managers for resources:**

```python
# GOOD
with open("data.json") as file:
    data = json.load(file)

with sqlite3.connect("db.sqlite") as conn:
    cursor = conn.cursor()
```

---

## Type Safety

**Use type hints everywhere:**

```python
from typing import TypedDict

class Trade(TypedDict):
    id: str
    pnl: float
    timestamp: int

def calculate_fitness(pattern: Pattern, trades: list[Trade]) -> float:
    if not trades:
        return 0.0
    return sum(t['pnl'] for t in trades) / len(trades)
```

---

## Common Python Gotchas

**Mutable default arguments:**

```python
# BAD - Default list shared across calls
def add_item(item, items=[]):
    items.append(item)
    return items

# GOOD
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

**Float comparison:**

```python
import math

# GOOD
if math.isclose(price, 100.0, rel_tol=1e-9):
    ...
```

---

## Pandas/NumPy Specific

**Chain awareness:**

```python
# GOOD - Explicit copy
df2 = df[df['price'] > 100].copy()
df2['new_col'] = 1
```

**Empty DataFrame handling:**

```python
mean_val = df['col'].mean() if not df.empty else 0.0
first_row = df.iloc[0] if not df.empty else None
```
