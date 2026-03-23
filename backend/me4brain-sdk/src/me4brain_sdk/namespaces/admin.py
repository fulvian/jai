from __future__ import annotations

"""Admin Namespace - System administration and backup."""

from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.common import Stats, HealthStatus


class AdminNamespace:
    """Admin operations - system management and backups.

    The admin namespace provides access to:
    - System statistics
    - Health monitoring
    - Backup and restore
    - Configuration management

    Example:
        # Get system stats
        stats = await client.admin.stats()
        print(f"Total episodes: {stats.total_episodes}")

        # Create backup
        backup = await client.admin.create_backup()
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def stats(self) -> Stats:
        """Get system statistics.

        Returns:
            System statistics
        """
        data = await self._http.get("/v1/admin/stats")
        return Stats.model_validate(data)

    async def health(self, detailed: bool = False) -> HealthStatus:
        """Get system health status.

        Args:
            detailed: Include detailed service status

        Returns:
            Health status
        """
        path = "/health/detailed" if detailed else "/health"
        data = await self._http.get(path)
        return HealthStatus.model_validate(data)

    async def create_backup(
        self,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
    ) -> dict[str, Any]:
        """Create a system backup.

        Args:
            include_episodic: Include episodic memory
            include_semantic: Include semantic memory
            include_procedural: Include procedural memory

        Returns:
            Backup metadata with ID
        """
        data = await self._http.post(
            "/v1/admin/backup",
            json_data={
                "include_episodic": include_episodic,
                "include_semantic": include_semantic,
                "include_procedural": include_procedural,
            },
        )
        return data

    async def list_backups(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List available backups.

        Args:
            limit: Maximum backups

        Returns:
            List of backup metadata
        """
        data = await self._http.get(
            "/v1/admin/backups",
            params={"limit": limit},
        )
        return data.get("backups", [])

    async def restore_backup(
        self,
        backup_id: str,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
    ) -> dict[str, Any]:
        """Restore from a backup.

        Args:
            backup_id: Backup ID to restore
            include_episodic: Restore episodic memory
            include_semantic: Restore semantic memory
            include_procedural: Restore procedural memory

        Returns:
            Restore result
        """
        data = await self._http.post(
            f"/v1/admin/backup/{backup_id}/restore",
            json_data={
                "include_episodic": include_episodic,
                "include_semantic": include_semantic,
                "include_procedural": include_procedural,
            },
        )
        return data

    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup.

        Args:
            backup_id: Backup ID

        Returns:
            True if deleted
        """
        await self._http.delete(f"/v1/admin/backup/{backup_id}")
        return True

    async def clear_memory(
        self,
        memory_type: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Clear a memory layer (destructive).

        Args:
            memory_type: "episodic", "semantic", or "procedural"
            confirm: Must be True to proceed

        Returns:
            Clear result
        """
        if not confirm:
            return {"error": "Must set confirm=True to clear memory"}

        data = await self._http.post(
            f"/v1/admin/memory/{memory_type}/clear",
            json_data={"confirm": True},
        )
        return data

    async def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Configuration values
        """
        data = await self._http.get("/v1/admin/config")
        return data

    async def update_config(
        self,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Update configuration.

        Args:
            config: Configuration values to update

        Returns:
            Updated configuration
        """
        data = await self._http.put(
            "/v1/admin/config",
            json_data=config,
        )
        return data
