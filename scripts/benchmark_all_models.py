#!/usr/bin/env python3
"""
Benchmark ALL models by starting vLLM via WSL for each.
Results appended to data/benchmark_results.md after each model.
"""

import asyncio
import json
import re
import subprocess

# Add scripts dir to path
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))

from ai_entry_exit_prompts import ENTRY_SYSTEM_PROMPT, format_entry_prompt
from evaluate_ai_mfe_capture import calculate_mfe_mae, get_forward_candles, load_canonical_periods_from_db

VLLM_URL = "http://localhost:8000"
RESULTS_FILE = Path(__file__).parent.parent / "data" / "benchmark_results.md"

# Models to test - ordered by size
ALL_MODELS = [
    # Tiny (< 500M)
    "Qwen/Qwen2.5-0.5B-Instruct",
    # Small (500M - 1.5B)
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    # Medium (2-3B)
    "google/gemma-2-2b-it",
    "Qwen/Qwen2.5-3B-Instruct",
    "stabilityai/stablelm-zephyr-3b",
    # Larger (3B+)
    "microsoft/Phi-3-mini-4k-instruct",
]


def start_vllm_wsl(model: str) -> subprocess.Popen:
    """Start vLLM in WSL."""
    # Kill any existing vLLM first
    subprocess.run(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", "pkill -f vllm || true"],
        capture_output=True,
        env={"MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*", **dict(__import__("os").environ)},
    )
    time.sleep(2)

    # Start new vLLM
    cmd = f'/home/bamn86/miniconda3/bin/vllm serve "{model}" --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.85'
    proc = subprocess.Popen(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*", **dict(__import__("os").environ)},
    )
    return proc


