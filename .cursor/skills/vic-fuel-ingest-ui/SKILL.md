---
name: vic-fuel-ingest-ui
description: >-
  Diagnoses when Fuel Up Plan charts show an older official ingest day while
  Data Analysis date controls look “newer”. Covers DB vs UI semantics, dual
  database checks, GitHub Actions ingest, and SQL cross-checks. Use when the
  user reports ingest day stuck (e.g. 10/04) on the main app but not on Data
  Analysis.
---

# Vic Fuel: ingest day stuck on Fuel Up vs Data Analysis

## What the product is doing (usually not a bug)

| Surface | What “date” means |
|--------|-------------------|
| **Fuel Up Plan → 7-day chart** | X-axis = **Melbourne calendar days that actually have rows** in `raw_prices` inside the last 7 days. If the last ingest was 10 Apr, the rightmost point is **10 Apr**. |
| **Data Analysis → As-of date** | A **calendar widget** capped at Melbourne “today”. You can pick **15 Apr** even when the latest row in the DB is still **10 Apr**. Snapshots use `ingested_at <= as_of`; they do **not** invent new official data after the last ingest. |

So “Analysis date can be updated” often means **the picker moved**, not that **`MAX(ingested_at)` moved**.

## When it *is* a real problem

1. **Two databases**: Streamlit Secrets point at DB **A**; GitHub Actions secrets point at DB **B**. Ingest updates B; the app reads A → chart stuck. **Fix:** align `POSTGRES_*` / `POSTGRES_DB_URL` between Streamlit Cloud and repo Actions secrets.
2. **Ingest not writing**: Actions was green but no inserts (addressed in `run_ingest.py` with non-zero exit + log line for max ingest day). **Fix:** red workflow → fix secrets/API; green → confirm log shows `latest Melbourne ingest calendar day`.
3. **SQL / timezone bug** (rare): `fetch_7_day_price_history` vs `fetch_max_ingest_date` disagree on the same connection. **Evidence:** NDJSON logs (see below).

## Runtime evidence (example from debug session `728b24`)

NDJSON logs (since removed) showed on the **same** `db_host`:

- `fetch_max_ingest_date` → `max_ingest_date`: **2026-04-10**
- `fetch_7_day_price_history` → `max_chart_day`: **2026-04-10**, `melbourne_today_py`: **2026-04-15**

So Fuel Up and Data Analysis agreed on the latest official ingest day; the chart was not “wrong” relative to `MAX(ingested_at)`.

## Agent workflow

1. Run locally with `.env`: compare `SELECT MAX((ingested_at AT TIME ZONE 'Australia/Melbourne')::date) FROM raw_prices` with the chart’s max `date` from `fetch_7_day_price_history` SQL (same connection as the app).
2. Compare `POSTGRES_*` host in Streamlit Secrets vs GitHub Actions secrets.
3. If (1) matches and both are old → explain date **picker** vs **data**; ingestion or wrong DB for Actions.
4. If chart max and SQL MAX differ → investigate timezone / filters (rare).

## Related files

- `src/app.py` — `fetch_7_day_price_history`, ingest captions
- `src/data_access/analysis.py` — `fetch_max_ingest_date`, `melbourne_today`
- `src/ingestion/run_ingest.py` — writes `raw_prices` / exit codes
- `.github/workflows/ingest.yml`
