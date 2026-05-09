# Fast_Swarm Exchange Integration

**Exchanges**: Binance, Coinbase, dYdX, Hyperliquid
**Protocol**: WebSocket for real-time data
**Storage**: PostgreSQL (candles, tickers, trades)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     StreamManager                            │
│              (stream_manager_service.py)                     │
│  Orchestrates all exchange connections                       │
├─────────────────────────────────────────────────────────────┤
│                    Event Handlers                            │
│  on_trade()  │  on_kline()  │  on_order_book()              │
└──────┬───────────────┬───────────────┬──────────────────────┘
       │               │               │
       ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                    DataCollector                             │
│               (collector_service.py)                         │
│  Batches and writes to database                              │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                     PostgreSQL                               │
│     candles  │  tickers  │  trades  │  exchange_state       │
└─────────────────────────────────────────────────────────────┘
```

---

## Exchange Clients

All clients in `exchanges/` inherit from `base_ws.py`:

| Exchange | File | Status | Symbols |
|----------|------|--------|---------|
| Binance | `binance_ws.py` | Active | BTCUSDT, ETHUSDT, SOLUSDT |
| Coinbase | `coinbase_ws.py` | Active | BTC-USD, ETH-USD |
| dYdX | `dydx_ws.py` | Active | Perpetuals |
| Hyperliquid | `hyperliquid_ws.py` | Active | Perpetuals |

---

## Base WebSocket Client

```python
# exchanges/base_ws.py
class BaseWebSocketClient(ABC):
    """Abstract base for all exchange WebSocket clients."""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.ws = None
        self.callbacks = {
            "trade": [],
            "kline": [],
            "order_book": []
        }

    @abstractmethod
    async def connect(self) -> None:
        """Establish WebSocket connection."""
        pass

    @abstractmethod
    async def subscribe(self) -> None:
        """Subscribe to market data channels."""
        pass

    @abstractmethod
    async def handle_message(self, message: dict) -> None:
        """Process incoming WebSocket message."""
        pass

    def on_trade(self, callback: Callable) -> None:
        self.callbacks["trade"].append(callback)

    def on_kline(self, callback: Callable) -> None:
        self.callbacks["kline"].append(callback)

    def on_order_book(self, callback: Callable) -> None:
        self.callbacks["order_book"].append(callback)
```

---

## Binance WebSocket

```python
# exchanges/binance_ws.py
class BinanceWebSocket(BaseWebSocketClient):
    """Binance WebSocket client for market data."""

    WS_URL = "wss://stream.binance.com:9443/ws"

    async def connect(self) -> None:
        streams = [f"{s.lower()}@kline_1m" for s in self.symbols]
        streams += [f"{s.lower()}@trade" for s in self.symbols]
        url = f"{self.WS_URL}/{'/'.join(streams)}"
        self.ws = await websockets.connect(url)

    async def handle_message(self, message: dict) -> None:
        event_type = message.get("e")

        if event_type == "kline":
            kline = self._parse_kline(message["k"])
            for callback in self.callbacks["kline"]:
                await callback(kline)

        elif event_type == "trade":
            trade = self._parse_trade(message)
            for callback in self.callbacks["trade"]:
                await callback(trade)

    def _parse_kline(self, k: dict) -> dict:
        return {
            "symbol": k["s"],
            "timeframe": k["i"],
            "timestamp": k["t"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "is_closed": k["x"]
        }
```

---

## Coinbase WebSocket

```python
# exchanges/coinbase_ws.py
class CoinbaseWebSocket(BaseWebSocketClient):
    """Coinbase Advanced Trade WebSocket client."""

    WS_URL = "wss://advanced-trade-ws.coinbase.com"

    async def subscribe(self) -> None:
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": self.symbols,
            "channel": "ticker",
            "api_key": self.api_key,
            "timestamp": str(int(time.time())),
            "signature": self._generate_signature()
        }
        await self.ws.send(json.dumps(subscribe_msg))

    async def handle_message(self, message: dict) -> None:
        channel = message.get("channel")

        if channel == "ticker":
            ticker = self._parse_ticker(message)
            for callback in self.callbacks["trade"]:
                await callback(ticker)
