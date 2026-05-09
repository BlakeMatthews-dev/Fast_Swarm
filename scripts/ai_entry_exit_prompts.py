#!/usr/bin/env python3
"""
AI Entry/Exit Decision Prompts for Pattern Evaluation.

Two-step decision process:
1. ENTRY: Pattern matched → AI confirms or rejects based on market context
2. EXIT: Each candle after entry → AI decides hold or exit based on evolving conditions
"""

# =============================================================================
# ENTRY DECISION PROMPT
# =============================================================================

INDICATOR_KNOWLEDGE = """## TECHNICAL INDICATOR REFERENCE

### RSI (Relative Strength Index)
Measures the ratio of recent upward price movements to total price movement.
Range: 0-100
- 0-25: EXTREMELY oversold - sellers exhausted, strong bounce probability
- 25-30: Oversold - selling pressure dominated, potential reversal zone
- 30-70: Neutral - neither buyers nor sellers dominating
- 70-75: Overbought - buying pressure dominated, potential pullback zone
- 75-100: EXTREMELY overbought - buyers exhausted, correction likely

### Stochastic K
Measures where price closed relative to its recent high-low range.
Range: 0-100
- Stoch = 100: Price closed at the HIGH of recent range
- Stoch = 50: Price closed in the MIDDLE of recent range
- Stoch = 20: Price closed near the BOTTOM (20%) of range - oversold
- Stoch = 10: Price at bottom 10% of range - VERY oversold
- Stoch < 5: Price essentially at the FLOOR - EXTREMELY oversold, rare

CRITICAL: Stoch < 10 means price has collapsed to near the lowest point.
This is often a capitulation/exhaustion signal, not just "oversold."

### MACD (Moving Average Convergence Divergence)
- MACD Line > 0: Short-term average above long-term (recent prices higher)
- MACD Line < 0: Short-term average below long-term (recent prices lower)
- MACD > Signal: Momentum accelerating upward (positive crossover)
- MACD < Signal: Momentum accelerating downward (negative crossover)

IMPORTANT: Negative MACD during oversold conditions explains WHY price fell.
It is not an additional reason to avoid - the selling already happened.

### ADX (Average Directional Index)
Measures trend STRENGTH, NOT direction. ADX does not tell you up or down.
- 0-20: Weak or absent trend - ranging/choppy market
- 20-40: Moderate trend strength
- 40-60: Strong trend
- 60+: Very strong trend (rare)

CRITICAL: Low ADX (< 20) means RANGING market where mean reversion works well.
Oversold + Low ADX = HIGH probability of bounce back to mean.

### Supertrend
Trend direction indicator using ATR-based dynamic bands.
- Direction = +1: Trend UP
- Direction = -1: Trend DOWN
- Direction = 0: Neutral/undefined

IMPORTANT: Downward Supertrend during oversold shows the TREND that caused the oversold state.
It explains context, not an additional negative signal.

---

## INDICATOR COMBINATIONS (CRITICAL)

### Oversold Combinations (GOOD for longs)
- RSI < 30 + Stoch < 20 = Double oversold, strong reversal signal
- RSI < 25 + Stoch < 10 = EXTREME oversold / capitulation, very high bounce probability
- Stoch < 5 alone = Price at the floor, sellers completely exhausted

### Oversold + Trend Context
- Oversold + ADX < 20 = Dip in ranging market, HIGH probability mean reversion - BEST SETUP
- Oversold + ADX > 40 = Strong trend! Could reverse OR continue. Higher risk.

### Overbought Combinations (BAD for longs)
- RSI > 70 + Stoch > 80 = Double overbought - HIGH pullback risk, AVOID longs
- RSI > 75 + Stoch > 90 = EXTREME overbought - reversal down likely

---

## CRITICAL: DOWNWARD INDICATORS DO NOT CANCEL OVERSOLD SIGNALS

When price is OVERSOLD (RSI < 30 or Stoch < 20):
- Negative MACD = explains WHY it's oversold (selling happened) - NOT a reason to avoid
- Downward Supertrend = confirms the down move occurred - NOT a reason to avoid
- Strong ADX = trend was powerful - does NOT mean it will continue forever

OVERSOLD + DOWNWARD INDICATORS = GOOD LONG SETUP
The downward indicators created the oversold condition. They are not additional negatives.

Example: Stoch = 5, MACD negative, Supertrend -1
- WRONG thinking: "Three downward signals, avoid!"
- RIGHT thinking: "Price crashed to the floor, sellers exhausted, bounce likely"

---

## OUR TRADING HISTORY (What worked for us)

MEMORY 1: "March 2020 - We bought BTC when RSI=25, Stoch=6, MACD was deeply negative. Everyone said 'don't catch falling knife' but we bought anyway. Price bounced +45% in 2 weeks. LESSON: Extreme oversold + negative momentum = BUY signal, not avoid signal."

MEMORY 2: "May 2021 - We bought ETH when Stoch=4, RSI=22, Supertrend was -1. The negative indicators EXPLAINED why it was oversold. We made +38% on that trade. LESSON: Stoch < 10 is a gift."

MEMORY 3: "Luna crash 2022 - We avoided buying SOL when RSI=72, Stoch=88. Good call - it dropped 60% after. LESSON: Overbought = stay away."

MEMORY 4: "November 2022 - RSI=50, Stoch=45, ADX=12. No clear signal. We skipped it. Correct - price went sideways. LESSON: Neutral = no edge, skip."

MEMORY 5: "January 2024 - Stoch dropped to 8, RSI=30, MACD histogram deeply negative. We hesitated because 'everything looks negative'. MISTAKE. Price bounced +25%. We missed it. LESSON LEARNED: Stop treating oversold + negative MACD as 'avoid'. The negative MACD is WHY it's oversold!"
"""

