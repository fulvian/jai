"""Food & Recipes API Tools - TheMealDB, Open Food Facts.

Tutti i tool sono 100% gratuiti e senza limiti:
- TheMealDB: Ricette, ingredienti, categorie
- Open Food Facts: Database prodotti alimentari
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

TIMEOUT = 15.0


# =============================================================================
# TheMealDB - Ricette (100% Gratuito)
# =============================================================================


async def mealdb_search(query: str) -> dict[str, Any]:
    """Cerca ricette per nome.

    Args:
        query: Nome piatto

    Returns:
        dict con ricette trovate
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://www.themealdb.com/api/json/v1/1/search.php",
                params={"s": query},
            )
            resp.raise_for_status()
            data = resp.json()

            meals = []
            for m in data.get("meals") or []:
                # Estrai ingredienti
                ingredients = []
                for i in range(1, 21):
                    ing = m.get(f"strIngredient{i}")
                    measure = m.get(f"strMeasure{i}")
                    if ing and ing.strip():
                        ingredients.append(f"{measure} {ing}".strip())

                meals.append(
                    {
                        "id": m.get("idMeal"),
                        "name": m.get("strMeal"),
                        "category": m.get("strCategory"),
                        "area": m.get("strArea"),
                        "instructions": m.get("strInstructions", "")[:500],
                        "ingredients": ingredients[:10],
                        "thumbnail": m.get("strMealThumb"),
                        "youtube": m.get("strYoutube"),
                    }
                )

            return {
                "query": query,
                "results": meals,
                "count": len(meals),
                "source": "TheMealDB",
            }

    except Exception as e:
        logger.error("mealdb_search_error", error=str(e))
        return {"error": str(e), "source": "TheMealDB"}


async def mealdb_random() -> dict[str, Any]:
    """Ottieni una ricetta casuale."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get("https://www.themealdb.com/api/json/v1/1/random.php")
            resp.raise_for_status()
            data = resp.json()

            m = (data.get("meals") or [{}])[0]
            if not m:
                return {"error": "Nessuna ricetta trovata", "source": "TheMealDB"}

            # Estrai ingredienti
            ingredients = []
            for i in range(1, 21):
                ing = m.get(f"strIngredient{i}")
                measure = m.get(f"strMeasure{i}")
                if ing and ing.strip():
                    ingredients.append(f"{measure} {ing}".strip())

            return {
                "id": m.get("idMeal"),
                "name": m.get("strMeal"),
                "category": m.get("strCategory"),
                "area": m.get("strArea"),
                "instructions": m.get("strInstructions"),
                "ingredients": ingredients,
                "thumbnail": m.get("strMealThumb"),
                "youtube": m.get("strYoutube"),
                "source": "TheMealDB",
            }

    except Exception as e:
        logger.error("mealdb_random_error", error=str(e))
        return {"error": str(e), "source": "TheMealDB"}


async def mealdb_by_ingredient(ingredient: str) -> dict[str, Any]:
    """Cerca ricette per ingrediente.

    Args:
        ingredient: Ingrediente principale

    Returns:
        dict con ricette
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://www.themealdb.com/api/json/v1/1/filter.php",
                params={"i": ingredient},
            )
            resp.raise_for_status()
            data = resp.json()

            meals = []
            for m in data.get("meals") or []:
                meals.append(
                    {
                        "id": m.get("idMeal"),
                        "name": m.get("strMeal"),
                        "thumbnail": m.get("strMealThumb"),
                    }
                )

            return {
                "ingredient": ingredient,
                "results": meals,
                "count": len(meals),
                "source": "TheMealDB",
            }

    except Exception as e:
        logger.error("mealdb_by_ingredient_error", error=str(e))
        return {"error": str(e), "source": "TheMealDB"}


async def mealdb_categories() -> dict[str, Any]:
    """Lista categorie di ricette."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get("https://www.themealdb.com/api/json/v1/1/categories.php")
            resp.raise_for_status()
            data = resp.json()

            categories = []
            for c in data.get("categories") or []:
                categories.append(
                    {
                        "id": c.get("idCategory"),
                        "name": c.get("strCategory"),
                        "description": c.get("strCategoryDescription", "")[:200],
                        "thumbnail": c.get("strCategoryThumb"),
                    }
                )

            return {
                "categories": categories,
                "count": len(categories),
                "source": "TheMealDB",
            }

    except Exception as e:
        logger.error("mealdb_categories_error", error=str(e))
        return {"error": str(e), "source": "TheMealDB"}


# =============================================================================
# Open Food Facts - Prodotti Alimentari (100% Gratuito)
# =============================================================================


async def openfoodfacts_search(query: str, page_size: int = 10) -> dict[str, Any]:
    """Cerca prodotti alimentari.

    Args:
        query: Nome prodotto
        page_size: Numero risultati

    Returns:
        dict con prodotti trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "search_terms": query,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": page_size,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            products = []
            for p in data.get("products", []):
                products.append(
                    {
                        "code": p.get("code"),
                        "name": p.get("product_name"),
                        "brand": p.get("brands"),
                        "categories": p.get("categories"),
                        "nutriscore": p.get("nutriscore_grade"),
                        "nova_group": p.get("nova_group"),
                        "ingredients": p.get("ingredients_text", "")[:200],
                        "image": p.get("image_url"),
                    }
                )

            return {
                "query": query,
                "results": products,
                "count": data.get("count", 0),
                "source": "Open Food Facts",
            }

    except Exception as e:
        logger.error("openfoodfacts_search_error", error=str(e))
        return {"error": str(e), "source": "Open Food Facts"}


