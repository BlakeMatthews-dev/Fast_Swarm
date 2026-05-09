import traceback
from typing import Any

from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select, text

from ..Models.trade_models import BacktestTrade


async def fetch_indicators_at_timestamp(
    session: AsyncSession, symbol: str, timestamp: int, timeframe: str = "1h"
) -> dict[str, Any] | None:
    """
    Fetch indicator snapshot from enhanced_candles at a specific timestamp.

    Args:
        session: Database session
        symbol: Trading pair symbol (e.g., 'BTC', 'ETH')
        timestamp: Unix timestamp (seconds or milliseconds)
        timeframe: Candle timeframe (default '1h')

    Returns:
        Dict of indicator values or None if not found
    """
    # Handle both seconds and milliseconds timestamps
    ts_seconds = timestamp / 1000.0 if timestamp > 10_000_000_000 else float(timestamp)

    result = await session.execute(
        text("""
            SELECT
                rsi_14, macd_line, macd_signal, atr_14, adx_14,
                bb_upper, bb_lower, stoch_k, stoch_d, cci_14,
                obv, supertrend, supertrend_direction, regime
            FROM enhanced_candles
            WHERE symbol = :symbol
            AND time = to_timestamp(:ts)
            AND timeframe = :timeframe
            LIMIT 1
        """),
        {"symbol": symbol, "ts": ts_seconds, "timeframe": timeframe},
    )
    row = result.fetchone()

    if not row or row.rsi_14 is None:
        return None

    return {
        "rsi_14": row.rsi_14,
        "macd_line": row.macd_line,
        "macd_signal": row.macd_signal,
        "atr_14": row.atr_14,
        "adx_14": row.adx_14,
        "bb_upper": row.bb_upper,
        "bb_lower": row.bb_lower,
        "stoch_k": row.stoch_k,
        "stoch_d": row.stoch_d,
        "cci_14": row.cci_14,
        "obv": row.obv,
        "supertrend": row.supertrend,
        "supertrend_direction": row.supertrend_direction,
        "regime": row.regime,
    }


async def fetch_indicators_batch(
    session: AsyncSession,
    lookups: list[tuple[str, int]],  # List of (symbol, timestamp) pairs
    timeframe: str = "1h",
) -> dict[tuple[str, float], dict[str, Any]]:
    """
    Batch fetch indicator snapshots from enhanced_candles.

    NOTE: TimescaleDB compressed hypertables perform poorly with CTE/VALUES joins
    (7+ seconds planning time!). Individual point lookups are ~2ms each and hit
    the index directly. This function uses individual queries which is actually
    faster for TimescaleDB.

    Args:
        session: Database session
        lookups: List of (symbol, timestamp) tuples to fetch
        timeframe: Candle timeframe (default '1h')

    Returns:
        Dict mapping (symbol, ts_seconds) -> indicator dict
    """
    if not lookups:
        return {}

    indicators = {}

    # Dedupe lookups to avoid redundant queries
    seen = set()
    unique_lookups = []
    for symbol, ts in lookups:
        if ts is None:
            continue
        ts_seconds = ts / 1000.0 if ts > 10_000_000_000 else float(ts)
        key = (symbol, ts_seconds)
        if key not in seen:
            seen.add(key)
            unique_lookups.append(key)

    # Individual point lookups are fast (~2ms each) on TimescaleDB indexes
    for symbol, ts_seconds in unique_lookups:
        result = await session.execute(
            text("""
                SELECT
                    rsi_14, macd_line, macd_signal, atr_14, adx_14,
                    bb_upper, bb_lower, stoch_k, stoch_d, cci_14,
                    obv, supertrend, supertrend_direction, regime
                FROM enhanced_candles
                WHERE symbol = :symbol
                AND time = to_timestamp(:ts)
                AND timeframe = :timeframe
                LIMIT 1
            """),
            {"symbol": symbol, "ts": ts_seconds, "timeframe": timeframe},
        )
        row = result.fetchone()

        if row and row.rsi_14 is not None:
            indicators[(symbol, ts_seconds)] = {
                "rsi_14": row.rsi_14,
                "macd_line": row.macd_line,
                "macd_signal": row.macd_signal,
                "atr_14": row.atr_14,
                "adx_14": row.adx_14,
                "bb_upper": row.bb_upper,
                "bb_lower": row.bb_lower,
                "stoch_k": row.stoch_k,
                "stoch_d": row.stoch_d,
                "cci_14": row.cci_14,
                "obv": row.obv,
                "supertrend": row.supertrend,
                "supertrend_direction": row.supertrend_direction,
                "regime": row.regime,
            }

    return indicators


