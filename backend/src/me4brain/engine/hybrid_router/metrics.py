"""Prometheus metrics for domain classification and fallback tracking.

Tracks:
- Classification method (LLM vs fallback)
- Latency by method
- LLM error types and rates
- Degradation level transitions
"""

from prometheus_client import Counter, Histogram, Gauge

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
