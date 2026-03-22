"""Semantic Router - Query Classification.

Decide il percorso di retrieval ottimale per ogni query:
- Vector Only: query semplici, fact-checking
- Graph Only: query relazionali, causali
- Hybrid: query complesse che richiedono entrambi
"""

from enum import Enum

import structlog
from pydantic import BaseModel

from me4brain.embeddings import get_embedding_service

logger = structlog.get_logger(__name__)


class QueryType(str, Enum):
    """Tipo di query rilevato."""

    SIMPLE = "simple"  # Fatti singoli, lookup
    RELATIONAL = "relational"  # Chi/cosa è collegato a X
    CAUSAL = "causal"  # Perché X, causa di Y
    TEMPORAL = "temporal"  # Quando, prima/dopo
    PROCEDURAL = "procedural"  # Come fare X
    CONVERSATIONAL = "conversational"  # Chit-chat, saluti


class RoutingDecision(str, Enum):
    """Decisione di routing."""

    VECTOR_ONLY = "vector_only"
    GRAPH_ONLY = "graph_only"
    HYBRID = "hybrid"
    TOOL_REQUIRED = "tool_required"
    NO_RETRIEVAL = "no_retrieval"


class RouterResult(BaseModel):
    """Risultato del routing."""

    query_type: QueryType
    decision: RoutingDecision
    confidence: float
    reasoning: str


# Pattern per classificazione euristica
RELATIONAL_PATTERNS = [
    "chi è collegato",
    "relazione tra",
    "connesso a",
    "chi conosce",
    "chi lavora con",
    "quali sono i",
    "elenca tutti",
    "who is related",
    "connected to",
    "relationship between",
]

CAUSAL_PATTERNS = [
    "perché",
    "causa di",
    "motivo di",
    "conseguenza",
    "effetto di",
    "why",
    "because",
    "reason for",
    "due to",
]

TEMPORAL_PATTERNS = [
    "quando",
    "prima di",
    "dopo di",
    "durante",
    "nel periodo",
    "when",
    "before",
    "after",
    "during",
]

PROCEDURAL_PATTERNS = [
    "come faccio",
    "come posso",
    "come si fa",
    "come funziona",
    "come eseguire",
    "procedura per",
    "steps to",
    "how to",
    "how do i",
    "tutorial",
]

CONVERSATIONAL_PATTERNS = [
    "ciao ",
    "ciao!",
    "ciao,",
    "buongiorno",
    "grazie",
    "hello",
    "hi ",
    "hi!",
    "thanks",
    "bye",
    "arrivederci",
    "chi sei",
]


