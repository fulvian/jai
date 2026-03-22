"""Tool Hierarchy Loader - Carica la configurazione gerarchica dei tool.

Mappa ogni tool a: domain > category > skill per retrieval più preciso.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Percorso al file di configurazione
HIERARCHY_FILE = Path(__file__).parent.parent.parent.parent.parent / "config" / "tool_hierarchy.yaml"


class ToolHierarchy:
    """Gestisce la mappatura gerarchica dei tool.

    Struttura: domain > category > skill > [tool_names]
    """

    def __init__(self) -> None:
        self._hierarchy: dict[str, dict[str, dict[str, list[str]]]] = {}
        self._tool_to_hierarchy: dict[
            str, tuple[str, str, str]
        ] = {}  # tool -> (domain, category, skill)
        self._loaded = False

    def load(self, path: Path | None = None) -> None:
        """Carica il file di configurazione YAML."""
        config_path = path or HIERARCHY_FILE

        if not config_path.exists():
            logger.warning("tool_hierarchy_file_not_found", path=str(config_path))
            self._loaded = True  # Mark as loaded to avoid repeated warnings
            return

        try:
            with open(config_path) as f:
                self._hierarchy = yaml.safe_load(f) or {}

            # Build reverse mapping: tool_name -> (domain, category, skill)
            for domain, categories in self._hierarchy.items():
                if not isinstance(categories, dict):
                    continue
                for category, skills in categories.items():
                    if not isinstance(skills, dict):
                        continue
                    for skill, tool_names in skills.items():
                        if not isinstance(tool_names, list):
                            continue
                        for tool_name in tool_names:
                            self._tool_to_hierarchy[tool_name] = (domain, category, skill)

            self._loaded = True
            logger.info(
                "tool_hierarchy_loaded",
                domains=len(self._hierarchy),
                total_tools=len(self._tool_to_hierarchy),
            )
        except Exception as e:
            logger.error("tool_hierarchy_load_failed", error=str(e))

    def get_hierarchy(self, tool_name: str) -> tuple[str, str, str]:
        """Ottiene domain, category, skill per un tool.

        Returns:
            Tuple (domain, category, skill). Se non trovato, ritorna ("", "", "").
        """
        if not self._loaded:
            self.load()

        return self._tool_to_hierarchy.get(tool_name, ("", "", ""))

    def get_category(self, tool_name: str) -> str:
        """Ottiene solo la category per un tool."""
        _, category, _ = self.get_hierarchy(tool_name)
        return category

    def get_skill(self, tool_name: str) -> str:
        """Ottiene solo la skill per un tool."""
        _, _, skill = self.get_hierarchy(tool_name)
        return skill

    def get_tools_by_category(self, domain: str, category: str) -> list[str]:
        """Ottiene tutti i tool per una specifica categoria."""
        if not self._loaded:
            self.load()

        result = []
        domain_data = self._hierarchy.get(domain, {})
        category_data = domain_data.get(category, {})

        for tool_list in category_data.values():
            if isinstance(tool_list, list):
                result.extend(tool_list)

        return result

    def get_categories_for_domain(self, domain: str) -> list[str]:
        """Ottiene tutte le categorie per un dominio."""
        if not self._loaded:
            self.load()

        domain_data = self._hierarchy.get(domain, {})
        return list(domain_data.keys()) if isinstance(domain_data, dict) else []

    def enrich_tool_metadata(self, tool_name: str, domain: str) -> dict[str, str]:
        """Arricchisce i metadata di un tool con category e skill.

        Returns:
            Dict con chiavi: domain, category, skill
        """
        hierarchy_domain, category, skill = self.get_hierarchy(tool_name)

        # Usa il dominio dalla gerarchia se presente, altrimenti quello passato
        final_domain = hierarchy_domain if hierarchy_domain else domain

        return {
            "domain": final_domain,
            "category": category,
            "skill": skill,
        }


# Singleton
_hierarchy: ToolHierarchy | None = None


def get_tool_hierarchy() -> ToolHierarchy:
    """Ottiene l'istanza singleton del ToolHierarchy."""
    global _hierarchy
    if _hierarchy is None:
        _hierarchy = ToolHierarchy()
        _hierarchy.load()
    return _hierarchy
