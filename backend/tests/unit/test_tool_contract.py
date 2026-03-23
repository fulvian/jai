"""Tests for Canonical Tool Contract schema.

These tests verify the ToolContract model and ToolContractRegistry singleton.
"""

from __future__ import annotations

from typing import Any

import pytest

from me4brain.engine.tool_contract import (
    LatencyClass,
    RiskLevel,
    ToolContract,
    ToolContractRegistry,
)


class TestToolContract:
    """Test ToolContract model validation and methods."""

    def test_create_minimal_contract(self) -> None:
        """Test creating a minimal valid contract."""
        contract = ToolContract(
            tool_id="gmail_search",
            domain="google_workspace",
            category="gmail",
            skill="search",
            name="gmail_search",
            description="Search emails in Gmail",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
            embedding_hint="Search Gmail emails by keywords",
        )

        assert contract.tool_id == "gmail_search"
        assert contract.domain == "google_workspace"
        assert contract.category == "gmail"
        assert contract.skill == "search"
        assert contract.name == "gmail_search"
        assert contract.description == "Search emails in Gmail"
        assert contract.risk_level == RiskLevel.MEDIUM
        assert contract.latency_class == LatencyClass.NORMAL
        assert contract.deprecation_status == "active"
        assert contract.version == "1.0.0"

    def test_create_full_contract(self) -> None:
        """Test creating a contract with all fields."""
        contract = ToolContract(
            tool_id="coingecko_price",
            domain="finance_crypto",
            category="crypto",
            skill="price",
            name="coingecko_price",
            description="Get cryptocurrency price from CoinGecko",
            parameters={
                "type": "object",
                "properties": {
                    "coin_id": {"type": "string", "description": "Coin ID (e.g., bitcoin)"},
                    "vs_currencies": {"type": "string", "description": "Quote currency"},
                },
                "required": ["coin_id"],
            },
            risk_level=RiskLevel.LOW,
            latency_class=LatencyClass.FAST,
            auth_requirements=["api_key"],
            version="2.1.0",
            schema_version="2026.1",
            deprecation_status="active",
            deprecated_aliases=["crypto_price", "coin_price"],
            aliases=["btc_price", "eth_price"],
            keywords=["crypto", "bitcoin", "price", "coin"],
            not_suitable_for=["stock", "forex"],
            embedding_hint="Get real-time cryptocurrency prices from CoinGecko API",
            priority_boost=1.2,
        )

        # Note: use_enum_values=True means enums are stored as their values (strings)
        assert contract.risk_level == "low"
        assert contract.latency_class == "fast"
        assert contract.auth_requirements == ["api_key"]
        assert contract.version == "2.1.0"
        assert contract.deprecated_aliases == ["crypto_price", "coin_price"]
        assert contract.aliases == ["btc_price", "eth_price"]
        assert contract.keywords == ["crypto", "bitcoin", "price", "coin"]
        assert contract.not_suitable_for == ["stock", "forex"]
        assert contract.priority_boost == 1.2

    def test_contract_validation_missing_required(self) -> None:
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ToolContract(
                tool_id="test_tool",
                # Missing required fields
            )

    def test_contract_validation_invalid_tool_id(self) -> None:
        """Test that invalid tool_id is rejected."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ToolContract(
                tool_id="invalid tool id!",  # Contains spaces and special chars
                domain="test_domain",
                category="test_category",
                skill="test_skill",
                name="test_tool",
                description="Test description",
                parameters={"type": "object"},
                embedding_hint="Test hint",
            )

    def test_contract_to_tool_definition(self) -> None:
        """Test converting contract to OpenAI tool definition."""
        contract = ToolContract(
            tool_id="test_tool",
            domain="test_domain",
            category="test_category",
            skill="test_skill",
            name="test_tool",
            description="Test tool description",
            parameters={
                "type": "object",
                "properties": {"param1": {"type": "string"}},
            },
            embedding_hint="Test embedding hint",
        )

        tool_def = contract.to_tool_definition()

        assert tool_def["name"] == "test_tool"
        assert tool_def["description"] == "Test tool description"
        # Domain info is stored with underscore prefix to avoid conflicts
        assert tool_def["_domain"] == "test_domain"
        assert tool_def["_category"] == "test_category"
        assert "param1" in tool_def["parameters"]["properties"]

    def test_contract_to_qdrant_metadata(self) -> None:
        """Test converting contract to Qdrant payload metadata."""
        contract = ToolContract(
            tool_id="test_tool",
            domain="test_domain",
            category="test_category",
            skill="test_skill",
            name="test_tool",
            description="Test tool description",
            parameters={"type": "object"},
            risk_level=RiskLevel.HIGH,
            latency_class=LatencyClass.SLOW,
            embedding_hint="Test embedding hint",
            priority_boost=1.5,
        )

        metadata = contract.to_qdrant_metadata()

        assert metadata["tool_name"] == "test_tool"
        assert metadata["domain"] == "test_domain"
        assert metadata["category"] == "test_category"
        assert metadata["skill"] == "test_skill"
        assert metadata["risk_level"] == "high"
        assert metadata["latency_class"] == "slow"
        assert metadata["priority_boost"] == 1.5
        assert metadata["type"] == "tool"
        assert metadata["subtype"] == "static"
        assert "_contract_version" in metadata


class TestToolContractRegistry:
    """Test ToolContractRegistry singleton."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        # Reset singleton for testing
        ToolContractRegistry._instance = None

    def teardown_method(self) -> None:
        """Reset registry after each test."""
        ToolContractRegistry._instance = None

    def test_singleton_pattern(self) -> None:
        """Test that get_instance returns same instance."""
        registry1 = ToolContractRegistry.get_instance()
        registry2 = ToolContractRegistry.get_instance()

        assert registry1 is registry2

    def test_register_single_contract(self) -> None:
        """Test registering a single contract."""
        registry = ToolContractRegistry.get_instance()

        contract = ToolContract(
            tool_id="test_tool",
            domain="test_domain",
            category="test_category",
            skill="test_skill",
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            embedding_hint="Test",
        )

        registry.register(contract)

        assert registry.get("test_tool") is contract
        assert len(registry.get_all()) == 1

    def test_register_batch(self) -> None:
        """Test registering multiple contracts at once."""
        registry = ToolContractRegistry.get_instance()

        contracts = [
            ToolContract(
                tool_id=f"tool_{i}",
                domain="test_domain",
                category="test_category",
                skill="test_skill",
                name=f"tool_{i}",
                description=f"Tool {i}",
                parameters={"type": "object"},
                embedding_hint="Test",
            )
            for i in range(3)
        ]

        count = registry.register_batch(contracts)

        assert count == 3
        assert len(registry.get_all()) == 3

    def test_get_by_domain(self) -> None:
        """Test getting contracts by domain."""
        registry = ToolContractRegistry.get_instance()

        contracts = [
            ToolContract(
                tool_id="tool_1",
                domain="finance_crypto",
                category="crypto",
                skill="price",
                name="tool_1",
                description="Tool 1",
                parameters={"type": "object"},
                embedding_hint="Test",
            ),
            ToolContract(
                tool_id="tool_2",
                domain="finance_crypto",
                category="crypto",
                skill="trending",
                name="tool_2",
                description="Tool 2",
                parameters={"type": "object"},
                embedding_hint="Test",
            ),
            ToolContract(
                tool_id="tool_3",
                domain="google_workspace",
                category="gmail",
                skill="search",
                name="tool_3",
                description="Tool 3",
                parameters={"type": "object"},
                embedding_hint="Test",
            ),
        ]

        registry.register_batch(contracts)

        finance_contracts = registry.get_by_domain("finance_crypto")
        assert len(finance_contracts) == 2

        gmail_contracts = registry.get_by_domain("google_workspace")
        assert len(gmail_contracts) == 1

    def test_get_domain_keywords(self) -> None:
        """Test generating keyword map from contracts."""
        registry = ToolContractRegistry.get_instance()

        contracts = [
            ToolContract(
                tool_id="tool_1",
                domain="finance_crypto",
                category="crypto",
                skill="price",
                name="tool_1",
                description="Tool 1",
                parameters={"type": "object"},
                keywords=["crypto", "bitcoin", "price"],
                embedding_hint="Test",
            ),
            ToolContract(
                tool_id="tool_2",
                domain="finance_crypto",
                category="crypto",
                skill="trending",
                name="tool_2",
                description="Tool 2",
                parameters={"type": "object"},
                keywords=["crypto", "trending", "popular"],
                embedding_hint="Test",
            ),
            ToolContract(
                tool_id="tool_3",
                domain="sports_nba",
                category="nba",
                skill="scores",
                name="tool_3",
                description="Tool 3",
                parameters={"type": "object"},
                keywords=["nba", "basketball", "scores"],
                embedding_hint="Test",
            ),
        ]

        registry.register_batch(contracts)

        keywords = registry.get_domain_keywords()

        assert "finance_crypto" in keywords
        assert set(keywords["finance_crypto"]) == {
            "crypto",
            "bitcoin",
            "price",
            "trending",
            "popular",
        }
        assert set(keywords["sports_nba"]) == {"nba", "basketball", "scores"}

    def test_get_tool_domains(self) -> None:
        """Test generating tool_name -> domain map."""
        registry = ToolContractRegistry.get_instance()

        contract = ToolContract(
            tool_id="coingecko_price",
            domain="finance_crypto",
            category="crypto",
            skill="price",
            name="coingecko_price",
            description="Get crypto price",
            parameters={"type": "object"},
            embedding_hint="Test",
        )

        registry.register(contract)

        tool_domains = registry.get_tool_domains()

        assert tool_domains == {"coingecko_price": "finance_crypto"}

    def test_sync_to_yaml_format(self) -> None:
        """Test YAML sync produces correct format."""
        registry = ToolContractRegistry.get_instance()

        contract = ToolContract(
            tool_id="test_tool",
            domain="test_domain",
            category="test_category",
            skill="test_skill",
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            embedding_hint="Test",
        )

        registry.register(contract)

        yaml_output = registry.sync_to_yaml_string()

        assert "test_domain:" in yaml_output
        assert "test_category:" in yaml_output
        assert "test_skill:" in yaml_output


class TestRiskLevelEnum:
    """Test RiskLevel enumeration."""

    def test_risk_level_values(self) -> None:
        """Test all risk levels exist."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestLatencyClassEnum:
    """Test LatencyClass enumeration."""

    def test_latency_class_values(self) -> None:
        """Test all latency classes exist."""
        assert LatencyClass.FAST.value == "fast"
        assert LatencyClass.NORMAL.value == "normal"
        assert LatencyClass.SLOW.value == "slow"
        assert LatencyClass.VARIABLE.value == "variable"
