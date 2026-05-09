"""
Unit Tests for CrucibleTestService.

Tests the Crucible mass walk-forward validation service:
- run_crucible_test lifecycle (status transitions, error handling)
- _calculate_crucible_metrics (fitness formula, regime scores, clamping)
- Wisdom generation integration (success/failure/storage)

All tests are async and fully mocked -- no real DB or backtest engine needed.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from Fast_Swarm.System.Services.crucible_test_service import CrucibleTestService


# ============================================================================
# Helpers
# ============================================================================


def _make_entry(
    entry_id=1,
    status="pending",
    agent_id="agent-abc",
    traits=None,
    assigned_patterns=None,
    pattern_weights=None,
    level_at_entry=3,
):
    """Build a mock CrucibleEntry with sensible defaults."""
    entry = MagicMock()
    entry.id = entry_id
    entry.status = status
    entry.agent_id = agent_id
    entry.traits = traits or {"risk_tolerance": 0.5}
    entry.assigned_patterns = assigned_patterns or ["pat-1", "pat-2"]
    entry.pattern_weights = pattern_weights or {"pat-1": 0.6, "pat-2": 0.4}
    entry.level_at_entry = level_at_entry
    entry.starting_balance = Decimal("50000.0")
    entry.current_balance = Decimal("50000.0")
    entry.overall_fitness = Decimal("0")
    entry.regime_scores = {}
    entry.started_at = None
    entry.completed_at = None
    entry.created_at = datetime.utcnow()
    return entry


def _make_trade(trade_id="t1", regime="bull", pnl_pct=2.0):
    """Build a lightweight mock trade object."""
    return SimpleNamespace(trade_id=trade_id, regime=regime, pnl_pct=pnl_pct)


def _make_pattern(pattern_id="pat-1"):
    """Build a mock Pattern row."""
    p = MagicMock()
    p.pattern_id = pattern_id
    p.entry_conditions = [{"indicator": "rsi", "operator": "<", "value": 30}]
    p.exit_conditions = [{"indicator": "rsi", "operator": ">", "value": 70}]
    p.fitness_score = 50.0
    return p


def _mock_session_with_entry(entry):
    """
    Return an AsyncMock session whose .exec() yields the given entry
    on the first call (CrucibleEntry lookup) and pattern rows on the second.
    """
    session = AsyncMock()

    # First exec -> CrucibleEntry query, second exec -> Pattern query
    entry_result = MagicMock()
    entry_result.first.return_value = entry

    pattern_result = MagicMock()
    pattern_result.all.return_value = [
        _make_pattern(pid) for pid in (entry.assigned_patterns if entry else [])
    ]

    session.exec = AsyncMock(side_effect=[entry_result, pattern_result])
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _mock_session_not_found():
    """Return a session whose first query returns None (entry not found)."""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    session.exec = AsyncMock(return_value=result)
    return session


# ============================================================================
# TestRunCrucibleTest
# ============================================================================


class TestRunCrucibleTest:
    """Tests for CrucibleTestService.run_crucible_test."""

    @pytest.mark.asyncio
    async def test_not_found_raises_value_error(self):
        """Nonexistent entry_id raises ValueError."""
        service = CrucibleTestService()
        session = _mock_session_not_found()

        with pytest.raises(ValueError, match="not found"):
            await service.run_crucible_test(session, entry_id=999)

    @pytest.mark.asyncio
    async def test_non_pending_early_return(self):
        """Entry with status != 'pending' returns early without running."""
        for status in ("running", "completed", "failed"):
            entry = _make_entry(status=status)
            session = AsyncMock()
            result_mock = MagicMock()
            result_mock.first.return_value = entry
            session.exec = AsyncMock(return_value=result_mock)

            service = CrucibleTestService()
            result = await service.run_crucible_test(session, entry_id=1)

            assert result["status"] == status
            assert "already started" in result["message"].lower() or "completed" in result["message"].lower()
            # commit should NOT have been called (no state change)
            session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.5,
            "win_rate": 60,
            "total_roi_pct": 10.0,
            "max_drawdown_pct": 5.0,
        },
    )
    async def test_status_running_then_completed(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """Status transitions from pending -> running -> completed."""
        entry = _make_entry(status="pending")
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        trades = [_make_trade("t1", "bull"), _make_trade("t2", "bear")]
        engine.run.return_value = trades
        mock_engine_factory.return_value = engine

        service = CrucibleTestService()

        # Patch wisdom import to avoid real LLM call
        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=MagicMock(
                            generate_wisdom_from_entry=AsyncMock(return_value=None)
                        )
                    )
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        # After the run, status should be "completed"
        assert entry.status == "completed"
        assert entry.started_at is not None
        assert entry.completed_at is not None
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={},
    )
    async def test_empty_trades_fitness_zero(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """No trades produced -> fitness = 0."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.return_value = []  # no trades
        mock_engine_factory.return_value = engine

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=MagicMock(
                            generate_wisdom_from_entry=AsyncMock(return_value=None)
                        )
                    )
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        assert entry.overall_fitness == 0.0
        assert result["status"] == "completed"
        assert result["total_trades"] == 0

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={
            "bull": {"fitness": 72.0},
            "bear": {"fitness": 45.0},
            "chop": {"fitness": 30.0},
            "lowvol": {"fitness": 60.0},
        },
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 2.0,
            "win_rate": 65,
            "total_roi_pct": 15.0,
            "max_drawdown_pct": 8.0,
        },
    )
    async def test_successful_run(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """Full run produces valid metrics and completed status."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        trades = [_make_trade(f"t{i}", "bull") for i in range(5)]
        engine.run.return_value = trades
        mock_engine_factory.return_value = engine

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=MagicMock(
                            generate_wisdom_from_entry=AsyncMock(return_value=None)
                        )
                    )
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        assert result["status"] == "completed"
        assert result["total_trades"] == 5
        assert result["overall_fitness"] is not None
        assert entry.regime_scores is not None

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    async def test_failed_run_status(self, mock_engine_factory):
        """Exception during backtest sets status to 'failed'."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        # Make engine.run raise
        engine = MagicMock()
        engine.run.side_effect = RuntimeError("backtest engine crashed")
        mock_engine_factory.return_value = engine

        service = CrucibleTestService()
        result = await service.run_crucible_test(session, entry_id=1)

        assert result["status"] == "failed"
        assert "backtest engine crashed" in result["error"]
        assert entry.status == "failed"

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.0,
            "win_rate": 55,
            "total_roi_pct": 5.0,
            "max_drawdown_pct": 3.0,
        },
    )
    async def test_assets_parameter(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """Custom assets list is forwarded to the backtest engine."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.return_value = [_make_trade()]
        mock_engine_factory.return_value = engine

        custom_assets = ["BTC", "ETH", "DOGE"]
        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=MagicMock(
                            generate_wisdom_from_entry=AsyncMock(return_value=None)
                        )
                    )
                )
            },
        ):
            await service.run_crucible_test(session, entry_id=1, assets=custom_assets)

        # Verify engine was called with our custom assets
        call_kwargs = engine.run.call_args
        dataset = call_kwargs[1]["dataset"] if "dataset" in (call_kwargs[1] or {}) else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs.get("dataset")
        assert dataset["assets"] == custom_assets

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.0,
            "win_rate": 55,
            "total_roi_pct": 5.0,
            "max_drawdown_pct": 3.0,
        },
    )
    async def test_default_10_assets(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """No assets param -> 10 default assets used."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.return_value = [_make_trade()]
        mock_engine_factory.return_value = engine

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=MagicMock(
                            generate_wisdom_from_entry=AsyncMock(return_value=None)
                        )
                    )
                )
            },
        ):
            await service.run_crucible_test(session, entry_id=1, assets=None)

        call_kwargs = engine.run.call_args
        dataset = call_kwargs[1]["dataset"] if "dataset" in (call_kwargs[1] or {}) else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs.get("dataset")
        assert len(dataset["assets"]) == 10


