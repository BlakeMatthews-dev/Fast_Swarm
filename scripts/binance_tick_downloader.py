"""
Binance Historical Tick Data Downloader

Downloads historical trade data from Binance Data Vision (data.binance.vision).
This is FREE historical tick data going back to 2017!

Data format: trade_id, price, qty, quoteQty, time, isBuyerMaker, isBestMatch

Usage:
    python scripts/binance_tick_downloader.py --list                    # Show available months
    python scripts/binance_tick_downloader.py --download 2024-12        # Download Dec 2024
    python scripts/binance_tick_downloader.py --download 2024-01:2024-12  # Download range
    python scripts/binance_tick_downloader.py --download-recent 7       # Last 7 days (daily files)
    python scripts/binance_tick_downloader.py --import-dir ./downloads  # Import downloaded ZIPs
"""

import argparse
import csv
import io
import os
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import requests

# Binance Data Vision base URL
BASE_URL = "https://data.binance.vision/data/spot"

# Symbols to download (Binance format -> our format)
SYMBOLS = {
    # Major USDT pairs (original)
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "XRPUSDT": "XRP-USD",
    "DOGEUSDT": "DOGE-USD",
    # Cross pairs (for correlation/arb analysis)
    "ETHBTC": "ETH-BTC",
    "SOLBTC": "SOL-BTC",
    "SOLETH": "SOL-ETH",
    # Additional top 10 tokens (2025)
    "LINKUSDT": "LINK-USD",
    "BNBUSDT": "BNB-USD",
    "ADAUSDT": "ADA-USD",
    "AVAXUSDT": "AVAX-USD",
    "DOTUSDT": "DOT-USD",
    "TRXUSDT": "TRX-USD",
    "TONUSDT": "TON-USD",
}

# Download directory
DOWNLOAD_DIR = Path(__file__).parent.parent / "data" / "binance_trades"

# Priority months: last 6 months + all canonical period coverage
# These are the ONLY months needed for regime testing
PRIORITY_MONTHS = {
    # Last 6 months (most recent)
    "2025": ["07", "08", "09", "10", "11", "12"],
    # 2024: ETF rally (Q1) - H2 already in DB from earlier import
    "2024": ["01", "02", "03"],
    # 2023: Recovery (Q1) + sideways (Q2-Q3)
    "2023": ["01", "02", "03", "04", "05", "06", "07", "08", "09"],
    # 2022: Luna crash (May) + bear market + FTX (Nov)
    "2022": ["05", "06", "07", "08", "09", "10", "11"],
    # 2021: Bull run (Q1) + May crash + Nov blowoff
    "2021": ["01", "02", "03", "04", "05", "11"],
    # 2020: COVID crash (Mar) + recovery (Apr-Jul) + Q4 bull
    "2020": ["03", "04", "05", "06", "07", "10", "11", "12"],
}


def get_db_connection():
    """Get database connection."""
    return psycopg.connect(
        host="localhost",
        port="5432",
        dbname="coinswarm",
        user="coinswarm",
        password="coinswarm_dev_2024",
    )


def list_available_months(symbol: str = "BTCUSDT") -> list[str]:
    """Check what months are available for a symbol."""
    # Try to get the checksum file which lists all available files
    url = f"{BASE_URL}/monthly/trades/{symbol}/"

    print(f"Checking available data for {symbol}...")
    print(f"URL: {url}")
    print()
    print("Available months (estimated based on Binance data availability):")
    print("-" * 40)

    # Binance has data from ~2017 for BTC
    start_year = 2019 if symbol in ["SOLUSDT"] else 2017
    current = datetime.now()

    months = []
    for year in range(start_year, current.year + 1):
        end_month = current.month if year == current.year else 12
        for month in range(1, end_month + 1):
            months.append(f"{year}-{month:02d}")

    for m in months[-24:]:  # Show last 24 months
        print(f"  {m}")

    print(f"\n  ... and {len(months) - 24} earlier months")
    print(f"\nTotal: {len(months)} months available")

    return months


def download_monthly_file(symbol: str, year: int, month: int, output_dir: Path) -> Path | None:
    """Download a monthly trades ZIP file."""
    filename = f"{symbol}-trades-{year}-{month:02d}.zip"
    url = f"{BASE_URL}/monthly/trades/{symbol}/{filename}"
    output_path = output_dir / filename

    if output_path.exists():
        print(f"  Already downloaded: {filename}")
        return output_path

    print(f"  Downloading: {filename}...", end=" ", flush=True)

    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)

        size_mb = downloaded / (1024 * 1024)
        print(f"OK ({size_mb:.1f} MB)")
        return output_path

    except requests.RequestException as e:
        print(f"FAILED: {e}")
        return None


