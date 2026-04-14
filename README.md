# TL;DR

**Vic Fuel Info** is a free, Streamlit-based app for Victorian drivers: compare **official** Servo Saver fuel prices with a **hybrid** Postgres backend, explore stations on a map, and dig into trends on a **Data Analysis** page (optional **Gemini / OpenAI** narrative). Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) + [Supabase](https://supabase.com/) (or any hosted Postgres). See [docs/deployment.md](docs/deployment.md).

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

---

## Why this project

Victoria publishes **Fair Fuel** open data via the Servo Saver API. Official snapshots are useful but can lag real-world changes. This MVP keeps the stack **lean**: **Postgres** + **scheduled GitHub Actions** ingestion (no Kafka), **Streamlit** for the UI, and room for **community-sourced** signals in the data model as you grow.

## What you can do today

| Area | Capability |
|------|----------------|
| **Fuel Up Plan** (`src/app.py`) | Pick fuel type, set location (suburb/postcode, optional device GPS, or Melbourne-centred default), see **cheapest / closest / best-value** stations within **10 km** on an interactive map. |
| **Trends** | State-wide **average prices** and **7-day history** under the map. |
| **Data Analysis** (`src/pages/…`) | Official **snapshot** views: maps, charts, filters by fuel and ingest date; optional **AI markdown briefing** from aggregates only ([docs/ai-dashboard-report.md](docs/ai-dashboard-report.md)). |

> **Data freshness:** Official prices follow the API’s rules and are **delayed by ~24 hours**. Treat outputs as indicative, not real-time trading signals.

## Architecture

```
Servo Saver API  ──►  GitHub Actions (ingest)  ──►  PostgreSQL (Supabase / Neon / …)
                                                        ▲
Streamlit app  ───────────────────────────────────────┘
  • Main: src/app.py
  • Pages: src/pages/
```

- **Ingestion:** `src/ingestion/run_ingest.py` — triggered by [`.github/workflows/ingest.yml`](.github/workflows/ingest.yml).
- **DB access:** `src/data_access/` — SQL helpers, schema, optional AI report module.
- **Connections:** `POSTGRES_DB_URL` **or** discrete `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` (better for special characters in passwords). See [`.env.example`](.env.example).

## Quick start (local)

```bash
git clone https://github.com/yinli113/vic_fuel_info.git
cd vic_fuel_info
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: database URL, SERVO_SAVER_API_CONSUMER_ID, optional GEMINI_API_KEY / OPENAI_API_KEY
python setup_db.py          # once, against your DB
streamlit run src/app.py
```

Open the sidebar to switch to **Data Analysis** when `src/pages/` is present.

## Deploy (public URL)

1. Push this repo to **GitHub**.
2. **Streamlit Cloud:** new app → repo → main file **`src/app.py`**.
3. **Secrets:** database variables (URL or discrete), optional API keys — [docs/deployment.md](docs/deployment.md).
4. **Supabase session pooler** (IPv4-friendly) is recommended for Cloud; see deployment doc for the `db.*` vs `pooler.supabase.com` note.

**GitHub Actions:** add repository secrets `POSTGRES_DB_URL` **or** discrete `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` (same as Streamlit), plus `SERVO_SAVER_API_CONSUMER_ID`. The app **does not** call the Vic API; only this workflow writes new official rows—see [docs/deployment.md](docs/deployment.md#3-database-and-ingestion).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `POSTGRES_DB_URL` **or** `POSTGRES_HOST` + `POSTGRES_USER` + `POSTGRES_PASSWORD` (+ optional port/db/ssl) | Database |
| `SERVO_SAVER_API_CONSUMER_ID` | Fair Fuel / Servo Saver API (ingestion) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `OPENAI_API_KEY` | Optional AI narrative on Data Analysis |

Full list and comments: [`.env.example`](.env.example). **Never commit `.env`** — it is gitignored.

## Repository layout

```
src/
  app.py                 # Main “Fuel Up Plan” experience
  pages/                 # Multipage Streamlit entries
  data_access/           # Queries, schema, pg_connect, AI report
  ingestion/             # Batch load from Servo Saver API
.github/workflows/      # Scheduled ingest
docs/                    # Deployment + AI report design notes
```

## Attribution

Contains data from the **Service Victoria Fair Fuel Open Data API** (Servo Saver). Use is subject to their terms; official price series are **approximately 24 hours delayed**.

## License

No `LICENSE` file is bundled yet; add one (e.g. MIT) if you open-source formally.

---

**Author note:** Built as a low-cost, public-interest MVP: free-tier hosting, direct Postgres writes, and hyper-local value for Victorian drivers.
