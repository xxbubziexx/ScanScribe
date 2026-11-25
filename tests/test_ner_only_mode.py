"""Unit and SQLite integration tests for Events Pipeline NER-only mode."""
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all ORM tables on Base.metadata
from app.config import Config, EventsPipelineConfig, OpenRouterConfig
from app.database import Base
from app.models.event import EntityObservation, Event, Monitor, SpanStore
from app.models.log_entry import LogEntry
from app.models.user import User
from app.routes.events.admin_router import events_llm_status
from app.services import ner_service
from app.services.events.pipeline import (
    ensure_ner_model_loaded,
    is_events_pipeline_active,
    process_transcript_for_monitor,
    warn_if_no_monitors_configured,
)
from app.services.queue_processor import _dispatch_events_pipeline, _unmatched_tg_last_logged


@pytest.fixture()
def sqlite_db():
    """Provide an isolated in-memory SQLite DB with PRAGMA foreign_keys=ON."""
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
    Session = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    try:
        yield Session
    finally:
        eng.dispose()


def _seed_monitor_and_log(Session, *, enabled: bool = True, talkgroup: str = "FIRE-DISP"):
    """Insert a Monitor and LogEntry row so FK constraints pass cleanly."""
    db = Session()
    try:
        monitor = Monitor(
            name="Test Dept",
            enabled=enabled,
            talkgroup_ids=f'["{talkgroup}"]',
            keyword_config='["EVT_TYPE"]',
        )
        db.add(monitor)
        log_entry = LogEntry(
            filename="test_clip.wav",
            timestamp=datetime(2026, 11, 24, 12, 0, 0),
            log_date="2026-11-24",
            transcript="Engine 1 responding to 123 Main St for structure fire",
            talkgroup=talkgroup,
        )
        db.add(log_entry)
        db.commit()
        return monitor.id, log_entry.id
    finally:
        db.close()


def test_config_ner_only_defaults_and_active_matrix():
    """Verify ner_only defaults to False and test all 4 (enabled, ner_only) states."""
    cfg_default = EventsPipelineConfig()
    assert cfg_default.enabled is False
    assert cfg_default.ner_only is False

    assert is_events_pipeline_active(None) is False
    assert is_events_pipeline_active(EventsPipelineConfig(enabled=False, ner_only=False)) is False
    assert is_events_pipeline_active(EventsPipelineConfig(enabled=False, ner_only=True)) is True
    assert is_events_pipeline_active(EventsPipelineConfig(enabled=True, ner_only=False)) is True
    assert is_events_pipeline_active(EventsPipelineConfig(enabled=True, ner_only=True)) is True


@pytest.mark.parametrize(
    "enabled,ner_only,expected_load",
    [
        (False, False, False),
        (False, True, True),
        (True, False, True),
        (True, True, True),
    ],
)
@patch("app.services.events.pipeline.get_settings")
@patch("app.services.events.pipeline.load_ner_model")
def test_ensure_ner_model_loaded_matrix(mock_load, mock_get_settings, enabled, ner_only, expected_load):
    """Verify ensure_ner_model_loaded() across all 4 (enabled, ner_only) combinations."""
    mock_load.return_value = True
    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=enabled,
            ner_only=ner_only,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg
    mock_get_settings.return_value = mock_settings

    assert ensure_ner_model_loaded() is expected_load
    assert mock_load.call_count == (1 if expected_load else 0)


