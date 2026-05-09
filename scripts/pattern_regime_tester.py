"""
Pattern Regime Tester - Standalone process for testing patterns across regime x timeframe matrix.

Runs INDEPENDENTLY of main FastAPI server. Uses local_agents backtest engine directly.

Features:
- Live terminal dashboard with progress stats
- Tests ALL regimes: crash, bear, bull, recovery, blowoff, sideways
- Tests ALL timeframes: 1m, 5m, 15m, 1h, 4h, 1d
- Generates random windows per timeframe (random_1m, random_5m, etc.)
- Stores full matrix: fitness_matrix[regime][timeframe] = {fitness, trades, windows}
- Ctrl+C to stop

Usage:
    python scripts/pattern_regime_tester.py              # Run with live dashboard
    python scripts/pattern_regime_tester.py --stats      # Show stats and exit
    python scripts/pattern_regime_tester.py --no-dash    # Run without dashboard
    python scripts/pattern_regime_tester.py --matrix     # Show matrix view
"""

import argparse
import random
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "local_agents"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.canonical_periods import get_canonical_periods_for_backtesting
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits

# ALL regimes and timeframes for complete matrix
ALL_REGIMES = ["crash", "bear", "bull", "recovery", "blowoff", "sideways"]
ALL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
TEST_ASSETS = ["BTC", "ETH", "SOL"]

# Random window settings per timeframe
RANDOM_WINDOWS_PER_TF = 10  # 10 random windows per timeframe
TIMEFRAME_WINDOW_CONFIG = {
    "1m": {"candles": 1440, "ms": 60 * 1000},  # 1 day of 1m candles
    "5m": {"candles": 576, "ms": 5 * 60 * 1000},  # 2 days of 5m candles
    "15m": {"candles": 384, "ms": 15 * 60 * 1000},  # 4 days of 15m candles
    "1h": {"candles": 500, "ms": 60 * 60 * 1000},  # ~21 days of 1h candles
    "4h": {"candles": 180, "ms": 4 * 60 * 60 * 1000},  # 30 days of 4h candles
    "1d": {"candles": 90, "ms": 24 * 60 * 60 * 1000},  # 90 days of 1d candles
}

# Global stop flag
STOP_FLAG = False


def signal_handler(sig, frame):
    global STOP_FLAG
    STOP_FLAG = True


signal.signal(signal.SIGINT, signal_handler)


def get_db_connection():
    """Get sync database connection."""
    import os

    import psycopg

    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "coinswarm"),
        user=os.getenv("POSTGRES_USER", "coinswarm"),
        password=os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024"),
    )


def get_data_ranges(conn) -> dict[str, dict]:
    """Get available data ranges per asset/timeframe."""
    ranges = {}
    with conn.cursor() as cur:
        for tf in ALL_TIMEFRAMES:
            cur.execute(
                """
                SELECT symbol, MIN(time), MAX(time), COUNT(*)
                FROM enhanced_candles
                WHERE timeframe = %s
                GROUP BY symbol
            """,
                (tf,),
            )
            for row in cur.fetchall():
                symbol, min_time, max_time, count = row
                asset = symbol.replace("/USDT", "").replace("-USD", "")
                if asset not in ranges:
                    ranges[asset] = {}
                ranges[asset][tf] = {
                    "min_ts": int(min_time.timestamp() * 1000) if min_time else 0,
                    "max_ts": int(max_time.timestamp() * 1000) if max_time else 0,
                    "count": count,
                }
    return ranges


def generate_random_windows(data_ranges: dict, timeframe: str, count: int = 10) -> list[dict]:
    """Generate random test windows for a timeframe."""
    windows = []
    config = TIMEFRAME_WINDOW_CONFIG.get(timeframe)
    if not config:
        return windows

    window_ms = config["candles"] * config["ms"]

    for asset in TEST_ASSETS:
        if asset not in data_ranges or timeframe not in data_ranges[asset]:
            continue

        range_info = data_ranges[asset][timeframe]
        available_range = range_info["max_ts"] - range_info["min_ts"] - window_ms

        if available_range <= 0 or range_info["count"] < config["candles"]:
            continue

        for _ in range(count):
            start_ts = range_info["min_ts"] + random.randint(0, int(available_range))
            end_ts = start_ts + window_ms
            windows.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "regime": f"random_{timeframe}",
                }
            )

    return windows


