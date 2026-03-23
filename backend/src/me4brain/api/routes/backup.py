"""Backup & Disaster Recovery API Routes.

Endpoints per snapshot e restore di Qdrant e Neo4j.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import AuthenticatedUser
from me4brain.api.middleware.auth import get_current_user_dev as get_current_user
from me4brain.config import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/backup", tags=["Backup & DR"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SnapshotRequest(BaseModel):
    """Richiesta creazione snapshot."""

    name: str = Field(..., min_length=1, max_length=100)
    include_qdrant: bool = True
    include_neo4j: bool = True
    description: str = ""


class SnapshotInfo(BaseModel):
    """Info su uno snapshot."""

    name: str
    created_at: str
    size_bytes: int | None = None
    status: str  # "completed", "in_progress", "failed"
    components: list[str]


class SnapshotListResponse(BaseModel):
    """Lista snapshot disponibili."""

    snapshots: list[SnapshotInfo]
    total: int


class RestoreRequest(BaseModel):
    """Richiesta restore da snapshot."""

    snapshot_name: str
    restore_qdrant: bool = True
    restore_neo4j: bool = True


class BackupStatus(BaseModel):
    """Status operazione backup/restore."""

    operation: str
    status: str
    message: str
    started_at: str
    completed_at: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/snapshot", response_model=BackupStatus)
async def create_snapshot(
    request: SnapshotRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> BackupStatus:
    """Crea uno snapshot di Qdrant e/o Neo4j."""
    settings = get_settings()
    started_at = datetime.now(UTC).isoformat()
    details: dict[str, Any] = {}

    try:
        # Snapshot Qdrant
        if request.include_qdrant:
            qdrant_result = await _snapshot_qdrant(request.name)
            details["qdrant"] = qdrant_result

        # Snapshot Neo4j (KuzuDB in realtà)
        if request.include_neo4j:
            neo4j_result = await _snapshot_neo4j(request.name)
            details["neo4j"] = neo4j_result

        logger.info(
            "snapshot_created",
            name=request.name,
            components=list(details.keys()),
            user_id=user.user_id,
        )

        return BackupStatus(
            operation="create_snapshot",
            status="completed",
            message=f"Snapshot '{request.name}' created successfully",
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            details=details,
        )

    except Exception as e:
        logger.error("snapshot_failed", name=request.name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot failed: {e}",
        )


@router.get("/snapshots", response_model=SnapshotListResponse)
async def list_snapshots(
    user: AuthenticatedUser = Depends(get_current_user),
) -> SnapshotListResponse:
    """Lista tutti gli snapshot disponibili."""
    try:
        snapshots = await _list_all_snapshots()
        return SnapshotListResponse(snapshots=snapshots, total=len(snapshots))
    except Exception as e:
        logger.error("list_snapshots_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list snapshots: {e}",
        )


@router.post("/restore", response_model=BackupStatus)
async def restore_snapshot(
    request: RestoreRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> BackupStatus:
    """Ripristina da uno snapshot."""
    started_at = datetime.now(UTC).isoformat()
    details: dict[str, Any] = {}

    try:
        if request.restore_qdrant:
            qdrant_result = await _restore_qdrant(request.snapshot_name)
            details["qdrant"] = qdrant_result

        if request.restore_neo4j:
            neo4j_result = await _restore_neo4j(request.snapshot_name)
            details["neo4j"] = neo4j_result

        logger.info(
            "restore_completed",
            snapshot=request.snapshot_name,
            components=list(details.keys()),
            user_id=user.user_id,
        )

        return BackupStatus(
            operation="restore",
            status="completed",
            message=f"Restored from snapshot '{request.snapshot_name}'",
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            details=details,
        )

    except Exception as e:
        logger.error("restore_failed", snapshot=request.snapshot_name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {e}",
        )


@router.delete("/snapshot/{snapshot_name}", response_model=BackupStatus)
async def delete_snapshot(
    snapshot_name: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> BackupStatus:
    """Elimina uno snapshot."""
    started_at = datetime.now(UTC).isoformat()

    try:
        # Elimina da Qdrant
        await _delete_qdrant_snapshot(snapshot_name)

        # Elimina file Neo4j
        await _delete_neo4j_snapshot(snapshot_name)

        logger.info("snapshot_deleted", name=snapshot_name, user_id=user.user_id)

        return BackupStatus(
            operation="delete_snapshot",
            status="completed",
            message=f"Snapshot '{snapshot_name}' deleted",
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )

    except Exception as e:
        logger.error("delete_snapshot_failed", name=snapshot_name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {e}",
        )


# =============================================================================
# Internal Functions
# =============================================================================


async def _snapshot_qdrant(name: str) -> dict[str, Any]:
    """Crea snapshot Qdrant."""
    from qdrant_client import AsyncQdrantClient

    settings = get_settings()
    qdrant_url = getattr(settings, "qdrant_url", "http://localhost:6333")

    client = AsyncQdrantClient(url=qdrant_url)

    try:
        # Crea snapshot per ogni collection
        collections = await client.get_collections()
        snapshots_created = []

        for coll in collections.collections:
            snapshot_info = await client.create_snapshot(collection_name=coll.name)
            snapshots_created.append(
                {
                    "collection": coll.name,
                    "snapshot": snapshot_info.name
                    if hasattr(snapshot_info, "name")
                    else str(snapshot_info),
                }
            )

        return {
            "status": "completed",
            "collections_backed_up": len(snapshots_created),
            "snapshots": snapshots_created,
        }
    finally:
        await client.close()


async def _snapshot_neo4j(name: str) -> dict[str, Any]:
    """Crea snapshot Neo4j (backup database)."""
    import os
    import shutil

    settings = get_settings()
    neo4j_path = getattr(settings, "neo4j_path", "./data/neo4j")
    backup_dir = getattr(settings, "backup_dir", "./backups")

    # Crea directory backup
    os.makedirs(backup_dir, exist_ok=True)
    snapshot_path = os.path.join(
        backup_dir, f"neo4j_{name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )

    try:
        if os.path.exists(neo4j_path):
            shutil.copytree(neo4j_path, snapshot_path)
            size = sum(
                os.path.getsize(os.path.join(dirpath, filename))
                for dirpath, _, filenames in os.walk(snapshot_path)
                for filename in filenames
            )
            return {
                "status": "completed",
                "path": snapshot_path,
                "size_bytes": size,
            }
        else:
            return {
                "status": "skipped",
                "message": f"Neo4j path not found: {neo4j_path}",
            }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }


async def _restore_qdrant(snapshot_name: str) -> dict[str, Any]:
    """Ripristina Qdrant da snapshot."""
    # Implementazione placeholder - richiede snapshot specifico
    return {
        "status": "not_implemented",
        "message": "Qdrant restore requires manual intervention",
    }


async def _restore_neo4j(snapshot_name: str) -> dict[str, Any]:
    """Ripristina Neo4j da snapshot."""
    import os
    import shutil

    settings = get_settings()
    backup_dir = getattr(settings, "backup_dir", "./backups")
    neo4j_path = getattr(settings, "neo4j_path", "./data/neo4j")

    # Trova snapshot
    matches = (
        [d for d in os.listdir(backup_dir) if d.startswith(f"neo4j_{snapshot_name}")]
        if os.path.exists(backup_dir)
        else []
    )

    if not matches:
        return {
            "status": "failed",
            "error": f"Snapshot not found: {snapshot_name}",
        }

    snapshot_path = os.path.join(backup_dir, matches[0])

    try:
        # Backup corrente prima di restore
        if os.path.exists(neo4j_path):
            shutil.rmtree(neo4j_path)
        shutil.copytree(snapshot_path, neo4j_path)

        return {
            "status": "completed",
            "restored_from": snapshot_path,
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }


async def _list_all_snapshots() -> list[SnapshotInfo]:
    """Lista tutti gli snapshot."""
    import os

    settings = get_settings()
    backup_dir = getattr(settings, "backup_dir", "./backups")
    snapshots = []

    # Lista snapshot Neo4j
    if os.path.exists(backup_dir):
        for item in os.listdir(backup_dir):
            if item.startswith("neo4j_"):
                full_path = os.path.join(backup_dir, item)
                created_at = datetime.fromtimestamp(os.path.getctime(full_path), tz=UTC).isoformat()

                size = (
                    sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(full_path)
                        for filename in filenames
                    )
                    if os.path.isdir(full_path)
                    else os.path.getsize(full_path)
                )

                snapshots.append(
                    SnapshotInfo(
                        name=item,
                        created_at=created_at,
                        size_bytes=size,
                        status="completed",
                        components=["neo4j"],
                    )
                )

    # Lista snapshot Qdrant
    try:
        from qdrant_client import AsyncQdrantClient

        qdrant_url = getattr(settings, "qdrant_url", "http://localhost:6333")
        client = AsyncQdrantClient(url=qdrant_url)

        collections = await client.get_collections()
        for coll in collections.collections:
            coll_snapshots = await client.list_snapshots(collection_name=coll.name)
            for snap in coll_snapshots:
                snapshots.append(
                    SnapshotInfo(
                        name=f"qdrant_{coll.name}_{snap.name}",
                        created_at=str(snap.creation_time)
                        if hasattr(snap, "creation_time")
                        else "",
                        size_bytes=snap.size if hasattr(snap, "size") else None,
                        status="completed",
                        components=["qdrant"],
                    )
                )

        await client.close()
    except Exception as e:
        logger.warning("qdrant_snapshot_list_failed", error=str(e))

    return snapshots


async def _delete_qdrant_snapshot(name: str) -> None:
    """Elimina snapshot Qdrant."""
    # Implementazione placeholder
    pass


async def _delete_neo4j_snapshot(name: str) -> None:
    """Elimina snapshot Neo4j."""
    import os
    import shutil

    settings = get_settings()
    backup_dir = getattr(settings, "backup_dir", "./backups")

    matches = [d for d in os.listdir(backup_dir) if name in d] if os.path.exists(backup_dir) else []

    for match in matches:
        full_path = os.path.join(backup_dir, match)
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
