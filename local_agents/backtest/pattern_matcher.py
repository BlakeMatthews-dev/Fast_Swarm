"""
Pattern Matching for Backtesting.

Evaluates pattern conditions against candle data using the confidence system.

MERGED FROM: local-utilities/metrics/pattern_matcher.py
This is the CANONICAL pattern matcher for Coinswarm.

Features:
- ~250+ indicator aliases (camelCase, snake_case, pandas_ta, PostgreSQL)
- COMPUTED_INDICATORS set for derived indicators
- INDICATOR_CANONICAL reverse mapping
- Confidence scoring via MatchResult
- Fuzzy period matching (finds ema_21 when ema_20 requested)
"""

import math
import re
from dataclasses import dataclass

from Fast_Swarm.local_agents.shared.confidence import (
    evaluate_condition_confidence,
)

# =============================================================================
# Indicator Name Mapping (V3 Canonical → pandas_ta → PostgreSQL enhanced_candles)
#
# MERGED FROM: local-utilities/metrics/pattern_matcher.py (~340 aliases)
# This is the CANONICAL indicator alias mapping for Coinswarm.
# =============================================================================

INDICATOR_ALIASES = {
    # =========================================================================
    # Momentum Indicators
    # =========================================================================
    "rsi14": "rsi_14",
    "rsi": "rsi_14",
    "rsi7": "rsi_7",
    "rsi21": "rsi_21",
    "RSI_14": "rsi_14",
    "RSI_7": "rsi_7",
    "RSI_21": "rsi_21",
    "macdLine": "macd_line",
    "macdSignal": "macd_signal",
    "macdHistogram": "macd_histogram",
    "MACD_12_26_9": "macd_line",
    "MACDs_12_26_9": "macd_signal",
    "MACDh_12_26_9": "macd_histogram",
    "stochasticK": "stoch_k",
    "stochasticD": "stoch_d",
    "stochK": "stoch_k",
    "stochD": "stoch_d",
    "STOCHk_14_3_3": "stoch_k",
    "STOCHd_14_3_3": "stoch_d",
    "STOCH_K": "stoch_k",
    "STOCH_D": "stoch_d",
    "williamsR": "willr_14",
    "willr": "willr_14",
    "WILLR_14": "willr_14",
    "mfi14": "mfi_14",
    "mfi": "mfi_14",
    "MFI_14": "mfi_14",
    "mfiVolume": "mfi_14",
    "ultimateOsc": "uo",
    "ultimateOscillator": "uo",
    "uo": "uo",
    "UO_7_14_28": "uo",
    "roc10": "roc_10",
    "roc": "roc_10",
    "ROC_10": "roc_10",
    "momentum": "mom_10",
    "momentum1": "mom_10",
    "momentum5": "mom_10",
    "momentum10": "mom_10",
    "mom": "mom_10",
    "MOM_10": "mom_10",
    "cmo14": "cmo_14",
    "cmo": "cmo_14",
    "CMO_14": "cmo_14",
    "cci20": "cci_14",
    "cci": "cci_14",
    "CCI_14": "cci_14",
    "CCI_20": "cci_20",
    "CCI_14_0.015": "cci_14",
    "bop": "bop",
    "BOP": "bop",
    "ao": "ao",
    "AO_5_34": "ao",
    "apo": "apo",
    "APO_12_26": "apo",
    # =========================================================================
    # Trend Indicators
    # =========================================================================
    "adx14": "adx_14",
    "adx": "adx_14",
    "ADX_14": "adx_14",
    "plusDI": "plus_di",
    "minusDI": "minus_di",
    "DMP_14": "plus_di",
    "DMN_14": "minus_di",
    "aroonUp": "aroon_up",
    "aroonDown": "aroon_down",
    "aroonOsc": "aroon_osc",
    "AROONU_14": "aroon_up",
    "AROOND_14": "aroon_down",
    "AROONOSC_14": "aroon_osc",
    "choppiness": "chop",
    "chop": "chop",
    "CHOP_14_1_100.0": "chop",
    "dpo": "dpo",
    "DPO_14": "dpo",
    "DPO_20": "dpo",
    # =========================================================================
    # Volatility Indicators
    # =========================================================================
    "atr14": "atr_14",
    "atr": "atr_14",
    "ATRr_14": "atr_14",
    "natr14": "natr_14",
    "natr": "natr_14",
    "NATR_14": "natr_14",
    "bollingerBandwidth": "bb_width",
    "bollingerPercentB": "bb_percent",
    "bbBandwidth": "bb_width",
    "bbPercentB": "bb_percent",
    "bbUpper": "bb_upper",
    "bbLower": "bb_lower",
    "bbMiddle": "bb_middle",
    "BBB_5_2.0_2.0": "bb_width",
    "BBP_5_2.0_2.0": "bb_percent",
    "BBU_5_2.0_2.0": "bb_upper",
    "BBL_5_2.0_2.0": "bb_lower",
    "BBM_5_2.0_2.0": "bb_middle",
    "BBW_20": "bb_width",
    "PERCENT_B": "bb_percent",
    "bb_percent_b": "bb_percent",
    "bollingerUpper": "bb_upper",
    "bollingerLower": "bb_lower",
    # =========================================================================
    # Volume Indicators
    # =========================================================================
    "ad": "ad",
    "AD": "ad",
    "adosc": "adosc",
    "ADOSC_3_10": "adosc",
    "cmf20": "cmf",
    "cmf": "cmf",
    "CMF_20": "cmf",
    "obv": "obv",
    "OBV": "obv",
    "volumeRatio": "volume_sma_20",
    "volumeSma": "volume_sma_20",
    "efi": "efi",
    "EFI_13": "efi",
    "PVT": "pvt",
    # =========================================================================
    # Moving Averages (map to PostgreSQL enhanced_candles columns)
    # =========================================================================
    "ema9": "ema_9",
    "ema10": "ema_9",  # Closest available
    "ema12": "ema_12",
    "ema20": "ema_21",  # Closest available
    "ema21": "ema_21",
    "ema26": "ema_26",
    "ema50": "sma_50",  # Use SMA as proxy
    "ema200": "sma_200",  # Use SMA as proxy
    "EMA_9": "ema_9",
    "EMA_10": "ema_9",
    "EMA_12": "ema_12",
    "EMA_20": "ema_21",
    "EMA_21": "ema_21",
    "EMA_26": "ema_26",
    "EMA_50": "sma_50",
    "EMA_200": "sma_200",
    "sma20": "sma_20",
    "sma50": "sma_50",
    "sma200": "sma_200",
    "SMA_20": "sma_20",
    "SMA_50": "sma_50",
    "SMA_200": "sma_200",
    "dema10": "dema",
    "DEMA_10": "dema",
    "DEMA_21": "dema",
    "hma16": "hma",
    "HMA_16": "hma",
    "tema10": "tema",
    "TEMA_10": "tema",
    "wma10": "wma",
    "WMA_10": "wma",
    # =========================================================================
    # Price vs MA (computed indicators - need special handling)
    # =========================================================================
    "priceVsEma10Pct": "ema_9",
    "priceVsEma20Pct": "ema_21",
    "priceVsEma50Pct": "sma_50",
    "priceVsEma200Pct": "sma_200",
    "priceVsSma20Pct": "sma_20",
    "priceVsSma50Pct": "sma_50",
    "priceVsSma200Pct": "sma_200",
    "priceVsEma": "ema_21",
    "priceVsSma": "sma_20",
    # =========================================================================
    # StochRSI
    # =========================================================================
    "stochRsi": "stochrsi_k",
    "stochRsiK": "stochrsi_k",
    "stochRsiD": "stochrsi_d",
    "STOCHRSIk_14_14_3_3": "stochrsi_k",
    "STOCHRSId_14_14_3_3": "stochrsi_d",
    # =========================================================================
    # TRIX
    # =========================================================================
    "trix": "trix",
    "trixSignal": "trix_signal",
    "TRIX_18_9": "trix",
    "TRIX_30_9": "trix",
    "TRIXs_30_9": "trix_signal",
    # =========================================================================
    # Fisher Transform
    # =========================================================================
    "fisherTransform": "fisher",
    "fisherSignal": "fisher_signal",
    "fisher": "fisher",
    "FISHERT_9": "fisher",
    "FISHERT_9_1": "fisher",
    "FISHERTs_9": "fisher_signal",
    "FISHERTs_9_1": "fisher_signal",
    # =========================================================================
    # Linear Regression
    # =========================================================================
    "linregSlope": "linreg",
    "linreg": "linreg",
    "LINREG_14": "linreg",
    # =========================================================================
    # Mass Index
    # =========================================================================
    "massIndex": "massi",
    "massi": "massi",
    "MASSI_9_25": "massi",
    # =========================================================================
    # Statistical Indicators
    # =========================================================================
    "vhf": "vhf",
    "VHF_28": "vhf",
    "entropy": "entropy",
    "ENTROPY_10": "entropy",
    "kurtosis": "kurtosis",
    "KURTOSIS_10": "kurtosis",
    "skew": "skew",
    "SKEW_10": "skew",
    "zscore": "zscore_14",
    "zscore50": "zscore_50",
    "ZSCORE_10": "zscore_14",
    "ZSCORE_20": "zscore_14",
    "ZS_20": "zscore_14",
    "ZS_30": "zscore_30",
    "ZS_50": "zscore_50",
    # =========================================================================
    # Cross-Asset Metrics
    # =========================================================================
    "btc_eth_correlation": "btc_eth_correlation_14d",
    "btcEthCorrelation": "btc_eth_correlation_14d",
    "correlation": "btc_eth_correlation_14d",
    "eth_btc_ratio": "eth_btc_ratio",
    "ethBtcRatio": "eth_btc_ratio",
    "alt_dominance": "alt_dominance_pct",
    "altDominance": "alt_dominance_pct",
    "l1_momentum": "l1_momentum_pct",
    "l1Momentum": "l1_momentum_pct",
    "defi_momentum": "defi_momentum_pct",
    "defiMomentum": "defi_momentum_pct",
    "meme_momentum": "meme_momentum_pct",
    "memeMomentum": "meme_momentum_pct",
    "market_breadth_20": "market_breadth_sma20_pct",
    "marketBreadth20": "market_breadth_sma20_pct",
    "market_breadth_50": "market_breadth_sma50_pct",
    "marketBreadth50": "market_breadth_sma50_pct",
    "assets_above_ema200": "assets_above_ema200_pct",
    "assetsAboveEma200": "assets_above_ema200_pct",
    # =========================================================================
    # Time-based Indicators
    # =========================================================================
    "dayOfWeek": "day_of_week",
    "hourOfDay": "hour_of_day",
    "hour": "hour_of_day",
    "day": "day_of_week",
    "isMonday": "is_monday",
    "isThursday": "is_thursday",
    "isUSMarketHours": "is_us_market_hours",
    "isUsMarketHours": "is_us_market_hours",
    # =========================================================================
    # Regime Indicators
    # =========================================================================
    "volatilityRegime": "regime",
    "trendRegime": "regime",
    "regime": "regime",
    # =========================================================================
    # BIAS indicator
    # =========================================================================
    "BIAS_26": "bias_26",
    "BIAS_SMA_26": "bias_26",
    "maCross": "bias_26",
    # =========================================================================
    # Cross signals (computed - use histogram as proxy)
    # =========================================================================
    "deathCross": "macd_histogram",
    "goldenCross": "macd_histogram",
    "macdBullishCross": "macd_histogram",
    "macdBearishCross": "macd_histogram",
    # =========================================================================
    # Volatility proxies
    # =========================================================================
    "cvi": "atr_14",
}

