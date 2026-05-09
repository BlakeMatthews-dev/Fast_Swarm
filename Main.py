# Windows + psycopg3 fix: must use SelectorEventLoop, not ProactorEventLoop
import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from Fast_Swarm.Agents.Hivemind.Routers import governance_router
from Fast_Swarm.Agents.Models.agent_models import EvolutionRunRequest
from Fast_Swarm.Agents.Routers import actions_router, evolution_router

# Import Domain Routers
from Fast_Swarm.Agents.Routers import agent_router as agents_router
from Fast_Swarm.Agents.Services.evolution_service import get_evolution_status, trigger_evolution
from Fast_Swarm.Database import async_session_maker, init_db
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
from Fast_Swarm.Patterns.Services.discovery_service import PatternDiscoveryService
from Fast_Swarm.System.Routers import system_router
from Fast_Swarm.Tests.Router import router as test_runner_router
from Fast_Swarm.Trades.Routers import trade_router as trades_router


async def evolution_loop():
    """
    Background evolution loop - runs continuously after startup.

    - Waits 60 seconds for data backfill to progress
    - Runs evolution with 5 generations per cycle
    - Waits 5 minutes between cycles
    """

    # Wait for initial backfill to progress
    print("[Evolution Loop] Waiting 60 seconds for data backfill...")
    await asyncio.sleep(60)

    while True:
        try:
            status = get_evolution_status()
            if status["is_running"]:
                print("[Evolution Loop] Evolution already running, waiting...")
                await asyncio.sleep(60)
                continue

            print("[Evolution Loop] Starting evolution cycle (5 generations)...")

            # Create a mock BackgroundTasks (we're already in background)
            class MockBackgroundTasks:
                def add_task(self, func, **kwargs):
                    asyncio.create_task(func(**kwargs))

            request = EvolutionRunRequest(
                generations=5,
                population_size=500,
                elite_percent=0.20,
                survival_percent=0.60,
                mutation_rate=0.15,
                assets=["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE"],
                timeframe="1h",  # Primary timeframe for evolution cycle
            )

            result = await trigger_evolution(MockBackgroundTasks(), request)
            print(f"[Evolution Loop] {result.get('message', 'Started')}")

            # Wait for evolution to complete + 2 minute cooldown
            while get_evolution_status()["is_running"]:
                await asyncio.sleep(30)

            print("[Evolution Loop] Cycle complete. Waiting 2 minutes before next cycle...")
            await asyncio.sleep(120)  # 2 minutes between cycles

        except Exception as e:
            print(f"[Evolution Loop] Error: {e}")
            await asyncio.sleep(60)


async def pattern_discovery_loop():
    """
    Background pattern discovery loop - creates new patterns periodically.

    - Waits 5 minutes for initial data to be available
    - Runs discovery cycle every 6 hours
    - Creates new patterns using ML feature extraction + LLM generation
    """
    print("[Pattern Discovery] Waiting 5 minutes for initial data...")
    await asyncio.sleep(300)  # 5 minutes

    discovery_service = PatternDiscoveryService()

    while True:
        try:
            print("[Pattern Discovery] Starting discovery cycle...")
            async with async_session_maker() as session:
                result = await discovery_service.run_discovery_cycle(session)
                print(f"[Pattern Discovery] Created {result.get('patterns_created', 0)} new patterns")

            # Run every 6 hours
            print("[Pattern Discovery] Sleeping 6 hours until next cycle...")
            await asyncio.sleep(6 * 60 * 60)

        except Exception as e:
            print(f"[Pattern Discovery] Error: {e}")
            await asyncio.sleep(300)  # Retry in 5 minutes


