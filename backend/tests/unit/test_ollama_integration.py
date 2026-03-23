"""Unit tests for Ollama client and provider factory."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response

from me4brain.llm import (
    LLMRequest,
    Message,
    OllamaClient,
    get_llm_config,
)
from me4brain.llm.provider_factory import (
    get_reasoning_client,
    get_tool_calling_client,
    resolve_model_client,
)


@pytest.fixture
def ollama_config():
    """Fixture per LLMConfig con Ollama abilitato."""
    config = get_llm_config()
    config.use_local_tool_calling = True
    config.ollama_base_url = "http://localhost:1234/v1"
    config.ollama_model = "qwen3.5-4b-mlx"
    return config


@pytest.fixture
def client(ollama_config):
    """Fixture per OllamaClient."""
    return OllamaClient(base_url=ollama_config.ollama_base_url)


@pytest.mark.asyncio
async def test_ollama_generate_response_success(client, ollama_config):
    """Test generazione risposta semplice via Ollama."""
    request = LLMRequest(
        model=ollama_config.ollama_model,
        messages=[Message(role="user", content="Hello")],
    )

    mock_response = {
        "id": "ollama-123",
        "model": "qwen3.5-4b-mlx",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Local hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    async with respx.mock(base_url=ollama_config.ollama_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json=mock_response))

        response = await client.generate_response(request)

        assert response.content == "Local hello!"
        assert response.model == "qwen3.5-4b-mlx"
        assert response.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_ollama_tool_calling_payload(client, ollama_config):
    """Test che il payload inviato a Ollama include i tool e le opzioni."""
    from me4brain.llm.models import Tool, ToolFunction

    request = LLMRequest(
        model=ollama_config.ollama_model,
        messages=[Message(role="user", content="Call tool")],
        tools=[
            Tool(
                type="function",
                function=ToolFunction(name="test_tool", description="Test", parameters={}),
            )
        ],
    )

    async with respx.mock(base_url=ollama_config.ollama_base_url) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        )

        await client.generate_response(request)

        # Verifica payload
        sent_payload = json.loads(route.calls.last.request.content)
        assert "tools" in sent_payload
        assert sent_payload["tools"][0]["function"]["name"] == "test_tool"

        # Qwen optimizations
        assert sent_payload["top_k"] == 100
        assert sent_payload["repetition_penalty"] == 1.1


@pytest.mark.asyncio
async def test_provider_factory_dispatch(ollama_config):
    """Test che la factory restituisce il client corretto in base alla config."""
    # Test con Ollama abilitato
    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=ollama_config):
        tc_client = get_tool_calling_client()
        assert isinstance(tc_client, OllamaClient)

        r_client = get_reasoning_client()
        # With "replace all" strategy, both should use Ollama when local tool calling is enabled
        assert tc_client == r_client

    # Test con Ollama disabilitato
    ollama_config.use_local_tool_calling = False
    ollama_config.llm_local_only = False
    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=ollama_config):
        tc_client = get_tool_calling_client()
        # Se disabilitato, tc_client deve essere NanoGPT (get_llm_client)
        from me4brain.llm.nanogpt import NanoGPTClient

        assert isinstance(tc_client, NanoGPTClient)


@pytest.mark.asyncio
async def test_resolve_model_client_blocks_cloud_when_local_only(ollama_config):
    """In local-only mode, cloud model resolution must be blocked."""
    ollama_config.llm_local_only = True
    ollama_config.use_local_tool_calling = True

    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=ollama_config):
        with pytest.raises(ValueError, match="llm_local_only=true"):
            resolve_model_client("mistralai/mistral-large-3-675b-instruct-2512")


@pytest.mark.asyncio
async def test_resolve_model_client_accepts_local_in_local_only(ollama_config):
    """In local-only mode, local models resolve to Ollama client."""
    ollama_config.llm_local_only = True
    ollama_config.use_local_tool_calling = True

    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=ollama_config):
        client, model = resolve_model_client("qwen3.5:4b")
        assert isinstance(client, OllamaClient)
        assert model == "qwen3.5:4b"


@pytest.mark.asyncio
async def test_ollama_retry_on_connection_error(client, ollama_config):
    """Test che OllamaClient esegue retry su errori di connessione."""
    request = LLMRequest(model="test", messages=[])

    async with respx.mock(base_url=ollama_config.ollama_base_url) as respx_mock:
        route = respx_mock.post("/chat/completions")
        route.side_effect = [
            httpx.ConnectError("Failed"),
            Response(200, json={"choices": [{"message": {"content": "Success after retry"}}]}),
        ]

        with patch("tenacity.nap.time.sleep"):
            response = await client.generate_response(request)

        assert response.content == "Success after retry"
        assert route.call_count == 2
