import os
import sys

_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from data_access.pg_connect import connect_postgres, postgres_connection_cache_key

# Load env manually
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

if not postgres_connection_cache_key():
    print(
        "Error: Set POSTGRES_DB_URL in .env, or POSTGRES_HOST + POSTGRES_USER + POSTGRES_PASSWORD."
    )
    sys.exit(1)

schema_path = os.path.join(os.path.dirname(__file__), 'src', 'data_access', 'schema.sql')

try:
    print("Connecting to Supabase...")
    conn = connect_postgres()
    cursor = conn.cursor()
    
    print("Executing schema.sql...")
    with open(schema_path, 'r') as file:
        schema_sql = file.read()
        
    cursor.execute(schema_sql)
    conn.commit()
    
    cursor.close()
    conn.close()
    print("Success! All tables and views created in Supabase.")
except Exception as e:
    print(f"Failed to setup database: {e}")