# Reverse mapping: PostgreSQL columns → canonical short names
INDICATOR_CANONICAL = {v: k for k, v in INDICATOR_ALIASES.items()}


# =============================================================================
# Computed/Derived Indicators (need special handling via compute_derived_indicator)
# =============================================================================

COMPUTED_INDICATORS = {
    # Cross conditions
    "goldenCross",
    "deathCross",
    "maCross",
    "macdCross",
    "macdBullishCross",
    "macdBearishCross",
    "stochasticCross",
    # Price vs MA conditions
    "aboveEma20",
    "aboveEma21",
    "aboveEma30",
    "aboveEma9",
    "aboveSma10",
    "aboveSma50",
    "aboveSma200",
    "priceBelowSma",
    "priceBelowEma",
    "priceAboveEma",
    "priceAboveSma",
    "priceVsEma",
    "priceVsSma",
    # Stochastic conditions
    "stochBullishCross",
    "stochBearishCross",
    "stochOversold",
    "stochOverbought",
    # RSI conditions
    "rsiOversold",
    "rsiOverbought",
    # Williams %R conditions
    "williamsOversold",
    "williamsOverbought",
    # Trend conditions
    "emaStackBullish",
    "emaStackBearish",
    "trendingUp",
    "trendingDown",
    "strongTrend",
    "weakTrend",
    # MACD conditions
    "macdPositive",
    "macd",
    # Bollinger conditions
    "bbAtUpper",
    "bbAtLower",
    "bbSqueeze",
    # Momentum conditions
    "momentumStrong",
    "momentumPositive",
    # Volume conditions
    "volumeSpike",
    "volumeDry",
    # Aroon conditions
    "aroonTrendUp",
    "aroonTrendDown",
    # Fisher conditions
    "fisherBullish",
    "fisherBearish",
    # PSAR conditions
    "psarBullish",
    # Other computed
    "atrPercent",
    "stddev20",
}


# Indicator bounds for confidence calculation
# Uses PostgreSQL enhanced_candles column names (lowercase with underscores)
INDICATOR_BOUNDS = {
    # RSI variants (0-100)
    "rsi_14": (0, 100),
    "rsi_7": (0, 100),
    "rsi_21": (0, 100),
    # Stochastic (0-100)
    "stoch_k": (0, 100),
    "stoch_d": (0, 100),
    # Stochastic RSI (0-100)
    "stochrsi_k": (0, 100),
    "stochrsi_d": (0, 100),
    # MFI (0-100)
    "mfi_14": (0, 100),
    # ADX (0-100)
    "adx_14": (0, 100),
    # Aroon (0-100)
    "aroon_up": (0, 100),
    "aroon_down": (0, 100),
    "aroon_osc": (-100, 100),
    # CMO (-100 to 100)
    "cmo_14": (-100, 100),
    # Williams %R (-100 to 0)
    "willr_14": (-100, 0),
    # CCI (typically -200 to 200)
    "cci_14": (-200, 200),
    "cci_20": (-200, 200),
    # MACD (typically -10 to 10 for most assets)
    "macd_line": (-10, 10),
    "macd_signal": (-10, 10),
    "macd_histogram": (-5, 5),
    # ROC/Momentum (typically -20 to 20)
    "roc_10": (-20, 20),
    "mom_10": (-50, 50),
    # Bollinger %B (0 to 1, can exceed)
    "bb_percent": (-0.5, 1.5),
    "bb_width": (0, 1),
    # TRIX (typically -0.5 to 0.5)
    "trix": (-0.5, 0.5),
    # DPO (typically -50 to 50)
    "dpo": (-50, 50),
    # Fisher Transform (typically -5 to 5)
    "fisher": (-5, 5),
    "fisher_signal": (-5, 5),
    # BIAS (typically -10 to 10 percent)
    "bias_26": (-10, 10),
    # ATR (typically 0 to 20 for normalized)
    "atr_14": (0, 20),
    "natr_14": (0, 20),
    # Z-Score (-3 to 3 typically)
    "zscore_14": (-3, 3),
    "zscore_30": (-3, 3),
    "zscore_50": (-3, 3),
    # Statistical (entropy, kurtosis, skew)
    "entropy": (0, 10),
    "kurtosis": (-10, 10),
    "skew": (-3, 3),
    # Ultimate Oscillator (0-100)
    "uo": (0, 100),
    # Awesome Oscillator (typically -50 to 50)
    "ao": (-50, 50),
    # Choppiness (0-100)
    "chop": (0, 100),
    # VHF (0-1)
    "vhf": (0, 1),
    # Mass Index
    "massi": (0, 40),
    # Volume (0 to very large, use relative)
    "volume": (0, 1e12),
    "volume_sma_20": (0, 1e12),
    # Default for unknown indicators
    "_default": (-100, 100),
}


def resolve_indicator(name: str, available: set[str]) -> str | None:
    """
    Resolve indicator name to actual column name.

    Tries (in order):
    1. Direct match (exact column name)
    2. Alias lookup (old name → PostgreSQL name)
    3. Case-insensitive match
    4. Snake_case conversion (camelCase → snake_case)
    5. Fuzzy period matching (ema_20 finds ema_21)

    Args:
        name: Canonical indicator name.
        available: Set of available column names.

    Returns:
        Resolved column name or None.
    """
    # Direct match
    if name in available:
        return name

    # Alias lookup
    if name in INDICATOR_ALIASES:
        alias = INDICATOR_ALIASES[name]
        if alias in available:
            return alias

    # Case-insensitive search
    name_lower = name.lower()
    for col in available:
        if col.lower() == name_lower:
            return col

    # Convert camelCase to snake_case and try again
    # aroonOsc -> aroon_osc, stochRsi -> stoch_rsi, macdLine -> macd_line
    snake_name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()
    if snake_name in available:
        return snake_name

    # Also try snake_case without trailing numbers
    for col in available:
        # Match if column starts with snake_name (handles period suffixes)
        if col.lower().startswith(snake_name):
            return col
        # Match if snake_name starts with column (handles missing periods)
        col_base = col.lower().rstrip("_0123456789")
        if snake_name.startswith(col_base) and col_base:
            return col

    # Fuzzy period matching: ema_20 might be stored as ema_21
    period_match = re.match(r"([a-z_]+)(\d+)", snake_name)
    if period_match:
        base, period = period_match.groups()
        period = int(period)
        # Try nearby periods
        for try_period in [period, period + 1, period - 1]:
            try_name = f"{base}_{try_period}"
            if try_name in available:
                return try_name

    return None


