"""
Queries for the Data Analysis page: official raw_prices snapshots by ingest date (Melbourne TZ).
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
from dotenv import load_dotenv

from data_access.pg_connect import connect_postgres, is_pooler_supabase_environ
from data_access.streamlit_env import (
    hydrate_secrets_into_environ,
    is_supabase_direct_db_url,
    looks_like_ipv6_routing_failure,
    streamlit_warn_supabase_direct_url,
)

load_dotenv()

AU_TZ = "Australia/Melbourne"


def get_db_connection():
    hydrate_secrets_into_environ()
    db_url = os.environ.get("POSTGRES_DB_URL")
    if not db_url:
        return None
    try:
        return connect_postgres()
    except ValueError as e:
        try:
            import streamlit as st

            st.error(str(e))
        except Exception:
            pass
        return None
    except Exception as e:
        err = str(e).lower()
        if "password authentication failed" in err and is_pooler_supabase_environ():
            try:
                import streamlit as st

                st.info(
                    "Use the **Database password** from Supabase → Project Settings → Database, "
                    "or set `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` in Secrets "
                    "(plain password, no URL encoding)."
                )
            except Exception:
                pass
        if is_supabase_direct_db_url(db_url) and looks_like_ipv6_routing_failure(e):
            streamlit_warn_supabase_direct_url()
        return None


def fetch_max_ingest_date(conn) -> date | None:
    q = f"""
        SELECT MAX((ingested_at AT TIME ZONE '{AU_TZ}')::date) AS d
        FROM raw_prices
    """
    df = pd.read_sql(q, conn)
    if df.empty or pd.isna(df.iloc[0]["d"]):
        return None
    return df.iloc[0]["d"]


def fetch_state_trend_7d(conn, fuel_type: str, end_date: date) -> pd.DataFrame:
    """One row per day in [end_date-6, end_date]: avg/median/spread, outage rate."""
    q = f"""
        SELECT d.snap_day AS date,
               AVG(sub.price) FILTER (
                   WHERE sub.is_available AND sub.price IS NOT NULL
               ) AS avg_price,
               MIN(sub.price) FILTER (
                   WHERE sub.is_available AND sub.price IS NOT NULL
               ) AS min_price,
               MAX(sub.price) FILTER (
                   WHERE sub.is_available AND sub.price IS NOT NULL
               ) AS max_price,
               percentile_cont(0.1) WITHIN GROUP (ORDER BY (
                   CASE
                       WHEN sub.is_available AND sub.price IS NOT NULL THEN sub.price
                   END
               )) AS p10_price,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (
                   CASE
                       WHEN sub.is_available AND sub.price IS NOT NULL THEN sub.price
                   END
               )) AS median_price,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY (
                   CASE
                       WHEN sub.is_available AND sub.price IS NOT NULL THEN sub.price
                   END
               )) AS p90_price,
               AVG(
                   CASE
                       WHEN sub.is_available IS TRUE THEN 0.0
                       WHEN sub.is_available IS FALSE THEN 1.0
                   END
               ) AS outage_rate,
               COUNT(sub.station_id) AS n_stations
        FROM generate_series(
            %s::date - interval '6 days',
            %s::date,
            interval '1 day'
        ) AS d(snap_day)
        LEFT JOIN LATERAL (
            SELECT DISTINCT ON (rp.station_id)
                rp.station_id,
                rp.price,
                rp.is_available
            FROM raw_prices rp
            JOIN raw_stations s ON s.id = rp.station_id
            WHERE rp.fuel_type = %s
              AND (rp.ingested_at AT TIME ZONE '{AU_TZ}')::date <= d.snap_day::date
            ORDER BY rp.station_id, rp.ingested_at DESC, rp.updated_at DESC
        ) sub ON true
        GROUP BY d.snap_day
        ORDER BY d.snap_day
    """
    return pd.read_sql(q, conn, params=(end_date, end_date, fuel_type))


def fetch_snapshot_station_rows(conn, fuel_type: str, as_of_date: date) -> pd.DataFrame:
    """Latest official row per station for fuel_type as of end of as_of_date (ingest-time)."""
    q = f"""
        SELECT DISTINCT ON (rp.station_id)
            rp.station_id,
            s.name AS station_name,
            s.brand_id,
            s.address,
            s.latitude,
            s.longitude,
            rp.price,
            rp.is_available
        FROM raw_prices rp
        JOIN raw_stations s ON s.id = rp.station_id
        WHERE rp.fuel_type = %s
          AND (rp.ingested_at AT TIME ZONE '{AU_TZ}')::date <= %s::date
        ORDER BY rp.station_id, rp.ingested_at DESC, rp.updated_at DESC
    """
    return pd.read_sql(q, conn, params=(fuel_type, as_of_date))
