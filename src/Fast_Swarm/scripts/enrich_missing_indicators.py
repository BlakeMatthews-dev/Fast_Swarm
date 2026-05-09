"""
Batch compute and persist indicators for timeframes missing them.

Usage:
    python -m Fast_Swarm.scripts.enrich_missing_indicators
"""

import asyncio
import sys
from datetime import datetime, UTC

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, "c:/fast_swarm/src")

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import calculate_indicators


# Mapping from pandas_ta output column names -> DB column names
# pandas_ta uses uppercase with full parameter specs (e.g. "RSI_14", "MACD_12_26_9")
# Our DB uses lowercase/custom names (e.g. "rsi_14", "macd_line")
PANDAS_TA_TO_DB = {
    # Moving Averages
    "SMA_20": "sma_20",
    "SMA_50": "sma_50",
    "SMA_200": "sma_200",
    "EMA_9": "ema_9",
    "EMA_12": "ema_12",
    "EMA_21": "ema_21",
    "EMA_26": "ema_26",
    # RSI
    "RSI_7": "rsi_7",
    "RSI_14": "rsi_14",
    "RSI_21": "rsi_21",
    # MACD
    "MACD_12_26_9": "macd_line",
    "MACDs_12_26_9": "macd_signal",
    "MACDh_12_26_9": "macd_histogram",
    # Bollinger Bands
    "BBU_5_2.0": "bb_upper",
    "BBM_5_2.0": "bb_middle",
    "BBL_5_2.0": "bb_lower",
    "BBB_5_2.0": "bb_bandwidth",
    "BBP_5_2.0": "bb_percent",
    # ATR/Volatility
    "ATRr_7": "atr_7",
    "ATRr_14": "atr_14",
    "NATR_14": "natr_14",
    "TRUERANGE_1": "true_range",
    # Stochastic
    "STOCHk_14_3_3": "stoch_k",
    "STOCHd_14_3_3": "stoch_d",
    "STOCHRSIk_14_14_3_3": "stochrsi_k",
    "STOCHRSId_14_14_3_3": "stochrsi_d",
    # ADX
    "ADX_14": "adx_14",
    "DMP_14": "plus_di",
    "DMN_14": "minus_di",
    # Volume
    "OBV": "obv",
    "CMF_20": "cmf_20",
    "MFI_14": "mfi_14",
    # Aroon
    "AROONU_14": "aroon_up",
    "AROOND_14": "aroon_down",
    "AROONOSC_14": "aroon_osc",
    # Other momentum
    "CCI_14_0.015": "cci_14",
    "WILLR_14": "willr_14",
    "ROC_10": "roc_10",
    # === NEW INDICATORS (previously unresolvable) ===
    # Momentum
    "CMO_14": "cmo_14",
    "MOM_10": "mom_10",
    "PPO_12_26_9": "ppo",
    "UO_7_14_28": "uo",
    # Fisher Transform
    "FISHERT_9_1": "fisher",
    "FISHERTs_9_1": "fisher_signal",
    # Volume
    "PVI_13": "pvi",
    # Volatility
    "UI_14": "ui_14",
    # Price analysis
    "BIAS_SMA_26": "bias_26",
    "ZS_30": "zscore_30",
    # Trend
    "SUPERTd_7_3.0": "supertrend_direction",
    # TSI (True Strength Index)
    "TSI_25_13": "tsi",
    "TSIs_25_13": "tsi_signal",
    # SMI (Stochastic Momentum Index)
    "SMI_13_25_13": "smi",
    # TRIX
    "TRIX_14": "trix_14",
    # DPO (Detrended Price Oscillator)
    "DPO_14": "dpo",
    # Mass Index
    "MASSI_9_25": "massi",
    # Linear Regression slope
    "LRm_14": "linreg_slope",
    # Z-Score 50-period
    "ZS_50": "zscore_50",
}

# DB column names to persist (derived from the mapping values)
INDICATOR_COLS = list(set(PANDAS_TA_TO_DB.values()))
# Also add volume_sma_20 which is computed manually
INDICATOR_COLS.append("volume_sma_20")


