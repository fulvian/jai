"""Canonical Tool Contract - Single Source of Truth for Tool Metadata.

This module defines the ToolContract model and ToolContractRegistry singleton.
All tool metadata MUST be defined through this contract and registered here.

The registry provides:
- Single source of truth for tool metadata
- Generation of tool definitions for catalog
- Keyword maps for domain classifier
- Qdrant metadata filters
- YAML hierarchy synchronization
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class RiskLevel(Enum):
    """Risk level for tool operations.

    Attributes:
        LOW: Read-only, no side effects
        MEDIUM: Write operations, rate limits
        HIGH: Destructive, monetary
        CRITICAL: Admin, security-sensitive
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LatencyClass(Enum):
    """Expected latency class for tool operations.

    Attributes:
        FAST: <500ms expected
        NORMAL: 500ms-2s expected
        SLOW: 2-10s expected
        VARIABLE: External dependency
    """

    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"
    VARIABLE = "variable"


class ToolContract(BaseModel):
    """Canonical tool metadata contract.

    This is the SINGLE SOURCE OF TRUTH for all tool metadata.
    Generated from domain handlers and used to produce:
    - ToolDefinition for catalog
    - Hierarchy index entries
    - Domain classifier keywords
    - Qdrant metadata filters
    - Documentation
    """

    # ========== IDENTITY (Required) ==========
    tool_id: str = Field(..., description="Unique tool identifier in snake_case")
    domain: str = Field(..., description="Primary domain (e.g., google_workspace)")
    category: str = Field(..., description="Sub-domain category (e.g., gmail, calendar)")
    skill: str = Field(..., description="Skill name (e.g., search, list)")

    # ========== SCHEMA (Required) ==========
    name: str = Field(..., description="LLM-facing function name (e.g., gmail_search)")
    description: str = Field(..., max_length=500, description="Clear description of what tool does")
    parameters: dict[str, Any] = Field(..., description="JSON Schema for tool arguments")

    # ========== CLASSIFICATION (Optional - defaults provided) ==========
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM)
    latency_class: LatencyClass = Field(default=LatencyClass.NORMAL)
    auth_requirements: list[str] = Field(default_factory=list)

    # ========== VERSIONING (Optional) ==========
    version: str = Field(default="1.0.0")
    schema_version: str = Field(default="2026.1")
    deprecation_status: str = Field(default="active")
    deprecated_aliases: list[str] = Field(default_factory=list)

    # ========== DISCOVERY (Used by classifiers and retrieval) ==========
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    not_suitable_for: list[str] = Field(default_factory=list)

    # ========== RETRIEVAL TUNING ==========
    embedding_hint: str = Field(..., description="Enhanced embedding text for better retrieval")
    priority_boost: float = Field(default=1.0)
    min_similarity_score: float = Field(default=0.0)

    # ========== EXECUTION HINTS ==========
    retry_policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_attempts": 3,
            "backoff_factor": 1.5,
            "retry_on": ["timeout", "rate_limit", "server_error"],
        }
    )
    timeout_seconds: float = Field(default=30.0)

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )

    @field_validator("tool_id")
    @classmethod
    def validate_tool_id(cls, v: str) -> str:
        """Validate tool_id format (snake_case alphanumeric)."""
        if not v.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool_id: '{v}'. Must be alphanumeric with underscores only.")
        return v

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate that parameters have required JSON Schema fields."""
        if "type" not in v and "properties" not in v:
            raise ValueError("Parameters must have 'type' or 'properties' field")
        return v

    def to_tool_definition(self) -> dict[str, Any]:
        """Generate OpenAI-compatible tool definition from contract.

        Returns:
            Dictionary with 'name', 'description', and 'parameters' fields.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            # Include domain for filtering
            "_domain": self.domain,
            "_category": self.category,
            "_skill": self.skill,
        }

    def to_qdrant_metadata(self) -> dict[str, Any]:
        """Generate Qdrant payload metadata from contract.

        Returns:
            Dictionary with all metadata fields for Qdrant point payload.
        """
        return {
            "tool_name": self.tool_id,
            "domain": self.domain,
            "category": self.category,
            "skill": self.skill,
            "description": self.description,
            "risk_level": self.risk_level.value
            if isinstance(self.risk_level, RiskLevel)
            else self.risk_level,
            "latency_class": self.latency_class.value
            if isinstance(self.latency_class, LatencyClass)
            else self.latency_class,
            "type": "tool",
            "subtype": "static",
            "priority_boost": self.priority_boost,
            "min_similarity_score": self.min_similarity_score,
            "schema_json": json.dumps(
                {
                    "function": {
                        "name": self.name,
                        "description": self.description,
                        "parameters": self.parameters,
                    }
                }
            ),
            "_contract_version": self.version,
        }


