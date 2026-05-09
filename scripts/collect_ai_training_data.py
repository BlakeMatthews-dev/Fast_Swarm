#!/usr/bin/env python3
"""
Collect AI Training Data: Confidence scores + reasoning for fine-tuning.

Model sees: Entry setup, agent traits, sentiment
Model outputs: Confidence (0-1) + reasoning
We record: Ground truth (hidden from model) for later evaluation

Decision rule: if model_confidence >= agent.ai_threshold then TAKE else SKIP
"""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

VLLM_URL = "http://localhost:8000"

# =============================================================================
# SYSTEM PROMPT - Indicator knowledge FIRST for vLLM prefix caching
# =============================================================================

INDICATOR_KNOWLEDGE = """## TECHNICAL INDICATOR REFERENCE

### RSI (Relative Strength Index)

Measures the ratio of recent upward price movements to total price movement.

Formula: RSI = 100 - (100 / (1 + AvgGain/AvgLoss))

Range: 0-100
- 0-25: EXTREMELY oversold - sellers exhausted, strong bounce probability
- 25-30: Oversold - selling pressure dominated, potential reversal zone
- 30-70: Neutral - neither buyers nor sellers dominating
- 70-75: Overbought - buying pressure dominated, potential pullback zone
- 75-100: EXTREMELY overbought - buyers exhausted, correction likely

The period (7/14/21) controls sensitivity. RSI(14) is standard.

---

### Stochastic K

Measures where price closed relative to its recent high-low range.

Formula: %K = (Close - LowestLow) / (HighestHigh - LowestLow) * 100

Range: 0-100
- Stoch = 100: Price closed at the HIGH of recent range
- Stoch = 50: Price closed in the MIDDLE of recent range
- Stoch = 20: Price closed near the BOTTOM (20%) of range - oversold
- Stoch = 10: Price at bottom 10% of range - VERY oversold
- Stoch < 5: Price essentially at the FLOOR - EXTREMELY oversold, rare

CRITICAL: Stoch < 10 means price has collapsed to near the lowest point of recent trading.
This is often a capitulation/exhaustion signal, not just "oversold."

---

### MACD (Moving Average Convergence Divergence)

Measures the relationship between fast and slow exponential moving averages.

Components:
- MACD Line = EMA(12) - EMA(26)
- Signal Line = EMA(9) of MACD Line

Interpretation:
- MACD Line > 0: Short-term average above long-term (recent prices higher)
- MACD Line < 0: Short-term average below long-term (recent prices lower)
- MACD > Signal: Momentum accelerating upward (bullish crossover)
- MACD < Signal: Momentum accelerating downward (bearish crossover)

IMPORTANT: Bearish MACD during oversold conditions explains WHY price fell.
It is not an additional reason to avoid - the selling already happened.

---

### ADX (Average Directional Index)

Measures trend STRENGTH, NOT direction. ADX does not tell you up or down.

Range: 0-100
- 0-20: Weak or absent trend - ranging/choppy market
- 20-25: Trend developing
- 25-40: Moderate trend strength
- 40-60: Strong trend
- 60+: Very strong trend (rare)

CRITICAL: Low ADX (< 20) means RANGING market where mean reversion works well.
Oversold + Low ADX = HIGH probability of bounce back to mean.

---

### Supertrend

Trend direction indicator using ATR-based dynamic bands.

Values:
- Direction = +1: Indicator considers trend BULLISH
- Direction = -1: Indicator considers trend BEARISH
- Direction = 0: Neutral/undefined

IMPORTANT: Bearish Supertrend during oversold conditions shows the TREND that caused
the oversold state. It explains context, not an additional negative signal.

---

### ATR (Average True Range)

Measures average price movement per period, accounting for gaps.

Interpretation:
- Higher ATR = more volatile, larger price swings
- Lower ATR = calmer, smaller price swings
- ATR does NOT indicate direction

Used for: position sizing, stop-loss placement, volatility context.

---

### Bollinger Bands

Statistical bands showing where price "usually" trades.

Components:
- Middle = SMA(20)
- Upper = SMA(20) + 2 standard deviations
- Lower = SMA(20) - 2 standard deviations

Interpretation:
- Price at upper band: ~2 std dev above average (extended high)
- Price at lower band: ~2 std dev below average (extended low)
- Wide bands = high volatility period
- Narrow bands = low volatility period

---

### Fear & Greed Index

Aggregate market sentiment indicator (0-100).

Ranges:
- 0-25: EXTREME FEAR - investors very worried, panic selling
- 25-45: Fear - cautious sentiment
- 45-55: Neutral - balanced sentiment
- 55-75: Greed - optimistic sentiment
- 75-100: EXTREME GREED - euphoria, complacency

---

## INDICATOR COMBINATIONS (CRITICAL)

Single indicators mean little. Combinations tell the full story.

### Oversold Combinations (GOOD for longs)
- RSI < 30 + Stoch < 20 = Double oversold confirmation, strong reversal signal
- RSI < 25 + Stoch < 10 = EXTREME oversold / capitulation, very high bounce probability
- Stoch < 5 alone = Price at the floor, sellers completely exhausted

### Oversold + Trend Context
- Oversold + ADX < 20 = Dip in ranging market, HIGH probability mean reversion - BEST SETUP
- Oversold + ADX 20-40 = Moderate trend, decent reversal probability
- Oversold + ADX > 40 = Strong trend! Could reverse OR continue. Higher risk.

### Neutral Zone (No Strong Signal)
- RSI 35-65 + Stoch 25-75 = NEUTRAL range - no extremes
- Neutral indicators alone = uncertain, no clear setup

### Overbought Combinations (BAD for longs)
- RSI > 70 = Price extended high - pullback risk
- Stoch > 80 = Price near top of range - limited upside
- RSI > 70 + Stoch > 80 = Double overbought - HIGH pullback risk, AVOID longs
- RSI > 75 + Stoch > 90 = EXTREME overbought - reversal down likely

### Strong Trend Context
- ADX > 50 = VERY strong trend - higher risk trades
- Strong trend + Oversold = Could still reverse, but higher risk

### Sentiment Context
- Extreme Fear + Oversold = Panic capitulation, often marks bottoms - BULLISH
- Extreme Fear + NOT oversold = Market worried but price hasn't crashed - CAUTION
- Extreme Greed + Oversold = Dip in bull market - BULLISH
- Extreme Greed + Overbought = Euphoria/blow-off top - AVOID longs

### MACD Context
- Bearish MACD + Oversold = Momentum pushed it down, selling may be exhausted - OK
- Bearish MACD + NOT oversold = Momentum still down, more downside possible - CAUTION
- Bullish MACD crossover + Oversold = Momentum turning at lows - early reversal signal

---

## CRITICAL: BEARISH INDICATORS DO NOT CANCEL OVERSOLD SIGNALS

When price is OVERSOLD (RSI < 30 or Stoch < 20):
- Bearish MACD = explains WHY it's oversold (selling happened) - NOT a reason to avoid
- Bearish Supertrend = confirms the down move occurred - NOT a reason to avoid
- Strong ADX = trend was powerful - does NOT mean it will continue forever

OVERSOLD + BEARISH INDICATORS = GOOD LONG SETUP
The bearish indicators created the oversold condition. They are not additional negatives.

Example: Stoch = 5, MACD bearish, Supertrend bearish
- WRONG thinking: "Three bearish signals, avoid!"
- RIGHT thinking: "Price crashed to the floor, sellers exhausted, bounce likely"

## WHEN TO TRADE (Choice 1 or 2)
- Stoch < 10 = At the floor, STRONG signal regardless of other indicators
- RSI < 30 OR Stoch < 20 = Oversold, good entry
- Bearish MACD/Supertrend with oversold = CONFIRMS the setup, not a negative

## WHEN TO HOLD (Choice 3 or 4)
- RSI > 70 OR Stoch > 80 = Overbought, avoid longs
- RSI > 40 AND Stoch > 40 AND ADX > 50 = Strong trend continuation, risky
- No oversold signal present = no clear reversal setup
"""

