"""Unit tests for PluginRegistry routing logic."""

import pytest

from me4brain.core.interfaces import DomainHandler, DomainCapability, DomainVolatility
from me4brain.core.plugin_registry import PluginRegistry


class MockHandler(DomainHandler):
    """Mock handler for testing."""

    def __init__(self, domain_name: str, keywords: set[str], base_score: float = 0.5):
        self._domain_name = domain_name
        self._keywords = keywords
        self._base_score = base_score

    @property
    def domain_name(self) -> str:
        return self._domain_name

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.STATIC

    @property
    def default_ttl_hours(self) -> int:
        return 24

    @property
    def capabilities(self) -> list[DomainCapability]:
        return []

    async def initialize(self) -> None:
        pass

    async def can_handle(self, query: str, analysis: dict) -> float:
        query_lower = query.lower()
        matches = sum(1 for kw in self._keywords if kw in query_lower)
        if matches == 0:
            return 0.0
        return min(0.9, self._base_score + matches * 0.1)

    async def execute(self, query: str, analysis: dict, context: dict):
        return []

    def handles_service(self, service_name: str) -> bool:
        return False

    async def execute_tool(self, tool_name: str, arguments: dict):
        return {}


class TestPluginRegistryRouting:
    """Test routing logic with web_search penalty."""

    @pytest.fixture
    async def registry(self):
        """Create registry with mock handlers."""
        registry = PluginRegistry(tenant_id="test")

        # Register handlers
        web_search = MockHandler(
            "web_search",
            {"cerca", "search", "trova", "web", "google"},
            base_score=0.25,
        )
        sports_nba = MockHandler(
            "sports_nba",
            {"lakers", "celtics", "nba", "basket", "partita"},
            base_score=0.4,
        )
        finance = MockHandler(
            "finance_crypto",
            {"bitcoin", "btc", "crypto", "ethereum"},
            base_score=0.5,
        )

        await registry.register(web_search)
        await registry.register(sports_nba)
        await registry.register(finance)

        return registry

    @pytest.mark.asyncio
    async def test_specific_handler_preferred_over_web_search(self, registry):
        """When a specific handler matches, it should be preferred over web_search."""
        # Query with NBA keywords + generic "cerca"
        query = "cerca statistiche Lakers"

        handler = await registry.route_query(query, {})

        assert handler is not None
        assert handler.domain_name == "sports_nba"

    @pytest.mark.asyncio
    async def test_web_search_used_when_no_specific_handler(self, registry):
        """web_search should be used when no specific handler matches."""
        # Query with only generic keywords
        query = "cerca su google le ultime notizie"

        handler = await registry.route_query(query, {})

        assert handler is not None
        assert handler.domain_name == "web_search"

    @pytest.mark.asyncio
    async def test_finance_handler_preferred(self, registry):
        """Finance handler should be preferred for crypto queries."""
        query = "trova prezzo bitcoin"

        handler = await registry.route_query(query, {})

        assert handler is not None
        assert handler.domain_name == "finance_crypto"

    @pytest.mark.asyncio
    async def test_min_score_threshold_lowered(self, registry):
        """min_score threshold should be 0.4 (was 0.5)."""
        # Query with only 1 NBA keyword (score = 0.4 + 0.1 = 0.5)
        query = "Lakers"

        handler = await registry.route_query(query, {})

        assert handler is not None
        assert handler.domain_name == "sports_nba"

    @pytest.mark.asyncio
    async def test_no_handler_when_below_threshold(self, registry):
        """No handler should be returned when all scores are below threshold."""
        # Query with no matching keywords
        query = "xyz abc def"

        handler = await registry.route_query(query, {})

        assert handler is None
