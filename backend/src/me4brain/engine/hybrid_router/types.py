"""Types for Hybrid Tool Router.

Two-stage routing architecture:
- Stage 1: Domain classification (which domains are relevant?)
- Stage 2: Embedding retrieval (which tools within those domains?)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Stage 1: Domain Classification Types
# =============================================================================


class DomainComplexity(BaseModel):
    """Single domain with its estimated complexity."""

    name: str = Field(..., description="Domain name (e.g., 'finance', 'geo_weather')")
    complexity: str = Field(
        default="medium",
        description="Estimated complexity: 'low' (1-3 tools), 'medium' (4-8), 'high' (>8)",
    )


class DomainScore(BaseModel):
    """Top-K domain with calibrated confidence score.

    Wave 2 enhancement: Returns per-domain confidence scores
    instead of single overall confidence for the classification.
    """

    domain: str = Field(..., description="Domain name (e.g., 'finance_crypto')")
    confidence: float = Field(
        ...,
        description="Calibrated confidence score (0.0-1.0). 0.7+ means strong match.",
    )
    reasoning: str | None = Field(
        default=None,
        description="Why this domain was selected",
    )


class DomainClassification(BaseModel):
    """Result of Stage 1 domain classification.

    The router LLM outputs this to indicate which domains are relevant
    and how complex the query is for each domain.

    Wave 2 enhancement: Now supports Top-K domain scoring with per-domain
    confidence scores via `top_k_domains` field.
    """

    # Legacy field: kept for backwards compatibility
    domains: list[DomainComplexity] = Field(
        default_factory=list,
        description="List of relevant domains with complexity (legacy format)",
    )
    confidence: float = Field(
        default=0.8,
        description="Classification confidence (0-1). Low = ambiguous query (legacy)",
    )
    query_summary: str = Field(
        default="",
        description="Brief summary of what the query is asking",
    )

    # Wave 2: Top-K domain scoring
    top_k_domains: list[DomainScore] = Field(
        default_factory=list,
        description="Top-K domains with per-domain confidence scores",
    )
    primary_domain: str | None = Field(
        default=None,
        description="Primary domain (highest confidence domain)",
    )

    @property
    def domain_names(self) -> list[str]:
        """Get just the domain names."""
        if self.top_k_domains:
            return [d.domain for d in self.top_k_domains]
        return [d.name for d in self.domains]

    @property
    def is_multi_domain(self) -> bool:
        """Check if query spans multiple domains."""
        if self.top_k_domains:
            return len(self.top_k_domains) > 1
        return len(self.domains) > 1

    @property
    def is_low_confidence(self) -> bool:
        """Check if classification confidence is below threshold."""
        if self.top_k_domains and len(self.top_k_domains) > 0:
            # Use primary domain confidence for threshold
            return self.top_k_domains[0].confidence < 0.5
        return self.confidence < 0.5

    @property
    def needs_fallback(self) -> bool:
        """Check if we need fallback (no domains or low confidence).

        Conversational queries usually have no domains but HIGH confidence.
        We only want to trigger fallback (web_search) if confidence is also low.
        """
        if self.top_k_domains:
            # Wave 2: Use primary domain confidence
            primary_confidence = self.top_k_domains[0].confidence if self.top_k_domains else 0.0
            if not self.top_k_domains and primary_confidence >= 0.8:
                return False  # Conversational query
            return primary_confidence < 0.4  # Low confidence threshold for rescue

        # Legacy path
        if not self.domains and self.confidence >= 0.8:
            return False  # Conversational query, trust the LLM that no tools are needed
        return not self.domains or self.is_low_confidence


# =============================================================================
# Stage 1b: Query Decomposition Types
# =============================================================================


@dataclass
class SubQuery:
    """An atomic sub-query targeting a single domain.

    Used by QueryDecomposer to break multi-intent queries into
    simpler, single-domain queries for more precise retrieval.
    """

    text: str  # The decomposed query text (was 'sub_query' but aligned with query_decomposer.py)
    domain: str  # Target domain for this sub-query
    intent: str = ""  # Optional intent label (e.g., "email_search", "flight_search")


# =============================================================================
# Stage 2: Tool Retrieval Types
# =============================================================================


@dataclass
class RetrievedTool:
    """A tool retrieved via embedding similarity.

    Supports hierarchical organization: domain > category > skill
    E.g., google_workspace > gmail > search
    """

    name: str
    domain: str
    similarity_score: float
    schema: dict[str, Any] = field(default_factory=dict)
    category: str = ""  # Sub-domain category (e.g., gmail, drive, crypto)
    skill: str = ""  # Specific skill type (e.g., search, send, book)


@dataclass
class ToolRetrievalResult:
    """Result of Stage 2 tool retrieval."""

    tools: list[RetrievedTool] = field(default_factory=list)
    total_payload_bytes: int = 0
    domains_searched: list[str] = field(default_factory=list)
    # Rescue tracking
    rescue_applied: bool = False
    rescue_policy: str = ""  # "domain_expand", "lexical_boost", "global_pass"
    rescue_trigger_reason: str = ""  # Why rescue was triggered

    @property
    def tool_names(self) -> list[str]:
        """Get just the tool names."""
        return [t.name for t in self.tools]

    @property
    def tool_count(self) -> int:
        """Number of tools retrieved."""
        return len(self.tools)

    @property
    def is_empty(self) -> bool:
        """Check if no tools were retrieved."""
        return len(self.tools) == 0

    def get_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI-compatible tool schemas."""
        return [t.schema for t in self.tools]


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class HybridRouterConfig:
    """Configuration for the hybrid router."""

    # Stage 1: Domain classification
    # Use lazy factory to read from LLMConfig instead of hardcoded defaults
    router_model: str = field(default_factory=lambda: _get_router_model())
    confidence_threshold: float = 0.5  # Lowered from 0.7
    fallback_domains: list[str] = field(default_factory=lambda: ["web_search"])

    # Stage 2: Embedding retrieval
    similarity_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "low": 0.72,  # Only very relevant tools
            "medium": 0.62,  # Moderate threshold (raised for precision)
            "high": 0.52,  # Include marginal but still relevant tools (raised)
        }
    )
    max_payload_bytes: int = 28_000  # Stay under 70% of 40KB for safety

    # Stage 3: Execution model selection
    # Using specific model placeholders that core.py will override
    execution_model_default: str = field(default_factory=lambda: _get_execution_model())
    execution_model_complex: str = field(default_factory=lambda: _get_execution_model())
    complex_threshold_tools: int = 10
    complex_threshold_domains: int = 3

    # LlamaIndex retriever settings (Qdrant-backed)
    use_llamaindex_retriever: bool = True  # Use Qdrant instead of in-memory
    use_llm_reranker: bool = True  # ✅ ABILITATO - critico per +8-12% accuracy
    reranker_model: str = field(default_factory=lambda: _get_router_model())
    rerank_top_n: int = 15
    coarse_top_k: int = 30  # Top-K for coarse vector retrieval
    min_similarity_score: float = 0.40  # Absolute floor - reject tools below this

    # Multi-intent decomposition
    use_query_decomposition: bool = True  # Decompose multi-domain queries
    decomposition_model: str = field(default_factory=lambda: _get_router_model())

    # Wave 2: Dynamic budgets and timeouts
    # Dynamic rerank budget based on query complexity
    rerank_budget_base: int = 20
    rerank_budget_per_domain: int = 5

    # Wave 2: Timeout budgets (in seconds)
    coarse_timeout_seconds: float = 10.0
    rerank_timeout_seconds: float = 30.0
    selection_timeout_seconds: float = 45.0

    @property
    def rerank_top_n_dynamic(self) -> int:
        """Dynamic rerank budget based on domain count.

        Allows more candidates for multi-domain queries.
        """
        return self.rerank_budget_base


def _get_router_model() -> str:
    """Lazy load router model from LLMConfig to get current dashboard settings."""
    try:
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        model = config.model_routing
        if model and model != "default":
            return model
    except Exception:
        pass
    return "qwen3:14b"  # Fallback default


def _get_execution_model() -> str:
    """Lazy load execution model from LLMConfig to get current dashboard settings."""
    try:
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        model = config.model_primary
        if model and model != "default":
            return model
    except Exception:
        pass
    return "qwen3:14b"  # Fallback default
