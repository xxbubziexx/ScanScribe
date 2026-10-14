"""Unit and integration tests for Scanner Intelligence conversational query engine."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.database import init_db, SessionLocal
from app.models.user import User
from app.models.log_entry import LogEntry
from app.models.chat import ChatThread, ChatMessage
from app.routes.auth import get_password_hash, create_access_token
from app.schemas.chat import ChatTimeScope
from app.services.chat_context import (
    parse_time_scope,
    extract_cited_ids,
    format_context_block,
    build_system_prompt,
    query_transmissions,
)


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def chat_auth():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "chat_operator").first()
        if not user:
            user = User(
                username="chat_operator",
                email="operator@scanscribe.local",
                hashed_password=get_password_hash("test-pass-1234"),
                is_active=True,
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = create_access_token(data={"sub": user.username})
        return {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user.id}
    finally:
        db.close()


def test_parse_time_scope_presets():
    now = datetime.now(timezone.utc)

    # 1h
    s1, e1, d1 = parse_time_scope(ChatTimeScope(preset="1h"))
    assert (e1 - s1).total_seconds() == pytest.approx(3600, abs=10)
    assert d1 == "Past 1 Hour"

    # 4h
    s4, e4, d4 = parse_time_scope(ChatTimeScope(preset="4h"))
    assert (e4 - s4).total_seconds() == pytest.approx(14400, abs=10)
    assert d4 == "Past 4 Hours"

    # today
    st, et, dt = parse_time_scope(ChatTimeScope(preset="today"))
    assert st.hour == 0 and st.minute == 0
    assert "Today" in dt


def test_extract_cited_ids():
    text = "Engine 4 responded [TX-1042] while Medic 12 arrived at 18:04 [TX-1043]. Earlier [TX-1042] checked in."
    ids = extract_cited_ids(text)
    assert ids == [1042, 1043]

    empty_ids = extract_cited_ids("No citations in this text.")
    assert empty_ids == []


def test_format_context_block():
    empty_block = format_context_block([], "Past 1 Hour")
    assert "NO RADIO TRANSMISSIONS RECORDED" in empty_block

    now = datetime.now(timezone.utc)
    mock_log = LogEntry(
        id=999,
        filename="test.mp3",
        timestamp=now,
        talkgroup="FIRE_DISP",
        transcript="Structure fire reported on 5th Street.",
    )
    block = format_context_block([mock_log], "Today")
    assert "[TX-999" in block
    assert "TG: FIRE_DISP" in block
    assert "Structure fire reported on 5th Street." in block


def test_chat_thread_lifecycle(client, chat_auth):
    headers = chat_auth["headers"]

    # 1. Create Thread
    create_res = client.post(
        "/api/chat/threads",
        headers=headers,
        json={"title": "Test Channel Query", "time_scope_preset": "4h", "talkgroups": ["POLICE_DISP"]},
    )
    assert create_res.status_code == 201
    thread_data = create_res.json()
    thread_id = thread_data["id"]
    assert thread_data["title"] == "Test Channel Query"
    assert thread_data["talkgroups"] == ["POLICE_DISP"]

    # 2. List Threads
    list_res = client.get("/api/chat/threads", headers=headers)
    assert list_res.status_code == 200
    threads = list_res.json()
    assert any(t["id"] == thread_id for t in threads)

    # 3. Get Thread Detail
    detail_res = client.get(f"/api/chat/threads/{thread_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == thread_id
    assert isinstance(detail["messages"], list)

    # 4. Patch Thread
    patch_res = client.patch(
        f"/api/chat/threads/{thread_id}",
        headers=headers,
        json={"title": "Updated Title", "time_scope_preset": "12h"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Title"
    assert patch_res.json()["time_scope_preset"] == "12h"

    # 5. Delete Thread
    del_res = client.delete(f"/api/chat/threads/{thread_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True

    # 6. Verify Deleted
    get_after_del = client.get(f"/api/chat/threads/{thread_id}", headers=headers)
    assert get_after_del.status_code == 404


def test_transmission_lookup(client, chat_auth):
    headers = chat_auth["headers"]
    db = SessionLocal()
    try:
        log = LogEntry(
            filename="unit_112_code3.mp3",
            timestamp=datetime.now(timezone.utc),
            log_date="2026-10-14",
            duration=4.2,
            audio_path="audio_storage/unit_112_code3.mp3",
            transcript="Unit 112 en route code 3 to vehicle rollover on Highway 61.",
            talkgroup="HIGHWAY_PATROL",
            confidence=0.98,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        log_id = log.id
    finally:
        db.close()

    res = client.get(f"/api/chat/transmissions/{log_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == log_id
    assert data["talkgroup"] == "HIGHWAY_PATROL"
    assert "Highway 61" in data["transcript"]
    assert data["audio_url"] == "/audio_storage/unit_112_code3.mp3"


def test_talkgroups_listing(client, chat_auth):
    headers = chat_auth["headers"]
    res = client.get("/api/chat/talkgroups", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
