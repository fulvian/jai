"""Utility Domain Package."""

from me4brain.domains.utility.handler import UtilityHandler


def get_handler() -> UtilityHandler:
    return UtilityHandler()


__all__ = ["UtilityHandler", "get_handler"]
