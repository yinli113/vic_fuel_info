import os
import sys
from datetime import date
from pathlib import Path

import altair as alt
import folium
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from folium.plugins import HeatMap
from streamlit_folium import st_folium

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data_access import ai_report
from data_access import analysis
from data_access.streamlit_env import hydrate_secrets_into_environ

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()
hydrate_secrets_into_environ()

st.set_page_config(
    page_title="Data Analysis",
    page_icon="📊",
    layout="wide",
)

FUEL_LABELS = {
    "Unleaded 91": "U91",
    "Premium 95": "P95",
    "Premium 98": "P98",
    "Diesel": "DSL",
    "Premium Diesel": "PDSL",
    "E10": "E10",
    "E85": "E85",
    "LPG": "LPG",
}


@st.cache_data(ttl=300)
def cached_trend(fuel_code: str, end_s: str) -> pd.DataFrame:
    conn = analysis.get_db_connection()
    if not conn:
        return pd.DataFrame()
    try:
        end_d = date.fromisoformat(end_s)
        return analysis.fetch_state_trend_7d(conn, fuel_code, end_d)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def cached_snapshot(fuel_code: str, as_of_s: str) -> pd.DataFrame:
    conn = analysis.get_db_connection()
    if not conn:
        return pd.DataFrame()
    try:
        as_of = date.fromisoformat(as_of_s)
        return analysis.fetch_snapshot_station_rows(conn, fuel_code, as_of)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def cached_max_ingest() -> str | None:
    conn = analysis.get_db_connection()
    if not conn:
        return None
    try:
        d = analysis.fetch_max_ingest_date(conn)
        return d.isoformat() if d else None
    finally:
        conn.close()


st.title("📊 Data Analysis & Trends")

st.caption(
    "Figures use **official** Servo Saver snapshots stored on each ingest. "
    "The selected **as-of date** follows **ingest calendar days** (Melbourne time), not the API’s per-row `updated_at`. "
    "Victorian open data can be delayed; treat this as indicative."
)

_health = analysis.get_db_connection()
if not _health:
    st.error(
        "Database is not configured. In **Streamlit Secrets** (or `.env` locally), set either "
        "`POSTGRES_DB_URL` **or** `POSTGRES_HOST` + `POSTGRES_USER` + `POSTGRES_PASSWORD`. "
        "See `.env.example`."
    )
    st.stop()
_health.close()

max_ingest_s = cached_max_ingest()
default_end = date.fromisoformat(max_ingest_s) if max_ingest_s else analysis.melbourne_today()
max_ingest_d = date.fromisoformat(max_ingest_s) if max_ingest_s else None
_today_melb = analysis.melbourne_today()
# Cap picker at latest ingest so the UI cannot sit "on today" with stale official rows (matches Fuel Up chart reality).
_asof_max = min(_today_melb, max_ingest_d) if max_ingest_d else _today_melb
_asof_default = min(default_end, _asof_max)
# Bust stale session-state dates from before the cap (value > max_value breaks the widget).
_DA_AS_OF_KEY = "da_as_of_ingest_cap_v1"
if _DA_AS_OF_KEY in st.session_state and st.session_state[_DA_AS_OF_KEY] > _asof_max:
    del st.session_state[_DA_AS_OF_KEY]

with st.sidebar:
    st.subheader("Filters")
    fuel_label = st.selectbox("Fuel type", list(FUEL_LABELS.keys()))
    fuel_code = FUEL_LABELS[fuel_label]
    as_of_date = st.date_input(
        "As-of date (ingest day)",
        value=_asof_default,
        max_value=_asof_max,
        key=_DA_AS_OF_KEY,
        help="Only through the latest official snapshot in the database (same limit as the Fuel Up 7-day chart end).",
    )
    if max_ingest_d:
        st.caption(
            f"Latest **official** snapshot day in the database: **{max_ingest_d.isoformat()}** "
            "(Melbourne calendar day of `ingested_at`). Newer calendar days appear after ingestion writes new rows."
        )
    map_mode = st.radio(
        "Map layer",
        ("Price intensity", "Unavailable / outage"),
        horizontal=False,
    )

as_of_s = as_of_date.isoformat()
trend_df = cached_trend(fuel_code, as_of_s)
snap_df = cached_snapshot(fuel_code, as_of_s)

geo_snap = snap_df.dropna(subset=["latitude", "longitude"]).copy()

