-- Migration: 002b_fix_hypertables.sql
-- Fix TimescaleDB hypertables: decompress → alter → recompress
-- WARNING: This can take several minutes for large tables!

-- ============================================================================
-- FUNDING_RATES (small table, quick)
-- ============================================================================
DO $$
DECLARE
    chunk RECORD;
BEGIN
    RAISE NOTICE 'Decompressing funding_rates chunks...';
    FOR chunk IN
        SELECT chunk_schema || '.' || chunk_name as chunk_full_name
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'funding_rates' AND is_compressed = true
    LOOP
        EXECUTE format('SELECT decompress_chunk(%L)', chunk.chunk_full_name);
    END LOOP;
END $$;

ALTER TABLE funding_rates ALTER COLUMN mark_price TYPE NUMERIC(18,8);
ALTER TABLE funding_rates ALTER COLUMN index_price TYPE NUMERIC(18,8);
ALTER TABLE funding_rates ALTER COLUMN open_interest TYPE NUMERIC(24,8);

-- Recompress (or let policy handle it)
SELECT compress_chunk(chunk_schema || '.' || chunk_name)
FROM timescaledb_information.chunks
WHERE hypertable_name = 'funding_rates' AND is_compressed = false;

-- ============================================================================
-- AGENT_TRADES (2.1M rows - medium)
-- ============================================================================
DO $$
DECLARE
    chunk RECORD;
BEGIN
    RAISE NOTICE 'Decompressing agent_trades chunks...';
    FOR chunk IN
        SELECT chunk_schema || '.' || chunk_name as chunk_full_name
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'agent_trades' AND is_compressed = true
    LOOP
        EXECUTE format('SELECT decompress_chunk(%L)', chunk.chunk_full_name);
    END LOOP;
END $$;

ALTER TABLE agent_trades ALTER COLUMN entry_price TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN exit_price TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN size TYPE NUMERIC(24,8);
ALTER TABLE agent_trades ALTER COLUMN pnl TYPE NUMERIC(18,8);
ALTER TABLE agent_trades ALTER COLUMN fees TYPE NUMERIC(18,8);

SELECT compress_chunk(chunk_schema || '.' || chunk_name)
FROM timescaledb_information.chunks
WHERE hypertable_name = 'agent_trades' AND is_compressed = false;

-- ============================================================================
-- ENHANCED_CANDLES (5.2M rows - LARGE, will take time!)
-- ============================================================================
DO $$
DECLARE
    chunk RECORD;
    i INTEGER := 0;
BEGIN
    RAISE NOTICE 'Decompressing enhanced_candles chunks (this may take a while)...';
    FOR chunk IN
        SELECT chunk_schema || '.' || chunk_name as chunk_full_name
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'enhanced_candles' AND is_compressed = true
    LOOP
        i := i + 1;
        IF i % 10 = 0 THEN
            RAISE NOTICE 'Decompressed % chunks...', i;
        END IF;
        EXECUTE format('SELECT decompress_chunk(%L)', chunk.chunk_full_name);
    END LOOP;
    RAISE NOTICE 'Decompressed % total chunks', i;
END $$;

ALTER TABLE enhanced_candles ALTER COLUMN open TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN high TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN low TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN close TYPE NUMERIC(18,8);
ALTER TABLE enhanced_candles ALTER COLUMN volume TYPE NUMERIC(24,8);

-- Recompress all chunks
DO $$
DECLARE
    chunk RECORD;
    i INTEGER := 0;
BEGIN
    RAISE NOTICE 'Recompressing enhanced_candles chunks...';
    FOR chunk IN
        SELECT chunk_schema || '.' || chunk_name as chunk_full_name
        FROM timescaledb_information.chunks
        WHERE hypertable_name = 'enhanced_candles' AND is_compressed = false
    LOOP
        i := i + 1;
        IF i % 10 = 0 THEN
            RAISE NOTICE 'Compressed % chunks...', i;
        END IF;
        EXECUTE format('SELECT compress_chunk(%L)', chunk.chunk_full_name);
    END LOOP;
    RAISE NOTICE 'Compressed % total chunks', i;
END $$;

-- Verify
SELECT 'Migration complete!' as status;
