# Skill: VIC Fuel MVP Development

## Description
Guidelines and domain knowledge for developing the Victoria Fuel Hybrid Data App.

## Domain Context
- **Data Source**: Service Victoria Fair Fuel Open Data API.
- **Data Nature**: Official data is delayed by ~24 hours. The app supplements this with real-time community crowdsourced reports.
- **API Constraints**: Requires `x-consumer-id` and unique `x-transactionid`. Strict rate limit of 10 requests / 60 seconds. Handle 500/504 errors with retries.

## Architecture
- **Frontend**: Streamlit
- **Hosting**: Streamlit Cloud
- **Database**: PostgreSQL (Supabase/Neon)
- **Ingestion**: GitHub Actions (Scheduled)

## Scale-up Triggers
Only revisit architecture (e.g., adding Kafka or a queue) if:
1. Real-time inserts from users overwhelm Postgres.
2. We need to push real-time notifications to users.
3. Scheduled ingestion causes timeout issues that require decoupled processing.

## Best Practices
- Always prioritize lean, low-cost solutions.
- Ensure community data is clearly separated and marked differently from official delayed data.
- Favor direct PostgreSQL views/queries for merging hybrid data over complex application-side merges.