async def create_trade(session: AsyncSession, trade: BacktestTrade) -> BacktestTrade:
    """Create a single trade record."""
    session.add(trade)
    await session.flush()
    return trade


def _validate_trade_record(record) -> tuple[bool, str]:
    """
    Validate a trade record before persistence.

    Returns:
        Tuple of (is_valid, error_message)
    """
    errors = []

    # Required fields
    if not hasattr(record, "trade_id") or not record.trade_id:
        errors.append("missing trade_id")
    if not hasattr(record, "agent_id") or not record.agent_id:
        errors.append("missing agent_id")
    if not hasattr(record, "asset") or not record.asset:
        errors.append("missing asset/symbol")

    # Numeric validation
    if hasattr(record, "entry_price"):
        if record.entry_price is None:
            errors.append("entry_price is None")
        elif record.entry_price <= 0:
            errors.append(f"invalid entry_price: {record.entry_price}")

    if hasattr(record, "exit_price"):
        if record.exit_price is None:
            errors.append("exit_price is None")
        elif record.exit_price <= 0:
            errors.append(f"invalid exit_price: {record.exit_price}")

    # PnL sanity check (warn but don't fail)
    if hasattr(record, "pnl_pct") and record.pnl_pct is not None:
        import math

        if not math.isfinite(record.pnl_pct):
            errors.append(f"pnl_pct is not finite: {record.pnl_pct}")
        elif abs(record.pnl_pct) > 1000:  # >1000% gain/loss is suspicious
            # Warning only - don't fail
            pass

    if errors:
        return False, "; ".join(errors)
    return True, ""


