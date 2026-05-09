"""
Indicator Enrichment Service - Precomputes derived indicators for enhanced_candles.

This service computes derived/computed indicators (like maCross, volatilityRegime, etc.)
and stores them directly in the enhanced_candles table. This eliminates the need to
compute these indicators on-the-fly during backtesting, providing massive performance gains.

The indicators computed here match what patterns expect from COMPUTED_INDICATORS in pattern_matcher.py.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Database import async_session_maker

logger = logging.getLogger("indicator_enrichment")


# Batch size for updates (avoid memory issues on 5M+ rows)
BATCH_SIZE = 10000

# Symbols to skip during enrichment (heavy query targets - enrich these during off-hours)
DEFAULT_SKIP_SYMBOLS = set()  # Don't skip any symbols — enrichment is required for all


async def check_db_activity(session) -> tuple[bool, int]:
    """
    Check if database has heavy activity that we should yield to.

    Returns:
        (is_busy, active_queries): Whether DB is busy and how many active queries
    """
    try:
        # Check for active queries (excluding our own and idle connections)
        result = await session.execute(text("""
            SELECT COUNT(*) FROM pg_stat_activity
            WHERE state = 'active'
            AND query NOT LIKE '%pg_stat_activity%'
            AND query NOT LIKE '%derived_computed_at%'
            AND datname = current_database()
        """))
        active_count = result.scalar() or 0

        # If more than 2 active queries, consider DB busy
        return active_count > 2, active_count
    except Exception:
        return False, 0


async def wait_for_db_idle(session, max_wait: int = 300, check_interval: int = 10) -> bool:
    """
    Wait for database to become less busy before proceeding.

    Args:
        session: Database session
        max_wait: Maximum seconds to wait
        check_interval: Seconds between checks

    Returns:
        True if DB became idle, False if timed out
    """
    import time
    start = time.time()

    while time.time() - start < max_wait:
        is_busy, active = await check_db_activity(session)
        if not is_busy:
            return True
        print(f"    [Yield] DB busy ({active} active queries), waiting {check_interval}s...", flush=True)
        await asyncio.sleep(check_interval)

    return False


async def compute_derived_indicators_batch(
    session: AsyncSession,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
) -> int:
    """
    Compute derived indicators for candles that don't have them yet.

    This updates the enhanced_candles table in batches, computing:
    - MA cross signals (ma_cross_20_50, golden_cross, death_cross)
    - MACD cross signal
    - Price vs MA percentages
    - RSI/Stoch conditions
    - Trend/volatility regimes
    - Session indicators
    - Volume conditions

    Args:
        session: Database session
        symbol: Optional symbol filter (e.g., 'BTC')
        timeframe: Optional timeframe filter (e.g., '1h')
        limit: Optional limit on rows to process

    Returns:
        Number of rows updated
    """
    # Build WHERE clause for filtering
    where_clauses = ["derived_computed_at IS NULL"]
    if symbol:
        where_clauses.append(f"symbol = '{symbol}'")
    if timeframe:
        where_clauses.append(f"timeframe = '{timeframe}'")

    where_sql = " AND ".join(where_clauses)
    limit_sql = f"LIMIT {limit}" if limit else ""

    # SQL to compute all derived indicators in one pass
    # This is MUCH faster than Python loops - let PostgreSQL do the work
    update_sql = text(f"""
        UPDATE enhanced_candles ec
        SET
            -- MA Cross signals (1 = bullish, -1 = bearish, 0 = neutral)
            ma_cross_20_50 = CASE
                WHEN ema_21 IS NOT NULL AND sma_50 IS NOT NULL THEN
                    CASE WHEN ema_21 > sma_50 THEN 1 WHEN ema_21 < sma_50 THEN -1 ELSE 0 END
                ELSE NULL
            END,

            golden_cross = CASE
                WHEN sma_50 IS NOT NULL AND sma_200 IS NOT NULL THEN
                    CASE WHEN sma_50 > sma_200 THEN 1 ELSE 0 END
                ELSE NULL
            END,

            death_cross = CASE
                WHEN sma_50 IS NOT NULL AND sma_200 IS NOT NULL THEN
                    CASE WHEN sma_50 < sma_200 THEN 1 ELSE 0 END
                ELSE NULL
            END,

            -- MACD Cross
            macd_cross = CASE
                WHEN macd_line IS NOT NULL AND macd_signal IS NOT NULL THEN
                    CASE WHEN macd_line > macd_signal THEN 1 WHEN macd_line < macd_signal THEN -1 ELSE 0 END
                ELSE NULL
            END,

            -- Price vs MA percentages
            price_vs_ema_9_pct = CASE
                WHEN ema_9 IS NOT NULL AND ema_9 > 0 THEN ((close - ema_9) / ema_9) * 100
                ELSE NULL
            END,

            price_vs_ema_20_pct = CASE
                WHEN ema_21 IS NOT NULL AND ema_21 > 0 THEN ((close - ema_21) / ema_21) * 100
                ELSE NULL
            END,

            price_vs_ema_21_pct = CASE
                WHEN ema_21 IS NOT NULL AND ema_21 > 0 THEN ((close - ema_21) / ema_21) * 100
                ELSE NULL
            END,

            price_vs_sma_50_pct = CASE
                WHEN sma_50 IS NOT NULL AND sma_50 > 0 THEN ((close - sma_50) / sma_50) * 100
                ELSE NULL
            END,

            price_vs_sma_200_pct = CASE
                WHEN sma_200 IS NOT NULL AND sma_200 > 0 THEN ((close - sma_200) / sma_200) * 100
                ELSE NULL
            END,

            -- Price above MA booleans
            price_above_ema_9 = CASE WHEN ema_9 IS NOT NULL THEN CASE WHEN close > ema_9 THEN 1 ELSE 0 END ELSE NULL END,
            price_above_ema_20 = CASE WHEN ema_21 IS NOT NULL THEN CASE WHEN close > ema_21 THEN 1 ELSE 0 END ELSE NULL END,
            price_above_ema_21 = CASE WHEN ema_21 IS NOT NULL THEN CASE WHEN close > ema_21 THEN 1 ELSE 0 END ELSE NULL END,
            price_above_sma_50 = CASE WHEN sma_50 IS NOT NULL THEN CASE WHEN close > sma_50 THEN 1 ELSE 0 END ELSE NULL END,
            price_above_sma_200 = CASE WHEN sma_200 IS NOT NULL THEN CASE WHEN close > sma_200 THEN 1 ELSE 0 END ELSE NULL END,

            -- RSI conditions
            rsi_oversold = CASE WHEN rsi_14 IS NOT NULL THEN CASE WHEN rsi_14 < 30 THEN 1 ELSE 0 END ELSE NULL END,
            rsi_overbought = CASE WHEN rsi_14 IS NOT NULL THEN CASE WHEN rsi_14 > 70 THEN 1 ELSE 0 END ELSE NULL END,
            rsi_neutral = CASE WHEN rsi_14 IS NOT NULL THEN CASE WHEN rsi_14 >= 30 AND rsi_14 <= 70 THEN 1 ELSE 0 END ELSE NULL END,

            -- Stochastic conditions
            stoch_oversold = CASE WHEN stoch_k IS NOT NULL THEN CASE WHEN stoch_k < 20 THEN 1 ELSE 0 END ELSE NULL END,
            stoch_overbought = CASE WHEN stoch_k IS NOT NULL THEN CASE WHEN stoch_k > 80 THEN 1 ELSE 0 END ELSE NULL END,

            -- Trend strength
            strong_trend = CASE WHEN adx_14 IS NOT NULL THEN CASE WHEN adx_14 > 25 THEN 1 ELSE 0 END ELSE NULL END,
            weak_trend = CASE WHEN adx_14 IS NOT NULL THEN CASE WHEN adx_14 < 20 THEN 1 ELSE 0 END ELSE NULL END,

            -- Volatility regime (based on NATR)
            volatility_regime = CASE
                WHEN natr_14 IS NOT NULL THEN
                    CASE
                        WHEN natr_14 < 2 THEN 'low'
                        WHEN natr_14 < 5 THEN 'medium'
                        ELSE 'high'
                    END
                ELSE NULL
            END,

            -- Trend regime (based on ADX and DI)
            trend_regime = CASE
                WHEN adx_14 IS NOT NULL THEN
                    CASE
                        WHEN adx_14 < 20 THEN 'sideways'
                        WHEN plus_di IS NOT NULL AND minus_di IS NOT NULL THEN
                            CASE WHEN plus_di > minus_di THEN 'uptrend' ELSE 'downtrend' END
                        ELSE 'sideways'
                    END
                ELSE NULL
            END,

            -- Session indicators (based on hour of candle timestamp)
            -- Note: Must use ec.time to avoid ambiguity with batch.time
            is_asian_session = CASE WHEN EXTRACT(HOUR FROM ec.time) >= 0 AND EXTRACT(HOUR FROM ec.time) < 8 THEN 1 ELSE 0 END,
            is_london_session = CASE WHEN EXTRACT(HOUR FROM ec.time) >= 8 AND EXTRACT(HOUR FROM ec.time) < 16 THEN 1 ELSE 0 END,
            is_us_session = CASE WHEN EXTRACT(HOUR FROM ec.time) >= 13 AND EXTRACT(HOUR FROM ec.time) < 21 THEN 1 ELSE 0 END,
            is_us_market_hours = CASE WHEN EXTRACT(HOUR FROM ec.time) >= 14 AND EXTRACT(HOUR FROM ec.time) < 21 THEN 1 ELSE 0 END,

            -- Bollinger conditions
            price_at_bb_upper = CASE WHEN bb_upper IS NOT NULL THEN CASE WHEN close >= bb_upper THEN 1 ELSE 0 END ELSE NULL END,
            price_at_bb_lower = CASE WHEN bb_lower IS NOT NULL THEN CASE WHEN close <= bb_lower THEN 1 ELSE 0 END ELSE NULL END,
            bb_squeeze = CASE WHEN bb_width IS NOT NULL THEN CASE WHEN bb_width < 0.05 THEN 1 ELSE 0 END ELSE NULL END,

            -- Volume conditions
            high_volume = CASE
                WHEN volume_sma_20 IS NOT NULL AND volume_sma_20 > 0 THEN
                    CASE WHEN volume > volume_sma_20 * 1.5 THEN 1 ELSE 0 END
                ELSE NULL
            END,
            low_volume = CASE
                WHEN volume_sma_20 IS NOT NULL AND volume_sma_20 > 0 THEN
                    CASE WHEN volume < volume_sma_20 * 0.5 THEN 1 ELSE 0 END
                ELSE NULL
            END,

            -- Mark as computed
            derived_computed_at = NOW()

        FROM (
            SELECT time, exchange, symbol, timeframe
            FROM enhanced_candles
            WHERE {where_sql}
            ORDER BY time
            {limit_sql}
        ) AS batch
        WHERE ec.time = batch.time
          AND ec.exchange = batch.exchange
          AND ec.symbol = batch.symbol
          AND ec.timeframe = batch.timeframe
    """)

    result = await session.execute(update_sql)
    await session.commit()

    return result.rowcount


async def run_enrichment(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    batch_size: int = BATCH_SIZE,
    batch_delay: float = 0.5,  # Delay between batches (seconds) to reduce DB load
    pair_delay: float = 2.0,  # Delay between symbol/timeframe pairs
    skip_symbols: set[str] | None = None,  # Symbols to skip (default: major coins)
    yield_to_other_queries: bool = True,  # Pause when DB is busy
) -> dict[str, int]:
    """
    Run full enrichment for specified symbols/timeframes.

    Runs at a gentle pace to avoid blocking other database operations.
    By default, skips major symbols (BTC, ETH, SOL, etc.) that are frequently
    queried by backtests - run those during off-hours.

    Args:
        symbols: List of symbols to enrich (default: all)
        timeframes: List of timeframes to enrich (default: all)
        batch_size: Rows per batch
        batch_delay: Seconds to sleep between batches (reduces DB contention)
        pair_delay: Seconds to sleep between symbol/timeframe pairs
        skip_symbols: Symbols to skip entirely (default: BTC, ETH, SOL, ADA, BNB, DOGE)
        yield_to_other_queries: If True, pause when other heavy queries are running

    Returns:
        Dict of symbol_timeframe -> rows updated
    """
    # Default: skip major symbols that are frequently used in backtests
    if skip_symbols is None:
        skip_symbols = DEFAULT_SKIP_SYMBOLS
    results = {}
    import time
    global_start = time.time()

    async with async_session_maker() as session:
        # CRITICAL: Disable TimescaleDB decompression limit for this session
        # The default limit (100k) is too low for our UPDATE queries on compressed hypertables.
        # Even with batching and WHERE clauses, the UPDATE...FROM pattern causes TimescaleDB
        # to decompress entire chunks looking for matching rows.
        try:
            await session.execute(text("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0"))
            print("[Enrichment] TimescaleDB decompression limit disabled for session", flush=True)
        except Exception as e:
            print(f"[Enrichment] Warning: Could not set TimescaleDB limit: {e}", flush=True)

        # Priority ordering for timeframes (longest first - most important for trading)
        TIMEFRAME_PRIORITY = {"1d": 0, "4h": 1, "1h": 2, "15m": 3, "5m": 4, "1m": 5}

        # Priority ordering for symbols (majors first)
        SYMBOL_PRIORITY = {
            "BTC": 0, "ETH": 1, "SOL": 2, "BNB": 3, "XRP": 4,
            "ADA": 5, "AVAX": 6, "DOGE": 7, "DOT": 8, "MATIC": 9,
            "LINK": 10, "UNI": 11, "ATOM": 12, "LTC": 13, "ETC": 14,
        }
        DEFAULT_SYMBOL_PRIORITY = 100  # Unknown symbols go last

        # Get distinct symbol/timeframe combinations with row counts
        if not symbols or not timeframes:
            query = text("""
                SELECT symbol, timeframe, COUNT(*) as pending_count
                FROM enhanced_candles
                WHERE derived_computed_at IS NULL
                GROUP BY symbol, timeframe
            """)
            result = await session.execute(query)
            pairs_with_counts = result.fetchall()

            # Sort by: timeframe priority (longest first), then symbol priority (majors first)
            def sort_key(row):
                symbol, timeframe, count = row
                tf_priority = TIMEFRAME_PRIORITY.get(timeframe, 10)
                sym_priority = SYMBOL_PRIORITY.get(symbol, DEFAULT_SYMBOL_PRIORITY)
                return (tf_priority, sym_priority, symbol)

            pairs_with_counts = sorted(pairs_with_counts, key=sort_key)

            # Filter out skipped symbols
            if skip_symbols:
                pairs_with_counts = [row for row in pairs_with_counts if row[0] not in skip_symbols]

            pairs = [(row[0], row[1]) for row in pairs_with_counts]
            pair_counts = {f"{row[0]}_{row[1]}": row[2] for row in pairs_with_counts}
        else:
            pairs = [(s, t) for s in symbols for t in timeframes if s not in (skip_symbols or set())]
            pair_counts = {}

        # Get total pending for ETA calculation
        total_pending_query = text("SELECT COUNT(*) FROM enhanced_candles WHERE derived_computed_at IS NULL")
        total_pending_result = await session.execute(total_pending_query)
        total_pending = total_pending_result.scalar() or 0

        total_updated = 0
        total_pairs = len(pairs)

        print("=" * 70, flush=True)
        print(f"[Enrichment] STARTING INDICATOR ENRICHMENT (LOW PRIORITY MODE)", flush=True)
        print(f"[Enrichment] Total pending: {total_pending:,} rows across {total_pairs} symbol/timeframe pairs", flush=True)
        print(f"[Enrichment] Priority: 1d -> 4h -> 1h -> 15m -> 5m -> 1m", flush=True)
        if skip_symbols:
            print(f"[Enrichment] SKIPPING: {', '.join(sorted(skip_symbols))} (run these during off-hours)", flush=True)
        print(f"[Enrichment] Throttle: {batch_delay}s between batches, {pair_delay}s between pairs", flush=True)
        if yield_to_other_queries:
            print(f"[Enrichment] Auto-yield: Will pause when DB is busy", flush=True)
        print("=" * 70, flush=True)

        for idx, (symbol, timeframe) in enumerate(pairs):
            pair_start = time.time()
            pair_pending = pair_counts.get(f"{symbol}_{timeframe}", 0)

            # Progress header for this pair
            pct_pairs = ((idx) / total_pairs * 100) if total_pairs > 0 else 0
            pct_rows = (total_updated / total_pending * 100) if total_pending > 0 else 0

            print(f"\n[{idx+1}/{total_pairs}] {symbol}/{timeframe} (~{pair_pending:,} rows)", flush=True)
            print(f"    Progress: {pct_rows:.1f}% rows | {pct_pairs:.1f}% pairs", flush=True)

            # ETA calculation (accounts for throttling)
            if total_updated > 0:
                elapsed = time.time() - global_start
                rate = total_updated / elapsed  # This includes delay time, so ETA is accurate
                remaining = total_pending - total_updated
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                if eta_minutes > 60:
                    print(f"    ETA: {eta_minutes/60:.1f} hours remaining at {rate:,.0f} rows/sec (throttled)", flush=True)
                else:
                    print(f"    ETA: {eta_minutes:.1f} minutes remaining at {rate:,.0f} rows/sec (throttled)", flush=True)

            updated = 0
            batch_num = 0
            while True:
                # Check if we should yield to other queries
                if yield_to_other_queries and batch_num > 0:
                    is_busy, active = await check_db_activity(session)
                    if is_busy:
                        print(f"    [Yield] DB busy ({active} queries), pausing...", flush=True)
                        await wait_for_db_idle(session, max_wait=300, check_interval=10)

                batch_num += 1
                batch_updated = await compute_derived_indicators_batch(
                    session,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=batch_size,
                )

                if batch_updated == 0:
                    break

                updated += batch_updated
                total_updated += batch_updated
                elapsed = time.time() - global_start
                rate = total_updated / elapsed if elapsed > 0 else 0
                pct_complete = (total_updated / total_pending * 100) if total_pending > 0 else 0

                # Compact batch progress
                print(f"    Batch {batch_num}: +{batch_updated:,} | {symbol}: {updated:,} | Total: {total_updated:,} ({pct_complete:.2f}%) | {rate:,.0f}/s", flush=True)

                # Throttle: sleep between batches to reduce DB contention
                if batch_delay > 0:
                    await asyncio.sleep(batch_delay)

            pair_elapsed = time.time() - pair_start
            if updated > 0:
                results[f"{symbol}_{timeframe}"] = updated
                print(f"    DONE: {updated:,} rows in {pair_elapsed:.1f}s", flush=True)
            else:
                print(f"    SKIP: No pending rows", flush=True)

            # Throttle: sleep between pairs to let other queries run
            if pair_delay > 0 and idx < len(pairs) - 1:
                await asyncio.sleep(pair_delay)

        total_elapsed = time.time() - global_start
        print("\n" + "=" * 70, flush=True)
        print(f"[Enrichment] COMPLETE!", flush=True)
        print(f"[Enrichment] Total: {total_updated:,} rows enriched", flush=True)
        print(f"[Enrichment] Time: {total_elapsed/60:.1f} minutes ({total_elapsed:.0f}s)", flush=True)
        print(f"[Enrichment] Rate: {total_updated/total_elapsed:,.0f} rows/sec average", flush=True)
        print("=" * 70, flush=True)

    return results


async def get_enrichment_status() -> dict:
    """
    Get current enrichment status.

    Returns:
        Dict with counts of enriched vs unenriched candles
    """
    async with async_session_maker() as session:
        query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(derived_computed_at) as enriched,
                COUNT(*) - COUNT(derived_computed_at) as pending
            FROM enhanced_candles
        """)
        result = await session.execute(query)
        row = result.fetchone()

        return {
            "total_candles": row[0],
            "enriched": row[1],
            "pending": row[2],
            "percent_complete": round(row[1] / row[0] * 100, 2) if row[0] > 0 else 0,
        }


