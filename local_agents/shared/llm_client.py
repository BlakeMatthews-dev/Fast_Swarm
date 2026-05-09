"""
LLM Client for Local Agents.

Provides Ollama integration for AI zone decisions and other LLM tasks.
Supports configurable models and timeout handling.

Now supports integration with the new ML layer (ml/integration/trading_bridge.py)
for UnifiedTradingInference when using UNIFIED mode.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

from Fast_Swarm.local_agents.config import Config

# Try to import the new ML layer (optional)
try:
    import sys
    from pathlib import Path

    # Add local-utilities to path for ML imports
    utilities_path = str(Path(__file__).parent.parent.parent / "local-utilities")
    if utilities_path not in sys.path:
        sys.path.insert(0, utilities_path)
    from ml.integration.trading_bridge import UnifiedTradingInference

    HAS_ML_LAYER = True
except ImportError:
    HAS_ML_LAYER = False
    UnifiedTradingInference = None


# =============================================================================
# AI Zone Mode
# =============================================================================


class AIZoneMode(Enum):
    """Modes for handling AI_REFLECT zone decisions."""

    SKIP = "skip"  # Treat as SKIP (fast backtesting)
    HEURISTIC = "heuristic"  # Use trait-based heuristics (legacy V3 style)
    LLM = "llm"  # Real Ollama calls (slower, CPU-friendly)
    VLLM = "vllm"  # vLLM with prefix caching (fast, GPU-optimized)
    UNIFIED = "unified"  # Use new ML layer UnifiedTradingInference


@dataclass
class LLMResponse:
    """Response from LLM call."""

    success: bool
    content: str
    parsed: dict | None = None
    error: str | None = None
    latency_ms: int = 0
    model: str = ""


class OllamaClient:
    """
    Client for Ollama local LLM.

    Handles:
    - Connection to Ollama server
    - JSON response parsing
    - Timeout and retry logic
    - Model selection
    """

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = None,
        max_retries: int = None,
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL (default from Config).
            model: Model to use (default from Config).
            timeout: Request timeout in seconds.
            max_retries: Number of retries on failure.
        """
        self.base_url = base_url or Config.OLLAMA_URL
        self.model = model or Config.OLLAMA_MODEL
        self.timeout = timeout or Config.LLM_TIMEOUT_SECONDS
        self.max_retries = max_retries or Config.LLM_MAX_RETRIES

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate completion from Ollama.

        Args:
            prompt: User prompt.
            system: Optional system prompt.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens to generate.
            json_mode: If True, expect JSON response.

        Returns:
            LLMResponse with content and parsed JSON if applicable.
        """
        start_time = time.time()

        # Build request payload with GPU optimization
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_gpu": getattr(Config, "OLLAMA_NUM_GPU", 99),
                "num_ctx": getattr(Config, "OLLAMA_NUM_CTX", 512),
            },
        }

        if system:
            payload["system"] = system

        if json_mode:
            payload["format"] = "json"

        # Try with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode())
                    content = result.get("response", "")

                    latency_ms = int((time.time() - start_time) * 1000)

                    # Try to parse JSON if expected
                    parsed = None
                    if json_mode and content:
                        try:
                            parsed = json.loads(content)
                        except json.JSONDecodeError:
                            # Try to extract JSON from content
                            parsed = self._extract_json(content)

                    return LLMResponse(
                        success=True,
                        content=content,
                        parsed=parsed,
                        latency_ms=latency_ms,
                        model=self.model,
                    )

            except urllib.error.URLError as e:
                last_error = f"Connection error: {e.reason}"
            except urllib.error.HTTPError as e:
                last_error = f"HTTP error: {e.code} {e.reason}"
            except Exception as e:
                last_error = str(e)

            # Wait before retry
            if attempt < self.max_retries - 1:
                time.sleep(1 * (attempt + 1))

        latency_ms = int((time.time() - start_time) * 1000)
        return LLMResponse(
            success=False,
            content="",
            error=last_error,
            latency_ms=latency_ms,
            model=self.model,
        )

    def _extract_json(self, text: str) -> dict | None:
        """Try to extract JSON from text content."""
        # Look for JSON block
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


# =============================================================================
# AI Zone Decision Prompts
# =============================================================================

# Full system prompt (used with larger models)
AI_ZONE_SYSTEM_PROMPT = """You are a trading decision assistant for an autonomous trading agent.

Your job is to evaluate uncertain trading opportunities and decide whether to TAKE or SKIP the trade.

You will receive:
- Pattern confidence score (0-1)
- Current market indicators
- Agent's personality traits
- Recent context

Respond with a JSON object:
{
    "decision": "TAKE" or "SKIP",
    "reasoning": "Brief explanation (1-2 sentences)"
}

