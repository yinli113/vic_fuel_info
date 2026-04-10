import os
import psycopg2
import sys

# Load env manually
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

db_url = os.environ.get("POSTGRES_DB_URL")
if not db_url or "[YOUR-PASSWORD]" in db_url:
    print("Error: Please replace [YOUR-PASSWORD] in .env with your actual password!")
    sys.exit(1)

schema_path = os.path.join(os.path.dirname(__file__), 'src', 'data_access', 'schema.sql')

try:
    print("Connecting to Supabase...")
    conn = psycopg2.connect(db_url)
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
