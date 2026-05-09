#!/usr/bin/env python3
"""
Evaluate AI Model Performance using MFE Capture %.

MFE Capture = How much of the maximum favorable excursion was captured.
- MFE Capture 100% = Exited at the perfect top
- MFE Capture 50% = Captured half the potential
- MFE Capture 0% = Exited at breakeven
- MFE Capture negative = Exited at a loss

Compares:
1. AI models (entry + exit decisions)
2. Top 10 agents (pattern-based rules)
3. Baseline (always hold to max_hold_periods)
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg2
from ai_entry_exit_prompts import (
    ENTRY_SYSTEM_PROMPT,
    EXIT_SYSTEM_PROMPT,
    format_entry_prompt,
    format_exit_prompt,
)


@dataclass
class TradeResult:
    """Result of a simulated trade."""

    regime: str
    period_id: str
    entry_time: str
    entry_price: float
    exit_price: float
    exit_time: str
    bars_held: int
    pnl_pct: float
    mfe_pct: float  # Max favorable excursion
    mae_pct: float  # Max adverse excursion
    mfe_capture_pct: float  # pnl_pct / mfe_pct * 100
    entry_decision: str  # CONFIRM or REJECT
    exit_reason: str  # AI_EXIT, MAX_HOLD, STOP_LOSS, etc.


VLLM_URL = "http://localhost:8000"
MAX_HOLD_BARS = 48  # Max bars to hold before forced exit
STOP_LOSS_PCT = -5.0  # Stop loss threshold


def load_canonical_data() -> dict:
    """Load exported canonical period data."""
    path = Path(__file__).parent.parent / "data" / "canonical_periods_indicators.json"
    with open(path) as f:
        return json.load(f)


def load_canonical_periods_from_db(conn) -> list:
    """Load canonical periods and ALL their candles directly from DB."""
    cur = conn.cursor()

    # Get all canonical periods
    cur.execute("""
        SELECT period_id, description, regime, start_date, end_date
        FROM canonical_periods
        ORDER BY start_date::timestamptz
    """)
    periods = []
    for row in cur.fetchall():
        periods.append(
            {
                "id": row[0],
                "name": row[0],  # period_id is the name
                "description": row[1],
                "regime": row[2],
                "start_date": row[3],
                "end_date": row[4],
            }
        )

    print(f"Loaded {len(periods)} canonical periods")

    # Get column names for enhanced_candles
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'enhanced_candles' ORDER BY ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]

    # For each period, get ALL candles
    results = []
    for period in periods:
        start = period["start_date"]
        end = period["end_date"]
        regime = period["regime"]
        name = period["name"]

        # Get all candles in the period for BTC 1h (primary test asset)
        cur.execute(
            """
            SELECT * FROM enhanced_candles
            WHERE symbol = 'BTC' AND timeframe = '1h'
            AND time >= %s::timestamptz AND time <= %s::timestamptz
            ORDER BY time
        """,
            (start, end),
        )

        rows = cur.fetchall()
        candles = [dict(zip(cols, row)) for row in rows]

        if candles:
            results.append(
                {
                    "period_id": period["id"],
                    "period_name": name,
                    "regime": regime,
                    "start_date": str(start),
                    "end_date": str(end),
                    "candles": candles,
                }
            )
            print(f"  {name}: {len(candles)} candles ({regime})")
        else:
            print(f"  {name}: NO DATA")

    return results


def get_forward_candles(conn, symbol: str, timeframe: str, start_time: str, num_bars: int) -> list:
    """Get candles forward from entry point for trade simulation."""
    cur = conn.cursor()

    # Get column names
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'enhanced_candles' ORDER BY ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]

    # Get forward candles
    cur.execute(
        """
        SELECT *
        FROM enhanced_candles
        WHERE symbol = %s AND timeframe = %s AND time >= %s
        ORDER BY time
        LIMIT %s
    """,
        (symbol, timeframe, start_time, num_bars),
    )

    rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def calculate_mfe_mae(candles: list, entry_price: float) -> tuple[float, float, int]:
    """Calculate MFE, MAE, and bar of MFE from forward candles."""
    if not candles:
        return 0.0, 0.0, 0

    mfe = 0.0  # Max favorable excursion (highest profit)
    mae = 0.0  # Max adverse excursion (deepest drawdown)
    mfe_bar = 0

    for i, candle in enumerate(candles):
        high = float(candle.get("high", entry_price))
        low = float(candle.get("low", entry_price))

        high_pct = (high - entry_price) / entry_price * 100
        low_pct = (low - entry_price) / entry_price * 100

        if high_pct > mfe:
            mfe = high_pct
            mfe_bar = i

        if low_pct < mae:
            mae = low_pct

    return mfe, mae, mfe_bar


async def get_ai_decision(
    client: httpx.AsyncClient,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, float, str]:
    """Get AI decision from vLLM."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.1,
    }

    try:
        resp = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON response
        import re

        match = re.search(r"\{[^}]+\}", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                choice = str(data.get("choice", "S")).upper().strip('"')
                confidence = float(data.get("confidence", 0.5))
                reasoning = data.get("reasoning", "") or data.get("primary_signal", "")

                # Map semantic labels to decisions
                # SB/B = BUY, S/SS = SKIP/SELL
                if choice in ("SB", "B"):
                    decision = "BUY"
                elif choice in ("S", "SS"):
                    decision = "SELL"
                else:
                    # Fallback: check reasoning for buy signals
                    reasoning_lower = reasoning.lower()
                    has_buy_signal = any(
                        x in reasoning_lower
                        for x in ["buy signal", "strong buy", "high probability", "bounce", "oversold"]
                    )
                    has_skip_signal = any(x in reasoning_lower for x in ["avoid", "overbought", "skip", "neutral"])

                    if has_buy_signal and not has_skip_signal:
                        decision = "BUY"
                        reasoning = f"[FIXED from reasoning] {reasoning}"
                    elif has_skip_signal:
                        decision = "SELL"
                    else:
                        decision = "NEUTRAL"

                return decision, confidence, f"choice={choice}: {reasoning}"
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback parsing
        if "BUY" in content.upper() or "+2" in content or "+1" in content:
            return "BUY", 0.5, content[:100]
        elif "EXIT" in content.upper():
            return "EXIT", 0.5, content[:100]
        elif "HOLD" in content.upper():
            return "HOLD", 0.5, content[:100]
        return "SELL", 0.5, content[:100]

    except Exception as e:
        return "ERROR", 0.0, str(e)


async def simulate_trade_with_ai(
    client: httpx.AsyncClient,
    model: str,
    entry_candle: dict,
    forward_candles: list,
    pattern_conditions: list,
    regime: str,
    period_id: str,
) -> TradeResult | None:
    """Simulate a single trade with AI entry/exit decisions."""

    entry_price = float(entry_candle.get("close", 0))
    if entry_price == 0:
        return None

    # Step 1: AI Entry Decision
    entry_prompt = format_entry_prompt(pattern_conditions, entry_candle, regime)
    entry_decision, entry_conf, entry_reason = await get_ai_decision(client, model, ENTRY_SYSTEM_PROMPT, entry_prompt)

    if entry_decision != "CONFIRM":
        # AI rejected entry - record as skipped trade
        return TradeResult(
            regime=regime,
            period_id=period_id,
            entry_time=str(entry_candle.get("time", "")),
            entry_price=entry_price,
            exit_price=entry_price,
            exit_time=str(entry_candle.get("time", "")),
            bars_held=0,
            pnl_pct=0.0,
            mfe_pct=0.0,
            mae_pct=0.0,
            mfe_capture_pct=0.0,
            entry_decision=entry_decision,
            exit_reason="AI_REJECTED",
        )

    # Step 2: Simulate forward with AI exit decisions
    mfe, mae, _ = calculate_mfe_mae(forward_candles, entry_price)
    peak_pnl = 0.0
    exit_bar = len(forward_candles) - 1
    exit_reason = "MAX_HOLD"

    for i, candle in enumerate(forward_candles):
        current_price = float(candle.get("close", entry_price))
        current_pnl = (current_price - entry_price) / entry_price * 100

        # Track peak
        if current_pnl > peak_pnl:
            peak_pnl = current_pnl

        # Check stop loss
        low_price = float(candle.get("low", current_price))
        low_pnl = (low_price - entry_price) / entry_price * 100
        if low_pnl <= STOP_LOSS_PCT:
            exit_bar = i
            exit_reason = "STOP_LOSS"
            break

        # AI exit decision every 4 bars (reduce API calls)
        if i > 0 and i % 4 == 0:
            exit_prompt = format_exit_prompt(
                entry_price=entry_price,
                entry_indicators=entry_candle,
                current_indicators=candle,
                bars_held=i,
                current_pnl_pct=current_pnl,
                peak_pnl_pct=peak_pnl,
            )
            exit_decision, _, _ = await get_ai_decision(client, model, EXIT_SYSTEM_PROMPT, exit_prompt)

            if exit_decision == "EXIT":
                exit_bar = i
                exit_reason = "AI_EXIT"
                break

    # Calculate final result
    exit_candle = forward_candles[exit_bar] if exit_bar < len(forward_candles) else forward_candles[-1]
    exit_price = float(exit_candle.get("close", entry_price))
    final_pnl = (exit_price - entry_price) / entry_price * 100
    mfe_capture = (final_pnl / mfe * 100) if mfe > 0 else 0.0

    return TradeResult(
        regime=regime,
        period_id=period_id,
        entry_time=str(entry_candle.get("time", "")),
        entry_price=entry_price,
        exit_price=exit_price,
        exit_time=str(exit_candle.get("time", "")),
        bars_held=exit_bar + 1,
        pnl_pct=final_pnl,
        mfe_pct=mfe,
        mae_pct=mae,
        mfe_capture_pct=mfe_capture,
        entry_decision=entry_decision,
        exit_reason=exit_reason,
    )


def check_pattern_match(indicators: dict, pattern_conditions: list) -> bool:
    """Check if pattern conditions are met."""
    for cond in pattern_conditions:
        ind = cond.get("indicator", "")
        op = cond.get("operator", "")
        val = cond.get("value", 0)
        actual = indicators.get(ind)

        if actual is None:
            return False

        if (
            (op == "<" and not (actual < val))
            or (op == ">" and not (actual > val))
            or (op == "<=" and not (actual <= val))
            or (op == ">=" and not (actual >= val))
            or (op == "==" and not (actual == val))
        ):
            return False
        elif op == "between" and isinstance(val, list) and len(val) == 2:
            if not (val[0] <= actual <= val[1]):
                return False

    return True


async def evaluate_model(model: str, max_periods: int = 0, max_candles_per_period: int = 0) -> dict:
    """Evaluate a model's MFE capture performance.

    Tests ALL candles in ALL canonical periods - AI decides BUY or SELL independently.
    Also tracks which candles a simple pattern (RSI < 35) would have caught.

    Args:
        model: vLLM model name
        max_periods: Limit periods to test (0 = all)
        max_candles_per_period: Limit candles per period (0 = all)
    """
    print(f"\n{'=' * 60}")
    print(f"Evaluating: {model}")
    print(f"{'=' * 60}")

    # Connect to DB
    conn = psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")

    # Load ALL candles for ALL canonical periods directly from DB
    periods = load_canonical_periods_from_db(conn)

    if max_periods > 0:
        periods = periods[:max_periods]

    total_candles = sum(len(p["candles"]) for p in periods)
    print(f"\nTotal candles to evaluate: {total_candles}")

    # Simple pattern for comparison
    pattern_conditions = [
        {"indicator": "rsi_14", "operator": "<", "value": 35},
    ]

    results_buy = []  # AI said BUY
    results_sell = []  # AI said SELL
    pattern_would_match = []  # Pattern would have triggered
    processed = 0

    async with httpx.AsyncClient() as client:
        for period_data in periods:
            regime = period_data["regime"]
            period_id = period_data["period_id"]
            period_name = period_data["period_name"]
            candles = period_data["candles"]

            if max_candles_per_period > 0:
                candles = candles[:max_candles_per_period]

            print(f"\n--- {period_name} ({regime}) - {len(candles)} candles ---")

            for entry_candle in candles:
                # Get forward candles from DB
                forward = get_forward_candles(
                    conn,
                    symbol=entry_candle.get("symbol", "BTC"),
                    timeframe=entry_candle.get("timeframe", "1h"),
                    start_time=entry_candle.get("time", ""),
                    num_bars=MAX_HOLD_BARS + 1,
                )

                if len(forward) < 10:
                    continue

                # Calculate MFE for this entry point
                entry_price = float(entry_candle.get("close", 0))
                mfe, mae, _ = calculate_mfe_mae(forward[1:], entry_price)

                # Check if pattern would match
                pattern_matched = check_pattern_match(entry_candle, pattern_conditions)
                if pattern_matched:
                    pattern_would_match.append({"mfe": mfe, "regime": regime})

                # Ask AI for decision on EVERY candle
                prompt = format_entry_prompt([], entry_candle, regime)
                decision, confidence, reasoning = await get_ai_decision(client, model, ENTRY_SYSTEM_PROMPT, prompt)

                rsi = entry_candle.get("rsi_14", 50)
                stoch = entry_candle.get("stoch_k", 50)

                result = {
                    "regime": regime,
                    "period_id": period_id,
                    "decision": decision,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "mfe": mfe,
                    "mae": mae,
                    "rsi": rsi,
                    "stoch": stoch,
                    "pattern_matched": pattern_matched,
                }

                processed += 1

                if decision == "BUY":
                    results_buy.append(result)
                    pattern_flag = "[P]" if pattern_matched else "   "
                    print(
                        f"  [{processed}/{total_candles}] {pattern_flag} BUY  RSI={rsi:.0f} Stoch={stoch:.0f} MFE={mfe:+.1f}%"
                    )
                else:
                    results_sell.append(result)
                    # Only print skips with high MFE (missed opportunities)
                    if mfe > 5:
                        print(
                            f"  [{processed}/{total_candles}]     SKIP RSI={rsi:.0f} Stoch={stoch:.0f} MFE={mfe:+.1f}% (missed)"
                        )

    conn.close()

    # Calculate metrics
    total = len(results_buy) + len(results_sell)

    metrics = {
        "model": model,
        "total_candles": total,
        "ai_buys": len(results_buy),
        "ai_sells": len(results_sell),
        "buy_rate": len(results_buy) / total if total else 0,
    }

    # AI BUY performance
    if results_buy:
        metrics["buy_performance"] = {
            "count": len(results_buy),
            "avg_mfe": sum(r["mfe"] for r in results_buy) / len(results_buy),
            "avg_mae": sum(r["mae"] for r in results_buy) / len(results_buy),
            "positive_mfe_rate": len([r for r in results_buy if r["mfe"] > 0]) / len(results_buy),
            "high_mfe_rate": len([r for r in results_buy if r["mfe"] > 5]) / len(results_buy),
        }

    # AI SELL (skipped) - what did we miss?
    if results_sell:
        high_mfe_missed = [r for r in results_sell if r["mfe"] > 5]
        metrics["sell_performance"] = {
            "count": len(results_sell),
            "avg_mfe_missed": sum(r["mfe"] for r in results_sell) / len(results_sell),
            "high_mfe_missed": len(high_mfe_missed),
            "high_mfe_missed_pct": len(high_mfe_missed) / len(results_sell) if results_sell else 0,
        }

    # Pattern comparison
    if pattern_would_match:
        metrics["pattern_baseline"] = {
            "count": len(pattern_would_match),
            "avg_mfe": sum(p["mfe"] for p in pattern_would_match) / len(pattern_would_match),
        }

    # By regime
    by_regime = {}
    for r in results_buy:
        regime = r["regime"]
        if regime not in by_regime:
            by_regime[regime] = []
        by_regime[regime].append(r)

    if by_regime:
        metrics["by_regime"] = {
            regime: {
                "count": len(trades),
                "avg_mfe": sum(t["mfe"] for t in trades) / len(trades),
            }
            for regime, trades in by_regime.items()
        }

    return metrics


async def main():
    """Run evaluation."""
    print("=" * 60)
    print("AI Model MFE Capture Evaluation")
    print("=" * 60)

    # Check vLLM
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                model = resp.json()["data"][0]["id"]
                print(f"[OK] vLLM running with: {model}")
            else:
                print("[X] vLLM not responding")
                return
    except Exception as e:
        print(f"[X] vLLM not running: {e}")
        return

    # Run evaluation - test ALL candles from ALL periods
    # Use max_periods=0 for all periods, max_candles_per_period=0 for all candles
    # Test all regimes: max_periods=0, but limit candles per period for speed
    metrics = await evaluate_model(model, max_periods=0, max_candles_per_period=50)

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Model: {metrics['model']}")
    print(f"Total candles: {metrics.get('total_candles', 0)}")
    print(f"AI BUYs: {metrics.get('ai_buys', 0)} | AI SKIPs: {metrics.get('ai_sells', 0)}")
    print(f"Buy Rate: {metrics.get('buy_rate', 0):.1%}")

    bp = metrics.get("buy_performance", {})
    if bp:
        print("\n[AI BUY PERFORMANCE]")
        print(f"  Count: {bp.get('count', 0)}")
        print(f"  Avg MFE: {bp.get('avg_mfe', 0):+.1f}%")
        print(f"  Avg MAE: {bp.get('avg_mae', 0):.1f}%")
        print(f"  Positive MFE: {bp.get('positive_mfe_rate', 0):.1%}")
        print(f"  High MFE (>5%): {bp.get('high_mfe_rate', 0):.1%}")

    sp = metrics.get("sell_performance", {})
    if sp:
        print("\n[AI SKIP ANALYSIS] (what we missed)")
        print(f"  Count: {sp.get('count', 0)}")
        print(f"  Avg MFE missed: {sp.get('avg_mfe_missed', 0):+.1f}%")
        print(f"  High MFE missed (>5%): {sp.get('high_mfe_missed', 0)} ({sp.get('high_mfe_missed_pct', 0):.1%})")

    pb = metrics.get("pattern_baseline", {})
    if pb:
        print("\n[PATTERN BASELINE] (RSI < 35)")
        print(f"  Would match: {pb.get('count', 0)} candles")
        print(f"  Avg MFE: {pb.get('avg_mfe', 0):+.1f}%")

    print("\n[BY REGIME]")
    for regime, data in metrics.get("by_regime", {}).items():
        print(f"  {regime:<12}: {data['count']:>2} buys, avg MFE {data['avg_mfe']:+.1f}%")

    # Save results
    out_path = Path(__file__).parent.parent / "data" / "ai_mfe_evaluation.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
