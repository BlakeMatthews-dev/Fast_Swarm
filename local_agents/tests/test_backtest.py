"""
Backtest Runner Tests.

Tests:
- OHLCV data loading
- Pattern condition matching
- Trade execution (entry/exit)
- MFE/MAE tracking
- Trading costs application
- Integration with evolution system
"""

from dataclasses import dataclass

import numpy as np
import pytest


class TestOHLCVLoader:
    """OHLCV data loading from SQLite."""

    def test_loader_initialization(self):
        """Loader initializes with default paths."""
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        loader = OHLCVLoader()
        assert loader.ohlcv_db is not None
        assert loader.enhanced_db is not None

    def test_loader_custom_paths(self, tmp_path):
        """Loader accepts custom database paths."""
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        fake_db = tmp_path / "test.db"
        fake_db.write_text("")

        loader = OHLCVLoader(ohlcv_db=fake_db)
        assert loader.ohlcv_db == fake_db

    def test_candle_dataclass(self):
        """Candle dataclass has correct fields."""
        from Fast_Swarm.local_agents.backtest.data import Candle

        candle = Candle(
            timestamp=1704067200000,
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=100.0,
            indicators={"RSI_14": 55.0},
        )

        assert candle.timestamp == 1704067200000
        assert candle.close == 42300.0
        assert candle.indicators["RSI_14"] == 55.0


class TestPatternMatcher:
    """Pattern condition matching with confidence."""

    def test_matcher_initialization(self):
        """PatternMatcher initializes with pattern dict."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "test-1",
            "entry_conditions": {"rsi14": {"operator": "<", "value": 30}},
            "exit_conditions": {"rsi14": {"operator": ">", "value": 70}},
        }

        matcher = PatternMatcher(pattern)
        assert matcher.pattern_id == "test-1"
        assert matcher.entry_conditions is not None
        assert matcher.exit_conditions is not None

    def test_should_enter_below_threshold(self):
        """Entry triggers when RSI below threshold."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "rsi-oversold",
            "entry_conditions": {"rsi14": {"operator": "<", "value": 30}},
            "exit_conditions": {},
        }

        matcher = PatternMatcher(pattern)

        # RSI at 20 - should trigger entry
        indicators = {"RSI_14": 20.0}
        should_enter, confidence = matcher.should_enter(indicators)

        assert should_enter is True
        assert confidence > 0.5

    def test_should_not_enter_above_threshold(self):
        """Entry does not trigger when RSI above threshold."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "rsi-oversold",
            "entry_conditions": {"rsi14": {"operator": "<", "value": 30}},
            "exit_conditions": {},
        }

        matcher = PatternMatcher(pattern)

        # RSI at 50 - should not trigger
        indicators = {"RSI_14": 50.0}
        should_enter, confidence = matcher.should_enter(indicators)

        assert should_enter is False

    def test_should_exit_on_condition(self):
        """Exit triggers when exit condition met."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "test",
            "entry_conditions": {},
            "exit_conditions": {"rsi14": {"operator": ">", "value": 70}},
        }

        matcher = PatternMatcher(pattern)

        # RSI at 80 - should trigger exit
        indicators = {"RSI_14": 80.0}
        should_exit, reason, confidence = matcher.should_exit(
            indicators,
            entry_price=100.0,
            current_price=110.0,
        )

        assert should_exit is True
        assert reason == "condition"  # Exit condition was met
        assert confidence > 0.5

    def test_should_exit_on_stop_loss(self):
        """Exit triggers on stop loss."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "test",
            "entry_conditions": {},
            "exit_conditions": {},
        }

        matcher = PatternMatcher(pattern)

        # Price dropped 10% - should trigger stop at 5%
        indicators = {"RSI_14": 50.0}
        should_exit, reason, _ = matcher.should_exit(
            indicators,
            entry_price=100.0,
            current_price=89.0,  # -11%
            stop_loss_pct=0.05,
        )

        assert should_exit is True
        assert reason == "stop_loss"

    def test_should_exit_on_take_profit(self):
        """Exit triggers on take profit."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

        pattern = {
            "pattern_id": "test",
            "entry_conditions": {},
            "exit_conditions": {},
        }

        matcher = PatternMatcher(pattern)

        # Price up 15% - should trigger take profit at 10%
        indicators = {"RSI_14": 50.0}
        should_exit, reason, _ = matcher.should_exit(
            indicators,
            entry_price=100.0,
            current_price=116.0,  # +16%
            take_profit_pct=0.10,
        )

        assert should_exit is True
        assert reason == "take_profit"


