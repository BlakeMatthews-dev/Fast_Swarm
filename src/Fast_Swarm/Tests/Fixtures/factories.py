"""
Test Factories for Fast_Swarm - MASTER TEST ADMIN

Generate test objects with sensible defaults and edge cases.
NO MAGIC NUMBERS - all values are documented and named.

Usage:
    agent = AgentFactory.create(fitness_score=75.0)
    trades = TradeFactory.create_batch(10, avg_pnl=2.0)
    edge_trades = TradeFactory.edge_cases()
"""

import random
import uuid
from datetime import datetime
from typing import Any

from Agents.Services.fitness_service import TradeData

# =============================================================================
# NAMED CONSTANTS (NO MAGIC NUMBERS)
# =============================================================================

# Trait names - the complete 22-trait genome
ALL_22_TRAITS = [
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    "win_rate_preference",
    "drawdown_sensitivity",
    "momentum_vs_reversion",
    "stop_loss_tightness",
    "entry_aggression",
    "exit_aggression",
    "lookback_preference",
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    "funding_rate_sensitivity",
    "correlation_awareness",
    "patience",
    "adaptability",
    "trend_following",
    "mean_reversion",
    "breakout_preference",
    "volume_sensitivity",
]

# Default trait value (middle of [0, 1] range)
DEFAULT_TRAIT_VALUE = 0.5

# ELO rating defaults
DEFAULT_ELO_RATING = 1500.0

# Fitness bounds
MIN_FITNESS = 0.0
MAX_FITNESS = 100.0

# Tier thresholds
TIER_DIES_THRESHOLD = 40.0
TIER_PROMOTED_THRESHOLD = 80.0

# Trade PnL bounds for realistic scenarios
REALISTIC_PNL_MIN_PCT = -20.0
REALISTIC_PNL_MAX_PCT = 50.0

# Extreme PnL for edge case testing
EXTREME_PNL_MIN_PCT = -100.0
EXTREME_PNL_MAX_PCT = 1000.0


# =============================================================================
# TRADE FACTORY
# =============================================================================


