"""Base LLM Provider Abstract Class."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from me4brain.llm.models import LLMChunk, LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Interfaccia base per i provider LLM."""

    @abstractmethod
    async def generate_response(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """Genera una risposta non-streaming.

        Args:
            request: La richiesta LLM con messaggi e parametri

        Returns:
            LLMResponse con il contenuto generato
        """
        ...

    @abstractmethod
    async def stream_response(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[LLMChunk, None]:
        """Genera una risposta streaming."""
        ...

    @abstractmethod
    async def generate_embeddings(
        self,
        text: str | list[str],
        model: str = "local/bge-m3",
    ) -> list[list[float]]:
        """Genera embeddings per il testo fornito."""
        ...
