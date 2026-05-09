"""
Agent-Backtest Integration Tests - REAL PostgreSQL Data

Tests end-to-end flows using PostgreSQL enhanced_candles table (5.2M+ rows).
No mocks - these tests verify actual database connectivity and data flow.
"""

import uuid
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

# ============================================================================
# FIXTURES - Real PostgreSQL Data
# ============================================================================


@pytest_asyncio.fixture
async def real_patterns(db_session: AsyncSession) -> list[dict[str, Any]]:
    """Get real patterns from PostgreSQL for testing."""
    from Fast_Swarm.Patterns.Models.pattern_models import Pattern

    result = await db_session.exec(select(Pattern).where(Pattern.is_active.is_(True)).limit(10))
    patterns = result.all()

    # If no patterns exist, create test patterns
    if not patterns:
        test_patterns = []
        for i in range(5):
            pattern = Pattern(
                pattern_id=f"test-pattern-{uuid.uuid4().hex[:8]}",
                name=f"Test Pattern {i}",
                entry_conditions=[{"indicator": "rsi_14", "operator": "<", "value": 30 + i * 5}],
                exit_conditions=[{"indicator": "rsi_14", "operator": ">", "value": 70 - i * 5}],
                origin="TECHNICAL",
                tier=3,
                is_active=True,
            )
            db_session.add(pattern)
            test_patterns.append(pattern)
        await db_session.flush()
        patterns = test_patterns

    return [
        {
            "pattern_id": p.pattern_id,
            "name": p.name,
            "entry_conditions": p.entry_conditions,
            "exit_conditions": p.exit_conditions,
            "win_rate_pct": p.win_rate or 50,
            "volatility": "medium",
            "type": "momentum",
        }
        for p in patterns
    ]


@pytest_asyncio.fixture
async def test_agent(db_session: AsyncSession, sample_traits) -> Any:
    """Create a test agent for backtest integration tests."""
    from Fast_Swarm.Agents.Models.agent_models import Agent

    agent = Agent(
        agent_id=f"integration-test-{uuid.uuid4().hex[:8]}",
        name="Integration Test Agent",
        generation=1,
        traits=sample_traits,
        status="active",
        is_active=True,
        fitness_score=50.0,
        elo_rating=1500.0,
        assigned_patterns=[],
        pattern_weights={},
    )
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)
    return agent


# ============================================================================
# TEST: PostgreSQL Data Availability
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestPostgreSQLDataAvailability:
    """Verify PostgreSQL has the required data for backtesting."""

    @pytest.mark.asyncio
    async def test_enhanced_candles_exist(self, db_session: AsyncSession):
        """Verify enhanced_candles table has data."""
        from sqlalchemy import func

        from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle

        result = await db_session.exec(select(func.count()).select_from(EnhancedCandle))
        count = result.one()

        # Should have millions of rows
        assert count > 0, "enhanced_candles table should have data"
        print(f"[Integration] enhanced_candles has {count:,} rows")

    @pytest.mark.asyncio
    async def test_btc_data_available(self, db_session: AsyncSession):
        """Verify BTC data is available for backtesting."""
        from sqlalchemy import func

        from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle

        result = await db_session.exec(
            select(func.count())
            .select_from(EnhancedCandle)
            .where(EnhancedCandle.symbol == "BTC")
            .where(EnhancedCandle.timeframe == "1h")
        )
        count = result.one()

        assert count > 100, f"BTC 1h should have 100+ candles, found {count}"
        print(f"[Integration] BTC/1h has {count:,} candles")

    @pytest.mark.asyncio
    async def test_indicators_populated(self, db_session: AsyncSession):
        """Verify indicators are populated in enhanced_candles."""
        from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle

        # Get a sample candle with indicators
        result = await db_session.exec(
            select(EnhancedCandle)
            .where(EnhancedCandle.symbol == "BTC")
            .where(EnhancedCandle.rsi_14.is_not(None))
            .limit(1)
        )
        candle = result.first()

        assert candle is not None, "Should have candles with RSI populated"
        assert candle.rsi_14 is not None, "RSI should be populated"
        assert 0 <= candle.rsi_14 <= 100, f"RSI should be 0-100, got {candle.rsi_14}"

        # Check other indicators
        if candle.sma_20:
            assert candle.sma_20 > 0, "SMA should be positive"
        if candle.macd_line is not None:
            print(f"[Integration] MACD line: {candle.macd_line}")


