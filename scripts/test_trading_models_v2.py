#!/usr/bin/env python3
"""
Trading Model Evaluation v2 - Asymmetric Cost Framework

Key insight: These are UNCERTAIN signals we'd skip by default.
- False positives (bad trades) = REAL MONEY LOST
- False negatives (missed trades) = $0 (we were skipping anyway)

Metrics that matter:
1. Net P&L on trades taken
2. Expectancy per trade
3. Precision (when it trades, is it right?)
4. Confidence calibration
"""

import asyncio
import json
import re
import time
from pathlib import Path

import httpx
import numpy as np

VLLM_URL = "http://localhost:8000"

# More nuanced prompt that emphasizes conservative approach
SYSTEM_PROMPT = """You are a cryptocurrency trading decision engine evaluating UNCERTAIN signals.

CRITICAL CONTEXT:
- These signals are already flagged as uncertain/ambiguous
- The DEFAULT action is SKIP (no trade)
- Only recommend trading if you see CLEAR profitable edge
- False positives (bad trades) cost REAL MONEY
- False negatives (missed trades) cost NOTHING - we were skipping anyway

DECISION FRAMEWORK:
- Consider the risk/reward ratio implied by indicators
- Evaluate if there's genuine edge or just noise
- Factor in confidence level and indicator alignment
- When in doubt, SKIP

OUTPUT FORMAT (JSON only):
{
    "action": "long" | "skip",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of key factors",
    "expected_rr": estimated risk:reward ratio (e.g., 2.5)
}

BE CONSERVATIVE: Only trade when you see clear edge. Default is SKIP."""


def load_trades() -> list[dict]:
    """Load test trades with P&L data."""
    trades_path = Path(__file__).parent.parent / "data" / "top_agent_trades.json"
    with open(trades_path) as f:
        return json.load(f)


def format_trade_prompt(trade: dict) -> str:
    """Format trade as evaluation request."""
    ind = trade["indicators"]

    # Classify indicator signals
    rsi = ind.get("rsi_14", 50)
    rsi_signal = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"

    macd_line = ind.get("macd_line", 0)
    macd_signal = ind.get("macd_signal", 0)
    macd_crossover = "bullish" if macd_line > macd_signal else "bearish"

    st_dir = ind.get("supertrend_direction", 0)
    trend = "bullish" if st_dir > 0 else "bearish" if st_dir < 0 else "neutral"

    return f"""UNCERTAIN SIGNAL EVALUATION

Asset: {trade["symbol"]}
Signal Zone: {trade.get("zone", "uncertain")}
Base Confidence: {trade["confidence"]:.1%}

TECHNICAL INDICATORS:
- RSI(14): {rsi:.1f} ({rsi_signal})
- MACD: Line={macd_line:.6f}, Signal={macd_signal:.6f} ({macd_crossover} crossover)
- Stochastic K: {ind.get("stoch_k", 50):.1f}
- ADX(14): {ind.get("adx_14", 25):.1f} (trend strength)
- ATR(14): {ind.get("atr_14", 0):.6f}
- Bollinger Bands: Lower={ind.get("bb_lower", 0):.4f}, Upper={ind.get("bb_upper", 0):.4f}
- Supertrend Direction: {trend}

UNCERTAINTY FACTORS:
- This signal is below our normal confidence threshold
- Mixed indicator readings detected
- Default recommendation would be SKIP

QUESTION: Is there enough edge here to trade, or should we skip?
Remember: Only recommend trading if you see clear profitable opportunity."""


def parse_model_response(response: str) -> dict:
    """Parse model JSON response."""
    # Try to extract JSON
    try:
        # Find JSON in response
        match = re.search(r"\{[^{}]+\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "action": data.get("action", "skip").lower(),
                "confidence": float(data.get("confidence", 0.5)),
                "reasoning": data.get("reasoning", ""),
                "expected_rr": float(data.get("expected_rr", 1.0)),
            }
    except:
        pass

    # Fallback parsing
    action = "skip"
    if "long" in response.lower() and "skip" not in response.lower():
        action = "long"

    # Extract confidence if present
    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', response)
    confidence = float(conf_match.group(1)) if conf_match else 0.5

    return {
        "action": action,
        "confidence": confidence,
        "reasoning": response[:200],
        "expected_rr": 1.0,
    }


async def test_single_trade(
    client: httpx.AsyncClient,
    trade: dict,
    model: str,
) -> dict:
    """Test a single trade and return full results."""
    prompt = format_trade_prompt(trade)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
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
        latency = time.perf_counter() - start

        parsed = parse_model_response(content)

        return {
            "success": True,
            "latency": latency,
            "raw_response": content,
            **parsed,
            "trade": trade,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency": time.perf_counter() - start,
            "trade": trade,
        }


