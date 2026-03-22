"""Skill Loader.

Discovers and loads skills from multiple sources:
- Workspace directory (~/.me4brain/skills/)
- Bundled skills (src/me4brain/skills/bundled/)
- ClawHub cache (~/.clawhub/skills/)
"""

import asyncio
from pathlib import Path
from typing import AsyncIterator

import structlog

from me4brain.skills.parser import SkillParser, SkillParseError
from me4brain.skills.types import (
    SkillDefinition,
    SkillSource,
    SkillStatus,
)

logger = structlog.get_logger(__name__)

# Default skill directories
DEFAULT_WORKSPACE_DIR = Path.home() / ".me4brain" / "skills"
DEFAULT_CLAWHUB_DIR = Path.home() / ".clawhub" / "skills"
BUNDLED_SKILLS_DIR = Path(__file__).parent / "bundled"
ANTIGRAVITY_SKILLS_DIR = Path.home() / ".gemini" / "antigravity" / "skills"


class SkillLoader:
    """Discovers and loads skills from filesystem."""

    def __init__(
        self,
        workspace_dir: Path | None = None,
        clawhub_dir: Path | None = None,
        antigravity_dir: Path | None = None,
        bundled_dir: Path | None = None,
    ):
        """Initialize loader with skill directories.

        Args:
            workspace_dir: User workspace skills directory
            clawhub_dir: ClawHub cache directory
            antigravity_dir: Antigravity native skills directory
            bundled_dir: Bundled skills directory
        """
        self.workspace_dir = workspace_dir or DEFAULT_WORKSPACE_DIR
        self.clawhub_dir = clawhub_dir or DEFAULT_CLAWHUB_DIR
        self.antigravity_dir = antigravity_dir or ANTIGRAVITY_SKILLS_DIR
        self.bundled_dir = bundled_dir or BUNDLED_SKILLS_DIR
        self.parser = SkillParser()

    async def discover_all(self) -> list[SkillDefinition]:
        """Discover all skills from all sources.

        Returns:
            List of discovered SkillDefinitions
        """
        skills: list[SkillDefinition] = []

        # Discover from each source
        async for skill in self._discover_from_directory(self.bundled_dir, SkillSource.BUNDLED):
            skills.append(skill)

        async for skill in self._discover_from_directory(self.workspace_dir, SkillSource.LOCAL):
            skills.append(skill)

        async for skill in self._discover_from_directory(self.clawhub_dir, SkillSource.CLAWHUB):
            skills.append(skill)
            
        async for skill in self._discover_from_directory(self.antigravity_dir, SkillSource.LOCAL):
            skills.append(skill)

        logger.info(
            "skills_discovered",
            total=len(skills),
            bundled=sum(1 for s in skills if s.metadata.source == SkillSource.BUNDLED),
            local=sum(1 for s in skills if s.metadata.source == SkillSource.LOCAL),
            clawhub=sum(1 for s in skills if s.metadata.source == SkillSource.CLAWHUB),
        )

        return skills

    async def discover_from_workspace(self) -> list[SkillDefinition]:
        """Discover skills only from workspace directory.

        Returns:
            List of workspace SkillDefinitions
        """
        skills = []
        async for skill in self._discover_from_directory(self.workspace_dir, SkillSource.LOCAL):
            skills.append(skill)
        return skills

    async def load_skill(self, skill_path: Path) -> SkillDefinition:
        """Load a specific skill from path.

        Args:
            skill_path: Path to skill directory or SKILL.md

        Returns:
            Loaded SkillDefinition
        """
        if skill_path.is_dir():
            skill_md = skill_path / "SKILL.md"
        else:
            skill_md = skill_path

        skill = self.parser.parse(skill_md)
        skill.status = SkillStatus.READY

        logger.info(
            "skill_loaded",
            skill_id=skill.id,
            name=skill.name,
            path=str(skill_path),
        )

        return skill

    async def _discover_from_directory(
        self,
        directory: Path,
        expected_source: SkillSource,
    ) -> AsyncIterator[SkillDefinition]:
        """Discover skills from a directory.

        Args:
            directory: Directory to search
            expected_source: Expected skill source type

        Yields:
            Discovered SkillDefinitions
        """
        if not directory.exists():
            logger.debug(
                "skill_directory_not_found",
                directory=str(directory),
            )
            return

        # Find all SKILL.md files
        skill_files = list(directory.rglob("SKILL.md"))

        for skill_md in skill_files:
            try:
                skill = self.parser.parse(skill_md)

                # Override source based on directory
                skill.metadata.source = expected_source

                yield skill

            except SkillParseError as e:
                logger.warning(
                    "skill_parse_failed",
                    path=str(skill_md),
                    error=str(e),
                )
            except Exception as e:
                logger.error(
                    "skill_discovery_error",
                    path=str(skill_md),
                    error=str(e),
                )

    async def refresh(self) -> list[SkillDefinition]:
        """Re-discover all skills (useful after install/update).

        Returns:
            Fresh list of all skills
        """
        logger.info("skills_refresh_started")
        return await self.discover_all()


def ensure_skill_directories() -> None:
    """Ensure skill directories exist."""
    DEFAULT_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(
        "skill_directories_ensured",
        workspace=str(DEFAULT_WORKSPACE_DIR),
    )
