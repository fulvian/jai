"""Shopping Domain Package."""

from me4brain.domains.shopping.handler import ShoppingHandler


def get_handler() -> ShoppingHandler:
    return ShoppingHandler()


__all__ = ["ShoppingHandler", "get_handler"]
