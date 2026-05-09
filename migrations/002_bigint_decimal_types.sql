-- Migration: 002_bigint_decimal_types.sql
-- Purpose: Fix integer overflow (BIGINT) and add financial precision (NUMERIC)
-- Date: 2026-01-10
--
-- Run with: psql -h localhost -U coinswarm -d coinswarm -f migrations/002_bigint_decimal_types.sql

BEGIN;

-- ============================================================================
-- PHASE 1: BIGINT TIMESTAMPS (Critical - fixes overflow error)
-- ============================================================================

-- order_book_snapshots - CURRENTLY FAILING
ALTER TABLE order_book_snapshots ALTER COLUMN timestamp TYPE BIGINT;

-- backtest_trades_unified
ALTER TABLE backtest_trades_unified ALTER COLUMN entry_timestamp TYPE BIGINT;
ALTER TABLE backtest_trades_unified ALTER COLUMN exit_timestamp TYPE BIGINT;
ALTER TABLE backtest_trades_unified ALTER COLUMN mfe_timestamp TYPE BIGINT;
ALTER TABLE backtest_trades_unified ALTER COLUMN mae_timestamp TYPE BIGINT;

-- tickers
ALTER TABLE tickers ALTER COLUMN timestamp TYPE BIGINT;

-- candles (legacy table)
ALTER TABLE candles ALTER COLUMN timestamp TYPE BIGINT;

-- sentiment tables (future-proofing)
ALTER TABLE fear_greed_index ALTER COLUMN timestamp TYPE BIGINT;
ALTER TABLE btc_dominance ALTER COLUMN timestamp TYPE BIGINT;

-- ============================================================================
-- PHASE 2: NUMERIC/DECIMAL FOR FINANCIAL DATA
-- ============================================================================

-- agents
ALTER TABLE agents ALTER COLUMN fitness_score TYPE NUMERIC(18,8);
ALTER TABLE agents ALTER COLUMN elo_rating TYPE NUMERIC(12,4);
ALTER TABLE agents ALTER COLUMN total_pnl TYPE NUMERIC(18,8);

-- candles (legacy)
ALTER TABLE candles ALTER COLUMN open TYPE NUMERIC(18,8);
ALTER TABLE candles ALTER COLUMN high TYPE NUMERIC(18,8);
ALTER TABLE candles ALTER COLUMN low TYPE NUMERIC(18,8);
ALTER TABLE candles ALTER COLUMN close TYPE NUMERIC(18,8);
ALTER TABLE candles ALTER COLUMN volume TYPE NUMERIC(24,8);
ALTER TABLE candles ALTER COLUMN quote_volume TYPE NUMERIC(24,8);

-- enhanced_candles
ALTER TABLE enhanced_candles ALTER COLUMN open TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN high TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN low TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN close TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN volume TYPE NUMERIC(24,8);

-- tickers
ALTER TABLE tickers ALTER COLUMN price TYPE NUMERIC(18,8);

-- exchange_ticks
ALTER TABLE exchange_ticks ALTER COLUMN price TYPE NUMERIC(18,8);
ALTER TABLE exchange_ticks ALTER COLUMN size TYPE NUMERIC(24,8);

-- order_book_snapshots
ALTER TABLE order_book_snapshots ALTER COLUMN mid_price TYPE NUMERIC(18,8);
ALTER TABLE order_book_snapshots ALTER COLUMN bid_vol_10 TYPE NUMERIC(24,8);
ALTER TABLE order_book_snapshots ALTER COLUMN ask_vol_10 TYPE NUMERIC(24,8);

-- exchange_state
ALTER TABLE exchange_state ALTER COLUMN last_price TYPE NUMERIC(18,8);
ALTER TABLE exchange_state ALTER COLUMN bid_price TYPE NUMERIC(18,8);
ALTER TABLE exchange_state ALTER COLUMN ask_price TYPE NUMERIC(18,8);
ALTER TABLE exchange_state ALTER COLUMN mid_price TYPE NUMERIC(18,8);
ALTER TABLE exchange_state ALTER COLUMN bid_depth_usd TYPE NUMERIC(18,2);
ALTER TABLE exchange_state ALTER COLUMN ask_depth_usd TYPE NUMERIC(18,2);

-- trades_live (legacy)
ALTER TABLE trades_live ALTER COLUMN price TYPE NUMERIC(18,8);
ALTER TABLE trades_live ALTER COLUMN size TYPE NUMERIC(24,8);

-- live_trades_unified
ALTER TABLE live_trades_unified ALTER COLUMN entry_price TYPE NUMERIC(18,8);
ALTER TABLE live_trades_unified ALTER COLUMN exit_price TYPE NUMERIC(18,8);
ALTER TABLE live_trades_unified ALTER COLUMN size TYPE NUMERIC(24,8);
ALTER TABLE live_trades_unified ALTER COLUMN size_usd TYPE NUMERIC(18,2);
ALTER TABLE live_trades_unified ALTER COLUMN pnl_usd TYPE NUMERIC(18,8);
ALTER TABLE live_trades_unified ALTER COLUMN fees_usd TYPE NUMERIC(18,8);
ALTER TABLE live_trades_unified ALTER COLUMN realized_pnl TYPE NUMERIC(18,8);

-- agent_trades
ALTER TABLE agent_trades ALTER COLUMN entry_price TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN exit_price TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN size TYPE NUMERIC(24,8);
ALTER TABLE agent_trades ALTER COLUMN pnl TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN fees TYPE NUMERIC(18,8);

-- backtest_trades_unified
ALTER TABLE backtest_trades_unified ALTER COLUMN entry_price TYPE NUMERIC(18,8);
ALTER TABLE backtest_trades_unified ALTER COLUMN exit_price TYPE NUMERIC(18,8);
ALTER TABLE backtest_trades_unified ALTER COLUMN position_size_usd TYPE NUMERIC(18,2);
ALTER TABLE backtest_trades_unified ALTER COLUMN pnl_usd TYPE NUMERIC(18,8);
ALTER TABLE backtest_trades_unified ALTER COLUMN mfe_price TYPE NUMERIC(18,8);
ALTER TABLE backtest_trades_unified ALTER COLUMN mae_price TYPE NUMERIC(18,8);

-- patterns
ALTER TABLE patterns ALTER COLUMN fitness_score TYPE NUMERIC(18,8);
ALTER TABLE patterns ALTER COLUMN total_roi_pct TYPE NUMERIC(12,6);

-- btc_dominance
ALTER TABLE btc_dominance ALTER COLUMN total_market_cap TYPE NUMERIC(24,2);

-- funding_rates
ALTER TABLE funding_rates ALTER COLUMN mark_price TYPE NUMERIC(18,8);
ALTER TABLE funding_rates ALTER COLUMN index_price TYPE NUMERIC(18,8);
ALTER TABLE funding_rates ALTER COLUMN open_interest TYPE NUMERIC(24,8);

-- crucible_entries
ALTER TABLE crucible_entries ALTER COLUMN starting_balance TYPE NUMERIC(18,2);
ALTER TABLE crucible_entries ALTER COLUMN current_balance TYPE NUMERIC(18,2);
ALTER TABLE crucible_entries ALTER COLUMN overall_fitness TYPE NUMERIC(18,8);

-- committees
ALTER TABLE committees ALTER COLUMN total_pnl TYPE NUMERIC(18,8);

COMMIT;

-- Verification queries (run after migration)
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'order_book_snapshots';
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'agents';
