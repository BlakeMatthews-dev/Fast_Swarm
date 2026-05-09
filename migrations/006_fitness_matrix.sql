-- Migration: 006_fitness_matrix.sql
-- Purpose: Add 2D fitness matrix (regime × timeframe) for heatmap display
-- Date: 2026-01-12
--
-- Run with: psql -h localhost -U coinswarm -d coinswarm -f migrations/006_fitness_matrix.sql

-- ============================================================================
-- STEP 1: Add fitness_matrix column to agents
-- ============================================================================
-- Stores 2D fitness matrix: regime → timeframe → fitness score
-- Example: {"crash": {"1m": 45.2, "1h": 52.1}, "bull": {"1m": 84.0, "15m": 70.0}}

ALTER TABLE agents
ADD COLUMN IF NOT EXISTS fitness_matrix JSONB DEFAULT '{}';

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Migration 006_fitness_matrix complete!' as status;

SELECT
    COUNT(*) as total_agents,
    COUNT(fitness_matrix) as with_matrix_column
FROM agents;
