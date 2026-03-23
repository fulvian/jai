"""LlamaIndex Bridge - Hybrid Retrieval con Neo4j + Qdrant.

Integra LlamaIndex con il sistema di memoria Me4BrAIn:
- Neo4jPropertyGraphStore per Semantic Memory
- QdrantVectorStore per Episodic Memory
- SubQuestionQueryEngine per query decomposition
"""

from typing import Any

import structlog
from llama_index.core import PropertyGraphIndex, Settings, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.query_engine import SubQuestionQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from pydantic import BaseModel, PrivateAttr

from me4brain.config import get_settings
from me4brain.embeddings import get_embedding_service

logger = structlog.get_logger(__name__)


class Me4BrAInEmbedding(BaseEmbedding):
    """Adapter per riusare il BGEM3Service esistente di Me4BrAIn.

    Evita di riscaricare il modello BGE-M3 già in cache.
    """

    _service: Any = PrivateAttr()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = get_embedding_service()

    @classmethod
    def class_name(cls) -> str:
        return "Me4BrAInEmbedding"

    def _get_query_embedding(self, query: str) -> list[float]:
        """Genera embedding per una query."""
        return self._service.embed_query(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        """Genera embedding per un testo."""
        return self._service.embed_query(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Genera embedding per più testi."""
        return self._service.embed_documents(texts)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)


class HybridRetrievalResult(BaseModel):
    """Risultato del retrieval ibrido LlamaIndex."""

    answer: str
    source_nodes: list[dict[str, Any]]
    sub_questions: list[str] = []


class LlamaIndexBridge:
    """Bridge tra LlamaIndex e Me4BrAIn memory layers.

    Fornisce:
    - PropertyGraphIndex su Neo4j (Semantic Memory)
    - VectorStoreIndex su Qdrant (Episodic Memory)
    - SubQuestionQueryEngine per query complesse
    """

    def __init__(self) -> None:
        """Inizializza il bridge con le configurazioni Me4BrAIn."""
        self._settings = get_settings()
        self._initialized = False
        self._graph_store: Neo4jPropertyGraphStore | None = None
        self._vector_store: QdrantVectorStore | None = None
        self._property_index: PropertyGraphIndex | None = None
        self._vector_index: VectorStoreIndex | None = None

    async def initialize(self) -> None:
        """Inizializza LlamaIndex con gli store Me4BrAIn."""
        if self._initialized:
            return

        # Riusa BGEM3Service esistente (nessun download!)
        Settings.embed_model = Me4BrAInEmbedding()
        logger.info("llamaindex_embedding_initialized", model="BGEM3Service (cached)")

        # Neo4j PropertyGraphStore
        try:
            self._graph_store = Neo4jPropertyGraphStore(
                url=self._settings.neo4j_uri,
                username=self._settings.neo4j_user,
                password=self._settings.neo4j_password.get_secret_value(),
            )
            logger.info("llamaindex_neo4j_connected", uri=self._settings.neo4j_uri)
        except Exception as e:
            logger.warning("llamaindex_neo4j_failed", error=str(e))
            self._graph_store = None

        # Qdrant VectorStore (sync client per compatibilità LlamaIndex)
        try:
            from qdrant_client import QdrantClient

            qdrant_client = QdrantClient(
                host=self._settings.qdrant_host,
                port=self._settings.qdrant_http_port,
            )
            self._vector_store = QdrantVectorStore(
                client=qdrant_client,
                collection_name="episodic_memories",
            )
            logger.info(
                "llamaindex_qdrant_connected",
                host=self._settings.qdrant_host,
            )
        except Exception as e:
            logger.warning("llamaindex_qdrant_failed", error=str(e))
            self._vector_store = None

        self._initialized = True

    def get_graph_store(self) -> Neo4jPropertyGraphStore | None:
        """Ottiene il Neo4j PropertyGraphStore."""
        return self._graph_store

    def get_vector_store(self) -> QdrantVectorStore | None:
        """Ottiene il Qdrant VectorStore."""
        return self._vector_store

    async def create_hybrid_query_engine(self) -> SubQuestionQueryEngine | None:
        """Crea un SubQuestionQueryEngine per query decomposition.

        Combina:
        - Graph query engine (Neo4j) per relazioni semantiche
        - Vector query engine (Qdrant) per similarità vettoriale
        """
        if not self._initialized:
            await self.initialize()

        tools = []

        # Vector Query Engine (Episodic Memory)
        if self._vector_store:
            try:
                self._vector_index = VectorStoreIndex.from_vector_store(self._vector_store)
                vector_engine = self._vector_index.as_query_engine()
                tools.append(
                    QueryEngineTool(
                        query_engine=vector_engine,
                        metadata=ToolMetadata(
                            name="episodic_memory",
                            description=(
                                "Query per ricordi, episodi, conversazioni passate. "
                                "Usa per: 'cosa abbiamo discusso', 'ricordi di...', "
                                "'conversazioni precedenti su...'"
                            ),
                        ),
                    )
                )
            except Exception as e:
                logger.warning("vector_engine_creation_failed", error=str(e))

        # Graph Query Engine (Semantic Memory)
        if self._graph_store:
            try:
                self._property_index = PropertyGraphIndex.from_existing(
                    property_graph_store=self._graph_store,
                )
                graph_engine = self._property_index.as_query_engine()
                tools.append(
                    QueryEngineTool(
                        query_engine=graph_engine,
                        metadata=ToolMetadata(
                            name="semantic_memory",
                            description=(
                                "Query per concetti, entità, relazioni nel grafo. "
                                "Usa per: 'relazione tra X e Y', 'cos'è...', "
                                "'entità correlate a...'"
                            ),
                        ),
                    )
                )
            except Exception as e:
                logger.warning("graph_engine_creation_failed", error=str(e))

        if not tools:
            logger.error("no_query_engines_available")
            return None

        # SubQuestionQueryEngine per decomposizione automatica
        sub_question_engine = SubQuestionQueryEngine.from_defaults(
            query_engine_tools=tools,
            use_async=True,
        )

        logger.info("hybrid_query_engine_created", tools=len(tools))
        return sub_question_engine

    async def hybrid_retrieval(
        self,
        query: str,
        tenant_id: str,
    ) -> HybridRetrievalResult:
        """Esegue retrieval ibrido con query decomposition.

        Args:
            query: La query dell'utente
            tenant_id: ID tenant per isolation

        Returns:
            HybridRetrievalResult con risposta e source nodes
        """
        engine = await self.create_hybrid_query_engine()
        if engine is None:
            return HybridRetrievalResult(
                answer="Nessun engine disponibile per la query.",
                source_nodes=[],
            )

        try:
            response = await engine.aquery(query)

            # Estrai source nodes
            source_nodes = []
            for node in response.source_nodes:
                source_nodes.append(
                    {
                        "text": node.text[:500] if node.text else "",
                        "score": node.score,
                        "metadata": node.metadata,
                    }
                )

            # Estrai sub-questions se disponibili
            sub_questions = []
            if hasattr(response, "metadata") and "sub_questions" in response.metadata:
                sub_questions = response.metadata["sub_questions"]

            return HybridRetrievalResult(
                answer=str(response),
                source_nodes=source_nodes,
                sub_questions=sub_questions,
            )

        except Exception as e:
            logger.error("hybrid_retrieval_failed", error=str(e))
            return HybridRetrievalResult(
                answer=f"Errore nel retrieval: {e}",
                source_nodes=[],
            )

    async def close(self) -> None:
        """Chiude le connessioni."""
        if self._graph_store:
            # Neo4j store gestisce il cleanup internamente
            self._graph_store = None
        logger.debug("llamaindex_bridge_closed")


# Singleton
_bridge: LlamaIndexBridge | None = None


def get_llamaindex_bridge() -> LlamaIndexBridge:
    """Ottiene l'istanza singleton del LlamaIndexBridge."""
    global _bridge
    if _bridge is None:
        _bridge = LlamaIndexBridge()
    return _bridge
