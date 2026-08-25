"""Database configuration and session management."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .config import get_settings


def utcnow() -> datetime:
    """Timezone-aware UTC 'now' for model defaults.

    SQLite's ``CURRENT_TIMESTAMP`` (what ``func.now()`` compiles to) stores naive UTC;
    SQLAlchemy reads it back without tzinfo, so downstream serializers can't distinguish
    it from a local wall-clock value. Binding Python-side aware datetimes via ``default``
    keeps the tzinfo on the outbound row and lets the frontend convert UTC -> local.
    """
    return datetime.now(timezone.utc)

settings = get_settings()

# Create SQLite engine for users database
SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=False,  # Set to True for SQL debugging
)

# Create separate engine for logs database
LOGS_DB_PATH = Path(settings.log_dir) / "scanscribe_logs.db"
LOGS_DATABASE_URL = f"sqlite:///{LOGS_DB_PATH}"

logs_engine = create_engine(
    LOGS_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Events pipeline DB (Worker/Master per monitor)
EVENTS_DB_PATH = settings.db_path.parent / "scanscribe_events.db"
EVENTS_DATABASE_URL = f"sqlite:///{EVENTS_DB_PATH}"

events_engine = create_engine(
    EVENTS_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
LogsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=logs_engine)
EventsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=events_engine)

Base = declarative_base()
LogsBase = declarative_base()
EventsBase = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_logs_db() -> Generator[Session, None, None]:
    """Dependency for getting logs database sessions."""
    db = LogsSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_events_db() -> Generator[Session, None, None]:
    """Dependency for getting events pipeline database sessions."""
    db = EventsSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    # Ensure all model modules are imported so Base.metadata is complete
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    LogsBase.metadata.create_all(bind=logs_engine)

    # Events pipeline DB
    from .models import event  # noqa: F401
    EventsBase.metadata.create_all(bind=events_engine)

    # Logs DB Migrations
    with logs_engine.connect() as conn:
        r = conn.execute(text("PRAGMA table_info(log_entries)"))
        log_cols = [row[1] for row in r.fetchall()]
        if "is_reviewed" not in log_cols:
            conn.execute(text("ALTER TABLE log_entries ADD COLUMN is_reviewed BOOLEAN DEFAULT 0"))
            conn.commit()
        if "corrected_transcript" not in log_cols:
            conn.execute(text("ALTER TABLE log_entries ADD COLUMN corrected_transcript VARCHAR"))
            conn.commit()

    # Migrations
    with events_engine.connect() as conn:
        r = conn.execute(text("PRAGMA table_info(monitors)"))
        m_cols = [row[1] for row in r.fetchall()]
        if "geo_region" not in m_cols:
            conn.execute(text("ALTER TABLE monitors ADD COLUMN geo_region VARCHAR(255)"))
            conn.commit()
        if "known_units" not in m_cols:
            conn.execute(text("ALTER TABLE monitors ADD COLUMN known_units TEXT"))
            conn.commit()

        r = conn.execute(text("PRAGMA table_info(events)"))
        cols = [row[1] for row in r.fetchall()]
        if "close_recommendation" not in cols:
            conn.execute(text("ALTER TABLE events ADD COLUMN close_recommendation BOOLEAN"))
            conn.commit()
        if "broadcast_type" not in cols:
            conn.execute(text("ALTER TABLE events ADD COLUMN broadcast_type VARCHAR(64)"))
            conn.commit()
        if "latitude" not in cols:
            conn.execute(text("ALTER TABLE events ADD COLUMN latitude FLOAT"))
            conn.commit()
        if "longitude" not in cols:
            conn.execute(text("ALTER TABLE events ADD COLUMN longitude FLOAT"))
            conn.commit()
        if "resolved_address" not in cols:
            conn.execute(text("ALTER TABLE events ADD COLUMN resolved_address VARCHAR(500)"))
            conn.commit()

        r = conn.execute(text("PRAGMA table_info(event_transcript_links)"))
        link_cols = [row[1] for row in r.fetchall()]
        if "entities_json" not in link_cols:
            conn.execute(text("ALTER TABLE event_transcript_links ADD COLUMN entities_json TEXT"))
            conn.commit()
        r = conn.execute(text("PRAGMA table_info(event_transcript_links)"))
        link_cols2 = [row[1] for row in r.fetchall()]
        if "llm_reason" not in link_cols2:
            conn.execute(text("ALTER TABLE event_transcript_links ADD COLUMN llm_reason TEXT"))
            conn.commit()
        # span_store schema changed (dropped legacy label columns, added 'status').
        # Wipe + recreate when the legacy columns are present — user opted-in to a clean slate
        # for entity observations (no backfill). Safe: SpanStore is regenerated from new ingest.
        r = conn.execute(text("PRAGMA table_info(span_store)"))
        span_cols = {row[1] for row in r.fetchall()}
        _LEGACY_SPAN_COLS = {"cross_streets", "persons", "vehicles", "plates"}
        if span_cols & _LEGACY_SPAN_COLS:
            conn.execute(text("DROP TABLE IF EXISTS span_store"))
            conn.commit()
            # Recreate via SQLAlchemy metadata so new schema is applied.
            from .models.event import SpanStore as _SpanStore
            _SpanStore.__table__.create(bind=events_engine, checkfirst=True)
