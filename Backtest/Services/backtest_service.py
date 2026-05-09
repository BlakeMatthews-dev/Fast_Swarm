"""
Backtest Service for Fast_Swarm.

Provides backtesting functionality for patterns and agents.
"""

import math
import uuid
from typing import Any

from ..Models.backtest_models import (
    BacktestConfig,
    BacktestResult,
    ExitStrategy,
    TradeRecord,
)

# =============================================================================
# Trading Costs by Liquidity Tier
# =============================================================================

TRADING_COSTS = {
    "tier1": {"slippage_bps": 1, "spread_bps": 2, "fee_bps": 10},  # BTC, ETH
    "tier2": {"slippage_bps": 3, "spread_bps": 5, "fee_bps": 10},  # SOL, BNB, XRP
    "tier3": {"slippage_bps": 5, "spread_bps": 10, "fee_bps": 10},  # DOT, LINK
    "tier4": {"slippage_bps": 10, "spread_bps": 20, "fee_bps": 15},  # Small caps
}

TIER1_ASSETS = {"BTC", "ETH"}
TIER2_ASSETS = {"SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX"}
TIER3_ASSETS = {"DOT", "LINK", "MATIC", "UNI", "ATOM", "LTC", "ARB", "OP"}


def get_asset_tier(asset: str) -> str:
    """Get liquidity tier for an asset."""
    symbol = asset.replace("-USD", "").replace("USDT", "").upper()
    if symbol in TIER1_ASSETS:
        return "tier1"
    if symbol in TIER2_ASSETS:
        return "tier2"
    if symbol in TIER3_ASSETS:
        return "tier3"
    return "tier4"


def get_trading_costs_pct(asset: str) -> float:
    """Get total round-trip trading costs as percentage."""
    tier = get_asset_tier(asset)
    costs = TRADING_COSTS[tier]
    # Round-trip: (slippage + spread + fee) * 2 sides, convert bps to pct
    return (costs["slippage_bps"] + costs["spread_bps"] + costs["fee_bps"]) * 2 / 100


def get_trading_costs_breakdown(asset: str) -> dict[str, float]:
    """Get detailed trading costs breakdown."""
    tier = get_asset_tier(asset)
    costs = TRADING_COSTS[tier]
    return {
        "slippage_pct": costs["slippage_bps"] * 2 / 100,  # Round-trip
        "spread_pct": costs["spread_bps"] * 2 / 100,
        "fee_pct": costs["fee_bps"] * 2 / 100,
        "total_pct": get_trading_costs_pct(asset),
    }


# =============================================================================
# Dynamic Trail Calculation
# =============================================================================


def calculate_dynamic_trail(
    profit_pct: float,
    base_trail: float = 2.0,
    max_trail: float = 12.0,
    log_scale: float = 2.9,
) -> float:
    """
    Calculate trail percentage based on current profit.

    Philosophy: Small gains = tight protection, big gains = room to run.
      - 0% profit  -> 2.0% trail (tight)
      - 10% profit -> 4.0% trail
      - 50% profit -> 7.0% trail
      - 100% profit -> 9.0% trail (moonshot mode)
    """
    if profit_pct <= 0:
        return base_trail

    log_component = log_scale * math.log1p(profit_pct / 10)
    trail = base_trail + log_component

    return min(trail, max_trail)


# =============================================================================
# MFE/MAE Calculation
# =============================================================================


def calculate_mfe_mae(
    entry_price: float,
    price_history: list[float],
    direction: str,
) -> tuple[float, float]:
    """
    Calculate Maximum Favorable Excursion and Maximum Adverse Excursion.

    Args:
        entry_price: Trade entry price.
        price_history: List of prices during trade.
        direction: 'long' or 'short'.

    Returns:
        Tuple of (mfe_pct, mae_pct).
    """
    if not price_history or entry_price <= 0:
        return 0.0, 0.0

    if direction == "long":
        best_price = max(price_history)
        worst_price = min(price_history)
        mfe = (best_price - entry_price) / entry_price * 100
        mae = (worst_price - entry_price) / entry_price * 100
    else:  # short
        best_price = min(price_history)
        worst_price = max(price_history)
        mfe = (entry_price - best_price) / entry_price * 100
        mae = (entry_price - worst_price) / entry_price * 100

    return mfe, mae


# =============================================================================
# Backtest Metrics Calculation
# =============================================================================


