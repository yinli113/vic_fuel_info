"""Append-only NDJSON for debug sessions (Cursor). Do not log secrets."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

SESSION_ID = "728b24"
_LOG_PATH = Path(__file__).resolve().parents[2] / ".cursor" / f"debug-{SESSION_ID}.log"


def db_host_fingerprint() -> str:
    h = (os.environ.get("POSTGRES_HOST") or "").strip()
    if h:
        return h
    url = (os.environ.get("POSTGRES_DB_URL") or "").strip()
    if url:
        try:
            return (urlparse(url).hostname or "")[:120]
        except Exception:
            return ""
    return ""


def agent_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": SESSION_ID,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": {**data, "db_host": db_host_fingerprint()},
            "timestamp": int(time.time() * 1000),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion
