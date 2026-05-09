---
paths:
  - v2/cloudflare-agents/**/*.ts
  - v3/cloudflare-agents/**/*.ts
  - "**/*.ts"
---

# TypeScript Code Quality Rules

> Extracted from comprehensive code review (420+ issues identified across codebase)

---

## Math & Division Safety

**Always guard against division by zero, NaN, and Infinity:**

```typescript
// BAD
const avgPrice = totalPrice / count;
const roi = (current - entry) / entry;

// GOOD
const avgPrice = count > 0 ? totalPrice / count : 0;
const roi = entry !== 0 ? (current - entry) / entry : 0;

// For fitness calculations, bound all results
const fitness = Math.min(100, Math.max(0, rawScore));
if (!isFinite(value) || isNaN(value)) return 50; // Neutral default
```

**Math edge cases to watch:**
- `Math.sqrt(negative)` → NaN
- `Math.log(0)` → -Infinity
- `Math.log(negative)` → NaN
- Percentages should be capped: `Math.min(100, Math.max(-100, pct))`

---

## Array & Object Access

**Always check array length before accessing elements:**

```typescript
// BAD
const first = prices[0];
const last = prices[prices.length - 1];

// GOOD
const first = prices.length > 0 ? prices[0] : null;
const last = prices.length > 0 ? prices[prices.length - 1] : null;

// For optional chaining
const value = result?.data?.items?.[0]?.price ?? 0;
```

---

## JSON Parsing

**Always wrap JSON.parse in try/catch:**

```typescript
// BAD
const data = JSON.parse(jsonString);

// GOOD
function safeParse<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json) as T;
  } catch {
    console.error('[Component] JSON parse failed:', json?.substring(0, 100));
    return fallback;
  }
}

const data = safeParse(jsonString, { default: 'value' });
```

---

## Async & Database Patterns

**Use db.batch() for multiple database operations:**

```typescript
// BAD - Race conditions, N+1 queries
for (const item of items) {
  await env.DB.prepare('INSERT INTO table VALUES (?)').bind(item).run();
}

// GOOD - Atomic batch (max 100 statements per batch)
const BATCH_LIMIT = 100;
for (let i = 0; i < items.length; i += BATCH_LIMIT) {
  const batch = items.slice(i, i + BATCH_LIMIT);
  await env.DB.batch(
    batch.map(item => env.DB.prepare('INSERT INTO table VALUES (?)').bind(item))
  );
}
```

**Always use timeouts for fetch:**

```typescript
// BAD
const response = await fetch(url);

// GOOD
async function fetchWithTimeout(url: string, timeout = 10000): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return response;
  } finally {
    clearTimeout(id);
  }
}
```

**Use Promise.allSettled for external APIs:**

```typescript
// BAD - One failure breaks all
const results = await Promise.all(urls.map(url => fetch(url)));

// GOOD - Resilient to individual failures
const results = await Promise.allSettled(urls.map(url => fetch(url)));
const successes = results.filter(r => r.status === 'fulfilled');
```

---

## Security Rules

**Never put API keys in URLs:**

```typescript
// BAD - Keys get logged/cached
const url = `https://api.example.com/data?apikey=${apiKey}`;

// GOOD - Keys in headers
const response = await fetch(url, {
  headers: { 'Authorization': `Bearer ${apiKey}` }
});
```

**Always use parameterized SQL:**

```typescript
// BAD - SQL injection risk
const sql = `SELECT * FROM patterns WHERE asset = '${asset}'`;

// GOOD - Parameterized
const result = await env.DB.prepare('SELECT * FROM patterns WHERE asset = ?').bind(asset).all();
```

**Validate table names if dynamic:**

```typescript
// If table names must be dynamic, whitelist them
const ALLOWED_TABLES = ['ohlcv_1h', 'ohlcv_6h', 'ohlcv_1d'];
if (!ALLOWED_TABLES.includes(tableName)) {
  throw new Error(`Invalid table: ${tableName}`);
}
```

---

## Error Handling

**Never swallow errors:**

```typescript
// BAD
try {
  await operation();
} catch {} // Error swallowed

// GOOD
try {
  await operation();
} catch (error) {
  console.error('[Component] Operation failed:', { error, context });
  throw error; // Re-throw or handle appropriately
}
```

**Always check response.ok for fetch:**

```typescript
// BAD - fetch doesn't reject on 404/500
const response = await fetch(url);
const data = await response.json();

// GOOD
const response = await fetch(url);
if (!response.ok) {
  throw new Error(`HTTP ${response.status}: ${response.statusText}`);
}
const data = await response.json();
```

---

## TypeScript Type Safety

**Avoid `as any` - use proper types:**

```typescript
// BAD
const result = data as any;

// GOOD - Define types
interface PatternResult {
  id: string;
  fitness_score: number;
}
const result = data as PatternResult;

// BETTER - Runtime validation with Zod or similar
const result = PatternResultSchema.parse(data);
```

**Add radix to parseInt:**

```typescript
// BAD - Can parse as octal
const num = parseInt(value);

// GOOD
const num = parseInt(value, 10);

// OR use Number() for cleaner behavior
const num = Number(value);
```

**Use Number.isNaN not global isNaN:**

```typescript
// BAD - isNaN coerces types unexpectedly
if (isNaN(value)) { ... } // isNaN('hello') === true

// GOOD
if (Number.isNaN(value)) { ... }
```

---

## Switch Statements

**Always include default case or exhaustive check:**

```typescript
// BAD
switch (status) {
  case 'pending': return handlePending();
  case 'complete': return handleComplete();
  // Missing default - returns undefined
}

// GOOD - Exhaustive check
function handleStatus(status: 'pending' | 'complete' | 'failed'): Result {
  switch (status) {
    case 'pending': return handlePending();
    case 'complete': return handleComplete();
    case 'failed': return handleFailed();
    default:
      const _exhaustive: never = status;
      throw new Error(`Unknown status: ${_exhaustive}`);
  }
}
```

---

## Cloudflare-Specific Limits

| Limit | Value | Consequence |
|-------|-------|-------------|
| **db.batch()** | 100 statements | Silent failure over 100 |
| **CPU time** | 30ms free / 30s paid | Script killed |
| **Memory** | 128MB | OOM crash |
| **Subrequests** | 50 per request | Excess requests fail |
| **KV value** | 25MB | Write fails |
| **DO storage value** | 128KB | Silent truncation |
| **Response size** | 100MB | Request fails |

**Chunk batches:**

```typescript
const BATCH_LIMIT = 100;
for (let i = 0; i < statements.length; i += BATCH_LIMIT) {
  await env.DB.batch(statements.slice(i, i + BATCH_LIMIT));
}
```

---

## ID Generation

**Use crypto.randomUUID() not Math.random():**

```typescript
// BAD - Not crypto-safe
const id = Math.random().toString(36).substring(2);

// GOOD - Crypto-safe UUID
const id = crypto.randomUUID();
```

---

## Logging Format

**Use structured logging:**

```typescript
// Format: [Component] Action { context }
console.log('[PatternDO] Backtest complete', { patternId, fitness: 78.5 });
console.error('[EvolutionAgent] Phase failed', { phase: 'discovery', error });
```
