"""Prompt Hints Registry.

Provides domain and skill-specific hints for the IterativeExecutor
to improve tool parameter selection quality.

Usage:
    from me4brain.engine.prompts.registry import PromptHintsRegistry

    registry = PromptHintsRegistry()
    await registry.initialize()

    hints = registry.get_domain_hints("google_workspace")
    skill_hints = registry.get_skill_hints(skill_definition)
"""

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Default paths
CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config" / "prompt_hints"
DOMAINS_DIR = CONFIG_DIR / "domains"
SKILL_CATEGORIES_DIR = CONFIG_DIR / "skill_categories"


class PromptHintsRegistry:
    """Central registry for prompt hints."""

    _instance: "PromptHintsRegistry | None" = None

    def __init__(
        self,
        domains_dir: Path | None = None,
        skill_categories_dir: Path | None = None,
    ):
        """Initialize registry.

        Args:
            domains_dir: Path to domain hints YAML files
            skill_categories_dir: Path to skill category hints YAML files
        """
        self._domains_dir = domains_dir or DOMAINS_DIR
        self._skill_categories_dir = skill_categories_dir or SKILL_CATEGORIES_DIR

        # Cached hints
        self._domain_hints: dict[str, str] = {}
        self._skill_category_hints: dict[str, str] = {}
        self._skill_category_patterns: dict[str, list[str]] = {}

        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "PromptHintsRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance.initialize()
        return cls._instance

    async def initialize(self) -> None:
        """Load all hints from YAML files."""
        if self._initialized:
            return

        # Load domain hints
        await self._load_domain_hints()

        # Load skill category hints
        await self._load_skill_category_hints()

        self._initialized = True

        logger.info(
            "prompt_hints_registry_initialized",
            domain_count=len(self._domain_hints),
            skill_category_count=len(self._skill_category_hints),
        )

    async def _load_domain_hints(self) -> None:
        """Load domain hints from YAML files."""
        if not self._domains_dir.exists():
            logger.warning("domains_dir_not_found", path=str(self._domains_dir))
            return

        for yaml_file in self._domains_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and "hints" in data:
                    domain_name = yaml_file.stem  # filename without extension
                    self._domain_hints[domain_name] = data["hints"].strip()

                    logger.debug(
                        "domain_hints_loaded",
                        domain=domain_name,
                        hints_length=len(data["hints"]),
                    )

            except Exception as e:
                logger.error(
                    "domain_hints_load_error",
                    file=str(yaml_file),
                    error=str(e),
                )

    async def _load_skill_category_hints(self) -> None:
        """Load skill category hints from YAML files."""
        if not self._skill_categories_dir.exists():
            logger.warning(
                "skill_categories_dir_not_found",
                path=str(self._skill_categories_dir),
            )
            return

        for yaml_file in self._skill_categories_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data:
                    category_name = yaml_file.stem

                    # Store hints
                    if "hints" in data:
                        self._skill_category_hints[category_name] = data["hints"].strip()

                    # Store patterns for matching
                    if "patterns" in data:
                        self._skill_category_patterns[category_name] = data["patterns"]

                    logger.debug(
                        "skill_category_hints_loaded",
                        category=category_name,
                        patterns=data.get("patterns", []),
                    )

            except Exception as e:
                logger.error(
                    "skill_category_hints_load_error",
                    file=str(yaml_file),
                    error=str(e),
                )

    def get_domain_hints(self, domain: str) -> str:
        """Get hints for a specific domain.

        Args:
            domain: Domain name (e.g., 'google_workspace')

        Returns:
            Hints string or empty if not found
        """
        # Try exact match first
        if domain in self._domain_hints:
            return self._domain_hints[domain]

        # Fallback to _default
        return self._domain_hints.get("_default", "")

    def get_skill_hints(self, skill_id: str, skill_tags: list[str] | None = None) -> str:
        """Get hints for a skill based on its ID and tags.

        Uses pattern matching to categorize skills.

        Args:
            skill_id: Skill identifier (e.g., 'apple-calendar')
            skill_tags: Optional list of skill tags

        Returns:
            Hints string or generic hints if not categorized
        """
        # 1. Check patterns for matching
        for category, patterns in self._skill_category_patterns.items():
            for pattern in patterns:
                if self._matches_pattern(skill_id, pattern):
                    if category in self._skill_category_hints:
                        return self._skill_category_hints[category]

        # 2. Check tags if provided
        if skill_tags:
            for tag in skill_tags:
                if tag in self._skill_category_hints:
                    return self._skill_category_hints[tag]

        # 3. Fallback to _generic
        return self._skill_category_hints.get("_generic", "")

    def _matches_pattern(self, skill_id: str, pattern: str) -> bool:
        """Check if skill_id matches a pattern.

        Supports:
        - Prefix: 'apple-*' matches 'apple-calendar'
        - Suffix: '*-search' matches 'ebay-search'
        - Contains: '*scraper*' matches 'reddit-scraper'
        - Exact: 'postgres' matches 'postgres'
        """
        if pattern.startswith("*") and pattern.endswith("*"):
            # Contains
            return pattern[1:-1] in skill_id
        elif pattern.startswith("*"):
            # Suffix
            return skill_id.endswith(pattern[1:])
        elif pattern.endswith("*"):
            # Prefix
            return skill_id.startswith(pattern[:-1])
        else:
            # Exact
            return skill_id == pattern

    def categorize_skill(self, skill_id: str, skill_tags: list[str] | None = None) -> str:
        """Determine the category of a skill.

        Args:
            skill_id: Skill identifier
            skill_tags: Optional skill tags

        Returns:
            Category name or '_generic' if uncategorized
        """
        # Check patterns
        for category, patterns in self._skill_category_patterns.items():
            for pattern in patterns:
                if self._matches_pattern(skill_id, pattern):
                    return category

        # Check tags
        if skill_tags:
            for tag in skill_tags:
                if tag in self._skill_category_patterns:
                    return tag

        return "_generic"

    def get_combined_hints(
        self,
        domain: str,
        skill_ids: list[str] | None = None,
    ) -> str:
        """Get combined hints for domain and skills.

        Args:
            domain: Domain name
            skill_ids: Optional list of skill IDs

        Returns:
            Combined hints string
        """
        hints_parts = []

        # Domain hints
        domain_hints = self.get_domain_hints(domain)
        if domain_hints:
            hints_parts.append(f"[{domain.upper()}]\n{domain_hints}")

        # Skill hints (deduplicated by category)
        if skill_ids:
            seen_categories = set()
            for skill_id in skill_ids:
                category = self.categorize_skill(skill_id)
                if category not in seen_categories:
                    skill_hints = self.get_skill_hints(skill_id)
                    if skill_hints:
                        hints_parts.append(f"[{category.upper()}]\n{skill_hints}")
                    seen_categories.add(category)

        return "\n\n".join(hints_parts)

    async def refresh(self) -> None:
        """Reload hints from files (hot-reload)."""
        self._domain_hints.clear()
        self._skill_category_hints.clear()
        self._skill_category_patterns.clear()
        self._initialized = False

        await self.initialize()

        logger.info("prompt_hints_registry_refreshed")

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "domains_count": len(self._domain_hints),
            "domains": list(self._domain_hints.keys()),
            "skill_categories_count": len(self._skill_category_hints),
            "skill_categories": list(self._skill_category_hints.keys()),
            "patterns_count": sum(len(p) for p in self._skill_category_patterns.values()),
        }
