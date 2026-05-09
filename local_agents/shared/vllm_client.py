"""
vLLM Client for Local Agents.

Fast inference with prefix caching for AI zone decisions.
Optimized for models that fit in VRAM (8GB for RTX 3070, 48GB for dual P40s).

Model recommendations by VRAM:
- 8GB (3070): Qwen2.5-7B-Instruct, Phi-3-mini-4k-instruct
- 24GB (P40): Qwen2.5-14B-Instruct, DeepSeek-V2-Lite
- 48GB (2xP40): Qwen2.5-32B-Instruct, Mixtral-8x7B

Usage:
    client = VLLMClient()  # Auto-starts vLLM server if not running
    response = client.generate(prompt, system="...")
"""

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# =============================================================================
# vLLM Server Configuration (from Config)
# =============================================================================

# Get settings from Config with fallbacks
try:
    from Fast_Swarm.local_agents.config import Config

    DEFAULT_MODEL = getattr(Config, "VLLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    VLLM_URL = getattr(Config, "VLLM_URL", "http://localhost:8000")
    ENABLE_PREFIX_CACHING = getattr(Config, "VLLM_ENABLE_PREFIX_CACHING", True)
    MAX_MODEL_LEN = getattr(Config, "VLLM_MAX_MODEL_LEN", 1024)
    GPU_MEMORY_UTILIZATION = getattr(Config, "VLLM_GPU_MEMORY_UTILIZATION", 0.80)
except ImportError:
    DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
    VLLM_URL = "http://localhost:8000"
    ENABLE_PREFIX_CACHING = True
    MAX_MODEL_LEN = 1024
    GPU_MEMORY_UTILIZATION = 0.80

# Parse host and port from URL
from urllib.parse import urlparse

_parsed = urlparse(VLLM_URL)
VLLM_HOST = _parsed.hostname or "0.0.0.0"
VLLM_PORT = _parsed.port or 8000


@dataclass
class VLLMResponse:
    """Response from vLLM call."""

    success: bool
    content: str
    parsed: dict | None = None
    error: str | None = None
    latency_ms: int = 0
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # Tokens served from prefix cache


class VLLMClient:
    """
    Client for vLLM local inference server.

    Features:
    - Prefix caching for repeated prompt prefixes
    - Auto-start vLLM server if not running
    - JSON mode for structured responses
    - Batch inference support
    """

    def __init__(
        self,
        base_url: str = VLLM_URL,
        model: str = DEFAULT_MODEL,
        auto_start: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize vLLM client.

        Args:
            base_url: vLLM server URL.
            model: Model to use (must be loaded in vLLM).
            auto_start: If True, start vLLM server if not running.
            timeout: Request timeout in seconds.
            max_retries: Number of retries on failure.
        """
        self.base_url = base_url
        self.model = model
        self.auto_start = auto_start
        self.timeout = timeout
        self.max_retries = max_retries

        # Prefix cache tracking
        self._prefix_hashes = {}  # hash -> prompt prefix

    def is_available(self) -> bool:
        """Check if vLLM server is running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """List available models."""
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/models")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    def start_server(self, gpu_memory_utilization: float = 0.90) -> bool:
        """
        Start vLLM server if not running.

        Args:
            gpu_memory_utilization: Fraction of GPU memory to use (0.9 = 90%).

        Returns:
            True if server started or already running.
        """
        if self.is_available():
            return True

        print(f"[vLLM] Starting server with model: {self.model}")

        # Build command
        cmd = [
            "python",
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            self.model,
            "--host",
            VLLM_HOST,
            "--port",
            str(VLLM_PORT),
            "--gpu-memory-utilization",
            str(gpu_memory_utilization),
            "--max-model-len",
            str(MAX_MODEL_LEN),
        ]

        if ENABLE_PREFIX_CACHING:
            cmd.append("--enable-prefix-caching")

        # Start server in background
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait for server to start
            for _ in range(30):  # Wait up to 30 seconds
                time.sleep(1)
                if self.is_available():
                    print("[vLLM] Server started successfully")
                    return True

            print("[vLLM] Server failed to start within timeout")
            return False

        except Exception as e:
            print(f"[vLLM] Failed to start server: {e}")
            return False

    def _compute_prefix_hash(self, text: str) -> str:
        """Compute hash for prefix caching."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_mode: bool = False,
        prefix: str | None = None,
    ) -> VLLMResponse:
        """
        Generate completion from vLLM.

        Args:
            prompt: User prompt.
            system: Optional system prompt.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens to generate.
            json_mode: If True, expect JSON response.
            prefix: Optional prefix for caching (reused across calls).

        Returns:
            VLLMResponse with content and parsed JSON if applicable.
        """
        start_time = time.time()

        # Check server
        if not self.is_available():
            if self.auto_start:
                if not self.start_server():
                    return VLLMResponse(
                        success=False,
                        content="",
                        error="vLLM server not available and failed to start",
                        latency_ms=int((time.time() - start_time) * 1000),
                        model=self.model,
                    )
            else:
                return VLLMResponse(
                    success=False,
                    content="",
                    error="vLLM server not available",
                    latency_ms=int((time.time() - start_time) * 1000),
                    model=self.model,
                )

        # Build messages for chat API
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        # Combine prefix with prompt if provided (for caching)
        full_prompt = f"{prefix}\n\n{prompt}" if prefix else prompt
        messages.append({"role": "user", "content": full_prompt})

        # Build request payload (OpenAI-compatible)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # Try with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode())

                    # Extract response
                    choice = result.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")

                    # Get usage stats
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)

                    latency_ms = int((time.time() - start_time) * 1000)

                    # Try to parse JSON if expected
                    parsed = None
                    if json_mode and content:
                        try:
                            parsed = json.loads(content)
                        except json.JSONDecodeError:
                            parsed = self._extract_json(content)

                    return VLLMResponse(
                        success=True,
                        content=content,
                        parsed=parsed,
                        latency_ms=latency_ms,
                        model=self.model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )

            except urllib.error.URLError as e:
                last_error = f"Connection error: {e.reason}"
            except urllib.error.HTTPError as e:
                last_error = f"HTTP error: {e.code} {e.reason}"
            except Exception as e:
                last_error = str(e)

            # Wait before retry
            if attempt < self.max_retries - 1:
                time.sleep(0.5 * (attempt + 1))

        latency_ms = int((time.time() - start_time) * 1000)
        return VLLMResponse(
            success=False,
            content="",
            error=last_error,
            latency_ms=latency_ms,
            model=self.model,
        )

    def _extract_json(self, text: str) -> dict | None:
        """Try to extract JSON from text content."""
        import re

        # Try to find JSON in markdown code block
        json_match = re.search(r"```json?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def batch_generate(
        self,
        prompts: list[str],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_mode: bool = False,
        shared_prefix: str | None = None,
    ) -> list[VLLMResponse]:
        """
        Generate completions for multiple prompts.

        Uses shared prefix for better cache efficiency.

        Args:
            prompts: List of prompts.
            system: Shared system prompt.
            temperature: Sampling temperature.
            max_tokens: Max tokens per response.
            json_mode: Expect JSON responses.
            shared_prefix: Common prefix for all prompts (cached).

        Returns:
            List of VLLMResponse objects.
        """
        responses = []
        for prompt in prompts:
            response = self.generate(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                prefix=shared_prefix,
            )
            responses.append(response)
        return responses


# =============================================================================
# AI Zone Handler with vLLM
# =============================================================================

AI_ZONE_SYSTEM_PROMPT = """You are a trading AI evaluating uncertain opportunities. Consider ALL factors holistically - indicators, confidence, agent personality. There are no fixed rules.

A high-risk agent might take a marginal setup. A conservative agent might skip a good one. RSI extremes can be reversals OR continuations. MACD divergences matter. Context matters.

Respond ONLY: {"decision": "TAKE" or "SKIP", "reasoning": "brief"}"""


def build_ai_zone_prompt(
    confidence: float,
    pattern_name: str,
    indicators: dict[str, float],
    traits: dict[str, float],
    recent_trades: list[dict] | None = None,
) -> str:
    """
    Build prompt for AI zone decision.

    Args:
        confidence: Pattern confidence score.
        pattern_name: Name of the matched pattern.
        indicators: Current indicator values.
        traits: Agent personality traits.
        recent_trades: Optional recent trade history.

    Returns:
        Formatted prompt string.
    """
    # Format key indicators
    key_indicators = ["RSI_14", "MACDh_12_26_9", "ADX_14", "ATRr_14", "BBP_20_2.0"]
    indicator_lines = []
    for ind in key_indicators:
        if ind in indicators:
            val = indicators[ind]
            if val is not None:
                indicator_lines.append(f"  {ind}: {val:.2f}")

    # Format traits
    key_traits = ["risk_tolerance", "entry_aggression", "volatility_seeking"]
    trait_lines = []
    for trait in key_traits:
        if trait in traits:
            trait_lines.append(f"  {trait}: {traits[trait]:.2f}")

    # Build prompt
    prompt = f"""## Trade Opportunity

Pattern: {pattern_name}
Confidence: {confidence:.2f} (in AI consultation zone)

## Current Indicators
{chr(10).join(indicator_lines) if indicator_lines else "  No indicators available"}

## Agent Personality
{chr(10).join(trait_lines) if trait_lines else "  Default traits"}

"""

    # Add recent trade context if available
    if recent_trades and len(recent_trades) > 0:
        wins = sum(1 for t in recent_trades[-10:] if t.get("pnl_pct", 0) > 0)
        total = len(recent_trades[-10:])
        recent_wr = wins / total if total > 0 else 0.5
        prompt += f"""## Recent Performance
  Last 10 trades: {wins}/{total} wins ({recent_wr * 100:.0f}% win rate)
"""

    prompt += """
Should the agent TAKE or SKIP this trade? Respond with JSON."""

    return prompt


class VLLMAIZoneHandler:
    """
    Handles AI zone decisions with vLLM for fast inference.

    Optimized for batching and prefix caching.
    """

    def __init__(
        self,
        client: VLLMClient | None = None,
        fallback_to_heuristic: bool = True,
    ):
        """
        Initialize AI zone handler.

        Args:
            client: Optional pre-configured VLLMClient.
            fallback_to_heuristic: If True, use heuristics when LLM unavailable.
        """
        self.client = client or VLLMClient()
        self.fallback_to_heuristic = fallback_to_heuristic

        # Track decisions for metrics
        self._decisions = []
        self._total_tokens = 0

    def decide(
        self,
        confidence: float,
        pattern_name: str,
        indicators: dict[str, float],
        traits: dict[str, float],
        recent_trades: list[dict] | None = None,
    ) -> tuple[bool, str, bool]:
        """
        Make AI zone decision.

        Args:
            confidence: Pattern confidence score.
            pattern_name: Matched pattern name.
            indicators: Current indicator values.
            traits: Agent personality traits.
            recent_trades: Recent trade history.

        Returns:
            Tuple of (should_trade, reasoning, ai_consulted).
        """
        # Check if vLLM is available
        if not self.client.is_available():
            if self.fallback_to_heuristic:
                entry_agg = traits.get("entry_aggression", 0.5)
                return entry_agg >= 0.5, "vLLM unavailable, used heuristic", False
            return False, "vLLM unavailable", False

        # Build prompt
        prompt = build_ai_zone_prompt(
            confidence=confidence,
            pattern_name=pattern_name,
            indicators=indicators,
            traits=traits,
            recent_trades=recent_trades,
        )

        # Call vLLM
        response = self.client.generate(
            prompt=prompt,
            system=AI_ZONE_SYSTEM_PROMPT,
            temperature=0.3,  # Lower for more consistent decisions
            max_tokens=150,
            json_mode=True,
        )

        if not response.success:
            if self.fallback_to_heuristic:
                entry_agg = traits.get("entry_aggression", 0.5)
                return entry_agg >= 0.5, f"vLLM error: {response.error}", False
            return False, f"vLLM error: {response.error}", False

        # Parse response
        if response.parsed:
            decision = response.parsed.get("decision", "").upper()
            reasoning = response.parsed.get("reasoning", "No reasoning provided")
            should_trade = decision == "TAKE"

            # Track decision
            self._decisions.append(
                {
                    "confidence": confidence,
                    "pattern": pattern_name,
                    "decision": decision,
                    "latency_ms": response.latency_ms,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                }
            )
            self._total_tokens += response.prompt_tokens + response.completion_tokens

            return should_trade, reasoning, True

        # Couldn't parse response, fall back
        if self.fallback_to_heuristic:
            entry_agg = traits.get("entry_aggression", 0.5)
            return entry_agg >= 0.5, "Could not parse vLLM response", False
        return False, "Could not parse vLLM response", False

    @property
    def decision_count(self) -> int:
        """Number of LLM decisions made."""
        return len(self._decisions)

    @property
    def avg_latency_ms(self) -> float:
        """Average LLM latency in milliseconds."""
        if not self._decisions:
            return 0
        return sum(d["latency_ms"] for d in self._decisions) / len(self._decisions)

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self._total_tokens


# =============================================================================
# Convenience Functions
# =============================================================================


def check_vllm_available() -> bool:
    """Check if vLLM server is running."""
    client = VLLMClient(auto_start=False)
    return client.is_available()


def start_vllm_server(model: str = DEFAULT_MODEL) -> bool:
    """Start vLLM server with specified model."""
    client = VLLMClient(model=model)
    return client.start_server()


# =============================================================================
# Async Client with Sliding Window (Fire-and-Forget Batching)
# =============================================================================


class AsyncVLLMClient:
    """
    Async vLLM client with sliding window concurrency control.

    Optimized for high-throughput backtesting:
    - Fire-and-forget: requests sent as fast as possible
    - Semaphore limits max in-flight requests (sliding window)
    - vLLM batches them internally on GPU
    - ~100 decisions/sec on RTX 3070

    Usage:
        client = AsyncVLLMClient(max_concurrent=64)
        results = await client.batch_decide(decisions)
    """

    def __init__(
        self,
        base_url: str = VLLM_URL,
        model: str = "Qwen/Qwen2.5-0.5B-Instruct",
        max_concurrent: int = 64,
        timeout: int = 60,
    ):
        self.base_url = base_url
        self.model = model
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._semaphore = None  # Created lazily in async context
        self._session = None

    async def _get_semaphore(self):
        """Get or create semaphore (must be in async context)."""
        if self._semaphore is None:
            import asyncio

            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            import aiohttp

            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _call_vllm(
        self,
        prompt: str,
        system: str,
        request_id: str = "",
    ) -> dict:
        """Single async vLLM call with semaphore control."""
        import time

        semaphore = await self._get_semaphore()
        session = await self._get_session()

        async with semaphore:  # Sliding window - auto-releases when done
            start = time.time()
            try:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 50,
                        "temperature": 0.1,
                    },
                ) as resp:
                    result = await resp.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # Parse decision (handle truncated JSON)
                    decision = "SKIP"
                    import re

                    # Look for "decision":"TAKE" or "decision":"SKIP" directly
                    # (works even if JSON is truncated)
                    match = re.search(r'"decision"\s*:\s*"(TAKE|SKIP)"', content, re.I)
                    if match:
                        decision = match.group(1).upper()

                    return {
                        "request_id": request_id,
                        "success": True,
                        "decision": decision,
                        "should_trade": decision == "TAKE",
                        "latency_ms": int((time.time() - start) * 1000),
                        "content": content,
                    }
            except Exception as e:
                return {
                    "request_id": request_id,
                    "success": False,
                    "decision": "SKIP",
                    "should_trade": False,
                    "latency_ms": int((time.time() - start) * 1000),
                    "error": str(e),
                }

    async def batch_decide(
        self,
        decisions: list[dict],
        system_prompt: str = AI_ZONE_SYSTEM_PROMPT,
    ) -> list[dict]:
        """
        Fire-and-forget batch AI decisions with sliding window.

        Args:
            decisions: List of dicts with keys:
                - request_id: Unique identifier
                - prompt: The decision prompt
            system_prompt: System prompt for all calls

        Returns:
            List of result dicts with:
                - request_id: Matching input ID
                - success: bool
                - should_trade: bool
                - decision: "TAKE" or "SKIP"
                - latency_ms: int
        """
        import asyncio

        tasks = [
            self._call_vllm(
                prompt=d["prompt"],
                system=system_prompt,
                request_id=d.get("request_id", str(i)),
            )
            for i, d in enumerate(decisions)
        ]

        # Fire all at once - semaphore controls max in-flight
        results = await asyncio.gather(*tasks)
        return results

    async def decide_single(
        self,
        confidence: float,
        pattern_name: str,
        indicators: dict,
        traits: dict,
        recent_trades: list = None,
        request_id: str = "",
    ) -> dict:
        """Single async decision (for live trading)."""
        prompt = build_ai_zone_prompt(
            confidence=confidence,
            pattern_name=pattern_name,
            indicators=indicators,
            traits=traits,
            recent_trades=recent_trades,
        )
        return await self._call_vllm(
            prompt=prompt,
            system=AI_ZONE_SYSTEM_PROMPT,
            request_id=request_id,
        )


# Global async client instance (reusable across backtests)
_async_client: AsyncVLLMClient | None = None


def get_async_vllm_client(max_concurrent: int = 64) -> AsyncVLLMClient:
    """Get or create global async vLLM client."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncVLLMClient(max_concurrent=max_concurrent)
    return _async_client
