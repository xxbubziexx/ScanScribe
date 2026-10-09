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
