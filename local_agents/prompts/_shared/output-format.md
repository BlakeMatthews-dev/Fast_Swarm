# Output Format

Respond with valid JSON only. No markdown code blocks, no explanation outside the JSON.

```json
{
    "choice": "SB" | "B" | "S" | "SS",
    "reasoning": "Brief explanation referencing key indicators"
}
```

Where:
- **SB** = STRONG BUY - Extreme oversold, high reversal probability
- **B** = BUY - Oversold with moderate edge
- **S** = SKIP - Neutral or mixed, no clear edge
- **SS** = STRONG SKIP - Overbought, poor risk/reward

---

## Key Indicator Correlations (from historical data)

**Lower values = BETTER for long entries:**
- Stoch_K: High MFE avg=11, Low MFE avg=92
- WillR_14: High MFE avg=-89, Low MFE avg=-6
- RSI_7: High MFE avg=21, Low MFE avg=76
- StochRSI: High MFE avg=12, Low MFE avg=89
- MFI_14: High MFE avg=18, Low MFE avg=67
- UO: High MFE avg=22, Low MFE avg=73

**Aroon_Down higher = BETTER** (confirms downtrend exhaustion)

---

## REAL EXAMPLES (from actual trades)

### STRONG BUY (SB) - Extreme oversold, 19.3% MFE

**COMP @ 2025-12-22** - Entry at crash bottom
```
RSI_14=13.5, RSI_7=4.3, Stoch_K=23.7, StochRSI_K=0, WillR=-100
MFI=43, CMO=-73, TSI=-21, UO=3, ROC=-11.3
ADX=36, Plus_DI=17.7, Minus_DI=48.5, Aroon_Down=100
BB_pct=0.0, ATR_pct=8.2%, Supertrend=-1
```
```json
{"choice": "SB", "reasoning": "RSI 13.5 extremely oversold, Stoch 24 at lows, WillR -100 at floor. MFI 43 shows selling exhaustion despite panic. Aroon_Down 100 confirms extended downtrend ready to reverse. BB_pct 0 = price at lower band. All momentum indicators at extremes. Historical setups like this average 19% MFE."}
```

### STRONG BUY (SB) - Capitulation bottom, 18.7% MFE

**SEI @ 2025-12-23** - After 10% crash
```
RSI_14=24.6, RSI_7=7.8, Stoch_K=0, StochRSI_K=0, WillR=-100
MFI=0, CMO=-51, TSI=-35, UO=4, ROC=-9.9
ADX=33, Plus_DI=20, Minus_DI=45, Aroon_Down=100
BB_pct=0.05, Supertrend=-1
```
```json
{"choice": "SB", "reasoning": "Stoch_K 0 and StochRSI 0 - can't go lower. RSI_7 at 7.8 is extreme capitulation. MFI 0 = complete selling exhaustion. TSI -35 deeply negative. All oscillators at absolute floors. This is maximum fear - strong buy signal."}
```

### BUY (B) - Moderate oversold, 2.2% MFE

**BTC @ 2025-12-25** - Pullback in range
```
RSI_14=46.9, RSI_7=38.3, Stoch_K=42.1, StochRSI_K=24.3, WillR=-69
MFI=36, CMO=-6, TSI=9, UO=52
ADX=18, Plus_DI=21, Minus_DI=22, Aroon_Down=57
BB_pct=0.35, Supertrend=1
```
```json
{"choice": "B", "reasoning": "RSI_7 38 and Stoch 42 moderately depressed. ADX 18 shows weak/no trend - mean reversion environment. MFI 36 below neutral. BB_pct 0.35 = lower half of bands. Not extreme enough for SB, but reasonable bounce setup. Expect ~2% MFE."}
```

### BUY (B) - Mid-range dip, 2.5% MFE

