"""
LLM Service for Fast_Swarm.

Provides async/sync LLM calls via:
- Conductor Router (default) — uses free cloud tokens via OpenAI-compatible API
- Ollama (fallback) — local GPU inference

Conductor picks the best free model for the task type automatically.
Set LLM_BACKEND=ollama to force local inference.
"""

import os

import httpx

# Backend selection: "conductor" (default) or "ollama"
LLM_BACKEND = os.getenv("LLM_BACKEND", "conductor")

# Conductor config (OpenAI-compatible API at port 8100)
CONDUCTOR_URL = os.getenv("CONDUCTOR_URL", "http://host.docker.internal:8100")
CONDUCTOR_KEY = os.getenv("CONDUCTOR_KEY", "sk-conductor-router-2026")

# Ollama config (fallback)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "90"))


def _call_conductor_sync(prompt: str) -> str:
    """Call Conductor Router (OpenAI-compatible) synchronously."""
    payload = {
        "model": "auto",  # Conductor picks best model
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    headers = {"Authorization": f"Bearer {CONDUCTOR_KEY}"}

    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        print(f"[LLMService] Calling Conductor ({CONDUCTOR_URL}) with {len(prompt)} char prompt...")
        response = client.post(f"{CONDUCTOR_URL}/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        model_used = result.get("model", "unknown")
        print(f"[LLMService] Conductor response: {len(content)} chars via {model_used}")
        return content


async def _call_conductor_async(prompt: str) -> str:
    """Call Conductor Router (OpenAI-compatible) asynchronously."""
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    headers = {"Authorization": f"Bearer {CONDUCTOR_KEY}"}

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        response = await client.post(f"{CONDUCTOR_URL}/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content


def _call_ollama_sync(prompt: str) -> str:
    """Call Ollama API synchronously."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_gpu": 99,
            "num_ctx": 2048,
            "num_predict": 500,
            "temperature": 0.1,
        },
    }

    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        print(f"[LLMService] Calling Ollama with {len(prompt)} char prompt...")
        response = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        llm_response = result.get("response", "")
        print(f"[LLMService] Got {len(llm_response)} char response from Ollama")
        return llm_response


async def _call_ollama_async(prompt: str) -> str:
    """Call Ollama API asynchronously."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_gpu": 99,
            "num_ctx": 512,
            "num_predict": 200,
            "temperature": 0.1,
        },
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "")


# =============================================================================
# Public API (same interface as before — drop-in replacement)
# =============================================================================


def ollama_call_sync(prompt: str) -> str:
    """
    Synchronous LLM call. Uses Conductor by default, falls back to Ollama.

    Used by genesis.py which expects a sync function.
    """
    try:
        if LLM_BACKEND == "conductor":
            return _call_conductor_sync(prompt)
    except Exception as e:
        print(f"[LLMService] Conductor failed ({e}), falling back to Ollama")

    try:
        return _call_ollama_sync(prompt)
    except httpx.ConnectError:
        raise RuntimeError("[LLMService] Neither Conductor nor Ollama available")
    except httpx.TimeoutException:
        raise RuntimeError(f"[LLMService] LLM timeout after {LLM_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"[LLMService] LLM HTTP error: {e.response.status_code}")


async def ollama_call_async(prompt: str) -> str:
    """
    Async LLM call. Uses Conductor by default, falls back to Ollama.
    """
    try:
        if LLM_BACKEND == "conductor":
            return await _call_conductor_async(prompt)
    except Exception as e:
        print(f"[LLMService] Conductor failed ({e}), falling back to Ollama")

    try:
        return await _call_ollama_async(prompt)
    except httpx.ConnectError:
        raise RuntimeError("[LLMService] Neither Conductor nor Ollama available")
    except httpx.TimeoutException:
        raise RuntimeError(f"[LLMService] LLM timeout after {LLM_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"[LLMService] LLM HTTP error: {e.response.status_code}")


async def check_ollama_available() -> bool:
    """Check if LLM backend is available."""
    try:
        if LLM_BACKEND == "conductor":
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{CONDUCTOR_URL}/health")
                return response.status_code == 200

        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                return OLLAMA_MODEL in model_names or any(OLLAMA_MODEL.split(":")[0] in name for name in model_names)
        return False
    except Exception:
        return False