TASK_PROMPT = """## CONTEXT

You are a second opinion for a trading agent. The agent ALREADY matched a pattern and wants to enter.
Your job: Evaluate if THIS setup is worth taking, given the current indicator conditions.

The agent's pattern matching is the PRIMARY signal. You are checking if conditions support it.

## YOUR TASK

Rate this trade on a scale from -2 to +2:

+2 = BUY CONFIDENT
     Strong oversold signals. Stoch < 10 or RSI < 30. High probability winner.

+1 = BUY UNCERTAIN
     Decent setup. Worth taking but less certain.

-1 = SELL UNCERTAIN
     Leaning toward avoiding this trade.

-2 = SELL CONFIDENT
     Confident this is a BAD trade. Overbought, or no oversold signal present.

OUTPUT FORMAT (JSON only):
{
    "choice": -2, -1, +1, or +2,
    "confidence": 0.0-1.0,
    "indicators_used": ["list", "of", "indicators", "that", "influenced", "decision"],
    "primary_signal": "the single most important indicator or combination",
    "reasoning": "2-3 sentences on key indicator combinations"
}

CRITICAL REMINDER:
- Stoch < 10 = BUY (price at floor, sellers exhausted)
- Oversold + Bearish MACD/Supertrend = BUY (bearish indicators EXPLAIN the oversold, not cancel it)
- Do NOT say "oversold but bearish trend so avoid" - that is WRONG logic
- Choice 4 = CONFIDENT it will LOSE (overbought or no oversold signal), not "uncertain"
- If Stoch < 10 and you choose SELL, you are making a mistake"""