def get_stats(conn) -> dict:
    """Get current testing stats."""
    with conn.cursor() as cur:
        # Pattern counts
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE entry_conditions IS NULL
                    OR entry_conditions = '[]'::jsonb
                    OR jsonb_array_length(entry_conditions) = 0) as invalid,
                COUNT(*) FILTER (WHERE fitness_matrix IS NOT NULL
                    AND fitness_matrix != '{}'::jsonb) as matrix_tested,
                COUNT(*) FILTER (WHERE fitness_by_regime IS NOT NULL
                    AND fitness_by_regime != '{}'::jsonb) as regime_tested,
                COUNT(*) FILTER (WHERE is_active = true) as active
            FROM patterns
        """)
        row = cur.fetchone()
        total, invalid, matrix_tested, regime_tested, active = row

        # Matrix coverage (how many regime x timeframe combos tested)
        cur.execute("""
            SELECT
                regime_key,
                COUNT(DISTINCT pattern_id) as patterns,
                ROUND(AVG(avg_fitness)::numeric, 2) as avg_fitness
            FROM (
                SELECT
                    p.pattern_id,
                    regime.key as regime_key,
                    (SELECT AVG((tf.value->>'fitness')::float)
                     FROM jsonb_each(regime.value) tf
                     WHERE tf.value->>'fitness' IS NOT NULL) as avg_fitness
                FROM patterns p,
                     jsonb_each(fitness_matrix) regime
                WHERE fitness_matrix IS NOT NULL
                  AND fitness_matrix != '{}'::jsonb
            ) sub
            WHERE avg_fitness IS NOT NULL
            GROUP BY regime_key
            ORDER BY avg_fitness ASC
        """)
        regime_rows = cur.fetchall()

        return {
            "total": total,
            "invalid": invalid,
            "matrix_tested": matrix_tested,
            "regime_tested": regime_tested,
            "active": active,
            "need_testing": total - invalid - matrix_tested,
            "regime_fitness": {row[0]: {"count": row[1], "avg": float(row[2]) if row[2] else 0} for row in regime_rows},
        }


def get_patterns_needing_test(conn, batch_size: int = 20) -> list[dict]:
    """Get patterns that need matrix testing."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.pattern_id,
                p.name,
                p.entry_conditions,
                p.exit_conditions,
                p.fitness_score,
                p.is_active
            FROM patterns p
            WHERE p.entry_conditions IS NOT NULL
              AND p.entry_conditions != '[]'::jsonb
              AND jsonb_array_length(p.entry_conditions) > 0
              AND (p.fitness_matrix IS NULL OR p.fitness_matrix = '{}'::jsonb)
            ORDER BY COALESCE(p.fitness_score, 0) ASC
            LIMIT %s
        """,
            (batch_size,),
        )

        rows = cur.fetchall()
        return [
            {
                "pattern_id": row[0],
                "name": row[1] or "unnamed",
                "entry_conditions": row[2],
                "exit_conditions": row[3],
                "fitness_score": row[4] or 0,
                "is_active": row[5],
            }
            for row in rows
        ]


def delete_invalid_patterns(conn) -> int:
    """Delete patterns without valid entry conditions."""
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM patterns
            WHERE entry_conditions IS NULL
               OR entry_conditions = '[]'::jsonb
               OR jsonb_array_length(entry_conditions) = 0
            RETURNING pattern_id
        """)
        deleted = cur.fetchall()
        conn.commit()
        return len(deleted)


