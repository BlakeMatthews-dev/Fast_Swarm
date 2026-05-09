#!/usr/bin/env python3
"""
Unified Pattern Matching and Simulation Engine.

This is the CANONICAL implementation for running trade simulations.
ALL callers should import from here:
- Pattern backtests (pg_backtest_runner.py)
- Agent backtests (local_backtest.py, walk_forward.py)
- Live trading (future)

Single source of truth prevents divergence between implementations.

The simulation engine:
1. Takes candles + pattern conditions
2. Matches entry conditions using metrics.pattern_matcher
3. Manages position lifecycle (entry, MFE/MAE tracking, exits)
4. Returns Trade objects with full detail for analysis/ML
"""

import json
import math

# Import from shared metrics module (the canonical matching logic)
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).parent.parent.parent / "local-utilities"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Import trait calculations
from backtesting.trait_calculations import (
    calculate_entry_confirmation_bars,
    calculate_exit_delay_bars,
    calculate_hold_limit_periods,
    calculate_position_size_usd,
    calculate_stop_loss,
    calculate_take_profit,
)
from metrics import (
    INDICATOR_COLS,
    TradingCosts,
    apply_entry_costs,
    apply_exit_costs,
    calculate_trade_costs,
    get_trading_costs,
    matches_all_conditions,
    matches_condition,
)

# Import core trade for compatibility
try:
    from core.trade import ClosedTrade as CoreClosedTrade
    from core.trade import TradeResult

    HAS_CORE_TRADE = True
except ImportError:
    HAS_CORE_TRADE = False
    CoreClosedTrade = None
    TradeResult = None

# Centralized logging
try:
    from logging_config import LogContext, ctx, get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)
    LogContext = None
    ctx = lambda *args, **kwargs: {}


# =============================================================================
# Configuration (matches TypeScript DEFAULT_BACKTEST_CONFIG)
# =============================================================================
MIN_CANDLES = 25  # Indicator warmup period
STOP_LOSS_PCT = -10.0
TAKE_PROFIT_PCT = 25.0
HOLD_LIMIT_1D = 30  # 30 days max hold for daily candles
HOLD_LIMIT_1H = 168  # 7 days max hold for hourly candles


# =============================================================================
# Trade Dataclass
# =============================================================================


