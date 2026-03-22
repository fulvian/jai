"""Sleep Mode - Background Consolidation.

Implementa il ciclo "Sleep" del sistema cognitivo:
- Consolidamento memoria (Working → Episodic → Semantic)
- Pruning episodi vecchi
- Aggiornamento pesi Knowledge Graph
- Backup e manutenzione
"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from pydantic import BaseModel, Field

from me4brain.embeddings import get_embedding_service
from me4brain.memory import (
    get_episodic_memory,
    get_semantic_memory,
)

logger = structlog.get_logger(__name__)


class ConsolidationConfig(BaseModel):
    """Configurazione per la consolidazione."""

    # Finestra temporale per episodi da consolidare
    min_age_hours: int = Field(
        default=24,
        description="Età minima in ore per consolidazione",
    )

    # Soglie
    min_importance: float = Field(
        default=0.6,
        description="Importanza minima per promuovere a Semantic",
    )
    min_frequency: int = Field(
        default=3,
        description="Frequenza minima per estrarre entità",
    )

    # Pruning
    max_episodic_age_days: int = Field(
        default=90,
        description="Età massima episodi prima del pruning",
    )
    prune_low_score_threshold: float = Field(
        default=0.3,
        description="Score sotto cui pruning aggressivo",
    )

    # LLM secondario per batch (cost optimization)
    use_secondary_llm: bool = Field(
        default=True,
        description="Usa LLM secondario per risparmio costi",
    )


class ConsolidationResult(BaseModel):
    """Risultato di un ciclo di consolidazione."""

    started_at: datetime
    completed_at: datetime
    episodes_processed: int
    entities_created: int
    relations_created: int
    episodes_pruned: int
    errors: list[str] = Field(default_factory=list)


class SleepMode:
    """Gestore del ciclo Sleep per consolidazione memoria.

    Il ciclo Sleep simula la consolidazione della memoria
    che avviene durante il sonno nel cervello umano:

    1. Working → Episodic: Già gestito in tempo reale
    2. Episodic → Semantic: Estrazione pattern ricorrenti
    3. Semantic Enrichment: Aggiornamento pesi e relazioni
    4. Pruning: Rimozione memoria a bassa priorità
    """

    def __init__(self, config: ConsolidationConfig | None = None) -> None:
        """Inizializza Sleep Mode.

        Args:
            config: Configurazione consolidazione (default: valori standard)
        """
        self.config = config or ConsolidationConfig()
        self._running = False
        self._task: asyncio.Task | None = None

    async def run_consolidation(
        self,
        tenant_id: str,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        """Esegue un ciclo completo di consolidazione.

        Args:
            tenant_id: ID del tenant da processare
            dry_run: Se True, non applica modifiche

        Returns:
            ConsolidationResult con statistiche
        """
        started_at = datetime.now(UTC)
        errors: list[str] = []
        episodes_processed = 0
        entities_created = 0
        relations_created = 0
        episodes_pruned = 0

        logger.info(
            "consolidation_started",
            tenant_id=tenant_id,
            dry_run=dry_run,
        )

        try:
            # Step 1: Episodic → Semantic (pattern extraction)
            result = await self._consolidate_episodic_to_semantic(tenant_id, dry_run)
            episodes_processed = result["episodes_processed"]
            entities_created = result["entities_created"]
            relations_created = result["relations_created"]

        except Exception as e:
            logger.error("consolidation_step1_error", error=str(e))
            errors.append(f"Pattern extraction failed: {e}")

        try:
            # Step 2: Pruning episodi vecchi
            if not dry_run:
                episodes_pruned = await self._prune_old_episodes(tenant_id)

        except Exception as e:
            logger.error("consolidation_step2_error", error=str(e))
            errors.append(f"Pruning failed: {e}")

        try:
            # Step 3: Semantic graph maintenance
            await self._maintain_semantic_graph(tenant_id, dry_run)

        except Exception as e:
            logger.error("consolidation_step3_error", error=str(e))
            errors.append(f"Graph maintenance failed: {e}")

        completed_at = datetime.now(UTC)

        result = ConsolidationResult(
            started_at=started_at,
            completed_at=completed_at,
            episodes_processed=episodes_processed,
            entities_created=entities_created,
            relations_created=relations_created,
            episodes_pruned=episodes_pruned,
            errors=errors,
        )

        logger.info(
            "consolidation_completed",
            tenant_id=tenant_id,
            duration_seconds=(completed_at - started_at).total_seconds(),
            episodes_processed=episodes_processed,
            entities_created=entities_created,
            episodes_pruned=episodes_pruned,
            errors_count=len(errors),
        )

        return result

    async def _consolidate_episodic_to_semantic(
        self,
        tenant_id: str,
        dry_run: bool,
    ) -> dict[str, int]:
        """Estrae pattern ricorrenti dalla memoria episodica.

        Identifica entità e relazioni menzionate frequentemente
        e le promuove al Knowledge Graph.
        """
        episodic = get_episodic_memory()
        semantic = get_semantic_memory()
        embeddings = get_embedding_service()

        # Calcola cutoff temporale
        cutoff_time = datetime.now(UTC) - timedelta(hours=self.config.min_age_hours)

        episodes_processed = 0
        entities_created = 0
        relations_created = 0

        try:
            # Recupero batch episodi da Qdrant usando scroll/search
            from qdrant_client.models import Filter, FieldCondition, Range

            qdrant = await episodic.get_qdrant()
            if qdrant is None:
                logger.warning("qdrant_not_available", action="skip_consolidation")
                return {"episodes_processed": 0, "entities_created": 0, "relations_created": 0}

            # Scroll attraverso episodi per tenant
            scroll_result = await qdrant.scroll(
                collection_name="me4brain_episodes",
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="tenant_id", match={"value": tenant_id}),
                    ]
                ),
                limit=100,
                with_payload=True,
            )

            episodes = scroll_result[0] if scroll_result else []

            for episode in episodes:
                payload = episode.payload or {}
                created_at_str = payload.get("created_at", "")

                # Parse timestamp e verifica età
                try:
                    if created_at_str:
                        episode_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        if episode_time > cutoff_time:
                            continue  # Troppo recente
                except ValueError:
                    continue

                episodes_processed += 1

                # Estrai entità dal contenuto (semplificato - in produzione usa NER/LLM)
                content = payload.get("content", "")
                importance = payload.get("importance", 0.5)

                if importance >= self.config.min_importance and not dry_run:
                    # Crea embedding e cerca entità simili
                    embedding = await embeddings.embed_text(content[:500])

                    # Cerca se esiste già entità simile
                    driver = await semantic.get_driver()
                    if driver:
                        # Crea entità se non esiste
                        from me4brain.memory.semantic import Entity

                        entity = Entity(
                            name=f"Episode_{episode.id}",
                            type="ConsolidatedEpisode",
                            tenant_id=tenant_id,
                            embedding=embedding,
                            properties={
                                "source_episode": str(episode.id),
                                "content_preview": content[:200],
                            },
                        )
                        await semantic.add_entity(entity)
                        entities_created += 1

        except Exception as e:
            logger.error("consolidation_batch_error", error=str(e), tenant_id=tenant_id)

        logger.debug(
            "episodic_consolidation_batch",
            tenant_id=tenant_id,
            episodes=episodes_processed,
            entities=entities_created,
        )

        return {
            "episodes_processed": episodes_processed,
            "entities_created": entities_created,
            "relations_created": relations_created,
        }

    async def _prune_old_episodes(self, tenant_id: str) -> int:
        """Rimuove episodi vecchi a bassa priorità."""
        episodic = get_episodic_memory()

        cutoff_time = datetime.now(UTC) - timedelta(days=self.config.max_episodic_age_days)
        pruned_count = 0

        try:
            from qdrant_client.models import Filter, FieldCondition, PointIdsList

            qdrant = await episodic.get_qdrant()
            if qdrant is None:
                logger.warning("qdrant_not_available", action="skip_pruning")
                return 0

            # Scroll per trovare episodi da pruning
            scroll_result = await qdrant.scroll(
                collection_name="me4brain_episodes",
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="tenant_id", match={"value": tenant_id}),
                    ]
                ),
                limit=500,
                with_payload=True,
            )

            episodes = scroll_result[0] if scroll_result else []
            ids_to_delete = []

            for episode in episodes:
                payload = episode.payload or {}
                created_at_str = payload.get("created_at", "")
                importance = payload.get("importance", 0.5)

                # Controlla criteri di pruning
                should_prune = False

                try:
                    if created_at_str:
                        episode_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        # Criteri: vecchio E basso score
                        if (
                            episode_time < cutoff_time
                            and importance < self.config.prune_low_score_threshold
                        ):
                            should_prune = True
                except ValueError:
                    pass

                if should_prune:
                    ids_to_delete.append(episode.id)

            # Elimina batch
            if ids_to_delete:
                await qdrant.delete(
                    collection_name="me4brain_episodes",
                    points_selector=PointIdsList(points=ids_to_delete),
                )
                pruned_count = len(ids_to_delete)

        except Exception as e:
            logger.error("pruning_batch_error", error=str(e), tenant_id=tenant_id)

        logger.debug(
            "episodes_pruned",
            tenant_id=tenant_id,
            count=pruned_count,
        )

        return pruned_count

    async def _maintain_semantic_graph(
        self,
        tenant_id: str,
        dry_run: bool,
    ) -> None:
        """Manutenzione del Knowledge Graph.

        - Aggiorna pesi basati su utilizzo
        - Rimuove entità orfane
        - Ottimizza struttura grafo
        """
        semantic = get_semantic_memory()

        driver = await semantic.get_driver()
        if driver is None:
            logger.warning("neo4j_not_available", action="skip_graph_maintenance")
            return

        try:
            async with driver.session() as session:
                if not dry_run:
                    # 1. Decay pesi relazioni non utilizzate (riduci del 10% se non accedute negli ultimi 30 giorni)
                    decay_result = await session.run(
                        """
                        MATCH ()-[r:RELATES_TO|CAUSES|PART_OF]->()
                        WHERE r.updated_at < datetime() - duration('P30D')
                        SET r.weight = r.weight * 0.9
                        RETURN count(r) as decayed_count
                        """
                    )
                    record = await decay_result.single()
                    decayed = record["decayed_count"] if record else 0

                    # 2. Rimozione nodi disconnessi (entità senza relazioni e vecchie)
                    orphan_result = await session.run(
                        """
                        MATCH (e:Entity {tenant_id: $tenant_id})
                        WHERE NOT (e)-[]-() 
                        AND e.created_at < datetime() - duration('P90D')
                        DETACH DELETE e
                        RETURN count(e) as deleted_count
                        """,
                        {"tenant_id": tenant_id},
                    )
                    orphan_record = await orphan_result.single()
                    deleted = orphan_record["deleted_count"] if orphan_record else 0

                    logger.info(
                        "graph_maintenance_completed",
                        tenant_id=tenant_id,
                        relations_decayed=decayed,
                        orphans_deleted=deleted,
                    )
                else:
                    logger.debug("graph_maintenance_dry_run", tenant_id=tenant_id)

        except Exception as e:
            logger.error("graph_maintenance_error", error=str(e), tenant_id=tenant_id)

        logger.debug("semantic_graph_maintained", tenant_id=tenant_id)

    async def start_background_scheduler(
        self,
        interval_hours: int = 6,
        tenant_ids: list[str] | None = None,
    ) -> None:
        """Avvia scheduler background per consolidazione periodica.

        Args:
            interval_hours: Intervallo tra cicli (default: 6h)
            tenant_ids: Lista di tenant da processare (None = tutti)
        """
        if self._running:
            logger.warning("scheduler_already_running")
            return

        self._running = True

        async def scheduler_loop():
            while self._running:
                try:
                    # Determina tenant da processare
                    tenants = tenant_ids or await self._get_all_tenants()

                    for tenant_id in tenants:
                        if not self._running:
                            break

                        await self.run_consolidation(tenant_id)

                        # Pausa tra tenant per non sovraccaricare
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error("scheduler_error", error=str(e))

                # Attendi prossimo ciclo
                await asyncio.sleep(interval_hours * 3600)

        self._task = asyncio.create_task(scheduler_loop())
        logger.info(
            "consolidation_scheduler_started",
            interval_hours=interval_hours,
        )

    async def stop_background_scheduler(self) -> None:
        """Ferma lo scheduler background."""
        self._running = False

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

            self._task = None

        logger.info("consolidation_scheduler_stopped")

    async def _get_all_tenants(self) -> list[str]:
        """Recupera lista di tutti i tenant attivi.

        In produzione, questo query il database dei tenant.
        """
        # Placeholder: ritorna tenant di default
        return ["default"]


# Singleton
_sleep_mode: SleepMode | None = None


def get_sleep_mode() -> SleepMode:
    """Ottiene l'istanza singleton di SleepMode."""
    global _sleep_mode
    if _sleep_mode is None:
        _sleep_mode = SleepMode()
    return _sleep_mode
