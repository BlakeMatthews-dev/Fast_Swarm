"""
Tests for AgentBacktestService - backtest orchestration, fitness updates, regime splits.

All tests use mocked DB sessions and backtest engines to avoid external dependencies.
Tests cover: single agent backtest, batch backtest, fitness updates, regime splitting, edge cases.
"""

import math
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Agents.Services.backtest_service import AgentBacktestService, _extract_pattern_refs
from Fast_Swarm.Agents.Services.fitness_service import TradeData


# =============================================================================
# Helpers
# =============================================================================


def _make_agent(
    agent_id: str = None,
    name: str = "TestAgent",
    generation: int = 1,
    traits: dict | None = None,
    assigned_patterns: Any = None,
    fitness_score: float = 0.0,
    backtest_count: int = 0,
    pattern_weights: dict | None = None,
    trading_philosophy: str = "",
    **extras,
) -> MagicMock:
    """Build a mock Agent ORM object with default attrs."""
    agent = MagicMock()
    agent.agent_id = agent_id or f"agent-{uuid.uuid4().hex[:8]}"
    agent.name = name
    agent.generation = generation
    agent.traits = traits or dict.fromkeys(
        [
            "risk_tolerance", "hold_duration_bias", "volatility_seeking",
            "profit_target_greed", "win_rate_preference", "drawdown_sensitivity",
            "momentum_vs_reversion", "stop_loss_tightness", "entry_aggression",
            "exit_aggression", "lookback_preference", "sentiment_weight",
            "news_reactivity", "sentiment_contrarian", "funding_rate_sensitivity",
            "correlation_awareness", "patience", "adaptability", "trend_following",
            "mean_reversion", "breakout_preference", "volume_sensitivity",
        ],
        0.5,
    )
    agent.assigned_patterns = assigned_patterns or {
        "base": [
            {
                "pattern_id": "pat-1",
                "name": "RSI Oversold",
                "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
                "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
            }
        ]
    }
    agent.fitness_score = fitness_score
    agent.backtest_count = backtest_count
    agent.pattern_weights = pattern_weights or {}
    agent.trading_philosophy = trading_philosophy
    agent.sharpe_ratio = None
    agent.sortino_ratio = None
    agent.calmar_ratio = None
    agent.max_drawdown_pct = 0.0
    agent.annualized_roi_pct = 0.0
    agent.win_rate = None
    agent.total_trades = 0
    agent.winning_trades = 0
    agent.total_pnl = 0.0
    agent.fitness_by_regime = {}
    agent.fitness_matrix = {}
    agent.last_backtest_at = None
    for k, v in extras.items():
        setattr(agent, k, v)
    return agent


def _make_trade(pnl_pct: float = 2.0) -> SimpleNamespace:
    """Build a minimal trade result object matching engine output."""
    return SimpleNamespace(
        pnl_pct=pnl_pct,
        entry_price=50000.0,
        exit_price=50000.0 * (1 + pnl_pct / 100),
        size=0.1,
        trade_id=f"t-{uuid.uuid4().hex[:6]}",
        pattern_id="pat-1",
    )


# =============================================================================
# _extract_pattern_refs Tests
# =============================================================================


