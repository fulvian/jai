"""Unit tests per NanoGPT client."""

import json
from unittest.mock import patch

import pytest
import httpx
import respx
from httpx import ConnectError, Response

from me4brain.llm import LLMConfig, LLMRequest, Message, NanoGPTClient, Tool, ToolFunction


@pytest.fixture
def mock_config():
    """Fixture per LLMConfig mockata."""
    return LLMConfig(
        NANOGPT_API_KEY="test-key",
        NANOGPT_BASE_URL="https://test.api/v1",
        LLM_PRIMARY_MODEL="deepseek/test-model",
    )


@pytest.fixture
def client(mock_config):
    """Fixture per NanoGPTClient."""
    return NanoGPTClient(
        api_key=mock_config.nanogpt_api_key,
        base_url=mock_config.nanogpt_base_url,
    )


@pytest.mark.asyncio
async def test_generate_response_success(client, mock_config):
    """Test generazione risposta semplice."""

    request = LLMRequest(
        model=mock_config.model_primary, messages=[Message(role="user", content="Hello")]
    )

    mock_response = {
        "id": "chatcmpl-123",
        "created": 1677652288,
        "model": "deepseek/test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello there!",
                },
                "finish_reason": "stop",
            }
        ],
    }

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json=mock_response))

        response = await client.generate_response(request)

        assert response.id == "chatcmpl-123"
        assert response.content == "Hello there!"
        assert response.model == "deepseek/test-model"


@pytest.mark.asyncio
async def test_generate_response_with_reasoning(client, mock_config):
    """Test generazione con reasoning field (NanoGPT)."""

    request = LLMRequest(
        model=mock_config.model_primary_thinking,
        messages=[Message(role="user", content="Solve x+1=2")],
    )

    mock_response = {
        "id": "chatcmpl-reason-123",
        "choices": [
            {
                "message": {"content": "x=1", "reasoning": "Subtract 1 from both sides."},
                "finish_reason": "stop",
            }
        ],
    }

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json=mock_response))

        response = await client.generate_response(request)

        assert response.content == "x=1"
        assert response.reasoning == "Subtract 1 from both sides."


@pytest.mark.asyncio
async def test_stream_response(client, mock_config):
    """Test streaming SEE response."""

    request = LLMRequest(
        model=mock_config.model_primary, messages=[Message(role="user", content="Count to 2")]
    )

    # SSE Stream chunks
    chunks = [
        'data: {"choices": [{"delta": {"content": "1"}}]}',
        'data: {"choices": [{"delta": {"content": "2"}}]}',
        "data: [DONE]",
    ]
    stream_content = "\n\n".join(chunks)

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=Response(
                200, headers={"Content-Type": "text/event-stream"}, text=stream_content
            )
        )

        accumulated_content = ""
        async for chunk in client.stream_response(request):
            if chunk.content:
                accumulated_content += chunk.content

        assert accumulated_content == "12"


@pytest.mark.asyncio
async def test_retry_on_error(client, mock_config):
    """Test retry automatico su errore di connessione."""

    request = LLMRequest(model="test", messages=[])

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        # Prima chiamata: Errore
        route = respx_mock.post("/chat/completions")
        route.side_effect = [
            ConnectError("Connection failed"),
            Response(200, json={"choices": [{"message": {"content": "Retry Works"}}]}),
        ]

        with patch("tenacity.nap.time.sleep"):
            response = await client.generate_response(request)

        assert response.content == "Retry Works"
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_generate_response_with_tools(client, mock_config):
    """Test generazione con tool calls nella risposta."""
    request = LLMRequest(
        model=mock_config.model_primary,
        messages=[Message(role="user", content="What's the weather?")],
        tools=[
            Tool(
                function=ToolFunction(name="get_weather", description="Get weather", parameters={})
            )
        ],
    )

    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Milan"}'},
                        }
                    ],
                }
            }
        ]
    }

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json=mock_response))
        response = await client.generate_response(request)

        assert len(response.choices[0].message.tool_calls) == 1
        assert response.choices[0].message.tool_calls[0].function.name == "get_weather"


@pytest.mark.asyncio
async def test_generate_response_http_error(client, mock_config):
    """Test gestione errori HTTP."""
    request = LLMRequest(model="test", messages=[])

    async with respx.mock(base_url=mock_config.nanogpt_base_url) as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(400, text="Bad Request"))

        with pytest.raises(httpx.HTTPStatusError):
            await client.generate_response(request)


@pytest.mark.asyncio
async def test_prepare_payload_special_params(client):
    """Test rami di _prepare_payload (reasoning effort, etc)."""
    request = LLMRequest(
        model="test", messages=[], reasoning_effort="high", response_format={"type": "json_object"}
    )

    payload = client._prepare_payload(request)
    assert payload["reasoning_effort"] == "high"
    assert payload["response_format"] == {"type": "json_object"}

    request.reasoning_exclude = True
    payload = client._prepare_payload(request)
    assert payload["reasoning"] == {"exclude": True}