async def persist_backtest_trades(
    session: AsyncSession,
    trade_records: list,
    source: str = "evolution_backtest",
    timeframe: str = "1h",
    batch_size: int = 100,
    fetch_indicators: bool = False,  # Disabled by default - backfill later when DB idle
) -> int:
    """
    Persist trades from backtest to backtest_trades_unified table.

    Args:
        session: Database session
        trade_records: List of TradeRecord dataclass objects (from local_agents)
        source: Source identifier ('evolution_backtest', 'pattern_backtest', 'chaos')
        timeframe: Timeframe used in backtest
        batch_size: Number of trades to insert per batch
        fetch_indicators: If True, fetch indicator snapshots from enhanced_candles.
                         Disabled by default to avoid DB contention during heavy writes.
                         Use backfill_trade_indicators() later when DB is idle.

    Returns:
        Number of trades persisted
    """
    if not trade_records:
        print(f"[Trade Persist] No trades to persist (source={source})")
        return 0

    persisted = 0
    skipped = 0
    failed = 0

    # Pre-validation summary
    first_trade = trade_records[0]
    agent_id = getattr(first_trade, "agent_id", "unknown")
    print(f"[Trade Persist] Starting: {len(trade_records)} trades for agent={agent_id}, source={source}")

    for i in range(0, len(trade_records), batch_size):
        batch = trade_records[i : i + batch_size]
        batch_trades = []
        valid_records = []

        # First pass: validate all records in batch
        for record in batch:
            is_valid, error_msg = _validate_trade_record(record)
            if not is_valid:
                print(
                    f"[Trade Persist] SKIP invalid trade: trade_id={getattr(record, 'trade_id', 'N/A')}, "
                    f"agent={getattr(record, 'agent_id', 'N/A')}, error={error_msg}"
                )
                skipped += 1
                continue
            valid_records.append(record)

        # Optionally fetch indicators (disabled by default to avoid DB contention)
        indicators_map = {}
        if fetch_indicators:
            indicator_lookups = []
            for record in valid_records:
                if record.entry_timestamp:
                    indicator_lookups.append((record.asset, record.entry_timestamp))
                if record.exit_timestamp:
                    indicator_lookups.append((record.asset, record.exit_timestamp))
            indicators_map = await fetch_indicators_batch(session, indicator_lookups, timeframe)

        # Second pass: create trade objects with pre-fetched indicators
        for record in valid_records:
            try:
                # Convert TradeRecord dataclass to BacktestTrade SQLModel
                trade = BacktestTrade(
                    trade_id=record.trade_id,
                    source=source,
                    agent_id=record.agent_id,
                    pattern_id=record.pattern_id,
                    # Trade basics - map field names
                    symbol=record.asset,  # TradeRecord uses 'asset', unified uses 'symbol'
                    timeframe=timeframe,
                    side=record.direction,  # TradeRecord uses 'direction', unified uses 'side'
                    # Timestamps
                    entry_timestamp=record.entry_timestamp,
                    exit_timestamp=record.exit_timestamp,
                    # Prices
                    entry_price=record.entry_price,
                    exit_price=record.exit_price,
                    # Position sizing - convert percent to USD estimate
                    position_size_usd=record.position_size_pct * 100 if record.position_size_pct else 0,
                    # PnL - TradeRecord has net pnl_pct (costs already applied)
                    gross_pnl_pct=None,  # Not tracked separately in TradeRecord
                    net_pnl_pct=record.pnl_pct,
                    is_winner=(record.pnl_pct > 0) if record.pnl_pct is not None else None,
                    # MFE/MAE
                    mfe_pct=record.mfe_pct,
                    mae_pct=record.mae_pct,
                    # Decision zone tracking
                    entry_confidence=getattr(record, "entry_confidence", None),
                    decision_zone=getattr(record, "decision_zone", None),
                    ai_consulted=getattr(record, "ai_consulted", None),
                    ai_decision=getattr(record, "ai_decision", None),
                )

                # Attach indicators from batch-fetched map
                if record.entry_timestamp:
                    entry_ts = (
                        record.entry_timestamp / 1000.0
                        if record.entry_timestamp > 10_000_000_000
                        else float(record.entry_timestamp)
                    )
                    trade.entry_indicators = indicators_map.get((record.asset, entry_ts))
                if record.exit_timestamp:
                    exit_ts = (
                        record.exit_timestamp / 1000.0
                        if record.exit_timestamp > 10_000_000_000
                        else float(record.exit_timestamp)
                    )
                    trade.exit_indicators = indicators_map.get((record.asset, exit_ts))

                batch_trades.append(trade)

            except AttributeError as e:
                print(
                    f"[Trade Persist] FAIL missing attribute: trade_id={getattr(record, 'trade_id', 'N/A')}, "
                    f"agent={getattr(record, 'agent_id', 'N/A')}, error={e}"
                )
                failed += 1
                continue
            except Exception as e:
                print(
                    f"[Trade Persist] FAIL creating BacktestTrade: trade_id={getattr(record, 'trade_id', 'N/A')}, "
                    f"agent={getattr(record, 'agent_id', 'N/A')}, error={type(e).__name__}: {e}"
                )
                failed += 1
                continue

        # Add all valid trades from batch
        for trade in batch_trades:
            session.add(trade)
            persisted += 1

        # Flush after each batch with error handling
        try:
            await session.flush()
        except IntegrityError as e:
            # Duplicate key or constraint violation
            print(f"[Trade Persist] INTEGRITY ERROR in batch {i // batch_size + 1}: {e.orig}")
            print(f"[Trade Persist] Rolling back batch. Affected trades: {[t.trade_id for t in batch_trades]}")
            await session.rollback()
            failed += len(batch_trades)
            persisted -= len(batch_trades)
        except DataError as e:
            # Invalid data type or value
            print(f"[Trade Persist] DATA ERROR in batch {i // batch_size + 1}: {e.orig}")
            print(f"[Trade Persist] Check numeric precision. Affected agent: {agent_id}")
            await session.rollback()
            failed += len(batch_trades)
            persisted -= len(batch_trades)
        except OperationalError as e:
            # Database connection or operational issue
            print(f"[Trade Persist] DATABASE ERROR in batch {i // batch_size + 1}: {e.orig}")
            print("[Trade Persist] Database may be unavailable. Stack trace:")
            traceback.print_exc()
            await session.rollback()
            failed += len(batch_trades)
            persisted -= len(batch_trades)
        except Exception as e:
            print(f"[Trade Persist] UNEXPECTED ERROR in batch {i // batch_size + 1}: {type(e).__name__}: {e}")
            traceback.print_exc()
            await session.rollback()
            failed += len(batch_trades)
            persisted -= len(batch_trades)

    # Commit the transaction to persist trades
    try:
        await session.commit()
    except Exception as e:
        print(f"[Trade Persist] COMMIT FAILED for agent={agent_id}: {type(e).__name__}: {e}")
        await session.rollback()
        return 0

    # Summary log
    if skipped > 0 or failed > 0:
        print(
            f"[Trade Persist] SUMMARY for agent={agent_id}: "
            f"persisted={persisted}, skipped={skipped}, failed={failed} of {len(trade_records)} total"
        )
    else:
        print(f"[Trade Persist] SUCCESS: {persisted} trades persisted for agent={agent_id}")

    return persisted