# --- Map (top) ---
st.subheader("Victoria overview")
legend_price_range: tuple[float, float] | None = None
if geo_snap.empty:
    st.info(
        "No station coordinates for this selection and date yet. Run ingestion to build history."
    )
    m = folium.Map(location=[-37.8136, 144.9631], zoom_start=7, tiles="CartoDB positron")
    st_folium(m, height=420, width=None, returned_objects=[], key="da_map_empty")
else:
    center_lat = float(geo_snap["latitude"].median())
    center_lon = float(geo_snap["longitude"].median())
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=7,
        tiles="CartoDB positron",
    )

    if map_mode == "Price intensity":
        rows = geo_snap[geo_snap["is_available"] & geo_snap["price"].notna()]
        if rows.empty:
            st.warning("No priced, available rows to plot for this selection.")
        else:
            vmin, vmax = float(rows["price"].min()), float(rows["price"].max())
            legend_price_range = (vmin, vmax)
            span = max(vmax - vmin, 1e-6)
            heat_data = [
                [float(r.latitude), float(r.longitude), (float(r.price) - vmin) / span]
                for _, r in rows.iterrows()
            ]
            HeatMap(heat_data, radius=12, blur=14, min_opacity=0.25, max_zoom=12).add_to(m)
    else:
        flagged = geo_snap[geo_snap["is_available"].notna()]
        if flagged.empty:
            st.warning("No stations with an availability flag for this selection.")
        else:
            heat_data = []
            for _, r in flagged.iterrows():
                avail = r["is_available"]
                # Use == False so numpy.bool_ from the driver matches (``is False`` does not).
                w = 1.0 if avail == False else 0.15
                heat_data.append([float(r.latitude), float(r.longitude), w])
            HeatMap(heat_data, radius=14, blur=16, min_opacity=0.2, max_zoom=12).add_to(m)

    st_folium(m, height=420, width=None, returned_objects=[], key="da_map_heat")

# Folium’s HeatMap uses a blue → cyan → lime → yellow → red ramp (Leaflet.heat defaults).
_GRADIENT_BAR = (
    "linear-gradient(to right, #0000ff, #00ffff, #00ff00, #ffff00, #ff0000)"
)
if map_mode == "Price intensity":
    range_note = ""
    if legend_price_range is not None:
        lo, hi = legend_price_range
        range_note = f"<p style='font-size:12px; color:#555; margin:6px 0 0 0;'>Snapshot price span: <strong>{lo:.1f}</strong>–<strong>{hi:.1f}</strong> ¢/L (normalized to the colour scale).</p>"
    legend_title = "Price intensity"
    legend_blurb = (
        "Warmer colours = higher reported price; cooler = lower. Opacity stacks where many stations overlap."
    )
else:
    range_note = ""
    legend_title = "Unavailable / outage"
    legend_blurb = (
        "Warmer colours = more weight on stations marked <strong>unavailable</strong> for this fuel; "
        "cool areas = mostly available. Opacity stacks where many stations overlap."
    )

st.markdown(
    f"""
<div style="margin: 0.5rem 0 1rem 0; padding: 10px 12px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e9ecef;">
  <div style="font-size: 13px; font-weight: 600; color: #333; margin-bottom: 6px;">Heatmap legend — {legend_title}</div>
  <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
    <span style="font-size: 12px; color: #555;">Low</span>
    <div style="flex: 1; min-width: 180px; max-width: 420px; height: 14px; border-radius: 4px; border: 1px solid #ccc; background: {_GRADIENT_BAR};"></div>
    <span style="font-size: 12px; color: #555;">High</span>
  </div>
  <p style="font-size: 12px; color: #555; margin: 8px 0 0 0;">{legend_blurb}</p>
  {range_note}
</div>
""",
    unsafe_allow_html=True,
)

st.divider()

# KPIs
k1, k2, k3 = st.columns([1, 1, 1])
n_geo = len(geo_snap)
if n_geo == 0:
    avg_price = None
    outage_rate = None
    n_outage_denom = 0
else:
    priced = geo_snap[geo_snap["is_available"] & geo_snap["price"].notna()]
    avg_price = float(priced["price"].mean()) if not priced.empty else None
    known = geo_snap["is_available"].notna()
    n_outage_denom = int(known.sum())
    if n_outage_denom > 0:
        outage_rate = float((geo_snap.loc[known, "is_available"] == False).sum()) / n_outage_denom
    else:
        outage_rate = None

with k1:
    st.metric(
        label=f"State avg price ({fuel_label})",
        value=f"{avg_price:.1f} ¢/L" if avg_price is not None else "—",
        help=(
            "Mean ¢/L over stations that are marked available with a price in the latest snapshot for this fuel."
        ),
    )
