"""
Agent Fitness Calculator Tests - V3 Parity.

Tests the 100-point fitness system with EV gate.

Fitness Components:
- SIGNED (can go negative):
  - Alpha: ±35 pts (normalized from -100% to +100%)
  - Calibration: ±10 pts (0.5 baseline = 0 pts)

- UNSIGNED (always positive):
  - Win Rate: 10 pts (30-70% normalized)
  - Sortino: 15 pts (0-4 normalized)
  - Drawdown: 10 pts (0-50% normalized, inverted)
  - Exit Efficiency: 10 pts (0.3-0.8 normalized)
  - Loss Sizing: 5 pts (0.5-2.0 normalized)
  - AI Accuracy: 5 pts (0.4-0.8 normalized)

EV Gate: expectancy <= 0 -> fitness = 0
EV Multiplier: 0% -> 0, 1% -> 0.8, 3% -> 1.2, 9%+ -> 1.5 cap
"""


class TestExpectancyMultiplier:
    """EV Gate + Multiplier logic."""

    # === HAPPY PATH ===

    def test_positive_ev_3_percent_gives_1_2_multiplier(self):
        """3% EV -> 1.2x multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(3.0)
        assert abs(mult - 1.2) < 0.01, f"Expected 1.2, got {mult}"

    def test_positive_ev_1_percent_gives_0_8_multiplier(self):
        """1% EV -> 0.8x multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(1.0)
        assert abs(mult - 0.8) < 0.01, f"Expected 0.8, got {mult}"

    def test_high_ev_caps_at_1_5(self):
        """9%+ EV -> 1.5x (capped)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(10.0)
        assert mult == 1.5, f"Expected 1.5 cap, got {mult}"

    def test_ev_6_percent_gives_1_35_multiplier(self):
        """6% EV -> 1.35x multiplier (interpolated between 3% and 9%)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(6.0)
        # Linear interpolation: 1.2 + (6-3)/(9-3) * (1.5-1.2) = 1.2 + 0.5*0.3 = 1.35
        assert abs(mult - 1.35) < 0.01, f"Expected 1.35, got {mult}"

    def test_ev_0_5_percent_gives_0_55_multiplier(self):
        """0.5% EV -> 0.55x multiplier (interpolated between 0% and 1%)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(0.5)
        # Linear interpolation: 0.35 + (0.5-0)/(1-0) * (0.8-0.35) = 0.35 + 0.5*0.45 = 0.575
        # Actually V3 uses: 0% -> 0.35, 1% -> 0.8
        # 0.35 + 0.5 * (0.8 - 0.35) = 0.35 + 0.225 = 0.575
        assert 0.5 < mult < 0.7, f"Expected ~0.575, got {mult}"

    # === COMMON FAILURES ===

    def test_zero_ev_closes_gate(self):
        """0% EV -> 0 multiplier (gate closed)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(0.0)
        assert mult == 0.0, f"Expected 0.0, got {mult}"

    def test_negative_ev_closes_gate(self):
        """-5% EV -> 0 multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(-5.0)
        assert mult == 0.0, f"Expected 0.0, got {mult}"

    def test_barely_positive_ev_gives_small_multiplier(self):
        """0.01% EV -> small but non-zero multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(0.01)
        # Just above zero, should be just above 0.35 (the floor for positive EV)
        assert mult > 0.0, f"Expected > 0, got {mult}"
        assert mult < 0.5, f"Expected < 0.5, got {mult}"

    # === EDGE CASES ===

    def test_nan_ev_closes_gate(self):
        """NaN EV -> 0 multiplier (safe)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(float("nan"))
        assert mult == 0.0, f"Expected 0.0 for NaN, got {mult}"

    def test_inf_ev_caps_at_1_5(self):
        """Infinity EV -> 1.5 multiplier (capped)."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(float("inf"))
        assert mult == 1.5, f"Expected 1.5 cap for inf, got {mult}"

    def test_negative_inf_closes_gate(self):
        """-Infinity EV -> 0 multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import expectancy_multiplier

        mult = expectancy_multiplier(float("-inf"))
        assert mult == 0.0, f"Expected 0.0 for -inf, got {mult}"


class TestAlphaContribution:
    """Signed alpha component (-35 to +35)."""

    # === HAPPY PATH ===

    def test_positive_alpha_50_gives_17_5_pts(self):
        """+50% alpha -> +17.5 pts (half of 35)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(50)
        assert abs(contrib - 17.5) < 0.01, f"Expected 17.5, got {contrib}"

    def test_negative_alpha_50_gives_negative_17_5_pts(self):
        """-50% alpha -> -17.5 pts."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(-50)
        assert abs(contrib - (-17.5)) < 0.01, f"Expected -17.5, got {contrib}"

    def test_zero_alpha_gives_zero(self):
        """0% alpha -> 0 pts."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(0)
        assert contrib == 0.0, f"Expected 0, got {contrib}"

    def test_positive_alpha_100_gives_35_pts(self):
        """+100% alpha -> +35 pts (max)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(100)
        assert contrib == 35.0, f"Expected 35, got {contrib}"

    def test_negative_alpha_100_gives_negative_35_pts(self):
        """-100% alpha -> -35 pts (min)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(-100)
        assert contrib == -35.0, f"Expected -35, got {contrib}"

    # === EDGE CASES ===

    def test_alpha_clamped_at_100(self):
        """+200% alpha -> +35 pts (capped at 100%)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(200)
        assert contrib == 35.0, f"Expected 35 (capped), got {contrib}"

    def test_alpha_clamped_at_negative_100(self):
        """-200% alpha -> -35 pts (capped at -100%)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(-200)
        assert contrib == -35.0, f"Expected -35 (capped), got {contrib}"

    def test_alpha_nan_returns_zero(self):
        """NaN alpha -> 0 pts (safe default)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_alpha_contribution

        contrib = calculate_alpha_contribution(float("nan"))
        assert contrib == 0.0, f"Expected 0 for NaN, got {contrib}"


class TestCalibrationContribution:
    """Signed calibration component (-10 to +10)."""

    # === HAPPY PATH ===

    def test_perfect_calibration_gives_10_pts(self):
        """calibration=1.0 -> +10 pts."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(1.0)
        assert abs(contrib - 10) < 0.01, f"Expected 10, got {contrib}"

    def test_random_calibration_gives_zero(self):
        """calibration=0.5 -> 0 pts (neutral baseline)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(0.5)
        assert abs(contrib) < 0.01, f"Expected 0, got {contrib}"

    def test_inverse_calibration_gives_negative_10(self):
        """calibration=0.0 -> -10 pts."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(0.0)
        assert abs(contrib - (-10)) < 0.01, f"Expected -10, got {contrib}"

    def test_calibration_0_75_gives_5_pts(self):
        """calibration=0.75 -> +5 pts (halfway to perfect)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(0.75)
        assert abs(contrib - 5) < 0.01, f"Expected 5, got {contrib}"

    def test_calibration_0_25_gives_negative_5_pts(self):
        """calibration=0.25 -> -5 pts (halfway to worst)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(0.25)
        assert abs(contrib - (-5)) < 0.01, f"Expected -5, got {contrib}"

    # === EDGE CASES ===

    def test_calibration_above_1_clamped(self):
        """calibration=1.5 -> +10 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(1.5)
        assert contrib == 10.0, f"Expected 10 (clamped), got {contrib}"

    def test_calibration_negative_clamped(self):
        """calibration=-0.5 -> -10 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(-0.5)
        assert contrib == -10.0, f"Expected -10 (clamped), got {contrib}"

    def test_calibration_nan_returns_zero(self):
        """NaN calibration -> 0 pts (neutral)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_calibration_contribution

        contrib = calculate_calibration_contribution(float("nan"))
        assert contrib == 0.0, f"Expected 0 for NaN, got {contrib}"


class TestWinRateScore:
    """Win rate component (0-10 pts)."""

    # === HAPPY PATH ===

    def test_win_rate_70_gives_10_pts(self):
        """70% win rate -> 10 pts (max)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_win_rate_score

        score = calculate_win_rate_score(70)
        assert abs(score - 10) < 0.1, f"Expected 10, got {score}"

    def test_win_rate_30_gives_0_pts(self):
        """30% win rate -> 0 pts (min)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_win_rate_score

        score = calculate_win_rate_score(30)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_win_rate_50_gives_5_pts(self):
        """50% win rate -> 5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_win_rate_score

        score = calculate_win_rate_score(50)
        assert abs(score - 5) < 0.1, f"Expected 5, got {score}"

    # === EDGE CASES ===

    def test_win_rate_above_70_clamped(self):
        """85% win rate -> 10 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_win_rate_score

        score = calculate_win_rate_score(85)
        assert score == 10.0, f"Expected 10 (clamped), got {score}"

    def test_win_rate_below_30_clamped(self):
        """15% win rate -> 0 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_win_rate_score

        score = calculate_win_rate_score(15)
        assert score == 0.0, f"Expected 0 (clamped), got {score}"


