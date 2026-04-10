"""Map Streamlit Cloud secrets into os.environ for libraries that only read env vars."""

from __future__ import annotations

import os
from urllib.parse import urlparse


def is_supabase_direct_db_url(db_url: str | None) -> bool:
    """True if URL targets db.*.supabase.co (IPv6 on direct; often fails on Streamlit Cloud)."""
    if not db_url or not isinstance(db_url, str):
        return False
    try:
        host = (urlparse(db_url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith(".supabase.co") and host.startswith("db.")


def looks_like_ipv6_routing_failure(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "cannot assign requested address" in msg
        or "network is unreachable" in msg
        or "no route to host" in msg
    )


def streamlit_warn_supabase_direct_url() -> None:
    """Show one clear fix hint in Streamlit when Secrets still use db.*.supabase.co."""
    try:
        import streamlit as st

        st.error(
            "`POSTGRES_DB_URL` points at Supabase **direct** host (`db.*.supabase.co`). "
            "Streamlit Cloud often cannot connect (IPv6). In **App settings → Secrets**, set "
            "`POSTGRES_DB_URL` to the **Session pooler** URI (host contains `pooler.supabase.com`, "
            "username `postgres.yourprojectref`), then **Reboot** the app."
        )
    except Exception:
        pass


def hydrate_secrets_into_environ() -> None:
    try:
        import streamlit as st

        s = st.secrets
        # Always apply secrets when present so Cloud updates win over any stale env
        # (e.g. old direct db.* URL vs session pooler pooler.supabase.com).
        for key in (
            "POSTGRES_DB_URL",
            "SERVO_SAVER_API_CONSUMER_ID",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
        ):
            if key in s:
                os.environ[key] = str(s[key])
    except Exception:
        pass
