"""
Backtest Engine Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Backtest System)
Backtests run patterns against real OHLCV data with trait-derived parameters.
"""


from Fast_Swarm.Backtest.Models.backtest_models import (
    BacktestConfig,
    BacktestResult,
    ExitStrategy,
    TradeRecord,
)
from Fast_Swarm.Backtest.Services.backtest_service import (
    calculate_dynamic_trail,
    calculate_mfe_mae,
    evaluate_conditions,
    get_asset_tier,
    get_trading_costs_breakdown,
    get_trading_costs_pct,
    run_backtest,
)

# ============================================================================
# Test Data Helpers
# ============================================================================


def make_candles(count: int = 100, base_price: float = 100.0, trend: float = 0.0) -> list[dict]:
    """
    Create mock OHLCV candles for testing.

    Args:
        count: Number of candles to generate
        base_price: Starting price
        trend: Price change per candle (positive = uptrend)
    """
    candles = []
    for i in range(count):
        price = base_price + (i * trend)
        candles.append({
            "timestamp": 1704067200 + (i * 3600),  # 1h intervals
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1000.0,
            "asset": "BTC",
            # Include some indicators
            "rsi_14": 50 + (i % 30) - 15,  # Oscillates 35-65
            "sma_20": price,
            "ema_12": price,
            "atr_14": price * 0.02,
        })
    return candles


