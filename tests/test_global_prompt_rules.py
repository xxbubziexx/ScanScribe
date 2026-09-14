"""Unit and integration tests for Global System Prompt Optional Injector."""
from unittest.mock import patch, MagicMock
import pytest
from app.services.events_router_engine import build_system_prompt, EventsRouter, SUMMARY_SYSTEM_PROMPT
from app.services.events_worker import get_global_prompt_rules
from app.database import EventsSessionLocal, init_db
from app.models.event import SystemSetting, Monitor, Event
from app.models.user import User
from app.routes.auth import get_current_active_user, get_current_admin_user
from fastapi.testclient import TestClient
from app.main import app


def test_build_system_prompt_without_rules():
    """Verify standard system prompt without global rules or known units."""
    prompt = build_system_prompt()
    assert "### Global Area & Operational Rules" not in prompt
    assert "### Known Unit Identifiers & Prefix Rules" not in prompt


def test_build_system_prompt_with_global_rules():
    """Verify global rules block injection."""
    rules = "10-50 = Motor Vehicle Accident\n10-97 = On Scene\nArea: St. Francois County, MO"
    prompt = build_system_prompt(global_rules=rules)
    assert "### Global Area & Operational Rules (AUTHORITATIVE GROUND TRUTH):" in prompt
    assert "10-50 = Motor Vehicle Accident" in prompt
    assert "Area: St. Francois County, MO" in prompt
    assert "### Known Unit Identifiers & Prefix Rules" not in prompt


def test_build_system_prompt_combined():
    """Verify both global rules and monitor known units are cleanly injected."""
    rules = "10-50 = MVA"
    units = "38xx = Park Hills\n100s = Farmington PD"
    prompt = build_system_prompt(known_units=units, global_rules=rules)

    assert "### Global Area & Operational Rules (AUTHORITATIVE GROUND TRUTH):" in prompt
    assert "10-50 = MVA" in prompt
    assert "### Known Unit Identifiers & Prefix Rules (AUTHORITATIVE GROUND TRUTH):" in prompt
    assert "38xx = Park Hills" in prompt


def test_build_system_prompt_empty_or_whitespace():
    """Verify whitespace-only rules are ignored and do not bloat prompt."""
    prompt = build_system_prompt(global_rules="   \n\t  ")
    assert "### Global Area & Operational Rules" not in prompt


def test_get_global_prompt_rules_db_precedence():
    """Verify DB SystemSetting takes precedence over config.yml fallback."""
    init_db()
    db = EventsSessionLocal()
    try:
        # Clear or create setting
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_prompt_rules").first()
        if not setting:
            setting = SystemSetting(key="global_prompt_rules", value="10-50 = DB Accident Code")
            db.add(setting)
        else:
            setting.value = "10-50 = DB Accident Code"
        db.commit()

        res = get_global_prompt_rules(db)
        assert res == "10-50 = DB Accident Code"
    finally:
        db.close()


def test_get_global_prompt_rules_fallback():
    """Verify fallback to config.yml when DB setting is missing or empty."""
    init_db()
    db = EventsSessionLocal()
    try:
        # Delete or empty setting
        db.query(SystemSetting).filter(SystemSetting.key == "global_prompt_rules").delete()
        db.commit()

        with patch("app.services.events_worker.get_settings") as mock_settings:
            mock_pipe = MagicMock()
            mock_pipe.global_prompt_rules = "10-50 = Config Fallback MVA"
            mock_settings.return_value.config.events_pipeline = mock_pipe

            res = get_global_prompt_rules(db)
            assert res == "10-50 = Config Fallback MVA"
    finally:
        db.close()


def test_global_rules_api_endpoints():
    """Verify GET and POST /api/events/global-rules endpoints."""
    init_db()
    client = TestClient(app)

    mock_admin = User(id=1, username="admin", is_active=True, is_admin=True)
    mock_regular = User(id=2, username="regular", is_active=True, is_admin=False)

    app.dependency_overrides[get_current_active_user] = lambda: mock_regular
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin

    try:
        # Update rules via POST (admin)
        update_resp = client.post(
            "/api/events/global-rules",
            json={"global_rules": "10-50 = Motor Vehicle Crash\n10-8 = Available"}
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["ok"] is True
        assert "10-50 = Motor Vehicle Crash" in update_resp.json()["global_rules"]

        # Read back via GET (regular active user)
        get_resp = client.get("/api/events/global-rules")
        assert get_resp.status_code == 200
        assert "10-50 = Motor Vehicle Crash" in get_resp.json()["global_rules"]
    finally:
        app.dependency_overrides.clear()


def test_global_rules_in_summary_generation():
    """Verify global_rules are injected into summary system prompt."""
    rules = "10-50 = Major Vehicle Crash"
    attachments = [{"time": "12:00:00", "talkgroup": "DISP", "transcript": "Dispatched to 10-50 on Route 8"}]

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Units dispatched to a major vehicle crash on Route 8."}}]
        }
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with patch("app.services.events_router_engine.openrouter_api_key", return_value="fake_key"):
            res = EventsRouter.generate_event_summary(
                event_type="Traffic Accident",
                location="Route 8",
                units="Engine 1",
                status_detail="Dispatched",
                attachments=attachments,
                global_rules=rules,
            )
            assert res == "Units dispatched to a major vehicle crash on Route 8."

            # Inspect payload sent to OpenRouter
            call_kwargs = mock_client.post.call_args[1]
            payload = call_kwargs["json"]
            sys_msg = payload["messages"][0]["content"]
            assert "### Global Area & Operational Rules (AUTHORITATIVE GROUND TRUTH):" in sys_msg
            assert "10-50 = Major Vehicle Crash" in sys_msg
