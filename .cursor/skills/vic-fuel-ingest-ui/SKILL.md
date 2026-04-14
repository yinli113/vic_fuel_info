---
name: vic-fuel-ingest-ui
description: >-
  Diagnoses when Fuel Up Plan charts show an older official ingest day while
  Data Analysis date controls look “newer”. Covers DB vs UI semantics, dual
  database checks, GitHub Actions ingest, and NDJSON debug logs in
  .cursor/debug-728b24.log. Use when the user reports ingest day stuck (e.g.
  10/04) on the main app but not on Data Analysis.
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

## Runtime evidence (debug session)

With current `main`, these code paths append one NDJSON line per call to:

`/.cursor/debug-728b24.log` (repo root `.cursor/`)

- `app.py` → `fetch_7_day_price_history` → `max_chart_day`, `row_count`, `melbourne_today_py`, `db_host`
- `analysis.py` → `fetch_max_ingest_date` → `max_ingest_date`, `db_host`

**Interpretation**

- If `max_chart_day` **equals** `max_ingest_date` and both are old → data really ends there; fix **ingest** or **DB routing**, not the chart formula.
- If they **differ** on the same run → investigate query/timezone (hypothesis not yet confirmed in the wild).

## Agent workflow

1. Read `.cursor/debug-728b24.log` after a local `streamlit run src/app.py` reproduction (Fuel Up + open Data Analysis once).
2. Compare `db_host` across log lines vs user’s Supabase project host.
3. If hosts match and dates match → explain picker vs chart; optionally improve UI copy only with user consent.
4. If hosts differ → instruct user to unify secrets; do not “fix” chart SQL speculatively.

## Related files

- `src/app.py` — `fetch_7_day_price_history`
- `src/data_access/analysis.py` — `fetch_max_ingest_date`, `melbourne_today`
- `src/ingestion/run_ingest.py` — writes `raw_prices` / exit codes
- `.github/workflows/ingest.yml`
- `src/data_access/debug_agent_log.py` — instrumentation sink (remove after confirmed fix if product owner requests)