class ToolContractRegistry:
    """Registry for all tool contracts.

    SINGLE INSTANCE that must be used for all tool metadata operations.

    Usage:
        registry = ToolContractRegistry.get_instance()
        registry.register(contract)
        contracts = registry.get_by_domain("finance_crypto")
        keywords = registry.get_domain_keywords()
    """

    _instance: ToolContractRegistry | None = None

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._contracts: dict[str, ToolContract] = {}
        self._domains: dict[str, set[str]] = {}  # domain -> set of tool_ids
        self._initialized: bool = False
        self._logger = structlog.get_logger(__name__)

    @classmethod
    def get_instance(cls) -> ToolContractRegistry:
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing only)."""
        cls._instance = None

    def register(self, contract: ToolContract) -> None:
        """Register a tool contract.

        Args:
            contract: ToolContract to register

        Raises:
            ValueError: If contract with same tool_id already exists
        """
        if contract.tool_id in self._contracts:
            raise ValueError(f"Contract with tool_id '{contract.tool_id}' already registered")

        self._contracts[contract.tool_id] = contract

        if contract.domain not in self._domains:
            self._domains[contract.domain] = set()
        self._domains[contract.domain].add(contract.tool_id)

        self._logger.debug(
            "tool_contract_registered",
            tool_id=contract.tool_id,
            domain=contract.domain,
        )

    def register_batch(self, contracts: list[ToolContract]) -> int:
        """Register multiple contracts at once.

        Args:
            contracts: List of ToolContract to register

        Returns:
            Number of contracts registered
        """
        count = 0
        for contract in contracts:
            try:
                self.register(contract)
                count += 1
            except ValueError as e:
                self._logger.warning(
                    "contract_registration_failed",
                    tool_id=contract.tool_id,
                    error=str(e),
                )
        return count

    def get(self, tool_id: str) -> ToolContract | None:
        """Get contract by tool_id.

        Args:
            tool_id: Unique tool identifier

        Returns:
            ToolContract if found, None otherwise
        """
        return self._contracts.get(tool_id)

    def get_by_domain(self, domain: str) -> list[ToolContract]:
        """Get all contracts for a domain.

        Args:
            domain: Domain name (e.g., 'finance_crypto')

        Returns:
            List of ToolContract for the domain
        """
        tool_ids = self._domains.get(domain, set())
        return [self._contracts[tid] for tid in tool_ids if tid in self._contracts]

    def get_all(self) -> list[ToolContract]:
        """Get all registered contracts.

        Returns:
            List of all ToolContract
        """
        return list(self._contracts.values())

    def get_domain_keywords(self) -> dict[str, list[str]]:
        """Generate keyword map for domain classifier from contracts.

        Aggregates keywords from all contracts in each domain.

        Returns:
            Dictionary mapping domain -> list of unique keywords
        """
        keywords: dict[str, set[str]] = {}
        for contract in self._contracts.values():
            if contract.domain not in keywords:
                keywords[contract.domain] = set()
            keywords[contract.domain].update(contract.keywords)

        return {d: list(kw) for d, kw in keywords.items()}

    def get_tool_domains(self) -> dict[str, str]:
        """Generate tool_name -> domain map.

        Returns:
            Dictionary mapping tool name to domain
        """
        return {c.name: c.domain for c in self._contracts.values()}

    def get_domains(self) -> list[str]:
        """Get list of all registered domains.

        Returns:
            List of domain names
        """
        return list(self._domains.keys())

    def is_registered(self, tool_id: str) -> bool:
        """Check if a tool is registered.

        Args:
            tool_id: Tool identifier to check

        Returns:
            True if registered, False otherwise
        """
        return tool_id in self._contracts

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dictionary with stats (contract count, domain count, etc.)
        """
        return {
            "total_contracts": len(self._contracts),
            "total_domains": len(self._domains),
            "contracts_by_domain": {
                domain: len(tool_ids) for domain, tool_ids in self._domains.items()
            },
            "initialized": self._initialized,
        }

    def sync_to_yaml_string(self) -> str:
        """Generate YAML string from all contracts.

        Returns:
            YAML-formatted string of tool hierarchy
        """
        import yaml

        hierarchy: dict[str, Any] = {}

        for contract in self._contracts.values():
            if contract.domain not in hierarchy:
                hierarchy[contract.domain] = {}
            if contract.category not in hierarchy[contract.domain]:
                hierarchy[contract.domain][contract.category] = {}
            if contract.skill not in hierarchy[contract.domain][contract.category]:
                hierarchy[contract.domain][contract.category][contract.skill] = {}

            hierarchy[contract.domain][contract.category][contract.skill][contract.name] = {
                "description": contract.description,
                "version": contract.version,
                "risk_level": contract.risk_level.value
                if isinstance(contract.risk_level, RiskLevel)
                else contract.risk_level,
            }

        return yaml.dump(hierarchy, default_flow_style=False, sort_keys=False)