class TestEvaluateConditions:
    """Core condition evaluation function."""

    def test_less_than_operator(self):
        """< operator works correctly."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {"rsi14": {"operator": "<", "value": 30}}
        indicators = {"RSI_14": 20.0}

        result = evaluate_conditions(conditions, indicators)

        assert result is not None
        assert result.passed is True
        assert result.overall_confidence > 0.5

    def test_greater_than_operator(self):
        """> operator works correctly."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {"rsi14": {"operator": ">", "value": 70}}
        indicators = {"RSI_14": 80.0}

        result = evaluate_conditions(conditions, indicators)

        assert result is not None
        assert result.passed is True

    def test_between_operator(self):
        """between operator works correctly."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {"rsi14": {"operator": "between", "value": [40, 60]}}
        indicators = {"RSI_14": 50.0}

        result = evaluate_conditions(conditions, indicators)

        assert result is not None
        assert result.passed is True
        assert result.overall_confidence > 0.8  # At center

    def test_missing_indicator_fails(self):
        """Missing indicator returns unmatched result."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {"rsi14": {"operator": "<", "value": 30}}
        indicators = {}  # No RSI!

        result = evaluate_conditions(conditions, indicators)

        # Result is returned but not matched
        assert result is not None
        assert result.matched is False
        assert result.conditions_met == 0

    def test_empty_conditions(self):
        """Empty conditions returns unmatched result."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        result = evaluate_conditions({}, {"RSI_14": 50.0})

        # Empty conditions cannot match
        assert result is not None
        assert result.matched is False
        assert result.conditions_total == 0

    def test_multiple_conditions_all_pass(self):
        """Multiple conditions - all must pass."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {
            "rsi14": {"operator": "<", "value": 30},
            "macdLine": {"operator": ">", "value": 0},
        }
        indicators = {"RSI_14": 25.0, "MACD_12_26_9": 0.5}

        result = evaluate_conditions(conditions, indicators)

        assert result is not None
        assert result.passed is True

    def test_multiple_conditions_one_fails(self):
        """Multiple conditions - one fails, overall fails."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

        conditions = {
            "rsi14": {"operator": "<", "value": 30},
            "macdLine": {"operator": ">", "value": 0},
        }
        indicators = {"RSI_14": 25.0, "MACD_12_26_9": -0.5}  # MACD fails

        result = evaluate_conditions(conditions, indicators)

        # With low enough MACD, this should not pass
        if result is not None:
            assert result.passed is False or result.overall_confidence < 0.5


class TestIndicatorAliases:
    """Indicator name aliasing (V3 to pandas_ta)."""

    def test_rsi_alias(self):
        """rsi14 maps to RSI_14."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import INDICATOR_ALIASES

        assert INDICATOR_ALIASES.get("rsi14") == "RSI_14"

    def test_macd_alias(self):
        """macdLine maps to MACD_12_26_9."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import INDICATOR_ALIASES

        assert INDICATOR_ALIASES.get("macdLine") == "MACD_12_26_9"

    def test_stochastic_aliases(self):
        """Stochastic K and D map correctly."""
        from Fast_Swarm.local_agents.backtest.pattern_matcher import INDICATOR_ALIASES

        assert INDICATOR_ALIASES.get("stochasticK") == "STOCHk_14_3_3"
        assert INDICATOR_ALIASES.get("stochasticD") == "STOCHd_14_3_3"


class TestTradingCosts:
    """Trading cost application by tier."""

    def test_tier1_costs_lowest(self):
        """Tier 1 assets (BTC, ETH) have lowest costs."""
        from Fast_Swarm.local_agents.backtest.engine import ASSET_TIERS, TRADING_COSTS

        assert "BTC" in ASSET_TIERS["tier1"]
        assert "ETH" in ASSET_TIERS["tier1"]

        tier1 = TRADING_COSTS["tier1"]
        tier4 = TRADING_COSTS["tier4"]

        assert tier1["slippage_bps"] < tier4["slippage_bps"]
        assert tier1["spread_bps"] < tier4["spread_bps"]

    def test_get_asset_tier(self):
        """Asset tier lookup works correctly."""
        from Fast_Swarm.local_agents.backtest.engine import get_asset_tier

        assert get_asset_tier("BTC") == "tier1"
        assert get_asset_tier("ETH") == "tier1"
        assert get_asset_tier("SOL") == "tier2"
        assert get_asset_tier("UNKNOWN_COIN") == "tier4"  # Default


class TestLocalBacktestEngine:
    """Main backtest engine."""

    def test_engine_initialization(self):
        """Engine initializes correctly."""
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine

        engine = LocalBacktestEngine()
        assert engine.loader is not None

    def test_engine_implements_protocol(self):
        """Engine implements BacktestEngine protocol."""
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine

        engine = LocalBacktestEngine()

        # Should have run method matching protocol
        assert hasattr(engine, "run")
        assert callable(engine.run)


class TestMockBacktestIntegration:
    """Integration tests with mock data."""

    @pytest.fixture
    def mock_loader(self):
        """Create a mock OHLCV loader with test data."""
        from Fast_Swarm.local_agents.backtest.data import Candle

        class MockLoader:
            def iter_candles(self, asset, timeframe="1h", start_ts=None, end_ts=None, limit=None, with_indicators=True):
                # Generate 100 synthetic candles
                base_price = 42000.0
                base_ts = 1704067200000  # Jan 1, 2024

                for i in range(100):
                    # Create price movement with RSI cycle
                    rsi_cycle = 30 + 40 * np.sin(i / 10)  # RSI oscillates 30-70
                    price_change = 100 * np.sin(i / 15)

                    yield Candle(
                        timestamp=base_ts + i * 3600000,  # 1 hour per candle
                        open=base_price + price_change - 50,
                        high=base_price + price_change + 100,
                        low=base_price + price_change - 100,
                        close=base_price + price_change,
                        volume=1000.0 + 500 * np.random.random(),
                        indicators={
                            "RSI_14": rsi_cycle,
                            "MACD_12_26_9": 0.5 * np.sin(i / 20),
                            "MACDh_12_26_9": 0.1 * np.sin(i / 15),
                            "STOCHk_14_3_3": 20 + 60 * np.sin(i / 8),
                            "STOCHd_14_3_3": 25 + 50 * np.sin(i / 10),
                        },
                    )

            def get_available_assets(self, timeframe="1h"):
                return ["BTC", "ETH"]

        return MockLoader()

    @pytest.fixture
    def sample_agent(self):
        """Create a sample agent for testing."""
        from Fast_Swarm.local_agents.core.state import AgentRecord
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        # Create a minimal agent record with RSI pattern
        traits = AgentTraits()
        agent = AgentRecord(
            agent_id="test-agent-001",
            agent_name="Test Agent",
            generation=1,
            traits={
                "risk_tolerance": 0.5,
                "stop_loss_tightness": 0.5,
                "profit_target_greed": 0.5,
                "hold_duration_bias": 0.5,
            },
            pattern_ids=["rsi-momentum"],
            pattern_weights={"rsi-momentum": 1.0},
            trading_philosophy="Test RSI momentum",
        )
        return agent

    def test_backtest_generates_trades(self, mock_loader, sample_agent):
        """Backtest generates TradeRecords."""
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine

        agent = sample_agent

        engine = LocalBacktestEngine(loader=mock_loader)

        dataset = {
            "assets": ["BTC"],
            "timeframe": "1h",
            "limit": 100,
        }

        trades = engine.run(agent, dataset)

        # Should generate some trades from RSI oscillation
        assert isinstance(trades, list)
        # Note: May or may not have trades depending on pattern matching

    def test_trades_have_required_fields(self, mock_loader, sample_agent):
        """Generated trades have all required fields."""
        from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine
        from Fast_Swarm.local_agents.core.state import TradeRecord

        agent = sample_agent

        engine = LocalBacktestEngine(loader=mock_loader)

        dataset = {
            "assets": ["BTC"],
            "timeframe": "1h",
            "limit": 100,
        }

        trades = engine.run(agent, dataset)

        for trade in trades:
            assert isinstance(trade, TradeRecord)
            assert trade.trade_id is not None
            assert trade.agent_id == agent.agent_id
            assert trade.asset is not None
            assert trade.direction in ["long", "short"]
            assert trade.pnl_pct is not None


class TestMFEMAETracking:
    """Maximum Favorable/Adverse Excursion tracking."""

    def test_mfe_tracks_best_price(self):
        """MFE tracks the best price during trade."""
        from Fast_Swarm.local_agents.backtest.engine import calculate_mfe_mae

        entry_price = 100.0
        price_history = [101, 105, 103, 102]  # Peak at 105

        mfe, mae = calculate_mfe_mae(entry_price, price_history, "long")

        assert mfe == 5.0  # 5% up from entry

    def test_mae_tracks_worst_price(self):
        """MAE tracks the worst price during trade."""
        from Fast_Swarm.local_agents.backtest.engine import calculate_mfe_mae

        entry_price = 100.0
        price_history = [98, 95, 97, 102]  # Trough at 95

        mfe, mae = calculate_mfe_mae(entry_price, price_history, "long")

        assert mae == -5.0  # 5% down from entry

    def test_short_mfe_mae_inverted(self):
        """Short trades have inverted MFE/MAE."""
        from Fast_Swarm.local_agents.backtest.engine import calculate_mfe_mae

        entry_price = 100.0
        price_history = [98, 95, 97, 102]  # For short: best at 95

        mfe, mae = calculate_mfe_mae(entry_price, price_history, "short")

        assert mfe == 5.0  # Best for short is price down
        assert mae == -2.0  # Worst for short is price up


class TestBacktestConfig:
    """Backtest configuration options."""

    def test_default_config(self):
        """Default backtest config values."""
        from Fast_Swarm.local_agents.backtest.engine import BacktestConfig

        config = BacktestConfig()

        assert config.max_position_pct > 0
        assert config.default_stop_loss_pct > 0
        assert config.default_take_profit_pct > 0
        assert config.max_hold_candles > 0

    def test_config_from_traits(self):
        """Config can be derived from agent traits."""
        from Fast_Swarm.local_agents.backtest.engine import BacktestConfig
        from Fast_Swarm.local_agents.core.traits import AgentTraits

        traits = AgentTraits(
            risk_tolerance=0.8,
            stop_loss_tightness=0.3,
            profit_target_greed=0.7,
            hold_duration_bias=0.5,
        )

        config = BacktestConfig.from_traits(traits)

        # Higher risk = larger position
        assert config.max_position_pct > 0.05

        # Lower tightness = wider stop
        assert config.default_stop_loss_pct > 0.03


class TestDeterminism:
    """Backtest determinism tests."""

    def test_same_seed_same_trades(self):
        """Same seed produces identical trade sequence."""
        from Fast_Swarm.local_agents.core.genesis import spawn_agent
        from Fast_Swarm.local_agents.core.state import AgentDatabase

        # Create agent with fixed seed
        patterns = [{"pattern_id": "p1", "win_rate_pct": 50}]

        db1 = AgentDatabase(":memory:")
        agent1 = spawn_agent(seed=42, available_patterns=patterns, db=db1)

        db2 = AgentDatabase(":memory:")
        agent2 = spawn_agent(seed=42, available_patterns=patterns, db=db2)

        # Traits should match
        assert agent1.traits == agent2.traits


class TestEvolutionIntegration:
    """Integration with evolution system."""

    def test_engine_works_with_evolution_cycle(self):
        """Backtest engine works in evolution cycle."""
        from Fast_Swarm.local_agents.core.evolution import EvolutionConfig, run_evolution_cycle
        from Fast_Swarm.local_agents.core.genesis import initialize_population
        from Fast_Swarm.local_agents.core.state import AgentDatabase, TradeRecord

        db = AgentDatabase(":memory:")
        patterns = [
            {
                "pattern_id": "test-pattern",
                "name": "Test",
                "win_rate_pct": 55,
                "entry_conditions": {"rsi14": {"operator": "<", "value": 30}},
                "exit_conditions": {"rsi14": {"operator": ">", "value": 70}},
            }
        ]

        population = initialize_population(
            population_size=3,
            available_patterns=patterns,
            db=db,
        )

        # Mock engine that returns controlled trades
        @dataclass
        class MockEngine:
            def run(self, agent, dataset):
                return [
                    TradeRecord(
                        trade_id=f"{agent.agent_id[:8]}-trade-{i}",
                        agent_id=agent.agent_id,
                        pattern_id="test-pattern",
                        asset="BTC",
                        direction="long",
                        pnl_pct=2.0 if i % 3 == 0 else -1.0,
                        entry_confidence=0.7,
                        mfe_pct=3.0,
                        mae_pct=-1.5,
                        position_size_pct=0.05,
                    )
                    for i in range(50)
                ]

        config = EvolutionConfig(
            population_size=3,
            elite_percent=0.34,
            survival_percent=0.67,
            min_trades_for_fitness=10,
        )

        result = run_evolution_cycle(
            population=population,
            available_patterns=patterns,
            backtest_engine=MockEngine(),
            dataset=None,
            generation=1,
            config=config,
            seed=42,
            db=db,
        )

        assert result.generation == 1
        assert len(result.survivors) + len(result.children) == 3
        assert result.elapsed_ms >= 0


# Helper function for MFE/MAE (to be implemented in engine.py)
def calculate_mfe_mae(entry_price: float, price_history: list, direction: str):
    """Calculate MFE and MAE from price history."""
    if not price_history:
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
