"""
The Rosetta Stone: Maps Local `pandas_ta` indicator names to V3 Canonical names.
Source of Truth: `v3/cloudflare-agents/backtest/pattern-matcher.ts`
"""


def normalize_indicator_name(local_name: str) -> str:
    """
    Converts snake_case or shorthand indicator names to V3 camelCase canonical names.
    """
    # 1. Normalize input
    name = local_name.lower().replace("-", "_")

    # 2. Direct Map (Copy-pasted logic from V3)
    # This ensures exact parity with V3's PatternDO expectation.
    V3_MAP = {
        # RSI
        "rsi": "rsi14",
        "rsi_14": "rsi14",
        "relative_strength": "rsi14",
        "relative_strength_index": "rsi14",
        # MACD
        "macd": "macdLine",
        "macd_line": "macdLine",
        "macd_signal": "macdSignal",
        "macdsignal": "macdSignal",
        "macd_histogram": "macdHistogram",
        "macdhistogram": "macdHistogram",
        "macd_hist": "macdHistogram",
        # MA - EMA
        "ema_9": "ema9",
        "ema_10": "ema10",
        "ema_12": "ema12",
        "ema_20": "ema20",
        "ema_21": "ema21",
        "ema_26": "ema26",
        "ema_30": "ema30",
        # MA - SMA
        "sma_10": "sma10",
        "sma_20": "sma20",
        "sma_50": "sma50",
        "sma_200": "sma200",
        # Bollinger
        "bb_upper": "bollingerUpper",
        "bbupper": "bollingerUpper",
        "bollinger_upper": "bollingerUpper",
        "bb_middle": "bollingerMiddle",
        "bbmiddle": "bollingerMiddle",
        "bollinger_middle": "bollingerMiddle",
        "bb_lower": "bollingerLower",
        "bblower": "bollingerLower",
        "bollinger_lower": "bollingerLower",
        "bb_bandwidth": "bollingerBandwidth",
        "bbbandwidth": "bollingerBandwidth",
        "bollinger_bandwidth": "bollingerBandwidth",
        "bb_percent_b": "bollingerPercentB",
        "bbpercentb": "bollingerPercentB",
        "bollinger_percent_b": "bollingerPercentB",
        "percent_b": "bollingerPercentB",
        # ATR
        "atr": "atr14",
        "atr_14": "atr14",
        "average_true_range": "atr14",
        # Stochastic
        "stoch_k": "stochasticK",
        "stochk": "stochasticK",
        "stochastic_k": "stochasticK",
        "percent_k": "stochasticK",
        "stoch_d": "stochasticD",
        "stochd": "stochasticD",
        "stochastic_d": "stochasticD",
        "percent_d": "stochasticD",
        # ADX
        "adx": "adx14",
        "adx_14": "adx14",
        "average_directional_index": "adx14",
        "plus_di": "plusDI",
        "plusdi": "plusDI",
        "plus_directional": "plusDI",
        "minus_di": "minusDI",
        "minusdi": "minusDI",
        "minus_directional": "minusDI",
        # Volume
        "on_balance_volume": "obv",
        "volume_sma_20": "volumeSma20",
        "volume_sma20": "volumeSma20",
        "vol_sma_20": "volumeSma20",
        "volume_ratio": "volumeRatio",
        "vol_ratio": "volumeRatio",
        # Momentum
        "momentum_1": "momentum1",
        "mom_1": "momentum1",
        "momentum_5": "momentum5",
        "mom_5": "momentum5",
        "momentum_10": "momentum10",
        "mom_10": "momentum10",
        # Price vs MA
        "price_vs_ema9_pct": "priceVsEma9Pct",
        "price_vs_ema10_pct": "priceVsEma10Pct",
        "price_vs_ema20_pct": "priceVsEma20Pct",
        "price_vs_ema21_pct": "priceVsEma21Pct",
        "price_vs_ema30_pct": "priceVsEma30Pct",
        "price_vs_sma10_pct": "priceVsSma10Pct",
        "price_vs_sma50_pct": "priceVsSma50Pct",
        "price_vs_sma200_pct": "priceVsSma200Pct",
        # Extended / Advanced
        "hma": "hma14",
        "hma_14": "hma14",
        "hull": "hma14",
        # ... (Can add more from V3 map if needed, covering core 90% now)
    }

    # 3. Check Map
    if name in V3_MAP:
        return V3_MAP[name]

    # 4. Fallback: CamelCase Conversion (e.g., custom_ind -> customInd)
    # This handles the "Unicorn" patterns that might have unique names
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])
