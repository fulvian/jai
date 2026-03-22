"""Test Health Endpoints."""

import pytest
from fastapi.testclient import TestClient

from me4brain.api.main import app


@pytest.fixture
def client() -> TestClient:
    """Test client per FastAPI."""
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "services" in data


def test_liveness_check(client: TestClient) -> None:
    """Test /health/live endpoint."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_readiness_check(client: TestClient) -> None:
    """Test /health/ready endpoint."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert "checks" in data
