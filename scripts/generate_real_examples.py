#!/usr/bin/env python3
"""
Generate Real Examples from Actual Peak/Trough Data

Finds:
- Highest MFE entries -> SB examples (buy at trough)
- Exit points of those entries -> SS examples (sell at peak)
- Moderate MFE entries -> B examples
- Low MFE entries -> S examples

Uses ALL available indicators and finds correlations.
"""

import json
import psycopg2
import statistics
from pathlib import Path
from collections import defaultdict

# Key indicators to include in examples (most relevant for trading)
KEY_INDICATORS = [
    # Momentum oscillators
    'rsi_14', 'rsi_7', 'rsi_21',
    'stoch_k', 'stoch_d', 'stochrsi_k', 'stochrsi_d',
    'cci_14', 'cci_20', 'willr_14',
    'roc_10', 'mom_10', 'ao', 'uo',
    'cmo_14', 'tsi', 'mfi_14',

    # Trend indicators
    'adx_14', 'plus_di', 'minus_di', 'adxr_14',
    'macd_line', 'macd_signal', 'macd_histogram',
    'supertrend_direction', 'psar_reversal',
    'aroon_up', 'aroon_down', 'aroon_osc',
    'fisher', 'vortex_pos', 'vortex_neg',

    # Volatility
    'atr_14', 'atr_pct', 'bb_width', 'bb_pct',
    'kc_upper', 'kc_lower', 'squeeze_on',
    'natr_14', 'chop_14',

    # Volume
    'obv', 'cmf_20', 'pvt', 'efi_13', 'kvo',
    'volume_sma_20', 'tick_cvd_ratio',

    # Price position
    'zscore_14', 'zscore_30', 'bb_percent',

    # Market context
    'regime', 'fear_greed_value',
    'order_imbalance', 'book_avg_imbalance',
]


def get_db_connection():
    return psycopg2.connect(
        host='localhost', dbname='coinswarm',
        user='coinswarm', password='coinswarm_dev_2024'
    )


def get_candle_with_all_indicators(conn, symbol, timeframe, candle_time):
    """Get a single candle with all indicator values."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM enhanced_candles
        WHERE symbol = %s AND timeframe = %s AND time = %s
    """, (symbol, timeframe, candle_time))

    row = cur.fetchone()
    if not row:
        return None

    # Get column names
    col_names = [desc[0] for desc in cur.description]
    return dict(zip(col_names, row))


def get_forward_mfe_with_exit(conn, symbol, timeframe, entry_time, bars=24):
    """Get MFE and the exact candle where MFE occurs (the exit point)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT time, high, low, close
        FROM enhanced_candles
        WHERE symbol = %s AND timeframe = %s AND time > %s
        ORDER BY time LIMIT %s
    """, (symbol, timeframe, entry_time, bars))

    rows = cur.fetchall()
    if not rows:
        return 0, 0, None

    entry_candle = get_candle_with_all_indicators(conn, symbol, timeframe, entry_time)
    if not entry_candle:
        return 0, 0, None

    entry_price = float(entry_candle['close'])
    if entry_price == 0:
        return 0, 0, None

    max_high = 0
    exit_time = None
    bars_to_mfe = 0

    for i, (time, high, low, close) in enumerate(rows):
        if float(high) > max_high:
            max_high = float(high)
            exit_time = time
            bars_to_mfe = i + 1

    mfe = (max_high - entry_price) / entry_price * 100
    return mfe, bars_to_mfe, exit_time


