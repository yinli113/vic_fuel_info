# TL;DR

The **Data Analysis** page can call **Google Gemini** or **OpenAI** to turn dashboard **aggregates** into a markdown briefing. Set `GEMINI_API_KEY` or `OPENAI_API_KEY` in `.env` (or Streamlit secrets), open the expander on that page, and click **Generate report**. No station names or addresses are sent—only stats we already computed for charts.

---

# AI dashboard report — how it fits this project

## What it does

On [`src/pages/1_Data_Analysis.py`](../src/pages/1_Data_Analysis.py), an optional expander **“Generate a short AI report from this dashboard”** builds a **fact block** from the current filters (fuel, as-of ingest date, map mode) and the same DataFrames used for KPIs, charts, and heatmap. That text is sent to an LLM; the model returns **markdown** sections (Overview, prices, geography vs CBD, seven-day dynamics, availability, brands, insights, caveats).

The narrative is **not** a new data source: it must ground claims in the supplied numbers. Official figures remain **Fair Fuel Open Data** (ingested snapshots), with delay vs pump prices called out in the prompt.

## Where the logic lives

| Piece | Location |
|--------|-----------|
| Fact assembly (KPIs, trend rows, CBD distance buckets, day-over-day helpers, brands) | [`src/data_access/ai_report.py`](../src/data_access/ai_report.py) — `build_dashboard_context()` |
| Provider choice, API calls, retries on 503/429, markdown tidy | same file — `generate_narrative_report()`, `_generate_gemini()`, `_generate_openai()` |
| UI, session state, `.env` load from repo root | [`src/pages/1_Data_Analysis.py`](../src/pages/1_Data_Analysis.py) |

## Environment variables

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | One of these **or** OpenAI | Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) |
| `OPENAI_API_KEY` | Optional alternative | OpenAI key if you prefer Chat Completions |
| `AI_REPORT_PROVIDER` | Optional | `gemini` or `openai` when **both** keys exist (otherwise Gemini is preferred if its key is set) |
| `GEMINI_REPORT_MODEL` | Optional | Default in code: `gemini-2.5-flash` (new keys cannot use deprecated `gemini-2.0-flash`). Try `gemini-2.5-flash-lite` for cost or load. |
| `OPENAI_REPORT_MODEL` | Optional | Default: `gpt-4o-mini` |

**Local:** add variables to the project root `.env`. The Data Analysis page loads `.env` via `load_dotenv(REPO_ROOT / ".env")` plus a generic `load_dotenv()`.

**Streamlit Cloud:** add the same keys under **Secrets** (do not commit `.env`).

## Dependencies

- `openai` and `google-genai` are listed in [`requirements.txt`](../requirements.txt).
- CBD distance buckets use **`geopy`** (already used elsewhere in the app).

## Privacy and data safety

- Only **aggregates** are included: state means, percentiles, brand-id rollups, trend lines, distance-from-CBD bands, counts. **No** station names, addresses, or coordinates are sent in the prompt.
- Aligns with treating **official raw rows as immutable**; the LLM does not write back to the database.

## Operations notes

- **503 / high demand:** Gemini calls **retry** a few times with backoff; persistent failures suggest waiting or switching to `gemini-2.5-flash-lite`.
- **Regenerate:** Changing fuel, date, or map layer clears the cached report fingerprint so you are not shown a stale narrative.
- **Cost:** Each click is one short completion; Flash-class models keep spend low for an MVP.

## Extending the feature

1. Add new derived facts in `build_dashboard_context()` (keep aggregates only).
2. Adjust section titles or instructions in `_system_prompt()` in `ai_report.py`.
3. If you add a new provider, branch inside `generate_narrative_report()` and mirror the existing pattern (system prompt + user fact block + token limits).
