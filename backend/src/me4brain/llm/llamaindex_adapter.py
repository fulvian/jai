"""LlamaIndex LLM Adapter - Bridge tra NanoGPT e LlamaIndex.

Permette di usare i modelli NanoGPT (Mistral, Kimi, etc.) con LlamaIndex
per funzionalità come reranking.
"""

from __future__ import annotations

from typing import Any, Sequence

import structlog
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms import CustomLLM
from llama_index.core.llms.callbacks import llm_completion_callback

from me4brain.llm.base import LLMProvider
from me4brain.llm.models import LLMRequest

logger = structlog.get_logger(__name__)


class NanoGPTLlamaIndexAdapter(CustomLLM):
    """Adapter to use Me4BrAIn LLM client with LlamaIndex.

    Wraps the configured LLM client (NanoGPT or Ollama) to provide 
    LlamaIndex-compatible LLM interface for use with rerankers.
    """

    model_name: str = "qwen3.5-4b-mlx"
    context_window: int = 32768
    max_tokens: int = 4096

    _client: LLMProvider | None = None

    def __init__(
        self,
        model_name: str = "qwen3.5-4b-mlx",
        **kwargs: Any,
    ) -> None:
        """Initialize adapter with model name.

        Args:
            model_name: Model identifier
        """
        super().__init__(model_name=model_name, **kwargs)
        self._client = None  # Lazy initialization

    def _get_client(self) -> LLMProvider:
        """Get or create LLM client."""
        if self._client is None:
            from me4brain.llm.provider_factory import get_tool_calling_client

            self._client = get_tool_calling_client()
        return self._client

    async def _get_fresh_client(self) -> LLMProvider:
        """Create a FRESH client (not singleton) for thread-safe sync calls."""
        from me4brain.llm.config import get_llm_config
        from me4brain.llm.nanogpt import NanoGPTClient
        from me4brain.llm.ollama import OllamaClient

        config = get_llm_config()
        if config.use_local_tool_calling:
            return OllamaClient(base_url=config.ollama_base_url, model=config.ollama_model)
        return NanoGPTClient(
            api_key=config.nanogpt_api_key, base_url=config.nanogpt_base_url
        )

    @property
    def metadata(self) -> LLMMetadata:
        """Return LLM metadata."""
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.max_tokens,
            model_name=self.model_name,
            is_chat_model=True,
        )

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Complete a prompt synchronously.

        FIX Issue #3: Uses a dedicated thread with its own event loop
        and a FRESH NanoGPT client to avoid 'Event loop is closed' errors.
        The shared self._client's HTTP session is bound to the main loop
        and cannot be reused in a thread's temporary loop.
        """
        import asyncio
        import concurrent.futures

        model = self.model_name
        max_tok = self.max_tokens

        async def _complete():
            # Create a FRESH client — do NOT reuse singleton here
            # because its httpx session is bound to the main event loop
            client = await self._get_fresh_client()
            try:
                request = LLMRequest(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    max_tokens=max_tok,
                    temperature=0.1,
                )
                response = await client.generate_response(request)
                return response.content
            finally:
                # Ensure the client's HTTP session is closed in this loop
                if hasattr(client, "_client") and client._client:
                    await client._client.aclose()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            text = pool.submit(asyncio.run, _complete()).result(timeout=300)

        return CompletionResponse(text=text)

    @llm_completion_callback()
    async def acomplete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """Complete a prompt asynchronously."""
        client = self._get_client()
        request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=0.1,
        )
        response = await client.generate_response(request)
        return CompletionResponse(text=response.content)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Chat completion synchronously.

        FIX Issue #3: Uses a dedicated thread with its own event loop
        and a FRESH NanoGPT client to avoid 'Event loop is closed' errors.
        """
        import asyncio
        import concurrent.futures

        model = self.model_name
        max_tok = self.max_tokens

        # Convert messages before entering the thread
        nano_messages = []
        for msg in messages:
            role = "user"
            if msg.role == MessageRole.SYSTEM:
                role = "system"
            elif msg.role == MessageRole.ASSISTANT:
                role = "assistant"
            nano_messages.append({"role": role, "content": msg.content})

        async def _chat():
            client = await self._get_fresh_client()
            try:
                request = LLMRequest(
                    messages=nano_messages,
                    model=model,
                    max_tokens=max_tok,
                    temperature=0.1,
                )
                response = await client.generate_response(request)
                return ChatResponse(
                    message=ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=response.content,
                    ),
                )
            finally:
                if hasattr(client, "_client") and client._client:
                    await client._client.aclose()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            return pool.submit(asyncio.run, _chat()).result(timeout=300)

    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Chat completion asynchronously."""
        client = self._get_client()

        # Convert LlamaIndex messages to NanoGPT format
        nano_messages = []
        for msg in messages:
            role = "user"
            if msg.role == MessageRole.SYSTEM:
                role = "system"
            elif msg.role == MessageRole.ASSISTANT:
                role = "assistant"
            elif msg.role == MessageRole.USER:
                role = "user"

            nano_messages.append({"role": role, "content": msg.content})

        request = LLMRequest(
            messages=nano_messages,
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=0.1,
        )

        response = await client.generate_response(request)

        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response.content,
            ),
        )

    def stream_complete(self, prompt: str, **kwargs: Any):
        """Stream completion (not implemented, falls back to complete)."""
        raise NotImplementedError("Streaming not supported for reranking")

    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        """Stream chat (not implemented)."""
        raise NotImplementedError("Streaming not supported for reranking")


# Cache adapters by model name
_llm_cache: dict[str, NanoGPTLlamaIndexAdapter] = {}


def get_llamaindex_llm(model_name: str | None = None) -> NanoGPTLlamaIndexAdapter:
    """Get LlamaIndex-compatible LLM adapter.

    Args:
        model_name: Optional model name, defaults to Mistral Large 3

    Returns:
        NanoGPTLlamaIndexAdapter instance (cached)
    """
    model = model_name or "qwen3.5-4b-mlx"

    if model not in _llm_cache:
        _llm_cache[model] = NanoGPTLlamaIndexAdapter(model_name=model)
        logger.info("llamaindex_llm_adapter_created", model=model)

    return _llm_cache[model]
