"""Medical Domain Package.

Handler per query mediche:
- RxNorm: Info farmaci, interazioni
- iCite: Metriche citazioni biomediche
- PubMed: Ricerca pubblicazioni biomediche

Volatilità: STABLE (dati farmaci cambiano raramente)
"""

from me4brain.domains.medical.handler import MedicalHandler


def get_handler() -> MedicalHandler:
    """Factory function for domain handler discovery.

    Called by PluginRegistry during auto-discovery.
    """
    return MedicalHandler()


__all__ = ["MedicalHandler", "get_handler"]