def calculate_metrics(trades: list) -> dict:
    """Calculate fitness from trades."""
    if not trades:
        return {"fitness": 0.0, "total_trades": 0, "win_rate": 0.0}

    total = len(trades)
    wins = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = wins / total if total > 0 else 0

    returns = [t.pnl_pct for t in trades]
    mean_return = sum(returns) / len(returns) if returns else 0

    import statistics

    if len(returns) > 1:
        std = statistics.stdev(returns)
        sharpe = (mean_return / std) if std > 0 else 0
    else:
        sharpe = 0

    fitness = (sharpe * 10) + (win_rate * 50) + (mean_return * 5)
    fitness = max(0, min(100, fitness))

    return {"fitness": round(fitness, 2), "total_trades": total, "win_rate": round(win_rate, 4)}


def test_single_pattern(pattern: dict, data_ranges: dict) -> dict:
    """Test one pattern across full regime x timeframe matrix."""
    loader = OHLCVLoader()
    default_traits = AgentTraits()
    config = BacktestConfig.from_traits(default_traits)

    pattern_dict = {
        pattern["pattern_id"]: {
            "pattern_id": pattern["pattern_id"],
            "entry_conditions": pattern["entry_conditions"],
            "exit_conditions": pattern["exit_conditions"] or [],
        }
    }

    test_agent = AgentRecord(
        agent_id=f"matrix_test_{pattern['pattern_id'][:8]}",
        agent_name=f"Test_{pattern['name'][:15]}",
        traits=default_traits.__dict__,
        pattern_ids=[pattern["pattern_id"]],
        pattern_weights={pattern["pattern_id"]: 1.0},
    )

    # Build full matrix: regime -> timeframe -> {fitness, trades, windows}
    fitness_matrix = {}

    # 1. Test canonical periods (crash, bear, bull, etc.) at each timeframe
    for timeframe in ALL_TIMEFRAMES:
        canonical_periods = get_canonical_periods_for_backtesting(
            assets=TEST_ASSETS,
            timeframes=[timeframe],
            regimes=ALL_REGIMES,
        )

        for period in canonical_periods:
            regime = period["regime"]
            if regime not in fitness_matrix:
                fitness_matrix[regime] = {}
            if timeframe not in fitness_matrix[regime]:
                fitness_matrix[regime][timeframe] = {"results": []}

            try:
                engine = LocalBacktestEngine(loader=loader, config=config, patterns=pattern_dict)
                trades = engine.run(
                    agent=test_agent,
                    dataset={
                        "assets": [period["asset"]],
                        "timeframe": timeframe,
                        "start_ts": period["start_ts"],
                        "end_ts": period["end_ts"],
                    },
                )
                metrics = calculate_metrics(trades)
                fitness_matrix[regime][timeframe]["results"].append(metrics)
            except Exception:
                continue

    # 2. Test random windows at each timeframe
    for timeframe in ALL_TIMEFRAMES:
        random_windows = generate_random_windows(data_ranges, timeframe, count=RANDOM_WINDOWS_PER_TF)
        regime_key = f"random_{timeframe}"

        if regime_key not in fitness_matrix:
            fitness_matrix[regime_key] = {}
        if timeframe not in fitness_matrix[regime_key]:
            fitness_matrix[regime_key][timeframe] = {"results": []}

        for window in random_windows:
            try:
                engine = LocalBacktestEngine(loader=loader, config=config, patterns=pattern_dict)
                trades = engine.run(
                    agent=test_agent,
                    dataset={
                        "assets": [window["asset"]],
                        "timeframe": timeframe,
                        "start_ts": window["start_ts"],
                        "end_ts": window["end_ts"],
                    },
                )
                metrics = calculate_metrics(trades)
                fitness_matrix[regime_key][timeframe]["results"].append(metrics)
            except Exception:
                continue

    # 3. Aggregate results per regime x timeframe
    final_matrix = {}
    best_regime, best_fitness = None, 0.0
    best_timeframe = None

    for regime, tf_data in fitness_matrix.items():
        final_matrix[regime] = {}
        regime_total_fitness = 0
        regime_count = 0

        for timeframe, data in tf_data.items():
            results = data.get("results", [])
            if results:
                avg_fitness = sum(r["fitness"] for r in results) / len(results)
                total_trades = sum(r["total_trades"] for r in results)
                final_matrix[regime][timeframe] = {
                    "fitness": round(avg_fitness, 2),
                    "trades": total_trades,
                    "windows": len(results),
                }
                regime_total_fitness += avg_fitness
                regime_count += 1

                if avg_fitness > best_fitness:
                    best_fitness = avg_fitness
                    best_regime = regime
                    best_timeframe = timeframe

    # 4. Also compute regime-level averages (across all timeframes)
    fitness_by_regime = {}
    for regime, tf_data in final_matrix.items():
        if tf_data:
            avg = sum(d["fitness"] for d in tf_data.values()) / len(tf_data)
            total_trades = sum(d["trades"] for d in tf_data.values())
            fitness_by_regime[regime] = {
                "fitness": round(avg, 2),
                "trades": total_trades,
                "timeframes": len(tf_data),
            }

    return {
        "pattern_id": pattern["pattern_id"],
        "fitness_matrix": final_matrix,
        "fitness_by_regime": fitness_by_regime,
        "best_regime": best_regime,
        "best_timeframe": best_timeframe,
        "best_regime_fitness": best_fitness,
    }