SYSTEM_PROMPT = INDICATOR_KNOWLEDGE + "\n" + TASK_PROMPT


def load_trades():
    path = Path(__file__).parent.parent / "data" / "agent_trades_full_context.json"
    with open(path) as f:
        return json.load(f)


def format_prompt(trade):
    """Format trade data into a concise prompt for evaluation."""
    ind = trade.get("indicators", {})

    rsi = ind.get("rsi_14", 50)
    rsi_zone = "EXTREMELY oversold" if rsi < 25 else "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"

    macd_line = ind.get("macd_line", 0)
    macd_signal_val = ind.get("macd_signal", 0)
    macd_cross = "bullish" if macd_line > macd_signal_val else "bearish"

    stoch = ind.get("stoch_k", 50)
    # Critical: Add Stoch interpretation - model was ignoring floor signals!
    if stoch < 5:
        stoch_zone = "AT THE FLOOR - sellers exhausted"
    elif stoch < 10:
        stoch_zone = "EXTREMELY oversold"
    elif stoch < 20:
        stoch_zone = "oversold"
    elif stoch > 95:
        stoch_zone = "at ceiling"
    elif stoch > 80:
        stoch_zone = "overbought"
    else:
        stoch_zone = "neutral"

    adx = ind.get("adx_14", 25)
    # Add context for ADX < 20 = mean reversion
    if adx < 20:
        trend_str = "weak/ranging - mean reversion likely"
    elif adx > 40:
        trend_str = "strong"
    else:
        trend_str = "moderate"

    st_dir = ind.get("supertrend_direction", 0)
    trend = "bullish" if st_dir > 0 else "bearish" if st_dir < 0 else "neutral"

    fg = trade.get("fear_greed", 50)
    sentiment = trade.get("sentiment", "Neutral")

    # Add combined signal highlights - be selective to avoid overcorrection
    combined = ""
    is_oversold = rsi < 30 or stoch < 20
    is_overbought = rsi > 70 or stoch > 80
    is_very_strong_trend = adx > 50  # Only warn on VERY strong trends
    is_bearish_trend = st_dir < 0
    is_truly_neutral = rsi > 35 and stoch > 25  # Both clearly NOT oversold

    # Prioritize bullish signals first
    if stoch < 10:
        combined = "\n\n** Stoch at floor - STRONG oversold signal, high bounce probability **"
    elif is_oversold and adx < 25:
        combined = "\n\n** OVERSOLD + WEAK TREND = High probability mean reversion **"
    elif is_oversold:
        combined = "\n\n** Oversold conditions present **"
    # Only warn on truly dangerous setups
    elif is_overbought:
        combined = "\n\n** WARNING: OVERBOUGHT - avoid longs **"
    elif is_truly_neutral and is_very_strong_trend and is_bearish_trend:
        combined = "\n\n** DANGER: Not oversold + Very strong downtrend (ADX>50) **"

    return f"""Symbol: {trade["symbol"]}
Fear & Greed: {fg:.0f}/100 ({sentiment})

INDICATORS:
- RSI(14): {rsi:.1f} ({rsi_zone})
- Stochastic K: {stoch:.1f} ({stoch_zone})
- MACD: {macd_cross} crossover
- ADX(14): {adx:.1f} ({trend_str})
- Supertrend: {trend}{combined}

Evaluate this setup."""


