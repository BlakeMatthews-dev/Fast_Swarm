# System Configuration

Configuration is managed via Environment Variables (loaded from `.env`).

## Database Connection
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `coinswarm` | DB Username. |
| `POSTGRES_PASSWORD` | `coinswarm_dev_2024` | DB Password. |
| `POSTGRES_HOST` | `localhost` | DB Host (use `postgres` if running inside docker). |
| `POSTGRES_DB` | `coinswarm` | Database Name. |
| `POSTGRES_PORT` | `5432` | Port. |

## Evolution Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `SWARM_POPULATION_SIZE` | `50` | Number of agents per generation. |
| `EVOLUTION_GENERATIONS` | `10` | Default generations for a run. |
| `MUTATION_RATE` | `0.1` | Probability of trait mutation. |

## LLM Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai`, or `anthropic`. |
| `LLM_MODEL` | `llama3` | Model name to use. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL for local inference. |