def download_daily_file(symbol: str, date: datetime, output_dir: Path) -> Path | None:
    """Download a daily trades ZIP file."""
    date_str = date.strftime("%Y-%m-%d")
    filename = f"{symbol}-trades-{date_str}.zip"
    url = f"{BASE_URL}/daily/trades/{symbol}/{filename}"
    output_path = output_dir / filename

    if output_path.exists():
        print(f"  Already downloaded: {filename}")
        return output_path

    print(f"  Downloading: {filename}...", end=" ", flush=True)

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"OK ({size_mb:.1f} MB)")
        return output_path

    except requests.RequestException as e:
        print(f"FAILED: {e}")
        return None


def stream_import_trades(conn, zip_path: Path, our_symbol: str, chunk_size: int = 100000, gentle: bool = False) -> int:
    """
    Stream trades from ZIP directly to database without loading all into memory.

    This avoids MemoryError on large files (1GB+ with 100M+ trades).

    Args:
        conn: Database connection
        zip_path: Path to ZIP file
        our_symbol: Our symbol format (e.g. 'BTC-USD')
        chunk_size: Rows per commit (default 100K, gentle mode uses 10K)
        gentle: If True, use smaller chunks and add delays between commits
    """
    # Gentle mode: smaller chunks to avoid overwhelming DB
    actual_chunk_size = 10000 if gentle else chunk_size
    inserted = 0
    chunk = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith(".csv"):
                with zf.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, "utf-8"))

                    for row in reader:
                        if len(row) < 6:
                            continue
                        try:
                            trade_id, price, qty, quote_qty, ts_ms, is_buyer_maker = row[:6]

                            # Skip header row
                            if trade_id == "id":
                                continue

                            # Handle both milliseconds (13 digits) and microseconds (16 digits)
                            ts_int = int(ts_ms)
                            if ts_int > 9999999999999:  # More than 13 digits = microseconds
                                ts_int = ts_int // 1000  # Convert to milliseconds

                            # Windows datetime.fromtimestamp() has range limits
                            # Use a safer approach: construct from Unix epoch
                            try:
                                trade_time = datetime.fromtimestamp(ts_int / 1000, tz=UTC)
                            except (OSError, OverflowError, ValueError):
                                # Fallback: manual conversion from epoch
                                epoch = datetime(1970, 1, 1, tzinfo=UTC)
                                trade_time = epoch + timedelta(milliseconds=ts_int)
                            side = "sell" if is_buyer_maker.lower() == "true" else "buy"

                            chunk.append(
                                (
                                    trade_time,
                                    our_symbol,
                                    float(price),
                                    float(qty),
                                    side,
                                    trade_id,
                                    "binance",
                                )
                            )

                            # Insert chunk when full
                            if len(chunk) >= actual_chunk_size:
                                with conn.cursor() as cur:
                                    with cur.copy(
                                        "COPY exchange_ticks (time, symbol, price, size, side, trade_id, exchange) FROM STDIN"
                                    ) as copy:
                                        for t in chunk:
                                            copy.write_row(t)
                                conn.commit()
                                inserted += len(chunk)
                                chunk = []

                                # Gentle mode: let DB breathe between chunks
                                if gentle:
                                    time.sleep(0.1)

                        except (ValueError, IndexError):
                            continue

    # Insert remaining trades
    if chunk:
        with conn.cursor() as cur:
            with cur.copy(
                "COPY exchange_ticks (time, symbol, price, size, side, trade_id, exchange) FROM STDIN"
            ) as copy:
                for t in chunk:
                    copy.write_row(t)
        conn.commit()
        inserted += len(chunk)

    return inserted


def is_priority_file(zip_path: Path) -> bool:
    """Check if this ZIP file is in our priority months list."""
    filename = zip_path.name
    # Parse: BTCUSDT-trades-2024-07.zip
    parts = filename.replace(".zip", "").split("-")
    if len(parts) < 4:
        return False

    year = parts[2]
    month = parts[3]

    if year in PRIORITY_MONTHS:
        return month in PRIORITY_MONTHS[year]
    return False


