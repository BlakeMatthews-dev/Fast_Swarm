# Data Architecture

## Overview
Coinswarm uses a hybrid data architecture, transitioning from legacy SQLite files to a robust PostgreSQL-centric model. The FastAPI wrapper primarily interacts with PostgreSQL using `SQLModel` (an async wrapper around SQLAlchemy + Pydantic).

## Primary Domains (Mapped)

These tables have corresponding `SQLModel` classes in the FastAPI application (`Fast_Swarm/*/Models/models.py`) and are fully accessible via the API.

### 1. Agents Table (`agents`)
Stores the persistent state of all autonomous agents.

| Column | Type | Description |
|--------|------|-------------|
| `agent_id` | UUID | Unique identifier. |
| `agent_name` | String | Human-readable name (e.g., "Neo_Gen1_X7"). |
| `traits` | JSONB | The 22-dimensional personality vector (Risk, Greed, etc.). |
| `fitness_score` | Float | ROI-based performance metric. |
| `status` | String | `active`, `retired`, `dead`. |
| `generation` | Integer | Evolutionary generation number. |
| `assigned_patterns` | JSONB | List of pattern IDs this agent is specialized in. |

### 2. Patterns Table (`patterns`)
Stores technical analysis patterns discovered or defined for the agents to use.

| Column | Type | Description |
|--------|------|-------------|
| `pattern_id` | String | Unique identifier or name (e.g., "bull_flag_1h"). |
| `entry_conditions` | JSONB | Logic for entering a trade. |
| `exit_conditions` | JSONB | Logic for exiting a trade. |
| `win_rate` | Float | Historical win rate (0.0-100.0). |
| `total_trades` | Integer | Number of times this pattern has triggered. |
| `fitness_score` | Float | Pattern-specific performance score. |

### 3. Trades Table (`agent_trades`)
Immutable log of all trading activity.

| Column | Type | Description |
|--------|------|-------------|
| `trade_id` | UUID | Unique trade identifier. |
| `agent_id` | UUID | Foreign key to `agents`. |
| `asset` | String | Symbol (e.g., "BTC/USDT"). |
| `direction` | String | `long` or `short`. |
| `entry_price` | Float | Price at entry. |
| `exit_price` | Float | Price at exit. |
| `pnl_pct` | Float | Percentage Profit/Loss. |
| `decision_zone` | String | Logic path taken (`execute`, `wait`, `ai_reflect`). |

## Unmapped Tables (Pending Integration)

The database contains additional tables that are currently **not mapped** to SQLModel classes in the FastAPI wrapper.

### Evolution & Backtesting
*   `evolution_cycles`: Metadata about each evolutionary generation.
*   `evolution_events`: Log of significant events (births, deaths, mutations).
*   `backtest_results`: Aggregated performance metrics for full backtest runs.
*   `backtest_trades_unified`: Consolidated view of all backtest trades.

### Market Data & Exchange
*   `klines` / `klines_hist`: Raw candlestick data from exchanges.
*   `funding_rates_hist`: Historical funding rates.
*   `open_interest` / `liquidations`: Derivatives market data.
*   `execution_stats`: Metrics on slippage and latency.
*   `market_trades`: Raw trade feed from the exchange.

### Governance (Swarm Intelligence)
*   `committees`: Groups of agents formed for consensus.
*   `committee_votes`: Individual votes within a committee.
*   `committee_decisions`: Final consensus decisions executed by the swarm.

### Miscellaneous
*   `agent_memories`: Storage for agent episodic memory.
*   `pattern_embeddings`: Vector representations of patterns.
*   `paper_trades` / `paper_positions`: Forward-testing (paper trading) logs.
*   `fear_greed_index`: Sentiment data source.

## ORM Strategy
We use `SQLModel` to define our data structures in Python code (`Fast_Swarm/*/Models/models.py`). This ensures:
1.  **Type Safety**: Automatic validation via Pydantic.
2.  **Async Support**: Native integration with `asyncpg` for high-concurrency access.
3.  **Migration Path**: Code-first schema definitions.
