"""
Canonical Periods - Historical market regimes for robust backtesting.

These are specific, labeled time periods representing different market conditions:
- Crashes (COVID, FTX, Luna, etc.)
- Blow-off tops (2017 ATH, 2021 ATHs)
- Recoveries
- Bull runs
- Bear markets
- Consolidation/sideways

Testing across ALL these periods ensures agents aren't overfitting to one regime.
"""

from datetime import UTC, datetime

# Canonical periods with regime labels
CANONICAL_PERIODS = {
    # === CRASHES (highest priority - tests risk management) ===
    "crash_2020_covid": {
        "start": "2020-03-08",
        "end": "2020-03-15",
        "regime": "crash",
        "description": "COVID black swan: -50% in 1 week",
    },
    "crash_2022_luna": {
        "start": "2022-05-07",
        "end": "2022-05-12",
        "regime": "crash",
        "description": "Luna/UST death spiral",
    },
    "crash_2022_ftx": {
        "start": "2022-11-06",
        "end": "2022-11-09",
        "regime": "crash",
        "description": "FTX collapse: -25%",
    },
    "crash_2021_may": {
        "start": "2021-05-12",
        "end": "2021-05-19",
        "regime": "crash",
        "description": "China ban + Elon tweet: -30%",
    },
    "crash_2018_jan": {
        "start": "2018-01-06",
        "end": "2018-02-06",
        "regime": "crash",
        "description": "Post-2017 ATH collapse: -65%",
    },
    # === BLOW-OFF TOPS (euphoria detection) ===
    "blowoff_2017_dec": {
        "start": "2017-12-01",
        "end": "2017-12-17",
        "regime": "blowoff",
        "description": "$19,783 ATH then crash",
    },
    "blowoff_2021_apr": {
        "start": "2021-04-01",
        "end": "2021-04-14",
        "regime": "blowoff",
        "description": "$64k ATH, Tesla/Coinbase hype",
    },
    "blowoff_2021_nov": {
        "start": "2021-11-01",
        "end": "2021-11-10",
        "regime": "blowoff",
        "description": "$68k ATH",
    },
    # === RECOVERY (bottom fishing) ===
    "recovery_2020_post_covid": {
        "start": "2020-03-16",
        "end": "2020-07-31",
        "regime": "recovery",
        "description": "Post-COVID: $5k -> $12k",
    },
    "recovery_2023": {
        "start": "2023-01-01",
        "end": "2023-03-31",
        "regime": "recovery",
        "description": "Post-FTX bounce",
    },
    "recovery_2019": {
        "start": "2019-01-01",
        "end": "2019-06-30",
        "regime": "recovery",
        "description": "Post-2018 bear: $3k -> $13k",
    },
    # === BULL RUNS ===
    "bull_2017_q4": {
        "start": "2017-09-15",
        "end": "2017-12-17",
        "regime": "bull",
        "description": "Parabolic run: $3k -> $20k",
    },
    "bull_2020_q4": {
        "start": "2020-10-01",
        "end": "2020-12-31",
        "regime": "bull",
        "description": "Institutional FOMO: $10k -> $29k",
    },
    "bull_2021_q1": {
        "start": "2021-01-01",
        "end": "2021-04-14",
        "regime": "bull",
        "description": "Retail/Tesla: $29k -> $64k",
    },
    "bull_2024": {
        "start": "2024-01-01",
        "end": "2024-03-15",
        "regime": "bull",
        "description": "ETF approval rally",
    },
    # === BEAR MARKETS ===
    "bear_2018": {
        "start": "2018-01-15",
        "end": "2018-12-15",
        "regime": "bear",
        "description": "Crypto winter: $20k -> $3k",
    },
    "bear_2022": {
        "start": "2022-05-01",
        "end": "2022-11-30",
        "regime": "bear",
        "description": "Luna/FTX bear: $40k -> $15k",
    },
    # === CONSOLIDATION/SIDEWAYS ===
    "sideways_2019_h2": {
        "start": "2019-07-01",
        "end": "2019-12-31",
        "regime": "sideways",
        "description": "Range-bound: $7k-$12k",
    },
    "sideways_2023_q2": {
        "start": "2023-04-01",
        "end": "2023-09-30",
        "regime": "sideways",
        "description": "Post-rally consolidation: $25k-$31k",
    },
}


def get_canonical_periods_for_backtesting(
    assets: list[str] = None,
    timeframes: list[str] = None,
    regimes: list[str] = None,
) -> list[dict]:
    """
    Get canonical periods formatted for backtest_agents().

    Args:
        assets: List of assets to test (default: BTC, ETH, SOL)
        timeframes: Timeframes to use (default: 1h)
        regimes: Filter to specific regimes (default: all)

    Returns:
        List of period dicts with: asset, timeframe, start_ts, end_ts, regime
    """
    assets = assets or ["BTC", "ETH", "SOL"]
    timeframes = timeframes or ["1h"]

    periods = []

    for period_name, period_data in CANONICAL_PERIODS.items():
        # Filter by regime if specified
        if regimes and period_data["regime"] not in regimes:
            continue

        # Parse dates to timestamps (milliseconds)
        start_dt = datetime.strptime(period_data["start"], "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = datetime.strptime(period_data["end"], "%Y-%m-%d").replace(tzinfo=UTC)
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        # Create period for each asset/timeframe combo
        for asset in assets:
            for tf in timeframes:
                periods.append(
                    {
                        "name": period_name,
                        "asset": asset,
                        "timeframe": tf,
                        "start_ts": start_ts,
                        "end_ts": end_ts,
                        "regime": period_data["regime"],
                        "description": period_data["description"],
                    }
                )

    return periods


def get_regime_summary() -> dict[str, int]:
    """Get count of periods per regime."""
    summary = {}
    for period_data in CANONICAL_PERIODS.values():
        regime = period_data["regime"]
        summary[regime] = summary.get(regime, 0) + 1
    return summary


# Quick access
REGIMES = ["crash", "blowoff", "recovery", "bull", "bear", "sideways"]
TOTAL_PERIODS = len(CANONICAL_PERIODS)