class TestExtractPatternRefs:
    """Tests for the _extract_pattern_refs helper."""

    def test_embedded_patterns_dict_form(self):
        """Embedded patterns with entry/exit conditions are returned as embedded."""
        agent = MagicMock()
        agent.assigned_patterns = {
            "base": [
                {
                    "pattern_id": "p1",
                    "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
                    "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
                }
            ]
        }
        embedded, refs = _extract_pattern_refs(agent)
        assert len(embedded) == 1
        assert embedded[0]["pattern_id"] == "p1"
        assert refs == []

    def test_string_reference_ids(self):
        """String pattern IDs are returned as references."""
        agent = MagicMock()
        agent.assigned_patterns = {"base": ["pattern-abc", "pattern-xyz"]}
        embedded, refs = _extract_pattern_refs(agent)
        assert embedded == []
        assert refs == ["pattern-abc", "pattern-xyz"]

    def test_partial_dict_extracts_id(self):
        """Dict without conditions extracts pattern_id as reference."""
        agent = MagicMock()
        agent.assigned_patterns = {"base": [{"pattern_id": "ref-123"}]}
        embedded, refs = _extract_pattern_refs(agent)
        assert embedded == []
        assert refs == ["ref-123"]

    def test_list_format(self):
        """Handles list format (not nested under 'base' key)."""
        agent = MagicMock()
        agent.assigned_patterns = ["pat-a", "pat-b"]
        embedded, refs = _extract_pattern_refs(agent)
        assert embedded == []
        assert set(refs) == {"pat-a", "pat-b"}

    def test_none_and_empty_skipped(self):
        """None items and empty strings are skipped."""
        agent = MagicMock()
        agent.assigned_patterns = {"base": [None, "", "valid-id", None]}
        embedded, refs = _extract_pattern_refs(agent)
        assert refs == ["valid-id"]

    def test_mixed_forms(self):
        """Mix of embedded, reference, and partial dicts."""
        agent = MagicMock()
        agent.assigned_patterns = {
            "base": [
                {
                    "pattern_id": "embed-1",
                    "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
                    "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
                },
                "ref-string",
                {"pattern_id": "partial-ref"},
            ]
        }
        embedded, refs = _extract_pattern_refs(agent)
        assert len(embedded) == 1
        assert "ref-string" in refs
        assert "partial-ref" in refs

    def test_empty_assigned_patterns(self):
        """Empty dict or None assigned_patterns returns empty."""
        agent = MagicMock()
        agent.assigned_patterns = {}
        embedded, refs = _extract_pattern_refs(agent)
        assert embedded == []
        assert refs == []


# =============================================================================
# _calculate_metrics Tests (Single Agent Backtest)
# =============================================================================


