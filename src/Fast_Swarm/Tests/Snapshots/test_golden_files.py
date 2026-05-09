"""
Golden File Regression Tests - SNAPSHOT GUARDIAN

MASTER TEST ADMIN DECREE: Yesterday's output is today's expectation.
These tests compare current output against frozen "golden" snapshots.

If a test fails:
1. INTENTIONAL CHANGE: Update the golden file with new snapshot
2. UNINTENTIONAL CHANGE: FIX THE REGRESSION

"History must not change."
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from Agents.Services.fitness_service import calculate_fitness
from Tests.Fixtures.canonical_agents import CANONICAL_AGENTS
from Tests.Fixtures.factories import TradeFactory

# =============================================================================
# GOLDEN FILE UTILITIES
# =============================================================================

SNAPSHOT_DIR = Path(__file__).parent / "golden"


def ensure_golden_dir():
    """Create golden directory if it doesn't exist."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)


def load_golden(name: str) -> dict[str, Any] | None:
    """Load a golden file, return None if doesn't exist."""
    path = SNAPSHOT_DIR / f"{name}.golden.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_golden(name: str, data: dict[str, Any]):
    """
    Save a new golden file.

    WARNING: Only call this when intentionally updating snapshots!
    """
    ensure_golden_dir()
    path = SNAPSHOT_DIR / f"{name}.golden.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def hash_dict(d: dict[str, Any]) -> str:
    """Create deterministic hash of a dictionary."""
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def fitness_result_to_dict(result) -> dict[str, Any]:
    """Convert fitness result to serializable dictionary."""
    return {
        "fitness_score": round(result.fitness_score, 6),
        "tier": result.tier,
        "ev": round(result.metrics.ev, 6),
        "win_rate": round(result.metrics.win_rate, 6),
        "sortino": round(result.metrics.sortino, 6),
        "max_drawdown": round(result.metrics.max_drawdown, 6),
        "ev_multiplier": round(result.ev_multiplier, 6),
    }


# =============================================================================
# TEST: Fitness Calculation Snapshots
# =============================================================================


class TestFitnessSnapshots:
    """Golden file tests for fitness calculations."""

    @pytest.mark.regression
    def test_balanced_trades_fitness(self):
        """
        SNAPSHOT: Balanced trade mix produces consistent fitness.
        """
        # Deterministic trades
        trades = TradeFactory.create_batch(count=50, seed=42, avg_pnl=1.5, win_rate=0.6)

        result = calculate_fitness(trades)
        current = fitness_result_to_dict(result)

        golden = load_golden("fitness_balanced_trades")
        if golden is None:
            # First run - create golden file
            save_golden("fitness_balanced_trades", current)
            pytest.skip("Golden file created - run again to verify")

        # Compare
        assert current == golden, f"Regression detected!\nExpected: {golden}\nGot: {current}"

    @pytest.mark.regression
    def test_all_winners_fitness(self):
        """
        SNAPSHOT: All winning trades fitness.
        """
        trades = TradeFactory.all_winners(count=30, pnl_pct=3.0)

        result = calculate_fitness(trades)
        current = fitness_result_to_dict(result)

        golden = load_golden("fitness_all_winners")
        if golden is None:
            save_golden("fitness_all_winners", current)
            pytest.skip("Golden file created - run again to verify")

        assert current == golden, f"Regression!\nExpected: {golden}\nGot: {current}"

    @pytest.mark.regression
    def test_all_losers_fitness(self):
        """
        SNAPSHOT: All losing trades fitness (should be 0 due to EV gate).
        """
        trades = TradeFactory.all_losers(count=30, pnl_pct=-3.0)

        result = calculate_fitness(trades)
        current = fitness_result_to_dict(result)

        golden = load_golden("fitness_all_losers")
        if golden is None:
            save_golden("fitness_all_losers", current)
            pytest.skip("Golden file created - run again to verify")

        assert current == golden, f"Regression!\nExpected: {golden}\nGot: {current}"

    @pytest.mark.regression
    def test_empty_trades_fitness(self):
        """
        SNAPSHOT: Empty trades fitness.
        """
        result = calculate_fitness([])
        current = fitness_result_to_dict(result)

        golden = load_golden("fitness_empty_trades")
        if golden is None:
            save_golden("fitness_empty_trades", current)
            pytest.skip("Golden file created - run again to verify")

        assert current == golden, f"Regression!\nExpected: {golden}\nGot: {current}"

    @pytest.mark.regression
    def test_single_trade_fitness(self):
        """
        SNAPSHOT: Single trade fitness.
        """
        trades = TradeFactory.single_trade(pnl_pct=5.0)

        result = calculate_fitness(trades)
        current = fitness_result_to_dict(result)

        golden = load_golden("fitness_single_trade")
        if golden is None:
            save_golden("fitness_single_trade", current)
            pytest.skip("Golden file created - run again to verify")

        assert current == golden, f"Regression!\nExpected: {golden}\nGot: {current}"


