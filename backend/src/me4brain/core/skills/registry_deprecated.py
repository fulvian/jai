"""DEPRECATED: Use me4brain.skills.registry.SkillRegistry instead.

This module is kept for backward compatibility.
"""

import warnings
warnings.warn(
    "me4brain.core.skills.registry is deprecated. Use me4brain.skills.registry.SkillRegistry",
    DeprecationWarning,
    stacklevel=2
)

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from me4brain.core.skills.parser import SkillParser
from me4brain.core.skills.types import Skill, SkillDefinition, ScoredSkill

logger = structlog.get_logger(__name__)


class SkillRegistry:
    """
    Registro centrale per tutte le skill (esplicite e cristallizzate).

    Le skill esplicite sono caricate da file SKILL.md.
    Le skill cristallizzate sono salvate in Qdrant per retrieval semantico.
    """

    COLLECTION_NAME = "me4brain_skills"
    EMBEDDING_SIZE = 1024  # BGE-M3 embedding size

    def __init__(
        self,
        qdrant: QdrantClient,
        skill_dir: Optional[Path] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Inizializza il registro skill.

        Args:
            qdrant: Client Qdrant per storage vettoriale
            skill_dir: Directory per skill esplicite (default: ~/.me4brain/skills)
            tenant_id: ID tenant per multi-tenancy
        """
        self.qdrant = qdrant
        self.skill_dir = skill_dir or Path.home() / ".me4brain" / "skills"
        self.tenant_id = tenant_id

        # Cache locale per skill esplicite
        self._explicit: dict[str, Skill] = {}

        # Parser per file SKILL.md
        self._parser = SkillParser()

    async def initialize(self) -> None:
        """Inizializza il registro e crea collection Qdrant se necessario."""
        # Assicura che la directory skill esista
        self.skill_dir.mkdir(parents=True, exist_ok=True)

        # Crea collection Qdrant se non esiste
        await self._ensure_collection()

        # Carica skill esplicite
        await self.load_explicit_skills()

        logger.info(
            "skill_registry_initialized",
            explicit_count=len(self._explicit),
            skill_dir=str(self.skill_dir),
        )

    async def _ensure_collection(self) -> None:
        """Crea collection Qdrant se non esiste."""
        collections = self.qdrant.get_collections().collections
        collection_names = [c.name for c in collections]

        if self.COLLECTION_NAME not in collection_names:
            self.qdrant.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.EMBEDDING_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("skill_collection_created", name=self.COLLECTION_NAME)

    async def load_explicit_skills(self) -> int:
        """
        Carica tutte le skill esplicite dalla directory.

        Returns:
            Numero di skill caricate
        """
        skills = self._parser.discover_skills(self.skill_dir)

        for skill_def in skills:
            skill = await self._definition_to_skill(skill_def)
            self._explicit[skill.id] = skill

        return len(skills)

    async def _definition_to_skill(self, definition: SkillDefinition) -> Skill:
        """Converte SkillDefinition in Skill."""
        skill_id = self._generate_skill_id(definition.name, "explicit")

        return Skill(
            id=skill_id,
            name=definition.name,
            description=definition.description,
            type="explicit",
            code=definition.instructions,
            embedding=[],  # Sarà popolato dal retriever
            version=definition.version,
            tenant_id=definition.tenant_id or self.tenant_id,
        )

    def _generate_skill_id(self, name: str, skill_type: str) -> str:
        """Genera ID univoco per skill."""
        base = f"{skill_type}:{name}:{self.tenant_id or 'global'}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    async def register_explicit(self, skill: Skill) -> None:
        """
        Registra skill esplicita.

        Args:
            skill: Skill da registrare
        """
        skill.type = "explicit"
        self._explicit[skill.id] = skill

        # Salva anche in Qdrant per retrieval (se ha embedding)
        if skill.embedding:
            await self._upsert_to_qdrant(skill)

        logger.info("skill_registered_explicit", skill_id=skill.id, name=skill.name)

    async def register_crystallized(self, skill: Skill) -> None:
        """
        Registra skill cristallizzata.

        Args:
            skill: Skill cristallizzata da registrare
        """
        skill.type = "crystallized"
        await self._upsert_to_qdrant(skill)

        logger.info(
            "skill_registered_crystallized",
            skill_id=skill.id,
            name=skill.name,
            signature=skill.tool_signature,
        )

    async def _upsert_to_qdrant(self, skill: Skill) -> None:
        """Inserisce o aggiorna skill in Qdrant."""
        if not skill.embedding:
            logger.warning("skill_missing_embedding", skill_id=skill.id)
            return

        payload = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "type": skill.type,
            "code": skill.code,
            "usage_count": skill.usage_count,
            "success_count": skill.success_count,
            "failure_count": skill.failure_count,
            "tenant_id": skill.tenant_id,
            "enabled": skill.enabled,
            "tool_signature": skill.tool_signature,
            "created_at": skill.created_at.isoformat(),
            "last_used": skill.last_used.isoformat() if skill.last_used else None,
        }

        point = PointStruct(
            id=skill.id,
            vector=skill.embedding,
            payload=payload,
        )

        self.qdrant.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[point],
        )

    async def find_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        skill_type: Optional[str] = None,
    ) -> list[ScoredSkill]:
        """
        Cerca skill per similarità semantica.

        Args:
            query_embedding: Vettore embedding della query
            top_k: Numero massimo di risultati
            skill_type: Filtra per tipo (explicit/crystallized)

        Returns:
            Lista di ScoredSkill ordinate per score
        """
        # Prepara filtro
        filter_conditions = []
        if skill_type:
            filter_conditions.append({"key": "type", "match": {"value": skill_type}})
        if self.tenant_id:
            filter_conditions.append(
                {"key": "tenant_id", "match": {"value": self.tenant_id}}
            )

        # Cerca in Qdrant
        results = self.qdrant.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_embedding,
            limit=top_k,
            query_filter={"must": filter_conditions} if filter_conditions else None,
        )

        scored_skills: list[ScoredSkill] = []
        for result in results:
            skill = self._payload_to_skill(result.payload, result.vector)
            scored = ScoredSkill.from_skill(skill, result.score)
            scored_skills.append(scored)

        # Includi anche skill esplicite dalla cache (se hanno embedding)
        for skill in self._explicit.values():
            if skill.enabled and skill_type in (None, "explicit"):
                # Per skill esplicite senza embedding, usa score 0.5
                scored = ScoredSkill.from_skill(skill, 0.5)
                scored_skills.append(scored)

        # Ordina per weighted score
        scored_skills.sort(key=lambda s: s.weighted_score, reverse=True)

        return scored_skills[:top_k]

    def _payload_to_skill(
        self, payload: dict, embedding: Optional[list[float]] = None
    ) -> Skill:
        """Converte payload Qdrant in Skill."""
        return Skill(
            id=payload["id"],
            name=payload["name"],
            description=payload["description"],
            type=payload["type"],
            code=payload["code"],
            embedding=embedding or [],
            usage_count=payload.get("usage_count", 0),
            success_count=payload.get("success_count", 0),
            failure_count=payload.get("failure_count", 0),
            tenant_id=payload.get("tenant_id"),
            enabled=payload.get("enabled", True),
            tool_signature=payload.get("tool_signature"),
            created_at=datetime.fromisoformat(payload["created_at"]),
            last_used=(
                datetime.fromisoformat(payload["last_used"])
                if payload.get("last_used")
                else None
            ),
        )

    async def find_by_signature(self, signature: str) -> Optional[Skill]:
        """
        Cerca skill per signature (hash tool chain).

        Args:
            signature: Signature della tool chain

        Returns:
            Skill se trovata, None altrimenti
        """
        # Cerca in Qdrant con filtro esatto
        results = self.qdrant.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter={
                "must": [{"key": "tool_signature", "match": {"value": signature}}]
            },
            limit=1,
        )

        points, _ = results
        if points:
            return self._payload_to_skill(points[0].payload, points[0].vector)
        return None

    async def get_by_id(self, skill_id: str) -> Optional[Skill]:
        """Ottiene skill per ID."""
        # Prima cerca in cache esplicite
        if skill_id in self._explicit:
            return self._explicit[skill_id]

        # Poi cerca in Qdrant
        try:
            results = self.qdrant.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[skill_id],
            )
            if results:
                return self._payload_to_skill(results[0].payload, results[0].vector)
        except Exception as e:
            logger.error("skill_get_error", skill_id=skill_id, error=str(e))

        return None

    async def update(self, skill: Skill) -> None:
        """Aggiorna skill esistente."""
        if skill.type == "explicit":
            self._explicit[skill.id] = skill
        await self._upsert_to_qdrant(skill)

    async def delete(self, skill_id: str) -> bool:
        """Elimina skill."""
        # Rimuovi da cache
        self._explicit.pop(skill_id, None)

        # Rimuovi da Qdrant
        try:
            self.qdrant.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector={"points": [skill_id]},
            )
            return True
        except Exception as e:
            logger.error("skill_delete_error", skill_id=skill_id, error=str(e))
            return False

    async def list_all(
        self, skill_type: Optional[str] = None, enabled_only: bool = True
    ) -> list[Skill]:
        """Lista tutte le skill."""
        skills: list[Skill] = []

        # Skill esplicite
        if skill_type in (None, "explicit"):
            for skill in self._explicit.values():
                if not enabled_only or skill.enabled:
                    skills.append(skill)

        # Skill cristallizzate da Qdrant
        if skill_type in (None, "crystallized"):
            filter_cond = [{"key": "type", "match": {"value": "crystallized"}}]
            if enabled_only:
                filter_cond.append({"key": "enabled", "match": {"value": True}})

            results, _ = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter={"must": filter_cond},
                limit=1000,
            )

            for point in results:
                skills.append(self._payload_to_skill(point.payload, point.vector))

        return skills

    @property
    def explicit_count(self) -> int:
        """Numero di skill esplicite."""
        return len(self._explicit)
