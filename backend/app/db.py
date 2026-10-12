from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = (settings.database_url or "").strip() or "sqlite:///./data/prospects.db"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql") and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


_URL = database_url()
_ENGINE_KW: dict = {"pool_pre_ping": True}
if _is_sqlite(_URL):
    _ENGINE_KW["connect_args"] = {"check_same_thread": False}
else:
    _ENGINE_KW["pool_recycle"] = 300

engine = create_engine(_URL, **_ENGINE_KW)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS paid_credits INTEGER DEFAULT 0"))
            return
        if engine.dialect.name != "sqlite":
            return
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(research_runs)"))]
        if "kind" not in cols:
            conn.execute(text("ALTER TABLE research_runs ADD COLUMN kind VARCHAR(40) DEFAULT 'outbound'"))
        inquiry_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(inquiries)"))]
        if inquiry_cols and "wants_help" not in inquiry_cols:
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN wants_help BOOLEAN DEFAULT 0"))
        if inquiry_cols and "search_count" not in inquiry_cols:
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN search_count INTEGER DEFAULT 1"))
        if inquiry_cols and "updated_at" not in inquiry_cols:
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN updated_at DATETIME"))
        if inquiry_cols and "paid_credits" not in inquiry_cols:
            conn.execute(text("ALTER TABLE inquiries ADD COLUMN paid_credits INTEGER DEFAULT 0"))
        if inquiry_cols:
            conn.execute(
                text(
                    "UPDATE inquiries SET email = lower(trim(email)) "
                    "WHERE email IS NOT NULL AND email != lower(trim(email))"
                )
            )
            conn.execute(
                text(
                    "DELETE FROM inquiries WHERE id NOT IN "
                    "(SELECT MIN(id) FROM inquiries GROUP BY email)"
                )
            )
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_inquiries_email ON inquiries(email)"))