# =============================================================================
# TEST: Canonical Agent Snapshots
# =============================================================================


class TestCanonicalAgentSnapshots:
    """Golden file tests for canonical agent traits."""

    @pytest.mark.regression
    @pytest.mark.parametrize("agent_name", list(CANONICAL_AGENTS.keys()))
    def test_canonical_agent_traits(self, agent_name):
        """
        SNAPSHOT: Canonical agent traits are stable.
        """
        agent = CANONICAL_AGENTS[agent_name]
        current = {
            "agent_id": agent["agent_id"],
            "traits": agent["traits"],
            "trait_hash": hash_dict(agent["traits"]),
        }

        golden = load_golden(f"agent_{agent_name}")
        if golden is None:
            save_golden(f"agent_{agent_name}", current)
            pytest.skip("Golden file created - run again to verify")

        # Compare trait hash
        assert current["trait_hash"] == golden["trait_hash"], (
            f"Agent {agent_name} traits changed!\n"
            f"Expected hash: {golden['trait_hash']}\n"
            f"Got hash: {current['trait_hash']}"
        )


# =============================================================================
# TEST: Seed Determinism Snapshots
# =============================================================================


class TestSeedDeterminismSnapshots:
    """Verify that seeded operations produce consistent results."""

    @pytest.mark.regression
    @pytest.mark.parametrize("seed", [42, 123, 999, 0, 1])
    def test_trade_batch_determinism(self, seed):
        """
        SNAPSHOT: Trade batch generation is deterministic with seed.
        """
        trades = TradeFactory.create_batch(count=20, seed=seed, avg_pnl=2.0, win_rate=0.55)

        # Hash the PnL values
        pnl_list = [round(t.pnl_pct, 6) for t in trades]
        current = {
            "seed": seed,
            "pnl_values": pnl_list,
            "hash": hash_dict({"pnl": pnl_list}),
        }

        golden = load_golden(f"trades_seed_{seed}")
        if golden is None:
            save_golden(f"trades_seed_{seed}", current)
            pytest.skip("Golden file created - run again to verify")

        assert current["hash"] == golden["hash"], f"Trade generation not deterministic for seed {seed}!"


# =============================================================================
# UTILITY: Update All Golden Files
# =============================================================================


def regenerate_all_golden_files():
    """
    Utility function to regenerate all golden files.

    Run this manually when intentionally changing behavior:
        python -c "from Tests.Snapshots.test_golden_files import regenerate_all_golden_files; regenerate_all_golden_files()"

    WARNING: This will overwrite all existing golden files!
    """
    ensure_golden_dir()

    # Fitness snapshots
    trades = TradeFactory.create_batch(count=50, seed=42, avg_pnl=1.5, win_rate=0.6)
    result = calculate_fitness(trades)
    save_golden("fitness_balanced_trades", fitness_result_to_dict(result))

    trades = TradeFactory.all_winners(count=30, pnl_pct=3.0)
    result = calculate_fitness(trades)
    save_golden("fitness_all_winners", fitness_result_to_dict(result))

    trades = TradeFactory.all_losers(count=30, pnl_pct=-3.0)
    result = calculate_fitness(trades)
    save_golden("fitness_all_losers", fitness_result_to_dict(result))

    result = calculate_fitness([])
    save_golden("fitness_empty_trades", fitness_result_to_dict(result))

    trades = TradeFactory.single_trade(pnl_pct=5.0)
    result = calculate_fitness(trades)
    save_golden("fitness_single_trade", fitness_result_to_dict(result))

    # Agent snapshots
    for agent_name, agent in CANONICAL_AGENTS.items():
        current = {
            "agent_id": agent["agent_id"],
            "traits": agent["traits"],
            "trait_hash": hash_dict(agent["traits"]),
        }
        save_golden(f"agent_{agent_name}", current)

    # Seed determinism snapshots
    for seed in [42, 123, 999, 0, 1]:
        trades = TradeFactory.create_batch(count=20, seed=seed, avg_pnl=2.0, win_rate=0.55)
        pnl_list = [round(t.pnl_pct, 6) for t in trades]
        current = {
            "seed": seed,
            "pnl_values": pnl_list,
            "hash": hash_dict({"pnl": pnl_list}),
        }
        save_golden(f"trades_seed_{seed}", current)

    print(f"Regenerated all golden files in {SNAPSHOT_DIR}")


if __name__ == "__main__":
    regenerate_all_golden_files()
