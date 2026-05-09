"""
Decision Zone Tests - 3-Zone System.

Zones:
- SKIP: confidence < min_threshold (no trade)
- AI_REFLECT: min_threshold <= confidence < ai_threshold (consult LLM)
- EXECUTE: confidence >= ai_threshold (auto trade)

AI Zone Modes (configurable):
- SKIP: Treat AI_REFLECT as SKIP (fast backtesting)
- LLM: Real Ollama calls (live trading)

Note: SIMULATE mode removed per user feedback - left undecided for now.
"""

from dataclasses import dataclass


# Local AgentTraits for tests (avoids conftest import issue)
@dataclass
class AgentTraits:
    """Agent traits for decision tests."""

    min_threshold: float = 0.35
    ai_threshold: float = 0.65
    risk_tolerance: float = 0.5
    entry_aggression: float = 0.5
    volatility_seeking: float = 0.5
    profit_target_greed: float = 0.5
    hold_duration_bias: float = 0.5


class TestZoneDetermination:
    """SKIP, AI_REFLECT, EXECUTE zones."""

    def test_below_min_threshold_is_skip(self):
        """Confidence < min_threshold -> SKIP."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.30, traits=traits)

        assert zone.zone == DecisionZone.SKIP

    def test_between_thresholds_is_ai_reflect(self):
        """min <= confidence < ai -> AI_REFLECT."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.50, traits=traits)

        assert zone.zone == DecisionZone.AI_REFLECT

    def test_above_ai_threshold_is_execute(self):
        """Confidence >= ai_threshold -> EXECUTE."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.70, traits=traits)

        assert zone.zone == DecisionZone.EXECUTE

    # === EDGE CASES ===

    def test_exactly_at_min_threshold(self):
        """Confidence == min_threshold -> AI_REFLECT (inclusive)."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.35, traits=traits)

        assert zone.zone == DecisionZone.AI_REFLECT

    def test_exactly_at_ai_threshold(self):
        """Confidence == ai_threshold -> EXECUTE (inclusive)."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.65, traits=traits)

        assert zone.zone == DecisionZone.EXECUTE

    def test_just_below_min_threshold(self):
        """Confidence just below min -> SKIP."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.349, traits=traits)

        assert zone.zone == DecisionZone.SKIP

    def test_just_below_ai_threshold(self):
        """Confidence just below ai -> AI_REFLECT."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.649, traits=traits)

        assert zone.zone == DecisionZone.AI_REFLECT

    def test_confidence_zero(self):
        """Confidence = 0 -> SKIP."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=0.0, traits=traits)

        assert zone.zone == DecisionZone.SKIP

    def test_confidence_one(self):
        """Confidence = 1.0 -> EXECUTE."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        zone = determine_zone(confidence=1.0, traits=traits)

        assert zone.zone == DecisionZone.EXECUTE


class TestZoneDecisionResult:
    """Zone decision result includes metadata."""

    def test_decision_includes_zone(self):
        """Decision result includes zone enum."""
        from Fast_Swarm.local_agents.core.decision import determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        result = determine_zone(confidence=0.50, traits=traits)

        assert hasattr(result, "zone")

    def test_decision_includes_confidence(self):
        """Decision result includes original confidence."""
        from Fast_Swarm.local_agents.core.decision import determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        result = determine_zone(confidence=0.50, traits=traits)

        assert hasattr(result, "confidence")
        assert result.confidence == 0.50

    def test_decision_includes_thresholds(self):
        """Decision result includes threshold values used."""
        from Fast_Swarm.local_agents.core.decision import determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        result = determine_zone(confidence=0.50, traits=traits)

        assert hasattr(result, "min_threshold")
        assert hasattr(result, "ai_threshold")
        assert result.min_threshold == 0.35
        assert result.ai_threshold == 0.65


class TestAIZoneModes:
    """Configurable AI zone handling."""

    def test_skip_mode_treats_as_skip(self):
        """AI_ZONE + skip mode -> behaves like SKIP."""
        from Fast_Swarm.local_agents.core.decision import AIZoneMode, handle_ai_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        result = handle_ai_zone(confidence=0.5, traits=traits, mode=AIZoneMode.SKIP)

        assert result.action == "skip"
        assert result.trade_decision is False

    def test_llm_mode_returns_pending(self):
        """AI_ZONE + llm mode -> returns pending for LLM decision."""
        from Fast_Swarm.local_agents.core.decision import AIZoneMode, handle_ai_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)
        result = handle_ai_zone(confidence=0.5, traits=traits, mode=AIZoneMode.LLM)

        # Should indicate LLM consultation needed
        assert result.action == "consult_llm" or result.requires_llm is True


class TestAIDecisionContext:
    """Context provided to AI for decision."""

    def test_context_includes_confidence(self):
        """AI context includes confidence score."""
        from Fast_Swarm.local_agents.core.decision import build_ai_decision_context
        # Using local AgentTraits

        traits = AgentTraits()
        context = build_ai_decision_context(
            confidence=0.55, traits=traits, pattern_id="pattern-001", indicators={"rsi": 35, "macd": 0.5}
        )

        assert "confidence" in context
        assert context["confidence"] == 0.55

    def test_context_includes_traits(self):
        """AI context includes relevant agent traits."""
        from Fast_Swarm.local_agents.core.decision import build_ai_decision_context
        # Using local AgentTraits

        traits = AgentTraits(risk_tolerance=0.7, entry_aggression=0.6)
        context = build_ai_decision_context(confidence=0.55, traits=traits, pattern_id="pattern-001", indicators={})

        assert "traits" in context
        assert context["traits"]["risk_tolerance"] == 0.7

    def test_context_includes_indicators(self):
        """AI context includes current indicators."""
        from Fast_Swarm.local_agents.core.decision import build_ai_decision_context
        # Using local AgentTraits

        traits = AgentTraits()
        context = build_ai_decision_context(
            confidence=0.55, traits=traits, pattern_id="pattern-001", indicators={"rsi": 28, "macd": -0.3}
        )

        assert "indicators" in context
        assert context["indicators"]["rsi"] == 28

    def test_context_includes_pattern_id(self):
        """AI context includes pattern being evaluated."""
        from Fast_Swarm.local_agents.core.decision import build_ai_decision_context
        # Using local AgentTraits

        traits = AgentTraits()
        context = build_ai_decision_context(confidence=0.55, traits=traits, pattern_id="pattern-001", indicators={})

        assert "pattern_id" in context
        assert context["pattern_id"] == "pattern-001"


class TestLLMDecisionParsing:
    """Parse LLM decision responses."""

    def test_parse_take_trade_decision(self):
        """Parse LLM 'TAKE' decision."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        response = {"decision": "TAKE", "reasoning": "RSI is oversold and MACD is turning positive"}

        result = parse_llm_decision(response)

        assert result.trade_decision is True
        assert result.reasoning is not None

    def test_parse_skip_trade_decision(self):
        """Parse LLM 'SKIP' decision."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        response = {"decision": "SKIP", "reasoning": "Uncertainty too high given recent volatility"}

        result = parse_llm_decision(response)

        assert result.trade_decision is False
        assert result.reasoning is not None

    def test_parse_decision_case_insensitive(self):
        """Decision parsing is case insensitive."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        response_lower = {"decision": "take", "reasoning": "test"}
        response_upper = {"decision": "TAKE", "reasoning": "test"}
        response_mixed = {"decision": "Take", "reasoning": "test"}

        assert parse_llm_decision(response_lower).trade_decision is True
        assert parse_llm_decision(response_upper).trade_decision is True
        assert parse_llm_decision(response_mixed).trade_decision is True

    def test_parse_invalid_decision_defaults_skip(self):
        """Invalid/malformed decision defaults to SKIP (safe)."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        response = {"decision": "maybe", "reasoning": "unsure"}

        result = parse_llm_decision(response)

        assert result.trade_decision is False  # Safe default

    def test_parse_missing_decision_defaults_skip(self):
        """Missing decision field defaults to SKIP."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        response = {"reasoning": "some text but no decision"}

        result = parse_llm_decision(response)

        assert result.trade_decision is False

    def test_parse_empty_response_defaults_skip(self):
        """Empty response defaults to SKIP."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        result = parse_llm_decision({})

        assert result.trade_decision is False

    def test_parse_none_response_defaults_skip(self):
        """None response defaults to SKIP."""
        from Fast_Swarm.local_agents.core.decision import parse_llm_decision

        result = parse_llm_decision(None)

        assert result.trade_decision is False


class TestDecisionTracking:
    """Track AI decisions for metrics."""

    def test_track_ai_decision_consulted(self):
        """Track when AI was consulted."""
        from Fast_Swarm.local_agents.core.decision import TradeDecisionTracker

        tracker = TradeDecisionTracker()
        tracker.record_ai_consulted(trade_id="trade-001")

        assert tracker.ai_consultations == 1

    def test_track_ai_decision_correct(self):
        """Track when AI decision was correct."""
        from Fast_Swarm.local_agents.core.decision import TradeDecisionTracker

        tracker = TradeDecisionTracker()
        tracker.record_ai_consulted(trade_id="trade-001")
        tracker.record_ai_outcome(trade_id="trade-001", was_correct=True)

        assert tracker.ai_correct == 1

    def test_track_ai_decision_incorrect(self):
        """Track when AI decision was incorrect."""
        from Fast_Swarm.local_agents.core.decision import TradeDecisionTracker

        tracker = TradeDecisionTracker()
        tracker.record_ai_consulted(trade_id="trade-001")
        tracker.record_ai_outcome(trade_id="trade-001", was_correct=False)

        assert tracker.ai_correct == 0
        assert tracker.ai_consultations == 1

    def test_calculate_ai_accuracy(self):
        """Calculate AI accuracy rate."""
        from Fast_Swarm.local_agents.core.decision import TradeDecisionTracker

        tracker = TradeDecisionTracker()

        # 3 consultations, 2 correct
        for i, correct in enumerate([True, True, False]):
            trade_id = f"trade-{i}"
            tracker.record_ai_consulted(trade_id=trade_id)
            tracker.record_ai_outcome(trade_id=trade_id, was_correct=correct)

        accuracy = tracker.ai_accuracy

        assert abs(accuracy - 0.667) < 0.01

    def test_ai_accuracy_no_consultations(self):
        """AI accuracy with 0 consultations returns neutral."""
        from Fast_Swarm.local_agents.core.decision import TradeDecisionTracker

        tracker = TradeDecisionTracker()

        # No consultations -> neutral (0.5 or None)
        accuracy = tracker.ai_accuracy

        assert accuracy is None or accuracy == 0.5


class TestDecisionZoneEnum:
    """DecisionZone enum values."""

    def test_zone_enum_values(self):
        """Zone enum has correct values."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone

        assert DecisionZone.SKIP.value == "skip"
        assert DecisionZone.AI_REFLECT.value == "reflect"
        assert DecisionZone.EXECUTE.value == "execute"

    def test_zone_enum_members(self):
        """Zone enum has exactly 3 members."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone

        assert len(DecisionZone) == 3


class TestAIZoneModeEnum:
    """AIZoneMode enum values."""

    def test_ai_zone_mode_values(self):
        """AI zone mode enum has correct values."""
        from Fast_Swarm.local_agents.core.decision import AIZoneMode

        assert AIZoneMode.SKIP.value == "skip"
        assert AIZoneMode.LLM.value == "llm"

    def test_ai_zone_mode_members(self):
        """AI zone mode enum has exactly 2 members (no SIMULATE)."""
        from Fast_Swarm.local_agents.core.decision import AIZoneMode

        # SIMULATE mode removed per user feedback
        assert len(AIZoneMode) == 2
        assert not hasattr(AIZoneMode, "SIMULATE")


class TestDecisionWithPatternContext:
    """Decision making with full pattern context."""

    def test_decision_with_pattern_name(self):
        """Include pattern name in decision context."""
        from Fast_Swarm.local_agents.core.decision import make_trade_decision
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)

        result = make_trade_decision(
            confidence=0.80,
            traits=traits,
            pattern_id="pattern-001",
            pattern_name="RSI Oversold Bounce",
            indicators={"rsi": 25},
        )

        assert result.zone.value == "execute"

    def test_decision_returns_action(self):
        """Decision returns actionable result."""
        from Fast_Swarm.local_agents.core.decision import make_trade_decision
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)

        # EXECUTE zone
        result = make_trade_decision(confidence=0.80, traits=traits, pattern_id="pattern-001")

        assert result.should_trade is True

        # SKIP zone
        result = make_trade_decision(confidence=0.20, traits=traits, pattern_id="pattern-001")

        assert result.should_trade is False


class TestZoneTransitions:
    """Test zone transitions at boundaries."""

    def test_transitions_across_full_range(self):
        """Test zone transitions from 0 to 1."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.35, ai_threshold=0.65)

        # Below min threshold
        for conf in [0.0, 0.1, 0.2, 0.34]:
            zone = determine_zone(confidence=conf, traits=traits)
            assert zone.zone == DecisionZone.SKIP, f"conf={conf} should be SKIP"

        # In AI zone
        for conf in [0.35, 0.40, 0.50, 0.64]:
            zone = determine_zone(confidence=conf, traits=traits)
            assert zone.zone == DecisionZone.AI_REFLECT, f"conf={conf} should be AI_REFLECT"

        # Execute zone
        for conf in [0.65, 0.70, 0.80, 0.90, 1.0]:
            zone = determine_zone(confidence=conf, traits=traits)
            assert zone.zone == DecisionZone.EXECUTE, f"conf={conf} should be EXECUTE"


