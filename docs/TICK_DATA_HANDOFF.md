# Tick Data Backfill - Session Handoff

## Current Status (2026-01-12)

### Downloads Completed (119GB total) ✅ ALL DONE
| Period | Status | Purpose | Notable |
|--------|--------|---------|---------|
| 2017-09 to 2017-12 | ✅ Complete | Bull run + blowoff | BTC/ETH only |
| 2018 full year | ✅ Complete | Jan crash + bear market | |
| 2019 full year | ✅ Complete | Recovery + sideways | |
| 2020-03 to 2020-12 | ✅ Complete | COVID crash + recovery + Q4 bull | |
| 2021-01 to 2021-11 | ✅ Complete | Bull + May crash + Nov blowoff | DOGE May: 3.2GB! |
| 2022-05 to 2022-11 | ✅ Complete | Luna crash + FTX + bear | BTC Nov: 2.9GB |
| 2023-01 to 2023-09 | ✅ Complete | Recovery + sideways | BTC Feb: 3.1GB |
| 2024-01 to 2024-12 | ✅ Complete | ETF rally + full year | |
| 2025-07 to 2025-12 | ✅ Complete | Last 6 months | |

### Import Progress
- **Full import running**: Task b668e2f (streaming, memory-safe)
- **337 ZIP files** being imported
- **331M+ ticks already in DB** from earlier batch
- Uses streaming import (100K chunks) to avoid MemoryError on large files

### Background Tasks Still Running
Check with: `tasklist | findstr python`
- **b07d6b2**: Importing 2024 Jul-Dec data
- **bc6d908**: Downloading 2021 (last few files)

## Files Created This Session

### Scripts
1. **`scripts/binance_tick_downloader.py`** - Downloads from data.binance.vision
   ```bash
   # List available months
   python scripts/binance_tick_downloader.py --list

   # Download range
   python scripts/binance_tick_downloader.py --download 2024-01:2024-06

   # Import downloaded ZIPs to database
   python scripts/binance_tick_downloader.py --import-dir data/binance_trades
   ```

2. **`scripts/tick_gap_filler.py`** - Detect/fill gaps + rollup to candles
   ```bash
   # Show gaps
   python scripts/tick_gap_filler.py --detect

   # Fill gaps from Coinbase API
   python scripts/tick_gap_filler.py --fill

   # Roll up ticks to candles (1m, 5m, 15m, 1h, 4h, 1d)
   python scripts/tick_gap_filler.py --rollup
   ```

### Downloaded Data Location
- **Path**: `data/binance_trades/*.zip`
- **Size**: ~101GB compressed
- **Format**: Binance trade CSV (trade_id, price, qty, quoteQty, time, isBuyerMaker)

## Next Steps (Priority Order)

### 1. Wait for Downloads to Complete
```bash
# Check if 2021 download finished
type C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin-Documents-Fast-Swarm\tasks\bc6d908.output
```

### 2. Import Remaining Data
```bash
# After downloads complete, import all ZIPs
python scripts/binance_tick_downloader.py --import-dir data/binance_trades
```
**Note**: Each file takes 5-15 min to parse+import. Large files (2021-2023) use 10-20GB RAM.

### 3. Roll Up to Candles
```bash
python scripts/tick_gap_filler.py --rollup
```

### 4. Run Pattern Regime Tester
```bash
python scripts/pattern_regime_tester.py --batch-size 50 --workers 4
```

## Database Info

### Current State
- **exchange_ticks**: 229M rows, 46GB (20GB data + 26GB indexes)
- **Total DB**: 56GB
- **Estimated final**: 400-800GB after all imports

### Storage Recommendation
- HDD is fine for import (sequential writes)
- Consider SSD or ZFS with L2ARC for backtesting (random reads)
- PostgreSQL tuning for HDD:
  ```
  shared_buffers = 4GB
  effective_io_concurrency = 2
  random_page_cost = 4
  ```

## Canonical Periods Covered

| Regime | Periods | Data Available |
|--------|---------|----------------|
| **crash** | COVID 2020, Luna 2022, FTX 2022, May 2021, Jan 2018 | ✅ All |
| **blowoff** | Dec 2017, Apr 2021, Nov 2021 | ✅ All |
| **recovery** | Post-COVID 2020, 2023, 2019 | ✅ All |
| **bull** | 2017 Q4, 2020 Q4, 2021 Q1, 2024 Q1 | ✅ All |
| **bear** | 2018, 2022 | ✅ All |
| **sideways** | 2019 H2, 2023 Q2-Q3 | ✅ All |

## Token Data Availability

| Token | Earliest Data |
|-------|---------------|
| BTC | 2017-08 |
| ETH | 2017-08 |
| XRP | 2018-05 |
| DOGE | 2019-07 |
| SOL | 2020-08 |

Older canonical periods only have BTC/ETH data (expected - other tokens didn't exist).
