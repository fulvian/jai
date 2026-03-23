"""Skill Integrator.

Integrates skills with Me4BrAIn components:
- HybridRouter: Register skills as tools
- ProceduralMemory: Store skill definitions
- EpisodicMemory: Log skill executions

This is the bridge between the skills system and the rest of Me4BrAIn.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from me4brain.skills.registry import SkillRegistry
from me4brain.skills.types import SkillDefinition, SkillStatus

logger = structlog.get_logger(__name__)


@dataclass
class IntegrationStats:
    """Statistics from skill integration."""

    total_skills: int
    integrated_skills: int
    skipped_skills: int
    failed_skills: int
    integration_time_ms: float


class SkillIntegrator:
    """Integrates skills with Me4BrAIn routing and memory systems."""

    # Domain mapping based on skill tags
    TAG_TO_DOMAIN = {
        "apple": "system",
        "notes": "system",
        "reminders": "system",
        "productivity": "system",
        "utility": "system",
        "system": "system",
        "files": "file_management",
        "clipboard": "system",
        "screen": "system",
        "capture": "system",
        "web": "web_search",
        "scraping": "web_search",
        "automation": "dev_tools",
        # Shopping / Marketplace domain
        "shopping": "shopping",
        "marketplace": "shopping",
        "subito": "shopping",
        "ebay": "shopping",
        "vinted": "shopping",
        "wallapop": "shopping",
        "usato": "shopping",
        "secondhand": "shopping",
        "used": "shopping",
        # Additional intent-based domains
        "travel": "travel",
        "food": "food",
        "entertainment": "entertainment",
        "sports": "sports",
        "padel": "sports",
        "playtomic": "sports",
    }

    def __init__(
        self,
        registry: SkillRegistry,
        default_domain: str = "utility",
    ):
        """Initialize integrator.

        Args:
            registry: SkillRegistry with discovered skills
            default_domain: Default domain for skills without tag match
        """
        self.registry = registry
        self.default_domain = default_domain

    async def integrate_with_router(
        self,
        router: Any,  # HybridToolRouter type
        embed_fn: Callable | None = None,
    ) -> IntegrationStats:
        """Integrate all ready skills with HybridRouter.

        Args:
            router: HybridToolRouter instance
            embed_fn: Embedding function (uses router's if not provided)

        Returns:
            Integration statistics
        """
        start_time = datetime.utcnow()

        integrated = 0
        skipped = 0
        failed = 0

        # Get all ready skills
        ready_skills = self.registry.ready_skills

        if not ready_skills:
            # Try to load skills first
            ready_skills = await self.registry.load_all_ready()

        logger.info(
            "skill_integration_started",
            ready_skills=len(ready_skills),
        )

        for skill in ready_skills:
            try:
                # Skip disabled skills
                if skill.status == SkillStatus.DISABLED:
                    skipped += 1
                    continue

                # Generate tool schema from skill
                tool_schema = self._generate_tool_schema(skill)

                # Determine domain
                domain = self._determine_domain(skill)

                # Add to router
                await router.add_tool(
                    tool_name=tool_schema["name"],
                    schema=tool_schema,
                    domain=domain,
                )

                skill.registered_tool_id = tool_schema["name"]
                integrated += 1

                logger.debug(
                    "skill_integrated",
                    skill_id=skill.id,
                    tool_name=tool_schema["name"],
                    domain=domain,
                )

            except Exception as e:
                logger.error(
                    "skill_integration_failed",
                    skill_id=skill.id,
                    error=str(e),
                )
                failed += 1

        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        stats = IntegrationStats(
            total_skills=len(self.registry.skills),
            integrated_skills=integrated,
            skipped_skills=skipped,
            failed_skills=failed,
            integration_time_ms=elapsed_ms,
        )

        logger.info(
            "skill_integration_completed",
            integrated=integrated,
            skipped=skipped,
            failed=failed,
            elapsed_ms=elapsed_ms,
        )

        return stats

    def _generate_tool_schema(self, skill: SkillDefinition) -> dict[str, Any]:
        """Generate OpenAI-compatible tool schema from skill.

        Args:
            skill: Skill definition

        Returns:
            Tool schema dict
        """
        # Normalize name for function calling
        tool_name = f"skill_{skill.metadata.name.lower().replace(' ', '_')}"

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": skill.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's request or query for this skill",
                        },
                        "options": {
                            "type": "object",
                            "description": "Optional parameters for the skill",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["query"],
                },
            },
            # Me4BrAIn extensions
            "x_skill_id": skill.id,
            "x_skill_instructions": skill.instructions[:2000],  # Truncate
            "x_skill_tags": skill.metadata.tags,
            "name": tool_name,  # Convenience field
        }

    def _determine_domain(self, skill: SkillDefinition) -> str:
        """Determine domain for skill based on tags.

        Args:
            skill: Skill definition

        Returns:
            Domain name
        """
        for tag in skill.metadata.tags:
            if tag.lower() in self.TAG_TO_DOMAIN:
                return self.TAG_TO_DOMAIN[tag.lower()]

        return self.default_domain

    async def register_skill_executor(
        self,
        executor_registry: dict[str, Callable],
    ) -> None:
        """Register skill execution handlers.

        Args:
            executor_registry: Dict mapping tool_name -> executor function
        """
        from me4brain.skills.executor import create_skill_executor

        for skill in self.registry.ready_skills:
            tool_name = f"skill_{skill.metadata.name.lower().replace(' ', '_')}"
            executor = create_skill_executor(skill)
            executor_registry[tool_name] = executor

            logger.debug(
                "skill_executor_registered",
                skill_id=skill.id,
                tool_name=tool_name,
            )


async def integrate_skills_with_engine(
    registry: SkillRegistry,
    router: Any,
) -> IntegrationStats:
    """Convenience function to integrate skills with engine.

    Args:
        registry: Initialized SkillRegistry
        router: HybridToolRouter instance

    Returns:
        Integration statistics
    """
    integrator = SkillIntegrator(registry)
    return await integrator.integrate_with_router(router)
