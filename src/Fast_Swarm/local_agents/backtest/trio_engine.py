"""
Trio Rotation Backtest Engine.

Sequential priority-based entry/exit flow for BTC/ETH/SOL trio.

ENTRY (from USD):
1. BTC-USD entry? → Buy BTC
2. ETH-USD entry? → Buy ETH
3. SOL-USD entry? → Buy SOL

ROTATION (from BTC):
1. ETH/BTC entry? → Rotate BTC→ETH
2. SOL/BTC entry? → Rotate BTC→SOL
3. BTC-USD exit? → Exit to USD

ROTATION (from ETH):
1. BTC/ETH entry? → Rotate ETH→BTC (when ETH expensive)
2. SOL/ETH entry? → Rotate ETH→SOL
3. ETH-USD exit? → Exit to USD

ROTATION (from SOL):
1. BTC/SOL entry? → Rotate SOL→BTC
2. ETH/SOL entry? → Rotate SOL→ETH
3. SOL-USD exit? → Exit to USD

Goal: Accumulate more BTC over time through smart rotations.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum

from Fast_Swarm.local_agents.backtest.cross_pairs import TrioDataBundle


class Holding(Enum):
    """What asset the agent currently holds."""

    USD = "USD"
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"


@dataclass
class TrioPosition:
    """Current position state in the trio."""

    holding: Holding = Holding.USD
    amount: float = 10000.0  # Start with $10K USD equivalent
    entry_price: float = 0.0  # Price when entered current holding
    entry_timestamp: int = 0

    # Track accumulation in BTC terms
    btc_equivalent: float = 0.0  # How much BTC this is worth

    # For performance tracking
    trades: list[dict] = field(default_factory=list)

    # Trailing stop tracking (highwater mark for profit-only trailing)
    highwater_price: float = 0.0  # Highest price seen since entry


@dataclass
class TrioTradeRecord:
    """Record of a trio rotation or entry/exit trade."""

    trade_id: str
    timestamp: int
    action: str  # 'buy', 'sell', 'rotate'
    from_asset: str
    to_asset: str
    from_amount: float
    to_amount: float
    price: float  # Exchange rate used
    pair_used: str  # e.g., 'ETH/BTC' or 'BTC-USD'
    data_source: str  # 'exchange' or 'synthetic'

    # BTC-denominated P&L
    btc_before: float
    btc_after: float
    btc_pnl: float


class TrioBacktestEngine:
    """
    Backtest engine for trio rotation strategy.

    Shows patterns different pairs in priority order:
    - When holding USD: USD pairs for entry
    - When holding asset: Cross pairs for rotation, USD pair for exit
    """

    # Priority order for each holding state
    ENTRY_PRIORITY = {
        Holding.USD: [
            ("BTC-USD", "entry"),  # Buy BTC?
            ("ETH-USD", "entry"),  # Buy ETH?
            ("SOL-USD", "entry"),  # Buy SOL?
        ],
    }

    ROTATION_PRIORITY = {
        Holding.BTC: [
            ("ETH/BTC", "entry"),  # Rotate to ETH? (ETH cheap vs BTC)
            ("SOL/BTC", "entry"),  # Rotate to SOL?
            ("BTC-USD", "exit"),  # Exit to USD?
        ],
        Holding.ETH: [
            ("ETH/BTC", "exit"),  # Rotate to BTC? (ETH expensive vs BTC)
            ("SOL/ETH", "entry"),  # Rotate to SOL?
            ("ETH-USD", "exit"),  # Exit to USD?
        ],
        Holding.SOL: [
            ("SOL/BTC", "exit"),  # Rotate to BTC? (SOL expensive vs BTC)
            ("SOL/ETH", "exit"),  # Rotate to ETH? (SOL expensive vs ETH)
            ("SOL-USD", "exit"),  # Exit to USD?
        ],
    }

    def __init__(
        self,
        pattern_matcher,  # Existing PatternMatcher
        patterns: dict[str, dict],
        slippage_pct: float = 0.1,  # 0.1% slippage per trade
        fee_pct: float = 0.1,  # 0.1% fee per trade
        use_bear_protection: bool = True,
    ):
        self.pattern_matcher = pattern_matcher
        self.patterns = patterns
        self.slippage_pct = slippage_pct
        self.fee_pct = fee_pct

        # Bear protection service (optional)
        self.bear_protection_service = None
        if use_bear_protection:
            try:
                from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
                    BearProtectionService,
                )
                self.bear_protection_service = BearProtectionService()
            except ImportError:
                pass  # Bear protection not available

    def run(
        self,
        agent,  # AgentRecord
        bundles: list[TrioDataBundle],  # Time-series of all 6 pairs
        initial_usd: float = 10000.0,
    ) -> tuple[list[TrioTradeRecord], TrioPosition]:
        """
        Run trio rotation backtest.

        Args:
            agent: Agent with patterns and traits
            bundles: List of TrioDataBundle, one per candle timestamp
            initial_usd: Starting USD amount

        Returns:
            Tuple of (trade_records, final_position)
        """
        position = TrioPosition(
            holding=Holding.USD,
            amount=initial_usd,
        )
        trades = []

        for bundle in bundles:
            trade = self._process_candle(agent, bundle, position)
            if trade:
                trades.append(trade)

        return trades, position

    def _process_candle(
        self,
        agent,
        bundle: TrioDataBundle,
        position: TrioPosition,
    ) -> TrioTradeRecord | None:
        """Process a single candle across the trio."""

        if position.holding == Holding.USD:
            # Looking to enter - check USD pairs
            priority_list = self.ENTRY_PRIORITY[Holding.USD]
        else:
            # Looking to rotate or exit
            priority_list = self.ROTATION_PRIORITY[position.holding]

        # Check each pair in priority order
        for pair, signal_type in priority_list:
            candle = bundle.get_pair(pair)
            if candle is None:
                continue

            # Build indicators for this pair's candle
            indicators = self._build_indicators(candle, bundle)

            # Check if pattern triggers
            if signal_type == "entry":
                triggered, confidence, pattern_id = self._check_entry(agent, indicators)
            else:
                triggered, confidence, pattern_id = self._check_exit(
                    agent, indicators, position, bundle.timestamp
                )

            if triggered:
                # Execute the trade
                trade = self._execute_trade(
                    position=position,
                    bundle=bundle,
                    pair=pair,
                    signal_type=signal_type,
                    confidence=confidence,
                    pattern_id=pattern_id,
                )
                return trade

        return None

    def _build_indicators(self, candle: dict, bundle: TrioDataBundle) -> dict:
        """
        Build indicator dict for pattern matching.

        Includes both the specific pair's indicators AND cross-pair context.
        """
        indicators = {}

        # Basic OHLCV
        indicators["open"] = candle.get("open", 0)
        indicators["high"] = candle.get("high", 0)
        indicators["low"] = candle.get("low", 0)
        indicators["close"] = candle.get("close", 0)
        indicators["volume"] = candle.get("volume", 0)

        # If candle has pre-computed indicators, include them
        for key in [
            "rsi_14",
            "macd_line",
            "macd_signal",
            "bb_upper",
            "bb_lower",
            "atr_14",
            "adx_14",
            "stoch_k",
            "stoch_d",
            "obv",
        ]:
            if key in candle:
                indicators[key] = candle[key]

        # Add cross-pair relative strength context
        rs = bundle.get_relative_strength()
        indicators["eth_vs_btc_change"] = rs.get("ETH_vs_BTC", 0)
        indicators["sol_vs_btc_change"] = rs.get("SOL_vs_BTC", 0)
        indicators["sol_vs_eth_change"] = rs.get("SOL_vs_ETH", 0)

        return indicators

    def _check_entry(self, agent, indicators: dict) -> tuple[bool, float, str | None]:
        """Check if any pattern triggers an entry signal."""
        best_confidence = 0.0
        best_pattern = None

        for pattern_id in agent.pattern_ids:
            pattern = self.patterns.get(pattern_id)
            if not pattern:
                continue

            entry_conditions = pattern.get("entry_conditions", [])
            if not entry_conditions:
                continue

            # Evaluate conditions (reuse existing pattern matcher logic)
            matched, confidence = self._evaluate_conditions(entry_conditions, indicators)

            if matched and confidence > best_confidence:
                best_confidence = confidence
                best_pattern = pattern_id

        # Apply agent's min threshold
        min_threshold = agent.traits.get("min_threshold", 0.3)
        if best_confidence >= min_threshold:
            return True, best_confidence, best_pattern

        return False, 0.0, None

    def _check_exit(
        self,
        agent,
        indicators: dict,
        position: TrioPosition,
        timestamp: int = 0,
    ) -> tuple[bool, float, str | None]:
        """
        Comprehensive exit check - collects ALL triggered exits, returns MOST PROFITABLE.

        Exit Types (all evaluated):
        - Bear Protection VETO (force all exits in crisis)
        - Stop Loss (capital preservation)
        - Take Profit (lock gains)
        - Trailing Stop (protect unrealized gains, profit-only mode)
        - Pattern-based indicator exits

        Priority: When multiple exits trigger simultaneously, choose the one
        that results in the best outcome (most profitable exit wins).
        Bear Protection VETO always wins (uses infinity value).
        """
        # Skip if holding USD (no position to exit)
        if position.holding == Holding.USD:
            return False, 0.0, None

        current_price = indicators.get("close", 0)
        entry_price = position.entry_price

        if entry_price <= 0 or current_price <= 0:
            return False, 0.0, None

        # Calculate P&L percentage
        pnl_pct = (current_price - entry_price) / entry_price

        # Collect all triggered exits with their "value" (higher = better exit)
        # Format: (value, confidence, reason)
        triggered_exits: list[tuple[float, float, str]] = []

        # =========================================================
        # 1. BEAR PROTECTION VETO (Supreme Risk Layer - FORCE ALL)
        # =========================================================
        if self.bear_protection_service:
            try:
                regime_state = self.bear_protection_service.evaluate_regime(
                    velocity=indicators.get("price_velocity", 0),
                    acceleration=indicators.get("price_acceleration", 0),
                    adx_jerk=indicators.get("adx_jerk", 0),
                )
                if regime_state and regime_state.exit_signal_active:
                    # VETO = force exit regardless of P&L (capital preservation supreme)
                    triggered_exits.append((float("inf"), 1.0, "bear_protection_veto"))
            except Exception:
                pass  # Bear protection evaluation failed, continue without it

        # =========================================================
        # 2. STOP LOSS (Capital Preservation)
        # =========================================================
        for pattern_id in agent.pattern_ids:
            pattern = self.patterns.get(pattern_id)
            if not pattern:
                continue
            exit_conditions = pattern.get("exit_conditions", {})
            sl_pct = exit_conditions.get("stop_loss_pct", 0.05)  # Default 5%
            if pnl_pct <= -sl_pct:
                # Value = how much loss we're limiting (less negative = better)
                triggered_exits.append((pnl_pct, 1.0, "stop_loss"))
                break  # Only need one SL trigger

        # =========================================================
        # 3. TAKE PROFIT (Lock Gains)
        # =========================================================
        for pattern_id in agent.pattern_ids:
            pattern = self.patterns.get(pattern_id)
            if not pattern:
                continue
            exit_conditions = pattern.get("exit_conditions", {})
            tp_pct = exit_conditions.get("take_profit_pct", 0.15)  # Default 15%
            if pnl_pct >= tp_pct:
                # Value = profit captured (higher = better)
                triggered_exits.append((pnl_pct, 1.0, "take_profit"))
                break  # Only need one TP trigger

        # =========================================================
        # 4. TRAILING STOP (Volatility-Adjusted via ATR)
        # =========================================================
        highwater = position.highwater_price
        if highwater <= 0:
            highwater = entry_price

        # Update highwater mark
        if current_price > highwater:
            position.highwater_price = current_price
            highwater = current_price

        # Calculate profit from entry to highwater
        if highwater > entry_price:
            profit_pct_from_entry = ((highwater - entry_price) / entry_price) * 100  # as %

            # Only activate trailing stop after minimum profit (profit-only mode)
            min_profit_to_trail = 2.0  # 2% profit before trailing kicks in
            if profit_pct_from_entry >= min_profit_to_trail:
                # Use volatility-adjusted trailing via ATR
                atr_value = indicators.get("atr_14", 0)
                if atr_value > 0:
                    # ATR-based trailing: stop at highwater - (ATR * multiplier)
                    # Higher ATR = wider stop to avoid noise-triggered exits
                    atr_multiplier = 2.0  # Standard ATR trailing multiplier
                    stop_price = highwater - (atr_value * atr_multiplier)
                    if current_price <= stop_price:
                        # Value = current P&L (we're locking in this profit)
                        triggered_exits.append((pnl_pct, 1.0, "atr_trailing_stop"))
                else:
                    # Fallback to fixed 3% trailing if no ATR available
                    trailing_pct = agent.traits.get("trailing_stop_pct", 0.03)
                    drawdown_from_peak = (highwater - current_price) / highwater
                    if drawdown_from_peak >= trailing_pct:
                        triggered_exits.append((pnl_pct, 1.0, "trailing_stop"))

        # =========================================================
        # 5. PATTERN-BASED INDICATOR EXITS
        # =========================================================
        best_pattern_confidence = 0.0
        for pattern_id in agent.pattern_ids:
            pattern = self.patterns.get(pattern_id)
            if not pattern:
                continue
            exit_indicator_conditions = pattern.get("exit_conditions", {}).get("conditions", [])
            if exit_indicator_conditions:
                matched, confidence = self._evaluate_conditions(exit_indicator_conditions, indicators)
                if matched and confidence > best_pattern_confidence:
                    best_pattern_confidence = confidence

        if best_pattern_confidence >= agent.traits.get("exit_threshold", 0.5):
            triggered_exits.append((pnl_pct, best_pattern_confidence, "pattern_exit"))

        # =========================================================
        # SELECT BEST EXIT (Most Profitable Wins)
        # =========================================================
        if not triggered_exits:
            return False, 0.0, None

        # Sort by value (highest first) - bear protection VETO always wins (inf value)
        triggered_exits.sort(key=lambda x: x[0], reverse=True)
        best_value, best_confidence, best_reason = triggered_exits[0]

        return True, best_confidence, best_reason

    def _evaluate_conditions(
        self,
        conditions: list,
        indicators: dict,
    ) -> tuple[bool, float]:
        """
        Evaluate pattern conditions against indicators.

        Simplified version - real implementation in pattern_matcher.py
        """
        if not conditions:
            return False, 0.0

        matched_count = 0
        total_confidence = 0.0

        for cond in conditions:
            indicator = cond.get("indicator", "")
            operator = cond.get("operator", "")
            value = cond.get("value")

            actual = indicators.get(indicator)
            if actual is None or value is None:
                continue  # Skip conditions with missing data

            matched = False
            if (
                (operator == "<" and actual < value)
                or (operator == ">" and actual > value)
                or (operator == "<=" and actual <= value)
                or (operator == ">=" and actual >= value)
                or (operator == "==" and actual == value)
            ):
                matched = True
            elif operator == "between" and isinstance(value, list) and len(value) == 2:
                matched = value[0] <= actual <= value[1]

            if matched:
                matched_count += 1
                total_confidence += 1.0

        if matched_count == len(conditions):
            return True, total_confidence / len(conditions)

        return False, 0.0

    def _execute_trade(
        self,
        position: TrioPosition,
        bundle: TrioDataBundle,
        pair: str,
        signal_type: str,
        confidence: float,
        pattern_id: str | None,
    ) -> TrioTradeRecord:
        """Execute a trade and update position."""

        candle = bundle.get_pair(pair)
        price = candle["close"]
        data_source = candle.get("source", "unknown")

        # Determine from/to assets based on pair and signal
        from_asset = position.holding.value
        to_asset = self._determine_to_asset(pair, signal_type, position.holding)

        # Calculate amounts with slippage and fees
        from_amount = position.amount
        effective_price = price * (1 + self.slippage_pct / 100)
        if signal_type == "exit":
            effective_price = price * (1 - self.slippage_pct / 100)

        # Apply fee
        to_amount = from_amount / effective_price * (1 - self.fee_pct / 100)

        # For cross-pair, amount calculation is different
        if "/" in pair:
            # Cross pair: e.g., ETH/BTC means price is in BTC terms
            if signal_type == "entry":
                to_amount = from_amount / effective_price * (1 - self.fee_pct / 100)
            else:
                to_amount = from_amount * effective_price * (1 - self.fee_pct / 100)
        else:
            # USD pair
            if signal_type == "entry":
                to_amount = from_amount / effective_price * (1 - self.fee_pct / 100)
            else:
                to_amount = from_amount * effective_price * (1 - self.fee_pct / 100)

        # Calculate BTC equivalent before and after
        btc_price = bundle.btc_usd["close"]
        btc_before = self._to_btc(position.holding.value, position.amount, bundle)

        # Update position
        position.holding = Holding[to_asset]
        position.amount = to_amount
        position.entry_price = price
        position.entry_timestamp = bundle.timestamp

        btc_after = self._to_btc(to_asset, to_amount, bundle)

        return TrioTradeRecord(
            trade_id=str(uuid.uuid4())[:8],
            timestamp=bundle.timestamp,
            action="rotate" if "/" in pair else ("buy" if signal_type == "entry" else "sell"),
            from_asset=from_asset,
            to_asset=to_asset,
            from_amount=from_amount,
            to_amount=to_amount,
            price=price,
            pair_used=pair,
            data_source=data_source,
            btc_before=btc_before,
            btc_after=btc_after,
            btc_pnl=btc_after - btc_before,
        )

    def _determine_to_asset(self, pair: str, signal_type: str, holding: Holding) -> str:
        """Determine what asset we're moving to."""

        if pair == "BTC-USD":
            return "BTC" if signal_type == "entry" else "USD"
        elif pair == "ETH-USD":
            return "ETH" if signal_type == "entry" else "USD"
        elif pair == "SOL-USD":
            return "SOL" if signal_type == "entry" else "USD"
        elif pair == "ETH/BTC":
            return "ETH" if signal_type == "entry" else "BTC"
        elif pair == "SOL/BTC":
            return "SOL" if signal_type == "entry" else "BTC"
        elif pair == "SOL/ETH":
            return "SOL" if signal_type == "entry" else "ETH"

        return "USD"

    def _to_btc(self, asset: str, amount: float, bundle: TrioDataBundle) -> float:
        """Convert any asset amount to BTC equivalent."""

        if asset == "BTC":
            return amount
        elif asset == "ETH":
            eth_btc = bundle.eth_btc["close"]
            return amount * eth_btc
        elif asset == "SOL":
            sol_btc = bundle.sol_btc["close"]
            return amount * sol_btc
        elif asset == "USD":
            btc_usd = bundle.btc_usd["close"]
            return amount / btc_usd

        return 0.0


def calculate_trio_metrics(trades: list[TrioTradeRecord]) -> dict:
    """Calculate performance metrics for trio rotation strategy."""

    if not trades:
        return {"total_trades": 0}

    # BTC accumulation metrics
    btc_pnls = [t.btc_pnl for t in trades]
    total_btc_pnl = sum(btc_pnls)

    winning_trades = [t for t in trades if t.btc_pnl > 0]
    losing_trades = [t for t in trades if t.btc_pnl < 0]

    win_rate = len(winning_trades) / len(trades) if trades else 0

    # Rotation vs USD trade breakdown
    rotations = [t for t in trades if t.action == "rotate"]
    usd_trades = [t for t in trades if t.action in ("buy", "sell")]

    return {
        "total_trades": len(trades),
        "rotations": len(rotations),
        "usd_trades": len(usd_trades),
        "win_rate": win_rate,
        "total_btc_pnl": total_btc_pnl,
        "avg_btc_pnl": total_btc_pnl / len(trades) if trades else 0,
        "best_trade_btc": max(btc_pnls) if btc_pnls else 0,
        "worst_trade_btc": min(btc_pnls) if btc_pnls else 0,
    }
