"""Food Domain Handler."""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class FoodHandler(DomainHandler):
    """Handler per Ricette e Prodotti Alimentari."""

    HANDLED_SERVICES = frozenset({"TheMealDBService", "OpenFoodFactsService"})

    FOOD_KEYWORDS = frozenset(
        {
            # Ricette
            "ricetta",
            "cucinare",
            "ingrediente",
            "piatto",
            "cucina",
            "pranzo",
            "cena",
            "colazione",
            "dessert",
            "dolce",
            # Prodotti
            "prodotto",
            "alimento",
            "nutriscore",
            "calorie",
            "proteine",
            "carboidrati",
            "grassi",
            "barcode",
            "nutrienti",
            "etichetta",
        }
    )

    @property
    def domain_name(self) -> str:
        return "food"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="recipes",
                description="Cerca ricette (TheMealDB)",
                required_params=["query"],
            ),
            DomainCapability(
                name="food_products",
                description="Info prodotti alimentari (Open Food Facts)",
                required_params=["query"],
                optional_params=["barcode"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.STABLE

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Check if this handler can process the query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.FOOD_KEYWORDS if kw in query_lower)
        if matches >= 2:
            return 0.9
        elif matches == 1:
            return 0.7
        return 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from .tools.food_api import execute_tool

        query_lower = query.lower()
        results = []

        if any(kw in query_lower for kw in ["ricetta", "cucinare", "piatto", "cucina"]):
            data = await execute_tool("mealdb_search", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="mealdb_search",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        if any(kw in query_lower for kw in ["prodotto", "alimento", "calorie", "nutri"]):
            data = await execute_tool("openfoodfacts_search", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="openfoodfacts_search",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        if not results:
            data = await execute_tool("mealdb_search", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="mealdb_search",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        return results
