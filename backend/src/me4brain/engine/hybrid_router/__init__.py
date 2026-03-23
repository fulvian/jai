"""Hybrid Router package.

Two-stage tool routing for scalable tool selection:
- Stage 1: Domain classifier (which domains?)
- Stage 2: Embedding retrieval (which tools?)
"""

from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.router import HybridToolRouter
from me4brain.engine.hybrid_router.tool_retriever import (
    ToolEmbeddingManager,
    ToolRetriever,
)
from me4brain.engine.hybrid_router.trace_contract import (
    FallbackType,
    PipelineTrace,
    StageTrace,
    StageType,
    create_pipeline_trace,
    create_stage_trace,
)
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    RetrievedTool,
    ToolRetrievalResult,
)

__all__ = [
    # Main router
    "HybridToolRouter",
    # Stage 1
    "DomainClassifier",
    "DomainClassification",
    "DomainComplexity",
    # Stage 2
    "ToolRetriever",
    "ToolEmbeddingManager",
    "RetrievedTool",
    "ToolRetrievalResult",
    # Config
    "HybridRouterConfig",
    # Instrumentation (Phase A)
    "StageTrace",
    "StageType",
    "FallbackType",
    "PipelineTrace",
    "create_stage_trace",
    "create_pipeline_trace",
]
