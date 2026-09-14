"""Unit tests for Event Header Summary Generation based on attachments."""
import pytest
from unittest.mock import MagicMock, patch
import httpx

from app.services.events_router_engine import (
    build_summary_user_prompt,
    SUMMARY_SYSTEM_PROMPT,
    EventsRouter,
)


def test_summary_system_prompt():
    """Verify system prompt instructs model to be factual and concise."""
    assert "911 / Public Safety Incident Communications Officer" in SUMMARY_SYSTEM_PROMPT
    assert "1 to 3 sentence operational summary" in SUMMARY_SYSTEM_PROMPT
    assert "chronological sequence of radio transmissions" in SUMMARY_SYSTEM_PROMPT


def test_build_summary_user_prompt_single_attachment():
    """Verify prompt formatting for an initial single-attachment event."""
    attachments = [
        {
            "time": "14:20:01",
            "talkgroup": "FIRE-DISP",
            "transcript": "Engine 4 respond to 12834 Springtown Road for smoke report",
        }
    ]

    prompt = build_summary_user_prompt(
        event_type="Structure Fire",
        location="12834 Springtown Road",
        units="Engine 4",
        status_detail="Dispatched",
        status="open",
        attachments=attachments,
    )

    assert "Incident Type: Structure Fire" in prompt
    assert "Location: 12834 Springtown Road" in prompt
    assert "Assigned Units: Engine 4" in prompt
    assert "Operational Status: Dispatched (open)" in prompt
    assert '[1] (14:20:01) [FIRE-DISP] "Engine 4 respond to 12834 Springtown Road for smoke report"' in prompt


def test_build_summary_user_prompt_multiple_attachments():
    """Verify chronological numbering and formatting of multiple attachments."""
    attachments = [
        {
            "time": "14:20:01",
            "talkgroup": "FIRE-DISP",
            "transcript": "Engine 4 respond to 12834 Springtown Road for smoke report",
        },
        {
            "time": "14:20:25",
            "talkgroup": "FIRE-DISP",
            "transcript": "Engine 4 copying, en route",
        },
        {
            "time": "14:22:15",
            "talkgroup": "FIRE-TAC",
            "transcript": "Engine 4 on scene, nothing showing, investigating",
        },
        {
            "time": "14:35:00",
            "talkgroup": "FIRE-TAC",
            "transcript": "Engine 4 false alarm burnt food, in service",
        },
    ]

    prompt = build_summary_user_prompt(
        event_type="Structure Fire",
        location="12834 Springtown Road",
        units="Engine 4",
        status_detail="Cleared",
        status="closed",
        attachments=attachments,
    )

    assert "Operational Status: Cleared (closed)" in prompt
    assert '[1] (14:20:01) [FIRE-DISP] "Engine 4 respond to 12834 Springtown Road for smoke report"' in prompt
    assert '[2] (14:20:25) [FIRE-DISP] "Engine 4 copying, en route"' in prompt
    assert '[3] (14:22:15) [FIRE-TAC] "Engine 4 on scene, nothing showing, investigating"' in prompt
    assert '[4] (14:35:00) [FIRE-TAC] "Engine 4 false alarm burnt food, in service"' in prompt


def test_generate_event_summary_empty_attachments():
    """Verify empty attachments returns existing summary without calling API."""
    res = EventsRouter.generate_event_summary(
        event_type="Medical",
        location="Main St",
        units="Medic 1",
        status_detail="Active",
        attachments=[],
        current_summary="Existing summary",
    )
    assert res == "Existing summary"


@patch("app.services.events_router_engine.openrouter_api_key", return_value="sk-or-test-key")
@patch("httpx.Client")
def test_generate_event_summary_success(mock_client_cls, mock_api_key):
    """Verify successful OpenRouter call cleans preambles/quotes and returns summary."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": 'Summary: "Engine 4 responded to 12834 Springtown Road for a smoke report, found burnt food, and cleared the scene."'
                }
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    attachments = [
        {"time": "14:20:00", "talkgroup": "DISP", "transcript": "Call dispatched"},
        {"time": "14:30:00", "talkgroup": "DISP", "transcript": "All units clear"},
    ]

    summary = EventsRouter.generate_event_summary(
        event_type="Structure Fire",
        location="12834 Springtown Road",
        units="Engine 4",
        status_detail="Cleared",
        status="closed",
        attachments=attachments,
    )

    assert summary == "Engine 4 responded to 12834 Springtown Road for a smoke report, found burnt food, and cleared the scene."


@patch("app.services.events_router_engine.openrouter_api_key", return_value="sk-or-test-key")
@patch("httpx.Client")
def test_generate_event_summary_rate_limit_fallback(mock_client_cls, mock_api_key):
    """Verify 429 rate limit or HTTP error falls back to current summary without breaking."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = '{"error": "Too Many Requests"}'
    
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Client error '429 Too Many Requests'",
        request=MagicMock(),
        response=mock_response,
    )
    mock_client_cls.return_value = mock_client

    summary = EventsRouter.generate_event_summary(
        event_type="Medical",
        location="100 Main St",
        units="Medic 2",
        status_detail="Dispatched",
        attachments=[{"time": "12:00:00", "talkgroup": "MED", "transcript": "Medic 2 dispatched"}],
        current_summary="Initial summary before rate limit",
    )

    assert summary == "Initial summary before rate limit"


