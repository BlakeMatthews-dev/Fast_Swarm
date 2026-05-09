-- Migration: 005_patterns_fitness_by_regime.sql
-- Purpose: Add per-regime fitness tracking to patterns
-- Date: 2026-01-12
--
-- Run with: psql -h localhost -U coinswarm -d coinswarm -f migrations/005_patterns_fitness_by_regime.sql

-- ============================================================================
-- STEP 1: Add fitness_by_regime column to patterns
-- ============================================================================
-- Stores fitness scores broken down by regime:
-- {"crash": {"fitness": 45.2, "trades": 120, "win_rate": 0.58}, ...}

ALTER TABLE patterns
ADD COLUMN IF NOT EXISTS fitness_by_regime JSONB DEFAULT '{}';

-- ============================================================================
-- STEP 2: Add best_regime tracking columns
-- ============================================================================
-- Track which regime the pattern performs best in

ALTER TABLE patterns
ADD COLUMN IF NOT EXISTS best_regime VARCHAR(50);

ALTER TABLE patterns
ADD COLUMN IF NOT EXISTS best_regime_fitness FLOAT;

-- ============================================================================
-- STEP 3: Cap any uncapped Sharpe ratios in patterns table
-- ============================================================================
-- Some patterns may have extreme Sharpe values from before the cap was added

UPDATE patterns
SET sharpe_ratio = GREATEST(-6, LEAST(6, sharpe_ratio))
WHERE sharpe_ratio IS NOT NULL AND (sharpe_ratio > 6 OR sharpe_ratio < -6);

SELECT 'Patterns Sharpe ratios capped:' as step, COUNT(*) as patterns_fixed
FROM patterns WHERE sharpe_ratio IS NOT NULL AND sharpe_ratio BETWEEN -6 AND 6;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Migration 005_patterns_fitness_by_regime complete!' as status;

SELECT
    COUNT(*) as total_patterns,
    COUNT(fitness_by_regime) as with_regime_column,
    COUNT(best_regime) as with_best_regime
FROM patterns;
