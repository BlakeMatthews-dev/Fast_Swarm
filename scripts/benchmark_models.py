#!/usr/bin/env python3
"""
Benchmark AI Models for Trading Decisions.

Runs each model through the same canonical period data and compares:
- Accuracy (buy oversold, skip overbought)
- MFE capture
- Speed (inferences/sec)
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2

# Import from our evaluation module
from ai_entry_exit_prompts import ENTRY_SYSTEM_PROMPT, format_entry_prompt
from evaluate_ai_mfe_capture import (
    calculate_mfe_mae,
    get_forward_candles,
    load_canonical_periods_from_db,
)

VLLM_URL = "http://localhost:8000"

# Models to benchmark (smallest to largest for quick iteration)
MODELS = [
    # Tier 1: Tiny (< 1B) - fastest
    "HuggingFaceTB/SmolLM-360M-Instruct",
    "Qwen/Qwen2.5-0.5B-Instruct",
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    # Tier 2: Small (1-2B) - good balance
    "Qwen/Qwen2.5-1.5B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "stabilityai/stablelm-2-zephyr-1_6b",
    # Tier 3: Medium (2-3B) - better reasoning
    "Qwen/Qwen2.5-3B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "google/gemma-2-2b-it",
    "stabilityai/stablelm-zephyr-3b",
    # Tier 4: Larger (3B+) - best quality
    "microsoft/Phi-3-mini-4k-instruct",
]


async def test_model_quick(model: str, candles: list, conn, max_samples: int = 50) -> dict:
    """Quick test of a model on sample candles."""
    results = {"buys": [], "skips": [], "errors": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.perf_counter()

        for i, candle in enumerate(candles[:max_samples]):
            try:
                # Get MFE for this entry
                forward = get_forward_candles(
                    conn,
                    symbol=candle.get("symbol", "BTC"),
                    timeframe=candle.get("timeframe", "1h"),
                    start_time=str(candle.get("time", "")),
                    num_bars=49,
                )
                if len(forward) < 10:
                    continue

                entry_price = float(candle.get("close", 0))
                mfe, mae, _ = calculate_mfe_mae(forward[1:], entry_price)

                # Get AI decision
                prompt = format_entry_prompt([], candle, "test")
                resp = await client.post(
                    f"{VLLM_URL}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": ENTRY_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 150,
                        "temperature": 0.1,
                    },
                )

                content = resp.json()["choices"][0]["message"]["content"]

                # Parse choice
                import re

                match = re.search(r'"choice"\s*:\s*([+-]?\d)', content)
                choice = int(match.group(1)) if match else 0

                rsi = float(candle.get("rsi_14") or 50)
                stoch = float(candle.get("stoch_k") or 50)

                result = {
                    "rsi": rsi,
                    "stoch": stoch,
                    "mfe": mfe,
                    "mae": mae,
                    "choice": choice,
                }

                if choice >= 1:
                    results["buys"].append(result)
                else:
                    results["skips"].append(result)

            except Exception:
                results["errors"] += 1

        elapsed = time.perf_counter() - start
        results["elapsed"] = elapsed
        results["rate"] = (len(results["buys"]) + len(results["skips"])) / elapsed if elapsed > 0 else 0

    return results


def analyze_results(results: dict, model: str) -> dict:
    """Analyze model performance."""
    buys = results["buys"]
    skips = results["skips"]

    metrics = {
        "model": model,
        "total": len(buys) + len(skips),
        "errors": results["errors"],
        "buy_count": len(buys),
        "skip_count": len(skips),
        "buy_rate": len(buys) / (len(buys) + len(skips)) if (buys or skips) else 0,
        "speed": results["rate"],
        "elapsed": results["elapsed"],
    }

    if buys:
        metrics["buy_avg_mfe"] = sum(b["mfe"] for b in buys) / len(buys)
        metrics["buy_avg_mae"] = sum(b["mae"] for b in buys) / len(buys)
        # Correct buys: oversold (stoch < 20 or rsi < 30)
        correct_buys = [b for b in buys if b["stoch"] < 20 or b["rsi"] < 30]
        metrics["buy_precision"] = len(correct_buys) / len(buys) if buys else 0

    if skips:
        metrics["skip_avg_mfe"] = sum(s["mfe"] for s in skips) / len(skips)
        # Correct skips: NOT oversold
        correct_skips = [s for s in skips if s["stoch"] >= 20 and s["rsi"] >= 30]
        metrics["skip_precision"] = len(correct_skips) / len(skips) if skips else 0

    return metrics


async def wait_for_vllm(timeout: int = 120) -> bool:
    """Wait for vLLM to be ready."""
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
                if resp.status_code == 200:
                    return True
            except:
                pass
            await asyncio.sleep(2)
    return False


async def benchmark_current_model(conn, sample_candles: list) -> dict:
    """Benchmark whatever model is currently loaded in vLLM."""
    # Check what model is loaded
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            model = resp.json()["data"][0]["id"]
        except Exception as e:
            print(f"[X] vLLM not running: {e}")
            return None

    print(f"\n{'=' * 60}")
    print(f"Testing: {model}")
    print(f"{'=' * 60}")

    results = await test_model_quick(model, sample_candles, conn, max_samples=100)
    metrics = analyze_results(results, model)

    print(f"  Samples: {metrics['total']} | Errors: {metrics['errors']}")
    print(f"  Speed: {metrics['speed']:.1f}/sec ({metrics['elapsed']:.1f}s)")
    print(f"  Buys: {metrics['buy_count']} ({metrics['buy_rate']:.1%})")

    if metrics.get("buy_avg_mfe"):
        print(f"  Buy Avg MFE: {metrics['buy_avg_mfe']:+.2f}%")
        print(f"  Buy Precision: {metrics.get('buy_precision', 0):.1%}")

    if metrics.get("skip_avg_mfe"):
        print(f"  Skip Avg MFE (missed): {metrics['skip_avg_mfe']:+.2f}%")

    return metrics


async def main():
    """Run benchmark on current vLLM model."""
    print("=" * 60)
    print("AI Model Benchmark")
    print("=" * 60)

    # Connect to DB
    conn = psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")

    # Load sample data from diverse periods
    print("Loading canonical periods...")
    periods = load_canonical_periods_from_db(conn)

    # Take samples from multiple regimes
    sample_candles = []
    for period in periods[:6]:  # First 6 periods with data
        sample_candles.extend(period["candles"][:50])  # 50 from each

    print(f"Sample size: {len(sample_candles)} candles from {min(6, len(periods))} periods")

    # Test current model
    metrics = await benchmark_current_model(conn, sample_candles)

    if metrics:
        # Save results
        results_dir = Path(__file__).parent.parent / "data"
        results_file = results_dir / "model_benchmarks.json"

        # Load existing or create new
        if results_file.exists():
            with open(results_file) as f:
                all_results = json.load(f)
        else:
            all_results = {"benchmarks": [], "updated": None}

        # Add/update this model's results
        all_results["benchmarks"] = [r for r in all_results["benchmarks"] if r["model"] != metrics["model"]]
        all_results["benchmarks"].append(metrics)
        all_results["updated"] = datetime.now().isoformat()

        with open(results_file, "w") as f:
            json.dump(all_results, f, indent=2, default=str)

        print(f"\nResults saved to: {results_file}")

        # Print leaderboard
        print(f"\n{'=' * 60}")
        print("LEADERBOARD")
        print(f"{'=' * 60}")
        sorted_results = sorted(all_results["benchmarks"], key=lambda x: x.get("buy_avg_mfe", 0), reverse=True)
        print(f"{'Model':<45} {'MFE':>8} {'Speed':>8} {'BuyRate':>8}")
        print("-" * 70)
        for r in sorted_results:
            mfe = r.get("buy_avg_mfe", 0)
            speed = r.get("speed", 0)
            buy_rate = r.get("buy_rate", 0)
            print(f"{r['model']:<45} {mfe:>+7.2f}% {speed:>7.1f}/s {buy_rate:>7.1%}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