def test_summarize_event_attachments_integration():
    """Verify summarize_event_attachments extracts transcripts and saves event.summary."""
    from app.services.events_worker import summarize_event_attachments
    from app.database import EventsSessionLocal, LogsSessionLocal, init_db
    from app.models.event import Event, EventTranscriptLink, Monitor
    from app.models.log_entry import LogEntry
    from datetime import datetime, timezone

    init_db()
    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
    try:
        mon = Monitor(name="Test Summary Monitor", talkgroup_ids='["DISP"]')
        events_db.add(mon)
        events_db.commit()

        ev = Event(
            event_id="test_sum_evt_1",
            monitor_id=mon.id,
            status="open",
            event_type="Commercial Fire",
            location="500 Market St",
            units="Engine 1, Ladder 1",
            status_detail="Working fire",
        )
        events_db.add(ev)
        events_db.commit()

        # Add 2 log entries
        le1 = LogEntry(filename="test_sum_1.wav", talkgroup="DISP", transcript="Engine 1 dispatched to 500 Market St for commercial fire", timestamp=datetime.now(timezone.utc))
        le2 = LogEntry(filename="test_sum_2.wav", talkgroup="DISP", transcript="Ladder 1 on scene, heavy smoke from roof", timestamp=datetime.now(timezone.utc))
        logs_db.add_all([le1, le2])
        logs_db.commit()

        # Link them
        link1 = EventTranscriptLink(event_id=ev.id, log_entry_id=le1.id)
        link2 = EventTranscriptLink(event_id=ev.id, log_entry_id=le2.id)
        events_db.add_all([link1, link2])
        events_db.commit()

        with patch.object(
            EventsRouter,
            "generate_event_summary",
            return_value="Engine 1 and Ladder 1 responded to 500 Market St for a commercial fire; Ladder 1 reported heavy smoke from the roof."
        ) as mock_gen:
            res = summarize_event_attachments(ev, events_db, logs_db)
            assert res == "Engine 1 and Ladder 1 responded to 500 Market St for a commercial fire; Ladder 1 reported heavy smoke from the roof."
            assert ev.summary == res
            assert mock_gen.called

            # Check arguments passed to mock_gen
            kwargs = mock_gen.call_args[1]
            assert kwargs["event_type"] == "Commercial Fire"
            assert kwargs["location"] == "500 Market St"
            assert len(kwargs["attachments"]) == 2
            assert kwargs["attachments"][0]["transcript"] == "Engine 1 dispatched to 500 Market St for commercial fire"
            assert kwargs["attachments"][1]["transcript"] == "Ladder 1 on scene, heavy smoke from roof"
    finally:
        events_db.close()
        logs_db.close()


def test_summarize_event_endpoint():
    """Verify POST /api/events/{event_id}/summarize endpoint executes successfully without import errors."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import EventsSessionLocal, LogsSessionLocal, init_db
    from app.models.event import Event, EventTranscriptLink, Monitor
    from app.models.log_entry import LogEntry
    from app.models.user import User
    from app.routes.auth import get_current_active_user
    from datetime import datetime, timezone

    init_db()
    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
    try:
        mon = Monitor(name="API Summary Monitor", talkgroup_ids='["DISP"]')
        events_db.add(mon)
        events_db.commit()

        ev = Event(
            event_id="test_api_sum_1",
            monitor_id=mon.id,
            status="open",
            event_type="Vehicle Accident",
            location="Highway 67",
            units="Unit 42",
        )
        events_db.add(ev)
        events_db.commit()

        le = LogEntry(filename="test_api_1.wav", talkgroup="DISP", transcript="Unit 42 en route to Highway 67", timestamp=datetime.now(timezone.utc))
        logs_db.add(le)
        logs_db.commit()

        link = EventTranscriptLink(event_id=ev.id, log_entry_id=le.id)
        events_db.add(link)
        events_db.commit()

        mock_user = User(id=1, username="testadmin", is_active=True, is_admin=True)
        app.dependency_overrides[get_current_active_user] = lambda: mock_user

        with patch.object(
            EventsRouter,
            "generate_event_summary",
            return_value="Unit 42 responded to a vehicle accident on Highway 67."
        ):
            client = TestClient(app)
            response = client.post(f"/api/events/{ev.event_id}/summarize")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["ok"] is True
            assert data["summary"] == "Unit 42 responded to a vehicle accident on Highway 67."
    finally:
        app.dependency_overrides.clear()
        events_db.close()
        logs_db.close()


