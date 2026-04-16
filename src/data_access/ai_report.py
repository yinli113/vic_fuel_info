"""
Optional LLM narrative for the Data Analysis page.

Uses only aggregate facts (no station names or addresses).
Supports OpenAI or Google Gemini (set keys and optional AI_REPORT_PROVIDER).
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import pandas as pd

from data_access.brand_display import brand_display_column

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
# 2.0 Flash is not offered to new API keys; 2.5 Flash is the current stable workhorse.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _system_prompt() -> str:
    return (
        "You write analytical markdown briefings for Australian drivers about Victorian fuel metrics.\n\n"
        "Hard rules: every number must appear in the user message (or a precomputed helper line there). "
        "Never invent stations, suburbs, prices, or dates. If distance-from-CBD buckets are given, you may "
        "say inner Melbourne vs further out using those labels only (we have no suburb names). "
        "Not financial advice. Attribute to Fair Fuel Open Data (ingested) and note delays vs pump prices.\n\n"
        "Markdown formatting (critical for the app):\n"
        "- Every section must start with a level-2 heading: two hash characters, a space, then the title, e.g. `## Overview`.\n"
        "- Never output a bare word like `Overview` without `## ` — the UI expects real markdown headings.\n"
        "- After each heading, add a blank line, then paragraphs.\n"
        "- Bold: wrap **complete** phrases only, e.g. `**232.98 c/L**` or `the outage rate was **1.2%**`. "
        "Never open `**` and stop mid-number; never leave a dangling `**` at the end.\n"
        "- Finish every sentence and section; do not stop mid-thought.\n\n"
        "Use **exactly** these headings (one per line, with ##):\n"
        "## Overview\n"
        "## Prices & market shape\n"
        "## Geography vs Melbourne CBD\n"
        "## Seven-day dynamics\n"
        "## Availability\n"
        "## Brands\n"
        "## Insights for drivers\n"
        "## Caveats\n\n"
        "Section focus:\n"
        "- **Overview**: 2–4 sentences only — ingest date, fuel type, how many stations in the snapshot, state average ¢/L. "
        "Do **not** put outage % here; that belongs under Availability.\n"
        "- **Availability**: outage / unavailable rate and what it means from the numbers alone.\n"
        "Do **not** copy this instruction list into the report.\n\n"
        "If a section has no data in the fact block, one short sentence under that heading is enough.\n\n"
        "**Geography vs Melbourne CBD**: inner vs outer means/medians vs heatmap story when numbers support it.\n"
        "**Seven-day dynamics**: calendar day-over-day and/or latest-two-ingest-day facts when present.\n"
        "**Insights for drivers**: 4–6 bullet points, grounded in stats.\n\n"
        "Aim for **400–550 words** when the fact block is full. Plain Australian English."
    )


def _tidy_report_markdown(text: str) -> str:
    """Fix common model glitches: unclosed ** from truncation, stray heading lines."""
    t = text.strip()
    if not t:
        return t
    while t.count("**") % 2 == 1:
        i = t.rfind("**")
        if i == -1:
            break
        t = (t[:i] + t[i + 2 :]).rstrip()
    # Promote a first line that is just "Overview" (no ##) to a proper heading
    lines = t.split("\n")
    if lines and lines[0].strip() == "Overview":
        lines[0] = "## Overview"
        t = "\n".join(lines)
    return t


def gemini_api_key() -> str | None:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip() or None


def openai_api_key() -> str | None:
    return (os.environ.get("OPENAI_API_KEY") or "").strip() or None


def resolve_provider() -> str:
    """
    Which backend to use: 'gemini' or 'openai'.

    Set AI_REPORT_PROVIDER to 'gemini' or 'openai' to force.
    If unset: prefer Gemini when GEMINI_API_KEY or GOOGLE_API_KEY exists, else OpenAI if set.
    """
    forced = (os.environ.get("AI_REPORT_PROVIDER") or "").strip().lower()
    if forced == "gemini":
        return "gemini"
    if forced == "openai":
        return "openai"
    if gemini_api_key():
        return "gemini"
    if openai_api_key():
        return "openai"
    return "none"


def report_backend_configured() -> bool:
    p = resolve_provider()
    if p == "none":
        return False
    if p == "gemini":
        return bool(gemini_api_key())
    return bool(openai_api_key())


def active_provider_description() -> str:
    """Human-readable backend + model for UI hints."""
    p = resolve_provider()
    if p == "gemini":
        m = os.environ.get("GEMINI_REPORT_MODEL", DEFAULT_GEMINI_MODEL).strip()
        return f"Google **Gemini** (`{m}`)"
    if p == "openai":
        m = os.environ.get("OPENAI_REPORT_MODEL", DEFAULT_OPENAI_MODEL).strip()
        return f"**OpenAI** (`{m}`)"
    return "not configured"


def build_dashboard_context(
    *,
    fuel_label: str,
    fuel_code: str,
    as_of_date: date,
    map_mode: str,
    avg_price: float | None,
    outage_rate: float | None,
    n_geo: int,
    n_outage_denom: int,
    geo_snap: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> str:
    """Serialize dashboard state into a compact fact block for the model."""
    lines: list[str] = [
        f"Fuel (label): {fuel_label} (API code: {fuel_code})",
        f"As-of ingest date (Melbourne calendar day): {as_of_date.isoformat()}",
        f"Map layer selected in UI: {map_mode}",
        f"Stations with coordinates in snapshot: {n_geo}",
        f"Stations with known availability flag: {n_outage_denom}",
    ]
    if avg_price is not None:
        lines.append(f"State mean price (available & priced stations): {avg_price:.2f} c/L")
    else:
        lines.append("State mean price: not available (no priced available rows).")
    if outage_rate is not None:
        lines.append(f"State outage / unavailable rate (among flagged stations): {outage_rate * 100:.2f}%")
    else:
        lines.append("State outage rate: not computable (no availability flags).")

    priced = geo_snap.loc[geo_snap["is_available"] & geo_snap["price"].notna(), "price"].astype(float)
    if not priced.empty:
        lines.append(
            f"Snapshot price among priced available stations: min {priced.min():.1f}, "
            f"median {priced.median():.1f}, max {priced.max():.1f} c/L (n={len(priced)})."
        )
        if len(priced) >= 5:
            q10 = float(priced.quantile(0.1))
            q90 = float(priced.quantile(0.9))
            lines.append(
                f"Snapshot dispersion (same set): estimated p10={q10:.1f} c/L, p90={q90:.1f} c/L "
                f"(middle 80% span ≈ {q90 - q10:.1f} c/L)."
            )

        gdf = geo_snap.loc[geo_snap["is_available"] & geo_snap["price"].notna()].dropna(
            subset=["latitude", "longitude"]
        )
        if len(gdf) >= 30:
            from geopy.distance import geodesic

            cbd = (-37.8136, 144.9631)
            lines.append(
                "Geography (no suburbs in data): great-circle distance from Melbourne CBD reference "
                f"({cbd[0]:.4f}, {cbd[1]:.4f}) to each station; buckets for priced available stations only."
            )

            def _km(row) -> float:
                return float(geodesic(cbd, (float(row["latitude"]), float(row["longitude"]))).km)

            gdf = gdf.copy()
            gdf["_km_cbd"] = gdf.apply(_km, axis=1)
            inner = gdf[gdf["_km_cbd"] <= 5.0]
            mid = gdf[(gdf["_km_cbd"] > 5.0) & (gdf["_km_cbd"] <= 25.0)]
            outer = gdf[gdf["_km_cbd"] > 25.0]

            def _band(name: str, sub: pd.DataFrame) -> None:
                if len(sub) < 12:
                    lines.append(f"  {name}: n={len(sub)} (too few stations for stable mean; skip strong claims)")
                    return
                px = sub["price"].astype(float)
                lines.append(
                    f"  {name}: n={len(sub)}, mean {px.mean():.1f} c/L, median {px.median():.1f} c/L"
                )

            _band("Within ~5 km of CBD (inner)", inner)
            _band("Between ~5 km and ~25 km of CBD (middle ring)", mid)
            _band("Beyond ~25 km of CBD (regional/Victoria)", outer)
            if len(inner) >= 12 and len(outer) >= 12:
                di = float(inner["price"].astype(float).mean())
                do = float(outer["price"].astype(float).mean())
                lines.append(
                    f"  Inner (~5 km) mean minus beyond-25 km mean = {di - do:+.2f} c/L "
                    "(positive ⇒ inner more expensive on average in this snapshot)."
                )

    if not geo_snap.empty and "brand_id" in geo_snap.columns:
        bdf = geo_snap.loc[geo_snap["is_available"] & geo_snap["price"].notna()].copy()
        if not bdf.empty:
            bdf["brand"] = brand_display_column(bdf).astype(str)
            g = (
                bdf.groupby("brand", as_index=False)
                .agg(mean_price=("price", "mean"), n=("price", "count"))
                .query("n >= 2")
                .sort_values("mean_price", ascending=True)
            )
            if not g.empty:
                cheap = g.head(5)
                ex = g.tail(5).iloc[::-1]
                lines.append(
                    "Brand mean c/L (min 2 stations; inferred / mapped brand labels): "
                    "cheapest → "
                    + ", ".join(f"{r.brand}={r.mean_price:.1f} (n={int(r.n)})" for r in cheap.itertuples())
                )
                lines.append(
                    "Most expensive brand means → "
                    + ", ".join(f"{r.brand}={r.mean_price:.1f} (n={int(r.n)})" for r in ex.itertuples())
                )

    if not trend_df.empty and trend_df["n_stations"].sum() > 0:
        t = trend_df.sort_values("date").reset_index(drop=True)
        lines.append("Last 7 ingest-day window (oldest → newest dates in data):")
        for _, row in t.iterrows():
            d = row["date"]
            parts = [f"date={d}"]
            if pd.notna(row.get("avg_price")):
                parts.append(f"avg={float(row['avg_price']):.1f}")
            if pd.notna(row.get("median_price")):
                parts.append(f"median={float(row['median_price']):.1f}")
            if pd.notna(row.get("min_price")) and pd.notna(row.get("max_price")):
                parts.append(f"min={float(row['min_price']):.1f}")
                parts.append(f"max={float(row['max_price']):.1f}")
            if pd.notna(row.get("outage_rate")):
                parts.append(f"outage_pct={float(row['outage_rate']) * 100:.1f}")
            if pd.notna(row.get("n_stations")):
                parts.append(f"stations={int(row['n_stations'])}")
            lines.append("  " + ", ".join(parts))

        lines.append("Precomputed trend helpers (quote these for change; do not invent others):")
        first = t.iloc[0]
        last = t.iloc[-1]
        if pd.notna(first.get("avg_price")) and pd.notna(last.get("avg_price")):
            da = float(last["avg_price"]) - float(first["avg_price"])
            lines.append(f"  State avg price: last day minus first day in window = {da:+.2f} c/L")
        if pd.notna(first.get("median_price")) and pd.notna(last.get("median_price")):
            dm = float(last["median_price"]) - float(first["median_price"])
            lines.append(f"  State median price: last minus first day in window = {dm:+.2f} c/L")
        if pd.notna(first.get("outage_rate")) and pd.notna(last.get("outage_rate")):
            o0 = float(first["outage_rate"]) * 100.0
            o1 = float(last["outage_rate"]) * 100.0
            lines.append(
                f"  Outage rate (pct points): last day {o1:.2f}% vs first day {o0:.2f}% "
                f"(delta {o1 - o0:+.2f} pp)"
            )

        t2 = t.copy()
        t2["_d"] = pd.to_datetime(t2["date"]).dt.date
        prev_cal = as_of_date - timedelta(days=1)
        row_today = t2[t2["_d"] == as_of_date]
        row_prev = t2[t2["_d"] == prev_cal]
        lines.append("Day-over-day (calendar; only if both days exist in the series above):")
        if not row_today.empty and not row_prev.empty:
            rt = row_today.iloc[0]
            rp = row_prev.iloc[0]
            if pd.notna(rt.get("avg_price")) and pd.notna(rp.get("avg_price")):
                d_avg = float(rt["avg_price"]) - float(rp["avg_price"])
                lines.append(
                    f"  As-of {as_of_date} vs {prev_cal}: state avg {float(rp['avg_price']):.2f} → "
                    f"{float(rt['avg_price']):.2f} c/L (change {d_avg:+.2f} c/L)."
                )
            if pd.notna(rt.get("median_price")) and pd.notna(rp.get("median_price")):
                d_med = float(rt["median_price"]) - float(rp["median_price"])
                lines.append(
                    f"  Same pair: state median {float(rp['median_price']):.2f} → "
                    f"{float(rt['median_price']):.2f} c/L (change {d_med:+.2f} c/L)."
                )
        else:
            lines.append(
                f"  No row for {as_of_date} and/or {prev_cal} in the 7-day window — use 'latest two ingest days' below."
            )
        if len(t2) >= 2:
            a = t2.iloc[-2]
            b = t2.iloc[-1]
            if pd.notna(a.get("avg_price")) and pd.notna(b.get("avg_price")):
                lines.append(
                    f"Latest two ingest days in series: {a['_d']} then {b['_d']}: "
                    f"avg {float(a['avg_price']):.2f} → {float(b['avg_price']):.2f} c/L "
                    f"(delta {float(b['avg_price']) - float(a['avg_price']):+.2f})."
                )

    lines.append(
        "Data source: official Victorian Fair Fuel Open Data (Servo Saver API), "
        "stored on scheduled ingest; may be delayed vs pump prices."
    )
    return "\n".join(lines)


def _generate_openai(context: str, *, api_key: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": "Write the analytical briefing from this fact block:\n\n" + context,
            },
        ],
        max_tokens=4096,
        temperature=0.45,
    )
    choice = resp.choices[0].message.content
    if not choice:
        raise RuntimeError("Empty response from OpenAI")
    return _tidy_report_markdown(choice.strip())


def _generate_gemini(context: str, *, api_key: str, model: str) -> str:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError

    client = genai.Client(api_key=api_key)
    user = "Write the analytical briefing from this fact block:\n\n" + context
    config = types.GenerateContentConfig(
        system_instruction=_system_prompt(),
        max_output_tokens=8192,
        temperature=0.45,
    )

    resp = None
    last_api_err: APIError | None = None
    for attempt in range(4):
        if attempt:
            time.sleep(min(20.0, 2.5**attempt))
        try:
            resp = client.models.generate_content(
                model=model,
                contents=user,
                config=config,
            )
            break
        except APIError as e:
            last_api_err = e
            if e.code in (503, 429) and attempt < 3:
                continue
            if e.code in (503, 429):
                _reraise_gemini_capacity(e)
            raise
    if resp is None:
        if last_api_err is not None:
            _reraise_gemini_capacity(last_api_err)
        raise RuntimeError("Gemini request failed with no response")

    text = (resp.text or "").strip()
    if text:
        return _tidy_report_markdown(text)

    fb = getattr(resp, "prompt_feedback", None)
    cand0 = resp.candidates[0] if resp.candidates else None
    finish = getattr(cand0, "finish_reason", None) if cand0 else None
    safety = getattr(cand0, "safety_ratings", None) if cand0 else None
    raise RuntimeError(
        "Gemini returned no usable text (blocked, empty, or unsupported response). "
        f"finish_reason={finish!r}, prompt_feedback={fb!r}, safety_ratings={safety!r}. "
        "Try GEMINI_REPORT_MODEL=gemini-2.5-flash-lite or check API key / quota in Google AI Studio."
    )


def _reraise_gemini_capacity(e: BaseException) -> None:
    """Add hints after retries exhausted for 503/429."""
    from google.genai.errors import APIError

    if isinstance(e, APIError) and e.code in (503, 429):
        raise RuntimeError(
            f"{e} — Google's side was busy after several automatic retries. "
            "Wait a minute and click **Generate report** again, or set "
            "`GEMINI_REPORT_MODEL=gemini-2.5-flash-lite` in `.env` (often less loaded) and restart Streamlit."
        ) from e
    raise e


def generate_narrative_report(context: str) -> str:
    """
    Call the configured LLM (Gemini or OpenAI). Returns markdown text.

    Env:
    - AI_REPORT_PROVIDER: 'gemini' | 'openai' (optional; auto-picks if one key is set).
    - GEMINI_API_KEY or GOOGLE_API_KEY for Gemini.
    - OPENAI_API_KEY for OpenAI.
    - GEMINI_REPORT_MODEL (default gemini-2.5-flash), OPENAI_REPORT_MODEL (default gpt-4o-mini).
    """
    provider = resolve_provider()
    if provider == "none":
        raise ValueError(
            "No AI key configured. Set GEMINI_API_KEY or GOOGLE_API_KEY for Gemini, "
            "or OPENAI_API_KEY for OpenAI (optionally force with AI_REPORT_PROVIDER)."
        )

    if provider == "gemini":
        key = gemini_api_key()
        if not key:
            raise ValueError("AI_REPORT_PROVIDER is gemini but GEMINI_API_KEY / GOOGLE_API_KEY is missing")
        model = os.environ.get("GEMINI_REPORT_MODEL", DEFAULT_GEMINI_MODEL).strip()
        return _generate_gemini(context, api_key=key, model=model)

    key = openai_api_key()
    if not key:
        raise ValueError("AI_REPORT_PROVIDER is openai but OPENAI_API_KEY is missing")
    model = os.environ.get("OPENAI_REPORT_MODEL", DEFAULT_OPENAI_MODEL).strip()
    return _generate_openai(context, api_key=key, model=model)
