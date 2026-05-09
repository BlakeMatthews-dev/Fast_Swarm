"""
Updated logging_config for Fast_Swarm using PostgreSQL instead of SQLite.

This is a modified version of the Coinswarm logging config adapted for:
- PostgreSQL backend instead of SQLite
- Async database operations (psycopg async)
- Integration with Fast_Swarm's existing database setup

Key changes:
1. SQLiteCriticalEventHandler -> PostgresCriticalEventHandler
2. Uses psycopg3 (async) for non-blocking I/O
3. Database setup via environment variables (matching Database.py)
4. Automatic table creation on first use
"""

import asyncio
import json
import logging
import logging.handlers
import os
import shutil
import sys
import threading
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg import AsyncConnection

    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

# Runtime-configurable environment overrides
# LOG_DIR: directory for file logs
# LOG_LEVEL: overall default log level
# LOG_CONSOLE_LEVEL: console handler level
# LOG_RETENTION_DAYS: file retention days
# ENABLE_POSTGRES_LOGGING: enable/disable Postgres handler (1/0)
LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).parent.resolve() / "logs")))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", os.getenv("LOG_RETENTION_DAYS", "90")))
LOG_LEVEL = os.getenv("LOG_LEVEL", None)
if LOG_LEVEL:
    try:
        LOG_LEVEL = int(LOG_LEVEL)
    except ValueError:
        LOG_LEVEL = getattr(logging, LOG_LEVEL.upper(), logging.DEBUG)
else:
    LOG_LEVEL = logging.DEBUG

LOG_CONSOLE_LEVEL = os.getenv("LOG_CONSOLE_LEVEL", None)
if LOG_CONSOLE_LEVEL:
    try:
        LOG_CONSOLE_LEVEL = int(LOG_CONSOLE_LEVEL)
    except ValueError:
        LOG_CONSOLE_LEVEL = getattr(logging, LOG_CONSOLE_LEVEL.upper(), logging.INFO)
else:
    LOG_CONSOLE_LEVEL = logging.INFO

ENABLE_POSTGRES_LOGGING = os.getenv("ENABLE_POSTGRES_LOGGING", "1") in ("1", "true", "True")


# =============================================================================
# WINDOWS-SAFE ROTATING FILE HANDLER
# =============================================================================


class WindowsSafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    RotatingFileHandler that gracefully handles Windows file locking issues.

    On Windows, files cannot be renamed while open by another process.
    This handler catches PermissionError during rotation and:
    1. Logs a warning instead of crashing
    2. Continues writing to the current file
    3. Retries rotation on next emit
    """

    def doRollover(self):
        """Perform rollover with Windows-safe error handling."""
        try:
            super().doRollover()
        except PermissionError:
            # File is locked by another process - skip rotation this time
            pass
        except OSError as e:
            # Other OS errors - log once and continue
            if not getattr(self, "_rotation_warned", False):
                self._rotation_warned = True
                print(f"[WARNING] Log rotation failed: {e}", file=sys.stderr)


# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Directory paths
SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_LOG_DIR = SCRIPT_DIR / "logs"

# Rotation settings
LOG_MAX_BYTES = 100 * 1024 * 1024  # 100 MB per file
LOG_BACKUP_COUNT = 20  # Keep 20 rotated files (~2 GB per module)

# PostgreSQL retention - 90 days
POSTGRES_RETENTION_DAYS = 90

# Default log levels
DEFAULT_LOG_LEVEL = logging.DEBUG
DEFAULT_CONSOLE_LEVEL = logging.INFO

# PostgreSQL connection settings
POSTGRES_USER = os.getenv("POSTGRES_USER", "coinswarm")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
POSTGRES_DB = os.getenv("POSTGRES_DB", "coinswarm")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

POSTGRES_CONN_STRING = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Critical event types
CRITICAL_EVENT_TYPES = frozenset(
    [
        # Trading events
        "trade_executed",
        "trade_failed",
        "order_placed",
        "order_filled",
        "order_rejected",
        "order_cancelled",
        "position_opened",
        "position_closed",
        "position_modified",
        # Risk events
        "risk_alert",
        "risk_check_failed",
        "circuit_breaker",
        "stop_loss_triggered",
        "take_profit_triggered",
        "max_drawdown_exceeded",
        # Decision events
        "pattern_decision",
        "committee_vote",
        "agent_selection",
        "signal_generated",
        # System events
        "api_error",
        "connection_lost",
        "connection_restored",
        "data_corruption",
        "data_gap_detected",
        "rate_limit_hit",
        # Wallet/signing events
        "wallet_operation",
        "signature_created",
        "signature_failed",
    ]
)


# =============================================================================
# JSON STRUCTURED FORMATTER
# =============================================================================


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging output."""

    RESERVED_ATTRS = frozenset(
        {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "message",
            "asctime",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Extract extra fields
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)

        if extra_fields:
            log_entry["extra"] = extra_fields

        # Add exception information if present
        if record.exc_info and record.exc_info[0] is not None:
            exception_type = record.exc_info[0]
            exception_value = record.exc_info[1]
            log_entry["exception"] = {
                "type": exception_type.__name__ if exception_type else None,
                "message": str(exception_value) if exception_value else None,
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str, ensure_ascii=False)


# =============================================================================
# CONSOLE FORMATTER WITH COLORS
# =============================================================================


class ColoredConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with ANSI color codes."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35;1m",  # Magenta bold
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a human-readable string."""
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        level = record.levelname
        if self.use_colors and level in self.COLORS:
            level_display = f"{self.COLORS[level]}{level}{self.RESET}"
        else:
            level_display = level

        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in StructuredJSONFormatter.RESERVED_ATTRS and not key.startswith("_"):
                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                extra_parts.append(f"{key}={value_str}")

        extra_str = ""
        if extra_parts:
            extra_str = f" {{{', '.join(extra_parts)}}}"

        message = f"[{timestamp}] [{level_display}] {record.name}: {record.getMessage()}{extra_str}"

        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"

        return message


# =============================================================================
# POSTGRESQL HANDLER FOR CRITICAL EVENTS
# =============================================================================


class PostgresCriticalEventHandler(logging.Handler):
    """
    Handler that writes critical events to PostgreSQL database.

    Captures:
    1. All log records at ERROR level or above
    2. Any log record with event_type in CRITICAL_EVENT_TYPES

    This implementation uses the application's async database engine if available
    (from Fast_Swarm.Database) and falls back to psycopg.AsyncConnection when needed.
    It also implements a synchronous fallback when no event loop is running.
    """

    def __init__(self, level: int = logging.WARNING, max_retries: int = 3):
        """Initialize the PostgreSQL handler."""
        super().__init__(level=level)
        self._initialized = False
        self._init_task = None
        self._max_retries = max_retries

    async def _initialize_table(self) -> None:
        """Create the critical_events table if it doesn't exist."""
        try:
            # Prefer using the project's async engine if available
            from Fast_Swarm.Database import engine as fastswarm_engine

            async with fastswarm_engine.begin() as conn:
                await conn.run_sync(self._create_table)
                self._initialized = True
                return
        except Exception:
            # Fall back to psycopg if installed
            pass

        if not PSYCOPG_AVAILABLE:
            sys.stderr.write("[PostgresCriticalEventHandler] No DB engine or psycopg available for table init\n")
            return

        try:
            async with await psycopg.AsyncConnection.connect(POSTGRES_CONN_STRING) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS critical_events (
                        id SERIAL PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        logger TEXT NOT NULL,
                        message TEXT NOT NULL,
                        event_type TEXT,
                        asset TEXT,
                        pattern_id TEXT,
                        trade_id TEXT,
                        order_id TEXT,
                        error_type TEXT,
                        error_message TEXT,
                        traceback TEXT,
                        extra_json JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # Create indexes
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_critical_events_timestamp ON critical_events(timestamp)"
                )
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_critical_events_level ON critical_events(level)")
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_critical_events_event_type ON critical_events(event_type)"
                )
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_critical_events_asset ON critical_events(asset)")
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_critical_events_created_at ON critical_events(created_at)"
                )

                self._initialized = True
        except Exception as e:
            sys.stderr.write(f"[PostgresCriticalEventHandler] Failed to initialize table: {e}\n")

    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record to PostgreSQL."""
        if not PSYCOPG_AVAILABLE:
            return

        try:
            # Check if should be written
            event_type = getattr(record, "event_type", None)
            is_critical_event_type = event_type in CRITICAL_EVENT_TYPES
            is_error_or_above = record.levelno >= logging.ERROR

            if not (is_critical_event_type or is_error_or_above):
                return

            # Extract fields
            asset = getattr(record, "asset", None) or getattr(record, "asset_symbol", None)
            pattern_id = getattr(record, "pattern_id", None)
            trade_id = getattr(record, "trade_id", None)
            order_id = getattr(record, "order_id", None) or getattr(record, "order_id_local", None)

            # Exception info
            error_type = None
            error_message = None
            traceback_str = None
            if record.exc_info and record.exc_info[0] is not None:
                error_type = record.exc_info[0].__name__
                error_message = str(record.exc_info[1]) if record.exc_info[1] else None
                traceback_str = "".join(traceback.format_exception(*record.exc_info))

            # Extra fields as JSON
            extra_json_dict = {}
            skip_fields = {
                "event_type",
                "asset",
                "asset_symbol",
                "pattern_id",
                "trade_id",
                "order_id",
                "order_id_local",
            }
            for key, value in record.__dict__.items():
                if key not in StructuredJSONFormatter.RESERVED_ATTRS and not key.startswith("_"):
                    if key not in skip_fields:
                        try:
                            json.dumps(value)
                            extra_json_dict[key] = value
                        except (TypeError, ValueError):
                            extra_json_dict[key] = str(value)

            extra_json = extra_json_dict if extra_json_dict else None

            # Schedule async insert
            self._schedule_insert(
                timestamp=datetime.now(UTC).isoformat(),
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
                event_type=event_type,
                asset=asset,
                pattern_id=pattern_id,
                trade_id=trade_id,
                order_id=order_id,
                error_type=error_type,
                error_message=error_message,
                traceback=traceback_str,
                extra_json=extra_json,
            )

        except Exception as e:
            sys.stderr.write(f"[PostgresCriticalEventHandler] emit() failed: {e}\n")

    def _schedule_insert(self, **fields) -> None:
        """Schedule an async insert (non-blocking)."""
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, use asyncio.run
            try:
                asyncio.run(self._async_insert(**fields))
            except Exception as e:
                sys.stderr.write(f"[PostgresCriticalEventHandler] Failed to insert: {e}\n")
            return

        # Schedule as task
        asyncio.create_task(self._async_insert(**fields))

    async def _async_insert(self, **fields) -> None:
        """Async insert into PostgreSQL using project's engine or psycopg fallback with retries."""
        # Ensure table exists
        if not self._initialized:
            await self._initialize_table()

        # Try to use project's engine first (async SQLAlchemy/SQLModel engine)
        try:
            from Fast_Swarm.Database import async_session_maker

            async with async_session_maker() as session:
                # Use raw SQL to avoid model dependencies
                for attempt in range(1, self._max_retries + 1):
                    try:
                        await session.execute(
                            """
                            INSERT INTO critical_events (
                                timestamp, level, logger, message, event_type,
                                asset, pattern_id, trade_id, order_id,
                                error_type, error_message, traceback, extra_json
                            ) VALUES (:timestamp, :level, :logger, :message, :event_type,
                                      :asset, :pattern_id, :trade_id, :order_id,
                                      :error_type, :error_message, :traceback, :extra_json)
                            """,
                            {
                                "timestamp": fields["timestamp"],
                                "level": fields["level"],
                                "logger": fields["logger"],
                                "message": fields["message"],
                                "event_type": fields["event_type"],
                                "asset": fields["asset"],
                                "pattern_id": fields["pattern_id"],
                                "trade_id": fields["trade_id"],
                                "order_id": fields["order_id"],
                                "error_type": fields["error_type"],
                                "error_message": fields["error_message"],
                                "traceback": fields["traceback"],
                                "extra_json": json.dumps(fields["extra_json"]) if fields["extra_json"] else None,
                            },
                        )
                        await session.commit()
                        return
                    except Exception:
                        if attempt >= self._max_retries:
                            raise
                        await asyncio.sleep(min(2**attempt, 5))
        except Exception:
            # Fall back to psycopg if available
            pass

        if not PSYCOPG_AVAILABLE:
            # Nothing else we can do
            return

        # psycopg fallback
        for attempt in range(1, self._max_retries + 1):
            try:
                async with await psycopg.AsyncConnection.connect(POSTGRES_CONN_STRING) as conn:
                    await conn.execute(
                        """
                        INSERT INTO critical_events (
                            timestamp, level, logger, message, event_type,
                            asset, pattern_id, trade_id, order_id,
                            error_type, error_message, traceback, extra_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            fields["timestamp"],
                            fields["level"],
                            fields["logger"],
                            fields["message"],
                            fields["event_type"],
                            fields["asset"],
                            fields["pattern_id"],
                            fields["trade_id"],
                            fields["order_id"],
                            fields["error_type"],
                            fields["error_message"],
                            fields["traceback"],
                            json.dumps(fields["extra_json"]) if fields["extra_json"] else None,
                        ),
                    )
                    return
            except Exception as e:
                if attempt >= self._max_retries:
                    sys.stderr.write(f"[PostgresCriticalEventHandler] _async_insert failed after retries: {e}\n")
                else:
                    await asyncio.sleep(min(2**attempt, 5))


# =============================================================================
# LOGGER FACTORY
# =============================================================================

# Thread-safe logger cache
_loggers: dict[str, logging.Logger] = {}
_loggers_lock = threading.Lock()


def _ensure_directories_exist() -> None:
    """Ensure the logs directory exists (configurable via LOG_DIR)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_old_file_logs(days: int | None = None) -> int:
    """Delete log files older than `days` from LOG_DIR. Returns number deleted."""
    days = days if days is not None else LOG_RETENTION_DAYS
    cutoff = datetime.now().timestamp() - (days * 24 * 3600)
    deleted = 0

    if not LOG_DIR.exists():
        return 0

    for path in LOG_DIR.iterdir():
        try:
            if path.is_file():
                mtime = path.stat().st_mtime
                if mtime < cutoff:
                    path.unlink()
                    deleted += 1
            elif path.is_dir() and path.name.endswith(".log"):  # defensive
                # remove directory if empty
                try:
                    shutil.rmtree(path)
                    deleted += 1
                except Exception:
                    pass
        except Exception:
            pass

    return deleted


def _create_file_handler(log_name: str) -> logging.Handler:
    """Create a rotating file handler for JSON log output."""
    log_file = LOG_DIR / f"{log_name}.jsonl"

    handler = WindowsSafeRotatingFileHandler(
        filename=str(log_file),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    # File logs should capture everything; level can be adjusted via LOG_LEVEL env
    handler.setLevel(LOG_LEVEL)
    handler.setFormatter(StructuredJSONFormatter())

    return handler


def _create_console_handler() -> logging.Handler:
    """Create a console handler for human-readable output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(LOG_CONSOLE_LEVEL)
    handler.setFormatter(ColoredConsoleFormatter())

    return handler


def _create_postgres_handler() -> logging.Handler:
    """Create a PostgreSQL handler for critical events."""
    return PostgresCriticalEventHandler()


def get_logger(
    name: str,
    level: int | None = None,
    console_level: int | None = None,
    enable_postgres: bool = True,
    enable_file: bool = True,
    enable_console: bool = True,
) -> logging.Logger:
    """
    Get a configured logger instance (thread-safe cache).

    Args:
        name: Logger name, typically __name__
        level: Overall logger level (overrides LOG_LEVEL env)
        console_level: Console output level (overrides LOG_CONSOLE_LEVEL env)
        enable_postgres: Enable PostgreSQL handler
        enable_file: Enable file handler
        enable_console: Enable console handler

    Returns:
        Configured logging.Logger instance
    """
    with _loggers_lock:
        if name in _loggers:
            return _loggers[name]

        _ensure_directories_exist()

        logger = logging.getLogger(name)
        logger.setLevel(level if level is not None else LOG_LEVEL)
        logger.propagate = False

        logger.handlers = []

        # Determine log file name
        if "." in name:
            log_file_name = name.split(".")[0]
        else:
            log_file_name = name

        # Add handlers
        if enable_file:
            logger.addHandler(_create_file_handler(log_file_name))

        if enable_console:
            console_handler = _create_console_handler()
            console_handler.setLevel(console_level if console_level is not None else LOG_CONSOLE_LEVEL)
            logger.addHandler(console_handler)

        if enable_postgres and ENABLE_POSTGRES_LOGGING:
            # Only add postgres handler if enabled in env and psycopg or project engine present
            logger.addHandler(_create_postgres_handler())

        _loggers[name] = logger

        return logger


# =============================================================================
# CONTEXT TEMPLATES (same as original)
# =============================================================================


class LogContext:
    """Pre-defined logging context templates."""

    FUNC_ENTRY = {"event": "function_entry", "function_name": None}
    FUNC_EXIT = {"event": "function_exit", "function_name": None, "execution_time_ms": None}

    ORDER_PLACEMENT = {
        "event_type": "order_placed",
        "asset": None,
        "side": None,
        "order_type": None,
        "size": None,
        "price": None,
        "order_id": None,
    }

    ORDER_FILLED = {
        "event_type": "order_filled",
        "asset": None,
        "order_id": None,
        "exchange_id": None,
        "fill_price": None,
        "fill_size": None,
        "slippage_bps": None,
        "time_to_fill_ms": None,
    }

    TRADE_EXECUTED = {
        "event_type": "trade_executed",
        "asset": None,
        "trade_id": None,
        "side": None,
        "size": None,
        "price": None,
        "fee": None,
        "pnl": None,
    }

    WS_CONNECTED = {
        "event_type": "ws_connected",
        "exchange": None,
        "url": None,
        "channels": None,
        "symbols": None,
    }

    WS_DISCONNECTED = {
        "event_type": "ws_disconnected",
        "exchange": None,
        "reason": None,
        "action": None,
        "delay": None,
        "attempt": None,
    }

    API_ERROR = {
        "event_type": "api_error",
        "endpoint": None,
        "status_code": None,
        "error_type": None,
        "error_msg": None,
    }

    EXCEPTION = {
        "event": "exception",
        "function_name": None,
        "operation": None,
        "error_type": None,
        "error_msg": None,
        "recovery": None,
    }

    DATA_FETCH = {
        "event": "data_fetch",
        "source": None,
        "asset": None,
        "timeframe": None,
        "count": None,
    }


def ctx(template: dict, **values) -> dict:
    """Fill a context template with runtime values."""
    result = {}

    field_expansions = {
        "asset": "asset_symbol",
    }

    for key, default_value in template.items():
        if default_value is not None:
            result[key] = default_value

    for key, value in values.items():
        if value is not None:
            expanded_key = field_expansions.get(key, key)
            result[expanded_key] = value

    return result


def ctx_exception(e: Exception, function_name: str = None, operation: str = None, recovery: str = None) -> dict:
    """Create exception context from an Exception object."""
    return ctx(
        LogContext.EXCEPTION,
        function_name=function_name,
        operation=operation,
        error_type=type(e).__name__,
        error_msg=str(e),
        recovery=recovery,
    )


# =============================================================================
# QUERY UTILITIES FOR POSTGRES
# =============================================================================


async def query_critical_events_async(
    event_type: str | None = None,
    level: str | None = None,
    asset: str | None = None,
    pattern_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query critical events from PostgreSQL (async)."""
    if not PSYCOPG_AVAILABLE:
        return []

    conditions = []
    params = []

    if event_type:
        conditions.append("event_type = %s")
        params.append(event_type)

    if level:
        conditions.append("level = %s")
        params.append(level)

    if asset:
        conditions.append("asset = %s")
        params.append(asset)

    if pattern_id:
        conditions.append("pattern_id = %s")
        params.append(pattern_id)

    if start_time:
        conditions.append("timestamp >= %s")
        params.append(start_time.isoformat())

    if end_time:
        conditions.append("timestamp <= %s")
        params.append(end_time.isoformat())

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.extend([limit, offset])

    try:
        async with await psycopg.AsyncConnection.connect(POSTGRES_CONN_STRING) as conn:
            # Note: where_clause is safe - built from hardcoded column names only
            cursor = await conn.execute(  # nosec B608
                f"""
                SELECT * FROM critical_events
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        sys.stderr.write(f"[query_critical_events_async] Failed: {e}\n")
        return []


async def cleanup_old_events_async(days: int = POSTGRES_RETENTION_DAYS) -> int:
    """Remove events older than specified number of days (async)."""
    if not PSYCOPG_AVAILABLE:
        return 0

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    try:
        async with await psycopg.AsyncConnection.connect(POSTGRES_CONN_STRING) as conn:
            cursor = await conn.execute(
                "DELETE FROM critical_events WHERE timestamp < %s",
                (cutoff,),
            )
            return cursor.rowcount
    except Exception as e:
        sys.stderr.write(f"[cleanup_old_events_async] Failed: {e}\n")
        return 0


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

if not PSYCOPG_AVAILABLE:
    print("[WARNING] psycopg[binary] not installed - PostgreSQL logging disabled", file=sys.stderr)

# Ensure directories exist at import time
_ensure_directories_exist()

# Schedule periodic cleanup of old logs (run once at startup)
try:
    deleted = cleanup_old_file_logs()
    if deleted:
        print(f"[INFO] Cleaned up {deleted} old log files", file=sys.stderr)
except Exception:
    pass
