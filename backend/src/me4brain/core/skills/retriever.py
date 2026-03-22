"""Skill Retriever - Recupero skill per task con ranking pesato."""

from typing import Optional

import structlog

from me4brain.core.skills.registry_deprecated import SkillRegistry
from me4brain.core.skills.types import ScoredSkill, Skill

logger = structlog.get_logger(__name__)


class SkillRetriever:
    """
    Recupera skill rilevanti per un task.

    Combina ricerca semantica con ranking basato su:
    - Similarità vettoriale
    - Success rate storico
    - Confidence (basato su usage count)
    """

    def __init__(
        self,
        registry: SkillRegistry,
        embed_func: Optional[callable] = None,
        min_similarity: float = 0.5,
    ):
        """
        Inizializza il retriever.

        Args:
            registry: Registry delle skill
            embed_func: Funzione per generare embedding (async)
            min_similarity: Similarità minima per considerare una skill
        """
        self.registry = registry
        self.embed_func = embed_func
        self.min_similarity = min_similarity

    async def retrieve(
        self,
        task_description: str,
        top_k: int = 3,
        skill_type: Optional[str] = None,
    ) -> list[ScoredSkill]:
        """
        Trova skill migliori per un task.

        Args:
            task_description: Descrizione del task
            top_k: Numero massimo di skill da restituire
            skill_type: Filtra per tipo (explicit/crystallized)

        Returns:
            Lista di ScoredSkill ordinate per weighted_score
        """
        if not self.embed_func:
            logger.warning("retriever_no_embed_func")
            return []

        try:
            # Genera embedding per il task
            query_embedding = await self.embed_func(task_description)

            # Cerca nel registry
            scored_skills = await self.registry.find_by_embedding(
                query_embedding=query_embedding,
                top_k=top_k * 2,  # Prendi più risultati per filtraggio
                skill_type=skill_type,
            )

            # Filtra per similarità minima
            filtered = [s for s in scored_skills if s.similarity_score >= self.min_similarity]

            # Ricalcola weighted score con formula finale
            for scored in filtered:
                scored.weighted_score = self._calculate_weighted_score(scored)

            # Riordina e limita
            filtered.sort(key=lambda s: s.weighted_score, reverse=True)

            result = filtered[:top_k]

            logger.info(
                "skills_retrieved",
                task=task_description[:50],
                found=len(result),
                top_score=result[0].weighted_score if result else 0,
            )

            return result

        except Exception as e:
            logger.error("skill_retrieval_failed", error=str(e))
            return []

    def _calculate_weighted_score(self, scored: ScoredSkill) -> float:
        """
        Calcola score pesato finale.

        Formula: similarity * success_rate * confidence * type_boost

        - similarity: da vector search (0-1)
        - success_rate: storico (0-1, default 0.5)
        - confidence: cresce con usage (0-1)
        - type_boost: 1.1 per explicit, 1.0 per crystallized
        """
        skill = scored.skill

        # Type boost: skill esplicite hanno leggera preferenza
        type_boost = 1.1 if skill.type == "explicit" else 1.0

        # Formula pesata
        weighted = (
            scored.similarity_score
            * skill.success_rate
            * (0.3 + 0.7 * skill.confidence)  # Min 30% even with 0 usage
            * type_boost
        )

        return weighted

    async def retrieve_best(
        self, task_description: str, skill_type: Optional[str] = None
    ) -> Optional[Skill]:
        """
        Restituisce la skill migliore per un task.

        Args:
            task_description: Descrizione del task
            skill_type: Filtra per tipo

        Returns:
            Skill migliore o None se nessuna trovata
        """
        results = await self.retrieve(task_description, top_k=1, skill_type=skill_type)
        return results[0].skill if results else None

    async def retrieve_for_tools(self, tool_names: list[str], top_k: int = 3) -> list[ScoredSkill]:
        """
        Trova skill che usano specifici tool.

        Args:
            tool_names: Lista di nomi tool
            top_k: Numero massimo risultati

        Returns:
            Skill che contengono i tool specificati
        """
        # Cerca per signature (tool names concatenati)
        search_text = " ".join(tool_names)
        return await self.retrieve(search_text, top_k=top_k)

    async def get_similar_skills(self, skill: Skill, top_k: int = 3) -> list[ScoredSkill]:
        """
        Trova skill simili a una data.

        Args:
            skill: Skill di riferimento
            top_k: Numero massimo risultati

        Returns:
            Skill simili (esclude la skill di input)
        """
        if not skill.embedding:
            # Genera embedding dalla descrizione
            if not self.embed_func:
                return []
            skill.embedding = await self.embed_func(skill.description)

        scored = await self.registry.find_by_embedding(
            query_embedding=skill.embedding,
            top_k=top_k + 1,  # +1 per escludere se stessa
        )

        # Escludi la skill stessa
        return [s for s in scored if s.skill.id != skill.id][:top_k]
