"""Productivity Domain Package."""

from me4brain.domains.productivity.handler import ProductivityHandler


def get_handler() -> ProductivityHandler:
    return ProductivityHandler()


__all__ = ["ProductivityHandler", "get_handler"]