```

---

## dYdX WebSocket

```python
# exchanges/dydx_ws.py
class DydxWebSocket(BaseWebSocketClient):
    """dYdX perpetuals WebSocket client."""

    WS_URL = "wss://api.dydx.exchange/v3/ws"

    async def subscribe(self) -> None:
        # Subscribe to orderbook and trades
        for symbol in self.symbols:
            subscribe_msg = {
                "type": "subscribe",
                "channel": "v3_trades",
                "id": symbol
            }
            await self.ws.send(json.dumps(subscribe_msg))
```

---

## Hyperliquid WebSocket

```python
# exchanges/hyperliquid_ws.py
class HyperliquidWebSocket(BaseWebSocketClient):
    """Hyperliquid perpetuals WebSocket client."""

    WS_URL = "wss://api.hyperliquid.xyz/ws"

    async def subscribe(self) -> None:
        subscribe_msg = {
            "method": "subscribe",
            "subscription": {
                "type": "trades",
                "coin": self.symbols[0]
            }
        }
        await self.ws.send(json.dumps(subscribe_msg))
```

---

## Stream Manager

Orchestrates all exchange connections:

```python
# Infrastructure/Services/stream_manager_service.py
class StreamManager:
    """Manages all exchange WebSocket connections."""

    def __init__(self):
        self.clients: Dict[str, BaseWebSocketClient] = {}
        self.trade_callbacks = []
        self.kline_callbacks = []
        self.order_book_callbacks = []

    async def start(self, symbols: Dict[str, List[str]]) -> None:
        """
        Start all exchange connections.

        Args:
            symbols: {"binance": ["BTCUSDT"], "coinbase": ["BTC-USD"]}
        """
        for exchange, symbol_list in symbols.items():
            client = self._create_client(exchange, symbol_list)

            # Wire up callbacks
            for cb in self.trade_callbacks:
                client.on_trade(cb)
            for cb in self.kline_callbacks:
                client.on_kline(cb)

            await client.connect()
            await client.subscribe()

            self.clients[exchange] = client

    async def stop(self) -> None:
        """Disconnect all clients."""
        for client in self.clients.values():
            await client.disconnect()

    def on_trade(self, callback: Callable) -> None:
        self.trade_callbacks.append(callback)

    def on_kline(self, callback: Callable) -> None:
        self.kline_callbacks.append(callback)

    def on_order_book(self, callback: Callable) -> None:
        self.order_book_callbacks.append(callback)
```

---

## Data Collector

Batches and writes data to database:

```python
# Infrastructure/Services/collector_service.py
class DataCollector:
    """Collects and batches market data for DB writes."""

    def __init__(self, batch_size: int = 100, flush_interval: int = 5):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.trade_buffer = []
        self.kline_buffer = []

    async def handle_live_trade(self, trade: dict) -> None:
        """Handle incoming trade from WebSocket."""
        self.trade_buffer.append(trade)

        if len(self.trade_buffer) >= self.batch_size:
            await self._flush_trades()

    async def handle_live_kline(self, kline: dict) -> None:
        """Handle incoming kline from WebSocket."""
        if kline.get("is_closed"):
            self.kline_buffer.append(kline)

            if len(self.kline_buffer) >= self.batch_size:
                await self._flush_klines()

    async def _flush_trades(self) -> None:
        """Write buffered trades to database."""
        if not self.trade_buffer:
            return

        async with async_session_maker() as session:
            for trade in self.trade_buffer:
                # Insert trade record
                pass
            await session.commit()

        self.trade_buffer.clear()

    async def verify_and_backfill(self, symbols: Dict[str, List[str]]) -> None:
        """Check for data gaps and backfill if needed."""
        for exchange, symbol_list in symbols.items():
            for symbol in symbol_list:
                gaps = await self._find_gaps(symbol)
                if gaps:
                    await self._backfill_gaps(exchange, symbol, gaps)
```

---

## Data Models

### Candle Model

```python
class Candle(SQLModel, table=True):
    __tablename__ = "candles"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None
    exchange: str = "binance"
    is_closed: bool = True
