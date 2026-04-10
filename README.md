# TL;DR

Streamlit + Postgres hybrid fuel app for Victoria. Run locally with `.env` from `.env.example`; put the app on the internet with [Streamlit Community Cloud](https://streamlit.io/cloud) and a hosted database — see [`docs/deployment.md`](docs/deployment.md).

# Victoria Fuel Hybrid Data App

A low-cost, public-interest hybrid data app that helps Victorians compare fuel prices, spot likely outages, and analyze price trends.

This project combines:
1. **Official 24-hour Delayed Data**: Sourced from the Service Victoria Fair Fuel Open Data API.
2. **Real-time Crowdsourced Data**: Community reports submitted directly through the app to bridge the 24-hour delay gap.

## Features
- **Map Integration**: View stations, prices, and outages visually.
- **Commuter Route Optimization**: Find the cheapest fuel along a route from A to B.
- **Price Cycle Forecaster**: Historical trends to predict whether to buy now or wait.
- **Hourly Suburb Trends**: Real-time dashboard for local price changes and outages.
- **Data Trust Scoring**: Confidence scores for community reports to ensure reliability.

## Architecture
- **Frontend**: Streamlit
- **Database**: PostgreSQL (with PostGIS for route calculations if needed)
- **Ingestion**: GitHub Actions (scheduled batch processing)

## Setup
See `.env.example` for required environment variables (create from your own secrets locally).

## Deploy (public URL)
Step-by-step: [`docs/deployment.md`](docs/deployment.md) — GitHub repo, Streamlit Cloud main file `src/app.py`, Secrets for `POSTGRES_DB_URL`, and internet-accessible Postgres (e.g. Supabase/Neon).

### Optional: AI narrative on Data Analysis
The **Data Analysis** page can generate a markdown briefing via **Gemini** or **OpenAI** from dashboard aggregates only. Configuration, env vars, and architecture are documented in [`docs/ai-dashboard-report.md`](docs/ai-dashboard-report.md).

## Attribution
Contains data from the Service Victoria Fair Fuel Open Data API. Official prices are delayed by approximately 24 hours.