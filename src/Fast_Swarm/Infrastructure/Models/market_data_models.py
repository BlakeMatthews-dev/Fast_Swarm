from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, Numeric
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

    # Aroon
    aroon_up: float | None = None
    aroon_down: float | None = None
    aroon_osc: float | None = None

    # Additional momentum indicators
    cci_14: float | None = None  # Commodity Channel Index
    willr_14: float | None = None  # Williams %R
    roc_10: float | None = None  # Rate of Change
    trix_14: float | None = None  # TRIX
    cmo_14: float | None = None  # Chande Momentum Oscillator
    emv_14: float | None = None  # Ease of Movement
    vhf_28: float | None = None  # Vertical Horizontal Filter
    mom_10: float | None = None  # Momentum (10-period)
    tsi: float | None = None  # True Strength Index
    tsi_signal: float | None = None  # TSI signal line
    smi: float | None = None  # Stochastic Momentum Index
    dpo: float | None = None  # Detrended Price Oscillator
    massi: float | None = None  # Mass Index
    linreg_slope: float | None = None  # Linear Regression Slope
    zscore_50: float | None = None  # Z-Score (50-period)
    uo: float | None = None  # Ultimate Oscillator
    fisher: float | None = None  # Fisher Transform
    fisher_signal: float | None = None  # Fisher Transform Signal
    supertrend_direction: int | None = None  # SuperTrend direction (1=up, -1=down)

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

    # ==========================================================================
    # DERIVED/COMPUTED INDICATORS
    # These are calculated from base indicators and stored for fast pattern matching.
    # Previously computed on-the-fly during backtests (expensive), now precomputed.
    # ==========================================================================

    # MA Cross signals (1 = bullish cross, -1 = bearish cross, 0 = no cross)
    ma_cross_20_50: int | None = None  # EMA 20 vs SMA 50
    golden_cross: int | None = None  # SMA 50 vs SMA 200
    death_cross: int | None = None  # SMA 50 vs SMA 200 (inverted)

    # MACD Cross signals (1 = bullish, -1 = bearish, 0 = none)
    macd_cross: int | None = None  # MACD line vs signal

    # Price vs MA (percent difference)
    price_vs_ema_9_pct: float | None = None
    price_vs_ema_20_pct: float | None = None
    price_vs_ema_21_pct: float | None = None
    price_vs_sma_50_pct: float | None = None
    price_vs_sma_200_pct: float | None = None

    # Boolean conditions (stored as int: 1=true, 0=false)
    price_above_ema_9: int | None = None
    price_above_ema_20: int | None = None
    price_above_ema_21: int | None = None
    price_above_sma_50: int | None = None
    price_above_sma_200: int | None = None

    # RSI conditions (1=true, 0=false)
    rsi_oversold: int | None = None  # RSI < 30
    rsi_overbought: int | None = None  # RSI > 70
    rsi_neutral: int | None = None  # 30 <= RSI <= 70

    # Stochastic conditions
    stoch_oversold: int | None = None  # K < 20
    stoch_overbought: int | None = None  # K > 80

    # Trend strength conditions
    strong_trend: int | None = None  # ADX > 25
    weak_trend: int | None = None  # ADX < 20

    # Regime indicators (categorical stored as string)
    volatility_regime: str | None = None  # "low", "medium", "high" based on NATR
    trend_regime: str | None = None  # "uptrend", "downtrend", "sideways" based on MAs

    # Session indicators (1=true, 0=false) - computed from candle timestamp
    is_asian_session: int | None = None  # 00:00-08:00 UTC
    is_london_session: int | None = None  # 08:00-16:00 UTC
    is_us_session: int | None = None  # 13:00-21:00 UTC
    is_us_market_hours: int | None = None  # 14:30-21:00 UTC (NYSE hours)

    # Bollinger conditions
    price_at_bb_upper: int | None = None  # Close >= BB upper
    price_at_bb_lower: int | None = None  # Close <= BB lower
    bb_squeeze: int | None = None  # BB width < threshold

    # Volume conditions
    high_volume: int | None = None  # Volume > 1.5x SMA(20)
    low_volume: int | None = None  # Volume < 0.5x SMA(20)

    # ==========================================================================
    # MOTION DERIVATIVES (for Bear Protection)
    # These track velocity, acceleration, and jerk of price/indicators.
    # Used by BearProtectionService for regime detection.
    # ==========================================================================

    # Price motion derivatives (z-scores, 21-period rolling)
    close_velocity_zscore: float | None = None  # 1st derivative of close
    close_acceleration_zscore: float | None = None  # 2nd derivative of close
    close_jerk_zscore: float | None = None  # 3rd derivative of close

    # ADX motion derivatives (z-scores)
    adx_14_velocity_zscore: float | None = None  # 1st derivative of ADX
    adx_14_acceleration_zscore: float | None = None  # 2nd derivative of ADX
    adx_14_jerk_zscore: float | None = None  # 3rd derivative of ADX

    # ==========================================================================
    # BEAR PROTECTION TRIGGERS (pre-computed boolean signals)
    # These are the final CTC (Crash-to-Cash) signals ready for use.
    # ==========================================================================

    # Single-TF defensive trigger: acc < -1.5 AND adx_jerk < -0.5
    # Use with multi-TF confirmation: BOTH 1h AND 4h must be true
    defensive_trigger: int | None = None  # 1 = danger signal, 0 = safe

    # Metadata
    enriched_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    derived_computed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


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


class PaperTrade(SQLModel, table=True):
    """
    Paper trading trade history for persistence.

    Records all paper trades executed by PaperTradingClient for:
    - Trade history persistence across restarts
    - Performance analysis
    - Audit trail
    """

    __tablename__ = "paper_trades"

    id: int | None = Field(default=None, primary_key=True)
    order_id: str = Field(index=True)  # Matches PaperTradingClient order_id
    agent_id: str | None = Field(default=None, index=True)  # Optional: link to agent

    # Trade details
    symbol: str = Field(index=True)
    side: str  # "buy" or "sell"
    size: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    price: Decimal = Field(sa_column=Column(Numeric(18, 8)))
    commission: Decimal = Field(sa_column=Column(Numeric(18, 8)))

    # Timing
    filled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))

    # P&L tracking (for sells)
    entry_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    realized_pnl: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))

    # Partial close tracking
    is_partial: bool = Field(default=False)
    close_fraction: float | None = Field(default=None)
    parent_order_id: str | None = Field(default=None, index=True)

    __table_args__ = (
        Index("ix_paper_trade_symbol_time", "symbol", "filled_at"),
        Index("ix_paper_trade_agent", "agent_id", "filled_at"),
        {"extend_existing": True},
    )
