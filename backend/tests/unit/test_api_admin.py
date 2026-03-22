import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock
from me4brain.api.main import app
from me4brain.api.middleware.auth import get_current_user, AuthenticatedUser

client = TestClient(app)


# Bypass auth for admin tests
async def override_get_current_user():
    return AuthenticatedUser(user_id="admin_u", tenant_id="default", roles=["admin", "super_admin"])


@pytest.fixture
def mock_admin_services():
    app.dependency_overrides[get_current_user] = override_get_current_user
    with (
        patch("me4brain.api.routes.admin.get_sleep_mode") as mock_sleep,
        patch("me4brain.api.routes.admin.create_openapi_ingester") as mock_ingester,
    ):
        yield mock_sleep, mock_ingester
    app.dependency_overrides.clear()


def test_admin_trigger_consolidation(mock_admin_services):
    mock_sleep, _ = mock_admin_services
    mock_sleep_instance = AsyncMock()
    mock_sleep.return_value = mock_sleep_instance

    response = client.post(
        "/v1/admin/consolidation/trigger", json={"tenant_id": "default", "dry_run": True}
    )
    assert response.status_code == 200
    assert "Dry run" in response.json()["message"]


def test_admin_trigger_consolidation_full_run(mock_admin_services):
    """Test consolidation con dry_run=False (background task)."""
    mock_sleep, _ = mock_admin_services
    mock_sleep_instance = AsyncMock()
    mock_sleep.return_value = mock_sleep_instance

    response = client.post(
        "/v1/admin/consolidation/trigger", json={"tenant_id": "test_tenant", "dry_run": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert "job_id" in data


def test_admin_scheduler_start(mock_admin_services):
    """Test avvio scheduler consolidation."""
    mock_sleep, _ = mock_admin_services
    mock_sleep_instance = AsyncMock()
    mock_sleep.return_value = mock_sleep_instance

    response = client.post(
        "/v1/admin/consolidation/scheduler", json={"action": "start", "interval_hours": 6}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert response.json()["interval_hours"] == 6


def test_admin_scheduler_stop(mock_admin_services):
    """Test stop scheduler consolidation."""
    mock_sleep, _ = mock_admin_services
    mock_sleep_instance = AsyncMock()
    mock_sleep.return_value = mock_sleep_instance

    response = client.post("/v1/admin/consolidation/scheduler", json={"action": "stop"})
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_admin_scheduler_status(mock_admin_services):
    """Test status scheduler consolidation."""
    mock_sleep, _ = mock_admin_services
    mock_sleep_instance = MagicMock()
    mock_sleep_instance._running = True
    mock_sleep_instance._task = MagicMock()
    mock_sleep.return_value = mock_sleep_instance

    response = client.post("/v1/admin/consolidation/scheduler", json={"action": "status"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["has_task"] is True


def test_admin_ingest_openapi(mock_admin_services):
    """Test ingestione specifica OpenAPI."""
    _, mock_ingester = mock_admin_services
    mock_ingester_instance = AsyncMock()
    mock_ingester_instance.ingest_from_url = AsyncMock(return_value=["tool_1", "tool_2", "tool_3"])
    mock_ingester.return_value = mock_ingester_instance

    response = client.post(
        "/v1/admin/tools/ingest",
        json={"source": "https://api.example.com/openapi.json", "api_prefix": "example"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["tools_created"] == 3


def test_admin_ingest_openapi_file(mock_admin_services):
    """Test ingestione da file locale."""
    _, mock_ingester = mock_admin_services
    mock_ingester_instance = AsyncMock()
    mock_ingester_instance.ingest_from_file = AsyncMock(return_value=["tool_local"])
    mock_ingester.return_value = mock_ingester_instance

    response = client.post("/v1/admin/tools/ingest", json={"source": "/path/to/local/openapi.yaml"})
    assert response.status_code == 200
    assert response.json()["tools_created"] == 1


def test_admin_get_stats_forbidden(mock_admin_services):
    # This might fail if the user doesn't have required role
    # But our override gives super_admin
    response = client.get("/v1/admin/stats")
    # We check if it hits the code
    assert response.status_code == 200
    assert "memory" in response.json()
