"""Map Streamlit Cloud secrets into os.environ for libraries that only read env vars."""

from __future__ import annotations

import os


def hydrate_secrets_into_environ() -> None:
    try:
        import streamlit as st

        s = st.secrets
        for key in (
            "POSTGRES_DB_URL",
            "SERVO_SAVER_API_CONSUMER_ID",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
        ):
            if key in s and not os.environ.get(key):
                os.environ[key] = str(s[key])
    except Exception:
        pass
