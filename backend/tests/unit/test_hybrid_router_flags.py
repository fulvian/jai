"""Hybrid router runtime flag tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from me4brain.engine.hybrid_router.router import HybridToolRouter
from me4brain.engine.hybrid_router.types import HybridRouterConfig


@pytest.mark.asyncio
async def test_stage0_and_context_rewrite_flags_disable_stage0_logic() -> None:
    mock_llm = MagicMock()
    router = HybridToolRouter(llm_client=mock_llm, config=HybridRouterConfig())

    # Simulate initialized internal components
    router._initialized = True
    router._classifier = MagicMock()
    router._retriever = MagicMock()
    router._config.use_query_decomposition = False
    router._classifier.classify_with_fallback = AsyncMock(
        return_value=(
            MagicMock(
                domain_names=["finance"],
                confidence=0.9,
                is_multi_domain=False,
                needs_fallback=False,
                domains=[MagicMock(name="finance")],
            ),
            False,
        )
    )
    router._retriever.retrieve = AsyncMock(
        return_value=MagicMock(
            tools=[], tool_count=0, total_payload_bytes=0, domains_searched=["finance"]
        )
    )

    # Stage0 components present but disabled by flags
    router._context_rewriter = MagicMock()
    router._context_rewriter.rewrite = AsyncMock()
    router._intent_analyzer = MagicMock()
    router._intent_analyzer.analyze = AsyncMock()
    router._enable_stage0_intent = False
    router._enable_context_rewrite = False

    await router.route("prezzo bitcoin", conversation_history=[{"role": "user", "content": "ctx"}])

    router._context_rewriter.rewrite.assert_not_called()
    router._intent_analyzer.analyze.assert_not_called()
