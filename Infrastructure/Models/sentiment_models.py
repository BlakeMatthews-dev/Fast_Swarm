"""
Sentiment data models for market sentiment indicators.

Contains:
- FearGreedIndex: Crypto Fear & Greed Index (0-100)
- MarketSentiment: Aggregated sentiment scores by metric type
- BtcDominance: BTC market dominance percentage
- FundingRate: Perpetual futures funding rates
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class FearGreedIndex(SQLModel, table=True):
    """
    Crypto Fear & Greed Index (0-100).

    Data covers 2005+ rows of historical sentiment data.
    0 = Extreme Fear, 100 = Extreme Greed
    """

    __tablename__ = "fear_greed_index"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    timestamp: int = Field(sa_column=Column(BigInteger, index=True))  # Unix epoch
    value: int  # 0-100
    classification: str | None = None  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    created_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class MarketSentiment(SQLModel, table=True):
    """
    Aggregated sentiment scores by metric type.

    Metric types include various sentiment indicators aggregated
    from multiple sources.
    """

    __tablename__ = "market_sentiment"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    metric_type: str = Field(index=True)  # Type of sentiment metric
    value: float  # Sentiment value
    classification: str | None = None
    extra_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, name="metadata"),  # Keep DB column name as 'metadata'
    )


class BtcDominance(SQLModel, table=True):
    """
    BTC market dominance percentage and total market cap.

    Tracks Bitcoin's share of the total crypto market cap over time.
    """

    __tablename__ = "btc_dominance"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    timestamp: int = Field(sa_column=Column(BigInteger, index=True))  # Unix epoch
    dominance: float  # Percentage (e.g., 52.3 = 52.3%)
    total_market_cap: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 2)))
    created_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class FundingRate(SQLModel, table=True):
    """
    Perpetual futures funding rates by symbol.

    Positive = longs pay shorts (bullish bias)
    Negative = shorts pay longs (bearish bias)
    """

    __tablename__ = "funding_rates"
    __table_args__ = ({"extend_existing": True},)

    time: datetime = Field(sa_column=Column(DateTime(timezone=True), primary_key=True))
    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True, index=True)
    funding_rate: float  # Current funding rate
    next_funding_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    funding_rate_8h: float | None = None  # 8-hour funding rate
    mark_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    index_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 8)))
    open_interest: Decimal | None = Field(default=None, sa_column=Column(Numeric(24, 8)))
