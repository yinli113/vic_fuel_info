# MVP Architecture

## Core Components
- **Data Ingestion**: A scheduled GitHub Actions workflow that queries the Fair Fuel Open Data API (rate-limited, 24-hr delayed data) and writes into `raw_` tables in PostgreSQL.
- **Data Storage**: PostgreSQL database holding both raw API data and real-time user crowdsourced reports.
- **Frontend & Business Logic**: Streamlit Cloud app that directly queries the PostgreSQL database, merging the raw API data and crowdsourced reports to present the most current view of fuel prices and station health to the user.

## Data Flow
1. **Official Data**: Service Victoria API -> GitHub Action -> Postgres (`raw_prices`, `raw_stations`)
2. **Community Data**: Streamlit App -> Postgres (`user_reports`)
3. **App Read**: Postgres -> Streamlit App (via `mart_hybrid_current_prices` views)

## Scale-Up Triggers
- Introduce background workers/queues if the volume of real-time inserts overwhelms Postgres.
- Add Confluent Kafka only if multiple distinct downstream consumers need real-time streaming notifications (e.g., push alerts, SMS notifications).