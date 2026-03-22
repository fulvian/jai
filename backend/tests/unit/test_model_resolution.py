"""Tests for model resolution via provider_factory.

Tests the resolve_model_client() function which routes model IDs to appropriate
LLM providers (Ollama, LM Studio, NanoGPT).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from me4brain.llm.provider_factory import resolve_model_client
from me4brain.llm.config import LLMConfig


@pytest.fixture
def mock_config():
    """Fixture for LLMConfig with required fields."""
    config = Mock(spec=LLMConfig)
    config.llm_local_only = False
    config.NANOGPT_API_KEY = "test-key"
    config.NANOGPT_BASE_URL = "https://test.api/v1"
    config.LLM_PRIMARY_MODEL = "mistralai/mistral-large-3"
    config.OLLAMA_BASE_URL = "http://localhost:11434"
    config.OLLAMA_MODEL = "qwen3.5-4b-mlx"
    return config


@pytest.fixture
def mock_clients():
    """Fixture providing mock client instances."""
    mock_ollama = Mock(name="OllamaClient")
    mock_nanogpt = Mock(name="NanoGPTClient")
    return {
        "ollama": mock_ollama,
        "nanogpt": mock_nanogpt,
    }


class TestResolveModelClient:
    """Test model ID resolution to correct LLM providers."""

    def test_ollama_model_with_colon_tag(self, mock_config, mock_clients):
        """Models with colon (Ollama tags) should resolve to Ollama.

        Ollama uses colons for model tags (e.g., qwen3:14b, llama2:7b).
        These should NOT be confused with provider_id:model_id format.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
        ]

        with patches[0], patches[1]:
            client, model = resolve_model_client("qwen3:14b")
            assert client is mock_clients["ollama"]
            assert model == "qwen3:14b"

    def test_ollama_family_models_without_slash(self, mock_config, mock_clients):
        """Common Ollama models (qwen, llama, mistral) without / should use Ollama.

        These are common open-source model families available in Ollama.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
        ]

        with patches[0], patches[1]:
            # Test qwen family
            client, model = resolve_model_client("qwen3")
            assert client is mock_clients["ollama"]
            assert model == "qwen3"

            # Test llama family
            client, model = resolve_model_client("llama2")
            assert client is mock_clients["ollama"]
            assert model == "llama2"

            # Test mistral family
            client, model = resolve_model_client("mistral-7b")
            assert client is mock_clients["ollama"]
            assert model == "mistral-7b"

    def test_mlx_models_use_lmstudio(self, mock_config, mock_clients):
        """MLX models (LM Studio format) should resolve to NanoGPT (LM Studio).

        MLX models end with '-mlx' or start with 'mlx-' and are served by LM Studio.
        NanoGPT client routes these to LM Studio via HTTP.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_llm_client", return_value=mock_clients["nanogpt"]
            ),
        ]

        with patches[0], patches[1]:
            # Test -mlx suffix
            client, model = resolve_model_client("qwen3.5-4b-mlx")
            assert client is mock_clients["nanogpt"]
            assert model == "qwen3.5-4b-mlx"

            # Test mlx- prefix
            client, model = resolve_model_client("mlx-qwen3.5-9b")
            assert client is mock_clients["nanogpt"]
            assert model == "mlx-qwen3.5-9b"

    def test_cloud_models_use_nanogpt(self, mock_config, mock_clients):
        """Cloud models with organization namespace should use NanoGPT.

        Models in format 'org/model' are cloud-hosted and should use NanoGPT client.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_llm_client", return_value=mock_clients["nanogpt"]
            ),
        ]

        with patches[0], patches[1]:
            client, model = resolve_model_client("mistralai/mistral-large-3-675b-instruct-2512")
            assert client is mock_clients["nanogpt"]
            assert model == "mistralai/mistral-large-3-675b-instruct-2512"

    def test_local_only_mode_forces_ollama(self, mock_config, mock_clients):
        """With llm_local_only=true, simple models should use Ollama.

        Local-only mode forces all models to use local providers, starting with Ollama.
        """
        mock_config.llm_local_only = True
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
        ]

        with patches[0], patches[1]:
            client, model = resolve_model_client("llama3")
            assert client is mock_clients["ollama"]
            assert model == "llama3"

    def test_model_id_preserved_in_resolution(self, mock_config, mock_clients):
        """Model ID should be returned unchanged from resolution.

        The resolved model ID should match input (for simple models).
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
            patch(
                "me4brain.llm.provider_factory.get_llm_client", return_value=mock_clients["nanogpt"]
            ),
        ]

        with patches[0], patches[1], patches[2]:
            test_cases = [
                "qwen3:14b",
                "qwen3.5-4b-mlx",
                "llama2:7b",
                "mistral-7b",
            ]

            for model_id in test_cases:
                _, resolved_model = resolve_model_client(model_id)
                assert resolved_model == model_id

    def test_uuid_format_detection(self, mock_config, mock_clients):
        """Models matching UUID:model format should be treated as dynamic provider.

        Actual UUIDs should trigger dynamic provider resolution.
        Non-UUIDs that look like provider:model should use normal resolution.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
        ]

        with patches[0], patches[1]:
            # Non-UUID colon format (has non-hex chars or wrong length)
            client, model = resolve_model_client("not-a-uuid:some-model")
            # Should treat as model with colon tag, not dynamic provider
            assert model == "not-a-uuid:some-model"
            assert client is mock_clients["ollama"]

    def test_multiple_colons_in_model(self, mock_config, mock_clients):
        """Models with multiple colons should use first colon as delimiter.

        Ollama models might have complex tags, split on first colon only.
        """
        patches = [
            patch("me4brain.llm.provider_factory.get_llm_config", return_value=mock_config),
            patch(
                "me4brain.llm.provider_factory.get_ollama_client",
                return_value=mock_clients["ollama"],
            ),
        ]

        with patches[0], patches[1]:
            client, model = resolve_model_client("qwen3:14b:some-variant")
            assert client is mock_clients["ollama"]
            # Should preserve everything after first colon
            assert model == "qwen3:14b:some-variant"
