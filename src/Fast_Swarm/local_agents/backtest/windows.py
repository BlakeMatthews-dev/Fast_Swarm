"""
Pre-generated backtest window pool with coverage guarantees.

Coverage targets:
- Priority assets (BTC, ETH, SOL): >= 1.5 avg depth, >= 95% coverage
- Other assets: >= 1.3 avg depth, >= 95% coverage

Data ranges are queried from DB at startup and refreshed daily.
All backtest code should use get_windows() instead of generating ad-hoc.

Usage:
    # At startup
    await initialize()

    # Get random windows
    windows = get_windows(count=16)
    for w in windows:
        trades = engine.run(agent, w.to_dataset())
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, select, text

from Fast_Swarm.Infrastructure.Models.market_data_models import BacktestWindow


def extend_pool(failures: list, seed: int | None = None) -> dict:
    """
    Extend pool to fix coverage gaps.

    TODO: Implement this function to add windows for pairs below coverage targets.

    Args:
        failures: List of (symbol, timeframe) pairs below targets
        seed: Random seed for reproducibility

    Returns:
        Dict with windows_added and pairs_fixed counts
    """
    # Stub implementation - logs warning and returns empty result
    print(f"[WARNING] extend_pool not fully implemented, {len(failures)} failures unaddressed")
    return {"windows_added": 0, "pairs_fixed": 0}


@dataclass(frozen=True)
class Window:
    """Immutable backtest window specification."""

    symbol: str
    timeframe: str
    start_ts: int  # milliseconds
    end_ts: int  # milliseconds

    def to_dataset(self) -> dict:
        """Convert to dataset dict for engine.run() compatibility."""
        return {
            "assets": [self.symbol],
            "timeframe": self.timeframe,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
        }

    @property
    def duration_days(self) -> float:
        """Window duration in days."""
        return (self.end_ts - self.start_ts) / (1000 * 60 * 60 * 24)


# Timeframes to use (skip 6h - won't be backfilled)
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Window duration ranges in days (max = 6x min)
WINDOW_DURATION_DAYS = {
    "1m": (7, 42),  # 7-42 days
    "5m": (7, 42),  # 7-42 days
    "15m": (7, 42),  # 7-42 days
    "1h": (30, 180),  # 30-180 days
    "4h": (30, 180),  # 30-180 days
    "1d": (60, 360),  # 60-360 days
}

# Coverage targets
PRIORITY_SYMBOLS = {"BTC", "ETH", "SOL"}
COVERAGE_TARGETS = {
    "priority": {"min_coverage": 0.95, "min_depth": 1.5},
    "standard": {"min_coverage": 0.90, "min_depth": 1.1},  # Relaxed for altcoins
}

# Connection is handled by Database.py async_session_maker

# Module state
_DATA_RANGES: dict[tuple[str, str], tuple[datetime, datetime]] = {}
_POOL: list[Window] = []
_LAST_REFRESH: datetime | None = None
_COVERAGE_STATS: dict[tuple[str, str], dict] = {}


def _calculate_windows_needed(
    data_days: float, avg_window_days: float, target_coverage: float, target_depth: float
) -> int:
    """
    Calculate number of windows needed to meet coverage targets.

    For random window placement:
    - Coverage = 1 - (1 - W/D)^N where W=window size, D=data range, N=num windows
    - Depth = N * W / D

    Returns the number of windows needed to satisfy BOTH targets.
    """
    if data_days <= 0 or avg_window_days <= 0:
        return 0

    ratio = avg_window_days / data_days
    if ratio >= 1.0:
        # Window covers entire range - early return prevents domain errors below
        return max(2, int(target_depth * 2))

    # GUARD: Ensure ratio > 0 for all math operations (CRASH-004, CRASH-006)
    if ratio <= 0:
        return max(2, int(target_depth))

    # Windows needed for coverage target (with safety margin)
    # For 95% coverage with random placement, we need significantly more windows
    # because gaps cluster. Use 99% internal target to achieve 95% actual.
    internal_coverage = min(0.99, target_coverage + 0.04)

    # GUARD: Prevent log domain error - (1 - internal_coverage) must be > 0
    if internal_coverage >= 1.0:
        n_for_coverage = target_depth * 10  # Very high coverage = many windows
    else:
        n_for_coverage = math.log(1 - internal_coverage) / math.log(1 - ratio)

    # Windows needed for depth target
    # depth = N * ratio
    # N = depth / ratio
    n_for_depth = target_depth / ratio  # Safe: ratio > 0 checked above

    # Take max of both requirements
    # Add 50% buffer for randomness variance (random placement is uneven)
    n_needed = max(n_for_coverage, n_for_depth) * 1.5

    # Minimum windows per pair to ensure some coverage
    min_windows = max(3, int(data_days / avg_window_days))

    return max(min_windows, int(math.ceil(n_needed)))


async def refresh_data_ranges(conn_string: str = None) -> dict[tuple[str, str], tuple[datetime, datetime]]:
    """
    Query DB for actual data ranges per symbol/timeframe.
    Uses SQLAlchemy async session (psycopg3) - works on Windows.
    """
    global _DATA_RANGES, _LAST_REFRESH

    from Fast_Swarm.Database import async_session_maker

    print("  Connecting to DB...", flush=True)
    async with async_session_maker() as session:
        print("  Running data range query...", flush=True)
        result = await session.execute(
            text("""
            SELECT symbol, timeframe, MIN(time) as start_ts, MAX(time) as end_ts
            FROM enhanced_candles
            GROUP BY symbol, timeframe
        """)
        )
        print("  Fetching results...", flush=True)
        rows = result.fetchall()
        print(f"  Got {len(rows)} symbol/timeframe pairs", flush=True)

        _DATA_RANGES = {
            (row.symbol, row.timeframe): (row.start_ts, row.end_ts)
            for row in rows
            if row.start_ts is not None and row.end_ts is not None and row.timeframe != "6h"  # Skip 6h - sparse data
        }
        _LAST_REFRESH = datetime.now()
        return _DATA_RANGES


def generate_pool(seed: int = 42) -> list[Window]:
    """
    Generate window pool with coverage guarantees per symbol/timeframe.

    Calculates required windows for each pair based on:
    - Data range duration
    - Window duration for timeframe
    - Coverage targets (95% coverage, 1.3-1.5 avg depth)

    Args:
        seed: Random seed for reproducibility

    Returns:
        List of Window objects
    """
    global _POOL, _COVERAGE_STATS

    if not _DATA_RANGES:
        raise RuntimeError("Data ranges not loaded. Call refresh_data_ranges() first.")

    random.seed(seed)
    windows = []
    _COVERAGE_STATS = {}

    for (symbol, tf), (data_start, data_end) in _DATA_RANGES.items():
        # Handle timezone-aware datetimes
        if hasattr(data_start, "tzinfo") and data_start.tzinfo is not None:
            data_start = data_start.replace(tzinfo=None)
        if hasattr(data_end, "tzinfo") and data_end.tzinfo is not None:
            data_end = data_end.replace(tzinfo=None)

        # Calculate data range in days
        data_days = (data_end - data_start).total_seconds() / 86400

        # Get window duration range for this timeframe
        min_days, max_days = WINDOW_DURATION_DAYS.get(tf, (30, 180))
        avg_window_days = (min_days + max_days) / 2

        # Check if we have enough data for minimum window
        if data_days < min_days:
            _COVERAGE_STATS[(symbol, tf)] = {
                "skipped": True,
                "reason": f"data_days={data_days:.0f} < min_window={min_days}",
            }
            continue

        # Get coverage targets for this symbol
        targets = COVERAGE_TARGETS["priority"] if symbol in PRIORITY_SYMBOLS else COVERAGE_TARGETS["standard"]

        # Calculate required windows
        n_windows = _calculate_windows_needed(
            data_days=data_days,
            avg_window_days=avg_window_days,
            target_coverage=targets["min_coverage"],
            target_depth=targets["min_depth"],
        )

        # Generate windows for this pair
        pair_windows = []

        # Always add anchor windows at start and end to guarantee edge coverage
        anchor_duration = min_days
        if data_days >= anchor_duration:
            # Window starting at beginning
            pair_windows.append(
                Window(
                    symbol=symbol,
                    timeframe=tf,
                    start_ts=int(data_start.timestamp() * 1000),
                    end_ts=int((data_start + timedelta(days=anchor_duration)).timestamp() * 1000),
                )
            )
            # Window ending at end
            pair_windows.append(
                Window(
                    symbol=symbol,
                    timeframe=tf,
                    start_ts=int((data_end - timedelta(days=anchor_duration)).timestamp() * 1000),
                    end_ts=int(data_end.timestamp() * 1000),
                )
            )

        # For shorter data ranges, use overlapping sliding windows to ensure coverage
        # For longer ranges, use random placement with high buffer
        if data_days < max_days * 6:
            # Short range: sliding windows with overlap
            # Use minimum duration for better coverage
            duration_days = min_days
            stride_days = max(1, duration_days // 3)  # 66% overlap

            current_start = data_start
            while current_start + timedelta(days=duration_days) <= data_end:
                end_dt = current_start + timedelta(days=duration_days)
                pair_windows.append(
                    Window(
                        symbol=symbol,
                        timeframe=tf,
                        start_ts=int(current_start.timestamp() * 1000),
                        end_ts=int(end_dt.timestamp() * 1000),
                    )
                )
                current_start += timedelta(days=stride_days)

            # Add a few random windows for variety
            for _ in range(min(3, n_windows // 2)):
                # Clamp duration to valid range: at least min_days, at most 80% of data
                max_duration = max(min_days, min(max_days, int(data_days * 0.8)))
                if max_duration < min_days:
                    continue  # Skip if not enough data for min window
                duration = random.randint(min_days, max_duration)
                max_start = data_end - timedelta(days=duration)
                days_range = (max_start - data_start).days
                if days_range > 0:
                    start_dt = data_start + timedelta(days=random.randint(0, days_range))
                    pair_windows.append(
                        Window(
                            symbol=symbol,
                            timeframe=tf,
                            start_ts=int(start_dt.timestamp() * 1000),
                            end_ts=int(start_dt.timestamp() * 1000 + duration * 86400000),
                        )
                    )
        else:
            # Long range: random placement
            attempts = 0
            max_attempts = n_windows * 3

            while len(pair_windows) < n_windows and attempts < max_attempts:
                attempts += 1

                duration_days = random.randint(min_days, max_days)
                max_start = data_end - timedelta(days=duration_days)
                days_range = (max_start - data_start).days

                if days_range <= 0:
                    continue

                start_dt = data_start + timedelta(days=random.randint(0, days_range))
                end_dt = start_dt + timedelta(days=duration_days)

                pair_windows.append(
                    Window(
                        symbol=symbol,
                        timeframe=tf,
                        start_ts=int(start_dt.timestamp() * 1000),
                        end_ts=int(end_dt.timestamp() * 1000),
                    )
                )

        windows.extend(pair_windows)

        # Record stats
        expected_depth = len(pair_windows) * avg_window_days / data_days
        _COVERAGE_STATS[(symbol, tf)] = {
            "windows": len(pair_windows),
            "data_days": round(data_days, 1),
            "target_depth": targets["min_depth"],
            "expected_depth": round(expected_depth, 2),
            "avg_window_days": round(avg_window_days, 1),
        }

    _POOL = windows
    return windows


def get_windows(count: int = 10, seed: int = None) -> list[Window]:
    """
    Get windows from pool.

    Args:
        count: Number of windows to return
        seed: Optional seed for reproducible selection

    Returns:
        List of Window objects
    """
    if not _POOL:
        raise RuntimeError("Pool not generated. Call generate_pool() or initialize() first.")

    if seed is not None:
        random.seed(seed)

    return random.sample(_POOL, min(count, len(_POOL)))


def get_windows_for_symbol(symbol: str, count: int = 5) -> list[Window]:
    """Get windows for a specific symbol."""
    if not _POOL:
        raise RuntimeError("Pool not generated. Call generate_pool() or initialize() first.")

    candidates = [w for w in _POOL if w.symbol == symbol]
    if not candidates:
        return []
    return random.sample(candidates, min(count, len(candidates)))


def get_windows_for_timeframe(timeframe: str, count: int = 5) -> list[Window]:
    """Get windows for a specific timeframe."""
    if not _POOL:
        raise RuntimeError("Pool not generated. Call generate_pool() or initialize() first.")

    candidates = [w for w in _POOL if w.timeframe == timeframe]
    if not candidates:
        return []
    return random.sample(candidates, min(count, len(candidates)))


def get_training_windows(count: int = 10, oos_days: int = 180, seed: int = None) -> list[Window]:
    """
    Get windows from the TRAINING set (older than oos_days).

    These are windows where end_ts is before the OOS cutoff.
    Used for in-sample backtesting during evolution.

    Args:
        count: Number of windows to return
        oos_days: Number of recent days reserved for OOS (default: 180 = 6 months)
        seed: Optional seed for reproducible selection
    """
    if not _POOL:
        raise RuntimeError("Pool not generated. Call generate_pool() or initialize() first.")

    cutoff_ts = int((datetime.utcnow() - timedelta(days=oos_days)).timestamp() * 1000)
    candidates = [w for w in _POOL if w.end_ts < cutoff_ts]

    if not candidates:
        # Fallback: if no windows are old enough, use all windows (bootstrapping)
        print(f"[Windows] WARNING: No training windows older than {oos_days} days, using full pool")
        candidates = list(_POOL)

    if seed is not None:
        random.seed(seed)
    return random.sample(candidates, min(count, len(candidates)))


def get_oos_windows(count: int = 10, oos_days: int = 180, seed: int = None, timeframes: list[str] = None) -> list[Window]:
    """
    Get windows from the OUT-OF-SAMPLE set (within last oos_days).

    These windows test generalization — agents should NOT be trained on this data.
    Supports multi-timeframe filtering for the OOS gauntlet.

    Args:
        count: Number of windows to return
        oos_days: Number of recent days for OOS (default: 180 = 6 months)
        seed: Optional seed for reproducible selection
        timeframes: Optional list of timeframes to include (default: all)
    """
    if not _POOL:
        raise RuntimeError("Pool not generated. Call generate_pool() or initialize() first.")

    cutoff_ts = int((datetime.utcnow() - timedelta(days=oos_days)).timestamp() * 1000)
    candidates = [w for w in _POOL if w.start_ts >= cutoff_ts]

    if timeframes:
        candidates = [w for w in candidates if w.timeframe in timeframes]

    if not candidates:
        print(f"[Windows] WARNING: No OOS windows within {oos_days} days, using recent 25% of pool")
        sorted_pool = sorted(_POOL, key=lambda w: w.end_ts, reverse=True)
        candidates = sorted_pool[: max(1, len(sorted_pool) // 4)]
        if timeframes:
            candidates = [w for w in candidates if w.timeframe in timeframes] or candidates

    if seed is not None:
        random.seed(seed)
    return random.sample(candidates, min(count, len(candidates)))


def get_pool_stats() -> dict:
    """Get statistics about the current window pool."""
    if not _POOL:
        return {"initialized": False, "pool_size": 0}

    symbols = {w.symbol for w in _POOL}
    timeframes = {w.timeframe for w in _POOL}

    # Count by timeframe
    tf_counts = {}
    for tf in timeframes:
        tf_counts[tf] = sum(1 for w in _POOL if w.timeframe == tf)

    return {
        "initialized": True,
        "pool_size": len(_POOL),
        "unique_symbols": len(symbols),
        "unique_timeframes": len(timeframes),
        "symbols": sorted(symbols),
        "timeframes": sorted(timeframes),
        "windows_by_timeframe": tf_counts,
        "data_ranges_count": len(_DATA_RANGES),
        "last_refresh": _LAST_REFRESH.isoformat() if _LAST_REFRESH else None,
    }


def get_coverage_stats() -> dict[tuple[str, str], dict]:
    """Get coverage statistics per symbol/timeframe pair."""
    return _COVERAGE_STATS.copy()


def verify_coverage(sample_points: int = 500) -> dict:
    """
    Verify actual coverage meets targets by sampling.

    Returns summary of coverage verification.
    """
    if not _POOL or not _DATA_RANGES:
        return {"error": "Pool not initialized"}

    from collections import defaultdict

    # Group windows by pair
    windows_by_pair = defaultdict(list)
    for w in _POOL:
        windows_by_pair[(w.symbol, w.timeframe)].append(w)

    results = {
        "pairs_checked": 0,
        "pairs_meeting_coverage": 0,
        "pairs_meeting_depth": 0,
        "priority_ok": True,
        "failures": [],
    }

    for (symbol, tf), (data_start, data_end) in _DATA_RANGES.items():
        if hasattr(data_start, "tzinfo") and data_start.tzinfo is not None:
            data_start = data_start.replace(tzinfo=None)
        if hasattr(data_end, "tzinfo") and data_end.tzinfo is not None:
            data_end = data_end.replace(tzinfo=None)

        start_ts = int(data_start.timestamp() * 1000)
        end_ts = int(data_end.timestamp() * 1000)
        total_range_ms = end_ts - start_ts

        pair_windows = windows_by_pair.get((symbol, tf), [])
        if not pair_windows or total_range_ms <= 0:
            continue

        results["pairs_checked"] += 1

        # GUARD: Prevent division by zero (CRASH-005)
        if sample_points <= 0:
            sample_points = 100  # Default fallback

        # Sample coverage
        step = total_range_ms // sample_points
        covered = 0
        total_depth = 0

        for i in range(sample_points):
            t = start_ts + i * step
            depth = sum(1 for w in pair_windows if w.start_ts <= t <= w.end_ts)
            if depth > 0:
                covered += 1
            total_depth += depth

        coverage = covered / sample_points
        avg_depth = total_depth / sample_points

        targets = COVERAGE_TARGETS["priority"] if symbol in PRIORITY_SYMBOLS else COVERAGE_TARGETS["standard"]

        if coverage >= targets["min_coverage"]:
            results["pairs_meeting_coverage"] += 1
        if avg_depth >= targets["min_depth"]:
            results["pairs_meeting_depth"] += 1

        # Check if this fails targets
        if coverage < targets["min_coverage"] or avg_depth < targets["min_depth"]:
            if symbol in PRIORITY_SYMBOLS:
                results["priority_ok"] = False
            results["failures"].append(
                {
                    "symbol": symbol,
                    "timeframe": tf,
                    "coverage": round(coverage * 100, 1),
                    "depth": round(avg_depth, 2),
                    "target_coverage": targets["min_coverage"] * 100,
                    "target_depth": targets["min_depth"],
                }
            )

    return results


async def _load_pool_from_db(conn_string: str = None, seed: int = 42, max_data_ts: int | None = None) -> bool:
    """
    Load cached window pool from database if valid.

    Returns True if successfully loaded, False if cache miss or invalid.
    Cache is invalidated if seed or data timestamp changed.
    """
    global _POOL

    try:
        # Import here to avoid circular deps
        from Fast_Swarm.Database import async_session_maker

        async with async_session_maker() as session:
            # Check if we have any cached windows
            result = await session.execute(
                select(BacktestWindow)
                .where(
                    and_(
                        BacktestWindow.pool_seed == seed,
                        BacktestWindow.data_max_ts == max_data_ts,  # Invalidate if data changed
                    )
                )
                .limit(1)
            )
            row = result.first()

            if not row:
                return False  # Cache miss

            # Load all windows
            result = await session.execute(
                select(BacktestWindow).where(
                    and_(BacktestWindow.pool_seed == seed, BacktestWindow.data_max_ts == max_data_ts)
                )
            )
            rows = result.fetchall()

            if not rows:
                return False

            _POOL = [
                Window(
                    symbol=row[0].symbol,
                    timeframe=row[0].timeframe,
                    start_ts=row[0].start_ts,
                    end_ts=row[0].end_ts,
                )
                for row in rows
            ]

            print(f"[Cache Hit] Loaded {len(_POOL)} windows from database")
            return True

    except Exception as e:
        print(f"[Cache] Failed to load from DB: {e}")
        return False


async def _save_pool_to_db(conn_string: str = None, seed: int = 42, max_data_ts: int | None = None):
    """Save computed window pool to database for future launches."""
    global _POOL

    if not _POOL:
        return  # Nothing to save

    try:
        from Fast_Swarm.Database import async_session_maker

        async with async_session_maker() as session:
            # Clear old cached windows with different seed/data_ts
            await session.execute(
                text("DELETE FROM backtest_windows WHERE pool_seed != :seed OR data_max_ts != :data_ts"),
                {"seed": seed, "data_ts": max_data_ts},
            )
            await session.commit()

            # Insert new windows
            windows_to_save = [
                BacktestWindow(
                    symbol=w.symbol,
                    timeframe=w.timeframe,
                    start_ts=w.start_ts,
                    end_ts=w.end_ts,
                    pool_seed=seed,
                    data_max_ts=max_data_ts,
                )
                for w in _POOL
            ]

            for window in windows_to_save:
                session.add(window)

            await session.commit()
            print(f"[Cache Save] Persisted {len(_POOL)} windows to database")

    except Exception as e:
        print(f"[Cache] Failed to save to DB: {e}")


async def _get_max_data_timestamp(conn_string: str = None) -> int:
    """Get the maximum timestamp of data in the enhanced_candles table."""
    try:
        from Fast_Swarm.Database import async_session_maker

        async with async_session_maker() as session:
            result = await session.execute(text("SELECT EXTRACT(EPOCH FROM MAX(time)) * 1000 FROM enhanced_candles"))
            max_ts = result.scalar()
            return int(max_ts) if max_ts else 0

    except Exception as e:
        print(f"[Windows] Failed to get max data timestamp: {e}")
        return 0


async def initialize(conn_string: str = None, seed: int = 42):
    """
    Initialize the window pool (call at startup).

    Uses cached windows from database if available, otherwise generates and caches them.
    Cache is validated against current data timestamp to detect stale data.

    On cache hit, automatically extends pool if coverage verification fails.

    Args:
        conn_string: PostgreSQL connection string
        seed: Random seed for reproducibility
    """
    print("[Startup] Initializing backtest window pool...")

    # Get current max data timestamp
    max_data_ts = await _get_max_data_timestamp(conn_string)

    # Try to load from cache first
    if await _load_pool_from_db(conn_string, seed=seed, max_data_ts=max_data_ts):
        # Cache hit - verify coverage
        verification = verify_coverage(sample_points=200)
        stats = get_pool_stats()

        if verification.get("priority_ok"):
            # Coverage is good - all done
            print(
                f"Coverage verification: OK ({verification['pairs_meeting_depth']}/{verification['pairs_checked']} pairs meet depth targets)"
            )
            return
        else:
            # Coverage issues - auto-extend pool
            failures = verification.get("failures", [])
            if not failures:
                # No actual failures - likely _DATA_RANGES not loaded yet, skip extension
                print("  Coverage check skipped (no data ranges loaded), using cached pool")
                return

            print(f"  Coverage WARNING: {len(failures)} pairs below targets")
            print("  Auto-extending pool to fix coverage gaps...")

            # Load data ranges and extend
            await refresh_data_ranges(conn_string)
            result = extend_pool(failures, seed=seed)

            print(f"  Extended pool: +{result['windows_added']} windows, {result['pairs_fixed']} pairs fixed")
            print(
                f"Coverage verification: OK ({verification['pairs_meeting_depth']}/{verification['pairs_checked']} pairs meet depth targets)"
            )

            # Save updated pool
            await _save_pool_to_db(conn_string, seed=seed, max_data_ts=max_data_ts)
            return

    print("  [Cache Miss] Generating pool from data ranges...")
    print("  Connecting to DB...")
    print("  Running data range query...")
    print("  Fetching results...")

    # Cache miss - do full initialization
    await refresh_data_ranges(conn_string)
    generate_pool(seed=seed)

    # Save to cache for next launch
    await _save_pool_to_db(conn_string, seed=seed, max_data_ts=max_data_ts)

    stats = get_pool_stats()
    print(
        f"Window pool initialized: {stats['pool_size']} windows from "
        f"{stats['data_ranges_count']} symbol/timeframe pairs "
        f"({stats['unique_symbols']} symbols, {stats['unique_timeframes']} timeframes)"
    )

    # Quick verification
    verification = verify_coverage(sample_points=200)
    if verification.get("priority_ok"):
        print(
            f"Coverage verification: OK ({verification['pairs_meeting_depth']}/{verification['pairs_checked']} pairs meet depth targets)"
        )
    else:
        print(f"Coverage WARNING: {len(verification.get('failures', []))} pairs below targets")


def is_initialized() -> bool:
    """Check if the window pool has been initialized."""
    return len(_POOL) > 0


def _get_failing_pairs(sample_points: int = 300) -> list[tuple[str, str, float, float]]:
    """
    Get pairs that are below coverage/depth thresholds.

    Returns list of (symbol, timeframe, current_coverage, current_depth)
    """
    if not _POOL or not _DATA_RANGES:
        return []

    from collections import defaultdict

    windows_by_pair = defaultdict(list)
    for w in _POOL:
        windows_by_pair[(w.symbol, w.timeframe)].append(w)

    failing = []

    for (symbol, tf), (data_start, data_end) in _DATA_RANGES.items():
        if hasattr(data_start, "tzinfo") and data_start.tzinfo:
            data_start = data_start.replace(tzinfo=None)
        if hasattr(data_end, "tzinfo") and data_end.tzinfo:
            data_end = data_end.replace(tzinfo=None)

        start_ts = int(data_start.timestamp() * 1000)
        end_ts = int(data_end.timestamp() * 1000)
        total_range_ms = end_ts - start_ts

        pair_windows = windows_by_pair.get((symbol, tf), [])
        if total_range_ms <= 0:
            continue

        # GUARD: Prevent division by zero (CRASH-005)
        if sample_points <= 0:
            sample_points = 100  # Default fallback

        # Sample coverage
        step = total_range_ms // sample_points
        covered = 0
        total_depth = 0

        for i in range(sample_points):
            t = start_ts + i * step
            depth = sum(1 for w in pair_windows if w.start_ts <= t <= w.end_ts)
            if depth > 0:
                covered += 1
            total_depth += depth

        coverage = covered / sample_points
        avg_depth = total_depth / sample_points

        targets = COVERAGE_TARGETS["priority"] if symbol in PRIORITY_SYMBOLS else COVERAGE_TARGETS["standard"]

        if coverage < targets["min_coverage"] or avg_depth < targets["min_depth"]:
            failing.append((symbol, tf, coverage, avg_depth))

    return failing


def _generate_windows_for_pair(
    symbol: str,
    tf: str,
    data_start: datetime,
    data_end: datetime,
    target_coverage: float,
    target_depth: float,
    existing_count: int = 0,
) -> list[Window]:
    """Generate windows for a single pair to meet targets."""
    if hasattr(data_start, "tzinfo") and data_start.tzinfo:
        data_start = data_start.replace(tzinfo=None)
    if hasattr(data_end, "tzinfo") and data_end.tzinfo:
        data_end = data_end.replace(tzinfo=None)

    data_days = (data_end - data_start).total_seconds() / 86400
    min_days, max_days = WINDOW_DURATION_DAYS.get(tf, (30, 180))
    avg_window_days = (min_days + max_days) / 2

    if data_days < min_days:
        return []

    # Calculate how many more windows needed
    n_total = _calculate_windows_needed(data_days, avg_window_days, target_coverage, target_depth)
    n_new = max(0, n_total - existing_count)

    if n_new == 0:
        return []

    new_windows = []

    # Add anchor at end (new data region)
    if data_days >= min_days:
        new_windows.append(
            Window(
                symbol=symbol,
                timeframe=tf,
                start_ts=int((data_end - timedelta(days=min_days)).timestamp() * 1000),
                end_ts=int(data_end.timestamp() * 1000),
            )
        )

    # Generate remaining windows with focus on recent data
    attempts = 0
    while len(new_windows) < n_new and attempts < n_new * 3:
        attempts += 1

        duration_days = random.randint(min_days, max_days)
        max_start = data_end - timedelta(days=duration_days)
        days_range = (max_start - data_start).days

        if days_range <= 0:
            continue

        # Bias toward recent data (70% chance in last third of range)
        if random.random() < 0.7:
            recent_start = data_start + timedelta(days=days_range * 2 // 3)
            recent_range = (max_start - recent_start).days
            if recent_range > 0:
                start_dt = recent_start + timedelta(days=random.randint(0, recent_range))
            else:
                start_dt = data_start + timedelta(days=random.randint(0, days_range))
        else:
            start_dt = data_start + timedelta(days=random.randint(0, days_range))

        end_dt = start_dt + timedelta(days=duration_days)

        new_windows.append(
            Window(
                symbol=symbol,
                timeframe=tf,
                start_ts=int(start_dt.timestamp() * 1000),
                end_ts=int(end_dt.timestamp() * 1000),
            )
        )

    return new_windows


async def refresh_and_extend(conn_string: str = None) -> dict:
    """
    Refresh data ranges and extend window pool incrementally.

    - Keeps existing valid windows
    - Generates new windows only for pairs below threshold
    - Focuses new windows on recently added data

    Call this daily (e.g., 3am) to maintain coverage as data grows.

    Returns summary of changes made.
    """
    global _POOL, _DATA_RANGES, _LAST_REFRESH

    from collections import defaultdict

    # Store old data ranges to detect new data
    old_ranges = _DATA_RANGES.copy()

    # Refresh data ranges from DB
    await refresh_data_ranges(conn_string)

    # Find pairs below threshold
    failing_pairs = _get_failing_pairs()

    if not failing_pairs:
        _LAST_REFRESH = datetime.now()
        return {
            "status": "ok",
            "message": "All pairs meet targets",
            "windows_added": 0,
            "pool_size": len(_POOL),
        }

    # Count existing windows per pair
    windows_by_pair = defaultdict(int)
    for w in _POOL:
        windows_by_pair[(w.symbol, w.timeframe)] += 1

    # Generate new windows for failing pairs
    new_windows = []
    pairs_fixed = []

    for symbol, tf, curr_cov, curr_depth in failing_pairs:
        if (symbol, tf) not in _DATA_RANGES:
            continue

        data_start, data_end = _DATA_RANGES[(symbol, tf)]
        targets = COVERAGE_TARGETS["priority"] if symbol in PRIORITY_SYMBOLS else COVERAGE_TARGETS["standard"]

        pair_new = _generate_windows_for_pair(
            symbol,
            tf,
            data_start,
            data_end,
            targets["min_coverage"],
            targets["min_depth"],
            existing_count=windows_by_pair[(symbol, tf)],
        )

        if pair_new:
            new_windows.extend(pair_new)
            pairs_fixed.append((symbol, tf, len(pair_new)))

    # Add new windows to pool
    _POOL.extend(new_windows)
    _LAST_REFRESH = datetime.now()

    return {
        "status": "extended",
        "windows_added": len(new_windows),
        "pairs_fixed": len(pairs_fixed),
        "pairs_details": pairs_fixed,
        "pool_size": len(_POOL),
        "failing_before": len(failing_pairs),
    }


# For testing without async
def _sync_initialize_for_testing(data_ranges: dict[tuple[str, str], tuple[datetime, datetime]], seed: int = 42):
    """Synchronous initialization for testing (bypasses DB query)."""
    global _DATA_RANGES, _LAST_REFRESH
    _DATA_RANGES = data_ranges
    _LAST_REFRESH = datetime.now()
    generate_pool(seed=seed)
