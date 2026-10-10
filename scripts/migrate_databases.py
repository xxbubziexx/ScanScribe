"""Migrate legacy three-database setup into unified scanscribe.db."""
import logging
from pathlib import Path
import shutil
import sqlite3

logger = logging.getLogger(__name__)


def _copy_matching_columns(cur: sqlite3.Cursor, target_table: str, source_schema: str, source_table: str) -> None:
    """Copy rows using only matching column names between legacy and target tables."""
    try:
        cur.execute(f"PRAGMA {source_schema}.table_info('{source_table}');")
        source_cols = {row[1] for row in cur.fetchall()}
        if not source_cols:
            return

        cur.execute(f"PRAGMA table_info('{target_table}');")
        target_cols = {row[1] for row in cur.fetchall()}
        if not target_cols:
            return

        common = [c for c in source_cols if c in target_cols]
        if not common:
            return

        col_list = ", ".join(f'"{c}"' for c in common)
        cur.execute(
            f'INSERT OR IGNORE INTO "{target_table}" ({col_list}) SELECT {col_list} FROM {source_schema}."{source_table}";'
        )
    except sqlite3.OperationalError as e:
        logger.warning(f"Note during copying {source_table} -> {target_table}: {e}")


def migrate_to_unified(data_dir: Path, log_dir: Path = None) -> None:
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
            _copy_matching_columns(cur, "log_entries", "legacy_logs", "log_entries")
            _copy_matching_columns(cur, "hour_summaries", "legacy_logs", "hour_summaries")
            conn.commit()
            logger.info("Migrated logs data successfully.")
        finally:
            cur.execute("DETACH DATABASE legacy_logs;")

    if events_db.is_file():
        logger.info(f"Attaching legacy events database: {events_db}")
        cur.execute(f"ATTACH DATABASE '{events_db}' AS legacy_events;")
        try:
            _copy_matching_columns(cur, "monitors", "legacy_events", "monitors")
            _copy_matching_columns(cur, "events", "legacy_events", "events")
            _copy_matching_columns(cur, "event_transcript_links", "legacy_events", "event_transcript_links")
            _copy_matching_columns(cur, "span_store", "legacy_events", "span_store")
            _copy_matching_columns(cur, "entity_observations", "legacy_events", "entity_observations")
            _copy_matching_columns(cur, "pipeline_debug_log", "legacy_events", "pipeline_debug_log")
            _copy_matching_columns(cur, "system_settings", "legacy_events", "system_settings")
            conn.commit()
            logger.info("Migrated events data successfully.")
        finally:
            cur.execute("DETACH DATABASE legacy_events;")

    conn.close()
    logger.info("Database consolidation complete.")


if __name__ == "__main__":
    from app.config import get_settings

    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    migrate_to_unified(s.db_path.parent, Path(s.log_dir))