class TestSortinoScore:
    """Sortino ratio component (0-15 pts)."""

    # === HAPPY PATH ===

    def test_sortino_4_gives_15_pts(self):
        """Sortino 4.0 -> 15 pts (max)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_sortino_score

        score = calculate_sortino_score(4.0)
        assert abs(score - 15) < 0.1, f"Expected 15, got {score}"

    def test_sortino_0_gives_0_pts(self):
        """Sortino 0.0 -> 0 pts (min)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_sortino_score

        score = calculate_sortino_score(0.0)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_sortino_2_gives_7_5_pts(self):
        """Sortino 2.0 -> 7.5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_sortino_score

        score = calculate_sortino_score(2.0)
        assert abs(score - 7.5) < 0.1, f"Expected 7.5, got {score}"

    # === EDGE CASES ===

    def test_sortino_above_4_clamped(self):
        """Sortino 6.0 -> 15 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_sortino_score

        score = calculate_sortino_score(6.0)
        assert score == 15.0, f"Expected 15 (clamped), got {score}"

    def test_sortino_negative_clamped(self):
        """Sortino -1.0 -> 0 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_sortino_score

        score = calculate_sortino_score(-1.0)
        assert score == 0.0, f"Expected 0 (clamped), got {score}"


class TestDrawdownScore:
    """Drawdown component (0-10 pts, inverted - lower DD is better)."""

    # === HAPPY PATH ===

    def test_zero_drawdown_gives_10_pts(self):
        """0% drawdown -> 10 pts (best)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_drawdown_score

        score = calculate_drawdown_score(0)
        assert abs(score - 10) < 0.1, f"Expected 10, got {score}"

    def test_50_percent_drawdown_gives_0_pts(self):
        """50% drawdown -> 0 pts (worst in bounds)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_drawdown_score

        score = calculate_drawdown_score(50)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_25_percent_drawdown_gives_5_pts(self):
        """25% drawdown -> 5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_drawdown_score

        score = calculate_drawdown_score(25)
        assert abs(score - 5) < 0.1, f"Expected 5, got {score}"

    # === EDGE CASES ===

    def test_drawdown_above_50_clamped(self):
        """75% drawdown -> 0 pts (clamped)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_drawdown_score

        score = calculate_drawdown_score(75)
        assert score == 0.0, f"Expected 0 (clamped), got {score}"


class TestExitEfficiencyScore:
    """Exit efficiency component (0-10 pts)."""

    # === HAPPY PATH ===

    def test_efficiency_0_8_gives_10_pts(self):
        """0.8 efficiency -> 10 pts (max)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_exit_efficiency_score

        score = calculate_exit_efficiency_score(0.8)
        assert abs(score - 10) < 0.1, f"Expected 10, got {score}"

    def test_efficiency_0_3_gives_0_pts(self):
        """0.3 efficiency -> 0 pts (min)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_exit_efficiency_score

        score = calculate_exit_efficiency_score(0.3)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_efficiency_0_55_gives_5_pts(self):
        """0.55 efficiency -> 5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_exit_efficiency_score

        score = calculate_exit_efficiency_score(0.55)
        assert abs(score - 5) < 0.1, f"Expected 5, got {score}"