def find_best_entries(conn, min_mfe=2.0, limit=50):
    """Find candles with highest forward MFE (best buy opportunities)."""
    cur = conn.cursor()

    # Get recent candles with low RSI/Stoch (potential bottoms)
    cur.execute("""
        SELECT symbol, timeframe, time, close, rsi_14, stoch_k
        FROM enhanced_candles
        WHERE timeframe = '1h'
        AND time > NOW() - INTERVAL '180 days'
        AND rsi_14 IS NOT NULL AND stoch_k IS NOT NULL
        AND rsi_14 < 40 AND stoch_k < 30
        ORDER BY time DESC
        LIMIT 500
    """)

    candidates = cur.fetchall()
    print(f"Checking {len(candidates)} low RSI/Stoch candidates...")

    best_entries = []
    for symbol, tf, time, close, rsi, stoch in candidates:
        mfe, bars, exit_time = get_forward_mfe_with_exit(conn, symbol, tf, time)
        if mfe >= min_mfe and exit_time:
            entry_candle = get_candle_with_all_indicators(conn, symbol, tf, time)
            exit_candle = get_candle_with_all_indicators(conn, symbol, tf, exit_time)
            if entry_candle and exit_candle:
                best_entries.append({
                    'entry': entry_candle,
                    'exit': exit_candle,
                    'mfe': mfe,
                    'bars_to_mfe': bars,
                })

    # Sort by MFE descending
    best_entries.sort(key=lambda x: x['mfe'], reverse=True)
    return best_entries[:limit]


def find_worst_entries(conn, max_mfe=0.5, limit=50):
    """Find candles with low MFE (poor buy opportunities - should skip)."""
    cur = conn.cursor()

    # Get candles with HIGH RSI/Stoch (potential tops - wrong time to buy)
    cur.execute("""
        SELECT symbol, timeframe, time, close, rsi_14, stoch_k
        FROM enhanced_candles
        WHERE timeframe = '1h'
        AND time > NOW() - INTERVAL '180 days'
        AND rsi_14 IS NOT NULL AND stoch_k IS NOT NULL
        AND rsi_14 > 55 AND stoch_k > 70
        ORDER BY time DESC
        LIMIT 500
    """)

    candidates = cur.fetchall()
    print(f"Checking {len(candidates)} high RSI/Stoch candidates...")

    worst_entries = []
    for symbol, tf, time, close, rsi, stoch in candidates:
        mfe, bars, exit_time = get_forward_mfe_with_exit(conn, symbol, tf, time)
        if mfe <= max_mfe:
            entry_candle = get_candle_with_all_indicators(conn, symbol, tf, time)
            if entry_candle:
                worst_entries.append({
                    'entry': entry_candle,
                    'mfe': mfe,
                    'bars_to_mfe': bars,
                })

    # Sort by MFE ascending (worst first)
    worst_entries.sort(key=lambda x: x['mfe'])
    return worst_entries[:limit]


def format_indicators(candle, keys=None):
    """Format indicator values for prompt."""
    if keys is None:
        keys = KEY_INDICATORS

    parts = []
    for k in keys:
        v = candle.get(k)
        if v is not None:
            if isinstance(v, float):
                if abs(v) < 0.01:
                    parts.append(f"{k}={v:.4f}")
                elif abs(v) < 100:
                    parts.append(f"{k}={v:.2f}")
                else:
                    parts.append(f"{k}={v:.0f}")
            else:
                parts.append(f"{k}={v}")
    return ", ".join(parts)


def find_indicator_correlations(entries, threshold=0.3):
    """Find which indicators correlate with MFE."""
    correlations = {}

    for ind in KEY_INDICATORS:
        values = []
        mfes = []
        for e in entries:
            v = e['entry'].get(ind)
            if v is not None and isinstance(v, (int, float)):
                values.append(float(v))
                mfes.append(e['mfe'])

        if len(values) >= 10:
            # Simple correlation: mean value for high MFE vs low MFE
            high_mfe = [v for v, m in zip(values, mfes) if m > 2.0]
            low_mfe = [v for v, m in zip(values, mfes) if m < 1.0]

            if high_mfe and low_mfe:
                high_mean = statistics.mean(high_mfe)
                low_mean = statistics.mean(low_mfe)
                diff = high_mean - low_mean

                # Normalize by range
                all_vals = values
                val_range = max(all_vals) - min(all_vals) if all_vals else 1
                if val_range > 0:
                    norm_diff = diff / val_range
                    if abs(norm_diff) > threshold:
                        correlations[ind] = {
                            'high_mfe_mean': high_mean,
                            'low_mfe_mean': low_mean,
                            'diff': diff,
                            'norm_diff': norm_diff,
                            'direction': 'lower_better' if norm_diff < 0 else 'higher_better'
                        }

    return correlations


