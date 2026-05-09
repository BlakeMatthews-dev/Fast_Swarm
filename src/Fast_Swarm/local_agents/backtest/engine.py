"""
Local Backtest Engine for Agent Evolution.

Runs backtests against real OHLCV data and returns TradeRecords
compatible with the evolution system.

Exit Strategies:
- FIXED: Standard stop-loss/take-profit
- TRAILING_*: Trailing stop at fixed percentage from peak
- DYNAMIC_TRAIL: Logarithmic trail widening (tight at 0% profit → wide at 100%)
- SCALED_OUT: Partial exits at profit milestones
- BREAKEVEN_TRAIL: Move stop to entry after +X% profit
- ATR_TRAIL: 2x ATR trailing stop
- ACCUMULATION: No stop loss for high-conviction assets (BTC, ETH, SOL)

Accumulation Mode (default ON for BTC/ETH/SOL):
- No stop loss - positions hold through any drawdown
- Exit only on: take profit OR end of data
- Rationale: These assets historically recover from any bear market
- Assumes patient capital with long time horizon
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions
from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
from Fast_Swarm.local_agents.core.state import AgentRecord, TradeRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.shared.fast_inference import DecisionRequest, FastDecisionEngine
from Fast_Swarm.local_agents.shared.llm_client import AIZoneHandler, AIZoneMode

# =============================================================================
# Exit Strategy Types
# =============================================================================


class ExitStrategy(Enum):
    """Available exit strategies for backtesting."""

    FIXED = "fixed"  # Fixed TP/SL only
    TRAILING_2PCT = "trailing_2pct"  # 2% trailing stop
    TRAILING_3PCT = "trailing_3pct"  # 3% trailing stop
    TRAILING_5PCT = "trailing_5pct"  # 5% trailing stop
    DYNAMIC_TRAIL = "dynamic_trail"  # Logarithmic widening (2% → 12%)
    SCALED_OUT = "scaled_out"  # 25% exit at each milestone
    BREAKEVEN_TRAIL = "breakeven_trail"  # Move to breakeven after +5%
    ATR_TRAIL = "atr_trail"  # 2x ATR from highwater
    ACCUMULATION = "accumulation"  # No stop loss, only exit on profit or end of data


# =============================================================================
# Accumulation Mode - High-conviction assets that never exit at a loss
# =============================================================================

# MAJORS: USD pairs for BTC, ETH, SOL - hold forever
MAJOR_USD_ASSETS = {
    "BTC",
    "ETH",
    "SOL",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
}

# CROSS PAIRS: Trade ratios to accumulate more of base asset
# Goal: Accumulate more BTC by trading ETH/BTC and SOL/BTC ratios
CROSS_PAIR_ASSETS = {
    # ETH priced in BTC
    "ETH/BTC",
    "ETHBTC",
    "ETH-BTC",
    # SOL priced in BTC
    "SOL/BTC",
    "SOLBTC",
    "SOL-BTC",
    # SOL priced in ETH
    "SOL/ETH",
    "SOLETH",
    "SOL-ETH",
    # Inverse notations
    "BTC/ETH",
    "BTCETH",
    "BTC-ETH",
    "BTC/SOL",
    "BTCSOL",
    "BTC-SOL",
    "ETH/SOL",
    "ETHSOL",
    "ETH-SOL",
}

# Combined: All assets that get accumulation treatment (no stop loss)
ACCUMULATION_ASSETS = MAJOR_USD_ASSETS | CROSS_PAIR_ASSETS

# ALTS: Everything else - short-term profit attempts WITH stop losses
# (Learned the hard way: 99% down alts don't recover)


# =============================================================================
# Dynamic Trail Calculation
# =============================================================================


def calculate_dynamic_trail(
    profit_pct: float,
    base_trail: float = 2.0,
    max_trail: float = 12.0,
    log_scale: float = 2.5,
) -> float:
    """
    Calculate trail percentage based on current profit.

    Uses logarithmic scaling so trail widens as profit grows,
    but with diminishing increases (protects gains better).

    Philosophy: Small gains = tight protection, big gains = room to run.
      - 0% profit  -> 2.0% trail (tight)
      - 10% profit -> 4.0% trail
      - 50% profit -> 7.0% trail
      - 100% profit -> 9.0% trail (moonshot mode)

    Args:
        profit_pct: Current profit percentage (e.g., 10.0 for 10%)
        base_trail: Minimum trail at 0% profit
        max_trail: Maximum trail (cap)
        log_scale: How aggressively trail widens

    Returns:
        Trail percentage to use
    """
    if profit_pct <= 0:
        return base_trail

    # Logarithmic scaling: trail = base + scale * ln(1 + profit/10)
    log_component = log_scale * math.log1p(profit_pct / 10)
    trail = base_trail + log_component

    return min(trail, max_trail)


# Optional vLLM import (may not be installed)
try:
    from Fast_Swarm.local_agents.shared.vllm_client import VLLMAIZoneHandler, VLLMClient  # noqa: F401

    HAS_VLLM = True
except ImportError:
    HAS_VLLM = False


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

# Convenient lookup dict for tests
ASSET_TIERS = {
    "tier1": TIER1_ASSETS,
    "tier2": TIER2_ASSETS,
    "tier3": TIER3_ASSETS,
}


def get_asset_tier(asset: str) -> str:
    """Get liquidity tier for an asset."""
    symbol = asset.replace("-USD", "").upper()
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


# =============================================================================
# Backtest Configuration
# =============================================================================


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    # Trade parameters (can be overridden by agent traits)
    max_position_pct: float = 0.05  # 5% default position size
    default_stop_loss_pct: float = 0.10  # 10% stop loss
    default_take_profit_pct: float = 0.25  # 25% take profit
    max_hold_candles: int = 168  # 7 days for 1h candles (DEPRECATED - not enforced)

    # Exit strategy configuration
    exit_strategy: ExitStrategy = ExitStrategy.FIXED

    # Accumulation mode - for high-conviction assets (BTC, ETH, SOL)
    # When enabled: no stop loss, unlimited capital, only exit on profit or end of data
    accumulation_mode: bool = True  # Default ON for BTC/ETH/SOL
    accumulation_assets: set = field(default_factory=lambda: ACCUMULATION_ASSETS)
    unlimited_capital: bool = True  # Can open new positions while others are underwater
    trailing_stop_pct: float = 3.0  # For TRAILING_* strategies
    breakeven_trigger_pct: float = 5.0  # For BREAKEVEN_TRAIL

    # Scaled exit levels (for SCALED_OUT strategy)
    # List of (profit_pct_of_target, exit_size_pct) tuples
    scaled_exit_levels: list[tuple] = field(
        default_factory=lambda: [
            (0.25, 25),  # Exit 25% of position at 25% of TP
            (0.50, 25),  # Exit 25% at 50% of TP
            (0.75, 25),  # Exit 25% at 75% of TP
            # Remaining 25% at full TP or SL
        ]
    )

    # ATR multiplier for ATR_TRAIL
    atr_multiplier: float = 2.0

    # Legacy aliases for compatibility
    @property
    def stop_loss_pct(self) -> float:
        return -self.default_stop_loss_pct * 100

    @property
    def take_profit_pct(self) -> float:
        return self.default_take_profit_pct * 100

    # Minimum confidence to enter
    min_confidence: float = 0.3

    # Data parameters
    min_candles_warmup: int = 50
    timeframe: str = "1h"

    # Cost modeling
    include_costs: bool = True

    @classmethod
    def from_traits(cls, traits: AgentTraits) -> BacktestConfig:
        """Create config from agent traits."""
        from Fast_Swarm.local_agents.core.traits import (
            calculate_max_hold_duration_ms,
            calculate_position_size,
            calculate_stop_loss_distance,
            calculate_take_profit_distance,
        )

        # Convert trait values to trading parameters
        position_size = calculate_position_size(traits.risk_tolerance)
        stop_loss = calculate_stop_loss_distance(traits.stop_loss_tightness)
        take_profit = calculate_take_profit_distance(traits.profit_target_greed)

        # Convert hold duration (ms) to candles (assume 1h)
        hold_ms = calculate_max_hold_duration_ms(traits.hold_duration_bias)
        max_hold_candles = max(1, int(hold_ms / 3_600_000))  # 1h = 3.6M ms

        return cls(
            max_position_pct=position_size,
            default_stop_loss_pct=stop_loss,
            default_take_profit_pct=take_profit,
            max_hold_candles=max_hold_candles,
            min_confidence=traits.min_threshold,
        )


# =============================================================================
# Trade State
# =============================================================================


@dataclass
class OpenTrade:
    """State of an open trade."""

    trade_id: str
    agent_id: str
    pattern_id: str
    asset: str
    direction: str
    entry_price: float
    entry_timestamp: int
    entry_confidence: float
    decision_zone: str
    ai_consulted: bool
    ai_decision: str | None
    position_size_pct: float

    # MFE/MAE tracking
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    mfe_price: float = 0.0
    mae_price: float = 0.0
    candles_held: int = 0

    # Trailing stop tracking
    peak_price: float = 0.0  # Best price in our favor
    trailing_stop_price: float = 0.0  # Current trailing stop level
    breakeven_activated: bool = False  # For BREAKEVEN_TRAIL

    # Scaled exit tracking
    position_remaining_pct: float = 100.0  # How much position is left
    scaled_exits_completed: int = 0  # How many partial exits done

    def update_mfe_mae(self, current_price: float):
        """Update MFE/MAE based on current price."""
        # GUARD: Protect against zero entry price (CRASH-003)
        if self.entry_price <= 0:
            return
        if self.direction == "long":
            current_pnl = ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            current_pnl = ((self.entry_price - current_price) / self.entry_price) * 100

        if current_pnl > self.mfe_pct:
            self.mfe_pct = current_pnl
            self.mfe_price = current_price

        if current_pnl < self.mae_pct:
            self.mae_pct = current_pnl
            self.mae_price = current_price

    def update_trailing_stop(
        self,
        current_price: float,
        trail_pct: float,
        config: BacktestConfig,
    ) -> bool:
        """
        Update trailing stop based on current price and exit strategy.

        Args:
            current_price: Current market price.
            trail_pct: Trail percentage to use.
            config: Backtest configuration.

        Returns:
            True if trailing stop was triggered.
        """
        # GUARD: Protect against zero entry price (CRASH-003)
        if self.entry_price <= 0:
            return False
        # Calculate current PnL
        if self.direction == "long":
            current_pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            current_pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100

        # Update peak price (best price in our favor)
        if self.direction == "long":
            if current_price > self.peak_price:
                self.peak_price = current_price
        else:
            if self.peak_price == 0 or current_price < self.peak_price:
                self.peak_price = current_price

        # For DYNAMIC_TRAIL, calculate trail based on profit
        if config.exit_strategy == ExitStrategy.DYNAMIC_TRAIL:
            trail_pct = calculate_dynamic_trail(current_pnl_pct)

        # For BREAKEVEN_TRAIL, check if we should activate breakeven
        if config.exit_strategy == ExitStrategy.BREAKEVEN_TRAIL:
            if current_pnl_pct >= config.breakeven_trigger_pct and not self.breakeven_activated:
                self.breakeven_activated = True
                # Set stop to entry + tiny buffer
                if self.direction == "long":
                    self.trailing_stop_price = self.entry_price * 1.001
                else:
                    self.trailing_stop_price = self.entry_price * 0.999

        # Calculate new trailing stop level
        if self.direction == "long":
            new_stop = self.peak_price * (1 - trail_pct / 100)
            # Only ratchet up, never down
            if new_stop > self.trailing_stop_price:
                self.trailing_stop_price = new_stop
            # Check if triggered
            return current_price <= self.trailing_stop_price and self.trailing_stop_price > 0
        else:
            new_stop = self.peak_price * (1 + trail_pct / 100)
            # Only ratchet down for shorts, never up
            if self.trailing_stop_price == 0 or new_stop < self.trailing_stop_price:
                self.trailing_stop_price = new_stop
            # Check if triggered
            return current_price >= self.trailing_stop_price and self.trailing_stop_price > 0


# =============================================================================
# Local Backtest Engine
# =============================================================================


class LocalBacktestEngine:
    """
    Backtest engine that runs agents against real OHLCV data.

    Implements the BacktestEngine protocol from evolution.py.
    """

    def __init__(
        self,
        loader: OHLCVLoader | None = None,
        config: BacktestConfig | None = None,
        patterns: dict[str, dict] | None = None,
        ai_zone_mode: AIZoneMode = AIZoneMode.HEURISTIC,
        ai_zone_handler: AIZoneHandler | None = None,
        preloaded_candles: dict[str, pd.DataFrame] | None = None,
        use_fast_inference: bool = True,
    ):
        """
        Initialize the backtest engine.

        Args:
            loader: OHLCV data loader. Creates default if not provided.
            config: Backtest configuration.
            patterns: Dict of pattern_id -> pattern definition.
            ai_zone_mode: Mode for AI_REFLECT zone (SKIP, HEURISTIC, LLM, VLLM, UNIFIED).
            ai_zone_handler: Pre-configured handler (overrides ai_zone_mode).
            preloaded_candles: Pre-loaded candle data as dict of asset -> DataFrame.
                               Use this to avoid repeated DB calls when backtesting many agents.
            use_fast_inference: If True, use FastDecisionEngine for AI zone decisions (0.001ms).
                               This is the recommended mode for backtesting.
        """
        self.loader = loader or OHLCVLoader()
        self.default_config = config or BacktestConfig()
        self.patterns = patterns or {}
        self.preloaded_candles = preloaded_candles or {}
        self.use_fast_inference = use_fast_inference

        # Fast inference engine for backtesting (0.001ms per decision)
        if use_fast_inference:
            self.fast_engine = FastDecisionEngine(mode="heuristic")
            self.ai_zone_handler = None  # Not used in fast mode
        else:
            self.fast_engine = None
            # Create AI zone handler based on mode
            if ai_zone_handler:
                self.ai_zone_handler = ai_zone_handler
            elif ai_zone_mode == AIZoneMode.VLLM:
                if not HAS_VLLM:
                    print("[Engine] vLLM not available, falling back to heuristic mode")
                    self.ai_zone_handler = AIZoneHandler(mode=AIZoneMode.HEURISTIC)
                else:
                    self.ai_zone_handler = VLLMAIZoneHandler()
            else:
                self.ai_zone_handler = AIZoneHandler(mode=ai_zone_mode)

    def set_patterns(self, patterns: dict[str, dict]):
        """Set pattern definitions."""
        self.patterns = patterns

    def run(
        self,
        agent: AgentRecord,
        dataset: dict | None = None,
    ) -> list[TradeRecord]:
        """
        Run backtest for an agent.

        This is the main entry point called by the evolution system.

        Args:
            agent: Agent to backtest.
            dataset: Optional dataset config (asset, timeframe, date range).

        Returns:
            List of TradeRecords.
        """
        # Get agent traits (filter to known fields for backward compatibility)
        from dataclasses import fields as dataclass_fields

        known_fields = {f.name for f in dataclass_fields(AgentTraits)}
        filtered_traits = {k: v for k, v in agent.traits.items() if k in known_fields}
        traits = AgentTraits(**filtered_traits)

        # Create config from traits
        config = BacktestConfig.from_traits(traits)

        # Get patterns for this agent
        agent_patterns = self._get_agent_patterns(agent)
        if not agent_patterns:
            return []

        # Get dataset parameters
        if dataset:
            assets = dataset.get("assets", ["BTC"])
            timeframe = dataset.get("timeframe", "1h")
            start_ts = dataset.get("start_ts")
            end_ts = dataset.get("end_ts")
        else:
            # Default: backtest on BTC, ETH
            assets = ["BTC", "ETH"]
            timeframe = "1h"
            start_ts = None
            end_ts = None

        # Run backtest for each asset
        all_trades = []

        for asset in assets:
            trades = self._backtest_asset(
                agent=agent,
                traits=traits,
                patterns=agent_patterns,
                asset=asset,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                config=config,
            )
            all_trades.extend(trades)

        return all_trades

    def _get_agent_patterns(self, agent: AgentRecord) -> list[dict]:
        """Get pattern definitions for an agent.

        Uses agent's stored pattern COPIES if available (new format).
        Falls back to looking up by pattern_id in self.patterns (legacy).
        """
        patterns = []

        # Prefer agent's stored pattern copies (new format)
        if hasattr(agent, "pattern_copies") and agent.pattern_copies:
            for pattern in agent.pattern_copies:
                pattern_copy = pattern.copy()
                pattern_id = pattern_copy.get("pattern_id", "")
                # Apply agent's pattern weight if not already set
                if "weight" not in pattern_copy:
                    weight = agent.pattern_weights.get(pattern_id, 1.0) if agent.pattern_weights else 1.0
                    pattern_copy["weight"] = weight
                patterns.append(pattern_copy)
            return patterns

        # Fallback: Look up patterns by ID (legacy agents without copies)
        for pattern_id in agent.pattern_ids:
            if pattern_id in self.patterns:
                pattern = self.patterns[pattern_id].copy()
                pattern["pattern_id"] = pattern_id
                # Apply agent's pattern weight
                weight = agent.pattern_weights.get(pattern_id, 1.0) if agent.pattern_weights else 1.0
                pattern["weight"] = weight
                patterns.append(pattern)

        return patterns

    def _backtest_asset(
        self,
        agent: AgentRecord,
        traits: AgentTraits,
        patterns: list[dict],
        asset: str,
        timeframe: str,
        start_ts: int | None,
        end_ts: int | None,
        config: BacktestConfig,
    ) -> list[TradeRecord]:
        """Run backtest for a single asset."""
        # Calculate warmup lookback — need 200 candles before window start
        # so indicators (SMA_200, etc.) are fully warmed at the window's first candle
        WARMUP_CANDLES = 200
        tf_ms = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
        warmup_ms = WARMUP_CANDLES * tf_ms.get(timeframe, 3600000)
        warmup_start = (start_ts - warmup_ms) if start_ts else None

        # Use preloaded candles if available (avoids repeated DB calls)
        cache_key = f"{asset}_{timeframe}"
        if cache_key in self.preloaded_candles:
            candles_df = self.preloaded_candles[cache_key]
            # Include warmup period before window start
            if warmup_start is not None:
                candles_df = candles_df[candles_df["timestamp"] >= warmup_start]
            if end_ts is not None:
                candles_df = candles_df[candles_df["timestamp"] <= end_ts]
        else:
            # Load candle data from database (with warmup lookback)
            candles_df = self.loader.load_candles(
                asset=asset,
                timeframe=timeframe,
                start_ts=warmup_start,
                end_ts=end_ts,
                with_indicators=True,
            )

        if len(candles_df) < config.min_candles_warmup:
            # Log insufficient data for debugging (helps diagnose 0-trade patterns)
            cache_hit = cache_key in self.preloaded_candles if self.preloaded_candles else False
            if len(candles_df) == 0:
                print(
                    f"  [Engine] {asset}/{timeframe}: No candles loaded (cache={'HIT' if cache_hit else 'MISS'}, ts={start_ts}-{end_ts})"
                )
            else:
                print(
                    f"  [Engine] {asset}/{timeframe}: Only {len(candles_df)} candles (need {config.min_candles_warmup})"
                )
            return []

        # Get indicator columns (only numeric columns)
        base_cols = {"timestamp", "open", "high", "low", "close", "volume", "asset", "timeframe"}
        skip_cols = {"regime", "computed_at", "index", "time", "symbol", "timeframe", "exchange", "enriched_at"}
        indicator_cols = [
            c
            for c in candles_df.columns
            if c not in base_cols
            and c not in skip_cols
            and candles_df[c].dtype in ["float64", "int64", "float32", "int32"]
        ]

        # Pre-extract numpy arrays for fast iteration (avoids to_dict overhead)
        close_arr = candles_df["close"].to_numpy()
        timestamp_arr = candles_df["timestamp"].to_numpy()
        # Pre-extract indicator arrays and track valid (non-NaN) values
        indicator_arrays = {}
        for col in indicator_cols:
            arr = candles_df[col].to_numpy()
            indicator_arrays[col] = arr

        trades = []
        open_trade: OpenTrade | None = None

        # Trading costs
        costs_pct = get_trading_costs_pct(asset) if config.include_costs else 0.0

        n_candles = len(candles_df)

        # Find where the actual window starts (after warmup lookback)
        # Only open new trades after start_ts; warmup candles are for indicator context only
        trade_start_idx = config.min_candles_warmup  # Default: skip indicator warmup
        if start_ts is not None:
            for idx in range(len(timestamp_arr)):
                if int(timestamp_arr[idx]) >= start_ts:
                    trade_start_idx = max(trade_start_idx, idx)
                    break

        # Iterate through candles (skip warmup period)
        for i in range(trade_start_idx, n_candles):
            close_price = float(close_arr[i])
            timestamp = int(timestamp_arr[i])

            # Extract indicators using pre-extracted arrays (much faster than dict access)
            indicators = {"close": close_price}
            for col, arr in indicator_arrays.items():
                val = arr[i]
                # numpy handles NaN check more efficiently
                if val == val:  # Fast NaN check: NaN != NaN
                    indicators[col] = float(val)

            # If we have an open trade, check for exit
            if open_trade:
                open_trade.candles_held += 1
                open_trade.update_mfe_mae(close_price)

                should_exit, exit_reason = self._check_exit(
                    open_trade=open_trade,
                    indicators=indicators,
                    current_price=close_price,
                    patterns=patterns,
                    config=config,
                )

                if should_exit:
                    # Close trade
                    trade_record = self._close_trade(
                        open_trade=open_trade,
                        exit_price=close_price,
                        exit_timestamp=timestamp,
                        exit_reason=exit_reason,
                        costs_pct=costs_pct,
                    )
                    trades.append(trade_record)
                    open_trade = None

            # If no open trade, check for entry
            if open_trade is None:
                entry_result = self._check_entry(
                    indicators=indicators,
                    patterns=patterns,
                    traits=traits,
                    config=config,
                    recent_trades=trades[-10:] if trades else [],  # Pass last 10 trades
                    current_timestamp=timestamp,
                )

                if entry_result:
                    pattern_id, confidence, direction, decision_zone, ai_consulted, ai_decision = entry_result

                    # Determine position size from traits
                    from Fast_Swarm.local_agents.core.traits import calculate_position_size

                    position_size = calculate_position_size(traits.risk_tolerance)

                    open_trade = OpenTrade(
                        trade_id=str(uuid.uuid4()),
                        agent_id=agent.agent_id,
                        pattern_id=pattern_id,
                        asset=asset,
                        direction=direction,
                        entry_price=close_price,
                        entry_timestamp=timestamp,
                        entry_confidence=confidence,
                        decision_zone=decision_zone,
                        ai_consulted=ai_consulted,
                        ai_decision=ai_decision,
                        position_size_pct=position_size * 100,
                    )

        # Close any remaining open trade at end of data
        if open_trade:
            # GUARD: Ensure we have data before accessing (CRASH-013)
            if len(close_arr) == 0:
                return trades  # No data to close with
            trade_record = self._close_trade(
                open_trade=open_trade,
                exit_price=float(close_arr[-1]),
                exit_timestamp=int(timestamp_arr[-1]),
                exit_reason="end_of_data",
                costs_pct=costs_pct,
            )
            trades.append(trade_record)

        return trades

    def _check_entry(
        self,
        indicators: dict[str, float],
        patterns: list[dict],
        traits: AgentTraits,
        config: BacktestConfig,
        recent_trades: list | None = None,
        current_timestamp: int = 0,
    ) -> tuple[str, float, str, str, bool, str | None] | None:
        """
        Check if any pattern triggers entry.

        Returns:
            Tuple of (pattern_id, confidence, direction, decision_zone, ai_consulted, ai_decision) or None.
        """
        best_match = None
        best_confidence = 0.0

        for pattern in patterns:
            entry_conditions = pattern.get("entry_conditions", pattern.get("conditions", {}))
            if not entry_conditions:
                continue

            result = evaluate_conditions(entry_conditions, indicators, match_threshold=0.6)

            if result.matched and result.confidence > best_confidence:
                best_confidence = result.confidence
                best_match = pattern

        if best_match is None:
            return None

        # Check against decision zones
        zone_result = determine_zone(best_confidence, traits)

        if zone_result.zone == DecisionZone.SKIP:
            return None

        # Get pattern info for AI decision
        pattern_id = best_match.get("pattern_id", "unknown")
        pattern_name = best_match.get("name", pattern_id)
        direction = best_match.get("direction", "long")

        ai_consulted = False
        ai_decision = None

        if zone_result.zone == DecisionZone.AI_REFLECT:
            # Use fast inference for backtesting (0.001ms) or slow AI handler for live
            if self.use_fast_inference and self.fast_engine:
                # Calculate recent win rate
                recent_win_rate = 0.5
                if recent_trades:
                    wins = sum(
                        1
                        for t in recent_trades[-10:]
                        if (getattr(t, "pnl_pct", None) or (t.get("pnl_pct", 0) if isinstance(t, dict) else 0)) > 0
                    )
                    total = min(len(recent_trades), 10)
                    recent_win_rate = wins / total if total > 0 else 0.5

                req = DecisionRequest(
                    request_id=f"{pattern_id}_{current_timestamp}",
                    confidence=best_confidence,
                    rsi=indicators.get("rsi_14", indicators.get("RSI_14", 50)),
                    macd=indicators.get("macd_histogram", indicators.get("MACDh_12_26_9", 0)),
                    risk_tolerance=traits.risk_tolerance,
                    entry_aggression=traits.entry_aggression,
                    recent_win_rate=recent_win_rate,
                    pattern_name=pattern_name,
                )
                result = self.fast_engine.decide(req)
                should_trade = result.should_trade
                ai_consulted = False  # Heuristic, not AI
                ai_decision = "TAKE" if should_trade else "SKIP"
            else:
                # Use slow AI zone handler (for live trading or when fast disabled)
                recent_trade_dicts = None
                if recent_trades:
                    recent_trade_dicts = []
                    for t in recent_trades:
                        if hasattr(t, "pnl_pct"):
                            recent_trade_dicts.append({"pnl_pct": t.pnl_pct})
                        elif isinstance(t, dict):
                            recent_trade_dicts.append({"pnl_pct": t.get("pnl_pct", 0)})

                traits_dict = {
                    "risk_tolerance": traits.risk_tolerance,
                    "entry_aggression": traits.entry_aggression,
                    "volatility_seeking": traits.volatility_seeking,
                }

                should_trade, reasoning, ai_consulted = self.ai_zone_handler.decide(
                    confidence=best_confidence,
                    pattern_name=pattern_name,
                    indicators=indicators,
                    traits=traits_dict,
                    recent_trades=recent_trade_dicts,
                )

                if ai_consulted:
                    ai_decision = "TAKE" if should_trade else "SKIP"

            if not should_trade:
                return None

        # Entry approved
        return (pattern_id, best_confidence, direction, zone_result.zone.value, ai_consulted, ai_decision)

    def _check_exit(
        self,
        open_trade: OpenTrade,
        indicators: dict[str, float],
        current_price: float,
        patterns: list[dict],
        config: BacktestConfig,
    ) -> tuple[bool, str]:
        """
        Check if trade should be closed.

        Supports multiple exit strategies:
        - FIXED: Standard stop-loss/take-profit
        - TRAILING_*: Fixed percentage trailing stop
        - DYNAMIC_TRAIL: Logarithmic trail (widens with profit)
        - BREAKEVEN_TRAIL: Move to breakeven after +X%, then trail
        - ATR_TRAIL: ATR-based trailing stop
        - ACCUMULATION: No stop loss for BTC/ETH/SOL - only exit on profit or end of data

        Returns:
            Tuple of (should_exit, reason).
        """
        # GUARD: Protect against zero entry price (CRASH-003)
        if open_trade.entry_price <= 0:
            return True, "invalid_entry_price"
        # Calculate unrealized PnL
        if open_trade.direction == "long":
            pnl_pct = ((current_price - open_trade.entry_price) / open_trade.entry_price) * 100
        else:
            pnl_pct = ((open_trade.entry_price - current_price) / open_trade.entry_price) * 100

        # Check if this is an accumulation asset (BTC, ETH, SOL majors + cross pairs)
        asset_upper = open_trade.asset.upper()
        is_accumulation_asset = config.accumulation_mode and (
            asset_upper in ACCUMULATION_ASSETS
            or
            # Also check normalized form for USD pairs
            asset_upper.replace("-USD", "").replace("USDT", "").replace("USD", "") in {"BTC", "ETH", "SOL"}
        )

        # Check hard stop loss - SKIP for accumulation assets
        if not is_accumulation_asset:
            if pnl_pct <= config.stop_loss_pct:
                return True, "stop_loss"

        # Check take profit (for FIXED strategy or as cap for trailing)
        if config.exit_strategy == ExitStrategy.FIXED:
            if pnl_pct >= config.take_profit_pct:
                return True, "take_profit"

        # Handle trailing stop strategies
        if config.exit_strategy in (
            ExitStrategy.TRAILING_2PCT,
            ExitStrategy.TRAILING_3PCT,
            ExitStrategy.TRAILING_5PCT,
            ExitStrategy.DYNAMIC_TRAIL,
            ExitStrategy.BREAKEVEN_TRAIL,
        ):
            # Determine trail percentage
            if config.exit_strategy == ExitStrategy.TRAILING_2PCT:
                trail_pct = 2.0
            elif config.exit_strategy == ExitStrategy.TRAILING_3PCT:
                trail_pct = 3.0
            elif config.exit_strategy == ExitStrategy.TRAILING_5PCT:
                trail_pct = 5.0
            elif config.exit_strategy == ExitStrategy.DYNAMIC_TRAIL:
                trail_pct = calculate_dynamic_trail(pnl_pct)
            elif config.exit_strategy == ExitStrategy.BREAKEVEN_TRAIL:
                trail_pct = config.trailing_stop_pct
            else:
                trail_pct = config.trailing_stop_pct

            # Update trailing stop and check if triggered
            if open_trade.update_trailing_stop(current_price, trail_pct, config):
                return True, "trailing_stop"

        # ATR-based trailing stop
        if config.exit_strategy == ExitStrategy.ATR_TRAIL:
            atr = indicators.get("atr", indicators.get("atr_14", 0))
            # GUARD: Protect against zero current_price (CRASH-012)
            if atr > 0 and current_price > 0:
                trail_distance = atr * config.atr_multiplier
                trail_pct = (trail_distance / current_price) * 100
                if open_trade.update_trailing_stop(current_price, trail_pct, config):
                    return True, "atr_trailing_stop"

        # Check exit conditions from pattern (only if they're indicator conditions)
        for pattern in patterns:
            if pattern.get("pattern_id") == open_trade.pattern_id:
                exit_conditions = pattern.get("exit_conditions", {})
                # Skip if exit_conditions is just stop_loss/take_profit params
                # Real indicator conditions have operator/value structure
                # Support both key formats:
                # - Legacy: stop_loss_pct, take_profit_pct, max_hold_periods
                # - New: stop_loss, take_profit, timeout_bars
                param_keys = [
                    "stop_loss_pct",
                    "take_profit_pct",
                    "max_hold_periods",  # Legacy
                    "stop_loss",
                    "take_profit",
                    "timeout_bars",  # New format
                ]
                if exit_conditions and not any(k in exit_conditions for k in param_keys):
                    result = evaluate_conditions(exit_conditions, indicators, match_threshold=0.6)
                    if result.matched:
                        return True, "condition"

        return False, ""

    def _close_trade(
        self,
        open_trade: OpenTrade,
        exit_price: float,
        exit_timestamp: int,
        exit_reason: str,
        costs_pct: float,
    ) -> TradeRecord:
        """Close trade and create TradeRecord."""
        # GUARD: Division by zero protection
        if open_trade.entry_price <= 0:
            print(f"[Engine] WARNING: Invalid entry_price={open_trade.entry_price}, skipping trade")
            gross_pnl = 0.0
        # Calculate PnL
        elif open_trade.direction == "long":
            gross_pnl = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
        else:
            gross_pnl = ((open_trade.entry_price - exit_price) / open_trade.entry_price) * 100

        # Subtract costs
        net_pnl = gross_pnl - costs_pct

        return TradeRecord(
            trade_id=open_trade.trade_id,
            agent_id=open_trade.agent_id,
            pattern_id=open_trade.pattern_id,
            asset=open_trade.asset,
            direction=open_trade.direction,
            entry_price=open_trade.entry_price,
            exit_price=exit_price,
            entry_timestamp=open_trade.entry_timestamp,
            exit_timestamp=exit_timestamp,
            pnl_pct=net_pnl,
            mfe_pct=open_trade.mfe_pct,
            mae_pct=open_trade.mae_pct,
            mfe_price=open_trade.mfe_price,
            mae_price=open_trade.mae_price,
            position_size_pct=open_trade.position_size_pct,
            entry_confidence=open_trade.entry_confidence,
            decision_zone=open_trade.decision_zone,
            ai_consulted=open_trade.ai_consulted,
            ai_decision=open_trade.ai_decision,
        )


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
# Convenience Functions
# =============================================================================


def create_backtest_engine(
    patterns: dict[str, dict] | None = None,
    db_path: str | None = None,
    ai_zone_mode: AIZoneMode = AIZoneMode.HEURISTIC,
) -> LocalBacktestEngine:
    """
    Create a configured backtest engine.

    Args:
        patterns: Pattern definitions.
        db_path: Path to OHLCV database.
        ai_zone_mode: Mode for AI_REFLECT zone (SKIP, HEURISTIC, LLM).

    Returns:
        Configured LocalBacktestEngine.
    """
    loader = OHLCVLoader(db_path=db_path) if db_path else OHLCVLoader()
    return LocalBacktestEngine(
        loader=loader,
        patterns=patterns or {},
        ai_zone_mode=ai_zone_mode,
    )


def run_quick_backtest(
    agent: AgentRecord,
    patterns: dict[str, dict],
    asset: str = "BTC",
    timeframe: str = "1h",
) -> list[TradeRecord]:
    """
    Run a quick backtest for development/testing.

    Args:
        agent: Agent to backtest.
        patterns: Pattern definitions.
        asset: Asset to backtest on.
        timeframe: Candle timeframe.

    Returns:
        List of TradeRecords.
    """
    engine = create_backtest_engine(patterns=patterns)

    return engine.run(
        agent=agent,
        dataset={
            "assets": [asset],
            "timeframe": timeframe,
        },
    )