class TestNarrowZone:
    """Test behavior with very narrow or overlapping thresholds."""

    def test_narrow_ai_zone(self):
        """Narrow AI zone (min=0.49, ai=0.51) still works."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.49, ai_threshold=0.51)

        assert determine_zone(0.48, traits).zone == DecisionZone.SKIP
        assert determine_zone(0.50, traits).zone == DecisionZone.AI_REFLECT
        assert determine_zone(0.52, traits).zone == DecisionZone.EXECUTE

    def test_zero_width_ai_zone(self):
        """Zero-width AI zone (min=ai) - edge case."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        traits = AgentTraits(min_threshold=0.50, ai_threshold=0.50)

        # At threshold, should be EXECUTE (ai_threshold inclusive)
        assert determine_zone(0.50, traits).zone == DecisionZone.EXECUTE
        assert determine_zone(0.49, traits).zone == DecisionZone.SKIP

    def test_inverted_thresholds_handled(self):
        """Inverted thresholds (min > ai) handled gracefully."""
        from Fast_Swarm.local_agents.core.decision import DecisionZone, determine_zone
        # Using local AgentTraits

        # This shouldn't happen normally, but handle gracefully
        traits = AgentTraits(min_threshold=0.70, ai_threshold=0.30)

        # Implementation should either swap them or handle consistently
        # Just verify no crash
        result = determine_zone(0.50, traits)
        assert result.zone in [DecisionZone.SKIP, DecisionZone.AI_REFLECT, DecisionZone.EXECUTE]
