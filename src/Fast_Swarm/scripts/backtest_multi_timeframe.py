"""
Backtest: Multi-Timeframe Divergence Signal

Tests whether requiring the signal on multiple timeframes improves results.

Strategies tested:
1. Single timeframe only (baseline)
2. AND - Both timeframes must show signal (full Kelly)
3. OR - Either timeframe shows signal (half Kelly), both = full Kelly

Author: Coinswarm Research
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import json

# =============================================================================
# CONFIGURATION
# =============================================================================

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")
RESULTS_DIR = Path("c:/fast_swarm/data/analysis_results")
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class MTFConfig:
    """Multi-timeframe backtest parameters."""
    initial_capital: float = 10000.0
    stop_loss_pct: float = 0.25  # 25% stop loss (optimal from previous tests)

    # Kelly fractions based on confirmation
    kelly_single: float = 0.5    # Half-Kelly for single timeframe
    kelly_both: float = 1.0      # Full Kelly for both timeframes

    # Signal thresholds (z-scores) - optimal from previous tests
    entry_velocity_threshold: float = -1.5
    entry_accel_threshold: float = 3.0
    exit_velocity_threshold: float = 1.5
    exit_accel_threshold: float = -3.0

    # Risk management
    max_position_pct: float = 0.50
    min_position_pct: float = 0.05

    # Timeframes to use
    primary_timeframe: str = "4h"
    secondary_timeframe: str = "1h"  # or "1d"


@dataclass
class Trade:
    """Record of a single trade."""
    entry_time: datetime
    entry_price: float
    entry_reason: str
    position_size: float
    shares: float
    signal_strength: str  # "single" or "both"

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    def close(self, exit_time: datetime, exit_price: float, exit_reason: str):
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
    wins: int = 0
    losses: int = 0
    total_win_pct: float = 0.0
    total_loss_pct: float = 0.0


# =============================================================================
# DATA LOADING
# =============================================================================

def load_timeframe_data(symbol: str, timeframe: str) -> pl.DataFrame:
    """Load derivatives data for a symbol/timeframe."""
    path = DERIVATIVES_DIR / f"symbol={symbol}" / f"timeframe={timeframe}"
    if not path.exists():
        raise FileNotFoundError(f"Data not found at {path}")

    df = pl.read_parquet(path)
    df = df.sort("time")
    return df


def align_timeframes(df_primary: pl.DataFrame, df_secondary: pl.DataFrame,
                     primary_tf: str, secondary_tf: str) -> pl.DataFrame:
    """
    Align two timeframes by matching secondary to primary timestamps.

    For each primary candle, we look up the most recent secondary candle
    that closed before or at the primary candle time.
    """
    # Get the columns we need from secondary
    secondary_cols = ["time", "close_velocity_zscore", "close_acceleration_zscore"]
    df_sec = df_secondary.select(secondary_cols).rename({
        "close_velocity_zscore": "sec_velocity_zscore",
        "close_acceleration_zscore": "sec_accel_zscore",
        "time": "sec_time"
    })

    # For each primary timestamp, find the latest secondary timestamp <= primary
    # Using asof join
    result = df_primary.join_asof(
        df_sec,
        left_on="time",
        right_on="sec_time",
        strategy="backward"  # Get most recent secondary candle
    )

    return result


# =============================================================================
# SIGNAL DETECTION
# =============================================================================

def detect_entry_signal(row: dict, config: MTFConfig) -> tuple[bool, bool]:
    """
    Detect entry signals on both timeframes.

    Returns (primary_signal, secondary_signal).
    """
    # Primary timeframe signal
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    primary_signal = False
    if vel is not None and acc is not None:
        if not (np.isnan(vel) or np.isnan(acc)):
            primary_signal = vel < config.entry_velocity_threshold and acc > config.entry_accel_threshold

    # Secondary timeframe signal
    sec_vel = row.get("sec_velocity_zscore")
    sec_acc = row.get("sec_accel_zscore")

    secondary_signal = False
    if sec_vel is not None and sec_acc is not None:
        if not (np.isnan(sec_vel) or np.isnan(sec_acc)):
            secondary_signal = sec_vel < config.entry_velocity_threshold and sec_acc > config.entry_accel_threshold

    return primary_signal, secondary_signal


def detect_exit_signal(row: dict, config: MTFConfig) -> bool:
    """Detect exit signal (primary timeframe only)."""
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    return vel > config.exit_velocity_threshold and acc < config.exit_accel_threshold


# =============================================================================
# KELLY SIZING
# =============================================================================

def calculate_kelly(state: BacktestState, config: MTFConfig, both_confirm: bool) -> float:
    """
    Calculate Kelly fraction based on confirmation level.

    - Single timeframe signal: Half-Kelly
    - Both timeframes confirm: Full Kelly
    """
    # Base Kelly from historical performance
    if state.wins + state.losses < 5:
        base_kelly = 0.10
    else:
        win_prob = state.wins / (state.wins + state.losses)

        if state.losses == 0:
            base_kelly = 0.30
        elif state.wins == 0:
            base_kelly = config.min_position_pct
        else:
            avg_win = state.total_win_pct / state.wins if state.wins > 0 else 0
            avg_loss = abs(state.total_loss_pct / state.losses) if state.losses > 0 else 1

            if avg_loss == 0:
                avg_loss = 1

            win_loss_ratio = avg_win / avg_loss
            base_kelly = win_prob - (1 - win_prob) / win_loss_ratio

    # Apply confirmation multiplier
    if both_confirm:
        kelly = base_kelly * config.kelly_both  # Full Kelly
    else:
        kelly = base_kelly * config.kelly_single  # Half Kelly

    # Clamp to bounds
    kelly = max(config.min_position_pct, min(config.max_position_pct, kelly))

    return kelly


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

def run_mtf_backtest(df: pl.DataFrame, config: MTFConfig,
                     mode: str = "AND", verbose: bool = True) -> BacktestState:
    """
    Run multi-timeframe backtest.

    Modes:
    - "AND": Only enter when BOTH timeframes show signal (full Kelly)
    - "OR": Enter when EITHER shows signal (half Kelly if single, full if both)
    - "PRIMARY": Only use primary timeframe (baseline)
    """
    state = BacktestState(capital=config.initial_capital)
    rows = df.to_dicts()
    n_rows = len(rows)

    if verbose:
        print(f"\nRunning MTF backtest ({mode} mode) on {n_rows:,} candles...")
        print(f"Primary: {config.primary_timeframe}, Secondary: {config.secondary_timeframe}")
        print(f"Initial capital: ${config.initial_capital:,.2f}")
        print(f"Kelly - Single: {config.kelly_single}x, Both: {config.kelly_both}x")
        print("-" * 60)

    last_pct = 0

    for i, row in enumerate(rows):
        current_time = row["time"]
        current_price = row["close"]

        # Progress
        pct_complete = int((i / n_rows) * 100)
        if verbose and pct_complete >= last_pct + 20:
            print(f"  Progress: {pct_complete}% - Capital: ${state.capital:,.2f}")
            last_pct = pct_complete

        if current_price is None or np.isnan(current_price) or current_price <= 0:
            continue

        # Record equity
        if state.position:
            unrealized = (current_price - state.position.entry_price) * state.position.shares
            equity = state.capital + unrealized
            dd = (current_price / state.position.entry_price - 1) * 100
            if dd < state.position.max_drawdown_pct:
                state.position.max_drawdown_pct = dd
        else:
            equity = state.capital

        state.equity_curve.append({
            "time": current_time,
            "equity": equity,
            "price": current_price,
        })

        # Check for exit if in position
        if state.position:
            exit_reason = None

            # Stop loss
            drawdown = (current_price / state.position.entry_price) - 1
            if drawdown <= -config.stop_loss_pct:
                exit_reason = "STOP_LOSS"
            elif detect_exit_signal(row, config):
                exit_reason = "EXIT_SIGNAL"

            if exit_reason:
                state.position.close(current_time, current_price, exit_reason)
                state.capital += state.position.pnl

                if state.position.pnl >= 0:
                    state.wins += 1
                    state.total_win_pct += state.position.pnl_pct
                else:
                    state.losses += 1
                    state.total_loss_pct += state.position.pnl_pct

                state.trades.append(state.position)
                state.position = None

        # Check for entry if not in position
        else:
            primary_sig, secondary_sig = detect_entry_signal(row, config)

            should_enter = False
            both_confirm = False

            if mode == "AND":
                # Require both timeframes
                if primary_sig and secondary_sig:
                    should_enter = True
                    both_confirm = True
            elif mode == "OR":
                # Enter on either, but adjust sizing
                if primary_sig or secondary_sig:
                    should_enter = True
                    both_confirm = primary_sig and secondary_sig
            elif mode == "PRIMARY":
                # Baseline - only primary
                if primary_sig:
                    should_enter = True
                    both_confirm = False

            if should_enter:
                kelly_pct = calculate_kelly(state, config, both_confirm)
                position_size = state.capital * kelly_pct
                shares = position_size / current_price

                signal_str = "both" if both_confirm else "single"

                state.position = Trade(
                    entry_time=current_time,
                    entry_price=current_price,
                    entry_reason=f"DIVERGENCE_{mode}",
                    position_size=position_size,
                    shares=shares,
                    signal_strength=signal_str
                )

                if verbose and len(state.trades) < 10:
                    print(f"  ENTRY ({signal_str}): {current_time.strftime('%Y-%m-%d')} @ ${current_price:,.2f} | "
                          f"Size: ${position_size:,.0f} ({kelly_pct*100:.0f}%)")

    # Close any open position
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

def analyze_results(state: BacktestState, config: MTFConfig) -> dict:
    """Generate comprehensive statistics."""
    if not state.trades:
        return {"error": "No trades"}

    n_trades = len(state.trades)
    n_wins = sum(1 for t in state.trades if t.pnl >= 0)
    win_rate = n_wins / n_trades if n_trades > 0 else 0

    all_pnl_pct = [t.pnl_pct for t in state.trades]
    win_pnl = [t.pnl_pct for t in state.trades if t.pnl >= 0]
    loss_pnl = [t.pnl_pct for t in state.trades if t.pnl < 0]

    avg_win = np.mean(win_pnl) if win_pnl else 0
    avg_loss = np.mean(loss_pnl) if loss_pnl else 0

    # Signal strength breakdown
    single_trades = [t for t in state.trades if t.signal_strength == "single"]
    both_trades = [t for t in state.trades if t.signal_strength == "both"]

    # Returns by signal strength
    single_pnl = [t.pnl_pct for t in single_trades] if single_trades else []
    both_pnl = [t.pnl_pct for t in both_trades] if both_trades else []

    # Time span
    if state.trades:
        first = state.trades[0]
        last = state.trades[-1]
        days = (last.exit_time - first.entry_time).days if last.exit_time else 0
        years = days / 365.25 if days > 0 else 1
    else:
        years = 1

    total_return = (state.capital / config.initial_capital) - 1
    cagr = (state.capital / config.initial_capital) ** (1/years) - 1 if years > 0 else 0

    gross_profit = sum(t.pnl for t in state.trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in state.trades if t.pnl < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    return {
        "summary": {
            "final_capital": state.capital,
            "total_return_pct": total_return * 100,
            "cagr_pct": cagr * 100,
            "years": years,
        },
        "trades": {
            "total": n_trades,
            "wins": n_wins,
            "losses": n_trades - n_wins,
            "win_rate_pct": win_rate * 100,
        },
        "returns": {
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "expectancy_pct": expectancy,
        },
        "risk": {
            "profit_factor": profit_factor,
        },
        "by_signal_strength": {
            "single_trades": len(single_trades),
            "single_avg_return": np.mean(single_pnl) if single_pnl else 0,
            "single_win_rate": sum(1 for p in single_pnl if p >= 0) / len(single_pnl) * 100 if single_pnl else 0,
            "both_trades": len(both_trades),
            "both_avg_return": np.mean(both_pnl) if both_pnl else 0,
            "both_win_rate": sum(1 for p in both_pnl if p >= 0) / len(both_pnl) * 100 if both_pnl else 0,
        },
    }


def print_comparison(results: dict, mode: str, config: MTFConfig):
    """Print formatted results."""
    s = results["summary"]
    t = results["trades"]
    r = results["returns"]
    sig = results["by_signal_strength"]

    print(f"\n{'='*60}")
    print(f"MODE: {mode} | {config.primary_timeframe} + {config.secondary_timeframe}")
    print(f"{'='*60}")
    print(f"Final Capital:   ${s['final_capital']:>10,.2f}")
    print(f"Total Return:    {s['total_return_pct']:>10.1f}%")
    print(f"CAGR:            {s['cagr_pct']:>10.1f}%")
    print(f"Trades:          {t['total']:>10}")
    print(f"Win Rate:        {t['win_rate_pct']:>10.1f}%")
    print(f"Avg Win:         {r['avg_win_pct']:>10.1f}%")
    print(f"Avg Loss:        {r['avg_loss_pct']:>10.1f}%")
    print(f"Expectancy:      {r['expectancy_pct']:>10.2f}%")
    print(f"Profit Factor:   {results['risk']['profit_factor']:>10.2f}")

    if sig["single_trades"] > 0 or sig["both_trades"] > 0:
        print(f"\n--- By Signal Strength ---")
        if sig["single_trades"] > 0:
            print(f"Single TF trades: {sig['single_trades']:>5} | "
                  f"Avg: {sig['single_avg_return']:+.1f}% | "
                  f"Win: {sig['single_win_rate']:.0f}%")
        if sig["both_trades"] > 0:
            print(f"Both TF trades:   {sig['both_trades']:>5} | "
                  f"Avg: {sig['both_avg_return']:+.1f}% | "
                  f"Win: {sig['both_win_rate']:.0f}%")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run multi-timeframe comparison."""

    print("=" * 70)
    print("MULTI-TIMEFRAME DIVERGENCE BACKTEST")
    print("Testing: Does confirmation from multiple timeframes improve results?")
    print("=" * 70)

    # Test different timeframe combinations
    tf_combinations = [
        ("4h", "1h"),   # Higher TF with lower TF confirmation
        ("4h", "1d"),   # Lower TF with higher TF confirmation
        ("1h", "15m"),  # Fast timeframes
    ]

    all_results = {}

    for primary_tf, secondary_tf in tf_combinations:
        print(f"\n{'#'*70}")
        print(f"# Testing: {primary_tf} + {secondary_tf}")
        print(f"{'#'*70}")

        config = MTFConfig(
            primary_timeframe=primary_tf,
            secondary_timeframe=secondary_tf,
        )

        # Load data
        try:
            print(f"\nLoading BTC {primary_tf} data...")
            df_primary = load_timeframe_data("BTC", primary_tf)
            print(f"  Loaded {len(df_primary):,} candles")

            print(f"Loading BTC {secondary_tf} data...")
            df_secondary = load_timeframe_data("BTC", secondary_tf)
            print(f"  Loaded {len(df_secondary):,} candles")
        except FileNotFoundError as e:
            print(f"  ERROR: {e}")
            continue

        # Align timeframes
        print("Aligning timeframes...")
        df_aligned = align_timeframes(df_primary, df_secondary, primary_tf, secondary_tf)
        print(f"  Aligned dataset: {len(df_aligned):,} candles")

        # Test each mode
        combo_results = {}

        for mode in ["PRIMARY", "AND", "OR"]:
            print(f"\n--- Testing mode: {mode} ---")
            state = run_mtf_backtest(df_aligned, config, mode=mode, verbose=False)
            results = analyze_results(state, config)
            combo_results[mode] = results
            print_comparison(results, mode, config)

        all_results[f"{primary_tf}+{secondary_tf}"] = combo_results

    # Summary comparison
    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON")
    print("=" * 70)
    print(f"{'Combination':<15} | {'Mode':<8} | {'Return':>8} | {'Trades':>6} | {'WinRate':>7} | {'Expect':>7}")
    print("-" * 70)

    for combo, modes in all_results.items():
        for mode, r in modes.items():
            if "error" in r:
                continue
            print(f"{combo:<15} | {mode:<8} | "
                  f"{r['summary']['total_return_pct']:>7.1f}% | "
                  f"{r['trades']['total']:>6} | "
                  f"{r['trades']['win_rate_pct']:>6.1f}% | "
                  f"{r['returns']['expectancy_pct']:>6.2f}%")

    # Save results
    results_file = RESULTS_DIR / "mtf_backtest_results.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")

    return all_results


if __name__ == "__main__":
    main()
