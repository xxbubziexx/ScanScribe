"""Unit and integration tests for security patches."""
import os
import sys
import tempfile
import yaml
from unittest.mock import MagicMock
import pytest

# Mock heavy/hardware-dependent ML modules not present on local dev environment
for mod in ['torch', 'torchaudio', 'transformers', 'accelerate', 'soundfile', 'librosa', 'audioread', 'silero_vad', 'openai']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Setup isolated test directory & config
test_dir = tempfile.mkdtemp(prefix="scanscribe_test_")
config_file = os.path.join(test_dir, "config.yml")
ingest_dir = os.path.join(test_dir, "ingest")
output_dir = os.path.join(test_dir, "audio_storage")
log_dir = os.path.join(test_dir, "logs")
db_path = os.path.join(test_dir, "scanscribe.db")
models_dir = os.path.join(test_dir, "models")

for d in [ingest_dir, output_dir, log_dir, models_dir]:
    os.makedirs(d, exist_ok=True)

with open(config_file, "w") as f:
    yaml.dump({
        "model": {"name": "test-model", "path": models_dir, "workers": 1, "device": "cpu"},
        "watcher": {"auto_start": False},
        "storage": {"save_audio_for_playback": True, "retention_days": 30, "cleanup_hour": 3},
        "events_pipeline": {"enabled": False},
    }, f)

os.environ["CONFIG_PATH"] = config_file
os.environ["INGEST_DIR"] = ingest_dir
os.environ["OUTPUT_DIR"] = output_dir
os.environ["LOG_DIR"] = log_dir
os.environ["DB_PATH"] = db_path
os.environ["SECRET_KEY"] = "test-secret-key-12345"

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal
from app.models.user import User
from app.routes.auth import get_password_hash, create_access_token
from app.utils.limiter import limiter


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def test_users():
    db = SessionLocal()
    try:
        # Create regular user
        user = db.query(User).filter(User.username == "test_regular_user").first()
        if not user:
            user = User(
                username="test_regular_user",
                email="regular@example.com",
                hashed_password=get_password_hash("password123"),
                is_active=True,
                is_admin=False,
            )
            db.add(user)

        # Create admin user
        admin = db.query(User).filter(User.username == "test_admin_user").first()
        if not admin:
            admin = User(
                username="test_admin_user",
                email="admin@example.com",
                hashed_password=get_password_hash("admin123"),
                is_active=True,
                is_admin=True,
            )
            db.add(admin)

        db.commit()

        user_token = create_access_token({"sub": "test_regular_user"})
        admin_token = create_access_token({"sub": "test_admin_user"})

        return {
            "user_token": user_token,
            "admin_token": admin_token,
        }
    finally:
        db.close()


def test_health_check_stripped_down(client):
    """Ensure /health returns only {'status': 'healthy'} without internal paths or model names."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "healthy"}
    assert "ingest_dir" not in data
    assert "model" not in data


def test_security_headers_present(client):
    """Ensure security headers are injected on responses."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Strict-Transport-Security" in response.headers
    assert "Content-Security-Policy" in response.headers
    assert "Access-Control-Allow-Origin" not in response.headers


def test_openapi_docs_disabled(client):
    """Ensure OpenAPI docs are disabled to prevent reconnaissance."""
    r_docs = client.get("/docs")
    assert r_docs.status_code == 404

    r_redoc = client.get("/redoc")
    assert r_redoc.status_code == 404

    r_openapi = client.get("/openapi.json")
    assert r_openapi.status_code == 404


