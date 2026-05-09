import json
import os
from datetime import datetime

import psycopg

STATS_HISTORY_FILE = "stats_history.json"


def load_previous_stats():
    """Load previous stats for delta calculation."""
    if os.path.exists(STATS_HISTORY_FILE):
        with open(STATS_HISTORY_FILE) as f:
            return json.load(f)
    return None


def save_current_stats(stats):
    """Save current stats for next comparison."""
    with open(STATS_HISTORY_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def delta_str(current, previous, suffix="", higher_is_better=True):
    """Format delta with arrow indicator."""
    if previous is None or current is None:
        return ""
    diff = float(current or 0) - float(previous or 0)
    if abs(diff) < 0.01:
        return ""
    arrow = "^" if diff > 0 else "v"
    color_good = diff > 0 if higher_is_better else diff < 0
    sign = "+" if diff > 0 else ""
    return f" ({sign}{diff:.2f}{suffix} {arrow})"


conn = psycopg.connect("postgresql://coinswarm:coinswarm_dev_2024@localhost:5432/coinswarm")
cur = conn.cursor()

# Load previous stats
prev = load_previous_stats()
prev_agents = prev.get("agents", {}) if prev else {}
prev_patterns = prev.get("patterns", {}) if prev else {}
prev_trades = prev.get("trades", {}) if prev else {}

print("=" * 70)
print(f"EVOLUTION PROGRESS REPORT  [{datetime.now().strftime('%H:%M:%S')}]")
print("=" * 70)

# Agent stats - added AVG(backtest_count)
cur.execute("""SELECT COUNT(*), ROUND(AVG(fitness_score)::numeric,2), MAX(backtest_count),
               COUNT(*) FILTER (WHERE fitness_score >= 50),
               COUNT(*) FILTER (WHERE backtest_count >= 3),
               ROUND(AVG(win_rate)::numeric,3),
               ROUND(AVG(total_pnl)::numeric,2),
               ROUND(AVG(annualized_roi_pct)::numeric,2),
               ROUND(AVG(sharpe_ratio)::numeric,2),
               ROUND(AVG(backtest_count)::numeric,2),
               COUNT(*) FILTER (WHERE fitness_by_regime IS NOT NULL AND fitness_by_regime != '{}'::jsonb)
               FROM agents WHERE status='active'""")
r = cur.fetchone()

agent_count = r[0]
avg_fitness = float(r[1] or 0)
max_bt = r[2] or 0
fit_50_plus = r[3]
evaluated = r[4]
win_rate = float(r[5] or 0)
avg_pnl = float(r[6] or 0)
avg_roi = float(r[7] or 0)
sharpe = float(r[8] or 0)
avg_backtests = float(r[9] or 0)
regime_count = r[10]

print(f"\nAGENTS ({agent_count} active):")
print(
    f"  Fitness:     Avg={avg_fitness}{delta_str(avg_fitness, prev_agents.get('avg_fitness'))} | 50+={fit_50_plus}{delta_str(fit_50_plus, prev_agents.get('fit_50_plus'))}"
)
print(
    f"  Backtests:   Avg={avg_backtests:.1f}{delta_str(avg_backtests, prev_agents.get('avg_backtests'))} | Max={max_bt} | Evaluated(3+)={evaluated}{delta_str(evaluated, prev_agents.get('evaluated'))}"
)
print(f"  Win Rate:    {win_rate * 100:.1f}%{delta_str(win_rate * 100, prev_agents.get('win_rate_pct'), '%')}")
print(f"  Avg ROI:     {avg_roi:.1f}%{delta_str(avg_roi, prev_agents.get('avg_roi'), '%')} (annualized)")
print(f"  Sharpe:      {sharpe:.2f}{delta_str(sharpe, prev_agents.get('sharpe'))}")
print(f"  Regime Data: {regime_count} agents have per-regime fitness")

# Best regime fitness per agent (specialists may score high in specific regimes)
cur.execute("""
    SELECT
        COUNT(*) as specialists,
        ROUND(AVG(best_regime_fit)::numeric, 2) as avg_best,
        MAX(best_regime_fit) as max_best
    FROM (
        SELECT
            agent_id,
            MAX((regime_data->>'fitness')::numeric) as best_regime_fit
        FROM agents,
            jsonb_each(fitness_by_regime) AS r(regime_key, regime_data)
        WHERE status = 'active'
          AND fitness_by_regime IS NOT NULL
          AND fitness_by_regime != '{}'::jsonb
        GROUP BY agent_id
    ) sub
    WHERE best_regime_fit >= 50
""")
specialist_row = cur.fetchone()
if specialist_row and specialist_row[0]:
    print(
        f"  Specialists: {specialist_row[0]} agents with 50+ in at least one regime (avg best={specialist_row[1]}, max={specialist_row[2]})"
    )

# Regime-specific fitness breakdown
cur.execute("""
    SELECT
        regime_key,
        COUNT(*) as agent_count,
        ROUND(AVG((regime_data->>'fitness')::numeric), 2) as avg_fitness,
        ROUND(AVG((regime_data->>'trades')::numeric), 0) as avg_trades,
        ROUND(AVG((regime_data->>'win_rate')::numeric), 3) as avg_win_rate
    FROM agents,
        jsonb_each(fitness_by_regime) AS r(regime_key, regime_data)
    WHERE status = 'active'
      AND fitness_by_regime IS NOT NULL
      AND fitness_by_regime != '{}'::jsonb
    GROUP BY regime_key
    ORDER BY avg_fitness DESC
""")
regime_rows = cur.fetchall()
prev_regimes = prev.get("regimes", {}) if prev else {}

if regime_rows:
    print("\n  REGIME FITNESS:")
    regime_stats = {}
    for row in regime_rows:
        regime_name, count, fitness, trades, wr = row
        prev_fit = prev_regimes.get(regime_name, {}).get("fitness")
        delta = delta_str(float(fitness or 0), prev_fit)
        wr_pct = float(wr or 0) * 100
        print(
            f"    {regime_name:12}: Fit={fitness}{delta} | Agents={count} | Trades={int(trades or 0)} | WR={wr_pct:.1f}%"
        )
        regime_stats[regime_name] = {"fitness": float(fitness or 0), "count": count, "trades": int(trades or 0)}
else:
    regime_stats = {}

# Pattern stats
cur.execute("""SELECT COUNT(*), ROUND(AVG(fitness_score)::numeric,2),
               COUNT(*) FILTER (WHERE fitness_score >= 50),
               COUNT(*) FILTER (WHERE fitness_score >= 70),
               ROUND(AVG(win_rate)::numeric,3),
               ROUND(AVG(total_roi_pct)::numeric,2),
               ROUND(AVG(sharpe_ratio)::numeric,2),
               ROUND(AVG(total_trades)::numeric,0)
               FROM patterns WHERE is_active=true""")
p = cur.fetchone()

pat_count = p[0]
pat_avg_fitness = float(p[1] or 0)
pat_50_plus = p[2]
pat_70_plus = p[3]
pat_win_rate = float(p[4] or 0)
pat_roi = float(p[5] or 0)
pat_sharpe = float(p[6] or 0)
pat_trades = p[7] or 0

print(f"\nPATTERNS ({pat_count} active):")
print(
    f"  Fitness:     Avg={pat_avg_fitness}{delta_str(pat_avg_fitness, prev_patterns.get('avg_fitness'))} | 50+={pat_50_plus}{delta_str(pat_50_plus, prev_patterns.get('fit_50_plus'))} | 70+={pat_70_plus}{delta_str(pat_70_plus, prev_patterns.get('fit_70_plus'))}"
)
print(
    f"  Win Rate:    {pat_win_rate * 100:.1f}%{delta_str(pat_win_rate * 100, prev_patterns.get('win_rate_pct'), '%')}"
)
print(f"  Avg ROI:     {pat_roi:.1f}%{delta_str(pat_roi, prev_patterns.get('avg_roi'), '%')} (cumulative)")
print(f"  Sharpe:      {pat_sharpe:.2f}{delta_str(pat_sharpe, prev_patterns.get('sharpe'))}")

# Trade counts
cur.execute("SELECT COUNT(*) FROM backtest_trades_unified WHERE source='evolution_backtest'")
evo_trades = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM backtest_trades_unified")
total_trades = cur.fetchone()[0]

evo_delta = evo_trades - prev_trades.get("evolution", 0) if prev_trades else 0
total_delta = total_trades - prev_trades.get("total", 0) if prev_trades else 0

print("\nTRADES:")
print(f"  Evolution:   {evo_trades:,}" + (f" (+{evo_delta:,})" if evo_delta > 0 else ""))
print(f"  Total:       {total_trades:,}" + (f" (+{total_delta:,})" if total_delta > 0 else ""))

# Calculate rate (trades per minute since last check)
if prev and prev.get("timestamp"):
    prev_time = datetime.fromisoformat(prev["timestamp"])
    elapsed_mins = (datetime.now() - prev_time).total_seconds() / 60
    if elapsed_mins > 0.5 and evo_delta > 0:
        rate = evo_delta / elapsed_mins
        print(f"  Rate:        {rate:.0f} trades/min")

print("\n" + "=" * 70)

# Save current stats for next comparison
current_stats = {
    "timestamp": datetime.now().isoformat(),
    "agents": {
        "count": agent_count,
        "avg_fitness": avg_fitness,
        "fit_50_plus": fit_50_plus,
        "avg_backtests": avg_backtests,
        "evaluated": evaluated,
        "win_rate_pct": win_rate * 100,
        "avg_roi": avg_roi,
        "sharpe": sharpe,
    },
    "patterns": {
        "count": pat_count,
        "avg_fitness": pat_avg_fitness,
        "fit_50_plus": pat_50_plus,
        "fit_70_plus": pat_70_plus,
        "win_rate_pct": pat_win_rate * 100,
        "avg_roi": pat_roi,
        "sharpe": pat_sharpe,
    },
    "trades": {
        "evolution": evo_trades,
        "total": total_trades,
    },
    "regimes": regime_stats,
}
save_current_stats(current_stats)

conn.close()
