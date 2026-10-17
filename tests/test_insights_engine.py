"""Characterization tests for the insights analytics engine (synthetic SQLite fixtures)."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import event as _event_models  # noqa: F401  (register tables)
from app.models.log_entry import LogEntry
from app.services import insights_engine as ie


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _add(db, ts: datetime, talkgroup="TG1", duration=6.0, proc=1.0, conf=0.9, deleted=False):
    db.add(
        LogEntry(
            filename=f"f_{ts.isoformat()}_{talkgroup}_{db.query(LogEntry).count()}.mp3",
            timestamp=ts,
            log_date=ts.date().isoformat(),
            duration=duration,
            transcript="test transmission",
            confidence=conf,
            processing_time=proc,
            talkgroup=talkgroup,
            is_deleted=deleted,
        )
    )


def test_hourly_activity_counts_by_hour_and_skips_deleted(db):
    day = date(2026, 10, 14)  # Wednesday
    _add(db, datetime(2026, 10, 14, 9, 5))
    _add(db, datetime(2026, 10, 14, 9, 40))
    _add(db, datetime(2026, 10, 14, 15, 0))
    _add(db, datetime(2026, 10, 14, 15, 1), deleted=True)
    db.commit()

    activity = ie.get_hourly_activity(db, day)
    assert len(activity) == 24
    assert activity[9]["count"] == 2
    assert activity[15]["count"] == 1
    assert activity[0]["count"] == 0


def test_diurnal_heatmap_day_of_week_and_hour_on_sqlite(db):
    # 2026-10-14 is a Wednesday (Sun=0 -> Wed=3)
    _add(db, datetime(2026, 10, 14, 9, 5))
    _add(db, datetime(2026, 10, 14, 9, 45))
    db.commit()

    hm = ie.get_diurnal_heatmap(db, date(2026, 10, 14), date(2026, 10, 14))
    assert hm["total_calls"] == 2
    assert hm["peak_day"] == "Wed"
    assert hm["peak_hour"] == "9 AM"
    wed = next(r for r in hm["matrix"] if r["day_label"] == "Wed")
    assert wed["hours"][9]["count"] == 2


def test_range_summary_and_activity_daily_buckets(db):
    for offset in range(3):
        _add(db, datetime(2026, 10, 12 + offset, 10, 0))
    db.commit()

    summary = ie.get_range_summary(db, date(2026, 10, 12), date(2026, 10, 14))
    assert summary["total"] == 3
    assert summary["range_days"] == 3

    activity = ie.get_range_activity(db, date(2026, 10, 12), date(2026, 10, 14))
    assert [p["count"] for p in activity] == [1, 1, 1]


def test_asr_quality_spectrum_tiers(db):
    base = datetime(2026, 10, 14, 8, 0)
    for i in range(6):
        _add(db, base + timedelta(minutes=i), conf=0.95)  # high
    for i in range(3):
        _add(db, base + timedelta(minutes=10 + i), conf=0.75)  # moderate
    for i in range(2):
        _add(db, base + timedelta(minutes=20 + i), conf=0.40)  # low
    db.commit()

    asr = ie.get_asr_quality_spectrum(db, date(2026, 10, 14), date(2026, 10, 14))
    assert asr["total_evaluated"] == 11
    assert asr["high_count"] == 6
    assert asr["moderate_count"] == 3
    assert asr["low_count"] == 2


def test_rtf_telemetry_real_data(db):
    base = datetime(2026, 10, 14, 8, 0)
    for i in range(5):
        _add(db, base + timedelta(minutes=i), duration=10.0, proc=2.0)
    db.commit()

    rtf = ie.get_rtf_telemetry(db, date(2026, 10, 14), date(2026, 10, 14))
    assert rtf["rtf"] == pytest.approx(0.2, abs=1e-3)
    assert rtf["status"] == "nominal"
    assert rtf["timeline"][8]["count"] == 5


def test_traffic_anomaly_flags_surge_hour(db):
    day = date(2026, 10, 14)
    # Quiet background across the day, large surge at 10:00
    for h in range(24):
        for m in range(2):
            _add(db, datetime(2026, 10, 14, h, m * 10), talkgroup="TG_BG")
    for m in range(40):
        _add(db, datetime(2026, 10, 14, 10, m), talkgroup="TG_FIRE")
    db.commit()

    out = ie.get_traffic_anomaly_telemetry(db, day)
    assert out["timeline"][10]["observed"] >= 40
    assert out["timeline"][10]["is_anomaly"] is True
    assert out["severity"] in {"high", "critical", "elevated"}
    assert out["primary_driver"] == "TG_FIRE"


def test_compute_insights_stats_payload_shape(db):
    _add(db, datetime(2026, 10, 14, 9, 0))
    db.commit()
    payload = ie.compute_insights_stats(db, date(2026, 10, 14), "hourly")
    for key in ("summary", "activity", "talkgroups", "heatmap", "rtf", "ner", "anomaly", "asr_quality"):
        assert key in payload
    assert payload["summary"]["total"] == 1


def test_no_demo_data_when_range_is_empty(db):
    day = date(2026, 10, 14)

    rtf = ie.get_rtf_telemetry(db, day, day)
    assert rtf["insufficient_data"] is True
    assert rtf["rtf"] == 0.0
    assert rtf["total_audio_s"] == 0.0

    asr = ie.get_asr_quality_spectrum(db, day, day)
    assert asr["insufficient_data"] is True
    assert asr["total_evaluated"] == 0

    ner = ie.get_ner_tactical_summary(db, day, day)
    assert ner["insufficient_data"] is True
    assert ner["all"] == []

    anomaly = ie.get_traffic_anomaly_telemetry(db, day)
    assert anomaly["insufficient_data"] is True
    assert anomaly["recent_anomalies"] == []
    assert anomaly["observed"] == 0


def test_anomaly_incident_comes_from_real_spans(db):
    from app.models.event import SpanStore

    day = date(2026, 10, 14)
    for h in range(24):
        _add(db, datetime(2026, 10, 14, h, 0), talkgroup="TG_BG")
    for m in range(40):
        _add(db, datetime(2026, 10, 14, 10, m), talkgroup="TG_FIRE")
    db.commit()

    surge_ids = [
        row[0]
        for row in db.query(LogEntry.id).filter(LogEntry.talkgroup == "TG_FIRE").all()
    ]
    for lid in surge_ids[:5]:
        db.add(SpanStore(monitor_id=1, log_entry_id=lid, evt_type="Structure Fire"))
    db.commit()

    out = ie.get_traffic_anomaly_telemetry(db, day, events_db=db)
    surge = next(a for a in out["recent_anomalies"] if a["hour"] == 10)
    assert surge["primary_driver"] == "TG_FIRE"
    assert surge["likely_incident"] == "Structure Fire"


def test_local_date_range_to_utc_helper():
    utc_start, utc_end = ie.local_date_range_to_utc(date(2026, 10, 14), date(2026, 10, 14))
    assert utc_start.tzinfo is not None
    assert utc_end.tzinfo is not None
    assert utc_end > utc_start


def test_parse_date_param_validation():
    from fastapi import HTTPException
    from app.routes.insights import parse_date_param

    d = parse_date_param("date", "2026-10-14")
    assert d == date(2026, 10, 14)
    assert parse_date_param("date", None) is None

    with pytest.raises(HTTPException) as exc_info:
        parse_date_param("date", "not-a-valid-date")
    assert exc_info.value.status_code == 422
