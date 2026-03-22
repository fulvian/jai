"""Shopping Domain Handler - Marketplaces, Price Comparison, and Purchases."""

from datetime import UTC, datetime
from typing import Any
import structlog
from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class ShoppingHandler(DomainHandler):
    """Domain handler for shopping, marketplaces, and price comparison."""

    SHOPPING_KEYWORDS = frozenset(
        {
            "compra",
            "comprare",
            "acquista",
            "ordinare",
            "buy",
            "purchase",
            "order",
            "prezzo",
            "costo",
            "prezzi",
            "price",
            "deals",
            "offerte",
            "amazon",
            "ebay",
            "subito",
            "vinted",
            "wallapop",
            "marketplace",
            "usato",
            "secondhand",
            "used",
            "nuovo",
            "new",
            "confronta",
            "compara",
            "compare",
            "scelta",
            "esperto",
            "expert",
            "sconto",
            "discount",
            "sale",
        }
    )

    @property
    def domain_name(self) -> str:
        return "shopping"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.REAL_TIME

    @property
    def default_ttl_hours(self) -> int:
        return 1

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="product_search",
                description="Ricerca prodotti su molteplici marketplace (nuovo e usato)",
                keywords=["amazon", "ebay", "subito", "usato"],
                example_queries=[
                    "Cerca un iPhone usato su Subito",
                    "Trova il prezzo migliore per un Kindle",
                    "Cerca su Vinted",
                ],
            ),
            DomainCapability(
                name="purchase_automation",
                description="Automazione di acquisti e monitoraggio prezzi",
                keywords=["compra", "ordina", "monitora", "prezzo"],
                example_queries=[
                    "Compra questo prodotto su Amazon",
                    "Avvisami se il prezzo scende",
                ],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("shopping_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        matches = sum(1 for kw in self.SHOPPING_KEYWORDS if kw in query.lower())
        return min(0.9, matches * 0.25) if matches else 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        return []

    def handles_service(self, service_name: str) -> bool:
        return False

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.shopping.tools import shopping_api

        return await shopping_api.execute_tool(tool_name, arguments)