def get_indicator_bounds(indicator: str) -> tuple[float, float]:
    """Get min/max bounds for an indicator."""
    if indicator in INDICATOR_BOUNDS:
        return INDICATOR_BOUNDS[indicator]

    # Try to find by prefix
    for key, bounds in INDICATOR_BOUNDS.items():
        if indicator.startswith(key.split("_")[0]):
            return bounds

    return INDICATOR_BOUNDS["_default"]


@dataclass
class MatchResult:
    """Result of pattern matching against a candle."""

    matched: bool
    confidence: float
    conditions_met: int
    conditions_total: int
    condition_details: list[dict]

    # Aliases for test compatibility
    @property
    def passed(self) -> bool:
        return self.matched

    @property
    def overall_confidence(self) -> float:
        return self.confidence


def evaluate_conditions(
    conditions: dict[str, dict] | list[dict],
    indicators: dict[str, float],
) -> MatchResult:
    """
    Evaluate pattern entry/exit conditions against indicator values.

    Args:
        conditions: Dict of indicator -> {operator, value} conditions,
                   OR list of {indicator, operator, value} dicts.
        indicators: Dict of indicator -> current value.

    Returns:
        MatchResult with confidence and condition details.

    Example (dict format):
        conditions = {
            'rsi14': {'operator': '<', 'value': 30},
            'macdHistogram': {'operator': '>', 'value': 0},
        }

    Example (list format from database):
        conditions = [
            {'indicator': 'rsi14', 'operator': '<', 'value': 30},
            {'indicator': 'macdHistogram', 'operator': '>', 'value': 0},
        ]
    """
    if not conditions:
        return MatchResult(
            matched=False,
            confidence=0.0,
            conditions_met=0,
            conditions_total=0,
            condition_details=[],
        )

    # Convert list format to dict format if needed
    if isinstance(conditions, list):
        conditions_dict = {}
        for cond in conditions:
            if isinstance(cond, dict) and "indicator" in cond:
                indicator_name = cond["indicator"]
                conditions_dict[indicator_name] = {
                    "operator": cond.get("operator", ">"),
                    "value": cond.get("value", cond.get("threshold", 0)),
                }
        conditions = conditions_dict

    available = set(indicators.keys())
    details = []
    confidences = []
    met_count = 0

    for indicator_name, condition in conditions.items():
        operator = condition.get("operator", ">")
        threshold = condition.get("value", condition.get("threshold", 0))

        # Resolve indicator name
        resolved = resolve_indicator(indicator_name, available)

        if resolved is None:
            details.append(
                {
                    "indicator": indicator_name,
                    "status": "missing",
                    "confidence": None,
                }
            )
            continue

        current_value = indicators.get(resolved)

        if current_value is None or (isinstance(current_value, float) and math.isnan(current_value)):
            details.append(
                {
                    "indicator": indicator_name,
                    "resolved": resolved,
                    "status": "nan",
                    "confidence": None,
                }
            )
            continue

        # Get bounds for confidence calculation
        min_val, max_val = get_indicator_bounds(resolved)

        # Handle string/categorical thresholds (e.g., 'high', 'uptrend')
        # These can't be numerically compared - skip them
        if isinstance(threshold, str):
            details.append(
                {
                    "indicator": indicator_name,
                    "resolved": resolved,
                    "status": "categorical",
                    "threshold": threshold,
                    "confidence": None,
                }
            )
            continue

        # Handle 'between' operator
        if operator == "between" and isinstance(threshold, (list, tuple)) and len(threshold) == 2:
            threshold_tuple = (float(threshold[0]), float(threshold[1]))
        else:
            threshold_tuple = threshold

        # Calculate confidence
        conf = evaluate_condition_confidence(
            operator=operator,
            value=current_value,
            threshold=threshold_tuple,
            indicator_min=min_val,
            indicator_max=max_val,
        )

        # Condition is "met" only if confidence >= 0.1 (inside threshold)
        # Values below 0.1 are in the decay zone (outside threshold)
        # The confidence system uses 0.1 as the base for inside-threshold values
        is_met = conf is not None and conf >= 0.1

        if is_met:
            met_count += 1
            confidences.append(conf)

        details.append(
            {
                "indicator": indicator_name,
                "resolved": resolved,
                "operator": operator,
                "threshold": threshold,
                "value": current_value,
                "confidence": conf,
                "met": is_met,
            }
        )

    # Calculate overall confidence
    if confidences:
        overall_confidence = sum(confidences) / len(confidences)
    else:
        overall_confidence = 0.0

    # Pattern matches if all conditions are met
    total_conditions = len([d for d in details if d.get("status") not in ("missing", "nan")])
    matched = met_count == total_conditions and total_conditions > 0

    return MatchResult(
        matched=matched,
        confidence=overall_confidence,
        conditions_met=met_count,
        conditions_total=total_conditions,
        condition_details=details,
    )