async def get_missing_data(symbol: str, timeframe: str, limit: int = 50000) -> pd.DataFrame:
    """Load candles that are missing indicators."""
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id, time, exchange, symbol, timeframe,
                       open, high, low, close, volume
                FROM enhanced_candles
                WHERE symbol = :symbol
                  AND timeframe = :timeframe
                  AND rsi_14 IS NULL
                ORDER BY time ASC
                LIMIT :limit
            """),
            {"symbol": symbol, "timeframe": timeframe, "limit": limit}
        )
        rows = result.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["id", "time", "exchange", "symbol", "timeframe",
                                      "open", "high", "low", "close", "volume"])
    return df


async def persist_indicators(df: pd.DataFrame, batch_size: int = 1000) -> int:
    """Persist computed indicators back to database."""
    if df.empty:
        return 0

    updated = 0
    async with async_session_maker() as session:
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]

            for _, row in batch.iterrows():
                # Build SET clause with available indicator columns
                set_parts = []
                params = {"row_id": row["id"]}

                for col in INDICATOR_COLS:
                    if col in row.index:
                        val = row[col]
                        if pd.notna(val):
                            param_name = f"val_{col}"
                            set_parts.append(f"{col} = :{param_name}")
                            params[param_name] = float(val)

                if set_parts:
                    set_parts.append("enriched_at = NOW()")
                    set_clause = ", ".join(set_parts)

                    await session.execute(
                        text(f"""
                            UPDATE enhanced_candles
                            SET {set_clause}
                            WHERE id = :row_id
                        """),
                        params
                    )
                    updated += 1

            await session.commit()
            print(f"  Persisted batch {i//batch_size + 1}: {updated} rows")

    return updated


async def enrich_timeframe(symbol: str, timeframe: str):
    """Enrich all missing candles for a symbol/timeframe."""
    print(f"\n[Enrich] {symbol}/{timeframe}...")

    # Load missing data
    df = await get_missing_data(symbol, timeframe)
    if df.empty:
        print(f"  No missing data for {symbol}/{timeframe}")
        return 0

    print(f"  Loaded {len(df)} candles missing indicators")

    # Need enough candles for indicator warmup (200+)
    if len(df) < 250:
        print(f"  Not enough candles for indicator warmup (need 250+)")
        return 0

    # Calculate indicators
    print(f"  Computing indicators...")
    df_enriched = calculate_indicators(df, verbose=False, min_candles=200)

    # Rename pandas_ta columns to DB column names
    rename_map = {k: v for k, v in PANDAS_TA_TO_DB.items() if k in df_enriched.columns}
    df_enriched = df_enriched.rename(columns=rename_map)

    # Compute volume_sma_20 if not present (manual, not from pandas_ta)
    if "volume_sma_20" not in df_enriched.columns and "volume" in df_enriched.columns:
        df_enriched["volume_sma_20"] = df_enriched["volume"].rolling(20).mean()

    print(f"  Mapped {len(rename_map)} pandas_ta columns to DB names")

    # Persist back to DB
    print(f"  Persisting to database...")
    updated = await persist_indicators(df_enriched)

    print(f"  Done: {updated} candles enriched")
    return updated


async def main():
    """Enrich all missing timeframes."""
    # Timeframes that need enrichment (from earlier check)
    missing_timeframes = [
        ("BTC", "1m"), ("BTC", "5m"), ("BTC", "15m"),
        ("ETH", "1m"), ("ETH", "5m"), ("ETH", "15m"),
        ("ADA", "1m"), ("ADA", "5m"), ("ADA", "15m"),
        ("SOL", "1m"), ("SOL", "5m"), ("SOL", "15m"),
    ]

    total = 0
    for symbol, timeframe in missing_timeframes:
        try:
            count = await enrich_timeframe(symbol, timeframe)
            total += count
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n=== Total enriched: {total} candles ===")


if __name__ == "__main__":
    asyncio.run(main())
