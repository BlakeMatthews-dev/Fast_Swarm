#!/usr/bin/env python3
"""
Comprehensive AI Fine-tuning Data Collection using Window Pool

Uses pre-generated windows from the window pool system for strategic sampling.
Processes one window at a time - fetch, process, commit, move on.

This creates labeled training data: (prompt, correct_answer) pairs.
"""

# Windows + psycopg3 fix: MUST be before any asyncio imports
import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
from jinja2 import Environment, FileSystemLoader

# Add parent to path for imports - avoid broken __init__.py
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import windows directly (bypass __init__.py with broken imports)
import importlib.util

windows_path = Path(__file__).parent.parent / "local_agents" / "backtest" / "windows.py"
spec = importlib.util.spec_from_file_location("windows", windows_path)
windows_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows_module)

init_window_pool = windows_module.initialize
get_windows_for_timeframe = windows_module.get_windows_for_timeframe
get_pool_stats = windows_module.get_pool_stats

# Load template
from jinja2 import select_autoescape

PROMPTS_DIR = Path(__file__).parent.parent / "local_agents" / "prompts"
env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=select_autoescape())
AI_TEMPLATE = env.get_template("ai_zone_decision.j2")

# vLLM runs in WSL - use WSL IP (get dynamically or use localhost if WSL2 mirrored networking)
import subprocess as _sp

try:
    _wsl_ip = _sp.check_output(["wsl", "hostname", "-I"], text=True).strip().split()[0]
    VLLM_URL = f"http://{_wsl_ip}:8000"
except Exception:
    VLLM_URL = "http://localhost:8000"
MFE_THRESHOLD = 1.5  # MFE > 1.5% = winner

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# JSONL file for easy viewing without SQL
JSONL_FILE = DATA_DIR / "ai_training_data.jsonl"


