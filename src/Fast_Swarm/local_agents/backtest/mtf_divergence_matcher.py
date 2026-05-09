"""
Multi-Timeframe Divergence Pattern Matcher.

Detects velocity/acceleration divergence signals across 1-3 timeframes
and applies tiered Kelly position sizing based on confirmation count.

Key Discovery (from backtest_triple_timeframe.py):
- Divergence signal: velocity < -1.5 z-score AND acceleration > 3.0 z-score
- This indicates "price falling but deceleration" = potential local bottom
- More timeframe confirmations = higher conviction = larger position

Optimal Kelly Multipliers (from +134% return backtest):
- 1 TF confirms: 0.50x Kelly (cautious)
- 2 TF confirm:  2.50x Kelly (leveraged)
- 3 TF confirm:  5.00x Kelly (maximum conviction)

Author: Coinswarm Research
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import polars as pl


DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


@dataclass
class DivergenceConfig:
    """Configuration for divergence signal detection."""

    # Signal thresholds (z-scores)
    entry_velocity_threshold: float = -1.5   # Velocity must be BELOW this (falling)
    entry_accel_threshold: float = 3.0       # Acceleration must be ABOVE this (slowing)
    exit_velocity_threshold: float = 1.5     # Opposite for exit
    exit_accel_threshold: float = -3.0       # Opposite for exit

    # Tiered Kelly multipliers based on confirmation count
    kelly_1tf: float = 0.50    # Single timeframe - cautious
    kelly_2tf: float = 2.50    # Two timeframes - leveraged
    kelly_3tf: float = 5.00    # All three - maximum conviction

    # Risk management
    base_kelly: float = 0.10   # Base Kelly fraction before multiplier
    max_position_pct: float = 2.50  # Maximum position (250% with 3TF)
    min_position_pct: float = 0.05  # Minimum position

    # Stop loss
    stop_loss_pct: float = 0.25  # 25% stop loss

    # Timeframe hierarchy (highest to lowest)
    timeframes: list = field(default_factory=lambda: ["1d", "4h", "1h"])


@dataclass
class DivergenceSignal:
    """Represents a divergence signal detection."""

    time: datetime
    price: float
    confirmations: int          # How many timeframes confirm (1, 2, or 3)
    confirming_timeframes: list  # Which timeframes confirmed
    kelly_multiplier: float     # Position size multiplier
    velocity_values: dict       # velocity z-score per timeframe
    accel_values: dict          # acceleration z-score per timeframe
    confidence: float           # 0-1 confidence score

    @property
    def is_strong(self) -> bool:
        """Signal is strong if 2+ timeframes confirm."""
        return self.confirmations >= 2


class MTFDivergenceMatcher:
    """
    Multi-Timeframe Divergence Pattern Matcher.

    Detects divergence signals across multiple timeframes and
    calculates position sizing based on confirmation count.
    """

    def __init__(self, config: Optional[DivergenceConfig] = None):
        """Initialize with optional config override."""
        self.config = config or DivergenceConfig()
        self._data_cache: dict[str, pl.DataFrame] = {}

    def load_timeframe_data(self, symbol: str, timeframe: str) -> Optional[pl.DataFrame]:
        """Load derivative data for a symbol/timeframe."""
        cache_key = f"{symbol}_{timeframe}"

        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        path = DERIVATIVES_DIR / f"symbol={symbol}" / f"timeframe={timeframe}"
        if not path.exists():
            return None

        df = pl.read_parquet(path).sort("time")
        self._data_cache[cache_key] = df
        return df

    def detect_divergence(
        self,
        velocity_zscore: float,
        accel_zscore: float,
        is_entry: bool = True,
    ) -> bool:
        """
        Check if a single timeframe shows divergence signal.

        Entry signal: velocity falling (< -1.5) + acceleration rising (> 3.0)
        Exit signal:  velocity rising (> 1.5) + acceleration falling (< -3.0)
        """
        if velocity_zscore is None or accel_zscore is None:
            return False
        if np.isnan(velocity_zscore) or np.isnan(accel_zscore):
            return False

        if is_entry:
            return (
                velocity_zscore < self.config.entry_velocity_threshold and
                accel_zscore > self.config.entry_accel_threshold
            )
        else:
            return (
                velocity_zscore > self.config.exit_velocity_threshold and
                accel_zscore < self.config.exit_accel_threshold
            )

    def count_confirmations(
        self,
        row: dict,
        tf_data: dict[str, dict],
        current_time: datetime,
        is_entry: bool = True,
    ) -> tuple[int, list, dict, dict]:
        """
        Count how many timeframes show the divergence signal.

        Returns:
            (confirmation_count, confirming_tfs, velocity_values, accel_values)
        """
        count = 0
        confirming_tfs = []
        velocity_values = {}
        accel_values = {}

        for tf in self.config.timeframes:
            vel_col = "close_velocity_zscore"
            acc_col = "close_acceleration_zscore"

            # Get values for this timeframe
            if tf == self.config.timeframes[-1]:
                # Primary (lowest) timeframe - use row directly
                vel = row.get(vel_col)
                acc = row.get(acc_col)
            else:
                # Higher timeframe - use tf_data lookup
                tf_row = tf_data.get(tf, {})
                vel = tf_row.get(vel_col)
                acc = tf_row.get(acc_col)

            velocity_values[tf] = vel
            accel_values[tf] = acc

            if self.detect_divergence(vel, acc, is_entry):
                count += 1
                confirming_tfs.append(tf)

        return count, confirming_tfs, velocity_values, accel_values

    def get_kelly_multiplier(self, confirmations: int) -> float:
        """Get Kelly multiplier based on confirmation count."""
        if confirmations >= 3:
            return self.config.kelly_3tf
        elif confirmations == 2:
            return self.config.kelly_2tf
        else:
            return self.config.kelly_1tf

    def calculate_position_size(
        self,
        capital: float,
        confirmations: int,
        win_rate: float = 0.58,  # Historical from backtest
        avg_win: float = 0.076,  # 7.6% avg win
        avg_loss: float = 0.044,  # 4.4% avg loss
    ) -> float:
        """
        Calculate position size using Kelly Criterion with tiered multipliers.

        Kelly % = win_prob - (1 - win_prob) / (avg_win / avg_loss)
        Then multiply by confirmation-based multiplier.
        """
        # Base Kelly calculation
        if avg_loss == 0:
            base_kelly = self.config.base_kelly
        else:
            win_loss_ratio = avg_win / avg_loss
            base_kelly = win_rate - (1 - win_rate) / win_loss_ratio

        # Clamp base Kelly to reasonable range
        base_kelly = max(0.05, min(0.30, base_kelly))

        # Apply confirmation multiplier
        multiplier = self.get_kelly_multiplier(confirmations)
        kelly = base_kelly * multiplier

        # Clamp final position
        kelly = max(self.config.min_position_pct, min(self.config.max_position_pct, kelly))

        return capital * kelly

    def check_entry(
        self,
        symbol: str,
        current_time: datetime,
        min_confirmations: int = 1,
    ) -> Optional[DivergenceSignal]:
        """
        Check for entry signal at a specific time.

        Args:
            symbol: Asset symbol (e.g., "BTC")
            current_time: Time to check
            min_confirmations: Minimum confirmations required (1, 2, or 3)

        Returns:
            DivergenceSignal if conditions met, None otherwise
        """
        # Load data for all timeframes
        tf_data = {}
        primary_tf = self.config.timeframes[-1]

        for tf in self.config.timeframes:
            df = self.load_timeframe_data(symbol, tf)
            if df is None:
                continue

            # Find the row at or before current_time
            filtered = df.filter(pl.col("time") <= current_time)
            if filtered.is_empty():
                continue

            row = filtered.tail(1).to_dicts()[0]
            tf_data[tf] = row

        if primary_tf not in tf_data:
            return None

        # Count confirmations
        primary_row = tf_data[primary_tf]
        count, confirming_tfs, vel_values, acc_values = self.count_confirmations(
            primary_row, tf_data, current_time, is_entry=True
        )

        if count < min_confirmations:
            return None

        # Calculate confidence based on z-score magnitude
        vel_avg = np.nanmean([v for v in vel_values.values() if v is not None])
        acc_avg = np.nanmean([v for v in acc_values.values() if v is not None])

        # Confidence: how far past thresholds are we?
        vel_excess = abs(vel_avg - self.config.entry_velocity_threshold) if vel_avg else 0
        acc_excess = abs(acc_avg - self.config.entry_accel_threshold) if acc_avg else 0
        confidence = min(1.0, (vel_excess + acc_excess) / 4)  # Normalize to 0-1

        return DivergenceSignal(
            time=primary_row.get("time", current_time),
            price=primary_row.get("close", 0),
            confirmations=count,
            confirming_timeframes=confirming_tfs,
            kelly_multiplier=self.get_kelly_multiplier(count),
            velocity_values=vel_values,
            accel_values=acc_values,
            confidence=confidence,
        )

    def check_exit(
        self,
        symbol: str,
        current_time: datetime,
        entry_price: float,
        current_price: float,
    ) -> tuple[bool, str, float]:
        """
        Check for exit signal.

        Returns:
            (should_exit, reason, confidence)
        """
        # Check stop loss first
        drawdown = (current_price / entry_price) - 1
        if drawdown <= -self.config.stop_loss_pct:
            return True, "STOP_LOSS", 1.0

        # Check divergence exit signal on primary timeframe
        primary_tf = self.config.timeframes[-1]
        df = self.load_timeframe_data(symbol, primary_tf)

        if df is not None:
            filtered = df.filter(pl.col("time") <= current_time)
            if not filtered.is_empty():
                row = filtered.tail(1).to_dicts()[0]
                vel = row.get("close_velocity_zscore")
                acc = row.get("close_acceleration_zscore")

                if self.detect_divergence(vel, acc, is_entry=False):
                    return True, "EXIT_SIGNAL", 0.8

        return False, "", 0.0


def create_divergence_pattern() -> dict:
    """
    Create a pattern definition compatible with the existing pattern system.

    This can be stored in the database and used by the backtest engine.
    """
    return {
        "pattern_id": "mtf_divergence_v1",
        "name": "Multi-Timeframe Velocity/Acceleration Divergence",
        "description": (
            "Detects local bottoms via velocity/acceleration divergence. "
            "Entry when velocity < -1.5 z-score AND acceleration > 3.0 z-score. "
            "Position size scales with timeframe confirmations."
        ),
        "direction": "long",
        "entry_conditions": [
            {
                "indicator": "close_velocity_zscore",
                "operator": "<",
                "value": -1.5,
                "description": "Velocity falling (price declining)",
            },
            {
                "indicator": "close_acceleration_zscore",
                "operator": ">",
                "value": 3.0,
                "description": "Acceleration rising (deceleration = slowing down)",
            },
        ],
        "exit_conditions": [
            {
                "indicator": "close_velocity_zscore",
                "operator": ">",
                "value": 1.5,
                "description": "Velocity rising (price gaining momentum)",
            },
            {
                "indicator": "close_acceleration_zscore",
                "operator": "<",
                "value": -3.0,
                "description": "Acceleration falling (momentum slowing)",
            },
        ],
        "params": {
            "stop_loss_pct": 0.25,
            "kelly_1tf": 0.50,
            "kelly_2tf": 2.50,
            "kelly_3tf": 5.00,
            "timeframes": ["1d", "4h", "1h"],
        },
        "origin": "motion_derivatives_analysis",
        "tier": 1,  # Highest tier - proven profitable
        "backtest_results": {
            "return_pct": 134.0,
            "trades": 186,
            "win_rate_pct": 57.5,
            "expectancy_pct": 2.51,
            "profit_factor": 2.26,
            "discovery_date": "2026-01-18",
        },
    }


# Convenience function for quick access
def get_matcher(config: Optional[DivergenceConfig] = None) -> MTFDivergenceMatcher:
    """Get a configured MTF Divergence Matcher instance."""
    return MTFDivergenceMatcher(config)


if __name__ == "__main__":
    # Quick test
    print("Multi-Timeframe Divergence Pattern Matcher")
    print("=" * 50)

    config = DivergenceConfig()
    print(f"Entry thresholds: vel < {config.entry_velocity_threshold}, acc > {config.entry_accel_threshold}")
    print(f"Kelly multipliers: 1TF={config.kelly_1tf}x, 2TF={config.kelly_2tf}x, 3TF={config.kelly_3tf}x")

    pattern = create_divergence_pattern()
    print(f"\nPattern ID: {pattern['pattern_id']}")
    print(f"Expected return: {pattern['backtest_results']['return_pct']}%")
