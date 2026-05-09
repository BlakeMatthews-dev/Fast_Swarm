"""
LLM Service for Fast_Swarm.

Provides async LLM calls via Ollama for:
- Agent pattern selection (birth_selection.j2)
- Philosophy generation (philosophy.j2)
- AI zone decisions (ai_zone_decision.j2)

Uses the centralized Ollama configuration from Fast_Swarm.local_agents.config.
"""

import httpx

# Ollama config (mirrors local_agents/config.py)
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "koshtenco/agi-trader-kz50-quantum:latest"
OLLAMA_TIMEOUT = 30  # seconds


async def ollama_call_async(prompt: str) -> str:
    """
    Call Ollama API asynchronously.

    Args:
        prompt: The prompt to send to the LLM.

    Returns:
        The LLM response text.

    Raises:
        RuntimeError: If Ollama is unavailable or times out.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_gpu": 99,  # Use all GPU layers
            "num_ctx": 512,  # Minimal context for speed
            "num_predict": 200,  # Allow slightly longer responses for JSON
            "temperature": 0.1,  # Consistent decisions
        },
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
    except httpx.TimeoutException:
        raise RuntimeError(f"[LLMService] Ollama timeout after {OLLAMA_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"[LLMService] Ollama HTTP error: {e.response.status_code}")
    except httpx.ConnectError:
        raise RuntimeError("[LLMService] Ollama not available at localhost:11434")


def ollama_call_sync(prompt: str) -> str:
    """
    Synchronous Ollama call using httpx sync client.

    Used by genesis.py which expects a sync function.
    Uses synchronous httpx to avoid asyncio issues in thread pools.

    Args:
        prompt: The prompt to send to the LLM.

    Returns:
        The LLM response text.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_gpu": 99,
            "num_ctx": 2048,  # Larger context for pattern list
            "num_predict": 500,  # Allow longer JSON responses
            "temperature": 0.1,
        },
    }

    try:
        # Use synchronous httpx client - no asyncio issues!
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            print(f"[LLMService] Calling Ollama with {len(prompt)} char prompt...")
            response = client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            llm_response = result.get("response", "")
            print(f"[LLMService] Got {len(llm_response)} char response from Ollama")
            return llm_response
    except httpx.TimeoutException:
        print(f"[LLMService] ERROR: Ollama timeout after {OLLAMA_TIMEOUT}s")
        raise RuntimeError(f"Ollama timeout after {OLLAMA_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        print(f"[LLMService] ERROR: Ollama HTTP error: {e.response.status_code}")
        raise RuntimeError(f"Ollama HTTP error: {e.response.status_code}")
    except httpx.ConnectError:
        print("[LLMService] ERROR: Ollama not available at localhost:11434")
        raise RuntimeError("Ollama not available at localhost:11434")


async def check_ollama_available() -> bool:
    """Check if Ollama is running and the model is loaded."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                return OLLAMA_MODEL in model_names or any(OLLAMA_MODEL.split(":")[0] in name for name in model_names)
        return False
    except Exception:
        return False
