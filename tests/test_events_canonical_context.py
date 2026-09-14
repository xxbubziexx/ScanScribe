"""Unit tests for Events Canonical Channel Context in EventsRouter."""
import pytest
from app.config import EventsPipelineConfig
from app.services.events_router_engine import (
    build_user_prompt,
    build_system_prompt,
    EventsRouter,
)


def test_config_recent_spans_limit():
    """Verify recent_spans_limit defaults to 6 in EventsPipelineConfig."""
    cfg = EventsPipelineConfig()
    assert cfg.recent_spans_limit == 6


def test_system_prompt_dialogue_continuity():
    """Verify system prompt includes guidance on channel context and dialogue continuity."""
    prompt = build_system_prompt()
    assert "CHANNEL CONTEXT & DIALOGUE CONTINUITY" in prompt
    assert "Recent Channel Transmissions" in prompt

    prompt_with_units = build_system_prompt(known_units="Engine 4, Medic 2")
    assert "CHANNEL CONTEXT & DIALOGUE CONTINUITY" in prompt_with_units
    assert "Engine 4, Medic 2" in prompt_with_units


def test_build_user_prompt_with_dict_spans():
    """Verify prompt formatting when recent_spans contains structured transmission dicts."""
    recent_spans = [
        {
            "transcript": "Engine 4 respond to 12834 Springtown Road for smoke report",
            "talkgroup": "FIRE-DISP",
            "units": "Engine 4",
            "location": "12834 Springtown Road",
            "time": "14:20:01",
        },
        {
            "transcript": "Engine 4 copying, en route",
            "talkgroup": "FIRE-DISP",
            "units": "Engine 4",
            "location": "",
            "time": "14:20:25",
        },
        {
            "transcript": "Medic 2 en route as well",
            "talkgroup": "FIRE-TAC",
            "units": "Medic 2",
            "location": "",
            "time": "14:20:50",
        },
    ]

    current_transcript = "Engine 4 on scene at Springtown Road, two-story wood frame, nothing showing"
    entities = {
        "UNIT": ["Engine 4"],
        "STATUS": ["on scene"],
        "LOC": ["Springtown Road"],
    }
    open_incidents = [
        {
            "event_id": "evt_abc123",
            "event_type": "Structure Fire",
            "location": "12834 Springtown Road",
            "units": "Engine 4, Medic 2",
            "status_detail": "Dispatched",
            "recent_transcripts": ["Engine 4 respond to 12834 Springtown Road"],
        }
    ]

    prompt = build_user_prompt(
        monitor_name="County Fire",
        talkgroup="FIRE-TAC",
        transcript=current_transcript,
        entities=entities,
        open_incidents=open_incidents,
        recent_spans=recent_spans,
    )

    # Verify Department and Talkgroup
    assert "Department/Monitor: County Fire" in prompt
    assert "Current Talkgroup: FIRE-TAC" in prompt

    # Verify Open Incidents section
    assert "Currently Open Incidents on this Monitor:" in prompt
    assert "evt_abc123" in prompt

    # Verify Chronological Sequential History
    assert "Recent Channel Transmissions (Sequential Context on this Monitor - Oldest to Most Recent):" in prompt
    assert '[T-3] (14:20:01) [FIRE-DISP] "Engine 4 respond to 12834 Springtown Road for smoke report" | Units: Engine 4, Loc: 12834 Springtown Road' in prompt
    assert '[T-2] (14:20:25) [FIRE-DISP] "Engine 4 copying, en route" | Units: Engine 4' in prompt
    assert '[T-1] (14:20:50) [FIRE-TAC] "Medic 2 en route as well" | Units: Medic 2' in prompt

    # Verify Current Transmission demarcation
    assert ">>> CURRENT TRANSMISSION TO EVALUATE <<<" in prompt
    assert f'Transcript: "{current_transcript}"' in prompt

    # Verify Extracted NER entities
    assert "Extracted Named Entities for Current Transmission (NER):" in prompt
    assert "UNIT: Engine 4" in prompt
    assert "STATUS: on scene" in prompt