Guidelines:
- TAKE if the setup looks favorable despite uncertainty
- SKIP if risk/reward is unfavorable or conditions are unclear
- Consider the agent's risk tolerance when deciding
- Be concise in your reasoning
"""

# Minimal system prompt for fast models (under 512 context)
AI_ZONE_SYSTEM_PROMPT_MINIMAL = 'Trading AI. Reply JSON: {"decision":"TAKE"/"SKIP","reasoning":"..."}'


def build_ai_zone_prompt_minimal(
    confidence: float,
    indicators: dict[str, float],
    traits: dict[str, float],
) -> str:
    """
    Build minimal prompt for fast inference (~100 tokens).

    For use with small/fast models like agi-trader-kz50-quantum.
    """
    # Extract key indicators
    rsi = indicators.get("RSI_14", 50)
    macd = indicators.get("MACDh_12_26_9", 0)
    adx = indicators.get("ADX_14", 25)

    # Extract key traits
    risk = traits.get("risk_tolerance", 0.5)
    aggr = traits.get("entry_aggression", 0.5)

    return f'{{"conf":{confidence:.2f},"rsi":{rsi:.0f},"macd":{macd:.2f},"adx":{adx:.0f},"risk":{risk:.2f},"aggr":{aggr:.2f}}} TAKE or SKIP?'


def build_ai_zone_prompt(
    confidence: float,
    pattern_name: str,
    indicators: dict[str, float],
    traits: dict[str, float],
    recent_trades: list[dict] | None = None,
    minimal: bool = False,
) -> str:
    """
    Build prompt for AI zone decision.

    Args:
        confidence: Pattern confidence score.
        pattern_name: Name of the matched pattern.
        indicators: Current indicator values.
        traits: Agent personality traits.
        recent_trades: Optional recent trade history.
        minimal: If True, use minimal prompt for fast inference.

    Returns:
        Formatted prompt string.
    """
    if minimal:
        return build_ai_zone_prompt_minimal(confidence, indicators, traits)

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


# =============================================================================
# AI Zone Handler with LLM
# =============================================================================


class AIZoneHandler:
    """
    Handles AI zone decisions with optional LLM integration.

    Modes:
    - SKIP: Always skip (fast backtesting)
    - HEURISTIC: Use entry_aggression trait (legacy behavior)
    - LLM: Call Ollama for decision
    - UNIFIED: Use new ML layer UnifiedTradingInference
    """

    def __init__(
        self,
        mode: AIZoneMode = AIZoneMode.SKIP,
        client: OllamaClient | None = None,
        use_minimal_prompts: bool = True,
        ml_model_id: str | None = None,
        ml_ensemble_id: str | None = None,
    ):
        """
        Initialize AI zone handler.

        Args:
            mode: AIZoneMode enum value.
            client: Optional pre-configured OllamaClient.
            use_minimal_prompts: If True, use minimal prompts for faster inference.
            ml_model_id: Model ID for UNIFIED mode (e.g., "qwen-trading").
            ml_ensemble_id: Ensemble ID for UNIFIED mode (e.g., "fast").
        """
        # Accept both string and enum
        if isinstance(mode, str):
            mode = AIZoneMode(mode.lower())
        self.mode = mode
        self.client = client or OllamaClient()
        self.use_minimal_prompts = use_minimal_prompts

        # ML layer inference (for UNIFIED mode)
        self._ml_inference = None
        if mode == AIZoneMode.UNIFIED and HAS_ML_LAYER:
            try:
                self._ml_inference = UnifiedTradingInference(
                    model_id=ml_model_id,
                    ensemble_id=ml_ensemble_id,
                )
            except Exception as e:
                print(f"[AIZoneHandler] Could not initialize ML layer: {e}")

        # Track decisions for metrics
        self._decisions = []
        self._warmed_up = False

    def warmup(self) -> bool:
        """
        Warm up the LLM by making a test call.

        This loads the model into GPU memory for faster subsequent calls.
        Returns True if warmup successful.
        """
        if self._warmed_up:
            return True

        if self.mode not in (AIZoneMode.LLM, AIZoneMode.VLLM, AIZoneMode.UNIFIED):
            self._warmed_up = True
            return True

        # UNIFIED mode - use ML layer warmup
        if self.mode == AIZoneMode.UNIFIED:
            if self._ml_inference:
                try:
                    latency = self._ml_inference.warmup()
                    self._warmed_up = True
                    print(f"[AIZoneHandler] ML layer warmed up in {latency:.1f}ms")
                    return True
                except Exception as e:
                    print(f"[AIZoneHandler] ML warmup failed: {e}")
                    return False
            return False

        if not self.client.is_available():
            return False

        # Make a test call to load the model
        response = self.client.generate(
            prompt='{"test":true} TAKE or SKIP?',
            max_tokens=10,
            json_mode=False,
        )

        if response.success:
            self._warmed_up = True
            print(f"[AIZoneHandler] Warmed up in {response.latency_ms}ms")

        return response.success

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
        if self.mode == AIZoneMode.SKIP:
            return False, "AI zone treated as skip", False

        elif self.mode == AIZoneMode.HEURISTIC:
            # Legacy behavior: use entry_aggression
            entry_agg = traits.get("entry_aggression", 0.5)
            should_trade = entry_agg >= 0.5
            reasoning = f"Heuristic: entry_aggression={entry_agg:.2f}"
            return should_trade, reasoning, False

        elif self.mode == AIZoneMode.LLM:
            return self._decide_with_llm(confidence, pattern_name, indicators, traits, recent_trades)

        elif self.mode == AIZoneMode.UNIFIED:
            return self._decide_with_ml_layer(confidence, pattern_name, indicators, traits)

        return False, f"Unknown mode: {self.mode}", False

    def _decide_with_ml_layer(
        self,
        confidence: float,
        pattern_name: str,
        indicators: dict[str, float],
        traits: dict[str, float],
    ) -> tuple[bool, str, bool]:
        """
        Make decision using new ML layer UnifiedTradingInference.

        This provides access to multiple models, ensembles, and better
        abstraction for trading decisions.
        """
        if not self._ml_inference:
            # Fall back to heuristic if ML layer not available
            entry_agg = traits.get("entry_aggression", 0.5)
            return entry_agg >= 0.5, "ML layer unavailable, used heuristic", False

        try:
            # Extract price from indicators
            price = indicators.get("close", indicators.get("price", 0))

            # Calculate 24h change if available
            change_24h = indicators.get("change_24h", 0)

            # Build MACD description
            macd_val = indicators.get("MACDh_12_26_9", indicators.get("macd", 0))
            if macd_val > 0.5:
                macd_desc = "Strong bullish"
            elif macd_val > 0:
                macd_desc = "Bullish"
            elif macd_val > -0.5:
                macd_desc = "Bearish"
            else:
                macd_desc = "Strong bearish"

            # Get trading decision
            decision = self._ml_inference.get_decision(
                symbol=indicators.get("asset", "BTC"),
                price=price,
                change_24h=change_24h,
                rsi=indicators.get("RSI_14", 50),
                macd=macd_desc,
                signal=f"Pattern: {pattern_name} (conf={confidence:.2f})",
                volume_ratio=indicators.get("volume_ratio", 1.0),
                funding_rate=indicators.get("funding_rate", 0.0),
            )

            # Track decision
            self._decisions.append(
                {
                    "confidence": confidence,
                    "pattern": pattern_name,
                    "decision": decision.action,
                    "latency_ms": decision.latency_ms,
                    "model": decision.model,
                }
            )

            # Convert BUY to TAKE, SELL/HOLD to SKIP
            should_trade = decision.action == "BUY"
            reasoning = f"ML: {decision.action} ({decision.confidence}%) via {decision.model}"

            return should_trade, reasoning, True

        except Exception as e:
            # Fall back to heuristic on error
            entry_agg = traits.get("entry_aggression", 0.5)
            return entry_agg >= 0.5, f"ML error: {e}", False

    def _decide_with_llm(
        self,
        confidence: float,
        pattern_name: str,
        indicators: dict[str, float],
        traits: dict[str, float],
        recent_trades: list[dict] | None,
    ) -> tuple[bool, str, bool]:
        """Make decision using LLM."""
        # Check if Ollama is available
        if not self.client.is_available():
            # Fall back to heuristic
            entry_agg = traits.get("entry_aggression", 0.5)
            return entry_agg >= 0.5, "LLM unavailable, used heuristic", False

        # Build prompt (minimal for speed)
        prompt = build_ai_zone_prompt(
            confidence=confidence,
            pattern_name=pattern_name,
            indicators=indicators,
            traits=traits,
            recent_trades=recent_trades,
            minimal=self.use_minimal_prompts,
        )

        # Use minimal system prompt for fast models
        system = AI_ZONE_SYSTEM_PROMPT_MINIMAL if self.use_minimal_prompts else AI_ZONE_SYSTEM_PROMPT
        max_tokens = 50 if self.use_minimal_prompts else 150

        # Call LLM
        response = self.client.generate(
            prompt=prompt,
            system=system,
            temperature=0.1,  # Very low for consistent decisions
            max_tokens=max_tokens,
            json_mode=True,
        )

        if not response.success:
            # Fall back to heuristic on error
            entry_agg = traits.get("entry_aggression", 0.5)
            return entry_agg >= 0.5, f"LLM error: {response.error}", False

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
                }
            )

            return should_trade, reasoning, True

        # Couldn't parse response, fall back
        entry_agg = traits.get("entry_aggression", 0.5)
        return entry_agg >= 0.5, "Could not parse LLM response", False

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


# =============================================================================
# Convenience Functions
# =============================================================================


def call_ollama(prompt: str, system: str | None = None) -> str:
    """
    Simple function to call Ollama.

    For use with llm_call parameter in spawn_agent, etc.

    Args:
        prompt: User prompt.
        system: Optional system prompt.

    Returns:
        Response content string.
    """
    client = OllamaClient()
    response = client.generate(prompt=prompt, system=system)
    return response.content if response.success else ""


def check_ollama_available() -> bool:
    """Check if Ollama server is running."""
    client = OllamaClient()
    return client.is_available()