with k2:
    st.metric(
        label="State outage / unavailable rate",
        value=f"{outage_rate * 100:.1f} %" if outage_rate is not None else "—",
        help=(
            "Among stations that include an availability flag for this fuel, the share marked unavailable. "
            "If the API left `is_available` blank on older ingests, those rows are excluded (they are not treated as outages)."
        ),
    )
with k3:
    st.metric(
        label="Stations in snapshot",
        value=str(n_geo),
        help="Stations with coordinates included in the as-of snapshot.",
    )
if n_geo and n_outage_denom < n_geo:
    st.caption(
        f"Availability KPI uses **{n_outage_denom}** of **{n_geo}** stations with a known flag; "
        f"**{n_geo - n_outage_denom}** have no `is_available` value for this fuel."
    )

st.divider()
st.subheader("Snapshot: price mix & brands")

snap_hist_col, snap_brand_col = st.columns(2)

with snap_hist_col:
    st.markdown("**Price distribution (available stations)**")
    priced_series = geo_snap.loc[geo_snap["is_available"] & geo_snap["price"].notna(), "price"].astype(float)
    if priced_series.empty:
        st.caption("No priced, available stations for this snapshot.")
    elif len(priced_series) < 5:
        st.caption("Need at least five priced stations for a histogram.")
    else:
        arr = priced_series.to_numpy()
        n_bins = int(min(20, max(8, round(np.sqrt(len(arr))))))
        counts, edges = np.histogram(arr, bins=n_bins)
        centers = (edges[:-1] + edges[1:]) / 2.0
        hist_df = pd.DataFrame({"stations": counts}, index=centers)
        hist_df.index.name = "¢/L (bin centre)"
        st.bar_chart(hist_df)
        st.caption("Counts of stations by price bin for the selected fuel and as-of date.")

with snap_brand_col:
    st.markdown("**Mean price by brand**")
    bdf = geo_snap.loc[geo_snap["is_available"] & geo_snap["price"].notna()].copy()
    if bdf.empty:
        st.caption("No priced, available stations for brand comparison.")
    else:
        bdf["brand"] = bdf["brand_id"].fillna("(no brand)").astype(str)
        brand_stats = (
            bdf.groupby("brand", as_index=False)
            .agg(mean_price=("price", "mean"), n=("price", "count"))
            .query("n >= 2")
            .sort_values("mean_price", ascending=True)
        )
        if brand_stats.empty:
            st.caption("Need at least two stations per brand to show brand means.")
        else:
            brand_order = brand_stats.sort_values("mean_price", ascending=True)["brand"].tolist()
            bchart = (
                alt.Chart(brand_stats)
                .mark_bar()
                .encode(
                    x=alt.X("mean_price:Q", title="Mean ¢/L"),
                    y=alt.Y("brand:N", sort=brand_order, title=None),
                    tooltip=[
                        alt.Tooltip("brand:N", title="Brand id"),
                        alt.Tooltip("mean_price:Q", title="Mean ¢/L", format=".1f"),
                        alt.Tooltip("n:Q", title="Stations"),
                    ],
                )
                .properties(height=min(420, max(160, 22 * int(len(brand_stats)))))
            )
            st.altair_chart(bchart, width="stretch")
            st.caption("Brands with fewer than two priced stations are hidden.")

st.divider()
st.subheader("Seven-day trends")

if trend_df.empty or trend_df["n_stations"].sum() == 0:
    st.info("Need ingested history across days for trend charts.")
