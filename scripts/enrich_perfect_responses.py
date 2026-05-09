#!/usr/bin/env python3
"""
Enrich Perfect Responses with Historical Correlations

Loads collected training data, clusters by indicator ranges,
calculates actual statistics, and regenerates rich perfect_response
with real correlations from the data.
"""

import json
from pathlib import Path
from collections import defaultdict
import statistics

DATA_DIR = Path(__file__).parent.parent / "data"
INPUT_FILE = DATA_DIR / "ai_training_data.jsonl"
OUTPUT_FILE = DATA_DIR / "ai_training_data_enriched.jsonl"


def bucket_value(val, buckets):
    """Assign value to nearest bucket."""
    for low, high, label in buckets:
        if low <= val < high:
            return label
    return buckets[-1][2]  # Last bucket for overflow


# Define indicator buckets for clustering
RSI_BUCKETS = [
    (0, 25, "deeply_oversold"),
    (25, 35, "oversold"),
    (35, 45, "low_neutral"),
    (45, 55, "neutral"),
    (55, 65, "high_neutral"),
    (65, 75, "overbought"),
    (75, 100, "deeply_overbought"),
]

STOCH_BUCKETS = [
    (0, 15, "extreme_low"),
    (15, 30, "low"),
    (30, 50, "mid_low"),
    (50, 70, "mid_high"),
    (70, 85, "high"),
    (85, 100, "extreme_high"),
]

ADX_BUCKETS = [
    (0, 15, "no_trend"),
    (15, 25, "weak_trend"),
    (25, 40, "moderate_trend"),
    (40, 60, "strong_trend"),
    (60, 100, "extreme_trend"),
]

def get_macd_bucket(macd_val):
    """
    MACD bucketing by sign only - works across all assets.
    BTC MACD might be 294, altcoin MACD might be 0.02.
    What matters is direction, not absolute value.
    """
    if macd_val > 0:
        return "bullish"
    elif macd_val < 0:
        return "bearish"
    else:
        return "neutral"


def get_cluster_key(indicators):
    """Create cluster key from indicator values."""
    rsi_bucket = bucket_value(indicators.get("rsi", 50), RSI_BUCKETS)
    stoch_bucket = bucket_value(indicators.get("stoch", 50), STOCH_BUCKETS)
    adx_bucket = bucket_value(indicators.get("adx", 25), ADX_BUCKETS)
    macd_bucket = get_macd_bucket(indicators.get("macd", 0))
    supertrend = "bullish" if indicators.get("supertrend", 0) > 0 else "bearish"

    return (rsi_bucket, stoch_bucket, adx_bucket, macd_bucket, supertrend)


def describe_cluster(cluster_key):
    """Human-readable description of cluster."""
    rsi, stoch, adx, macd, trend = cluster_key
    return f"RSI {rsi}, Stoch {stoch}, ADX {adx}, MACD {macd}, trend {trend}"


