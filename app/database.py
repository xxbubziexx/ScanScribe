"""Unified database configuration and session management with WAL mode and connection pooling."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .config import get_settings


def utcnow() -> datetime:
    """Timezone-aware UTC 'now' for model defaults.

    SQLite's CURRENT_TIMESTAMP stores naive UTC; binding Python-side aware
    datetimes keeps tzinfo on the row so downstream consumers can safely parse it.
    """
    return datetime.now(timezone.utc)


settings = get_settings()

SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.db_path}"

# Ensure parent directory for database exists
try:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 15,  # 15s driver level lock wait
    },
    pool_pre_ping=True,
    echo=False,
)


# Enforce SQLite PRAGMAs on every connection checkout
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # Write-Ahead Logging allows concurrent readers alongside writers
    cursor.execute("PRAGMA journal_mode=WAL;")
    # Wait up to 5000ms if another thread is writing instead of throwing immediately
    cursor.execute("PRAGMA busy_timeout=5000;")
    # Enforce referential integrity
    cursor.execute("PRAGMA foreign_keys=ON;")
    # Synchronous NORMAL is fully crash-safe in WAL mode and drastically faster
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Backward-compatibility aliases for smooth transition across modules
LogsBase = Base
EventsBase = Base
logs_engine = engine
events_engine = engine
LogsSessionLocal = SessionLocal
EventsSessionLocal = SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_logs_db() -> Generator[Session, None, None]:
    """Backward compatibility alias for get_db."""
    yield from get_db()


def get_events_db() -> Generator[Session, None, None]:
    """Backward compatibility alias for get_db."""
    yield from get_db()


def auto_migrate_legacy_databases() -> None:
    """Auto-detect legacy multi-database setup and migrate into unified database."""
    try:
        data_dir = Path(settings.db_path).parent
        log_dir = Path(settings.log_dir) if getattr(settings, "log_dir", None) else data_dir.parent / "logs"
        marker = data_dir / ".migrated_unified"
        if marker.is_file():
            return

        legacy_logs = log_dir / "scanscribe_logs.db"
        legacy_events = data_dir / "scanscribe_events.db"
        if legacy_logs.is_file() or legacy_events.is_file():
            import logging
            from scripts.migrate_databases import migrate_to_unified

            logging.getLogger(__name__).info("Legacy databases detected; consolidating into unified database...")
            migrate_to_unified(data_dir, log_dir)
            try:
                marker.write_text("migrated\n", encoding="utf-8")
            except Exception:
                pass
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Legacy database auto-migration check note: %s", exc)


def init_db():
    """Initialize database tables with complete model metadata."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    auto_migrate_legacy_databases()

