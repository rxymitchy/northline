"""Copy every Northline table from one database to another (e.g. Render Postgres -> Neon).

Usage (from the backend folder):
    py -3.13 scripts/copy_db.py "<FROM_DATABASE_URL>" "<TO_DATABASE_URL>"
    py -3.13 scripts/copy_db.py "<FROM_DATABASE_URL>" vercel     (target read from .env.vercel)

The target tables are created if missing. The script refuses to run if the target already
has rows, so it can never overwrite live data. The source is only read, never changed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, select, text  # noqa: E402


def _vercel_url() -> str:
    """Read the Neon URL pulled by `vercel env pull .env.vercel` (direct connection preferred)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.vercel")
    found = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            key, _, val = line.strip().partition("=")
            found[key] = val.strip().strip('"')
    url = found.get("DATABASE_URL_UNPOOLED") or found.get("DATABASE_URL") or ""
    if not url:
        raise SystemExit("No DATABASE_URL in .env.vercel. Run: vercel env pull .env.vercel --environment production")
    return url


def _url(raw: str) -> str:
    url = raw.strip()
    if url.lower() == "vercel":
        url = _vercel_url()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql") and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _fill_required(table, row: dict) -> dict:
    """Older rows can hold NULL in columns that are now required: fill them sensibly."""
    for col in table.columns:
        if col.nullable or col.primary_key or row.get(col.name) is not None:
            continue
        if col.name.endswith("_at") and row.get("created_at") is not None:
            row[col.name] = row["created_at"]
        elif col.default is not None and col.default.is_scalar:
            row[col.name] = col.default.arg
        elif col.default is not None and col.default.is_callable:
            row[col.name] = col.default.arg(None)
    return row


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    from app import models  # noqa: F401  (registers tables)
    from app.db import Base

    src = create_engine(_url(sys.argv[1]))
    dst = create_engine(_url(sys.argv[2]))
    tables = Base.metadata.sorted_tables  # parents before children

    Base.metadata.create_all(dst)
    with dst.connect() as conn:
        busy = {t.name: conn.execute(select(func.count()).select_from(t)).scalar() for t in tables}
    if any(busy.values()):
        print("Target database already has data, stopping so nothing is overwritten:")
        for name, n in busy.items():
            if n:
                print(f"  {name}: {n} rows")
        sys.exit(2)

    with src.connect() as s, dst.begin() as d:
        src_cols = {}
        for t in tables:
            try:
                src_cols[t.name] = {c["name"] for c in s.dialect.get_columns(s, t.name)}
            except Exception:
                src_cols[t.name] = set()
        for t in tables:
            have = src_cols.get(t.name) or set()
            if not have:
                print(f"  {t.name}: not in source, skipped")
                continue
            cols = [c for c in t.columns if c.name in have]
            rows = [_fill_required(t, dict(r._mapping)) for r in s.execute(select(*cols))]
            if rows:
                d.execute(t.insert(), rows)
            print(f"  {t.name}: {len(rows)} rows copied")
        if dst.dialect.name == "postgresql":
            # Move id counters past the copied rows so new inserts do not collide.
            for t in tables:
                if "id" in t.columns:
                    d.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {t.name}), 0) + 1, false)"
                        )
                    )
    print("Done.")


if __name__ == "__main__":
    main()