def ensure_vllm_running():
    """Check if vLLM is running, start it if not."""
    import subprocess
    import time

    try:
        resp = httpx.get(f"{VLLM_URL}/health", timeout=5.0)
        if resp.status_code == 200:
            print("vLLM already running")
            return True
    except Exception:
        pass

    print("Starting vLLM server in WSL...")
    # vLLM runs in WSL
    subprocess.Popen(
        ["wsl", "vllm", "serve", "Qwen/Qwen2.5-1.5B-Instruct", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for it to be ready (up to 60s)
    for i in range(60):
        time.sleep(1)
        try:
            resp = httpx.get(f"{VLLM_URL}/health", timeout=2.0)
            if resp.status_code == 200:
                print(f"  vLLM ready after {i + 1}s")
                return True
        except Exception:
            if i % 10 == 9:
                print(f"  Waiting... ({i + 1}s)")

    print("  WARNING: vLLM failed to start after 60s")
    return False


def get_db_connection():
    """PostgreSQL connection."""
    return psycopg2.connect(host="localhost", dbname="coinswarm", user="coinswarm", password="coinswarm_dev_2024")


def ensure_training_table(conn):
    """Create dedicated table for AI training data."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_training_decisions (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            candle_time TIMESTAMP NOT NULL,
            regime TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,

            -- Indicators at decision time
            rsi_14 REAL,
            stoch_k REAL,
            adx_14 REAL,
            macd_line REAL,
            macd_signal REAL,
            supertrend_direction INTEGER,

            -- AI decision
            ai_choice TEXT NOT NULL,
            ai_reasoning TEXT,

            -- Actual outcome
            forward_mfe REAL NOT NULL,
            forward_mae REAL,
            is_winner BOOLEAN NOT NULL,

            -- For training: what SHOULD have been the choice
            correct_choice TEXT NOT NULL,

            -- Full prompt for fine-tuning
            full_prompt TEXT,

            -- Full raw AI response (for training)
            ai_raw_response TEXT,

            -- Exit indicators at optimal exit point
            exit_indicators JSONB,

            -- Perfect response (what AI should output for training)
            perfect_response TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_training_regime ON ai_training_decisions(regime)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_training_winner ON ai_training_decisions(is_winner)")
    conn.commit()


def get_top_agents_by_regime(conn, limit_per_regime=20):
    """Get top N agents for each regime - only agents with fitness_by_regime data."""
    cur = conn.cursor()

    # Get distinct regimes from canonical_periods
    cur.execute("SELECT DISTINCT regime FROM canonical_periods WHERE regime IS NOT NULL")
    regimes = [r[0] for r in cur.fetchall()]

    agents_by_regime = {}
    for regime in regimes:
        # Get top agents for this regime - extract fitness from nested JSON
        cur.execute(
            """
            SELECT id, name, traits, trading_philosophy,
                   (fitness_by_regime->%s->>'fitness')::float as regime_fitness
            FROM agents
            WHERE status = 'active'
            AND fitness_by_regime IS NOT NULL
            AND fitness_by_regime != '{}'::jsonb
            AND fitness_by_regime ? %s
            ORDER BY (fitness_by_regime->%s->>'fitness')::float DESC NULLS LAST
            LIMIT %s
        """,
            (regime, regime, regime, limit_per_regime),
        )

        agents_by_regime[regime] = []
        for row in cur.fetchall():
            agents_by_regime[regime].append(
                {
                    "id": row[0],
                    "name": row[1],
                    "traits": row[2] or {},
                    "philosophy": row[3] or "",
                    "regime_fitness": row[4],
                }
            )

    return agents_by_regime


def get_candles_for_window(conn, window):
    """
    Get uncertain-zone candles within a specific window.

    Only fetches candles bounded by window timestamps - fast query!
    """
    cur = conn.cursor()

    # Convert millisecond timestamps to datetime
    start_dt = datetime.fromtimestamp(window.start_ts / 1000)
    end_dt = datetime.fromtimestamp(window.end_ts / 1000)

    cur.execute(
        """
        SELECT time, close, rsi_14, stoch_k, adx_14,
               macd_line, macd_signal, supertrend_direction
        FROM enhanced_candles
        WHERE symbol = %s AND timeframe = %s
        AND time >= %s AND time <= %s
        AND rsi_14 IS NOT NULL AND stoch_k IS NOT NULL
        AND rsi_14 BETWEEN 30 AND 70
        AND stoch_k BETWEEN 20 AND 80
        ORDER BY time
    """,
        (window.symbol, window.timeframe, start_dt, end_dt),
    )

    columns = ["time", "close", "rsi_14", "stoch_k", "adx_14", "macd_line", "macd_signal", "supertrend_direction"]

    results = []
    for row in cur.fetchall():
        d = dict(zip(columns, row, strict=False))
        d["symbol"] = window.symbol
        d["timeframe"] = window.timeframe
        results.append(d)
    return results


def get_forward_mfe(conn, candle, bars=24):
    """Get MFE/MAE, bars to MFE, and exit indicators for next N bars after entry."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT time, high, low, close, rsi_14, stoch_k, adx_14, macd_line, macd_signal
        FROM enhanced_candles
        WHERE symbol = %s AND timeframe = %s AND time > %s
        ORDER BY time LIMIT %s
    """,
        (candle["symbol"], candle["timeframe"], candle["time"], bars),
    )

    rows = cur.fetchall()
    if not rows:
        return 0, 0, 0, {}

    entry_price = float(candle["close"])
    if entry_price == 0:
        return 0, 0, 0, {}

    max_high = 0
    bars_to_mfe = 0
    exit_indicators = {}

    for i, r in enumerate(rows):
        high = float(r[1])
        if high > max_high:
            max_high = high
            bars_to_mfe = i + 1  # 1-indexed (how many bars to reach MFE)
            exit_indicators = {
                "exit_time": str(r[0]),
                "exit_rsi": float(r[4]) if r[4] else None,
                "exit_stoch": float(r[5]) if r[5] else None,
                "exit_adx": float(r[6]) if r[6] else None,
                "exit_macd": float(r[7]) if r[7] else None,
                "bars_to_mfe": bars_to_mfe,
            }

    min_low = min(float(r[2]) for r in rows)
    mfe = (max_high - entry_price) / entry_price * 100
    mae = (entry_price - min_low) / entry_price * 100
    return mfe, mae, bars_to_mfe, exit_indicators


def ask_ai(candle, agent):
    """Ask AI for decision, return choice, reasoning, and full prompt."""
    indicators = {
        "rsi_14": float(candle["rsi_14"]) if candle["rsi_14"] is not None else "N/A",
        "stoch_k": float(candle["stoch_k"]) if candle["stoch_k"] is not None else "N/A",
        "adx_14": float(candle["adx_14"]) if candle["adx_14"] is not None else "N/A",
        "macd_line": float(candle["macd_line"]) if candle["macd_line"] is not None else "N/A",
        "macd_signal": float(candle["macd_signal"]) if candle["macd_signal"] is not None else "N/A",
        "supertrend": int(candle["supertrend_direction"]) if candle["supertrend_direction"] is not None else "N/A",
    }

    prompt = AI_TEMPLATE.render(
        asset=candle["symbol"],
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

        # Parse reasoning
        reason_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', content)
        reasoning = reason_match.group(1) if reason_match else ""

        return choice, reasoning, prompt, content  # content = full raw response
    except Exception as e:
        return "ERROR", str(e), prompt, ""


def determine_correct_choice(mfe, is_winner):
    """Determine what the AI SHOULD have said based on outcome."""
    if mfe >= 3.0:
        return "SB"  # Strong winner
    elif is_winner:
        return "B"  # Winner
    elif mfe < 0.5:
        return "SS"  # Strong loser
    else:
        return "S"  # Loser/neutral


def run_collection(candles_per_symbol=50, agents_per_regime=20):
    """
    Run collection - simple sync approach, no window pool.

    1. Get list of symbols
    2. For each symbol: fetch N random uncertain candles, process
    3. Commit after each symbol
    """
    # Ensure vLLM is running before we start
    ensure_vllm_running()

    conn = get_db_connection()
    ensure_training_table(conn)

    # Known symbols with 1h data (skip slow DISTINCT query)
    symbols = [
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
        "ADA",
        "DOGE",
        "AVAX",
        "DOT",
        "MATIC",
        "LINK",
        "UNI",
        "ATOM",
        "LTC",
        "ETC",
        "XLM",
        "ALGO",
        "NEAR",
        "FTM",
        "AAVE",
    ]
    print(f"Using {len(symbols)} known symbols")
    cur = conn.cursor()

    print("\nLoading agents by regime...")
    agents_by_regime = get_top_agents_by_regime(conn, agents_per_regime)
    total_agents = sum(len(agents) for agents in agents_by_regime.values())
    print(f"  Regimes: {list(agents_by_regime.keys())}")
    print(f"  Total agents: {total_agents}")

    # Pick 5 random agents to use
    all_agents = []
    for agents in agents_by_regime.values():
        all_agents.extend(agents)
    import random

    sample_agents = random.sample(all_agents, min(5, len(all_agents)))
    print(f"  Using {len(sample_agents)} sample agents per candle")

    total_candles = 0
    total_inserted = 0

    for s_idx, symbol in enumerate(symbols):
        # Fetch N random uncertain candles for this symbol
        # Use bounded time range (last 90 days) for fast query
        cur.execute(
            """
            SELECT time, close, rsi_14, stoch_k, adx_14,
                   macd_line, macd_signal, supertrend_direction
            FROM enhanced_candles
            WHERE symbol = %s AND timeframe = '1h'
            AND time > NOW() - INTERVAL '90 days'
            AND rsi_14 IS NOT NULL AND stoch_k IS NOT NULL
            AND rsi_14 BETWEEN 30 AND 70
            AND stoch_k BETWEEN 20 AND 80
            ORDER BY time DESC
            LIMIT %s
        """,
            (symbol, candles_per_symbol),
        )

        columns = ["time", "close", "rsi_14", "stoch_k", "adx_14", "macd_line", "macd_signal", "supertrend_direction"]
        candles = []
        for row in cur.fetchall():
            d = dict(zip(columns, row, strict=False))
            d["symbol"] = symbol
            d["timeframe"] = "1h"
            candles.append(d)

        if not candles:
            continue

        print(f"\n[{s_idx + 1}/{len(symbols)}] {symbol}: {len(candles)} candles")

        for candle in candles:
            mfe, mae, bars_to_mfe, exit_indicators = get_forward_mfe(conn, candle)
            is_winner = mfe > MFE_THRESHOLD
            correct_choice = determine_correct_choice(mfe, is_winner)

            # Generate perfect response
            rsi = float(candle["rsi_14"]) if candle["rsi_14"] else 50
            stoch = float(candle["stoch_k"]) if candle["stoch_k"] else 50
            adx = float(candle["adx_14"]) if candle["adx_14"] else 25
            exit_rsi = exit_indicators.get("exit_rsi", 50) or 50
            exit_stoch = exit_indicators.get("exit_stoch", 50) or 50

            if correct_choice == "SB":
                perfect_reasoning = (
                    f"RSI {rsi:.0f} + Stoch {stoch:.0f} oversold with ADX {adx:.0f}. "
                    f"Similar setups historically gain {mfe:.1f}% in ~{bars_to_mfe} bars. "
                    f"Exit when RSI reaches {exit_rsi:.0f} and Stoch {exit_stoch:.0f}."
                )
            elif correct_choice == "B":
                perfect_reasoning = (
                    f"RSI {rsi:.0f}, Stoch {stoch:.0f}, ADX {adx:.0f} suggests edge. "
                    f"Historically ~{mfe:.1f}% in {bars_to_mfe} bars. "
                    f"Watch for RSI {exit_rsi:.0f}/Stoch {exit_stoch:.0f} to exit."
                )
            elif correct_choice == "SS":
                perfect_reasoning = (
                    f"RSI {rsi:.0f}, Stoch {stoch:.0f} not oversold enough. "
                    f"Similar setups historically underperform. No edge."
                )
            else:
                perfect_reasoning = (
                    f"RSI {rsi:.0f}, Stoch {stoch:.0f} neutral zone. No clear signal. Historically weak, skip."
                )

            perfect_response = json.dumps(
                {
                    "choice": correct_choice,
                    "reasoning": perfect_reasoning,
                    "expected_bars": bars_to_mfe if is_winner else None,
                    "exit_signal": f"RSI>{exit_rsi:.0f} or Stoch>{exit_stoch:.0f}" if is_winner else None,
                }
            )

            # Test with sample agents
            for agent in sample_agents:
                choice, reasoning, prompt, raw_response = ask_ai(candle, agent)

                cur.execute(
                    """
                    INSERT INTO ai_training_decisions (
                        candle_time, regime, agent_id, agent_name,
                        rsi_14, stoch_k, adx_14, macd_line, macd_signal, supertrend_direction,
                        ai_choice, ai_reasoning, forward_mfe, forward_mae, is_winner,
                        correct_choice, full_prompt, ai_raw_response, exit_indicators, perfect_response
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        candle["time"],
                        symbol,
                        agent["id"],
                        agent["name"],
                        candle["rsi_14"],
                        candle["stoch_k"],
                        candle["adx_14"],
                        candle["macd_line"],
                        candle["macd_signal"],
                        candle["supertrend_direction"],
                        choice,
                        reasoning,
                        mfe,
                        mae,
                        is_winner,
                        correct_choice,
                        prompt,
                        raw_response,
                        json.dumps(exit_indicators),
                        perfect_response,
                    ),
                )

                # JSONL output
                record = {
                    "candle_time": str(candle["time"]),
                    "symbol": symbol,
                    "agent": agent["name"],
                    "entry_indicators": {
                        "rsi": rsi,
                        "stoch": stoch,
                        "adx": adx,
                        "macd": candle["macd_line"],
                        "supertrend": candle["supertrend_direction"],
                    },
                    "ai_choice": choice,
                    "ai_reasoning": reasoning,
                    "correct_choice": correct_choice,
                    "is_winner": is_winner,
                    "mfe": round(mfe, 2),
                    "bars_to_mfe": bars_to_mfe,
                    "exit_indicators": exit_indicators,
                    "perfect_response": json.loads(perfect_response),
                }
                with open(JSONL_FILE, "a") as f:
                    f.write(json.dumps(record) + "\n")

                total_inserted += 1

            total_candles += 1

        # Commit after each symbol
        conn.commit()
        print(f"  [OK] {total_candles} candles, {total_inserted} records")

    conn.close()

    print(f"\n{'=' * 60}")
    print("COLLECTION COMPLETE")
    print(f"  Symbols processed: {len(symbols)}")
    print(f"  Total candles: {total_candles}")
    print(f"  Total records: {total_inserted}")
    print(f"  JSONL: {JSONL_FILE}")


def print_summary(conn=None):
    """Print summary of collected data."""
    if conn is None:
        conn = get_db_connection()

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM ai_training_decisions")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT
            ai_choice,
            COUNT(*) as cnt,
            SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as winners,
            AVG(forward_mfe) as avg_mfe
        FROM ai_training_decisions
        GROUP BY ai_choice
        ORDER BY cnt DESC
    """)

    print(f"\n{'=' * 60}")
    print(f"AI DECISION SUMMARY ({total} total)")
    print(f"{'=' * 60}")
    print(f"{'Choice':<10} {'Count':<10} {'Winners':<10} {'Win Rate':<10} {'Avg MFE':<10}")
    print("-" * 50)

    for row in cur.fetchall():
        choice, cnt, winners, avg_mfe = row
        win_rate = winners / cnt * 100 if cnt > 0 else 0
        print(f"{choice:<10} {cnt:<10} {winners:<10} {win_rate:<10.1f}% {avg_mfe:<10.2f}%")

    # Accuracy: how often AI matched correct choice
    cur.execute("""
        SELECT
            COUNT(CASE WHEN ai_choice = correct_choice THEN 1 END) as correct,
            COUNT(*) as total
        FROM ai_training_decisions
    """)
    correct, total = cur.fetchone()
    print(f"\nOverall Accuracy: {correct}/{total} ({correct / total * 100:.1f}%)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        print_summary()
    else:
        # Default: 50 candles per symbol, 20 symbols = 1000 candles * 5 agents = 5000 records
        candles_per_symbol = int(sys.argv[1]) if len(sys.argv) > 1 else 50
        print(f"Starting collection: {candles_per_symbol} candles per symbol")
        print("Processing symbol-by-symbol (sync, no memory buildup)")
        run_collection(candles_per_symbol=candles_per_symbol, agents_per_regime=20)
        print_summary()
