"""Integration tests for Database Overview, Audio Logs bulk ZIP, and NER CSV Exporter."""
import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all ORM tables on Base.metadata
from app.config import get_settings
from app.database import Base, get_events_db, get_logs_db
from app.main import app
from app.models.event import (
    EntityObservation,
    Event,
    EventTranscriptLink,
    Monitor,
    SpanStore,
    SystemSetting,
)
from app.models.log_entry import LogEntry
from app.models.user import User
from app.routes.auth import get_current_user


def _make_sqlite_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(eng, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

    Base.metadata.create_all(bind=eng)
    return eng, sessionmaker(autocommit=False, autoflush=False, bind=eng)


@pytest.fixture()
def db_ctx():
    """Isolated SQLite session factory + FastAPI dependency overrides."""
    eng, Session = _make_sqlite_session()
    active_user = {"user": User(id=1, username="admin", email="admin@localhost", is_active=True, is_admin=True)}

    def _override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def _override_user():
        return active_user["user"]

    app.dependency_overrides[get_logs_db] = _override_db
    app.dependency_overrides[get_events_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    try:
        yield Session, active_user
    finally:
        app.dependency_overrides.clear()
        eng.dispose()


def _seed_dashboard_data(Session, audio_dir: Path):
    """Populate realistic logs, monitors, spans, observations, and events."""
    db = Session()
    try:
        today = datetime.now().date()
        now_local = datetime.now()
        yesterday_local = now_local - timedelta(days=1)

        # Save one real audio file under audio_dir
        rel_audio = f"{today.strftime('%Y/%m/%d')}/clip1.wav"
        real_audio = audio_dir / rel_audio
        real_audio.parent.mkdir(parents=True, exist_ok=True)
        real_audio.write_bytes(b"RIFFtestwavdata")

        log1 = LogEntry(
            filename="clip1.wav",
            timestamp=now_local,
            log_date=today.isoformat(),
            duration=12.5,
            file_size=real_audio.stat().st_size,
            audio_path=f"audio_storage/{rel_audio}",
            transcript="Engine 1 responding to 123 Main St for structure fire",
            confidence=0.94,
            talkgroup="FIRE-DISP",
            is_reviewed=True,
            corrected_transcript="Engine 1 responding to 123 Main St for structure fire",
            is_deleted=False,
        )
        log2 = LogEntry(
            filename="clip2.wav",
            timestamp=yesterday_local,
            log_date=(today - timedelta(days=1)).isoformat(),
            duration=7.0,
            file_size=2048,
            audio_path="file not saved",
            transcript="Medic 4 en route to 123 Main St",
            confidence=0.88,
            talkgroup="EMS-TAC",
            is_reviewed=False,
            is_deleted=False,
        )
        log_deleted = LogEntry(
            filename="deleted.wav",
            timestamp=now_local,
            log_date=today.isoformat(),
            duration=5.0,
            file_size=1024,
            audio_path="file not saved",
            transcript="Deleted entry must be excluded",
            talkgroup="FIRE-DISP",
            is_deleted=True,
        )
        db.add_all([log1, log2, log_deleted])
        db.flush()

        mon = Monitor(
            name="County Fire & EMS",
            enabled=True,
            talkgroup_ids='["FIRE-DISP", "EMS-TAC"]',
            keyword_config='["EVT_TYPE"]',
        )
        db.add(mon)
        db.flush()

        span1 = SpanStore(
            monitor_id=mon.id,
            talkgroup="FIRE-DISP",
            transcript=log1.transcript,
            evt_type="structure fire",
            units="Engine 1",
            addresses="123 Main St",
            log_entry_id=log1.id,
            created_at=datetime.now(timezone.utc),
        )
        span2 = SpanStore(
            monitor_id=mon.id,
            talkgroup="EMS-TAC",
            transcript=log2.transcript,
            units="Medic 4",
            addresses="123 Main St",
            log_entry_id=log2.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([span1, span2])
        db.flush()

        obs = [
            EntityObservation(
                span_store_id=span1.id,
                monitor_id=mon.id,
                talkgroup="FIRE-DISP",
                log_entry_id=log1.id,
                ts=datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc),
                label="UNIT",
                canonical="Engine 1",
                raw="Engine 1",
            ),
            EntityObservation(
                span_store_id=span1.id,
                monitor_id=mon.id,
                talkgroup="FIRE-DISP",
                log_entry_id=log1.id,
                ts=datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc),
                label="ADDRESS",
                canonical="123 Main St",
                raw="123 Main St",
            ),
            EntityObservation(
                span_store_id=span2.id,
                monitor_id=mon.id,
                talkgroup="EMS-TAC",
                log_entry_id=log2.id,
                ts=datetime(2026, 11, 24, 13, 0, 0, tzinfo=timezone.utc),
                label="ADDRESS",
                canonical="123 Main St",
                raw="123 Main St",
            ),
            EntityObservation(
                span_store_id=span2.id,
                monitor_id=mon.id,
                talkgroup="EMS-TAC",
                log_entry_id=log2.id,
                ts=datetime(2026, 11, 24, 13, 0, 0, tzinfo=timezone.utc),
                label="UNIT",
                canonical="Medic 4",
                raw="Medic 4",
            ),
        ]
        db.add_all(obs)

        ev = Event(
            event_id="evt_test_001",
            monitor_id=mon.id,
            status="open",
            event_type="Structure Fire",
            created_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        db.add(SystemSetting(key="audio_layout", value="sharded"))
        db.commit()

        return {
            "log1_id": log1.id,
            "log2_id": log2.id,
            "log_deleted_id": log_deleted.id,
            "monitor_id": mon.id,
            "obs_ids": [o.id for o in obs],
        }
    finally:
        db.close()


def test_maintenance_overview_admin_only_and_metrics(db_ctx, tmp_path):
    """GET /api/maintenance/overview enforces admin role and returns accurate counts and telemetry."""
    Session, active_user = db_ctx
    _seed_dashboard_data(Session, tmp_path)
    client = TestClient(app)

    # Non-admin must get 403
    active_user["user"] = User(id=2, username="viewer", email="viewer@localhost", is_active=True, is_admin=False)
    r_forbidden = client.get("/api/maintenance/overview")
    assert r_forbidden.status_code == 403

    # Admin succeeds
    active_user["user"] = User(id=1, username="admin", email="admin@localhost", is_active=True, is_admin=True)
    r = client.get("/api/maintenance/overview")
    assert r.status_code == 200
    body = r.json()

    tables_by_key = {t["key"]: t for t in body["tables"]}
    # Soft-deleted entry must be excluded
    assert tables_by_key["logs"]["row_count"] == 2
    assert tables_by_key["logs"]["secondary_value"] == "1"  # 1 reviewed
    assert tables_by_key["spans"]["row_count"] == 2
    assert tables_by_key["entities"]["row_count"] == 4
    assert tables_by_key["entities"]["secondary_value"] == "3"  # Engine 1, 123 Main St, Medic 4
    assert tables_by_key["events"]["row_count"] == 1
    assert tables_by_key["events"]["secondary_value"] == "1"  # 1 open
    assert tables_by_key["monitors"]["row_count"] == 1

    ner = body["ner"]
    assert ner["total_logs"] == 2
    assert ner["covered_logs"] == 2
    assert ner["coverage_pct"] == 100.0
    assert ner["total_observations"] == 4
    labels = {item["label"]: item for item in ner["labels"]}
    assert labels["ADDRESS"]["total_count"] == 2
    assert labels["ADDRESS"]["unique_raw_count"] == 1
    assert labels["UNIT"]["total_count"] == 2
    assert labels["UNIT"]["unique_raw_count"] == 2

    storage = body["storage"]
    assert storage["audio_files_count"] == 1
    assert storage["audio_layout"] == "sharded"
    assert storage["page_size"] > 0
    assert len(body["daily_volume"]) == 7
    assert body["logs_last_24h"] >= 1
    assert any(tg["talkgroup"] == "FIRE-DISP" for tg in body["top_talkgroups_24h"])


def test_logs_talkgroup_filter_and_bulk_zip_download(db_ctx, tmp_path):
    """GET /api/logs?talkgroup= filters accurately and POST /api/logs/bulk-download builds audio+CSV ZIP."""
    Session, _ = db_ctx
    seeded = _seed_dashboard_data(Session, tmp_path)
    client = TestClient(app)

    # Talkgroup filter
    r_tg = client.get("/api/logs", params={"talkgroup": "EMS-TAC"})
    assert r_tg.status_code == 200
    tg_data = r_tg.json()
    assert tg_data["total"] == 1
    assert tg_data["logs"][0]["id"] == seeded["log2_id"]

    # Empty IDs rejected by schema validation
    r_empty = client.post("/api/logs/bulk-download", json={"ids": []})
    assert r_empty.status_code == 422

    # Bulk download with 1 real audio file + 1 missing/unsaved file + 1 soft-deleted ID
    settings = get_settings()
    with patch.object(settings, "output_dir", str(tmp_path)):
        r_zip = client.post(
            "/api/logs/bulk-download",
            json={"ids": [seeded["log1_id"], seeded["log2_id"], seeded["log_deleted_id"]]},
        )

    assert r_zip.status_code == 200
    assert r_zip.headers["content-type"] == "application/zip"
    assert r_zip.headers["x-export-count"] == "2"
    assert r_zip.headers["x-audio-count"] == "1"

    with zipfile.ZipFile(io.BytesIO(r_zip.content), "r") as zf:
        names = zf.namelist()
        assert "metadata.csv" in names
        audio_entries = [n for n in names if n.startswith("audio/")]
        assert len(audio_entries) == 1
        assert zf.read(audio_entries[0]) == b"RIFFtestwavdata"

        meta_rows = list(csv.DictReader(io.StringIO(zf.read("metadata.csv").decode("utf-8"))))
        assert len(meta_rows) == 2
        by_id = {int(row["id"]): row for row in meta_rows}
        assert by_id[seeded["log1_id"]]["audio_included"] == "True"
        assert by_id[seeded["log1_id"]]["audio_file"] == audio_entries[0]
        assert by_id[seeded["log2_id"]]["audio_included"] == "False"
        assert by_id[seeded["log2_id"]]["audio_file"] == ""


def test_entities_csv_export_all_modes(db_ctx, tmp_path):
    """POST /api/events/entities/export-csv supports single/multi-label, dedupe, context, and selected IDs."""
    Session, _ = db_ctx
    seeded = _seed_dashboard_data(Session, tmp_path)
    client = TestClient(app)

    # Mode 1: Single label, raw only, no dedupe -> 1-column CSV
    r1 = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["ADDRESS"], "deduplicate": False, "include_context": False},
    )
    assert r1.status_code == 200
    assert r1.headers["x-row-count"] == "2"
    rows1 = list(csv.reader(io.StringIO(r1.text)))
    assert rows1[0] == ["raw"]
    assert rows1[1:] == [["123 Main St"], ["123 Main St"]]

    # Mode 2a: Single label, deduplicated with counts
    r2a = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["ADDRESS"], "deduplicate": True, "include_counts": True, "include_context": False},
    )
    assert r2a.status_code == 200
    rows2a = list(csv.reader(io.StringIO(r2a.text)))
    assert rows2a[0] == ["raw", "count"]
    assert rows2a[1] == ["123 Main St", "2"]

    # Mode 2b: Multi-label, deduplicated without counts
    r2b = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["UNIT", "ADDRESS"], "deduplicate": True, "include_counts": False, "include_context": False},
    )
    assert r2b.status_code == 200
    rows2b = list(csv.reader(io.StringIO(r2b.text)))
    assert rows2b[0] == ["label", "raw"]
    assert len(rows2b) == 4  # header + 3 unique (label, raw) pairs

    # Mode 3: With context, non-deduplicated -> includes transcript from SpanStore join
    r3 = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["UNIT"], "deduplicate": False, "include_context": True, "talkgroup": "FIRE"},
    )
    assert r3.status_code == 200
    assert r3.headers["x-row-count"] == "1"
    rows3 = list(csv.DictReader(io.StringIO(r3.text)))
    assert len(rows3) == 1
    assert rows3[0]["raw"] == "Engine 1"
    assert "structure fire" in rows3[0]["transcript"]

    # Mode 4: With context + deduplicated -> aggregated talkgroups and first/last seen
    r4 = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["ADDRESS"], "deduplicate": True, "include_context": True},
    )
    assert r4.status_code == 200
    rows4 = list(csv.DictReader(io.StringIO(r4.text)))
    assert len(rows4) == 1
    assert rows4[0]["count"] == "2"
    assert rows4[0]["talkgroups"] == "EMS-TAC | FIRE-DISP"

    # Mode 5: Selected observation IDs only
    r5 = client.post(
        "/api/events/entities/export-csv",
        json={"labels": ["UNIT", "ADDRESS"], "ids": [seeded["obs_ids"][0]], "deduplicate": False, "include_context": False},
    )
    assert r5.status_code == 200
    assert r5.headers["x-row-count"] == "1"
    rows5 = list(csv.reader(io.StringIO(r5.text)))
    assert rows5[1] == ["UNIT", "Engine 1"]


