-- Setup PostgreSQL Database Schema for Victoria Fuel App

-- 1. Raw Stations Table (Official Data)
CREATE TABLE IF NOT EXISTS raw_stations (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    brand_id VARCHAR(50),
    address VARCHAR(400) NOT NULL,
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    contact_phone VARCHAR(20),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- 2. Raw Prices Table (Official Data - Append Only for historical tracking)
CREATE TABLE IF NOT EXISTS raw_prices (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) REFERENCES raw_stations(id),
    fuel_type VARCHAR(10) NOT NULL,
    price DECIMAL(6, 1),
    is_available BOOLEAN NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying latest prices quickly
CREATE INDEX IF NOT EXISTS idx_raw_prices_station_fuel ON raw_prices (station_id, fuel_type, updated_at DESC);

-- 3. User Reports Table (Real-time Community Data)
CREATE TABLE IF NOT EXISTS user_reports (
    report_id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) REFERENCES raw_stations(id),
    fuel_type VARCHAR(10) NOT NULL,
    reported_price DECIMAL(6, 1),
    is_available BOOLEAN NOT NULL,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_session_id VARCHAR(100), -- For basic tracking/trust scoring
    confidence_score INTEGER DEFAULT 0
);

-- Index for community data
CREATE INDEX IF NOT EXISTS idx_user_reports_station_fuel ON user_reports (station_id, fuel_type, reported_at DESC);

-- 4. Materialized View / View for Hybrid Current Prices
-- Merges official data and community data, taking the most recent one.
CREATE OR REPLACE VIEW mart_hybrid_current_prices AS
WITH latest_official AS (
    SELECT DISTINCT ON (station_id, fuel_type)
        station_id,
        fuel_type,
        price,
        is_available,
        updated_at AS source_updated_at,
        'official' AS data_source
    FROM raw_prices
    ORDER BY station_id, fuel_type, updated_at DESC
),
latest_community AS (
    SELECT DISTINCT ON (station_id, fuel_type)
        station_id,
        fuel_type,
        reported_price AS price,
        is_available,
        reported_at AS source_updated_at,
        'community' AS data_source
    FROM user_reports
    ORDER BY station_id, fuel_type, reported_at DESC
),
combined AS (
    SELECT * FROM latest_official
    UNION ALL
    SELECT * FROM latest_community
),
ranked_combined AS (
    SELECT DISTINCT ON (station_id, fuel_type)
        station_id,
        fuel_type,
        price,
        is_available,
        source_updated_at,
        data_source
    FROM combined
    ORDER BY station_id, fuel_type, source_updated_at DESC
)
SELECT 
    r.station_id,
    s.name AS station_name,
    s.brand_id,
    s.address,
    s.latitude,
    s.longitude,
    r.fuel_type,
    r.price,
    r.is_available,
    r.source_updated_at,
    r.data_source
FROM ranked_combined r
JOIN raw_stations s ON r.station_id = s.id;
