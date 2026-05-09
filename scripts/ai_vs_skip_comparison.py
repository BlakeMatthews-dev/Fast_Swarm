#!/usr/bin/env python3
"""
A/B Test: AI-Assisted Uncertainty vs Skip Uncertainty

For each candle in canonical periods:
1. Check if pattern match is CERTAIN (strong signal) or UNCERTAIN (gray zone)
2. Strategy A: Uncertain → Ask AI with full context → Maybe trade
3. Strategy B: Uncertain → Always skip
4. Compare: Total PnL, EV per trade, Accuracy
"""

import re
from pathlib import Path

import httpx
import psycopg2
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Load template with includes support
PROMPTS_DIR = Path(__file__).parent.parent / "local_agents" / "prompts"
env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=select_autoescape())
AI_TEMPLATE = env.get_template("ai_zone_decision.j2")

VLLM_URL = "http://localhost:8000"


def get_db_connection():
    return psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")


def load_top_agent(conn):
    """Load top agent with full details."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, traits, trading_philosophy, assigned_patterns
        FROM agents WHERE status = 'active'
        ORDER BY fitness_score DESC LIMIT 1
    """)
    row = cur.fetchone()
    return {"id": row[0], "name": row[1], "traits": row[2] or {}, "philosophy": row[3] or "", "patterns": row[4] or {}}


def load_canonical_candles(conn, limit=200):
    """Load candles from canonical periods with full indicators."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.time, c.close, c.rsi_14, c.stoch_k, c.adx_14,
               c.macd_line, c.macd_signal, c.supertrend_direction,
               cp.regime, cp.period_id as period_name
        FROM enhanced_candles c
        JOIN canonical_periods cp ON c.time BETWEEN cp.start_date::timestamp AND cp.end_date::timestamp
        WHERE c.symbol = 'BTC' AND c.timeframe = '1h'
        AND c.rsi_14 IS NOT NULL AND c.stoch_k IS NOT NULL
        ORDER BY c.time
        LIMIT %s
    """,
        (limit,),
    )

    columns = [
        "time",
        "close",
        "rsi_14",
        "stoch_k",
        "adx_14",
        "macd_line",
        "macd_signal",
        "supertrend_direction",
        "regime",
        "period_name",
    ]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_forward_mfe(conn, time, bars=24):
    """Get MFE for next N bars after entry."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT high, low, close FROM enhanced_candles
        WHERE symbol = 'BTC' AND timeframe = '1h' AND time > %s
        ORDER BY time LIMIT %s
    """,
        (time, bars),
    )

    rows = cur.fetchall()
    if not rows:
        return 0, 0

    entry_price = float(rows[0][2]) if rows else 0
    if entry_price == 0:
        return 0, 0

    max_high = max(float(r[0]) for r in rows)
    min_low = min(float(r[1]) for r in rows)

    mfe = (max_high - entry_price) / entry_price * 100
    mae = (entry_price - min_low) / entry_price * 100
    return mfe, mae


def classify_signal(candle, agent_traits):
    """Classify candle as CERTAIN_BUY, CERTAIN_SKIP, or UNCERTAIN."""
    rsi = float(candle["rsi_14"])
    stoch = float(candle["stoch_k"])

    # Get agent's thresholds
    min_thresh = agent_traits.get("min_threshold", 0.5)
    ai_thresh = agent_traits.get("ai_threshold", 0.9)

    # Strong oversold = certain buy
    if rsi < 25 or stoch < 10:
        return "CERTAIN_BUY", 1.0

    # Oversold = likely buy
    if rsi < 30 or stoch < 20:
        return "CERTAIN_BUY", 0.8

    # Strong overbought = certain skip
    if rsi > 75 or stoch > 90:
        return "CERTAIN_SKIP", 1.0

    # Overbought = likely skip
    if rsi > 70 or stoch > 80:
        return "CERTAIN_SKIP", 0.8

    # Gray zone - UNCERTAIN
    # Calculate how "interesting" this setup is
    uncertainty_score = 0.5

    # Slightly oversold but not extreme
    if 30 <= rsi < 40 or 20 <= stoch < 35:
        uncertainty_score = 0.6

    # Slightly overbought but not extreme
    if 60 < rsi <= 70 or 65 < stoch <= 80:
        uncertainty_score = 0.4

    return "UNCERTAIN", uncertainty_score


def ask_ai(candle, agent, regime):
    """Ask AI for decision on uncertain candle using Jinja template."""
    indicators = {
        "rsi_14": float(candle["rsi_14"]) if candle["rsi_14"] is not None else "N/A",
        "stoch_k": float(candle["stoch_k"]) if candle["stoch_k"] is not None else "N/A",
        "adx_14": float(candle["adx_14"]) if candle["adx_14"] is not None else "N/A",
        "macd_line": float(candle["macd_line"]) if candle["macd_line"] is not None else "N/A",
        "macd_signal": float(candle["macd_signal"]) if candle["macd_signal"] is not None else "N/A",
        "supertrend": int(candle["supertrend_direction"]) if candle["supertrend_direction"] is not None else "N/A",
    }

    # Render the Jinja template
    prompt = AI_TEMPLATE.render(
        asset="BTC",
        pattern_name="Uncertain Signal",
        pattern_id="uncertain",
        direction="long",
        confidence=0.65,
        min_threshold=0.5,
        ai_threshold=0.9,
        indicators=indicators,
        agent_name=agent["name"],
        traits=agent["traits"],
        philosophy=agent["philosophy"],
        recent_win_rate=0.5,
        recent_pnl_pct=0,
        trades_today=0,
        memories=[],
    )

    try:
        resp = httpx.post(
            f"{VLLM_URL}/v1/chat/completions",
            json={
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1,
            },
            timeout=30.0,
        )

        content = resp.json()["choices"][0]["message"]["content"]

        # Parse choice
        match = re.search(r'"choice"\s*:\s*"?([^",}]+)"?', content)
        choice = match.group(1).strip().upper() if match else "S"

        return choice in ("SB", "B"), choice
    except Exception as e:
        print(f"  AI Error: {e}")
        return False, "ERROR"