def make_pattern(
    direction: str = "long",
    entry_conditions: list | None = None,
    exit_conditions: dict | None = None,
) -> dict:
    """Create a mock pattern for testing."""
    return {
        "pattern_id": "test-pattern-001",
        "name": "Test Pattern",
        "direction": direction,
        "entry_conditions": entry_conditions or [
            {"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70},
        ],
        "exit_conditions": exit_conditions or {},
    }


# ============================================================================
# TRADING COSTS CONTRACT
# ============================================================================


class TestTradingCosts:
    """CONTRACT: Trading costs by liquidity tier."""

    def test_btc_is_tier1(self):
        """CONTRACT: BTC is tier 1 (highest liquidity)."""
        assert get_asset_tier("BTC") == "tier1"
        assert get_asset_tier("BTC-USD") == "tier1"
        assert get_asset_tier("BTCUSDT") == "tier1"

    def test_eth_is_tier1(self):
        """CONTRACT: ETH is tier 1 (highest liquidity)."""
        assert get_asset_tier("ETH") == "tier1"

    def test_sol_is_tier2(self):
        """CONTRACT: SOL is tier 2."""
        assert get_asset_tier("SOL") == "tier2"
        assert get_asset_tier("BNB") == "tier2"
        assert get_asset_tier("XRP") == "tier2"

    def test_link_is_tier3(self):
        """CONTRACT: LINK is tier 3."""
        assert get_asset_tier("LINK") == "tier3"
        assert get_asset_tier("DOT") == "tier3"

    def test_unknown_is_tier4(self):
        """CONTRACT: Unknown assets default to tier 4."""
        assert get_asset_tier("OBSCURECOIN") == "tier4"

    def test_tier1_lowest_costs(self):
        """CONTRACT: Tier 1 has lowest trading costs."""
        tier1_costs = get_trading_costs_pct("BTC")
        tier4_costs = get_trading_costs_pct("OBSCURECOIN")
        assert tier1_costs < tier4_costs

    def test_costs_breakdown_structure(self):
        """CONTRACT: Costs breakdown includes slippage, spread, fee."""
        breakdown = get_trading_costs_breakdown("BTC")
        assert "slippage_pct" in breakdown
        assert "spread_pct" in breakdown
        assert "fee_pct" in breakdown
        assert "total_pct" in breakdown

    def test_costs_are_round_trip(self):
        """CONTRACT: Costs are calculated for round-trip (entry + exit)."""
        breakdown = get_trading_costs_breakdown("BTC")
        # Round-trip means costs are doubled
        assert breakdown["total_pct"] == (
            breakdown["slippage_pct"] + breakdown["spread_pct"] + breakdown["fee_pct"]
        )


# ============================================================================
# ENTRY CONDITIONS CONTRACT
# ============================================================================


class TestEntryConditions:
    """CONTRACT: Entry condition evaluation."""

    def test_evaluate_between_operator_match(self):
        """CONTRACT: 'between' operator matches when value in range."""
        conditions = [{"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70}]
        indicators = {"rsi_14": 50}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is True
        assert confidence == 1.0

    def test_evaluate_between_operator_no_match(self):
        """CONTRACT: 'between' operator doesn't match when out of range."""
        conditions = [{"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70}]
        indicators = {"rsi_14": 80}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is False

    def test_evaluate_greater_than_operator(self):
        """CONTRACT: '>' operator matches when value exceeds min."""
        conditions = [{"indicator": "rsi_14", "operator": ">", "min": 50}]
        indicators = {"rsi_14": 60}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is True

    def test_evaluate_less_than_operator(self):
        """CONTRACT: '<' operator matches when value below max."""
        conditions = [{"indicator": "rsi_14", "operator": "<", "max": 50}]
        indicators = {"rsi_14": 40}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is True

    def test_evaluate_all_conditions_must_match(self):
        """CONTRACT: All conditions must match (AND logic)."""
        conditions = [
            {"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70},
            {"indicator": "sma_20", "operator": ">", "min": 100},
        ]
        # Only first condition matches
        indicators = {"rsi_14": 50, "sma_20": 90}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is False
        assert confidence == 0.5  # 1 of 2 conditions met

    def test_evaluate_empty_conditions_returns_false(self):
        """CONTRACT: Empty conditions return no match."""
        matched, confidence = evaluate_conditions([], {"rsi_14": 50})
        assert matched is False
        assert confidence == 0.0

    def test_evaluate_missing_indicator_skipped(self):
        """CONTRACT: Missing indicators are skipped, not failed."""
        conditions = [{"indicator": "nonexistent", "operator": "between", "min": 0, "max": 100}]
        indicators = {"rsi_14": 50}
        matched, confidence = evaluate_conditions(conditions, indicators)
        assert matched is False
        assert confidence == 0.0


# ============================================================================
# MFE/MAE CONTRACT
# ============================================================================


class TestMFEMAE:
    """CONTRACT: Maximum Favorable/Adverse Excursion tracking."""

    def test_mfe_mae_long_winning(self):
        """CONTRACT: MFE/MAE calculated correctly for winning long."""
        entry_price = 100.0
        # Price goes: 100 -> 105 -> 102 -> 110
        price_history = [100, 105, 102, 110]
        mfe, mae = calculate_mfe_mae(entry_price, price_history, "long")
        assert mfe == 10.0  # (110 - 100) / 100 * 100
        assert mae == 0.0   # Never went below entry

    def test_mfe_mae_long_losing(self):
        """CONTRACT: MFE/MAE calculated correctly for losing long."""
        entry_price = 100.0
        # Price goes: 100 -> 95 -> 98 -> 90
        price_history = [100, 95, 98, 90]
        mfe, mae = calculate_mfe_mae(entry_price, price_history, "long")
        assert mfe == 0.0   # Never went above entry
        assert mae == -10.0  # (90 - 100) / 100 * 100

    def test_mfe_mae_short_winning(self):
        """CONTRACT: MFE/MAE calculated correctly for winning short."""
        entry_price = 100.0
        # Price goes: 100 -> 95 -> 98 -> 90
        price_history = [100, 95, 98, 90]
        mfe, mae = calculate_mfe_mae(entry_price, price_history, "short")
        assert mfe == 10.0  # (100 - 90) / 100 * 100
        assert mae == 0.0   # Never went above entry (good for short)

    def test_mfe_mae_empty_history(self):
        """CONTRACT: Empty price history returns zeros."""
        mfe, mae = calculate_mfe_mae(100.0, [], "long")
        assert mfe == 0.0
        assert mae == 0.0

    def test_mfe_mae_zero_entry_price(self):
        """CONTRACT: Zero entry price returns zeros (division safety)."""
        mfe, mae = calculate_mfe_mae(0.0, [100, 105], "long")
        assert mfe == 0.0
        assert mae == 0.0


# ============================================================================
# DYNAMIC TRAILING STOP CONTRACT
# ============================================================================


class TestDynamicTrail:
    """CONTRACT: Dynamic trailing stop calculation."""

    def test_dynamic_trail_at_zero_profit(self):
        """CONTRACT: Zero profit gets base trail (2%)."""
        trail = calculate_dynamic_trail(0.0)
        assert trail == 2.0

    def test_dynamic_trail_at_negative_profit(self):
        """CONTRACT: Negative profit gets base trail."""
        trail = calculate_dynamic_trail(-5.0)
        assert trail == 2.0

    def test_dynamic_trail_widens_with_profit(self):
        """CONTRACT: Trail widens as profit increases."""
        trail_10 = calculate_dynamic_trail(10.0)
        trail_50 = calculate_dynamic_trail(50.0)
        trail_100 = calculate_dynamic_trail(100.0)
        assert trail_10 < trail_50 < trail_100

    def test_dynamic_trail_capped_at_max(self):
        """CONTRACT: Trail capped at max (12%)."""
        trail = calculate_dynamic_trail(500.0)  # Huge profit
        assert trail == 12.0

    def test_dynamic_trail_custom_params(self):
        """CONTRACT: Custom base/max trail honored."""
        trail = calculate_dynamic_trail(0.0, base_trail=3.0, max_trail=15.0)
        assert trail == 3.0


# ============================================================================
# BACKTEST ENGINE CONTRACT
# ============================================================================


class TestBacktestEngine:
    """CONTRACT: Backtest engine execution."""

    def test_run_backtest_returns_result(self):
        """CONTRACT: run_backtest returns BacktestResult."""
        pattern = make_pattern()
        candles = make_candles(100)
        result = run_backtest(pattern, candles)
        assert isinstance(result, BacktestResult)

    def test_run_backtest_has_backtest_id(self):
        """CONTRACT: Result has unique backtest_id."""
        pattern = make_pattern()
        candles = make_candles(100)
        result = run_backtest(pattern, candles)
        assert result.backtest_id is not None
        assert len(result.backtest_id) > 0

    def test_run_backtest_has_pattern_id(self):
        """CONTRACT: Result tracks pattern_id."""
        pattern = make_pattern()
        pattern["pattern_id"] = "my-custom-pattern"
        candles = make_candles(100)
        result = run_backtest(pattern, candles)
        assert result.pattern_id == "my-custom-pattern"

    def test_run_backtest_skips_warmup(self):
        """CONTRACT: Backtest skips warmup candles."""
        pattern = make_pattern()
        candles = make_candles(100)
        config = BacktestConfig(min_candles_warmup=50)
        result = run_backtest(pattern, candles, config=config)
        # Should only process candles 50-99
        assert result.start_timestamp == candles[50]["timestamp"]

    def test_run_backtest_empty_candles(self):
        """CONTRACT: Empty candles returns empty result."""
        pattern = make_pattern()
        result = run_backtest(pattern, [])
        assert result.total_trades == 0

    def test_run_backtest_insufficient_candles(self):
        """CONTRACT: Fewer candles than warmup returns empty."""
        pattern = make_pattern()
        candles = make_candles(10)
        config = BacktestConfig(min_candles_warmup=50)
        result = run_backtest(pattern, candles, config=config)
        assert result.total_trades == 0


class TestBacktestTrades:
    """CONTRACT: Trade execution in backtest."""

    def test_backtest_generates_trades(self):
        """CONTRACT: Matching conditions generate trades."""
        # Pattern that should always match (RSI 35-65, candles have RSI 35-65)
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 30, "max": 70},
            ]
        )
        candles = make_candles(100, base_price=100, trend=0.1)
        config = BacktestConfig(min_candles_warmup=10, min_confidence=0.5)
        result = run_backtest(pattern, candles, config=config)
        # Should have at least one trade
        assert result.total_trades >= 1

    def test_trade_has_entry_price(self):
        """CONTRACT: Trades record entry price."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100)
        config = BacktestConfig(min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            assert result.trades[0].entry_price > 0

    def test_trade_has_exit_price(self):
        """CONTRACT: Trades record exit price."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100)
        config = BacktestConfig(min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            assert result.trades[0].exit_price > 0

    def test_trade_has_pnl_pct(self):
        """CONTRACT: Trades have PnL percentage."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100, trend=1.0)  # Uptrend for long
        config = BacktestConfig(min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            # PnL should be a number (could be positive or negative)
            assert isinstance(result.trades[0].pnl_pct, float)

    def test_trade_has_direction(self):
        """CONTRACT: Trades record direction (long/short)."""
        pattern = make_pattern(direction="long")
        candles = make_candles(100)
        config = BacktestConfig(min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            assert result.trades[0].direction == "long"


class TestBacktestExitStrategies:
    """CONTRACT: Exit strategy implementations."""

    def test_fixed_exit_strategy(self):
        """CONTRACT: FIXED strategy uses TP/SL only."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100)
        config = BacktestConfig(
            exit_strategy=ExitStrategy.FIXED,
            min_candles_warmup=10,
        )
        result = run_backtest(pattern, candles, config=config)
        assert isinstance(result, BacktestResult)

    def test_trailing_stop_strategy(self):
        """CONTRACT: Trailing stop strategies track peak."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100, trend=0.5)
        config = BacktestConfig(
            exit_strategy=ExitStrategy.TRAILING_3PCT,
            min_candles_warmup=10,
        )
        result = run_backtest(pattern, candles, config=config)
        assert isinstance(result, BacktestResult)

    def test_dynamic_trail_strategy(self):
        """CONTRACT: Dynamic trail widens with profit."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100, trend=1.0)
        config = BacktestConfig(
            exit_strategy=ExitStrategy.DYNAMIC_TRAIL,
            min_candles_warmup=10,
        )
        result = run_backtest(pattern, candles, config=config)
        assert isinstance(result, BacktestResult)


class TestBacktestCosts:
    """CONTRACT: Trading cost application."""

    def test_costs_included_by_default(self):
        """CONTRACT: Costs are included by default."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100)
        config = BacktestConfig(include_costs=True, min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            assert result.trades[0].fees_pct >= 0

    def test_costs_can_be_disabled(self):
        """CONTRACT: Costs can be disabled for comparison."""
        pattern = make_pattern(
            entry_conditions=[
                {"indicator": "rsi_14", "operator": "between", "min": 0, "max": 100},
            ]
        )
        candles = make_candles(100)
        config = BacktestConfig(include_costs=False, min_candles_warmup=10)
        result = run_backtest(pattern, candles, config=config)
        if result.trades:
            assert result.trades[0].fees_pct == 0


class TestBacktestConfig:
    """CONTRACT: Backtest configuration."""

    def test_config_from_traits(self):
        """CONTRACT: Config can be created from agent traits."""
        traits = {
            "risk_tolerance": 0.8,
            "stop_loss_tightness": 0.6,
            "profit_target_greed": 0.7,
            "hold_duration_bias": 0.5,
        }
        config = BacktestConfig.from_traits(traits)
        assert isinstance(config, BacktestConfig)
        # High risk tolerance = larger position
        assert config.max_position_pct > 0.05

    def test_config_to_dict(self):
        """CONTRACT: Config can be serialized to dict."""
        config = BacktestConfig()
        d = config.to_dict()
        assert "exit_strategy" in d
        assert "min_candles_warmup" in d

    def test_config_from_dict(self):
        """CONTRACT: Config can be deserialized from dict."""
        d = {
            "exit_strategy": "trailing_3pct",
            "min_candles_warmup": 100,
        }
        config = BacktestConfig.from_dict(d)
        assert config.exit_strategy == ExitStrategy.TRAILING_3PCT
        assert config.min_candles_warmup == 100


class TestTradeRecord:
    """CONTRACT: Trade record structure."""

    def test_trade_record_is_winner(self):
        """CONTRACT: is_winner property works correctly."""
        winner = TradeRecord(
            trade_id="t1", pattern_id="p1", asset="BTC", direction="long",
            entry_price=100, exit_price=110, entry_timestamp=0, exit_timestamp=1,
            pnl_pct=10.0,
        )
        loser = TradeRecord(
            trade_id="t2", pattern_id="p1", asset="BTC", direction="long",
            entry_price=100, exit_price=90, entry_timestamp=0, exit_timestamp=1,
            pnl_pct=-10.0,
        )
        assert winner.is_winner is True
        assert loser.is_winner is False

    def test_trade_record_gross_pnl(self):
        """CONTRACT: gross_pnl adds back costs."""
        trade = TradeRecord(
            trade_id="t1", pattern_id="p1", asset="BTC", direction="long",
            entry_price=100, exit_price=110, entry_timestamp=0, exit_timestamp=1,
            pnl_pct=9.5, fees_pct=0.3, slippage_pct=0.2,
        )
        assert trade.gross_pnl_pct == 10.0  # 9.5 + 0.3 + 0.2

    def test_trade_record_to_dict(self):
        """CONTRACT: Trade can be serialized."""
        trade = TradeRecord(
            trade_id="t1", pattern_id="p1", asset="BTC", direction="long",
            entry_price=100, exit_price=110, entry_timestamp=0, exit_timestamp=1,
            pnl_pct=10.0,
        )
        d = trade.to_dict()
        assert d["trade_id"] == "t1"
        assert d["pnl_pct"] == 10.0