def test_registration_does_not_grant_admin(client, test_users):
    """Ensure /api/auth/register creates normal non-admin users."""
    import uuid
    random_name = f"newuser_{uuid.uuid4().hex[:8]}"
    payload = {
        "username": random_name,
        "email": f"{random_name}@example.com",
        "password": "Password123!",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == random_name
    assert data["is_admin"] is False


def test_settings_config_admin_guard(client, test_users):
    """Verify GET and POST /api/settings/config require admin access."""
    # 1. Unauthenticated -> 401
    r_unauth = client.get("/api/settings/config")
    assert r_unauth.status_code == 401

    # 2. Regular user -> 403
    r_user = client.get(
        "/api/settings/config",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_user.status_code == 403

    # 3. Admin user -> 200
    r_admin = client.get(
        "/api/settings/config",
        headers={"Authorization": f"Bearer {test_users['admin_token']}"}
    )
    assert r_admin.status_code == 200
    assert "content" in r_admin.json()

    # POST config with regular user -> 403
    r_post_user = client.post(
        "/api/settings/config",
        json={"content": "test: true"},
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_post_user.status_code == 403

    # POST restart with regular user -> 403
    r_restart_user = client.post(
        "/api/settings/restart",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_restart_user.status_code == 403


def test_events_debug_admin_guard(client, test_users):
    """Verify GET and DELETE /api/events/debug require admin access."""
    # Unauthenticated -> 401
    assert client.get("/api/events/debug").status_code == 401

    # Regular user -> 403
    r_user = client.get(
        "/api/events/debug",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_user.status_code == 403

    # Admin user -> 200
    r_admin = client.get(
        "/api/events/debug",
        headers={"Authorization": f"Bearer {test_users['admin_token']}"}
    )
    assert r_admin.status_code == 200


def test_watcher_status_admin_guard(client, test_users):
    """Verify GET /api/watcher/status requires admin access."""
    # Unauthenticated -> 401
    assert client.get("/api/watcher/status").status_code == 401

    # Regular user -> 403
    r_user = client.get(
        "/api/watcher/status",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_user.status_code == 403

    # Admin user -> 200
    r_admin = client.get(
        "/api/watcher/status",
        headers={"Authorization": f"Bearer {test_users['admin_token']}"}
    )
    assert r_admin.status_code == 200
    data = r_admin.json()
    assert "memory_used_gb" in data
    assert "cpu_percent" in data


def test_auth_login_rate_limiting(client):
    """Verify rate limiter blocks after 5 requests per minute on login/token endpoints."""
    # Reset limiter storage if needed for clean test
    limiter.reset()

    # Make 5 requests (valid or invalid)
    for i in range(5):
        r = client.post(
            "/api/auth/token",
            data={"username": f"user_{i}", "password": "wrongpassword"}
        )
        assert r.status_code in (400, 401), f"Attempt {i+1} got unexpected {r.status_code}"

    # 6th request must be 429
    r6 = client.post(
        "/api/auth/token",
        data={"username": "user_6", "password": "wrongpassword"}
    )
    assert r6.status_code == 429


def test_auth_login_endpoint_rate_limiting(client):
    """Verify /api/auth/login endpoint is also rate limited."""
    limiter.reset()

    for i in range(5):
        r = client.post(
            "/api/auth/login",
            data={"username": f"user_{i}", "password": "wrongpassword"}
        )
        assert r.status_code in (400, 401), f"Attempt {i+1} got unexpected {r.status_code}"

    r6 = client.post(
        "/api/auth/login",
        data={"username": "user_6", "password": "wrongpassword"}
    )
    assert r6.status_code == 429


def test_events_debug_delete_admin_guard(client, test_users):
    """Verify DELETE /api/events/debug requires admin access."""
    # Unauthenticated -> 401
    assert client.delete("/api/events/debug").status_code == 401

    # Regular user -> 403
    r_user = client.delete(
        "/api/events/debug",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_user.status_code == 403

    # Admin user -> 200
    r_admin = client.delete(
        "/api/events/debug",
        headers={"Authorization": f"Bearer {test_users['admin_token']}"}
    )
    assert r_admin.status_code == 200


def test_react_spa_routes_intact(client):
    """Verify frontend SPA serving and legacy redirect routes remain functional."""
    # Legacy redirect endpoints return 307
    r_root = client.get("/", follow_redirects=False)
    assert r_root.status_code == 307
    assert r_root.headers["location"] == "/app/"

    r_login_redir = client.get("/login", follow_redirects=False)
    assert r_login_redir.status_code == 307
    assert r_login_redir.headers["location"] == "/app/login"

    r_settings_redir = client.get("/settings", follow_redirects=False)
    assert r_settings_redir.status_code == 307
    assert r_settings_redir.headers["location"] == "/app/settings"

    # SPA shell endpoints (returns 200 or 503 if dist not built in test env)
    r_app = client.get("/app", follow_redirects=False)
    assert r_app.status_code in (200, 503)

    r_app_slash = client.get("/app/", follow_redirects=False)
    assert r_app_slash.status_code in (200, 503)


def test_users_list_and_last_seen_tracking(client, test_users):
    """Verify GET /api/users/list returns user records with last_seen_at tracked."""
    # Unauthenticated -> 401
    assert client.get("/api/users/list").status_code == 401

    # Regular user -> 403
    r_user = client.get(
        "/api/users/list",
        headers={"Authorization": f"Bearer {test_users['user_token']}"}
    )
    assert r_user.status_code == 403

    # Admin user -> 200
    r_admin = client.get(
        "/api/users/list",
        headers={"Authorization": f"Bearer {test_users['admin_token']}"}
    )
    assert r_admin.status_code == 200
    users = r_admin.json()
    assert isinstance(users, list)
    assert len(users) >= 2

    for u in users:
        assert "username" in u
        assert "email" in u
        assert "is_admin" in u
        assert "created_at" in u
        assert "last_seen_at" in u

    # The admin user making the request was just active, so last_seen_at should be populated
    admin_entry = [u for u in users if u["username"] == "test_admin_user"][0]
    assert admin_entry["last_seen_at"] is not None


def test_insights_stats_activity_events_count(client, test_users):
    """Verify GET /api/insights/stats returns events_count in activity points."""
    # Unauthenticated -> 401
    assert client.get("/api/insights/stats").status_code == 401

    headers = {"Authorization": f"Bearer {test_users['user_token']}"}

    # 1. Hourly view
    r_hourly = client.get("/api/insights/stats?view=hourly", headers=headers)
    assert r_hourly.status_code == 200
    data_hourly = r_hourly.json()
    assert "activity" in data_hourly
    assert len(data_hourly["activity"]) == 24
    for pt in data_hourly["activity"]:
        assert "label" in pt
        assert "count" in pt
        assert "events_count" in pt
        assert isinstance(pt["events_count"], int)

    # 2. Daily view
    r_daily = client.get("/api/insights/stats?view=daily", headers=headers)
    assert r_daily.status_code == 200
    data_daily = r_daily.json()
    assert len(data_daily["activity"]) == 7
    for pt in data_daily["activity"]:
        assert "events_count" in pt
        assert isinstance(pt["events_count"], int)

    # 3. Weekly view
    r_weekly = client.get("/api/insights/stats?view=weekly", headers=headers)
    assert r_weekly.status_code == 200
    data_weekly = r_weekly.json()
    assert len(data_weekly["activity"]) == 8
    for pt in data_weekly["activity"]:
        assert "events_count" in pt
        assert isinstance(pt["events_count"], int)


def test_insights_search_attached_events(client, test_users):
    """Verify GET /api/insights/search returns attached_events for open and closed events."""
    from datetime import datetime
    from app.database import LogsSessionLocal, EventsSessionLocal, init_db
    from app.models.log_entry import LogEntry
    from app.models.event import Monitor, Event, EventTranscriptLink

    init_db()

    # Unauthenticated -> 401
    assert client.get("/api/insights/search").status_code == 401

    headers = {"Authorization": f"Bearer {test_users['user_token']}"}

    logs_db = LogsSessionLocal()
    events_db = EventsSessionLocal()
    try:
        now = datetime.now()
        log1 = LogEntry(
            filename="test1.mp3",
            timestamp=now,
            talkgroup="Dispatch 1",
            transcript="Structure fire on Main St",
            duration=5.0,
            file_size=1024,
            audio_path="test1.mp3",
        )
        log2 = LogEntry(
            filename="test2.mp3",
            timestamp=now,
            talkgroup="Dispatch 2",
            transcript="Accident scene cleared",
            duration=4.0,
            file_size=2048,
            audio_path="test2.mp3",
        )
        log3 = LogEntry(
            filename="test3.mp3",
            timestamp=now,
            talkgroup="Dispatch 3",
            transcript="Routine radio check",
            duration=3.0,
            file_size=512,
            audio_path="test3.mp3",
        )
        logs_db.add_all([log1, log2, log3])
        logs_db.commit()
        logs_db.refresh(log1)
        logs_db.refresh(log2)
        logs_db.refresh(log3)

        mon = Monitor(name="Test Monitor", talkgroup_ids='["Dispatch 1", "Dispatch 2"]')
        events_db.add(mon)
        events_db.commit()
        events_db.refresh(mon)

        ev_open = Event(
            event_id="EVT-TEST-OPEN",
            monitor_id=mon.id,
            status="open",
            event_type="Structure Fire",
        )
        ev_closed = Event(
            event_id="EVT-TEST-CLOSED",
            monitor_id=mon.id,
            status="closed",
            event_type="Traffic Accident",
        )
        events_db.add_all([ev_open, ev_closed])
        events_db.commit()
        events_db.refresh(ev_open)
        events_db.refresh(ev_closed)

        link1 = EventTranscriptLink(
            event_id=ev_open.id,
            log_entry_id=log1.id,
        )
        link2 = EventTranscriptLink(
            event_id=ev_closed.id,
            log_entry_id=log2.id,
        )
        events_db.add_all([link1, link2])
        events_db.commit()

        date_str = now.strftime("%Y-%m-%d")
        r = client.get(f"/api/insights/search?date={date_str}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        results_by_id = {item["id"]: item for item in data["results"]}

        # log1 -> attached to open event
        assert log1.id in results_by_id
        evs1 = results_by_id[log1.id].get("attached_events", [])
        assert len(evs1) == 1
        assert evs1[0]["event_id"] == "EVT-TEST-OPEN"
        assert evs1[0]["status"] == "open"
        assert evs1[0]["event_type"] == "Structure Fire"

        # log2 -> attached to closed event
        assert log2.id in results_by_id
        evs2 = results_by_id[log2.id].get("attached_events", [])
        assert len(evs2) == 1
        assert evs2[0]["event_id"] == "EVT-TEST-CLOSED"
        assert evs2[0]["status"] == "closed"
        assert evs2[0]["event_type"] == "Traffic Accident"

        # log3 -> unattached
        assert log3.id in results_by_id
        assert results_by_id[log3.id].get("attached_events") == []
    finally:
        logs_db.close()
        events_db.close()



