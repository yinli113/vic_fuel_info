"""
Map Servo Saver `brand_id` values to human-readable labels.

The open-data payload exposes opaque Salesforce-style `brandId` strings; we infer a
display name from each station's `name` using common Victorian retail patterns,
with optional explicit overrides for stable IDs.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

# Optional: pin a brand_id to a display string when inference is wrong or ambiguous.
BRAND_ID_OVERRIDES: dict[str, str] = {}

# (display label, substrings) — first match wins per station name (order matters).
_BRAND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("7-Eleven", ("7-eleven", "7 eleven", "seven eleven", "7-11")),
    ("Shell Coles Express", ("shell coles", "coles express", "coles express /")),
    ("Shell", ("shell",)),
    (
        "BP",
        (
            " bp ",
            " bp,",
            "(bp)",
            "[bp]",
            " bp.",
            "/bp/",
            " bp)",
            "/bp ",
            "(bp ",
            "british petroleum",
        ),
    ),
    ("Ampol", ("ampol", "eg ampol", "caltex", "the foodary")),  # legacy Caltex → Ampol
    ("United", ("united",)),
    ("Liberty", ("liberty",)),
    ("Mobil", ("mobil",)),
    ("Puma Energy", ("puma",)),
    ("Vibe", ("vibe ", "vibe,", "(vibe)")),
    ("Metro", ("metro fuels", "metro petroleum", " metro ")),
    ("FastFuel 24/7", ("fastfuel", "fast fuel")),
    ("Costco", ("costco",)),
    ("Woolworths / EG", ("woolworths", " eg ", "/eg ", " eg,", "caltex woolworths")),
    ("NightOwl", ("nightowl", "night owl")),
    ("Matilda", ("matilda",)),
    ("Pacific Petroleum", ("pacific petroleum", "pacific fuels")),
    ("Neumann Petroleum", ("neumann",)),
    ("APCO", ("apco",)),
    ("Independent", ("independent", "unbranded", "no brand")),
]


def _normalize(s: str) -> str:
    return " ".join(str(s).lower().split())


def infer_brand_label_from_station_name(station_name: str | None) -> str | None:
    """Return a retail label if `station_name` matches a known pattern."""
    if station_name is None or (isinstance(station_name, float) and str(station_name) == "nan"):
        return None
    blob = _normalize(station_name)
    if not blob:
        return None
    padded = f" {blob} "
    for label, needles in _BRAND_RULES:
        for n in needles:
            if n in padded or (n.strip() and n.strip() in blob):
                return label
    if blob.startswith("bp ") or blob.endswith(" bp") or blob == "bp" or blob.endswith(" bp."):
        return "BP"
    return None


def _short_id(brand_id: str) -> str:
    s = str(brand_id).strip()
    if len(s) <= 10:
        return s
    return f"…{s[-6:]}"


def display_brand_for_group(station_names: list[str], brand_id: object) -> str:
    """
    Choose one chart/legend label for all rows sharing a `brand_id`.

    Uses modal inferred label from station names; falls back to overrides or a
    compact opaque-id suffix so multiple unknown chains stay distinct.
    """
    bid = brand_id
    if bid is None or (isinstance(bid, float) and str(bid) == "nan") or pd.isna(bid):
        return "No brand"

    sid = str(bid).strip()
    if sid in BRAND_ID_OVERRIDES:
        return BRAND_ID_OVERRIDES[sid]

    inferred: list[str] = []
    for n in station_names:
        lab = infer_brand_label_from_station_name(n)
        if lab:
            inferred.append(lab)

    if inferred:
        return Counter(inferred).most_common(1)[0][0]

    return f"Other ({_short_id(sid)})"


def brand_display_column(df: pd.DataFrame) -> pd.Series:
    """
    One display label per row from `brand_id` + `station_name` (same index as `df`).
    """
    if df.empty or "brand_id" not in df.columns or "station_name" not in df.columns:
        return pd.Series(dtype=object)
    mapping: dict[object, str] = {}
    for bid, sub in df.groupby(df["brand_id"], dropna=False, sort=False):
        mapping[bid] = display_brand_for_group(sub["station_name"].astype(str).tolist(), bid)
    return df["brand_id"].map(mapping)
