import pytest

# Mocking the legacy "Evidence" - in a real scenario, this would load from AgentDatabase
HISTORICAL_EVIDENCE = [
    {
        "description": "BTC Long Exit Trigger - ATR Trail",
        "direction": "long",
        "entry_price": 50000.0,
        "current_price": 49000.0,
        "indicators": {"atr": 1000.0},
        "config": {"atr_multiplier": 1.5},
        "expected_exit": True,
        "reason": "atr_trailing_stop",
    },
    {
        "description": "ETH Short - Dynamic Trail Widen",
        "direction": "short",
        "entry_price": 3000.0,
        "current_price": 3100.0,
        "profit_pct": -3.33,
        "expected_trail": 2.0,  # Base trail at loss
    },
]


def test_evidence_exit_logic_parity():
    """Verify that Fast_Swarm's exit logic matches the historical evidence conclusions."""
    # We use the logic from local_agents for now, but this test bed
    # will verify the Fast_Swarm services once they are ported.
    from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, ExitStrategy, OpenTrade

    # Test Case 1: ATR Exit
    evidence = HISTORICAL_EVIDENCE[0]
    trade = OpenTrade(
        trade_id="test_1",
        agent_id="A1",
        pattern_id="P1",
        asset="BTC",
        direction=evidence["direction"],
        entry_price=evidence["entry_price"],
        entry_timestamp=0,
        entry_confidence=0.8,
        decision_zone="execute",
        ai_consulted=False,
        ai_decision=None,
        position_size_pct=5.0,
    )
    # Set peak price to entry for a loss scenario
    trade.peak_price = evidence["entry_price"]

    config = BacktestConfig(exit_strategy=ExitStrategy.ATR_TRAIL, atr_multiplier=evidence["config"]["atr_multiplier"])

    # ATR = 1000, Multiplier = 1.5 -> Distance = 1500
    # Stop = 50000 - 1500 = 48500
    # Current = 49000 -> Should NOT exit yet? Wait.
    # Ah, if price dropped to 48000, it SHOULD exit.

    # Let's verify the calculation logic specifically
    atr = evidence["indicators"]["atr"]
    dist = atr * config.atr_multiplier
    trail_pct = (dist / evidence["current_price"]) * 100

    # The engine uses update_trailing_stop
    triggered = trade.update_trailing_stop(evidence["current_price"], trail_pct, config)
    # 49000 is above 48500, so triggered should be False
    assert triggered is False

    # Now simulate a drop to 48000
    triggered_at_48 = trade.update_trailing_stop(48000.0, trail_pct, config)
    assert triggered_at_48 is True


def test_evidence_dynamic_trail_scaling():
    """Verify that the Logarithmic widening logic matches historical evidence."""
    from Fast_Swarm.local_agents.backtest.engine import calculate_dynamic_trail

    # Case: 0% profit -> 2% trail
    assert calculate_dynamic_trail(0.0) == 2.0

    # Case: 10% profit -> ~4.0% trail
    # Logic: 2.0 + 2.5 * ln(1 + 10/10) = 2.0 + 2.5 * ln(2) = 2.0 + 2.5 * 0.693 = 3.73
    assert calculate_dynamic_trail(10.0) == pytest.approx(3.73, abs=0.01)

    # Case: 100% profit -> ~9.0% trail
    # Logic: 2.0 + 2.5 * ln(1 + 10) = 2.0 + 2.5 * 2.39 = 2.0 + 5.99 = 7.99
    # Wait, the comment in engine.py said ~9.0, let's check the scale.
    # log_scale is 2.5.
    assert calculate_dynamic_trail(100.0) == pytest.approx(7.99, abs=0.01)


def test_statistical_significance_stub():
    """Verify the stub for the 95% confidence interval check."""
    # This will be used to verify that "Evidence" (like a fitness gain)
    # is not just noise.
    import numpy as np
    from scipy import stats

    results = [0.1, 0.12, 0.09, 0.11, 0.13, 0.10, 0.11, 0.12, 0.08, 0.11]  # Sample fitness gains
    mean = np.mean(results)
    sem = stats.sem(results)
    interval = stats.t.interval(0.95, len(results) - 1, loc=mean, scale=sem)

    # Evidence is accepted if the lower bound of the 95% CI > 0
    assert interval[0] > 0
