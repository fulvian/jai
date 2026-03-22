"""Entertainment Domain - Movies, Books, Music APIs."""

from .handler import EntertainmentHandler


def get_handler() -> EntertainmentHandler:
    """Factory function for domain handler discovery."""
    return EntertainmentHandler()


__all__ = ["EntertainmentHandler", "get_handler"]
