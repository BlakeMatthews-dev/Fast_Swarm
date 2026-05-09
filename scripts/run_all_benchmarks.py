#!/usr/bin/env python3
"""
Run benchmarks on ALL models sequentially.

Starts vLLM with each model, runs benchmark, appends to results file.
Results file: data/benchmark_results.md (watch this file!)
"""

import asyncio
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from ai_entry_exit_prompts import ENTRY_SYSTEM_PROMPT, format_entry_prompt
from evaluate_ai_mfe_capture import calculate_mfe_mae, get_forward_candles, load_canonical_periods_from_db

VLLM_URL = "http://localhost:8000"
RESULTS_FILE = Path(__file__).parent.parent / "data" / "benchmark_results.md"

# All models to test - ordered by size (fastest first)
ALL_MODELS = [
    # Tiny (< 500M)
    "HuggingFaceTB/SmolLM-135M-Instruct",
    "HuggingFaceTB/SmolLM-360M-Instruct",
    "Qwen/Qwen2.5-0.5B-Instruct",
    # Small (500M - 1.5B)
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "meta-llama/Llama-3.2-1B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "HuggingFaceTB/SmolLM-1.7B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "stabilityai/stablelm-2-zephyr-1_6b",
    # Medium (2-3B)
    "google/gemma-2b-it",
    "google/gemma-2-2b-it",
    "Qwen/Qwen2.5-3B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "stabilityai/stablelm-zephyr-3b",
    # Larger (3B+)
    "microsoft/Phi-3-mini-4k-instruct",
]


def append_result(model: str, metrics: dict, status: str = "OK"):
    """Append result to markdown file."""
    with open(RESULTS_FILE, "a") as f:
        if status == "OK":
            f.write(
                f"| {model:<45} | {metrics.get('buy_avg_mfe', 0):+6.2f}% | "
                f"{metrics.get('skip_avg_mfe', 0):+6.2f}% | {metrics.get('buy_rate', 0):5.1%} | "
                f"{metrics.get('speed', 0):5.1f}/s | {metrics.get('buy_precision', 0):5.1%} | OK |\n"
            )
        else:
            f.write(f"| {model:<45} | {'N/A':>7} | {'N/A':>7} | {'N/A':>6} | {'N/A':>6} | {'N/A':>6} | {status} |\n")
        f.flush()


def init_results_file():
    """Initialize results markdown file with header."""
    with open(RESULTS_FILE, "w") as f:
        f.write("# AI Model Benchmark Results\n\n")
        f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("| Model | Buy MFE | Skip MFE | Buy Rate | Speed | Precision | Status |\n")
        f.write("|-------|---------|----------|----------|-------|-----------|--------|\n")
        f.flush()


async def test_model(model: str, sample_candles: list, conn, max_samples: int = 100) -> dict:
    """Test a model and return metrics."""
    results = {"buys": [], "skips": [], "errors": 0}
    import re

    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.perf_counter()

        for candle in sample_candles[:max_samples]:
            try:
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
                match = re.search(r'"choice"\s*:\s*([+-]?\d)', content)
                choice = int(match.group(1)) if match else 0

                rsi = float(candle.get("rsi_14") or 50)
                stoch = float(candle.get("stoch_k") or 50)

                result = {"rsi": rsi, "stoch": stoch, "mfe": mfe, "mae": mae, "choice": choice}

                if choice >= 1:
                    results["buys"].append(result)
                else:
                    results["skips"].append(result)

            except Exception:
                results["errors"] += 1

        elapsed = time.perf_counter() - start
        results["elapsed"] = elapsed
        results["rate"] = (len(results["buys"]) + len(results["skips"])) / elapsed if elapsed > 0 else 0

    # Calculate metrics
    buys = results["buys"]
    skips = results["skips"]

    metrics = {
        "buy_count": len(buys),
        "skip_count": len(skips),
        "buy_rate": len(buys) / (len(buys) + len(skips)) if (buys or skips) else 0,
        "speed": results["rate"],
        "errors": results["errors"],
    }

    if buys:
        metrics["buy_avg_mfe"] = sum(b["mfe"] for b in buys) / len(buys)
        correct_buys = [b for b in buys if b["stoch"] < 20 or b["rsi"] < 30]
        metrics["buy_precision"] = len(correct_buys) / len(buys)

    if skips:
        metrics["skip_avg_mfe"] = sum(s["mfe"] for s in skips) / len(skips)

    return metrics