def generate_example(entry_data, choice, correlations):
    """Generate a formatted example with reasoning."""
    candle = entry_data['entry']
    mfe = entry_data['mfe']
    bars = entry_data.get('bars_to_mfe', 0)

    # Select most relevant indicators based on correlations
    relevant_inds = list(correlations.keys())[:15]  # Top 15 correlated

    # Add always-include indicators
    must_have = ['rsi_14', 'stoch_k', 'adx_14', 'macd_histogram', 'supertrend_direction',
                 'bb_pct', 'atr_pct', 'cmf_20', 'mfi_14', 'squeeze_on']
    for ind in must_have:
        if ind not in relevant_inds:
            relevant_inds.append(ind)

    # Format indicators
    ind_str = format_indicators(candle, relevant_inds[:20])

    # Build reasoning based on actual values and correlations
    reasons = []

    rsi = candle.get('rsi_14', 50)
    stoch = candle.get('stoch_k', 50)
    adx = candle.get('adx_14', 25)
    bb_pct = candle.get('bb_pct', 0.5)
    mfi = candle.get('mfi_14', 50)
    cmf = candle.get('cmf_20', 0)

    if choice in ['SB', 'B']:
        if rsi < 35:
            reasons.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 45:
            reasons.append(f"RSI {rsi:.0f} low-neutral")

        if stoch < 25:
            reasons.append(f"Stoch {stoch:.0f} at extremes")
        elif stoch < 40:
            reasons.append(f"Stoch {stoch:.0f} depressed")

        if bb_pct and bb_pct < 0.2:
            reasons.append(f"BB% {bb_pct:.2f} near lower band")

        if mfi and mfi < 30:
            reasons.append(f"MFI {mfi:.0f} shows selling exhaustion")

        if adx < 20:
            reasons.append(f"ADX {adx:.0f} weak trend favors reversal")

        reasons.append(f"Historical MFE {mfe:.1f}% in {bars} bars")

    else:  # SS, S
        if rsi > 60:
            reasons.append(f"RSI {rsi:.0f} elevated")
        elif rsi > 50:
            reasons.append(f"RSI {rsi:.0f} neutral-high")

        if stoch > 70:
            reasons.append(f"Stoch {stoch:.0f} overbought zone")
        elif stoch > 55:
            reasons.append(f"Stoch {stoch:.0f} mid-high")

        if bb_pct and bb_pct > 0.8:
            reasons.append(f"BB% {bb_pct:.2f} near upper band")

        if mfi and mfi > 70:
            reasons.append(f"MFI {mfi:.0f} buying exhaustion")

        reasons.append(f"MFE only {mfe:.1f}% - poor risk/reward")

    reasoning = ". ".join(reasons) + "."

    return {
        'indicators': ind_str,
        'choice': choice,
        'reasoning': reasoning,
        'mfe': mfe,
        'bars': bars,
        'symbol': candle.get('symbol'),
        'time': str(candle.get('time')),
    }


