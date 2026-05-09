from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, Numeric, Index, Integer
from sqlmodel import Field, SQLModel


class Candle(SQLModel, table=True):
    """Legacy candle model - points to empty table. Use EnhancedCandle instead."""

    __tablename__ = "candles"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True, default="binance")
    asset: str = Field(index=True)
    timeframe: str = Field(index=True)
    timestamp: int = Field(sa_column=Column(BigInteger, index=True))
    open: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    high: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    low: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    close: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    volume: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
    quote_volume: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
    is_closed: bool = Field(default=True)


class EnhancedCandle(SQLModel, table=True):
    """
    Main candle table with 200+ pre-computed indicators.

    Contains 5.2M rows covering 2017-2025, multi-timeframe (1m, 5m, 15m, 1h, etc.)
    TimescaleDB hypertable with compression enabled.
    """

    __tablename__ = "enhanced_candles"
    __table_args__ = ({"extend_existing": True},)

    # Primary key (composite: time, exchange, symbol, timeframe)
    time: datetime = Field(sa_column=Column(DateTime(timezone=True), primary_key=True))
    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True, index=True)
    timeframe: str = Field(primary_key=True, index=True)

    # Core OHLCV
    open: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    high: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    low: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    close: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    volume: Decimal = Field(sa_column=Column(Numeric(24, 8)))

    # Moving Averages
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_9: float | None = None
    ema_12: float | None = None
    ema_21: float | None = None
    ema_26: float | None = None

    # RSI family
    rsi_7: float | None = None
    rsi_14: float | None = None
    rsi_21: float | None = None

    # MACD
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Bollinger Bands
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    bb_pct: float | None = None

    # ATR/Volatility
    atr_7: float | None = None
    atr_14: float | None = None
    natr_14: float | None = None
    true_range: float | None = None

    # Stochastic
    stoch_k: float | None = None
    stoch_d: float | None = None
    stochrsi_k: float | None = None
    stochrsi_d: float | None = None

    # ADX/Trend
    adx_14: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None

    # Volume indicators
    obv: float | None = None
    volume_sma_20: float | None = None
    cmf_20: float | None = None
    mfi_14: float | None = None

    # Sentiment/Regime
    fear_greed_value: float | None = None
    fear_greed_class: str | None = None
    regime: str | None = None
    regime_encoded: int | None = None

    # Tick aggregates
    tick_cvd_ratio: float | None = None
    tick_trade_imbalance: float | None = None
    tick_buy_volume_pct: float | None = None
    tick_volatility: float | None = None
    tick_momentum: float | None = None

    # Order book aggregates
    book_avg_spread_bps: float | None = None
    book_avg_imbalance: float | None = None
    book_depth_ratio: float | None = None

    # Cross-asset metrics
    btc_eth_correlation_14d: float | None = None
    eth_btc_ratio: float | None = None
    alt_dominance_pct: float | None = None

    # Metadata
    enriched_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Ticker(SQLModel, table=True):
    __tablename__ = "tickers"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    symbol: str = Field(index=True)
    price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    timestamp: int = Field(sa_column=Column(BigInteger))


class ExchangeTick(SQLModel, table=True):
    """
    Raw tick data from exchanges (12.5M+ rows).
    TimescaleDB hypertable with individual trades.
    """

    __tablename__ = "exchange_ticks"
    __table_args__ = ({"extend_existing": True},)

    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True, index=True)
    trade_id: str = Field(primary_key=True)
    time: datetime = Field(sa_column=Column(DateTime(timezone=True), primary_key=True))
    price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    size: Decimal = Field(sa_column=Column(Numeric(24, 8)))
    side: str  # buy/sell


class OrderBookSnapshot(SQLModel, table=True):
    """
    Order book snapshots with depth and imbalance (781K+ rows).
    """

    __tablename__ = "order_book_snapshots"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    symbol: str = Field(index=True)
    timestamp: int = Field(sa_column=Column(BigInteger, index=True))
    bid_vol_10: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
    ask_vol_10: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
    imbalance: float | None = None  # Order book imbalance ratio
    spread_bps: float | None = None  # Spread in basis points
    mid_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    created_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class BacktestWindow(SQLModel, table=True):
    """
    Pre-computed backtest windows cached for fast startup.
    
    Cached from windows.py generate_pool() to avoid recomputation on every launch.
    Invalidated when data ranges change (checked against max data timestamp).
    """

    __tablename__ = "backtest_windows"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    timeframe: str = Field(index=True)
    start_ts: int = Field(sa_column=Column(BigInteger))  # milliseconds
    end_ts: int = Field(sa_column=Column(BigInteger))  # milliseconds
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))
    
    # Track cache validity
    pool_seed: int = Field(default=42, sa_column=Column(Integer))  # Seed used to generate pool
    data_max_ts: int | None = Field(default=None, sa_column=Column(BigInteger))  # Max timestamp in milliseconds
    
    __table_args__ = (
        Index("ix_backtest_window_pair", "symbol", "timeframe"),
        Index("ix_backtest_window_range", "start_ts", "end_ts"),
        {"extend_existing": True},
    )