TASK_PROMPT = """## YOUR TASK

Rate this trade setup using one of these labels:

SB = STRONG BUY - Stoch < 10 or RSI < 25. Extreme oversold. High probability winner.
B = BUY - RSI < 30 or Stoch < 20. Oversold conditions. Worth taking.
S = SKIP - Neutral conditions. No clear edge. Pass on this trade.
SS = STRONG SKIP - Overbought (RSI > 70, Stoch > 80). Avoid this trade.

OUTPUT FORMAT (JSON only):
{
    "choice": "SB", "B", "S", or "SS",
    "primary_signal": "the single most important indicator",
    "reasoning": "brief explanation"
}

APPLY THESE LESSONS FROM OUR HISTORY:
- Stoch < 10 → We made money buying these. Choice = "SB".
- RSI < 30 → Oversold, we made money. Choice = "B" or "SB".
- RSI > 70 + Stoch > 80 → We lost money. Choice = "SS".
- Neutral (RSI 40-60, Stoch 40-60) → No edge. Choice = "S"."""

ENTRY_SYSTEM_PROMPT = INDICATOR_KNOWLEDGE + "\n" + TASK_PROMPT


def format_entry_prompt(pattern_conditions: list, indicators: dict, regime: str) -> str:
    """Format the entry decision prompt with INTERPRETED indicator values."""

    # Convert Decimals to float safely
    def to_float(val, default=0):
        try:
            return float(val) if val is not None else default
        except:
            return default

    # Get key indicators
    rsi = to_float(indicators.get("rsi_14"), 50)
    stoch = to_float(indicators.get("stoch_k"), 50)
    adx = to_float(indicators.get("adx_14"), 25)
    macd_line = to_float(indicators.get("macd_line"), 0)
    macd_signal = to_float(indicators.get("macd_signal"), 0)
    supertrend = indicators.get("supertrend_direction", 0)

    # Interpret RSI
    if rsi < 25:
        rsi_zone = "EXTREMELY OVERSOLD - sellers exhausted"
    elif rsi < 30:
        rsi_zone = "oversold"
    elif rsi > 75:
        rsi_zone = "EXTREMELY OVERBOUGHT - avoid longs"
    elif rsi > 70:
        rsi_zone = "overbought"
    else:
        rsi_zone = "neutral"

    # Interpret Stochastic - CRITICAL for model to understand
    if stoch < 5:
        stoch_zone = "AT THE FLOOR - sellers completely exhausted, STRONG BUY signal"
    elif stoch < 10:
        stoch_zone = "EXTREMELY OVERSOLD - high bounce probability"
    elif stoch < 20:
        stoch_zone = "oversold"
    elif stoch > 90:
        stoch_zone = "at ceiling - avoid longs"
    elif stoch > 80:
        stoch_zone = "overbought"
    else:
        stoch_zone = "neutral"

    # Interpret ADX
    if adx < 20:
        adx_zone = "weak/ranging - mean reversion likely works"
    elif adx > 40:
        adx_zone = "strong trend"
    else:
        adx_zone = "moderate"

    # Interpret MACD
    macd_cross = "positive" if macd_line > macd_signal else "negative"

    # Interpret Supertrend
    trend = "UP" if supertrend == 1 else "DOWN" if supertrend == -1 else "FLAT"

    # Combined signal highlight - THIS IS KEY
    is_oversold = rsi < 30 or stoch < 20
    is_overbought = rsi > 70 or stoch > 80

    if stoch < 10:
        combined = "\n\n** SIGNAL: Stoch at floor (<10) = STRONG BUY. We made money on these before! **"
    elif is_oversold and adx < 25:
        combined = "\n\n** SIGNAL: Oversold + weak trend = High probability mean reversion. BUY. **"
    elif is_oversold:
        combined = "\n\n** Oversold conditions present **"
    elif is_overbought:
        combined = "\n\n** WARNING: OVERBOUGHT - avoid longs, choose SS **"
    else:
        combined = "\n\n** Neutral - no clear oversold signal **"

    return f"""INDICATORS:
- RSI(14): {rsi:.1f} ({rsi_zone})
- Stochastic K: {stoch:.1f} ({stoch_zone})
- MACD: {macd_cross} crossover
- ADX(14): {adx:.1f} ({adx_zone})
- Supertrend: {trend}{combined}

Evaluate this setup."""


# =============================================================================
# EXIT DECISION PROMPT
# =============================================================================