def parse_response(response):
    """Parse model response to extract choice, confidence, and reasoning."""

    def convert_scale(raw_choice):
        """Convert -2 to +2 scale to internal 1-4 scale."""
        # +2 → 1 (BUY-HI), +1 → 2 (BUY-LO), -1 → 3 (SELL-LO), -2 → 4 (SELL-HI)
        # 0 → 3 (treat as uncertain/SELL-LO)
        mapping = {2: 1, 1: 2, -1: 3, -2: 4, 0: 3}
        return mapping.get(raw_choice, 3)

    try:
        match = re.search(r"\{[^{}]+\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            raw_choice = int(data.get("choice", 0))
            choice = convert_scale(raw_choice)
            conf = float(data.get("confidence", 0.5))
            conf = max(0.0, min(1.0, conf))
            return {
                "choice": choice,
                "raw_choice": raw_choice,
                "confidence": conf,
                "indicators_used": data.get("indicators_used", []),
                "primary_signal": data.get("primary_signal", ""),
                "reasoning": data.get("reasoning", ""),
                "parse_success": True,
            }
    except:
        pass

    # Fallback parsing - look for -2, -1, +1, +2 or 1-4
    choice_match = re.search(r'choice["\s:]+([+-]?[0-4])', response, re.I)
    conf_match = re.search(r'confidence["\s:]+([0-9.]+)', response, re.I)

    raw_choice = int(choice_match.group(1)) if choice_match else 0
    choice = convert_scale(raw_choice)
    conf = float(conf_match.group(1)) if conf_match else 0.5
    conf = max(0.0, min(1.0, conf))

    return {
        "choice": choice,
        "raw_choice": raw_choice,
        "confidence": conf,
        "indicators_used": [],
        "primary_signal": "",
        "reasoning": response[:200],
        "parse_success": bool(choice_match and conf_match),
    }


async def get_model_confidence(client, trade, model):
    prompt = format_prompt(trade)
    try:
        resp = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1,
            },
            timeout=30.0,
        )
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = parse_response(content)
        return {**parsed, "raw_response": content, "error": None}
    except Exception as e:
        return {"confidence": None, "reasoning": None, "raw_response": None, "parse_success": False, "error": str(e)}


async def collect_data(trades, model, concurrency=24):
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def process_trade(trade):
        async with semaphore, httpx.AsyncClient() as client:
            ai_out = await get_model_confidence(client, trade, model)

            ground_truth = {
                "pnl_pct": trade["pnl_pct"],
                "was_winner": trade["is_winner"],
            }

            if ai_out.get("choice") is not None:
                # Choice 1,2 = TAKE, Choice 3,4 = HOLD
                would_take = ai_out["choice"] in [1, 2]
                # For TAKE: correct if winner. For HOLD: correct if loser.
                if would_take:
                    decision_correct = trade["is_winner"]
                else:
                    decision_correct = not trade["is_winner"]
                ground_truth["would_take"] = would_take
                ground_truth["decision_correct"] = decision_correct
                ground_truth["choice"] = ai_out["choice"]

            return {
                "input": {
                    "symbol": trade["symbol"],
                    "pattern": trade.get("pattern_name"),
                    "agent_name": trade.get("agent_name"),
                    "fear_greed": trade.get("fear_greed"),
                    "sentiment": trade.get("sentiment"),
                    "indicators": trade.get("indicators", {}),
                },
                "output": {
                    "choice": ai_out.get("choice"),
                    "confidence": ai_out.get("confidence"),
                    "reasoning": ai_out.get("reasoning"),
                },
                "ground_truth": ground_truth,
                "meta": {
                    "raw_response": ai_out.get("raw_response"),
                    "parse_success": ai_out.get("parse_success"),
                    "error": ai_out.get("error"),
                },
            }

    print(f"  Collecting data for {len(trades)} trades...")
    start = time.perf_counter()
    results = await asyncio.gather(*[process_trade(t) for t in trades])
    elapsed = time.perf_counter() - start
    print(f"  Done in {elapsed:.1f}s ({len(trades) / elapsed:.1f}/s)")
    return results