def already_imported(conn, zip_path: Path, min_rows: int = 1_000_000) -> bool:
    """
    Check if this month's data is already substantially imported.

    Returns True if more than min_rows exist for this symbol/month.
    """
    filename = zip_path.name
    parts = filename.replace(".zip", "").split("-")
    if len(parts) < 4:
        return False

    binance_symbol = parts[0]
    year = parts[2]
    month = parts[3]
    our_symbol = SYMBOLS.get(binance_symbol)

    if not our_symbol:
        return False

    # Calculate month boundaries
    start_date = datetime(int(year), int(month), 1, tzinfo=UTC)
    if int(month) == 12:
        end_date = datetime(int(year) + 1, 1, 1, tzinfo=UTC)
    else:
        end_date = datetime(int(year), int(month) + 1, 1, tzinfo=UTC)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM exchange_ticks
            WHERE symbol = %s AND time >= %s AND time < %s
        """,
            (our_symbol, start_date, end_date),
        )
        count = cur.fetchone()[0]

    return count >= min_rows


def parse_trades_csv(zip_path: Path, our_symbol: str) -> list[dict]:
    """Parse trades from a Binance ZIP file. DEPRECATED - use stream_import_trades instead."""
    trades = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith(".csv"):
                with zf.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, "utf-8"))

                    for row in reader:
                        if len(row) < 6:
                            continue
                        try:
                            trade_id, price, qty, quote_qty, ts_ms, is_buyer_maker = row[:6]

                            if trade_id == "id":
                                continue

                            # Handle both milliseconds (13 digits) and microseconds (16 digits)
                            ts_int = int(ts_ms)
                            if ts_int > 9999999999999:  # More than 13 digits = microseconds
                                ts_int = ts_int // 1000  # Convert to milliseconds
                            trade_time = datetime.fromtimestamp(ts_int / 1000, tz=UTC)
                            side = "sell" if is_buyer_maker.lower() == "true" else "buy"

                            trades.append(
                                {
                                    "time": trade_time,
                                    "symbol": our_symbol,
                                    "price": float(price),
                                    "size": float(qty),
                                    "side": side,
                                    "trade_id": trade_id,
                                    "exchange": "binance",
                                }
                            )
                        except (ValueError, IndexError):
                            continue

    return trades


def import_trades_to_db(conn, trades: list[dict], batch_size: int = 10000) -> int:
    """Import trades into database. DEPRECATED - use stream_import_trades instead."""
    if not trades:
        return 0

    inserted = 0

    with conn.cursor() as cur:
        for i in range(0, len(trades), batch_size):
            batch = trades[i : i + batch_size]

            with cur.copy(
                "COPY exchange_ticks (time, symbol, price, size, side, trade_id, exchange) FROM STDIN"
            ) as copy:
                for t in batch:
                    copy.write_row(
                        (
                            t["time"],
                            t["symbol"],
                            t["price"],
                            t["size"],
                            t["side"],
                            t["trade_id"],
                            t["exchange"],
                        )
                    )

            inserted += len(batch)

        conn.commit()

    return inserted


def download_month_range(start_month: str, end_month: str):
    """Download a range of months."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    start_year, start_m = map(int, start_month.split("-"))
    end_year, end_m = map(int, end_month.split("-"))

    print(f"Downloading {start_month} to {end_month}")
    print(f"Output directory: {DOWNLOAD_DIR}")
    print("=" * 60)

    for binance_symbol, our_symbol in SYMBOLS.items():
        print(f"\n{binance_symbol} -> {our_symbol}:")

        year, month = start_year, start_m
        while (year, month) <= (end_year, end_m):
            download_monthly_file(binance_symbol, year, month, DOWNLOAD_DIR)

            month += 1
            if month > 12:
                month = 1
                year += 1

            time.sleep(0.5)  # Be nice to Binance


