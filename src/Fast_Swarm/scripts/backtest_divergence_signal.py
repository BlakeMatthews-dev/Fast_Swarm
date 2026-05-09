"""
Backtest: Motion Derivatives Divergence Signal

Strategy:
- ENTRY: Velocity < -1.5 z-score AND Acceleration > +1.5 z-score (PRE-BOTTOM)
- EXIT: Next local TOP (velocity > +1.5 AND acceleration < -1.5)
- STOP: -20% from entry
- SIZING: Half-Kelly

Author: Coinswarm Research
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json

# =============================================================================
# CONFIGURATION
# =============================================================================

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")
RESULTS_DIR = Path("c:/fast_swarm/data/analysis_results")
RESULTS_DIR.mkdir(exist_ok=True)

@dataclass
class BacktestConfig:
    """Backtest parameters."""
    initial_capital: float = 10000.0
    stop_loss_pct: float = 0.20  # 20% stop loss
    kelly_fraction: float = 0.5  # Half-Kelly

    # Signal thresholds (z-scores)
    entry_velocity_threshold: float = -2.0  # Velocity below this (tightened)
    entry_accel_threshold: float = 2.0      # Acceleration above this (tightened)
    exit_velocity_threshold: float = 2.0    # Velocity above this (TOP)
    exit_accel_threshold: float = -2.0      # Acceleration below this (TOP)

    # Risk management
    max_position_pct: float = 0.50  # Never risk more than 50% of capital
    min_position_pct: float = 0.05  # Minimum 5% position


@dataclass
class Trade:
    """Record of a single trade."""
    entry_time: datetime
    entry_price: float
    entry_reason: str
    position_size: float  # Dollar amount
    shares: float

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    pnl: float = 0.0
    pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0  # Worst intra-trade drawdown

    def close(self, exit_time: datetime, exit_price: float, exit_reason: str):
        """Close the trade and calculate PnL."""
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.pnl = (exit_price - self.entry_price) * self.shares
        self.pnl_pct = (exit_price / self.entry_price - 1) * 100


@dataclass
class BacktestState:
    """Current state of the backtest."""
    capital: float
    position: Optional[Trade] = None
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    # For Kelly calculation (updated after each trade)
    wins: int = 0
    losses: int = 0
    total_win_pct: float = 0.0
    total_loss_pct: float = 0.0


# =============================================================================
# KELLY CRITERION
# =============================================================================

def calculate_kelly(state: BacktestState, config: BacktestConfig) -> float:
    """
    Calculate Kelly fraction for position sizing.

    Kelly % = W - (1-W)/R
    Where:
        W = Win probability
        R = Win/Loss ratio (average win / average loss)

    We use HALF-Kelly for safety (less volatility, still good growth).
    """
    if state.wins + state.losses < 5:
        # Not enough data - use conservative 10%
        return 0.10

    win_prob = state.wins / (state.wins + state.losses)

    if state.losses == 0:
        # All wins - use max allowed
        return config.max_position_pct

    if state.wins == 0:
        # All losses - use minimum
        return config.min_position_pct

    avg_win = state.total_win_pct / state.wins if state.wins > 0 else 0
    avg_loss = abs(state.total_loss_pct / state.losses) if state.losses > 0 else 1

    if avg_loss == 0:
        avg_loss = 1  # Prevent division by zero

    win_loss_ratio = avg_win / avg_loss

    # Kelly formula
    kelly = win_prob - (1 - win_prob) / win_loss_ratio

    # Apply half-Kelly
    kelly *= config.kelly_fraction

    # Clamp to bounds
    kelly = max(config.min_position_pct, min(config.max_position_pct, kelly))

    return kelly


# =============================================================================
# SIGNAL DETECTION
# =============================================================================

def detect_entry_signal(row: dict, config: BacktestConfig) -> bool:
    """
    Detect PRE-BOTTOM entry signal.

    Conditions:
    - Velocity z-score < -1.5 (price falling fast)
    - Acceleration z-score > +1.5 (but slowing down - about to reverse)

    This divergence indicates we're near a local bottom.
    """
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    return vel < config.entry_velocity_threshold and acc > config.entry_accel_threshold


def detect_exit_signal(row: dict, config: BacktestConfig) -> bool:
    """
    Detect TOP exit signal.

    Conditions:
    - Velocity z-score > +1.5 (price rising fast)
    - Acceleration z-score < -1.5 (but slowing down - about to reverse)

    This divergence indicates we're near a local top.
    """
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    return vel > config.exit_velocity_threshold and acc < config.exit_accel_threshold


def check_stop_loss(entry_price: float, current_price: float, config: BacktestConfig) -> bool:
    """Check if stop loss has been triggered."""
    drawdown = (current_price / entry_price) - 1
    return drawdown <= -config.stop_loss_pct


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

def run_backtest(df: pl.DataFrame, config: BacktestConfig, verbose: bool = True) -> BacktestState:
    """
    Run the backtest on the provided data.

    Returns BacktestState with all trades and equity curve.
    """
    state = BacktestState(capital=config.initial_capital)

    # Convert to list of dicts for iteration
    rows = df.to_dicts()
    n_rows = len(rows)

    if verbose:
        print(f"\nRunning backtest on {n_rows:,} candles...")
        print(f"Initial capital: ${config.initial_capital:,.2f}")
        print(f"Stop loss: {config.stop_loss_pct*100:.0f}%")
        print(f"Kelly fraction: {config.kelly_fraction}")
        print("-" * 60)

    # Track progress
    last_pct = 0

    for i, row in enumerate(rows):
        current_time = row["time"]
        current_price = row["close"]

        # Progress reporting
        pct_complete = int((i / n_rows) * 100)
        if verbose and pct_complete >= last_pct + 10:
            print(f"  Progress: {pct_complete}% ({i:,}/{n_rows:,}) - Capital: ${state.capital:,.2f}")
            last_pct = pct_complete

        # Skip if price is invalid
        if current_price is None or np.isnan(current_price) or current_price <= 0:
            continue

        # Record equity
        if state.position:
            # Mark-to-market
            unrealized = (current_price - state.position.entry_price) * state.position.shares
            equity = state.capital + unrealized

            # Track max drawdown for this trade
            dd = (current_price / state.position.entry_price - 1) * 100
            if dd < state.position.max_drawdown_pct:
                state.position.max_drawdown_pct = dd
        else:
            equity = state.capital

        state.equity_curve.append({
            "time": current_time,
            "equity": equity,
            "price": current_price,
            "in_position": state.position is not None
        })

        # If in position, check for exit
        if state.position:
            exit_reason = None

            # Check stop loss first
            if check_stop_loss(state.position.entry_price, current_price, config):
                exit_reason = "STOP_LOSS"
            # Check exit signal
            elif detect_exit_signal(row, config):
                exit_reason = "EXIT_SIGNAL"

            if exit_reason:
                # Close position
                state.position.close(current_time, current_price, exit_reason)

                # Update capital
                state.capital += state.position.pnl

                # Update win/loss stats for Kelly
                if state.position.pnl >= 0:
                    state.wins += 1
                    state.total_win_pct += state.position.pnl_pct
                else:
                    state.losses += 1
                    state.total_loss_pct += state.position.pnl_pct

                # Record trade
                state.trades.append(state.position)

                if verbose and len(state.trades) <= 20:  # Show first 20 trades
                    pnl_sign = "+" if state.position.pnl >= 0 else ""
                    print(f"  TRADE #{len(state.trades)}: {state.position.entry_time.strftime('%Y-%m-%d')} -> "
                          f"{current_time.strftime('%Y-%m-%d')} | "
                          f"{pnl_sign}{state.position.pnl_pct:.1f}% | "
                          f"${state.capital:,.0f} | {exit_reason}")

                state.position = None

        # If not in position, check for entry
        else:
            if detect_entry_signal(row, config):
                # Calculate position size using Kelly
                kelly_pct = calculate_kelly(state, config)
                position_size = state.capital * kelly_pct

                # Calculate shares
                shares = position_size / current_price

                # Open position
                state.position = Trade(
                    entry_time=current_time,
                    entry_price=current_price,
                    entry_reason="DIVERGENCE_SIGNAL",
                    position_size=position_size,
                    shares=shares
                )

                if verbose and len(state.trades) < 20:
                    print(f"  ENTRY: {current_time.strftime('%Y-%m-%d %H:%M')} @ ${current_price:,.2f} | "
                          f"Size: ${position_size:,.0f} ({kelly_pct*100:.1f}% Kelly)")

    # Close any open position at end
    if state.position:
        final_row = rows[-1]
        state.position.close(final_row["time"], final_row["close"], "END_OF_DATA")
        state.capital += state.position.pnl

        if state.position.pnl >= 0:
            state.wins += 1
            state.total_win_pct += state.position.pnl_pct
        else:
            state.losses += 1
            state.total_loss_pct += state.position.pnl_pct

        state.trades.append(state.position)

    return state


# =============================================================================
# RESULTS ANALYSIS
# =============================================================================

def analyze_results(state: BacktestState, config: BacktestConfig) -> dict:
    """Generate comprehensive backtest statistics."""

    if not state.trades:
        return {"error": "No trades executed"}

    # Basic stats
    n_trades = len(state.trades)
    n_wins = sum(1 for t in state.trades if t.pnl >= 0)
    n_losses = n_trades - n_wins
    win_rate = n_wins / n_trades if n_trades > 0 else 0

    # PnL stats
    all_pnl_pct = [t.pnl_pct for t in state.trades]
    win_pnl = [t.pnl_pct for t in state.trades if t.pnl >= 0]
    loss_pnl = [t.pnl_pct for t in state.trades if t.pnl < 0]

    avg_win = np.mean(win_pnl) if win_pnl else 0
    avg_loss = np.mean(loss_pnl) if loss_pnl else 0

    # Drawdown analysis
    max_drawdowns = [t.max_drawdown_pct for t in state.trades]

    # Exit reason breakdown
    exit_reasons = {}
    for t in state.trades:
        reason = t.exit_reason or "UNKNOWN"
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    # Equity curve analysis
    if state.equity_curve:
        equities = [e["equity"] for e in state.equity_curve]
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak
            if dd < max_dd:
                max_dd = dd
    else:
        max_dd = 0

    # Time analysis
    if state.trades:
        first_trade = state.trades[0]
        last_trade = state.trades[-1]
        total_days = (last_trade.exit_time - first_trade.entry_time).days if last_trade.exit_time else 0
        years = total_days / 365.25 if total_days > 0 else 1
    else:
        years = 1

    # CAGR
    final_capital = state.capital
    initial_capital = config.initial_capital
    total_return = (final_capital / initial_capital) - 1
    cagr = (final_capital / initial_capital) ** (1/years) - 1 if years > 0 else 0

    # Profit factor
    gross_profit = sum(t.pnl for t in state.trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in state.trades if t.pnl < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Win/Loss ratio
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    # Expectancy per trade
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    # Sortino ratio (using only downside deviation)
    if loss_pnl:
        downside_dev = np.std(loss_pnl)
        sortino = (np.mean(all_pnl_pct) / downside_dev) if downside_dev > 0 else 0
    else:
        sortino = float('inf')  # No losses

    return {
        "summary": {
            "initial_capital": initial_capital,
            "final_capital": final_capital,
            "total_return_pct": total_return * 100,
            "cagr_pct": cagr * 100,
            "max_drawdown_pct": max_dd * 100,
            "years": years,
        },
        "trades": {
            "total": n_trades,
            "wins": n_wins,
            "losses": n_losses,
            "win_rate_pct": win_rate * 100,
        },
        "returns": {
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "best_trade_pct": max(all_pnl_pct) if all_pnl_pct else 0,
            "worst_trade_pct": min(all_pnl_pct) if all_pnl_pct else 0,
            "median_return_pct": np.median(all_pnl_pct) if all_pnl_pct else 0,
        },
        "risk_metrics": {
            "profit_factor": profit_factor,
            "win_loss_ratio": win_loss_ratio,
            "expectancy_per_trade_pct": expectancy,
            "sortino_ratio": sortino,
        },
        "drawdowns": {
            "max_intra_trade_dd_pct": min(max_drawdowns) if max_drawdowns else 0,
            "avg_intra_trade_dd_pct": np.mean(max_drawdowns) if max_drawdowns else 0,
        },
        "exit_reasons": exit_reasons,
    }


def print_results(results: dict, config: BacktestConfig):
    """Print formatted backtest results."""

    print("\n" + "=" * 70)
    print("BACKTEST RESULTS: DIVERGENCE SIGNAL STRATEGY")
    print("=" * 70)

    s = results["summary"]
    print(f"\n--- SUMMARY ---")
    print(f"Initial Capital:    ${s['initial_capital']:>12,.2f}")
    print(f"Final Capital:      ${s['final_capital']:>12,.2f}")
    print(f"Total Return:       {s['total_return_pct']:>12.2f}%")
    print(f"CAGR:               {s['cagr_pct']:>12.2f}%")
    print(f"Max Drawdown:       {s['max_drawdown_pct']:>12.2f}%")
    print(f"Time Period:        {s['years']:>12.2f} years")

    t = results["trades"]
    print(f"\n--- TRADES ---")
    print(f"Total Trades:       {t['total']:>12}")
    print(f"Wins:               {t['wins']:>12}")
    print(f"Losses:             {t['losses']:>12}")
    print(f"Win Rate:           {t['win_rate_pct']:>12.1f}%")

    r = results["returns"]
    print(f"\n--- RETURNS ---")
    print(f"Avg Win:            {r['avg_win_pct']:>12.2f}%")
    print(f"Avg Loss:           {r['avg_loss_pct']:>12.2f}%")
    print(f"Best Trade:         {r['best_trade_pct']:>12.2f}%")
    print(f"Worst Trade:        {r['worst_trade_pct']:>12.2f}%")
    print(f"Median Return:      {r['median_return_pct']:>12.2f}%")

    m = results["risk_metrics"]
    print(f"\n--- RISK METRICS ---")
    print(f"Profit Factor:      {m['profit_factor']:>12.2f}")
    print(f"Win/Loss Ratio:     {m['win_loss_ratio']:>12.2f}")
    print(f"Expectancy/Trade:   {m['expectancy_per_trade_pct']:>12.2f}%")
    print(f"Sortino Ratio:      {m['sortino_ratio']:>12.2f}")

    d = results["drawdowns"]
    print(f"\n--- DRAWDOWNS ---")
    print(f"Worst Intra-Trade:  {d['max_intra_trade_dd_pct']:>12.2f}%")
    print(f"Avg Intra-Trade:    {d['avg_intra_trade_dd_pct']:>12.2f}%")

    print(f"\n--- EXIT REASONS ---")
    for reason, count in results["exit_reasons"].items():
        pct = count / results["trades"]["total"] * 100
        print(f"  {reason:20} {count:>6} ({pct:>5.1f}%)")

    print("\n--- STRATEGY PARAMETERS ---")
    print(f"Entry: vel < {config.entry_velocity_threshold} AND acc > {config.entry_accel_threshold}")
    print(f"Exit:  vel > {config.exit_velocity_threshold} AND acc < {config.exit_accel_threshold}")
    print(f"Stop Loss: {config.stop_loss_pct*100:.0f}%")
    print(f"Kelly Fraction: {config.kelly_fraction}")

    print("=" * 70)


def save_results(state: BacktestState, results: dict, config: BacktestConfig):
    """Save backtest results to files."""

    # Save trade list
    trades_data = []
    for t in state.trades:
        trades_data.append({
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "entry_price": t.entry_price,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "exit_price": t.exit_price,
            "exit_reason": t.exit_reason,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
            "max_dd_pct": t.max_drawdown_pct,
            "position_size": t.position_size,
        })

    trades_file = RESULTS_DIR / "backtest_trades.json"
    with open(trades_file, "w") as f:
        json.dump(trades_data, f, indent=2)

    # Save equity curve
    equity_file = RESULTS_DIR / "backtest_equity.json"
    equity_data = []
    for e in state.equity_curve[::10]:  # Sample every 10th point to reduce size
        equity_data.append({
            "time": e["time"].isoformat() if hasattr(e["time"], "isoformat") else str(e["time"]),
            "equity": e["equity"],
            "price": e["price"],
        })
    with open(equity_file, "w") as f:
        json.dump(equity_data, f, indent=2)

    # Save summary
    summary_file = RESULTS_DIR / "backtest_summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to:")
    print(f"  Trades: {trades_file}")
    print(f"  Equity: {equity_file}")
    print(f"  Summary: {summary_file}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run the full backtest."""

    print("=" * 70)
    print("DIVERGENCE SIGNAL BACKTEST")
    print("Strategy: Velocity/Acceleration Divergence at Local Extremes")
    print("=" * 70)

    # Configuration
    config = BacktestConfig(
        initial_capital=10000.0,
        stop_loss_pct=0.20,  # 20% stop loss
        kelly_fraction=0.5,  # Half-Kelly
    )

    # Load BTC 4h data
    btc_path = DERIVATIVES_DIR / "symbol=BTC" / "timeframe=4h"
    if not btc_path.exists():
        print(f"ERROR: Data not found at {btc_path}")
        return

    print(f"\nLoading BTC 4h data from {btc_path}...")
    df = pl.read_parquet(btc_path)
    print(f"Loaded {len(df):,} candles")
    print(f"Date range: {df['time'].min()} to {df['time'].max()}")
    print(f"Columns: {len(df.columns)}")

    # Check for required columns
    required = ["time", "close", "close_velocity_zscore", "close_acceleration_zscore"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}")
        return

    # Sort by time
    df = df.sort("time")

    # Run backtest
    state = run_backtest(df, config, verbose=True)

    # Analyze results
    results = analyze_results(state, config)

    # Print results
    print_results(results, config)

    # Save results
    save_results(state, results, config)

    # Print trade-by-trade summary
    print("\n" + "=" * 70)
    print("TRADE-BY-TRADE SUMMARY (First 30 trades)")
    print("=" * 70)
    print(f"{'#':>3} | {'Entry Date':>12} | {'Exit Date':>12} | {'Return':>8} | {'Max DD':>8} | {'Exit':<12}")
    print("-" * 70)

    for i, t in enumerate(state.trades[:30], 1):
        entry_date = t.entry_time.strftime("%Y-%m-%d") if t.entry_time else "N/A"
        exit_date = t.exit_time.strftime("%Y-%m-%d") if t.exit_time else "N/A"
        pnl_str = f"{t.pnl_pct:+.1f}%"
        dd_str = f"{t.max_drawdown_pct:.1f}%"
        print(f"{i:>3} | {entry_date:>12} | {exit_date:>12} | {pnl_str:>8} | {dd_str:>8} | {t.exit_reason:<12}")

    if len(state.trades) > 30:
        print(f"... and {len(state.trades) - 30} more trades")

    return state, results


if __name__ == "__main__":
    main()