else:
    tdf = trend_df.copy()
    tdf["date"] = pd.to_datetime(tdf["date"])

    st.markdown("**Price spread (available stations)**")
    spread_cols = ["min_price", "p10_price", "median_price", "p90_price", "max_price"]
    spread_ready = tdf.dropna(subset=["median_price"], how="all")
    if spread_ready.empty or spread_ready[spread_cols].notna().sum().sum() == 0:
        st.caption("No spread statistics yet (need priced rows per day).")
    else:
        spread_chart = spread_ready.set_index("date")[spread_cols].rename(
            columns={
                "min_price": "Min",
                "p10_price": "10th %ile",
                "median_price": "Median",
                "p90_price": "90th %ile",
                "max_price": "Max",
            }
        )
        st.line_chart(spread_chart)
        st.caption(
            "Daily snapshot of the **distribution** of prices (min / p10 / median / p90 / max). "
            "Flat lines across days are normal when the market barely moves between ingests."
        )

    st.markdown("**State average price vs outage rate**")
    dual_plot = tdf[["date", "avg_price", "outage_rate"]].copy()
    dual_plot["outage_pct"] = dual_plot["outage_rate"] * 100.0
    if dual_plot["avg_price"].notna().sum() == 0:
        st.caption("No average price series to plot.")
    else:
        base = alt.Chart(dual_plot).encode(
            x=alt.X("date:T", title="Date", axis=alt.Axis(format="%d %b")),
        )
        price_line = base.mark_line(point=True, color="#1f77b4").encode(
            y=alt.Y("avg_price:Q", title="Avg price (¢/L)"),
        )
        layers = [price_line]
        if dual_plot["outage_pct"].notna().any():
            out_max = float(dual_plot["outage_pct"].max())
            out_domain_max = max(5.0, out_max * 1.15)
            outage_line = base.mark_line(point=True, color="#d62728", strokeDash=[4, 3]).encode(
                y=alt.Y(
                    "outage_pct:Q",
                    title="Outage %",
                    scale=alt.Scale(domain=[0, out_domain_max]),
                ),
            )
            layers.append(outage_line)
        if len(layers) == 1:
            st.altair_chart(price_line.properties(height=320), width="stretch")
        else:
            dual_chart = alt.layer(*layers).resolve_scale(y="independent").properties(height=320)
            st.altair_chart(dual_chart, width="stretch")
        st.caption(
            "Blue: mean ¢/L over available, priced stations. Red (dashed): share of stations with a known flag marked unavailable. "
            "The two vertical scales are independent."
        )

st.divider()
st.subheader("AI narrative (optional)")

_report_ctx_key = "ai_report_context_key"
_report_md_key = "ai_report_markdown"

with st.expander("Generate a short AI report from this dashboard", expanded=False):
    with st.expander("Setup, models & privacy (read this once)", expanded=False):
        st.markdown(
            "- Only **aggregate** stats are sent (no station names or addresses).\n"
            "- **Gemini**: `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env` or Streamlit secrets.\n"
            "- **OpenAI**: `OPENAI_API_KEY` if you prefer it.\n"
            "- If both keys exist: set `AI_REPORT_PROVIDER` to `gemini` or `openai`.\n"
            "- Models: `GEMINI_REPORT_MODEL` (default **gemini-2.5-flash**; try **gemini-2.5-flash-lite** for lowest cost), "
            "`OPENAI_REPORT_MODEL` (default **gpt-4o-mini**)."
        )

    ctx_fingerprint = f"{fuel_label}|{fuel_code}|{as_of_s}|{map_mode}"
    if st.session_state.get(_report_ctx_key) != ctx_fingerprint:
        st.session_state[_report_md_key] = ""

    if ai_report.report_backend_configured():
        st.caption(f"Active backend: {ai_report.active_provider_description()}")

    if not ai_report.report_backend_configured():
        st.info(
            "Add **GEMINI_API_KEY** or **GOOGLE_API_KEY** (Gemini), or **OPENAI_API_KEY** (OpenAI), "
            "to your environment or Streamlit secrets."
        )
    else:
        st.markdown("**1.** Click the button. **2.** Scroll down in this box — the narrative appears under *Generated report*.")
        gen = st.button("Generate report", type="primary", key="ai_report_generate_btn")
        if gen:
            with st.spinner("Calling Gemini / OpenAI…"):
                try:
                    ctx = ai_report.build_dashboard_context(
                        fuel_label=fuel_label,
                        fuel_code=fuel_code,
                        as_of_date=as_of_date,
                        map_mode=map_mode,
                        avg_price=avg_price,
                        outage_rate=outage_rate,
                        n_geo=n_geo,
                        n_outage_denom=n_outage_denom,
                        geo_snap=geo_snap,
                        trend_df=trend_df,
                    )
                    st.session_state[_report_md_key] = ai_report.generate_narrative_report(ctx)
                    st.session_state[_report_ctx_key] = ctx_fingerprint
                except Exception as e:
                    st.session_state[_report_md_key] = ""
                    st.error(f"Could not generate report: {e}")

        report_body = (st.session_state.get(_report_md_key) or "").strip()
        if report_body:
            st.divider()
            st.markdown("### Generated report")
            st.caption("Fair Fuel Open Data (ingested). Verify numbers against the charts above.")
            st.markdown(report_body)
        elif ai_report.report_backend_configured():
            st.caption("No report yet — click **Generate report**.")
