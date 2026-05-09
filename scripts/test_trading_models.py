#!/usr/bin/env python3
"""
Test trading models against real backtest trades.

Tests vLLM-compatible models for trading decision accuracy.
Uses trades from data/model_test_trades.json (extracted from backtest_trades_unified).
"""

import asyncio
import json
import re
import time
from pathlib import Path

import httpx

# Models to test (vLLM-compatible only - generative models)
VLLM_MODELS = [
    # Tier 1: General small instruction models
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
    "Qwen/Qwen2-0.5B-Instruct",
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "google/gemma-2-2b-it",
    "google/gemma-2b-it",
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "microsoft/Phi-3-mini-4k-instruct",
    # Tier 2: SmolLM family
    "HuggingFaceTB/SmolLM-135M-Instruct",
    "HuggingFaceTB/SmolLM-360M-Instruct",
    "HuggingFaceTB/SmolLM-1.7B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    # Tier 3: StableLM
    "stabilityai/stablelm-2-zephyr-1_6b",
    "stabilityai/stablelm-zephyr-3b",
    # Tier 4: Quantized 7B (AWQ) - require --quantization awq flag
    # "TheBloke/Mistral-7B-Instruct-v0.2-AWQ",
    # Tier 5: Trading-specific (verify they exist and work)
    # "RichardErkhov/KRX-Trader_-_qwen2.5-test-4bits",
    # "Caliban-17/Adaptive-Trader",
]

VLLM_URL = "http://localhost:8000"
SYSTEM_PROMPT = """You are a trading AI evaluating uncertain opportunities. Consider ALL factors holistically - indicators, confidence, agent personality. There are no fixed rules.

A high-risk agent might take a marginal setup. A conservative agent might skip a good one. RSI extremes can be reversals OR continuations. MACD divergences matter. Context matters.

Respond ONLY: {"decision": "TAKE" or "SKIP", "reasoning": "brief"}"""


def load_trades() -> list[dict]:
    """Load test trades from JSON file."""
    trades_path = Path(__file__).parent.parent / "data" / "model_test_trades.json"
    with open(trades_path) as f:
        return json.load(f)


def format_trade_prompt(trade: dict) -> str:
    """Format a trade into a prompt for the model."""
    ind = trade["indicators"]
    return f"""Trade opportunity for {trade["symbol"]}:
- Confidence: {trade["confidence"]:.1%}
- RSI(14): {ind.get("rsi_14", "N/A"):.1f}
- MACD Line: {ind.get("macd_line", "N/A"):.6f}
- MACD Signal: {ind.get("macd_signal", "N/A"):.6f}
- Stoch K: {ind.get("stoch_k", "N/A"):.1f}
- ADX(14): {ind.get("adx_14", "N/A"):.1f}
- ATR(14): {ind.get("atr_14", "N/A"):.6f}
- BB Upper: {ind.get("bb_upper", "N/A"):.4f}
- BB Lower: {ind.get("bb_lower", "N/A"):.4f}
- Supertrend Direction: {ind.get("supertrend_direction", "N/A")}
- Zone: {trade.get("zone", "N/A")}

Should you TAKE or SKIP this trade?"""


def parse_decision(response: str) -> str:
    """Extract TAKE/SKIP from model response."""
    # Look for "decision":"TAKE" or "decision":"SKIP" directly
    match = re.search(r'"decision"\s*:\s*"(TAKE|SKIP)"', response, re.I)
    if match:
        return match.group(1).upper()

    # Fallback: look for TAKE or SKIP anywhere
    if "TAKE" in response.upper():
        return "TAKE"
    return "SKIP"


async def test_single_trade(
    client: httpx.AsyncClient,
    trade: dict,
    model: str,
) -> tuple[str, float, str]:
    """Test a single trade and return (decision, latency, raw_response)."""
    prompt = format_trade_prompt(trade)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 150,
        "temperature": 0.1,
    }

    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        decision = parse_decision(content)
        latency = time.perf_counter() - start
        return decision, latency, content
    except Exception as e:
        print(f"    Error: {e}")
        return "ERROR", time.perf_counter() - start, str(e)


