"""Session Knowledge Graph — Graph-based session management.

Gestisce sessioni come nodi nel Knowledge Graph Neo4j.
Ogni sessione, turn, topic e prompt diventa un nodo con embeddings.
Le sessioni si auto-organizzano tramite community detection (Louvain).

Pipeline di retrieval:
  Query → BGE-M3 Embedding → Neo4j Vector Search (top-50)
        → Graph Boost (PageRank) → LLM Reranking (Mistral)
        → RRF Fusion → Risultati

Schema Neo4j:
  (:Session {id, tenant_id, title, created_at, updated_at, embedding})
  (:Turn {id, session_id, role, content_preview, timestamp, embedding})
  (:Topic {id, name, tenant_id, embedding})
  (:PromptTemplate {id, label, content, category, embedding})
  (:TopicCluster {id, name, description, session_count})

  (Session)-[:CONTAINS]->(Turn)
  (Session)-[:HAS_TOPIC {weight, extracted_at}]->(Topic)
  (Session)-[:RELATED_TO {similarity, method}]->(Session)
  (Session)-[:BELONGS_TO]->(TopicCluster)
  (Topic)-[:RELATED_TO]->(Topic)
  (Turn)-[:MENTIONS]->(Topic)
  (Turn)-[:FOLLOWS]->(Turn)
  (PromptTemplate)-[:FOR_TOPIC]->(Topic)
  (PromptTemplate)-[:USED_IN]->(Session)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
import structlog

from me4brain.config import get_settings
from me4brain.memory.semantic import SemanticMemory, get_semantic_memory

logger = structlog.get_logger(__name__)

# Redis key prefix for community detection cooldown
COMMUNITY_COOLDOWN_KEY_PREFIX = "me4brain:community_detection:last_run"
# Cooldown per community detection automatica (5 minuti per tenant)
COMMUNITY_DETECTION_COOLDOWN_SECONDS = 300  # 5 min

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class SessionNode:
    """Rappresenta una sessione nel grafo."""

    id: str
    tenant_id: str
    title: str = "Nuova Chat"
    created_at: str = ""
    updated_at: str = ""
    turn_count: int = 0
    embedding: list[float] = field(default_factory=list)


@dataclass
class TurnNode:
    """Rappresenta un singolo turn (query/risposta) nel grafo."""

    id: str
    session_id: str
    role: str  # "user" | "assistant"
    content_preview: str = ""  # Primi 500 chars
    timestamp: str = ""
    embedding: list[float] = field(default_factory=list)


@dataclass
class TopicNode:
    """Topic estratto automaticamente."""

    id: str
    name: str
    tenant_id: str
    embedding: list[float] = field(default_factory=list)


@dataclass
class TopicCluster:
    """Cluster tematico (output di community detection)."""

    id: str
    name: str
    description: str = ""
    session_count: int = 0
    topics: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)


@dataclass
class PromptTemplateNode:
    """Prompt template nel grafo."""

    id: str
    label: str
    content: str
    category: str = "general"
    tenant_id: str = ""
    usage_count: int = 0
    last_used_at: str = ""
    variables: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)


@dataclass
class SessionSearchResult:
    """Risultato di una ricerca semantica sessioni."""

    session_id: str
    title: str
    score: float
    topics: list[str] = field(default_factory=list)
    cluster_name: str = ""
    turn_count: int = 0
    updated_at: str = ""


@dataclass
class ConnectedNode:
    """Nodo connesso nel grafo — punto di esplorazione esterna."""

    id: str
    name: str
    node_type: str  # 'topic' | 'session' | 'cluster'
    connection_score: float = 0.0
    relation_type: str = ""  # Tipo di relazione (HAS_TOPIC, RELATED_TO, etc.)
    shared_sessions: int = 0  # Quante sessioni condividono questo nodo
    description: str = ""


# ============================================================================
# Topic Extraction Prompt
# ============================================================================

TOPIC_EXTRACTION_PROMPT = """Analizza questa conversazione ed estrai i topic principali.

CONVERSAZIONE:
{conversation}

REGOLE:
1. Estrai da 1 a 5 topic principali
2. Ogni topic deve essere una parola o frase breve (max 3 parole)
3. Usa italiano se la conversazione è in italiano, inglese altrimenti
4. Sii specifico: "Machine Learning" è meglio di "Tecnologia"
5. Rispondi SOLO con un JSON array di stringhe

FORMATO OUTPUT (JSON puro, nessun markdown):
["topic1", "topic2", "topic3"]"""


CLUSTER_NAMING_PROMPT = """Dato questo gruppo di topic correlati, genera un nome breve e un'icona per il cluster.

TOPIC NEL CLUSTER:
{topics}

SESSIONI NEL CLUSTER:
{sessions}

