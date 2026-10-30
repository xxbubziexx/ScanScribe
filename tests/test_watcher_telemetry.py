import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.routes.auth import get_current_active_user
from app.models.user import User


def test_health_check_returns_status():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "healthy"}


def test_watcher_status_accessible_to_non_admin_active_user():
    regular_user = User(
        id=99,
        username="operator_bob",
        email="operator_bob@example.com",
        is_active=True,
        is_admin=False,
    )

    app.dependency_overrides[get_current_active_user] = lambda: regular_user
    client = TestClient(app)

    try:
        response = client.get("/api/watcher/status")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data
        assert "engine_device" in data
        assert "processor_running" in data
        assert "memory_used_gb" in data
        assert "cpu_percent" in data
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
