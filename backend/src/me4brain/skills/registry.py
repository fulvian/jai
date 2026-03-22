"""Skill Registry.

Central registry for managing skill lifecycle, dependencies,
and integration with ProceduralMemory.
"""

import asyncio
from datetime import datetime
from typing import Any

import structlog

from me4brain.skills.types import (
    SkillDefinition,
    SkillSource,
    SkillStatus,
)
from me4brain.skills.loader import SkillLoader

logger = structlog.get_logger(__name__)


class SkillRegistry:
    """Central registry for skill management."""

    def __init__(self, loader: SkillLoader | None = None):
        """Initialize registry.

        Args:
            loader: SkillLoader instance (creates default if None)
        """
        self.loader = loader or SkillLoader()
        self._skills: dict[str, SkillDefinition] = {}
        self._loaded = False

    @property
    def skills(self) -> list[SkillDefinition]:
        """Get all registered skills."""
        return list(self._skills.values())

    @property
    def ready_skills(self) -> list[SkillDefinition]:
        """Get skills that are ready to use."""
        return [s for s in self._skills.values() if s.status == SkillStatus.READY]

    async def initialize(self) -> None:
        """Initialize registry by discovering all skills.

        Should be called once at startup.
        """
        if self._loaded:
            return

        discovered = await self.loader.discover_all()

        for skill in discovered:
            self._skills[skill.id] = skill

        self._loaded = True

        logger.info(
            "skill_registry_initialized",
            total_skills=len(self._skills),
        )

    async def load_skill(self, skill_id: str) -> SkillDefinition:
        """Load a specific skill, checking requirements.

        Args:
            skill_id: Skill identifier

        Returns:
            Loaded SkillDefinition

        Raises:
            KeyError: If skill not found
            ValueError: If requirements not met
        """
        if skill_id not in self._skills:
            raise KeyError(f"Skill not found: {skill_id}")

        skill = self._skills[skill_id]

        if skill.status == SkillStatus.READY:
            return skill

        # Check requirements
        skill.status = SkillStatus.LOADING

        requirements_check = skill.check_requirements()
        unmet = [(req, err) for req, met, err in requirements_check if not met]

        if unmet:
            skill.status = SkillStatus.ERROR
            skill.error_message = "; ".join(err for _, err in unmet)

            logger.warning(
                "skill_requirements_unmet",
                skill_id=skill_id,
                unmet_count=len(unmet),
                errors=skill.error_message,
            )

            raise ValueError(f"Skill requirements not met: {skill.error_message}")

        skill.status = SkillStatus.READY

        logger.info(
            "skill_loaded",
            skill_id=skill_id,
            name=skill.name,
        )

        return skill

    async def load_all_ready(self) -> list[SkillDefinition]:
        """Load all skills that have requirements met.

        Returns:
            List of successfully loaded skills
        """
        ready = []

        for skill_id in list(self._skills.keys()):
            try:
                skill = await self.load_skill(skill_id)
                ready.append(skill)
            except ValueError:
                # Requirements not met, skip
                continue

        return ready

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        """Get skill by ID.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillDefinition or None if not found
        """
        return self._skills.get(skill_id)

    def get_skills_by_source(self, source: SkillSource) -> list[SkillDefinition]:
        """Get skills by source type.

        Args:
            source: SkillSource to filter by

        Returns:
            List of matching skills
        """
        return [s for s in self._skills.values() if s.metadata.source == source]

    def search_skills(self, query: str) -> list[SkillDefinition]:
        """Search skills by name or description.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching skills
        """
        query_lower = query.lower()

        return [
            s
            for s in self._skills.values()
            if query_lower in s.name.lower()
            or query_lower in s.description.lower()
            or any(query_lower in tag.lower() for tag in s.metadata.tags)
        ]

    async def register_with_procedural_memory(
        self,
        skill: SkillDefinition,
        procedural_memory: Any,  # ProceduralMemory type
        tenant_id: str,
    ) -> str:
        """Register skill as a tool in ProceduralMemory.

        Args:
            skill: Skill to register
            procedural_memory: ProceduralMemory instance
            tenant_id: Tenant ID for isolation

        Returns:
            Registered tool ID
        """
        # Import here to avoid circular dependency
        from me4brain.memory.procedural import Tool

        tool = Tool(
            name=f"skill_{skill.id.replace('/', '_').replace('@', '')}",
            description=skill.description,
            tenant_id=tenant_id,
            api_schema={
                "type": "skill",
                "skill_id": skill.id,
                "instructions": skill.instructions[:1000],  # Truncate for storage
            },
        )

        tool_id = await procedural_memory.register_tool(tool)
        skill.registered_tool_id = tool_id

        logger.info(
            "skill_registered_as_tool",
            skill_id=skill.id,
            tool_id=tool_id,
        )

        return tool_id

    def mark_used(self, skill_id: str) -> None:
        """Mark a skill as recently used.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._skills:
            self._skills[skill_id].last_used_at = datetime.utcnow()

    def disable_skill(self, skill_id: str) -> None:
        """Disable a skill.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._skills:
            self._skills[skill_id].status = SkillStatus.DISABLED
            logger.info("skill_disabled", skill_id=skill_id)

    def enable_skill(self, skill_id: str) -> None:
        """Re-enable a disabled skill.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._skills:
            self._skills[skill_id].status = SkillStatus.DISCOVERED
            logger.info("skill_enabled", skill_id=skill_id)

    async def refresh(self) -> None:
        """Refresh skill registry from disk.

        Re-discovers skills and updates registry.
        """
        discovered = await self.loader.refresh()

        # Update existing, add new
        for skill in discovered:
            if skill.id in self._skills:
                # Preserve status and last_used
                old = self._skills[skill.id]
                skill.status = old.status
                skill.last_used_at = old.last_used_at
                skill.registered_tool_id = old.registered_tool_id

            self._skills[skill.id] = skill

        logger.info(
            "skill_registry_refreshed",
            total_skills=len(self._skills),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dictionary with stats
        """
        by_status = {}
        by_source = {}

        for skill in self._skills.values():
            by_status[skill.status.value] = by_status.get(skill.status.value, 0) + 1
            by_source[skill.metadata.source.value] = (
                by_source.get(skill.metadata.source.value, 0) + 1
            )

        return {
            "total": len(self._skills),
            "by_status": by_status,
            "by_source": by_source,
        }
