"""Unit tests for Phase 2: Database Consolidation & Schema Constraints."""
import pytest
from sqlalchemy import text
from app.database import engine, SessionLocal
from app.models.log_entry import LogEntry
from app.models.event import Monitor, Event, EventTranscriptLink, SpanStore
from datetime import datetime, timezone


def test_sqlite_pragmas():
    """Verify WAL mode, busy timeout, synchronous, and foreign keys PRAGMAs."""
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
        foreign_keys = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous;")).scalar()

    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000
    assert foreign_keys == 1
    assert synchronous in (1, "1")  # NORMAL


def test_event_units_list_property():
    """Verify Event.units_list handles JSON lists, strings, and CSV gracefully."""
    e1 = Event(event_id="E1", monitor_id=1, units='["Engine 1", "Squad 2"]')
    assert e1.units_list == ["Engine 1", "Squad 2"]

    e2 = Event(event_id="E2", monitor_id=1, units="Engine 1, Truck 4")
    assert e2.units_list == ["Engine 1", "Truck 4"]

    e3 = Event(event_id="E3", monitor_id=1, units=None)
    assert e3.units_list == []

    e4 = Event(event_id="E4", monitor_id=1, units="")
    assert e4.units_list == []


def test_cascade_delete_and_foreign_keys():
    """Verify foreign key enforcement and cascade delete behavior."""
    from app.database import init_db
    init_db()
    db = SessionLocal()
    try:
        # Create monitor
        monitor = Monitor(name="Test Monitor", talkgroup_ids="[]")
        db.add(monitor)
        db.flush()

        # Create log entry
        log_entry = LogEntry(
            filename="test.wav",
            timestamp=datetime.now(timezone.utc),
            transcript="Test transmission",
        )
        db.add(log_entry)
        db.flush()

        # Create event
        event = Event(
            event_id="EVT-TEST-001",
            monitor_id=monitor.id,
            event_type="Structure Fire",
        )
        db.add(event)
        db.flush()

        # Link event to log entry
        link = EventTranscriptLink(
            event_id=event.id,
            log_entry_id=log_entry.id,
            entities_json="{}",
        )
        db.add(link)
        db.commit()

        # Verify link exists
        assert db.query(EventTranscriptLink).filter_by(id=link.id).count() == 1

        # Delete Event -> verify EventTranscriptLink is cascade deleted
        db.delete(event)
        db.commit()

        assert db.query(EventTranscriptLink).filter_by(id=link.id).count() == 0

        # LogEntry should still exist
        assert db.query(LogEntry).filter_by(id=log_entry.id).count() == 1
    finally:
        db.close()


def test_legacy_database_migration(tmp_path):
    """Verify that legacy multi-database setups migrate non-destructively."""
    import sqlite3
    from scripts.migrate_databases import migrate_to_unified

    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    log_dir.mkdir()

    # Create target unified db with empty tables
    target_db = data_dir / "scanscribe.db"
    conn_target = sqlite3.connect(target_db)
    conn_target.execute(
        "CREATE TABLE log_entries (id INTEGER PRIMARY KEY, filename TEXT, transcript TEXT, timestamp DATETIME);"
    )
    conn_target.execute(
        "CREATE TABLE monitors (id INTEGER PRIMARY KEY, name TEXT, talkgroup_ids TEXT, known_units TEXT);"
    )
    conn_target.close()

    # Create legacy logs db
    legacy_logs = log_dir / "scanscribe_logs.db"
    conn_logs = sqlite3.connect(legacy_logs)
    conn_logs.execute("CREATE TABLE log_entries (id INTEGER PRIMARY KEY, filename TEXT, transcript TEXT);")
    conn_logs.execute("INSERT INTO log_entries VALUES (101, 'legacy_call.wav', 'Officer en route');")
    conn_logs.commit()
    conn_logs.close()

    # Create legacy events db (monitors without known_units column)
    legacy_events = data_dir / "scanscribe_events.db"
    conn_events = sqlite3.connect(legacy_events)
    conn_events.execute("CREATE TABLE monitors (id INTEGER PRIMARY KEY, name TEXT, talkgroup_ids TEXT);")
    conn_events.execute("INSERT INTO monitors VALUES (1, 'Legacy Fire', '[\"FIRE-1\"]');")
    conn_events.commit()
    conn_events.close()

    # Run migration
    migrate_to_unified(data_dir, log_dir)

    # Verify backups exist
    assert (legacy_logs.with_suffix(".db.bak")).is_file()
    assert (legacy_events.with_suffix(".db.bak")).is_file()

    # Verify rows in target db
    conn = sqlite3.connect(target_db)
    cur = conn.cursor()
    cur.execute("SELECT id, filename, transcript FROM log_entries WHERE id = 101;")
    row_log = cur.fetchone()
    assert row_log == (101, "legacy_call.wav", "Officer en route")

    cur.execute("SELECT id, name, talkgroup_ids, known_units FROM monitors WHERE id = 1;")
    row_mon = cur.fetchone()
    assert row_mon == (1, "Legacy Fire", '["FIRE-1"]', None)
    conn.close()

