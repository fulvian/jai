"""Travel Domain - Flights and Airports APIs."""

from .handler import TravelHandler


def get_handler() -> TravelHandler:
    """Factory function for domain handler discovery."""
    return TravelHandler()


__all__ = ["TravelHandler", "get_handler"]
