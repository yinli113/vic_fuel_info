import os
import sys
import time
import uuid
import logging
import requests
import psycopg2
from datetime import datetime, timezone
from psycopg2.extras import execute_values

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from data_access.pg_connect import connect_postgres, postgres_connection_cache_key

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "https://api.fuel.service.vic.gov.au/open-data/v1/fuel/prices"

# Load env manually if running locally outside of GitHub Actions
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

CONSUMER_ID = os.environ.get("SERVO_SAVER_API_CONSUMER_ID")


def get_db_connection():
    if not postgres_connection_cache_key():
        raise ValueError(
            "Database not configured: set POSTGRES_DB_URL or POSTGRES_HOST+POSTGRES_USER+POSTGRES_PASSWORD"
        )
    return connect_postgres()

def fetch_fuel_data():
    if not CONSUMER_ID or CONSUMER_ID == "your_api_consumer_id_here":
        logging.warning("SERVO_SAVER_API_CONSUMER_ID is not set or invalid. Skipping ingestion.")
        return None
    
    headers = {
        "User-Agent": "VicFuelHybridApp/1.0",
        "x-consumer-id": CONSUMER_ID,
        "x-transactionid": str(uuid.uuid4())
    }
    
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"Fetching data from API (Attempt {attempt + 1})")
            response = requests.get(API_URL, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logging.error("Rate limit exceeded (429).")
                break
            elif response.status_code in [500, 503, 504]:
                logging.warning(f"Server error {response.status_code}. Retrying...")
                time.sleep(10)
                continue
            else:
                logging.error(f"Unexpected error: {response.status_code} - {response.text}")
                break
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            time.sleep(10)
            
    return None

def process_and_save_data(data) -> bool:
    """Return True if new price rows were committed. False → caller should fail the job (e.g. GitHub Actions)."""
    if not data or "fuelPriceDetails" not in data:
        logging.error("API payload missing fuelPriceDetails — nothing to insert.")
        return False

    stations = []
    prices = []

    for item in data["fuelPriceDetails"]:
        station = item.get('fuelStation', {})
        station_id = station.get('id')
        
        if not station_id:
            continue
            
        location = station.get('location', {})
        stations.append((
            station_id,
            station.get('name'),
            station.get('brandId'),
            station.get('address'),
            location.get('latitude'),
            location.get('longitude'),
            station.get('contactPhone'),
            item.get('updatedAt')
        ))
        
        for fuel in item.get('fuelPrices', []):
            prices.append(
                (
                    station_id,
                    fuel.get('fuelType'),
                    fuel.get('price'),
                    fuel.get('isAvailable'),
                    fuel.get('updatedAt'),
                )
            )
            
    if not stations:
        logging.error("No valid stations in API payload — nothing to insert.")
        return False

    if not prices:
        logging.error("No price rows in API payload — nothing to insert.")
        return False

    # One wall-clock time for this snapshot so MAX(ingested_at) always moves on successful runs
    # (avoids relying on DB default alone if the instance ever misbehaves).
    ingest_ts = datetime.now(timezone.utc)
    rows_6 = [(*t, ingest_ts) for t in prices]

    # Database insertion
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Upsert Stations
        station_query = """
            INSERT INTO raw_stations (id, name, brand_id, address, latitude, longitude, contact_phone, updated_at)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                brand_id = EXCLUDED.brand_id,
                address = EXCLUDED.address,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                contact_phone = EXCLUDED.contact_phone,
                updated_at = EXCLUDED.updated_at
        """
        execute_values(cursor, station_query, stations)
        logging.info(f"Upserted {len(stations)} stations.")
        
        # Insert Prices (explicit ingested_at so each run advances MAX(ingested_at))
        price_query = """
            INSERT INTO raw_prices (station_id, fuel_type, price, is_available, updated_at, ingested_at)
            VALUES %s
        """
        logging.info("Batch ingested_at (UTC) for this run: %s", ingest_ts.isoformat())
        execute_values(cursor, price_query, rows_6)
        logging.info(f"Inserted {len(rows_6)} price records.")

        conn.commit()
        cursor.execute(
            """
            SELECT MAX((ingested_at AT TIME ZONE 'Australia/Melbourne')::date)
            FROM raw_prices
            """
        )
        max_ingest_day = cursor.fetchone()[0]
        logging.info(
            "After commit: raw_prices latest Melbourne ingest calendar day = %s (MAX ingested_at in Melbourne).",
            max_ingest_day,
        )
        cursor.close()
        conn.close()
        logging.info("Data successfully saved to database.")
        return True
    except Exception as e:
        logging.error("Database error: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.info("Starting ingestion job...")
    data = fetch_fuel_data()
    if data is None:
        logging.error(
            "Ingestion aborted: API unreachable / bad response, or SERVO_SAVER_API_CONSUMER_ID missing. "
            "Fix secrets and re-run; this exit code is non-zero so GitHub Actions does not show false green."
        )
        sys.exit(1)
    if not process_and_save_data(data):
        logging.error("Ingestion did not commit new price rows — see errors above.")
        sys.exit(1)
    logging.info("Ingestion job completed successfully.")