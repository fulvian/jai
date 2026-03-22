from __future__ import annotations
"""Episodic Memory Namespace - Long-term autobiographical memory."""

from datetime import datetime
from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.memory import Episode, EpisodeSearchResult


class EpisodicNamespace:
    """Episodic Memory operations - autobiographical event storage.

    Episodic memory stores and retrieves past experiences and events.
    It uses vector similarity search for semantic retrieval.

    Example:
        # Store an episode
        episode = await client.episodic.store(
            content="Had a productive meeting about Q4 budget",
            importance=0.8,
            tags=["meeting", "budget", "Q4"],
        )

        # Search episodes
        results = await client.episodic.search(
            query="budget discussions",
            limit=10,
        )
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def store(
        self,
        content: str,
        summary: str | None = None,
        importance: float = 0.5,
        source: str = "conversation",
        tags: list[str] | None = None,
        event_time: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Episode:
        """Store a new episode.

        Args:
            content: Episode content
            summary: Optional summary
            importance: Importance score (0-1)
            source: Source type
            tags: Optional tags
            event_time: When the event occurred
            metadata: Additional metadata

        Returns:
            Stored episode
        """
        data = await self._http.post(
            "/v1/memory/episodes",
            json_data={
                "content": content,
                "summary": summary,
                "importance": importance,
                "source": source,
                "tags": tags or [],
                "event_time": event_time.isoformat() if event_time else None,
                "metadata": metadata or {},
            },
        )
        return Episode.model_validate(data)

    async def get(self, episode_id: str) -> Episode:
        """Get episode by ID.

        Args:
            episode_id: Episode identifier

        Returns:
            Episode details
        """
        data = await self._http.get(f"/v1/memory/episodes/{episode_id}")
        return Episode.model_validate(data)

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
        tags: list[str] | None = None,
        source: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[EpisodeSearchResult]:
        """Search episodes by semantic similarity.

        Args:
            query: Search query
            limit: Maximum results
            min_score: Minimum similarity score
            tags: Filter by tags
            source: Filter by source
            since: Filter from date
            until: Filter to date

        Returns:
            List of matching episodes with scores
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "min_score": min_score,
        }
        if tags:
            params["tags"] = ",".join(tags)
        if source:
            params["source"] = source
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        data = await self._http.post(
            "/v1/memory/search",
            json_data=params,
        )

        results = []
        for item in data.get("results", []):
            results.append(
                EpisodeSearchResult(
                    id=item.get("id", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                    metadata=item.get("metadata", {}),
                    event_time=datetime.fromisoformat(item["event_time"])
                    if item.get("event_time")
                    else None,
                )
            )
        return results

    async def update(
        self,
        episode_id: str,
        importance: float | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Episode:
        """Update episode metadata.

        Args:
            episode_id: Episode identifier
            importance: New importance score
            tags: New tags (replaces existing)
            metadata: Additional metadata (merged)

        Returns:
            Updated episode
        """
        update_data: dict[str, Any] = {}
        if importance is not None:
            update_data["importance"] = importance
        if tags is not None:
            update_data["tags"] = tags
        if metadata is not None:
            update_data["metadata"] = metadata

        data = await self._http.put(
            f"/v1/memory/episodes/{episode_id}",
            json_data=update_data,
        )
        return Episode.model_validate(data)

    async def delete(self, episode_id: str) -> bool:
        """Delete an episode.

        Args:
            episode_id: Episode identifier

        Returns:
            True if deleted
        """
        await self._http.delete(f"/v1/memory/episodes/{episode_id}")
        return True

    async def get_related(
        self,
        episode_id: str,
        limit: int = 5,
    ) -> list[Episode]:
        """Get related episodes.

        Args:
            episode_id: Episode identifier
            limit: Maximum related episodes

        Returns:
            List of related episodes
        """
        data = await self._http.get(
            f"/v1/memory/episodes/{episode_id}/related",
            params={"limit": limit},
        )
        return [Episode.model_validate(e) for e in data.get("episodes", [])]

    async def get_candidates_for_consolidation(
        self,
        min_importance: float = 0.7,
        max_age_hours: int = 24,
    ) -> list[Episode]:
        """Get episodes suitable for consolidation to semantic memory.

        Args:
            min_importance: Minimum importance threshold
            max_age_hours: Maximum age in hours

        Returns:
            List of candidate episodes
        """
        data = await self._http.get(
            "/v1/memory/episodes/consolidation-candidates",
            params={
                "min_importance": min_importance,
                "max_age_hours": max_age_hours,
            },
        )
        return [Episode.model_validate(e) for e in data.get("episodes", [])]