def update_pattern(conn, result: dict):
    """Save pattern matrix results."""
    import json

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE patterns
            SET fitness_matrix = %s,
                fitness_by_regime = %s,
                best_regime = %s,
                best_regime_fitness = %s,
                last_backtest_at = NOW()
            WHERE pattern_id = %s
        """,
            (
                json.dumps(result.get("fitness_matrix", {})),
                json.dumps(result.get("fitness_by_regime", {})),
                result.get("best_regime"),
                result.get("best_regime_fitness"),
                result["pattern_id"],
            ),
        )
    conn.commit()


def run_with_dashboard(batch_size: int = 10, workers: int = 4):
    """Run with live Rich dashboard."""
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()

    # Stats tracking
    session_start = datetime.now()
    total_tested = 0
    total_deleted = 0
    current_batch = []
    last_results = []
    rate_history = []

    def make_dashboard(stats: dict, current: str = "") -> Layout:
        layout = Layout()

        # Header
        elapsed = (datetime.now() - session_start).total_seconds()
        rate = total_tested / elapsed * 3600 if elapsed > 0 else 0

        header = Table.grid()
        header.add_column()
        header.add_row(Text("PATTERN REGIME x TIMEFRAME MATRIX TESTER", style="bold cyan"))
        header.add_row(Text(f"Ctrl+C to stop | Elapsed: {elapsed / 60:.1f}m | Rate: {rate:.0f}/hr", style="dim"))

        # Main stats table
        stats_table = Table(title="Progress", show_header=True, header_style="bold")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")
        stats_table.add_row("Total Patterns", f"{stats.get('total', 0):,}")
        stats_table.add_row("Invalid", f"{stats.get('invalid', 0):,}")
        stats_table.add_row("Matrix Tested", f"{stats.get('matrix_tested', 0):,}")
        stats_table.add_row("Need Testing", f"{stats.get('need_testing', 0):,}")
        stats_table.add_row("", "")
        stats_table.add_row("Session Tested", f"{total_tested:,}")
        stats_table.add_row("Session Deleted", f"{total_deleted:,}")

        # Regime fitness table (aggregated across timeframes)
        regime_table = Table(title="Regime Fitness (avg across TFs)", show_header=True, header_style="bold")
        regime_table.add_column("Regime", style="cyan")
        regime_table.add_column("Avg Fitness", justify="right")
        regime_table.add_column("Patterns", justify="right")
        regime_table.add_column("Status")

        regime_data = stats.get("regime_fitness", {})
        all_regimes = ALL_REGIMES + [f"random_{tf}" for tf in ALL_TIMEFRAMES]
        for regime in all_regimes:
            if regime in regime_data:
                avg = regime_data[regime]["avg"]
                cnt = regime_data[regime]["count"]
                if avg < 20:
                    status = "[red]CRITICAL[/red]"
                elif avg < 40:
                    status = "[yellow]Weak[/yellow]"
                else:
                    status = "[green]OK[/green]"
                regime_table.add_row(regime, f"{avg:.1f}", str(cnt), status)
            else:
                regime_table.add_row(regime, "-", "0", "[dim]No data[/dim]")

        # Current activity
        activity = Text(current or "Idle...", style="dim")

        # Compose layout
        layout.split_column(
            Layout(Panel(header), size=4),
            Layout(name="main"),
            Layout(Panel(activity, title="Current"), size=3),
        )
        layout["main"].split_row(
            Layout(Panel(stats_table)),
            Layout(Panel(regime_table)),
        )

        return layout

    # Main loop
    conn = get_db_connection()

    try:
        # Initial cleanup
        deleted = delete_invalid_patterns(conn)
        total_deleted = deleted

        # Get data ranges for random window generation
        data_ranges = get_data_ranges(conn)

        with Live(make_dashboard(get_stats(conn)), refresh_per_second=2, console=console) as live:
            while not STOP_FLAG:
                stats = get_stats(conn)

                if stats["need_testing"] == 0:
                    live.update(make_dashboard(stats, "Queue empty - waiting..."))
                    time.sleep(10)
                    continue

                # Get batch
                patterns = get_patterns_needing_test(conn, batch_size)
                if not patterns:
                    time.sleep(5)
                    continue

                live.update(make_dashboard(stats, f"Testing batch of {len(patterns)} patterns..."))

                # Test in parallel
                batch_start = time.time()
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(test_single_pattern, p, data_ranges): p for p in patterns}

                    for future in as_completed(futures):
                        if STOP_FLAG:
                            break

                        try:
                            result = future.result(timeout=300)  # 5 min timeout per pattern
                            if "error" not in result:
                                update_pattern(conn, result)
                                total_tested += 1
                                best = result.get("best_regime", "?")
                                best_tf = result.get("best_timeframe", "?")
                                fit = result.get("best_regime_fitness", 0)
                                live.update(
                                    make_dashboard(
                                        get_stats(conn),
                                        f"Tested {result['pattern_id'][:12]}... best={best}@{best_tf} ({fit:.1f})",
                                    )
                                )
                        except Exception:
                            pass

                batch_time = time.time() - batch_start
                rate = len(patterns) / batch_time * 3600 if batch_time > 0 else 0
                rate_history.append(rate)

    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        console.print("\n[bold green]Session complete![/bold green]")
        console.print(f"Tested: {total_tested} | Deleted: {total_deleted}")


def show_stats():
    """Show stats and exit."""
    conn = get_db_connection()
    try:
        stats = get_stats(conn)
        print()
        print("=" * 60)
        print("PATTERN REGIME x TIMEFRAME MATRIX TESTER STATS")
        print("=" * 60)
        print(f"Total patterns:      {stats['total']:,}")
        print(f"Invalid (delete):    {stats['invalid']:,}")
        print(f"Matrix tested:       {stats['matrix_tested']:,}")
        print(f"Need testing:        {stats['need_testing']:,}")
        print()
        print("Regime Fitness (averaged across timeframes):")
        all_regimes = ALL_REGIMES + [f"random_{tf}" for tf in ALL_TIMEFRAMES]
        for regime in all_regimes:
            data = stats["regime_fitness"].get(regime, {})
            if data:
                print(f"  {regime:14} avg={data['avg']:5.1f}  patterns={data['count']}")
            else:
                print(f"  {regime:14} (no data)")
        print("=" * 60)
    finally:
        conn.close()


def show_matrix():
    """Show full matrix view of top patterns."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get patterns with matrix data
            cur.execute("""
                SELECT
                    p.pattern_id,
                    p.name,
                    p.fitness_matrix,
                    p.best_regime,
                    p.best_regime_fitness
                FROM patterns p
                WHERE p.fitness_matrix IS NOT NULL
                  AND p.fitness_matrix != '{}'::jsonb
                ORDER BY p.best_regime_fitness DESC
                LIMIT 20
            """)
            rows = cur.fetchall()

        if not rows:
            print("No patterns with matrix data yet. Run the tester first.")
            return

        print()
        print("=" * 120)
        print("TOP PATTERNS - REGIME x TIMEFRAME MATRIX")
        print("=" * 120)
        print()

        # Header
        header = f"{'Pattern':<20} | {'Best':<15} |"
        for regime in ["crash", "bear", "bull", "recovery"]:
            header += f" {regime:^8} |"
        print(header)
        print("-" * 120)

        for row in rows:
            pid, name, matrix, best_regime, best_fitness = row
            name_short = (name or pid[:15])[:18]
            best_str = f"{best_regime or '?'}:{best_fitness or 0:.0f}"

            line = f"{name_short:<20} | {best_str:<15} |"

            for regime in ["crash", "bear", "bull", "recovery"]:
                if regime in matrix:
                    # Find best timeframe for this regime
                    best_tf, best_f = None, 0
                    for tf, data in matrix[regime].items():
                        if isinstance(data, dict) and data.get("fitness", 0) > best_f:
                            best_f = data["fitness"]
                            best_tf = tf
                    if best_tf:
                        line += f" {best_tf}-{best_f:.0f}".center(8) + " |"
                    else:
                        line += "    -    |"
                else:
                    line += "    -    |"

            print(line)

        print("-" * 120)
        print()

        # Show best regime breakdown for top pattern
        if rows:
            top = rows[0]
            pid, name, matrix, best_regime, best_fitness = top
            print(f"TOP PATTERN: {name or pid}")
            print(f"Best: {best_regime} @ {best_fitness:.1f}")
            print()
            if best_regime and best_regime in matrix:
                print(f"All timeframes for {best_regime}:")
                for tf in ALL_TIMEFRAMES:
                    if tf in matrix[best_regime]:
                        data = matrix[best_regime][tf]
                        if isinstance(data, dict):
                            print(
                                f"  {tf:>4}: {data.get('fitness', 0):5.1f} ({data.get('trades', 0)} trades, {data.get('windows', 0)} windows)"
                            )

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Pattern Regime x Timeframe Matrix Tester")
    parser.add_argument(
        "--batch-size", type=int, default=5, help="Patterns per batch (default 5 - matrix tests are heavy)"
    )
    parser.add_argument("--workers", type=int, default=2, help="Parallel workers (default 2)")
    parser.add_argument("--stats", action="store_true", help="Show stats and exit")
    parser.add_argument("--matrix", action="store_true", help="Show matrix view and exit")
    parser.add_argument("--no-dash", action="store_true", help="Run without dashboard")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.matrix:
        show_matrix()
    elif args.no_dash:
        # Simple loop without rich
        conn = get_db_connection()
        data_ranges = get_data_ranges(conn)
        try:
            while not STOP_FLAG:
                patterns = get_patterns_needing_test(conn, args.batch_size)
                if not patterns:
                    print("Queue empty, waiting...")
                    time.sleep(30)
                    continue

                for p in patterns:
                    if STOP_FLAG:
                        break
                    result = test_single_pattern(p, data_ranges)
                    if "error" not in result:
                        update_pattern(conn, result)
                        print(
                            f"Tested {p['pattern_id'][:12]}... best={result.get('best_regime')}@{result.get('best_timeframe')}"
                        )
        finally:
            conn.close()
    else:
        run_with_dashboard(args.batch_size, args.workers)


if __name__ == "__main__":
    main()
