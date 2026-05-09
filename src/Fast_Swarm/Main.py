# Windows + psycopg3 fix: must use SelectorEventLoop, not ProactorEventLoop
import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# =============================================================================
# OpenTelemetry Tracing Setup
# =============================================================================
# Set OTEL_ENABLED=1 to enable tracing, OTEL_EXPORTER=jaeger for Jaeger export
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "0") == "1"

if OTEL_ENABLED:
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        # Create tracer provider with service name
        resource = Resource.create({"service.name": "fast-swarm"})
        provider = TracerProvider(resource=resource)

        # Choose exporter based on env var
        if os.getenv("OTEL_EXPORTER") == "jaeger":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=os.getenv("OTEL_ENDPOINT", "localhost:4317"))
                print("[OTel] Using OTLP/Jaeger exporter")
            except ImportError:
                exporter = ConsoleSpanExporter()
                print("[OTel] Jaeger exporter not installed, falling back to console")
        else:
            exporter = ConsoleSpanExporter()
            print("[OTel] Using console exporter (set OTEL_EXPORTER=jaeger for Jaeger)")

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        OTEL_TRACER = trace.get_tracer("fast-swarm")
        print("[OTel] Tracing enabled")
    except ImportError as e:
        print(f"[OTel] OpenTelemetry not installed: {e}")
        print("[OTel] Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi")
        OTEL_ENABLED = False
        OTEL_TRACER = None
else:
    OTEL_TRACER = None

from Fast_Swarm.Agents.Hivemind.Routers import governance_router
from Fast_Swarm.Agents.Routers import actions_router, evolution_router

# Import Domain Routers
from Fast_Swarm.Agents.Routers import agent_router as agents_router
from Fast_Swarm.Agents.Services.evolution_service import reset_evolution_flag
from Fast_Swarm.Database import init_db
from Fast_Swarm.Dependencies import data_collector, robustness_service, stream_manager
from Fast_Swarm.Docker import ensure_database
from Fast_Swarm.Evolution.Routers import evolution_router as evolution_monitor_router
from Fast_Swarm.Infrastructure.Routers import exchange_router as exchanges_router
from Fast_Swarm.Infrastructure.Routers import market_data_router, sentiment_router
from Fast_Swarm.Infrastructure.Services.backfill_service import startup_backfill

# Window pool for backtest - pre-generated at startup, refreshed daily
from Fast_Swarm.local_agents.backtest.windows import initialize as init_window_pool
from Fast_Swarm.local_agents.backtest.windows import refresh_and_extend as refresh_window_pool
from Fast_Swarm.Patterns.Routers import pattern_router as patterns_router
from Fast_Swarm.System.Routers import system_router, taskmaster_router
from Fast_Swarm.System.Services.orchestrator import get_orchestrator
from Fast_Swarm.System.Services.taskmaster_service import get_taskmaster, ComponentStatus
from Fast_Swarm.Tests.Router import router as test_runner_router
from Fast_Swarm.Trades.Routers import trade_router as trades_router
from Fast_Swarm.Trading.Routers import trading_router

# =============================================================================
# REMOVED: Separate concurrent loops (evolution_loop, pattern_discovery_loop,
# pattern_backtest_loop) - these caused resource contention.
#
# REPLACED WITH: BacktestOrchestrator - runs phases sequentially:
# 1. Load windows ONCE from pool
# 2. Test batch of patterns on those windows
# 3. Test batch of agents on those SAME windows (reusing preloaded data)
# 4. Run evolution cycle
# 5. Run pattern discovery
# 6. Cooldown, then repeat
#
# P0 (Data Collection) runs independently - never blocked by P2 operations.
# =============================================================================