class TradeFactory:
    """Factory for creating test trades."""

    @staticmethod
    def create(
        pnl_pct: float = 2.0,
        is_win: bool | None = None,
        entry_price: float = 50000.0,
        exit_price: float | None = None,
        size: float = 0.1,
    ) -> TradeData:
        """
        Create a single trade.

        Args:
            pnl_pct: PnL percentage
            is_win: Whether trade is a winner (auto-detected if None)
            entry_price: Entry price
            exit_price: Exit price (calculated from pnl_pct if None)
            size: Position size

        Returns:
            TradeData instance
        """
        if is_win is None:
            is_win = pnl_pct > 0

        if exit_price is None:
            exit_price = entry_price * (1 + pnl_pct / 100)

        pnl = (exit_price - entry_price) * size

        return TradeData(
            pnl=pnl,
            pnl_pct=pnl_pct,
            is_win=is_win,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
        )

    @staticmethod
    def create_batch(
        count: int,
        avg_pnl: float = 1.0,
        win_rate: float = 0.6,
        seed: int | None = None,
    ) -> list[TradeData]:
        """
        Create a batch of trades with target characteristics.

        Args:
            count: Number of trades
            avg_pnl: Average PnL percentage
            win_rate: Target win rate (0-1)
            seed: Random seed for reproducibility

        Returns:
            List of TradeData
        """
        if seed is not None:
            random.seed(seed)

        trades = []
        for _ in range(count):
            is_win = random.random() < win_rate

            if is_win:
                pnl = abs(random.gauss(avg_pnl * 1.5, 2))
            else:
                pnl = -abs(random.gauss(avg_pnl * 1.0, 1.5))

            trades.append(TradeFactory.create(pnl_pct=pnl, is_win=is_win))

        return trades

    @staticmethod
    def all_winners(count: int = 10, pnl_pct: float = 5.0) -> list[TradeData]:
        """Create all winning trades (tests zero downside deviation)."""
        return [TradeFactory.create(pnl_pct=pnl_pct) for _ in range(count)]

    @staticmethod
    def all_losers(count: int = 10, pnl_pct: float = -5.0) -> list[TradeData]:
        """Create all losing trades (tests zero gross profit)."""
        return [TradeFactory.create(pnl_pct=pnl_pct) for _ in range(count)]

    @staticmethod
    def identical_pnl(count: int = 10, pnl_pct: float = 2.0) -> list[TradeData]:
        """Create trades with identical PnL (tests zero variance)."""
        return [TradeFactory.create(pnl_pct=pnl_pct) for _ in range(count)]

    @staticmethod
    def zero_pnl(count: int = 10) -> list[TradeData]:
        """Create trades with zero PnL (edge case)."""
        return [TradeFactory.create(pnl_pct=0.0, is_win=False) for _ in range(count)]

    @staticmethod
    def single_trade(pnl_pct: float = 5.0) -> list[TradeData]:
        """Create single trade (minimum viable backtest)."""
        return [TradeFactory.create(pnl_pct=pnl_pct)]

    @staticmethod
    def empty_list() -> list[TradeData]:
        """Create empty trade list (tests division by zero guards)."""
        return []

    @staticmethod
    def with_nan() -> list[TradeData]:
        """Create trades with NaN values (tests NaN filtering)."""
        return [
            TradeFactory.create(pnl_pct=5.0),
            TradeData(pnl=float("nan"), pnl_pct=float("nan"), is_win=True),
            TradeFactory.create(pnl_pct=3.0),
        ]

    @staticmethod
    def with_inf() -> list[TradeData]:
        """Create trades with Inf values (tests Inf filtering)."""
        return [
            TradeFactory.create(pnl_pct=5.0),
            TradeData(pnl=float("inf"), pnl_pct=float("inf"), is_win=True),
            TradeFactory.create(pnl_pct=3.0),
        ]

    @staticmethod
    def with_negative_inf() -> list[TradeData]:
        """Create trades with negative Inf values."""
        return [
            TradeFactory.create(pnl_pct=5.0),
            TradeData(pnl=float("-inf"), pnl_pct=float("-inf"), is_win=False),
            TradeFactory.create(pnl_pct=3.0),
        ]

    @staticmethod
    def extreme_trades() -> list[TradeData]:
        """Create extreme edge case trades."""
        return [
            TradeFactory.create(pnl_pct=EXTREME_PNL_MAX_PCT),  # 1000% gain
            TradeFactory.create(pnl_pct=EXTREME_PNL_MIN_PCT),  # 100% loss
            TradeData(pnl=float("inf"), pnl_pct=float("inf"), is_win=True),
            TradeData(pnl=float("nan"), pnl_pct=float("nan"), is_win=True),
            TradeFactory.create(pnl_pct=0.0),
        ]

    @staticmethod
    def edge_cases() -> dict[str, list[TradeData]]:
        """Return all edge case scenarios as a dictionary."""
        return {
            "empty": TradeFactory.empty_list(),
            "single_winner": TradeFactory.single_trade(5.0),
            "single_loser": TradeFactory.single_trade(-5.0),
            "all_winners": TradeFactory.all_winners(),
            "all_losers": TradeFactory.all_losers(),
            "identical_pnl": TradeFactory.identical_pnl(),
            "zero_pnl": TradeFactory.zero_pnl(),
            "with_nan": TradeFactory.with_nan(),
            "with_inf": TradeFactory.with_inf(),
            "with_neg_inf": TradeFactory.with_negative_inf(),
            "extreme": TradeFactory.extreme_trades(),
        }


# =============================================================================
# AGENT FACTORY
# =============================================================================


