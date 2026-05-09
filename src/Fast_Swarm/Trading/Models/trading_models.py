"""
Trading Models - Enums and data classes for the trading system.

Three trading modes:
1. PAPER_ONLY - Simulated trades only, no real execution
2. APPROVAL - Paper trades queue for user approval, execute as limit orders when approved
                Bear protection exits auto-execute without approval
3. FULL_AUTO - Auto-execute all trades as limit orders, with override capability
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TradingMode(Enum):
    """Trading execution modes."""

    PAPER_ONLY = "paper_only"  # Simulated only
    APPROVAL = "approval"  # Requires user approval (except bear protection)
    FULL_AUTO = "full_auto"  # Auto-execute with override capability


class SignalType(Enum):
    """Types of trading signals."""

    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_NORMAL = "exit_normal"
    EXIT_BEAR_PROTECTION = "exit_bear_protection"  # Auto-executes in APPROVAL mode
    EXIT_STOP_LOSS = "exit_stop_loss"
    EXIT_TAKE_PROFIT = "exit_take_profit"


class ApprovalStatus(Enum):
    """Status of trades pending approval."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_EXECUTED = "auto_executed"  # Bear protection bypassed approval


@dataclass
class PendingTrade:
    """A trade waiting for user approval."""

    trade_id: str
    agent_id: str
    agent_name: str
    symbol: str
    side: str  # "long" or "short"
    signal_type: SignalType
    suggested_price: float
    size: float
    size_usd: float
    reason: str  # Why the agent wants this trade
    pattern_id: str | None = None
    pattern_name: str | None = None
    regime: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None  # Auto-reject after this time
    status: ApprovalStatus = ApprovalStatus.PENDING
    approval_time: datetime | None = None
    limit_price: float | None = None  # Price for limit order when approved
    entry_signals: dict[str, Any] | None = None

    def is_bear_protection(self) -> bool:
        """Check if this is a bear protection exit (auto-execute)."""
        return self.signal_type == SignalType.EXIT_BEAR_PROTECTION

    def is_expired(self) -> bool:
        """Check if approval window has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class TradingConfig:
    """Configuration for an agent's trading session."""

    agent_id: str
    mode: TradingMode = TradingMode.PAPER_ONLY
    symbols: list[str] = field(default_factory=lambda: ["BTC-USDT"])
    initial_balance: float = 10000.0

    # Limit order settings
    limit_buffer_pct: float = 0.1  # 0.1% buffer from suggested price
    order_expiry_hours: int = 24  # Cancel unfilled orders after this

    # Approval settings (for APPROVAL mode)
    approval_timeout_minutes: int = 60  # Auto-reject pending trades after this
    bear_protection_auto_execute: bool = True  # Always true - bear exits bypass approval

    # Risk limits
    max_position_pct: float = 0.25  # Max 25% of balance per position
    max_daily_trades: int = 10


@dataclass
class ExecutionResult:
    """Result of executing a trade on the exchange."""

    success: bool
    order_id: str | None = None
    fill_price: float | None = None
    fill_size: float | None = None
    slippage_pct: float | None = None
    fees: float | None = None
    error: str | None = None
    exchange_response: dict | None = None
