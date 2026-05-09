-- Migration: 003_patterns_cleanup.sql
-- Purpose: Fix data quality issues in patterns table
-- Date: 2026-01-10
--
-- Run with: psql -h localhost -U coinswarm -d coinswarm -f migrations/003_patterns_cleanup.sql

-- ============================================================================
-- STEP 1: Normalize win_rate to decimal (0-1)
-- ============================================================================
-- Some patterns store win_rate as percentage (0-100), others as decimal (0-1)
-- Standardize to decimal format for consistency

UPDATE patterns
SET win_rate = win_rate / 100.0
WHERE win_rate > 1;

SELECT 'Win rate normalized:' as step,
       COUNT(*) as patterns_updated
FROM patterns WHERE win_rate IS NOT NULL AND win_rate <= 1;

-- ============================================================================
-- STEP 2: Cap impossible drawdowns at 100%
-- ============================================================================
-- Max drawdown by definition cannot exceed 100% (total loss of capital)
-- Values > 100% indicate calculation bugs

UPDATE patterns
SET max_drawdown_pct = 100.0
WHERE max_drawdown_pct > 100;

SELECT 'Drawdowns capped:' as step,
       COUNT(*) as patterns_fixed
FROM patterns WHERE max_drawdown_pct IS NOT NULL AND max_drawdown_pct > 100;

-- ============================================================================
-- STEP 3: Cap extreme Sharpe ratios to ±6
-- ============================================================================
-- Sharpe > 6 or < -6 indicates calculation anomalies (low std deviation)
-- New calculations are now capped in code; this fixes historical data

UPDATE patterns
SET sharpe_ratio = GREATEST(-6, LEAST(6, sharpe_ratio))
WHERE sharpe_ratio IS NOT NULL AND (sharpe_ratio > 6 OR sharpe_ratio < -6);

SELECT 'Sharpe ratios capped:' as step,
       COUNT(*) as patterns_fixed
FROM patterns WHERE sharpe_ratio IS NOT NULL AND (sharpe_ratio > 6 OR sharpe_ratio < -6);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Final verification' as check_type;

SELECT
    'win_rate' as metric,
    MIN(win_rate) as min_val,
    MAX(win_rate) as max_val,
    COUNT(*) as non_null_count
FROM patterns WHERE win_rate IS NOT NULL
UNION ALL
SELECT
    'max_drawdown_pct',
    MIN(max_drawdown_pct),
    MAX(max_drawdown_pct),
    COUNT(*)
FROM patterns WHERE max_drawdown_pct IS NOT NULL
UNION ALL
SELECT
    'sharpe_ratio',
    MIN(sharpe_ratio),
    MAX(sharpe_ratio),
    COUNT(*)
FROM patterns WHERE sharpe_ratio IS NOT NULL;

SELECT 'Migration 003_patterns_cleanup complete!' as status;
