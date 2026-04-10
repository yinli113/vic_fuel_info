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

- **Schema**: Run `python setup_db.py` (or your migration path) against the **same** hosted database once.
- **Ingestion**: Keep [GitHub Actions](https://docs.github.com/en/actions) (e.g. `.github/workflows/ingest.yml`) pointed at that DB via repository **Secrets** (`POSTGRES_DB_URL`), so scheduled jobs refresh official data while the live app reads it.

## 4. Local vs Cloud

- **Local**: `.env` + `load_dotenv()` as today.
- **Cloud**: No `.env` on the server; use **Streamlit Secrets** only. Do not commit real URLs or keys.

## 5. Alternatives (if you outgrow Streamlit Cloud)

- **Railway / Render / Fly.io**: Run `streamlit run src/app.py` in a container or process with env vars set to the same names as `.env.example`.
- **Custom domain**: Supported on Streamlit Cloud paid plans; free tier uses the default `*.streamlit.app` hostname.
