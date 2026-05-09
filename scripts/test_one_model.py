#!/usr/bin/env python3
"""
Test a single model with 3 scenarios and 50 real candles.
Appends results to data/model_results.md
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from ai_entry_exit_prompts import ENTRY_SYSTEM_PROMPT, format_entry_prompt
from evaluate_ai_mfe_capture import calculate_mfe_mae, get_forward_candles, load_canonical_periods_from_db

VLLM_URL = "http://localhost:8000"
RESULTS_FILE = Path(__file__).parent.parent / "data" / "model_results.md"


def get_model_name():
    """Get currently loaded model from vLLM."""
    try:
        resp = httpx.get(f"{VLLM_URL}/v1/models", timeout=5.0)
        return resp.json()["data"][0]["id"]
    except:
        return None


def test_scenarios(model: str):
    """Test 3 basic scenarios."""
    tests = [
        (
            "OVERSOLD",
            {
                "rsi_14": 22,
                "stoch_k": 6,
                "adx_14": 18,
                "macd_line": -150,
                "macd_signal": -100,
                "supertrend_direction": -1,
            },
            "SB",
        ),
        (
            "OVERBOUGHT",
            {
                "rsi_14": 78,
                "stoch_k": 92,
                "adx_14": 35,
                "macd_line": 200,
                "macd_signal": 150,
                "supertrend_direction": 1,
            },
            "SS",
        ),
        (
            "NEUTRAL",
            {"rsi_14": 52, "stoch_k": 48, "adx_14": 22, "macd_line": 10, "macd_signal": 5, "supertrend_direction": 0},
            "S",
        ),
    ]

    results = []
    for name, ind, expected in tests:
        prompt = format_entry_prompt([], ind, "test")
        resp = httpx.post(
            f"{VLLM_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "system", "content": ENTRY_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1,
            },
            timeout=30.0,
        )
        content = resp.json()["choices"][0]["message"]["content"]

        # Parse choice
        match = re.search(r'"choice"\s*:\s*"?([^",}]+)"?', content)
        choice = match.group(1).strip().upper() if match else "?"

        correct = choice == expected or (expected in ("SB", "B") and choice in ("SB", "B"))
        results.append((name, expected, choice, correct))
        print(f"  {name}: expected={expected}, got={choice} {'OK' if correct else 'WRONG'}")

    return results


def test_real_candles(model: str, max_candles: int = 50):
    """Test on real candles and measure MFE."""
    conn = psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")

    periods = load_canonical_periods_from_db(conn)

    buys = []
    skips = []

    # Sample from first 3 periods with data
    candle_count = 0
    for period in periods[:5]:
        if candle_count >= max_candles:
            break

        regime = period["regime"]
        for candle in period["candles"][:15]:
            if candle_count >= max_candles:
                break
            candle_count += 1

            try:
                forward = get_forward_candles(conn, "BTC", "1h", str(candle["time"]), 49)
                if len(forward) < 10:
                    continue

                entry_price = float(candle["close"])
                mfe, mae, _ = calculate_mfe_mae(forward[1:], entry_price)

                prompt = format_entry_prompt([], candle, regime)
                resp = httpx.post(
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
                    timeout=30.0,
                )
                content = resp.json()["choices"][0]["message"]["content"]

                # Parse
                match = re.search(r'"choice"\s*:\s*"?([^",}]+)"?', content)
                choice = match.group(1).strip().upper() if match else "S"

                rsi = float(candle.get("rsi_14") or 50)
                stoch = float(candle.get("stoch_k") or 50)

                is_buy = choice in ("SB", "B")

                if is_buy:
                    buys.append({"mfe": mfe, "rsi": rsi, "stoch": stoch})
                else:
                    skips.append({"mfe": mfe, "rsi": rsi, "stoch": stoch})

            except Exception as e:
                print(f"  Error: {e}")

    conn.close()

    # Calculate metrics
    total = len(buys) + len(skips)
    buy_rate = len(buys) / total if total else 0
    buy_mfe = sum(b["mfe"] for b in buys) / len(buys) if buys else 0
    skip_mfe = sum(s["mfe"] for s in skips) / len(skips) if skips else 0

    # Precision: bought on oversold?
    correct_buys = [b for b in buys if b["stoch"] < 20 or b["rsi"] < 30]
    precision = len(correct_buys) / len(buys) if buys else 0

    print(f"  Buys: {len(buys)}, Skips: {len(skips)}")
    print(f"  Buy Rate: {buy_rate:.1%}, Buy MFE: {buy_mfe:+.2f}%, Precision: {precision:.1%}")

    return {
        "buys": len(buys),
        "skips": len(skips),
        "buy_rate": buy_rate,
        "buy_mfe": buy_mfe,
        "skip_mfe": skip_mfe,
        "precision": precision,
    }


def append_results(model: str, scenarios: list, metrics: dict):
    """Append to results file."""
    # Create file if doesn't exist
    if not RESULTS_FILE.exists():
        with open(RESULTS_FILE, "w") as f:
            f.write("# Model Benchmark Results\n\n")

    with open(RESULTS_FILE, "a") as f:
        f.write(f"\n## {model}\n")
        f.write(f"**Tested:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        # Scenarios
        f.write("**Scenarios:**\n")
        for name, expected, got, correct in scenarios:
            f.write(f"- {name}: {expected}->{got} {'OK' if correct else 'WRONG'}\n")

        # Metrics
        f.write(f"\n**Real Candles ({metrics['buys'] + metrics['skips']} samples):**\n")
        f.write(f"- Buy Rate: {metrics['buy_rate']:.1%}\n")
        f.write(f"- Buy MFE: {metrics['buy_mfe']:+.2f}%\n")
        f.write(f"- Skip MFE: {metrics['skip_mfe']:+.2f}%\n")
        f.write(f"- Precision: {metrics['precision']:.1%}\n")
        f.write("\n---\n")
        f.flush()

    print(f"\nResults appended to {RESULTS_FILE}")


def main():
    model = get_model_name()
    if not model:
        print("ERROR: vLLM not running!")
        sys.exit(1)

    print(f"=== Testing: {model} ===\n")

    print("1. Scenario tests:")
    scenarios = test_scenarios(model)

    print("\n2. Real candle tests:")
    metrics = test_real_candles(model, max_candles=50)

    append_results(model, scenarios, metrics)
    print("\nDONE!")


if __name__ == "__main__":
    main()