class AgentFactory:
    """Factory for creating test agents."""

    @staticmethod
    def create(
        agent_id: str | None = None,
        name: str = "Test Agent",
        generation: int = 1,
        traits: dict[str, float] | None = None,
        fitness_score: float = 50.0,
        status: str = "active",
        backtest_count: int = 5,
        seed: int | None = None,
        traits_override: dict[str, float] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Create agent dictionary with defaults.

        Args:
            agent_id: Unique ID (generated if None)
            name: Agent name
            generation: Agent generation
            traits: Full trait dictionary (generated if None)
            fitness_score: Fitness score
            status: Agent status
            backtest_count: Number of backtests
            seed: Random seed for trait generation
            traits_override: Override specific traits after generation

        Returns:
            Agent dictionary
        """
        if agent_id is None:
            agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"

        if traits is None:
            traits = AgentFactory._generate_traits(seed)

        if traits_override:
            traits = {**traits, **traits_override}

        return {
            "agent_id": agent_id,
            "name": name,
            "generation": generation,
            "traits": traits,
            "fitness_score": fitness_score,
            "status": status,
            "backtest_count": backtest_count,
            "is_active": status == "active",
            "elo_rating": DEFAULT_ELO_RATING,
            "created_at": datetime.utcnow(),
            **kwargs,
        }

    @staticmethod
    def _generate_traits(seed: int | None = None) -> dict[str, float]:
        """Generate 22 traits with optional seed."""
        if seed is not None:
            random.seed(seed)
            return {t: random.random() for t in ALL_22_TRAITS}
        return dict.fromkeys(ALL_22_TRAITS, DEFAULT_TRAIT_VALUE)

    @staticmethod
    def create_batch(count: int, **common_kwargs) -> list[dict[str, Any]]:
        """Create multiple agents."""
        return [
            AgentFactory.create(agent_id=f"test-agent-batch-{i}", fitness_score=20.0 + i * 10, **common_kwargs)
            for i in range(count)
        ]

    @staticmethod
    def high_performer(seed: int = 42) -> dict[str, Any]:
        """Create a high-performing agent."""
        return AgentFactory.create(
            agent_id=f"test-agent-high-{seed}",
            name="High Performer",
            fitness_score=85.0,
            backtest_count=50,
            seed=seed,
        )

    @staticmethod
    def low_performer(seed: int = 99) -> dict[str, Any]:
        """Create a low-performing agent."""
        return AgentFactory.create(
            agent_id=f"test-agent-low-{seed}",
            name="Low Performer",
            fitness_score=25.0,
            backtest_count=50,
            seed=seed,
        )

    @staticmethod
    def untested(seed: int = 0) -> dict[str, Any]:
        """Create an untested agent (low backtest count)."""
        return AgentFactory.create(
            agent_id=f"test-agent-untested-{seed}",
            name="Untested Agent",
            fitness_score=0.0,
            backtest_count=0,
            seed=seed,
        )


# =============================================================================
# PATTERN FACTORY
# =============================================================================


class PatternFactory:
    """Factory for creating test patterns."""

    @staticmethod
    def create(
        pattern_id: str | None = None,
        name: str = "Test Pattern",
        entry_conditions: dict | None = None,
        exit_conditions: dict | None = None,
        direction: str = "long",
        is_active: bool = True,
        fitness_score: float | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Create pattern dictionary."""
        if pattern_id is None:
            pattern_id = f"test-pattern-{uuid.uuid4().hex[:8]}"

        if entry_conditions is None:
            entry_conditions = {"indicator": "rsi_14", "operator": "<", "value": 30}

        if exit_conditions is None:
            exit_conditions = {"indicator": "rsi_14", "operator": ">", "value": 70}

        return {
            "pattern_id": pattern_id,
            "name": name,
            "entry_conditions": entry_conditions,
            "exit_conditions": exit_conditions,
            "direction": direction,
            "is_active": is_active,
            "fitness_score": fitness_score,
            **kwargs,
        }

    @staticmethod
    def rsi_oversold() -> dict[str, Any]:
        """Create RSI oversold pattern."""
        return PatternFactory.create(
            pattern_id="canonical-rsi-oversold",
            name="RSI Oversold",
            entry_conditions={"indicator": "rsi_14", "operator": "<", "value": 30},
            exit_conditions={"indicator": "rsi_14", "operator": ">", "value": 70},
        )

    @staticmethod
    def macd_cross() -> dict[str, Any]:
        """Create MACD bullish cross pattern."""
        return PatternFactory.create(
            pattern_id="canonical-macd-cross",
            name="MACD Bullish Cross",
            entry_conditions={"indicator": "macd_histogram", "operator": ">", "value": 0},
            exit_conditions={"indicator": "macd_histogram", "operator": "<", "value": 0},
        )

    @staticmethod
    def bb_squeeze() -> dict[str, Any]:
        """Create Bollinger Band squeeze pattern."""
        return PatternFactory.create(
            pattern_id="canonical-bb-squeeze",
            name="BB Squeeze",
            entry_conditions={"indicator": "bb_width", "operator": "<", "value": 0.05},
            exit_conditions={"indicator": "bb_width", "operator": ">", "value": 0.15},
        )