# ============================================================================
# TestCrucibleMetrics
# ============================================================================


class TestCrucibleMetrics:
    """Tests for CrucibleTestService._calculate_crucible_metrics."""

    def _service(self):
        return CrucibleTestService()

    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 2.0,
            "win_rate": 60,
            "total_roi_pct": 20.0,
            "max_drawdown_pct": 5.0,
        },
    )
    def test_fitness_formula(self, mock_bt_metrics, mock_regime_metrics):
        """Fitness uses: (sharpe*10) + (win_rate*50) + (roi/100*20) - (max_dd/100*10)."""
        trades = [_make_trade("t1"), _make_trade("t2")]
        result = self._service()._calculate_crucible_metrics(trades)

        # Manual formula: (2.0*10) + (60*50) + (20/100*20) - (5/100*10)
        #               = 20 + 3000 + 4 - 0.5 = 3023.5
        # Clamped to [0, 100] -> 100.0
        expected = max(0.0, min(100.0, (2.0 * 10) + (60 * 50) + (20 / 100 * 20) - (5 / 100 * 10)))
        assert result["overall_fitness"] == expected

    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
    )
    def test_fitness_clamped_0_100(self, mock_bt_metrics, mock_regime_metrics):
        """Fitness is always clamped to [0, 100] regardless of input extremes."""
        service = self._service()

        # Test upper clamp: huge positive values
        mock_bt_metrics.return_value = {
            "sharpe_ratio": 100, "win_rate": 100,
            "total_roi_pct": 10000, "max_drawdown_pct": 0,
        }
        result_high = service._calculate_crucible_metrics([_make_trade()])
        assert result_high["overall_fitness"] <= 100.0

        # Test lower clamp: terrible values
        mock_bt_metrics.return_value = {
            "sharpe_ratio": -50, "win_rate": 0,
            "total_roi_pct": -500, "max_drawdown_pct": 100,
        }
        result_low = service._calculate_crucible_metrics([_make_trade()])
        assert result_low["overall_fitness"] >= 0.0

    def test_empty_trades_returns_zeros(self):
        """Empty trades list returns all-zero metrics without calling backtest."""
        result = self._service()._calculate_crucible_metrics([])

        assert result["overall_fitness"] == 0.0
        assert result["total_pnl_pct"] == 0.0
        assert result["regime_scores"] == {
            "bull": 0.0, "bear": 0.0, "chop": 0.0, "lowvol": 0.0
        }

    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={
            "bull": {"fitness": 80.0},
            "bear": {"fitness": 40.0},
            "chop": {"fitness": 25.0},
            "lowvol": {"fitness": 55.0},
        },
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.5, "win_rate": 55,
            "total_roi_pct": 12.0, "max_drawdown_pct": 7.0,
        },
    )
    def test_regime_scores_present(self, mock_bt_metrics, mock_regime_metrics):
        """Result contains bull/bear/chop/lowvol regime scores."""
        trades = [_make_trade("t1", "bull"), _make_trade("t2", "bear")]
        result = self._service()._calculate_crucible_metrics(trades)

        scores = result["regime_scores"]
        assert "bull" in scores
        assert "bear" in scores
        assert "chop" in scores
        assert "lowvol" in scores
        assert scores["bull"] == 80.0
        assert scores["bear"] == 40.0

    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.0, "win_rate": 50,
            "total_roi_pct": 8.5, "max_drawdown_pct": 4.0,
        },
    )
    def test_total_pnl_pct(self, mock_bt_metrics, mock_regime_metrics):
        """total_pnl_pct comes from metrics['total_roi_pct']."""
        result = self._service()._calculate_crucible_metrics([_make_trade()])
        assert result["total_pnl_pct"] == 8.5