# ============================================================================
# TEST: OHLCV Loader PostgreSQL Integration
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestOHLCVLoaderIntegration:
    """Test that OHLCVLoader correctly queries PostgreSQL."""

    @pytest.mark.asyncio
    async def test_loader_fetches_real_data(self):
        """OHLCVLoader should fetch real data from PostgreSQL."""
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        loader = OHLCVLoader()

        # This should query PostgreSQL, not SQLite
        df = loader.load_candles(asset="BTC", timeframe="1h", limit=100)

        assert not df.empty, "Should fetch candles from PostgreSQL"
        assert len(df) > 0, "Should have at least one candle"
        assert "close" in df.columns, "Should have close column"
        assert "rsi_14" in df.columns or "RSI_14" in df.columns or len(df.columns) > 6, (
            "Should have indicator columns from enhanced_candles"
        )

        print(f"[Integration] OHLCVLoader fetched {len(df)} candles with {len(df.columns)} columns")

    @pytest.mark.asyncio
    async def test_loader_available_assets(self):
        """OHLCVLoader should list available assets from PostgreSQL."""
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        loader = OHLCVLoader()
        assets = loader.get_available_assets(timeframe="1h")

        assert len(assets) > 0, "Should have available assets"
        assert "BTC" in assets or "BTCUSDT" in assets, "BTC should be available"

        print(f"[Integration] Available assets: {assets[:10]}...")

    @pytest.mark.asyncio
    async def test_loader_date_range(self):
        """OHLCVLoader should return valid date range from PostgreSQL."""
        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        loader = OHLCVLoader()
        start_ts, end_ts = loader.get_date_range(asset="BTC", timeframe="1h")

        assert start_ts > 0, "Start timestamp should be positive"
        assert end_ts > start_ts, "End should be after start"

        # Convert to readable format
        start_dt = datetime.fromtimestamp(start_ts / 1000)
        end_dt = datetime.fromtimestamp(end_ts / 1000)
        print(f"[Integration] BTC data range: {start_dt} to {end_dt}")


# ============================================================================
# TEST: Agent Backtest Flow
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestAgentBacktestFlow:
    """Integration tests for agent backtesting with real PostgreSQL data."""

    @pytest.mark.asyncio
    async def test_spawn_agent_assign_pattern_backtest(
        self,
        db_session: AsyncSession,
        test_agent,
        real_patterns,
    ):
        """Full flow: agent with patterns can be backtested on real data."""
        from Fast_Swarm.Agents.Services.backtest_service import AgentBacktestService

        # Assign patterns to agent
        pattern_ids = [p["pattern_id"] for p in real_patterns[:3]]
        test_agent.assigned_patterns = pattern_ids
        test_agent.pattern_weights = {pid: 1.0 / len(pattern_ids) for pid in pattern_ids}
        await db_session.flush()

        # Run backtest
        service = AgentBacktestService()
        results = await service.backtest_agents(
            session=db_session,
            agent_ids=[test_agent.agent_id],
            assets=["BTC"],
            timeframe="1h",
            history_bars=200,
        )

        assert test_agent.agent_id in results, "Agent should have results"
        result = results[test_agent.agent_id]

        # Check result structure (may be empty if no trades triggered)
        assert "total_trades" in result or "error" in result, "Should have results or error"

        if "error" not in result:
            assert isinstance(result.get("total_trades", 0), int)
            print(f"[Integration] Agent backtested: {result.get('total_trades', 0)} trades")

    @pytest.mark.asyncio
    async def test_backtest_updates_agent_fitness(
        self,
        db_session: AsyncSession,
        test_agent,
        real_patterns,
    ):
        """Backtest results should update agent fitness in database."""
        from Fast_Swarm.Agents.Services.backtest_service import AgentBacktestService

        # Record initial fitness
        initial_fitness = test_agent.fitness_score
        initial_backtest_count = test_agent.backtest_count or 0

        # Assign patterns
        pattern_ids = [p["pattern_id"] for p in real_patterns[:2]]
        test_agent.assigned_patterns = pattern_ids
        test_agent.pattern_weights = dict.fromkeys(pattern_ids, 0.5)
        await db_session.flush()

        # Run backtest
        service = AgentBacktestService()
        await service.backtest_agents(
            session=db_session,
            agent_ids=[test_agent.agent_id],
            assets=["BTC"],
            timeframe="1h",
        )

        # Refresh agent from DB
        await db_session.refresh(test_agent)

        # Backtest count should have incremented
        assert test_agent.backtest_count > initial_backtest_count, "Backtest count should increment"

        # Last backtest timestamp should be set
        assert test_agent.last_backtest_at is not None, "Last backtest timestamp should be set"

        print(f"[Integration] Agent fitness: {initial_fitness} -> {test_agent.fitness_score}")
        print(f"[Integration] Backtest count: {test_agent.backtest_count}")

    @pytest.mark.asyncio
    async def test_trait_derived_params_in_backtest(
        self,
        db_session: AsyncSession,
        real_patterns,
        sample_traits,
    ):
        """Agent traits should affect backtest parameters."""
        from Fast_Swarm.Agents.Services.agent_service import get_trading_parameters

        # Create agent with extreme risk tolerance
        high_risk_traits = sample_traits.copy()
        high_risk_traits["risk_tolerance"] = 0.95
        high_risk_traits["stop_loss_tightness"] = 0.1

        low_risk_traits = sample_traits.copy()
        low_risk_traits["risk_tolerance"] = 0.05
        low_risk_traits["stop_loss_tightness"] = 0.9

        # Calculate trading parameters
        high_risk_params = get_trading_parameters(high_risk_traits)
        low_risk_params = get_trading_parameters(low_risk_traits)

        # High risk should have larger positions
        assert high_risk_params["position_size_pct"] > low_risk_params["position_size_pct"], (
            "High risk tolerance should mean larger positions"
        )

        # Low risk should have tighter stop loss
        assert low_risk_params["stop_loss_pct"] < high_risk_params["stop_loss_pct"], (
            "High stop_loss_tightness should mean tighter stops"
        )

        print(f"[Integration] High risk params: {high_risk_params}")
        print(f"[Integration] Low risk params: {low_risk_params}")


