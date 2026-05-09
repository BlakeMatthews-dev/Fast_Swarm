# Technical Indicator Dictionary

> **Purpose:** Educational reference explaining what indicators measure and represent.
> This is NOT a trading guide - it explains the math and market dynamics behind each indicator.

---

## Momentum Oscillators

### RSI (Relative Strength Index) - `rsi_7`, `rsi_14`, `rsi_21`

**What it measures:** The ratio of recent upward price movements to total price movement magnitude.

**Mathematical basis:**
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss over N periods
```

**What values represent:**
- **0-30:** Recent price action has been predominantly downward. Sellers have been in control.
- **30-70:** Mixed price action. Neither buyers nor sellers dominating.
- **70-100:** Recent price action has been predominantly upward. Buyers have been in control.

**The number (7, 14, 21):** How many periods are averaged. Smaller = more reactive to recent moves. Larger = smoother, slower to change.

**Market dynamics:** RSI reflects the balance of buying vs selling pressure over the lookback period. Extreme values indicate one side has dominated recently, which may or may not continue.

---

### Stochastic Oscillator - `stoch_k`, `stoch_d`

**What it measures:** Where the current close sits relative to the high-low range over N periods.

**Mathematical basis:**
```
%K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
%D = 3-period SMA of %K
```

**What values represent:**
- **0-20:** Price is near the bottom of its recent range.
- **20-80:** Price is somewhere in the middle of its recent range.
- **80-100:** Price is near the top of its recent range.

**Market dynamics:** Shows whether price is closing near the highs or lows of recent trading. A stock can close at the top of its range in both uptrends and downtrends.

---

### CCI (Commodity Channel Index) - `cci_14`, `cci_20`

**What it measures:** How far price has deviated from its statistical mean, normalized by mean deviation.

**Mathematical basis:**
```
CCI = (Typical Price - SMA) / (0.015 * Mean Deviation)
Typical Price = (High + Low + Close) / 3
```

**What values represent:**
- **Below -100:** Price is significantly below its recent average (> 1.5 standard deviations).
- **-100 to +100:** Price is within normal statistical range of its recent average.
- **Above +100:** Price is significantly above its recent average (> 1.5 standard deviations).

**Market dynamics:** Identifies when price has moved unusually far from its mean. The 0.015 constant is designed so roughly 70-80% of values fall between -100 and +100.

---

## Trend Indicators

### MACD (Moving Average Convergence Divergence) - `macd_line`, `macd_signal`, `macd_histogram`

**What it measures:** The relationship between two exponential moving averages of different lengths.

**Mathematical basis:**
```
MACD Line = EMA(12) - EMA(26)
Signal Line = EMA(9) of MACD Line
Histogram = MACD Line - Signal Line
```

**What values represent:**
- **MACD Line positive:** Short-term average is above long-term average (recent prices higher than older prices).
- **MACD Line negative:** Short-term average is below long-term average (recent prices lower than older prices).
- **Histogram positive:** MACD Line is above Signal Line (momentum is increasing).
- **Histogram negative:** MACD Line is below Signal Line (momentum is decreasing).

**Crossovers:**
- **MACD crosses above Signal:** Short-term momentum is accelerating relative to medium-term.
- **MACD crosses below Signal:** Short-term momentum is decelerating relative to medium-term.

**Market dynamics:** MACD captures the relationship between fast and slow price momentum. When they converge, momentum is neutral. When they diverge, one timeframe's momentum is stronger.

---

### ADX (Average Directional Index) - `adx_14`, `adx_20`

**What it measures:** The strength of a trend, regardless of its direction.

**Mathematical basis:**
```
+DI = (Smoothed +DM / ATR) * 100
-DI = (Smoothed -DM / ATR) * 100
DX = |+DI - -DI| / (+DI + -DI) * 100
ADX = Smoothed average of DX
```

**What values represent:**
- **0-20:** Weak or absent trend. Price is moving sideways or choppy.
- **20-40:** Trend is present and developing.
- **40-60:** Strong trend in effect.
- **60+:** Very strong trend (relatively rare).

**Critical concept:** ADX measures trend STRENGTH, not direction. ADX of 50 means "strong trend" - it doesn't say whether that trend is up or down. Use price action or +DI/-DI to determine direction.

**Market dynamics:** High ADX means price is moving consistently in one direction. Low ADX means price is oscillating without clear direction.

---

### Supertrend - `supertrend`, `supertrend_direction`

**What it measures:** A trend-following indicator that uses ATR to set dynamic support/resistance levels.

**Mathematical basis:**
```
Basic Upper Band = (High + Low) / 2 + (Multiplier * ATR)
Basic Lower Band = (High + Low) / 2 - (Multiplier * ATR)
Direction flips when price crosses the band
```

**What values represent:**
- **Direction +1:** Price is above the lower band; indicator considers trend bullish.
- **Direction -1:** Price is below the upper band; indicator considers trend bearish.
- **Direction 0:** Neutral/undefined state.

**The supertrend value:** The actual band level that would trigger a direction change if crossed.

**Market dynamics:** Supertrend adapts to volatility via ATR. In high volatility, bands are wider (requires larger moves to flip). In low volatility, bands are tighter.

---

## Volatility Indicators

### ATR (Average True Range) - `atr_14`, `atr_20`

**What it measures:** The average range of price movement per period, accounting for gaps.

**Mathematical basis:**
```
True Range = max(High - Low, |High - Previous Close|, |Low - Previous Close|)
ATR = Smoothed average of True Range over N periods
```

**What values represent:**
- ATR is in price units (e.g., ATR of 2.5 on a $100 stock means average $2.50 range per bar).
- Higher ATR = more volatile, larger typical price swings.
- Lower ATR = less volatile, smaller typical price swings.

**Market dynamics:** ATR expands during active/volatile periods and contracts during quiet periods. It doesn't indicate direction - a stock dropping 5% daily has high ATR just like one rising 5% daily.

**Common uses:** Position sizing (smaller positions when ATR is high), stop-loss placement (stops wider in high ATR environments).

---

### Bollinger Bands - `bb_upper`, `bb_lower`, `bb_middle`

**What it measures:** Statistical bands around a moving average showing where price "usually" trades.

**Mathematical basis:**
```
Middle Band = SMA(20)
Upper Band = SMA(20) + (2 * Standard Deviation)
Lower Band = SMA(20) - (2 * Standard Deviation)
```

**What values represent:**
- **Price at upper band:** Price is ~2 standard deviations above its recent average.
- **Price at lower band:** Price is ~2 standard deviations below its recent average.
- **Band width:** How volatile price has been. Wide bands = high volatility. Narrow bands = low volatility.

**Statistical context:** By normal distribution properties, ~95% of prices should fall within 2 standard deviations. However, markets are not normally distributed - fat tails are common.

**Market dynamics:** Bands expand during volatile periods and contract during quiet periods. Price touching a band doesn't automatically mean reversal - in strong trends, price can "walk the band" for extended periods.

---

## Volume Indicators

### OBV (On-Balance Volume) - `obv`

**What it measures:** Cumulative volume that adds volume on up days and subtracts on down days.

**Mathematical basis:**
```
If Close > Previous Close: OBV = Previous OBV + Volume
If Close < Previous Close: OBV = Previous OBV - Volume
If Close = Previous Close: OBV = Previous OBV
```

**What values represent:**
- **Rising OBV:** More volume occurring on up days than down days (accumulation).
- **Falling OBV:** More volume occurring on down days than up days (distribution).

**Market dynamics:** OBV attempts to show whether volume is flowing into (buying) or out of (selling) an asset. The absolute value is less important than the direction and divergences from price.

---

## Sentiment Indicators

### Fear and Greed Index - `fear_greed`

**What it measures:** Aggregate market sentiment derived from multiple market factors.

**Components typically include:**
- Market momentum (S&P 500 vs 125-day average)
- Stock price strength (52-week highs vs lows)
- Stock price breadth (advancing vs declining volume)
- Put/Call ratio
- VIX (market volatility)
- Safe haven demand (bonds vs stocks)
- Junk bond demand (yield spreads)

**What values represent:**
- **0-25:** Extreme Fear - Investors are very worried, selling pressure high.
- **25-45:** Fear - Investors are cautious.
- **45-55:** Neutral - Mixed sentiment.
- **55-75:** Greed - Investors are optimistic, buying pressure high.
- **75-100:** Extreme Greed - Investors are very confident, potentially complacent.

**Market dynamics:** Sentiment is a contrarian indicator in theory (extreme fear = potential bottom, extreme greed = potential top) but trends can persist at extremes for extended periods.

---

## Indicator Combinations

**CRITICAL: Single indicators mean little. Combinations tell the story.**

### Oversold Combinations

| Combination | What it Means | Implication |
|-------------|---------------|-------------|
| RSI < 30 + Stoch < 20 | Double oversold confirmation | Strong reversal probability |
| RSI < 25 + Stoch < 10 | Extreme oversold / capitulation | Very high bounce probability |
| Stoch < 10 alone | Price at bottom 10% of recent range | Sellers exhausted at this level |
| Stoch < 5 | Price essentially at the floor | Rare - often marks local bottom |

### Oversold + Trend Context

| Combination | What it Means | Implication |
|-------------|---------------|-------------|
| Oversold + ADX < 20 | Dip in ranging market | High probability of mean reversion |
| Oversold + ADX > 40 | Strong trend pushed it down | Could snap back violently OR continue |
| Oversold + Bearish Supertrend | Trend caused the oversold condition | Explains WHY oversold, not additional negative |
| Oversold + Bearish MACD | Momentum drove it down | The selling that caused oversold, not new info |

### Oversold + Sentiment

| Combination | What it Means | Implication |
|-------------|---------------|-------------|
| Oversold + Extreme Fear | Panic selling / capitulation | Often marks bottoms |
| Oversold + Extreme Greed | Dip in bull market | "Buy the dip" opportunity |
| Oversold + Neutral sentiment | Normal pullback | Standard mean reversion setup |

### Overbought Combinations

| Combination | What it Means | Implication |
|-------------|---------------|-------------|
| RSI > 70 + Stoch > 80 | Double overbought | Pullback likely |
| Overbought + Extreme Greed | Euphoria / blow-off top risk | High risk of reversal |
| Overbought + ADX > 40 | Strong uptrend | Can stay overbought longer |

### MACD Context

| Combination | What it Means | Implication |
|-------------|---------------|-------------|
| Bearish MACD + Oversold | Momentum down, price at lows | Selling may be exhausted |
| Bullish MACD crossover + Oversold | Momentum turning while still low | Early reversal signal |
| MACD divergence (price lower, MACD higher) | Momentum not confirming price | Reversal warning |

---

## Key Concept: Indicators Explain, Not Compound

**CRITICAL UNDERSTANDING:**

When you see oversold RSI + oversold Stoch + bearish MACD + bearish Supertrend, these are NOT four separate reasons to avoid the trade.

They are ONE story: "Price has fallen significantly and is now at depressed levels."

- The bearish MACD explains WHY price fell
- The bearish Supertrend confirms the down move happened
- The oversold RSI/Stoch show WHERE price ended up (at lows)

The question is: "Now that price is at these lows, what happens next?" - NOT "How many bearish signals can I count?"

---

## Indicator Relationships

### Confirming vs Diverging Signals

When multiple indicators point the same direction, they are **confirming**:
- RSI oversold + Stochastic oversold + Price at lower Bollinger Band = Multiple measures agree price has fallen significantly.

When indicators disagree, they are **diverging**:
- Price making new lows but RSI making higher lows = Momentum is not confirming the price move. This is a BULLISH divergence suggesting reversal.

### Trend vs Mean-Reversion Context

The same indicator reading has different implications depending on market context:

**In strong trends (high ADX > 40):**
- Oscillators can stay at extremes for extended periods
- BUT extreme oversold (Stoch < 10) often still bounces

**In ranging markets (low ADX < 20):**
- Oscillators reliably revert from extremes
- Oversold + low ADX = high probability mean reversion

### Timeframe Considerations

Indicator periods (7, 14, 21, etc.) determine sensitivity:
- **Shorter periods:** More signals, more false positives, react faster
- **Longer periods:** Fewer signals, more reliable, react slower

---

*This dictionary explains what indicators measure. Trading decisions require judgment about context, risk, and probability - not mechanical rules.*
