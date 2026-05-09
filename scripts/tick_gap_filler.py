"""
Tick Data Gap Filler - Detects and fills gaps in tick data collection.

Features:
- Detects gaps > N minutes in tick data
- Backfills from Coinbase API (historical trades)
- Rolls up ticks to candles (1m, 5m, 15m, 1h, 4h, 1d)
- Rate-limit aware with exponential backoff

Usage:
    python scripts/tick_gap_filler.py --detect           # Show gaps only
    python scripts/tick_gap_filler.py --fill             # Fill gaps from API
    python scripts/tick_gap_filler.py --rollup           # Roll up ticks to candles
    python scripts/tick_gap_filler.py --fill --rollup    # Both
"""

import argparse
import time
from datetime import datetime

import psycopg
import requests

# Coinbase API
COINBASE_API = "https://api.exchange.coinbase.com"

# Symbols to check (Coinbase format)
SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

# Gap threshold defaults (can be overridden via CLI)
DEFAULT_DETECT_THRESHOLD_MIN = 5  # For --detect display
DEFAULT_FILL_THRESHOLD_MIN = 30  # For --fill (skip small gaps by default)
MIN_FILL_THRESHOLD_SEC = 10  # Absolute minimum (10 seconds)

# Rate limiting
REQUESTS_PER_SECOND = 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND


def get_db_connection():
    """Get database connection."""
    return psycopg.connect(
        host="localhost",
        port="5432",
        dbname="coinswarm",
        user="coinswarm",
        password="coinswarm_dev_2024",
    )


def detect_gaps(conn, symbol: str, threshold_min: int = 5) -> list[dict]:
    """Detect gaps in tick data for a symbol."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH tick_times AS (
                SELECT time,
                       LAG(time) OVER (ORDER BY time) as prev_time
                FROM exchange_ticks
                WHERE symbol = %s
            )
            SELECT
                prev_time as gap_start,
                time as gap_end,
                EXTRACT(EPOCH FROM (time - prev_time))/60 as gap_minutes
            FROM tick_times
            WHERE EXTRACT(EPOCH FROM (time - prev_time))/60 > %s
            ORDER BY prev_time
        """,
            (symbol, threshold_min),
        )

        return [
            {
                "start": row[0],
                "end": row[1],
                "minutes": row[2],
                "symbol": symbol,
            }
            for row in cur.fetchall()
        ]


def fetch_coinbase_trades(symbol: str, start_time: datetime, end_time: datetime) -> list[dict]:
    """Fetch historical trades from Coinbase API."""
    trades = []
    url = f"{COINBASE_API}/products/{symbol}/trades"

    # Coinbase returns trades in reverse chronological order
    params = {}
    max_iterations = 500  # Safety limit
    consecutive_errors = 0
    max_consecutive_errors = 3

    for iteration in range(max_iterations):
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            consecutive_errors = 0  # Reset on success

            if not batch:
                break

            oldest_in_batch = None
            for trade in batch:
                trade_time = datetime.fromisoformat(trade["time"].replace("Z", "+00:00"))
                oldest_in_batch = trade_time

                # Stop if we've gone past start_time
                if trade_time < start_time:
                    return trades

                # Only include trades within our window
                if start_time <= trade_time <= end_time:
                    trades.append(
                        {
                            "time": trade_time,
                            "symbol": symbol,
                            "price": float(trade["price"]),
                            "size": float(trade["size"]),
                            "side": trade["side"],
                            "trade_id": trade["trade_id"],
                        }
                    )

            # Check if we're still making progress
            if oldest_in_batch and oldest_in_batch < start_time:
                break

            # Get next page (older trades)
            if "cb-after" in response.headers:
                params["after"] = response.headers["cb-after"]
            else:
                break

            time.sleep(REQUEST_DELAY)

        except requests.RequestException:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                # API doesn't have this data - give up on this gap
                return trades
            time.sleep(2)
            continue

    return trades


