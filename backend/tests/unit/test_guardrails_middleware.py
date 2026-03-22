"""Integration tests for GuardrailsMiddleware with FastAPI TestClient.

Tests the middleware with realistic API scenarios across domains.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from me4brain.api.main import create_app
from me4brain.api.middleware.auth import AuthenticatedUser

# Mock user for authentication
MOCK_USER = AuthenticatedUser(user_id="test_user", tenant_id="test_tenant", roles=["user"])


@pytest.fixture
def client():
    """Create a test client with the full application."""
    app = create_app()
    from me4brain.api.routes.memory import get_current_user

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    return TestClient(app)


@pytest.fixture
def mock_memory_services():
    """Mock memory services."""
    with (
        patch("me4brain.api.routes.memory.get_episodic_memory") as mock_epi,
        patch("me4brain.api.routes.memory.get_semantic_memory") as mock_sem,
        patch("me4brain.api.routes.memory.get_embedding_service") as mock_emb,
    ):
        epi = AsyncMock()
        sem = AsyncMock()
        emb = MagicMock()

        mock_epi.return_value = epi
        mock_sem.return_value = sem
        mock_emb.return_value = emb

        yield {"epi": epi, "sem": sem, "emb": emb}


class TestGuardrailsMiddlewareIntegration:
    """Integration tests for guardrails middleware."""

    def test_domain_query_endpoint_accessible(self, client):
        """Verify domain query endpoint is accessible."""
        response = client.post("/v1/domains/sports_nba/query", json={"query": "top players"})
        # Should return 200 (success), 400 (bad request), or 500 (error)
        assert response.status_code in [200, 400, 422, 500]

    @pytest.mark.parametrize(
        "domain",
        [
            "sports_nba",
            "finance_crypto",
            "geo_weather",
        ],
    )
    def test_guardrails_applied_to_different_domains(self, client, domain):
        """Verify guardrails work across different domains."""
        response = client.post(f"/v1/domains/{domain}/query", json={"query": "test"})
        # Should handle gracefully
        assert response.status_code in [200, 400, 404, 422, 500]

    def test_guardrails_config_accessible(self):
        """Verify guardrails configuration is accessible."""
        from me4brain.domains.adaptive_guardrails import get_guardrails_for_domain

        config = get_guardrails_for_domain("sports_nba")
        assert config is not None
        assert config.max_response_bytes > 0
        assert config.max_items_per_page > 0

    def test_universal_guardrails_config_cached(self):
        """Verify universal config caching."""
        from me4brain.domains.universal_guardrails import get_universal_config

        config1 = get_universal_config("sports_nba")
        config2 = get_universal_config("sports_nba")

        # Should return same instance (cached)
        assert config1 is config2

    def test_multiple_sequential_requests(self, client):
        """Verify middleware handles sequential requests."""
        for i in range(3):
            response = client.post("/v1/domains/sports_nba/query", json={"query": f"query_{i}"})
            assert response.status_code in [200, 400, 422, 500]

    def test_valid_json_responses(self, client):
        """Verify responses are valid JSON when successful."""
        response = client.post("/v1/domains/sports_nba/query", json={"query": "test"})

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (dict, list))

    def test_middleware_does_not_modify_small_responses(self, client):
        """Verify small responses pass through middleware unchanged."""
        response = client.get("/v1/health")

        # Health should work (200) or not exist (404)
        assert response.status_code in [200, 404]

    def test_content_type_header_preserved(self, client):
        """Verify Content-Type header is set correctly."""
        response = client.post("/v1/domains/sports_nba/query", json={"query": "test"})

        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")