def generate_rich_response(record, cluster_stats):
    """Generate enriched perfect_response with real correlations."""
    indicators = record["entry_indicators"]
    exit_ind = record.get("exit_indicators", {})
    correct = record["correct_choice"]
    mfe = record.get("mfe", 0)
    bars = record.get("bars_to_mfe", 0)

    cluster_key = get_cluster_key(indicators)
    stats = cluster_stats.get(cluster_key, {})

    # Get cluster statistics
    avg_mfe = stats.get("avg_mfe", mfe)
    avg_bars = stats.get("avg_bars", bars)
    win_rate = stats.get("win_rate", 0)
    sample_size = stats.get("count", 1)

    # Format indicator ranges for the response
    rsi = indicators.get("rsi", 50)
    stoch = indicators.get("stoch", 50)
    adx = indicators.get("adx", 25)
    macd = indicators.get("macd", 0)
    supertrend = "bullish" if indicators.get("supertrend", 0) > 0 else "bearish"

    # Exit indicators (handle None values)
    exit_rsi = exit_ind.get("exit_rsi") or rsi
    exit_stoch = exit_ind.get("exit_stoch") or stoch
    exit_adx = exit_ind.get("exit_adx") or adx

    # Helper for MACD direction
    macd_dir = get_macd_bucket(macd)

    # Build rich reasoning based on correct choice
    if correct == "SB":
        reasoning = (
            f"Strong buy signal detected. "
            f"RSI at {rsi:.1f} (in the {bucket_value(rsi, RSI_BUCKETS)} zone) combined with "
            f"Stochastic at {stoch:.1f} ({bucket_value(stoch, STOCH_BUCKETS)}) indicates oversold conditions. "
            f"ADX at {adx:.1f} shows {bucket_value(adx, ADX_BUCKETS)} strength. "
            f"MACD is {macd_dir}. Supertrend is {supertrend}. "
            f"In {sample_size} similar setups with RSI {rsi-3:.0f}-{rsi+3:.0f}, Stoch {stoch-5:.0f}-{stoch+5:.0f}, "
            f"ADX {adx-3:.0f}-{adx+3:.0f}, MACD {macd_dir}, and {supertrend} trend, "
            f"we observed an average MFE of {avg_mfe:.2f}% within {avg_bars:.1f} candles "
            f"with a {win_rate:.0f}% win rate. "
            f"Exit when RSI reaches {exit_rsi:.0f} and Stoch approaches {exit_stoch:.0f}."
        )
    elif correct == "B":
        reasoning = (
            f"Moderate buy signal. "
            f"RSI at {rsi:.1f} ({bucket_value(rsi, RSI_BUCKETS)}) with "
            f"Stochastic at {stoch:.1f} ({bucket_value(stoch, STOCH_BUCKETS)}) suggests potential upside. "
            f"ADX at {adx:.1f} indicates {bucket_value(adx, ADX_BUCKETS)}. "
            f"MACD is {macd_dir}. Supertrend direction: {supertrend}. "
            f"Historical data from {sample_size} similar setups (RSI {rsi-3:.0f}-{rsi+3:.0f}, "
            f"Stoch {stoch-5:.0f}-{stoch+5:.0f}, ADX {adx-3:.0f}-{adx+3:.0f}, MACD {macd_dir}) shows "
            f"average MFE of {avg_mfe:.2f}% over {avg_bars:.1f} candles, {win_rate:.0f}% win rate. "
            f"Consider exit near RSI {exit_rsi:.0f}, Stoch {exit_stoch:.0f}."
        )
    elif correct == "S":
        reasoning = (
            f"Weak setup - skip recommended. "
            f"RSI at {rsi:.1f} is {bucket_value(rsi, RSI_BUCKETS)}, "
            f"Stoch at {stoch:.1f} is {bucket_value(stoch, STOCH_BUCKETS)}. "
            f"ADX of {adx:.1f} shows {bucket_value(adx, ADX_BUCKETS)}. "
            f"MACD is {macd_dir}. Supertrend: {supertrend}. "
            f"Analysis of {sample_size} similar patterns (RSI {rsi-3:.0f}-{rsi+3:.0f}, Stoch {stoch-5:.0f}-{stoch+5:.0f}, "
            f"ADX {adx-3:.0f}-{adx+3:.0f}, MACD {macd_dir}, {supertrend} trend) reveals "
            f"average MFE of only {avg_mfe:.2f}% in {avg_bars:.1f} candles with {win_rate:.0f}% success. "
            f"Insufficient edge for entry."
        )
    else:  # SS
        reasoning = (
            f"Strong skip - no edge. "
            f"RSI {rsi:.1f} ({bucket_value(rsi, RSI_BUCKETS)}), Stoch {stoch:.1f} ({bucket_value(stoch, STOCH_BUCKETS)}) "
            f"lack oversold conditions. ADX at {adx:.1f} indicates {bucket_value(adx, ADX_BUCKETS)}. "
            f"MACD is {macd_dir}. Supertrend: {supertrend}. "
            f"Historical analysis of {sample_size} matching setups (RSI {rsi-3:.0f}-{rsi+3:.0f}, "
            f"Stoch {stoch-5:.0f}-{stoch+5:.0f}, ADX {adx-3:.0f}-{adx+3:.0f}, MACD {macd_dir}, "
            f"{supertrend}) shows average MFE of {avg_mfe:.2f}% over {avg_bars:.1f} candles, "
            f"only {win_rate:.0f}% win rate. Risk/reward unfavorable."
        )

    return {
        "choice": correct,
        "reasoning": reasoning,
        "cluster_stats": {
            "sample_size": sample_size,
            "avg_mfe": round(avg_mfe, 2),
            "avg_bars": round(avg_bars, 1),
            "win_rate": round(win_rate, 1),
        },
        "exit_signal": f"RSI {exit_rsi:.0f}, Stoch {exit_stoch:.0f}, ADX {exit_adx:.0f}",
    }


def main():
    print(f"Loading data from {INPUT_FILE}...")

    # Load all records (skip malformed lines)
    records = []
    skipped = 0
    with open(INPUT_FILE) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
                if skipped <= 3:
                    print(f"  Skipping malformed line {line_num}: {line[:50]}...")

    if skipped > 0:
        print(f"  (Skipped {skipped} malformed lines)")

    print(f"Loaded {len(records)} records")

    # Build cluster statistics
    print("Building cluster statistics...")
    clusters = defaultdict(list)

    for record in records:
        indicators = record.get("entry_indicators", {})
        cluster_key = get_cluster_key(indicators)
        clusters[cluster_key].append({
            "mfe": record.get("mfe", 0),
            "bars": record.get("bars_to_mfe", 0),
            "is_winner": record.get("is_winner", False),
        })

    # Calculate statistics per cluster
    cluster_stats = {}
    for key, items in clusters.items():
        mfes = [i["mfe"] for i in items]
        bars = [i["bars"] for i in items if i["bars"] > 0]
        winners = sum(1 for i in items if i["is_winner"])

        cluster_stats[key] = {
            "count": len(items),
            "avg_mfe": statistics.mean(mfes) if mfes else 0,
            "avg_bars": statistics.mean(bars) if bars else 0,
            "win_rate": (winners / len(items) * 100) if items else 0,
        }

    print(f"Found {len(cluster_stats)} unique indicator clusters")

    # Show top clusters by sample size
    print("\nTop clusters by sample size:")
    sorted_clusters = sorted(cluster_stats.items(), key=lambda x: x[1]["count"], reverse=True)
    for key, stats in sorted_clusters[:10]:
        print(f"  {describe_cluster(key)}: {stats['count']} samples, "
              f"avg MFE {stats['avg_mfe']:.2f}%, win rate {stats['win_rate']:.0f}%")

    # Enrich records with new perfect_response
    print(f"\nEnriching records...")
    enriched = []
    for record in records:
        record["perfect_response"] = generate_rich_response(record, cluster_stats)
        enriched.append(record)

    # Write enriched data
    print(f"Writing to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        for record in enriched:
            f.write(json.dumps(record) + "\n")

    print(f"\nDone! Enriched {len(enriched)} records")

    # Show sample
    print("\n" + "="*60)
    print("SAMPLE ENRICHED RESPONSE:")
    print("="*60)
    sample = enriched[0]
    print(f"Symbol: {sample['symbol']}")
    print(f"Correct choice: {sample['correct_choice']}")
    print(f"Entry indicators: {sample['entry_indicators']}")
    print(f"\nPerfect response reasoning:")
    print(sample["perfect_response"]["reasoning"])


if __name__ == "__main__":
    main()
