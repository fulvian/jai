"""Ollama / mlx_lm.server LLM Provider.

Client OpenAI-compatible per modelli locali (Qwen 3.5-4B-MLX via mlx_lm.server).
Supporta tool calling, streaming, e non-streaming.

IMPORTANT: mlx_lm.server accetta solo il path assoluto del modello come model ID.
Il model name alias (es. "qwen3.5-4b-mlx") non è valido → 404 Not Found.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx
import structlog

from me4brain.llm.base import LLMProvider
from me4brain.llm.models import (
    LLMChunk,
    LLMRequest,
    LLMResponse,
    Message,
    Usage,
    Choice,
    ChoiceMessage,
    ChoiceDelta,
    DeltaContent,
)

logger = structlog.get_logger(__name__)


class OllamaClient(LLMProvider):
    """Client per mlx_lm.server (o Ollama) via API OpenAI-compatible.

    Ottimizzato per Qwen 3.5-4B-MLX su Apple Silicon con mlx_lm.server.

    NOTE su httpx base_url:
    - httpx richiede SEMPRE il trailing slash per concatenare correttamente path relativi.
    - Esempio: base_url="http://localhost:1234/v1/" + "chat/completions" → corretto
    - Esempio: base_url="http://localhost:1234/v1" + "chat/completions" → droppa /v1 → 404
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        """Inizializza il client.

        Args:
            base_url: URL endpoint OpenAI-compatible (es. http://localhost:1234/v1)
            model: Model ID. Se None, carica OLLAMA_MODEL dal .env.
            timeout: Timeout per le risposte (inferenza locale può essere lenta, tool-calling 120s+ typical).
        """
        if model is None:
            from me4brain.llm.config import get_llm_config

            model = get_llm_config().ollama_model
        # CRITICAL FIX: httpx richiede trailing slash sul base_url
        # senza di esso /v1 viene droppato e l'URL diventa http://localhost:1234/chat/completions → 404
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.default_model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=30.0),
            headers={"Content-Type": "application/json"},
        )
        logger.info(
            "ollama_client_initialized",
            base_url=self.base_url,
            model=self.default_model,
        )

    def _prepare_payload(self, request: LLMRequest) -> dict[str, Any]:
        """Prepara il payload JSON ottimizzato per Qwen 3.5-4B-MLX su mlx_lm.server."""
        # mlx_lm.server richiede il path assoluto del modello, non alias
        model = request.model or self.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature if request.temperature is not None else 0.3,
            "stream": request.stream,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        # Parametri ottimali per Qwen 3.5-4B-MLX (mlx_lm.server SOTA 2026)
        payload["top_p"] = request.top_p if request.top_p is not None else 0.9
        payload["repetition_penalty"] = 1.05
        payload["frequency_penalty"] = 0.0
        payload["presence_penalty"] = 0.0

        if request.stop:
            payload["stop"] = request.stop
        if request.response_format:
            payload["response_format"] = request.response_format

        # Tool calling (supportato nativamente da mlx_lm.server)
        if request.tools:
            payload["tools"] = [t.model_dump(exclude_none=True) for t in request.tools]
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice

        return payload

    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Invia una richiesta NON-streaming a mlx_lm.server."""
        request.stream = False  # Forza non-streaming per questa method
        payload = self._prepare_payload(request)

        logger.debug(
            "ollama_request_sent",
            model=payload["model"],
            base_url=self.base_url,
            messages_count=len(request.messages),
            tools_count=len(request.tools) if request.tools else 0,
        )

        try:
            response = await self._client.post("chat/completions", json=payload)
            logger.debug(
                "ollama_response_received",
                status=response.status_code,
                url=str(response.url),
            )
            response.raise_for_status()
            data = response.json()

            # 🎯 Phase 5: Comprehensive Logging - Raw LLM response
            logger.debug("ollama_raw_response_data", data=data)

            # Valida la risposta per evitare "empty text or tool calls" errors
            if not data.get("choices") or len(data["choices"]) == 0:
                logger.warning("ollama_empty_choices", data=data)
                raise ValueError("Ollama returned empty choices")

            choices = []
            for c in data.get("choices", []):
                msg_data = c.get("message", {})

                # Validation: scelta deve avere content o tool_calls o reasoning
                content = msg_data.get("content") or ""
                reasoning = msg_data.get("reasoning")
                tool_calls = msg_data.get("tool_calls")

                if not content and not tool_calls and not reasoning:
                    logger.warning("ollama_invalid_choice_message", message=msg_data)

                choice = Choice(
                    index=c.get("index", 0),
                    message=ChoiceMessage(
                        role=msg_data.get("role", "assistant"),
                        content=content,
                        reasoning=reasoning,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=c.get("finish_reason"),
                )
                choices.append(choice)

            usage_data = data.get("usage", {})
            return LLMResponse(
                id=data.get("id", "mlx-id"),
                model=data.get("model", payload["model"]),
                choices=choices,
                usage=Usage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                ),
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "ollama_http_error",
                status=e.response.status_code,
                text=e.response.text[:500],
                url=str(e.request.url),
            )
            raise
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.error("ollama_parse_error", error=str(e), data=locals().get("data"))
            raise
        except Exception as e:
            logger.error("ollama_error", error=str(e), error_type=type(e).__name__)
            raise

    async def stream_response(self, request: LLMRequest) -> AsyncGenerator[LLMChunk, None]:
        """Invia una richiesta streaming a mlx_lm.server."""
        request.stream = True
        payload = self._prepare_payload(request)

        logger.debug(
            "ollama_stream_request_sent",
            model=payload["model"],
            base_url=self.base_url,
            messages_count=len(request.messages),
        )

        try:
            async with self._client.stream("POST", "chat/completions", json=payload) as response:
                logger.debug(
                    "ollama_stream_response_received",
                    status=response.status_code,
                    url=str(response.url),
                )
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    # 🎯 Phase 5: Comprehensive Logging - Raw stream chunk
                    # logger.trace("ollama_raw_stream_chunk", data=data_str)

                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning("ollama_stream_json_decode_error", data=data_str[:100])
                        continue

                    try:
                        choices = chunk_data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        reasoning = delta.get("reasoning")

                        # Se abbiamo content o tool_calls o reasoning, yieldiamo il chunk
                        if content is None and reasoning is None and not delta.get("tool_calls"):
                            continue

                        yield LLMChunk(
                            id=chunk_data.get("id", "mlx-stream-id"),
                            model=chunk_data.get("model", payload["model"]),
                            choices=[
                                ChoiceDelta(
                                    index=0,
                                    delta=DeltaContent(
                                        content=content,
                                        reasoning=reasoning,
                                        tool_calls=delta.get("tool_calls"),
                                    ),
                                    finish_reason=choices[0].get("finish_reason"),
                                )
                            ],
                        )
                    except json.JSONDecodeError:
                        continue

        except httpx.HTTPStatusError as e:
            logger.error(
                "ollama_stream_http_error",
                status=e.response.status_code,
                text=e.response.text[:500],
                url=str(e.request.url),
            )
            raise
        except Exception as e:
            logger.error("ollama_stream_error", error=str(e), error_type=type(e).__name__)
            raise

    async def generate_embeddings(
        self,
        text: str | list[str],
        model: str = "local/bge-m3",
    ) -> list[list[float]]:
        """Genera embeddings (non implementato — Me4BrAIn usa BGE-M3 direttamente)."""
        raise NotImplementedError("Embeddings via Ollama non implementati.")


# =============================================================================
# Singleton — si invalida automaticamente quando la config cambia
# =============================================================================

_ollama_client: Optional[OllamaClient] = None
_ollama_client_config_hash: Optional[str] = None


def get_ollama_client() -> OllamaClient:
    """Restituisce l'istanza singleton del client per mlx_lm.server.

    Il singleton si ricostruisce automaticamente se la configurazione cambia
    (in fase di sviluppo, dopo modifiche a .env e restart).
    """
    global _ollama_client, _ollama_client_config_hash

    from me4brain.llm.config import get_llm_config

    config = get_llm_config()
    config_hash = f"{config.ollama_base_url}|{config.ollama_model}"

    if _ollama_client is None or _ollama_client_config_hash != config_hash:
        logger.info(
            "ollama_client_created",
            base_url=config.ollama_base_url,
            model=config.ollama_model,
        )
        _ollama_client = OllamaClient(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
        )
        _ollama_client_config_hash = config_hash

    return _ollama_client
