"""
Market Snapshot Service.

Collects the FULL market state across all timeframes, order book, and ticks
into a single flat dict. This dict is:
  1. Passed to agents for pattern evaluation (they see everything)
  2. Recorded on trade open/close as entry_signals/exit_signals JSONB

Base timeframe indicators use bare names (rsi_14, adx_14, etc.).
Higher timeframe indicators get a suffix (_5m, _15m, _1h, _4h, _1d).
Order book and tick data use their column names directly.

The result is a single dict with ~500+ keys that any pattern can match against.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Columns to skip when flattening candle rows (metadata, not indicators)
_META_COLS = frozenset({
    "time", "exchange", "symbol", "timeframe",
    "enriched_at", "derived_computed_at", "id",
})

# Timeframes to collect, in order. First is the base (no suffix).
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


async def collect_market_snapshot(
    session: AsyncSession,
    symbol: str,
    exchange: str = "binance",
) -> dict | None:
    """
    Collect full market state for a symbol across all timeframes + depth + ticks.

    Returns a flat dict with ~500+ keys:
      - Base TF (1m): rsi_14, adx_14, close, volume, ...
      - Higher TFs: rsi_14_5m, rsi_14_1h, adx_14_4h, ...
      - Order book: ob_bid_vol_10, ob_ask_vol_10, ob_imbalance, ob_spread_bps, ob_mid_price
      - Tick summary: tick_count_1m, tick_buy_vol_1m, tick_sell_vol_1m, tick_vwap_1m

    Returns None if no base candle data is available.
    """
    # Normalize symbol for DB lookup
    base_sym = symbol.replace("-USDT", "").replace("-USD", "").replace("USDT", "").replace("USD", "")
    symbol_patterns = [symbol, f"{base_sym}USDT", f"{base_sym}-USD", base_sym]

    snapshot = {}

    # ------------------------------------------------------------------
    # 1. Multi-timeframe candles from enhanced_candles
    #    Uses get_latest_enriched_candle which computes indicators on-the-fly
    #    when the DB row is missing them (e.g., freshly-collected 1m candles).
    # ------------------------------------------------------------------
    base_found = False
    try:
        from Fast_Swarm.Main import get_latest_enriched_candle
    except ImportError:
        get_latest_enriched_candle = None

    for tf in TIMEFRAMES:
        candle = None

        # Prefer the enriched candle path (computes indicators on-the-fly if missing)
        if get_latest_enriched_candle is not None:
            try:
                candle = await get_latest_enriched_candle(session, symbol, timeframe=tf)
            except Exception:
                pass

        # Fallback: raw DB query
        if not candle:
            result = await session.execute(
                text("""
                    SELECT * FROM enhanced_candles
                    WHERE symbol = ANY(:symbols) AND timeframe = :tf
                    ORDER BY time DESC LIMIT 1
                """),
                {"symbols": symbol_patterns, "tf": tf},
            )
            row = result.mappings().first()
            if row:
                candle = dict(row)

        if not candle:
            continue

        suffix = "" if tf == "1m" else f"_{tf}"

        for col, val in candle.items():
            if col in _META_COLS or val is None:
                continue
            # Coerce Decimal → float so downstream math works
            if hasattr(val, "as_tuple"):  # duck-type Decimal check
                val = float(val)
            snapshot[f"{col}{suffix}"] = val

        if tf == "1m":
            base_found = True
            # Preserve OHLCV on base without suffix
            for ohlcv in ("open", "high", "low", "close", "volume"):
                if ohlcv in candle and candle[ohlcv] is not None:
                    v = candle[ohlcv]
                    snapshot[ohlcv] = float(v) if hasattr(v, "as_tuple") else v

    if not base_found:
        return None

    # ------------------------------------------------------------------
    # 2. Latest order book snapshot
    # ------------------------------------------------------------------
    try:
        # Match exchange-specific symbol format
        ob_symbols = symbol_patterns + [f"{base_sym}-USD"]
        ob_result = await session.execute(
            text("""
                SELECT bid_vol_10, ask_vol_10, imbalance, spread_bps, mid_price
                FROM order_book_snapshots
                WHERE symbol = ANY(:symbols)
                ORDER BY created_at DESC LIMIT 1
            """),
            {"symbols": ob_symbols},
        )
        ob_row = ob_result.mappings().first()
        if ob_row:
            for col, val in dict(ob_row).items():
                if val is not None:
                    snapshot[f"ob_{col}"] = float(val)
    except Exception as e:
        logger.debug("Order book snapshot fetch failed: %s", e)

    # ------------------------------------------------------------------
    # 3. Tick summary for the last 1 minute
    # ------------------------------------------------------------------
    try:
        tick_result = await session.execute(
            text("""
                SELECT
                    count(*) as tick_count_1m,
                    sum(size) FILTER (WHERE side = 'buy') as tick_buy_vol_1m,
                    sum(size) FILTER (WHERE side = 'sell') as tick_sell_vol_1m,
                    sum(price * size) / NULLIF(sum(size), 0) as tick_vwap_1m,
                    max(price) - min(price) as tick_range_1m,
                    stddev(price) as tick_price_stddev_1m
                FROM exchange_ticks
                WHERE symbol = ANY(:symbols)
                  AND time >= now() - interval '1 minute'
            """),
            {"symbols": symbol_patterns + [f"{base_sym}-USD"]},
        )
        tick_row = tick_result.mappings().first()
        if tick_row:
            for col, val in dict(tick_row).items():
                if val is not None:
                    snapshot[col] = float(val)
    except Exception as e:
        logger.debug("Tick summary fetch failed: %s", e)

    # ------------------------------------------------------------------
    # 4. Metadata
    # ------------------------------------------------------------------
    snapshot["_snapshot_time"] = datetime.now(timezone.utc).isoformat()
    snapshot["_symbol"] = symbol
    snapshot["_exchange"] = exchange
    available_tfs = []
    keys = set(snapshot.keys())
    for tf in TIMEFRAMES:
        if tf == "1m":
            if base_found:
                available_tfs.append(tf)
        elif any(k.endswith(f"_{tf}") for k in keys):
            available_tfs.append(tf)
    snapshot["_timeframes_available"] = available_tfs

    return snapshot


def snapshot_to_jsonb(snapshot: dict) -> dict:
    """
    Prepare snapshot dict for JSONB storage.

    Converts non-serializable types (Decimal, datetime) to float/str.
    Strips None values and internal metadata keys.
    """
    import decimal

    clean = {}
    for k, v in snapshot.items():
        if v is None:
            continue
        if isinstance(v, decimal.Decimal):
            clean[k] = float(v)
        elif isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, (int, float, str, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean
