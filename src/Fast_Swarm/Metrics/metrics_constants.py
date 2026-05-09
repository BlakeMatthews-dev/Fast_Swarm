"""
Metrics Constants.

Regime taxonomy, fitness bounds, and normalization parameters
for the V4 specialist fitness model.
"""

# =============================================================================
# Regime Taxonomy
# =============================================================================

SPECIALIST_REGIMES = [
    "bull",       # Main moneymakers - positive skew, high alpha
    "blowoff",    # Exit timing - captures tops, high exit efficiency
    "sideways",   # Crab/chop - low drawdown, consistent small gains
    "crash",      # Sudden drops - shorts or stays flat, negative beta
    "bear",       # Extended downtrends (incl. winter) - profits from decline
    "recovery",   # Catching the bounce - fast entry after bottom
    "volatile",   # High uncertainty - thrives in chaos, wide stops
]

NON_SPECIALIST_REGIMES = [
    "transition",  # Coach's job - regime switching
    "random",      # Baseline testing - goal: don't blow up
]

ALL_REGIMES = SPECIALIST_REGIMES + NON_SPECIALIST_REGIMES

# =============================================================================
# V4 Fitness Weights
# =============================================================================

WEIGHTS_V4 = {
    "specialist_depth": 40,   # How good in BEST regime
    "risk_discipline": 35,    # How safe OUTSIDE best regime
    "signal_quality": 20,     # Is the edge real?
    "uniqueness": 5,          # Tiebreaker: diversity
}

# =============================================================================
# Specialist Depth Bounds
# =============================================================================

SPECIALIST_DEPTH_BOUNDS = {
    "sortino": {"saturation": 4.0},           # Diminishing returns
    "alpha_pct": {"min": -100, "max": 100},   # Linear within bounds
    "expectancy_pct": {"min": 0, "max": 10},  # 0-10% range
    "exit_efficiency": {"min": 0.3, "max": 0.9},
    "payoff_ratio": {"min": 0.5, "max": 3.0},
}

# Sub-weights within specialist depth (sum to 40)
SPECIALIST_DEPTH_SUBWEIGHTS = {
    "sortino": 12,           # Diminishing returns curve
    "alpha": 10,             # Linear
    "expectancy": 8,         # Linear
    "exit_efficiency": 5,    # Linear
    "payoff_ratio": 5,       # Linear
}

# =============================================================================
# Risk Discipline Thresholds
# =============================================================================

RISK_DISCIPLINE_THRESHOLDS = {
    "exposure_threshold": 0.30,          # >30% trading outside specialty -> penalty
    "exposure_penalty_rate": 30.0,       # pts per unit over threshold
    "exposure_max_penalty": 10.0,

    "drawdown_threshold": 10.0,          # >10% drawdown outside specialty -> penalty
    "drawdown_penalty_rate": 1.0,        # pts per % over threshold
    "drawdown_max_penalty": 10.0,

    "ruin_threshold": 0.15,              # >15% ruin probability -> penalty
    "ruin_penalty_rate": 40.0,           # pts per unit
    "ruin_max_penalty": 10.0,

    "consec_loss_threshold": 5,          # >5 consecutive losses -> penalty
    "consec_loss_penalty_rate": 1.5,     # pts per loss over threshold
    "consec_loss_max_penalty": 5.0,
}

# =============================================================================
# EV Gate Breakpoints
# =============================================================================

EV_BREAKPOINTS = [
    (0.0, 0.0),       # 0% EV -> 0 multiplier (HARD GATE)
    (0.001, 0.35),    # Just above 0 -> 0.35
    (1.0, 0.8),       # 1% EV -> 0.8x
    (3.0, 1.2),       # 3% EV -> 1.2x
    (9.0, 1.5),       # 9%+ EV -> 1.5x (cap)
]

# =============================================================================
# Interaction Penalty Thresholds
# =============================================================================

INTERACTION_PENALTIES = {
    "fragile": {
        "sortino_threshold": 2.5,
        "drawdown_threshold": 30.0,
        "penalty_factor": 0.75,
    },
    "high_ruin": {
        "ruin_threshold": 0.30,
        "penalty_factor": 0.70,
    },
    "low_trades": {
        "trades_threshold": 15,
        "penalty_factor": 0.60,
    },
}

# =============================================================================
# Specialist Regime Classification
# =============================================================================

CLASSIFICATION_MIN_SCORE = 15.0  # Minimum score to be classified as specialist

# =============================================================================
# Regime Weights (for backtest fitness aggregation)
# =============================================================================

REGIME_WEIGHTS = {
    # Random windows (baseline difficulty)
    "random_1m": 1.0,
    "random_5m": 1.0,
    "random_15m": 1.0,
    "random_1h": 1.0,
    "random_4h": 1.0,
    "random_1d": 1.0,
    # Canonical periods (varying difficulty)
    "bull": 0.5,       # Everyone can win in a bull market
    "bear": 2.0,       # Harder to profit when prices fall
    "crash": 3.0,      # Survival is critical - highest weight
    "sideways": 2.5,   # Market spends most time here, hard to profit
    "blowoff": 1.5,    # Volatility spike before reversal
    "recovery": 1.5,   # Catching the bounce
    "volatile": 2.0,   # High uncertainty
    "winter": 2.0,     # Extended bear
    "transition": 1.5, # Regime change
}

# =============================================================================
# Skew Expectations by Regime
# =============================================================================

EXPECTED_SKEW = {
    "bull": "positive",       # Momentum riders want positive skew
    "blowoff": "positive",    # Capturing tops -> positive skew
    "sideways": "neutral",    # Range-bound -> near zero skew
    "crash": "negative",      # Profits from drops -> negative skew OK
    "bear": "negative",       # Extended declines -> negative skew OK
    "recovery": "positive",   # Catching bounces -> positive skew
    "volatile": "neutral",    # Chaos -> either direction
}
