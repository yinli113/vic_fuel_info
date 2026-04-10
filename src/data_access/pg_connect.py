"""Postgres connections from DATABASE_URL-style strings.

Uses urllib parsing + explicit psycopg2 keyword args so usernames like ``postgres.<ref>``
and percent-encoded passwords behave reliably (avoids some libpq URI edge cases).
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import psycopg2


def connect_from_database_url(url: str):
    if not url or not isinstance(url, str):
        raise ValueError("database URL is empty")
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    if "postgres" not in scheme:
        raise ValueError("POSTGRES_DB_URL must use postgres:// or postgresql://")
    if not p.hostname:
        raise ValueError("POSTGRES_DB_URL missing host")
    user = unquote(p.username) if p.username else None
    password = unquote(p.password) if p.password is not None else None
    port = p.port or 5432
    path = (p.path or "").lstrip("/")
    dbname = path or "postgres"
    q = parse_qs(p.query)
    ssl_vals = q.get("sslmode", [])
    if ssl_vals:
        sslmode = ssl_vals[0]
    elif "supabase" in p.hostname.lower():
        sslmode = "require"
    else:
        sslmode = "prefer"
    kw: dict = {
        "host": p.hostname,
        "port": port,
        "dbname": dbname,
        "sslmode": sslmode,
    }
    if user is not None:
        kw["user"] = user
    if password is not None:
        kw["password"] = password
    return psycopg2.connect(**kw)
