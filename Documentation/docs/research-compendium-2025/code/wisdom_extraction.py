#!/usr/bin/env python3
"""
Wisdom Extraction Implementation.

This module extracts high-level trading rules from patterns in memory,
generating WHEN-DO-BECAUSE wisdom rules.

Paper References:
- Reflect Agent (arxiv-2510.08068): Verbal feedback wisdom
- MacroHFT (arxiv-2406.14537): Memory hierarchy

Related Concept: ../concepts/memory-systems.md
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class WisdomRule:
    """
    High-level trading belief.

    Format: WHEN <condition> DO <action> BECAUSE <reason>

    Paper Reference: Reflect Agent
    "Verbal feedback loop enables agents to articulate
     and refine their trading philosophy"
    """

    rule_id: str
    agent_id: str

    # Rule components (natural language)
    when_condition: str
    do_action: str
    because_reason: str

    # Structured condition for automated matching
    condition_struct: dict[str, dict]
    # Example:
    # {
    #     'rsi': {'op': '<', 'value': 25},
    #     'regime': {'op': '==', 'value': 'bear_volatile'},
    # }

    # Confidence and evidence
    confidence: float
    supporting_trades: int
    contradicting_trades: int

    # Origin
    trigger_type: str  # 'losing_streak', 'regime_shift', 'pattern_discovery', 'manual'

    # Lifecycle
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_validated: datetime = field(default_factory=datetime.utcnow)
    times_applied: int = 0
    times_helpful: int = 0


@dataclass
class SemanticStats:
    """Aggregated statistics for wisdom extraction."""

    pattern_id: str
    trade_count: int
    win_rate: float
    avg_pnl_pct: float
    performance_by_regime: dict[str, dict]
    performance_by_condition: dict[str, dict]


# =============================================================================
# Wisdom Triggers
# =============================================================================


def check_wisdom_triggers(
    recent_trades: list[dict], regime_history: list[str], semantic_stats: dict[str, SemanticStats]
) -> list[dict]:
    """
    Check if conditions warrant wisdom extraction.

    Returns list of triggered conditions with context.

    Triggers:
    1. Losing streak (3+ consecutive losses)
    2. Regime change (market regime shifted)
    3. Pattern breakthrough (pattern exceeds expectations)
    4. Repeated failure (same mistake 5+ times)
    """
    triggers = []

    # Trigger 1: Losing streak
    consecutive_losses = 0
    for trade in reversed(recent_trades):
        if trade.get("pnl_pct", 0) < 0:
            consecutive_losses += 1
        else:
            break

    if consecutive_losses >= 3:
        triggers.append(
            {
                "type": "losing_streak",
                "severity": min(1.0, consecutive_losses / 5),
                "context": {
                    "consecutive_losses": consecutive_losses,
                    "recent_trades": recent_trades[-consecutive_losses:],
                },
            }
        )

    # Trigger 2: Regime change
    if len(regime_history) >= 2 and regime_history[-1] != regime_history[-2]:
        triggers.append(
            {
                "type": "regime_change",
                "severity": 0.7,
                "context": {
                    "old_regime": regime_history[-2],
                    "new_regime": regime_history[-1],
                },
            }
        )

    # Trigger 3: Pattern breakthrough
    for pattern_id, stats in semantic_stats.items():
        if stats.trade_count >= 20 and stats.win_rate > 0.7:
            triggers.append(
                {
                    "type": "pattern_breakthrough",
                    "severity": 0.8,
                    "context": {
                        "pattern_id": pattern_id,
                        "win_rate": stats.win_rate,
                        "trade_count": stats.trade_count,
                    },
                }
            )

    # Trigger 4: Repeated failure
    pattern_failures = {}
    for trade in recent_trades[-20:]:
        if trade.get("pnl_pct", 0) < -0.02:  # 2% loss
            pattern = trade.get("pattern_id", "unknown")
            regime = trade.get("regime", "unknown")
            key = f"{pattern}_{regime}"
            pattern_failures[key] = pattern_failures.get(key, 0) + 1

    for key, count in pattern_failures.items():
        if count >= 5:
            pattern, regime = key.rsplit("_", 1)
            triggers.append(
                {
                    "type": "repeated_failure",
                    "severity": 0.9,
                    "context": {
                        "pattern_id": pattern,
                        "regime": regime,
                        "failure_count": count,
                    },
                }
            )

    return triggers


# =============================================================================
# Rule Generation
# =============================================================================


def extract_wisdom_rule(
    trigger: dict, recent_trades: list[dict], semantic_stats: dict[str, SemanticStats], agent_id: str
) -> WisdomRule | None:
    """
    Extract a wisdom rule from triggered condition.

    Uses pattern analysis to generate WHEN-DO-BECAUSE rules.

    Args:
        trigger: Trigger info from check_wisdom_triggers
        recent_trades: Recent trade history
        semantic_stats: Aggregated pattern statistics
        agent_id: Agent generating the rule

    Returns:
        New WisdomRule or None if extraction failed
    """
    trigger_type = trigger["type"]
    context = trigger["context"]

    if trigger_type == "losing_streak":
        return _extract_losing_streak_wisdom(context, recent_trades, agent_id)
    elif trigger_type == "regime_change":
        return _extract_regime_change_wisdom(context, semantic_stats, agent_id)
    elif trigger_type == "pattern_breakthrough":
        return _extract_breakthrough_wisdom(context, semantic_stats, agent_id)
    elif trigger_type == "repeated_failure":
        return _extract_failure_wisdom(context, recent_trades, agent_id)

    return None


def _extract_losing_streak_wisdom(context: dict, recent_trades: list[dict], agent_id: str) -> WisdomRule | None:
    """Extract wisdom from losing streak."""
    losing_trades = context["recent_trades"]

    # Find common factors in losing trades
    common_regime = find_most_common(t.get("regime") for t in losing_trades)
    common_pattern = find_most_common(t.get("pattern_id") for t in losing_trades)

    # Analyze conditions
    avg_rsi = np.mean([t.get("entry_rsi", 50) for t in losing_trades])
    avg_volume = np.mean([t.get("entry_volume_ratio", 1) for t in losing_trades])

    # Generate rule
    when_parts = []
    condition_struct = {}

    if common_regime:
        when_parts.append(f"regime is {common_regime}")
        condition_struct["regime"] = {"op": "==", "value": common_regime}

    if avg_rsi < 30:
        when_parts.append("RSI < 30")
        condition_struct["rsi"] = {"op": "<", "value": 30}
    elif avg_rsi > 70:
        when_parts.append("RSI > 70")
        condition_struct["rsi"] = {"op": ">", "value": 70}

    if not when_parts:
        when_parts.append(f"using pattern {common_pattern}")

    when_condition = " AND ".join(when_parts)
    do_action = "reduce position size by 50% OR skip trade"
    because_reason = f"{context['consecutive_losses']} consecutive losses in these conditions"

    return WisdomRule(
        rule_id=generate_rule_id(agent_id, "losing_streak"),
        agent_id=agent_id,
        when_condition=when_condition,
        do_action=do_action,
        because_reason=because_reason,
        condition_struct=condition_struct,
        confidence=min(0.9, 0.5 + context["consecutive_losses"] * 0.1),
        supporting_trades=context["consecutive_losses"],
        contradicting_trades=0,
        trigger_type="losing_streak",
    )


def _extract_regime_change_wisdom(
    context: dict, semantic_stats: dict[str, SemanticStats], agent_id: str
) -> WisdomRule | None:
    """Extract wisdom from regime change."""
    old_regime = context["old_regime"]
    new_regime = context["new_regime"]

    # Find patterns that perform differently across regimes
    regime_sensitive_patterns = []

    for pattern_id, stats in semantic_stats.items():
        old_perf = stats.performance_by_regime.get(old_regime, {}).get("win_rate", 0.5)
        new_perf = stats.performance_by_regime.get(new_regime, {}).get("win_rate", 0.5)

        if abs(old_perf - new_perf) > 0.2:  # 20% difference
            regime_sensitive_patterns.append(
                {
                    "pattern_id": pattern_id,
                    "old_perf": old_perf,
                    "new_perf": new_perf,
                }
            )

    if not regime_sensitive_patterns:
        return None

    # Generate rule for most sensitive pattern
    worst = min(regime_sensitive_patterns, key=lambda x: x["new_perf"])

    when_condition = f"regime changes to {new_regime}"
    do_action = f"avoid pattern {worst['pattern_id']} until performance validates"
    because_reason = f"pattern win rate drops from {worst['old_perf']:.0%} to {worst['new_perf']:.0%} in {new_regime}"

    return WisdomRule(
        rule_id=generate_rule_id(agent_id, "regime_change"),
        agent_id=agent_id,
        when_condition=when_condition,
        do_action=do_action,
        because_reason=because_reason,
        condition_struct={
            "regime": {"op": "==", "value": new_regime},
            "pattern": {"op": "==", "value": worst["pattern_id"]},
        },
        confidence=0.7,
        supporting_trades=5,  # Placeholder
        contradicting_trades=0,
        trigger_type="regime_change",
    )


def _extract_breakthrough_wisdom(
    context: dict, semantic_stats: dict[str, SemanticStats], agent_id: str
) -> WisdomRule | None:
    """Extract wisdom from pattern breakthrough."""
    pattern_id = context["pattern_id"]
    stats = semantic_stats.get(pattern_id)

    if not stats:
        return None

    # Find best conditions for this pattern
    best_regime = max(stats.performance_by_regime.items(), key=lambda x: x[1].get("win_rate", 0), default=(None, {}))[0]

    when_condition = f"pattern {pattern_id} signals AND regime is {best_regime}"
    do_action = "increase confidence in signal, consider larger position"
    because_reason = f"pattern has {context['win_rate']:.0%} win rate over {context['trade_count']} trades"

    return WisdomRule(
        rule_id=generate_rule_id(agent_id, "breakthrough"),
        agent_id=agent_id,
        when_condition=when_condition,
        do_action=do_action,
        because_reason=because_reason,
        condition_struct={
            "pattern": {"op": "==", "value": pattern_id},
            "regime": {"op": "==", "value": best_regime},
        },
        confidence=min(0.95, 0.6 + context["win_rate"] * 0.3),
        supporting_trades=context["trade_count"],
        contradicting_trades=int(context["trade_count"] * (1 - context["win_rate"])),
        trigger_type="pattern_breakthrough",
    )


def _extract_failure_wisdom(context: dict, recent_trades: list[dict], agent_id: str) -> WisdomRule | None:
    """Extract wisdom from repeated failure."""
    pattern_id = context["pattern_id"]
    regime = context["regime"]
    failure_count = context["failure_count"]

    when_condition = f"pattern {pattern_id} signals AND regime is {regime}"
    do_action = "skip trade OR require additional confirmation"
    because_reason = f"{failure_count} failures in last 20 trades with this pattern/regime combo"

    return WisdomRule(
        rule_id=generate_rule_id(agent_id, "repeated_failure"),
        agent_id=agent_id,
        when_condition=when_condition,
        do_action=do_action,
        because_reason=because_reason,
        condition_struct={
            "pattern": {"op": "==", "value": pattern_id},
            "regime": {"op": "==", "value": regime},
        },
        confidence=min(0.9, 0.5 + failure_count * 0.08),
        supporting_trades=failure_count,
        contradicting_trades=0,
        trigger_type="repeated_failure",
    )


# =============================================================================
# Rule Application
# =============================================================================


def apply_wisdom_rules(
    current_context: dict, proposed_action: str, wisdom_rules: list[WisdomRule], min_confidence: float = 0.6
) -> tuple[str, list[WisdomRule], str]:
    """
    Apply wisdom rules to modify proposed action.

    Args:
        current_context: Current market context
        proposed_action: Proposed trade action ('BUY', 'SELL', 'HOLD')
        wisdom_rules: Available wisdom rules
        min_confidence: Minimum confidence to apply rule

    Returns:
        (modified_action, triggered_rules, explanation)
    """
    if proposed_action == "HOLD":
        return "HOLD", [], "No action proposed"

    triggered = []
    explanations = []
    position_multiplier = 1.0
    skip_trade = False

    for rule in wisdom_rules:
        if rule.confidence < min_confidence:
            continue

        if matches_condition(current_context, rule.condition_struct):
            triggered.append(rule)
            rule.times_applied += 1

            # Parse action
            action_lower = rule.do_action.lower()

            if "skip" in action_lower:
                skip_trade = True
                explanations.append(f"Skipping: {rule.because_reason}")

            if "reduce" in action_lower:
                if "50%" in action_lower:
                    position_multiplier *= 0.5
                elif "25%" in action_lower:
                    position_multiplier *= 0.75
                else:
                    position_multiplier *= 0.7
                explanations.append(f"Reducing size: {rule.because_reason}")

            if "increase" in action_lower and "confidence" in action_lower:
                position_multiplier *= 1.2
                explanations.append(f"Increasing confidence: {rule.because_reason}")

    # Determine final action
    if skip_trade:
        modified_action = "HOLD"
    else:
        modified_action = f"{proposed_action}:size_mult={position_multiplier:.2f}"

    explanation = " | ".join(explanations) if explanations else "No rules triggered"

    return modified_action, triggered, explanation


def matches_condition(context: dict, condition_struct: dict) -> bool:
    """
    Check if context matches structured condition.

    Args:
        context: Current market context
        condition_struct: Structured conditions from wisdom rule

    Returns:
        True if all conditions match
    """
    for field, condition in condition_struct.items():
        value = context.get(field)
        if value is None:
            continue

        op = condition.get("op", "==")
        target = condition.get("value")

        if (
            (op == "==" and value != target)
            or (op == "!=" and value == target)
            or (op == "<" and not (value < target))
            or (op == ">" and not (value > target))
            or (op == "<=" and not (value <= target))
            or (op == ">=" and not (value >= target))
        ):
            return False

    return True


# =============================================================================
# Rule Management
# =============================================================================


def validate_wisdom_rule(rule: WisdomRule, recent_outcomes: list[dict]) -> float:
    """
    Validate rule against recent outcomes.

    Updates rule confidence based on whether it would have helped.

    Returns:
        Updated confidence score
    """
    helpful = 0
    harmful = 0
    neutral = 0

    for outcome in recent_outcomes:
        context = outcome.get("context", {})
        result = outcome.get("pnl_pct", 0)

        if matches_condition(context, rule.condition_struct):
            # Rule would have been applied
            action = rule.do_action.lower()

            if "skip" in action or "reduce" in action:
                # Rule suggests caution
                if result < -0.01:  # Would have lost
                    helpful += 1
                elif result > 0.02:  # Would have won big
                    harmful += 1
                else:
                    neutral += 1
            elif "increase" in action:
                # Rule suggests confidence
                if result > 0.01:
                    helpful += 1
                elif result < -0.02:
                    harmful += 1
                else:
                    neutral += 1

    total = helpful + harmful + neutral
    if total == 0:
        return rule.confidence

    # Update confidence
    helpfulness = helpful / total
    new_confidence = 0.7 * rule.confidence + 0.3 * helpfulness

    rule.confidence = max(0.1, min(0.95, new_confidence))
    rule.last_validated = datetime.utcnow()
    rule.supporting_trades += helpful
    rule.contradicting_trades += harmful

    if helpful > 0:
        rule.times_helpful += helpful

    return rule.confidence


def prune_weak_rules(rules: list[WisdomRule], min_confidence: float = 0.4, min_supporting: int = 3) -> list[WisdomRule]:
    """
    Remove rules that no longer meet quality threshold.

    Args:
        rules: List of wisdom rules
        min_confidence: Minimum confidence to keep
        min_supporting: Minimum supporting trades to keep

    Returns:
        Filtered list of rules
    """
    return [rule for rule in rules if rule.confidence >= min_confidence and rule.supporting_trades >= min_supporting]


# =============================================================================
# Utility Functions
# =============================================================================


def generate_rule_id(agent_id: str, trigger_type: str) -> str:
    """Generate unique rule ID."""
    data = f"{agent_id}:{trigger_type}:{datetime.utcnow().isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def find_most_common(items) -> str | None:
    """Find most common item in iterable."""
    counts = {}
    for item in items:
        if item is not None:
            counts[item] = counts.get(item, 0) + 1

    if not counts:
        return None

    return max(counts.items(), key=lambda x: x[1])[0]


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Simulate recent trades
    recent_trades = [
        {"pnl_pct": 0.02, "regime": "bull_calm", "pattern_id": "breakout_1", "entry_rsi": 55},
        {"pnl_pct": -0.03, "regime": "bear_volatile", "pattern_id": "dip_buy_1", "entry_rsi": 28},
        {"pnl_pct": -0.02, "regime": "bear_volatile", "pattern_id": "dip_buy_1", "entry_rsi": 25},
        {"pnl_pct": -0.04, "regime": "bear_volatile", "pattern_id": "dip_buy_1", "entry_rsi": 22},
        {"pnl_pct": -0.01, "regime": "bear_volatile", "pattern_id": "momentum_1", "entry_rsi": 45},
    ]

    regime_history = ["bull_calm", "bull_volatile", "bear_volatile"]

    semantic_stats = {
        "dip_buy_1": SemanticStats(
            pattern_id="dip_buy_1",
            trade_count=25,
            win_rate=0.45,
            avg_pnl_pct=-0.005,
            performance_by_regime={
                "bull_calm": {"win_rate": 0.65, "trades": 10},
                "bear_volatile": {"win_rate": 0.25, "trades": 15},
            },
            performance_by_condition={},
        ),
    }

    # Check triggers
    print("Checking wisdom triggers...")
    triggers = check_wisdom_triggers(recent_trades, regime_history, semantic_stats)
    print(f"Found {len(triggers)} triggers:")
    for t in triggers:
        print(f"  - {t['type']}: severity={t['severity']:.2f}")

    # Extract rules
    print("\nExtracting wisdom rules...")
    rules = []
    for trigger in triggers:
        rule = extract_wisdom_rule(trigger, recent_trades, semantic_stats, "agent_001")
        if rule:
            rules.append(rule)
            print(f"\nRule: {rule.rule_id}")
            print(f"  WHEN: {rule.when_condition}")
            print(f"  DO: {rule.do_action}")
            print(f"  BECAUSE: {rule.because_reason}")
            print(f"  Confidence: {rule.confidence:.2f}")

    # Apply rules
    print("\n\nApplying rules to proposed trade...")
    context = {"regime": "bear_volatile", "pattern": "dip_buy_1", "rsi": 26}
    action, triggered, explanation = apply_wisdom_rules(context, "BUY", rules)
    print("Proposed: BUY")
    print(f"Modified: {action}")
    print(f"Triggered {len(triggered)} rules")
    print(f"Explanation: {explanation}")
