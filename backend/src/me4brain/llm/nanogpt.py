"""NanoGPT LLM Client Implementation."""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from me4brain.llm.base import LLMProvider
from me4brain.llm.config import LLMConfig, get_llm_config
from me4brain.llm.models import (
    Choice,
    ChoiceDelta,
    ChoiceMessage,
    DeltaContent,
    LLMChunk,
    LLMRequest,
    LLMResponse,
    ToolCall,
    ToolCallFunction,
)

logger = structlog.get_logger(__name__)


class LMStudioAutoLoader:
    """Handles automatic model loading for LM Studio.

    LM Studio requires models to be explicitly loaded before making inference requests.
    This class provides auto-loading functionality to ensure models are available.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/").replace("/v1", "")  # Remove /v1 suffix
        self._loaded_model: str | None = None
        self._lock = asyncio.Lock()

    def _get_api_base_url(self) -> str:
        """Get the API base URL (without /v1)."""
        return self.base_url

    async def is_model_loaded(self, model_identifier: str) -> bool:
        """Check if a specific model is currently loaded in LM Studio.

        Args:
            model_identifier: The model identifier (e.g., 'mlx/qwen3.5:9b')

        Returns:
            True if the model is loaded, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._get_api_base_url()}/api/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    # LM Studio returns {"data": [{"id": "model-identifier", ...}]}
                    loaded_models = data.get("data", [])
                    for loaded in loaded_models:
                        loaded_id = loaded.get("id", "")
                        # Check if the requested model identifier is in the loaded model ID
                        # Also handle case where model_identifier might be 'qwen3.5' and loaded is 'qwen3.5-9b-instruct'
                        if model_identifier.lower() in loaded_id.lower():
                            return True
                        # Also check if the loaded ID is in the model_identifier (reverse check)
                        if loaded_id.lower() in model_identifier.lower():
                            self._loaded_model = loaded_id
                            return True
                    return False
                return False
        except Exception as e:
            logger.warning("lmstudio_check_loaded_error", error=str(e))
            return False

    async def load_model(self, model_identifier: str) -> bool:
        """Load a model in LM Studio.

        Args:
            model_identifier: The model to load (e.g., 'mlx-community/qwen3.5-9b-instruct-4bit')

        Returns:
            True if model was loaded successfully, False otherwise.
        """
        async with self._lock:
            # Double-check after acquiring lock
            if await self.is_model_loaded(model_identifier):
                return True

            try:
                # Try to get list of available models to find a match
                available_model = await self._find_available_model(model_identifier)
                if not available_model:
                    logger.error("lmstudio_model_not_found", model=model_identifier)
                    return False

                logger.info("lmstudio_loading_model", model=available_model)
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{self._get_api_base_url()}/api/v1/models/load",
                        json={"model": available_model},
                    )
                    if response.status_code == 200:
                        self._loaded_model = available_model
                        logger.info("lmstudio_model_loaded", model=available_model)
                        return True
                    else:
                        logger.error(
                            "lmstudio_load_failed",
                            status=response.status_code,
                            response=response.text,
                        )
                        return False
            except Exception as e:
                logger.error("lmstudio_load_error", error=str(e))
                return False

    async def _find_available_model(self, model_identifier: str) -> str | None:
        """Find the best matching available model for the given identifier.

        Args:
            model_identifier: The model identifier from config

        Returns:
            The model identifier to use for loading, or None if not found.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First try the direct model
                response = await client.get(f"{self._get_api_base_url()}/api/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    available = data.get("data", [])

                    # First, try exact/close match
                    for model in available:
                        model_id = model.get("id", "")
                        if model_identifier.lower() in model_id.lower():
                            return model_id

                    # If not found, look for MLX models when identifier contains 'mlx' or ':'
                    # Common pattern: config has 'mlx/qwen3.5:9b' but LM Studio has 'mlx-community/...'
                    if "mlx" in model_identifier.lower() or ":" in model_identifier:
                        for model in available:
                            model_id = model.get("id", "")
                            # Look for mlx-community models
                            if "mlx" in model_id.lower():
                                logger.info("lmstudio_found_mlx_model", model=model_id)
                                return model_id

                    # Return first available model as fallback
                    if available:
                        fallback = available[0].get("id")
                        logger.warning("lmstudio_using_fallback_model", model=fallback)
                        return fallback

                return None
        except Exception as e:
            logger.error("lmstudio_list_models_error", error=str(e))
            return None

    async def ensure_model_loaded(self, model_identifier: str) -> bool:
        """Ensure the model is loaded, loading it if necessary.

        Args:
            model_identifier: The model identifier to ensure is loaded

        Returns:
            True if model is loaded (or was loaded), False otherwise.
        """
        # Check if already loaded
        if await self.is_model_loaded(model_identifier):
            logger.debug("lmstudio_model_already_loaded", model=model_identifier)
            return True

        # Load the model
        return await self.load_model(model_identifier)


# Global auto-loader instance
_lmstudio_auto_loader: LMStudioAutoLoader | None = None


def get_lmstudio_auto_loader() -> LMStudioAutoLoader:
    """Get or create the LM Studio auto-loader instance."""
    global _lmstudio_auto_loader
    if _lmstudio_auto_loader is None:
        config = get_llm_config()
        _lmstudio_auto_loader = LMStudioAutoLoader(config.lmstudio_base_url)
    return _lmstudio_auto_loader


def get_llm_client() -> "NanoGPTClient":
    """Factory per ottenere l'istanza del client.

    Quando llm_local_only=True, ritorna Ollama client (via NanoGPTClient
    con routing to Ollama) per us locale.
    """
    config = get_llm_config()
    if config.llm_local_only:
        # Usa Ollama come backend locale - NanoGPTClient fa il routing
        # automatico per modelli con ":" nella URL di Ollama
        return NanoGPTClient(
            api_key=config.nanogpt_api_key or "dummy",
            base_url=config.ollama_base_url,  # Ollama base URL
        )
    return NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )


class NanoGPTClient(LLMProvider):
    """Client per interagire con le API NanoGPT."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._config_cache: LLMConfig | None = None
        # Track if user explicitly provided a non-default base_url
        # If so, we should always respect it instead of auto-detecting
        cfg = get_llm_config()
        self._user_provided_base_url = self.base_url != cfg.nanogpt_base_url.rstrip("/")
        # qwen3.5 thinking models can take 150+ seconds per request
        # Increased timeouts to accommodate slow local LLM responses
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,  # Connection timeout (was 10s)
                read=1800.0,  # Read timeout 30min (was 600s) - accommodates thinking models
                write=120.0,  # Write timeout 2min (was 60s)
                pool=30.0,  # Pool timeout (was 10s)
            ),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _get_config(self) -> LLMConfig:
        if self._config_cache is None:
            self._config_cache = get_llm_config()
        return self._config_cache

    def _get_base_url_for_model(self, model: str) -> str:
        """Determine base URL for a model.

        Best practice: If user explicitly provided a base_url (non-default),
        always respect it. Only auto-detect when using default nanogpt_base_url.

        This allows users to pass base_url="http://localhost:11434/v1" with
        model="mlx/qwen3.5:9b" and have it work correctly via Ollama's
        MLX backend, instead of being incorrectly routed to LM Studio.
        """
        # If user explicitly provided a base_url, always use it
        if self._user_provided_base_url:
            return self.base_url

        # Only auto-detect when using default nanogpt_base_url
        model_lower = model.lower()
        cfg = get_llm_config()
        is_default_cloud_client = self.base_url.rstrip("/") == cfg.nanogpt_base_url.rstrip("/")
        if (
            "lmstudio" in model_lower
            or model_lower.startswith("mlx/")
            or (
                (model_lower.startswith("mlx-") or model_lower.endswith("-mlx"))
                and cfg.use_local_tool_calling
                and is_default_cloud_client
            )
        ):
            return cfg.lmstudio_base_url.rstrip("/")
        if ":" in model:
            return cfg.ollama_base_url.rstrip("/")
        return self.base_url

    def _normalize_model_for_provider(self, model: str, base_url: str) -> str:
        """Normalize model name based on the provider.

        Some providers don't understand certain prefixes. For example:
        - Ollama doesn't understand 'mlx/' prefix - it expects 'qwen3.5:9b'
        - LM Studio understands 'mlx/' format

        Best practice: strip provider-specific prefixes when calling the API.
        """
        cfg = get_llm_config()
        ollama_base = cfg.ollama_base_url.rstrip("/")
        lmstudio_base = cfg.lmstudio_base_url.rstrip("/")

        # Strip mlx/ prefix when using Ollama since it doesn't understand it
        if base_url == ollama_base and model.startswith("mlx/"):
            return model[4:]  # Remove 'mlx/' prefix

        return model

    def _prepare_payload(self, request: LLMRequest) -> dict[str, Any]:
        """Prepara il payload JSON per la richiesta."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }

        # Handling reasoning effort / exclude
        if request.reasoning_exclude:
            payload["reasoning"] = {"exclude": True}
        elif request.reasoning_effort != "medium":  # medium è default
            # Se il modello supporta reasoning_effort nativo
            payload["reasoning_effort"] = request.reasoning_effort

        # Tool calling parameters
        if request.tools:
            payload["tools"] = [t.model_dump(exclude_none=True) for t in request.tools]
            payload["tool_choice"] = request.tool_choice
            payload["parallel_tool_calls"] = request.parallel_tool_calls

        # Structured Output (JSON Schema)
        if request.response_format:
            payload["response_format"] = request.response_format

        # Altri parametri opzionali
        if request.top_p:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        return payload

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Esegue una chiamata POST non-streaming."""
        request.stream = False  # Forza stream=False per sicurezza
        payload = self._prepare_payload(request)

        # DEBUG: Log payload size
        import json

        payload_json = json.dumps(payload)
        tools_count = len(payload.get("tools", []))
        logger.info(
            "llm_request_debug",
            model=request.model,
            payload_size_kb=len(payload_json) / 1024,
            tools_count=tools_count,
        )
        # DEBUG: Log first tool name to diagnose issue
        if payload.get("tools"):
            first_tool = payload["tools"][0]
            logger.info(
                "llm_payload_first_tool_debug",
                first_tool_keys=list(first_tool.keys())
                if isinstance(first_tool, dict)
                else "NOT_DICT",
                first_tool_function_name=first_tool.get("function", {}).get("name", "MISSING")
                if isinstance(first_tool, dict)
                else "N/A",
            )
        logger.debug("llm_request", model=request.model, stream=False)

        base_url = self._get_base_url_for_model(request.model)

        # Normalize model name based on provider (e.g., strip 'mlx/' for Ollama)
        effective_model = self._normalize_model_for_provider(request.model, base_url)
        if effective_model != request.model:
            logger.debug(
                "model_name_normalized",
                original=request.model,
                normalized=effective_model,
                provider_base_url=base_url,
            )
            payload["model"] = effective_model

        # Auto-load model if going to LM Studio and model is not loaded
        if base_url == get_llm_config().lmstudio_base_url.rstrip("/"):
            auto_loader = get_lmstudio_auto_loader()
            # Use normalized model name for LM Studio as well
            model_loaded = await auto_loader.ensure_model_loaded(effective_model)
            if not model_loaded:
                logger.error("lmstudio_auto_load_failed", model=request.model)
                logger.warning(
                    "lmstudio_auto_load_continue_without_block",
                    model=request.model,
                )

        try:
            response = await self.client.post(f"{base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            # Parsing della risposta standard OpenAI-compatible
            choices = []
            for c in data.get("choices", []):
                msg_data = c.get("message", {})

                # Estrazione tool calls se presenti
                tool_calls_data = msg_data.get("tool_calls")
                tool_calls = None
                if tool_calls_data:
                    tool_calls = []
                    for tc in tool_calls_data:
                        # Filter out malformed tool calls with empty function name
                        # NanoGPT/Mistral sometimes generates phantom tool calls with empty name
                        tool_name = tc.get("function", {}).get("name", "")
                        if not tool_name:
                            logger.warning(
                                "nanogpt_empty_tool_name_skipped",
                                tc_id=tc.get("id"),
                            )
                            continue

                        raw_args = tc["function"].get("arguments", "{}")
                        logger.debug(
                            "nanogpt_raw_tool_arguments",
                            tool=tool_name,
                            raw_args=raw_args,
                            type=type(raw_args).__name__,
                        )
                        # Se è già un dict (alcuni provider NanoGPT lo fanno), serializza in JSON
                        if isinstance(raw_args, dict):
                            args_str = json.dumps(raw_args)
                        else:
                            args_str = str(raw_args)

                        tool_calls.append(
                            ToolCall(
                                id=tc.get("id", str(uuid4())),
                                type=tc.get("type", "function"),
                                function=ToolCallFunction(
                                    name=tool_name,
                                    arguments=args_str,
                                ),
                            )
                        )

                # Estrazione reasoning (NanoGPT specific)
                # Può essere in: message.reasoning, message.reasoning_content
                reasoning = msg_data.get("reasoning") or msg_data.get("reasoning_content")

                # Per modelli :thinking (es. qwen3.5), content può essere empty string ""
                # o null - in tal caso usiamo reasoning come fallback per ottenere
                # il contenuto effettivo
                content = msg_data.get("content")
                if (content is None or content == "") and reasoning:
                    logger.debug(
                        "nanogpt_using_reasoning_as_content",
                        content_len=len(content) if content else 0,
                        reasoning_len=len(reasoning),
                    )
                    content = reasoning
                    reasoning = None  # Evita duplicazione

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

            return LLMResponse(
                id=data.get("id") or str(uuid4()),
                created=datetime.fromtimestamp(data.get("created", 0)),
                model=data.get("model", request.model),
                choices=choices,
                request_id=request.request_id,
            )

        except httpx.HTTPStatusError as e:
            logger.error("nanogpt_api_error", status=e.response.status_code, text=e.response.text)
            # DEBUG: Save payload to file for analysis when 503
            if e.response.status_code == 503:
                import pathlib

                debug_path = pathlib.Path("/tmp/nanogpt_failed_payload.json")
                debug_path.write_text(payload_json)
                logger.error(
                    "nanogpt_503_debug",
                    payload_saved_to=str(debug_path),
                    payload_size_kb=len(payload_json) / 1024,
                )
            raise
        except Exception as e:
            logger.error("nanogpt_request_failed", error=str(e))
            raise

    async def generate_embeddings(
        self,
        text: str | list[str],
        model: str = "local/bge-m3",
    ) -> list[list[float]]:
        """Genera embeddings tramite BGE-M3 locale (bypass NanoGPT)."""
        from me4brain.embeddings.bge_m3 import get_embedding_service

        embedding_service = get_embedding_service()
        if isinstance(text, list):
            return await embedding_service.embed_documents_async(text)
        return [await embedding_service.embed_document_async(text)]

    async def stream_response(self, request: LLMRequest) -> AsyncGenerator[LLMChunk, None]:
        """Esegue una chiamata POST streaming SSE."""
        request.stream = True
        payload = self._prepare_payload(request)

        logger.debug("llm_stream_start", model=request.model)

        base_url = self._get_base_url_for_model(request.model)

        # Auto-load model if going to LM Studio and model is not loaded
        if base_url == get_llm_config().lmstudio_base_url.rstrip("/"):
            auto_loader = get_lmstudio_auto_loader()
            model_loaded = await auto_loader.ensure_model_loaded(request.model)
            if not model_loaded:
                logger.error("lmstudio_auto_load_failed_stream", model=request.model)
                logger.warning(
                    "lmstudio_auto_load_continue_without_block_stream",
                    model=request.model,
                )

        async with self.client.stream(
            "POST", f"{base_url}/chat/completions", json=payload
        ) as response:
            if response.status_code != 200:
                await response.aread()
                logger.error("nanogpt_stream_error", status=response.status_code)
                raise httpx.HTTPStatusError(
                    f"HTTP Error {response.status_code}",
                    request=response.request,
                    response=response,
                )

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                raw_data = line[6:].strip()  # Rimuove 'data: '
                if raw_data == "[DONE]":
                    break

                try:
                    chunk_data = json.loads(raw_data)

                    choices = []
                    for c in chunk_data.get("choices", []):
                        delta = c.get("delta", {})

                        # Streaming tool calls è complesso, per ora supportiamo base
                        # In futuro: state machine per accumulare tool calls frammentati

                        # Reasoning stream (NanoGPT specific)
                        reasoning = delta.get("reasoning") or delta.get("reasoning_content")

                        choices.append(
                            ChoiceDelta(
                                index=c.get("index", 0),
                                delta=DeltaContent(
                                    content=delta.get("content"), reasoning=reasoning
                                ),
                                finish_reason=c.get("finish_reason"),
                            )
                        )

                    yield LLMChunk(
                        id=chunk_data.get("id", "stream"),
                        model=chunk_data.get("model", request.model),
                        choices=choices,
                    )

                except json.JSONDecodeError:
                    logger.warning("nanogpt_stream_decode_error", line=line)
                    continue
