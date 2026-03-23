"""Prometheus metrics for domain classification and fallback tracking.

Tracks:
- Classification method (LLM vs fallback)
- Latency by method
- LLM error types and rates
- Degradation level transitions
"""

from prometheus_client import Counter, Gauge, Histogram

# Classification method tracking
CLASSIFICATION_TOTAL = Counter(
    "domain_classification_total",
    "Total domain classifications",
    ["method", "success"],  # method: llm, fallback_keyword, fallback_heuristic
)

CLASSIFICATION_LATENCY = Histogram(
    "domain_classification_latency_seconds",
    "Domain classification latency",
    ["method"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),  # Up to timeout
)

# LLM error tracking
LLM_ERRORS = Counter(
    "domain_classification_llm_errors_total",
    "LLM errors during classification",
    ["error_type"],  # timeout, connection, parse, validation
)

# Degradation level tracking
DEGRADATION_LEVEL = Gauge(
    "domain_classification_degradation_level",
    "Current degradation level (0=FULL_LLM, 1=SIMPLIFIED_LLM, 2=HYBRID, 3=KEYWORD_ONLY)",
    ["query_type"],
)

DEGRADATION_TRANSITIONS = Counter(
    "domain_classification_degradation_transitions",
    "Number of transitions between degradation levels",
    ["from_level", "to_level"],
)

# Confidence tracking
CLASSIFICATION_CONFIDENCE = Histogram(
    "domain_classification_confidence",
    "Classification confidence scores",
    ["method"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# Retry tracking
CLASSIFICATION_RETRIES = Counter(
    "domain_classification_retries_total",
    "Total retry attempts",
    ["reason"],  # timeout, error, low_confidence
)

# Query context tracking
QUERY_WITH_CONTEXT = Counter(
    "domain_classification_with_context_total",
    "Queries classified with conversation context",
    ["has_context"],
)

# =============================================================================
# Cache Metrics (Phase 6)
# =============================================================================

# Cache hit/miss tracking
CACHE_HITS = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["model", "provider"],
)

CACHE_MISSES = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["model", "provider"],
)

# Cache hit ratio gauge
CACHE_HIT_RATIO = Gauge(
    "cache_hit_ratio",
    "Cache hit ratio",
    ["model", "provider"],
)

# Semantic similarity score
SEMANTIC_SIMILARITY_SCORE = Histogram(
    "semantic_similarity_score",
    "Semantic similarity score for cache matches",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0),
)

# Cache operation latency
CACHE_OPERATION_LATENCY = Histogram(
    "cache_operation_latency_seconds",
    "Cache operation latency",
    ["operation"],  # get, set, invalidate
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

# =============================================================================
# Retrieval SLO Metrics (Wave 4)
# =============================================================================

# Tool selection recall - tracks whether correct tools appear in top-K
TOOL_SELECTION_RECALL = Gauge(
    "tool_selection_recall_at_10",
    "Tool selection recall@10 - proportion of queries where correct tool appears in top 10",
)

# Wrong domain failures - queries routed to wrong domain
WRONG_DOMAIN_FAILURES = Counter(
    "wrong_domain_failures_total",
    "Total queries routed to wrong domain",
    ["expected_domain", "actual_domain"],
)

# Zero result rate - queries returning 0 tools
ZERO_RESULT_RETRIEVALS = Counter(
    "zero_result_retrievals_total",
    "Total retrievals returning zero results",
)

# Rescue policy triggers
RESCUE_POLICY_TRIGGERS = Counter(
    "rescue_policy_triggers_total",
    "Total rescue policy triggers",
    ["trigger_reason", "policy_applied"],
)

# Retrieval latency by complexity
RETRIEVAL_LATENCY = Histogram(
    "retrieval_latency_seconds",
    "Tool retrieval latency in seconds",
    ["complexity"],  # simple, medium, complex
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0),
)

# Tool selection latency
TOOL_SELECTION_LATENCY = Histogram(
    "tool_selection_latency_seconds",
    "Tool selection (LLM call) latency in seconds",
    ["complexity"],
    buckets=(1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0),
)

# End-to-end routing latency
ROUTING_LATENCY = Histogram(
    "routing_latency_seconds",
    "End-to-end routing latency (classification + retrieval + selection)",
    ["complexity"],
    buckets=(1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 90.0),
)

# Classification confidence histogram
CLASSIFICATION_CONFIDENCE_HIST = Histogram(
    "classification_confidence_histogram",
    "Domain classification confidence distribution",
    ["domain"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# Index consistency - drift between manifest and actual tools
INDEX_DRIFT = Gauge(
    "index_drift_count",
    "Number of tools with inconsistent metadata between manifest and actual index",
)

# Retrieval result count
RETRIEVAL_RESULT_COUNT = Histogram(
    "retrieval_result_count",
    "Number of tools returned per retrieval",
    ["domain"],
    buckets=(1, 3, 5, 10, 15, 20, 25, 30),
)
