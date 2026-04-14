-- Run SECOND (after 01_indexes… succeeds).
-- Extends session timeout where the role allows it (Supabase may still cap the editor).
SET statement_timeout = '15min';

CREATE OR REPLACE VIEW mart_hybrid_current_prices AS
WITH latest_official AS (
    SELECT DISTINCT ON (station_id, fuel_type)
        station_id,
        fuel_type,
        price,
        is_available,
        updated_at AS source_updated_at,
        ingested_at AS sort_ts,
        'official' AS data_source
    FROM raw_prices
    ORDER BY station_id, fuel_type, ingested_at DESC, updated_at DESC
),
latest_community AS (
    SELECT DISTINCT ON (station_id, fuel_type)
        station_id,
        fuel_type,
        reported_price AS price,
        is_available,
        reported_at AS source_updated_at,
        reported_at AS sort_ts,
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
    ORDER BY station_id, fuel_type, sort_ts DESC
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
