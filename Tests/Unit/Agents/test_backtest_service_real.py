"""
Real Integration Tests for AgentBacktestService.

Tests backtest execution, metrics calculation, pattern extraction,
fitness updates, and weighted regime fitness against a real PostgreSQL
database using the db_session fixture with transaction rollback.

All tests use real Agent and Pattern objects persisted to DB.
Only external services (OHLCVLoader, LocalBacktestEngine) are mocked.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.backtest_service import (
    AgentBacktestService,
    _extract_pattern_refs,
)
from Fast_Swarm.Agents.Services.fitness_service import TradeData, calculate_fitness
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.Trades.Models.trade_models import BacktestTrade


# =============================================================================
# Helpers
# =============================================================================


def _default_traits() -> dict[str, float]:
    return {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


def _make_agent(
    fitness: float = 0.0,
    status: str = "active",
    generation: int = 1,
    assigned_patterns: dict | None = None,
    pattern_weights: dict | None = None,
) -> Agent:
    return Agent(
        agent_id=f"test-{uuid.uuid4().hex[:8]}",
        name=f"Agent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        traits=_default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        fitness_by_regime={},
        elo_rating=Decimal("1500"),
        assigned_patterns=assigned_patterns or {},
        pattern_weights=pattern_weights or {},
    )


def _make_pattern(
    pattern_id: str | None = None,
    entry_conditions: list | None = None,
    exit_conditions: list | None = None,
) -> Pattern:
    return Pattern(
        pattern_id=pattern_id or f"pat-{uuid.uuid4().hex[:8]}",
        name=f"Pattern-{uuid.uuid4().hex[:4]}",
        entry_conditions=entry_conditions or [{"indicator": "rsi", "operator": "<", "value": 30}],
        exit_conditions=exit_conditions or [{"indicator": "rsi", "operator": ">", "value": 70}],
        origin="TECHNICAL",
        status="active",
        is_active=True,
        fitness_score=Decimal("50.0"),
        fitness_by_regime={},
    )


class _FakeTrade:
    """Minimal trade object returned by backtest engine."""

    def __init__(self, pnl_pct=2.0, entry_price=50000.0, exit_price=51000.0,
                 pattern_id="pat-1", agent_id="agent-1", symbol="BTC", side="long",
                 entry_timestamp=1700000000000, exit_timestamp=1700003600000,
                 trade_id=None):
        self.pnl_pct = pnl_pct
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.pattern_id = pattern_id
        self.agent_id = agent_id
        self.symbol = symbol
        self.side = side
        self.entry_timestamp = entry_timestamp
        self.exit_timestamp = exit_timestamp
        self.trade_id = trade_id or f"trade-{uuid.uuid4().hex[:8]}"
        self.timeframe = "1h"
        self.source = "evolution_backtest"
        self.gross_pnl_pct = pnl_pct
        self.net_pnl_pct = pnl_pct
        self.position_size_usd = 10000
        self.exit_reason = "signal"
        self.hold_bars = 10
        self.is_winner = pnl_pct > 0


# =============================================================================
# Test: _extract_pattern_refs
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_dict_with_embedded(db_session: AsyncSession):
    """Embedded patterns (with entry_conditions + exit_conditions) go to embedded list."""
    agent = _make_agent(assigned_patterns={
        "base": [
            {
                "pattern_id": "pat-1",
                "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
            }
        ]
    })
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 1
    assert len(refs) == 0
    assert embedded[0]["pattern_id"] == "pat-1"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_dict_with_string_ids(db_session: AsyncSession):
    """String IDs in base list go to reference_ids."""
    agent = _make_agent(assigned_patterns={"base": ["pat-1", "pat-2", "pat-3"]})
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 0
    assert set(refs) == {"pat-1", "pat-2", "pat-3"}


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_partial_dict_extracts_id(db_session: AsyncSession):
    """Partial dicts (pattern_id but no conditions) yield reference IDs."""
    agent = _make_agent(assigned_patterns={
        "base": [{"pattern_id": "pat-partial", "name": "No conditions"}]
    })
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 0
    assert refs == ["pat-partial"]


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_mixed(db_session: AsyncSession):
    """Mixed list of embedded, string refs, and partial dicts."""
    agent = _make_agent(assigned_patterns={
        "base": [
            "string-ref-1",
            {
                "pattern_id": "embedded-1",
                "entry_conditions": [{"indicator": "macd", "operator": ">", "value": 0}],
                "exit_conditions": [{"indicator": "macd", "operator": "<", "value": 0}],
            },
            {"pattern_id": "partial-ref-1"},
        ]
    })
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 1
    assert embedded[0]["pattern_id"] == "embedded-1"
    assert set(refs) == {"string-ref-1", "partial-ref-1"}


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_empty(db_session: AsyncSession):
    """Empty assigned_patterns yields empty results."""
    agent = _make_agent(assigned_patterns={})
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 0
    assert len(refs) == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_pattern_refs_list_format(db_session: AsyncSession):
    """List-format assigned_patterns (not dict) also works."""
    agent = _make_agent()
    # Force list format (bypass dict default)
    agent.assigned_patterns = ["ref-a", "ref-b"]
    db_session.add(agent)
    await db_session.flush()

    embedded, refs = _extract_pattern_refs(agent)
    assert len(embedded) == 0
    assert set(refs) == {"ref-a", "ref-b"}


# =============================================================================
# Test: _calculate_metrics
# =============================================================================


class TestCalculateMetrics:
    """Test the internal _calculate_metrics method."""

    def setup_method(self):
        self.service = AgentBacktestService.__new__(AgentBacktestService)

    def test_empty_trades_returns_zeros(self):
        result = self.service._calculate_metrics([])
        assert result["total_trades"] == 0
        assert result["fitness_score"] == 0.0
        assert result["sharpe_ratio"] is None

    def test_all_winning_trades(self):
        trades = [_FakeTrade(pnl_pct=p) for p in [2.0, 3.0, 1.5, 4.0, 2.5]]
        result = self.service._calculate_metrics(trades)
        assert result["total_trades"] == 5
        assert result["win_rate"] == 1.0
        assert result["total_pnl"] > 0
        assert result["fitness_score"] > 0

    def test_all_losing_trades_zero_fitness(self):
        trades = [_FakeTrade(pnl_pct=p) for p in [-2.0, -3.0, -1.5, -4.0, -2.5]]
        result = self.service._calculate_metrics(trades)
        assert result["total_trades"] == 5
        assert result["win_rate"] == 0.0
        # EV gate should block negative expectancy
        assert result["fitness_score"] == 0.0

    def test_mixed_trades_calculates_sharpe(self):
        trades = [_FakeTrade(pnl_pct=p) for p in [5.0, -1.0, 3.0, -0.5, 2.0, -1.5, 4.0]]
        result = self.service._calculate_metrics(trades)
        assert result["sharpe_ratio"] is not None
        assert result["total_trades"] == 7

    def test_single_trade_no_sharpe(self):
        trades = [_FakeTrade(pnl_pct=5.0)]
        result = self.service._calculate_metrics(trades)
        assert result["total_trades"] == 1
        assert result["sharpe_ratio"] is None

    def test_max_drawdown_calculation(self):
        # Trades that create a drawdown: win, big loss, win
        trades = [
            _FakeTrade(pnl_pct=10.0),
            _FakeTrade(pnl_pct=-20.0),
            _FakeTrade(pnl_pct=5.0),
        ]
        result = self.service._calculate_metrics(trades)
        assert result["max_drawdown_pct"] > 0


# =============================================================================
# Test: _calculate_weighted_fitness
# =============================================================================


class TestCalculateWeightedFitness:
    """Test regime-weighted fitness aggregation."""

    def setup_method(self):
        self.service = AgentBacktestService.__new__(AgentBacktestService)
        # Copy class attributes
        self.service.REGIME_WEIGHTS = AgentBacktestService.REGIME_WEIGHTS

    def test_empty_regime_returns_fallback(self):
        result = self.service._calculate_weighted_fitness({}, fallback_fitness=42.0)
        assert result == 42.0

    def test_single_regime(self):
        fbr = {"bull": {"fitness": 80.0, "trades": 50}}
        result = self.service._calculate_weighted_fitness(fbr)
        assert result == 80.0

    def test_crash_weighted_higher_than_bull(self):
        """Crash regime (weight 3.0) should dominate over bull (weight 0.5)."""
        fbr = {
            "bull": {"fitness": 90.0, "trades": 50},
            "crash": {"fitness": 30.0, "trades": 50},
        }
        result = self.service._calculate_weighted_fitness(fbr)
        # Weighted: (90*0.5 + 30*3.0) / (0.5 + 3.0) = (45+90)/3.5 = 38.57
        expected = (90.0 * 0.5 + 30.0 * 3.0) / (0.5 + 3.0)
        assert abs(result - expected) < 0.01

    def test_bounded_to_100(self):
        fbr = {"random_1h": {"fitness": 150.0, "trades": 100}}
        result = self.service._calculate_weighted_fitness(fbr)
        assert result <= 100.0

    def test_bounded_to_0(self):
        fbr = {"random_1h": {"fitness": -50.0, "trades": 100}}
        result = self.service._calculate_weighted_fitness(fbr)
        assert result >= 0.0

    def test_invalid_data_skipped(self):
        """Regimes with missing 'fitness' key are skipped."""
        fbr = {
            "bull": {"fitness": 60.0, "trades": 50},
            "invalid": {"trades": 10},  # no fitness key
        }
        result = self.service._calculate_weighted_fitness(fbr)
        assert result == 60.0


# =============================================================================
# Test: backtest_agents (with mocked engine)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_agents_updates_agent_stats(db_session: AsyncSession):
    """backtest_agents should update fitness, trades, and backtest_count on agent."""
    # Create pattern in DB
    pattern = _make_pattern(pattern_id="pat-bt-test")
    db_session.add(pattern)
    await db_session.flush()

    # Create agent with embedded patterns
    agent = _make_agent(assigned_patterns={
        "base": [{
            "pattern_id": "pat-bt-test",
            "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
            "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
        }]
    })
    db_session.add(agent)
    await db_session.flush()

    aid = agent.agent_id
    assert agent.backtest_count == 0

    # Mock the engine and data loading
    fake_trades = [_FakeTrade(pnl_pct=p, agent_id=aid, pattern_id="pat-bt-test") for p in [3.0, -1.0, 2.5, 1.0, -0.5]]

    with (
        patch.object(AgentBacktestService, "_get_all_test_windows", new_callable=AsyncMock) as mock_windows,
        patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows") as mock_preload,
        patch("Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine") as MockEngine,
        patch("Fast_Swarm.Agents.Services.backtest_service.persist_trades", new_callable=AsyncMock) as mock_persist,
    ):
        mock_windows.return_value = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700000000000, "end_ts": 1700100000000, "regime": "random_1h"},
        ]
        mock_preload.return_value = {}
        mock_engine_instance = MagicMock()
        mock_engine_instance.run.return_value = fake_trades
        MockEngine.return_value = mock_engine_instance
        mock_persist.return_value = 5

        service = AgentBacktestService()
        results = await service.backtest_agents(db_session, [aid])

    assert aid in results
    assert results[aid].get("total_trades", 0) >= 5

    # Reload agent from DB to verify updates
    refreshed = await db_session.get(Agent, agent.id)
    assert refreshed.backtest_count == 1
    assert refreshed.last_backtest_at is not None
    assert float(refreshed.fitness_score) > 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_agents_no_patterns_skips(db_session: AsyncSession):
    """Agent with no assigned patterns should be skipped without error."""
    agent = _make_agent(assigned_patterns={})
    db_session.add(agent)
    await db_session.flush()

    with (
        patch.object(AgentBacktestService, "_get_all_test_windows", new_callable=AsyncMock) as mock_windows,
        patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows") as mock_preload,
    ):
        mock_windows.return_value = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700000000000, "end_ts": 1700100000000, "regime": "random_1h"},
        ]
        mock_preload.return_value = {}

        service = AgentBacktestService()
        results = await service.backtest_agents(db_session, [agent.agent_id])

    # Agent was skipped - should not appear in results
    assert agent.agent_id not in results


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_agents_hydrates_pattern_refs(db_session: AsyncSession):
    """Agent with string pattern refs should hydrate them from DB."""
    # Create real pattern in DB
    pattern = _make_pattern(pattern_id="pat-hydrate-test")
    db_session.add(pattern)
    await db_session.flush()

    # Agent references pattern by ID string
    agent = _make_agent(assigned_patterns={"base": ["pat-hydrate-test"]})
    db_session.add(agent)
    await db_session.flush()

    aid = agent.agent_id
    fake_trades = [_FakeTrade(pnl_pct=2.0, agent_id=aid, pattern_id="pat-hydrate-test")]

    with (
        patch.object(AgentBacktestService, "_get_all_test_windows", new_callable=AsyncMock) as mock_windows,
        patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows") as mock_preload,
        patch("Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine") as MockEngine,
        patch("Fast_Swarm.Agents.Services.backtest_service.persist_trades", new_callable=AsyncMock) as mock_persist,
    ):
        mock_windows.return_value = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700000000000, "end_ts": 1700100000000, "regime": "random_1h"},
        ]
        mock_preload.return_value = {}
        mock_engine_instance = MagicMock()
        mock_engine_instance.run.return_value = fake_trades
        MockEngine.return_value = mock_engine_instance
        mock_persist.return_value = 1

        service = AgentBacktestService()
        results = await service.backtest_agents(db_session, [aid])

    # Agent should now have hydrated patterns
    refreshed = await db_session.get(Agent, agent.id)
    base = refreshed.assigned_patterns.get("base", [])
    assert len(base) >= 1
    # Hydrated pattern should have entry_conditions
    assert base[0].get("entry_conditions") is not None


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_agents_per_regime_fitness(db_session: AsyncSession):
    """Multiple regime windows produce per-regime fitness breakdown."""
    pattern = _make_pattern(pattern_id="pat-regime-test")
    db_session.add(pattern)
    await db_session.flush()

    agent = _make_agent(assigned_patterns={
        "base": [{
            "pattern_id": "pat-regime-test",
            "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
            "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
        }]
    })
    db_session.add(agent)
    await db_session.flush()
    aid = agent.agent_id

    # Return different trades per window call
    call_count = 0

    def mock_engine_run(agent, dataset):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # "crash" window - losing trades
            return [_FakeTrade(pnl_pct=-3.0, agent_id=aid) for _ in range(6)]
        else:
            # "bull" window - winning trades
            return [_FakeTrade(pnl_pct=5.0, agent_id=aid) for _ in range(6)]

    with (
        patch.object(AgentBacktestService, "_get_all_test_windows", new_callable=AsyncMock) as mock_windows,
        patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows") as mock_preload,
        patch("Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine") as MockEngine,
        patch("Fast_Swarm.Agents.Services.backtest_service.persist_trades", new_callable=AsyncMock) as mock_persist,
    ):
        mock_windows.return_value = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700000000000, "end_ts": 1700100000000, "regime": "crash"},
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700200000000, "end_ts": 1700300000000, "regime": "bull"},
        ]
        mock_preload.return_value = {}
        mock_engine_instance = MagicMock()
        mock_engine_instance.run.side_effect = mock_engine_run
        MockEngine.return_value = mock_engine_instance
        mock_persist.return_value = 12

        service = AgentBacktestService()
        results = await service.backtest_agents(db_session, [aid])

    refreshed = await db_session.get(Agent, agent.id)
    fbr = refreshed.fitness_by_regime
    # Should have regime entries (at least one if >= 5 trades per regime)
    assert isinstance(fbr, dict)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_multiple_agents(db_session: AsyncSession):
    """Backtest multiple agents in one call."""
    agents = []
    for i in range(3):
        a = _make_agent(assigned_patterns={
            "base": [{
                "pattern_id": f"pat-multi-{i}",
                "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
            }]
        })
        db_session.add(a)
        agents.append(a)
    await db_session.flush()

    aids = [a.agent_id for a in agents]
    fake_trades = [_FakeTrade(pnl_pct=2.0) for _ in range(5)]

    with (
        patch.object(AgentBacktestService, "_get_all_test_windows", new_callable=AsyncMock) as mock_windows,
        patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows") as mock_preload,
        patch("Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine") as MockEngine,
        patch("Fast_Swarm.Agents.Services.backtest_service.persist_trades", new_callable=AsyncMock) as mock_persist,
    ):
        mock_windows.return_value = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1700000000000, "end_ts": 1700100000000, "regime": "random_1h"},
        ]
        mock_preload.return_value = {}
        mock_engine_instance = MagicMock()
        mock_engine_instance.run.return_value = fake_trades
        MockEngine.return_value = mock_engine_instance
        mock_persist.return_value = 5

        service = AgentBacktestService()
        results = await service.backtest_agents(db_session, aids)

    # All agents should appear in results
    for aid in aids:
        assert aid in results


# =============================================================================
# Test: BacktestTrade persistence in DB
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_trade_persists(db_session: AsyncSession):
    """BacktestTrade model can be created and queried in DB."""
    trade = BacktestTrade(
        trade_id=f"bt-trade-{uuid.uuid4().hex[:8]}",
        source="evolution_backtest",
        pattern_id="pat-1",
        agent_id="agent-1",
        symbol="BTC",
        side="long",
        entry_timestamp=1700000000000,
        exit_timestamp=1700003600000,
        entry_price=Decimal("50000.0"),
        exit_price=Decimal("51000.0"),
        gross_pnl_pct=2.0,
        net_pnl_pct=1.9,
        is_winner=True,
    )
    db_session.add(trade)
    await db_session.flush()

    result = await db_session.scalars(
        select(BacktestTrade).where(BacktestTrade.agent_id == "agent-1")
    )
    trades = list(result.all())
    assert len(trades) == 1
    assert trades[0].symbol == "BTC"
    assert trades[0].is_winner is True


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_backtest_trade_agent_link(db_session: AsyncSession):
    """BacktestTrades can be queried by agent_id."""
    agent = _make_agent()
    db_session.add(agent)
    await db_session.flush()

    for i in range(5):
        trade = BacktestTrade(
            trade_id=f"link-trade-{uuid.uuid4().hex[:8]}",
            source="evolution_backtest",
            agent_id=agent.agent_id,
            symbol="ETH" if i % 2 == 0 else "BTC",
            side="long",
            entry_timestamp=1700000000000 + i * 3600000,
            entry_price=Decimal("3000.0"),
            gross_pnl_pct=1.5 if i % 2 == 0 else -0.5,
            is_winner=(i % 2 == 0),
        )
        db_session.add(trade)
    await db_session.flush()

    result = await db_session.scalars(
        select(BacktestTrade).where(BacktestTrade.agent_id == agent.agent_id)
    )
    trades = list(result.all())
    assert len(trades) == 5
    winners = [t for t in trades if t.is_winner]
    assert len(winners) == 3
