#!/usr/bin/env python
"""
Trio Rotation Backtest Test Script.

Tests the trio rotation strategy with synthetic cross-pair data.
Goal: Accumulate more BTC over time by rotating between BTC/ETH/SOL.
"""

import os
import sys

# Add both parent (for Fast_Swarm module) and current (for local_agents)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
parent_of_project = os.path.dirname(project_root)

sys.path.insert(0, parent_of_project)  # For Fast_Swarm imports
sys.path.insert(0, project_root)  # For local_agents imports

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, "local-utilities", ".env"))

from dataclasses import dataclass
from datetime import datetime

from Fast_Swarm.local_agents.backtest.cross_pairs import TrioDataLoader
from Fast_Swarm.local_agents.backtest.trio_engine import (
    Holding,
    TrioBacktestEngine,
    TrioTradeRecord,
    calculate_trio_metrics,
)


@dataclass
class MockAgentRecord:
    """Minimal agent for testing trio backtest."""

    agent_id: str
    pattern_ids: list[str]
    traits: dict


def create_test_patterns() -> dict[str, dict]:
    """
    Create test patterns for trio rotation.

    These patterns work on RSI oversold/overbought conditions.
    """
    return {
        "rsi_oversold": {
            "pattern_id": "rsi_oversold",
            "name": "RSI Oversold Entry",
            "entry_conditions": [
                {"indicator": "rsi_14", "operator": "<", "value": 35},
            ],
            "exit_conditions": {
                "take_profit_pct": 5.0,
                "stop_loss_pct": -3.0,
            },
        },
        "rsi_overbought": {
            "pattern_id": "rsi_overbought",
            "name": "RSI Overbought Exit",
            "entry_conditions": [
                {"indicator": "rsi_14", "operator": ">", "value": 65},
            ],
            "exit_conditions": {
                "take_profit_pct": 3.0,
            },
        },
        "macd_bullish": {
            "pattern_id": "macd_bullish",
            "name": "MACD Bullish Cross",
            "entry_conditions": [
                {"indicator": "macd_histogram", "operator": ">", "value": 0},
                {"indicator": "rsi_14", "operator": "<", "value": 60},
            ],
            "exit_conditions": {
                "take_profit_pct": 8.0,
                "stop_loss_pct": -5.0,
            },
        },
        "volatility_breakout": {
            "pattern_id": "volatility_breakout",
            "name": "Volatility Expansion",
            "entry_conditions": [
                {"indicator": "bb_width", "operator": ">", "value": 0.03},
                {"indicator": "close", "operator": ">", "value": 0},  # Always true
            ],
            "exit_conditions": {
                "take_profit_pct": 10.0,
            },
        },
    }


def create_test_agent(pattern_ids: list[str]) -> MockAgentRecord:
    """Create a test agent with specified patterns."""
    return MockAgentRecord(
        agent_id="test-trio-agent-001",
        pattern_ids=pattern_ids,
        traits={
            "min_threshold": 0.5,  # 50% confidence threshold
            "risk_tolerance": 0.6,
            "momentum_vs_reversion": 0.4,  # Slight reversion preference
        },
    )


def print_trade_summary(trades: list[TrioTradeRecord]) -> None:
    """Print a summary of trades."""
    print("\n" + "=" * 80)
    print("TRADE HISTORY")
    print("=" * 80)

    for i, trade in enumerate(trades[:20], 1):  # Show first 20
        ts_str = datetime.fromtimestamp(trade.timestamp / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"\n{i}. [{ts_str}] {trade.action.upper()}: {trade.from_asset} → {trade.to_asset}")
        print(f"   Pair: {trade.pair_used} @ {trade.price:.8f}")
        print(f"   Amount: {trade.from_amount:.4f} → {trade.to_amount:.4f}")
        print(f"   BTC P&L: {trade.btc_pnl:+.8f} ({trade.data_source})")

    if len(trades) > 20:
        print(f"\n... and {len(trades) - 20} more trades")


