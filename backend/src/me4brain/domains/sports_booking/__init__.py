"""Sports Booking Domain.

Dominio per prenotazione campi sportivi (padel, tennis) tramite Playtomic.
"""

from .handler import SportsBookingHandler


def get_handler() -> SportsBookingHandler:
    """Factory function per ottenere l'handler del dominio."""
    return SportsBookingHandler()


__all__ = ["SportsBookingHandler", "get_handler"]
