"""Provider Registry - Gestione dinamica provider LLM.

Permette di aggiungere, modificare, eliminare provider API a runtime.
Supporta OpenAI-compatible, Anthropic, e provider custom.
Include gestione subscription (NanoGPT Pro) vs API-paid.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class ProviderType(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    COHERE = "cohere"
    CUSTOM = "custom"


class ModelAccessMode(str, Enum):
    SUBSCRIPTION = "subscription"
    API_PAID = "api_paid"
    BOTH = "both"


@dataclass
class ProviderModel:
    id: str
    display_name: str
    context_window: int = 32768
    max_output_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    access_mode: str = ModelAccessMode.API_PAID.value
    pricing: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderModel":
        return cls(
            id=data.get("id", data.get("model_id", "")),
            display_name=data.get("display_name", data.get("name", data.get("id", ""))),
            context_window=data.get("context_window", 32768),
            max_output_tokens=data.get("max_output_tokens", 4096),
            supports_tools=data.get("supports_tools", True),
            supports_vision=data.get("supports_vision", False),
            supports_streaming=data.get("supports_streaming", True),
            access_mode=data.get("access_mode", ModelAccessMode.API_PAID.value),
            pricing=data.get("pricing"),
        )


@dataclass
class ProviderTestResult:
    success: bool
    latency_ms: float
    error: Optional[str] = None
    models_count: Optional[int] = None


@dataclass
class SubscriptionConfig:
    enabled: bool = False
    weekly_token_limit: Optional[int] = None
    reset_day: int = 1
    tokens_used_this_week: int = 0
    last_reset: Optional[str] = None


@dataclass
class LLMProviderConfig:
    id: str
    name: str
    type: ProviderType
    base_url: str
    api_key: Optional[str] = None
    api_key_header: str = "Authorization"
    models: list = field(default_factory=list)
    is_local: bool = False
    is_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_test: Optional[dict] = None
    subscription: Optional[dict] = None

    def to_dict(self, mask_api_key: bool = True) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "base_url": self.base_url,
            "api_key": "***" if (mask_api_key and self.api_key) else None,
            "api_key_header": self.api_key_header,
            "models": [m.to_dict() if hasattr(m, "to_dict") else m for m in self.models],
            "is_local": self.is_local,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_test": self.last_test,
            "subscription": self.subscription,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LLMProviderConfig":
        models = []
        for m in data.get("models", []):
            if isinstance(m, dict):
                models.append(ProviderModel.from_dict(m))
            else:
                models.append(m)

        return cls(
            id=data["id"],
            name=data["name"],
            type=ProviderType(data.get("type", "openai_compatible")),
            base_url=data["base_url"],
            api_key=data.get("api_key"),
            api_key_header=data.get("api_key_header", "Authorization"),
            models=models,
            is_local=data.get("is_local", False),
            is_enabled=data.get("is_enabled", True),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            last_test=data.get("last_test"),
            subscription=data.get("subscription"),
        )


class ProviderRegistry:
    """Registry per gestire provider LLM dinamici."""

    DEFAULT_STORAGE_PATH = Path(__file__).parent.parent.parent.parent / "storage" / "providers.json"

    def __init__(self, storage_path: Optional[Path] = None, encryption_key: Optional[str] = None):
        self._storage_path = storage_path or self.DEFAULT_STORAGE_PATH
        self._providers: dict[str, LLMProviderConfig] = {}
        self._encryption_key = encryption_key
        self._fernet = self._get_fernet(encryption_key)
        self._load()

    def _get_fernet(self, key: Optional[str]):
        if not key:
            import os

            key = os.environ.get("ME4BRAIN_API_KEY", "default-key-change-in-production")
        key_bytes = hashlib.sha256(key.encode()).digest()
        from cryptography.fernet import Fernet

        return Fernet(base64.urlsafe_b64encode(key_bytes))

    def _encrypt(self, value: str) -> str:
        if self._fernet and value:
            return self._fernet.encrypt(value.encode()).decode()
        return value

    def _decrypt(self, value: str) -> str:
        if self._fernet and value:
            try:
                return self._fernet.decrypt(value.encode()).decode()
            except Exception:
                return value
        return value

    def _load(self):
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                for p in data.get("providers", []):
                    if p.get("api_key_encrypted"):
                        p["api_key"] = self._decrypt(p["api_key_encrypted"])
                        del p["api_key_encrypted"]
                    self._providers[p["id"]] = LLMProviderConfig.from_dict(p)
                logger.info("providers_loaded", count=len(self._providers))
            except Exception as e:
                logger.error("providers_load_error", error=str(e))

    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "providers": []}
        for p in self._providers.values():
            pd = p.to_dict(mask_api_key=False)
            if p.api_key:
                pd["api_key_encrypted"] = self._encrypt(p.api_key)
                del pd["api_key"]
            pd["models"] = [m.to_dict() if hasattr(m, "to_dict") else m for m in p.models]
            data["providers"].append(pd)
        self._storage_path.write_text(json.dumps(data, indent=2))

    def list_all(self) -> list[LLMProviderConfig]:
        return list(self._providers.values())

    def get(self, provider_id: str) -> Optional[LLMProviderConfig]:
        return self._providers.get(provider_id)

    def create(self, data: dict) -> LLMProviderConfig:
        models = []
        for m in data.get("models", []):
            if isinstance(m, dict):
                models.append(ProviderModel.from_dict(m))

        provider = LLMProviderConfig(
            id=str(uuid.uuid4()),
            name=data["name"],
            type=ProviderType(data.get("type", "openai_compatible")),
            base_url=data["base_url"],
            api_key=data.get("api_key"),
            api_key_header=data.get("api_key_header", "Authorization"),
            models=models,
            is_local=data.get("is_local", False),
            is_enabled=data.get("is_enabled", True),
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            subscription=data.get("subscription"),
        )
        self._providers[provider.id] = provider
        self._save()
        logger.info("provider_created", id=provider.id, name=provider.name)
        return provider

    def update(self, provider_id: str, data: dict) -> Optional[LLMProviderConfig]:
        if provider_id not in self._providers:
            return None
        provider = self._providers[provider_id]

        for key, value in data.items():
            if key == "models":
                provider.models = [
                    ProviderModel.from_dict(m) if isinstance(m, dict) else m for m in value
                ]
            elif key == "type":
                provider.type = ProviderType(value)
            elif key == "subscription":
                provider.subscription = value
            elif hasattr(provider, key):
                setattr(provider, key, value)

        provider.updated_at = datetime.utcnow().isoformat()
        self._save()
        logger.info("provider_updated", id=provider_id)
        return provider

    def delete(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            del self._providers[provider_id]
            self._save()
            logger.info("provider_deleted", id=provider_id)
            return True
        return False

    async def test_connection(self, provider_id: str) -> ProviderTestResult:
        provider = self.get(provider_id)
        if not provider:
            return ProviderTestResult(success=False, latency_ms=0, error="Provider not found")

        start = asyncio.get_event_loop().time()
        try:
            headers = {"Content-Type": "application/json"}
            if provider.api_key:
                if provider.api_key_header == "Authorization":
                    headers["Authorization"] = f"Bearer {provider.api_key}"
                else:
                    headers[provider.api_key_header] = provider.api_key

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{provider.base_url}/models", headers=headers)
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    models_count = len(data.get("data", data.get("models", [])))
                    provider.last_test = {
                        "success": True,
                        "latency_ms": latency_ms,
                        "models_count": models_count,
                    }
                    self._save()
                    return ProviderTestResult(
                        success=True, latency_ms=latency_ms, models_count=models_count
                    )
                else:
                    error_msg = f"HTTP {response.status_code}"
                    provider.last_test = {
                        "success": False,
                        "latency_ms": latency_ms,
                        "error": error_msg,
                    }
                    self._save()
                    return ProviderTestResult(success=False, latency_ms=latency_ms, error=error_msg)

        except Exception as e:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            error_msg = str(e)
            provider.last_test = {"success": False, "latency_ms": latency_ms, "error": error_msg}
            self._save()
            return ProviderTestResult(success=False, latency_ms=latency_ms, error=error_msg)

    async def discover_models(self, provider_id: str) -> list[ProviderModel]:
        """Auto-discover models from provider endpoint."""
        provider = self.get(provider_id)
        if not provider:
            return []

        models = []
        try:
            headers = {"Content-Type": "application/json"}
            if provider.api_key:
                if provider.api_key_header == "Authorization":
                    headers["Authorization"] = f"Bearer {provider.api_key}"
                else:
                    headers[provider.api_key_header] = provider.api_key

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{provider.base_url}/models", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("data", data.get("models", [])):
                        model_id = m.get("id", m.get("name", "unknown"))
                        models.append(
                            ProviderModel(
                                id=model_id,
                                display_name=model_id,
                                context_window=m.get("context_window", 32768),
                                supports_tools=m.get("supports_tools", True),
                                supports_vision=m.get("supports_vision", False),
                                access_mode=ModelAccessMode.API_PAID.value,
                                pricing=m.get("pricing"),
                            )
                        )
                    logger.info("models_discovered", provider=provider_id, count=len(models))
        except Exception as e:
            logger.warning("model_discovery_failed", provider=provider_id, error=str(e))

        return models

    def get_subscription_models(self) -> list[tuple[LLMProviderConfig, ProviderModel]]:
        """Get all models available via subscription."""
        result = []
        for provider in self._providers.values():
            if (
                provider.is_enabled
                and provider.subscription
                and provider.subscription.get("enabled")
            ):
                for model in provider.models:
                    if model.access_mode in (
                        ModelAccessMode.SUBSCRIPTION.value,
                        ModelAccessMode.BOTH.value,
                    ):
                        result.append((provider, model))
        return result

    def get_api_paid_models(self) -> list[tuple[LLMProviderConfig, ProviderModel]]:
        """Get all models that require API payment."""
        result = []
        for provider in self._providers.values():
            if provider.is_enabled:
                for model in provider.models:
                    if model.access_mode in (
                        ModelAccessMode.API_PAID.value,
                        ModelAccessMode.BOTH.value,
                    ):
                        result.append((provider, model))
        return result

    def update_token_usage(self, provider_id: str, tokens_used: int) -> Optional[dict]:
        """Update token usage for subscription tracking."""
        provider = self.get(provider_id)
        if not provider or not provider.subscription:
            return None

        sub = provider.subscription
        sub["tokens_used_this_week"] = sub.get("tokens_used_this_week", 0) + tokens_used
        provider.subscription = sub
        self._save()

        return {
            "tokens_used": sub["tokens_used_this_week"],
            "limit": sub.get("weekly_token_limit"),
            "remaining": (
                sub.get("weekly_token_limit", float("inf")) - sub["tokens_used_this_week"]
            )
            if sub.get("weekly_token_limit")
            else None,
        }


_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
