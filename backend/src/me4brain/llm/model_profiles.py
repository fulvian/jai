"""Model Profiles Registry - SOTA 2026.

Registry di profili per modelli LLM con caratteristiche, limiti e raccomandazioni.
Supporta routing intelligente basato su complessità query e risorse disponibili.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class ModelCapability(str, Enum):
    TOOL_CALLING = "tool_calling"
    VISION = "vision"
    STREAMING = "streaming"
    JSON_MODE = "json_mode"
    EMBEDDINGS = "embeddings"
    REASONING = "reasoning"


class ModelProvider(str, Enum):
    LOCAL_MLX = "local_mlx"
    LOCAL_OLLAMA = "local_ollama"
    LOCAL_LMSTUDIO = "local_lmstudio"
    CLOUD_NANOGPT = "cloud_nanogpt"
    CLOUD_OPENAI = "cloud_openai"
    CLOUD_ANTHROPIC = "cloud_anthropic"


@dataclass
class ModelProfile:
    """Profilo completo di un modello LLM."""

    id: str
    name: str
    provider: ModelProvider
    context_window: int
    max_output_tokens: int
    capabilities: list[ModelCapability] = field(default_factory=list)
    vram_required_gb: Optional[float] = None
    speed_tps: Optional[float] = None
    recommended_for: list[str] = field(default_factory=list)
    not_recommended_for: list[str] = field(default_factory=list)
    quantization: Optional[str] = None
    cost_per_1k_tokens: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_local(self) -> bool:
        return self.provider in (
            ModelProvider.LOCAL_MLX,
            ModelProvider.LOCAL_OLLAMA,
            ModelProvider.LOCAL_LMSTUDIO,
        )

    @property
    def supports_tools(self) -> bool:
        return ModelCapability.TOOL_CALLING in self.capabilities

    @property
    def supports_vision(self) -> bool:
        return ModelCapability.VISION in self.capabilities

    def is_recommended_for(self, task: str) -> bool:
        if task in self.not_recommended_for:
            return False
        return task in self.recommended_for or not self.recommended_for


MODEL_PROFILES: dict[str, ModelProfile] = {
    "qwen3.5-4b-mlx": ModelProfile(
        id="qwen3.5-4b-mlx",
        name="Qwen 3.5 4B MLX",
        provider=ModelProvider.LOCAL_MLX,
        context_window=32768,
        max_output_tokens=4096,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        vram_required_gb=3.5,
        speed_tps=30,
        recommended_for=["routing", "extraction", "tool_selection", "classification"],
        not_recommended_for=["synthesis_complex", "vision", "deep_reasoning"],
        quantization="4bit",
        metadata={
            "model_path": "/Users/fulvio/.cache/lm-studio/models/mlx-community/Qwen2.5-3B-4bit",
            "architecture": "qwen2",
        },
    ),
    "qwen2.5-7b-mlx": ModelProfile(
        id="qwen2.5-7b-mlx",
        name="Qwen 2.5 7B MLX",
        provider=ModelProvider.LOCAL_MLX,
        context_window=32768,
        max_output_tokens=8192,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        vram_required_gb=6.0,
        speed_tps=20,
        recommended_for=["routing", "extraction", "tool_selection", "synthesis_simple"],
        not_recommended_for=["vision"],
        quantization="4bit",
    ),
    "lfm2-5-7b-mlx": ModelProfile(
        id="lfm2-5-7b-mlx",
        name="Liquid Foundation Models 2.5 7B MLX",
        provider=ModelProvider.LOCAL_MLX,
        context_window=32768,
        max_output_tokens=8192,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        vram_required_gb=6.0,
        speed_tps=25,
        recommended_for=["tool_calling", "structured_output", "function_calling"],
        not_recommended_for=["vision"],
        quantization="4bit",
    ),
    "mistral-large-3": ModelProfile(
        id="mistralai/mistral-large-3-675b-instruct-2512",
        name="Mistral Large 3 675B (Cloud - NanoGPT)",
        provider=ModelProvider.CLOUD_NANOGPT,
        context_window=131072,
        max_output_tokens=16384,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
            ModelCapability.REASONING,
        ],
        vram_required_gb=None,
        speed_tps=80,
        recommended_for=["synthesis", "reasoning", "complex_observation", "deep_analysis"],
        not_recommended_for=[],
        cost_per_1k_tokens=0.002,
    ),
}


def get_model_profile(model_id: str) -> Optional[ModelProfile]:
    """Ottiene il profilo di un modello per ID."""
    return MODEL_PROFILES.get(model_id)


def get_all_profiles() -> list[ModelProfile]:
    """Restituisce tutti i profili disponibili."""
    return list(MODEL_PROFILES.values())


def get_local_models() -> list[ModelProfile]:
    """Restituisce solo i modelli locali."""
    return [p for p in MODEL_PROFILES.values() if p.is_local]


def get_cloud_models() -> list[ModelProfile]:
    """Restituisce solo i modelli cloud."""
    return [p for p in MODEL_PROFILES.values() if not p.is_local]


def get_models_by_capability(capability: ModelCapability) -> list[ModelProfile]:
    """Restituisce modelli con una specifica capability."""
    return [p for p in MODEL_PROFILES.values() if capability in p.capabilities]


def get_models_for_task(task: str) -> list[ModelProfile]:
    """Restituisce modelli raccomandati per un task specifico."""
    return [p for p in MODEL_PROFILES.values() if p.is_recommended_for(task)]


def get_best_model_for_task(
    task: str,
    prefer_local: bool = True,
    max_vram_gb: Optional[float] = None,
) -> Optional[ModelProfile]:
    """Seleziona il miglior modello per un task dato.

    Args:
        task: Nome del task (es. "routing", "synthesis", "tool_calling")
        prefer_local: Se True, preferisce modelli locali
        max_vram_gb: Limite VRAM disponibile (per modelli locali)

    Returns:
        ModelProfile del modello migliore o None
    """
    candidates = get_models_for_task(task)

    if not candidates:
        candidates = list(MODEL_PROFILES.values())

    if prefer_local:
        local = [c for c in candidates if c.is_local]
        if local:
            candidates = local

    if max_vram_gb is not None:
        candidates = [
            c for c in candidates if c.vram_required_gb is None or c.vram_required_gb <= max_vram_gb
        ]

    if not candidates:
        return None

    def score_model(m: ModelProfile) -> float:
        score = 0.0
        if m.is_recommended_for(task):
            score += 10.0
        if m.speed_tps:
            score += min(m.speed_tps / 10, 5.0)
        if m.supports_tools and task in ("tool_calling", "tool_selection"):
            score += 5.0
        if m.context_window >= 64000:
            score += 3.0
        return score

    candidates.sort(key=score_model, reverse=True)
    return candidates[0]


def estimate_vram_for_context(
    model_id: str,
    context_tokens: int,
) -> float:
    """Stima la VRAM necessaria per un dato contesto.

    Formula approssimativa: base_vram + (context_tokens * bytes_per_token / 1GB)
    Per modelli quantizzati 4-bit: ~0.5 bytes per token
    """
    profile = get_model_profile(model_id)
    if not profile:
        return 0.0

    base_vram = profile.vram_required_gb or 0.0

    if profile.quantization and "4bit" in profile.quantization:
        bytes_per_token = 0.5
    elif profile.quantization and "8bit" in profile.quantization:
        bytes_per_token = 1.0
    else:
        bytes_per_token = 2.0

    context_vram = (context_tokens * bytes_per_token) / (1024**3)

    return base_vram + context_vram


def get_context_window_for_model(model_id: str) -> int:
    """Restituisce il context window per un modello."""
    profile = get_model_profile(model_id)
    return profile.context_window if profile else 32768