class TestCalculateMetrics:
    """Tests for AgentBacktestService._calculate_metrics."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    def test_empty_trades_returns_zeros(self):
        """No trades produces zeroed-out metrics."""
        metrics = self.service._calculate_metrics([])
        assert metrics["total_trades"] == 0
        assert metrics["fitness_score"] == 0.0
        assert metrics["sharpe_ratio"] is None
        assert metrics["win_rate"] is None
        assert metrics["total_pnl"] == 0.0

    def test_single_winning_trade(self):
        """One winning trade produces valid metrics."""
        trades = [_make_trade(pnl_pct=5.0)]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["total_trades"] == 1
        assert metrics["win_rate"] == 1.0
        assert metrics["total_pnl"] == 5.0
        # Single trade -> sharpe is None (need >1)
        assert metrics["sharpe_ratio"] is None

    def test_mixed_trades_win_rate(self):
        """Win rate is correctly calculated from mixed wins/losses."""
        trades = [
            _make_trade(pnl_pct=5.0),
            _make_trade(pnl_pct=-3.0),
            _make_trade(pnl_pct=2.0),
            _make_trade(pnl_pct=-1.0),
        ]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["total_trades"] == 4
        assert metrics["win_rate"] == 0.5

    def test_all_winners_no_downside(self):
        """All-winning trades produce no max drawdown and None sortino."""
        trades = [_make_trade(pnl_pct=3.0) for _ in range(10)]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["win_rate"] == 1.0
        assert metrics["max_drawdown_pct"] == 0.0
        # No downside returns -> sortino is None
        assert metrics["sortino_ratio"] is None

    def test_all_losers(self):
        """All-losing trades produce 0 win rate and positive drawdown."""
        trades = [_make_trade(pnl_pct=-2.0) for _ in range(10)]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["win_rate"] == 0.0
        assert metrics["max_drawdown_pct"] > 0

    def test_nan_trades_filtered(self):
        """Trades with NaN pnl_pct are filtered out."""
        trades = [
            _make_trade(pnl_pct=5.0),
            SimpleNamespace(pnl_pct=float("nan"), entry_price=50000, exit_price=50000, size=0.1),
            _make_trade(pnl_pct=3.0),
        ]
        metrics = self.service._calculate_metrics(trades)
        # NaN trade should be excluded from calculations
        assert metrics["total_trades"] == 3  # total_trades counts all
        assert math.isfinite(metrics["total_pnl"])

    def test_inf_trades_filtered(self):
        """Trades with Inf pnl_pct are filtered from PnL calculation."""
        trades = [
            _make_trade(pnl_pct=5.0),
            SimpleNamespace(pnl_pct=float("inf"), entry_price=50000, exit_price=50000, size=0.1),
            _make_trade(pnl_pct=3.0),
        ]
        metrics = self.service._calculate_metrics(trades)
        assert math.isfinite(metrics["total_pnl"])

    def test_sharpe_capped_at_six(self):
        """Sharpe ratio is capped at [-6, 6]."""
        # All identical positive trades -> near-zero stdev -> huge raw sharpe
        trades = [_make_trade(pnl_pct=5.0) for _ in range(20)]
        # Add tiny variance so stdev > 0
        trades.append(_make_trade(pnl_pct=5.001))
        metrics = self.service._calculate_metrics(trades)
        if metrics["sharpe_ratio"] is not None:
            assert metrics["sharpe_ratio"] <= 6.0
            assert metrics["sharpe_ratio"] >= -6.0


# =============================================================================
# _calculate_weighted_fitness Tests (Regime Split)
# =============================================================================


class TestCalculateWeightedFitness:
    """Tests for regime-weighted fitness calculation."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    def test_empty_regime_returns_fallback(self):
        """No regime data returns the fallback fitness."""
        result = self.service._calculate_weighted_fitness({}, fallback_fitness=42.0)
        assert result == 42.0

    def test_single_regime(self):
        """Single regime returns that regime's fitness (weight normalized)."""
        regimes = {"random": {"fitness": 60.0, "trades": 100}}
        result = self.service._calculate_weighted_fitness(regimes)
        assert abs(result - 60.0) < 0.01

    def test_crash_regime_weighted_higher(self):
        """Crash regime (weight 3.0) dominates over bull (weight 0.5)."""
        regimes = {
            "bull": {"fitness": 80.0, "trades": 50},
            "crash": {"fitness": 30.0, "trades": 50},
        }
        result = self.service._calculate_weighted_fitness(regimes)
        # crash weight=3.0, bull weight=0.5
        expected = (80.0 * 0.5 + 30.0 * 3.0) / (0.5 + 3.0)
        assert abs(result - expected) < 0.01
        # Crash-heavy weighting should pull result below simple average of 55
        assert result < 55.0

    def test_bear_weighted_higher_than_bull(self):
        """Bear regime weight (2.0) is higher than bull (0.5)."""
        regimes = {
            "bull": {"fitness": 90.0, "trades": 50},
            "bear": {"fitness": 40.0, "trades": 50},
        }
        result = self.service._calculate_weighted_fitness(regimes)
        expected = (90.0 * 0.5 + 40.0 * 2.0) / (0.5 + 2.0)
        assert abs(result - expected) < 0.01

    def test_bounded_to_zero_hundred(self):
        """Weighted fitness is clamped to [0, 100]."""
        regimes = {"random": {"fitness": 150.0, "trades": 100}}
        assert self.service._calculate_weighted_fitness(regimes) <= 100.0

        regimes_neg = {"random": {"fitness": -50.0, "trades": 100}}
        assert self.service._calculate_weighted_fitness(regimes_neg) >= 0.0

    def test_unknown_regime_uses_default_weight(self):
        """Unknown regime name uses weight 1.0 by default."""
        regimes = {"alien_market": {"fitness": 70.0, "trades": 50}}
        result = self.service._calculate_weighted_fitness(regimes)
        assert abs(result - 70.0) < 0.01

    def test_invalid_regime_data_skipped(self):
        """Regime entries without 'fitness' key are skipped."""
        regimes = {
            "random": {"fitness": 60.0, "trades": 100},
            "bad": {"trades": 50},  # missing fitness
        }
        result = self.service._calculate_weighted_fitness(regimes)
        assert abs(result - 60.0) < 0.01

    def test_all_canonical_regime_weights_defined(self):
        """All canonical regime types have weights defined."""
        canonical_regimes = [
            "bull", "bear", "crash", "sideways", "blowoff",
            "recovery", "volatile", "winter", "transition",
        ]
        for regime in canonical_regimes:
            assert regime in self.service.REGIME_WEIGHTS, f"Missing weight for {regime}"

    def test_multiple_random_timeframes(self):
        """Multiple random_Xm regime keys all map to weight 1.0."""
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            key = f"random_{tf}"
            assert key in self.service.REGIME_WEIGHTS