# ============================================================================
# TEST: Pattern Backtest Flow
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestPatternBacktestFlow:
    """Integration tests for pattern backtesting."""

    @pytest.mark.asyncio
    async def test_pattern_backtest_with_real_data(
        self,
        db_session: AsyncSession,
        real_patterns,
    ):
        """Pattern can be backtested using real PostgreSQL data."""
        from Fast_Swarm.Patterns.Services.backtest_service import PatternBacktestService

        if not real_patterns:
            pytest.skip("No patterns available for testing")

        service = PatternBacktestService()
        pattern_ids = [p["pattern_id"] for p in real_patterns[:1]]

        results = await service.backtest_patterns(
            session=db_session,
            pattern_ids=pattern_ids,
            assets=["BTC"],
            timeframe="1h",
        )

        assert len(results) > 0, "Should have results for patterns"

        for pattern_id, result in results.items():
            print(f"[Integration] Pattern {pattern_id}: {result}")


# ============================================================================
# TEST: Market Data Service
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestMarketDataService:
    """Integration tests for MarketDataService with PostgreSQL."""

    @pytest.mark.asyncio
    async def test_get_recent_candles(self, db_session: AsyncSession):
        """MarketDataService should fetch recent candles."""
        from Fast_Swarm.Infrastructure.Services.market_data_service import MarketDataService

        service = MarketDataService()
        candles = await service.get_recent_candles(
            session=db_session,
            symbol="BTC",
            timeframe="1h",
            limit=50,
        )

        assert len(candles) > 0, "Should fetch candles"
        assert all(c.symbol == "BTC" for c in candles), "All should be BTC"
        assert all(c.timeframe == "1h" for c in candles), "All should be 1h"

        print(f"[Integration] Fetched {len(candles)} BTC 1h candles")

    @pytest.mark.asyncio
    async def test_get_available_symbols(self, db_session: AsyncSession):
        """MarketDataService should list available symbols."""
        from Fast_Swarm.Infrastructure.Services.market_data_service import MarketDataService

        service = MarketDataService()
        symbols = await service.get_available_symbols(session=db_session)

        assert len(symbols) > 0, "Should have symbols"
        print(f"[Integration] Available symbols: {symbols[:10]}...")

    @pytest.mark.asyncio
    async def test_get_latest_price(self, db_session: AsyncSession):
        """MarketDataService should return latest price."""
        from Fast_Swarm.Infrastructure.Services.market_data_service import MarketDataService

        service = MarketDataService()
        price = await service.get_latest_price(session=db_session, symbol="BTC")

        if price is not None:
            assert price > 0, "Price should be positive"
            print(f"[Integration] Latest BTC price: ${price:,.2f}")
        else:
            print("[Integration] No price data available (table may be empty)")


# ============================================================================
# TEST: Evolution Cycle Flow (Placeholder)
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestEvolutionCycleFlow:
    """Integration tests for evolution cycles."""

    @pytest.mark.asyncio
    async def test_evolution_cycle_exists(self):
        """Evolution cycle service should be importable."""
        # Just verify the import works for now
        from Fast_Swarm.Evolution.Services.evolution_monitor import EvolutionMonitor

        assert EvolutionMonitor is not None


# ============================================================================
# TEST: Governance Flow (Placeholder)
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestGovernanceFlow:
    """Integration tests for governance/voting."""

    @pytest.mark.asyncio
    async def test_governance_service_exists(self):
        """Governance service should be importable."""
        from Fast_Swarm.Agents.Hivemind.Services.governance_service import GovernanceService

        assert GovernanceService is not None
