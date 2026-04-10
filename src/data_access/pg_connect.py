"""Postgres connections from POSTGRES_DB_URL or discrete POSTGRES_* env vars."""

from __future__ import annotations

import os
from urllib.parse import parse_qs, unquote, urlparse

import psycopg2


def _validate_supabase_pooler_user(host: str, user: str | None) -> None:
    host_l = host.lower()
    if "pooler.supabase.com" not in host_l:
        return
    suffix = "postgres."
    if not user or not user.startswith(suffix) or len(user) <= len(suffix):
        raise ValueError(
            "Supabase session pooler needs user `postgres.<project-ref>` (see Connect → Session pooler). "
            "Plain `postgres` is wrong for pooler.supabase.com:5432. "
            "Or set POSTGRES_HOST / POSTGRES_USER / POSTGRES_PASSWORD separately in Secrets."
        )


def connect_from_database_url(url: str):
    if not url or not isinstance(url, str):
        raise ValueError("database URL is empty")
    url = url.strip()
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    if "postgres" not in scheme:
        raise ValueError("POSTGRES_DB_URL must use postgres:// or postgresql://")
    if not p.hostname:
        raise ValueError("POSTGRES_DB_URL missing host")
    host = p.hostname or ""
    host_l = host.lower()
    user = unquote(p.username) if p.username else None
    _validate_supabase_pooler_user(host_l, user)
    password = unquote(p.password) if p.password is not None else None
    port = p.port or 5432
    path = (p.path or "").lstrip("/")
    dbname = path or "postgres"
    q = parse_qs(p.query)
    ssl_vals = q.get("sslmode", [])
    if ssl_vals:
        sslmode = ssl_vals[0]
    elif "supabase" in host_l:
        sslmode = "require"
    else:
        sslmode = "prefer"
    kw: dict = {
        "host": host,
        "port": port,
        "dbname": dbname,
        "sslmode": sslmode,
    }
    if user is not None:
        kw["user"] = user
    if password is not None:
        kw["password"] = password
    return psycopg2.connect(**kw)


def connect_postgres():
    """Prefer discrete POSTGRES_* vars if POSTGRES_HOST+USER+PASSWORD are set; else POSTGRES_DB_URL."""
    host = (os.environ.get("POSTGRES_HOST") or "").strip()
    user = (os.environ.get("POSTGRES_USER") or "").strip()
    has_pw = "POSTGRES_PASSWORD" in os.environ
    password = os.environ.get("POSTGRES_PASSWORD") if has_pw else None

    if host and user and has_pw:
        _validate_supabase_pooler_user(host.lower(), user)
        port = int((os.environ.get("POSTGRES_PORT") or "5432").strip() or "5432")
        dbname = (os.environ.get("POSTGRES_DBNAME") or "postgres").strip() or "postgres"
        sslmode = (os.environ.get("POSTGRES_SSLMODE") or "").strip()
        if not sslmode:
            sslmode = "require" if "supabase" in host.lower() else "prefer"
        return psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password if password is not None else "",
            dbname=dbname,
            sslmode=sslmode,
        )

    url = (os.environ.get("POSTGRES_DB_URL") or "").strip()
    if url:
        return connect_from_database_url(url)

    raise ValueError(
        "Database not configured: set POSTGRES_DB_URL, or set POSTGRES_HOST, POSTGRES_USER, "
        "and POSTGRES_PASSWORD (optional: POSTGRES_PORT, POSTGRES_DBNAME, POSTGRES_SSLMODE)."
    )


def postgres_connection_cache_key() -> str:
    """Stable key for Streamlit cache when URL or password changes."""
    host = (os.environ.get("POSTGRES_HOST") or "").strip()
    user = (os.environ.get("POSTGRES_USER") or "").strip()
    if host and user and "POSTGRES_PASSWORD" in os.environ:
        port = (os.environ.get("POSTGRES_PORT") or "5432").strip()
        dbname = (os.environ.get("POSTGRES_DBNAME") or "postgres").strip()
        ssl = (os.environ.get("POSTGRES_SSLMODE") or "").strip()
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        return f"d|{host}|{port}|{user}|{pw}|{dbname}|{ssl}"
    return (os.environ.get("POSTGRES_DB_URL") or "").strip()


def is_pooler_supabase_environ() -> bool:
    url = (os.environ.get("POSTGRES_DB_URL") or "").lower()
    host = (os.environ.get("POSTGRES_HOST") or "").lower()
    return "pooler.supabase.com" in url or "pooler.supabase.com" in host
