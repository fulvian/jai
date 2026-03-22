from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Calcola il path assoluto alla root del progetto
# This file: src/me4brain/llm/config.py → root = ../../..
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class LLMConfig(BaseSettings):
    """Configurazione per il sottosistema LLM."""

    # NanoGPT Credentials
    nanogpt_api_key: str = Field(default="", alias="NANOGPT_API_KEY")
    nanogpt_base_url: str = Field(default="https://nano-gpt.com/api/v1", alias="NANOGPT_BASE_URL")

    # Selection - Qwen 3.5-4B-MLX for local inference
    # Primary Reasoning & Synthesis
    model_primary: str = Field(
        default="mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled",
        alias="LLM_PRIMARY_MODEL",
    )
    model_primary_thinking: str = Field(
        default="mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled",
        alias="LLM_PRIMARY_THINKING_MODEL",
    )

    # Agentic / Tool Calling
    model_agentic: str = Field(
        default="mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled",
        alias="LLM_AGENTIC_MODEL",
    )
    model_agentic_fast: str = Field(
        default="qwen3.5:4b",
        alias="LLM_AGENTIC_FAST_MODEL",
    )

    # Intent Routing
    model_routing: str = Field(
        default="qwen3.5:9b",
        alias="LLM_ROUTING_MODEL",
    )

    # Vision
    model_vision: str = Field(
        default="qwen3.5:9b",
        alias="LLM_VISION_MODEL",
    )

    # Extraction
    model_extraction: str = Field(
        default="qwen3.5:4b",
        alias="LLM_EXTRACTION_MODEL",
    )

    # Synthesis
    model_synthesis: str = Field(
        default="qwen3.5:9b",
        alias="LLM_SYNTHESIS_MODEL",
    )

    model_fallback: str = Field(
        default="qwen3.5:9b",
        alias="LLM_FALLBACK_MODEL",
    )

    # === Local LLM Providers (OpenAI-compatible APIs) ===
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        alias="OLLAMA_BASE_URL",
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        alias="LMSTUDIO_BASE_URL",
    )
    ollama_model: str = Field(
        default="qwen3.5:4b",
        alias="OLLAMA_MODEL",
    )
    use_local_tool_calling: bool = Field(
        default=True,
        alias="USE_LOCAL_TOOL_CALLING",
    )
    llm_local_only: bool = Field(
        default=True,
        alias="LLM_LOCAL_ONLY",
    )
    llm_allow_cloud_fallback: bool = Field(
        default=False,
        alias="LLM_ALLOW_CLOUD_FALLBACK",
    )

    # === Runtime Configuration (persisted to .env) ===
    context_overflow_strategy: Literal["map_reduce", "truncate", "cloud_fallback"] = Field(
        default="map_reduce",
        alias="CONTEXT_OVERFLOW_STRATEGY",
    )
    default_temperature: float = Field(
        default=0.3,
        alias="LLM_DEFAULT_TEMPERATURE",
    )
    default_max_tokens: int = Field(
        default=8192,
        alias="LLM_DEFAULT_MAX_TOKENS",
    )
    context_window_size: int = Field(
        default=32768,
        alias="LLM_CONTEXT_WINDOW_SIZE",
    )
    enable_streaming: bool = Field(
        default=True,
        alias="LLM_ENABLE_STREAMING",
    )
    enable_caching: bool = Field(
        default=True,
        alias="LLM_ENABLE_CACHING",
    )
    enable_metrics: bool = Field(
        default=False,
        alias="LLM_ENABLE_METRICS",
    )

    # Intent Analysis Configuration
    intent_analysis_timeout: float = Field(
        default=60.0,
        alias="INTENT_ANALYSIS_TIMEOUT",
    )
    intent_cache_ttl: float = Field(
        default=300.0,
        alias="INTENT_CACHE_TTL",
    )
    intent_analysis_model: str = Field(
        default="model_routing",
        alias="INTENT_ANALYSIS_MODEL",
    )
    use_unified_intent_analyzer: bool = Field(
        default=False,
        alias="USE_UNIFIED_INTENT_ANALYZER",
    )
    use_stage0_intent_analyzer: bool = Field(
        default=True,
        alias="USE_STAGE0_INTENT_ANALYZER",
    )
    use_context_rewrite_for_routing: bool = Field(
        default=True,
        alias="USE_CONTEXT_REWRITE_FOR_ROUTING",
    )
    use_query_decomposition: bool = Field(
        default=True,
        alias="USE_QUERY_DECOMPOSITION",
    )

    # Defaults - increased for qwen3.5 thinking models (150s+ per request)
    default_timeout: float = 1800.0  # 30 min per query complesse multi-tool (was 300s = 5min)
    max_retries: int = 3

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),  # Absolute path — funziona da qualsiasi cwd
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_llm_config() -> LLMConfig:
    """Restituisce la configurazione LLM singleton."""
    return LLMConfig()  # type: ignore