# ============================================================================
# TestWisdomGeneration
# ============================================================================


class TestWisdomGeneration:
    """Tests for wisdom generation integration within run_crucible_test."""

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.5, "win_rate": 60,
            "total_roi_pct": 10.0, "max_drawdown_pct": 5.0,
        },
    )
    async def test_wisdom_generated_on_success(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """WisdomTransferService.generate_wisdom_from_entry called on completion."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.return_value = [_make_trade()]
        mock_engine_factory.return_value = engine

        mock_wisdom = MagicMock()
        mock_wisdom.id = 42
        mock_wisdom_service_instance = MagicMock()
        mock_wisdom_service_instance.generate_wisdom_from_entry = AsyncMock(
            return_value=mock_wisdom
        )

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=mock_wisdom_service_instance
                    )
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        mock_wisdom_service_instance.generate_wisdom_from_entry.assert_awaited_once()
        assert result["wisdom_id"] == 42

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    async def test_no_wisdom_on_failure(self, mock_engine_factory):
        """Wisdom is NOT generated when the backtest fails."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.side_effect = RuntimeError("engine exploded")
        mock_engine_factory.return_value = engine

        mock_wisdom_service_cls = MagicMock()
        mock_wisdom_service_instance = MagicMock()
        mock_wisdom_service_instance.generate_wisdom_from_entry = AsyncMock()
        mock_wisdom_service_cls.return_value = mock_wisdom_service_instance

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=mock_wisdom_service_cls
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        assert result["status"] == "failed"
        # Wisdom generation should never have been called
        mock_wisdom_service_instance.generate_wisdom_from_entry.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.create_backtest_engine"
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_metrics_by_regime",
        return_value={},
    )
    @patch(
        "Fast_Swarm.System.Services.crucible_test_service.calculate_backtest_metrics",
        return_value={
            "sharpe_ratio": 1.0, "win_rate": 55,
            "total_roi_pct": 7.0, "max_drawdown_pct": 3.0,
        },
    )
    async def test_wisdom_stored(
        self, mock_bt_metrics, mock_regime_metrics, mock_engine_factory
    ):
        """Generated wisdom record is returned via wisdom_id in the result."""
        entry = _make_entry()
        session = _mock_session_with_entry(entry)

        engine = MagicMock()
        engine.run.return_value = [_make_trade()]
        mock_engine_factory.return_value = engine

        mock_wisdom = MagicMock()
        mock_wisdom.id = 99
        mock_wisdom_service_instance = MagicMock()
        mock_wisdom_service_instance.generate_wisdom_from_entry = AsyncMock(
            return_value=mock_wisdom
        )

        service = CrucibleTestService()

        with patch.dict(
            "sys.modules",
            {
                "Fast_Swarm.System.Services.wisdom_service": MagicMock(
                    WisdomTransferService=MagicMock(
                        return_value=mock_wisdom_service_instance
                    )
                )
            },
        ):
            result = await service.run_crucible_test(session, entry_id=1)

        assert result["wisdom_id"] == 99
        assert result["status"] == "completed"