def test_build_user_prompt_with_str_spans():
    """Verify backwards-compatibility with raw string recent_spans."""
    recent_spans = [
        "First transmission on channel",
        "Second transmission on channel",
    ]

    prompt = build_user_prompt(
        monitor_name="Police Main",
        talkgroup="PD-DISP",
        transcript="Third transmission",
        recent_spans=recent_spans,
    )

    assert '[T-2] "First transmission on channel"' in prompt
    assert '[T-1] "Second transmission on channel"' in prompt
    assert '>>> CURRENT TRANSMISSION TO EVALUATE <<<' in prompt
    assert 'Transcript: "Third transmission"' in prompt


def test_build_user_prompt_empty_spans():
    """Verify graceful handling when channel is quiet (no recent spans)."""
    prompt = build_user_prompt(
        monitor_name="EMS",
        talkgroup="MED-1",
        transcript="Medic 1 en route",
        recent_spans=[],
    )

    assert "Recent Channel Transmissions: None (Channel was quiet)" in prompt
    assert "Currently Open Incidents on this Monitor: None (Idle)" in prompt
    assert '>>> CURRENT TRANSMISSION TO EVALUATE <<<' in prompt


def test_build_user_prompt_span_capping():
    """Verify recent_spans is capped at 8 items to protect prompt token size."""
    many_spans = [f"Transmission #{i}" for i in range(1, 15)]

    prompt = build_user_prompt(
        monitor_name="Fire",
        talkgroup="FIRE-DISP",
        transcript="Final transmission",
        recent_spans=many_spans,
    )

    # Should only contain 8 items (T-8 down to T-1)
    assert '[T-8] "Transmission #7"' in prompt
    assert '[T-1] "Transmission #14"' in prompt
    assert '"Transmission #1"' not in prompt
    assert '"Transmission #6"' not in prompt


def test_build_user_prompt_with_open_incident_summary():
    """Verify open incidents include the running summary in the user prompt."""
    open_incidents = [
        {
            "event_id": "evt_sum999",
            "event_type": "Commercial Fire",
            "location": "500 Market St",
            "units": "Engine 1, Ladder 1",
            "status_detail": "Working Fire",
            "summary": "Engine 1 and Ladder 1 on scene with heavy smoke showing from 2nd floor roof.",
            "recent_transcripts": ["Ladder 1 on scene, heavy smoke from roof"],
        }
    ]

    prompt = build_user_prompt(
        monitor_name="Fire",
        talkgroup="FIRE-DISP",
        transcript="Ventilation complete on roof",
        open_incidents=open_incidents,
    )

    assert "Currently Open Incidents on this Monitor:" in prompt
    assert "evt_sum999" in prompt
    assert 'Summary: "Engine 1 and Ladder 1 on scene with heavy smoke showing from 2nd floor roof."' in prompt
    assert "Ladder 1 on scene, heavy smoke from roof" in prompt