def download_recent_days(days: int):
    """Download recent daily files."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading last {days} days of daily trade data")
    print(f"Output directory: {DOWNLOAD_DIR}")
    print("=" * 60)

    today = datetime.now()

    for binance_symbol, our_symbol in SYMBOLS.items():
        print(f"\n{binance_symbol} -> {our_symbol}:")

        for i in range(1, days + 1):  # Start from yesterday (today might not be ready)
            date = today - timedelta(days=i)
            download_daily_file(binance_symbol, date, DOWNLOAD_DIR)
            time.sleep(0.3)


def import_directory(dir_path: Path, priority_only: bool = False, gentle: bool = False, dry_run: bool = False):
    """
    Import ZIP files from a directory into the database using streaming.

    Args:
        dir_path: Directory containing ZIP files
        priority_only: If True, only import priority months (last 6 + canonical periods)
        gentle: If True, use smaller chunks and delays between commits
        dry_run: If True, just show what would be imported without doing it
    """
    conn = get_db_connection()

    zip_files = sorted(dir_path.glob("*.zip"))
    total_files = len(zip_files)

    # Filter to priority files if requested
    if priority_only:
        zip_files = [f for f in zip_files if is_priority_file(f)]
        print(f"Priority mode: {len(zip_files)}/{total_files} files match priority months")
    else:
        print(f"Found {len(zip_files)} ZIP files")

    # Sort by year-month descending (newest first) for priority import
    def sort_key(f):
        parts = f.name.replace(".zip", "").split("-")
        if len(parts) >= 4:
            return (parts[2], parts[3])  # year, month
        return ("0000", "00")

    zip_files = sorted(zip_files, key=sort_key, reverse=True)

    print("=" * 60)
    if gentle:
        print("GENTLE MODE: 10K chunks, 0.1s delay between chunks, 5s between files")
    if dry_run:
        print("DRY RUN: Not actually importing")
    print()

    total_imported = 0
    skipped = 0
    imported_files = 0

    for i, zip_path in enumerate(zip_files):
        # Determine symbol from filename
        filename = zip_path.name
        binance_symbol = filename.split("-")[0]
        our_symbol = SYMBOLS.get(binance_symbol)

        if not our_symbol:
            print(f"Skipping unknown symbol: {filename}")
            continue

        # Check if already imported
        if already_imported(conn, zip_path):
            print(f"[{i + 1}/{len(zip_files)}] {filename} - SKIP (already imported)")
            skipped += 1
            continue

        # Get file size for progress indication
        file_size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"\n[{i + 1}/{len(zip_files)}] {filename} ({file_size_mb:.0f} MB)")

        if dry_run:
            print("  Would import (dry run)")
            continue

        # Stream import
        mode_str = "gentle" if gentle else "fast"
        print(f"  Streaming import ({mode_str})...", end=" ", flush=True)
        try:
            imported = stream_import_trades(conn, zip_path, our_symbol, gentle=gentle)
            print(f"{imported:,} rows inserted")
            total_imported += imported
            imported_files += 1

            # Gentle mode: delay between files
            if gentle:
                print("  Waiting 5s for DB to breathe...")
                time.sleep(5)

        except Exception as e:
            print(f"ERROR: {e}")
            conn.rollback()

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"FILES: {imported_files} imported, {skipped} skipped (already in DB)")
    print(f"TOTAL IMPORTED: {total_imported:,} trades")


def main():
    parser = argparse.ArgumentParser(
        description="Binance Historical Tick Data Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download data
  python scripts/binance_tick_downloader.py --download 2024-06:2024-12

  # Import with priority + gentle mode (recommended)
  python scripts/binance_tick_downloader.py --import-dir data/binance_trades --priority --gentle

  # Dry run to see what would be imported
  python scripts/binance_tick_downloader.py --import-dir data/binance_trades --priority --dry-run
""",
    )
    parser.add_argument("--list", action="store_true", help="List available months")
    parser.add_argument("--download", type=str, help="Download month(s): 2024-12 or 2024-01:2024-12")
    parser.add_argument("--download-recent", type=int, metavar="DAYS", help="Download last N days")
    parser.add_argument("--import-dir", type=str, help="Import ZIPs from directory")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Symbol for --list")

    # Import mode flags
    parser.add_argument(
        "--priority", action="store_true", help="Only import priority months (last 6 + canonical periods)"
    )
    parser.add_argument("--gentle", action="store_true", help="Gentle mode: 10K chunks with delays (won't stall DB)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without actually importing")

    args = parser.parse_args()

    if args.list:
        list_available_months(args.symbol)

    elif args.download:
        if ":" in args.download:
            start, end = args.download.split(":")
            download_month_range(start, end)
        else:
            download_month_range(args.download, args.download)

    elif args.download_recent:
        download_recent_days(args.download_recent)

    elif args.import_dir:
        import_directory(
            Path(args.import_dir),
            priority_only=args.priority,
            gentle=args.gentle,
            dry_run=args.dry_run,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
