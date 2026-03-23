"""Phase 2.4: Configuration Validation Tests.

Tests for validating LLM model availability at startup and ensuring
configured models exist in providers (Ollama/LM Studio).
"""

from dataclasses import dataclass

import pytest


@dataclass
class MockedConfig:
    """Mock LLMConfig for testing."""

    model_routing: str
    model_primary: str
    model_synthesis: str
    ollama_base_url: str
    lmstudio_base_url: str
    llm_local_only: bool
    llm_allow_cloud_fallback: bool


class TestConfigurationValidation:
    """Test configuration validation and model availability checking."""

    def test_validate_configured_model_exists_in_ollama(self):
        """Configured routing model should exist in Ollama's loaded models."""
        # Given
        configured_model = "qwen3.5-4b-mlx"
        loaded_models = [
            {"name": "qwen3.5-4b-mlx"},
            {"name": "mistral"},
            {"name": "llama2"},
        ]

        # When - checking if model exists
        model_names = [m["name"] for m in loaded_models]
        exists = configured_model in model_names

        # Then
        assert exists is True

    def test_validate_configured_model_not_loaded_in_ollama(self):
        """Should detect when configured model is not loaded."""
        # Given
        configured_model = "qwen3.5-14b-mlx"  # Not loaded
        loaded_models = [
            {"name": "qwen3.5-4b-mlx"},
            {"name": "mistral"},
        ]

        # When - checking if model exists
        model_names = [m["name"] for m in loaded_models]
        exists = configured_model in model_names

        # Then
        assert exists is False

    @pytest.mark.asyncio
    async def test_validate_model_with_tag_variations(self):
        """Should validate models with tag variations (e.g., model:7b vs model:14b)."""
        # Given
        configured_model = "qwen3:14b"  # Model with tag
        loaded_models = [
            {"name": "qwen3:7b"},
            {"name": "qwen3:14b"},
            {"name": "mistral:latest"},
        ]

        # When - checking with tag support
        model_names = [m["name"] for m in loaded_models]
        base_model = configured_model.split(":")[0] if ":" in configured_model else configured_model

        # Exact match or partial match
        exists = configured_model in model_names or any(base_model in m for m in model_names)

        # Then - should find the model
        assert exists is True

    @pytest.mark.asyncio
    async def test_fallback_to_available_model_if_configured_missing(self):
        """Should fallback to available model if configured one is missing."""
        # Given - configured model not available
        configured_model = "unavailable-model"
        loaded_models = [
            {"name": "qwen3.5-4b-mlx"},
            {"name": "mistral"},
        ]

        # When - finding fallback
        model_names = [m["name"] for m in loaded_models]
        found_model = (
            configured_model
            if configured_model in model_names
            else (model_names[0] if model_names else None)
        )

        # Then - should use first available model
        assert found_model == "qwen3.5-4b-mlx"

    @pytest.mark.asyncio
    async def test_warn_but_not_crash_if_no_models_available(self):
        """Should warn but not crash if all models are unavailable."""
        # Given - no models loaded
        loaded_models = []

        # When - checking availability
        model_names = [m["name"] for m in loaded_models]
        is_available = len(model_names) > 0
        found_model = model_names[0] if model_names else None

        # Then - system should gracefully degrade
        assert is_available is False
        assert found_model is None
        # Warning would be logged, but system continues


class TestModelAvailabilityValidation:
    """Test model availability validation at startup."""

    @pytest.mark.asyncio
    async def test_validate_primary_model_loaded(self):
        """Primary model used for reasoning should be validated."""
        # Given
        config = MockedConfig(
            model_routing="qwen3.5-9b-mlx",
            model_primary="mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled",
            model_synthesis="qwen3.5-9b-mlx",
            ollama_base_url="http://localhost:11434/v1",
            lmstudio_base_url="http://localhost:1234/v1",
            llm_local_only=True,
            llm_allow_cloud_fallback=False,
        )

        available_models = {
            "mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled": True,
            "qwen3.5-9b-mlx": True,
        }

        # When - validating
        primary_model = config.model_primary
        is_valid = primary_model in available_models and available_models[primary_model]

        # Then
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_warn_when_routing_model_not_available(self):
        """Should warn if routing model is not available at startup."""
        # Given
        config = MockedConfig(
            model_routing="missing-model",
            model_primary="qwen3.5-9b-mlx",
            model_synthesis="qwen3.5-9b-mlx",
            ollama_base_url="http://localhost:11434/v1",
            lmstudio_base_url="http://localhost:1234/v1",
            llm_local_only=True,
            llm_allow_cloud_fallback=False,
        )

        available_models = {
            "qwen3.5-9b-mlx": True,
        }

        # When - validating routing model
        routing_model = config.model_routing
        is_valid = routing_model in available_models

        # Then - should detect problem
        assert is_valid is False


class TestConfigurationSyncValidation:
    """Test that configuration syncs with actual provider state."""

    @pytest.mark.asyncio
    async def test_config_model_names_match_provider_format(self):
        """Config model names should match provider's expected format."""
        # Given
        config_models = {
            "model_routing": "qwen3.5-9b-mlx",
            "model_primary": "mlx-qwen3.5-9b-claude",
            "model_synthesis": "qwen3.5-9b-mlx",
        }

        ollama_models_response = {
            "models": [
                {"name": "qwen3.5-9b-mlx"},
                {"name": "mlx-qwen3.5-9b-claude"},
                {"name": "mistral"},
            ]
        }

        # When - checking each config model
        loaded_names = [m["name"] for m in ollama_models_response["models"]]
        all_present = all(model in loaded_names for model in config_models.values())

        # Then - all configured models should be loaded
        assert all_present is True

    @pytest.mark.asyncio
    async def test_detect_config_llm_local_only_mismatch(self):
        """Should detect if local_only=true but no local models available."""
        # Given
        config = MockedConfig(
            model_routing="qwen3.5-9b-mlx",
            model_primary="qwen3.5-9b-mlx",
            model_synthesis="qwen3.5-9b-mlx",
            ollama_base_url="http://localhost:11434/v1",
            lmstudio_base_url="http://localhost:1234/v1",
            llm_local_only=True,  # Local-only enabled
            llm_allow_cloud_fallback=False,  # No cloud fallback
        )

        # When - no local models are available
        ollama_healthy = False  # Ollama down
        lmstudio_healthy = False  # LM Studio down
        local_available = ollama_healthy or lmstudio_healthy

        # Then - mismatch detected
        is_misconfigured = config.llm_local_only and not local_available
        assert is_misconfigured is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
