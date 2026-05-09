#!/usr/bin/env python3
"""
Terminal Regime x Timeframe Heatmap for Agent Fitness.

Displays a 2D matrix showing agent performance across:
- Regimes: crash, bull, bear, sideways, blowoff, recovery, random
- Timeframes: 1m, 5m, 15m, 1h, 4h, 1d

Usage:
    python scripts/show_regime_heatmap.py --top 20
    python scripts/show_regime_heatmap.py --agent agent_abc123
    python scripts/show_regime_heatmap.py --regime crash --top 10
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ANSI color codes for terminal
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    DIM = "\033[2m"


def fitness_color(fitness: float) -> str:
    """Return color code based on fitness score."""
    if fitness >= 70:
        return Colors.GREEN
    elif fitness >= 50:
        return Colors.CYAN
    elif fitness >= 30:
        return Colors.YELLOW
    else:
        return Colors.RED


def format_cell(fitness: float, width: int = 6) -> str:
    """Format a fitness value with color."""
    if fitness == 0:
        return f"{Colors.DIM}{'--':^{width}}{Colors.RESET}"
    color = fitness_color(fitness)
    return f"{color}{fitness:>{width}.0f}{Colors.RESET}"


def get_best_tf_for_regime(matrix: dict, regime: str) -> tuple:
    """Get best timeframe and fitness for a regime."""
    if regime not in matrix or not matrix[regime]:
        return None, 0
    best_tf = max(matrix[regime].items(), key=lambda x: x[1])
    return best_tf[0], best_tf[1]


def get_best_regime(matrix: dict) -> tuple:
    """Get the regime with highest average fitness."""
    if not matrix:
        return None, 0, {}

    best_regime = None
    best_avg = 0
    best_tfs = {}

    for regime, tfs in matrix.items():
        if tfs:
            avg = sum(tfs.values()) / len(tfs)
            if avg > best_avg:
                best_avg = avg
                best_regime = regime
                best_tfs = tfs

    return best_regime, best_avg, best_tfs


def print_heatmap(agents: list[dict], regimes: list[str] = None, timeframes: list[str] = None):
    """Print the regime x timeframe heatmap for multiple agents."""

    # Default regimes and timeframes to display
    if regimes is None:
        regimes = ["crash", "bear", "bull", "sideways", "random", "recovery", "blowoff"]
    if timeframes is None:
        timeframes = ["1m", "15m", "1h", "4h", "1d"]

    # Column widths
    name_width = 20
    regime_width = 8
    best_width = 40

    # Print header
    header = f"{'Agent':<{name_width}}"
    for regime in regimes:
        header += f" | {regime[:regime_width]:^{regime_width}}"
    header += f" | {'Best Performance':<{best_width}}"

    print()
    print(f"{Colors.BOLD}Regime x Timeframe Fitness Heatmap{Colors.RESET}")
    print("=" * len(header.replace(Colors.BOLD, "").replace(Colors.RESET, "")))
    print(f"{Colors.BOLD}{header}{Colors.RESET}")
    print("-" * len(header))

    # Print each agent
    for agent in agents:
        name = agent.get("name", agent.get("agent_id", "Unknown"))[:name_width]
        matrix = agent.get("fitness_matrix", {})

        row = f"{name:<{name_width}}"

        for regime in regimes:
            best_tf, fitness = get_best_tf_for_regime(matrix, regime)
            if best_tf and fitness > 0:
                cell = f"{best_tf}-{fitness:.0f}"
            else:
                cell = "--"
            row += f" | {cell:^{regime_width}}"

        # Best regime column
        best_regime, best_avg, best_tfs = get_best_regime(matrix)
        if best_regime and best_tfs:
            # Sort timeframes by fitness descending
            sorted_tfs = sorted(best_tfs.items(), key=lambda x: x[1], reverse=True)
            tf_str = ", ".join(f"{tf}={f:.0f}" for tf, f in sorted_tfs[:4])
            best_col = f"{best_regime}: {tf_str}"[:best_width]
        else:
            best_col = "No data"

        # Color the best regime name
        if best_avg >= 70:
            color = Colors.GREEN
        elif best_avg >= 50:
            color = Colors.CYAN
        else:
            color = Colors.RESET

        row += f" | {color}{best_col:<{best_width}}{Colors.RESET}"
        print(row)

    print()
    print(
        f"{Colors.DIM}Legend: cell format = best_timeframe-fitness | Color: "
        f"{Colors.GREEN}>=70{Colors.RESET}{Colors.DIM}, "
        f"{Colors.CYAN}>=50{Colors.RESET}{Colors.DIM}, "
        f"{Colors.YELLOW}>=30{Colors.RESET}{Colors.DIM}, "
        f"{Colors.RED}<30{Colors.RESET}"
    )
    print()


def print_single_agent_matrix(agent: dict, timeframes: list[str] = None):
    """Print detailed matrix for a single agent."""

    if timeframes is None:
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

    name = agent.get("name", agent.get("agent_id", "Unknown"))
    matrix = agent.get("fitness_matrix", {})
    fitness_score = agent.get("fitness_score", 0)

    print()
    print(f"{Colors.BOLD}Agent: {name}{Colors.RESET}")
    print(f"Overall Fitness: {fitness_color(fitness_score)}{fitness_score:.1f}{Colors.RESET}")
    print()

    # Get all regimes that have data
    regimes = sorted(matrix.keys())
    if not regimes:
        print("No fitness matrix data available for this agent.")
        return

    # Column width
    col_width = 8

    # Header row
    header = f"{'Regime':<12}"
    for tf in timeframes:
        header += f" | {tf:^{col_width}}"
    header += f" | {'Avg':^{col_width}}"

    print(f"{Colors.BOLD}{header}{Colors.RESET}")
    print("-" * len(header))

    # Data rows
    for regime in regimes:
        row = f"{regime:<12}"
        values = []

        for tf in timeframes:
            fitness = matrix.get(regime, {}).get(tf, 0)
            if fitness > 0:
                values.append(fitness)
            row += f" | {format_cell(fitness, col_width)}"

        # Average
        avg = sum(values) / len(values) if values else 0
        row += f" | {format_cell(avg, col_width)}"
        print(row)

    # Column averages
    print("-" * len(header))
    avg_row = f"{'Avg':<12}"
    for tf in timeframes:
        col_values = [matrix.get(r, {}).get(tf, 0) for r in regimes]
        col_values = [v for v in col_values if v > 0]
        avg = sum(col_values) / len(col_values) if col_values else 0
        avg_row += f" | {format_cell(avg, col_width)}"
    print(avg_row)
    print()


def main():
    parser = argparse.ArgumentParser(description="Display regime x timeframe fitness heatmap")
    parser.add_argument("--top", type=int, default=20, help="Number of top agents to display")
    parser.add_argument("--agent", type=str, help="Show detailed matrix for specific agent")
    parser.add_argument("--regime", type=str, help="Filter/sort by specific regime")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of table")
    args = parser.parse_args()

    # Connect to database
    import psycopg

    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "coinswarm"),
        user=os.getenv("POSTGRES_USER", "coinswarm"),
        password=os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024"),
    )
    cur = conn.cursor()

    try:
        if args.agent:
            # Show detailed matrix for single agent
            cur.execute(
                """
                SELECT agent_id, name, fitness_score, fitness_matrix
                FROM agents
                WHERE agent_id = %s OR name ILIKE %s
                LIMIT 1
            """,
                (args.agent, f"%{args.agent}%"),
            )
            row = cur.fetchone()

            if row:
                agent = {
                    "agent_id": row[0],
                    "name": row[1],
                    "fitness_score": float(row[2]) if row[2] else 0,
                    "fitness_matrix": row[3] or {},
                }
                print_single_agent_matrix(agent)
            else:
                print(f"Agent not found: {args.agent}")
        else:
            # Show heatmap for top agents
            if args.regime:
                # Sort by specific regime fitness
                cur.execute(
                    """
                    SELECT agent_id, name, fitness_score, fitness_matrix,
                           fitness_by_regime->%s->>'fitness' as regime_fitness
                    FROM agents
                    WHERE status = 'active'
                      AND fitness_matrix IS NOT NULL
                      AND fitness_matrix != '{}'::jsonb
                    ORDER BY (fitness_by_regime->%s->>'fitness')::float DESC NULLS LAST
                    LIMIT %s
                """,
                    (args.regime, args.regime, args.top),
                )
            else:
                # Sort by overall fitness
                cur.execute(
                    """
                    SELECT agent_id, name, fitness_score, fitness_matrix
                    FROM agents
                    WHERE status = 'active'
                      AND fitness_matrix IS NOT NULL
                      AND fitness_matrix != '{}'::jsonb
                    ORDER BY fitness_score DESC NULLS LAST
                    LIMIT %s
                """,
                    (args.top,),
                )

            rows = cur.fetchall()

            if not rows:
                print("No agents with fitness matrix data found.")
                print("Run a backtest first to populate fitness_matrix.")
                return

            agents = []
            for row in rows:
                agents.append(
                    {
                        "agent_id": row[0],
                        "name": row[1],
                        "fitness_score": float(row[2]) if row[2] else 0,
                        "fitness_matrix": row[3] or {},
                    }
                )

            if args.json:
                import json

                print(json.dumps(agents, indent=2, default=str))
            else:
                print_heatmap(agents)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
