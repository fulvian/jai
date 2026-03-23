"""Structured trace contract for hybrid routing pipeline.

Implements Phase A of the implementation plan: standardized trace logging
across all stages (0/1/1b/2/3/synthesis) with consistent telemetry fields.

This ensures observability and debugging of the complete routing lifecycle.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StageType(str, Enum):
    """Pipeline stage identifiers."""

    STAGE_0 = "stage_0_intent_analysis"
    STAGE_1 = "stage_1_domain_classification"
    STAGE_1B = "stage_1b_query_decomposition"
    STAGE_2 = "stage_2_tool_retrieval"
    STAGE_3 = "stage_3_tool_selection"
    SYNTHESIS = "synthesis"


class FallbackType(str, Enum):
    """Fallback trigger reasons."""

    MODEL_NOT_FOUND = "model_not_found"
    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE_ERROR = "llm_parse_error"
    LLM_EXCEPTION = "llm_exception"
    NO_TOOLS_SELECTED = "no_tools_selected"
    QUOTA_EXCEEDED = "quota_exceeded"
    API_ERROR = "api_error"
    HEURISTIC_DECOMPOSITION = "heuristic_decomposition"
    CONJUNCTION_SPLIT = "conjunction_split"
    NONE = "none"


@dataclass
class StageTrace:
    """Structured trace for a single routing stage.

    Phase A (Instrumentation): All required fields for complete observability.
    """

    # Identity & Timing
    stage: StageType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0

    # Model Resolution (CRITICAL for debugging)
    model_requested: str = ""  # e.g., "qwen3.5-9b-mlx", "default"
    provider_resolved: str = ""  # e.g., "lm_studio", "ollama", "none"
    model_effective: str | None = None  # Actual model used (may differ if fallback)

    # Fallback Tracking
    fallback_applied: bool = False
    fallback_type: FallbackType = FallbackType.NONE
    fallback_reason: str = ""  # Detailed reason for fallback
    fallback_chain: list[str] = field(default_factory=list)  # Attempted models in order

    # Execution Results
    success: bool = False
    error_code: str | None = None  # e.g., "OUT_OF_USAGE_CREDITS"
    error_message: str | None = None

    # Stage-Specific Outputs (populated by each stage)
    input_query: str = ""
    output_domains: list[str] = field(default_factory=list)
    output_count: int = 0  # e.g., num subqueries, num tools, etc.
    output_metadata: dict[str, Any] = field(default_factory=dict)

    # Confidence & Quality Metrics
    confidence_score: float | None = None
    used_fallback_keywords: bool = False  # For domain classifier fallback

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        data = asdict(self)
        data["stage"] = self.stage.value
        data["fallback_type"] = self.fallback_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    def log(self, logger_instance=None):
        """Log this trace as structured JSON."""
        target_logger = logger_instance or logger
        target_logger.info(f"stage_trace_{self.stage.value}", **self.to_dict())


@dataclass
class PipelineTrace:
    """Complete trace for entire query pipeline execution.

    Aggregates all stage traces and provides end-to-end observability.
    """

    # Identity
    query: str
    correlation_id: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None

    # Stage Traces
    stages: dict[str, StageTrace] = field(default_factory=dict)  # key: stage name

    # Overall Result
    success: bool = False
    total_duration_ms: float = 0.0
    tools_executed: int = 0
    final_error: str | None = None

    def add_stage(self, trace: StageTrace):
        """Add a stage trace to this pipeline."""
        self.stages[trace.stage.value] = trace

    def finalize(self):
        """Mark pipeline as complete and calculate totals."""
        self.end_time = datetime.utcnow()
        self.total_duration_ms = (self.end_time - self.start_time).total_seconds() * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "query_preview": self.query[:100],
            "correlation_id": self.correlation_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "tools_executed": self.tools_executed,
            "final_error": self.final_error,
            "stages": [trace.to_dict() for trace in self.stages.values()],
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    def log(self, logger_instance=None):
        """Log complete pipeline trace."""
        target_logger = logger_instance or logger
        target_logger.info("pipeline_trace_complete", **self.to_dict())


def create_stage_trace(stage: StageType) -> StageTrace:
    """Factory function to create a new stage trace."""
    return StageTrace(stage=stage)


def create_pipeline_trace(query: str, correlation_id: str) -> PipelineTrace:
    """Factory function to create a new pipeline trace."""
    return PipelineTrace(query=query, correlation_id=correlation_id)
