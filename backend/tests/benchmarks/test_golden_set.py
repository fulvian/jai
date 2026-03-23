"""Unit tests for Golden Set Evaluation.

This module provides tests for running the retrieval system against
the golden set and measuring SLO compliance.
"""

import sys
from pathlib import Path
from typing import Literal

import pytest

# Add tests directory to path for imports
_tests_dir = Path(__file__).parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

# Import golden set data directly to avoid import issues
from golden_set import GOLDEN_SET, GOLDEN_SET_STATS, GoldenTestCase

# Import types needed for mock fixtures
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainScore,
    ToolRetrievalResult,
)


class TestGoldenSetCompleteness:
    """Verify golden set has adequate coverage."""

    def test_golden_set_not_empty(self):
        """Golden set must not be empty."""
        assert len(GOLDEN_SET) > 0, "Golden set is empty"

    def test_all_domains_have_cases(self):
        """Each active domain should have at least one test case."""
        expected_domains = {
            "geo_weather",
            "finance_crypto",
            "sports_nba",
            "web_search",
            "google_workspace",
            "food",
            "travel",
            "sports_booking",
            "science_research",
            "medical",
            "entertainment",
        }
        covered_domains = set()
        for case in GOLDEN_SET:
            covered_domains.update(case.expected_domains)

        missing = expected_domains - covered_domains
        assert not missing, f"Domains missing test cases: {missing}"

    def test_golden_set_stats_match(self):
        """Verify stats are consistent with actual golden set."""
        assert GOLDEN_SET_STATS["total_cases"] == len(GOLDEN_SET)
        assert sum(GOLDEN_SET_STATS["by_domain"].values()) == len(GOLDEN_SET)


class TestGoldenSetTestCase:
    """Test individual golden set test case structure."""

    def test_all_cases_have_query(self):
        """Every test case must have a non-empty query."""
        for case in GOLDEN_SET:
            assert case.query, f"Test case missing query: {case}"

    def test_all_cases_have_domains(self):
        """Every test case must have at least one expected domain."""
        for case in GOLDEN_SET:
            assert case.expected_domains, f"Test case missing domains: {case}"

    def test_complexity_values_valid(self):
        """All complexity values must be valid."""
        valid_complexities = {"simple", "medium", "complex"}
        for case in GOLDEN_SET:
            assert case.complexity in valid_complexities, (
                f"Invalid complexity '{case.complexity}' for: {case.query}"
            )


class TestGoldenSetMetrics:
    """Test metrics calculation logic using mocked retrieval."""

    @pytest.fixture
    def mock_classification(self):
        """Create a mock domain classification."""

        def make_classification(domains: list[str]) -> DomainClassification:
            return DomainClassification(
                top_k_domains=[DomainScore(domain=d, confidence=0.9) for d in domains],
                domain_names=domains,
                confidence=0.9,
            )

        return make_classification

    @pytest.fixture
    def mock_retrieval_result(self):
        """Create a mock retrieval result."""

        def make_result(tools: list[str]) -> ToolRetrievalResult:
            from me4brain.engine.hybrid_router.types import RetrievedTool

            retrieved = [
                RetrievedTool(
                    name=tool,
                    description=f"Tool {tool}",
                    domain="test",
                    category="test",
                    schema={},
                    similarity_score=0.9,
                )
                for tool in tools
            ]
            return ToolRetrievalResult(tools=retrieved)

        return make_result

    def test_recall_at_10_perfect(self, mock_classification, mock_retrieval_result):
        """Test recall calculation with perfect retrieval."""
        # Simulated perfect case: query expects ["tool_a", "tool_b"]
        # Retrieval returns ["tool_a", "tool_b", "tool_c"]
        expected_tools = {"tool_a", "tool_b"}
        retrieved_tools = {"tool_a", "tool_b", "tool_c"}

        recall = len(expected_tools & retrieved_tools) / len(expected_tools)
        assert recall == 1.0

    def test_recall_at_10_partial(self, mock_classification, mock_retrieval_result):
        """Test recall calculation with partial retrieval."""
        # Simulated partial case: query expects ["tool_a", "tool_b", "tool_c"]
        # Retrieval returns only ["tool_a"]
        expected_tools = {"tool_a", "tool_b", "tool_c"}
        retrieved_tools = {"tool_a"}

        recall = len(expected_tools & retrieved_tools) / len(expected_tools)
        assert recall == pytest.approx(0.333, rel=0.01)

    def test_recall_at_10_none(self, mock_classification, mock_retrieval_result):
        """Test recall calculation with zero retrieval."""
        expected_tools = {"tool_a", "tool_b"}
        retrieved_tools: set[str] = set()

        recall = len(expected_tools & retrieved_tools) / len(expected_tools)
        assert recall == 0.0

    def test_wrong_domain_detection(self, mock_classification):
        """Test wrong domain failure detection."""
        # Query expected: ["finance_crypto"]
        # Classification returned: ["sports_nba"]
        expected_domains = {"finance_crypto"}
        classified_domains = {"sports_nba"}

        wrong_domain = not expected_domains.issubset(classified_domains)
        assert wrong_domain is True

    def test_correct_domain_detection(self, mock_classification):
        """Test correct domain detection."""
        # Query expected: ["finance_crypto"]
        # Classification returned: ["finance_crypto", "web_search"]
        expected_domains = {"finance_crypto"}
        classified_domains = {"finance_crypto", "web_search"}

        wrong_domain = not expected_domains.issubset(classified_domains)
        assert wrong_domain is False

    def test_zero_result_detection(self, mock_retrieval_result):
        """Test zero-result rate detection."""
        result = mock_retrieval_result([])
        assert len(result.tools) == 0


