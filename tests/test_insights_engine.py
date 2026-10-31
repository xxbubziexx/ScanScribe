"""Characterization tests for the insights analytics engine (synthetic SQLite fixtures)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import event as _event_models  # noqa: F401  (register tables)
from app.models.event import EntityObservation, SpanStore
from app.models.log_entry import LogEntry
from app.routes.insights import parse_date_param
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


def _add(
    db,
    ts: datetime,
    talkgroup="TG1",
    duration=6.0,
    proc=1.0,
    conf=0.9,
    deleted=False,
    transcript="test transmission",
):
    db.add(
        LogEntry(
            filename=f"f_{ts.isoformat()}_{talkgroup}_{db.query(LogEntry).count()}.mp3",
            timestamp=ts,
            log_date=ts.date().isoformat(),
            duration=duration,
            transcript=transcript,
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


def test_diurnal_heatmap_normalizes_peak_day_by_weekday_occurrences(db):
    # 8-day window from 2026-10-11 (Sun) to 2026-10-18 (Sun):
    # Sundays occur twice (3 calls each = 6 total, 3.0/day avg).
    # Wednesday 2026-10-14 occurs once with 5 calls (5.0/day avg).
    for m in range(3):
        _add(db, datetime(2026, 10, 11, 10, m))
        _add(db, datetime(2026, 10, 18, 10, m))
    for m in range(5):
        _add(db, datetime(2026, 10, 14, 14, m))
    db.commit()

    hm = ie.get_diurnal_heatmap(db, date(2026, 10, 11), date(2026, 10, 18))
    assert hm["peak_day"] == "Wed"


def test_range_summary_and_activity_daily_buckets(db):
    for offset in range(3):
        _add(db, datetime(2026, 10, 12 + offset, 10, 0))
    db.commit()

    summary = ie.get_range_summary(db, date(2026, 10, 12), date(2026, 10, 14))
    assert summary["total"] == 3
    assert summary["range_days"] == 3

    activity = ie.get_range_activity(db, date(2026, 10, 12), date(2026, 10, 14))
    assert [p["count"] for p in activity] == [1, 1, 1]


def test_asr_quality_spectrum_tiers_and_excludes_vad_rejected(db):
    base = datetime(2026, 10, 14, 8, 0)
    for i in range(6):
        _add(db, base + timedelta(minutes=i), conf=0.95)  # high
    for i in range(3):
        _add(db, base + timedelta(minutes=10 + i), conf=0.75)  # moderate
    for i in range(2):
        _add(db, base + timedelta(minutes=20 + i), conf=0.40)  # low
    # VAD_REJECTED and zero-confidence noise must not corrupt ASR quality metrics
    for i in range(5):
        _add(db, base + timedelta(minutes=30 + i), conf=0.0, transcript="VAD_REJECTED")
    db.commit()

    asr = ie.get_asr_quality_spectrum(db, date(2026, 10, 14), date(2026, 10, 14))
    assert asr["total_evaluated"] == 11
    assert asr["high_count"] == 6
    assert asr["moderate_count"] == 3
    assert asr["low_count"] == 2
    assert round(asr["high_percentage"] + asr["moderate_percentage"] + asr["low_percentage"], 1) == 100.0


def test_rtf_telemetry_real_data_and_excludes_vad_rejected(db):
    base = datetime(2026, 10, 14, 8, 0)
    for i in range(5):
        _add(db, base + timedelta(minutes=i), duration=10.0, proc=2.0, conf=0.9)
    # Fast VAD_REJECTED short-circuits must not skew Whisper RTF or confidence
    for i in range(5):
        _add(db, base + timedelta(minutes=10 + i), duration=10.0, proc=0.1, conf=0.0, transcript="VAD_REJECTED")
    db.commit()

    rtf = ie.get_rtf_telemetry(db, date(2026, 10, 14), date(2026, 10, 14))
    assert rtf["rtf"] == pytest.approx(0.2, abs=1e-3)
    assert rtf["avg_confidence"] == pytest.approx(90.0, abs=0.1)
    assert rtf["status"] == "nominal"
    assert rtf["timeline"][8]["count"] == 5


def test_talkgroup_breakdown_shares_computed_against_full_station_totals(db):
    day = date(2026, 10, 14)
    # Create 4 talkgroups, each with 10 calls of 10s (total 40 calls, 400s airtime)
    for idx in range(4):
        for m in range(10):
            _add(db, datetime(2026, 10, 14, 9, m), talkgroup=f"TG_{idx}", duration=10.0)
    db.commit()

    # Request limit=2; each talkgroup still accounts for 25% of station total (not 50% of top-2!)
    top2 = ie.get_talkgroup_breakdown(db, day, "hourly", limit=2)
    assert len(top2) == 2
    assert top2[0]["percentage"] == pytest.approx(25.0, abs=0.1)
    assert top2[0]["call_percentage"] == pytest.approx(25.0, abs=0.1)


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


def test_anomaly_incident_comes_from_real_spans_and_filters_noise(db):
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
    # Add more noisy spans than genuine incident spans to ensure noise is stripped
    for lid in surge_ids[:10]:
        db.add(SpanStore(monitor_id=1, log_entry_id=lid, evt_type="., 92., status check."))
    for lid in surge_ids[10:15]:
        db.add(SpanStore(monitor_id=1, log_entry_id=lid, evt_type="Structure Fire."))
    db.commit()

    out = ie.get_traffic_anomaly_telemetry(db, day, events_db=db)
    surge = next(a for a in out["recent_anomalies"] if a["hour"] == 10)
    assert surge["primary_driver"] == "TG_FIRE"
    assert surge["likely_incident"] == "Structure Fire"


def test_ner_tactical_summary_slices_per_category_and_counts_all_tactical(db):
    day = date(2026, 10, 14)
    ts = datetime(2026, 10, 14, 12, 0)
    # Insert 5 distinct UNIT entities (freq 3 each) and 1 EVT_TYPE entity (freq 2)
    for u_idx in range(5):
        for _ in range(3):
            db.add(
                EntityObservation(
                    span_store_id=1,
                    monitor_id=1,
                    log_entry_id=1,
                    label="UNIT",
                    raw=f"Unit {u_idx}",
                    canonical=f"Unit {u_idx}",
                    ts=ts,
                )
            )
    for _ in range(2):
        db.add(
            EntityObservation(
                span_store_id=1,
                monitor_id=1,
                log_entry_id=1,
                label="EVT_TYPE",
                raw="Brush Fire",
                canonical="Brush Fire",
                ts=ts,
            )
        )
    # Punctuation fragment should be ignored in candidate lists
    db.add(
        EntityObservation(
            span_store_id=1,
            monitor_id=1,
            log_entry_id=1,
            label="EVT_TYPE",
            raw=".",
            canonical=".",
            ts=ts,
        )
    )
    db.commit()

    ner = ie.get_ner_tactical_summary(db, day, day, limit=3)
    assert len(ner["units"]) == 3
    assert len(ner["call_types"]) == 1
    assert ner["call_types"][0]["canonical"] == "Brush Fire"
    assert ner["total_entities_detected"] >= 17


def test_local_date_range_to_utc_helper():
    utc_start, utc_end = ie.local_date_range_to_utc(date(2026, 10, 14), date(2026, 10, 14))
    assert utc_start.tzinfo is not None
    assert utc_end.tzinfo is not None
    assert utc_end > utc_start


def test_parse_date_param_validation():
    d = parse_date_param("date", "2026-10-14")
    assert d == date(2026, 10, 14)
    assert parse_date_param("date", None) is None

    with pytest.raises(HTTPException) as exc_info:
        parse_date_param("date", "not-a-valid-date")
    assert exc_info.value.status_code == 422


def test_talkgroup_tracker_telemetry(db):
    # Yesterday: TG_PATROL active
    yesterday = date(2026, 10, 13)
    _add(db, datetime(2026, 10, 13, 12, 0), talkgroup="TG_PATROL", duration=10.0)

    # Today: TG_PATROL (3 calls), TG_DISPATCH (5 calls, first seen), TG_NEW_FIRE (1 call, first seen)
    today = date(2026, 10, 14)
    for _ in range(5):
        _add(db, datetime(2026, 10, 14, 8, 30), talkgroup="TG_DISPATCH", duration=8.0)
    for _ in range(3):
        _add(db, datetime(2026, 10, 14, 9, 15), talkgroup="TG_PATROL", duration=12.0)
    _add(db, datetime(2026, 10, 14, 11, 0), talkgroup="TG_NEW_FIRE", duration=20.0)
    db.commit()

    tracker = ie.get_talkgroup_tracker_telemetry(db, today, today)
    assert tracker["total_talkgroups"] == 3
    assert tracker["total_calls"] == 9
    assert tracker["busiest_talkgroup"]["talkgroup"] == "TG_DISPATCH"
    assert tracker["busiest_talkgroup"]["count"] == 5

    ranked = tracker["ranked_talkgroups"]
    assert len(ranked) == 3
    assert ranked[0]["talkgroup"] == "TG_DISPATCH"
    assert ranked[1]["talkgroup"] == "TG_PATROL"
    assert ranked[2]["talkgroup"] == "TG_NEW_FIRE"

    # TG_DISPATCH and TG_NEW_FIRE are brand new (first seen on today)
    new_tgs = [t["talkgroup"] for t in tracker["new_talkgroups"]]
    assert "TG_DISPATCH" in new_tgs
    assert "TG_NEW_FIRE" in new_tgs
    assert "TG_PATROL" not in new_tgs

    # TG_PATROL was seen yesterday; TG_DISPATCH and TG_NEW_FIRE are new vs yesterday
    vs_yesterday = [t["talkgroup"] for t in tracker["new_vs_yesterday"]]
    assert "TG_DISPATCH" in vs_yesterday
    assert "TG_NEW_FIRE" in vs_yesterday
    assert "TG_PATROL" not in vs_yesterday