**SOL @ 2025-12-25** - Consolidation pullback
```
RSI_14=46.3, RSI_7=47.2, Stoch_K=38.3, StochRSI_K=46.8, WillR=-59
MFI=43, CMO=-7, TSI=-8, UO=55
ADX=15, Aroon_Down=50
BB_pct=0.40, Supertrend=-1
```
```json
{"choice": "B", "reasoning": "Stoch 38 depressed, MFI 43 below neutral. ADX 15 very weak trend favors mean reversion. TSI slightly negative. Not oversold enough for SB but decent probability of bounce. Moderate edge present."}
```

### SKIP (S) - Mixed signals, -2.8% MFE

**NEAR @ 2025-12-22** - Overbought but not extreme
```
RSI_14=73, RSI_7=86.6, Stoch_K=97, StochRSI_K=100, WillR=-3.6
MFI=93, CMO=46, TSI=36, UO=92
ADX=47, Plus_DI=60, Minus_DI=12, Aroon_Up=100
BB_pct=0.95, Supertrend=1
```
```json
{"choice": "S", "reasoning": "RSI 73 overbought, Stoch 97 extreme. MFI 93 = buying exhaustion. However strong trend (ADX 47) can stay overbought. Skip - wrong time to enter long, but not necessarily a short. Wait for pullback."}
```

### SKIP (S) - Neutral zone, no edge

**Example neutral setup:**
```
RSI_14=52, RSI_7=50, Stoch_K=55, StochRSI_K=50, WillR=-45
MFI=50, CMO=5, TSI=2, UO=50
ADX=22, Aroon_Up=50, Aroon_Down=50
BB_pct=0.50, Supertrend=1
```
```json
{"choice": "S", "reasoning": "All indicators near 50 - perfectly neutral. No oversold condition, no edge. RSI 52, Stoch 55, MFI 50 all mid-range. Skip and wait for oscillators to reach extremes."}
```

### STRONG SKIP (SS) - At peak after rally, 0.3% MFE remaining

**COMP @ 2025-12-23** - After 19% move, at top
```
RSI_14=62.7, RSI_7=69.7, Stoch_K=85.8, StochRSI_K=87.7, WillR=-7.2
MFI=91, CMO=25, TSI=3, UO=63
ADX=36, Plus_DI=41, Minus_DI=16, Aroon_Up=93
BB_pct=0.85, Supertrend=1
```
```json
{"choice": "SS", "reasoning": "Stoch 86 overbought, MFI 91 = extreme buying exhaustion. WillR -7 near ceiling. This is AFTER a big move - only 0.3% MFE left. Aroon_Up 93 confirms extended rally. Terrible risk/reward to enter here."}
```

### STRONG SKIP (SS) - Extreme overbought, -9.7% MFE

**ENJ @ 2025-12-23** - Blow-off top
```
RSI_14=81.4, RSI_7=95.6, Stoch_K=100, StochRSI_K=83.2, WillR=0
MFI=100, CMO=63, TSI=57
ADX=58, Plus_DI=81, Minus_DI=6, Aroon_Up=100
BB_pct=1.0, Supertrend=1
```
```json
{"choice": "SS", "reasoning": "RSI 81 extreme overbought, RSI_7 at 95.6! Stoch 100, MFI 100 - literally cannot be more overbought. WillR at 0 ceiling. This is a blow-off top. Historical result: -9.7% MFE. Strong skip - do NOT buy here."}
```

### STRONG SKIP (SS) - Overbought trap, -8.2% MFE

**SEI @ 2025-12-22** - Extended rally
```
RSI_14=67.2, RSI_7=75, Stoch_K=95.6, StochRSI_K=35.6, WillR=-4.1
MFI=2, CMO=34, TSI=31, UO=94
ADX=19, Plus_DI=27, Minus_DI=19, Aroon_Up=79
BB_pct=0.92, Supertrend=1
```
```json
{"choice": "SS", "reasoning": "Stoch 96 extremely overbought, WillR -4 near ceiling. UO 94 = unsustainable buying pressure. ADX only 19 = weak trend that can't support these levels. Price likely to mean-revert hard. -8.2% historical MFE."}
```

---

**CRITICAL**: We buy at LOWS (oversold oscillators), not at highs. High RSI/Stoch/MFI = price already moved = late entry = poor risk/reward.