def test_monitor_delete_impact_and_cascade(db_ctx, tmp_path):
    """GET /api/events/monitors/{id}/delete-impact reports exact cascade counts and DELETE preserves log_entries."""
    Session, _ = db_ctx
    seeded = _seed_dashboard_data(Session, tmp_path)

    # Link a transcript to the seeded event so event_links_count == 1
    db = Session()
    try:
        ev = db.query(Event).filter(Event.monitor_id == seeded["monitor_id"]).first()
        db.add(EventTranscriptLink(event_id=ev.id, log_entry_id=seeded["log1_id"]))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)

    # 404 on missing monitor
    r_missing = client.get("/api/events/monitors/99999/delete-impact")
    assert r_missing.status_code == 404

    # Exact counts on seeded monitor
    r_impact = client.get(f"/api/events/monitors/{seeded['monitor_id']}/delete-impact")
    assert r_impact.status_code == 200
    impact = r_impact.json()
    assert impact["monitor_id"] == seeded["monitor_id"]
    assert impact["monitor_name"] == "County Fire & EMS"
    assert impact["events_count"] == 1
    assert impact["event_links_count"] == 1
    assert impact["span_store_count"] == 2
    assert impact["entity_observations_count"] == 4
    assert impact["total_dependent_rows"] == 8

    # Deleting the monitor cascades all 4 dependent tables while preserving log_entries
    r_del = client.delete(f"/api/events/monitors/{seeded['monitor_id']}")
    assert r_del.status_code == 200

    verify_db = Session()
    try:
        assert verify_db.query(Monitor).count() == 0
        assert verify_db.query(Event).count() == 0
        assert verify_db.query(EventTranscriptLink).count() == 0
        assert verify_db.query(SpanStore).count() == 0
        assert verify_db.query(EntityObservation).count() == 0
        # Transmissions (log_entries) are preserved
        assert verify_db.query(LogEntry).filter(LogEntry.is_deleted.is_not(True)).count() == 2
    finally:
        verify_db.close()