def test_process_transcript_ner_only_sqlite_end_to_end(sqlite_db):
    """With enabled=False, ner_only=True, and invalid OpenRouter key: writes spans/observations, 0 events, 0 HTTP calls."""
    monitor_id, log_entry_id = _seed_monitor_and_log(sqlite_db, enabled=True, talkgroup="FIRE-DISP")

    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=False,
            ner_only=True,
            ner_model_path="./models/test",
        ),
        openrouter=OpenRouterConfig(api_key="invalid-key-must-not-be-called"),
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    with (
        patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        patch(
            "app.services.events.pipeline.extract_entities",
            return_value=({"UNIT": ["Engine 1"], "ADDRESS": ["123 Main St"], "EVT_TYPE": ["structure fire"]}, []),
        ) as mock_extract,
        patch("app.services.events.pipeline.EventsRouter") as mock_router,
        patch("app.services.events_router_engine.httpx.Client") as mock_httpx_client,
    ):
        process_transcript_for_monitor(
            monitor_id=monitor_id,
            talkgroup="FIRE-DISP",
            transcript="Engine 1 responding to 123 Main St for structure fire",
            log_entry_id=log_entry_id,
            log_timestamp=datetime(2026, 11, 24, 12, 0, 0),
        )

    assert mock_extract.call_count == 1
    assert mock_router.route_transcript.call_count == 0
    assert mock_httpx_client.call_count == 0

    verify_db = sqlite_db()
    try:
        spans = verify_db.query(SpanStore).all()
        obs = verify_db.query(EntityObservation).all()
        events = verify_db.query(Event).all()
        assert len(spans) == 1
        assert spans[0].monitor_id == monitor_id
        assert spans[0].log_entry_id == log_entry_id
        assert spans[0].units == "Engine 1"
        assert spans[0].addresses == "123 Main St"
        assert spans[0].evt_type == "structure fire"

        assert len(obs) == 3
        assert all(o.span_store_id == spans[0].id for o in obs)
        assert all(o.log_entry_id == log_entry_id for o in obs)
        assert {(o.label, o.canonical) for o in obs} == {
            ("UNIT", "Engine 1"),
            ("ADDRESS", "123 Main St"),
            ("EVT_TYPE", "structure fire"),
        }
        assert len(events) == 0
    finally:
        verify_db.close()


def test_ner_only_takes_precedence_over_enabled_sqlite(sqlite_db):
    """When both enabled=True and ner_only=True, ner_only writes spans/entities and suppresses LLM router."""
    monitor_id, log_entry_id = _seed_monitor_and_log(sqlite_db, enabled=True, talkgroup="EMS-TAC")

    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=True,
            ner_only=True,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    with (
        patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        patch(
            "app.services.events.pipeline.extract_entities",
            return_value=({"UNIT": ["Medic 2"], "EVT_TYPE": ["medical"]}, []),
        ) as mock_extract,
        patch("app.services.events.pipeline.EventsRouter") as mock_router,
    ):
        process_transcript_for_monitor(
            monitor_id=monitor_id,
            talkgroup="EMS-TAC",
            transcript="Medic 2 en route",
            log_entry_id=log_entry_id,
            log_timestamp=datetime(2026, 11, 24, 12, 5, 0),
        )

    assert mock_extract.call_count == 1
    assert mock_router.route_transcript.call_count == 0

    verify_db = sqlite_db()
    try:
        assert verify_db.query(SpanStore).count() == 1
        assert verify_db.query(EntityObservation).count() == 2
        assert verify_db.query(Event).count() == 0
    finally:
        verify_db.close()


def test_full_pipeline_enabled_true_ner_only_false_calls_router(sqlite_db):
    """When enabled=True and ner_only=False, existing router behavior is preserved."""
    monitor_id, log_entry_id = _seed_monitor_and_log(sqlite_db, enabled=True, talkgroup="FIRE-DISP")

    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=True,
            ner_only=False,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    with (
        patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        patch(
            "app.services.events.pipeline.extract_entities",
            return_value=({"EVT_TYPE": ["structure fire"], "UNIT": ["Engine 1"]}, []),
        ),
        patch("app.services.events.pipeline.EventsRouter") as mock_router,
        patch("app.services.events.pipeline.append_pipeline_debug"),
    ):
        mock_router.route_transcript.return_value = {"action": "SKIP", "reason": "test", "duration_ms": 1.0}
        process_transcript_for_monitor(
            monitor_id=monitor_id,
            talkgroup="FIRE-DISP",
            transcript="Engine 1 responding to structure fire",
            log_entry_id=log_entry_id,
            log_timestamp=datetime(2026, 11, 24, 12, 10, 0),
        )

    assert mock_router.route_transcript.call_count == 1
    verify_db = sqlite_db()
    try:
        assert verify_db.query(SpanStore).count() == 1
        assert verify_db.query(EntityObservation).count() == 2
    finally:
        verify_db.close()