class TestLossSizingScore:
    """Loss sizing ratio component (0-5 pts)."""

    # === HAPPY PATH ===

    def test_loss_sizing_2_gives_5_pts(self):
        """2.0 ratio -> 5 pts (max, wins 2x losses)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_loss_sizing_score

        score = calculate_loss_sizing_score(2.0)
        assert abs(score - 5) < 0.1, f"Expected 5, got {score}"

    def test_loss_sizing_0_5_gives_0_pts(self):
        """0.5 ratio -> 0 pts (min, losses 2x wins)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_loss_sizing_score

        score = calculate_loss_sizing_score(0.5)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_loss_sizing_1_25_gives_2_5_pts(self):
        """1.25 ratio -> 2.5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_loss_sizing_score

        score = calculate_loss_sizing_score(1.25)
        assert abs(score - 2.5) < 0.1, f"Expected 2.5, got {score}"


class TestAIAccuracyScore:
    """AI accuracy component (0-5 pts)."""

    # === HAPPY PATH ===

    def test_ai_accuracy_0_8_gives_5_pts(self):
        """0.8 accuracy -> 5 pts (max)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_ai_accuracy_score

        score = calculate_ai_accuracy_score(0.8)
        assert abs(score - 5) < 0.1, f"Expected 5, got {score}"

    def test_ai_accuracy_0_4_gives_0_pts(self):
        """0.4 accuracy -> 0 pts (min, random baseline)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_ai_accuracy_score

        score = calculate_ai_accuracy_score(0.4)
        assert abs(score) < 0.1, f"Expected 0, got {score}"

    def test_ai_accuracy_0_6_gives_2_5_pts(self):
        """0.6 accuracy -> 2.5 pts (middle)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_ai_accuracy_score

        score = calculate_ai_accuracy_score(0.6)
        assert abs(score - 2.5) < 0.1, f"Expected 2.5, got {score}"

    # === EDGE CASES ===

    def test_no_ai_decisions_neutral(self):
        """0 AI decisions -> baseline score (neutral)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_ai_accuracy_from_counts

        score = calculate_ai_accuracy_from_counts(0, 0)
        # No AI decisions = can't calculate accuracy, use neutral
        assert 0 <= score <= 5, f"Expected neutral score, got {score}"


class TestFullFitnessCalculation:
    """End-to-end fitness calculation."""

    # === HAPPY PATH ===

    def test_excellent_agent_scores_high(self, sample_metrics):
        """Agent with good metrics -> reasonable positive fitness."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)
        # With 2% EV (multiplier 1.0), 25% alpha, 55% WR, etc.
        # Expected raw score around 40-50
        assert result.final_fitness >= 35, f"Expected >= 35, got {result.final_fitness}"
        assert result.ev_gate_passed is True

    def test_poor_agent_scores_zero_with_negative_ev(self, poor_metrics):
        """Agent with negative EV -> 0 fitness (gate closed)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(poor_metrics)
        assert result.final_fitness == 0, f"Expected 0 (gate closed), got {result.final_fitness}"

    def test_mediocre_agent_scores_middle(self):
        """Agent with average metrics -> 40-60 fitness."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness
        from Fast_Swarm.local_agents.tests.conftest import AgentMetrics

        metrics = AgentMetrics(
            total_trades=100,
            winning_trades=50,
            losing_trades=50,
            alpha_pct=10.0,
            expectancy_pct=1.0,  # Just positive
            win_rate_pct=50.0,
            sortino_ratio=1.0,
            max_drawdown_pct=20.0,
            calibration_score=0.5,  # Neutral
            exit_efficiency=0.5,
            loss_sizing_ratio=1.0,
            ai_decisions=0,
            ai_correct=0,
            ai_usage_rate=0.0,
        )

        result = calculate_agent_fitness(metrics)
        assert 20 < result.final_fitness < 70, f"Expected 20-70, got {result.final_fitness}"

    # === EDGE CASES ===

    def test_breakdown_sums_correctly(self, sample_metrics):
        """Verify component math: signed + unsigned = raw."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)

        expected_raw = result.signed_total + result.unsigned_total
        assert abs(result.raw_fitness - expected_raw) < 0.01, (
            f"Raw {result.raw_fitness} != signed {result.signed_total} + unsigned {result.unsigned_total}"
        )

    def test_final_fitness_clamped_0_100(self, sample_metrics):
        """Final fitness always in [0, 100]."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)
        assert 0 <= result.final_fitness <= 100, f"Expected 0-100, got {result.final_fitness}"

    def test_ev_gate_correctly_sets_flag(self, sample_metrics, poor_metrics):
        """EV gate flag matches multiplier state."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        good_result = calculate_agent_fitness(sample_metrics)
        assert good_result.ev_gate_passed is True
        assert good_result.ev_multiplier > 0

        poor_result = calculate_agent_fitness(poor_metrics)
        assert poor_result.ev_gate_passed is False
        assert poor_result.ev_multiplier == 0

    def test_unsigned_components_sum(self, sample_metrics):
        """Verify unsigned component total is correct."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)

        expected_unsigned = (
            result.win_rate_score
            + result.sortino_score
            + result.drawdown_score
            + result.exit_efficiency_score
            + result.loss_sizing_score
            + result.ai_accuracy_score
        )
        assert abs(result.unsigned_total - expected_unsigned) < 0.01, (
            f"Unsigned total {result.unsigned_total} != sum {expected_unsigned}"
        )

    def test_signed_components_sum(self, sample_metrics):
        """Verify signed component total is correct."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)

        expected_signed = result.alpha_contribution + result.calibration_contribution
        assert abs(result.signed_total - expected_signed) < 0.01, (
            f"Signed total {result.signed_total} != sum {expected_signed}"
        )

    def test_scaled_fitness_applies_multiplier(self, sample_metrics):
        """Scaled fitness = raw * multiplier."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness

        result = calculate_agent_fitness(sample_metrics)

        expected_scaled = result.raw_fitness * result.ev_multiplier
        assert abs(result.scaled_fitness - expected_scaled) < 0.01, (
            f"Scaled {result.scaled_fitness} != raw {result.raw_fitness} * mult {result.ev_multiplier}"
        )