async def add_derived_columns_if_missing():
    """
    Add the derived indicator columns to enhanced_candles if they don't exist.

    This is a one-time migration that adds the new columns.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    columns = [
        ("ma_cross_20_50", "INTEGER"),
        ("golden_cross", "INTEGER"),
        ("death_cross", "INTEGER"),
        ("macd_cross", "INTEGER"),
        ("price_vs_ema_9_pct", "DOUBLE PRECISION"),
        ("price_vs_ema_20_pct", "DOUBLE PRECISION"),
        ("price_vs_ema_21_pct", "DOUBLE PRECISION"),
        ("price_vs_sma_50_pct", "DOUBLE PRECISION"),
        ("price_vs_sma_200_pct", "DOUBLE PRECISION"),
        ("price_above_ema_9", "INTEGER"),
        ("price_above_ema_20", "INTEGER"),
        ("price_above_ema_21", "INTEGER"),
        ("price_above_sma_50", "INTEGER"),
        ("price_above_sma_200", "INTEGER"),
        ("rsi_oversold", "INTEGER"),
        ("rsi_overbought", "INTEGER"),
        ("rsi_neutral", "INTEGER"),
        ("stoch_oversold", "INTEGER"),
        ("stoch_overbought", "INTEGER"),
        ("strong_trend", "INTEGER"),
        ("weak_trend", "INTEGER"),
        ("volatility_regime", "VARCHAR(20)"),
        ("trend_regime", "VARCHAR(20)"),
        ("is_asian_session", "INTEGER"),
        ("is_london_session", "INTEGER"),
        ("is_us_session", "INTEGER"),
        ("is_us_market_hours", "INTEGER"),
        ("price_at_bb_upper", "INTEGER"),
        ("price_at_bb_lower", "INTEGER"),
        ("bb_squeeze", "INTEGER"),
        ("high_volume", "INTEGER"),
        ("low_volume", "INTEGER"),
        ("derived_computed_at", "TIMESTAMPTZ"),
        # Motion derivatives (Bear Protection)
        ("close_velocity_zscore", "DOUBLE PRECISION"),
        ("close_acceleration_zscore", "DOUBLE PRECISION"),
        ("close_jerk_zscore", "DOUBLE PRECISION"),
        ("adx_14_velocity_zscore", "DOUBLE PRECISION"),
        ("adx_14_acceleration_zscore", "DOUBLE PRECISION"),
        ("adx_14_jerk_zscore", "DOUBLE PRECISION"),
        # CTC trigger
        ("defensive_trigger", "INTEGER"),
    ]

    async with async_session_maker() as session:
        for col_name, col_type in columns:
            try:
                await session.execute(text(f"""
                    ALTER TABLE enhanced_candles
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """))
            except Exception as e:
                logger.warning(f"Column {col_name} may already exist: {e}")

        await session.commit()
        logger.info(f"[Migration] Added {len(columns)} derived indicator columns")


async def compute_motion_derivatives_batch(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    batch_size: int = 5000,
) -> int:
    """
    Compute motion derivatives for a symbol/timeframe using PostgreSQL window functions.

    Computes:
    - close_velocity_zscore: z-score of price velocity (1st derivative)
    - close_acceleration_zscore: z-score of price acceleration (2nd derivative)
    - close_jerk_zscore: z-score of price jerk (3rd derivative)
    - adx_14_jerk_zscore: z-score of ADX jerk (3rd derivative of ADX)
    - defensive_trigger: 1 if acc < -1.5 AND adx_jerk < -0.5, else 0

    Uses window functions for efficient batch computation.
    """
    # This SQL computes motion derivatives with z-scores
    # Window size = 21 periods for rolling mean/std
    update_sql = text("""
        WITH derivatives AS (
            SELECT
                time, exchange, symbol, timeframe,
                close,
                adx_14,
                -- Velocity (1st derivative)
                close - LAG(close, 1) OVER w AS close_vel,
                adx_14 - LAG(adx_14, 1) OVER w AS adx_vel,
                -- Acceleration (2nd derivative) - needs nested CTE
                ROW_NUMBER() OVER w AS rn
            FROM enhanced_candles
            WHERE symbol = :symbol
              AND timeframe = :timeframe
              AND close_acceleration_zscore IS NULL
            WINDOW w AS (PARTITION BY exchange, symbol, timeframe ORDER BY time)
            LIMIT :batch_size
        ),
        accel AS (
            SELECT
                d.*,
                close_vel - LAG(close_vel, 1) OVER w AS close_acc,
                adx_vel - LAG(adx_vel, 1) OVER w AS adx_acc
            FROM derivatives d
            WINDOW w AS (PARTITION BY exchange, symbol, timeframe ORDER BY time)
        ),
        jerk AS (
            SELECT
                a.*,
                close_acc - LAG(close_acc, 1) OVER w AS close_jrk,
                adx_acc - LAG(adx_acc, 1) OVER w AS adx_jrk
            FROM accel a
            WINDOW w AS (PARTITION BY exchange, symbol, timeframe ORDER BY time)
        ),
        zscores AS (
            SELECT
                j.time, j.exchange, j.symbol, j.timeframe,
                j.close_acc,
                j.adx_jrk,
                -- Z-score of acceleration (21-period rolling)
                CASE
                    WHEN STDDEV(j.close_acc) OVER w21 > 0 THEN
                        (j.close_acc - AVG(j.close_acc) OVER w21) / STDDEV(j.close_acc) OVER w21
                    ELSE NULL
                END AS acc_zscore,
                -- Z-score of ADX jerk (21-period rolling)
                CASE
                    WHEN STDDEV(j.adx_jrk) OVER w21 > 0 THEN
                        (j.adx_jrk - AVG(j.adx_jrk) OVER w21) / STDDEV(j.adx_jrk) OVER w21
                    ELSE NULL
                END AS adx_jerk_zscore
            FROM jerk j
            WINDOW w21 AS (
                PARTITION BY j.exchange, j.symbol, j.timeframe
                ORDER BY j.time
                ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
            )
        )
        UPDATE enhanced_candles ec
        SET
            close_acceleration_zscore = z.acc_zscore,
            adx_14_jerk_zscore = z.adx_jerk_zscore,
            -- Defensive trigger: CTC signal fires when BOTH conditions met
            defensive_trigger = CASE
                WHEN z.acc_zscore IS NOT NULL AND z.adx_jerk_zscore IS NOT NULL THEN
                    CASE WHEN z.acc_zscore < -1.5 AND z.adx_jerk_zscore < -0.5 THEN 1 ELSE 0 END
                ELSE NULL
            END
        FROM zscores z
        WHERE ec.time = z.time
          AND ec.exchange = z.exchange
          AND ec.symbol = z.symbol
          AND ec.timeframe = z.timeframe
    """)

    result = await session.execute(update_sql, {
        "symbol": symbol,
        "timeframe": timeframe,
        "batch_size": batch_size,
    })
    await session.commit()

    return result.rowcount


async def run_motion_derivative_enrichment(
    symbols: list[str] = None,
    timeframes: list[str] = None,
) -> dict[str, int]:
    """
    Run motion derivative enrichment for Bear Protection.

    This computes close_acceleration_zscore, adx_14_jerk_zscore, and defensive_trigger
    for all candles that don't have them yet.

    Args:
        symbols: List of symbols to process (default: all)
        timeframes: List of timeframes (default: 1h, 4h for Bear Protection)

    Returns:
        Dict of symbol_timeframe -> rows updated
    """
    import time as time_module

    # Default to Bear Protection timeframes
    if timeframes is None:
        timeframes = ["1h", "4h"]

    results = {}

    async with async_session_maker() as session:
        # Disable TimescaleDB decompression limit
        try:
            await session.execute(text("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0"))
        except Exception:
            pass

        # Get symbols with pending enrichment
        if not symbols:
            query = text("""
                SELECT DISTINCT symbol
                FROM enhanced_candles
                WHERE close_acceleration_zscore IS NULL
                  AND timeframe = ANY(:timeframes)
            """)
            result = await session.execute(query, {"timeframes": timeframes})
            symbols = [row[0] for row in result.fetchall()]

        print("=" * 70)
        print("[Motion Derivatives] Starting Bear Protection enrichment")
        print(f"[Motion Derivatives] Symbols: {len(symbols)}, Timeframes: {timeframes}")
        print("=" * 70)

        total_updated = 0
        for symbol in symbols:
            for tf in timeframes:
                start = time_module.time()
                updated = 0

                # Process in batches
                while True:
                    batch_updated = await compute_motion_derivatives_batch(
                        session, symbol, tf, batch_size=5000
                    )
                    if batch_updated == 0:
                        break
                    updated += batch_updated
                    total_updated += batch_updated
                    print(f"  {symbol}/{tf}: +{batch_updated} ({updated} total)")

                if updated > 0:
                    elapsed = time_module.time() - start
                    results[f"{symbol}_{tf}"] = updated
                    print(f"  {symbol}/{tf} DONE: {updated} rows in {elapsed:.1f}s")

        print("=" * 70)
        print(f"[Motion Derivatives] Complete: {total_updated} rows enriched")
        print("=" * 70)

    return results


# Convenience function for running from command line or startup
async def startup_enrichment(background: bool = True):
    """
    Run indicator enrichment on startup.

    Args:
        background: Run in background task (default: True)
    """
    async def _run():
        # First ensure columns exist
        await add_derived_columns_if_missing()

        # Check status
        status = await get_enrichment_status()
        logger.info(f"[Enrichment] Status: {status['enriched']:,}/{status['total_candles']:,} enriched ({status['percent_complete']}%)")

        if status['pending'] > 0:
            logger.info(f"[Enrichment] Starting enrichment of {status['pending']:,} pending candles...")
            await run_enrichment()
        else:
            logger.info("[Enrichment] All candles already enriched!")

    if background:
        asyncio.create_task(_run())
    else:
        await _run()


# =============================================================================
# On-Demand Single Candle Enrichment
# =============================================================================

def compute_derived_for_candle(candle: dict) -> dict:
    """
    Compute all derived indicators for a single candle in memory.

    This is a pure Python function that computes the same indicators as the
    SQL batch enrichment, but for a single candle. Used during pattern matching
    when a candle hasn't been pre-enriched.

    Args:
        candle: Dict with candle data (close, ema_21, sma_50, rsi_14, etc.)

    Returns:
        Dict of computed derived indicator values
    """
    derived = {}

    # Extract base values (with None safety)
    close = candle.get("close") or 0
    ema_9 = candle.get("ema_9")
    ema_21 = candle.get("ema_21")
    sma_50 = candle.get("sma_50")
    sma_200 = candle.get("sma_200")
    macd_line = candle.get("macd_line")
    macd_signal = candle.get("macd_signal")
    rsi_14 = candle.get("rsi_14")
    stoch_k = candle.get("stoch_k")
    adx_14 = candle.get("adx_14")
    plus_di = candle.get("plus_di")
    minus_di = candle.get("minus_di")
    natr_14 = candle.get("natr_14")
    bb_upper = candle.get("bb_upper")
    bb_lower = candle.get("bb_lower")
    bb_width = candle.get("bb_width")
    volume = candle.get("volume")
    volume_sma_20 = candle.get("volume_sma_20")

    # Get timestamp for session indicators
    timestamp = candle.get("time") or candle.get("timestamp")

    # MA Cross signals (1 = bullish, -1 = bearish, 0 = neutral)
    if ema_21 is not None and sma_50 is not None:
        derived["ma_cross_20_50"] = 1 if ema_21 > sma_50 else (-1 if ema_21 < sma_50 else 0)

    if sma_50 is not None and sma_200 is not None:
        derived["golden_cross"] = 1 if sma_50 > sma_200 else 0
        derived["death_cross"] = 1 if sma_50 < sma_200 else 0

    # MACD Cross
    if macd_line is not None and macd_signal is not None:
        derived["macd_cross"] = 1 if macd_line > macd_signal else (-1 if macd_line < macd_signal else 0)

    # Price vs MA percentages
    if ema_9 is not None and ema_9 > 0:
        derived["price_vs_ema_9_pct"] = ((close - ema_9) / ema_9) * 100
    if ema_21 is not None and ema_21 > 0:
        derived["price_vs_ema_20_pct"] = ((close - ema_21) / ema_21) * 100
        derived["price_vs_ema_21_pct"] = ((close - ema_21) / ema_21) * 100
    if sma_50 is not None and sma_50 > 0:
        derived["price_vs_sma_50_pct"] = ((close - sma_50) / sma_50) * 100
    if sma_200 is not None and sma_200 > 0:
        derived["price_vs_sma_200_pct"] = ((close - sma_200) / sma_200) * 100

    # Price above MA booleans
    if ema_9 is not None:
        derived["price_above_ema_9"] = 1 if close > ema_9 else 0
    if ema_21 is not None:
        derived["price_above_ema_20"] = 1 if close > ema_21 else 0
        derived["price_above_ema_21"] = 1 if close > ema_21 else 0
    if sma_50 is not None:
        derived["price_above_sma_50"] = 1 if close > sma_50 else 0
    if sma_200 is not None:
        derived["price_above_sma_200"] = 1 if close > sma_200 else 0

    # RSI conditions
    if rsi_14 is not None:
        derived["rsi_oversold"] = 1 if rsi_14 < 30 else 0
        derived["rsi_overbought"] = 1 if rsi_14 > 70 else 0
        derived["rsi_neutral"] = 1 if 30 <= rsi_14 <= 70 else 0

    # Stochastic conditions
    if stoch_k is not None:
        derived["stoch_oversold"] = 1 if stoch_k < 20 else 0
        derived["stoch_overbought"] = 1 if stoch_k > 80 else 0

    # Trend strength
    if adx_14 is not None:
        derived["strong_trend"] = 1 if adx_14 > 25 else 0
        derived["weak_trend"] = 1 if adx_14 < 20 else 0

    # Volatility regime
    if natr_14 is not None:
        if natr_14 < 2:
            derived["volatility_regime"] = "low"
        elif natr_14 < 5:
            derived["volatility_regime"] = "medium"
        else:
            derived["volatility_regime"] = "high"

    # Trend regime
    if adx_14 is not None:
        if adx_14 < 20:
            derived["trend_regime"] = "sideways"
        elif plus_di is not None and minus_di is not None:
            derived["trend_regime"] = "uptrend" if plus_di > minus_di else "downtrend"
        else:
            derived["trend_regime"] = "sideways"

    # Session indicators (based on hour)
    if timestamp is not None:
        try:
            if hasattr(timestamp, "hour"):
                hour = timestamp.hour
            else:
                # Assume Unix timestamp in seconds or milliseconds
                ts = timestamp if timestamp < 1e12 else timestamp / 1000
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                hour = dt.hour

            derived["is_asian_session"] = 1 if 0 <= hour < 8 else 0
            derived["is_london_session"] = 1 if 8 <= hour < 16 else 0
            derived["is_us_session"] = 1 if 13 <= hour < 21 else 0
            derived["is_us_market_hours"] = 1 if 14 <= hour < 21 else 0
        except Exception:
            pass

    # Bollinger conditions
    if bb_upper is not None and close >= bb_upper:
        derived["price_at_bb_upper"] = 1
    elif bb_upper is not None:
        derived["price_at_bb_upper"] = 0

    if bb_lower is not None and close <= bb_lower:
        derived["price_at_bb_lower"] = 1
    elif bb_lower is not None:
        derived["price_at_bb_lower"] = 0

    if bb_width is not None:
        derived["bb_squeeze"] = 1 if bb_width < 0.05 else 0

    # Volume conditions
    if volume is not None and volume_sma_20 is not None and volume_sma_20 > 0:
        derived["high_volume"] = 1 if volume > volume_sma_20 * 1.5 else 0
        derived["low_volume"] = 1 if volume < volume_sma_20 * 0.5 else 0

    return derived


async def enrich_candle_on_demand(
    session,
    candle: dict,
    persist: bool = True,
) -> dict:
    """
    Compute derived indicators for a single candle and optionally persist to DB.

    This is called during pattern matching when we encounter a candle that
    hasn't been pre-enriched. It computes the values in Python and updates
    the database row so future queries will have the precomputed values.

    Args:
        session: Database session (AsyncSession)
        candle: Dict with candle data including primary keys (time, exchange, symbol, timeframe)
        persist: Whether to persist to database (default True)

    Returns:
        Dict of computed derived indicator values
    """
    # Compute derived indicators
    derived = compute_derived_for_candle(candle)

    if not derived:
        return derived

    # Persist to database if requested
    if persist and session is not None:
        try:
            # Build UPDATE statement for this specific candle
            time_val = candle.get("time")
            exchange = candle.get("exchange")
            symbol = candle.get("symbol")
            timeframe = candle.get("timeframe")

            if all([time_val, exchange, symbol, timeframe]):
                # Build SET clause from derived values
                set_parts = []
                params = {
                    "time_val": time_val,
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                }

                for col, val in derived.items():
                    param_name = f"val_{col}"
                    set_parts.append(f"{col} = :{param_name}")
                    params[param_name] = val

                # Mark as computed
                set_parts.append("derived_computed_at = NOW()")

                set_clause = ", ".join(set_parts)

                update_sql = text(f"""
                    UPDATE enhanced_candles
                    SET {set_clause}
                    WHERE time = :time_val
                      AND exchange = :exchange
                      AND symbol = :symbol
                      AND timeframe = :timeframe
                      AND derived_computed_at IS NULL
                """)

                await session.execute(update_sql, params)
                # Don't commit here - let the caller manage the transaction

        except Exception as e:
            # Log but don't fail - enrichment is best-effort
            logger.debug(f"[OnDemand] Failed to persist derived indicators: {e}")

    return derived


def enrich_candle_dict(candle: dict) -> dict:
    """
    Enrich a candle dict with derived indicators (in-memory only, no DB).

    This is a synchronous helper for pattern matching that adds derived
    indicator values directly to the candle dict if they're missing.

    Args:
        candle: Dict with candle data

    Returns:
        Same dict with derived indicators added (mutates input)
    """
    # Check if already enriched
    if candle.get("derived_computed_at") is not None:
        return candle

    # Compute derived indicators
    derived = compute_derived_for_candle(candle)

    # Add to candle dict (only if not already present)
    for key, value in derived.items():
        if key not in candle or candle[key] is None:
            candle[key] = value

    return candle