def test_both_false_is_complete_noop(sqlite_db):
    """When both enabled=False and ner_only=False, nothing runs and nothing is written."""
    monitor_id, log_entry_id = _seed_monitor_and_log(sqlite_db, enabled=True, talkgroup="FIRE-DISP")

    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=False,
            ner_only=False,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    with (
        patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
        patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        patch("app.services.events.pipeline.extract_entities") as mock_extract,
        patch("app.services.events.pipeline.EventsRouter") as mock_router,
    ):
        process_transcript_for_monitor(
            monitor_id=monitor_id,
            talkgroup="FIRE-DISP",
            transcript="Engine 1 responding",
            log_entry_id=log_entry_id,
            log_timestamp=datetime(2026, 11, 24, 12, 15, 0),
        )

    assert mock_extract.call_count == 0
    assert mock_router.route_transcript.call_count == 0
    verify_db = sqlite_db()
    try:
        assert verify_db.query(SpanStore).count() == 0
        assert verify_db.query(EntityObservation).count() == 0
        assert verify_db.query(Event).count() == 0
    finally:
        verify_db.close()


def test_warn_if_no_monitors_configured_sqlite(sqlite_db, caplog):
    """Startup monitor check warns when 0 monitors or 0 enabled monitors exist, and stays quiet when enabled."""
    caplog.set_level(logging.WARNING)

    # 1. Zero monitors
    caplog.clear()
    warn_if_no_monitors_configured(session_factory=sqlite_db)
    assert any("no monitors are defined" in rec.message for rec in caplog.records)

    # 2. Only disabled monitor
    db = sqlite_db()
    try:
        m_disabled = Monitor(name="Disabled", enabled=False, talkgroup_ids='["TG-1"]')
        db.add(m_disabled)
        db.commit()
    finally:
        db.close()

    caplog.clear()
    warn_if_no_monitors_configured(session_factory=sqlite_db)
    assert any("no monitors are enabled" in rec.message for rec in caplog.records)

    # 3. Enabled monitor exists -> no warning
    db = sqlite_db()
    try:
        m_enabled = Monitor(name="Enabled", enabled=True, talkgroup_ids='["TG-1"]')
        db.add(m_enabled)
        db.commit()
    finally:
        db.close()

    caplog.clear()
    warn_if_no_monitors_configured(session_factory=sqlite_db)
    assert not any("no monitors" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
@patch("app.services.queue_processor.get_matching_monitor_ids")
@patch("app.services.queue_processor.EventsSessionLocal")
@patch("app.services.queue_processor.logger")
async def test_unmatched_talkgroup_rate_limited_logging(mock_logger, mock_session_cls, mock_get_ids):
    """Verify rate-limited INFO logging normalizes whitespace/case for unmatched talkgroups."""
    mock_db = MagicMock()
    mock_session_cls.return_value = mock_db
    mock_get_ids.return_value = []
    _unmatched_tg_last_logged.clear()

    # Call 1: should log
    await _dispatch_events_pipeline(
        talkgroup="POLICE  TAC-99",
        transcript_text="Test transmission",
        log_entry_id=501,
        timestamp=datetime.utcnow(),
    )
    info_calls = [c for c in mock_logger.info.call_args_list if "unmatched talkgroup" in str(c)]
    assert len(info_calls) == 1

    # Call 2 immediately with collapsed whitespace/different case: shares bucket, rate-limited
    await _dispatch_events_pipeline(
        talkgroup="police tac-99",
        transcript_text="Another test transmission",
        log_entry_id=502,
        timestamp=datetime.utcnow(),
    )
    info_calls_2 = [c for c in mock_logger.info.call_args_list if "unmatched talkgroup" in str(c)]
    assert len(info_calls_2) == 1


def test_ner_failure_logs_warning_and_writes_no_span(sqlite_db, caplog):
    """Real extract_entities() raises when unloaded or on inference error -> WARNING logged with log_entry_id, 0 spans."""
    monitor_id, log_entry_id = _seed_monitor_and_log(sqlite_db, enabled=True, talkgroup="FIRE-DISP")

    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=False,
            ner_only=True,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    caplog.set_level(logging.WARNING)
    orig_pipeline = ner_service._pipeline
    try:
        # Case 1: _pipeline is None -> RuntimeError("NER model is not loaded")
        ner_service._pipeline = None
        caplog.clear()
        with (
            patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
            patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
            patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        ):
            process_transcript_for_monitor(
                monitor_id=monitor_id,
                talkgroup="FIRE-DISP",
                transcript="Engine 1 responding",
                log_entry_id=log_entry_id,
            )
        assert any(
            rec.levelno == logging.WARNING and str(log_entry_id) in rec.getMessage() and rec.exc_info is not None
            for rec in caplog.records
        )

        # Case 2: _pipeline raises CUDA error -> propagates out of extract_entities and logs WARNING
        failing_pipe = MagicMock(side_effect=RuntimeError("CUDA boom"))
        ner_service._pipeline = failing_pipe
        caplog.clear()
        with (
            patch("app.services.events.pipeline.EventsSessionLocal", sqlite_db),
            patch("app.services.events.pipeline.LogsSessionLocal", sqlite_db),
            patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        ):
            process_transcript_for_monitor(
                monitor_id=monitor_id,
                talkgroup="FIRE-DISP",
                transcript="Engine 1 responding",
                log_entry_id=log_entry_id,
            )
        assert any(
            rec.levelno == logging.WARNING and str(log_entry_id) in rec.getMessage() and rec.exc_info is not None
            for rec in caplog.records
        )
    finally:
        ner_service._pipeline = orig_pipeline

    verify_db = sqlite_db()
    try:
        assert verify_db.query(SpanStore).count() == 0
        assert verify_db.query(EntityObservation).count() == 0
    finally:
        verify_db.close()


def test_span_commit_failure_logs_warning_and_rolls_back(caplog):
    """When events_db.commit() raises, process_transcript_for_monitor logs WARNING with log_entry_id and rolls back."""
    app_cfg = Config(
        events_pipeline=EventsPipelineConfig(
            enabled=False,
            ner_only=True,
            ner_model_path="./models/test",
        )
    )
    mock_settings = MagicMock()
    mock_settings.config = app_cfg

    mock_db = MagicMock()
    mock_db.commit.side_effect = RuntimeError("SQLite disk I/O error")

    caplog.set_level(logging.WARNING)
    with (
        patch("app.services.events.pipeline.EventsSessionLocal", return_value=mock_db),
        patch("app.services.events.pipeline.LogsSessionLocal", return_value=MagicMock()),
        patch("app.services.events.pipeline.get_settings", return_value=mock_settings),
        patch(
            "app.services.events.pipeline.extract_entities",
            return_value=({"UNIT": ["Engine 1"]}, []),
        ),
    ):
        process_transcript_for_monitor(
            monitor_id=1,
            talkgroup="FIRE-DISP",
            transcript="Engine 1 responding",
            log_entry_id=9876,
        )

    assert mock_db.rollback.call_count == 1
    assert any(
        rec.levelno == logging.WARNING and "9876" in rec.getMessage() and rec.exc_info is not None
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_events_llm_status_ner_only_mode():
    """Verify /api/events/llm-status reports ok/unreachable in ner_only mode and disabled when off."""
    user = User(id=1, username="tester", email="tester@localhost", is_admin=True, is_active=True)

    mock_settings = MagicMock()

    # 1. ner_only=True, enabled=False, loaded=True -> status=ok, ner_only=True
    mock_settings.config = Config(
        events_pipeline=EventsPipelineConfig(enabled=False, ner_only=True, ner_model_path="./models/test")
    )
    with (
        patch("app.routes.events.admin_router.get_settings", return_value=mock_settings),
        patch("app.routes.events.admin_router.is_loaded", return_value=True),
    ):
        res = await events_llm_status(current_user=user)
    assert res["enabled"] is True
    assert res["ner_only"] is True
    assert res["status"] == "ok"

    # 2. ner_only=True, enabled=False, loaded=False -> status=unreachable
    with (
        patch("app.routes.events.admin_router.get_settings", return_value=mock_settings),
        patch("app.routes.events.admin_router.is_loaded", return_value=False),
    ):
        res = await events_llm_status(current_user=user)
    assert res["enabled"] is True
    assert res["ner_only"] is True
    assert res["status"] == "unreachable"

    # 3. ner_only=False, enabled=False -> status=disabled
    mock_settings.config = Config(
        events_pipeline=EventsPipelineConfig(enabled=False, ner_only=False, ner_model_path="./models/test")
    )
    with patch("app.routes.events.admin_router.get_settings", return_value=mock_settings):
        res = await events_llm_status(current_user=user)
    assert res["enabled"] is False
    assert res["ner_only"] is False
    assert res["status"] == "disabled"