async def evaluate_model(
    trades: list[dict],
    model: str,
    confidence_thresholds: list[float] = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85],
    concurrency: int = 16,
) -> dict:
    """Evaluate model across different confidence thresholds."""
    print(f"\n  Testing {len(trades)} signals...")

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_test(trade: dict):
        async with semaphore:
            async with httpx.AsyncClient() as client:
                return await test_single_trade(client, trade, model)

    start = time.perf_counter()
    results = await asyncio.gather(*[bounded_test(t) for t in trades])
    total_time = time.perf_counter() - start

    # Filter successful results
    valid_results = [r for r in results if r.get("success", False)]
    errors = len(results) - len(valid_results)

    print(f"  Completed: {len(valid_results)} valid, {errors} errors, {total_time:.1f}s")

    # Evaluate at each threshold
    threshold_results = {}

    for threshold in confidence_thresholds:
        metrics = calculate_metrics(valid_results, threshold)
        threshold_results[threshold] = metrics

    return {
        "model": model,
        "total_signals": len(trades),
        "valid_results": len(valid_results),
        "errors": errors,
        "total_time": total_time,
        "raw_results": valid_results,
        "by_threshold": threshold_results,
    }


def calculate_metrics(results: list[dict], confidence_threshold: float) -> dict:
    """Calculate trading metrics at a specific confidence threshold."""

    # Separate trades vs skips based on model decision AND confidence
    trades_taken = []
    trades_skipped = []

    for r in results:
        would_trade = r["action"] == "long" and r["confidence"] >= confidence_threshold

        if would_trade:
            trades_taken.append(r)
        else:
            trades_skipped.append(r)

    if not trades_taken:
        return {
            "threshold": confidence_threshold,
            "trades_taken": 0,
            "trades_skipped": len(trades_skipped),
            "selectivity": 0,
            "net_pnl": 0,
            "expectancy": 0,
            "precision": 0,
            "note": "Model skipped everything at this threshold",
        }

    # Calculate P&L for trades taken
    pnls = []
    winning_trades = []
    losing_trades = []

    for r in trades_taken:
        pnl = r["trade"]["pnl_pct"]  # Actual outcome
        pnls.append(pnl)

        if pnl > 0:
            winning_trades.append(r)
        else:
            losing_trades.append(r)

    net_pnl = sum(pnls)
    avg_win = np.mean([r["trade"]["pnl_pct"] for r in winning_trades]) if winning_trades else 0
    avg_loss = np.mean([r["trade"]["pnl_pct"] for r in losing_trades]) if losing_trades else 0

    win_rate = len(winning_trades) / len(trades_taken) if trades_taken else 0
    precision = win_rate  # Same as precision in this context

    # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    # Selectivity = what % of signals does model trade?
    selectivity = len(trades_taken) / len(results) if results else 0

    # Profit factor
    total_wins = sum(r["trade"]["pnl_pct"] for r in winning_trades) if winning_trades else 0
    total_losses = abs(sum(r["trade"]["pnl_pct"] for r in losing_trades)) if losing_trades else 0.01
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    # Confidence calibration (model confidence vs actual win rate)
    avg_confidence = np.mean([r["confidence"] for r in trades_taken])
    calibration_error = abs(avg_confidence - win_rate)

    return {
        "threshold": confidence_threshold,
        "trades_taken": len(trades_taken),
        "trades_skipped": len(trades_skipped),
        "selectivity": selectivity,
        # PRIMARY METRICS
        "net_pnl": net_pnl,
        "expectancy": expectancy,
        "precision": precision,
        "profit_factor": profit_factor,
        # SECONDARY
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "wins": len(winning_trades),
        "losses": len(losing_trades),
        # CALIBRATION
        "avg_confidence": avg_confidence,
        "calibration_error": calibration_error,
    }


def print_results(eval_results: dict):
    """Pretty print evaluation results."""
    print(f"\n{'=' * 70}")
    print(f"MODEL: {eval_results['model']}")
    print(f"{'=' * 70}")

    print(f"\nSignals tested: {eval_results['total_signals']}")
    print(f"Valid responses: {eval_results['valid_results']}")
    print(f"Errors: {eval_results['errors']}")
    print(f"Total time: {eval_results['total_time']:.1f}s")

    print(f"\n{'─' * 70}")
    print(f"{'Threshold':>10} {'Trades':>8} {'Select%':>8} {'Net P&L':>10} {'Expect':>8} {'Precision':>10} {'PF':>6}")
    print(f"{'─' * 70}")

    for threshold, metrics in eval_results["by_threshold"].items():
        if metrics["trades_taken"] > 0:
            print(
                f"{threshold:>10.2f} {metrics['trades_taken']:>8} "
                f"{metrics['selectivity']:>7.1%} {metrics['net_pnl']:>9.1f}% "
                f"{metrics['expectancy']:>7.2f}% {metrics['precision']:>9.1%} "
                f"{metrics['profit_factor']:>6.2f}"
            )
        else:
            print(f"{threshold:>10.2f} {'(skipped all)':>40}")

    # Find best threshold by net P&L
    best_threshold = max(eval_results["by_threshold"].items(), key=lambda x: x[1].get("net_pnl", float("-inf")))

    print(f"\n{'─' * 70}")
    print(f"BEST THRESHOLD: {best_threshold[0]}")
    print(f"  Net P&L: {best_threshold[1]['net_pnl']:.1f}%")
    print(f"  Expectancy: {best_threshold[1]['expectancy']:.2f}% per trade")
    print(f"  Precision: {best_threshold[1]['precision']:.1%}")
    print(f"  Trades: {best_threshold[1]['trades_taken']}/{eval_results['valid_results']}")