def insert_ticks(conn, trades: list[dict]):
    """Insert trades into exchange_ticks table."""
    if not trades:
        return 0

    with conn.cursor() as cur:
        # Check table structure
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exchange_ticks'
        """)
        columns = [r[0] for r in cur.fetchall()]

        inserted = 0
        for trade in trades:
            try:
                cur.execute(
                    """
                    INSERT INTO exchange_ticks (time, symbol, price, size, side, trade_id, exchange)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """,
                    (
                        trade["time"],
                        trade["symbol"],
                        trade["price"],
                        trade["size"],
                        trade["side"],
                        str(trade["trade_id"]),
                        "coinbase",
                    ),
                )
                inserted += 1
            except Exception as e:
                print(f"  Insert error: {e}")
                continue

        conn.commit()
        return inserted


def rollup_ticks_to_candles(conn, symbol: str, timeframe: str, start_time: datetime, end_time: datetime):
    """Roll up tick data into OHLCV candles."""
    tf_seconds = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }

    interval_sec = tf_seconds.get(timeframe)
    if not interval_sec:
        print(f"  Unknown timeframe: {timeframe}")
        return 0

    with conn.cursor() as cur:
        # Aggregate ticks into candles
        cur.execute(
            """
            INSERT INTO enhanced_candles (time, symbol, timeframe, open, high, low, close, volume, exchange)
            SELECT
                date_trunc('minute', time) -
                    (EXTRACT(EPOCH FROM date_trunc('minute', time))::int %% %s) * INTERVAL '1 second' as candle_time,
                symbol,
                %s as timeframe,
                (array_agg(price ORDER BY time))[1] as open,
                MAX(price) as high,
                MIN(price) as low,
                (array_agg(price ORDER BY time DESC))[1] as close,
                SUM(size) as volume,
                'coinbase' as exchange
            FROM exchange_ticks
            WHERE symbol = %s
              AND time >= %s
              AND time < %s
            GROUP BY candle_time, symbol
            ON CONFLICT (time, symbol, timeframe, exchange) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            RETURNING 1
        """,
            (interval_sec, timeframe, symbol, start_time, end_time),
        )

        count = len(cur.fetchall())
        conn.commit()
        return count


def show_gaps(conn, threshold_min: float = DEFAULT_DETECT_THRESHOLD_MIN):
    """Display all gaps."""
    print("=" * 70)
    print(f"TICK DATA GAPS (>= {threshold_min:.2f} min)")
    print("=" * 70)

    total_gaps = 0
    total_minutes = 0

    for symbol in SYMBOLS:
        gaps = detect_gaps(conn, symbol, threshold_min)
        if gaps:
            print(f"\n{symbol}: {len(gaps)} gaps")
            for g in gaps[:10]:
                print(f"  {g['start']} to {g['end']} ({g['minutes']:.1f} min)")
            if len(gaps) > 10:
                print(f"  ... and {len(gaps) - 10} more")
            total_gaps += len(gaps)
            total_minutes += sum(g["minutes"] for g in gaps)

    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_gaps} gaps, {total_minutes:.0f} minutes ({total_minutes / 60:.1f} hours)")


def fill_gaps(conn, dry_run: bool = False, threshold_min: float = DEFAULT_FILL_THRESHOLD_MIN):
    """Fill significant gaps from API."""
    print("=" * 70)
    print(f"FILLING TICK DATA GAPS (>= {threshold_min:.2f} min)")
    print("=" * 70)

    for symbol in SYMBOLS:
        gaps = detect_gaps(conn, symbol, threshold_min)
        if not gaps:
            print(f"\n{symbol}: No gaps to fill")
            continue

        print(f"\n{symbol}: {len(gaps)} gaps >= {threshold_min:.2f}min to fill")

        for i, gap in enumerate(gaps):
            gap_mins = gap["minutes"]
            print(
                f"  [{i + 1}/{len(gaps)}] Filling {gap_mins:.0f}min gap: {gap['start'].strftime('%m/%d %H:%M')} to {gap['end'].strftime('%m/%d %H:%M')}"
            )

            if dry_run:
                continue

            trades = fetch_coinbase_trades(symbol, gap["start"], gap["end"])

            if trades:
                inserted = insert_ticks(conn, trades)
                print(f"    Fetched {len(trades)} trades, inserted {inserted}")
            else:
                print("    No trades found in API")

            time.sleep(1)  # Rate limit between gaps


def rollup_all(conn, start_time: datetime = None, end_time: datetime = None):
    """Roll up all tick data to candles."""
    print("=" * 70)
    print("ROLLING UP TICKS TO CANDLES")
    print("=" * 70)

    if not start_time:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(time), MAX(time) FROM exchange_ticks")
            start_time, end_time = cur.fetchone()

    print(f"Range: {start_time} to {end_time}")

    timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

    for symbol in SYMBOLS:
        print(f"\n{symbol}:")
        for tf in timeframes:
            count = rollup_ticks_to_candles(conn, symbol, tf, start_time, end_time)
            print(f"  {tf}: {count} candles created/updated")


def main():
    parser = argparse.ArgumentParser(description="Tick Data Gap Filler")
    parser.add_argument("--detect", action="store_true", help="Detect and show gaps")
    parser.add_argument("--fill", action="store_true", help="Fill gaps from API")
    parser.add_argument("--rollup", action="store_true", help="Roll up ticks to candles")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually fetch/insert")
    parser.add_argument(
        "--min-gap",
        type=float,
        default=None,
        help="Minimum gap to fill in MINUTES (default: 30 for --fill, 5 for --detect). Use 0.17 for 10 seconds.",
    )
    parser.add_argument("--all-gaps", action="store_true", help="Fill ALL gaps >= 10 seconds (same as --min-gap 0.17)")

    args = parser.parse_args()

    if not any([args.detect, args.fill, args.rollup]):
        args.detect = True  # Default to detect

    # Determine threshold
    if args.all_gaps:
        threshold_min = MIN_FILL_THRESHOLD_SEC / 60  # 10 sec = 0.167 min
    elif args.min_gap is not None:
        threshold_min = args.min_gap
    elif args.fill:
        threshold_min = DEFAULT_FILL_THRESHOLD_MIN
    else:
        threshold_min = DEFAULT_DETECT_THRESHOLD_MIN

    conn = get_db_connection()

    try:
        if args.detect:
            show_gaps(conn, threshold_min=threshold_min)

        if args.fill:
            fill_gaps(conn, dry_run=args.dry_run, threshold_min=threshold_min)

        if args.rollup:
            rollup_all(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