# Backward compatibility alias
persist_trades = persist_backtest_trades


async def get_all_trades(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    agent_id: str | None = None,
    pattern_id: str | None = None,
    symbol: str | None = None,
    source: str | None = None,
):
    """Get trades from unified backtest table."""
    statement = select(BacktestTrade)

    if agent_id:
        statement = statement.where(BacktestTrade.agent_id == agent_id)

    if pattern_id:
        statement = statement.where(BacktestTrade.pattern_id == pattern_id)

    if symbol:
        statement = statement.where(BacktestTrade.symbol == symbol)

    if source:
        statement = statement.where(BacktestTrade.source == source)

    statement = statement.order_by(desc(BacktestTrade.entry_timestamp)).offset(offset).limit(limit)
    result = await session.execute(statement)
    return result.scalars().all()


async def get_trade_by_id(session: AsyncSession, trade_id: str):
    """Get a specific trade by trade_id."""
    statement = select(BacktestTrade).where(BacktestTrade.trade_id == trade_id)
    result = await session.execute(statement)
    return result.scalars().first()


async def get_agent_trade_stats(session: AsyncSession, agent_id: str) -> dict:
    """
    Get aggregate trade statistics for an agent using SQL aggregation.

    Optimized to compute all stats in a single SQL query instead of
    loading all trades into memory.
    """
    # Single aggregation query - no need to load individual trades
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE is_winner = true) as win_count,
                COUNT(*) FILTER (WHERE is_winner = false) as loss_count,
                AVG(net_pnl_pct) as avg_pnl_pct,
                SUM(net_pnl_pct) as total_pnl_pct
            FROM backtest_trades_unified
            WHERE agent_id = :agent_id
        """),
        {"agent_id": agent_id},
    )
    row = result.fetchone()

    if not row or row.total_trades == 0:
        return {
            "agent_id": agent_id,
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": None,
            "avg_pnl_pct": None,
            "total_pnl_pct": None,
        }

    total = row.total_trades
    win_count = row.win_count or 0

    return {
        "agent_id": agent_id,
        "total_trades": total,
        "win_count": win_count,
        "loss_count": row.loss_count or 0,
        "win_rate": win_count / total if total > 0 else None,
        "avg_pnl_pct": round(float(row.avg_pnl_pct), 4) if row.avg_pnl_pct else None,
        "total_pnl_pct": round(float(row.total_pnl_pct), 4) if row.total_pnl_pct else None,
    }
