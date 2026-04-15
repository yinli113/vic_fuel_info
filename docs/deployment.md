# TL;DR

Host the Streamlit app on [Streamlit Community Cloud](https://streamlit.io/cloud) (free tier): push this repo to GitHub, connect it in Cloud, set **Main file path** to `src/app.py`, add **Secrets** for your hosted Postgres URL and optional API keys, then share the public `*.streamlit.app` URL. Your database must be reachable from the internet (Supabase, Neon, or similar), not `localhost`.

# Deploy Vic Fuel Info (Streamlit)

## 1. Prerequisites

- **GitHub**: This project in a GitHub repository (Streamlit Cloud deploys from GitHub).
- **Internet-accessible Postgres**: e.g. [Supabase](https://supabase.com/) or [Neon](https://neon.tech/) free tier. Copy the **connection string** (often `postgresql://...`).
- **Optional**: Servo Saver API consumer ID, Gemini key — same as local `.env` (see `.env.example`).

## 2. Streamlit Community Cloud

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub.
2. **New app** → pick this repo, branch (usually `main`), and set:
   - **Main file path**: `src/app.py`
3. **Advanced settings** → **Python version** to match your project (3.11+ recommended if you use that locally).
4. **Secrets** (App settings → Secrets). Example TOML:

```toml
POSTGRES_DB_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
# Optional:
# SERVO_SAVER_API_CONSUMER_ID = "..."
# GEMINI_API_KEY = "..."
```

The app maps these into `os.environ` on startup (see `src/data_access/streamlit_env.py`) so existing DB code keeps working.

5. **Deploy**. Cloud gives you a URL like `https://your-app.streamlit.app`.

## 3. Database and ingestion

**Two separate things (easy to mix up):**

| What | Calls Vic fuel API? | Writes `raw_prices`? |
|------|---------------------|----------------------|
| **Streamlit app** (Cloud) | **No** — it only **reads** Postgres | No |
| **GitHub Action** [`.github/workflows/ingest.yml`](../.github/workflows/ingest.yml) | **Yes** (`run_ingest.py`) | **Yes** — each run sets `ingested_at` |

So the **“official ingest day”** in charts is the latest **`ingested_at`** in your database. It moves forward only when the **Action succeeds** on a schedule (twice daily UTC in the workflow) or when you **Run workflow** manually. Refreshing the Streamlit page does not pull new official rows from the API.

- **Schema**: Run `python setup_db.py` (or your migration SQL) against the **same** hosted database once.
- **Ingestion secrets**: In the repo → **Settings → Secrets and variables → Actions**, set `SERVO_SAVER_API_CONSUMER_ID` and **either** `POSTGRES_DB_URL` **or** the discrete `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` (same names as Streamlit). If Actions has no valid DB env, ingestion never writes and ingest days stay old.
- **Check it really wrote data**: **Actions** tab → open the job log. You should see `Inserted N price records` and `latest Melbourne ingest calendar day = YYYY-MM-DD`. If the workflow was green before but those lines never appeared, the script used to **exit 0 on failure** (fixed in `run_ingest.py`); upgrade `main` and re-run the workflow—failures should now show **red** with a non-zero exit code.
- **If `MAX(ingested_at)` in Supabase never moves** after a green run: pull latest `main` (ingest now sets `ingested_at` explicitly in Python). In SQL Editor run:
  - `SELECT MAX(id) AS newest_id, MAX(ingested_at) AS newest_ts, COUNT(*)::bigint AS n FROM raw_prices;`
  - `SELECT id, ingested_at FROM raw_prices ORDER BY id DESC LIMIT 5;`  
  If `newest_id` never grows, inserts are not landing in this database (wrong project, RLS, or workflow not on latest commit). If `newest_ts` grows but Melbourne **date** stays the same, you are likely still on one Melbourne calendar day across runs (rerun after local midnight Melbourne to confirm).

## 4. Local vs Cloud

- **Local**: `.env` + `load_dotenv()` as today.
- **Cloud**: No `.env` on the server; use **Streamlit Secrets** only. Do not commit real URLs or keys.

## 5. Alternatives (if you outgrow Streamlit Cloud)

- **Railway / Render / Fly.io**: Run `streamlit run src/app.py` in a container or process with env vars set to the same names as `.env.example`.
- **Custom domain**: Supported on Streamlit Cloud paid plans; free tier uses the default `*.streamlit.app` hostname.
