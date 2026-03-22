from __future__ import annotations
"""Procedural Memory Namespace - Skills and tool management."""

from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.tools import (
    SkillInfo,
    IntentMapping,
    MuscleMemoryPattern,
)


class ProceduralNamespace:
    """Procedural Memory operations - skills and tool patterns.

    Procedural memory manages learned skills, tool mappings, and
    muscle memory patterns for efficient tool selection.

    Example:
        # List available skills
        skills = await client.procedural.list_skills()

        # Search tools by intent
        mappings = await client.procedural.intent_map(
            query="calculate financial projections"
        )

        # Get muscle memory patterns
        patterns = await client.procedural.muscle_memory()
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def list_skills(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillInfo]:
        """List registered skills/tools.

        Args:
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of skills
        """
        data = await self._http.get(
            "/v1/procedural/skills",
            params={"limit": limit, "offset": offset},
        )
        return [SkillInfo.model_validate(s) for s in data.get("skills", [])]

    async def get_skill(self, skill_id: str) -> SkillInfo:
        """Get skill details.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill information
        """
        data = await self._http.get(f"/v1/procedural/skills/{skill_id}")
        return SkillInfo.model_validate(data)

    async def register_skill(
        self,
        name: str,
        description: str,
        endpoint: str | None = None,
        method: str = "POST",
        api_schema: dict[str, Any] | None = None,
    ) -> SkillInfo:
        """Register a new skill/tool.

        Args:
            name: Skill name
            description: Skill description
            endpoint: API endpoint
            method: HTTP method
            api_schema: OpenAPI schema

        Returns:
            Registered skill
        """
        data = await self._http.post(
            "/v1/procedural/skills",
            json_data={
                "name": name,
                "description": description,
                "endpoint": endpoint,
                "method": method,
                "api_schema": api_schema or {},
            },
        )
        return SkillInfo.model_validate(data)

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.

        Args:
            skill_id: Skill identifier

        Returns:
            True if deleted
        """
        await self._http.delete(f"/v1/procedural/skills/{skill_id}")
        return True

    async def intent_map(
        self,
        query: str,
        limit: int = 20,
    ) -> list[IntentMapping]:
        """Get tool mappings for an intent.

        Args:
            query: Intent query
            limit: Maximum results

        Returns:
            List of intent-to-tool mappings
        """
        data = await self._http.get(
            "/v1/procedural/intent-map",
            params={"query": query, "limit": limit},
        )
        return [IntentMapping.model_validate(m) for m in data.get("mappings", [])]

    async def muscle_memory(
        self,
        limit: int = 50,
    ) -> list[MuscleMemoryPattern]:
        """Get muscle memory patterns (cached tool selections).

        Args:
            limit: Maximum patterns

        Returns:
            List of cached patterns
        """
        data = await self._http.get(
            "/v1/procedural/muscle-memory",
            params={"limit": limit},
        )
        return [MuscleMemoryPattern.model_validate(p) for p in data.get("patterns", [])]

    async def clear_muscle_memory(self) -> bool:
        """Clear muscle memory cache.

        Returns:
            True if cleared
        """
        await self._http.delete("/v1/procedural/muscle-memory")
        return True

    async def search_tools(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
    ) -> list[SkillInfo]:
        """Search for tools by query.

        Args:
            query: Search query
            limit: Maximum results
            category: Filter by category

        Returns:
            List of matching tools
        """
        params: dict[str, Any] = {"query": query, "limit": limit}
        if category:
            params["category"] = category

        data = await self._http.post(
            "/v1/tools/search",
            json_data=params,
        )
        return [SkillInfo.model_validate(t) for t in data.get("tools", [])]