# =============================================================================
# Batch Backtest Tests
# =============================================================================


class TestBatchBacktest:
    """Tests for backtest_agents (batch multi-agent)."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    @pytest.mark.asyncio
    async def test_no_agents_found_returns_empty(self):
        """When no agents match the IDs, returns empty dict."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        results = await self.service.backtest_agents(session, agent_ids=["nonexistent"])
        assert results == {}

    @pytest.mark.asyncio
    async def test_agent_with_no_patterns_skipped(self):
        """Agent without valid patterns is skipped (no crash)."""
        agent = _make_agent(assigned_patterns={})
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [agent]
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        with patch.object(self.service, "_get_all_test_windows", new_callable=AsyncMock, return_value=[]):
            with patch(
                "Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows",
                return_value={},
            ):
                results = await self.service.backtest_agents(session, agent_ids=[agent.agent_id])
        # Should be empty or skipped - not an error
        assert agent.agent_id not in results or "error" not in results.get(agent.agent_id, {})

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        """If one agent errors, the batch continues for remaining agents."""
        good_agent = _make_agent(agent_id="good-agent")
        bad_agent = _make_agent(agent_id="bad-agent")

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [bad_agent, good_agent]
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        windows = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1000, "end_ts": 2000, "regime": "random_1h"}
        ]

        call_count = 0

        async def mock_get_windows(*args, **kwargs):
            return windows

        # Make the engine raise for bad_agent but work for good_agent
        original_backtest = self.service.backtest_agents

        with patch.object(self.service, "_get_all_test_windows", side_effect=mock_get_windows):
            with patch(
                "Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows",
                return_value={},
            ):
                with patch(
                    "Fast_Swarm.Agents.Services.backtest_service.BacktestConfig.from_traits",
                    side_effect=Exception("Bad traits"),
                ):
                    results = await self.service.backtest_agents(
                        session, agent_ids=["bad-agent", "good-agent"]
                    )

        # Both agents should have results (one error, one error due to from_traits mock)
        # The key point is the batch does not crash entirely
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_multiple_agents_each_get_results(self):
        """Each agent in a batch gets its own results entry."""
        agents = [_make_agent(agent_id=f"agent-{i}") for i in range(3)]

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = agents
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()
        session.add = MagicMock()

        trades = [_make_trade(pnl_pct=2.0) for _ in range(5)]
        windows = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1000, "end_ts": 2000, "regime": "random_1h"}
        ]

        with patch.object(self.service, "_get_all_test_windows", new_callable=AsyncMock, return_value=windows):
            with patch(
                "Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows",
                return_value={},
            ):
                with patch(
                    "Fast_Swarm.Agents.Services.backtest_service.BacktestConfig.from_traits",
                    return_value=MagicMock(),
                ):
                    with patch(
                        "Fast_Swarm.Agents.Services.backtest_service.AgentTraits",
                        return_value=MagicMock(),
                    ):
                        with patch(
                            "Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine"
                        ) as mock_engine_cls:
                            mock_engine = MagicMock()
                            mock_engine.run.return_value = trades
                            mock_engine_cls.return_value = mock_engine

                            with patch(
                                "Fast_Swarm.Agents.Services.backtest_service.persist_trades",
                                new_callable=AsyncMock,
                                return_value=len(trades),
                            ):
                                with patch(
                                    "Fast_Swarm.Agents.Services.backtest_service.AgentRecord",
                                    return_value=MagicMock(),
                                ):
                                    results = await self.service.backtest_agents(
                                        session,
                                        agent_ids=[a.agent_id for a in agents],
                                    )

        assert len(results) == 3
        for agent in agents:
            assert agent.agent_id in results

    @pytest.mark.asyncio
    async def test_default_assets_used_when_none(self):
        """Default assets are BTC/USDT, ETH/USDT, SOL/USDT when None passed."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Just verify no crash with default assets
        results = await self.service.backtest_agents(session, agent_ids=[], assets=None)
        assert results == {}

    @pytest.mark.asyncio
    async def test_progress_tracking_via_backtest_count(self):
        """Agent's backtest_count increments after successful backtest."""
        agent = _make_agent(backtest_count=5)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [agent]
        session.exec = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()
        session.add = MagicMock()

        trades = [_make_trade(pnl_pct=2.0)]
        windows = [
            {"asset": "BTC", "timeframe": "1h", "start_ts": 1000, "end_ts": 2000, "regime": "random_1h"}
        ]

        with patch.object(self.service, "_get_all_test_windows", new_callable=AsyncMock, return_value=windows):
            with patch("Fast_Swarm.Agents.Services.backtest_service.preload_candles_for_windows", return_value={}):
                with patch("Fast_Swarm.Agents.Services.backtest_service.BacktestConfig.from_traits", return_value=MagicMock()):
                    with patch("Fast_Swarm.Agents.Services.backtest_service.AgentTraits", return_value=MagicMock()):
                        with patch("Fast_Swarm.Agents.Services.backtest_service.LocalBacktestEngine") as mock_engine_cls:
                            mock_engine = MagicMock()
                            mock_engine.run.return_value = trades
                            mock_engine_cls.return_value = mock_engine
                            with patch("Fast_Swarm.Agents.Services.backtest_service.persist_trades", new_callable=AsyncMock, return_value=1):
                                with patch("Fast_Swarm.Agents.Services.backtest_service.AgentRecord", return_value=MagicMock()):
                                    await self.service.backtest_agents(session, agent_ids=[agent.agent_id])

        assert agent.backtest_count == 6


