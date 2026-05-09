"""
Backtest Models for Fast_Swarm.

Provides data structures for backtest configuration and results.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExitStrategy(Enum):
    """Available exit strategies for backtesting."""

    FIXED = "fixed"  # Fixed TP/SL only
    TRAILING_2PCT = "trailing_2pct"  # 2% trailing stop
    TRAILING_3PCT = "trailing_3pct"  # 3% trailing stop
    TRAILING_5PCT = "trailing_5pct"  # 5% trailing stop
    DYNAMIC_TRAIL = "dynamic_trail"  # Logarithmic widening (2% -> 12%)
    BREAKEVEN_TRAIL = "breakeven_trail"  # Move to breakeven after +5%
    ATR_TRAIL = "atr_trail"  # 2x ATR from highwater


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    # Trade parameters
    max_position_pct: float = 0.05  # 5% default position size
    default_stop_loss_pct: float = 0.10  # 10% stop loss
    default_take_profit_pct: float = 0.25  # 25% take profit
    max_hold_candles: int = 168  # 7 days for 1h candles

    # Exit strategy configuration
    exit_strategy: ExitStrategy = ExitStrategy.FIXED
    trailing_stop_pct: float = 3.0  # For TRAILING_* strategies
    breakeven_trigger_pct: float = 5.0  # For BREAKEVEN_TRAIL

    # ATR multiplier for ATR_TRAIL
    atr_multiplier: float = 2.0

    # Minimum confidence to enter
    min_confidence: float = 0.3

    # Data parameters
    min_candles_warmup: int = 50
    timeframe: str = "1h"

    # Cost modeling
    include_costs: bool = True

    # Legacy aliases for compatibility
    @property
    def stop_loss_pct(self) -> float:
        return -self.default_stop_loss_pct * 100

    @property
    def take_profit_pct(self) -> float:
        return self.default_take_profit_pct * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_position_pct": self.max_position_pct,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "default_take_profit_pct": self.default_take_profit_pct,
            "max_hold_candles": self.max_hold_candles,
            "exit_strategy": self.exit_strategy.value,
            "trailing_stop_pct": self.trailing_stop_pct,
            "breakeven_trigger_pct": self.breakeven_trigger_pct,
            "atr_multiplier": self.atr_multiplier,
            "min_confidence": self.min_confidence,
            "min_candles_warmup": self.min_candles_warmup,
            "timeframe": self.timeframe,
            "include_costs": self.include_costs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestConfig":
        """Create from dictionary."""
        exit_strategy = data.get("exit_strategy", "fixed")
        if isinstance(exit_strategy, str):
            exit_strategy = ExitStrategy(exit_strategy)
        return cls(
            max_position_pct=data.get("max_position_pct", 0.05),
            default_stop_loss_pct=data.get("default_stop_loss_pct", 0.10),
            default_take_profit_pct=data.get("default_take_profit_pct", 0.25),
            max_hold_candles=data.get("max_hold_candles", 168),
            exit_strategy=exit_strategy,
            trailing_stop_pct=data.get("trailing_stop_pct", 3.0),
            breakeven_trigger_pct=data.get("breakeven_trigger_pct", 5.0),
            atr_multiplier=data.get("atr_multiplier", 2.0),
            min_confidence=data.get("min_confidence", 0.3),
            min_candles_warmup=data.get("min_candles_warmup", 50),
            timeframe=data.get("timeframe", "1h"),
            include_costs=data.get("include_costs", True),
        )

    @classmethod
    def from_traits(cls, traits: dict[str, float]) -> "BacktestConfig":
        """Create config from agent traits."""
        risk_tolerance = traits.get("risk_tolerance", 0.5)
        stop_loss_tightness = traits.get("stop_loss_tightness", 0.5)
        profit_target_greed = traits.get("profit_target_greed", 0.5)
        hold_duration_bias = traits.get("hold_duration_bias", 0.5)

        # Convert traits to trading parameters
        # Higher risk_tolerance = larger positions (2% to 10%)
        position_size = 0.02 + (risk_tolerance * 0.08)

        # Higher stop_loss_tightness = tighter stops (5% to 15%)
        stop_loss = 0.15 - (stop_loss_tightness * 0.10)

        # Higher profit_target_greed = higher take profit (15% to 50%)
        take_profit = 0.15 + (profit_target_greed * 0.35)

        # Higher hold_duration_bias = longer holds (24h to 336h / 2 weeks)
        max_hold = int(24 + (hold_duration_bias * 312))

        return cls(
            max_position_pct=position_size,
            default_stop_loss_pct=stop_loss,
            default_take_profit_pct=take_profit,
            max_hold_candles=max_hold,
        )


@dataclass
class TradeRecord:
    """Record of a single trade from backtesting."""

    trade_id: str
    pattern_id: str
    asset: str
    direction: str  # "long" or "short"
    entry_price: float
    exit_price: float
    entry_timestamp: int
    exit_timestamp: int
    pnl_pct: float
    mfe_pct: float = 0.0  # Maximum Favorable Excursion
    mae_pct: float = 0.0  # Maximum Adverse Excursion
    position_size_pct: float = 5.0
    entry_confidence: float = 0.5
    exit_reason: str = "unknown"
    candles_held: int = 0
    fees_pct: float = 0.0
    slippage_pct: float = 0.0

    # Optional agent tracking
    agent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "pattern_id": self.pattern_id,
            "asset": self.asset,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "pnl_pct": self.pnl_pct,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "position_size_pct": self.position_size_pct,
            "entry_confidence": self.entry_confidence,
            "exit_reason": self.exit_reason,
            "candles_held": self.candles_held,
            "fees_pct": self.fees_pct,
            "slippage_pct": self.slippage_pct,
            "agent_id": self.agent_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeRecord":
        """Create from dictionary."""
        return cls(
            trade_id=data.get("trade_id", str(uuid.uuid4())),
            pattern_id=data.get("pattern_id", "unknown"),
            asset=data.get("asset", "BTC"),
            direction=data.get("direction", "long"),
            entry_price=data.get("entry_price", 0.0),
            exit_price=data.get("exit_price", 0.0),
            entry_timestamp=data.get("entry_timestamp", 0),
            exit_timestamp=data.get("exit_timestamp", 0),
            pnl_pct=data.get("pnl_pct", 0.0),
            mfe_pct=data.get("mfe_pct", 0.0),
            mae_pct=data.get("mae_pct", 0.0),
            position_size_pct=data.get("position_size_pct", 5.0),
            entry_confidence=data.get("entry_confidence", 0.5),
            exit_reason=data.get("exit_reason", "unknown"),
            candles_held=data.get("candles_held", 0),
            fees_pct=data.get("fees_pct", 0.0),
            slippage_pct=data.get("slippage_pct", 0.0),
            agent_id=data.get("agent_id"),
        )

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl_pct > 0

    @property
    def gross_pnl_pct(self) -> float:
        """Calculate gross PnL before costs."""
        return self.pnl_pct + self.fees_pct + self.slippage_pct

    @property
    def hold_duration_hours(self) -> float:
        """Calculate hold duration in hours."""
        return (self.exit_timestamp - self.entry_timestamp) / 3600


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    backtest_id: str
    pattern_id: str
    config: BacktestConfig
    trades: list[TradeRecord]
    start_timestamp: int
    end_timestamp: int

    # Computed metrics (set after initialization)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_roi_pct: float = 0.0
    avg_trade_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_winner_pct: float = 0.0
    avg_loser_pct: float = 0.0
    avg_hold_candles: float = 0.0
    total_fees_pct: float = 0.0
    total_slippage_pct: float = 0.0

    # Metadata
    asset: str = "BTC"
    timeframe: str = "1h"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Compute metrics after initialization."""
        if self.trades and self.total_trades == 0:
            self._compute_metrics()

    def _compute_metrics(self):
        """Compute all metrics from trades."""
        if not self.trades:
            return

        self.total_trades = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        self.winning_trades = len(winners)
        self.losing_trades = len(losers)
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0

        # ROI and averages
        pnls = [t.pnl_pct for t in self.trades]
        self.total_roi_pct = sum(pnls)
        self.avg_trade_pnl_pct = self.total_roi_pct / self.total_trades if self.total_trades > 0 else 0

        if winners:
            self.avg_winner_pct = sum(t.pnl_pct for t in winners) / len(winners)
        if losers:
            self.avg_loser_pct = sum(t.pnl_pct for t in losers) / len(losers)

        # Hold duration
        hold_times = [t.candles_held for t in self.trades]
        self.avg_hold_candles = sum(hold_times) / len(hold_times) if hold_times else 0

        # Costs
        self.total_fees_pct = sum(t.fees_pct for t in self.trades)
        self.total_slippage_pct = sum(t.slippage_pct for t in self.trades)

        # Profit factor
        gross_profit = sum(t.pnl_pct for t in winners) if winners else 0
        gross_loss = abs(sum(t.pnl_pct for t in losers)) if losers else 0
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0)

        # Max drawdown (simple calculation)
        self._compute_drawdown()

        # Sharpe ratio (simplified)
        self._compute_sharpe()

    def _compute_drawdown(self):
        """Compute maximum drawdown."""
        if not self.trades:
            self.max_drawdown_pct = 0.0
            return

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in self.trades:
            cumulative += trade.pnl_pct
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        self.max_drawdown_pct = max_dd

    def _compute_sharpe(self):
        """Compute Sharpe ratio (simplified, assumes risk-free rate = 0)."""
        if len(self.trades) < 2:
            self.sharpe_ratio = 0.0
            return

        pnls = [t.pnl_pct for t in self.trades]
        mean_return = sum(pnls) / len(pnls)

        # Standard deviation
        variance = sum((p - mean_return) ** 2 for p in pnls) / len(pnls)
        std_dev = variance**0.5 if variance > 0 else 0

        # Sharpe = mean / std (annualized factor would apply in production)
        sharpe = mean_return / std_dev if std_dev > 0 else 0
        # Cap at ±6 to filter calculation anomalies while allowing exceptional strategies
        self.sharpe_ratio = max(-6.0, min(6.0, sharpe))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "backtest_id": self.backtest_id,
            "pattern_id": self.pattern_id,
            "config": self.config.to_dict(),
            "trades": [t.to_dict() for t in self.trades],
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_roi_pct": self.total_roi_pct,
            "avg_trade_pnl_pct": self.avg_trade_pnl_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "profit_factor": self.profit_factor,
            "avg_winner_pct": self.avg_winner_pct,
            "avg_loser_pct": self.avg_loser_pct,
            "avg_hold_candles": self.avg_hold_candles,
            "total_fees_pct": self.total_fees_pct,
            "total_slippage_pct": self.total_slippage_pct,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "created_at": self.created_at.isoformat(),
        }


# Type aliases for compatibility
OpenTrade = dict[str, Any]  # Trade state during backtest
Candle = dict[str, Any]  # OHLCV candle data