async def pattern_backtest_loop():
    """
    Background pattern backtesting loop - tests patterns continuously.

    Every 3rd cycle also runs regime backtest (canonical crash/bull/bear periods).
    """
    print("[Pattern Backtest] Waiting 2 minutes for data backfill...")
    await asyncio.sleep(120)

    discovery_service = PatternDiscoveryService()
    from sqlmodel import select

    from Fast_Swarm.Patterns.Models.pattern_models import Pattern
    from Fast_Swarm.Patterns.Services.backtest_service import PatternBacktestService

    regime_backtest_service = PatternBacktestService()
    cycle_count = 0

    while True:
        try:
            cycle_count += 1
            print("[Pattern Backtest] Running batch backtest...")
            async with async_session_maker() as session:
                result = await discovery_service.run_batch_backtest(session, batch_size=50)
                tested = result.get("patterns_tested", 0)
                promotions = result.get("tier_promotions", {})
                print(
                    f"[Pattern Backtest] Tested {tested} patterns, "
                    f"promotions: T1={promotions.get('to_tier_1', 0)}, T2={promotions.get('to_tier_2', 0)}"
                )

            if cycle_count % 3 == 0:
                print("[Pattern Backtest] Running regime backtest...")
                async with async_session_maker() as session:
                    result = await session.exec(
                        select(Pattern)
                        .where(Pattern.is_active == True)
                        .where(Pattern.fitness_by_regime == {})
                        .limit(20)
                    )
                    patterns = result.all()
                    if patterns:
                        ids = [p.pattern_id for p in patterns]
                        await regime_backtest_service.backtest_patterns_by_regime(session, ids)
                        print(f"[Pattern Backtest] Regime tested {len(ids)} patterns")

            await asyncio.sleep(600)

        except Exception as e:
            print(f"[Pattern Backtest] Error: {e}")
            await asyncio.sleep(120)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Ensure Docker and PostgreSQL are running
    print("Starting up CoinSwarm FastAPI...")
    await ensure_database()

    # 1. Startup: Initialize Database
    await init_db()

    # 1.1. Reset evolution global flag (prevents stuck flag after crash)
    from Fast_Swarm.Agents.Services.evolution_service import reset_evolution_flag

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

    # FIX: Track background tasks for proper cancellation on shutdown (LEAK-001)
    background_tasks: list[asyncio.Task] = []

    # Third: Start historical OHLCV backfill in background
    # This fills gaps in BTC/ETH/SOL data for backtesting
    background_tasks.append(asyncio.create_task(startup_backfill(), name="startup_backfill"))

    # 4. Start Robustness Chaos Loop
    robustness_service.register_test(data_collector._flush_batches)
    robustness_service.register_test(robustness_service.validate_economic_assumptions)  # EDD Tests
    background_tasks.append(asyncio.create_task(robustness_service.start_chaos_loop(), name="chaos_loop"))

    # 5. Start Evolution Loop (continuous background evolution)
    print("[Startup] Starting evolution loop...")
    background_tasks.append(asyncio.create_task(evolution_loop(), name="evolution_loop"))

    # 6. Start Pattern Discovery Loop (creates new patterns every 6 hours)
    print("[Startup] Starting pattern discovery loop...")
    background_tasks.append(asyncio.create_task(pattern_discovery_loop(), name="pattern_discovery"))

    # 7. Start Pattern Backtest Loop (tests patterns every 10 minutes)
    print("[Startup] Starting pattern backtest loop...")
    background_tasks.append(asyncio.create_task(pattern_backtest_loop(), name="pattern_backtest"))

    # 8. Start Window Pool Refresh Loop (maintains coverage as data grows)
    print("[Startup] Starting window pool refresh loop...")
    background_tasks.append(asyncio.create_task(window_pool_refresh_loop(), name="window_refresh"))

    yield

    # Shutdown logic - FIX: Cancel all background tasks properly (LEAK-001)
    print("Shutting down...")
    for task in background_tasks:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass  # Expected during shutdown
    await stream_manager.stop()
    await data_collector.flush_all()  # Flush all pending data
    await robustness_service.stop()


app = FastAPI(
    title="CoinSwarm FastAPI",
    description="FastAPI wrapper for Coinswarm trading system",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware for dashboard access
# FIX: Don't combine wildcard origins with credentials (SEC-001)
# Either use specific origins with credentials, or wildcard without credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"],
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
app.include_router(evolution_monitor_router.router)
app.include_router(governance_router.router)
app.include_router(market_data_router.router)
app.include_router(exchanges_router.router)
app.include_router(sentiment_router.router)
app.include_router(system_router.router)
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