```

### Enhanced Candle (with indicators)

```python
class EnhancedCandle(SQLModel, table=True):
    __tablename__ = "enhanced_candles"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    timeframe: str  # 1m, 5m, 15m, 1h, 6h, 1d
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Pre-computed indicators
    rsi_14: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
```

### Exchange State

```python
class ExchangeState(SQLModel, table=True):
    __tablename__ = "exchange_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    exchange: str
    symbol: str
    last_price: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    volume_24h: Optional[float] = None
    is_trading: bool = True
    latency_ms: Optional[float] = None
    last_update: datetime
```

---

## Startup Flow

```python
# Main.py lifespan
async def lifespan(app: FastAPI):
    # Configure symbols per exchange
    symbols = {
        "binance": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "coinbase": ["BTC-USD", "ETH-USD"]
    }

    # Wire up event handlers
    stream_manager.on_trade(data_collector.handle_live_trade)
    stream_manager.on_kline(data_collector.handle_live_kline)
    stream_manager.on_order_book(data_collector.handle_order_book)

    # Start WebSocket connections
    await stream_manager.start(symbols)

    # Verify data and backfill gaps
    await data_collector.verify_and_backfill(symbols)

    # Start historical OHLCV backfill
    asyncio.create_task(startup_backfill())

    yield

    # Shutdown
    await stream_manager.stop()
    await data_collector.flush_all()
```

---

## Backfill Service

Fills historical data gaps:

```python
# Infrastructure/Services/backfill_service.py
async def startup_backfill() -> None:
    """
    Background task to backfill historical OHLCV data.

    Runs at startup and fills gaps for backtesting.
    """
    assets = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE"]
    timeframes = ["1h", "6h", "1d"]

    for asset in assets:
        for timeframe in timeframes:
            symbol = f"{asset}USDT"
            await backfill_candles(symbol, timeframe)
```

---

## Timeframes Supported

| Timeframe | Description | Use Case |
|-----------|-------------|----------|
| `1m` | 1 minute | Real-time streaming |
| `5m` | 5 minutes | Short-term signals |
| `15m` | 15 minutes | Intraday trading |
| `1h` | 1 hour | Primary backtest timeframe |
| `6h` | 6 hours | Swing trading |
| `1d` | 1 day | Position trading |

---

## Indicator Computation

### Pre-Computed (on ingestion)

Common indicators stored in `enhanced_candles`:
- RSI (14)
- SMA (20, 50)
- EMA (12, 26)
- MACD + Signal
- Bollinger Bands
- ATR (14)

### On-Demand (during backtest)

Exotic indicators computed when needed:
- Custom moving average periods
- Specialized oscillators
- Pattern-specific indicators

---

## API Endpoints

### GET /exchanges

```json
{
    "exchanges": ["binance", "coinbase", "dydx", "hyperliquid"]
}
```

### GET /exchanges/{exchange}/state

```json
{
    "exchange": "binance",
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "status": "connected",
    "latency_ms": 45,
    "last_update": "2026-01-13T10:30:00Z"
}
```

### GET /market-data/candles

```json
{
    "candles": [...],
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "count": 100
}
```

---

## Environment Variables

```bash
# Exchange API Keys (optional for public data)
BINANCE_API_KEY=
BINANCE_API_SECRET=
COINBASE_API_KEY=
COINBASE_API_SECRET=
COINBASE_ENVIRONMENT=sandbox  # or production

# dYdX (if using private endpoints)
DYDX_API_KEY=
DYDX_API_SECRET=
DYDX_PASSPHRASE=

# Hyperliquid (if using private endpoints)
HYPERLIQUID_API_KEY=
HYPERLIQUID_API_SECRET=
```

---

## Key Design Decisions

### Why WebSocket over REST?
- Real-time data without polling
- Lower latency for market data
- More efficient for high-frequency updates

### Why 4 Exchanges?
- Binance: Highest liquidity, most pairs
- Coinbase: US-regulated, institutional
- dYdX: Decentralized perpetuals
- Hyperliquid: Low-fee perpetuals

### Why Pre-Compute Indicators?
- Faster backtest execution
- Consistent indicator values
- Reduced computation during evolution

---

*Last Updated: 2026-01-13*