def analyze_results(results):
    valid = [r for r in results if r["output"].get("choice") is not None]
    errors = len(results) - len(valid)

    if not valid:
        return {"error": "No valid results"}

    # Choice distribution
    choice_stats = {}
    for c in [1, 2, 3, 4]:
        subset = [r for r in valid if r["ground_truth"].get("choice") == c]
        wins = [r for r in subset if r["ground_truth"]["was_winner"]]
        pnl = sum(r["ground_truth"]["pnl_pct"] for r in subset)
        choice_stats[c] = {
            "count": len(subset),
            "wins": len(wins),
            "losses": len(subset) - len(wins),
            "win_rate": len(wins) / len(subset) if subset else 0,
            "pnl": pnl,
        }

    correct = [r for r in valid if r["ground_truth"].get("decision_correct")]
    takes = [r for r in valid if r["ground_truth"].get("would_take")]
    skips = [r for r in valid if not r["ground_truth"].get("would_take")]

    take_wins = [r for r in takes if r["ground_truth"]["was_winner"]]
    skip_losses = [r for r in skips if not r["ground_truth"]["was_winner"]]

    take_pnl = sum(r["ground_truth"]["pnl_pct"] for r in takes)
    skip_pnl = sum(r["ground_truth"]["pnl_pct"] for r in skips)
    total_pnl = sum(r["ground_truth"]["pnl_pct"] for r in valid)

    agent_expectancy = total_pnl / len(valid)
    ai_expectancy = take_pnl / len(takes) if takes else 0

    winners = [r for r in valid if r["ground_truth"]["was_winner"]]
    losers = [r for r in valid if not r["ground_truth"]["was_winner"]]

    confs = [r["output"]["confidence"] for r in valid if r["output"].get("confidence") is not None]

    return {
        "total": len(valid),
        "errors": errors,
        "takes": len(takes),
        "skips": len(skips),
        "accuracy": len(correct) / len(valid),
        "agent_pnl": total_pnl,
        "agent_expectancy": agent_expectancy,
        "ai_take_pnl": take_pnl,
        "ai_skip_pnl": skip_pnl,
        "ai_expectancy": ai_expectancy,
        "take_win_rate": len(take_wins) / len(takes) if takes else 0,
        "skip_loss_rate": len(skip_losses) / len(skips) if skips else 0,
        "choice_stats": choice_stats,
        "conf_range": (min(confs), max(confs)) if confs else (0, 0),
        "avg_confidence": sum(confs) / len(confs) if confs else 0,
        "conf_winners": sum(r["output"]["confidence"] for r in winners if r["output"].get("confidence")) / len(winners)
        if winners
        else 0,
        "conf_losers": sum(r["output"]["confidence"] for r in losers if r["output"].get("confidence")) / len(losers)
        if losers
        else 0,
    }


