"""Unit tests for Events Pipeline NER-only mode."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from app.config import EventsPipelineConfig, Config
from app.models.event import SpanStore, EntityObservation, Event
from app.services.events.pipeline import (
    ensure_ner_model_loaded,
    process_transcript_for_monitor,
)
from app.services.queue_processor import _dispatch_events_pipeline, _unmatched_tg_last_logged


def test_config_ner_only_field():
    """Verify ner_only defaults to False and can be set to True."""
    cfg_default = EventsPipelineConfig()
    assert cfg_default.ner_only is False

    cfg_custom = EventsPipelineConfig(ner_only=True)
    assert cfg_custom.ner_only is True


@patch("app.services.events.pipeline.get_settings")
@patch("app.services.events.pipeline.load_ner_model")
def test_ensure_ner_model_loaded_ner_only(mock_load, mock_get_settings):
    """Verify ensure_ner_model_loaded() loads model when ner_only=True even if enabled=False."""
    # Case 1: both False -> False
    app_cfg = Config(events_pipeline=EventsPipelineConfig(enabled=False, ner_only=False, ner_model_path="./models/test"))
    mock_settings = MagicMock()
    mock_settings.config = app_cfg
    mock_get_settings.return_value = mock_settings
    assert ensure_ner_model_loaded() is False
    assert mock_load.call_count == 0

    # Case 2: ner_only=True, enabled=False -> True
    mock_load.return_value = True
    app_cfg = Config(events_pipeline=EventsPipelineConfig(enabled=False, ner_only=True, ner_model_path="./models/test"))
    mock_settings.config = app_cfg
    assert ensure_ner_model_loaded() is True
    assert mock_load.call_count == 1


@patch("app.services.events.pipeline.EventsSessionLocal")
@patch("app.services.events.pipeline.extract_entities")
@patch("app.services.events.pipeline.EventsRouter")
@patch("app.services.events.pipeline.get_settings")
def test_process_transcript_ner_only_creates_spans_and_bypasses_router(
    mock_get_settings, mock_router, mock_extract, mock_session_cls
):
    """Verify ner_only writes SpanStore/EntityObservation and never touches EventsRouter or Event rows."""
    cfg = EventsPipelineConfig(enabled=False, ner_only=True, ner_model_path="./models/test")
    mock_settings = MagicMock()
    mock_settings.config = Config(events_pipeline=cfg)
    mock_get_settings.return_value = mock_settings

    mock_db = MagicMock()
    mock_session_cls.return_value = mock_db

    mock_extract.return_value = (
        {"UNIT": ["Engine 1"], "LOC": ["Main St"]},
        [],
    )

    process_transcript_for_monitor(
        monitor_id=1,
        talkgroup="FIRE-DISP",
        transcript="Engine 1 responding to Main St",
        log_entry_id=101,
        log_timestamp=datetime(2026, 11, 24, 12, 0, 0),
    )

    # extract_entities should be called
    assert mock_extract.call_count == 1
    # DB operations: span added, entity observations added, committed
    assert mock_db.add.call_count >= 1
    assert mock_db.commit.call_count == 1

    # Crucial: EventsRouter.route_transcript must NEVER be called
    assert mock_router.route_transcript.call_count == 0
    # Crucial: Event table must NOT be queried for open events
    for call in mock_db.query.call_args_list:
        model_queried = call[0][0]
        assert model_queried is not Event


@patch("app.services.events.pipeline.EventsSessionLocal")
@patch("app.services.events.pipeline.extract_entities")
@patch("app.services.events.pipeline.EventsRouter")
@patch("app.services.events.pipeline.get_settings")
def test_ner_only_takes_precedence_over_enabled(
    mock_get_settings, mock_router, mock_extract, mock_session_cls
):
    """When both enabled=True and ner_only=True, ner_only suppresses the LLM router."""
    cfg = EventsPipelineConfig(enabled=True, ner_only=True, ner_model_path="./models/test")
    mock_settings = MagicMock()
    mock_settings.config = Config(events_pipeline=cfg)
    mock_get_settings.return_value = mock_settings

    mock_db = MagicMock()
    mock_session_cls.return_value = mock_db
    mock_extract.return_value = ({"UNIT": ["Medic 2"]}, [])

    process_transcript_for_monitor(
        monitor_id=2,
        talkgroup="EMS-TAC",
        transcript="Medic 2 en route",
        log_entry_id=102,
        log_timestamp=datetime(2026, 11, 24, 12, 5, 0),
    )

    assert mock_extract.call_count == 1
    assert mock_db.commit.call_count == 1
    assert mock_router.route_transcript.call_count == 0


@pytest.mark.asyncio
@patch("app.services.queue_processor.get_matching_monitor_ids")
@patch("app.services.queue_processor.EventsSessionLocal")
@patch("app.services.queue_processor.logger")
async def test_unmatched_talkgroup_rate_limited_logging(mock_logger, mock_session_cls, mock_get_ids):
    """Verify rate-limited INFO logging when talkgroup matches no monitors."""
    mock_db = MagicMock()
    mock_session_cls.return_value = mock_db
    mock_get_ids.return_value = []
    _unmatched_tg_last_logged.clear()

    # Call 1: should log
    await _dispatch_events_pipeline(
        talkgroup="POLICE-TAC-99",
        transcript_text="Test transmission",
        log_entry_id=501,
        timestamp=datetime.utcnow(),
    )
    info_calls = [c for c in mock_logger.info.call_args_list if "unmatched talkgroup" in str(c)]
    assert len(info_calls) == 1

    # Call 2 immediately: should be rate-limited (not logged again)
    await _dispatch_events_pipeline(
        talkgroup="POLICE-TAC-99",
        transcript_text="Another test transmission",
        log_entry_id=502,
        timestamp=datetime.utcnow(),
    )
    info_calls_2 = [c for c in mock_logger.info.call_args_list if "unmatched talkgroup" in str(c)]
    assert len(info_calls_2) == 1
