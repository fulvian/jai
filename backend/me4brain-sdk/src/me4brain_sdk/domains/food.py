"""Food Domain - Recipes, Nutrition, Meal planning."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class Recipe(BaseModel):
    """Recipe information."""

    id: str
    name: str
    instructions: str | None = None
    category: str | None = None
    cuisine: str | None = None
    image_url: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class NutritionInfo(BaseModel):
    """Nutrition information."""

    product_name: str
    brands: str | None = None
    calories: float | None = None
    proteins: float | None = None
    carbohydrates: float | None = None
    fat: float | None = None
    fiber: float | None = None
    nutriscore: str | None = None


class FoodDomain(BaseDomain):
    """Food domain - recipes, nutrition, meal planning.

    Example:
        # Search recipes
        recipes = await client.domains.food.recipe_search("pasta carbonara")

        # Get nutrition info
        nutrition = await client.domains.food.nutrition_lookup("12345678")
    """

    @property
    def domain_name(self) -> str:
        return "food"

    async def recipe_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[Recipe]:
        """Search recipes (TheMealDB).

        Args:
            query: Recipe name search
            max_results: Maximum results

        Returns:
            List of recipes
        """
        result = await self._execute_tool(
            "mealdb_search",
            {"query": query, "max_results": max_results},
        )
        recipes = result.get("result", {}).get("recipes", [])
        return [Recipe.model_validate(r) for r in recipes]

    async def recipe_by_id(self, recipe_id: str) -> Recipe:
        """Get recipe details by ID.

        Args:
            recipe_id: Recipe ID

        Returns:
            Recipe details with instructions
        """
        result = await self._execute_tool("mealdb_recipe", {"recipe_id": recipe_id})
        return Recipe.model_validate(result.get("result", {}))

    async def recipes_by_category(
        self,
        category: str,
        max_results: int = 10,
    ) -> list[Recipe]:
        """Get recipes by category.

        Args:
            category: Category name (e.g., "Seafood", "Vegetarian")
            max_results: Maximum results

        Returns:
            List of recipes
        """
        result = await self._execute_tool(
            "mealdb_category",
            {"category": category, "max_results": max_results},
        )
        recipes = result.get("result", {}).get("recipes", [])
        return [Recipe.model_validate(r) for r in recipes]

    async def nutrition_lookup(self, barcode: str) -> NutritionInfo:
        """Get nutrition by barcode (Open Food Facts).

        Args:
            barcode: Product barcode

        Returns:
            Nutrition information
        """
        result = await self._execute_tool("openfoodfacts_lookup", {"barcode": barcode})
        return NutritionInfo.model_validate(result.get("result", {}))

    async def nutrition_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[NutritionInfo]:
        """Search food products.

        Args:
            query: Product search query
            max_results: Maximum results

        Returns:
            List of products with nutrition
        """
        result = await self._execute_tool(
            "openfoodfacts_search",
            {"query": query, "max_results": max_results},
        )
        products = result.get("result", {}).get("products", [])
        return [NutritionInfo.model_validate(p) for p in products]
