#!/usr/bin/env python3
"""
Three Pillars Signal Fusion Implementation.

This module combines Technical, Sentiment, and Fundamental signals
into unified trading decisions with regime-adaptive weighting.

Paper References:
- MAT Three Pillars (arxiv-2310.01232): Inter-modal fusion
- TradingAgents (arxiv-2412.20138): Role specialization
- FinAgent (arxiv-2512.02227): Multi-source integration

Related Concept: ../concepts/three-pillars.md
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class PillarSignal:
    """Signal from a single pillar."""

    signal: float  # -1 to +1 (bearish to bullish)
    confidence: float  # 0 to 1
    components: dict[str, float]  # Individual indicator signals


@dataclass
class FusedSignal:
    """Result of three pillars fusion."""

    signal: float
    confidence: float
    decision: str  # 'BUY', 'SELL', 'HOLD'
    strength: str  # 'strong', 'moderate', 'weak'
    pillars: dict[str, PillarSignal]
    all_agree: bool
    weights_used: dict[str, float]


# =============================================================================
# Technical Analysis Pillar (40%)
# =============================================================================


def calculate_technical_signal(
    prices: np.ndarray, volumes: np.ndarray, high: np.ndarray | None = None, low: np.ndarray | None = None
) -> PillarSignal:
    """
    Generate technical analysis signal.

    Components (weights):
    - Trend (35%): EMA cross, price vs SMAs
    - Momentum (30%): RSI, MACD
    - Volatility (20%): Bollinger Bands position
    - Volume (15%): OBV trend, volume ratio

    Args:
        prices: Close prices (most recent last)
        volumes: Volume data
        high: High prices (optional)
        low: Low prices (optional)

    Returns:
        PillarSignal with combined technical signal
    """
    if len(prices) < 50:
        return PillarSignal(signal=0, confidence=0.3, components={})

    components = {}

    # === TREND (35%) ===
    ema_20 = _ema(prices, 20)
    ema_50 = _ema(prices, 50)

    price_vs_ema20 = (prices[-1] - ema_20[-1]) / ema_20[-1]
    ema_cross = (ema_20[-1] - ema_50[-1]) / ema_50[-1]

    trend_signal = np.tanh(price_vs_ema20 * 10 + ema_cross * 20)
    components["trend"] = float(trend_signal)

    # === MOMENTUM (30%) ===
    rsi = _calculate_rsi(prices, 14)
    rsi_signal = (rsi - 50) / 50  # -1 to +1

    macd_line, macd_signal_line, macd_hist = _calculate_macd(prices)
    macd_signal = np.tanh(macd_hist[-1] * 100)

    momentum_signal = 0.5 * rsi_signal + 0.5 * macd_signal
    components["momentum"] = float(momentum_signal)

    # === VOLATILITY (20%) ===
    bb_upper, bb_middle, bb_lower = _calculate_bollinger(prices)
    bb_range = bb_upper[-1] - bb_lower[-1]
    if bb_range > 0:
        bb_position = (prices[-1] - bb_lower[-1]) / bb_range
    else:
        bb_position = 0.5

    # At lower band = potentially bullish (oversold)
    # At upper band = potentially bearish (overbought)
    vol_signal = (0.5 - bb_position) * 2  # Inverted
    components["volatility"] = float(vol_signal)

    # === VOLUME (15%) ===
    obv = _calculate_obv(prices, volumes)
    obv_trend = (obv[-1] - obv[-20]) / (abs(obv[-20]) + 1e-8)

    vol_ratio = np.mean(volumes[-5:]) / (np.mean(volumes[-20:]) + 1e-8)
    volume_signal = np.tanh(obv_trend) * min(vol_ratio, 2) / 2
    components["volume"] = float(volume_signal)

    # === WEIGHTED COMBINATION ===
    final_signal = 0.35 * trend_signal + 0.30 * momentum_signal + 0.20 * vol_signal + 0.15 * volume_signal

    # Confidence based on component agreement
    signals = [trend_signal, momentum_signal, vol_signal, volume_signal]
    agreement = sum(1 for s in signals if s * final_signal > 0) / len(signals)
    confidence = agreement * abs(final_signal)

    return PillarSignal(
        signal=float(np.clip(final_signal, -1, 1)), confidence=float(np.clip(confidence, 0, 1)), components=components
    )


# =============================================================================
# Sentiment Analysis Pillar (30%)
# =============================================================================


def calculate_sentiment_signal(
    fear_greed: int,
    funding_rate: float,
    long_short_ratio: float,
    social_sentiment: float = 0.0,
    agent_traits: dict | None = None,
) -> PillarSignal:
    """
    Generate sentiment analysis signal.

    Components:
    - Fear & Greed Index (35%): Inverted - fear = bullish
    - Funding Rate (20%): Negative = shorts paying = bullish
    - Long/Short Ratio (20%): High ratio = contrarian bearish
    - Social Sentiment (25%): Direct signal

    Args:
        fear_greed: Fear & Greed Index (0-100)
        funding_rate: Current funding rate (-0.1% to +0.1%)
        long_short_ratio: Ratio of longs to shorts
        social_sentiment: NLP-derived sentiment (-1 to +1)
        agent_traits: Optional traits for contrarian adjustment

    Returns:
        PillarSignal with combined sentiment signal
    """
    if agent_traits is None:
        agent_traits = {"sentiment_contrarian": 0.5, "sentiment_weight": 0.5}

    components = {}

    # === FEAR & GREED (35%) ===
    # 0-25: Extreme Fear (buy signal)
    # 75-100: Extreme Greed (sell signal)
    fg_signal = (50 - fear_greed) / 50
    components["fear_greed"] = float(fg_signal)

    # === FUNDING RATE (20%) ===
    # Negative = shorts pay longs = potential bottom
    # Positive = longs pay shorts = potential top
    funding_signal = -np.tanh(funding_rate * 1000)
    components["funding"] = float(funding_signal)

    # === LONG/SHORT RATIO (20%) ===
    # High ratio = crowded longs = contrarian bearish
    ls_signal = -(long_short_ratio - 1)
    ls_signal = float(np.clip(ls_signal, -1, 1))
    components["long_short"] = ls_signal

    # === SOCIAL SENTIMENT (25%) ===
    components["social"] = float(social_sentiment)

    # === BASE SIGNAL ===
    base_signal = 0.35 * fg_signal + 0.20 * funding_signal + 0.20 * ls_signal + 0.25 * social_sentiment

    # === CONTRARIAN ADJUSTMENT ===
    contrarian = agent_traits.get("sentiment_contrarian", 0.5)
    if contrarian > 0.5:
        inversion = (contrarian - 0.5) * 2
        final_signal = base_signal * (1 - inversion * 2)
    else:
        final_signal = base_signal

    # Confidence scales with agent's sentiment weight
    sentiment_weight = agent_traits.get("sentiment_weight", 0.5)
    confidence = abs(final_signal) * sentiment_weight

    return PillarSignal(
        signal=float(np.clip(final_signal, -1, 1)), confidence=float(np.clip(confidence, 0, 1)), components=components
    )


# =============================================================================
# Fundamental Analysis Pillar (30%)
# =============================================================================


def calculate_fundamental_signal(
    nvt_ratio: float = 100,
    sopr: float = 1.0,
    exchange_netflow: float = 0.0,
    active_addresses_change: float = 0.0,
    macro_conditions: dict | None = None,
) -> PillarSignal:
    """
    Generate fundamental analysis signal.

    Components:
    - NVT Ratio (20%): High = overvalued
    - SOPR (20%): <1 = coins moving at loss
    - Exchange Flows (30%): Positive = bearish
    - Active Addresses (10%): Growing = bullish
    - Macro (20%): DXY, rates

    Args:
        nvt_ratio: Network Value to Transactions (20-200 typical)
        sopr: Spent Output Profit Ratio (around 1.0)
        exchange_netflow: Net flow to exchanges (positive = bearish)
        active_addresses_change: % change in active addresses
        macro_conditions: Dict with 'dxy_trend', 'rate_expectations'

    Returns:
        PillarSignal with combined fundamental signal
    """
    if macro_conditions is None:
        macro_conditions = {"dxy_trend": 0, "rate_expectations": 0}

    components = {}

    # === NVT RATIO (20%) ===
    # High NVT = overvalued (bearish), Low = undervalued (bullish)
    nvt_signal = (100 - nvt_ratio) / 100
    nvt_signal = float(np.clip(nvt_signal, -1, 1))
    components["nvt"] = nvt_signal

    # === SOPR (20%) ===
    # <1 = coins moving at loss (capitulation, bullish)
    # >1 = coins moving in profit (selling pressure, bearish)
    sopr_signal = -(sopr - 1) * 5
    sopr_signal = float(np.clip(sopr_signal, -1, 1))
    components["sopr"] = sopr_signal

    # === EXCHANGE FLOWS (30%) ===
    # Positive = coins to exchanges (bearish)
    # Negative = coins leaving exchanges (bullish)
    flow_signal = -np.tanh(exchange_netflow * 10)
    components["exchange_flow"] = float(flow_signal)

    # === ACTIVE ADDRESSES (10%) ===
    addr_signal = np.tanh(active_addresses_change * 10)
    components["active_addresses"] = float(addr_signal)

    # === MACRO (20%) ===
    dxy_trend = macro_conditions.get("dxy_trend", 0)
    rate_exp = macro_conditions.get("rate_expectations", 0)

    # Strong dollar / rising rates = risk-off = bearish for crypto
    macro_signal = -(0.6 * dxy_trend + 0.4 * rate_exp)
    components["macro"] = float(macro_signal)

    # === WEIGHTED COMBINATION ===
    final_signal = (
        0.20 * nvt_signal + 0.20 * sopr_signal + 0.30 * flow_signal + 0.10 * addr_signal + 0.20 * macro_signal
    )

    # Confidence based on data availability
    available = [nvt_signal, sopr_signal, flow_signal, addr_signal, macro_signal]
    non_zero = [s for s in available if abs(s) > 0.1]

    if len(non_zero) < 3:
        confidence = 0.3  # Low confidence with limited data
    else:
        agreement = sum(1 for s in non_zero if s * final_signal > 0) / len(non_zero)
        confidence = agreement * abs(final_signal)

    return PillarSignal(
        signal=float(np.clip(final_signal, -1, 1)), confidence=float(np.clip(confidence, 0, 1)), components=components
    )


# =============================================================================
# Three Pillars Fusion
# =============================================================================

# Regime-based weights
REGIME_WEIGHTS = {
    "bull_volatile": {"technical": 0.45, "sentiment": 0.35, "fundamental": 0.20},
    "bull_calm": {"technical": 0.35, "sentiment": 0.25, "fundamental": 0.40},
    "bear_volatile": {"technical": 0.50, "sentiment": 0.35, "fundamental": 0.15},
    "bear_calm": {"technical": 0.30, "sentiment": 0.30, "fundamental": 0.40},
    "sideways": {"technical": 0.40, "sentiment": 0.30, "fundamental": 0.30},
}


def fuse_three_pillars(
    technical: PillarSignal,
    sentiment: PillarSignal,
    fundamental: PillarSignal,
    regime: str = "sideways",
    custom_weights: dict | None = None,
) -> FusedSignal:
    """
    Combine three pillars into final trading signal.

    Uses regime-dependent weighting for adaptive fusion.

    Args:
        technical: Technical analysis signal
        sentiment: Sentiment analysis signal
        fundamental: Fundamental analysis signal
        regime: Current market regime
        custom_weights: Optional custom weights override

    Returns:
        FusedSignal with combined decision

    Paper Reference: MAT Three Pillars
    "Inter-modal fusion captures complementary information"
    """
    # Get weights
    if custom_weights:
        weights = custom_weights
    else:
        weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["sideways"])

    tech_w = weights["technical"]
    sent_w = weights["sentiment"]
    fund_w = weights["fundamental"]

    # Weighted signal
    final_signal = tech_w * technical.signal + sent_w * sentiment.signal + fund_w * fundamental.signal

    # Weighted confidence
    weighted_conf = tech_w * technical.confidence + sent_w * sentiment.confidence + fund_w * fundamental.confidence

    # Agreement bonus
    signals = [technical.signal, sentiment.signal, fundamental.signal]
    all_agree = all(s * final_signal > 0 for s in signals if abs(s) > 0.1)

    if all_agree:
        weighted_conf = min(1.0, weighted_conf * 1.2)  # 20% bonus

    # Determine decision
    if abs(final_signal) < 0.15 or weighted_conf < 0.4:
        decision = "HOLD"
        strength = "weak"
    elif final_signal > 0.3:
        decision = "BUY"
        strength = "strong" if final_signal > 0.6 else "moderate"
    elif final_signal < -0.3:
        decision = "SELL"
        strength = "strong" if final_signal < -0.6 else "moderate"
    else:
        decision = "BUY" if final_signal > 0 else "SELL"
        strength = "weak"

    return FusedSignal(
        signal=float(np.clip(final_signal, -1, 1)),
        confidence=float(np.clip(weighted_conf, 0, 1)),
        decision=decision,
        strength=strength,
        pillars={
            "technical": technical,
            "sentiment": sentiment,
            "fundamental": fundamental,
        },
        all_agree=all_agree,
        weights_used=weights,
    )


def get_agent_pillar_weights(agent_traits: dict) -> dict:
    """
    Determine pillar weights based on agent traits.

    Returns custom weights for agent specialization.

    Paper Reference: TradingAgents - role specialization
    """
    sentiment_weight = agent_traits.get("sentiment_weight", 0.5)
    lookback = agent_traits.get("lookback_preference", 0.5)

    if sentiment_weight > 0.7:
        # Sentiment specialist
        return {"technical": 0.30, "sentiment": 0.50, "fundamental": 0.20}
    elif lookback > 0.7:
        # Fundamental/long-term specialist
        return {"technical": 0.25, "sentiment": 0.25, "fundamental": 0.50}
    else:
        # Technical specialist (default)
        return {"technical": 0.45, "sentiment": 0.25, "fundamental": 0.30}


# =============================================================================
# Technical Indicator Helpers
# =============================================================================


def _ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Calculate Exponential Moving Average."""
    alpha = 2 / (period + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate Relative Strength Index."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calculate_macd(
    prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate MACD line, signal, and histogram."""
    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _calculate_bollinger(
    prices: np.ndarray, period: int = 20, std_dev: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate Bollinger Bands."""
    middle = np.convolve(prices, np.ones(period) / period, mode="valid")
    middle = np.pad(middle, (period - 1, 0), mode="edge")

    rolling_std = np.array([np.std(prices[max(0, i - period + 1) : i + 1]) for i in range(len(prices))])

    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std

    return upper, middle, lower


def _calculate_obv(prices: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """Calculate On-Balance Volume."""
    obv = np.zeros_like(volumes)
    obv[0] = volumes[0]

    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif prices[i] < prices[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    return obv


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Generate sample data
    np.random.seed(42)
    n = 100

    prices = 50000 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))
    volumes = np.random.uniform(1000, 5000, n)

    # Calculate technical signal
    print("Calculating Technical Signal...")
    tech_signal = calculate_technical_signal(prices, volumes)
    print(f"  Signal: {tech_signal.signal:.3f}")
    print(f"  Confidence: {tech_signal.confidence:.3f}")
    print(f"  Components: {tech_signal.components}")

    # Calculate sentiment signal
    print("\nCalculating Sentiment Signal...")
    sent_signal = calculate_sentiment_signal(
        fear_greed=35,
        funding_rate=-0.0001,
        long_short_ratio=1.2,
        social_sentiment=0.2,
    )
    print(f"  Signal: {sent_signal.signal:.3f}")
    print(f"  Confidence: {sent_signal.confidence:.3f}")

    # Calculate fundamental signal
    print("\nCalculating Fundamental Signal...")
    fund_signal = calculate_fundamental_signal(
        nvt_ratio=85,
        sopr=0.98,
        exchange_netflow=-500,
        active_addresses_change=0.05,
    )
    print(f"  Signal: {fund_signal.signal:.3f}")
    print(f"  Confidence: {fund_signal.confidence:.3f}")

    # Fuse signals
    print("\nFusing Three Pillars (bull_volatile regime)...")
    fused = fuse_three_pillars(tech_signal, sent_signal, fund_signal, regime="bull_volatile")
    print(f"  Final Signal: {fused.signal:.3f}")
    print(f"  Confidence: {fused.confidence:.3f}")
    print(f"  Decision: {fused.decision} ({fused.strength})")
    print(f"  All Pillars Agree: {fused.all_agree}")
    print(f"  Weights Used: {fused.weights_used}")