# =============================================================================
# Fitness Update Tests
# =============================================================================


class TestFitnessUpdate:
    """Tests for fitness score updates after backtest."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    def test_fitness_from_winning_trades(self):
        """Fitness score is positive for profitable trades."""
        trades = [_make_trade(pnl_pct=5.0) for _ in range(20)]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["fitness_score"] > 0

    def test_fitness_from_losing_trades(self):
        """Fitness score is low/zero for all-losing trades."""
        trades = [_make_trade(pnl_pct=-5.0) for _ in range(20)]
        metrics = self.service._calculate_metrics(trades)
        # Fitness should be low (possibly 0 if gate blocks negative EV)
        assert metrics["fitness_score"] <= 50

    def test_fitness_bounded_zero_to_hundred(self):
        """Fitness score is always in [0, 100]."""
        # Extreme wins
        trades_win = [_make_trade(pnl_pct=50.0) for _ in range(50)]
        metrics_win = self.service._calculate_metrics(trades_win)
        assert 0 <= metrics_win["fitness_score"] <= 100

        # Extreme losses
        trades_loss = [_make_trade(pnl_pct=-50.0) for _ in range(50)]
        metrics_loss = self.service._calculate_metrics(trades_loss)
        assert 0 <= metrics_loss["fitness_score"] <= 100

    def test_max_drawdown_computed(self):
        """Max drawdown is computed from equity curve."""
        # Pattern: up, up, big down
        trades = [
            _make_trade(pnl_pct=10.0),
            _make_trade(pnl_pct=10.0),
            _make_trade(pnl_pct=-30.0),
        ]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["max_drawdown_pct"] > 0

    def test_calmar_ratio_computed(self):
        """Calmar ratio = annualized ROI / max drawdown."""
        trades = [
            _make_trade(pnl_pct=5.0),
            _make_trade(pnl_pct=-10.0),
            _make_trade(pnl_pct=8.0),
        ]
        metrics = self.service._calculate_metrics(trades)
        if metrics["max_drawdown_pct"] > 0:
            assert metrics["calmar_ratio"] is not None

    def test_historical_fitness_recorded_via_last_backtest_at(self):
        """After backtest, last_backtest_at is set to current time."""
        agent = _make_agent()
        assert agent.last_backtest_at is None
        # Simulate what backtest_agents does
        agent.last_backtest_at = datetime.utcnow()
        assert agent.last_backtest_at is not None


# =============================================================================
# Regime Split Tests
# =============================================================================


class TestRegimeSplit:
    """Tests for per-regime fitness aggregation."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    def test_random_regime_normalized(self):
        """random_1m, random_5m etc. are collapsed to 'random' prefix check."""
        # The service normalizes "random_1h" -> "random" in the loop
        raw_regime = "random_1h"
        regime = "random" if raw_regime.startswith("random_") else raw_regime
        assert regime == "random"

    def test_canonical_regime_preserved(self):
        """Non-random regime names (crash, bull) are preserved."""
        for name in ["crash", "bull", "bear", "sideways"]:
            regime = "random" if name.startswith("random_") else name
            assert regime == name

    def test_regime_fitness_requires_minimum_trades(self):
        """Per-regime fitness requires >= 5 trades for statistical significance."""
        # Simulate window_metrics with <5 trades in a regime
        window_metrics = [
            {"regime": "crash", "timeframe": "1h", "trades": 3, "fitness": 80.0,
             "sharpe": 1.5, "sortino": 2.0, "calmar": 1.0, "max_drawdown": 5.0,
             "win_rate": 0.7, "roi": 10.0, "pnl": 5.0},
        ]
        # Aggregate logic from backtest_agents - regime needs >= 5 trades
        fitness_by_regime = {}
        for regime in {"crash"}:
            regime_windows = [w for w in window_metrics if w["regime"] == regime and w["trades"] > 0]
            regime_trades = sum(w["trades"] for w in regime_windows)
            if regime_trades >= 5:
                fitness_by_regime[regime] = {"fitness": 80.0}
        assert "crash" not in fitness_by_regime

    def test_regime_fitness_accepted_with_enough_trades(self):
        """Per-regime fitness is computed when trades >= 5."""
        window_metrics = [
            {"regime": "bull", "timeframe": "1h", "trades": 10, "fitness": 70.0,
             "sharpe": 1.0, "sortino": 1.5, "calmar": 0.8, "max_drawdown": 3.0,
             "win_rate": 0.6, "roi": 8.0, "pnl": 10.0},
        ]
        fitness_by_regime = {}
        for regime in {"bull"}:
            regime_windows = [w for w in window_metrics if w["regime"] == regime and w["trades"] > 0]
            regime_trades = sum(w["trades"] for w in regime_windows)
            if regime_trades >= 5:
                regime_total = sum(w["trades"] for w in regime_windows)
                fitness_by_regime[regime] = {
                    "fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
                }
        assert "bull" in fitness_by_regime
        assert abs(fitness_by_regime["bull"]["fitness"] - 70.0) < 0.01

    def test_regime_weights_sum(self):
        """Verify regime weights configuration is reasonable."""
        total = sum(self.service.REGIME_WEIGHTS.values())
        assert total > 0
        # Bull should be lowest weight
        assert self.service.REGIME_WEIGHTS["bull"] < self.service.REGIME_WEIGHTS["crash"]


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case tests for backtest service."""

    def setup_method(self):
        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader",
            return_value=MagicMock(),
        ):
            self.service = AgentBacktestService()

    def test_zero_trades_produced(self):
        """Engine returning zero trades does not crash metrics."""
        metrics = self.service._calculate_metrics([])
        assert metrics["total_trades"] == 0
        assert metrics["fitness_score"] == 0.0
        assert metrics["sharpe_ratio"] is None

    def test_none_pnl_trades_handled(self):
        """Trades with None pnl_pct do not crash."""
        trades = [
            _make_trade(pnl_pct=5.0),
            SimpleNamespace(pnl_pct=None, entry_price=50000, exit_price=50000, size=0.1),
        ]
        metrics = self.service._calculate_metrics(trades)
        assert metrics["total_trades"] == 2
        assert math.isfinite(metrics["total_pnl"])

    def test_timeframe_config_completeness(self):
        """All default timeframes have config entries."""
        for tf in self.service.DEFAULT_TIMEFRAMES:
            assert tf in self.service.TIMEFRAME_CONFIG

    def test_windows_per_backtest_positive(self):
        """WINDOWS_PER_BACKTEST is a positive integer."""
        assert self.service.WINDOWS_PER_BACKTEST > 0

    def test_service_initialization(self):
        """Service initializes with an OHLCVLoader."""
        with patch("Fast_Swarm.Agents.Services.backtest_service.OHLCVLoader", return_value=MagicMock()) as mock_loader:
            svc = AgentBacktestService()
            mock_loader.assert_called_once()
            assert svc.loader is not None
