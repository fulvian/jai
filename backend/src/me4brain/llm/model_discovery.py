"""Model Discovery - Scansione reale modelli locali.

Scansiona:
- LM Studio: ~/.cache/lm-studio/models/
- Ollama: ~/.ollama/models/manifests/
- MLX Server: via API HTTP

SOTA 2026: Discovery dinamica invece di profili hardcoded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class ModelSource(str, Enum):
    LM_STUDIO = "local_lmstudio"
    OLLAMA = "local_ollama"
    MLX_SERVER = "local_mlx"
    CLOUD_NANOGPT = "cloud_nanogpt"


@dataclass
class DiscoveredModel:
    id: str
    name: str
    source: ModelSource
    path: Optional[str] = None
    context_window: int = 32768
    max_output_tokens: int = 4096
    quantization: Optional[str] = None
    size_gb: Optional[float] = None
    supports_tools: bool = True
    supports_vision: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.source.value,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "quantization": self.quantization,
            "vram_required_gb": self.size_gb,
            "path": self.path,
            "is_local": self.source != ModelSource.CLOUD_NANOGPT,
        }


class ModelDiscovery:
    """Scansiona modelli LLM installati localmente.

    Supporta:
    - LM Studio (cartella ~/.cache/lm-studio/models/)
    - Ollama (cartella ~/.ollama/models/)
    - MLX Server (via API HTTP)
    """

    LM_STUDIO_MODELS_DIR = Path.home() / ".cache" / "lm-studio" / "models"
    OLLAMA_MODELS_DIR = Path.home() / ".ollama" / "models"

    CONTEXT_WINDOW_MAP = {
        "qwen": 32768,
        "llama": 8192,
        "mistral": 32768,
        "phi": 4096,
        "gemma": 8192,
        "deepseek": 64000,
        "lfm": 32768,
    }

    def __init__(self, mlx_server_url: str = "http://localhost:1234/v1"):
        self.mlx_server_url = mlx_server_url

    def scan_lm_studio(self) -> list[DiscoveredModel]:
        """Scansiona cartella modelli LM Studio."""
        models = []

        if not self.LM_STUDIO_MODELS_DIR.exists():
            logger.debug("lm_studio_dir_not_found", path=str(self.LM_STUDIO_MODELS_DIR))
            return models

        try:
            for org_dir in self.LM_STUDIO_MODELS_DIR.iterdir():
                if not org_dir.is_dir():
                    continue
                if org_dir.name.startswith("."):
                    continue

                for model_dir in org_dir.iterdir():
                    if not model_dir.is_dir():
                        continue
                    if model_dir.name.startswith("."):
                        continue

                    model_id = f"lmstudio/{org_dir.name}/{model_dir.name}"
                    display_name = model_dir.name.replace("-", " ").replace("_", " ")

                    size_gb = self._get_dir_size_gb(model_dir)
                    quantization = self._detect_quantization(model_dir.name)
                    context_window = self._estimate_context_window(model_dir.name)

                    models.append(
                        DiscoveredModel(
                            id=model_id,
                            name=display_name,
                            source=ModelSource.LM_STUDIO,
                            path=str(model_dir),
                            context_window=context_window,
                            quantization=quantization,
                            size_gb=size_gb,
                            metadata={"org": org_dir.name, "model_dir": model_dir.name},
                        )
                    )

            logger.info("lm_studio_scan_complete", count=len(models))
        except Exception as e:
            logger.warning("lm_studio_scan_error", error=str(e))

        return models

    def scan_ollama(self) -> list[DiscoveredModel]:
        """Scansiona modelli Ollama installati."""
        models = []
        manifests_dir = self.OLLAMA_MODELS_DIR / "manifests"

        if not manifests_dir.exists():
            logger.debug("ollama_dir_not_found", path=str(manifests_dir))
            return models

        try:
            for registry_dir in manifests_dir.iterdir():
                if not registry_dir.is_dir():
                    continue

                for org_dir in registry_dir.iterdir():
                    if not org_dir.is_dir():
                        continue

                    for model_file in org_dir.iterdir():
                        if not model_file.is_file():
                            continue

                        model_tag = model_file.name
                        model_name = org_dir.name
                        model_id = f"ollama/{model_name}:{model_tag}"

                        context_window = self._estimate_context_window(model_name)

                        models.append(
                            DiscoveredModel(
                                id=model_id,
                                name=f"{model_name}:{model_tag}",
                                source=ModelSource.OLLAMA,
                                context_window=context_window,
                                metadata={
                                    "registry": registry_dir.name,
                                    "org": org_dir.name,
                                    "tag": model_tag,
                                },
                            )
                        )

            logger.info("ollama_scan_complete", count=len(models))
        except Exception as e:
            logger.warning("ollama_scan_error", error=str(e))

        return models

    async def scan_mlx_server(self) -> list[DiscoveredModel]:
        """Scansiona modelli via mlx_lm.server API."""
        models = []

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.mlx_server_url}/models")
                if response.status_code == 200:
                    data = response.json()
                    for model_data in data.get("data", []):
                        model_id = model_data.get("id", "unknown")

                        display_name = model_id
                        if "/" in model_id:
                            display_name = model_id.split("/")[-1]

                        models.append(
                            DiscoveredModel(
                                id=f"mlx/{model_id}",
                                name=display_name,
                                source=ModelSource.MLX_SERVER,
                                context_window=self._estimate_context_window(model_id),
                                metadata={"raw_id": model_id},
                            )
                        )

            logger.info("mlx_server_scan_complete", count=len(models))
        except httpx.ConnectError:
            logger.debug("mlx_server_not_running", url=self.mlx_server_url)
        except Exception as e:
            logger.warning("mlx_server_scan_error", error=str(e))

        return models

    def get_all_local_models_sync(self) -> list[DiscoveredModel]:
        """Ottiene tutti i modelli locali (sincrono, senza MLX server)."""
        models = []
        models.extend(self.scan_lm_studio())
        models.extend(self.scan_ollama())
        return models

    async def get_all_local_models(self) -> list[DiscoveredModel]:
        """Ottiene tutti i modelli locali (async, include MLX server)."""
        models = self.get_all_local_models_sync()
        models.extend(await self.scan_mlx_server())
        return models

    def _get_dir_size_gb(self, path: Path) -> float:
        """Calcola dimensione directory in GB."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except (PermissionError, OSError):
            pass
        return round(total / (1024**3), 2)

    def _detect_quantization(self, name: str) -> Optional[str]:
        """Rileva quantizzazione dal nome."""
        name_lower = name.lower()
        if "4bit" in name_lower or "-4b" in name_lower or "_4bit" in name_lower:
            return "4bit"
        if "8bit" in name_lower or "-8b" in name_lower or "_8bit" in name_lower:
            return "8bit"
        if "q4" in name_lower:
            return "Q4"
        if "q5" in name_lower:
            return "Q5"
        if "q6" in name_lower:
            return "Q6"
        if "q8" in name_lower:
            return "Q8"
        if "fp16" in name_lower:
            return "fp16"
        if "bf16" in name_lower:
            return "bf16"
        return None

    def _estimate_context_window(self, name: str) -> int:
        """Stima context window dal nome del modello."""
        name_lower = name.lower()

        for key, ctx in self.CONTEXT_WINDOW_MAP.items():
            if key in name_lower:
                return ctx

        return 32768


_discovery: Optional[ModelDiscovery] = None


def get_model_discovery() -> ModelDiscovery:
    """Ottiene il singleton del discovery."""
    global _discovery
    if _discovery is None:
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        _discovery = ModelDiscovery(mlx_server_url=config.ollama_base_url)
    return _discovery


async def discover_all_models() -> list[DiscoveredModel]:
    """Convenience function per scoprire tutti i modelli."""
    discovery = get_model_discovery()
    return await discovery.get_all_local_models()
