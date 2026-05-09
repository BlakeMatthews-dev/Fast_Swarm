#!/usr/bin/env python3
"""
Market Regime Classification Implementation.

This module provides regime detection using both HMM-based and rule-based
approaches to identify market states for strategy adaptation.

Paper References:
- MacroHFT (arxiv-2406.14537): Regime-aware agent behavior
- HMM Finance papers: Markov regime switching

Related Concept: ../concepts/regime-detection.md
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Regime(Enum):
    """Market regime classifications."""

    BULL_VOLATILE = "bull_volatile"
    BULL_CALM = "bull_calm"
    BEAR_VOLATILE = "bear_volatile"
    BEAR_CALM = "bear_calm"
    SIDEWAYS = "sideways"


@dataclass
class RegimeClassification:
    """Result of regime classification."""

    regime: Regime
    confidence: float
    probabilities: dict[str, float]
    features: dict[str, float]


# =============================================================================
# Rule-Based Classifier (Simpler, More Interpretable)
# =============================================================================


def classify_regime_rules(prices: np.ndarray, volumes: np.ndarray, lookback: int = 20) -> RegimeClassification:
    """
    Rule-based regime classification.

    Faster and more interpretable than HMM.
    Good for real-time classification.

    Args:
        prices: Array of close prices (most recent last)
        volumes: Array of volumes
        lookback: Lookback period for calculations

    Returns:
        RegimeClassification with regime and confidence
    """
    if len(prices) < max(lookback, 50):
        return RegimeClassification(
            regime=Regime.SIDEWAYS, confidence=0.3, probabilities={r.value: 0.2 for r in Regime}, features={}
        )

    # Calculate features
    features = extract_regime_features(prices, volumes, lookback)

    # Classify trend
    trend_score = (
        0.4 * features["return_20d_zscore"] + 0.3 * features["price_vs_sma20"] + 0.3 * features["sma20_vs_sma50"]
    )

    if trend_score > 0.5:
        trend = "bull"
    elif trend_score < -0.5:
        trend = "bear"
    else:
        trend = "sideways"

    # Classify volatility
    vol_percentile = features["volatility_percentile"]
    is_volatile = vol_percentile > 0.6

    # Determine regime
    if trend == "sideways":
        regime = Regime.SIDEWAYS
    elif trend == "bull":
        regime = Regime.BULL_VOLATILE if is_volatile else Regime.BULL_CALM
    else:  # bear
        regime = Regime.BEAR_VOLATILE if is_volatile else Regime.BEAR_CALM

    # Calculate confidence based on feature clarity
    trend_clarity = abs(trend_score)
    vol_clarity = abs(vol_percentile - 0.5) * 2
    confidence = min(1.0, (trend_clarity + vol_clarity) / 2)

    # Estimate probabilities (soft classification)
    probabilities = estimate_regime_probabilities(features)

    return RegimeClassification(regime=regime, confidence=confidence, probabilities=probabilities, features=features)


def extract_regime_features(prices: np.ndarray, volumes: np.ndarray, lookback: int = 20) -> dict[str, float]:
    """
    Extract features for regime classification.

    Args:
        prices: Close prices
        volumes: Volume data
        lookback: Feature calculation lookback

    Returns:
        Dict of feature name -> value
    """
    returns = np.diff(prices) / prices[:-1]

    # Moving averages
    sma_20 = np.mean(prices[-20:])
    sma_50 = np.mean(prices[-50:])

    # Returns
    return_20d = (prices[-1] - prices[-20]) / prices[-20]
    return_5d = (prices[-1] - prices[-5]) / prices[-5]

    # Volatility
    volatility_20d = np.std(returns[-20:]) * np.sqrt(252)
    volatility_60d = np.std(returns[-60:]) * np.sqrt(252) if len(returns) >= 60 else volatility_20d

    # Z-score of return (how unusual)
    return_mean = np.mean(returns[-60:]) if len(returns) >= 60 else np.mean(returns)
    return_std = np.std(returns[-60:]) if len(returns) >= 60 else np.std(returns)
    return_20d_zscore = (return_20d - return_mean * 20) / (return_std * np.sqrt(20) + 1e-8)

    # Price position relative to MAs
    price_vs_sma20 = (prices[-1] - sma_20) / sma_20
    price_vs_sma50 = (prices[-1] - sma_50) / sma_50
    sma20_vs_sma50 = (sma_20 - sma_50) / sma_50

    # Volatility percentile (where does current vol rank)
    vol_history = [np.std(returns[i : i + 20]) for i in range(len(returns) - 20)]
    if vol_history:
        current_vol = np.std(returns[-20:])
        vol_percentile = sum(1 for v in vol_history if v < current_vol) / len(vol_history)
    else:
        vol_percentile = 0.5

    # Volume features
    volume_ratio = np.mean(volumes[-5:]) / (np.mean(volumes[-20:]) + 1e-8)

    return {
        "return_20d": return_20d,
        "return_5d": return_5d,
        "return_20d_zscore": return_20d_zscore,
        "volatility_20d": volatility_20d,
        "volatility_60d": volatility_60d,
        "volatility_percentile": vol_percentile,
        "price_vs_sma20": price_vs_sma20,
        "price_vs_sma50": price_vs_sma50,
        "sma20_vs_sma50": sma20_vs_sma50,
        "volume_ratio": volume_ratio,
    }


def estimate_regime_probabilities(features: dict[str, float]) -> dict[str, float]:
    """
    Estimate probability distribution over regimes.

    Uses softmax over feature-derived scores for each regime.
    """
    scores = {}

    # Bull volatile score
    scores["bull_volatile"] = (
        max(0, features["return_20d_zscore"]) * 0.4
        + max(0, features["price_vs_sma20"]) * 0.3
        + max(0, features["volatility_percentile"] - 0.5) * 2 * 0.3
    )

    # Bull calm score
    scores["bull_calm"] = (
        max(0, features["return_20d_zscore"]) * 0.4
        + max(0, features["price_vs_sma20"]) * 0.3
        + max(0, 0.5 - features["volatility_percentile"]) * 2 * 0.3
    )

    # Bear volatile score
    scores["bear_volatile"] = (
        max(0, -features["return_20d_zscore"]) * 0.4
        + max(0, -features["price_vs_sma20"]) * 0.3
        + max(0, features["volatility_percentile"] - 0.5) * 2 * 0.3
    )

    # Bear calm score
    scores["bear_calm"] = (
        max(0, -features["return_20d_zscore"]) * 0.4
        + max(0, -features["price_vs_sma20"]) * 0.3
        + max(0, 0.5 - features["volatility_percentile"]) * 2 * 0.3
    )

    # Sideways score (low absolute trend)
    scores["sideways"] = (
        max(0, 1 - abs(features["return_20d_zscore"])) * 0.5 + max(0, 1 - abs(features["price_vs_sma20"]) * 10) * 0.5
    )

    # Softmax normalization
    max_score = max(scores.values())
    exp_scores = {k: np.exp(v - max_score) for k, v in scores.items()}
    total = sum(exp_scores.values())

    return {k: v / total for k, v in exp_scores.items()}


# =============================================================================
# HMM-Based Classifier (More Sophisticated)
# =============================================================================


class HMMRegimeClassifier:
    """
    Hidden Markov Model based regime classifier.

    Uses Gaussian HMM to model latent market states.

    Paper Reference: MacroHFT
    "Regime detection enables adaptive strategy selection"

    Note: Requires hmmlearn package.
    """

    def __init__(self, n_regimes: int = 4, random_state: int = 42):
        """
        Initialize HMM classifier.

        Args:
            n_regimes: Number of hidden states (typically 4-5)
            random_state: Random seed for reproducibility
        """
        self.n_regimes = n_regimes
        self.random_state = random_state
        self.model = None
        self.regime_labels = {}
        self.is_fitted = False

        # Try to import hmmlearn
        try:
            from hmmlearn import GaussianHMM

            self._hmm_available = True
        except ImportError:
            self._hmm_available = False
            print("Warning: hmmlearn not available, use rule-based classifier")

    def fit(self, returns: np.ndarray, volatility: np.ndarray) -> None:
        """
        Fit HMM on historical data.

        Args:
            returns: Array of log returns
            volatility: Array of realized volatility (e.g., rolling std)
        """
        if not self._hmm_available:
            raise RuntimeError("hmmlearn not installed")

        from hmmlearn import GaussianHMM

        # Combine features
        X = np.column_stack([returns, volatility])

        # Initialize and fit HMM
        self.model = GaussianHMM(
            n_components=self.n_regimes, covariance_type="full", n_iter=100, random_state=self.random_state
        )
        self.model.fit(X)
        self.is_fitted = True

        # Label regimes based on learned parameters
        self._label_regimes()

    def _label_regimes(self) -> None:
        """
        Assign human-readable labels to learned regimes.

        Based on the mean returns and volatility of each state.
        """
        if self.model is None:
            return

        means = self.model.means_
        median_vol = np.median([m[1] for m in means])

        for i in range(self.n_regimes):
            ret_mean = means[i, 0]
            vol_mean = means[i, 1]

            # Determine trend direction
            if ret_mean > 0.0005:
                trend = "bull"
            elif ret_mean < -0.0005:
                trend = "bear"
            else:
                trend = "sideways"

            # Determine volatility level
            vol_level = "volatile" if vol_mean > median_vol else "calm"

            # Assign label
            if trend == "sideways":
                self.regime_labels[i] = "sideways"
            else:
                self.regime_labels[i] = f"{trend}_{vol_level}"

    def predict(self, returns: np.ndarray, volatility: np.ndarray) -> str:
        """
        Predict current regime.

        Args:
            returns: Recent returns
            volatility: Recent volatility

        Returns:
            Regime label string
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        X = np.column_stack([returns, volatility])
        hidden_states = self.model.predict(X)
        current_state = hidden_states[-1]

        return self.regime_labels.get(current_state, "unknown")

    def predict_proba(self, returns: np.ndarray, volatility: np.ndarray) -> dict[str, float]:
        """
        Get probability distribution over regimes.

        Returns:
            Dict mapping regime labels to probabilities
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted")

        X = np.column_stack([returns, volatility])
        posteriors = self.model.predict_proba(X)
        current_probs = posteriors[-1]

        return {self.regime_labels.get(i, f"state_{i}"): float(prob) for i, prob in enumerate(current_probs)}


# =============================================================================
# Regime Transition Detection
# =============================================================================


def detect_regime_transition(
    regime_history: list[str], confidence_history: list[float], window: int = 5
) -> tuple[bool, str, str]:
    """
    Detect if a regime transition is occurring.

    Args:
        regime_history: Recent regime classifications
        confidence_history: Confidence of each classification
        window: Lookback window

    Returns:
        (is_transitioning, current_regime, likely_new_regime)
    """
    if len(regime_history) < window:
        current = regime_history[-1] if regime_history else "unknown"
        return False, current, current

    recent = regime_history[-window:]
    recent_conf = confidence_history[-window:]
    current = regime_history[-1]

    # Check 1: Multiple regime changes (instability)
    unique_regimes = len(set(recent))
    if unique_regimes >= 3:
        return True, current, "transitioning"

    # Check 2: Sustained change from previous regime
    if len(regime_history) > window:
        previous = regime_history[-window - 1]
        if all(r == current for r in recent[-3:]) and current != previous:
            return True, previous, current

    # Check 3: Declining confidence
    if all(c < 0.5 for c in recent_conf):
        return True, current, "uncertain"

    return False, current, current


# =============================================================================
# Strategy Adaptation by Regime
# =============================================================================

REGIME_STRATEGY_PARAMS = {
    "bull_volatile": {
        "position_size_mult": 0.8,
        "stop_loss_atr_mult": 2.0,
        "preferred_strategies": ["momentum", "breakout"],
        "avoid_strategies": ["mean_reversion"],
        "max_hold_hours": 48,
    },
    "bull_calm": {
        "position_size_mult": 1.2,
        "stop_loss_atr_mult": 3.0,
        "preferred_strategies": ["trend_following", "dip_buying"],
        "avoid_strategies": [],
        "max_hold_hours": 168,
    },
    "bear_volatile": {
        "position_size_mult": 0.5,
        "stop_loss_atr_mult": 1.5,
        "preferred_strategies": ["mean_reversion"],
        "avoid_strategies": ["momentum", "breakout"],
        "max_hold_hours": 24,
    },
    "bear_calm": {
        "position_size_mult": 0.7,
        "stop_loss_atr_mult": 2.0,
        "preferred_strategies": ["mean_reversion", "support_bounce"],
        "avoid_strategies": ["trend_following"],
        "max_hold_hours": 72,
    },
    "sideways": {
        "position_size_mult": 0.6,
        "stop_loss_atr_mult": 1.5,
        "preferred_strategies": ["range_trading", "mean_reversion"],
        "avoid_strategies": ["trend_following", "breakout"],
        "max_hold_hours": 48,
    },
}


def get_regime_strategy_params(regime: str) -> dict:
    """
    Get strategy parameters for current regime.

    Args:
        regime: Current regime string

    Returns:
        Dict of strategy parameters
    """
    return REGIME_STRATEGY_PARAMS.get(regime, REGIME_STRATEGY_PARAMS["sideways"])


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Generate sample data
    np.random.seed(42)
    n_days = 100

    # Simulated price series (trending up with noise)
    drift = 0.001
    volatility = 0.02
    returns = np.random.normal(drift, volatility, n_days)
    prices = 100 * np.exp(np.cumsum(returns))
    volumes = np.random.uniform(1000, 5000, n_days)

    # Classify regime
    result = classify_regime_rules(prices, volumes)

    print("Regime Classification Result:")
    print(f"  Regime: {result.regime.value}")
    print(f"  Confidence: {result.confidence:.3f}")
    print("  Probabilities:")
    for regime, prob in result.probabilities.items():
        print(f"    {regime}: {prob:.3f}")
    print("\n  Key Features:")
    for name, value in list(result.features.items())[:5]:
        print(f"    {name}: {value:.4f}")

    # Get strategy params for this regime
    params = get_regime_strategy_params(result.regime.value)
    print("\n  Strategy Params:")
    print(f"    Position size mult: {params['position_size_mult']}")
    print(f"    Stop loss ATR mult: {params['stop_loss_atr_mult']}")
    print(f"    Preferred: {params['preferred_strategies']}")