def test_build_user_prompt_with_canonical_location():
    """Verify open incidents format location with canonical resolved_address and spoken address."""
    # Case 1: Spoken and Resolved differ
    open_incidents_diff = [
        {
            "event_id": "evt_loc_diff",
            "event_type": "Medical",
            "location": "1646 Rue De LaPay",
            "resolved_address": "1646 Rue De La Paix, MO 63000",
            "units": "Medic 1",
            "status_detail": "En Route",
        }
    ]
    prompt = build_user_prompt(
        monitor_name="EMS",
        talkgroup="MED-1",
        transcript="Medic 1 approaching scene",
        open_incidents=open_incidents_diff,
    )
    assert "Location: 1646 Rue De La Paix, MO 63000 (Spoken: 1646 Rue De LaPay)" in prompt

    # Case 2: Resolved matches Spoken
    open_incidents_same = [
        {
            "event_id": "evt_loc_same",
            "event_type": "Medical",
            "location": "12834 Springtown Road",
            "resolved_address": "12834 Springtown Road",
            "units": "Medic 1",
            "status_detail": "En Route",
        }
    ]
    prompt_same = build_user_prompt(
        monitor_name="EMS",
        talkgroup="MED-1",
        transcript="Medic 1 on scene",
        open_incidents=open_incidents_same,
    )
    assert "Location: 12834 Springtown Road |" in prompt_same
    assert "(Spoken:" not in prompt_same

    # Case 3: Only resolved_address set
    open_incidents_only_resolved = [
        {
            "event_id": "evt_loc_only_res",
            "event_type": "Medical",
            "location": "",
            "resolved_address": "9007 Crossman Road",
            "units": "Medic 1",
            "status_detail": "En Route",
        }
    ]
    prompt_only_res = build_user_prompt(
        monitor_name="EMS",
        talkgroup="MED-1",
        transcript="Medic 1 on scene",
        open_incidents=open_incidents_only_resolved,
    )
    assert "Location: 9007 Crossman Road |" in prompt_only_res
    assert "(Spoken:" not in prompt_only_res


def test_system_prompt_operational_vs_chatter_guidelines():
    """Verify system prompt explicitly defines operational updates vs routine chatter."""
    prompt = build_system_prompt()
    
    # Operational updates section
    assert "OPERATIONAL UPDATES (MANDATORY ATTACHES)" in prompt
    assert "Unit Status Reports" in prompt
    assert "Incident Logistics & Command Directives" in prompt
    assert "Patient & Hazard Updates" in prompt
    
    # Specific mandatory attach keywords and examples
    assert "arriving" in prompt
    assert "on scene" in prompt
    assert "en route" in prompt
    assert "position on Lambeth" in prompt
    assert "second page" in prompt
    assert "EMS downgrade" in prompt
    assert "aeromedical / helicopter standby" in prompt
    assert "weather flight aborts" in prompt
    assert "entrapment" in prompt
    assert "overturned" in prompt
    
    # Routine chatter section
    assert "ROUTINE CHATTER (SKIP)" in prompt
    assert "Reserve \"SKIP\" strictly for non-operational traffic" in prompt
    assert "10-4" in prompt
    assert "Copy" in prompt
    assert "That's clear" in prompt
    assert "Central 42" in prompt


def test_is_pure_chatter_standalone_acknowledgments():
    """Verify standalone acknowledgments and pleasantries are detected as pure chatter."""
    from app.services.events_worker import _is_pure_chatter

    chatter_samples = [
        "10-4",
        "10-4 copy",
        "10 4",
        "copy",
        "Copy that",
        "copied",
        "That's clear",
        "thats clear",
        "Have a good night",
        "have a good day",
        "Central 42",
        "dispatch 12",
        "roger",
        "roger that",
        "thanks",
        "thank you",
        "93, 2140",
        "Central 42, 10-4",
        "Copy that, thank you",
        "ok",
        "okay",
        "affirmative",
        "negative",
        "check mdt",
    ]
    for text in chatter_samples:
        assert _is_pure_chatter(text), f"Expected '{text}' to be recognized as pure chatter"


def test_is_pure_chatter_short_text_no_entities():
    """Verify short text (< 5 words) with no entities and no emergency keywords is chatter."""
    from app.services.events_worker import _is_pure_chatter

    assert _is_pure_chatter("")
    assert _is_pure_chatter("   ")
    assert _is_pure_chatter("Yeah okay")
    assert _is_pure_chatter("Testing 1 2 3")
    assert _is_pure_chatter("Stand by")


