"""Migrate legacy three-database setup into unified scanscribe.db."""
import sqlite3
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate_to_unified(data_dir: Path, log_dir: Path = None):
    """Migrate scanscribe.db, scanscribe_logs.db, and scanscribe_events.db into unified database."""
    target_db = data_dir / "scanscribe.db"
    if log_dir is None:
        log_dir = data_dir.parent / "logs"
    logs_db = log_dir / "scanscribe_logs.db"
    events_db = data_dir / "scanscribe_events.db"

    # Backup existing databases if found
    for p in [target_db, logs_db, events_db]:
        if p.is_file():
            shutil.copy2(p, p.with_suffix(".db.bak"))
            logger.info(f"Backed up {p.name} to {p.name}.bak")

    # Connect to target unified DB
    conn = sqlite3.connect(target_db)
    cur = conn.cursor()

    if logs_db.is_file():
        logger.info(f"Attaching legacy logs database: {logs_db}")
        cur.execute(f"ATTACH DATABASE '{logs_db}' AS legacy_logs;")
        try:
            cur.execute("INSERT OR IGNORE INTO log_entries SELECT * FROM legacy_logs.log_entries;")
            cur.execute("INSERT OR IGNORE INTO hour_summaries SELECT * FROM legacy_logs.hour_summaries;")
            conn.commit()
            logger.info("Migrated logs data successfully.")
        except sqlite3.OperationalError as e:
            logger.warning(f"Note during logs migration: {e}")
        finally:
            cur.execute("DETACH DATABASE legacy_logs;")

    if events_db.is_file():
        logger.info(f"Attaching legacy events database: {events_db}")
        cur.execute(f"ATTACH DATABASE '{events_db}' AS legacy_events;")
        try:
            cur.execute("INSERT OR IGNORE INTO monitors SELECT * FROM legacy_events.monitors;")
            cur.execute("INSERT OR IGNORE INTO events SELECT * FROM legacy_events.events;")
            cur.execute("INSERT OR IGNORE INTO event_transcript_links SELECT * FROM legacy_events.event_transcript_links;")
            cur.execute("INSERT OR IGNORE INTO span_store SELECT * FROM legacy_events.span_store;")
            cur.execute("INSERT OR IGNORE INTO entity_observations SELECT * FROM legacy_events.entity_observations;")
            cur.execute("INSERT OR IGNORE INTO pipeline_debug_log SELECT * FROM legacy_events.pipeline_debug_log;")
            cur.execute("INSERT OR IGNORE INTO system_settings SELECT * FROM legacy_events.system_settings;")
            conn.commit()
            logger.info("Migrated events data successfully.")
        except sqlite3.OperationalError as e:
            logger.warning(f"Note during events migration: {e}")
        finally:
            cur.execute("DETACH DATABASE legacy_events;")

    conn.close()
    logger.info("Database consolidation complete.")


if __name__ == "__main__":
    from app.config import get_settings

    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    migrate_to_unified(s.db_path.parent, Path(s.log_dir))