def print_reasoning_examples(eval_results: dict, threshold: float = 0.7):
    """Show example reasoning at a specific threshold."""
    results = eval_results["raw_results"]

    # Categorize by outcome
    categories = {
        "correct_trade_win": [],  # Traded, actually won
        "correct_skip_loss": [],  # Skipped (or low conf), actually lost
        "wrong_trade_loss": [],  # Traded, actually lost (FALSE POSITIVE - BAD!)
        "wrong_skip_win": [],  # Skipped, actually won (missed opportunity - OK)
    }

    for r in results:
        would_trade = r["action"] == "long" and r["confidence"] >= threshold
        actual_win = r["trade"]["pnl_pct"] > 0

        if would_trade and actual_win:
            categories["correct_trade_win"].append(r)
        elif not would_trade and not actual_win:
            categories["correct_skip_loss"].append(r)
        elif would_trade and not actual_win:
            categories["wrong_trade_loss"].append(r)
        else:  # not would_trade and actual_win
            categories["wrong_skip_win"].append(r)

    print(f"\n{'=' * 70}")
    print(f"REASONING EXAMPLES (threshold={threshold})")
    print(f"{'=' * 70}")

    labels = {
        "correct_trade_win": "[GOOD] Traded + Won",
        "wrong_trade_loss": "[BAD!] Traded + Lost (FALSE POSITIVE)",
        "correct_skip_loss": "[OK] Skipped + Would Have Lost",
        "wrong_skip_win": "[Missed] Skipped + Would Have Won",
    }

    for cat, label in labels.items():
        examples = categories[cat][:2]
        if examples:
            print(f"\n{label} ({len(categories[cat])} total)")
            print(f"{'─' * 70}")
            for ex in examples:
                trade = ex["trade"]
                print(
                    f"  {trade['symbol']} | Actual P&L: {trade['pnl_pct']:+.1f}% | Model Conf: {ex['confidence']:.0%}"
                )
                print(f"  RSI: {trade['indicators'].get('rsi_14', 0):.0f} | Base Conf: {trade['confidence']:.0%}")
                print(f"  Reasoning: {ex['reasoning'][:150]}...")
                print()


async def check_vllm() -> tuple[bool, str]:
    """Check if vLLM is running."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    return True, data["data"][0]["id"]
        return False, "No model loaded"
    except Exception as e:
        return False, str(e)


async def main():
    """Run evaluation."""
    print("=" * 70)
    print("Trading Model Evaluation v2")
    print("Asymmetric Cost Framework: Precision > Accuracy")
    print("=" * 70)

    # Load trades
    trades = load_trades()
    winners = [t for t in trades if t["pnl_pct"] > 0]
    losers = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)

    print(f"\nDataset: {len(trades)} uncertain signals")
    print(f"  Winners: {len(winners)} (avg +{np.mean([t['pnl_pct'] for t in winners]):.1f}%)")
    print(f"  Losers: {len(losers)} (avg {np.mean([t['pnl_pct'] for t in losers]):.1f}%)")
    print(f"  If traded ALL: {total_pnl:.1f}% net P&L")
    print("  Baseline (skip all): 0% net P&L")

    # Check vLLM
    running, model = await check_vllm()
    if not running:
        print(f"\n[X] vLLM not running: {model}")
        return

    print(f"\n[OK] Model: {model}")

    # Evaluate
    eval_results = await evaluate_model(
        trades,
        model,
        confidence_thresholds=[0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9],
        concurrency=24,
    )

    # Print results
    print_results(eval_results)
    print_reasoning_examples(eval_results, threshold=0.7)

    # Save results
    output_path = Path(__file__).parent.parent / "data" / "model_eval_v2.json"

    # Prepare serializable results
    save_data = {
        "model": eval_results["model"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_signals": eval_results["total_signals"],
        "by_threshold": eval_results["by_threshold"],
    }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