Rispondi SOLO con un JSON:
{{"name": "Nome Cluster (max 3 parole)", "description": "Breve descrizione", "icon": "emoji appropriato"}}"""


# ============================================================================
# SessionKnowledgeGraph
# ============================================================================


class SessionKnowledgeGraph:
    """Layer dedicato alla gestione sessioni nel grafo Neo4j.

    Estende le capacità di SemanticMemory per create un knowledge graph
    specifico per le sessioni di chat, con auto-clustering e topic extraction.
    """

    def __init__(
        self,
        semantic: SemanticMemory | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        """Inizializza il Session Knowledge Graph.

        Args:
            semantic: SemanticMemory instance (per DI/testing)
            redis_client: Redis client opzionale (per cooldown distribuito)
        """
        self._semantic = semantic
        self._redis = redis_client
        self._schema_initialized = False

    @property
    def semantic(self) -> SemanticMemory:
        """Lazy load SemanticMemory."""
        if self._semantic is None:
            self._semantic = get_semantic_memory()
        return self._semantic

    async def _get_embedding_service(self):
        """Lazy load embedding service (evita import pesante al bootstrap)."""
        from me4brain.embeddings.bge_m3 import get_embedding_service

        return get_embedding_service()

    async def _get_llm_client(self):
        """Lazy load LLM client."""
        from me4brain.llm import get_llm_client

        return get_llm_client()

    async def _get_redis(self) -> redis.Redis | None:
        """Lazy load Redis client for distributed cooldown.

        Returns:
            Redis client o None se Redis non è disponibile.
        """
        if self._redis is None:
            try:
                settings = get_settings()
                self._redis = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
                logger.info("session_graph_redis_connected")
            except Exception as e:
                logger.warning(
                    "session_graph_redis_unavailable",
                    error=str(e),
                    hint="Cooldown will use in-memory fallback",
                )
                self._redis = None
        return self._redis

    # ========================================================================
    # Schema Initialization
    # ========================================================================

    async def initialize_schema(self) -> None:
        """Crea constraints e indici per il Session Knowledge Graph.

        Idempotente: sicuro da chiamare multiple volte.
        """
        if self._schema_initialized:
            return

        driver = await self.semantic.get_driver()
        if driver is None:
            logger.warning("session_graph_init_skipped", reason="neo4j not available")
            return

        async with driver.session() as session:
            # === Constraints (unicità) ===
            constraints = [
                "CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
                "CREATE CONSTRAINT turn_id IF NOT EXISTS FOR (t:Turn) REQUIRE t.id IS UNIQUE",
                "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
                "CREATE CONSTRAINT prompt_template_id IF NOT EXISTS FOR (p:PromptTemplate) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT topic_cluster_id IF NOT EXISTS FOR (c:TopicCluster) REQUIRE c.id IS UNIQUE",
            ]

            # === Indexes (performance) ===
            indexes = [
                "CREATE INDEX session_tenant IF NOT EXISTS FOR (s:Session) ON (s.tenant_id)",
                "CREATE INDEX session_updated IF NOT EXISTS FOR (s:Session) ON (s.updated_at)",
                "CREATE INDEX turn_session IF NOT EXISTS FOR (t:Turn) ON (t.session_id)",
                "CREATE INDEX turn_role IF NOT EXISTS FOR (t:Turn) ON (t.role)",
                "CREATE INDEX topic_tenant IF NOT EXISTS FOR (t:Topic) ON (t.tenant_id)",
                "CREATE INDEX topic_name IF NOT EXISTS FOR (t:Topic) ON (t.name)",
                "CREATE INDEX prompt_tenant IF NOT EXISTS FOR (p:PromptTemplate) ON (p.tenant_id)",
                "CREATE INDEX prompt_category IF NOT EXISTS FOR (p:PromptTemplate) ON (p.category)",
                "CREATE INDEX cluster_tenant IF NOT EXISTS FOR (c:TopicCluster) ON (c.tenant_id)",
            ]

            for stmt in constraints + indexes:
                try:
                    await session.run(stmt)
                except Exception as e:
                    logger.warning("schema_statement_failed", stmt=stmt[:60], error=str(e))

            # === Vector Indexes (Neo4j 5.x native) ===
            vector_indexes = [
                """
                CREATE VECTOR INDEX session_embedding IF NOT EXISTS
                FOR (s:Session) ON (s.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
                """
                CREATE VECTOR INDEX topic_embedding IF NOT EXISTS
                FOR (t:Topic) ON (t.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
                """
                CREATE VECTOR INDEX prompt_embedding IF NOT EXISTS
                FOR (p:PromptTemplate) ON (p.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
            ]

            for stmt in vector_indexes:
                try:
                    await session.run(stmt)
                except Exception as e:
                    # Vector indexes might not be available in all Neo4j editions
                    logger.warning(
                        "vector_index_creation_failed",
                        error=str(e),
                        hint="Vector index requires Neo4j 5.11+ Enterprise or AuraDB",
                    )

        self._schema_initialized = True
        logger.info("session_graph_schema_initialized")

    # ========================================================================
    # Session Ingestion
    # ========================================================================

    async def ingest_session(
        self,
        session_id: str,
        tenant_id: str,
        title: str,
        turns: list[dict[str, Any]],
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> SessionNode:
        """Indicizza una sessione nel grafo con tutti i suoi turns.

        Crea/aggiorna nodi Session e Turn, genera embeddings,
        estrae topics automaticamente.

        Args:
            session_id: ID univoco della sessione
            tenant_id: ID tenant per isolamento
            title: Titolo della sessione
            turns: Lista di dict con {role, content, timestamp?}
            created_at: Timestamp creazione (ISO format)
            updated_at: Timestamp ultimo aggiornamento (ISO format)

        Returns:
            SessionNode creato/aggiornato
        """
        await self.initialize_schema()

        driver = await self.semantic.get_driver()
        if driver is None:
            raise RuntimeError("Neo4j non disponibile per ingestione sessione")

        embedding_service = await self._get_embedding_service()
        now = datetime.now(UTC).isoformat()

        # Genera embedding della sessione (concatenando tutti i contenuti)
        session_text = f"{title}\n" + "\n".join(
            f"{t.get('role', 'user')}: {t.get('content', '')[:300]}"
            for t in turns
            if t.get("content")
        )
        session_embedding = await embedding_service.embed_document_async(
            session_text[:2000]  # Limita a 2000 chars per embedding
        )

        # Crea/aggiorna nodo Session
        async with driver.session() as neo_session:
            await neo_session.run(
                """
                MERGE (s:Session {id: $id})
                SET s.tenant_id = $tenant_id,
                    s.title = $title,
                    s.created_at = $created_at,
                    s.updated_at = $updated_at,
                    s.turn_count = $turn_count,
                    s.embedding = $embedding
                """,
                {
                    "id": session_id,
                    "tenant_id": tenant_id,
                    "title": title,
                    "created_at": created_at or now,
                    "updated_at": updated_at or now,
                    "turn_count": len(turns),
                    "embedding": session_embedding,
                },
            )

            # Crea nodi Turn con embeddings e relazioni
            prev_turn_id: str | None = None
            for i, turn in enumerate(turns):
                turn_id = f"{session_id}_turn_{i}"
                content = turn.get("content", "")
                content_preview = content[:500]

                # Embedding solo per contenuti significativi
                turn_embedding: list[float] = []
                if content and len(content) > 20:
                    turn_embedding = await embedding_service.embed_document_async(content[:1000])

                await neo_session.run(
                    """
                    MERGE (t:Turn {id: $id})
                    SET t.session_id = $session_id,
                        t.role = $role,
                        t.content_preview = $content_preview,
                        t.timestamp = $timestamp,
                        t.embedding = $embedding
                    WITH t
                    MATCH (s:Session {id: $session_id})
                    MERGE (s)-[:CONTAINS]->(t)
                    """,
                    {
                        "id": turn_id,
                        "session_id": session_id,
                        "role": turn.get("role", "user"),
                        "content_preview": content_preview,
                        "timestamp": turn.get("timestamp", now),
                        "embedding": turn_embedding,
                    },
                )

                # Relazione FOLLOWS tra turns consecutivi
                if prev_turn_id:
                    await neo_session.run(
                        """
                        MATCH (prev:Turn {id: $prev_id})
                        MATCH (curr:Turn {id: $curr_id})
                        MERGE (prev)-[:FOLLOWS]->(curr)
                        """,
                        {"prev_id": prev_turn_id, "curr_id": turn_id},
                    )
                prev_turn_id = turn_id

        logger.info(
            "session_ingested",
            session_id=session_id,
            turn_count=len(turns),
            tenant_id=tenant_id,
        )

        # Estrai topic in background (fire-and-forget)
        asyncio.create_task(self._safe_extract_topics(session_id, tenant_id, turns))

        # Community detection periodica (fire-and-forget con cooldown)
        asyncio.create_task(self._safe_detect_communities(tenant_id))

        return SessionNode(
            id=session_id,
            tenant_id=tenant_id,
            title=title,
            created_at=created_at or now,
            updated_at=updated_at or now,
            turn_count=len(turns),
            embedding=session_embedding,
        )

    # ========================================================================
    # Topic Extraction (LLM-based)
    # ========================================================================

    async def _safe_extract_topics(
        self,
        session_id: str,
        tenant_id: str,
        turns: list[dict[str, Any]],
    ) -> None:
        """Wrapper sicuro per estrazione topic (non propaga eccezioni)."""
        try:
            await self.extract_topics(session_id, tenant_id, turns)
        except Exception as e:
            logger.warning(
                "topic_extraction_failed",
                session_id=session_id,
                error=str(e),
            )

    async def _safe_detect_communities(self, tenant_id: str) -> None:
        """Community detection automatica con cooldown per tenant.

        Usa Redis per cooldown distribuito tra multiple istanze.
        Fallback a in-memory se Redis non è disponibile.
        Evita ricalcoli eccessivi: max una volta ogni 5 minuti per tenant.
        Non propaga eccezioni (fire-and-forget).
        """
        cooldown_key = f"{COMMUNITY_COOLDOWN_KEY_PREFIX}:{tenant_id}"

        # Try distributed cooldown with Redis
        redis_client = await self._get_redis()

        if redis_client is not None:
            try:
                # Check cooldown in Redis using GET with NX (only set if not exists)
                cooldown_value = await redis_client.get(cooldown_key)
                if cooldown_value is not None:
                    last_run = float(cooldown_value)
                    if time.time() - last_run < COMMUNITY_DETECTION_COOLDOWN_SECONDS:
                        logger.debug(
                            "community_detection_cooldown_active",
                            tenant_id=tenant_id,
                            cooldown_remaining=COMMUNITY_DETECTION_COOLDOWN_SECONDS
                            - (time.time() - last_run),
                        )
                        return

                # Set cooldown with atomic operation
                await redis_client.setex(
                    cooldown_key,
                    COMMUNITY_DETECTION_COOLDOWN_SECONDS,
                    str(time.time()),
                )
            except Exception as e:
                logger.warning(
                    "community_detection_cooldown_redis_error",
                    tenant_id=tenant_id,
                    error=str(e),
                    hint="Falling back to in-memory cooldown",
                )
                # Fall through to in-memory cooldown
        else:
            # Fallback to in-memory cooldown
            now = time.monotonic()
            last_run = getattr(self, "_last_community_detection", 0)
            if now - last_run < COMMUNITY_DETECTION_COOLDOWN_SECONDS:
                return
            self._last_community_detection = now

        # Run community detection
        try:
            clusters = await self.detect_communities(tenant_id)
            if clusters:
                logger.info(
                    "auto_community_detection_completed",
                    tenant_id=tenant_id,
                    cluster_count=len(clusters),
                )
        except Exception as e:
            logger.warning(
                "auto_community_detection_failed",
                tenant_id=tenant_id,
                error=str(e),
            )

    async def extract_topics(
        self,
        session_id: str,
        tenant_id: str,
        turns: list[dict[str, Any]],
    ) -> list[TopicNode]:
        """Estrae topic dalla conversazione via LLM.

        Args:
            session_id: ID sessione
            tenant_id: ID tenant
            turns: Lista di turns della sessione

        Returns:
            Lista di TopicNode estratti
        """
        from me4brain.llm import LLMRequest

        # Costruisci contesto della conversazione
        conversation = "\n".join(
            f"{t.get('role', 'user')}: {t.get('content', '')[:200]}"
            for t in turns
            if t.get("content")
        )

        if not conversation.strip():
            return []

        # Chiamata LLM per estrazione topic
        llm_client = await self._get_llm_client()
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": "Sei un esperto di analisi conversazionale. Rispondi SOLO con JSON valido.",
                },
                {
                    "role": "user",
                    "content": TOPIC_EXTRACTION_PROMPT.format(conversation=conversation[:3000]),
                },
            ],
            model=config.model_extraction,
            max_tokens=200,
            temperature=0.1,
        )

        response = await llm_client.generate_response(request)

        # Parse JSON response
        try:
            # Pulisci markdown wrapper se presente
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            topic_names: list[str] = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            logger.warning(
                "topic_extraction_parse_failed",
                session_id=session_id,
                raw_response=response.content[:200],
            )
            return []

        if not isinstance(topic_names, list):
            return []

        # Crea nodi Topic e relazioni nel grafo
        embedding_service = await self._get_embedding_service()
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        topics: list[TopicNode] = []
        now = datetime.now(UTC).isoformat()

        for name in topic_names[:5]:  # Max 5 topic
            if not isinstance(name, str) or not name.strip():
                continue

            name = name.strip()
            topic_id = f"topic_{tenant_id}_{name.lower().replace(' ', '_')}"

            # Embedding del topic
            topic_embedding = await embedding_service.embed_document_async(name)

            async with driver.session() as neo_session:
                # MERGE topic (riusa se esiste)
                await neo_session.run(
                    """
                    MERGE (t:Topic {id: $id})
                    SET t.name = $name,
                        t.tenant_id = $tenant_id,
                        t.embedding = $embedding
                    """,
                    {
                        "id": topic_id,
                        "name": name,
                        "tenant_id": tenant_id,
                        "embedding": topic_embedding,
                    },
                )

                # Relazione Session -> Topic
                await neo_session.run(
                    """
                    MATCH (s:Session {id: $session_id})
                    MATCH (t:Topic {id: $topic_id})
                    MERGE (s)-[r:HAS_TOPIC]->(t)
                    SET r.weight = 1.0,
                        r.extracted_at = $extracted_at
                    """,
                    {
                        "session_id": session_id,
                        "topic_id": topic_id,
                        "extracted_at": now,
                    },
                )

            topics.append(
                TopicNode(
                    id=topic_id,
                    name=name,
                    tenant_id=tenant_id,
                    embedding=topic_embedding,
                )
            )

        logger.info(
            "topics_extracted",
            session_id=session_id,
            topic_count=len(topics),
            topics=[t.name for t in topics],
        )

        # Calcola similarità con altre sessioni dopo l'estrazione
        await self._compute_session_similarities(session_id, tenant_id)

        return topics

    # ========================================================================
    # Session Similarity
    # ========================================================================

    async def _compute_session_similarities(
        self,
        session_id: str,
        tenant_id: str,
        threshold: float = 0.75,  # Raised from 0.40 to prevent false positive connections
    ) -> None:
        """Calcola similarità tra la sessione e tutte le altre del tenant.

        Crea relazioni RELATED_TO tra sessioni con similarità > threshold.

        Args:
            session_id: ID sessione sorgente
            tenant_id: ID tenant
            threshold: Soglia minima di similarità (Layer III GraphRAG)
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return

        logger.info("computing_session_similarities", session_id=session_id, threshold=threshold)

        async with driver.session() as neo_session:
            # Usa topic overlap + embedding similarity
            result = await neo_session.run(
                """
                MATCH (s1:Session {id: $session_id, tenant_id: $tenant_id})
                MATCH (s2:Session {tenant_id: $tenant_id})
                WHERE s2.id <> s1.id
                  AND s2.embedding IS NOT NULL
                  AND s1.embedding IS NOT NULL

                // Topic overlap score
                OPTIONAL MATCH (s1)-[:HAS_TOPIC]->(t:Topic)<-[:HAS_TOPIC]-(s2)
                WITH s1, s2, count(t) AS shared_topics

                // Embedding cosine similarity (using Neo4j vector function)
                WITH s1, s2, shared_topics,
                     vector.similarity.cosine(s1.embedding, s2.embedding) AS cosine_sim

                // Combined score: embedding base score + up to 15% bonus for shared topics
                WITH s1, s2,
                     CASE 
                       WHEN cosine_sim + (shared_topics * 0.05) > 1.0 THEN 1.0 
                       ELSE cosine_sim + (shared_topics * 0.05) 
                     END AS combined_score,
                     cosine_sim,
                     shared_topics

                WHERE combined_score > $threshold

                MERGE (s1)-[r:RELATED_TO]-(s2)
                SET r.similarity = combined_score,
                    r.cosine_sim = cosine_sim,
                    r.shared_topics = shared_topics,
                    r.method = 'hybrid',
                    r.updated_at = $now

                RETURN s2.id, combined_score
                ORDER BY combined_score DESC
                LIMIT 20
                """,
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "threshold": threshold,
                    "now": datetime.now(UTC).isoformat(),
                },
            )

            records = [r async for r in result]
            if records:
                logger.info(
                    "session_similarities_computed",
                    session_id=session_id,
                    related_count=len(records),
                    top_score=records[0][1] if records else 0,
                )

    # ========================================================================
    # Community Detection (Louvain)
    # ========================================================================

    async def detect_communities(
        self,
        tenant_id: str,
        min_cluster_size: int = 2,
    ) -> list[TopicCluster]:
        """Esegue community detection sulle sessioni del tenant.

        Usa Louvain algorithm implementato con NetworkX in-process
        (Neo4j Community Edition non include GDS).

        Args:
            tenant_id: ID tenant
            min_cluster_size: Minimo sessioni per formare un cluster

        Returns:
            Lista di TopicCluster identificati
        """
        import networkx as nx

        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        # 1. Carica grafo sessioni e relazioni dal Neo4j
        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (s:Session {tenant_id: $tenant_id})
                OPTIONAL MATCH (s)-[r:RELATED_TO]-(s2:Session {tenant_id: $tenant_id})
                OPTIONAL MATCH (s)-[:HAS_TOPIC]->(t:Topic)
                RETURN s.id AS session_id, s.title AS title,
                       collect(DISTINCT {id: s2.id, sim: r.similarity}) AS related,
                       collect(DISTINCT t.name) AS topics
                """,
                {"tenant_id": tenant_id},
            )

            sessions_data: dict[str, dict] = {}
            G = nx.Graph()

            async for record in result:
                sid = record["session_id"]
                sessions_data[sid] = {
                    "title": record["title"],
                    "topics": [t for t in record["topics"] if t],
                }
                G.add_node(sid)

                for rel in record["related"]:
                    if rel["id"] and rel["sim"]:
                        G.add_edge(sid, rel["id"], weight=rel["sim"])

        if len(G.nodes) < min_cluster_size:
            logger.info(
                "community_detection_skipped",
                reason="not enough sessions",
                session_count=len(G.nodes),
            )
            return []

        # 2. Esegui Louvain community detection
        try:
            from networkx.algorithms.community import louvain_communities

            communities = louvain_communities(G, weight="weight", resolution=1.0)
        except ImportError:
            logger.warning("louvain_not_available", hint="pip install networkx[community]")
            return []

        # 3. Filtra cluster troppo piccoli
        valid_communities = [c for c in communities if len(c) >= min_cluster_size]

        # 4. Genera nomi per i cluster via LLM e salva nel grafo
        clusters: list[TopicCluster] = []

        for i, community_sessions in enumerate(valid_communities):
            cluster_id = f"cluster_{tenant_id}_{i}_{uuid.uuid4().hex[:8]}"

            # Raccogli topic e titoli per il naming
            all_topics: list[str] = []
            session_titles: list[str] = []
            for sid in community_sessions:
                data = sessions_data.get(sid, {})
                all_topics.extend(data.get("topics", []))
                if data.get("title"):
                    session_titles.append(data["title"])

            # Genera nome cluster via LLM
            cluster_name, cluster_desc = await self._generate_cluster_name(
                list(set(all_topics)), session_titles
            )

            cluster = TopicCluster(
                id=cluster_id,
                name=cluster_name,
                description=cluster_desc,
                session_count=len(community_sessions),
                topics=list(set(all_topics)),
                session_ids=list(community_sessions),
            )
            clusters.append(cluster)

            # Salva cluster nel grafo
            async with driver.session() as neo_session:
                await neo_session.run(
                    """
                    MERGE (c:TopicCluster {id: $id})
                    SET c.name = $name,
                        c.description = $description,
                        c.tenant_id = $tenant_id,
                        c.session_count = $session_count,
                        c.updated_at = $now
                    """,
                    {
                        "id": cluster_id,
                        "name": cluster_name,
                        "description": cluster_desc,
                        "tenant_id": tenant_id,
                        "session_count": len(community_sessions),
                        "now": datetime.now(UTC).isoformat(),
                    },
                )

                # Collega sessioni al cluster
                for sid in community_sessions:
                    await neo_session.run(
                        """
                        MATCH (s:Session {id: $session_id})
                        MATCH (c:TopicCluster {id: $cluster_id})
                        MERGE (s)-[:BELONGS_TO]->(c)
                        """,
                        {"session_id": sid, "cluster_id": cluster_id},
                    )

        logger.info(
            "communities_detected",
            tenant_id=tenant_id,
            cluster_count=len(clusters),
            clusters=[{"name": c.name, "sessions": c.session_count} for c in clusters],
        )

        return clusters

    async def _generate_cluster_name(
        self,
        topics: list[str],
        session_titles: list[str],
    ) -> tuple[str, str]:
        """Genera nome e descrizione per un cluster via LLM.

        Returns:
            Tuple (name, description)
        """
        from me4brain.llm import LLMRequest
        from me4brain.llm.config import get_llm_config

        if not topics and not session_titles:
            return "Generale", "Sessioni non categorizzate"

        try:
            llm_client = await self._get_llm_client()
            config = get_llm_config()
            request = LLMRequest(
                messages=[
                    {
                        "role": "system",
                        "content": "Sei un esperto di categorizzazione. Rispondi SOLO con JSON valido.",
                    },
                    {
                        "role": "user",
                        "content": CLUSTER_NAMING_PROMPT.format(
                            topics=", ".join(topics[:10]),
                            sessions="\n- ".join(session_titles[:5]),
                        ),
                    },
                ],
                model=config.model_extraction,
                max_tokens=200,
                temperature=0.3,
            )

            response = await llm_client.generate_response(request)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(content)
            name = data.get("name", topics[0] if topics else "Generale")
            icon = data.get("icon", "📁")
            desc = data.get("description", "")
            return f"{icon} {name}", desc

        except Exception as e:
            logger.warning("cluster_naming_failed", error=str(e))
            # Fallback: usa il topic più frequente
            return topics[0] if topics else "Generale", ""

    # ========================================================================
    # Retrieval & Search
    # ========================================================================

    async def get_session_clusters(
        self,
        tenant_id: str,
    ) -> list[TopicCluster]:
        """Recupera i cluster tematici per un tenant.

        Returns:
            Lista di TopicCluster con le sessioni associate
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (c:TopicCluster {tenant_id: $tenant_id})
                OPTIONAL MATCH (s:Session)-[:BELONGS_TO]->(c)
                OPTIONAL MATCH (s)-[:HAS_TOPIC]->(t:Topic)
                WITH c,
                     collect(DISTINCT s.id) AS session_ids,
                     collect(DISTINCT t.name) AS topic_names,
                     count(DISTINCT s) AS session_count
                RETURN c.id, c.name, c.description, session_count,
                       session_ids, topic_names
                ORDER BY session_count DESC
                """,
                {"tenant_id": tenant_id},
            )

            clusters: list[TopicCluster] = []
            async for record in result:
                clusters.append(
                    TopicCluster(
                        id=record[0],
                        name=record[1] or "Generale",
                        description=record[2] or "",
                        session_count=record[3],
                        session_ids=[s for s in record[4] if s],
                        topics=[t for t in record[5] if t],
                    )
                )

            return clusters

    async def get_related_sessions(
        self,
        session_id: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[SessionSearchResult]:
        """Recupera sessioni correlate via graph traversal.

        Args:
            session_id: ID sessione sorgente
            tenant_id: ID tenant
            limit: Numero massimo di risultati

        Returns:
            Lista di SessionSearchResult ordinate per rilevanza
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (s1:Session {id: $session_id, tenant_id: $tenant_id})
                      -[r:RELATED_TO]-(s2:Session {tenant_id: $tenant_id})
                OPTIONAL MATCH (s2)-[:HAS_TOPIC]->(t:Topic)
                OPTIONAL MATCH (s2)-[:BELONGS_TO]->(c:TopicCluster)
                RETURN s2.id, s2.title, r.similarity,
                       collect(DISTINCT t.name) AS topics,
                       c.name AS cluster_name,
                       s2.turn_count, s2.updated_at
                ORDER BY r.similarity DESC
                LIMIT $limit
                """,
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "limit": limit,
                },
            )

            results: list[SessionSearchResult] = []
            async for record in result:
                results.append(
                    SessionSearchResult(
                        session_id=record[0],
                        title=record[1] or "Senza titolo",
                        score=record[2] or 0.0,
                        topics=[t for t in record[3] if t],
                        cluster_name=record[4] or "",
                        turn_count=record[5] or 0,
                        updated_at=record[6] or "",
                    )
                )

            return results

    async def get_connected_nodes(
        self,
        session_id: str,
        tenant_id: str,
        top_k: int = 3,
    ) -> list[ConnectedNode]:
        """Trova i nodi del grafo più connessi a una sessione.

        Attraversa il grafo per trovare entità (topic, sessioni, cluster)
        che fungono da hub di connessione, permettendo esplorazione esterna.

        Scoring composito:
        - Topic condivisi con altre sessioni (peso alto)
        - Sessioni correlate con più relazioni 2-hop (peso medio)
        - Cluster di appartenenza (contesto)

        Args:
            session_id: ID sessione sorgente
            tenant_id: ID tenant
            top_k: Numero massimo di nodi da restituire

        Returns:
            Lista di ConnectedNode ordinati per connection_score
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        nodes: list[ConnectedNode] = []

        async with driver.session() as neo_session:
            # 1. Topic hub: topic della sessione più connessi ad altre sessioni
            topic_result = await neo_session.run(
                """
                MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})
                      -[:HAS_TOPIC]->(t:Topic)
                OPTIONAL MATCH (t)<-[:HAS_TOPIC]-(other:Session)
                WHERE other.id <> $session_id
                WITH t, count(DISTINCT other) AS shared_count,
                     collect(DISTINCT other.title)[..3] AS sample_titles
                RETURN t.id, t.name, shared_count, sample_titles
                ORDER BY shared_count DESC
                LIMIT $limit
                """,
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "limit": top_k * 2,
                },
            )

            async for record in topic_result:
                sample = record[3] or []
                desc = f"Presente in {record[2]} sessioni" + (
                    f" (es. {', '.join(sample[:2])})" if sample else ""
                )
                nodes.append(
                    ConnectedNode(
                        id=record[0],
                        name=record[1],
                        node_type="topic",
                        connection_score=float(record[2]) * 1.5,
                        relation_type="HAS_TOPIC",
                        shared_sessions=record[2],
                        description=desc,
                    )
                )

            # 2. Sessioni hub: sessioni 2-hop (s -> related -> related)
            hub_result = await neo_session.run(
                """
                MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})
                      -[r1:RELATED_TO]-(bridge:Session)
                      -[r2:RELATED_TO]-(hub:Session {tenant_id: $tenant_id})
                WHERE hub.id <> $session_id
                  AND hub.id <> bridge.id
                  AND r1.similarity > 0.70
                  AND r2.similarity > 0.70
                WITH hub,
                     count(DISTINCT bridge) AS bridge_count,
                     avg(r2.similarity) AS avg_sim
                RETURN hub.id, hub.title, bridge_count, avg_sim
                ORDER BY bridge_count DESC, avg_sim DESC
                LIMIT $limit
                """,
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "limit": top_k,
                },
            )

            async for record in hub_result:
                sim = record[3] or 0.0
                nodes.append(
                    ConnectedNode(
                        id=record[0],
                        name=record[1] or "Sessione correlata",
                        node_type="session",
                        connection_score=float(record[2]) + sim,
                        relation_type="RELATED_TO (2-hop)",
                        shared_sessions=record[2],
                        description=(
                            f"Raggiungibile via {record[2]} sessioni ponte (sim. media {sim:.0%})"
                        ),
                    )
                )

            # 3. Cluster di appartenenza con contesto
            cluster_result = await neo_session.run(
                """
                MATCH (s:Session {id: $session_id})
                      -[:BELONGS_TO]->(c:TopicCluster)
                OPTIONAL MATCH (other:Session)-[:BELONGS_TO]->(c)
                WHERE other.id <> $session_id
                RETURN c.id, c.name, c.description,
                       count(DISTINCT other) AS sibling_count
                ORDER BY sibling_count DESC
                LIMIT 2
                """,
                {"session_id": session_id},
            )

            async for record in cluster_result:
                nodes.append(
                    ConnectedNode(
                        id=record[0],
                        name=record[1] or "Cluster",
                        node_type="cluster",
                        connection_score=float(record[3]) * 0.8,
                        relation_type="BELONGS_TO",
                        shared_sessions=record[3],
                        description=record[2] or f"{record[3]} sessioni nel cluster",
                    )
                )

        # Sort complessivo e take top_k
        nodes.sort(key=lambda n: n.connection_score, reverse=True)
        return nodes[:top_k]

    async def search_sessions_semantic(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        use_reranking: bool = True,
    ) -> list[SessionSearchResult]:
        """Ricerca semantica sessioni con pipeline 5-stage.

        Pipeline:
        1. BGE-M3 Embedding della query
        2. Neo4j Vector Search (top-50 candidati)
        3. Graph Boost (PageRank personalizzato)
        4. LLM Reranking (opzionale, via LlamaIndex LLMRerank)
        5. Risultati finali ordinati

        Args:
            query: Query di ricerca
            tenant_id: ID tenant
            top_k: Numero di risultati
            use_reranking: Se attivare LLM reranking (Stage 4)

        Returns:
            Lista ordinata di SessionSearchResult
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        # Stage 1: Embedding della query
        embedding_service = await self._get_embedding_service()
        query_embedding = await embedding_service.embed_query_async(query)

        # Stage 2: Neo4j Vector Search (candidati)
        async with driver.session() as neo_session:
            try:
                # Prova vector index nativo (Neo4j 5.11+)
                result = await neo_session.run(
                    """
                    CALL db.index.vector.queryNodes(
                        'session_embedding', $top_k, $embedding
                    ) YIELD node, score
                    WHERE node.tenant_id = $tenant_id
                    OPTIONAL MATCH (node)-[:HAS_TOPIC]->(t:Topic)
                    OPTIONAL MATCH (node)-[:BELONGS_TO]->(c:TopicCluster)
                    RETURN node.id, node.title, score,
                           collect(DISTINCT t.name) AS topics,
                           c.name AS cluster_name,
                           node.turn_count, node.updated_at
                    ORDER BY score DESC
                    LIMIT $top_k
                    """,
                    {
                        "embedding": query_embedding,
                        "tenant_id": tenant_id,
                        "top_k": min(top_k * 5, 50),  # Over-fetch per reranking
                    },
                )
            except Exception:
                # Fallback: cosine similarity manuale (senza vector index)
                result = await neo_session.run(
                    """
                    MATCH (s:Session {tenant_id: $tenant_id})
                    WHERE s.embedding IS NOT NULL
                    WITH s, vector.similarity.cosine(s.embedding, $embedding) AS score
                    WHERE score > 0.3
                    OPTIONAL MATCH (s)-[:HAS_TOPIC]->(t:Topic)
                    OPTIONAL MATCH (s)-[:BELONGS_TO]->(c:TopicCluster)
                    RETURN s.id, s.title, score,
                           collect(DISTINCT t.name) AS topics,
                           c.name AS cluster_name,
                           s.turn_count, s.updated_at
                    ORDER BY score DESC
                    LIMIT $top_k
                    """,
                    {
                        "embedding": query_embedding,
                        "tenant_id": tenant_id,
                        "top_k": min(top_k * 5, 50),
                    },
                )

            candidates: list[SessionSearchResult] = []
            async for record in result:
                candidates.append(
                    SessionSearchResult(
                        session_id=record[0],
                        title=record[1] or "Senza titolo",
                        score=float(record[2]),
                        topics=[t for t in record[3] if t],
                        cluster_name=record[4] or "",
                        turn_count=record[5] or 0,
                        updated_at=record[6] or "",
                    )
                )

        if not candidates:
            return []

        # Stage 3: Graph Boost (via shared topics/relations)
        for candidate in candidates:
            if len(candidate.topics) > 0:
                # Boost sessioni con più topic (informazione più ricca)
                topic_boost = min(len(candidate.topics) * 0.02, 0.1)
                candidate.score += topic_boost

        # Stage 4: LLM Reranking (opzionale)
        if use_reranking and len(candidates) > top_k:
            candidates = await self._llm_rerank(query, candidates, top_k)
        else:
            candidates.sort(key=lambda x: x.score, reverse=True)
            candidates = candidates[:top_k]

        return candidates

    async def _llm_rerank(
        self,
        query: str,
        candidates: list[SessionSearchResult],
        top_k: int,
    ) -> list[SessionSearchResult]:
        """Reranking via LlamaIndex LLMRerank.

        Usa NanoGPTLlamaIndexAdapter per reranking fine-grained.
        """
        try:
            from llama_index.core.postprocessor import LLMRerank
            from llama_index.core.schema import NodeWithScore, TextNode

            from me4brain.llm.llamaindex_adapter import get_llamaindex_llm

            llm = get_llamaindex_llm()
            reranker = LLMRerank(llm=llm, top_n=top_k)

            # Converti candidati in nodi LlamaIndex
            nodes = []
            for c in candidates:
                node = TextNode(
                    text=f"Sessione: {c.title}\nTopic: {', '.join(c.topics)}",
                    metadata={
                        "session_id": c.session_id,
                        "original_score": c.score,
                    },
                )
                nodes.append(NodeWithScore(node=node, score=c.score))

            # Rerank
            reranked = reranker.postprocess_nodes(nodes, query_str=query)

            # Ricostruisci risultati
            reranked_results: list[SessionSearchResult] = []
            for rn in reranked:
                sid = rn.node.metadata.get("session_id")
                for c in candidates:
                    if c.session_id == sid:
                        c.score = rn.score or c.score
                        reranked_results.append(c)
                        break

            logger.info(
                "session_reranking_complete",
                query=query[:50],
                input_count=len(candidates),
                output_count=len(reranked_results),
            )

            return reranked_results

        except Exception as e:
            logger.warning("session_reranking_failed", error=str(e))
            # Fallback: ritorna candidati ordinati per score originale
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:top_k]

    # ========================================================================
    # Topics & Prompts
    # ========================================================================

    async def get_topics(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Recupera tutti i topic con conteggio sessioni.

        Returns:
            Lista di dict con {id, name, session_count}
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (t:Topic {tenant_id: $tenant_id})
                OPTIONAL MATCH (s:Session)-[:HAS_TOPIC]->(t)
                RETURN t.id, t.name, count(s) AS session_count
                ORDER BY session_count DESC
                LIMIT $limit
                """,
                {"tenant_id": tenant_id, "limit": limit},
            )

            topics: list[dict[str, Any]] = []
            async for record in result:
                topics.append(
                    {
                        "id": record[0],
                        "name": record[1],
                        "session_count": record[2],
                    }
                )

            return topics

    # ========================================================================
    # Prompt Library
    # ========================================================================

    async def save_prompt_template(
        self,
        prompt: PromptTemplateNode,
    ) -> str:
        """Salva un prompt template nel grafo.

        Args:
            prompt: PromptTemplateNode da salvare

        Returns:
            ID del prompt
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            raise RuntimeError("Neo4j non disponibile")

        await self.initialize_schema()

        embedding_service = await self._get_embedding_service()
        prompt_embedding = await embedding_service.embed_document_async(
            f"{prompt.label}: {prompt.content}"
        )

        async with driver.session() as neo_session:
            prompt_id = prompt.id or f"prompt_{uuid.uuid4().hex[:12]}"

            await neo_session.run(
                """
                MERGE (p:PromptTemplate {id: $id})
                SET p.label = $label,
                    p.content = $content,
                    p.category = $category,
                    p.tenant_id = $tenant_id,
                    p.usage_count = $usage_count,
                    p.last_used_at = $last_used_at,
                    p.variables = $variables,
                    p.embedding = $embedding,
                    p.updated_at = $now
                """,
                {
                    "id": prompt_id,
                    "label": prompt.label,
                    "content": prompt.content,
                    "category": prompt.category,
                    "tenant_id": prompt.tenant_id,
                    "usage_count": prompt.usage_count,
                    "last_used_at": prompt.last_used_at,
                    "variables": prompt.variables,
                    "embedding": prompt_embedding,
                    "now": datetime.now(UTC).isoformat(),
                },
            )

            # Collega ai topic specificati
            for topic_name in prompt.topics:
                topic_id = f"topic_{prompt.tenant_id}_{topic_name.lower().replace(' ', '_')}"
                await neo_session.run(
                    """
                    MERGE (t:Topic {id: $topic_id})
                    ON CREATE SET t.name = $name, t.tenant_id = $tenant_id
                    WITH t
                    MATCH (p:PromptTemplate {id: $prompt_id})
                    MERGE (p)-[:FOR_TOPIC]->(t)
                    """,
                    {
                        "topic_id": topic_id,
                        "name": topic_name,
                        "tenant_id": prompt.tenant_id,
                        "prompt_id": prompt_id,
                    },
                )

        logger.info(
            "prompt_template_saved",
            prompt_id=prompt_id,
            label=prompt.label,
        )

        return prompt_id

    async def get_prompt_library(
        self,
        tenant_id: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recupera la libreria prompt.

        Args:
            tenant_id: ID tenant
            category: Filtro opzionale per categoria

        Returns:
            Lista di prompt template con topic associati
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        where_clause = "WHERE p.tenant_id = $tenant_id"
        if category:
            where_clause += " AND p.category = $category"

        async with driver.session() as neo_session:
            result = await neo_session.run(
                f"""
                MATCH (p:PromptTemplate)
                {where_clause}
                OPTIONAL MATCH (p)-[:FOR_TOPIC]->(t:Topic)
                RETURN p.id, p.label, p.content, p.category,
                       collect(DISTINCT t.name) AS topics,
                       p.usage_count, p.last_used_at, p.variables
                ORDER BY p.usage_count DESC
                """,
                {"tenant_id": tenant_id, "category": category},
            )

            prompts: list[dict[str, Any]] = []
            async for record in result:
                prompts.append(
                    {
                        "id": record[0],
                        "label": record[1],
                        "content": record[2],
                        "category": record[3] or "general",
                        "topics": [t for t in record[4] if t],
                        "usage_count": record[5] or 0,
                        "last_used_at": record[6],
                        "variables": record[7] or [],
                    }
                )

            return prompts

    async def search_prompts_semantic(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Ricerca semantica prompt.

        Args:
            query: Query di ricerca
            tenant_id: ID tenant
            top_k: Numero di risultati

        Returns:
            Lista di prompt ordinati per rilevanza
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        embedding_service = await self._get_embedding_service()
        query_embedding = await embedding_service.embed_query_async(query)

        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (p:PromptTemplate {tenant_id: $tenant_id})
                WHERE p.embedding IS NOT NULL
                WITH p, vector.similarity.cosine(p.embedding, $embedding) AS score
                WHERE score > 0.3
                OPTIONAL MATCH (p)-[:FOR_TOPIC]->(t:Topic)
                RETURN p.id, p.label, p.content, p.category,
                       collect(DISTINCT t.name) AS topics,
                       p.usage_count, score
                ORDER BY score DESC
                LIMIT $top_k
                """,
                {
                    "embedding": query_embedding,
                    "tenant_id": tenant_id,
                    "top_k": top_k,
                },
            )

            results: list[dict[str, Any]] = []
            async for record in result:
                results.append(
                    {
                        "id": record[0],
                        "label": record[1],
                        "content": record[2],
                        "category": record[3] or "general",
                        "topics": [t for t in record[4] if t],
                        "usage_count": record[5] or 0,
                        "score": record[6],
                    }
                )

            return results

    async def suggest_prompts_for_session(
        self,
        session_id: str,
        tenant_id: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Suggerisce prompt rilevanti per la sessione corrente.

        Trova prompt che condividono topic con la sessione.

        Args:
            session_id: ID sessione
            tenant_id: ID tenant
            top_k: Numero di suggerimenti

        Returns:
            Lista di prompt suggeriti
        """
        driver = await self.semantic.get_driver()
        if driver is None:
            return []

        async with driver.session() as neo_session:
            result = await neo_session.run(
                """
                MATCH (s:Session {id: $session_id, tenant_id: $tenant_id})
                      -[:HAS_TOPIC]->(t:Topic)
                      <-[:FOR_TOPIC]-(p:PromptTemplate {tenant_id: $tenant_id})
                WITH p, count(t) AS shared_topics
                OPTIONAL MATCH (p)-[:FOR_TOPIC]->(t2:Topic)
                RETURN p.id, p.label, p.content, p.category,
                       collect(DISTINCT t2.name) AS topics,
                       shared_topics, p.usage_count
                ORDER BY shared_topics DESC, p.usage_count DESC
                LIMIT $top_k
                """,
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "top_k": top_k,
                },
            )

            results: list[dict[str, Any]] = []
            async for record in result:
                results.append(
                    {
                        "id": record[0],
                        "label": record[1],
                        "content": record[2],
                        "category": record[3] or "general",
                        "topics": [t for t in record[4] if t],
                        "shared_topics": record[5],
                        "usage_count": record[6] or 0,
                    }
                )

            return results

    # ========================================================================
    # Reindex (Migration)
    # ========================================================================

    async def reindex_all_sessions(
        self,
        tenant_id: str,
        sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Reindicizza tutte le sessioni esistenti nel grafo.

        Per migrazione da sistema legacy (Redis-only) al grafo.

        Args:
            tenant_id: ID tenant
            sessions: Lista di sessioni con {id, title, turns[], created_at, updated_at}

        Returns:
            Report della migrazione {total, success, errors}
        """
        report = {"total": len(sessions), "success": 0, "errors": 0, "error_details": []}

        for session_data in sessions:
            try:
                await self.ingest_session(
                    session_id=session_data["id"],
                    tenant_id=tenant_id,
                    title=session_data.get("title", "Senza titolo"),
                    turns=session_data.get("turns", []),
                    created_at=session_data.get("created_at"),
                    updated_at=session_data.get("updated_at"),
                )
                report["success"] += 1
            except Exception as e:
                report["errors"] += 1
                report["error_details"].append(
                    {"session_id": session_data.get("id"), "error": str(e)}
                )
                logger.warning(
                    "reindex_session_failed",
                    session_id=session_data.get("id"),
                    error=str(e),
                )

        # Dopo il reindex, esegui community detection
        if report["success"] > 0:
            try:
                clusters = await self.detect_communities(tenant_id)
                report["clusters_created"] = len(clusters)
            except Exception as e:
                logger.warning("post_reindex_community_detection_failed", error=str(e))

        logger.info(
            "reindex_complete",
            tenant_id=tenant_id,
            total=report["total"],
            success=report["success"],
            errors=report["errors"],
        )

        return report


# ============================================================================
# Singleton
# ============================================================================

_session_graph: SessionKnowledgeGraph | None = None


def get_session_graph() -> SessionKnowledgeGraph:
    """Ottiene l'istanza singleton del SessionKnowledgeGraph."""
    global _session_graph
    if _session_graph is None:
        _session_graph = SessionKnowledgeGraph()
    return _session_graph