class SemanticRouter:
    """Router semantico per classificazione query.

    Utilizza una combinazione di:
    1. Pattern matching euristico (veloce)
    2. Embedding similarity con prototipi (accurato)
    """

    # Prototipi per ogni tipo di query (pre-computati)
    QUERY_PROTOTYPES: dict[QueryType, list[str]] = {
        QueryType.SIMPLE: [
            "Qual è il nome del progetto?",
            "Quanti utenti ci sono?",
            "Cosa significa X?",
        ],
        QueryType.RELATIONAL: [
            "Chi lavora con Mario?",
            "Quali progetti sono collegati?",
            "Mostrami le dipendenze",
        ],
        QueryType.CAUSAL: [
            "Perché il sistema è lento?",
            "Qual è la causa dell'errore?",
            "Cosa ha provocato il problema?",
        ],
        QueryType.TEMPORAL: [
            "Quando è stato creato?",
            "Cosa è successo prima?",
            "Cronologia degli eventi",
        ],
        QueryType.PROCEDURAL: [
            "Come posso configurare?",
            "Qual è la procedura?",
            "Passaggi per installare",
        ],
        QueryType.CONVERSATIONAL: [
            "Ciao, come stai?",
            "Grazie mille!",
            "Arrivederci",
        ],
    }

    # Mapping QueryType -> RoutingDecision
    TYPE_TO_DECISION: dict[QueryType, RoutingDecision] = {
        QueryType.SIMPLE: RoutingDecision.VECTOR_ONLY,
        QueryType.RELATIONAL: RoutingDecision.GRAPH_ONLY,
        QueryType.CAUSAL: RoutingDecision.HYBRID,
        QueryType.TEMPORAL: RoutingDecision.HYBRID,
        QueryType.PROCEDURAL: RoutingDecision.TOOL_REQUIRED,
        QueryType.CONVERSATIONAL: RoutingDecision.NO_RETRIEVAL,
    }

    def __init__(self) -> None:
        """Inizializza il router."""
        self._prototype_embeddings: dict[QueryType, list[list[float]]] | None = None

    def _compute_prototype_embeddings(self) -> dict[QueryType, list[list[float]]]:
        """Calcola embeddings dei prototipi (lazy, cached)."""
        if self._prototype_embeddings is not None:
            return self._prototype_embeddings

        embedding_service = get_embedding_service()
        self._prototype_embeddings = {}

        for query_type, prototypes in self.QUERY_PROTOTYPES.items():
            embeddings = embedding_service.embed_documents(prototypes)
            self._prototype_embeddings[query_type] = embeddings

        logger.info("router_prototypes_computed", types=len(self._prototype_embeddings))
        return self._prototype_embeddings

    def _pattern_match(self, query: str) -> tuple[QueryType | None, float]:
        """Classifica query tramite pattern matching.

        Returns:
            (QueryType, confidence) o (None, 0) se nessun match
        """
        query_lower = query.lower()

        # Pattern procedurali
        for pattern in PROCEDURAL_PATTERNS:
            if pattern in query_lower:
                return QueryType.PROCEDURAL, 0.85

        # Pattern causali
        for pattern in CAUSAL_PATTERNS:
            if pattern in query_lower:
                return QueryType.CAUSAL, 0.8

        # Pattern relazionali
        for pattern in RELATIONAL_PATTERNS:
            if pattern in query_lower:
                return QueryType.RELATIONAL, 0.8

        # Pattern temporali
        for pattern in TEMPORAL_PATTERNS:
            if pattern in query_lower:
                return QueryType.TEMPORAL, 0.75

        # Controlla pattern conversazionali (priorità bassa per evitare collisioni tipo 'hi'/'chi')
        for pattern in CONVERSATIONAL_PATTERNS:
            if pattern in query_lower:
                # Se è un match esatto o seguito da spazio/punteggiatura
                if (
                    pattern.strip() == query_lower.strip()
                    or f" {pattern.strip()} " in f" {query_lower} "
                ):
                    return QueryType.CONVERSATIONAL, 0.9

        return None, 0.0

    def _semantic_match(
        self,
        query_embedding: list[float],
    ) -> tuple[QueryType, float]:
        """Classifica query tramite similarity con prototipi.

        Returns:
            (QueryType, confidence)
        """
        import numpy as np

        prototype_embeddings = self._compute_prototype_embeddings()

        best_type = QueryType.SIMPLE
        best_score = 0.0

        query_vec = np.array(query_embedding)

        for query_type, embeddings in prototype_embeddings.items():
            # Calcola similarity media con prototipi del tipo
            similarities = []
            for proto_emb in embeddings:
                proto_vec = np.array(proto_emb)
                # Cosine similarity
                sim = np.dot(query_vec, proto_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(proto_vec) + 1e-8
                )
                similarities.append(sim)

            avg_sim = np.mean(similarities)

            if avg_sim > best_score:
                best_score = float(avg_sim)
                best_type = query_type

        return best_type, best_score

    def route(
        self,
        query: str,
        query_embedding: list[float] | None = None,
    ) -> RouterResult:
        """Classifica una query e determina il routing.

        Args:
            query: La query utente
            query_embedding: Embedding pre-calcolato (opzionale)

        Returns:
            RouterResult con tipo, decisione e confidence
        """
        # Step 1: Pattern matching (veloce)
        pattern_type, pattern_conf = self._pattern_match(query)

        if pattern_type is not None and pattern_conf > 0.8:
            decision = self.TYPE_TO_DECISION[pattern_type]
            return RouterResult(
                query_type=pattern_type,
                decision=decision,
                confidence=pattern_conf,
                reasoning=f"Pattern match: detected {pattern_type.value} pattern",
            )

        # Step 2: Semantic matching (accurato)
        if query_embedding is None:
            embedding_service = get_embedding_service()
            query_embedding = embedding_service.embed_query(query)

        semantic_type, semantic_conf = self._semantic_match(query_embedding)

        # Combina risultati se abbiamo match parziale da pattern
        if pattern_type is not None and pattern_conf > 0.5:
            # Usa pattern type se similarity è vicina
            if abs(semantic_conf - pattern_conf) < 0.15:
                final_type = pattern_type
                final_conf = (pattern_conf + semantic_conf) / 2
            else:
                # Usa il più confident
                if pattern_conf > semantic_conf:
                    final_type = pattern_type
                    final_conf = pattern_conf
                else:
                    final_type = semantic_type
                    final_conf = semantic_conf
        else:
            final_type = semantic_type
            final_conf = semantic_conf

        decision = self.TYPE_TO_DECISION[final_type]

        logger.debug(
            "query_routed",
            query=query[:50],
            query_type=final_type.value,
            decision=decision.value,
            confidence=final_conf,
        )

        return RouterResult(
            query_type=final_type,
            decision=decision,
            confidence=final_conf,
            reasoning=f"Semantic similarity: {final_type.value} (conf={final_conf:.2f})",
        )


# Singleton
_router: SemanticRouter | None = None


def get_semantic_router() -> SemanticRouter:
    """Ottiene l'istanza singleton del router."""
    global _router
    if _router is None:
        _router = SemanticRouter()
    return _router