async def openfoodfacts_product(barcode: str) -> dict[str, Any]:
    """Dettagli prodotto per barcode.

    Args:
        barcode: Codice a barre prodotto

    Returns:
        dict con dettagli prodotto
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != 1:
                return {
                    "error": f"Prodotto {barcode} non trovato",
                    "source": "Open Food Facts",
                }

            p = data.get("product", {})
            nutriments = p.get("nutriments", {})

            return {
                "code": p.get("code"),
                "name": p.get("product_name"),
                "brand": p.get("brands"),
                "categories": p.get("categories"),
                "ingredients": p.get("ingredients_text"),
                "nutriscore": p.get("nutriscore_grade"),
                "nova_group": p.get("nova_group"),
                "nutrition": {
                    "energy_kcal": nutriments.get("energy-kcal_100g"),
                    "fat": nutriments.get("fat_100g"),
                    "carbs": nutriments.get("carbohydrates_100g"),
                    "proteins": nutriments.get("proteins_100g"),
                    "salt": nutriments.get("salt_100g"),
                    "sugars": nutriments.get("sugars_100g"),
                },
                "allergens": p.get("allergens"),
                "image": p.get("image_url"),
                "source": "Open Food Facts",
            }

    except Exception as e:
        logger.error("openfoodfacts_product_error", error=str(e))
        return {"error": str(e), "source": "Open Food Facts"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # TheMealDB (Recipes)
    "mealdb_search": mealdb_search,
    "mealdb_random": mealdb_random,
    "mealdb_by_ingredient": mealdb_by_ingredient,
    "mealdb_categories": mealdb_categories,
    # Open Food Facts (Products)
    "openfoodfacts_search": openfoodfacts_search,
    "openfoodfacts_product": openfoodfacts_product,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool food per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown food tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Food tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # TheMealDB (Recipes)
        ToolDefinition(
            name="mealdb_search",
            description="Search for recipes by dish name. Returns ingredients, cooking instructions, and images. Use when user asks 'recipe for X', 'how to make Y', 'find dish Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Dish name or recipe to search (e.g., 'pasta carbonara', 'chicken curry')",
                    required=True,
                ),
            },
            domain="food",
            category="recipes",
        ),
        ToolDefinition(
            name="mealdb_random",
            description="Get a random recipe with full details. Use when user asks 'suggest a recipe', 'random meal idea', 'what should I cook today'.",
            parameters={},
            domain="food",
            category="recipes",
        ),
        ToolDefinition(
            name="mealdb_by_ingredient",
            description="Find recipes that use a specific ingredient. Use when user asks 'recipes with chicken', 'what can I make with eggs', 'dishes using tomatoes'.",
            parameters={
                "ingredient": ToolParameter(
                    type="string",
                    description="Main ingredient to search (e.g., 'chicken', 'beef', 'salmon')",
                    required=True,
                ),
            },
            domain="food",
            category="recipes",
        ),
        ToolDefinition(
            name="mealdb_categories",
            description="List all recipe categories available (Seafood, Breakfast, Dessert, etc.). Use when user asks 'what types of recipes', 'food categories', 'meal categories'.",
            parameters={},
            domain="food",
            category="recipes",
        ),
        # Open Food Facts (Products)
        ToolDefinition(
            name="openfoodfacts_search",
            description="Search food products database for nutrition info, ingredients, and nutriscore. Use when user asks 'nutrition facts for X', 'is Y healthy', 'ingredients in Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Product name to search (e.g., 'Nutella', 'Coca-Cola')",
                    required=True,
                ),
                "page_size": ToolParameter(
                    type="integer",
                    description="Number of results to return",
                    required=False,
                ),
            },
            domain="food",
            category="products",
        ),
        ToolDefinition(
            name="openfoodfacts_product",
            description="Get complete product information by barcode (EAN/UPC). Returns nutrition, ingredients, allergens, nutriscore. Use when user scans a barcode or asks 'barcode lookup'.",
            parameters={
                "barcode": ToolParameter(
                    type="string",
                    description="Product barcode (EAN/UPC, e.g., '8000500310427')",
                    required=True,
                ),
            },
            domain="food",
            category="products",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