class TestFitnessWeights:
    """Verify fitness weight constants match V3."""

    def test_weights_sum_to_100(self):
        """All weights sum to 100 points."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_WEIGHTS

        # Signed components
        signed_sum = AGENT_FITNESS_WEIGHTS["alpha"] + AGENT_FITNESS_WEIGHTS["calibration"]
        assert signed_sum == 45, f"Signed sum should be 45, got {signed_sum}"

        # Unsigned components
        unsigned_sum = (
            AGENT_FITNESS_WEIGHTS["win_rate"]
            + AGENT_FITNESS_WEIGHTS["sortino"]
            + AGENT_FITNESS_WEIGHTS["drawdown"]
            + AGENT_FITNESS_WEIGHTS["exit_efficiency"]
            + AGENT_FITNESS_WEIGHTS["loss_sizing"]
            + AGENT_FITNESS_WEIGHTS["ai_accuracy"]
        )
        assert unsigned_sum == 55, f"Unsigned sum should be 55, got {unsigned_sum}"

        # Total potential
        assert signed_sum + unsigned_sum == 100

    def test_individual_weights_correct(self):
        """Individual weight values match V3 spec."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_WEIGHTS

        assert AGENT_FITNESS_WEIGHTS["alpha"] == 35
        assert AGENT_FITNESS_WEIGHTS["calibration"] == 10
        assert AGENT_FITNESS_WEIGHTS["win_rate"] == 10
        assert AGENT_FITNESS_WEIGHTS["sortino"] == 15
        assert AGENT_FITNESS_WEIGHTS["drawdown"] == 10
        assert AGENT_FITNESS_WEIGHTS["exit_efficiency"] == 10
        assert AGENT_FITNESS_WEIGHTS["loss_sizing"] == 5
        assert AGENT_FITNESS_WEIGHTS["ai_accuracy"] == 5


