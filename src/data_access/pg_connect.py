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
    url = url.strip()
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    if "postgres" not in scheme:
        raise ValueError("POSTGRES_DB_URL must use postgres:// or postgresql://")
    if not p.hostname:
        raise ValueError("POSTGRES_DB_URL missing host")
    host = (p.hostname or "").lower()
    user = unquote(p.username) if p.username else None
    # Supabase shared pooler (session mode on :5432) — username must be postgres.<project_ref>.
    # Plain "postgres" is for transaction mode (different host/port); wrong combo → auth as "postgres" fails.
    if "pooler.supabase.com" in host:
        suffix = "postgres."
        if not user or not user.startswith(suffix) or len(user) <= len(suffix):
            raise ValueError(
                "POSTGRES_DB_URL uses pooler.supabase.com but the username is not "
                "`postgres.<project-ref>`. Open Supabase → Connect → **Session pooler**, copy the "
                "URI (user looks like `postgres.qegzrxnfyrtzdtuvcltk`, not just `postgres`). "
                "Reset the **Database password** in Project Settings → Database if login still fails."
            )
    password = unquote(p.password) if p.password is not None else None
    port = p.port or 5432
    path = (p.path or "").lstrip("/")
    dbname = path or "postgres"
    q = parse_qs(p.query)
    ssl_vals = q.get("sslmode", [])
    if ssl_vals:
        sslmode = ssl_vals[0]
    elif "supabase" in host:
        sslmode = "require"
    else:
        sslmode = "prefer"
    kw: dict = {
        "host": p.hostname or "",
        "port": port,
        "dbname": dbname,
        "sslmode": sslmode,
    }
    if user is not None:
        kw["user"] = user
    if password is not None:
        kw["password"] = password
    return psycopg2.connect(**kw)
