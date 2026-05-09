"""
Global Configuration for Local Agents.

V3 Parity + Local Enhancements.
"""

import os
from pathlib import Path


class Config:
    # ==========================================================================
    # Database - PostgreSQL ONLY (no SQLite)
    # ==========================================================================
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "coinswarm")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "coinswarm")
    # POSTGRES_PASSWORD must be set via environment variable

    # ==========================================================================
    # LLM Settings (Ollama - optimized for GPU)
    # ==========================================================================
    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_MODEL = "koshtenco/agi-trader-kz50-quantum:latest"  # 3.2B trading model, ~250ms after warmup
    # Alternatives: "phi4:14b" (smarter but slower), "qwq:32b" (reasoning)
    LLM_TIMEOUT_SECONDS = 30
    LLM_MAX_RETRIES = 2

    # Ollama optimization options
    OLLAMA_NUM_GPU = 99  # Use all available GPU layers
    OLLAMA_NUM_CTX = 512  # Minimal context for speed
    OLLAMA_NUM_PREDICT = 50  # Short responses
    OLLAMA_TEMPERATURE = 0.1  # Consistent decisions

    # ==========================================================================
    # vLLM Settings (fast, GPU-optimized with prefix caching)
    # Run in WSL: wsl -d Ubuntu -- bash -c "source ~/miniconda3/bin/activate && \
    #   python3 -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-1.5B-Instruct \
    #   --host 0.0.0.0 --port 8000 --max-model-len 1024 --gpu-memory-utilization 0.80 \
    #   --enable-prefix-caching --enforce-eager"
    # ==========================================================================
    VLLM_URL = "http://localhost:8000"
    VLLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"  # Fits in 8GB VRAM with enforce-eager
    # 24GB (P40): "Qwen/Qwen2.5-14B-Instruct", "deepseek-ai/DeepSeek-V2-Lite"
    # 48GB (2xP40): "Qwen/Qwen2.5-32B-Instruct", "mistralai/Mixtral-8x7B-Instruct-v0.1"
    VLLM_GPU_MEMORY_UTILIZATION = 0.80  # Use 80% of VRAM
    VLLM_MAX_MODEL_LEN = 1024  # Context window (reduced for 8GB VRAM)
    VLLM_ENABLE_PREFIX_CACHING = True  # Key optimization for repeated prompts

    # ==========================================================================
    # AI Zone Modes
    # ==========================================================================
    # skip: Treat AI_REFLECT zone as SKIP (fast backtesting) - DEPRECATED
    # heuristic: Use entry_aggression trait (V3 style) - DEPRECATED
    # llm: Real Ollama calls (works without GPU, moderate speed)
    # vllm: vLLM with prefix caching (fast, requires GPU)
    #
    # NOTE: Always use LLM/vLLM for AI decisions - no heuristics or skips
    AI_ZONE_BACKTEST_MODE = "llm"  # Always use LLM for real AI decisions
    AI_ZONE_LIVE_MODE = "vllm"  # Use vLLM for live trading

    # Legacy flag (deprecated - use AI_ZONE_* instead)
    MOCK_AI_ZONE = False

    # ==========================================================================
    # Evolution Settings
    # ==========================================================================
    POPULATION_SIZE = 20
    ELITE_PERCENT = 0.10  # Top 10% are elite parents
    SURVIVAL_PERCENT = 0.70  # Top 70% survive
    MUTATION_RATE = 0.10  # 10% chance per trait

    # Generations
    MAX_GENERATIONS = 100
    CONVERGENCE_THRESHOLD = 0.01  # Stop if fitness improvement < 1%

    # ==========================================================================
    # Memory Review Triggers
    # ==========================================================================
    REVIEW_ON_SESSION_END = True
    REVIEW_ON_BIRTH = True
    REVIEW_BACKTEST_INTERVAL = 50  # Every N backtests
    REVIEW_MEMORY_COUNT_THRESHOLD = 100
    REVIEW_WEAK_MEMORY_COUNT = 10
    REVIEW_WEAK_THRESHOLD = 0.15

    # ==========================================================================
    # Memory Settings
    # ==========================================================================
    MAX_SHORT_TERM_MEMORY = 10  # Items in context window
    MAX_REFLECTION_EVENTS = 10  # Significant events per condensation
    MEMORY_CONDENSATION_DEFAULT = 0.5
    INHERITANCE_DECAY_DEFAULT = 0.3

    # ==========================================================================
    # Backtesting
    # ==========================================================================
    MIN_TRADES_FOR_SIGNIFICANCE = 2  # Minimum trades for fitness calculation
    BACKTEST_DATASET_DAYS = 365  # Default dataset length
    # NOTE: No train/test split - all data is for backtesting (pure evaluation)

    # ==========================================================================
    # Fitness Thresholds
    # ==========================================================================
    FITNESS_DEATH_THRESHOLD = 40  # < 40 = agent dies
    FITNESS_PROMOTE_THRESHOLD = 80  # >= 80 = promoted to next tier

    # ==========================================================================
    # Paths
    # ==========================================================================
    PROMPTS_DIR = Path(__file__).parent / "prompts"
    DATA_DIR = Path(os.getcwd()) / "data"

    @classmethod
    def ensure_dirs(cls):
        """Create required directories."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


class DevConfig(Config):
    """
    Development configuration for faster iteration.

    Use smaller population, fewer generations, lower trade thresholds.
    """

    # ==========================================================================
    # Smaller Evolution for Dev
    # ==========================================================================
    POPULATION_SIZE = 5  # Just 5 agents for testing
    ELITE_PERCENT = 0.40  # 2 elite (40% of 5)
    SURVIVAL_PERCENT = 0.60  # 3 survive (60% of 5)
    MAX_GENERATIONS = 5  # Quick test runs
    CONVERGENCE_THRESHOLD = 0.05  # Less strict convergence

    # ==========================================================================
    # Lower Thresholds for Dev
    # ==========================================================================
    MIN_TRADES_FOR_SIGNIFICANCE = 10  # Fewer trades needed
    BACKTEST_DATASET_DAYS = 30  # Just 1 month of data

    # ==========================================================================
    # Memory - Less Review
    # ==========================================================================
    REVIEW_BACKTEST_INTERVAL = 10
    REVIEW_MEMORY_COUNT_THRESHOLD = 20


class TestConfig(Config):
    """
    Test configuration for unit/integration tests.

    Minimal settings. Uses same PostgreSQL as dev (no SQLite).
    """

    # ==========================================================================
    # Minimal Evolution
    # ==========================================================================
    POPULATION_SIZE = 3
    ELITE_PERCENT = 0.34  # 1 elite
    SURVIVAL_PERCENT = 0.67  # 2 survive
    MAX_GENERATIONS = 2
    MIN_TRADES_FOR_SIGNIFICANCE = 5
    BACKTEST_DATASET_DAYS = 7
