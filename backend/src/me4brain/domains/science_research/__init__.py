"""Science & Research Domain Package.

Implementa domain handler per ricerca accademica:
- ArXiv: Preprint fisica, matematica, CS
- Crossref: DOI e metadata
- Europe PMC: Life sciences
- OpenAlex: Knowledge graph accademico
- Semantic Scholar: Paper graph
- PubMed: Articoli biomedicali

Volatilità: STABLE (paper non cambiano frequentemente)
"""

from me4brain.domains.science_research.handler import ScienceResearchHandler


def get_handler() -> ScienceResearchHandler:
    """Factory function for domain handler discovery."""
    return ScienceResearchHandler()


__all__ = ["ScienceResearchHandler", "get_handler"]
