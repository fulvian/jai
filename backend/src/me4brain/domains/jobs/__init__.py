"""Jobs Domain - Remote Work APIs."""

from .handler import JobsHandler


def get_handler() -> JobsHandler:
    """Factory function for domain handler discovery."""
    return JobsHandler()


__all__ = ["JobsHandler", "get_handler"]