async def window_pool_refresh_loop():
    """
    Background loop to refresh window pool daily at 3am.

    Checks coverage thresholds and generates new windows only for
    pairs that fall below targets (e.g., when new data is added).
    """
    from datetime import datetime
    from datetime import time as dt_time

    # Wait for initial setup
    await asyncio.sleep(300)  # 5 minutes

    while True:
        try:
            now = datetime.now()
            # Calculate seconds until 3am
            target = datetime.combine(now.date(), dt_time(3, 0))
            if now >= target:
                # Already past 3am today, wait until tomorrow
                target = datetime.combine(now.date() + timedelta(days=1), dt_time(3, 0))

            wait_seconds = (target - now).total_seconds()
            print(f"[Window Pool] Next refresh at 3am ({wait_seconds / 3600:.1f} hours)")
            await asyncio.sleep(wait_seconds)

            # Refresh window pool
            print("[Window Pool] Starting daily refresh...")
            result = await refresh_window_pool()
            print(
                f"[Window Pool] Refresh complete: {result.get('status')}, "
                f"+{result.get('windows_added', 0)} windows, "
                f"pool size: {result.get('pool_size', 0)}"
            )

        except Exception as e:
            print(f"[Window Pool] Error: {e}")
            await asyncio.sleep(3600)  # Retry in 1 hour


async def get_latest_enriched_candle(session, symbol: str, timeframe: str = "1h") -> dict | None:
    """
    Fetch the most recent candle with all indicators computed.

    If the latest candle in DB doesn't have base indicators (rsi_14, ema_21, etc.),
    fetches a window of 250 candles and computes indicators on-the-fly using
    calculate_indicators_fast(). This ensures paper trading always has indicator
    data even for newly-collected candles.

    Args:
        session: AsyncSession
        symbol: e.g., "BTCUSDT" or "BTC"
        timeframe: e.g., "1h", "1m"

    Returns:
        Dict with OHLCV + all indicator columns, or None if not found
    """
    import pandas as pd
    from sqlalchemy import text

    # Normalize symbol (handle both "BTC" and "BTCUSDT" and "BTC-USDT")
    base_symbol = symbol.replace("-", "").replace("USDT", "").replace("USD", "")
    symbol_patterns = [symbol, f"{base_symbol}USDT", f"{base_symbol}-USD", base_symbol]

    # First try: get latest candle and check if it has indicators
    query = text("""
        SELECT * FROM enhanced_candles
        WHERE symbol = ANY(:symbols)
          AND timeframe = :timeframe
        ORDER BY time DESC
        LIMIT 1
    """)

    result = await session.execute(
        query,
        {"symbols": symbol_patterns, "timeframe": timeframe}
    )
    row = result.mappings().first()

    if not row:
        return None

    candle = dict(row)

    # Check if ALL key base indicators are populated (not just a few)
    # Previously, backtest enrichment mapped ATR incorrectly, so atr_14 might be NULL
    key_indicators = ["rsi_14", "ema_21", "atr_14", "adx_14", "macd_line"]
    if all(candle.get(k) is not None for k in key_indicators):
        # All key indicators present - return as-is
        return candle

    # Base indicators missing - fetch window and compute on-the-fly
    window_query = text("""
        SELECT time, open, high, low, close, volume
        FROM enhanced_candles
        WHERE symbol = ANY(:symbols)
          AND timeframe = :timeframe
        ORDER BY time DESC
        LIMIT 250
    """)

    window_result = await session.execute(
        window_query,
        {"symbols": symbol_patterns, "timeframe": timeframe}
    )
    rows = window_result.fetchall()

    if len(rows) < 20:
        # Not enough data to compute indicators
        return candle

    # Build DataFrame (reverse to chronological order)
    df = pd.DataFrame(
        list(reversed(rows)),
        columns=["time", "open", "high", "low", "close", "volume"]
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute indicators
    try:
        from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import calculate_indicators_fast
        df = calculate_indicators_fast(df, verbose=False)

        # Rename columns to match DB column names
        col_renames = {
            "MACD_12_26_9": "macd_line",
            "MACDs_12_26_9": "macd_signal",
            "MACDh_12_26_9": "macd_histogram",
            "BBL_20_2.0": "bb_lower",
            "BBM_20_2.0": "bb_middle",
            "BBU_20_2.0": "bb_upper",
            "BBB_20_2.0": "bb_width",
            "BBP_20_2.0": "bb_percent",
            "STOCHk_14_3_3": "stoch_k",
            "STOCHd_14_3_3": "stoch_d",
            "STOCHRSIk_14_14_3_3": "stochrsi_k",
            "STOCHRSId_14_14_3_3": "stochrsi_d",
            "DMP_14": "plus_di",
            "DMN_14": "minus_di",
            "ATRr_7": "atr_7",
            "ATRr_14": "atr_14",
            "NATR_14": "natr_14",
            "TRUERANGE_14": "true_range",
            "AROONU_14": "aroon_up",
            "AROOND_14": "aroon_down",
            "AROONOSC_14": "aroon_osc",
            "CCI_14": "cci_14",
            "WILLR_14": "willr_14",
            "ROC_10": "roc_10",
            "CMF_20": "cmf_20",
            "MFI_14": "mfi_14",
            "EMV_14": "emv_14",
            "VHF_28": "vhf_28",
            "TRIX_14": "trix",
            "CMO_14": "cmo_14",
        }
        df.columns = [c.lower() if c not in col_renames else c for c in df.columns]
        df.rename(columns={k: v for k, v in col_renames.items() if k in df.columns}, inplace=True)

        # Get the last row (most recent candle with all indicators)
        last_row = df.iloc[-1].to_dict()

        # Merge with original candle data (preserve DB fields like exchange, symbol, timeframe)
        # Filter out NaN values (pandas NaN is not None, need explicit check)
        enriched = {**candle}
        for k, v in last_row.items():
            if k == "time":
                continue
            if v is None:
                continue
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                pass  # Non-numeric values (strings etc.) can't be checked with isna
            enriched[k] = v

        # Also compute derived indicators
        from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import compute_derived_for_candle
        derived = compute_derived_for_candle(enriched)
        enriched.update(derived)

        return enriched

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Paper Trading] On-the-fly indicator computation failed: {e}")
        return candle