def wait_for_vllm(model: str, timeout: int = 300) -> bool:
    """Wait for vLLM to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    loaded = data["data"][0]["id"]
                    if model in loaded or loaded in model:
                        return True
        except:
            pass
        time.sleep(3)
    return False


def kill_vllm():
    """Kill vLLM processes."""
    subprocess.run(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", "pkill -9 -f vllm || true"],
        capture_output=True,
        env={"MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*", **dict(__import__("os").environ)},
    )


async def test_model(model: str, sample_candles: list, conn, max_samples: int = 100) -> dict:
    """Test a model and return metrics by regime."""
    results_by_regime = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.perf_counter()
        processed = 0

        for candle in sample_candles[:max_samples]:
            try:
                regime = candle.get("_regime", "unknown")
                if regime not in results_by_regime:
                    results_by_regime[regime] = {"buys": [], "skips": [], "errors": 0}

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

                prompt = format_entry_prompt([], candle, regime)
                resp = await client.post(
                    f"{VLLM_URL}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": ENTRY_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 200,
                        "temperature": 0.1,
                    },
                )

                content = resp.json()["choices"][0]["message"]["content"]

                # Parse response - now using semantic labels SB/B/S/SS
                match = re.search(r"\{[^}]+\}", content, re.DOTALL)
                choice = "S"
                reasoning = ""
                if match:
                    try:
                        data = json.loads(match.group())
                        choice = str(data.get("choice", "S")).upper().strip('"')
                        reasoning = data.get("reasoning", "") or data.get("primary_signal", "")
                    except:
                        pass

                # Map semantic labels to buy decision
                # Also check reasoning as fallback
                reasoning_lower = reasoning.lower()
                has_buy_signal = any(
                    x in reasoning_lower for x in ["buy signal", "strong buy", "high probability", "bounce", "oversold"]
                )
                has_skip_signal = any(x in reasoning_lower for x in ["avoid", "overbought", "skip", "neutral"])

                rsi = float(candle.get("rsi_14") or 50)
                stoch = float(candle.get("stoch_k") or 50)

                result = {"rsi": rsi, "stoch": stoch, "mfe": mfe, "mae": mae, "choice": choice}

                # Determine if it's a buy
                is_buy = choice in ("SB", "B") or (
                    choice not in ("SB", "B", "S", "SS") and has_buy_signal and not has_skip_signal
                )

                if is_buy:
                    results_by_regime[regime]["buys"].append(result)
                else:
                    results_by_regime[regime]["skips"].append(result)

                processed += 1
                if processed % 20 == 0:
                    print(f"    Processed {processed}/{max_samples}...")

            except Exception:
                results_by_regime.get(regime, {"errors": 0})["errors"] = (
                    results_by_regime.get(regime, {}).get("errors", 0) + 1
                )

        elapsed = time.perf_counter() - start

    # Aggregate metrics
    total_buys = sum(len(r["buys"]) for r in results_by_regime.values())
    total_skips = sum(len(r["skips"]) for r in results_by_regime.values())

    metrics = {
        "total_buys": total_buys,
        "total_skips": total_skips,
        "buy_rate": total_buys / (total_buys + total_skips) if (total_buys + total_skips) else 0,
        "speed": processed / elapsed if elapsed > 0 else 0,
        "by_regime": {},
    }

    # Per-regime metrics
    for regime, data in results_by_regime.items():
        buys = data["buys"]
        skips = data["skips"]
        if buys:
            avg_mfe = sum(b["mfe"] for b in buys) / len(buys)
            # Precision: did we buy on oversold?
            correct = [b for b in buys if b["stoch"] < 20 or b["rsi"] < 30]
            precision = len(correct) / len(buys) if buys else 0
            metrics["by_regime"][regime] = {
                "buys": len(buys),
                "skips": len(skips),
                "avg_mfe": avg_mfe,
                "precision": precision,
            }

    # Overall buy MFE
    all_buys = []
    for r in results_by_regime.values():
        all_buys.extend(r["buys"])
    if all_buys:
        metrics["buy_avg_mfe"] = sum(b["mfe"] for b in all_buys) / len(all_buys)
        correct = [b for b in all_buys if b["stoch"] < 20 or b["rsi"] < 30]
        metrics["precision"] = len(correct) / len(all_buys)

    return metrics


def append_result(model: str, metrics: dict, status: str = "OK"):
    """Append result to markdown file."""
    with open(RESULTS_FILE, "a") as f:
        if status == "OK":
            buy_mfe = metrics.get("buy_avg_mfe", 0)
            buy_rate = metrics.get("buy_rate", 0)
            speed = metrics.get("speed", 0)
            precision = metrics.get("precision", 0)

            f.write(f"\n### {model}\n")
            f.write(f"- **Buy Rate:** {buy_rate:.1%}\n")
            f.write(f"- **Buy MFE:** {buy_mfe:+.2f}%\n")
            f.write(f"- **Precision:** {precision:.1%}\n")
            f.write(f"- **Speed:** {speed:.1f}/s\n")

            # Per-regime breakdown
            if metrics.get("by_regime"):
                f.write("- **By Regime:**\n")
                for regime, data in metrics["by_regime"].items():
                    f.write(f"  - {regime}: {data['buys']} buys, MFE={data['avg_mfe']:+.2f}%\n")
        else:
            f.write(f"\n### {model}\n")
            f.write(f"- **Status:** {status}\n")
        f.flush()


def init_results_file():
    """Initialize results file."""
    with open(RESULTS_FILE, "w") as f:
        f.write("# AI Model Benchmark Results\n\n")
        f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Testing {len(ALL_MODELS)} models on canonical period data.\n")
        f.write("Evaluating entry decisions with reasoning-based fix for small model number errors.\n")
        f.flush()


async def run_benchmark():
    """Run benchmark on all models."""
    print("=" * 70)
    print("AI MODEL BENCHMARK - ALL MODELS")
    print(f"Results file: {RESULTS_FILE}")
    print("=" * 70)

    init_results_file()

    # Connect to DB
    conn = psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")

    # Load sample data from multiple regimes
    print("\nLoading canonical periods...")
    periods = load_canonical_periods_from_db(conn)

    # Sample candles from each regime
    sample_candles = []
    for period in periods:
        regime = period["regime"]
        for candle in period["candles"][:25]:  # 25 per period
            candle["_regime"] = regime
            sample_candles.append(candle)

    print(f"Sample: {len(sample_candles)} candles from {len(periods)} periods")
    print(f"\nTesting {len(ALL_MODELS)} models...\n")

    vllm_proc = None

    for i, model in enumerate(ALL_MODELS):
        print(f"\n[{i + 1}/{len(ALL_MODELS)}] {model}")

        try:
            # Kill any existing vLLM
            print("  Stopping previous vLLM...")
            kill_vllm()
            time.sleep(3)

            # Start new vLLM
            print("  Starting vLLM...")
            vllm_proc = start_vllm_wsl(model)

            # Wait for ready
            print("  Waiting for model to load...")
            ready = wait_for_vllm(model, timeout=300)

            if not ready:
                print("  [X] Timeout - model failed to load")
                append_result(model, {}, "TIMEOUT")
                continue

            # Run benchmark
            print("  Running benchmark...")
            metrics = await test_model(model, sample_candles, conn, max_samples=150)

            # Report
            buy_mfe = metrics.get("buy_avg_mfe", 0)
            buy_rate = metrics.get("buy_rate", 0)
            precision = metrics.get("precision", 0)
            speed = metrics.get("speed", 0)

            print(
                f"  Buy Rate: {buy_rate:.1%} | Buy MFE: {buy_mfe:+.2f}% | Precision: {precision:.1%} | Speed: {speed:.1f}/s"
            )

            # Show per-regime
            for regime, data in metrics.get("by_regime", {}).items():
                print(f"    {regime}: {data['buys']} buys, MFE={data['avg_mfe']:+.2f}%")

            append_result(model, metrics, "OK")

        except Exception as e:
            print(f"  [X] Error: {e}")
            append_result(model, {}, f"ERROR: {e}")

    # Cleanup
    kill_vllm()
    conn.close()

    with open(RESULTS_FILE, "a") as f:
        f.write(f"\n---\n**Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"\n{'=' * 70}")
    print(f"DONE! Results saved to: {RESULTS_FILE}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
