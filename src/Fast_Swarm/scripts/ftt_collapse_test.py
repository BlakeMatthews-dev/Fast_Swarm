"""
FTT Collapse Test: Bear Protection vs FTX Token Crash

Downloads FTT/USD from CryptoCompare, enhances with indicators,
and tests 2-TF Bear Protection (1h/4h confirmation).

FTT Timeline:
- Nov 2: CoinDesk article exposes Alameda
- Nov 6: Binance announces selling FTT
- Nov 7-8: Bank run, FTT drops 80%
- Nov 11: FTX bankruptcy
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
import statistics
import json

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# AJ config
ACC_THRESH = -1.5
JERK_THRESH = -0.5
CAPITAL = 1000


def fetch_crypto_compare(fsym, tsym, endpoint, limit, to_ts):
    """Fetch OHLCV from CryptoCompare."""
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {"fsym": fsym, "tsym": tsym, "limit": limit, "toTs": to_ts}
    resp = requests.get(url, params=params)
    data = resp.json()
    if data.get("Response") == "Success":
        return data["Data"]["Data"]
    return []


def compute_zscore(values, lookback=20):
    """Rolling z-score."""
    zscores = [None] * len(values)
    for i in range(lookback, len(values)):
        window = [v for v in values[i - lookback : i] if v is not None]
        if len(window) >= 2:
            m, s = statistics.mean(window), statistics.stdev(window)
            zscores[i] = (values[i] - m) / s if s > 0 else 0
    return zscores


def derivative(vals):
    """First derivative."""
    return [None] + [
        vals[i] - vals[i - 1]
        if vals[i] is not None and vals[i - 1] is not None
        else None
        for i in range(1, len(vals))
    ]


def compute_adx(highs, lows, closes, period=14):
    """Compute ADX indicator."""
    n = len(closes)
    if n < period + 1:
        return [None] * n

    tr = [None]
    for i in range(1, n):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i - 1])
        l_pc = abs(lows[i] - closes[i - 1])
        tr.append(max(h_l, h_pc, l_pc))

    plus_dm = [None]
    minus_dm = [None]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

    atr = [None] * n
    smooth_plus = [None] * n
    smooth_minus = [None] * n

    if n > period:
        atr[period] = sum(t for t in tr[1 : period + 1] if t) / period
        smooth_plus[period] = (
            sum(d for d in plus_dm[1 : period + 1] if d is not None) / period
        )
        smooth_minus[period] = (
            sum(d for d in minus_dm[1 : period + 1] if d is not None) / period
        )

        for i in range(period + 1, n):
            if atr[i - 1] and tr[i]:
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
            if smooth_plus[i - 1] is not None and plus_dm[i] is not None:
                smooth_plus[i] = (smooth_plus[i - 1] * (period - 1) + plus_dm[i]) / period
            if smooth_minus[i - 1] is not None and minus_dm[i] is not None:
                smooth_minus[i] = (
                    smooth_minus[i - 1] * (period - 1) + minus_dm[i]
                ) / period

    plus_di = [None] * n
    minus_di = [None] * n
    for i in range(period, n):
        if atr[i] and atr[i] > 0:
            plus_di[i] = 100 * smooth_plus[i] / atr[i] if smooth_plus[i] else 0
            minus_di[i] = 100 * smooth_minus[i] / atr[i] if smooth_minus[i] else 0

    dx = [None] * n
    for i in range(period, n):
        if plus_di[i] is not None and minus_di[i] is not None:
            di_sum = plus_di[i] + minus_di[i]
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum if di_sum > 0 else 0

    adx = [None] * n
    if n > 2 * period:
        valid_dx = [d for d in dx[period : 2 * period] if d is not None]
        if valid_dx:
            adx[2 * period - 1] = statistics.mean(valid_dx)
            for i in range(2 * period, n):
                if adx[i - 1] is not None and dx[i] is not None:
                    adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return adx


def enhance_candles(candles):
    """Add indicators to candles."""
    times = [datetime.fromtimestamp(c["time"], tz=timezone.utc) for c in candles]
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c.get("volumeto", c.get("volume", 0)) for c in candles]
    opens = [c["open"] for c in candles]

    # Close derivatives
    close_vel = derivative(closes)
    close_acc = derivative(close_vel)
    close_acc_clean = [x if x else 0 for x in close_acc]
    close_acc_z = compute_zscore(close_acc_clean)
    close_vel_clean = [x if x else 0 for x in close_vel]
    close_vel_z = compute_zscore(close_vel_clean)

    # ADX and jerk
    adx = compute_adx(highs, lows, closes)
    adx_vel = derivative(adx)
    adx_acc = derivative(adx_vel)
    adx_acc_clean = [x if x else 0 for x in adx_acc]
    adx_jerk_z = compute_zscore(adx_acc_clean)

    rows = []
    for i in range(len(candles)):
        rows.append(
            {
                "time": times[i],
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i],
                "close_velocity_zscore": close_vel_z[i],
                "close_acceleration_zscore": close_acc_z[i],
                "adx_14": adx[i],
                "adx_14_jerk_zscore": adx_jerk_z[i],
            }
        )
    return rows


def check_defensive(row):
    """Check if AJ signal fires."""
    acc = row.get("close_acceleration_zscore")
    jerk = row.get("adx_14_jerk_zscore")
    if acc is None or jerk is None:
        return False
    return acc < ACC_THRESH and jerk < JERK_THRESH


def max_drawdown(equity):
    """Compute max drawdown percentage."""
    peak = equity[0]
    mdd = 0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        mdd = max(mdd, dd)
    return mdd * 100


def run_ftt_test():
    print("=" * 80)
    print("FTT COLLAPSE TEST: Bear Protection vs FTX Token")
    print("=" * 80)

    # Fetch data
    to_ts = int(datetime(2022, 12, 31, tzinfo=timezone.utc).timestamp())

    print("\nFetching FTT/USD 1h data...")
    candles_1h = fetch_crypto_compare("FTT", "USD", "histohour", 2000, to_ts)
    print(f"Got {len(candles_1h)} 1h candles")

    if not candles_1h:
        print("ERROR: Failed to fetch FTT data")
        return

    # Aggregate to 4h
    print("Aggregating to 4h...")
    candles_4h = []
    for i in range(0, len(candles_1h) - 3, 4):
        chunk = candles_1h[i : i + 4]
        if len(chunk) == 4:
            candles_4h.append(
                {
                    "time": chunk[0]["time"],
                    "open": chunk[0]["open"],
                    "high": max(c["high"] for c in chunk),
                    "low": min(c["low"] for c in chunk),
                    "close": chunk[-1]["close"],
                    "volumeto": sum(c["volumeto"] for c in chunk),
                }
            )
    print(f"Created {len(candles_4h)} 4h candles")

    # Enhance
    print("\nEnhancing with indicators...")
    rows_1h = enhance_candles(candles_1h)
    rows_4h = enhance_candles(candles_4h)

    # Date range
    print(f"Date range: {rows_1h[0]['time'].date()} to {rows_1h[-1]['time'].date()}")

    # Crash stats
    crash_start = datetime(2022, 11, 6, tzinfo=timezone.utc)
    crash_end = datetime(2022, 11, 14, tzinfo=timezone.utc)

    pre_crash = [r for r in rows_1h if r["time"] < crash_start]
    crash_rows = [r for r in rows_1h if crash_start <= r["time"] <= crash_end]

    if pre_crash and crash_rows:
        pre_price = pre_crash[-1]["close"]
        crash_low = min(r["close"] for r in crash_rows)
        print(f"\nFTT CRASH: ${pre_price:.2f} -> ${crash_low:.2f} ({(crash_low/pre_price-1)*100:.1f}%)")

    # Align timeframes
    tf1_data = {r["time"]: r for r in rows_1h}
    tf4_data = {r["time"]: r for r in rows_4h}

    aligned = []
    tf4_times = sorted(tf4_data.keys())
    tf4_idx = 0

    for t in sorted(tf1_data.keys()):
        while tf4_idx + 1 < len(tf4_times) and tf4_times[tf4_idx + 1] <= t:
            tf4_idx += 1
        if tf4_idx < len(tf4_times) and tf4_times[tf4_idx] <= t:
            aligned.append((t, tf1_data[t], tf4_data[tf4_times[tf4_idx]]))

    print(f"\nAligned {len(aligned)} periods for 1h/4h test")

    # Run both single-TF and 2-TF tests
    def run_backtest(data_rows, mode="1h-only"):
        """Run backtest with specified mode."""
        prices = [r["close"] for r in data_rows]
        if not prices or prices[0] <= 0:
            return None

        bh_shares = CAPITAL / prices[0]
        ctc_shares = CAPITAL / prices[0]
        ctc_cash = 0
        in_def = False

        bh_equity = [CAPITAL]
        ctc_equity = [CAPITAL]
        signals = []

        warmup = 50
        for i in range(warmup, len(data_rows)):
            price = prices[i]
            row = data_rows[i]

            bh_equity.append(bh_shares * price)

            is_def = check_defensive(row)

            if is_def and ctc_shares > 0:
                ctc_cash = ctc_shares * price
                ctc_shares = 0
                in_def = True
                signals.append((row["time"], price, "EXIT", row["close_acceleration_zscore"], row["adx_14_jerk_zscore"]))
            elif not is_def and in_def and ctc_cash > 0:
                ctc_shares = ctc_cash / price
                ctc_cash = 0
                in_def = False
                signals.append((row["time"], price, "ENTER", None, None))

            ctc_equity.append(ctc_shares * price + ctc_cash)

        return {
            "bh_equity": bh_equity,
            "ctc_equity": ctc_equity,
            "signals": signals,
            "in_def": in_def,
            "bh_roi": (bh_equity[-1] / CAPITAL - 1) * 100,
            "ctc_roi": (ctc_equity[-1] / CAPITAL - 1) * 100,
            "bh_dd": max_drawdown(bh_equity),
            "ctc_dd": max_drawdown(ctc_equity),
        }

    # Test 1: Single TF (1h only)
    print("\n" + "=" * 80)
    print("TEST 1: SINGLE TIMEFRAME (1h only)")
    print("=" * 80)

    result_1h = run_backtest(rows_1h, "1h-only")
    if result_1h:
        print(f"\nBuy & Hold:  {result_1h['bh_roi']:>+8.1f}% ROI, {result_1h['bh_dd']:>6.1f}% MaxDD")
        print(f"CTC:         {result_1h['ctc_roi']:>+8.1f}% ROI, {result_1h['ctc_dd']:>6.1f}% MaxDD")
        print(f"Protection:  {result_1h['ctc_roi'] - result_1h['bh_roi']:>+8.1f}%")
        print(f"Signals: {len(result_1h['signals'])}")

        # Show crash signals
        crash_sigs = [s for s in result_1h['signals'] if crash_start <= s[0] <= crash_end]
        pre_sigs = [s for s in result_1h['signals'] if datetime(2022, 11, 1, tzinfo=timezone.utc) < s[0] < crash_start]

        if pre_sigs:
            print(f"\nPre-crash signals (Nov 1-5): {len(pre_sigs)}")
            for t, p, action, acc, jerk in pre_sigs[-3:]:
                print(f"  {t.strftime('%m-%d %H:%M')}: {action} ${p:.2f} (acc={acc:.2f})" if acc else f"  {t.strftime('%m-%d %H:%M')}: {action} ${p:.2f}")

        if crash_sigs:
            print(f"\nCrash signals (Nov 6-14): {len(crash_sigs)}")
            for t, p, action, acc, jerk in crash_sigs[:3]:
                print(f"  {t.strftime('%m-%d %H:%M')}: {action} ${p:.2f} (acc={acc:.2f})" if acc else f"  {t.strftime('%m-%d %H:%M')}: {action} ${p:.2f}")

    # Test 2: Single TF (4h only)
    print("\n" + "=" * 80)
    print("TEST 2: SINGLE TIMEFRAME (4h only)")
    print("=" * 80)

    result_4h = run_backtest(rows_4h, "4h-only")
    if result_4h:
        print(f"\nBuy & Hold:  {result_4h['bh_roi']:>+8.1f}% ROI, {result_4h['bh_dd']:>6.1f}% MaxDD")
        print(f"CTC:         {result_4h['ctc_roi']:>+8.1f}% ROI, {result_4h['ctc_dd']:>6.1f}% MaxDD")
        print(f"Protection:  {result_4h['ctc_roi'] - result_4h['bh_roi']:>+8.1f}%")
        print(f"Signals: {len(result_4h['signals'])}")

    # Test 3: 2-TF confirmation (original)
    print("\n" + "=" * 80)
    print("TEST 3: 2-TF CONFIRMATION (1h AND 4h must agree)")
    print("=" * 80)

    # Backtest with alignment
    prices = [a[1]["close"] for a in aligned]
    if not prices or prices[0] <= 0:
        print("ERROR: No valid price data")
        return

    bh_shares = CAPITAL / prices[0]
    ctc_shares = CAPITAL / prices[0]
    ctc_cash = 0
    in_def = False

    bh_equity = [CAPITAL]
    ctc_equity = [CAPITAL]
    signals = []

    warmup = 50
    for i in range(warmup, len(aligned)):
        t, r1h, r4h = aligned[i]
        price = prices[i]

        bh_equity.append(bh_shares * price)

        # 2-TF confirmation
        def_1h = check_defensive(r1h)
        def_4h = check_defensive(r4h)
        is_def = def_1h and def_4h

        if is_def and ctc_shares > 0:
            ctc_cash = ctc_shares * price
            ctc_shares = 0
            in_def = True
            signals.append((t, price, "EXIT", r1h["close_acceleration_zscore"], r1h["adx_14_jerk_zscore"]))
        elif not is_def and in_def and ctc_cash > 0:
            ctc_shares = ctc_cash / price
            ctc_cash = 0
            in_def = False
            signals.append((t, price, "ENTER", None, None))

        ctc_equity.append(ctc_shares * price + ctc_cash)

    # Results
    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100
    bh_dd = max_drawdown(bh_equity)
    ctc_dd = max_drawdown(ctc_equity)

    print("\n" + "=" * 80)
    print("FTT BEAR PROTECTION RESULTS (1h/4h 2-TF Confirmation)")
    print("=" * 80)
    print(f"\nPeriod: {aligned[warmup][0].date()} to {aligned[-1][0].date()}")
    print()
    print(f"Buy & Hold:  {bh_roi:>+8.1f}% ROI, {bh_dd:>6.1f}% MaxDD")
    print(f"CTC:         {ctc_roi:>+8.1f}% ROI, {ctc_dd:>6.1f}% MaxDD")
    print(f"Protection:  {ctc_roi - bh_roi:>+8.1f}%")
    print()
    print(f"Final B&H value:  ${bh_equity[-1]:.2f}")
    print(f"Final CTC value:  ${ctc_equity[-1]:.2f}")

    # Signal analysis
    crash_signals = [s for s in signals if crash_start <= s[0] <= crash_end]
    pre_signals = [
        s
        for s in signals
        if datetime(2022, 11, 1, tzinfo=timezone.utc) < s[0] < crash_start
    ]

    print(f"\nTotal signals: {len(signals)}")

    if pre_signals:
        print(f"\nPRE-CRASH SIGNALS (Nov 1-5):")
        for t, p, action, acc, jerk in pre_signals[-5:]:
            if acc is not None:
                print(f"  {t.strftime('%Y-%m-%d %H:%M')}: {action} at ${p:.2f} (acc={acc:.2f}, jerk={jerk:.2f})")
            else:
                print(f"  {t.strftime('%Y-%m-%d %H:%M')}: {action} at ${p:.2f}")

    if crash_signals:
        print(f"\nCRASH SIGNALS (Nov 6-14):")
        for t, p, action, acc, jerk in crash_signals[:5]:
            if acc is not None:
                print(f"  {t.strftime('%Y-%m-%d %H:%M')}: {action} at ${p:.2f} (acc={acc:.2f}, jerk={jerk:.2f})")
            else:
                print(f"  {t.strftime('%Y-%m-%d %H:%M')}: {action} at ${p:.2f}")

    print(f"\nFinal state: {'IN CASH' if in_def else 'IN POSITION'}")

    # Verdict
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)
    protection = ctc_roi - bh_roi
    if protection > 10:
        print(f"STRONG PROTECTION: +{protection:.1f}% saved vs holding FTT")
    elif protection > 0:
        print(f"PROTECTED: +{protection:.1f}% saved vs holding FTT")
    else:
        print(f"FAILED: Bear Protection did not help on FTT")


if __name__ == "__main__":
    run_ftt_test()
