"""Tech/Coding Domain - Developer Tools APIs."""

from .handler import TechCodingHandler


def get_handler() -> TechCodingHandler:
    """Factory function for domain handler discovery."""
    return TechCodingHandler()


__all__ = ["TechCodingHandler", "get_handler"]
