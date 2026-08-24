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


def test_registration_does_not_grant_admin(client):
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
