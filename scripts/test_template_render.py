#!/usr/bin/env python3
"""Test that the template renders correctly with includes."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROMPTS_DIR = Path(__file__).parent.parent / "local_agents" / "prompts"

env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=select_autoescape())
template = env.get_template("ai_zone_decision.j2")

# Test render
result = template.render(
    asset="BTC",
    pattern_name="Test Pattern",
    pattern_id="test-123",
    direction="long",
    confidence=0.65,
    min_threshold=0.5,
    ai_threshold=0.9,
    indicators={
        "rsi_14": 45.5,
        "stoch_k": 72.0,
        "adx_14": 25.0,
        "macd_line": 10.5,
        "macd_signal": 8.2,
        "supertrend": -1,
    },
    agent_name="TestAgent",
    traits={"aggression": 0.5, "patience": 0.7},
    philosophy="Test philosophy",
    recent_win_rate=0.55,
    recent_pnl_pct=2.5,
    trades_today=3,
    memories=[],
)

print("=== RENDERED PROMPT ===")
print(result)
print("\n=== TOKEN COUNT (approx) ===")
print(f"~{len(result.split())} words, ~{len(result) // 4} tokens")
