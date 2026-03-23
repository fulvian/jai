"""Tests per Session Title Generation API."""

import pytest
from unittest.mock import AsyncMock, patch

from me4brain.api.routes.session_title import (
    GenerateTitleRequest,
    GenerateTitleResponse,
    _parse_title,
    _build_title_request,
    generate_session_title,
)


class TestParseTitle:
    """Test per il parsing del titolo generato."""

    def test_parse_title_valid(self):
        """Test con risposta valida."""
        assert _parse_title("Python Programming Tips") == "Python Programming Tips"

    def test_parse_title_with_quotes(self):
        """Test con virgolette da rimuovere."""
        assert _parse_title('"Python Programming"') == "Python Programming"

    def test_parse_title_with_single_quotes(self):
        """Test con virgolette singole da rimuovere."""
        assert _parse_title("'Python Programming'") == "Python Programming"

    def test_parse_title_with_whitespace(self):
        """Test con whitespace iniziale/finale."""
        assert _parse_title("  Python Programming  ") == "Python Programming"

    def test_parse_title_with_newlines(self):
        """Test con newline - i newline vengono mantenuti."""
        # Il parsing attuale mantiene i newline, la gestione dipende dal client
        assert _parse_title("Python\nProgramming\nTips") == "Python\nProgramming\nTips"

    def test_parse_title_empty(self):
        """Test con risposta vuota."""
        assert _parse_title("") is None
        assert _parse_title(None) is None

    def test_parse_title_too_long(self):
        """Test con titolo troppo lungo."""
        long_title = "A" * 100
        assert _parse_title(long_title) is None

    def test_parse_title_only_short_words(self):
        """Test con solo parole corte (< 2 caratteri)."""
        assert _parse_title("a b c d") is None


class TestBuildTitleRequest:
    """Test per la costruzione della request LLM."""

    def test_build_title_request(self):
        """Test che la request viene costruita correttamente."""
        prompt = "Come posso imparare Python?"
        request = _build_title_request(prompt)

        assert len(request.messages) == 2
        assert request.messages[0].role == "system"
        assert request.messages[1].role == "user"
        # Content can be str or list[MessageContent]
        content = request.messages[1].content
        if isinstance(content, str):
            assert prompt in content
        assert request.max_tokens == 20
        assert request.temperature == 0.3


class TestGenerateSessionTitle:
    """Test per la generazione del titolo."""

    @pytest.mark.asyncio
    async def test_generate_title_success(self):
        """Test generazione titolo con successo."""
        mock_response = AsyncMock()
        mock_response.content = "Python Learning Tips"

        with patch("me4brain.api.routes.session_title.DynamicLLMClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.generate_response = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            title = await generate_session_title("Come posso imparare Python?")

            assert title == "Python Learning Tips"
            mock_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_title_timeout(self):
        """Test generazione titolo con timeout."""
        with patch("me4brain.api.routes.session_title.DynamicLLMClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.generate_response = AsyncMock(side_effect=TimeoutError())
            mock_client_class.return_value = mock_client

            title = await generate_session_title("Test prompt", timeout=1.0)

            assert title is None

    @pytest.mark.asyncio
    async def test_generate_title_parse_failure(self):
        """Test generazione titolo con parsing fallito."""
        mock_response = AsyncMock()
        mock_response.content = ""  # Risposta vuota

        with patch("me4brain.api.routes.session_title.DynamicLLMClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.generate_response = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            title = await generate_session_title("Test prompt")

            assert title is None


class TestGenerateTitleEndpoint:
    """Test per l'endpoint API."""

    @pytest.mark.asyncio
    async def test_generate_title_endpoint_success(self, test_client):
        """Test endpoint con generazione riuscita."""
        mock_response = AsyncMock()
        mock_response.content = "Python Tips"

        with patch("me4brain.api.routes.session_title.DynamicLLMClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.generate_response = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            response = await test_client.post(
                "/v1/sessions/generate-title",
                json={"prompt": "Come imparare Python velocemente?"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "title" in data
            assert data["title"] == "Python Tips"

    @pytest.mark.asyncio
    async def test_generate_title_endpoint_fallback(self, test_client):
        """Test endpoint con fallback su truncation."""
        # Mock della funzione generate_session_title per restituire None (forza fallback)
        with patch(
            "me4brain.api.routes.session_title.generate_session_title",
            new_callable=AsyncMock,
            return_value=None,
        ):
            long_prompt = "Questa è una domanda molto lunga che dovrebbe essere troncata"
            response = await test_client.post(
                "/v1/sessions/generate-title",
                json={"prompt": long_prompt},
            )

            assert response.status_code == 200
            data = response.json()
            assert "title" in data
            # Il fallback dovrebbe troncare a 50 caratteri
            assert len(data["title"]) <= 53  # 50 + "..."

    @pytest.mark.asyncio
    async def test_generate_title_endpoint_empty_prompt(self, test_client):
        """Test endpoint con prompt vuoto."""
        response = await test_client.post(
            "/v1/sessions/generate-title",
            json={"prompt": ""},
        )

        # Dovrebbe fallire validazione
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_title_endpoint_prompt_too_long(self, test_client):
        """Test endpoint con prompt troppo lungo."""
        long_prompt = "A" * 3000  # Superiore al limite di 2000

        response = await test_client.post(
            "/v1/sessions/generate-title",
            json={"prompt": long_prompt},
        )

        # Dovrebbe fallire validazione
        assert response.status_code == 422