async def wait_for_vllm(model: str, timeout: int = 180) -> bool:
    """Wait for vLLM to load the model."""
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
                if resp.status_code == 200:
                    loaded = resp.json()["data"][0]["id"]
                    if model in loaded or loaded in model:
                        return True
            except:
                pass
            await asyncio.sleep(3)
    return False


def start_vllm(model: str) -> subprocess.Popen:
    """Start vLLM with the specified model via WSL."""
    # Run vLLM through WSL
    cmd = [
        "wsl",
        "-e",
        "bash",
        "-c",
        f"source ~/.bashrc && vllm serve {model} --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.85",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    return proc


def kill_vllm(proc: subprocess.Popen):
    """Kill vLLM process via WSL."""
    # Kill the WSL process and any vLLM inside
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    # Also kill vLLM processes inside WSL
    subprocess.run(["wsl", "-e", "bash", "-c", "pkill -f vllm"], capture_output=True)
    try:
        proc.wait(timeout=5)
    except:
        pass


async def run_all_benchmarks():
    """Run benchmarks on all models."""
    print("=" * 70)
    print("AI MODEL BENCHMARK - ALL MODELS")
    print(f"Results file: {RESULTS_FILE}")
    print("=" * 70)

    # Initialize results file
    init_results_file()

    # Connect to DB
    conn = psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")

    # Load sample data
    print("\nLoading canonical periods...")
    periods = load_canonical_periods_from_db(conn)

    sample_candles = []
    for period in periods[:4]:  # 4 periods
        sample_candles.extend(period["candles"][:75])  # 75 each = 300 total

    print(f"Sample: {len(sample_candles)} candles")
    print(f"\nTesting {len(ALL_MODELS)} models...\n")

    vllm_proc = None

    for i, model in enumerate(ALL_MODELS):
        print(f"\n[{i + 1}/{len(ALL_MODELS)}] {model}")

        try:
            # Kill any existing vLLM
            if vllm_proc:
                print("  Stopping previous vLLM...")
                kill_vllm(vllm_proc)
                await asyncio.sleep(3)

            # Start new vLLM
            print("  Starting vLLM...")
            vllm_proc = start_vllm(model)

            # Wait for it to be ready
            print("  Waiting for model to load...")
            ready = await wait_for_vllm(model, timeout=300)

            if not ready:
                print("  [X] Timeout - model failed to load")
                append_result(model, {}, "TIMEOUT")
                continue

            # Run benchmark
            print("  Running benchmark...")
            metrics = await test_model(model, sample_candles, conn, max_samples=100)

            # Report results
            buy_mfe = metrics.get("buy_avg_mfe", 0)
            speed = metrics.get("speed", 0)
            buy_rate = metrics.get("buy_rate", 0)
            precision = metrics.get("buy_precision", 0)

            print(
                f"  Buy MFE: {buy_mfe:+.2f}% | Speed: {speed:.1f}/s | "
                f"Buy Rate: {buy_rate:.1%} | Precision: {precision:.1%}"
            )

            append_result(model, metrics, "OK")

        except Exception as e:
            print(f"  [X] Error: {e}")
            append_result(model, {}, "ERROR")

    # Cleanup
    if vllm_proc:
        kill_vllm(vllm_proc)

    conn.close()

    # Final summary
    with open(RESULTS_FILE, "a") as f:
        f.write(f"\n**Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"\n{'=' * 70}")
    print(f"DONE! Results saved to: {RESULTS_FILE}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