def calculate_backtest_metrics(trades: list[TradeRecord]) -> dict[str, Any]:
    """
    Calculate comprehensive metrics from a list of trades.

    Args:
        trades: List of TradeRecord objects.

    Returns:
        Dict of metrics.
    """
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_roi_pct": 0.0,
            "avg_trade_pnl_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "profit_factor": 0.0,
            "avg_winner_pct": 0.0,
            "avg_loser_pct": 0.0,
            "avg_hold_candles": 0.0,
            "total_fees_pct": 0.0,
            "avg_mfe_pct": 0.0,
            "avg_mae_pct": 0.0,
            "expectancy": 0.0,
        }

    total_trades = len(trades)
    winners = [t for t in trades if t.pnl_pct > 0]
    losers = [t for t in trades if t.pnl_pct <= 0]

    winning_trades = len(winners)
    losing_trades = len(losers)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    # ROI and averages
    pnls = [t.pnl_pct for t in trades]
    total_roi_pct = sum(pnls)
    avg_trade_pnl_pct = total_roi_pct / total_trades if total_trades > 0 else 0

    avg_winner_pct = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
    avg_loser_pct = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

    # Expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    expectancy = (win_rate * avg_winner_pct) + ((1 - win_rate) * avg_loser_pct)

    # Hold duration
    hold_times = [t.candles_held for t in trades]
    avg_hold_candles = sum(hold_times) / len(hold_times) if hold_times else 0

    # Costs
    total_fees_pct = sum(t.fees_pct for t in trades)

    # MFE/MAE
    avg_mfe_pct = sum(t.mfe_pct for t in trades) / total_trades if total_trades > 0 else 0
    avg_mae_pct = sum(t.mae_pct for t in trades) / total_trades if total_trades > 0 else 0

    # Profit factor
    gross_profit = sum(t.pnl_pct for t in winners) if winners else 0
    gross_loss = abs(sum(t.pnl_pct for t in losers)) if losers else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0)

    # Max drawdown
    max_drawdown_pct = _calculate_max_drawdown(pnls)

    # Sharpe ratio
    sharpe_ratio = _calculate_sharpe(pnls)

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_roi_pct": total_roi_pct,
        "avg_trade_pnl_pct": avg_trade_pnl_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "profit_factor": profit_factor,
        "avg_winner_pct": avg_winner_pct,
        "avg_loser_pct": avg_loser_pct,
        "avg_hold_candles": avg_hold_candles,
        "total_fees_pct": total_fees_pct,
        "avg_mfe_pct": avg_mfe_pct,
        "avg_mae_pct": avg_mae_pct,
        "expectancy": expectancy,
    }


