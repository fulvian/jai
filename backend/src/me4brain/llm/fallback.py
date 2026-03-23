"""Fallback Provider - Wrapper per gestire il failover tra provider.

Se il provider primario (locale) fallisce o restituisce una risposta invalida
(es. no tool calls quando attese), riprova con il provider di fallback (cloud).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog

from me4brain.llm.base import LLMProvider
from me4brain.llm.models import LLMChunk, LLMRequest, LLMResponse

logger = structlog.get_logger(__name__)


class FallbackProvider(LLMProvider):
    """Wrapper che implementa la logica di fallback tra due provider."""

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        name: str = "default",
        fallback_model: str | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = name
        self.fallback_model = fallback_model

    def _get_fallback_request(self, request: LLMRequest) -> LLMRequest:
        """Crea una copia della request con il modello di fallback corretto."""
        if self.fallback_model is None:
            # Se non è specificato un modello di fallback, usa il modello dalla config
            from me4brain.llm.config import get_llm_config

            config = get_llm_config()
            fallback_model = config.model_fallback
        else:
            fallback_model = self.fallback_model

        # Usa model_copy per creare una copia shallow e aggiorna solo il modello
        return request.model_copy(update={"model": fallback_model})

    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self.primary.generate_response(request)

            # Validazione euristica: se ci sono tools nella richiesta ma non nella risposta,
            # e non c'è contenuto testuale significativo, potrebbe essere un fail del locale.
            if request.tools and not response.choices[0].message.tool_calls:
                # Se il modello non ha risposto nulla o ha dato una risposta troppo corta
                content = response.choices[0].message.content or ""
                if len(content.strip()) < 10:
                    logger.warning(
                        "fallback_triggered_empty_response",
                        provider_name=self.name,
                        content_len=len(content),
                    )
                    fallback_request = self._get_fallback_request(request)
                    return await self.fallback.generate_response(fallback_request)

            return response
        except Exception as e:
            logger.warning("fallback_triggered_on_error", provider_name=self.name, error=str(e))
            fallback_request = self._get_fallback_request(request)
            return await self.fallback.generate_response(fallback_request)

    async def stream_response(self, request: LLMRequest) -> AsyncGenerator[LLMChunk, None]:
        # Lo streaming è più complesso da gestire col fallback a metà.
        # Per ora, se il primario fallisce all'inizio, usiamo il fallback.
        try:
            async for chunk in self.primary.stream_response(request):
                yield chunk
        except Exception as e:
            logger.warning("stream_fallback_triggered", provider_name=self.name, error=str(e))
            fallback_request = self._get_fallback_request(request)
            async for chunk in self.fallback.stream_response(fallback_request):
                yield chunk

    async def generate_embeddings(self, text: str | list[str]) -> list[list[float]]:
        return await self.primary.generate_embeddings(text)
