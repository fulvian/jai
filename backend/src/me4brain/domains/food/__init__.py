"""Food Domain - Recipes and Products APIs."""

from .handler import FoodHandler


def get_handler() -> FoodHandler:
    """Factory function for domain handler discovery."""
    return FoodHandler()


__all__ = ["FoodHandler", "get_handler"]
