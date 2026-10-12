from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
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
