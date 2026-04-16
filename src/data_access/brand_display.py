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
    ("OTR", (" otr ", "otr ", "/otr", "(otr)", " on the run")),
    ("Reddy Express", ("reddy express", "reddy ")),
    ("X Convenience", ("x convenience", "x conv")),
    ("Enhance", ("enhance fuels", "enhance ")),
    ("Mogas", ("mogas",)),
    ("Refuel", ("refuel",)),
    ("Freedom Fuels", ("freedom fuels",)),
    ("Pearl Energy", ("pearl energy", "pearl petroleum")),
    ("Vortex", ("vortex",)),
    ("Rely", ("rely fuel", "rely ", "rely,")),
    ("Choice", ("choice petrol", "choice fuels")),
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


def _longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    strings = [s for s in strings if s]
    if not strings:
        return ""
    s0 = min(strings, key=len)
    for i, c in enumerate(s0):
        if not all(len(s) > i and s[i] == c for s in strings):
            return s0[:i]
    return s0


def _first_retail_segment(raw: str) -> str | None:
    """Leading text before address-style separators (often the trading name)."""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    for sep in [",", "\n", " — ", " – "]:
        if sep in s:
            s = s.split(sep, 1)[0]
    if " - " in s:
        s = s.split(" - ", 1)[0]
    s = s.strip()
    if "(" in s:
        # "Foo (formerly Bar)" → keep "Foo"
        s = s[: s.find("(")].strip()
    s = s[:72].strip()
    return s or None


def _to_brand_title(blob: str) -> str:
    """Title case with a few petrol-brand fixes."""
    t = " ".join(blob.split()).strip()
    if not t:
        return t
    words = t.split()
    out: list[str] = []
    lower_small = {"and", "of", "the", "in", "on", "at"}
    for i, w in enumerate(words):
        wl = w.lower()
        if i > 0 and wl in lower_small:
            out.append(wl)
            continue
        if wl in ("bp",):
            out.append("BP")
        elif wl in ("otr",):
            out.append("OTR")
        elif wl in ("apco",):
            out.append("APCO")
        elif wl in ("eg",) and i > 0:
            out.append("EG")
        else:
            out.append(w.capitalize())
    s2 = " ".join(out)
    for a, b in (("7-eleven", "7-Eleven"), ("Bp", "BP")):
        s2 = s2.replace(a, b).replace(a.title(), b)
    return s2


def fallback_name_from_station_names(station_names: list[str]) -> str | None:
    """
    When keyword rules miss, derive a label from how stations name themselves:
    longest common prefix, or the most repeated first segment of the name.
    """
    raw_list = [str(x) for x in station_names if x is not None and str(x).lower() != "nan"]
    if not raw_list:
        return None

    if len(raw_list) == 1:
        seg = _first_retail_segment(raw_list[0])
        if seg and len(seg) >= 4:
            return _to_brand_title(_normalize(seg))
        return None

    norms = [_normalize(r) for r in raw_list]
    norms = [n for n in norms if n]
    if len(norms) >= 2:
        lcp = _longest_common_prefix(norms).rstrip()
        if len(lcp) >= 5:
            return _to_brand_title(lcp)

    segments: list[str] = []
    for r in raw_list:
        seg = _first_retail_segment(r)
        if seg:
            segments.append(_normalize(seg))
    if not segments:
        return None

    if len(set(segments)) == 1 and len(segments[0]) >= 4:
        return _to_brand_title(segments[0])

    cnt = Counter(segments)
    best, n = cnt.most_common(1)[0]
    if len(best) < 4:
        return None
    # Require the winning label to show up more than once, or dominate the group.
    if n >= 2 or (len(segments) >= 3 and n >= len(segments) * 0.5):
        return _to_brand_title(best)

    return None


def display_brand_for_group(station_names: list[str], brand_id: object) -> str:
    """
    Choose one chart/legend label for all rows sharing a `brand_id`.

    Uses modal inferred label from station names; then title heuristics; then a
    short id suffix (no \"Other\" prefix) so distinct chains stay separable.
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

    fallback = fallback_name_from_station_names(station_names)
    if fallback:
        return fallback

    return _short_id(sid)


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