async def paper_trading_loop():
    """
    Background loop that evaluates paper trading agents against live market data.

    Runs every 60 seconds (1 candle on 1m timeframe).
    Gets latest enriched candle from DB, evaluates patterns, places trades.

    Note: Bear protection is checked inside evaluate_and_trade() - agents in
    DEFENSIVE mode will have positions force-closed and new entries blocked.
    """
    import logging
    from Fast_Swarm.Database import async_session_maker
    from Fast_Swarm.Trading.Services.agent_paper_trading_service import paper_trading_service

    logger = logging.getLogger(__name__)
    logger.info("[Paper Trading] Starting background trading loop...")

    # Wait for system to stabilize
    await asyncio.sleep(30)

    # Restore sessions from DB (survives container restarts)
    try:
        restore_session = async_session_maker()
        try:
            restored = await paper_trading_service.restore_sessions(restore_session)
            if restored:
                logger.info("[Paper Trading] Restored %d sessions from DB", restored)
        finally:
            await restore_session.close()
    except Exception as e:
        logger.error("[Paper Trading] Session restore failed: %s", e)

    while True:
        try:
            session = async_session_maker()
            try:
                # Get all active paper trading agents
                active_agents = paper_trading_service.get_all_active_agents()
                logger.info(f"[Paper Trading] Cycle: {len(active_agents)} active agents")

                if not active_agents:
                    await asyncio.sleep(60)
                    continue

                # Pre-fetch candle data ONCE per symbol (shared across all agents)
                all_symbols = set()
                for info in active_agents.values():
                    all_symbols.update(info.get("symbols", []))

                candle_cache = {}
                for symbol in all_symbols:
                    try:
                        # Full market snapshot: all TFs + order book + ticks
                        from Fast_Swarm.Infrastructure.Services.market_snapshot_service import collect_market_snapshot
                        candle = await collect_market_snapshot(session, symbol)
                        if candle and candle.get("close"):
                            candle_cache[symbol] = candle
                    except Exception as e:
                        logger.error(f"[Paper Trading] Failed to fetch {symbol}: {e}")

                for agent_id, info in active_agents.items():
                    if info.get("paused", False):
                        continue

                    symbols = info.get("symbols", [])
                    for symbol in symbols:
                        candle = candle_cache.get(symbol)
                        try:

                            if candle is None:
                                logger.debug(f"[Paper Trading] No candle data for {symbol}")
                                continue

                            # Log indicator availability (first iteration only for each symbol)
                            indicator_keys = [k for k in candle if candle[k] is not None and k not in (
                                "time", "exchange", "symbol", "timeframe", "open", "high", "low", "close", "volume"
                            )]
                            logger.debug(f"[Paper Trading] {symbol}: {len(indicator_keys)} indicators available")

                            # Determine regime (from candle or current market)
                            regime = candle.get("regime", "unknown")
                            current_price = candle.get("close", 0.0)

                            if current_price <= 0:
                                continue

                            # Evaluate and potentially trade
                            indicators_count = len([k for k in candle if candle[k] is not None]) - 9  # subtract OHLCV+meta
                            result = await paper_trading_service.evaluate_and_trade(
                                session=session,
                                agent_id=agent_id,
                                symbol=symbol,
                                current_price=current_price,
                                candle_data=candle,
                                regime=regime,
                            )

                            if result:
                                logger.info(f"[Paper Trading] {agent_id[:8]} {symbol}: {result.get('action', 'unknown')} @ ${current_price:.0f} ({indicators_count} indicators)")
                            else:
                                logger.info(f"[Paper Trading] {agent_id[:8]} {symbol}: hold @ ${current_price:.0f} ({indicators_count} ind, regime={regime})")

                        except Exception as e:
                            # Rollback so next agent isn't poisoned by this failure
                            try:
                                await session.rollback()
                            except Exception:
                                pass
                            logger.error(f"[Paper Trading] Error for {agent_id[:8]}/{symbol}: {e}")
            finally:
                await session.close()

        except Exception as e:
            logger.error(f"[Paper Trading] Loop error: {e}")

        # Run every 15 seconds — evaluate on 1m candles for fast signals
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Ensure Docker and PostgreSQL are running
    print("Starting up CoinSwarm FastAPI...")
    await ensure_database()

    # 1. Startup: Initialize Database
    await init_db()

    # 1.1. Reset evolution global flag (prevents stuck flag after crash)
    reset_evolution_flag()
    print("[Startup] Evolution flag reset (prevents stuck flag after crash)")

    # 1.5. Initialize window pool for backtesting (queries DB for data ranges)
    try:
        await init_window_pool(seed=42)
    except Exception as e:
        print(f"[Startup] WARNING: Window pool init failed: {e}")
        print("[Startup] Backtests will fail until window pool is initialized")

    # 2. Configure symbols
    symbols = {"binance": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "coinbase": ["BTC-USD", "ETH-USD"]}

    # 3. Start Data Collection
    # Link events to collector
    stream_manager.on_trade(data_collector.handle_live_trade)
    stream_manager.on_kline(data_collector.handle_live_kline)
    stream_manager.on_order_book(data_collector.handle_order_book)

    # First: Live Stream
    await stream_manager.start(symbols)

    # Second: Health Check & Backfill
    await data_collector.verify_and_backfill(symbols)

    # Third: Start historical OHLCV backfill in background
    # This fills gaps in BTC/ETH/SOL data for backtesting
    asyncio.create_task(startup_backfill())

    # 4. Robustness Chaos Loop (disabled - runs random EDD tests periodically)
    # robustness_service.register_test(data_collector._flush_batches)
    # robustness_service.register_test(robustness_service.validate_economic_assumptions)
    # asyncio.create_task(robustness_service.start_chaos_loop())

    # 5. Start Backtest Orchestrator (P2 - sequential pipeline)
    # This replaces the old concurrent loops (evolution_loop, pattern_discovery_loop,
    # pattern_backtest_loop) which caused resource contention.
    #
    # Priority System:
    # - P0: Data collection (above) - runs independently, never blocked
    # - P1: Live trades - not implemented yet
    # - P2: Backtesting/Evolution - handled by orchestrator sequentially
    print("[Startup] Starting backtest orchestrator (P2 sequential pipeline)...")
    orchestrator = get_orchestrator()
    await orchestrator.start()

    # 6. Start Taskmaster (monitors system health, pokes stalled components)
    print("[Startup] Starting Taskmaster monitoring...")
    taskmaster = get_taskmaster()

    # Register the orchestrator as a monitored component
    def orchestrator_health_check():
        """Health check function for the orchestrator."""
        orch = get_orchestrator()
        return {
            "status": ComponentStatus.HEALTHY if orch._running else ComponentStatus.STALLED,
            "last_active_at": orch.state.last_cycle_at,
            "metadata": {
                "current_phase": orch.state.phase.value,
                "cycles_completed": orch.state.cycles_completed,
                "is_running": orch._running,
            }
        }

    taskmaster.register_component(
        component_id="orchestrator",
        name="Backtest Orchestrator",
        health_check=orchestrator_health_check
    )

    await taskmaster.start_monitoring()

    # 7. Start Window Pool Refresh Loop (daily at 3am, low impact)
    print("[Startup] Starting window pool refresh loop...")
    asyncio.create_task(window_pool_refresh_loop())

    # 8. Start Paper Trading Loop (evaluates agents every 60s)
    print("[Startup] Starting paper trading loop...")
    asyncio.create_task(paper_trading_loop())

    # 9. Start Sentiment Collector (Fear & Greed backfill + 4h refresh)
    print("[Startup] Starting sentiment collector...")
    from Fast_Swarm.Infrastructure.Services.sentiment_collector import sentiment_collector_loop
    asyncio.create_task(sentiment_collector_loop())

    yield

    # Shutdown logic
    print("Shutting down...")

    # Stop taskmaster first (stops monitoring)
    await taskmaster.stop_monitoring()

    # Stop orchestrator (graceful shutdown of P2 operations)
    await orchestrator.stop()

    await stream_manager.stop()
    await data_collector.flush_all()  # Flush all pending data
    await robustness_service.stop()