def run_comparison(limit=100):
    """Run A/B comparison."""
    conn = get_db_connection()

    print("Loading agent and candles...")
    agent = load_top_agent(conn)
    candles = load_canonical_candles(conn, limit)
    print(f"Agent: {agent['name']}")
    print(f"Candles: {len(candles)}")

    # Results tracking
    results = {
        "certain_buy": {"trades": 0, "total_mfe": 0, "wins": 0},
        "certain_skip": {"count": 0},
        "uncertain_ai": {"trades": 0, "skips": 0, "total_mfe": 0, "wins": 0},
        "uncertain_skip": {"count": 0, "missed_mfe": 0, "missed_wins": 0},
    }

    print("\nProcessing candles...")
    for i, candle in enumerate(candles):
        signal, confidence = classify_signal(candle, agent["traits"])
        mfe, mae = get_forward_mfe(conn, candle["time"])
        is_winner = mfe > 1.5  # 1.5% MFE = winner

        if signal == "CERTAIN_BUY":
            results["certain_buy"]["trades"] += 1
            results["certain_buy"]["total_mfe"] += mfe
            if is_winner:
                results["certain_buy"]["wins"] += 1

        elif signal == "CERTAIN_SKIP":
            results["certain_skip"]["count"] += 1

        else:  # UNCERTAIN
            # Strategy A: Ask AI
            ai_buy, ai_choice = ask_ai(candle, agent, candle["regime"])

            if ai_buy:
                results["uncertain_ai"]["trades"] += 1
                results["uncertain_ai"]["total_mfe"] += mfe
                if is_winner:
                    results["uncertain_ai"]["wins"] += 1
            else:
                results["uncertain_ai"]["skips"] += 1

            # Strategy B: Always skip (track what we missed)
            results["uncertain_skip"]["count"] += 1
            results["uncertain_skip"]["missed_mfe"] += mfe
            if is_winner:
                results["uncertain_skip"]["missed_wins"] += 1

        if (i + 1) % 20 == 0:
            print(f"  Processed {i + 1}/{len(candles)}...")

    conn.close()
    return results, agent


def print_results(results, agent):
    """Print comparison results."""
    print("\n" + "=" * 70)
    print("RESULTS: AI vs Skip on Uncertain Signals")
    print(f"Agent: {agent['name']}")
    print("=" * 70)

    # Certain signals (baseline)
    cb = results["certain_buy"]
    if cb["trades"] > 0:
        cb_wr = cb["wins"] / cb["trades"] * 100
        cb_ev = cb["total_mfe"] / cb["trades"]
        print("\nCERTAIN BUYS (baseline):")
        print(f"  Trades: {cb['trades']}, Win Rate: {cb_wr:.1f}%, Avg MFE: {cb_ev:.2f}%")

    print(f"\nCERTAIN SKIPS: {results['certain_skip']['count']}")

    # Strategy A: AI-assisted
    ai = results["uncertain_ai"]
    print("\n--- STRATEGY A: AI-Assisted Uncertainty ---")
    print(f"  AI said BUY: {ai['trades']}")
    print(f"  AI said SKIP: {ai['skips']}")
    if ai["trades"] > 0:
        ai_wr = ai["wins"] / ai["trades"] * 100
        ai_ev = ai["total_mfe"] / ai["trades"]
        print(f"  Win Rate: {ai_wr:.1f}%")
        print(f"  Avg MFE: {ai_ev:.2f}%")
        print(f"  Total Value: {ai['total_mfe']:.2f}%")

    # Strategy B: Always skip
    skip = results["uncertain_skip"]
    print("\n--- STRATEGY B: Always Skip Uncertainty ---")
    print(f"  Skipped: {skip['count']}")
    print(f"  Missed Winners: {skip['missed_wins']}")
    print(f"  Missed MFE: {skip['missed_mfe']:.2f}%")

    # Comparison
    print("\n--- COMPARISON ---")
    if ai["trades"] > 0 and skip["count"] > 0:
        ai_total = ai["total_mfe"]
        skip_total = 0  # Strategy B gets 0 from uncertain

        print(f"  AI Total Value: {ai_total:.2f}%")
        print(f"  Skip Total Value: {skip_total:.2f}%")
        print(f"  AI Advantage: {ai_total - skip_total:.2f}%")

        if ai_total > 0:
            print("\n  [OK] AI ADDS VALUE in uncertain zones!")
        else:
            print("\n  ✗ Skipping uncertain is better")


if __name__ == "__main__":
    results, agent = run_comparison(limit=100)
    print_results(results, agent)
