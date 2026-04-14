-- Run this FIRST in Supabase SQL Editor as its own query (click Run once).
-- Helps DISTINCT ON (latest_official) on large raw_prices; may take 1–5+ minutes.
-- user_reports already has idx_user_reports_station_fuel (station_id, fuel_type, reported_at DESC) from schema.
-- If this times out, use psql / Supabase CLI, or ask Supabase support about editor limits.

CREATE INDEX IF NOT EXISTS idx_raw_prices_mart_latest_official
    ON raw_prices (station_id, fuel_type, ingested_at DESC, updated_at DESC);