@dataclass
class Trade:
    """
    Single executed trade with full indicator capture and MFE/MAE tracking.

    Used by all backtest/simulation engines for detailed analysis.
    Provides conversion to core.ClosedTrade for compatibility with fitness calculators.
    """

    pnl_pct: float
    duration: int
    entry_price: float
    exit_price: float
    entry_timestamp: int
    exit_timestamp: int
    # Exit details
    exit_reason: str = ""  # 'take_profit', 'stop_loss', 'timeout', 'trailing_*', 'ml_exit_*'
    entry_indicators: dict[str, float] = field(default_factory=dict)
    exit_indicators: dict[str, float] = field(default_factory=dict)
    costs: TradingCosts | None = None
    gross_pnl_pct: float = 0.0  # PnL before costs

    # MFE/MAE tracking (Max Favorable/Adverse Excursion)
    mfe_pct: float = 0.0  # Maximum unrealized profit during trade
    mae_pct: float = 0.0  # Maximum unrealized loss during trade (negative)
    mfe_timestamp: int = 0  # When max profit occurred
    mae_timestamp: int = 0  # When max drawdown occurred
    mfe_bars_from_entry: int = 0  # Bars after entry when MFE occurred
    mae_bars_from_entry: int = 0  # Bars after entry when MAE occurred

    # Context fields
    pattern_name: str = ""
    symbol: str = ""
    side: str = "long"
    size_usd: float = 100.0  # Default position size

    # Pattern conditions (WHY the trade happened)
    entry_conditions: list[dict] = field(default_factory=list)
    exit_conditions: dict = field(default_factory=dict)

    # Enhanced context fields
    timeframe: str = "1h"
    ai_confidence: float | None = None
    regime_at_entry: str | None = None
    agent_traits_snapshot: dict[str, float] | None = None

    @property
    def exit_efficiency(self) -> float:
        """How much of the max profit was captured (pnl / mfe)."""
        if self.mfe_pct <= 0:
            return 0.0
        return min(1.0, max(-1.0, self.pnl_pct / self.mfe_pct))

    def to_core_trade(self) -> "CoreClosedTrade":
        """Convert to core.ClosedTrade for compatibility with fitness calculators."""
        if not HAS_CORE_TRADE or CoreClosedTrade is None:
            raise ImportError("core.trade module not available")
        return CoreClosedTrade(
            pattern_name=self.pattern_name or "unknown",
            symbol=self.symbol or "unknown",
            side=self.side,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            entry_time=self.entry_timestamp,
            exit_time=self.exit_timestamp,
            size_usd=self.size_usd,
            pnl_pct=self.pnl_pct,
            gross_pnl_pct=self.gross_pnl_pct,
            exit_reason=self.exit_reason,
            mfe_pct=self.mfe_pct,
            mae_pct=self.mae_pct,
            entry_indicators=self.entry_indicators,
            exit_indicators=self.exit_indicators,
            slippage_pct=self.costs.slippage_bps / 100 if self.costs else 0.0,
            fee_rate_bps=self.costs.round_trip_fee_bps if self.costs else 0.0,
            venue_type="backtest",
        )

    def to_trade_result(self) -> "TradeResult":
        """Convert to TradeResult for fitness calculation."""
        if not HAS_CORE_TRADE or TradeResult is None:
            raise ImportError("core.trade module not available")
        return TradeResult(pnl_pct=self.pnl_pct, is_win=self.pnl_pct > 0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for agent memory recording."""
        return {
            "pnl_pct": self.pnl_pct,
            "duration": self.duration,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "exit_reason": self.exit_reason,
            "entry_indicators": self.entry_indicators,
            "exit_indicators": self.exit_indicators,
            "gross_pnl_pct": self.gross_pnl_pct,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "mfe_timestamp": self.mfe_timestamp,
            "mae_timestamp": self.mae_timestamp,
            "mfe_bars_from_entry": self.mfe_bars_from_entry,
            "mae_bars_from_entry": self.mae_bars_from_entry,
            "pattern_name": self.pattern_name,
            "symbol": self.symbol,
            "side": self.side,
            "size_usd": self.size_usd,
            "is_win": self.pnl_pct > 0,
            "entry_conditions": self.entry_conditions,
            "exit_conditions": self.exit_conditions,
            "timeframe": self.timeframe,
            "ai_confidence": self.ai_confidence,
            "regime_at_entry": self.regime_at_entry,
            "agent_traits_snapshot": self.agent_traits_snapshot,
        }


# =============================================================================
# Timestamp Conversion
# =============================================================================


def timestamp_to_int(ts) -> int:
    """Convert a pandas Timestamp or datetime to Unix timestamp (milliseconds)."""
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    if hasattr(ts, "value"):  # pandas Timestamp
        try:
            return int(ts.value // 1_000_000)
        except Exception:
            pass
    if hasattr(ts, "timestamp"):  # datetime
        try:
            return int(ts.timestamp() * 1000)
        except Exception:
            pass
    try:
        return int(ts)
    except (ValueError, TypeError):
        return 0


# =============================================================================
# Indicator Extraction
# =============================================================================


def extract_indicators(row: dict) -> dict[str, float]:
    """Extract all indicator values from a candle row."""
    BASE_COLS = {
        "asset",
        "timestamp",
        "timeframe",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "computed_at",
        "time",
        "date",
        "symbol",
        "index",
    }
    indicators = {}
    cols_to_check = INDICATOR_COLS if INDICATOR_COLS else row.keys()
    for col in cols_to_check:
        if col in BASE_COLS:
            continue
        val = row.get(col)
        if val is not None and isinstance(val, (int, float)):
            if not (math.isnan(val) or math.isinf(val)):
                indicators[col] = float(val)
    return indicators


# =============================================================================
# Regime Classification
# =============================================================================


def classify_regime(indicators: dict[str, float]) -> str:
    """
    Classify market regime from actual indicator values.

    Regimes:
    - 'bull': Strong upward trend (ADX > 25, RSI > 55, positive returns)
    - 'bear': Strong downward trend (ADX > 25, RSI < 45, negative returns)
    - 'chop': Choppy/ranging market (ADX < 25, high volatility)
    - 'lowvol': Low volatility consolidation (ADX < 20, low volatility)
    - 'neutral': Unclear/transitional regime
    """
    adx = indicators.get("adx_14", indicators.get("adx", 25))
    rsi = indicators.get("rsi_14", indicators.get("rsi", 50))
    vol_pct = indicators.get("volatility_percentile", indicators.get("vol_percentile", 50))
    ret_10 = indicators.get("return_10", indicators.get("ret_10", 0))
    ret_20 = indicators.get("return_20", indicators.get("ret_20", 0))

    trend_strength = adx > 25 if adx else False

    if trend_strength:
        bullish_signals = sum(
            [
                rsi > 55 if rsi else False,
                ret_10 > 0 if ret_10 else False,
                ret_20 > 0 if ret_20 else False,
            ]
        )
        bearish_signals = sum(
            [
                rsi < 45 if rsi else False,
                ret_10 < 0 if ret_10 else False,
                ret_20 < 0 if ret_20 else False,
            ]
        )
        if bullish_signals >= 2:
            return "bull"
        elif bearish_signals >= 2:
            return "bear"

    if adx and adx < 20 and vol_pct and vol_pct < 30:
        return "lowvol"
    if adx and adx < 25 and vol_pct and vol_pct > 60:
        return "chop"

    return "neutral"


# =============================================================================
# Condition Confidence
# =============================================================================


def calculate_condition_confidence(
    actual: float,
    operator: str,
    threshold: float | None,
    threshold_max: float | None,
    indicator: str,
) -> float | None:
    """
    Calculate confidence score for a condition trigger.
    Confidence = distance from threshold normalized by typical indicator range.
    """
    if actual is None or threshold is None:
        return None

    INDICATOR_RANGES = {
        "RSI": (0, 100),
        "ADX": (0, 100),
        "CCI": (-200, 200),
        "WILLR": (-100, 0),
        "MFI": (0, 100),
        "STOCH": (0, 100),
        "ROC": (-50, 50),
        "ATR": (0, 10),
        "OBV": None,
        "MACD": None,
    }

    indicator_type = None
    for key in INDICATOR_RANGES:
        if key in indicator.upper():
            indicator_type = key
            break

    typical_range = INDICATOR_RANGES.get(indicator_type)
    if not typical_range:
        typical_range = (0, 100)

    range_size = typical_range[1] - typical_range[0]
    if range_size <= 0:
        return None

    if operator == "<":
        distance = threshold - actual
    elif operator == ">":
        distance = actual - threshold
    elif operator == "between" and threshold_max:
        dist_to_min = actual - threshold
        dist_to_max = threshold_max - actual
        distance = min(dist_to_min, dist_to_max)
    else:
        return None

    confidence = max(0, min(1, distance / range_size))
    return confidence


def calculate_entry_confidence(
    indicators: dict[str, float],
    conditions: list[dict],
) -> float | None:
    """Calculate overall entry confidence (minimum across all conditions)."""
    if not conditions:
        return None

    confidences = []
    for cond in conditions:
        indicator = cond.get("indicator", "")
        operator = cond.get("operator", "")
        threshold = cond.get("value")
        threshold_max = cond.get("max_value")

        actual = indicators.get(indicator)
        if actual is None:
            for key in indicators:
                if indicator.lower() in key.lower():
                    actual = indicators[key]
                    break

        if actual is None or threshold is None:
            continue

        conf = calculate_condition_confidence(
            actual=actual,
            operator=operator,
            threshold=threshold,
            threshold_max=threshold_max,
            indicator=indicator,
        )
        if conf is not None:
            confidences.append(conf)

    if not confidences:
        return None
    return min(confidences)


# =============================================================================
# Exit Condition Parsing
# =============================================================================


def parse_exit_conditions(exit_conditions) -> dict:
    """Parse exit conditions from pattern (handles JSON string, dict, or list)."""
    if not exit_conditions:
        return {}

    if isinstance(exit_conditions, str):
        try:
            parsed = json.loads(exit_conditions)
            if isinstance(parsed, list):
                return _merge_exit_conditions_list(parsed)
            return parsed
        except json.JSONDecodeError:
            logger.warning("Failed to parse exit conditions")
            return {}

    if isinstance(exit_conditions, list):
        return _merge_exit_conditions_list(exit_conditions)

    return exit_conditions


def _merge_exit_conditions_list(conditions_list: list) -> dict:
    """Merge a list of exit condition dicts into a single dict."""
    if not conditions_list:
        return {}

    result = {}
    for item in conditions_list:
        if not isinstance(item, dict):
            continue
        if "stop_loss_pct" in item or "take_profit_pct" in item or "max_hold_periods" in item:
            result.update(item)
        elif "type" in item and "value" in item:
            exit_type = item["type"]
            exit_value = item["value"]
            if exit_type == "trailing_stop":
                result["trailing_stop_pct"] = exit_value
            elif exit_type == "take_profit":
                result["take_profit_pct"] = exit_value
            elif exit_type == "stop_loss":
                result["stop_loss_pct"] = -abs(exit_value)
            elif exit_type == "max_hold":
                result["max_hold_periods"] = int(exit_value)
            else:
                result[exit_type] = exit_value
        else:
            result.update(item)

    return result


# =============================================================================
# ML Indicator Exits
# =============================================================================


def check_ml_indicator_exits(
    indicators: dict, exit_conditions: dict, available_cols: set | None = None
) -> tuple[bool, str]:
    """Check if ML indicator exit conditions are met."""
    ml_exits = exit_conditions.get("ml_indicator_exits", [])
    if not ml_exits:
        return False, ""

    logic = exit_conditions.get("exit_logic", "OR")
    if available_cols is None:
        available_cols = set(indicators.keys())

    if logic == "AND":
        for exit_cond in ml_exits:
            if not matches_condition(indicators, exit_cond, available_cols):
                return False, ""
        indicator_name = ml_exits[0].get("indicator", "ml_indicator") if ml_exits else "ml_indicator"
        return True, f"ml_exit_{indicator_name}"
    else:
        for exit_cond in ml_exits:
            if matches_condition(indicators, exit_cond, available_cols):
                indicator_name = exit_cond.get("indicator", "ml_indicator")
                return True, f"ml_exit_{indicator_name}"
        return False, ""


# =============================================================================
# Dynamic Exit Strategies
# =============================================================================


def calculate_dynamic_trail_pct(
    profit_pct: float, base_trail: float = 2.0, max_trail: float = 12.0, log_scale: float = 2.5
) -> float:
    """Logarithmic trailing stop that widens as profit grows."""
    if profit_pct <= 0:
        return base_trail
    log_component = log_scale * math.log1p(profit_pct / 10)
    return min(base_trail + log_component, max_trail)


def get_atr_multiplier_for_profit(profit_pct: float) -> float:
    """ATR multiplier that scales with profit tier."""
    if profit_pct <= 0 or profit_pct < 5:
        return 2.0
    elif profit_pct < 15:
        return 2.5
    elif profit_pct < 30:
        return 3.0
    elif profit_pct < 50:
        return 3.5
    else:
        return 4.0


def calculate_trailing_stop_price(
    entry_price: float, peak_price: float, profit_pct: float, trail_config: dict, atr_value: float = 0.0
) -> tuple[float, str]:
    """Calculate trailing stop price based on configured exit strategy."""
    # ATR-based trailing (highest priority)
    if trail_config.get("use_atr_trailing") and atr_value > 0:
        multiplier = get_atr_multiplier_for_profit(profit_pct)
        atr_distance = multiplier * atr_value
        stop_price = peak_price - atr_distance
        if profit_pct > 0:
            stop_price = max(stop_price, entry_price * 1.001)
        return stop_price, "atr_trail"

    # Dynamic/logarithmic trailing
    if trail_config.get("use_dynamic_trail"):
        dynamic_offset = calculate_dynamic_trail_pct(profit_pct)
        stop_price = peak_price * (1 - dynamic_offset / 100)
        return stop_price, "dynamic_trail"

    # Fixed trailing
    if trail_config.get("use_trailing_stop"):
        offset = trail_config.get("trailing_stop_offset_pct", 2.0)
        stop_price = peak_price * (1 - offset / 100)
        offset_label = f"{offset:.1f}".rstrip("0").rstrip(".")
        return stop_price, f"trailing_{offset_label}pct"

    return 0.0, ""


# =============================================================================
# Main Simulation Engine
# =============================================================================


def run_simulation(
    df: pd.DataFrame,
    conditions: list,
    asset: str,
    timeframe: str,
    stop_loss_pct: float = STOP_LOSS_PCT,
    take_profit_pct: float = TAKE_PROFIT_PCT,
    capture_indicators: bool = True,
    exit_conditions: dict | None = None,
    pattern_id: str = "",
    position_size_usd: float = 100.0,
    agent_traits: dict[str, float] | None = None,
    use_ai: bool = False,
    ai_confidence_threshold: float = 0.4,
) -> list[Trade]:
    """
    Run backtest simulation on candles with full indicator capture.

    This is the CANONICAL simulation engine. All callers should use this.

    Args:
        df: DataFrame with OHLCV and calculated indicators
        conditions: Pattern entry conditions
        asset: Asset symbol (for cost calculation)
        timeframe: '1d' or '1h'
        stop_loss_pct: Stop loss threshold (can be overridden by exit_conditions/traits)
        take_profit_pct: Take profit threshold (can be overridden by exit_conditions/traits)
        capture_indicators: Whether to capture full indicator state
        exit_conditions: Optional ML/dynamic exit conditions (parsed dict)
        pattern_id: Pattern identifier for context tracking
        position_size_usd: Position size for trade conversion
        agent_traits: Optional dict of agent traits for trait-aware backtesting
        use_ai: Whether to consult AI for low-confidence entries
        ai_confidence_threshold: Below this confidence, ask AI

    Returns:
        List of Trade objects with full details
    """
    trades = []
    in_position = False
    entry_price = 0.0
    raw_entry_price = 0.0
    entry_index = 0
    entry_timestamp = 0
    entry_indicators = {}

    # MFE/MAE tracking
    mfe_pct = 0.0
    mae_pct = 0.0
    mfe_timestamp = 0
    mae_timestamp = 0
    mfe_bars_from_entry = 0
    mae_bars_from_entry = 0

    entry_confidence: float | None = None
    peak_price = 0.0

    # Initialize AI inference if requested
    ai_inference = None
    if use_ai:
        try:
            from ml.integration import UnifiedTradingInference

            ai_inference = UnifiedTradingInference(
                model_id="qwen-trading",
                traits=agent_traits,
            )
        except ImportError:
            try:
                from fast_trading_inference import TradingInference

                ai_inference = TradingInference()
                if not ai_inference.is_available():
                    ai_inference = None
            except ImportError:
                pass

    # Get exit parameters
    if exit_conditions:
        effective_stop_loss = exit_conditions.get("stop_loss_pct", stop_loss_pct)
        effective_take_profit = exit_conditions.get("take_profit_pct", take_profit_pct)
        hold_limit = exit_conditions.get("max_hold_periods", HOLD_LIMIT_1D if timeframe == "1d" else HOLD_LIMIT_1H)
    else:
        effective_stop_loss = stop_loss_pct
        effective_take_profit = take_profit_pct
        hold_limit = HOLD_LIMIT_1D if timeframe == "1d" else HOLD_LIMIT_1H

    # Apply trait-aware calculations
    effective_stop_loss = calculate_stop_loss(agent_traits, effective_stop_loss)
    effective_take_profit = calculate_take_profit(agent_traits, effective_take_profit)
    effective_position_size = calculate_position_size_usd(agent_traits, default_usd=position_size_usd)
    hold_limit = calculate_hold_limit_periods(agent_traits, hold_limit, timeframe)
    entry_confirmation_bars = calculate_entry_confirmation_bars(agent_traits)
    exit_delay_bars = calculate_exit_delay_bars(agent_traits)

    # Dynamic exit parameters
    use_trailing = False
    trailing_offset_pct = 2.0
    use_dynamic_trail = False
    use_atr_trail = False
    use_breakeven = False
    breakeven_trigger_pct = 5.0

    if exit_conditions:
        use_trailing = exit_conditions.get("use_trailing_stop", False)
        trailing_offset_pct = exit_conditions.get(
            "trailing_stop_offset_pct", exit_conditions.get("trailing_stop_pct", 2.0)
        )
        use_dynamic_trail = exit_conditions.get("use_dynamic_trail", False)
        use_atr_trail = exit_conditions.get("use_atr_trailing", False)
        use_breakeven = exit_conditions.get("use_breakeven_stop", False)
        breakeven_trigger_pct = exit_conditions.get("breakeven_trigger_pct", 5.0)

    # Entry confirmation tracking
    pending_entry = False
    confirmation_count = 0
    pending_entry_indicators = {}

    # Exit delay tracking
    pending_exit = False
    exit_delay_count = 0
    pending_exit_reason = ""

    trade_costs = calculate_trade_costs(asset)
    available_cols = set(df.columns)

    # Start after indicator warmup
    for i in range(MIN_CANDLES, len(df) - 1):
        row = df.iloc[i]
        row_dict = row.to_dict()

        if not in_position and not pending_entry:
            if matches_all_conditions(row_dict, conditions, available_cols):
                heuristic_confidence = calculate_entry_confidence(row_dict, conditions)
                final_confidence = heuristic_confidence

                # AI integration for mid-zone confidence
                if ai_inference and heuristic_confidence is not None and agent_traits:
                    uncertainty_anchor = agent_traits.get("uncertainty_anchor", 0.5)
                    ai_assist_range = agent_traits.get("ai_assist_range", 0.2)
                    mid_zone_low = uncertainty_anchor - ai_assist_range
                    mid_zone_high = uncertainty_anchor + ai_assist_range

                    if mid_zone_low <= heuristic_confidence <= mid_zone_high:
                        try:
                            rsi = row_dict.get("rsi_14", row_dict.get("rsi", 50))
                            macd = row_dict.get("macd_line", row_dict.get("macd", 0))
                            macd_str = "Bullish" if macd > 0 else ("Bearish" if macd < 0 else "Neutral")
                            price = row_dict.get("close", 0)
                            change = row_dict.get("return_1", 0) * 100

                            ai_decision = ai_inference.get_decision(
                                symbol=asset,
                                price=price,
                                change_24h=change,
                                rsi=rsi,
                                macd=macd_str,
                                signal=f"Pattern {pattern_id} triggered (conf={heuristic_confidence:.2f})",
                            )
                            if ai_decision.is_valid:
                                final_confidence = ai_decision.confidence / 100.0
                        except Exception:
                            pass

                entry_confidence = final_confidence

                if entry_confirmation_bars == 0:
                    in_position = True
                    raw_entry_price = row["close"]
                    entry_price = apply_entry_costs(raw_entry_price, asset)
                    entry_index = i
                    entry_timestamp = timestamp_to_int(row["timestamp"])
                    if capture_indicators:
                        entry_indicators = extract_indicators(row_dict)

                    mfe_pct = 0.0
                    mae_pct = 0.0
                    mfe_timestamp = entry_timestamp
                    mae_timestamp = entry_timestamp
                    mfe_bars_from_entry = 0
                    mae_bars_from_entry = 0
                    peak_price = raw_entry_price
                else:
                    pending_entry = True
                    confirmation_count = 1
                    if capture_indicators:
                        pending_entry_indicators = extract_indicators(row_dict)

        elif pending_entry and not in_position:
            if matches_all_conditions(row_dict, conditions, available_cols):
                confirmation_count += 1
                if confirmation_count >= entry_confirmation_bars:
                    in_position = True
                    pending_entry = False
                    raw_entry_price = row["close"]
                    entry_price = apply_entry_costs(raw_entry_price, asset)
                    entry_index = i
                    entry_timestamp = timestamp_to_int(row["timestamp"])
                    if capture_indicators:
                        entry_indicators = extract_indicators(row_dict)

                    mfe_pct = 0.0
                    mae_pct = 0.0
                    mfe_timestamp = entry_timestamp
                    mae_timestamp = entry_timestamp
                    mfe_bars_from_entry = 0
                    mae_bars_from_entry = 0
                    confirmation_count = 0
                    peak_price = raw_entry_price
            else:
                pending_entry = False
                confirmation_count = 0
                pending_entry_indicators = {}

        elif in_position:
            hold_duration = i - entry_index
            raw_exit_price = row["close"]
            exit_price = apply_exit_costs(raw_exit_price, asset)
            current_timestamp = timestamp_to_int(row["timestamp"])

            gross_pnl_pct = ((raw_exit_price - raw_entry_price) / raw_entry_price) * 100
            net_pnl_pct = ((exit_price - entry_price) / entry_price) * 100

            costs = get_trading_costs(asset)
            fee_cost_pct = costs["fee_bps"] / 100 * 2
            net_pnl_pct -= fee_cost_pct

            # Track MFE/MAE
            unrealized_pct = gross_pnl_pct
            if unrealized_pct > mfe_pct:
                mfe_pct = unrealized_pct
                mfe_timestamp = current_timestamp
                mfe_bars_from_entry = hold_duration
            if unrealized_pct < mae_pct:
                mae_pct = unrealized_pct
                mae_timestamp = current_timestamp
                mae_bars_from_entry = hold_duration

            if raw_exit_price > peak_price:
                peak_price = raw_exit_price

            # Handle pending exit delay
            if pending_exit:
                exit_delay_count += 1
                if exit_delay_count >= exit_delay_bars:
                    exit_indicators = {}
                    if capture_indicators:
                        exit_indicators = extract_indicators(row_dict)

                    trades.append(
                        Trade(
                            pnl_pct=net_pnl_pct,
                            duration=hold_duration,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            entry_timestamp=entry_timestamp,
                            exit_timestamp=current_timestamp,
                            exit_reason=pending_exit_reason,
                            entry_indicators=entry_indicators,
                            exit_indicators=exit_indicators,
                            costs=trade_costs,
                            gross_pnl_pct=gross_pnl_pct,
                            mfe_pct=mfe_pct,
                            mae_pct=mae_pct,
                            mfe_timestamp=mfe_timestamp,
                            mae_timestamp=mae_timestamp,
                            mfe_bars_from_entry=mfe_bars_from_entry,
                            mae_bars_from_entry=mae_bars_from_entry,
                            pattern_name=pattern_id,
                            symbol=asset,
                            side="long",
                            size_usd=effective_position_size,
                            entry_conditions=conditions,
                            exit_conditions=exit_conditions or {},
                            timeframe=timeframe,
                            ai_confidence=entry_confidence,
                            regime_at_entry=classify_regime(entry_indicators),
                            agent_traits_snapshot=dict(agent_traits) if agent_traits else None,
                        )
                    )
                    in_position = False
                    pending_exit = False
                    exit_delay_count = 0
                    pending_exit_reason = ""
                    entry_indicators = {}
                continue

            # Determine exit reason
            exit_reason = ""
            should_exit = False

            # 1. STOP LOSS
            if net_pnl_pct <= effective_stop_loss:
                should_exit = True
                exit_reason = "stop_loss"

            # 2. TRAILING STOP
            elif (use_trailing or use_dynamic_trail or use_atr_trail) and peak_price > 0:
                atr_value = row_dict.get("ATR_14", row_dict.get("atr_14", row_dict.get("atr", 0)))
                trail_config = {
                    "use_trailing_stop": use_trailing,
                    "trailing_stop_offset_pct": trailing_offset_pct,
                    "use_dynamic_trail": use_dynamic_trail,
                    "use_atr_trailing": use_atr_trail,
                }
                trailing_stop, exit_label = calculate_trailing_stop_price(
                    entry_price=raw_entry_price,
                    peak_price=peak_price,
                    profit_pct=gross_pnl_pct,
                    trail_config=trail_config,
                    atr_value=atr_value,
                )
                if trailing_stop > 0 and raw_exit_price <= trailing_stop:
                    should_exit = True
                    exit_reason = exit_label

            # 3. BREAKEVEN STOP
            if not should_exit and use_breakeven and gross_pnl_pct >= breakeven_trigger_pct:
                breakeven_stop = raw_entry_price * 1.001
                if raw_exit_price <= breakeven_stop:
                    should_exit = True
                    exit_reason = "breakeven_stop"

            # 4. FIXED TAKE PROFIT (only if trailing NOT enabled)
            if not should_exit and not (use_trailing or use_dynamic_trail or use_atr_trail):
                if net_pnl_pct >= effective_take_profit:
                    should_exit = True
                    exit_reason = "take_profit"

            # 5. MAX HOLD TIMEOUT (only if trailing NOT enabled)
            if not should_exit and not (use_trailing or use_dynamic_trail or use_atr_trail):
                if hold_duration >= hold_limit:
                    should_exit = True
                    exit_reason = "timeout"

            # 6. ML INDICATOR EXITS
            if not should_exit and exit_conditions:
                ml_exit, ml_reason = check_ml_indicator_exits(row_dict, exit_conditions, available_cols)
                if ml_exit:
                    should_exit = True
                    exit_reason = ml_reason

            if should_exit:
                if exit_reason == "stop_loss" or exit_delay_bars == 0:
                    exit_indicators = {}
                    if capture_indicators:
                        exit_indicators = extract_indicators(row_dict)

                    trades.append(
                        Trade(
                            pnl_pct=net_pnl_pct,
                            duration=hold_duration,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            entry_timestamp=entry_timestamp,
                            exit_timestamp=current_timestamp,
                            exit_reason=exit_reason,
                            entry_indicators=entry_indicators,
                            exit_indicators=exit_indicators,
                            costs=trade_costs,
                            gross_pnl_pct=gross_pnl_pct,
                            mfe_pct=mfe_pct,
                            mae_pct=mae_pct,
                            mfe_timestamp=mfe_timestamp,
                            mae_timestamp=mae_timestamp,
                            mfe_bars_from_entry=mfe_bars_from_entry,
                            mae_bars_from_entry=mae_bars_from_entry,
                            pattern_name=pattern_id,
                            symbol=asset,
                            side="long",
                            size_usd=effective_position_size,
                            entry_conditions=conditions,
                            exit_conditions=exit_conditions or {},
                            timeframe=timeframe,
                            ai_confidence=entry_confidence,
                            regime_at_entry=classify_regime(entry_indicators),
                            agent_traits_snapshot=dict(agent_traits) if agent_traits else None,
                        )
                    )
                    in_position = False
                    entry_indicators = {}
                else:
                    pending_exit = True
                    exit_delay_count = 1
                    pending_exit_reason = exit_reason

    return trades