app = FastAPI(
    title="CoinSwarm FastAPI",
    description="FastAPI wrapper for Coinswarm trading system",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Don't redirect /patterns to /patterns/ (breaks dashboard fetch)
)

# Instrument FastAPI with OpenTelemetry (must be after app creation)
if OTEL_ENABLED:
    try:
        FastAPIInstrumentor.instrument_app(app)
        print("[OTel] FastAPI instrumentation active")
    except Exception as e:
        print(f"[OTel] FastAPI instrumentation failed: {e}")

# Add CORS middleware for dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(agents_router.router)
app.include_router(evolution_router.router)
app.include_router(actions_router.router)
app.include_router(patterns_router.router)
app.include_router(trades_router.router)
app.include_router(trading_router.router)
app.include_router(evolution_monitor_router.router)
app.include_router(governance_router.router)
app.include_router(market_data_router.router)
app.include_router(exchanges_router.router)
app.include_router(sentiment_router.router)
app.include_router(system_router.router)
app.include_router(taskmaster_router.router)
app.include_router(test_runner_router.router)

# Mount static files for dashboard
DASHBOARD_DIR = Path(__file__).parent / "Dashboard"
app.mount("/dashboard/css", StaticFiles(directory=DASHBOARD_DIR / "css"), name="css")
app.mount("/dashboard/js", StaticFiles(directory=DASHBOARD_DIR / "js"), name="js")


@app.get("/", tags=["System"])
async def root():
    return {"message": "CoinSwarm API is running", "status": "active"}


@app.get("/dashboard", tags=["Dashboard"])
async def dashboard():
    """Serve the main dashboard."""
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/dashboard/", tags=["Dashboard"])
async def dashboard_slash():
    """Serve the main dashboard (with trailing slash)."""
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/dashboard/evolution", tags=["Dashboard"])
async def evolution_dashboard():
    """Serve the evolution progress dashboard."""
    return FileResponse(DASHBOARD_DIR / "evolution.html")
