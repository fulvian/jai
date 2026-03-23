"""Provider factory tests for strict local-only mode."""

from unittest.mock import patch

import pytest

from me4brain.llm.provider_factory import resolve_model_client


class DummyConfig:
    def __init__(self) -> None:
        self.ollama_model = "qwen3.5:4b"
        self.llm_local_only = True
        self.use_local_tool_calling = True
        self.llm_allow_cloud_fallback = False


def test_dynamic_provider_blocked_in_local_only() -> None:
    """provider_id:model_id dynamic resolution must be disabled in local-only mode."""
    cfg = DummyConfig()
    with patch("me4brain.llm.provider_factory.get_llm_config", return_value=cfg):
        with pytest.raises(ValueError, match="Dynamic provider resolution is disabled"):
            resolve_model_client("123e4567-e89b-12d3-a456-426614174000:mistralai/mistral-large-3")