def print_results(analysis, model):
    print(f"\n{'=' * 70}")
    print(f"MODEL: {model}")
    print(f"{'=' * 70}")

    print(f"\nSAMPLE: {analysis['total']} trades, {analysis['errors']} errors")

    print("\nAGENT BASELINE (took everything):")
    print(f"  Net P&L: {analysis['agent_pnl']:.1f}%")
    print(f"  Expectancy: {analysis['agent_expectancy']:.2f}%/trade")

    # Choice distribution
    choice_labels = {1: "BUY-HI", 2: "BUY-LO", 3: "SELL-LO", 4: "SELL-HI"}
    print("\nCHOICE DISTRIBUTION:")
    print(f"  {'Choice':<12} {'Count':>6} {'Wins':>6} {'Losses':>6} {'WinRate':>8} {'PnL':>10}")
    print(f"  {'-' * 52}")
    for c in [1, 2, 3, 4]:
        stats = analysis["choice_stats"].get(c, {})
        label = choice_labels[c]
        count = stats.get("count", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        wr = stats.get("win_rate", 0)
        pnl = stats.get("pnl", 0)
        print(f"  {label:<12} {count:>6} {wins:>6} {losses:>6} {wr:>7.1%} {pnl:>+9.1f}%")

    print("\nAI FILTERED (choices 1,2 = TAKE):")
    print(f"  Takes: {analysis['takes']} | Skips: {analysis['skips']}")
    print(f"  Take P&L: {analysis['ai_take_pnl']:.1f}%")
    print(f"  Skip P&L: {analysis['ai_skip_pnl']:.1f}% (avoided)")
    print(f"  AI Expectancy: {analysis['ai_expectancy']:.2f}%/trade")

    print("\nDECISION QUALITY:")
    print(f"  Overall Accuracy: {analysis['accuracy']:.1%}")
    print(f"  Take Win Rate: {analysis['take_win_rate']:.1%}")
    print(f"  Skip Loss Rate: {analysis['skip_loss_rate']:.1%}")

    print("\nCALIBRATION:")
    conf_min, conf_max = analysis.get("conf_range", (0, 0))
    print(f"  Confidence Range: {conf_min:.2f} - {conf_max:.2f}")
    print(f"  Avg Confidence: {analysis['avg_confidence']:.2f}")
    print(f"  Conf on Winners: {analysis['conf_winners']:.2f}")
    print(f"  Conf on Losers: {analysis['conf_losers']:.2f}")

    print(f"\n{'-' * 70}")
    if analysis["ai_skip_pnl"] < 0:
        print(f"[GOOD] AI skipped net losers: {analysis['ai_skip_pnl']:.1f}%")
    else:
        print(f"[BAD] AI skipped profitable trades: {analysis['ai_skip_pnl']:.1f}%")

    if analysis["ai_expectancy"] > analysis["agent_expectancy"]:
        improvement = analysis["ai_expectancy"] - analysis["agent_expectancy"]
        print(f"[GOOD] AI improved expectancy by {improvement:.2f}%/trade")
    else:
        decline = analysis["agent_expectancy"] - analysis["ai_expectancy"]
        print(f"[BAD] AI reduced expectancy by {decline:.2f}%/trade")


async def main():
    print("=" * 70)
    print("AI Training Data Collection")
    print("=" * 70)

    trades = load_trades()
    print(f"\nLoaded {len(trades)} trades with full context")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{VLLM_URL}/v1/models", timeout=5.0)
            model = resp.json()["data"][0]["id"]
            print(f"[OK] Model: {model}")
    except:
        print("[X] vLLM not running")
        return

    results = await collect_data(trades, model)
    analysis = analyze_results(results)
    print_results(analysis, model)

    output_dir = Path(__file__).parent.parent / "data"
    training_file = output_dir / "ai_training_dataset.json"
    with open(training_file, "w") as f:
        json.dump(
            {
                "model": model,
                "collected_at": datetime.now().isoformat(),
                "total_samples": len(results),
                "analysis": analysis,
                "samples": results,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nTraining dataset saved: {training_file}")

    choice_labels = {1: "BUY-HI", 2: "BUY-LO", 3: "SELL-LO", 4: "SELL-HI"}
    print(f"\n{'=' * 70}")
    print("SAMPLE ENTRIES")
    print(f"{'=' * 70}")
    for i, r in enumerate(results[:5]):
        print(f"\n--- Example {i + 1} ---")
        choice = r["output"].get("choice", 0)
        choice_label = choice_labels.get(choice, "???")
        print(f"Symbol: {r['input']['symbol']} | Sentiment: {r['input'].get('sentiment', 'N/A')}")
        print(f"Choice: {choice} ({choice_label}) | Confidence: {r['output'].get('confidence', 0):.2f}")
        print(
            f"Actual: {'WIN' if r['ground_truth']['was_winner'] else 'LOSS'} | PnL: {r['ground_truth']['pnl_pct']:.1f}%"
        )
        print(f"Reasoning: {(r['output'].get('reasoning') or '')[:120]}...")


if __name__ == "__main__":
    asyncio.run(main())