class PatternMatcher:
    """
    Matches patterns against candle data.

    Handles both entry and exit conditions.
    """

    def __init__(
        self,
        pattern: dict | None = None,
        entry_conditions: dict[str, dict] | None = None,
        exit_conditions: dict[str, dict] | None = None,
        direction: str = "long",
        min_confidence: float = 0.3,
    ):
        """
        Initialize pattern matcher.

        Args:
            pattern: Pattern dict with entry_conditions, exit_conditions, etc.
            entry_conditions: Conditions for entering a trade (overrides pattern).
            exit_conditions: Conditions for exiting (overrides pattern).
            direction: "long" or "short".
            min_confidence: Minimum confidence to trigger entry.
        """
        # Support both pattern dict and direct conditions
        if pattern:
            self.pattern_id = pattern.get("pattern_id", "unknown")
            self.entry_conditions = entry_conditions or pattern.get("entry_conditions", pattern.get("conditions", {}))
            self.exit_conditions = exit_conditions or pattern.get("exit_conditions", {})
            self.direction = pattern.get("direction", direction)
        else:
            self.pattern_id = "unknown"
            self.entry_conditions = entry_conditions or {}
            self.exit_conditions = exit_conditions or {}
            self.direction = direction

        self.min_confidence = min_confidence

    def check_entry(self, indicators: dict[str, float]) -> MatchResult:
        """Check if entry conditions are met."""
        return evaluate_conditions(self.entry_conditions, indicators)

    def check_exit(self, indicators: dict[str, float]) -> MatchResult:
        """Check if exit conditions are met."""
        if not self.exit_conditions:
            return MatchResult(
                matched=False,
                confidence=0.0,
                conditions_met=0,
                conditions_total=0,
                condition_details=[],
            )
        return evaluate_conditions(self.exit_conditions, indicators)

    def should_enter(self, indicators: dict[str, float]) -> tuple[bool, float]:
        """
        Check if we should enter a trade.

        Returns:
            Tuple of (should_enter, confidence).
        """
        result = self.check_entry(indicators)
        should_enter = result.matched and result.confidence >= self.min_confidence
        return should_enter, result.confidence

    def should_exit(
        self,
        indicators: dict[str, float],
        entry_price: float,
        current_price: float,
        stop_loss_pct: float = -10.0,
        take_profit_pct: float = 25.0,
    ) -> tuple[bool, str, float]:
        """
        Check if we should exit a trade.

        Returns:
            Tuple of (should_exit, reason, confidence).
            Reasons: 'condition', 'stop_loss', 'take_profit'
        """
        # Calculate unrealized PnL
        if self.direction == "long":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        # Check stop loss
        if pnl_pct <= stop_loss_pct:
            return True, "stop_loss", 1.0

        # Check take profit
        if pnl_pct >= take_profit_pct:
            return True, "take_profit", 1.0

        # Check exit conditions
        if self.exit_conditions:
            result = self.check_exit(indicators)
            if result.matched:
                return True, "condition", result.confidence

        return False, "", 0.0
