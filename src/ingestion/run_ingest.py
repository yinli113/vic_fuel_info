import os
import sys
import time
import uuid
import logging
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from data_access.pg_connect import connect_from_database_url

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
DB_URL = os.environ.get("POSTGRES_DB_URL")

def get_db_connection():
    if not DB_URL:
        raise ValueError("POSTGRES_DB_URL environment variable is not set")
    return connect_from_database_url(DB_URL)

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

def process_and_save_data(data):
    if not data or 'fuelPriceDetails' not in data:
        logging.info("No data to process.")
        return
        
    stations = []
    prices = []
    
    for item in data['fuelPriceDetails']:
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
            prices.append((
                station_id,
                fuel.get('fuelType'),
                fuel.get('price'),
                fuel.get('isAvailable'),
                fuel.get('updatedAt')
            ))
            
    if not stations:
        logging.info("No valid stations found in data.")
        return

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
        
        # Insert Prices
        price_query = """
            INSERT INTO raw_prices (station_id, fuel_type, price, is_available, updated_at)
            VALUES %s
        """
        execute_values(cursor, price_query, prices)
        logging.info(f"Inserted {len(prices)} price records.")
        
        conn.commit()
        cursor.close()
        conn.close()
        logging.info("Data successfully saved to database.")
    except Exception as e:
        logging.error(f"Database error: {e}")

if __name__ == "__main__":
    logging.info("Starting ingestion job...")
    data = fetch_fuel_data()
    if data:
        process_and_save_data(data)
    logging.info("Ingestion job completed.")