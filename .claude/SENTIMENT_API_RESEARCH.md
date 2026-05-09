# Crypto Sentiment API Research Report

**Date:** 2025-12-23
**Purpose:** Historical sentiment data collection for Coinswarm trading system

---

## Summary

We successfully collected **2,880 days of Fear & Greed Index data** (2018-01-31 to 2025-12-23) using the free Alternative.me API. News sentiment collection is rate-limited on the free tier.

---

## API Research Findings

### 1. Fear & Greed Index (Alternative.me) - WORKING

| Attribute | Value |
|-----------|-------|
| **Status** | Successfully collected |
| **Cost** | FREE |
| **API Key Required** | No |
| **Historical Depth** | 2018-01-31 to present (~7 years) |
| **Update Frequency** | Daily |
| **Rate Limit** | 60 requests/minute |
| **Data Points** | 2,880 daily readings |
| **Endpoint** | `https://api.alternative.me/fng/?limit=0` |

**Data Structure:**
```json
{
  "value": "30",           // 0-100 scale
  "value_classification": "Fear",  // Extreme Fear, Fear, Neutral, Greed, Extreme Greed
  "timestamp": "1517443200"
}
```

**Distribution in our data:**
- Extreme Fear: 595 days (20.7%)
- Fear: 827 days (28.7%)
- Neutral: 388 days (13.5%)
- Greed: 789 days (27.4%)
- Extreme Greed: 281 days (9.8%)

---

### 2. CryptoCompare News API - LIMITED

| Attribute | Value |
|-----------|-------|
| **Status** | Rate limited on free tier |
| **Cost** | Free tier: ~50 requests/day |
| **API Key Required** | Yes (we have one) |
| **Historical Depth** | Years of news articles |
| **Rate Limit** | Very strict on free tier |
| **Endpoint** | `https://min-api.cryptocompare.com/data/v2/news/` |

**Notes:**
- Our API key hit the daily limit during testing
- Each request returns ~50 articles
- Would need paid tier ($80-200/mo) for serious historical backfill
- Can run incrementally (5-10 requests/day) to slowly build up data

---

### 3. LunarCrush - PAID ONLY

| Attribute | Value |
|-----------|-------|
| **Status** | Requires paid subscription |
| **Cost** | Paid "Individual" tier required |
| **API Key** | We have one but it's not working |
| **Error** | "You must have an active Individual or higher subscription" |

**Notes:**
- Used to have a free tier, now paywalled
- Excellent social sentiment data (Twitter, Reddit aggregation)
- Would need paid subscription for historical data

---

### 4. Santiment - LIMITED FREE TIER

| Attribute | Value |
|-----------|-------|
| **Status** | Limited free access |
| **Cost** | Free trial, then paid |
| **Historical Depth** | Since 2014 |
| **Features** | On-chain, social, development metrics |

**Notes:**
- GraphQL API via `sanpy` Python client
- Free tier has limited historical access
- Would need paid plan for full historical sentiment

---

### 5. CoinGlass Fear & Greed - PAID ONLY

| Attribute | Value |
|-----------|-------|
| **Status** | Requires paid plan |
| **API Key** | We have one |
| **Error** | "Upgrade plan" |

---

### 6. SentiCrypt - SSL ISSUES

| Attribute | Value |
|-----------|-------|
| **Status** | SSL connection failed |
| **Cost** | FREE (no key required) |
| **Claims** | 4+ years of BTC sentiment data |
| **Issue** | SSL/TLS handshake errors |

---

## Data Collected

### Location
```
c:\Users\Admin\Documents\Coinswarm-1\local-utilities\coinswarm_sentiment.sqlite
```

### Tables Created

1. **fear_greed_index** - Daily Fear & Greed values
   - timestamp, date, value (0-100), classification
   - 2,880 records (2018-01-31 to 2025-12-23)

2. **crypto_news** - Individual news articles
   - news_id, timestamp, title, body, source, categories, tags, upvotes, downvotes
   - 0 records (rate limited)

3. **daily_sentiment** - Aggregated daily sentiment per asset
   - date, asset, article_count, avg_sentiment, positive/negative/neutral counts
   - Ready for computed aggregations

4. **backfill_progress** - Tracks incremental backfill state

---

## Script Usage

```bash
# Show current data status
python sentiment_backfill.py --status

# Backfill Fear & Greed (FREE - fetches all ~2900 records instantly)
python sentiment_backfill.py --source fng

# Backfill news incrementally (limited by rate limits)
python sentiment_backfill.py --source news --news-requests 5

# Backfill everything
python sentiment_backfill.py
```

---

## Recommendations

### Immediate Use (FREE)
1. **Fear & Greed Index** - Already collected 7 years of data
   - Use as market-wide sentiment indicator
   - Correlate with price movements for pattern discovery
   - Values < 25 = "Extreme Fear" (historically good buy signals)
   - Values > 75 = "Extreme Greed" (historically good sell signals)

### Gradual Collection (FREE but slow)
2. **CryptoCompare News** - Run daily with 5-10 requests
   - Over time, build up historical news archive
   - Script tracks progress and continues where left off

### If Budget Allows
3. **LunarCrush** ($49/mo?) - Best social sentiment
   - Twitter, Reddit aggregation
   - Galaxy Score for overall sentiment

4. **Santiment** (pricing varies) - Most comprehensive
   - On-chain metrics
   - Development activity
   - Social volume

---

## Integration with Trading System

The Fear & Greed Index can be incorporated into pattern discovery:

```python
# Example: Load sentiment into pattern evaluation
import sqlite3

conn = sqlite3.connect('coinswarm_sentiment.sqlite')
cursor = conn.cursor()

# Get sentiment for a specific date
cursor.execute("""
    SELECT value, classification
    FROM fear_greed_index
    WHERE date = '2024-01-15'
""")
sentiment = cursor.fetchone()  # (42, 'Fear')

# Use in pattern conditions
if sentiment[0] < 25:  # Extreme Fear
    # Historically good buying opportunity
    pass
```

---

## API Keys We Have

| Service | Key Status | Location |
|---------|------------|----------|
| CryptoCompare | Have key, rate limited | `.env.api-keys.backup` |
| LunarCrush | Have key, requires paid tier | `.env.dont_delete_yet_human_said_so` |
| CoinGlass | Have key, requires paid tier | `.env.dont_delete_yet_human_said_so` |
| Alternative.me (FNG) | No key needed | N/A |

---

## Sources

- [Alternative.me Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/)
- [CryptoCompare News API](https://min-api.cryptocompare.com/documentation?key=News)
- [LunarCrush API](https://lunarcrush.com/about/api)
- [Santiment API](https://api.santiment.net/)
- [SentiCrypt](https://senticrypt.com/)
- [CoinGlass API](https://docs.coinglass.com)