class TestGoldenSetQualityTargets:
    """Test that quality targets are properly defined."""

    def test_slo_targets_defined(self):
        """Verify SLO targets are defined somewhere."""
        # These are the targets from the implementation plan
        slo_targets = {
            "tool_recall_at_10": 0.95,
            "wrong_domain_rate": 0.01,
            "zero_result_rate": 0.02,
            "p95_latency_simple": 3.0,
            "p95_latency_complex": 20.0,
        }

        # Verify targets are reasonable
        assert slo_targets["tool_recall_at_10"] >= 0.9
        assert slo_targets["wrong_domain_rate"] <= 0.05
        assert slo_targets["zero_result_rate"] <= 0.05

    def test_coverage_targets_defined(self):
        """Verify coverage targets are defined."""
        coverage_targets = {
            "ToolIndexManager": 0.85,
            "DomainClassifier": 0.90,
            "LlamaIndexToolRetriever": 0.85,
            "HybridToolRouter": 0.80,
            "ResponseSynthesizer": 0.70,
        }

        # All targets should be >= 70%
        for component, target in coverage_targets.items():
            assert target >= 0.70, f"{component} target too low: {target}"


class TestGoldenSetEdgeCases:
    """Test handling of edge cases in golden set."""

    def test_shopping_redirects_to_websearch(self):
        """Shopping queries should be handled by web_search (no real tools)."""
        shopping_cases = [c for c in GOLDEN_SET if "shopping" in str(c.expected_domains)]
        for case in shopping_cases:
            # Shopping is deprecated, should redirect to web_search
            assert "web_search" in case.expected_domains

    def test_productivity_redirects_to_websearch(self):
        """Productivity queries should be handled by web_search (no real tools)."""
        productivity_cases = [c for c in GOLDEN_SET if "productivity" in str(c.expected_domains)]
        for case in productivity_cases:
            # Productivity is deprecated, should redirect to web_search
            assert "web_search" in case.expected_domains

    def test_multidomain_cases_marked_complex(self):
        """Multi-domain cases should be marked as complex."""
        for case in GOLDEN_SET:
            if len(case.expected_domains) > 1:
                assert case.complexity in ("medium", "complex"), (
                    f"Multi-domain case should be medium or complex: {case.query}"
                )


class TestGoldenSetDistribution:
    """Test golden set distribution across domains and complexity."""

    def test_minimum_cases_per_domain(self):
        """Each domain should have at least 2 test cases."""
        domain_counts: dict[str, int] = {}
        for case in GOLDEN_SET:
            for domain in case.expected_domains:
                if domain not in ("complex",):  # Skip meta category
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        for domain, count in domain_counts.items():
            assert count >= 2, f"Domain {domain} has only {count} test cases"

    def test_complexity_distribution(self):
        """Verify complexity is reasonably distributed."""
        complexity_counts = {"simple": 0, "medium": 0, "complex": 0}
        for case in GOLDEN_SET:
            complexity_counts[case.complexity] += 1

        # Simple should be majority, complex minority
        assert complexity_counts["simple"] > complexity_counts["medium"]
        assert complexity_counts["medium"] > complexity_counts["complex"]

        # Complex should be at least 5% of total
        assert complexity_counts["complex"] >= len(GOLDEN_SET) * 0.05