def print_metrics(metrics: dict) -> None:
    """Print performance metrics."""
    print("\n" + "=" * 80)
    print("PERFORMANCE METRICS")
    print("=" * 80)

    print(f"\nTotal Trades:     {metrics.get('total_trades', 0)}")
    print(f"  - Rotations:    {metrics.get('rotations', 0)}")
    print(f"  - USD Trades:   {metrics.get('usd_trades', 0)}")
    print(f"\nWin Rate:         {metrics.get('win_rate', 0):.1%}")
    print(f"Total BTC P&L:    {metrics.get('total_btc_pnl', 0):+.8f}")
    print(f"Avg BTC P&L:      {metrics.get('avg_btc_pnl', 0):+.8f}")
    print(f"Best Trade:       {metrics.get('best_trade_btc', 0):+.8f}")
    print(f"Worst Trade:      {metrics.get('worst_trade_btc', 0):+.8f}")


def main():
    """Run trio rotation backtest test."""
    print("=" * 80)
    print("TRIO ROTATION BACKTEST TEST")
    print("=" * 80)
    print("\nStrategy: Accumulate BTC by rotating between BTC/ETH/SOL")
    print("Priority: Cross-pairs first (rotation), then USD pairs (entry/exit)")

    # Step 1: Load trio data
    print("\n" + "-" * 40)
    print("STEP 1: Loading Trio Data")
    print("-" * 40)

    loader = TrioDataLoader(timeframe="1h")
    bundles = loader.load(limit=1000)  # Load 1000 candles for test

    if not bundles:
        print("ERROR: No data loaded. Check database connection.")
        return

    stats = loader.get_stats()
    print("\nLoaded data:")
    print(f"  - BTC-USD: {stats['btc_candles']} candles")
    print(f"  - ETH-USD: {stats['eth_candles']} candles")
    print(f"  - SOL-USD: {stats['sol_candles']} candles")
    print(f"  - Cross-pairs: {stats['cross_pairs']}")
    print(f"  - Total bundles: {len(bundles)}")

    # Show sample bundle
    sample = bundles[0]
    print(f"\nSample bundle (timestamp {sample.timestamp}):")
    print(f"  BTC-USD: ${sample.btc_usd['close']:,.2f}")
    print(f"  ETH-USD: ${sample.eth_usd['close']:,.2f}")
    print(f"  SOL-USD: ${sample.sol_usd['close']:,.2f}")
    print(f"  ETH/BTC: {sample.eth_btc['close']:.6f}")
    print(f"  SOL/BTC: {sample.sol_btc['close']:.8f}")
    print(f"  SOL/ETH: {sample.sol_eth['close']:.6f}")

    # Step 2: Create test patterns and agent
    print("\n" + "-" * 40)
    print("STEP 2: Creating Test Agent")
    print("-" * 40)

    patterns = create_test_patterns()
    agent = create_test_agent(["rsi_oversold", "macd_bullish", "volatility_breakout"])

    print(f"\nAgent: {agent.agent_id}")
    print(f"Patterns: {agent.pattern_ids}")
    print(f"Min threshold: {agent.traits['min_threshold']}")

    # Step 3: Run backtest
    print("\n" + "-" * 40)
    print("STEP 3: Running Trio Backtest")
    print("-" * 40)

    engine = TrioBacktestEngine(
        pattern_matcher=None,  # Using built-in evaluation
        patterns=patterns,
        slippage_pct=0.1,
        fee_pct=0.1,
    )

    trades, final_position = engine.run(
        agent=agent,
        bundles=bundles,
        initial_usd=10000.0,
    )

    print(f"\nCompleted {len(bundles)} candles")
    print(f"Generated {len(trades)} trades")

    # Step 4: Show results
    print_trade_summary(trades)

    metrics = calculate_trio_metrics(trades)
    print_metrics(metrics)

    # Final position
    print("\n" + "=" * 80)
    print("FINAL POSITION")
    print("=" * 80)
    print(f"\nHolding: {final_position.holding.value}")
    print(f"Amount: {final_position.amount:.4f}")

    if final_position.holding == Holding.USD:
        print(f"Value: ${final_position.amount:,.2f}")
    else:
        # Get BTC equivalent from last bundle
        last_bundle = bundles[-1]
        btc_value = engine._to_btc(final_position.holding.value, final_position.amount, last_bundle)
        print(f"BTC Equivalent: {btc_value:.8f} BTC")
        usd_value = btc_value * last_bundle.btc_usd["close"]
        print(f"USD Value: ${usd_value:,.2f}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