def test_is_pure_chatter_preserves_operational_and_emergency_transmissions():
    """Verify operational traffic with emergency keywords or directives is NOT filtered as chatter."""
    from app.services.events_worker import _is_pure_chatter

    operational_samples = [
        "341 arriving",
        "Engine 4 en route",
        "Engine 4 on scene",
        "Helicopter standby on weather",
        "Air Evac weather abort",
        "Air Evac 15 minute ETA",
        "Position on Lambeth",
        "Two vehicles overturned with entrapment",
        "Medic 2 transporting to Mercy",
        "Request second page for ladder",
        "Downgrade EMS response",
        "Brush fire approaching structure",
        "Subject in custody",
        "Traffic stop on Main",
        "Heavy smoke showing",
    ]
    for text in operational_samples:
        assert not _is_pure_chatter(text), f"Expected operational transmission '{text}' NOT to be filtered as chatter"


def test_is_pure_chatter_preserves_extracted_entities():
    """Verify short transmissions with extracted entities are NOT filtered as chatter."""
    from app.services.events_worker import _is_pure_chatter

    # Location entity
    assert not _is_pure_chatter("12834 Springtown", entities={"LOC": ["12834 Springtown"]})
    # Unit entity
    assert not _is_pure_chatter("Medic 1", entities={"UNIT": ["Medic 1"]})
    # Event type entity
    assert not _is_pure_chatter("Working fire", entities={"EVT_TYPE": ["Structure Fire"]})
    # Status entity
    assert not _is_pure_chatter("In service", entities={"STATUS": ["in service"]})


def test_route_transcript_reasoning_fallback(monkeypatch):
    """Verify route_transcript extracts JSON from choices[0].message.reasoning when content is empty."""
    from unittest.mock import MagicMock

    monkeypatch.setattr("app.services.events_router_engine.openrouter_api_key", lambda cfg: "test_key")
    monkeypatch.setattr("app.services.events_router_engine.openrouter_base_url", lambda cfg: "https://openrouter.ai/api/v1")
    monkeypatch.setattr("app.services.events_router_engine.openrouter_model", lambda cfg: "meta-llama/llama-3.3-70b-instruct")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.text = ""
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning": (
                        "The unit 341 is arriving at the open accident incident evt_col123.\n"
                        "```json\n"
                        "{\n"
                        '  "action": "ATTACH",\n'
                        '  "event_id": "evt_col123",\n'
                        '  "reason": "Unit 341 arriving on scene",\n'
                        '  "event_type": "Traffic Collision",\n'
                        '  "units": ["341"],\n'
                        '  "status_detail": "On scene"\n'
                        "}\n"
                        "```"
                    ),
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    monkeypatch.setattr("httpx.Client", lambda **kwargs: mock_client)

    result = EventsRouter.route_transcript(
        monitor_name="Sheriff Dispatch",
        talkgroup="COUNTY-LAW",
        transcript="341 arriving",
        open_incidents=[{"event_id": "evt_col123", "event_type": "Traffic Collision"}],
    )

    assert result["action"] == "ATTACH"
    assert result["event_id"] == "evt_col123"
    assert result["units"] == ["341"]
    assert result["status_detail"] == "On scene"
    assert result["error"] is None


def test_route_transcript_empty_response_retry_fallback(monkeypatch):
    """Verify route_transcript retries without reasoning/response_format if 200 OK returns empty content."""
    from unittest.mock import MagicMock

    monkeypatch.setattr("app.services.events_router_engine.openrouter_api_key", lambda cfg: "test_key")
    monkeypatch.setattr("app.services.events_router_engine.openrouter_base_url", lambda cfg: "https://openrouter.ai/api/v1")
    monkeypatch.setattr("app.services.events_router_engine.openrouter_model", lambda cfg: "meta-llama/llama-3.3-70b-instruct")

    first_response = MagicMock()
    first_response.status_code = 200
    first_response.is_success = True
    first_response.text = '{"choices": [{"message": {"content": ""}}]}'
    first_response.raise_for_status = MagicMock()
    first_response.json.return_value = {
        "choices": [{"message": {"content": "", "reasoning": ""}}]
    }

    retry_response = MagicMock()
    retry_response.status_code = 200
    retry_response.is_success = True
    retry_response.text = ""
    retry_response.raise_for_status = MagicMock()
    retry_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        "{\n"
                        '  "action": "ATTACH",\n'
                        '  "event_id": "evt_col123",\n'
                        '  "reason": "Air Evac weather abort coordinates with command",\n'
                        '  "event_type": "Traffic Collision",\n'
                        '  "units": ["Air Evac"],\n'
                        '  "status_detail": "Weather Abort"\n'
                        "}"
                    )
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = [first_response, retry_response]

    monkeypatch.setattr("httpx.Client", lambda **kwargs: mock_client)

    result = EventsRouter.route_transcript(
        monitor_name="Sheriff Dispatch",
        talkgroup="COUNTY-LAW",
        transcript="Air Evac weather abort",
        open_incidents=[{"event_id": "evt_col123", "event_type": "Traffic Collision"}],
    )

    assert mock_client.post.call_count == 2
    assert result["action"] == "ATTACH"
    assert result["event_id"] == "evt_col123"
    assert result["units"] == ["Air Evac"]
    assert result["error"] is None


