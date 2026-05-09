-- Migration: 004_fitness_by_regime.sql
-- Purpose: Add per-regime fitness tracking to agents
-- Date: 2026-01-11
--
-- Run with: psql -h localhost -U coinswarm -d coinswarm -f migrations/004_fitness_by_regime.sql

-- ============================================================================
-- STEP 1: Add fitness_by_regime column
-- ============================================================================
-- Stores fitness scores broken down by canonical period types:
-- {"crash": 45.2, "bull": 72.1, "bear": 38.5, "sideways": 55.0, ...}

ALTER TABLE agents
ADD COLUMN IF NOT EXISTS fitness_by_regime JSONB DEFAULT '{}';

-- ============================================================================
-- STEP 2: Cap any uncapped Sharpe ratios in agents table
-- ============================================================================
-- Some agents may have extreme Sharpe values from before the cap was added

UPDATE agents
SET sharpe_ratio = GREATEST(-6, LEAST(6, sharpe_ratio))
WHERE sharpe_ratio IS NOT NULL AND (sharpe_ratio > 6 OR sharpe_ratio < -6);

SELECT 'Sharpe ratios capped:' as step, COUNT(*) as agents_fixed
FROM agents WHERE sharpe_ratio IS NOT NULL AND sharpe_ratio BETWEEN -6 AND 6;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Migration 004_fitness_by_regime complete!' as status;

SELECT
    COUNT(*) as total_agents,
    COUNT(fitness_by_regime) as with_regime_column
FROM agents;