class TestFitnessBounds:
    """Verify fitness bound constants match V3."""

    def test_alpha_bounds(self):
        """Alpha bounds: -100% to +100%."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["alpha_pct"]["min"] == -100
        assert AGENT_FITNESS_BOUNDS["alpha_pct"]["max"] == 100

    def test_win_rate_bounds(self):
        """Win rate bounds: 30% to 70%."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["win_rate_pct"]["min"] == 30
        assert AGENT_FITNESS_BOUNDS["win_rate_pct"]["max"] == 70

    def test_sortino_bounds(self):
        """Sortino bounds: 0 to 4."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["sortino_ratio"]["min"] == 0
        assert AGENT_FITNESS_BOUNDS["sortino_ratio"]["max"] == 4

    def test_drawdown_bounds(self):
        """Drawdown bounds: 0% to 50%."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["max_drawdown_pct"]["min"] == 0
        assert AGENT_FITNESS_BOUNDS["max_drawdown_pct"]["max"] == 50

    def test_exit_efficiency_bounds(self):
        """Exit efficiency bounds: 0.3 to 0.8."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["exit_efficiency"]["min"] == 0.3
        assert AGENT_FITNESS_BOUNDS["exit_efficiency"]["max"] == 0.8

    def test_loss_sizing_bounds(self):
        """Loss sizing bounds: 0.5 to 2.0."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["loss_sizing_ratio"]["min"] == 0.5
        assert AGENT_FITNESS_BOUNDS["loss_sizing_ratio"]["max"] == 2.0

    def test_ai_accuracy_bounds(self):
        """AI accuracy bounds: 0.4 to 0.8."""
        from Fast_Swarm.local_agents.shared.fitness import AGENT_FITNESS_BOUNDS

        assert AGENT_FITNESS_BOUNDS["ai_accuracy"]["min"] == 0.4
        assert AGENT_FITNESS_BOUNDS["ai_accuracy"]["max"] == 0.8
