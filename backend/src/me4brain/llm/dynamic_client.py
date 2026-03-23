"""Dynamic LLM Client - Supporto per provider dinamici.

Client generico che supporta API OpenAI-compatible e Anthropic.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import httpx
import structlog

from me4brain.llm.base import LLMProvider
from me4brain.llm.models import (
    Choice,
    ChoiceDelta,
    ChoiceMessage,
    DeltaContent,
    LLMChunk,
    LLMRequest,
    LLMResponse,
    Usage,
)
from me4brain.llm.provider_registry import ProviderType

logger = structlog.get_logger(__name__)


class DynamicLLMClient(LLMProvider):
    """Client generico per qualsiasi provider LLM dinamico.

    Supporta:
    - OpenAI-compatible API (default)
    - Anthropic API
    - Custom endpoints
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        api_key_header: str = "Authorization",
        provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE,
        default_model: str = "default",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header
        self.provider_type = provider_type
        self.default_model = default_model

        headers = {"Content-Type": "application/json"}
        if api_key:
            if api_key_header == "Authorization":
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                headers[api_key_header] = api_key

        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/",
            timeout=httpx.Timeout(timeout, connect=30.0),
            headers=headers,
        )

        logger.info(
            "dynamic_client_initialized",
            base_url=self.base_url,
            provider_type=provider_type.value,
        )

    def _prepare_payload(self, request: LLMRequest) -> dict[str, Any]:
        """Prepara il payload in base al tipo di provider."""
        if self.provider_type == ProviderType.ANTHROPIC:
            return self._prepare_anthropic_payload(request)
        return self._prepare_openai_payload(request)

    def _prepare_openai_payload(self, request: LLMRequest) -> dict[str, Any]:
        """Prepara payload per API OpenAI-compatible."""
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature if request.temperature is not None else 0.3,
            "stream": request.stream,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        if request.tools:
            payload["tools"] = [t.model_dump(exclude_none=True) for t in request.tools]
            payload["tool_choice"] = request.tool_choice
            if request.parallel_tool_calls is not None:
                payload["parallel_tool_calls"] = request.parallel_tool_calls

        if request.response_format:
            payload["response_format"] = request.response_format

        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        if request.reasoning_exclude:
            payload["reasoning"] = {"exclude": True}
        elif request.reasoning_effort != "medium":
            payload["reasoning_effort"] = request.reasoning_effort

        return payload

    def _prepare_anthropic_payload(self, request: LLMRequest) -> dict[str, Any]:
        """Prepara payload per API Anthropic."""
        system_msg = ""
        messages = []

        for m in request.messages:
            if m.role == "system":
                system_msg = m.content or ""
            else:
                msg_content = m.content
                if m.tool_call_id and m.tool_calls:
                    msg_content = [
                        {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                    ]
                elif m.role == "assistant" and m.tool_calls:
                    msg_content = [{"type": "text", "text": m.content or ""}]
                    for tc in m.tool_calls:
                        msg_content.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id", str(uuid.uuid4())),
                                "name": tc.get("function", {}).get("name", ""),
                                "input": json.loads(tc.get("function", {}).get("arguments", "{}")),
                            }
                        )
                messages.append({"role": m.role, "content": msg_content})

        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
        }

        if system_msg:
            payload["system"] = system_msg

        if request.tools:
            payload["tools"] = [
                {
                    "name": t.function.name,
                    "description": t.function.description or "",
                    "input_schema": t.function.parameters or {"type": "object"},
                }
                for t in request.tools
            ]

        return payload

    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Genera una risposta non-streaming."""
        request.stream = False
        payload = self._prepare_payload(request)

        logger.debug(
            "dynamic_client_request", model=payload.get("model"), provider=self.provider_type.value
        )

        if self.provider_type == ProviderType.ANTHROPIC:
            endpoint = "messages"
        else:
            endpoint = "chat/completions"

        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            if self.provider_type == ProviderType.ANTHROPIC:
                return self._parse_anthropic_response(data, request)
            return self._parse_openai_response(data, request)

        except httpx.HTTPStatusError as e:
            logger.error(
                "dynamic_client_http_error",
                status=e.response.status_code,
                text=e.response.text[:500],
            )
            raise
        except Exception as e:
            logger.error("dynamic_client_error", error=str(e))
            raise

    def _parse_openai_response(self, data: dict, request: LLMRequest) -> LLMResponse:
        """Parse risposta OpenAI-compatible."""
        choices = []
        for c in data.get("choices", []):
            msg = c.get("message", {})

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                parsed_tool_calls = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    parsed_tool_calls.append(
                        {
                            "id": tc.get("id", str(uuid.uuid4())),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": args,
                            },
                        }
                    )
                tool_calls = parsed_tool_calls

            # Extract content and reasoning
            # For models with thinking (qwen3.5), content may be empty but reasoning has the actual thought
            content = msg.get("content")
            reasoning = msg.get("reasoning") or msg.get("reasoning_content")

            # If content is empty but reasoning exists, use reasoning as content (for thinking models)
            if (content is None or content == "") and reasoning:
                logger.debug(
                    "dynamic_client_using_reasoning_as_content",
                    content_len=len(content) if content else 0,
                    reasoning_len=len(reasoning),
                )
                content = reasoning
                reasoning = None  # Avoid duplication

            choices.append(
                Choice(
                    index=c.get("index", 0),
                    message=ChoiceMessage(
                        role=msg.get("role", "assistant"),
                        content=content,
                        reasoning=reasoning,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=c.get("finish_reason"),
                )
            )

        usage_data = data.get("usage", {})
        return LLMResponse(
            id=data.get("id", str(uuid.uuid4())),
            model=data.get("model", request.model or self.default_model),
            created=datetime.fromtimestamp(data.get("created", 0))
            if data.get("created")
            else datetime.utcnow(),
            choices=choices,
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            if usage_data
            else None,
        )

    def _parse_anthropic_response(self, data: dict, request: LLMRequest) -> LLMResponse:
        """Parse risposta Anthropic."""
        content_blocks = data.get("content", [])
        text_content = ""
        tool_calls = None

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    {
                        "id": block.get("id", str(uuid.uuid4())),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        usage_data = data.get("usage", {})
        return LLMResponse(
            id=data.get("id", str(uuid.uuid4())),
            model=data.get("model", request.model or self.default_model),
            created=datetime.utcnow(),
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(
                        role="assistant",
                        content=text_content,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=data.get("stop_reason"),
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            )
            if usage_data
            else None,
        )

    async def stream_response(self, request: LLMRequest) -> AsyncGenerator[LLMChunk, None]:
        """Genera una risposta streaming."""
        request.stream = True
        payload = self._prepare_payload(request)

        if self.provider_type == ProviderType.ANTHROPIC:
            endpoint = "messages"
        else:
            endpoint = "chat/completions"

        logger.debug("dynamic_client_stream_start", model=payload.get("model"))

        try:
            async with self._client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue

                    for c in choices:
                        delta = c.get("delta", {})
                        content = delta.get("content")
                        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                        tool_calls = delta.get("tool_calls")

                        if content is None and reasoning is None and not tool_calls:
                            continue

                        yield LLMChunk(
                            id=chunk_data.get("id", str(uuid.uuid4())),
                            model=chunk_data.get("model", request.model or self.default_model),
                            choices=[
                                ChoiceDelta(
                                    index=c.get("index", 0),
                                    delta=DeltaContent(
                                        content=content,
                                        reasoning=reasoning,
                                        tool_calls=tool_calls,
                                    ),
                                    finish_reason=c.get("finish_reason"),
                                )
                            ],
                        )

        except httpx.HTTPStatusError as e:
            logger.error("dynamic_client_stream_http_error", status=e.response.status_code)
            raise
        except Exception as e:
            logger.error("dynamic_client_stream_error", error=str(e))
            raise

    async def generate_embeddings(
        self, text: str | list[str], model: str = "default"
    ) -> list[list[float]]:
        """Genera embeddings - non supportato per provider dinamici."""
        raise NotImplementedError(
            "Embeddings not supported for dynamic providers. Use local BGE-M3 instead."
        )


def get_client_for_provider(provider_id: str, model_id: str | None = None) -> DynamicLLMClient:
    """Factory per ottenere un client per un provider specifico."""
    from me4brain.llm.provider_registry import get_provider_registry

    registry = get_provider_registry()
    provider = registry.get(provider_id)

    if not provider:
        raise ValueError(f"Provider not found: {provider_id}")

    return DynamicLLMClient(
        base_url=provider.base_url,
        api_key=provider.api_key,
        api_key_header=provider.api_key_header,
        provider_type=provider.type,
        default_model=model_id or (provider.models[0].id if provider.models else "default"),
    )
