#!/usr/bin/env python3
"""
Debug AI decision making - show a few examples with full reasoning.
"""

from pathlib import Path

import httpx
import psycopg2
from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).parent.parent / "local_agents" / "prompts"
env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=select_autoescape())
AI_TEMPLATE = env.get_template("ai_zone_decision.j2")

VLLM_URL = "http://localhost:8000"


def get_db_connection():
    return psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")


def load_top_agent(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, traits, trading_philosophy, assigned_patterns
        FROM agents WHERE status = 'active'
        ORDER BY fitness_score DESC LIMIT 1
    """)
    row = cur.fetchone()
    return {"id": row[0], "name": row[1], "traits": row[2] or {}, "philosophy": row[3] or "", "patterns": row[4] or {}}


def get_uncertain_candles(conn, limit=10):
    """Get candles that fall in the uncertain zone."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.time, c.close, c.rsi_14, c.stoch_k, c.adx_14,
               c.macd_line, c.macd_signal, c.supertrend_direction,
               cp.regime, cp.period_id
        FROM enhanced_candles c
        JOIN canonical_periods cp ON c.time BETWEEN cp.start_date::timestamp AND cp.end_date::timestamp
        WHERE c.symbol = 'BTC' AND c.timeframe = '1h'
        AND c.rsi_14 IS NOT NULL AND c.stoch_k IS NOT NULL
        AND c.rsi_14 BETWEEN 30 AND 70
        AND c.stoch_k BETWEEN 20 AND 80
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


def ask_ai_verbose(candle, agent):
    """Ask AI with full output."""
    indicators = {
        "rsi_14": float(candle["rsi_14"]) if candle["rsi_14"] is not None else "N/A",
        "stoch_k": float(candle["stoch_k"]) if candle["stoch_k"] is not None else "N/A",
        "adx_14": float(candle["adx_14"]) if candle["adx_14"] is not None else "N/A",
        "macd_line": float(candle["macd_line"]) if candle["macd_line"] is not None else "N/A",
        "macd_signal": float(candle["macd_signal"]) if candle["macd_signal"] is not None else "N/A",
        "supertrend": int(candle["supertrend_direction"]) if candle["supertrend_direction"] is not None else "N/A",
    }

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
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=30.0,
        )

        content = resp.json()["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        return f"ERROR: {e}"


def main():
    conn = get_db_connection()
    agent = load_top_agent(conn)
    candles = get_uncertain_candles(conn, limit=6)

    print(f"Agent: {agent['name']}")
    print("=" * 80)

    winners = 0
    losers = 0

    for i, candle in enumerate(candles):
        mfe, mae = get_forward_mfe(conn, candle["time"])
        is_winner = mfe > 1.5

        print(f"\n{'=' * 80}")
        print(f"CANDLE {i + 1}: {candle['time']}")
        print(
            f"  RSI: {float(candle['rsi_14']):.1f}  Stoch: {float(candle['stoch_k']):.1f}  ADX: {float(candle['adx_14']):.1f}"
        )
        print(f"  MACD: {float(candle['macd_line']):.4f}  Signal: {float(candle['macd_signal']):.4f}")
        print(f"  Supertrend: {candle['supertrend_direction']}  Regime: {candle['regime']}")
        print(f"  Forward MFE: {mfe:.2f}%  {'WINNER' if is_winner else 'LOSER'}")
        print("-" * 40)
        print("AI RESPONSE:")

        response = ask_ai_verbose(candle, agent)
        print(response)

        if is_winner:
            winners += 1
        else:
            losers += 1

    print("\n" + "=" * 80)
    print(f"Sample: {winners} winners, {losers} losers")
    conn.close()


if __name__ == "__main__":
    main()