EXIT_SYSTEM_PROMPT = """You are managing an OPEN position, deciding whether to HOLD or EXIT on each candle.

## Your Role
You entered a trade. Now you must decide at each candle: continue holding or exit now.

## Key Considerations
1. **Trend Health:** Is the trend that got you in still intact?
2. **Momentum Shift:** Are oscillators diverging from price?
3. **Profit Protection:** Have gains become significant enough to lock in?
4. **Risk Signals:** Are warning signs appearing?

## Exit Triggers to Watch
- Momentum divergence (price up, RSI down or vice versa)
- Trend indicator flip (Supertrend, MACD crossover)
- Extreme readings reversing (RSI leaving overbought/oversold)
- Bollinger band rejection
- Volume divergence

Respond with JSON: {"decision": "HOLD" or "EXIT", "confidence": 0.0-1.0, "reasoning": "brief"}"""


def format_exit_prompt(
    entry_price: float,
    entry_indicators: dict,
    current_indicators: dict,
    bars_held: int,
    current_pnl_pct: float,
    peak_pnl_pct: float,  # MFE so far
) -> str:
    """Format the exit decision prompt with position and market data."""

    price = current_indicators.get("close", 0)

    # Calculate indicator changes
    rsi_entry = entry_indicators.get("rsi_14", 50)
    rsi_now = current_indicators.get("rsi_14", 50)
    rsi_change = rsi_now - rsi_entry

    macd_entry = entry_indicators.get("macd_histogram", 0)
    macd_now = current_indicators.get("macd_histogram", 0)

    adx_now = current_indicators.get("adx_14", 0)
    supertrend = current_indicators.get("supertrend_direction", 0)

    # Key indicators now
    ind_lines = []
    for key, label in [
        ("rsi_14", "RSI"),
        ("stoch_k", "Stoch"),
        ("macd_histogram", "MACD Hist"),
        ("adx_14", "ADX"),
        ("supertrend_direction", "Supertrend"),
    ]:
        if key in current_indicators and current_indicators[key] is not None:
            ind_lines.append(
                f"{label}: {current_indicators[key]:.1f}"
                if isinstance(current_indicators[key], float)
                else f"{label}: {current_indicators[key]}"
            )

    return f"""## Open Position Status
**Entry Price:** {entry_price:,.2f}
**Current Price:** {price:,.2f}
**Bars Held:** {bars_held}
**Current P&L:** {current_pnl_pct:+.1f}%
**Peak P&L (MFE):** {peak_pnl_pct:+.1f}%
**Giveback:** {peak_pnl_pct - current_pnl_pct:.1f}% from peak

## Indicator Changes Since Entry
**RSI:** {rsi_entry:.0f} -> {rsi_now:.0f} ({rsi_change:+.0f})
**MACD Hist:** {macd_entry:.2f} -> {macd_now:.2f}

## Current Readings
{" | ".join(ind_lines)}

## Decision Required
Should we HOLD this position or EXIT now?"""


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test entry prompt
    test_pattern = [
        {"indicator": "rsi_14", "operator": "<", "value": 30, "description": "RSI(14) < 30 (oversold)"},
        {"indicator": "stoch_k", "operator": "<", "value": 20, "description": "Stoch K < 20 (oversold)"},
    ]

    test_indicators = {
        "close": 42500.0,
        "rsi_14": 28.5,
        "rsi_7": 25.2,
        "stoch_k": 15.3,
        "stoch_d": 18.7,
        "macd_line": -150.5,
        "macd_signal": -120.3,
        "macd_histogram": -30.2,
        "adx_14": 35.2,
        "plus_di": 18.5,
        "minus_di": 28.3,
        "cci_14": -125.5,
        "willr_14": -85.2,
        "mfi_14": 22.1,
        "atr_14": 850.5,
        "bb_upper": 45000.0,
        "bb_middle": 43500.0,
        "bb_lower": 42000.0,
        "supertrend_direction": -1,
        "sma_20": 43200.0,
        "sma_50": 44100.0,
        "sma_200": 41500.0,
        "obv": 125000,
        "cmf_20": -0.15,
    }

    print("=" * 70)
    print("ENTRY PROMPT TEST")
    print("=" * 70)
    print("\n[SYSTEM PROMPT]")
    print(ENTRY_SYSTEM_PROMPT[:500] + "...")
    print("\n[USER PROMPT]")
    print(format_entry_prompt(test_pattern, test_indicators, "bear"))

    print("\n" + "=" * 70)
    print("EXIT PROMPT TEST")
    print("=" * 70)
    print("\n[SYSTEM PROMPT]")
    print(EXIT_SYSTEM_PROMPT[:500] + "...")
    print("\n[USER PROMPT]")

    # Simulate 5 bars later
    current_indicators = test_indicators.copy()
    current_indicators["close"] = 43800.0
    current_indicators["rsi_14"] = 45.2
    current_indicators["macd_histogram"] = -15.5

    print(
        format_exit_prompt(
            entry_price=42500.0,
            entry_indicators=test_indicators,
            current_indicators=current_indicators,
            bars_held=5,
            current_pnl_pct=3.06,
            peak_pnl_pct=4.2,
        )
    )
