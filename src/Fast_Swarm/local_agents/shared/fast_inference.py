"""
Ultra-Fast LLM Inference for Bulk Agent Decisions.

Optimized for making HUNDREDS of AI decisions per backtest via:
1. Static prefix caching - System prompt tokenized once
2. Minimal context - Only 6 essential numbers per decision
3. Single-token output - "T" (take) or "S" (skip)
4. True batch inference - vLLM concurrent processing
5. Async pipeline - Queue decisions, process in batches

Target: <10ms per decision with warm cache and batching.

Usage:
    engine = FastDecisionEngine()
    decisions = engine.batch_decide(decision_requests)
"""

import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass

# =============================================================================
# Configuration
# =============================================================================

try:
    from Fast_Swarm.local_agents.config import Config

    VLLM_URL = getattr(Config, "VLLM_URL", "http://localhost:8000")
    VLLM_MODEL = getattr(Config, "VLLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
except ImportError:
    VLLM_URL = "http://localhost:8000"
    VLLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


# =============================================================================
# Ultra-Compact Prompt System
# =============================================================================

# This STATIC system prompt is cached after first call (~50 tokens)
# Never changes across any agent or decision
FAST_SYSTEM_PROMPT = """Trade decision AI. Input: 6 numbers. Output: T or S only.

Numbers: conf, rsi, macd, risk, aggr, wr
- conf: pattern confidence 0-1, higher=stronger signal
- rsi: 0-100, <30 oversold, >70 overbought
- macd: momentum, >0 bullish
- risk: agent risk tolerance 0-1
- aggr: entry aggression 0-1
- wr: recent win rate 0-1

Rules:
- High conf (>0.6) + aligned indicators = T
- Low conf (<0.4) + aggressive agent = T
- Conflicting signals = S
- Always consider risk vs reward

Reply with ONLY "T" or "S", nothing else."""


def build_fast_prompt(
    confidence: float,
    rsi: float,
    macd: float,
    risk_tolerance: float,
    entry_aggression: float,
    recent_win_rate: float,
) -> str:
    """
    Build ultra-minimal prompt (~20 tokens).

    Format: "0.45 28.3 -0.5 0.7 0.8 0.6"
    """
    return f"{confidence:.2f} {rsi:.1f} {macd:.2f} {risk_tolerance:.2f} {entry_aggression:.2f} {recent_win_rate:.2f}"


@dataclass
class DecisionRequest:
    """Input for a single decision."""

    request_id: str
    confidence: float
    rsi: float = 50.0
    macd: float = 0.0
    risk_tolerance: float = 0.5
    entry_aggression: float = 0.5
    recent_win_rate: float = 0.5

    # Optional full context for debugging
    pattern_name: str = ""
    candle_index: int = 0


@dataclass
class DecisionResult:
    """Output from a single decision."""

    request_id: str
    should_trade: bool
    latency_ms: float = 0.0
    cached: bool = False
    error: str | None = None


# =============================================================================
# Fast Decision Engine
# =============================================================================


class FastDecisionEngine:
    """
    Ultra-fast LLM inference engine for bulk agent decisions.

    Modes:
    - HEURISTIC: Pure rule-based (0.001ms per decision) - for backtesting
    - LLM: Full vLLM inference (~300-2000ms) - for live trading
    - HYBRID: Heuristic with occasional LLM validation (configurable %)

    Optimizations:
    - Prefix caching: System prompt tokenized once
    - Minimal prompts: 6 numbers only
    - Single-token output: T or S
    - Batch inference: Process multiple requests concurrently
    - Result caching: Skip LLM for identical inputs
    """

    def __init__(
        self,
        base_url: str = VLLM_URL,
        model: str = VLLM_MODEL,
        batch_size: int = 32,
        max_concurrent: int = 8,
        cache_results: bool = True,
        timeout: float = 5.0,
        mode: str = "heuristic",  # "heuristic", "llm", or "hybrid"
        llm_sample_rate: float = 0.01,  # For hybrid: % of decisions to validate with LLM
    ):
        """
        Initialize fast decision engine.

        Args:
            base_url: vLLM server URL
            model: Model name
            batch_size: Max requests per batch
            max_concurrent: Max concurrent HTTP requests
            cache_results: Cache identical inputs
            timeout: Request timeout in seconds
            mode: Decision mode - "heuristic", "llm", or "hybrid"
            llm_sample_rate: For hybrid mode, fraction of decisions to validate with LLM
        """
        self.base_url = base_url
        self.model = model
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.cache_results = cache_results
        self.timeout = timeout
        self.mode = mode.lower()
        self.llm_sample_rate = llm_sample_rate

        # Result cache: hash -> (should_trade, cached_at)
        self._cache: dict[str, tuple[bool, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Metrics
        self._total_decisions = 0
        self._total_latency_ms = 0.0
        self._heuristic_decisions = 0
        self._llm_decisions = 0
        self._llm_heuristic_agreement = 0  # For hybrid validation
        self._warmed_up = False

        # Thread pool for concurrent requests
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent)

    def _hash_request(self, req: DecisionRequest) -> str:
        """Create cache key from request."""
        # Round values to reduce cache misses from floating point variance
        key = f"{req.confidence:.2f}|{req.rsi:.0f}|{req.macd:.1f}|{req.risk_tolerance:.1f}|{req.entry_aggression:.1f}|{req.recent_win_rate:.1f}"
        return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:12]

    def is_available(self) -> bool:
        """Check if vLLM server is running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=2) as response:  # nosec B310 - trusted localhost URL
                return response.status == 200
        except Exception:
            return False

    def warmup(self) -> bool:
        """
        Warm up the model by making a test call.

        This loads the model and caches the system prompt prefix.
        """
        if self._warmed_up:
            return True

        if not self.is_available():
            return False

        # Make a test call to cache the system prompt
        test_req = DecisionRequest(
            request_id="warmup",
            confidence=0.5,
            rsi=50,
            macd=0,
        )
        result = self._single_decide(test_req)

        if result.error is None:
            self._warmed_up = True
            print(f"[FastInference] Warmed up in {result.latency_ms:.0f}ms")
            return True

        return False

    def _single_decide(self, req: DecisionRequest) -> DecisionResult:
        """Make a single decision via vLLM."""
        start = time.perf_counter()

        # Check cache
        if self.cache_results:
            cache_key = self._hash_request(req)
            if cache_key in self._cache:
                self._cache_hits += 1
                should_trade, _ = self._cache[cache_key]
                return DecisionResult(
                    request_id=req.request_id,
                    should_trade=should_trade,
                    latency_ms=0.01,  # Cache hit
                    cached=True,
                )
            self._cache_misses += 1

        # Build prompt
        prompt = build_fast_prompt(
            confidence=req.confidence,
            rsi=req.rsi,
            macd=req.macd,
            risk_tolerance=req.risk_tolerance,
            entry_aggression=req.entry_aggression,
            recent_win_rate=req.recent_win_rate,
        )

        # Build request payload
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": FAST_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,  # Deterministic
            "max_tokens": 1,  # Just T or S
            "stream": False,
        }

        try:
            http_req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(http_req, timeout=self.timeout) as response:  # nosec B310 - trusted localhost URL
                result = json.loads(response.read().decode())

            # Extract response
            choice = result.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "").strip().upper()

            # Parse T or S
            should_trade = content.startswith("T")

            latency_ms = (time.perf_counter() - start) * 1000

            # Cache result
            if self.cache_results:
                self._cache[cache_key] = (should_trade, time.time())

            # Update metrics
            self._total_decisions += 1
            self._total_latency_ms += latency_ms

            return DecisionResult(
                request_id=req.request_id,
                should_trade=should_trade,
                latency_ms=latency_ms,
                cached=False,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return DecisionResult(
                request_id=req.request_id,
                should_trade=False,  # Default to skip on error
                latency_ms=latency_ms,
                error=str(e),
            )

    def decide(self, req: DecisionRequest) -> DecisionResult:
        """
        Make a single decision using configured mode.

        Modes:
        - heuristic: Fast rule-based (0.001ms)
        - llm: Full vLLM inference (~300-2000ms)
        - hybrid: Heuristic with occasional LLM validation
        """
        import random

        if self.mode == "heuristic":
            self._heuristic_decisions += 1
            return self.decide_heuristic(req)

        elif self.mode == "llm":
            self._llm_decisions += 1
            if self.is_available():
                return self._single_decide(req)
            else:
                # Fallback to heuristic if LLM unavailable
                self._heuristic_decisions += 1
                return self.decide_heuristic(req)

        elif self.mode == "hybrid":
            # Always get heuristic decision
            heuristic_result = self.decide_heuristic(req)
            self._heuristic_decisions += 1

            # Occasionally validate with LLM
            if random.random() < self.llm_sample_rate and self.is_available():
                llm_result = self._single_decide(req)
                self._llm_decisions += 1

                # Track agreement
                if llm_result.should_trade == heuristic_result.should_trade:
                    self._llm_heuristic_agreement += 1

                # Return LLM result for this sample
                return llm_result

            return heuristic_result

        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    def batch_decide(
        self,
        requests: list[DecisionRequest],
        parallel: bool = True,
    ) -> list[DecisionResult]:
        """
        Make decisions for a batch of requests.

        Uses configured mode (heuristic/llm/hybrid).

        Args:
            requests: List of decision requests
            parallel: If True, process requests concurrently

        Returns:
            List of decision results in same order as requests
        """
        if not requests:
            return []

        # For heuristic mode, skip all the complexity
        if self.mode == "heuristic":
            results = []
            for req in requests:
                results.append(self.decide_heuristic(req))
                self._heuristic_decisions += 1
            return results

        # For hybrid mode, use decide() which handles sampling
        if self.mode == "hybrid":
            return [self.decide(req) for req in requests]

        # LLM mode - use cache and parallel processing
        # Split into cache hits and misses
        cached_results = {}
        uncached_requests = []

        if self.cache_results:
            for req in requests:
                cache_key = self._hash_request(req)
                if cache_key in self._cache:
                    should_trade, _ = self._cache[cache_key]
                    cached_results[req.request_id] = DecisionResult(
                        request_id=req.request_id,
                        should_trade=should_trade,
                        latency_ms=0.01,
                        cached=True,
                    )
                    self._cache_hits += 1
                else:
                    uncached_requests.append(req)
                    self._cache_misses += 1
        else:
            uncached_requests = requests

        # Process uncached requests
        new_results = {}

        if uncached_requests:
            if parallel and len(uncached_requests) > 1:
                # Process in parallel using thread pool
                futures = {self._executor.submit(self._single_decide, req): req.request_id for req in uncached_requests}

                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    new_results[result.request_id] = result
                    self._llm_decisions += 1
            else:
                # Process sequentially
                for req in uncached_requests:
                    result = self._single_decide(req)
                    new_results[result.request_id] = result
                    self._llm_decisions += 1

        # Combine and return in original order
        all_results = {**cached_results, **new_results}
        return [all_results[req.request_id] for req in requests]

    def decide_heuristic(self, req: DecisionRequest) -> DecisionResult:
        """
        Fast heuristic decision without LLM.

        Used as fallback when LLM is unavailable.
        """
        # Simple rule-based decision
        score = 0.0

        # High confidence = take
        if req.confidence > 0.6:
            score += 0.3
        elif req.confidence > 0.4:
            score += 0.1

        # RSI alignment
        if req.rsi < 30:  # Oversold = buy opportunity
            score += 0.2
        elif req.rsi > 70:  # Overbought = caution
            score -= 0.2

        # MACD positive = bullish
        if req.macd > 0:
            score += 0.1

        # Agent personality
        score += (req.entry_aggression - 0.5) * 0.2
        score += (req.risk_tolerance - 0.5) * 0.1

        # Recent performance
        if req.recent_win_rate > 0.55:
            score += 0.1
        elif req.recent_win_rate < 0.45:
            score -= 0.1

        should_trade = score > 0

        return DecisionResult(
            request_id=req.request_id,
            should_trade=should_trade,
            latency_ms=0.001,
            cached=False,
        )

    def batch_decide_with_fallback(
        self,
        requests: list[DecisionRequest],
    ) -> list[DecisionResult]:
        """
        Batch decide with heuristic fallback if LLM unavailable.
        """
        if not self.is_available():
            return [self.decide_heuristic(req) for req in requests]

        return self.batch_decide(requests, parallel=True)

    @property
    def stats(self) -> dict:
        """Get performance statistics."""
        avg_latency = self._total_latency_ms / self._total_decisions if self._total_decisions > 0 else 0
        cache_rate = (
            self._cache_hits / (self._cache_hits + self._cache_misses)
            if (self._cache_hits + self._cache_misses) > 0
            else 0
        )

        return {
            "total_decisions": self._total_decisions,
            "avg_latency_ms": avg_latency,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": cache_rate,
            "warmed_up": self._warmed_up,
        }

    def clear_cache(self):
        """Clear the result cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def shutdown(self):
        """Shutdown the executor."""
        self._executor.shutdown(wait=False)


# =============================================================================
# Sliding Window Backtest Integration
# =============================================================================


class BacktestDecisionBatcher:
    """
    Batches AI decisions across sliding window backtests.

    Instead of making one decision per candle, collects decisions
    across multiple windows and processes in batches.
    """

    def __init__(
        self,
        engine: FastDecisionEngine | None = None,
        batch_size: int = 100,
        flush_interval_ms: float = 50.0,
    ):
        """
        Initialize batcher.

        Args:
            engine: FastDecisionEngine instance
            batch_size: Process when this many requests queued
            flush_interval_ms: Force flush after this time
        """
        self.engine = engine or FastDecisionEngine()
        self.batch_size = batch_size
        self.flush_interval_ms = flush_interval_ms

        # Pending requests
        self._pending: deque[DecisionRequest] = deque()
        self._results: dict[str, DecisionResult] = {}
        self._lock = threading.Lock()
        self._last_flush = time.perf_counter()

    def queue_decision(self, req: DecisionRequest):
        """Add decision request to queue."""
        with self._lock:
            self._pending.append(req)

    def get_result(self, request_id: str) -> DecisionResult | None:
        """Get result if available."""
        return self._results.get(request_id)

    def flush(self) -> int:
        """
        Process all pending requests.

        Returns number of decisions made.
        """
        with self._lock:
            if not self._pending:
                return 0

            requests = list(self._pending)
            self._pending.clear()

        results = self.engine.batch_decide(requests, parallel=True)

        with self._lock:
            for result in results:
                self._results[result.request_id] = result
            self._last_flush = time.perf_counter()

        return len(results)

    def maybe_flush(self) -> int:
        """
        Flush if batch is full or time elapsed.

        Returns number of decisions made.
        """
        with self._lock:
            should_flush = (
                len(self._pending) >= self.batch_size
                or (time.perf_counter() - self._last_flush) * 1000 >= self.flush_interval_ms
            )

        if should_flush:
            return self.flush()
        return 0


# =============================================================================
# Convenience Functions
# =============================================================================

# Global engine instance for convenience
_global_engine: FastDecisionEngine | None = None


def get_fast_engine() -> FastDecisionEngine:
    """Get or create global FastDecisionEngine instance."""
    global _global_engine
    if _global_engine is None:
        _global_engine = FastDecisionEngine()
    return _global_engine


def fast_decide(
    confidence: float,
    rsi: float = 50.0,
    macd: float = 0.0,
    risk_tolerance: float = 0.5,
    entry_aggression: float = 0.5,
    recent_win_rate: float = 0.5,
) -> bool:
    """
    Quick single decision.

    Returns True if should take trade, False if should skip.
    """
    engine = get_fast_engine()
    req = DecisionRequest(
        request_id="single",
        confidence=confidence,
        rsi=rsi,
        macd=macd,
        risk_tolerance=risk_tolerance,
        entry_aggression=entry_aggression,
        recent_win_rate=recent_win_rate,
    )

    if engine.is_available():
        result = engine._single_decide(req)
    else:
        result = engine.decide_heuristic(req)

    return result.should_trade


def benchmark_inference(n_requests: int = 100) -> dict:
    """
    Benchmark inference speed.

    Args:
        n_requests: Number of requests to make

    Returns:
        Benchmark results dict
    """
    import random

    engine = FastDecisionEngine()

    if not engine.is_available():
        return {"error": "vLLM server not available"}

    # Warmup
    engine.warmup()

    # Generate random requests
    requests = [
        DecisionRequest(
            request_id=f"bench_{i}",
            confidence=random.uniform(0.3, 0.8),
            rsi=random.uniform(20, 80),
            macd=random.uniform(-2, 2),
            risk_tolerance=random.uniform(0.3, 0.7),
            entry_aggression=random.uniform(0.3, 0.7),
            recent_win_rate=random.uniform(0.4, 0.6),
        )
        for i in range(n_requests)
    ]

    # Clear cache for fair benchmark
    engine.clear_cache()

    # Benchmark sequential
    start = time.perf_counter()
    sequential_results = engine.batch_decide(requests, parallel=False)
    sequential_time = time.perf_counter() - start

    # Clear cache
    engine.clear_cache()

    # Benchmark parallel
    start = time.perf_counter()
    parallel_results = engine.batch_decide(requests, parallel=True)
    parallel_time = time.perf_counter() - start

    # Benchmark with cache
    start = time.perf_counter()
    cached_results = engine.batch_decide(requests, parallel=True)
    cached_time = time.perf_counter() - start

    return {
        "n_requests": n_requests,
        "sequential": {
            "total_ms": sequential_time * 1000,
            "per_request_ms": (sequential_time * 1000) / n_requests,
        },
        "parallel": {
            "total_ms": parallel_time * 1000,
            "per_request_ms": (parallel_time * 1000) / n_requests,
        },
        "cached": {
            "total_ms": cached_time * 1000,
            "per_request_ms": (cached_time * 1000) / n_requests,
            "cache_hit_rate": engine.stats["cache_hit_rate"],
        },
        "speedup": {
            "parallel_vs_sequential": sequential_time / parallel_time if parallel_time > 0 else 0,
            "cached_vs_parallel": parallel_time / cached_time if cached_time > 0 else 0,
        },
    }