def main():
    conn = get_db_connection()

    print("=" * 60)
    print("FINDING REAL EXAMPLES FROM DATA")
    print("=" * 60)

    # Find best entries (SB candidates)
    print("\n1. Finding best entries (high MFE = Strong Buy)...")
    best = find_best_entries(conn, min_mfe=2.5, limit=30)
    print(f"   Found {len(best)} entries with MFE >= 2.5%")

    # Find moderate entries (B candidates)
    print("\n2. Finding moderate entries (B)...")
    moderate_cur = conn.cursor()
    moderate_cur.execute("""
        SELECT symbol, timeframe, time
        FROM enhanced_candles
        WHERE timeframe = '1h'
        AND time > NOW() - INTERVAL '180 days'
        AND rsi_14 BETWEEN 40 AND 50
        AND stoch_k BETWEEN 30 AND 50
        ORDER BY time DESC LIMIT 200
    """)
    moderate = []
    for symbol, tf, time in moderate_cur.fetchall():
        mfe, bars, exit_time = get_forward_mfe_with_exit(conn, symbol, tf, time)
        if 1.5 <= mfe <= 2.5:
            candle = get_candle_with_all_indicators(conn, symbol, tf, time)
            if candle:
                moderate.append({'entry': candle, 'mfe': mfe, 'bars_to_mfe': bars})
    moderate = moderate[:20]
    print(f"   Found {len(moderate)} moderate entries")

    # Find worst entries (SS candidates)
    print("\n3. Finding worst entries (low MFE = Strong Skip)...")
    worst = find_worst_entries(conn, max_mfe=0.5, limit=30)
    print(f"   Found {len(worst)} entries with MFE <= 0.5%")

    # Find correlations
    print("\n4. Analyzing indicator correlations...")
    all_entries = best + moderate + worst
    correlations = find_indicator_correlations(all_entries)
    print(f"   Found {len(correlations)} significant correlations")

    # Show top correlations
    sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]['norm_diff']), reverse=True)
    print("\n   Top correlations with MFE:")
    for ind, data in sorted_corr[:10]:
        print(f"     {ind}: {data['direction']} (high MFE mean: {data['high_mfe_mean']:.2f}, low: {data['low_mfe_mean']:.2f})")

    # Generate examples
    print("\n5. Generating examples...")

    examples = {
        'SB': [],
        'B': [],
        'S': [],
        'SS': [],
    }

    # SB from best entries
    for entry in best[:5]:
        ex = generate_example(entry, 'SB', correlations)
        examples['SB'].append(ex)

    # SS from exit points of best entries (peaks)
    for entry in best[:5]:
        if 'exit' in entry:
            exit_data = {'entry': entry['exit'], 'mfe': 0.3, 'bars_to_mfe': 0}
            ex = generate_example(exit_data, 'SS', correlations)
            ex['reasoning'] = f"At peak after {entry['mfe']:.1f}% move. " + ex['reasoning']
            examples['SS'].append(ex)

    # B from moderate
    for entry in moderate[:5]:
        ex = generate_example(entry, 'B', correlations)
        examples['B'].append(ex)

    # S from low-mfe entries
    for entry in worst[10:15]:  # Skip worst, use mediocre
        ex = generate_example(entry, 'S', correlations)
        examples['S'].append(ex)

    # SS from absolute worst
    for entry in worst[:5]:
        ex = generate_example(entry, 'SS', correlations)
        examples['SS'].append(ex)

    # Output
    print("\n" + "=" * 60)
    print("GENERATED EXAMPLES")
    print("=" * 60)

    for choice in ['SB', 'B', 'S', 'SS']:
        print(f"\n### {choice} EXAMPLES ###")
        for ex in examples[choice]:
            print(f"\n**{ex['symbol']} @ {ex['time']}** (MFE: {ex['mfe']:.1f}%)")
            print(f"Indicators: {ex['indicators'][:200]}...")
            print(f"Response: {{'choice': '{ex['choice']}', 'reasoning': '{ex['reasoning']}'}}")

    # Save to file
    output_file = Path(__file__).parent.parent / 'data' / 'real_examples.json'
    with open(output_file, 'w') as f:
        json.dump({
            'correlations': {k: {kk: str(vv) if not isinstance(vv, (int, float, str)) else vv
                                 for kk, vv in v.items()}
                            for k, v in correlations.items()},
            'examples': examples,
        }, f, indent=2, default=str)
    print(f"\n\nSaved to {output_file}")


if __name__ == '__main__':
    main()