def test_create_event_deduplication_safeguard(monkeypatch):
    """Verify _create_event_full merges into recent open event of same type instead of duplicating."""
    from app.services.events_worker import _create_event_full
    from app.models.event import Event, EventTranscriptLink
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.event import EventsBase

    # Create in-memory SQLite for testing
    test_engine = create_engine("sqlite:///:memory:")
    EventsBase.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    from unittest.mock import MagicMock
    monkeypatch.setattr("app.services.events_worker.LogsSessionLocal", lambda: MagicMock())
    monkeypatch.setattr("app.services.events_worker.append_pipeline_debug", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.events_worker.summarize_event_attachments", lambda *args, **kwargs: "Mock Summary")
    monkeypatch.setattr("app.services.events_worker._dispatch_geocoding_for_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.events_worker.websocket_manager.broadcast_sync", lambda *args, **kwargs: None)

    # First event creation: Units 208, 213 dispatched to Psychiatric Call
    eid1 = _create_event_full(
        events_db=db,
        monitor_id=1,
        talkgroup="LAW-DISP",
        transcript="Central 208, 213 psychiatric.",
        entities={"UNIT": ["208", "213"], "EVT_TYPE": ["psychiatric"]},
        log_entry_id=101,
        log_timestamp=None,
        duration_ms=50.0,
        raw_output=[],
        event_type="Psychiatric Call",
        units=["208", "213"],
        status_detail="Dispatched",
    )

    ev1 = db.query(Event).filter(Event.event_id == eid1).first()
    assert ev1 is not None
    assert ev1.units == "208, 213"
    assert ev1.location is None

    # Second event creation 5 seconds later: Psychiatric emergency at Nelson Auto Sales
    eid2 = _create_event_full(
        events_db=db,
        monitor_id=1,
        talkgroup="LAW-DISP",
        transcript="Psychiatric the area of Nelson auto sales 120.",
        entities={"LOC": ["Nelson auto sales"], "EVT_TYPE": ["psychiatric"]},
        log_entry_id=102,
        log_timestamp=None,
        duration_ms=50.0,
        raw_output=[],
        event_type="Psychiatric Emergency",
        location="Nelson Auto Sales",
        status_detail="Active",
    )

    # Should deduplicate and return the SAME event_id
    assert eid2 == eid1
    # Total open events should remain 1
    open_count = db.query(Event).filter(Event.status == "open").count()
    assert open_count == 1

    # Updated event should now contain merged location AND units
    db.refresh(ev1)
    assert ev1.location == "Nelson Auto Sales"
    assert "208" in ev1.units and "213" in ev1.units
    # Should have 2 linked transcripts
    links = db.query(EventTranscriptLink).filter(EventTranscriptLink.event_id == ev1.id).all()
    assert len(links) == 2


def test_openrouter_rate_limit_manager_record_429_retry_after():
    """Verify OpenRouterRateLimitManager parses Retry-After header."""
    from app.services.events_router_engine import OpenRouterRateLimitManager
    OpenRouterRateLimitManager.reset()

    wait = OpenRouterRateLimitManager.record_429(
        status_code=429,
        headers={"retry-after": "45"},
        body_text="Rate limit exceeded",
    )
    assert wait == 45.0
    is_limited, rem, reason = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is True
    assert 40 <= rem <= 45
    assert "Retry-After 45s" in reason

    OpenRouterRateLimitManager.reset()
    is_limited, _, _ = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is False


def test_openrouter_rate_limit_manager_record_429_daily_reset_ms():
    """Verify OpenRouterRateLimitManager parses OpenRouter daily limit reset in milliseconds."""
    import time
    import json
    from app.services.events_router_engine import OpenRouterRateLimitManager
    OpenRouterRateLimitManager.reset()

    # Simulate reset 300 seconds from now in epoch ms
    future_ms = int((time.time() + 300) * 1000)
    body = json.dumps({
        "error": {
            "message": "Rate limit exceeded: free-models-per-day-high-balance. ",
            "code": 429,
            "metadata": {
                "headers": {
                    "X-RateLimit-Limit": "1000",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(future_ms),
                },
                "limit_source": "openrouter_free_tier_daily",
            },
        }
    })
    wait = OpenRouterRateLimitManager.record_429(
        status_code=429,
        headers={},
        body_text=body,
    )
    assert 290 <= wait <= 301
    is_limited, rem, reason = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is True
    assert 290 <= rem <= 301
    assert "free-models-per-day" in reason or "resets at" in reason

    OpenRouterRateLimitManager.reset()


def test_events_router_short_circuits_during_rate_limit():
    """Verify route_transcript skips without making an HTTP request when rate limited."""
    import time
    from app.services.events_router_engine import EventsRouter, OpenRouterRateLimitManager

    OpenRouterRateLimitManager._cooldown_until = time.time() + 120.0
    OpenRouterRateLimitManager._cooldown_reason = "Mock cooldown"

    res = EventsRouter.route_transcript(
        monitor_name="Test Monitor",
        talkgroup="FIRE-DISP",
        transcript="Structure fire at 123 Main St",
        entities={"EVT_TYPE": ["fire"]},
        open_incidents=[],
    )
    assert res["action"] == "SKIP"
    assert res["error"] == "rate_limit_cooldown"
    assert "Rate-limit cooldown active" in res["reason"]

    OpenRouterRateLimitManager.reset()


def test_generate_event_summary_short_circuits_during_rate_limit():
    """Verify generate_event_summary returns current summary when rate limited."""
    import time
    from app.services.events_router_engine import EventsRouter, OpenRouterRateLimitManager

    OpenRouterRateLimitManager._cooldown_until = time.time() + 120.0
    OpenRouterRateLimitManager._cooldown_reason = "Mock cooldown"

    res = EventsRouter.generate_event_summary(
        event_type="Fire",
        location="123 Main St",
        units="E1",
        status_detail="Active",
        attachments=[{"time": "12:00", "talkgroup": "LAW", "transcript": "On scene"}],
        current_summary="Existing summary untouched",
    )
    assert res == "Existing summary untouched"

    OpenRouterRateLimitManager.reset()


def test_summarize_event_attachments_dynamic_update(monkeypatch):
    """Verify summarize_event_attachments updates summary dynamically without debouncing."""
    from datetime import datetime, timezone, timedelta
    from app.services.events_worker import summarize_event_attachments
    from app.models.event import Event, EventTranscriptLink, EventsBase
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from unittest.mock import MagicMock

    engine = create_engine("sqlite:///:memory:")
    EventsBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    ev = Event(
        id=1,
        event_id="test-debounce-1",
        monitor_id=1,
        status="open",
        summary="Initial summary",
        master_last_run_at=datetime.now(timezone.utc) - timedelta(seconds=20),
    )
    db.add(ev)
    link = EventTranscriptLink(
        event_id=1,
        log_entry_id=101,
    )
    db.add(link)
    db.commit()

    mock_log = MagicMock()
    mock_log.id = 101
    mock_log.transcript = "Structure fire fully involved"
    mock_log.timestamp = datetime.now(timezone.utc)
    mock_log.talkgroup = "FIRE-DISP"

    mock_logs_db = MagicMock()
    mock_logs_db.query.return_value.filter.return_value.all.return_value = [mock_log]

    call_count = 0
    def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return f"Updated summary #{call_count}"

    monkeypatch.setattr("app.services.events_router_engine.EventsRouter.generate_event_summary", mock_generate)

    # Calling summarize_event_attachments immediately updates summary without dropping updates
    res = summarize_event_attachments(ev, db, mock_logs_db, force=False)
    assert res == "Updated summary #1"
    assert ev.summary == "Updated summary #1"
    assert call_count == 1

    # Calling again on another attachment also runs and updates without being blocked by debounce
    res_forced = summarize_event_attachments(ev, db, mock_logs_db, force=True)
    assert res_forced == "Updated summary #2"
    assert ev.summary == "Updated summary #2"
    assert call_count == 2


def test_openrouter_rate_limit_manager_regex_fallback():
    """Verify OpenRouterRateLimitManager extracts reset timestamp via regex when JSON is unparsed."""
    import time
    from app.services.events_router_engine import OpenRouterRateLimitManager
    OpenRouterRateLimitManager.reset()

    future_ms = int((time.time() + 450) * 1000)
    raw_body = f"Some partial HTML or raw text error: 'x-ratelimit-reset': {future_ms}, please try later."
    wait = OpenRouterRateLimitManager.record_429(
        status_code=429,
        headers={},
        body_text=raw_body,
    )
    assert 440 <= wait <= 455
    status = OpenRouterRateLimitManager.get_status()
    assert status["is_rate_limited"] is True
    assert status["seconds_remaining"] >= 440
    assert "UTC" in (status["reset_time_formatted"] or "")

    OpenRouterRateLimitManager.reset()


def test_openrouter_rate_limit_manager_get_status_and_db_persistence():
    """Verify OpenRouterRateLimitManager formats status properly and handles reset."""
    import time
    from app.services.events_router_engine import OpenRouterRateLimitManager
    OpenRouterRateLimitManager.reset()

    assert OpenRouterRateLimitManager.get_status()["is_rate_limited"] is False

    OpenRouterRateLimitManager._cooldown_until = time.time() + 180.0
    OpenRouterRateLimitManager._cooldown_reason = "Test custom cooldown"
    OpenRouterRateLimitManager._limit_source = "custom_test"

    status = OpenRouterRateLimitManager.get_status()
    assert status["is_rate_limited"] is True
    assert 175 <= status["seconds_remaining"] <= 181
    assert status["reason"] == "Test custom cooldown"
    assert status["limit_source"] == "custom_test"
    assert status["cooldown_until_iso"] is not None

    OpenRouterRateLimitManager.reset()
    assert OpenRouterRateLimitManager.get_status()["is_rate_limited"] is False


def test_rate_limit_status_api_endpoints():
    """Verify GET /api/events/rate-limit-status and POST /api/events/rate-limit-status/reset."""
    import time
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.routes.auth import get_current_active_user, get_current_admin_user
    from app.services.events_router_engine import OpenRouterRateLimitManager

    OpenRouterRateLimitManager.reset()
    OpenRouterRateLimitManager._cooldown_until = time.time() + 120.0
    OpenRouterRateLimitManager._cooldown_reason = "Daily quota reached"

    mock_admin = User(id=1, username="testadmin", is_active=True, is_admin=True)
    app.dependency_overrides[get_current_active_user] = lambda: mock_admin
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin

    try:
        client = TestClient(app)
        get_res = client.get("/api/events/rate-limit-status")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["is_rate_limited"] is True
        assert data["seconds_remaining"] > 100
        assert data["reason"] == "Daily quota reached"

        # Test reset endpoint
        post_res = client.post("/api/events/rate-limit-status/reset")
        assert post_res.status_code == 200
        assert post_res.json()["ok"] is True

        # Now status should be false
        get_after = client.get("/api/events/rate-limit-status")
        assert get_after.json()["is_rate_limited"] is False
    finally:
        app.dependency_overrides.clear()
        OpenRouterRateLimitManager.reset()


def test_rate_limiter_config_disabled(monkeypatch):
    """Verify rate limiter is bypassed when enabled=False in config."""
    from app.config import get_settings, RateLimiterConfig
    from app.services.events_router_engine import OpenRouterRateLimitManager

    OpenRouterRateLimitManager.reset()
    settings = get_settings()
    monkeypatch.setattr(settings.config, "rate_limiter", RateLimiterConfig(enabled=False, auto_start_events_after_timeout=True))

    wait = OpenRouterRateLimitManager.record_429(
        status_code=429,
        headers={"retry-after": "60"},
        body_text="Rate limit",
    )
    assert wait == 0.0
    is_limited, rem, _ = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is False
    assert rem == 0.0

    status = OpenRouterRateLimitManager.get_status()
    assert status["is_rate_limited"] is False
    assert status["rate_limiter_enabled"] is False

    OpenRouterRateLimitManager.reset()


def test_rate_limiter_config_auto_start_disabled(monkeypatch):
    """Verify events routing holds in paused state when auto_start_events_after_timeout=False."""
    import time
    from app.config import get_settings, RateLimiterConfig
    from app.services.events_router_engine import OpenRouterRateLimitManager

    OpenRouterRateLimitManager.reset()
    settings = get_settings()
    monkeypatch.setattr(settings.config, "rate_limiter", RateLimiterConfig(enabled=True, auto_start_events_after_timeout=False))

    # Set cooldown to a timestamp in the past
    past_time = time.time() - 10.0
    OpenRouterRateLimitManager._cooldown_until = past_time
    OpenRouterRateLimitManager._cooldown_reason = "Expired 429"

    is_limited, rem, reason = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is True
    assert rem == 0.0
    assert "Auto-start is disabled in config" in reason

    status = OpenRouterRateLimitManager.get_status()
    assert status["is_rate_limited"] is True
    assert status["is_paused_waiting_start"] is True
    assert status["auto_start_events_after_timeout"] is False

    OpenRouterRateLimitManager.reset()


def test_rate_limiter_config_auto_start_enabled(monkeypatch):
    """Verify events routing automatically resumes when auto_start_events_after_timeout=True."""
    import time
    from app.config import get_settings, RateLimiterConfig
    from app.services.events_router_engine import OpenRouterRateLimitManager

    OpenRouterRateLimitManager.reset()
    settings = get_settings()
    monkeypatch.setattr(settings.config, "rate_limiter", RateLimiterConfig(enabled=True, auto_start_events_after_timeout=True))

    past_time = time.time() - 10.0
    OpenRouterRateLimitManager._cooldown_until = past_time
    OpenRouterRateLimitManager._cooldown_reason = "Expired 429"

    is_limited, rem, _ = OpenRouterRateLimitManager.is_rate_limited()
    assert is_limited is False
    assert rem == 0.0

    status = OpenRouterRateLimitManager.get_status()
    assert status["is_rate_limited"] is False
    assert status["is_paused_waiting_start"] is False

    OpenRouterRateLimitManager.reset()


def test_settings_save_config_auto_restart():
    """Verify POST /api/settings/config?restart=true accepts restart option and returns restarting flag."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.routes.auth import get_current_admin_user

    mock_admin = User(id=1, username="adminuser", is_active=True, is_admin=True)
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin

    try:
        client = TestClient(app)
        # Mock valid yaml save without restart
        res = client.post("/api/settings/config?restart=false", json={"content": "model:\n  name: test\n"})
        assert res.status_code == 200
        assert res.json().get("restarting") is False
    finally:
        app.dependency_overrides.clear()