async def test_model_batch(
    trades: list[dict],
    model: str,
    concurrency: int = 16,
    show_reasoning: bool = True,
) -> dict:
    """Test all trades against a model with concurrent requests."""
    print(f"\n  Testing {len(trades)} trades (concurrency={concurrency})...")

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_test(trade: dict) -> tuple[dict, str, float, str]:
        async with semaphore:
            async with httpx.AsyncClient() as client:
                decision, latency, response = await test_single_trade(client, trade, model)
                return trade, decision, latency, response

    start = time.perf_counter()
    results = await asyncio.gather(*[bounded_test(t) for t in trades])
    total_time = time.perf_counter() - start

    # Calculate metrics
    correct = 0
    total = 0
    errors = 0
    latencies = []
    examples = {"correct_take": [], "correct_skip": [], "wrong_take": [], "wrong_skip": []}

    for trade, decision, latency, response in results:
        if decision == "ERROR":
            errors += 1
            continue

        total += 1
        latencies.append(latency)

        # Accuracy: TAKE for winners, SKIP for losers
        is_winner = trade["is_winner"]
        is_correct = (is_winner and decision == "TAKE") or (not is_winner and decision == "SKIP")
        if is_correct:
            correct += 1
            key = "correct_take" if decision == "TAKE" else "correct_skip"
        else:
            key = "wrong_take" if decision == "TAKE" else "wrong_skip"

        if len(examples[key]) < 3:  # Keep up to 3 examples of each type
            examples[key].append(
                {
                    "symbol": trade["symbol"],
                    "pnl": trade["pnl_pct"],
                    "is_winner": is_winner,
                    "decision": decision,
                    "response": response,
                    "rsi": trade["indicators"].get("rsi_14", 0),
                    "confidence": trade["confidence"],
                }
            )

    accuracy = correct / total if total > 0 else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    throughput = total / total_time if total_time > 0 else 0

    # Show reasoning examples
    if show_reasoning:
        print("\n  --- REASONING EXAMPLES ---")
        for category, label in [
            ("correct_take", "CORRECT TAKE (winner)"),
            ("correct_skip", "CORRECT SKIP (loser)"),
            ("wrong_take", "WRONG TAKE (was loser)"),
            ("wrong_skip", "WRONG SKIP (was winner)"),
        ]:
            if examples[category]:
                print(f"\n  [{label}]")
                for ex in examples[category][:2]:
                    print(
                        f"    {ex['symbol']} | PnL: {ex['pnl']:.1f}% | RSI: {ex['rsi']:.0f} | Conf: {ex['confidence']:.0%}"
                    )
                    print(f"    Response: {ex['response'][:200]}...")

    return {
        "accuracy": accuracy,
        "correct": correct,
        "total": total,
        "errors": errors,
        "avg_latency_ms": avg_latency * 1000,
        "throughput_per_sec": throughput,
        "total_time_sec": total_time,
        "examples": examples,
    }


async def check_vllm_running(model: str | None = None) -> tuple[bool, str]:
    """Check if vLLM is running and return current model."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    current_model = data["data"][0]["id"]
                    if model and current_model != model:
                        return False, f"Wrong model loaded: {current_model} (need {model})"
                    return True, current_model
            return False, "No models loaded"
    except Exception as e:
        return False, str(e)


async def main():
    """Run model evaluation."""
    print("=" * 60)
    print("Trading Model Evaluation")
    print("=" * 60)

    # Load trades
    trades = load_trades()
    winners = [t for t in trades if t["is_winner"]]
    losers = [t for t in trades if not t["is_winner"]]
    print(f"\nLoaded {len(trades)} trades: {len(winners)} winners, {len(losers)} losers")

    # Check vLLM
    running, current_model = await check_vllm_running()
    if not running:
        print(f"\n[X] vLLM not running: {current_model}")
        print("\nTo start vLLM with a model:")
        print(
            "  wsl -d Ubuntu -- bash -c 'cd ~/vllm && source venv/bin/activate && python -m vllm.entrypoints.openai.api_server --model MODEL_NAME --host 0.0.0.0 --port 8000'"
        )
        return

    print(f"\n[OK] vLLM running with model: {current_model}")

    # Test current model
    print(f"\n{'=' * 60}")
    print(f"Testing: {current_model}")
    print(f"{'=' * 60}")

    results = await test_model_batch(trades, current_model, concurrency=32)

    print("\n  Results:")
    print(f"    Accuracy:    {results['accuracy']:.1%} ({results['correct']}/{results['total']})")
    print(f"    Throughput:  {results['throughput_per_sec']:.1f} decisions/sec")
    print(f"    Avg latency: {results['avg_latency_ms']:.0f}ms")
    print(f"    Total time:  {results['total_time_sec']:.1f}s")
    if results["errors"] > 0:
        print(f"    Errors:      {results['errors']}")

    # Save results
    output_path = Path(__file__).parent.parent / "data" / "model_test_results.json"
    existing_results = {}
    if output_path.exists():
        with open(output_path) as f:
            existing_results = json.load(f)

    existing_results[current_model] = {
        **results,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(output_path, "w") as f:
        json.dump(existing_results, f, indent=2)

    print(f"\n  Results saved to: {output_path}")

    # Show comparison if multiple results
    if len(existing_results) > 1:
        print(f"\n{'=' * 60}")
        print("All Results:")
        print(f"{'=' * 60}")
        print(f"{'Model':<45} {'Accuracy':>10} {'Speed':>12}")
        print("-" * 70)
        for model_name, res in sorted(existing_results.items(), key=lambda x: -x[1].get("accuracy", 0)):
            acc = res.get("accuracy", 0)
            speed = res.get("throughput_per_sec", 0)
            print(f"{model_name:<45} {acc:>9.1%} {speed:>10.1f}/s")


if __name__ == "__main__":
    asyncio.run(main())