def calculate_metrics_by_regime(
    trades: list[TradeRecord],
    regime_map: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """
    Calculate metrics grouped by canonical regime type.

    Args:
        trades: List of TradeRecord objects
        regime_map: Dict mapping trade_id -> regime (e.g., "crash", "bull", "bear")

    Returns:
        Dict mapping regime -> metrics dict
        Example: {"crash": {"win_rate": 0.45, ...}, "bull": {"win_rate": 0.72, ...}}
    """
    from collections import defaultdict

    # Group trades by regime
    by_regime: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        regime = regime_map.get(trade.trade_id, "unknown")
        by_regime[regime].append(trade)

    # Calculate metrics for each regime with enough trades
    results = {}
    for regime, regime_trades in by_regime.items():
        if len(regime_trades) >= 5:  # Minimum trades for statistical significance
            metrics = calculate_backtest_metrics(regime_trades)
            # Extract key fitness-relevant metrics
            results[regime] = {
                "fitness": _calculate_regime_fitness(metrics),
                "trades": metrics["total_trades"],
                "win_rate": metrics["win_rate"],
                "sharpe": metrics["sharpe_ratio"],
                "max_dd": metrics["max_drawdown_pct"],
                "roi": metrics["total_roi_pct"],
            }

    return results


def _calculate_regime_fitness(metrics: dict[str, Any]) -> float:
    """
    Calculate fitness score for a single regime.

    Uses same formula as agent fitness for consistency.
    """
    sharpe = metrics.get("sharpe_ratio", 0) or 0
    win_rate = metrics.get("win_rate", 0) or 0
    roi = metrics.get("total_roi_pct", 0) or 0
    max_dd = metrics.get("max_drawdown_pct", 0) or 0

    fitness = (sharpe * 10) + (win_rate * 50) + (roi / 100 * 20) - (max_dd / 100 * 10)
    return max(0.0, min(100.0, fitness))


def _calculate_max_drawdown(pnls: list[float]) -> float:
    """Calculate maximum drawdown from PnL series."""
    if not pnls:
        return 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0

    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return max_dd


def _calculate_sharpe(pnls: list[float]) -> float:
    """Calculate Sharpe ratio from PnL series."""
    if len(pnls) < 2:
        return 0.0

    mean_return = sum(pnls) / len(pnls)
    variance = sum((p - mean_return) ** 2 for p in pnls) / len(pnls)
    std_dev = variance**0.5 if variance > 0 else 0

    sharpe = mean_return / std_dev if std_dev > 0 else 0
    # Cap at ±6 to filter calculation anomalies while allowing exceptional strategies
    return max(-6.0, min(6.0, sharpe))


# =============================================================================
# Pattern Matching (Simplified)
# =============================================================================


def evaluate_conditions(
    conditions: list[dict[str, Any]],
    indicators: dict[str, int | float],
) -> tuple[bool, float]:
    """
    Evaluate pattern conditions against indicator values.

    Args:
        conditions: List of condition dicts with indicator, operator, min/max.
        indicators: Dict of indicator -> current value.

    Returns:
        Tuple of (matched, confidence).
    """
    if not conditions:
        return False, 0.0

    met_count = 0
    total_conditions = 0

    for cond in conditions:
        indicator = cond.get("indicator", "")
        value = indicators.get(indicator)

        if value is None:
            continue

        total_conditions += 1
        min_val = cond.get("min")
        max_val = cond.get("max")
        operator = cond.get("operator", "between")

        if operator == "between" or (min_val is not None and max_val is not None):
            if min_val is not None and max_val is not None and min_val <= value <= max_val:
                met_count += 1
        elif operator == "<" and max_val is not None:
            if value < max_val:
                met_count += 1
        elif operator == ">" and min_val is not None:
            if value > min_val:
                met_count += 1
        elif operator == "<=" and max_val is not None:
            if value <= max_val:
                met_count += 1
        elif operator == ">=" and min_val is not None:
            if value >= min_val:
                met_count += 1

    if total_conditions == 0:
        return False, 0.0

    confidence = met_count / total_conditions
    matched = met_count == total_conditions

    return matched, confidence


# =============================================================================
# Backtest Engine
# =============================================================================


def run_backtest(
    pattern: dict[str, Any],
    candles: list[dict[str, Any]],
    config: BacktestConfig | None = None,
    agent_id: str | None = None,
) -> BacktestResult:
    """
    Run a backtest for a pattern against historical candle data.

    Args:
        pattern: Pattern dict with entry_conditions, exit_conditions.
        candles: List of OHLCV candle dicts with indicators.
        config: Backtest configuration.
        agent_id: Optional agent ID for tracking.

    Returns:
        BacktestResult with trades and metrics.
    """
    config = config or BacktestConfig()
    pattern_id = pattern.get("pattern_id", str(uuid.uuid4()))
    entry_conditions = pattern.get("entry_conditions", [])
    exit_conditions = pattern.get("exit_conditions", {})
    direction = pattern.get("direction", "long")
    asset = candles[0].get("asset", "BTC") if candles else "BTC"

    # Get trading costs
    if config.include_costs:
        costs_pct = get_trading_costs_pct(asset)
        costs_breakdown = get_trading_costs_breakdown(asset)
    else:
        costs_pct = 0.0
        costs_breakdown = {"slippage_pct": 0, "fee_pct": 0, "spread_pct": 0, "total_pct": 0}

    trades = []
    open_trade: dict[str, Any] | None = None

    # Skip warmup period
    start_idx = config.min_candles_warmup
    if start_idx >= len(candles):
        return BacktestResult(
            backtest_id=str(uuid.uuid4()),
            pattern_id=pattern_id,
            config=config,
            trades=[],
            start_timestamp=candles[0].get("timestamp", 0) if candles else 0,
            end_timestamp=candles[-1].get("timestamp", 0) if candles else 0,
            asset=asset,
        )

    for i in range(start_idx, len(candles)):
        candle = candles[i]
        close_price = candle.get("close", 0)
        timestamp = candle.get("timestamp", 0)

        # Extract indicators from candle
        indicators = {k: v for k, v in candle.items() if isinstance(v, (int, float)) and not math.isnan(v)}

        # If we have an open trade, check for exit
        if open_trade is not None:
            open_trade["candles_held"] += 1
            open_trade["price_history"].append(close_price)

            should_exit, exit_reason = _check_exit(
                open_trade=open_trade,
                current_price=close_price,
                indicators=indicators,
                exit_conditions=exit_conditions,
                config=config,
            )

            if should_exit:
                trade = _close_trade(
                    open_trade=open_trade,
                    exit_price=close_price,
                    exit_timestamp=timestamp,
                    exit_reason=exit_reason,
                    costs_breakdown=costs_breakdown,
                    agent_id=agent_id,
                )
                trades.append(trade)
                open_trade = None

        # If no open trade, check for entry
        if open_trade is None:
            matched, confidence = evaluate_conditions(entry_conditions, indicators)

            if matched and confidence >= config.min_confidence:
                open_trade = {
                    "trade_id": str(uuid.uuid4()),
                    "pattern_id": pattern_id,
                    "asset": asset,
                    "direction": direction,
                    "entry_price": close_price,
                    "entry_timestamp": timestamp,
                    "entry_confidence": confidence,
                    "candles_held": 0,
                    "price_history": [close_price],
                    "peak_price": close_price,
                    "trailing_stop_price": 0.0,
                    "breakeven_activated": False,
                }

    # Close any remaining open trade
    if open_trade is not None:
        last_candle = candles[-1]
        trade = _close_trade(
            open_trade=open_trade,
            exit_price=last_candle.get("close", 0),
            exit_timestamp=last_candle.get("timestamp", 0),
            exit_reason="end_of_data",
            costs_breakdown=costs_breakdown,
            agent_id=agent_id,
        )
        trades.append(trade)

    return BacktestResult(
        backtest_id=str(uuid.uuid4()),
        pattern_id=pattern_id,
        config=config,
        trades=trades,
        start_timestamp=candles[start_idx].get("timestamp", 0) if len(candles) > start_idx else 0,
        end_timestamp=candles[-1].get("timestamp", 0) if candles else 0,
        asset=asset,
        timeframe=config.timeframe,
    )


def _check_exit(
    open_trade: dict[str, Any],
    current_price: float,
    indicators: dict[str, int | float],
    exit_conditions: dict[str, Any],
    config: BacktestConfig,
) -> tuple[bool, str]:
    """Check if trade should be exited."""
    direction = open_trade["direction"]
    entry_price = open_trade["entry_price"]

    # Calculate unrealized PnL
    if direction == "long":
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        pnl_pct = ((entry_price - current_price) / entry_price) * 100

    # Check hard stop loss
    if pnl_pct <= config.stop_loss_pct:
        return True, "stop_loss"

    # Check take profit (FIXED strategy)
    if config.exit_strategy == ExitStrategy.FIXED:
        if pnl_pct >= config.take_profit_pct:
            return True, "take_profit"

    # Check exit conditions from pattern (prioritized before trailing stops)
    if exit_conditions:
        exit_conds = exit_conditions.get("conditions", [])
        if exit_conds:
            matched, _ = evaluate_conditions(exit_conds, indicators)
            if matched:
                return True, "condition"

    # Trailing stop strategies
    if config.exit_strategy in (
        ExitStrategy.TRAILING_2PCT,
        ExitStrategy.TRAILING_3PCT,
        ExitStrategy.TRAILING_5PCT,
        ExitStrategy.DYNAMIC_TRAIL,
        ExitStrategy.BREAKEVEN_TRAIL,
    ):
        triggered = _check_trailing_stop(open_trade, current_price, pnl_pct, config)
        if triggered:
            return True, "trailing_stop"

    # Note: Time-based 'max_hold' exit has been removed by design (pattern-based exits preferred)
    return False, ""


def _check_trailing_stop(
    open_trade: dict[str, Any],
    current_price: float,
    pnl_pct: float,
    config: BacktestConfig,
) -> bool:
    """Check and update trailing stop."""
    direction = open_trade["direction"]

    # Determine trail percentage
    if config.exit_strategy == ExitStrategy.TRAILING_2PCT:
        trail_pct = 2.0
    elif config.exit_strategy == ExitStrategy.TRAILING_3PCT:
        trail_pct = 3.0
    elif config.exit_strategy == ExitStrategy.TRAILING_5PCT:
        trail_pct = 5.0
    elif config.exit_strategy == ExitStrategy.DYNAMIC_TRAIL:
        trail_pct = calculate_dynamic_trail(pnl_pct)
    else:
        trail_pct = config.trailing_stop_pct

    # Update peak price
    if direction == "long":
        if current_price > open_trade["peak_price"]:
            open_trade["peak_price"] = current_price
    else:
        if open_trade["peak_price"] == 0 or current_price < open_trade["peak_price"]:
            open_trade["peak_price"] = current_price

    # For BREAKEVEN_TRAIL, check if we should activate breakeven
    if config.exit_strategy == ExitStrategy.BREAKEVEN_TRAIL:
        if pnl_pct >= config.breakeven_trigger_pct and not open_trade["breakeven_activated"]:
            open_trade["breakeven_activated"] = True
            entry_price = open_trade["entry_price"]
            if direction == "long":
                open_trade["trailing_stop_price"] = entry_price * 1.001
            else:
                open_trade["trailing_stop_price"] = entry_price * 0.999

    # Calculate new trailing stop level
    peak_price = open_trade["peak_price"]
    if direction == "long":
        new_stop = peak_price * (1 - trail_pct / 100)
        if new_stop > open_trade["trailing_stop_price"]:
            open_trade["trailing_stop_price"] = new_stop
        return current_price <= open_trade["trailing_stop_price"] and open_trade["trailing_stop_price"] > 0
    else:
        new_stop = peak_price * (1 + trail_pct / 100)
        if open_trade["trailing_stop_price"] == 0 or new_stop < open_trade["trailing_stop_price"]:
            open_trade["trailing_stop_price"] = new_stop
        return current_price >= open_trade["trailing_stop_price"] and open_trade["trailing_stop_price"] > 0


def _close_trade(
    open_trade: dict[str, Any],
    exit_price: float,
    exit_timestamp: int,
    exit_reason: str,
    costs_breakdown: dict[str, int | float],
    agent_id: str | None = None,
) -> TradeRecord:
    """Close trade and create TradeRecord."""
    direction = open_trade["direction"]
    entry_price = open_trade["entry_price"]

    # Calculate gross PnL
    if direction == "long":
        gross_pnl = ((exit_price - entry_price) / entry_price) * 100
    else:
        gross_pnl = ((entry_price - exit_price) / entry_price) * 100

    # Calculate MFE/MAE
    mfe_pct, mae_pct = calculate_mfe_mae(
        entry_price=entry_price,
        price_history=open_trade["price_history"],
        direction=direction,
    )

    # Subtract costs
    fees_pct = costs_breakdown.get("fee_pct", 0)
    slippage_pct = costs_breakdown.get("slippage_pct", 0)
    net_pnl = gross_pnl - fees_pct - slippage_pct

    return TradeRecord(
        trade_id=open_trade["trade_id"],
        pattern_id=open_trade["pattern_id"],
        asset=open_trade["asset"],
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_timestamp=open_trade["entry_timestamp"],
        exit_timestamp=exit_timestamp,
        pnl_pct=net_pnl,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        entry_confidence=open_trade["entry_confidence"],
        exit_reason=exit_reason,
        candles_held=open_trade["candles_held"],
        fees_pct=fees_pct,
        slippage_pct=slippage_pct,
        agent_id=agent_id,
    )


# =============================================================================
# Convenience Functions
# =============================================================================


def run_quick_backtest(
    pattern: dict[str, Any],
    candles: list[dict[str, Any]],
    asset: str = "BTC",
) -> dict[str, Any]:
    """
    Run a quick backtest and return metrics.

    Args:
        pattern: Pattern dict.
        candles: OHLCV candles.
        asset: Asset symbol.

    Returns:
        Dict of metrics.
    """
    result = run_backtest(pattern, candles)
    return calculate_backtest_metrics(result.trades)


def validate_backtest_result(result: BacktestResult) -> list[str]:
    """
    Validate backtest result for common issues.

    Returns list of warning messages.
    """
    warnings = []

    if result.total_trades < 30:
        warnings.append(f"Low trade count ({result.total_trades}) - results may not be statistically significant")

    if result.sharpe_ratio > 3.0:
        warnings.append(f"Unusually high Sharpe ({result.sharpe_ratio:.2f}) - possible overfitting")

    if result.win_rate > 0.7:
        warnings.append(f"Unusually high win rate ({result.win_rate:.1%}) - possible lookahead bias")

    if result.max_drawdown_pct > 30:
        warnings.append(f"High drawdown ({result.max_drawdown_pct:.1f}%) - risk management concern")

    if result.total_fees_pct == 0 and result.total_trades > 0:
        warnings.append("No fees included - results may be optimistic")

    return warnings
